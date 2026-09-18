from __future__ import annotations

import copy
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
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

from .config import ConfigService
from .installer import (
    InstallError,
    delete_staged_portable_folder,
    finalize_staged_registered_integration,
    restore_staged_portable_folder,
    restore_staged_registered_integration,
    stage_portable_editor_folder,
    stage_registered_appimage_integration,
)
from .managed_registry import get_managed_installation, get_managed_versions, record_paths, remove_managed_installation
from .storage_layout import is_within, prune_empty_parents, prune_empty_version_tree, version_root
from .registry import EditorEntry
from .ui_titles import app_dialog_title
from .versioning import appimage_metadata_path

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
    def __init__(self, editor: EditorEntry, portable_root: Path | None, managed: dict) -> None:
        super().__init__(editor, f"Purge {editor.name}", "Review every Suite-managed version that will be removed.")
        layout = QVBoxLayout(self)
        layout.addWidget(self.branding_header())
        warning = QLabel(
            "Purge removes every retained version of this editor from Suite Pythoine. It is intentionally broader than "
            "Remove Version, Remove Portable Folder or Uninstall AppImage."
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
            lines.append(
                f"{item.version}{' — ' + ', '.join(tags) if tags else ''}\n"
                f"  Portable: {item.portable_root if item.has_portable else 'Not present'}\n"
                f"  AppImage: {item.appimage_path if item.has_appimage else 'Not present'}"
            )
        versions.setText("\n\n".join(lines) if lines else "No version inventory is available.")
        versions.setTextFormat(Qt.TextFormat.PlainText)
        versions.setWordWrap(True)
        versions.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(versions)
        note = QLabel("Editor-specific Suite preferences and the complete managed-installation registry entry will also be removed.")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)


class PurgeConfirmPage(PurgeBrandedPage):
    def __init__(self, editor: EditorEntry) -> None:
        super().__init__(editor, "Confirm purge", "This operation is destructive and cannot be undone after cleanup completes.")
        self.setCommitPage(True)
        layout = QVBoxLayout(self)
        layout.addWidget(self.branding_header())
        self.confirm = QCheckBox(
            f"I understand that Purge Editor removes both the portable and Suite-managed installed copies of {editor.name}."
        )
        self.confirm.setChecked(False)
        self.confirm.stateChanged.connect(lambda _state: self.completeChanged.emit())
        layout.addWidget(self.confirm)
        layout.addStretch(1)

    def isComplete(self) -> bool:  # noqa: N802 - Qt API
        return self.confirm.isChecked()


class PurgeProgressPage(PurgeBrandedPage):
    STEPS = (
        "Stage portable editor",
        "Stage installed AppImage integration",
        "Remove Suite registry and editor preferences",
        "Remove staged editor files",
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
    ) -> None:
        super().__init__(editor, "Purging editor", "Suite Pythoine will remove only the paths reviewed on the previous page.")
        self.setFinalPage(True)
        self.portable_root = portable_root
        self.editors_root = editors_root
        self.installed_dir = installed_dir
        self.config = config
        self.refresh_desktop_callback = refresh_desktop_callback
        self.finished_callback = finished_callback
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
        managed_versions = get_managed_versions(data, self.editor.editor_id)
        desktop_parents = set()
        portable_stages: list[tuple[Path, Path]] = []
        integration_stage: list[tuple[Path, Path]] = []
        config_committed = False
        cleanup_started = False
        try:
            self._mark(0, "⟳")
            for item in self.editor.versions:
                if item.has_portable and item.portable_root is not None:
                    portable_stages.append(stage_portable_editor_folder(item.portable_root, self.editors_root))
            self._mark(0, "✓")

            self._mark(1, "⟳")
            for record in managed_versions.values():
                paths = record_paths(record)
                if paths.get("desktop") is not None:
                    desktop_parents.add(paths["desktop"].parent)
                if record.get("appimage_path"):
                    integration_stage.extend(stage_registered_appimage_integration(record, installed_dir=self.installed_dir))
            self._mark(1, "✓")

            self._mark(2, "⟳")
            remove_managed_installation(data, self.editor.editor_id)
            overrides = data.get("editor_overrides", {})
            if isinstance(overrides, dict):
                overrides.pop(self.editor.editor_id, None)
            preferences = data.get("extension_preferences", {})
            if isinstance(preferences, dict):
                for extension in list(preferences):
                    if preferences.get(extension) == self.editor.editor_id:
                        preferences.pop(extension, None)
            if data.get("last_selected_editor") == self.editor.editor_id:
                data["last_selected_editor"] = None
            if not self.config.save():
                raise InstallError("Could not save the Suite Pythoine registry/preferences transaction.")
            config_committed = True
            self._mark(2, "✓")

            cleanup_started = True
            self._mark(3, "⟳")
            finalize_staged_registered_integration(integration_stage)
            for original, staged in portable_stages:
                delete_staged_portable_folder(original, staged, self.editors_root)
                prune_empty_version_tree(original.parent, self.editors_root)
            for item in self.editor.versions:
                if item.has_appimage and not item.managed_record and item.appimage_path is not None:
                    container = version_root(self.editors_root, self.editor.name, item.version)
                    for target in (item.appimage_path, appimage_metadata_path(item.appimage_path), item.icon):
                        if target is None or not target.exists():
                            continue
                        target = target.expanduser().resolve(strict=False)
                        if target.is_symlink() or not is_within(target, container):
                            raise InstallError(f"Refusing to purge unregistered artifact outside its version folder: {target}")
                        target.unlink()
                if item.appimage_path is not None:
                    prune_empty_version_tree(item.appimage_path.parent.parent, self.editors_root)
            self._mark(3, "✓")

            self._mark(4, "⟳")
            for parent in desktop_parents:
                self.refresh_desktop_callback(parent)
            self._mark(4, "✓")
            self.succeeded = True
            self.message.setText(f"Every retained version of {self.editor.name} has been purged from Suite Pythoine.")
        except Exception as exc:
            self.error_message = str(exc)
            if cleanup_started and config_committed:
                self.succeeded = True
                self.message.setText(
                    f"{self.editor.name} was removed from Suite Pythoine, but final disk cleanup was incomplete: {exc}"
                )
                for index in range(self.steps.count()):
                    item = self.steps.item(index)
                    if item is not None and item.text().startswith(("○", "⟳")):
                        self._mark(index, "!")
            else:
                self.message.setText(f"Purge stopped: {exc}")
                try:
                    restore_staged_registered_integration(integration_stage)
                except Exception:
                    pass
                for original, staged in reversed(portable_stages):
                    if staged.exists() and not original.exists():
                        try:
                            restore_staged_portable_folder(original, staged, self.editors_root)
                        except Exception:
                            pass
                if config_committed or data != snapshot:
                    data.clear()
                    data.update(snapshot)
                    self.config.save()
                for index in range(self.steps.count()):
                    item = self.steps.item(index)
                    if item is not None and item.text().startswith(("○", "⟳")):
                        self._mark(index, "✕")
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
        self.setMinimumSize(760, 560)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)
        pixmap = _editor_pixmap(editor, 128)
        if pixmap is not None:
            self.setWindowIcon(QIcon(pixmap))
            self.setPixmap(QWizard.WizardPixmap.LogoPixmap, pixmap)

        self.review_page = PurgeReviewPage(editor, portable_root, managed)
        self.confirm_page = PurgeConfirmPage(editor)
        self.progress_page = PurgeProgressPage(
            editor,
            portable_root=portable_root,
            editors_root=editors_root,
            installed_dir=installed_dir,
            config=config,
            refresh_desktop_callback=refresh_desktop_callback,
            finished_callback=finished_callback,
        )
        self.addPage(self.review_page)
        self.addPage(self.confirm_page)
        self.addPage(self.progress_page)
        self.setButtonText(QWizard.WizardButton.NextButton, "Continue")
        self.setButtonText(QWizard.WizardButton.CommitButton, "Purge")
        self.setButtonText(QWizard.WizardButton.FinishButton, "Finish")


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
