from __future__ import annotations

import copy
import os
import shutil
import uuid
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from .config import ConfigService
from .catalogue.component_catalog import profile_for_id
from .installer import (
    InstallError,
    delete_staged_portable_folder,
    finalize_staged_registered_integration,
    restore_staged_portable_folder,
    restore_staged_registered_integration,
    stage_portable_editor_folder,
    stage_registered_appimage_integration,
)
from .installation_state import get_managed_installation, desktop_selection
from .purge_assets import (
    delete_staged_recovery_folder, restore_staged_recovery_folder,
    stage_recovery_folder, stage_unregistered_version_file, stage_managed_portable_desktop_entry,
)
from .storage_layout import prune_empty_parents, recovery_root, version_root, validate_version_boundary
from .registry import EditorEntry
from .ui_titles import app_dialog_title
from .installer import desktop_entry_path

RefreshDesktopCallback = Callable[[Path], None]
FinishedCallback = Callable[[], None]


class PurgeBrandedPage(QWizardPage):
    def __init__(self, editor: EditorEntry, title: str, subtitle: str = "") -> None:
        super().__init__()
        self.editor = editor
        self.setTitle(title)
        self.setSubTitle(subtitle)

    def branding_header(self) -> QFrame:
        frame = QFrame()
        row = QHBoxLayout(frame)
        row.setContentsMargins(0, 0, 0, 8)
        pixmap = _editor_pixmap(self.editor, 88)
        if pixmap is not None:
            icon = QLabel()
            icon.setPixmap(pixmap)
            icon.setFixedSize(96, 96)
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row.addWidget(icon)
        text = QVBoxLayout()
        name = QLabel(self.editor.name)
        font = name.font()
        font.setBold(True)
        font.setPointSize(max(font.pointSize() + 4, 15))
        name.setFont(font)
        text.addWidget(name)
        version = self.editor.installed_version or self.editor.source_version or "Unknown"
        text.addWidget(_plain_label(f"Version {version}"))
        if self.editor.description:
            text.addWidget(_plain_label(self.editor.description))
        text.addStretch(1)
        row.addLayout(text, 1)
        return frame


class PurgeReviewPage(PurgeBrandedPage):
    def __init__(self, editor: EditorEntry, portable_root: Path | None, managed: dict, editors_root: Path) -> None:
        super().__init__(editor, f"Purge {editor.name}", "Review every Suite-managed version that will be removed.")
        layout = QVBoxLayout(self)
        layout.addWidget(self.branding_header())
        warning = QLabel(
            "Purge removes all retained Portable, AppImage and Recovery assets for every managed version. "
            "The original source ZIP and its Recovery metadata will be deleted too. This is broader than "
            "Uninstall Version, Remove Portable or Remove AppImage."
        )
        warning.setWordWrap(True)
        layout.addWidget(warning)

        versions = QLabel()
        lines = []
        for item in editor.versions:
            tags = []
            if item.version == editor.active_version:
                tags.append("Active")
            if item.desktop_integrated:
                tags.append("Desktop integrated")
            recovered = item.recovery_dir or recovery_root(editors_root, editor.name, item.version)
            lines.append(
                f"{item.version}{' — ' + ', '.join(tags) if tags else ''}\n"
                f"  Portable: {item.portable_root if item.has_portable else 'Not present'}\n"
                f"  AppImage: {item.appimage_path if item.has_appimage else 'Not present'}\n"
                f"  Recovery: {recovered if recovered.is_dir() or recovered.is_symlink() else 'Not present'}"
            )
        versions.setText("\n\n".join(lines) if lines else "No version inventory is available.")
        versions.setTextFormat(Qt.TextFormat.PlainText)
        versions.setWordWrap(True)
        versions.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        inventory_scroll = QScrollArea()
        inventory_scroll.setWidgetResizable(True)
        inventory_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inventory_scroll.setFrameShape(QFrame.Shape.StyledPanel)
        inventory_body = QWidget()
        inventory_layout = QVBoxLayout(inventory_body)
        inventory_layout.setContentsMargins(8, 8, 8, 8)
        inventory_layout.addWidget(versions)
        inventory_layout.addStretch(1)
        inventory_scroll.setWidget(inventory_body)
        layout.addWidget(inventory_scroll, 1)
        self.remove_preferences = QCheckBox("Also remove this application's preferences")
        self.remove_preferences.setChecked(False)
        layout.addWidget(self.remove_preferences)
        note = QLabel(
            "Suite routing/selection references to the purged application are cleaned automatically. "
            "The application's own trusted preferences folder is preserved unless this option is checked. "
            "User documents and the trusted catalogue are never included."
        )
        note.setWordWrap(True)
        layout.addWidget(note)


class PurgeConfirmPage(PurgeBrandedPage):
    def __init__(self, editor: EditorEntry) -> None:
        super().__init__(editor, "Confirm purge", "This operation is destructive and cannot be undone after cleanup completes.")
        self.setCommitPage(True)
        layout = QVBoxLayout(self)
        layout.addWidget(self.branding_header())
        self.confirm = QCheckBox(
            f"I understand that Purge permanently removes Portable, AppImage and retained Recovery archives of {editor.name}."
        )
        self.confirm.setChecked(False)
        self.confirm.stateChanged.connect(lambda _state: self.completeChanged.emit())
        layout.addWidget(self.confirm)
        layout.addStretch(1)

    def isComplete(self) -> bool:  # noqa: N802 - Qt API
        return self.confirm.isChecked()


class PurgeProgressPage(PurgeBrandedPage):
    STEPS = (
        "Validate every exact-version directory and the desktop launcher",
        "Stage full version directories and verified launcher",
        "Stage optional application preferences",
        "Update Suite routing and selection references",
        "Finalize all staged assets",
        "Refresh desktop integration",
    )

    def __init__(
        self,
        editor: EditorEntry,
        *,
        portable_root: Path | None,
        editors_root: Path,
        installed_dir: Path,
        config: ConfigService,
        refresh_desktop_callback: RefreshDesktopCallback,
        finished_callback: FinishedCallback,
        remove_preferences_callback: Callable[[], bool],
    ) -> None:
        super().__init__(editor, "Purging application", "Suite Pythoine will remove only the paths reviewed on the previous page.")
        self.setFinalPage(True)
        self.portable_root = portable_root
        self.editors_root = editors_root
        self.installed_dir = installed_dir
        self.config = config
        self.refresh_desktop_callback = refresh_desktop_callback
        self.finished_callback = finished_callback
        self.remove_preferences_callback = remove_preferences_callback
        self.started = False
        self.finished = False
        self.succeeded = False
        self.error_message = ""

        layout = QVBoxLayout(self)
        layout.addWidget(self.branding_header())
        self.steps = QListWidget()
        self.steps.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for label in self.STEPS:
            self.steps.addItem(QListWidgetItem(f"○  {label}"))
        layout.addWidget(self.steps, 1)
        self.message = QLabel("Ready to purge.")
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        self.message.setWordWrap(True)
        layout.addWidget(self.message)

    def initializePage(self) -> None:  # noqa: N802 - Qt API
        if self.started:
            return
        self.started = True
        wizard = self.wizard()
        if wizard is not None:
            wizard.setOption(QWizard.WizardOption.DisabledBackButtonOnLastPage, True)
        QTimer.singleShot(0, self._run)

    def isComplete(self) -> bool:  # noqa: N802 - Qt API
        return self.finished

    def _mark(self, index: int, symbol: str) -> None:
        item = self.steps.item(index)
        if item is not None:
            item.setText(f"{symbol}  {self.STEPS[index]}")

    def _run(self) -> None:
        data = self.config.as_dict()
        snapshot = copy.deepcopy(data)
        root = self.editors_root.expanduser().resolve(strict=False)
        stages: list[tuple[Path, Path]] = []
        desktop = desktop_entry_path(self.editor.editor_id)
        desktop_stage: tuple[Path, Path] | None = None
        preferences_stage: tuple[Path, Path] | None = None
        remove_preferences = bool(self.remove_preferences_callback())
        config_committed = False
        cleanup_started = False
        try:
            self._mark(0, '⟳')
            if self.editor.desktop_issue in {'broken', 'legacy-launcher', 'external-target'}:
                raise InstallError('Existing desktop launcher requires explicit repair before Purge. It will not be overwritten or removed by inference.')
            originals: list[Path] = []
            for item in self.editor.versions:
                if item.validation_issue:
                    raise InstallError(f'{item.version}: {item.validation_issue}')
                # Source paths are what discovery actually validated. Do not
                # assume every legacy component uses the catalogue display name
                # as the literal directory name.
                if item.portable_root is not None:
                    version_dir = item.portable_root.parent
                elif item.appimage_path is not None:
                    version_dir = item.appimage_path.parent.parent
                elif item.recovery_dir is not None:
                    version_dir = item.recovery_dir.parent
                else:
                    raise InstallError(f'Cannot establish a physical version folder for {item.version}.')
                validate_version_boundary(version_dir, root)
                if (version_dir.is_symlink() or not version_dir.is_dir()
                        or version_dir.name != item.version or version_dir.parent.parent.resolve(strict=False) != root):
                    raise InstallError(f'Unsafe or mismatched version root: {version_dir}')
                if version_dir in originals:
                    raise InstallError(f'Duplicate physical version entry: {version_dir}')
                originals.append(version_dir)
            state, _version, _runtime = desktop_selection(
                self.editor.editor_id, {v.version:v for v in self.editor.versions}, root)
            if state not in {'ready', 'missing'}:
                raise InstallError('Desktop target changed during Purge preflight; repair it explicitly first.')
            self._mark(0, '✓')
            self._mark(1, '⟳')
            for original in originals:
                staged = original.with_name('.' + original.name + '.purge-stage-' + uuid.uuid4().hex[:10])
                if staged.exists() or staged.is_symlink():
                    raise InstallError(f'Purge stage already occupied: {staged}')
                os.replace(original, staged)
                stages.append((original, staged))
            if state == 'ready':
                if not desktop.is_file() or desktop.is_symlink():
                    raise InstallError('Verified desktop launcher changed during Purge staging.')
                alternate = desktop.with_name('.' + desktop.name + '.purge-stage-' + uuid.uuid4().hex[:10])
                os.replace(desktop, alternate)
                desktop_stage = (desktop, alternate)
            self._mark(1, '✓')
            self._mark(2, '⟳')
            if remove_preferences:
                preferences = _component_preferences_path(self.editor)
                if preferences is not None and (preferences.exists() or preferences.is_symlink()):
                    if preferences.is_symlink() or not preferences.is_dir():
                        raise InstallError(f'Application preferences path is not a safe directory: {preferences}')
                    staged_preferences = preferences.with_name(
                        '.' + preferences.name + '.purge-stage-' + uuid.uuid4().hex[:10]
                    )
                    if staged_preferences.exists() or staged_preferences.is_symlink():
                        raise InstallError(f'Preferences staging path already exists: {staged_preferences}')
                    os.replace(preferences, staged_preferences)
                    preferences_stage = (preferences, staged_preferences)
            self._mark(2, '✓')
            self._mark(3, '⟳')
            overrides = data.get('editor_overrides', {})
            if isinstance(overrides, dict):
                overrides.pop(self.editor.editor_id, None)
            # Purging application-specific choices must NOT unroute Suite's
            # globally trusted catalogue MIME/extension capabilities.
            prefs = data.get('extension_preferences', {})
            if isinstance(prefs, dict):
                for extension in list(prefs):
                    if prefs[extension] == self.editor.editor_id:
                        prefs.pop(extension, None)
            if data.get('last_selected_editor') == self.editor.editor_id:
                data['last_selected_editor'] = None
            data['routing_index'] = {}
            if not self.config.save():
                raise InstallError('Could not save cleared Suite routing/selection references. All installations will be restored.')
            config_committed = True
            self._mark(3, '✓')
            cleanup_started = True
            self._mark(4, '⟳')
            # After this point deletion can be irreversible. Never claim a
            # complete Purge if any staged artifact still survives.
            for _original, staged in stages:
                shutil.rmtree(staged)
            if desktop_stage is not None:
                desktop_stage[1].unlink()
            if preferences_stage is not None:
                shutil.rmtree(preferences_stage[1])
            for original in originals:
                prune_empty_parents(original.parent, root)
            remaining = [str(s) for _,s in stages if s.exists() or s.is_symlink()]
            if desktop_stage is not None and desktop_stage[1].exists():
                remaining.append(str(desktop_stage[1]))
            if preferences_stage is not None and preferences_stage[1].exists():
                remaining.append(str(preferences_stage[1]))
            if remaining:
                raise InstallError('Purge cleanup left staged assets: ' + ', '.join(remaining))
            self._mark(4, '✓')
            self._mark(5, '⟳')
            if desktop_stage is not None:
                self.refresh_desktop_callback(desktop.parent)
            self._mark(5, '✓')
            self.succeeded = True
            suffix = ' Application preferences were also removed.' if remove_preferences else ' Application preferences were preserved.'
            self.message.setText(f'Purged every validated {self.editor.name} version, retained Recovery ZIP and verified launcher.' + suffix)
        except Exception as exc:
            self.error_message = str(exc)
            if not cleanup_started:
                rollback_errors: list[str] = []
                if desktop_stage is not None and desktop_stage[1].exists():
                    try:
                        os.replace(desktop_stage[1], desktop_stage[0])
                    except OSError as e:
                        rollback_errors.append(f'{desktop_stage[1]}: {e}')
                if preferences_stage is not None and preferences_stage[1].exists():
                    try:
                        os.replace(preferences_stage[1], preferences_stage[0])
                    except OSError as e:
                        rollback_errors.append(f'{preferences_stage[1]}: {e}')
                for original, staged in reversed(stages):
                    if staged.exists():
                        try:
                            os.replace(staged, original)
                        except OSError as e:
                            rollback_errors.append(f'{staged}: {e}')
                data.clear(); data.update(snapshot)
                if not self.config.save():
                    rollback_errors.append('Could not restore preferences')
                if rollback_errors:
                    self.error_message += ' | Rollback incomplete: ' + '; '.join(rollback_errors)
                self.message.setText('Purge stopped before cleanup: ' + self.error_message)
            else:
                # A failed rmtree may already have deleted some files.
                # Preserve any remaining stage, and disclose its actual path.
                pending = [str(s) for _,s in stages if s.exists() or s.is_symlink()]
                if desktop_stage is not None and desktop_stage[1].exists():
                    pending.append(str(desktop_stage[1]))
                if preferences_stage is not None and preferences_stage[1].exists():
                    pending.append(str(preferences_stage[1]))
                self.message.setText('Purge INCOMPLETE; inspect remaining staged paths manually: '
                                     + self.error_message + '\n' + '\n'.join(pending))
            for i in range(len(self.STEPS)):
                item = self.steps.item(i)
                if item is not None and item.text().startswith(('○', '⟳')):
                    self._mark(i, '✕')
        finally:
            self.finished = True
            try:
                self.finished_callback()
            finally:
                self.completeChanged.emit()


class PurgeEditorWizard(QWizard):
    def __init__(
        self,
        parent,
        editor: EditorEntry,
        *,
        portable_root: Path | None,
        editors_root: Path,
        installed_dir: Path,
        config: ConfigService,
        refresh_desktop_callback: RefreshDesktopCallback,
        finished_callback: FinishedCallback,
    ) -> None:
        super().__init__(parent)
        managed = get_managed_installation(config.as_dict(), editor.editor_id)
        self.setWindowTitle(app_dialog_title(f"Purge {editor.name}"))
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setMinimumSize(820, 640)
        self.resize(980, 800)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)
        pixmap = _editor_pixmap(editor, 128)
        if pixmap is not None:
            self.setWindowIcon(QIcon(pixmap))
            self.setPixmap(QWizard.WizardPixmap.LogoPixmap, pixmap)

        self.review_page = PurgeReviewPage(editor, portable_root, managed, editors_root)
        self.confirm_page = PurgeConfirmPage(editor)
        self.progress_page = PurgeProgressPage(
            editor,
            portable_root=portable_root,
            editors_root=editors_root,
            installed_dir=installed_dir,
            config=config,
            refresh_desktop_callback=refresh_desktop_callback,
            finished_callback=finished_callback,
            remove_preferences_callback=lambda: self.review_page.remove_preferences.isChecked(),
        )
        self.addPage(self.review_page)
        self.addPage(self.confirm_page)
        self.addPage(self.progress_page)
        self.setButtonText(QWizard.WizardButton.NextButton, "Continue")
        self.setButtonText(QWizard.WizardButton.CommitButton, "Purge")
        self.setButtonText(QWizard.WizardButton.FinishButton, "Finish")


def _component_preferences_path(editor: EditorEntry) -> Path | None:
    """Return only the trusted catalogue-controlled application config folder."""
    profile = profile_for_id(editor.editor_id)
    subdir = profile.config_subdir if profile is not None else None
    if not subdir:
        return None
    if (Path(subdir).name != subdir or subdir in {".", "..", "suite-pythoine"}
            or "/" in subdir or "\\" in subdir):
        raise InstallError(f"Unsafe configured preferences directory: {subdir}")
    base = (Path(os.environ.get("APPDATA")) if os.name == "nt" and os.environ.get("APPDATA")
            else Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"))
    config_base = (base / "brunonlinespace").expanduser().absolute()
    return config_base / subdir


def _plain_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def _editor_pixmap(editor: EditorEntry, size: int) -> QPixmap | None:
    if editor.icon is None or not editor.icon.is_file():
        return None
    pixmap = QPixmap(str(editor.icon))
    if pixmap.isNull():
        return None
    return pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
