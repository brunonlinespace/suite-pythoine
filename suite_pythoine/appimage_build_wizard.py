from __future__ import annotations

from pathlib import Path
import copy
import os
import shutil
import stat
import sys
import tempfile
from typing import Callable

from PyQt6.QtCore import QProcess, QTimer, Qt
from PyQt6.QtGui import QFontDatabase, QIcon, QPixmap, QTextCursor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWizard,
    QWizardPage,
    QWidget,
)

from .appimage_inspection import inspect_appimage
from .config import ConfigService
from .installer import (
    InstallError,
    clean_build_dirs,
    find_appimage_build_script,
    find_built_appimage,
    install_appimage,
    install_icon,
    snapshot_appimages,
)
from .installation_state import (
    get_managed_group,
    record_paths,
    set_active_version,
    set_desktop_version,
)
from .registry import EditorEntry, EditorVersionInfo, inspect_editor_root
from .runtime.runtime_launcher import RuntimeLauncher
from .versioning import appimage_metadata_path
from .installer import desktop_entry_path
from .ui_titles import app_dialog_title


RegisterCallback = Callable[..., tuple[dict, Path]]
ReconcileCallback = Callable[[EditorEntry, EditorVersionInfo, tuple[str, ...] | None], tuple[str | None, Path | None, bool]]
FinalizeDesktopCallback = Callable[[EditorEntry, EditorVersionInfo, str | None, Path | None, bool], None]
RefreshDesktopCallback = Callable[[Path | None], None]
FinishedCallback = Callable[[], None]


STEP_LABELS = (
    ("identity", "Verify exact Portable identity"),
    ("prepare", "Prepare isolated AppImage build"),
    ("build", "Build AppImage"),
    ("verify", "Verify exact build artifact"),
    ("install", "Install managed AppImage"),
    ("registry", "Record AppImage verification metadata"),
    ("desktop", "Reconcile active runtime"),
    ("cleanup", "Clean temporary build output"),
)


def _plain(text: object, *, wrap: bool = True) -> QLabel:
    label = QLabel(str(text))
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    label.setWordWrap(wrap)
    label.setMinimumWidth(0)
    label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    return label


def _component_pixmap(editor: EditorEntry, version: EditorVersionInfo, size: int) -> QPixmap | None:
    for candidate in (version.icon, editor.icon):
        if candidate is None:
            continue
        try:
            path = Path(candidate).expanduser().resolve(strict=False)
        except (OSError, ValueError):
            continue
        if not path.is_file():
            continue
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            continue
        return pixmap.scaled(
            size,
            size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    return None


class BuildBrandedPage(QWizardPage):
    """Direct-build page using the same visual language as the source installer."""

    def __init__(self, wizard: "ManagedAppImageBuildWizard", title: str, subtitle: str = "") -> None:
        super().__init__(wizard)
        self.owner = wizard
        self.setTitle(title)
        self.setSubTitle(subtitle)

    def branding_header(self) -> QFrame:
        frame = QFrame()
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 8)
        pixmap = _component_pixmap(self.owner.editor, self.owner.version, 88)
        if pixmap is not None:
            icon = QLabel()
            icon.setPixmap(pixmap)
            icon.setFixedSize(96, 96)
            icon.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        text = QVBoxLayout()
        name = QLabel(self.owner.editor.name)
        font = name.font()
        font.setBold(True)
        font.setPointSize(max(font.pointSize() + 4, 15))
        name.setFont(font)
        text.addWidget(name)
        version = QLabel(f"Version {self.owner.version.version}")
        version.setTextFormat(Qt.TextFormat.PlainText)
        text.addWidget(version)
        if self.owner.editor.description:
            description = QLabel(self.owner.editor.description)
            description.setTextFormat(Qt.TextFormat.PlainText)
            description.setWordWrap(True)
            text.addWidget(description)
        text.addStretch(1)
        layout.addLayout(text, 1)
        return frame


def _scrollable_build_page_layout(page: QWizardPage) -> QVBoxLayout:
    outer = QVBoxLayout(page)
    outer.setContentsMargins(0, 0, 0, 0)
    scroll = QScrollArea(page)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    body = QWidget()
    layout = QVBoxLayout(body)
    layout.setContentsMargins(8, 6, 8, 6)
    layout.setSpacing(10)
    scroll.setWidget(body)
    outer.addWidget(scroll)
    page._suite_scroll = scroll
    return layout


class BuildPlanPage(BuildBrandedPage):
    def __init__(self, wizard: "ManagedAppImageBuildWizard") -> None:
        super().__init__(
            wizard,
            "Rebuild managed AppImage" if wizard.rebuild else "Build managed AppImage",
            "Build this exact installed Portable version without reinstalling or changing version selection.",
        )
        layout = _scrollable_build_page_layout(self)
        layout.addWidget(self.branding_header())

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        form.addRow("Version:", _plain(wizard.version.version, wrap=False))
        form.addRow("Source:", _plain(wizard.portable_root, wrap=False))
        form.addRow("Builder:", _plain(wizard.build_script or "Not detected", wrap=False))
        form.addRow("Destination:", _plain(wizard.destination_root, wrap=False))
        form.addRow("Operation:", _plain("Rebuild existing managed AppImage" if wizard.rebuild else "Build new managed AppImage", wrap=False))
        layout.addLayout(form)

        if wizard.rebuild:
            note = QLabel(
                "The existing managed AppImage remains the rollback copy until the replacement has built, "
                "verified, installed, registered, and committed successfully."
            )
        else:
            note = QLabel(
                "The selected Portable version is the only build source. Suite Pythoine will not compare, "
                "upgrade, downgrade, activate, or remove any other installed version."
            )
        note.setWordWrap(True)
        layout.addWidget(note)

        options = QGroupBox("Troubleshooting")
        option_layout = QVBoxLayout(options)
        wizard.keep_failed_build_files = QCheckBox("Keep temporary AppImage build/output files if the build fails")
        wizard.keep_failed_build_files.setChecked(False)
        option_layout.addWidget(wizard.keep_failed_build_files)
        layout.addWidget(options)
        layout.addStretch(1)


class BuildProgressPage(BuildBrandedPage):
    def __init__(self, wizard: "ManagedAppImageBuildWizard") -> None:
        super().__init__(
            wizard,
            f"{'Rebuilding' if wizard.rebuild else 'Building'} {wizard.editor.name}",
            "The checklist is the build state; technical build output remains available below.",
        )
        layout = QVBoxLayout(self)
        layout.addWidget(self.branding_header())
        self.steps = QListWidget()
        self.steps.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.step_items: dict[str, QListWidgetItem] = {}
        for key, label in STEP_LABELS:
            item = QListWidgetItem(f"○  {label}")
            self.steps.addItem(item)
            self.step_items[key] = item
        self.steps.setMinimumHeight(180)
        self.steps.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.steps, 1)

        self.result_label = QLabel("")
        self.result_label.setTextFormat(Qt.TextFormat.PlainText)
        self.result_label.setWordWrap(True)
        self.result_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        layout.addWidget(self.result_label)

        self.command_label = QLabel("Command: waiting for build to begin")
        self.command_label.setTextFormat(Qt.TextFormat.PlainText)
        self.command_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.command_label.setWordWrap(True)
        layout.addWidget(self.command_label)

        self.toggle_output = QPushButton("Show technical details")
        self.toggle_output.setCheckable(True)
        self.toggle_output.toggled.connect(self._toggle_output)
        layout.addWidget(self.toggle_output)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setVisible(False)
        self.output.setMinimumHeight(150)
        self.output.setMaximumHeight(260)
        self.output.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.output.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        layout.addWidget(self.output, 1)
        self._collapsed_wizard_size = None
        self._collapsed_steps_height = None
        self._started_once = False

    def isFinalPage(self) -> bool:  # noqa: N802 - Qt API
        return True

    def initializePage(self) -> None:  # noqa: N802 - Qt API
        if self._started_once:
            return
        self._started_once = True
        self.owner._set_buttons_building(True)
        QTimer.singleShot(0, self.owner.begin_build)

    def _toggle_output(self, checked: bool) -> None:
        wizard = self.wizard()
        if checked:
            self._collapsed_steps_height = max(180, self.steps.height())
            self.steps.setMinimumHeight(self._collapsed_steps_height)
            self.steps.setMaximumHeight(16777215)
            if wizard is not None:
                self._collapsed_wizard_size = wizard.size()
            self.output.setVisible(True)
            self.toggle_output.setText("Hide technical details")
            QTimer.singleShot(0, self._grow_wizard_for_output)
        else:
            self.output.setVisible(False)
            self.steps.setMinimumHeight(180)
            self.steps.setMaximumHeight(16777215)
            self.toggle_output.setText("Show technical details")
            if wizard is not None and self._collapsed_wizard_size is not None:
                wizard.resize(self._collapsed_wizard_size)
            self._collapsed_wizard_size = None
            self._collapsed_steps_height = None

    def _grow_wizard_for_output(self) -> None:
        wizard = self.wizard()
        if wizard is None or self._collapsed_wizard_size is None or not self.output.isVisible():
            return
        extra = max(170, min(260, self.output.sizeHint().height()))
        target_height = self._collapsed_wizard_size.height() + extra
        screen = wizard.screen()
        if screen is not None:
            available = screen.availableGeometry()
            target_height = min(target_height, max(self._collapsed_wizard_size.height(), available.height() - 32))
        wizard.resize(self._collapsed_wizard_size.width(), target_height)


class ManagedAppImageBuildWizard(QWizard):
    """Build/rebuild one managed AppImage from one exact managed Portable version."""

    def __init__(
        self,
        parent,
        editor: EditorEntry,
        version: EditorVersionInfo,
        *,
        editors_root: Path,
        installed_dir: Path,
        config: ConfigService,
        launcher: RuntimeLauncher,
        register_callback: RegisterCallback,
        reconcile_callback: ReconcileCallback,
        finalize_desktop_callback: FinalizeDesktopCallback,
        refresh_desktop_callback: RefreshDesktopCallback,
        finished_callback: FinishedCallback,
    ) -> None:
        super().__init__(parent)
        self.editor = editor
        self.version = version
        self.editors_root = editors_root.expanduser().resolve(strict=False)
        self.installed_dir = installed_dir.expanduser().resolve(strict=False)
        self.config = config
        self.launcher = launcher
        self.register_callback = register_callback
        self.reconcile_callback = reconcile_callback
        self.finalize_desktop_callback = finalize_desktop_callback
        self.refresh_desktop_callback = refresh_desktop_callback
        self.finished_callback = finished_callback

        if version.portable_root is None:
            raise InstallError("The selected version has no Portable source root.")
        self.portable_root = version.portable_root.expanduser().resolve(strict=False)
        self.build_script = find_appimage_build_script(self.portable_root)
        self.destination_root = self.installed_dir / editor.name / version.version / "AppImage"
        self.rebuild = bool(version.has_appimage)

        self.keep_failed_build_files: QCheckBox
        self.progress = BuildProgressPage(self)
        self.addPage(BuildPlanPage(self))
        self.addPage(self.progress)
        self.setWindowTitle(app_dialog_title("Build AppImage" if not self.rebuild else "Rebuild AppImage"))
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setMinimumSize(820, 640)
        self.resize(980, 800)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)
        self.setOption(QWizard.WizardOption.NoBackButtonOnLastPage, True)

        pixmap = _component_pixmap(editor, version, 128)
        if pixmap is not None:
            self.setWindowIcon(QIcon(pixmap))
            self.setPixmap(QWizard.WizardPixmap.LogoPixmap, pixmap)

        self.started = False
        self.finished = False
        self.succeeded = False
        self.error_message = ""
        self.installed_appimage: Path | None = None
        self.installed_icon: Path | None = None
        self.source_editor: EditorEntry | None = None
        self._process: QProcess | None = None
        self._before_build: dict[str, tuple[int, int]] = {}
        self._config_snapshot: dict | None = None
        self._pre_active_version = editor.active_version
        self._pre_launch_mode = editor.launch_mode
        self._pre_command: tuple[str, ...] | None = None
        self._pre_runtime: str | None = None
        self._desktop_path = desktop_entry_path(editor.editor_id)
        self._desktop_existed = False
        self._desktop_backup: bytes | None = None
        self._desktop_mode: int | None = None
        self._backup_temp: tempfile.TemporaryDirectory | None = None
        self._backup_files: dict[str, tuple[Path, Path]] = {}
        self._old_appimage: Path | None = None
        self._old_icon: Path | None = None
        self._new_metadata: Path | None = None
        self._desktop_result: Path | None = None
        self._desktop_runtime_after: str | None = None
        self._desktop_changed = False

    def _set_step(self, key: str, state: str, detail: str = "") -> None:
        prefixes = {"pending": "○", "active": "⟳", "done": "✓", "skip": "—", "fail": "✗"}
        label = dict(STEP_LABELS)[key]
        suffix = f" — {detail}" if detail else ""
        self.progress.step_items[key].setText(f"{prefixes.get(state, '○')}  {label}{suffix}")
        self.progress.steps.scrollToItem(self.progress.step_items[key])

    def _log(self, text: str) -> None:
        if not text:
            return
        self.progress.output.moveCursor(QTextCursor.MoveOperation.End)
        self.progress.output.insertPlainText(text if text.endswith("\n") else text + "\n")
        self.progress.output.moveCursor(QTextCursor.MoveOperation.End)

    def _set_buttons_building(self, building: bool) -> None:
        for which in (QWizard.WizardButton.BackButton, QWizard.WizardButton.NextButton, QWizard.WizardButton.FinishButton):
            button = self.button(which)
            if button is not None:
                button.setEnabled(not building and (which != QWizard.WizardButton.FinishButton or self.finished))
        cancel = self.button(QWizard.WizardButton.CancelButton)
        if cancel is not None:
            cancel.setEnabled(not building)

    def _active_runtime_snapshot(self) -> None:
        if self.editor.active_version != self.version.version:
            self._pre_command = None
            self._pre_runtime = None
            return
        selected = self.editor.command()
        self._pre_command = selected
        if selected and self.version.portable_command and selected == self.version.portable_command:
            self._pre_runtime = "Portable"
        elif selected and self.version.installed_command and selected == self.version.installed_command:
            self._pre_runtime = "AppImage"
        else:
            self._pre_runtime = None

    def _backup_path(self, key: str, path: Path | None) -> None:
        if path is None or not path.is_file():
            return
        if self._backup_temp is None:
            self._backup_temp = tempfile.TemporaryDirectory(prefix="suite-pythoine-appimage-backup-")
        backup = Path(self._backup_temp.name) / key
        shutil.copy2(path, backup)
        self._backup_files[key] = (path, backup)

    def _prepare_rollback_state(self) -> None:
        self._config_snapshot = copy.deepcopy(self.config.as_dict())
        self._active_runtime_snapshot()
        if self._desktop_path.is_file():
            self._desktop_existed = True
            self._desktop_backup = self._desktop_path.read_bytes()
            self._desktop_mode = self._desktop_path.stat().st_mode

        # The exact real artifact, not a generic version/desktop record, is the
        # replacement target. This closes the Portable-desktop ownership hole.
        self._old_appimage = self.version.appimage_path if self.version.has_appimage else None
        if self._old_appimage is not None:
            expected = self.editors_root / self.editor.name / self.version.version / 'AppImage'
            if (self._old_appimage.is_symlink() or not self._old_appimage.resolve(strict=False).is_relative_to(expected.resolve(strict=False))):
                raise InstallError('Refusing to replace an AppImage outside the exact managed version.')
        self._old_icon = self.version.icon if self.version.icon is not None and self.version.icon.is_file() else None
        self._backup_path("appimage", self._old_appimage)
        if self._old_appimage is not None:
            self._backup_path("metadata", appimage_metadata_path(self._old_appimage))
        self._backup_path("icon", self._old_icon)

    def _preflight(self) -> None:
        if os.name == "nt" or not sys.platform.startswith("linux"):
            raise InstallError("Managed AppImage building is available only on Linux.")
        if not self.portable_root.is_dir() or self.portable_root.is_symlink():
            raise InstallError("The selected Portable source folder is missing or unsafe.")
        try:
            relative = self.portable_root.relative_to(self.editors_root)
        except ValueError as exc:
            raise InstallError("The selected Portable source is outside Suite Pythoine's managed Applications folder.") from exc
        if not relative.parts:
            raise InstallError("The selected Portable source root is invalid.")

        fresh = inspect_editor_root(
            self.portable_root,
            config=self.config.as_dict(),
            installed_dir=self.installed_dir,
            python_executable=self.launcher.python_executable(),
        )
        if fresh.editor_id != self.editor.editor_id:
            raise InstallError(
                f"Portable identity mismatch: inventory says {self.editor.editor_id}, source identifies {fresh.editor_id}."
            )
        if not fresh.source_version or fresh.source_version.casefold() != self.version.version.casefold():
            raise InstallError(
                f"Portable version mismatch: inventory says {self.version.version}, source identifies {fresh.source_version or 'Unknown'}."
            )
        self.source_editor = fresh

        self.build_script = find_appimage_build_script(self.portable_root)
        if self.build_script is None or not self.build_script.is_file() or self.build_script.is_symlink():
            raise InstallError("No supported AppImage builder was found inside this exact Portable version.")
        try:
            self.build_script.resolve(strict=False).relative_to(self.portable_root)
        except ValueError as exc:
            raise InstallError("The detected AppImage builder resolves outside the selected Portable version.") from exc
        try:
            self.build_script.chmod(self.build_script.stat().st_mode | stat.S_IXUSR)
        except OSError as exc:
            raise InstallError(f"Could not make AppImage builder executable: {exc}") from exc

    def begin_build(self) -> None:
        if self.started:
            return
        self.started = True
        self._set_buttons_building(True)
        try:
            self._set_step("identity", "active")
            self._preflight()
            self._set_step("identity", "done", f"{self.editor.editor_id} {self.version.version}")

            self._set_step("prepare", "active")
            self._prepare_rollback_state()
            self._before_build = snapshot_appimages(self.portable_root)
            self._set_step("prepare", "done", self.build_script.name if self.build_script else "builder")
            self._start_process()
        except (InstallError, OSError, ValueError, shutil.Error) as exc:
            self._fail("identity" if self.source_editor is None else "prepare", str(exc), rollback=False)

    def _start_process(self) -> None:
        assert self.build_script is not None
        self._set_step("build", "active")
        self.progress.command_label.setText(f"Command: {self.build_script}")
        self._log(f"$ {self.build_script}")
        process = QProcess(self)
        self._process = process
        process.setProgram(str(self.build_script))
        process.setWorkingDirectory(str(self.portable_root))
        process.setProcessEnvironment(self.launcher.process_environment())
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(self._read_output)
        process.finished.connect(self._process_finished)
        process.errorOccurred.connect(self._process_error)
        process.start()

    def _read_output(self) -> None:
        if self._process is None:
            return
        data = bytes(self._process.readAllStandardOutput()).decode("utf-8", "replace")
        if data:
            self._log(data.rstrip("\n"))

    def _process_error(self, error) -> None:
        if self._process is None or self.finished:
            return
        self._read_output()
        if error == QProcess.ProcessError.FailedToStart:
            self._cleanup_failed_build()
            self._fail("build", f"Could not start AppImage builder: {self.build_script}", rollback=False)

    def _process_finished(self, code: int, status: QProcess.ExitStatus) -> None:
        self._read_output()
        if self.finished:
            return
        if status != QProcess.ExitStatus.NormalExit or code != 0:
            cleanup_note = self._cleanup_failed_build()
            self._fail("build", f"AppImage builder exited with code {code}.{cleanup_note}", rollback=False)
            return
        self._set_step("build", "done")
        try:
            self._commit_built_artifact()
        except (InstallError, OSError, ValueError, shutil.Error) as exc:
            active = next(
                (key for key in ("verify", "install", "registry", "desktop", "cleanup") if self.progress.step_items[key].text().startswith("⟳")),
                "verify",
            )
            self._cleanup_failed_build()
            self._fail(active, str(exc), rollback=True)

    def _preserve_version_selection(self) -> None:
        data = self.config.as_dict()
        overrides = data.setdefault("editor_overrides", {})
        if not isinstance(overrides, dict):
            overrides = {}
            data["editor_overrides"] = overrides
        override = overrides.setdefault(self.editor.editor_id, {})
        if not isinstance(override, dict):
            override = {}
            overrides[self.editor.editor_id] = override
        if self._pre_active_version:
            override["active_version"] = self._pre_active_version
            set_active_version(data, self.editor.editor_id, self._pre_active_version)
        data["routing_index"] = {}

    def _restore_existing_desktop_claim(self) -> None:
        if self._config_snapshot is None:
            return
        old_group = get_managed_group(self._config_snapshot, self.editor.editor_id)
        if old_group.get("desktop_version") != self.version.version:
            return
        if not self._desktop_path.is_file():
            return
        set_desktop_version(self.config.as_dict(), self.editor.editor_id, self.version.version, self._desktop_path)

    def _commit_built_artifact(self) -> None:
        assert self.source_editor is not None
        assert self.build_script is not None

        self._set_step("verify", "active")
        artifact = find_built_appimage(
            self.portable_root,
            build_script=self.build_script,
            before=self._before_build,
            expected_version=self.version.version,
        )
        if artifact is None:
            raise InstallError("The build completed, but no AppImage created or changed by this build was found. Older artifacts were ignored.")
        inspection = inspect_appimage(artifact)
        if inspection.editor_id != self.editor.editor_id:
            raise InstallError(
                f"Built AppImage identity mismatch: expected {self.editor.editor_id}, artifact identifies {inspection.editor_id}."
            )
        if inspection.version.casefold() != self.version.version.casefold():
            raise InstallError(
                f"Built AppImage version mismatch: expected {self.version.version}, artifact identifies {inspection.version}."
            )
        self._set_step("verify", "done", artifact.name)
        self._log(f"[suite] Verified exact build artifact: {artifact}")

        self._set_step("install", "active")
        installed = install_appimage(
            artifact,
            self.installed_dir,
            editor_id=self.editor.editor_id,
            name=self.editor.name,
            version=self.version.version,
            architecture=inspection.architecture,
        )
        self.installed_appimage = installed
        self.installed_icon = install_icon(
            self.source_editor.icon,
            self.installed_dir,
            self.editor.editor_id,
            name=self.editor.name,
            version=self.version.version,
        )
        self._set_step("install", "done", installed.name)

        self._set_step("registry", "active")
        registered, _metadata = self.register_callback(
            self.source_editor,
            installed,
            None,
            self.installed_icon,
            version=self.version.version,
            source_artifact=artifact,
            build_script=self.build_script,
            provenance="built",
            built_from_runtime="Portable",
            set_active=False,
            desktop_integrated=False,
        )
        self._new_metadata = appimage_metadata_path(installed)
        self._restore_existing_desktop_claim()
        self._preserve_version_selection()
        self._set_step("registry", "done", str(registered.get("version") or self.version.version))

        updated_version = EditorVersionInfo(
            version=self.version.version,
            portable_root=self.version.portable_root,
            portable_command=self.version.portable_command,
            appimage_path=installed,
            installed_command=(str(installed),),
            icon=self.installed_icon or self.version.icon,
            managed_record=dict(registered),
            desktop_integrated=bool(registered.get("desktop_integrated")),
            modified=max(self.version.modified, installed.stat().st_mtime),
        )

        self._set_step("desktop", "active")
        runtime_after, desktop, changed = self.reconcile_callback(self.editor, updated_version, self._pre_command)
        self._desktop_runtime_after = runtime_after
        self._desktop_result = desktop
        self._desktop_changed = changed
        if not self.config.save():
            raise InstallError("Could not save Suite Pythoine's managed AppImage state.")
        self.finalize_desktop_callback(self.editor, updated_version, runtime_after, desktop, changed)
        if runtime_after is None:
            self._set_step("desktop", "skip", "selected version is inactive")
        elif changed:
            self._set_step("desktop", "done", f"active {runtime_after} runtime")
        else:
            self._set_step("desktop", "skip", f"active runtime remains {runtime_after}")

        # Only after every commit stage succeeds may an old differently-named
        # managed AppImage be retired. The common same-path rebuild was already
        # replaced atomically by install_appimage and remains recoverable from
        # the temporary rollback copy until this point.
        if self._old_appimage is not None:
            old_resolved = self._old_appimage.expanduser().resolve(strict=False)
            if old_resolved != installed.resolve(strict=False) and old_resolved.is_file():
                try:
                    old_resolved.unlink()
                    old_sidecar = appimage_metadata_path(old_resolved)
                    if old_sidecar.is_file():
                        old_sidecar.unlink()
                except OSError as exc:
                    self._log(f"[suite] WARNING: old rebuilt AppImage cleanup was incomplete: {exc}")

        self._set_step("cleanup", "active")
        clean_build_dirs(self.portable_root, self.build_script, include_dist=True)
        self._set_step("cleanup", "done")
        self._log("[suite] Removed temporary build directories and generated dist output after managed AppImage installation.")
        self._success()

    def _cleanup_failed_build(self) -> str:
        if self.keep_failed_build_files.isChecked():
            self._log("[suite] Kept temporary build/output files for troubleshooting.")
            return " Temporary build files were kept for troubleshooting, as requested."
        try:
            clean_build_dirs(self.portable_root, self.build_script, include_dist=True)
            self._log("[suite] Removed temporary build directories and generated dist output after failure.")
            return " Temporary build directories and generated dist output were removed."
        except OSError as exc:
            self._log(f"[suite] WARNING: failed-build cleanup was incomplete: {exc}")
            return f" Temporary build cleanup was incomplete: {exc}"

    def _restore_file(self, key: str) -> None:
        pair = self._backup_files.get(key)
        if pair is None:
            return
        original, backup = pair
        original.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup, original)

    def _rollback(self) -> None:
        # Remove newly installed artifacts that did not exist at the same path
        # before this transaction, then restore all backed-up managed files.
        old_app = self._old_appimage.expanduser().resolve(strict=False) if self._old_appimage is not None else None
        if self.installed_appimage is not None:
            new_app = self.installed_appimage.expanduser().resolve(strict=False)
            if old_app is None or new_app != old_app:
                for path in (appimage_metadata_path(new_app), new_app):
                    try:
                        if path.is_file():
                            path.unlink()
                    except OSError:
                        pass
        if self.installed_icon is not None:
            new_icon = self.installed_icon.expanduser().resolve(strict=False)
            old_icon = self._old_icon.expanduser().resolve(strict=False) if self._old_icon is not None else None
            if old_icon is None or new_icon != old_icon:
                try:
                    if new_icon.is_file():
                        new_icon.unlink()
                except OSError:
                    pass
        for key in ("appimage", "metadata", "icon"):
            try:
                self._restore_file(key)
            except OSError:
                pass

        try:
            if self._desktop_existed and self._desktop_backup is not None:
                self._desktop_path.parent.mkdir(parents=True, exist_ok=True)
                self._desktop_path.write_bytes(self._desktop_backup)
                if self._desktop_mode is not None:
                    self._desktop_path.chmod(self._desktop_mode)
            elif not self._desktop_existed and self._desktop_path.exists():
                self._desktop_path.unlink()
        except OSError:
            pass

        if self._config_snapshot is not None:
            data = self.config.as_dict()
            data.clear()
            data.update(copy.deepcopy(self._config_snapshot))
            self.config.save()
        try:
            if self._desktop_path.parent.is_dir():
                self.refresh_desktop_callback(self._desktop_path.parent)
        except OSError:
            pass

    def _dispose_backup(self) -> None:
        if self._backup_temp is not None:
            self._backup_temp.cleanup()
            self._backup_temp = None

    def _fail(self, step: str, message: str, *, rollback: bool) -> None:
        if self.finished:
            return
        if rollback:
            self._rollback()
        self._dispose_backup()
        self._set_step(step, "fail")
        self.finished = True
        self.succeeded = False
        self.error_message = message
        self.progress.result_label.setText(f"Build failed: {message}")
        self._log(f"[suite] ERROR: {message}")
        self._set_buttons_building(False)
        finish = self.button(QWizard.WizardButton.FinishButton)
        if finish is not None:
            finish.setEnabled(True)

    def _success(self) -> None:
        self._dispose_backup()
        self.finished = True
        self.succeeded = True
        operation = "Rebuilt" if self.rebuild else "Built"
        self.progress.result_label.setText(
            f"{operation} {self.editor.name} {self.version.version} AppImage successfully. "
            "The active version and Launch runtime preference were preserved."
        )
        self._set_buttons_building(False)
        finish = self.button(QWizard.WizardButton.FinishButton)
        if finish is not None:
            finish.setEnabled(True)
        try:
            self.finished_callback()
        except Exception:
            pass

    def accept(self) -> None:
        if self.currentPage() is self.progress and not self.finished:
            return
        super().accept()

    def reject(self) -> None:
        if self._process is not None and self._process.state() != QProcess.ProcessState.NotRunning:
            QMessageBox.information(self, app_dialog_title("Build In Progress"), "Wait for the current AppImage build to finish before closing this wizard.")
            return
        self._dispose_backup()
        super().reject()
