from __future__ import annotations

from pathlib import Path
import os
import shutil
import stat
import sys
from typing import Callable

from PyQt6.QtCore import QProcess, QTimer, Qt
from PyQt6.QtGui import QFontDatabase, QIcon, QPixmap, QTextCursor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWizard,
    QWizardPage,
    QWidget,
)

from . import APP_NAME, __version__
from .config import ConfigService
from .install_inspection import ZipEditorInspection
from .installer import (
    InstallError,
    build_script_version,
    clean_build_dirs,
    find_appimage_build_script,
    find_built_appimage,
    import_zip,
    install_appimage,
    install_icon,
    sha256_file,
    snapshot_appimages,
    uninstall_registered_appimage_integration,
    synchronize_desktop_integration,
)
from .registry import EditorEntry, UnknownComponentError, inspect_editor_root
from .runtime_launcher import RuntimeLauncher
from .versioning import compare_versions, version_from_filename, version_sort_key
from .version_management import classify_install, versions_to_remove
from .ui_titles import app_dialog_title
from .managed_registry import get_managed_versions, remove_managed_version
from .storage_layout import appimage_root, is_within, portable_root, prune_empty_parents, version_root


RegisterCallback = Callable[[EditorEntry, Path, Path, Path | None], tuple[dict, Path]]
RefreshDesktopCallback = Callable[[Path], None]
FinishedCallback = Callable[[], None]


STEP_LABELS = (
    ("source", "Install portable source"),
    ("identity", "Verify component identity"),
    ("prepare", "Prepare AppImage build"),
    ("build", "Build AppImage"),
    ("verify", "Verify new AppImage"),
    ("appimage", "Install managed AppImage"),
    ("icon", "Install application icon"),
    ("desktop", "Create application-menu launcher"),
    ("registry", "Register managed installation"),
    ("versions", "Apply version-management policy"),
    ("cleanup", "Finalise installation"),
)


class BrandedPage(QWizardPage):
    def __init__(self, inspection: ZipEditorInspection, title: str, subtitle: str = "") -> None:
        super().__init__()
        self.inspection = inspection
        self.setTitle(title)
        self.setSubTitle(subtitle)

    def branding_header(self) -> QFrame:
        frame = QFrame()
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 8)
        icon = QLabel()
        pixmap = _inspection_pixmap(self.inspection, 88)
        if pixmap is not None:
            icon.setPixmap(pixmap)
            if self.inspection.icon_relative:
                icon.setToolTip(f"Wizard icon source: {self.inspection.icon_relative}")
            icon.setFixedSize(96, 96)
            icon.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        text = QVBoxLayout()
        name = QLabel(self.inspection.name)
        font = name.font()
        font.setBold(True)
        font.setPointSize(max(font.pointSize() + 4, 15))
        name.setFont(font)
        text.addWidget(name)
        version = QLabel(f"Version {self.inspection.version or self.inspection.builder_version or 'Unknown'}")
        version.setTextFormat(Qt.TextFormat.PlainText)
        text.addWidget(version)
        if self.inspection.description:
            description = QLabel(self.inspection.description)
            description.setTextFormat(Qt.TextFormat.PlainText)
            description.setWordWrap(True)
            text.addWidget(description)
        text.addStretch(1)
        layout.addLayout(text, 1)
        return frame


class WelcomePage(BrandedPage):
    def __init__(self, inspection: ZipEditorInspection) -> None:
        super().__init__(inspection, f"Install {inspection.name}", "Suite Pythoine has inspected the editor archive without executing it.")
        layout = QVBoxLayout(self)
        layout.addWidget(self.branding_header())

        details = QFormLayout()
        details.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        details.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        details.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)

        archive = _plain_label(inspection.zip_path.name, wrap=False)
        archive.setToolTip(str(inspection.zip_path))
        details.addRow("Archive:", archive)
        # The pad-family UI calls the common publisher identity "Editor ID".
        # The internal routing/application key remains inspection.editor_id.
        details.addRow("Editor ID:", _plain_label(inspection.publisher_id or "Not declared", wrap=False))
        details.addRow("Source folder:", _plain_label(inspection.source_folder_name, wrap=False))
        formats = ", ".join(inspection.extensions) if inspection.extensions else "Not declared"
        details.addRow("Supported formats:", _plain_label(formats, wrap=True))
        builder = inspection.builder_relative or "No AppImage builder detected"
        details.addRow("AppImage builder:", _plain_label(builder, wrap=False))
        icon_source = inspection.icon_relative or "No suitable application icon detected"
        icon_label = _plain_label(icon_source, wrap=False)
        icon_label.setToolTip(icon_source)
        details.addRow("Wizard icon source:", icon_label)
        layout.addLayout(details)

        note = QLabel(
            "The editor's logo and metadata are used only to brand this installation wizard. "
            "Suite Pythoine does not import or execute the editor's GUI/About-dialog code."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)


def _scrollable_page_layout(page: QWizardPage) -> QVBoxLayout:
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


class OptionsPage(BrandedPage):
    def __init__(
        self,
        inspection: ZipEditorInspection,
        *,
        destination: Path,
        installed_dir: Path,
        existing_editor: EditorEntry | None = None,
    ) -> None:
        super().__init__(inspection, "Installation options", "Choose how Suite Pythoine should install this component.")
        self.destination = destination
        self.installed_dir = installed_dir
        self.existing_editor = existing_editor
        self.incoming_version = inspection.version or inspection.builder_version or "Unknown"
        self._relation: int | None = None
        layout = _scrollable_page_layout(self)
        layout.addWidget(self.branding_header())

        group = QGroupBox("Components")
        box = QVBoxLayout(group)
        self.portable = QCheckBox("Install portable source in the Components folder")
        self.portable.setChecked(True)
        self.portable.setEnabled(False)
        box.addWidget(self.portable)

        self.build_appimage = QCheckBox("Build and install a managed AppImage")
        can_build = sys.platform.startswith("linux") and inspection.has_builder
        self.build_appimage.setChecked(can_build)
        self.build_appimage.setEnabled(can_build)
        if not sys.platform.startswith("linux"):
            self.build_appimage.setToolTip("Managed AppImage building is available on Linux.")
        elif not inspection.has_builder:
            self.build_appimage.setToolTip("No AppImage build script was detected in this archive.")
        box.addWidget(self.build_appimage)

        self.keep_failed_build_files = QCheckBox("Keep temporary AppImage build files if the build fails (for troubleshooting)")
        self.keep_failed_build_files.setChecked(False)
        self.keep_failed_build_files.setEnabled(can_build)
        self.keep_failed_build_files.setToolTip("Normally Suite removes temporary build environments after a failed build to avoid wasting disk space.")
        box.addWidget(self.keep_failed_build_files)

        self.install_icon = QCheckBox("Install the component logo with the managed AppImage")
        self.install_icon.setChecked(can_build)
        self.install_icon.setEnabled(False)
        box.addWidget(self.install_icon)

        self.desktop = QCheckBox("Create or update the application-menu launcher for the active version")
        self.desktop.setChecked(can_build)
        self.desktop.setEnabled(False)
        box.addWidget(self.desktop)

        self.prefer_installed = QCheckBox("Use the verified installed AppImage as this component's launch runtime")
        preserve_portable = existing_editor is not None and existing_editor.launch_mode == "portable"
        self.prefer_installed.setChecked(can_build and not preserve_portable)
        self.prefer_installed.setEnabled(can_build)
        box.addWidget(self.prefer_installed)

        self.delete_zip = QCheckBox("Delete the original ZIP after every selected step succeeds")
        self.delete_zip.setChecked(False)
        box.addWidget(self.delete_zip)
        layout.addWidget(group)

        self.operation_group = QButtonGroup(self)
        self.operation_radios: dict[str, QRadioButton] = {}
        self.make_active = QCheckBox("Make this version active after installation")
        self.make_active.setChecked(True)

        if existing_editor is not None and existing_editor.versions:
            version_group = QGroupBox("Version management")
            version_box = QVBoxLayout(version_group)
            active = existing_editor.active_version
            versions_text = ", ".join(item.version for item in existing_editor.versions)
            context_group = QWidget()
            context_form = QFormLayout(context_group)
            context_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            context_form.addRow("Currently available:", _plain_label(versions_text))
            context_form.addRow("Active version:", _plain_label(active or "Unknown"))
            context_form.addRow("Incoming version:", _plain_label(self.incoming_version))
            version_box.addWidget(context_group)
            decision = classify_install(
                self.incoming_version, active, [item.version for item in existing_editor.versions]
            )
            self._relation = compare_versions(self.incoming_version, active)
            exact_present = decision.exact_present

            def add_mode(key: str, label: str, checked: bool = False) -> None:
                radio = QRadioButton(label)
                radio.setProperty("suite_mode", key)
                radio.setChecked(checked)
                radio.toggled.connect(self._sync_version_choice)
                self.operation_group.addButton(radio)
                self.operation_radios[key] = radio
                version_box.addWidget(radio)

            if exact_present:
                add_mode("reinstall", f"Reinstall/repair {self.incoming_version}", True)
                self.make_active.setChecked(self.incoming_version == active)
                version_box.addWidget(self.make_active)
            elif self._relation is not None and self._relation > 0:
                add_mode("upgrade_remove", "Upgrade and remove older managed versions after the new version is verified", True)
                add_mode("upgrade_alongside", "Install alongside older versions")
                self.make_active.setChecked(True)
                self.make_active.setEnabled(False)
                version_box.addWidget(self.make_active)
            elif self._relation is not None and self._relation < 0:
                add_mode("downgrade_alongside", "Install this older version alongside the current version", True)
                add_mode("downgrade_remove", "Downgrade and remove newer managed versions after verification")
                self.make_active.setChecked(False)
                version_box.addWidget(self.make_active)
            else:
                add_mode("alongside", "Install alongside existing versions", True)
                self.make_active.setChecked(False)
                version_box.addWidget(self.make_active)
            layout.addWidget(version_group)
        else:
            self.make_active.setChecked(True)
            self.make_active.hide()

        if destination.exists():
            replace_group = QGroupBox("Existing copy of this version")
            replace_layout = QVBoxLayout(replace_group)
            warning = QLabel(
                f"{destination} already exists. The archive will not be merged into it. "
                "Replacement is staged and rolled back if the source-copy operation fails."
            )
            warning.setTextFormat(Qt.TextFormat.PlainText)
            warning.setWordWrap(True)
            replace_layout.addWidget(warning)
            self.replace_existing = QCheckBox("Replace/reinstall this portable version with the archive")
            self.replace_existing.setChecked(False)
            self.replace_existing.stateChanged.connect(lambda _state: self.completeChanged.emit())
            replace_layout.addWidget(self.replace_existing)
            layout.addWidget(replace_group)
        else:
            self.replace_existing = QCheckBox()
            self.replace_existing.setChecked(True)
            self.replace_existing.hide()

        paths = QGroupBox("Destination")
        form = QFormLayout(paths)
        form.addRow("Portable source:", _plain_label(str(destination)))
        form.addRow("Managed AppImage folder:", _plain_label(str(appimage_root(installed_dir, inspection.name, self.incoming_version))))
        layout.addWidget(paths)
        layout.addStretch(1)

        self.build_appimage.toggled.connect(self._sync_build_options)
        self._sync_version_choice()

    @property
    def operation_mode(self) -> str:
        for key, radio in self.operation_radios.items():
            if radio.isChecked():
                return key
        return "install"

    @property
    def make_active_after_install(self) -> bool:
        mode = self.operation_mode
        if mode in {"upgrade_remove", "downgrade_remove", "install"}:
            return True
        return self.make_active.isChecked()

    @property
    def remove_older_after_success(self) -> bool:
        return self.operation_mode == "upgrade_remove"

    @property
    def remove_newer_after_success(self) -> bool:
        return self.operation_mode == "downgrade_remove"

    def _sync_version_choice(self) -> None:
        mode = self.operation_mode
        if mode in {"upgrade_remove", "downgrade_remove"}:
            self.make_active.setChecked(True)
            self.make_active.setEnabled(False)
        elif mode == "upgrade_alongside":
            self.make_active.setChecked(True)
            self.make_active.setEnabled(True)
        elif mode == "downgrade_alongside":
            self.make_active.setEnabled(True)
        elif mode == "reinstall":
            self.make_active.setEnabled(True)
        self.completeChanged.emit()

    def _sync_build_options(self, checked: bool) -> None:
        self.install_icon.setChecked(checked)
        self.desktop.setChecked(checked)
        self.prefer_installed.setEnabled(checked)
        self.keep_failed_build_files.setEnabled(checked)
        if not checked:
            self.prefer_installed.setChecked(False)
            self.keep_failed_build_files.setChecked(False)

    def isComplete(self) -> bool:  # noqa: N802 - Qt API
        return not self.destination.exists() or self.replace_existing.isChecked()


class ReviewPage(BrandedPage):
    def __init__(self, inspection: ZipEditorInspection, options: OptionsPage, *, destination: Path, installed_dir: Path) -> None:
        super().__init__(inspection, "Ready to install", "Review the actions before Suite Pythoine changes anything.")
        self.options = options
        self.destination = destination
        self.installed_dir = installed_dir
        layout = QVBoxLayout(self)
        layout.addWidget(self.branding_header())
        self.summary = QLabel()
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        self.summary.setWordWrap(True)
        self.summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.summary)
        layout.addStretch(1)

    def initializePage(self) -> None:  # noqa: N802 - Qt API
        operation_labels = {
            "install": "Install as the first managed version",
            "reinstall": "Reinstall/repair this existing version",
            "upgrade_remove": "Upgrade and remove older managed versions after verification",
            "upgrade_alongside": "Upgrade and keep older versions available",
            "downgrade_alongside": "Install older version alongside the active version",
            "downgrade_remove": "Downgrade and remove newer managed versions after verification",
            "alongside": "Install alongside existing versions",
        }
        lines = [
            f"Version action: {operation_labels.get(self.options.operation_mode, self.options.operation_mode)}",
            f"Active after install: {'Yes' if self.options.make_active_after_install else 'No'}",
            "",
            f"✓ {'Replace' if self.destination.exists() else 'Install'} portable source",
            f"  {self.destination}",
        ]
        if self.options.build_appimage.isChecked():
            lines.extend(
                [
                    f"✓ Run {self.inspection.builder_relative}",
                    ("— Keep temporary build files if the builder fails" if self.options.keep_failed_build_files.isChecked() else "✓ Remove temporary build files if the builder fails"),
                    "✓ Accept only an AppImage created or changed by this build",
                    "✓ Verify source/build version identity",
                    f"✓ Install managed AppImage under {appimage_root(self.installed_dir, self.inspection.name, self.inspection.version or self.inspection.builder_version)}",
                    "✓ Install the detected component logo",
                    ("✓ Create/update the per-user application-menu launcher" if self.options.make_active_after_install else "— Preserve the existing desktop-integrated version"),
                    "✓ Record AppImage, SHA-256, desktop ID/path and icon path in Suite's registry",
                    f"✓ Preferred launch mode: {'Installed when verified' if self.options.prefer_installed.isChecked() else 'Portable'}",
                ]
            )
        else:
            lines.append("— AppImage build/integration will be skipped")
        if self.options.delete_zip.isChecked():
            lines.append(f"✓ Delete {self.inspection.zip_path.name} only after all selected steps succeed")
        else:
            lines.append("— Keep the original ZIP")
        lines.extend([
            "",
            f"Archive SHA-256: {self.inspection.archive_sha256}",
            f"Portable source expands to approximately {_human_bytes(self.inspection.expanded_bytes)} before the safety reserve.",
            "Suite will check destination free space immediately before the single staged extraction.",
        ])
        self.summary.setText("\n".join(lines))


class ProgressPage(BrandedPage):
    def __init__(
        self,
        inspection: ZipEditorInspection,
        options: OptionsPage,
        *,
        editors_root: Path,
        installed_dir: Path,
        config: ConfigService,
        launcher: RuntimeLauncher,
        register_callback: Callable[..., tuple[dict, Path]],
        refresh_desktop_callback: RefreshDesktopCallback,
        finished_callback: FinishedCallback,
    ) -> None:
        super().__init__(inspection, f"Installing {inspection.name}", "The checklist is the installer state; technical build output remains available below.")
        self.options = options
        self.editors_root = editors_root
        self.installed_dir = installed_dir
        self.config = config
        self.launcher = launcher
        self.register_callback = register_callback
        self.refresh_desktop_callback = refresh_desktop_callback
        self.finished_callback = finished_callback
        self.started = False
        self.finished = False
        self.succeeded = False
        self.error_message = ""
        self.editor_root: Path | None = None
        self.editor: EditorEntry | None = None
        self.installed_appimage: Path | None = None
        self.installed_version: str | None = None
        self.registry_record: dict = {}
        self._before_build: dict[str, tuple[int, int]] = {}
        self._build_script: Path | None = None
        self._expected_version: str | None = None
        self._process: QProcess | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(self.branding_header())
        self.steps = QListWidget()
        self.steps.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.step_items: dict[str, QListWidgetItem] = {}
        for key, label in STEP_LABELS:
            item = QListWidgetItem(f"○  {label}")
            self.step_items[key] = item
            self.steps.addItem(item)
        self.steps.setMinimumHeight(180)
        self.steps.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.steps, 1)

        # Keep the outcome/status outside the technical console. In earlier
        # revisions this label sat below two large minimum-height widgets and
        # could be squeezed into the console/button strip on shorter desktops.
        self.result_label = QLabel()
        self.result_label.setTextFormat(Qt.TextFormat.PlainText)
        self.result_label.setWordWrap(True)
        self.result_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        layout.addWidget(self.result_label)

        self.command_label = QLabel("Command: waiting for installation to begin")
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
        self._collapsed_wizard_size = None
        self._collapsed_steps_height = None
        self.output.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        fixed = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        self.output.setFont(fixed)
        layout.addWidget(self.output, 1)

    def initializePage(self) -> None:  # noqa: N802 - Qt API
        wizard = self.wizard()
        if wizard is not None:
            wizard.button(QWizard.WizardButton.BackButton).setEnabled(False)
            wizard.button(QWizard.WizardButton.CancelButton).setEnabled(False)
        if not self.started:
            self.started = True
            QTimer.singleShot(0, self._start)

    def isComplete(self) -> bool:  # noqa: N802 - Qt API
        return self.finished

    def _set_step(self, key: str, state: str, detail: str | None = None) -> None:
        item = self.step_items[key]
        label = dict(STEP_LABELS)[key]
        prefix = {"pending": "○", "active": "⟳", "done": "✓", "skip": "—", "fail": "✕"}[state]
        text = f"{prefix}  {label}"
        if detail:
            text += f" — {detail}"
        item.setText(text)
        self.steps.scrollToItem(item)

    def _log(self, text: str) -> None:
        if not text:
            return
        self.output.moveCursor(QTextCursor.MoveOperation.End)
        self.output.insertPlainText(text if text.endswith("\n") else text + "\n")
        self.output.moveCursor(QTextCursor.MoveOperation.End)

    def _toggle_output(self, checked: bool) -> None:
        """Expand technical output without collapsing the installation checklist.

        0.2.0 squeezed the checklist to a 155 px maximum whenever the console
        opened. That made the upper installer visibly jump smaller. Preserve the
        checklist's current height, grow the wizard when the screen permits it,
        and restore the prior window size when details are hidden.
        """
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

    def _start(self) -> None:
        failure_step = "source"
        try:
            self._set_step("source", "active")
            self.command_label.setText(f"Command: import {self.inspection.zip_path}")
            self._log(f"[suite] Source archive: {self.inspection.zip_path}")
            self._log(f"[suite] Archive SHA-256: {self.inspection.archive_sha256}")
            self.editor_root = import_zip(
                self.inspection.zip_path,
                self.editors_root,
                replace_existing=self.options.replace_existing.isChecked(),
                destination=self.options.destination,
            )
            self._set_step("source", "done", str(self.editor_root))

            failure_step = "identity"
            self._set_step("identity", "active")
            self.editor = inspect_editor_root(
                self.editor_root,
                config=self.config.as_dict(),
                installed_dir=self.installed_dir,
                python_executable=self.launcher.python_executable(),
            )
            if self.editor.editor_id != self.inspection.editor_id:
                raise InstallError(
                    f"Component identity changed after import: expected {self.inspection.editor_id}, got {self.editor.editor_id}."
                )
            self._set_step("identity", "done", self.editor.source_version or "version unknown")
            self._log(f"[suite] Identified {self.editor.name} ({self.editor.editor_id})")

            if not self.options.build_appimage.isChecked():
                for key in ("prepare", "build", "verify", "appimage", "icon", "desktop", "registry"):
                    self._set_step(key, "skip")
                self._force_safe_portable_preference_if_needed()
                self._apply_version_policy()
                self._finalize_success()
                return

            failure_step = "prepare"
            self._set_step("prepare", "active")
            self._build_script = find_appimage_build_script(self.editor_root)
            if self._build_script is None:
                raise InstallError("The AppImage builder detected during inspection is no longer present after import.")
            try:
                self._build_script.chmod(self._build_script.stat().st_mode | stat.S_IXUSR)
            except OSError as exc:
                raise InstallError(f"Could not make AppImage builder executable: {exc}") from exc
            self._before_build = snapshot_appimages(self.editor_root)
            self._expected_version = self.editor.source_version or build_script_version(self._build_script)
            self._set_step("prepare", "done", self._expected_version or "version unknown")
            self._start_build()
        except (InstallError, UnknownComponentError, OSError, shutil.Error) as exc:
            self._fail(failure_step, str(exc))

    def _start_build(self) -> None:
        assert self._build_script is not None
        assert self.editor_root is not None
        self._set_step("build", "active")
        self.command_label.setText(f"Command: {self._build_script}")
        self._log(f"\n$ {self._build_script}\n")
        process = QProcess(self)
        self._process = process
        process.setProgram(str(self._build_script))
        process.setWorkingDirectory(str(self.editor_root))
        process.setProcessEnvironment(self.launcher.process_environment())
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(self._read_output)
        process.finished.connect(self._build_finished)
        process.errorOccurred.connect(self._build_process_error)
        process.start()

    def _read_output(self) -> None:
        if self._process is None:
            return
        data = bytes(self._process.readAllStandardOutput()).decode("utf-8", "replace")
        if data:
            self._log(data.rstrip("\n"))

    def _build_process_error(self, error) -> None:
        if self._process is None or self.finished:
            return
        self._read_output()
        if error == QProcess.ProcessError.FailedToStart:
            self._fail("build", f"Could not start AppImage builder: {self._build_script}")

    def _build_finished(self, code: int, status: QProcess.ExitStatus) -> None:
        self._read_output()
        if status != QProcess.ExitStatus.NormalExit or code != 0:
            cleanup_note = ""
            if self.editor_root is not None and not self.options.keep_failed_build_files.isChecked():
                try:
                    clean_build_dirs(self.editor_root)
                    cleanup_note = " Temporary build directories were removed to reclaim storage."
                    self._log("[suite] Removed temporary build directories after the failed AppImage build.")
                except OSError as exc:
                    cleanup_note = f" Temporary build cleanup was incomplete: {exc}"
                    self._log(f"[suite] WARNING: failed-build cleanup was incomplete: {exc}")
            elif self.options.keep_failed_build_files.isChecked():
                cleanup_note = " Temporary build files were kept for troubleshooting, as requested."
                self._log("[suite] Kept temporary build files after failure for troubleshooting.")
            self._fail(
                "build",
                f"AppImage builder exited with code {code}. The portable source remains installed."
                f"{cleanup_note} "
                "If you successfully build the AppImage separately, drag that .AppImage onto Suite Pythoine or use Tools → Install Component… to adopt it.",
            )
            return
        self._set_step("build", "done")
        try:
            self._finish_appimage_install()
        except (InstallError, OSError, shutil.Error) as exc:
            active = next(
                (key for key in ("verify", "appimage", "icon", "desktop", "registry", "versions") if self.step_items[key].text().startswith("⟳")),
                "verify",
            )
            self._fail(active, str(exc))

    def _finish_appimage_install(self) -> None:
        assert self.editor_root is not None
        assert self.editor is not None
        assert self._build_script is not None

        self._set_step("verify", "active")
        artifact = find_built_appimage(
            self.editor_root,
            build_script=self._build_script,
            before=self._before_build,
            expected_version=self._expected_version,
        )
        if artifact is None:
            raise InstallError(
                "The build completed, but no AppImage created or changed by this build was found. Older artifacts were ignored."
            )
        artifact_version = version_from_filename(artifact) or build_script_version(self._build_script)
        if self._expected_version and artifact_version and self._expected_version.casefold() != artifact_version.casefold():
            raise InstallError(
                f"Build version mismatch: source/build version {self._expected_version}, artifact version {artifact_version}."
            )
        self.installed_version = artifact_version or self._expected_version
        self._set_step("verify", "done", artifact.name)
        self._log(f"[suite] New build artifact: {artifact}")
        self._log(f"[suite] Artifact SHA-256: {sha256_file(artifact)}")

        self._set_step("appimage", "active")
        installed = install_appimage(artifact, self.installed_dir, editor_id=self.editor.editor_id, name=self.editor.name, version=self.installed_version or self.editor.source_version)
        self.installed_appimage = installed
        self._set_step("appimage", "done", str(installed))

        self._set_step("icon", "active")
        installed_icon = install_icon(self.editor.icon, self.installed_dir, self.editor.editor_id, name=self.editor.name, version=self.installed_version or self.editor.source_version)
        if installed_icon is None:
            self._set_step("icon", "skip", "no installable icon detected")
        else:
            self._set_step("icon", "done", installed_icon.name)

        desktop = None
        if self.options.make_active_after_install:
            self._set_step("desktop", "active")
            desktop = synchronize_desktop_integration(
                self.editor.name,
                self.editor.editor_id,
                installed,
                installed_icon,
                self.editor.root,
            )
            self._set_step("desktop", "done", desktop.name)
        else:
            self._set_step("desktop", "skip", "existing active desktop integration preserved")

        self._set_step("registry", "active")
        record, metadata = self.register_callback(
            self.editor,
            installed,
            desktop,
            installed_icon,
            version=self.installed_version,
            source_artifact=artifact,
            build_script=self._build_script,
            set_active=self.options.make_active_after_install,
            desktop_integrated=bool(desktop),
        )
        self.registry_record = record
        if desktop is not None:
            self.refresh_desktop_callback(desktop.parent)
        override = _editor_override(self.config, self.editor.editor_id)
        for key in ("installed_path", "installed_version", "installed_source_version", "installed_sha256", "built_artifact", "build_script"):
            override.pop(key, None)
        if self.options.make_active_after_install:
            override["active_version"] = self.installed_version or self.editor.source_version or self.options.incoming_version
            override["launch_mode"] = "installed" if self.options.prefer_installed.isChecked() else "portable"
        self.config.save()
        self._set_step("registry", "done", metadata.name)
        clean_build_dirs(self.editor_root)
        self._apply_version_policy()
        self._finalize_success()

    def _remove_managed_version_now(self, version: str) -> None:
        if self.editor is None:
            return
        records = get_managed_versions(self.config.as_dict(), self.editor.editor_id)
        record = records.get(version, {})
        if record and record.get("appimage_path"):
            uninstall_registered_appimage_integration(record, installed_dir=self.installed_dir)
            remove_managed_version(self.config.as_dict(), self.editor.editor_id, version)
        container = version_root(self.editors_root, self.editor.name, version)
        if container.exists():
            if container.is_symlink() or not is_within(container, self.editors_root):
                raise InstallError(f"Refusing to remove unsafe managed version folder: {container}")
            shutil.rmtree(container)
            prune_empty_parents(container.parent, self.editors_root)

    def _apply_version_policy(self) -> None:
        self._set_step("versions", "active")
        if self.editor is None:
            self._set_step("versions", "skip")
            return
        incoming = self.installed_version or self.editor.source_version or self.options.incoming_version
        override = _editor_override(self.config, self.editor.editor_id)
        if self.options.make_active_after_install:
            override["active_version"] = incoming

        existing = self.options.existing_editor
        existing_versions = [item.version for item in existing.versions] if existing is not None else []
        remove_versions = list(versions_to_remove(existing_versions, incoming, self.options.operation_mode))

        deferred: list[str] = []
        for version in sorted(set(remove_versions), key=version_sort_key):
            # Suite cannot safely delete the version whose code is currently
            # executing. Defer only that self-version until the newly active
            # Suite starts successfully; all other applications are cleaned now.
            if self.editor.editor_id == "suite-pythoine" and version.casefold() == __version__.casefold():
                deferred.append(version)
                self._log(f"[suite] Deferred removal of running Suite Pythoine {version} until the new version starts.")
                continue
            self._log(f"[suite] Removing superseded managed version {version}")
            self._remove_managed_version_now(version)

        if deferred:
            self.config.set(
                "pending_self_cleanup",
                {
                    "editor_id": "suite-pythoine",
                    "target_version": incoming,
                    "remove_versions": deferred,
                    "editors_root": str(self.editors_root),
                    "application_name": self.editor.name,
                },
            )
        self.config.save()
        if remove_versions:
            detail = f"removed {len(remove_versions) - len(deferred)}, deferred {len(deferred)}"
        elif self.options.operation_mode in {"upgrade_alongside", "downgrade_alongside", "alongside"}:
            detail = "older/newer versions retained and remain launchable"
        elif self.options.operation_mode == "reinstall":
            detail = "existing version repaired/reinstalled"
        else:
            detail = "active version recorded"
        self._set_step("versions", "done", detail)

    def _force_safe_portable_preference_if_needed(self) -> None:
        if self.editor is None:
            return
        override = _editor_override(self.config, self.editor.editor_id)
        if self.editor.portable_command and self.editor.installed_command and self.editor.version_status in {"mismatch", "unverified"}:
            if override.get("launch_mode") == "installed":
                override["launch_mode"] = "portable"
                self.config.save()
                self._log("[suite] Existing installed AppImage is mismatched/unverified; launch preference changed to Portable.")

    def _finalize_success(self) -> None:
        self._set_step("cleanup", "active")
        if self.options.delete_zip.isChecked():
            try:
                self.inspection.zip_path.unlink()
                self._log(f"[suite] Removed original archive: {self.inspection.zip_path}")
            except OSError as exc:
                self._fail("cleanup", f"Installation succeeded, but the original ZIP could not be removed: {exc}")
                return
        self._set_step("cleanup", "done")
        self.finished = True
        self.succeeded = True
        self.result_label.setText(f"{self.inspection.name} was installed successfully.")
        self.command_label.setText("Command: installation complete")
        self._unlock_wizard()
        self.finished_callback()
        self.completeChanged.emit()

    def _fail(self, key: str, message: str) -> None:
        if key in self.step_items:
            self._set_step(key, "fail", message)
        self.finished = True
        self.succeeded = False
        self.error_message = message
        self.result_label.setText(
            f"Installation stopped: {message}\n\n"
            "Completed atomic steps have been left in a consistent state; an existing managed AppImage is not replaced unless a verified new artifact reaches the install step."
        )
        self._log(f"[suite] ERROR: {message}")
        self._unlock_wizard()
        self.finished_callback()
        self.completeChanged.emit()

    def _unlock_wizard(self) -> None:
        wizard = self.wizard()
        if wizard is not None:
            wizard.button(QWizard.WizardButton.CancelButton).setEnabled(True)


class FinishPage(BrandedPage):
    def __init__(self, inspection: ZipEditorInspection, progress: ProgressPage) -> None:
        super().__init__(inspection, "Installation complete", "")
        self.progress = progress
        layout = QVBoxLayout(self)
        layout.addWidget(self.branding_header())
        self.message = QLabel()
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        self.message.setWordWrap(True)
        self.message.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.message)
        self.launch_editor = QCheckBox(f"Launch {inspection.name} when this wizard closes")
        self.launch_editor.setChecked(False)
        layout.addWidget(self.launch_editor)
        layout.addStretch(1)

    def initializePage(self) -> None:  # noqa: N802 - Qt API
        if self.progress.succeeded:
            self.setTitle(f"{self.inspection.name} installed")
            lines = ["All selected installation steps completed successfully."]
            if self.progress.editor_root:
                lines.append(f"\nPortable source:\n{self.progress.editor_root}")
            if self.progress.installed_appimage:
                lines.append(f"\nManaged AppImage:\n{self.progress.installed_appimage}")
                lines.append(f"\nInstalled version: {self.progress.installed_version or 'Unknown'}")
            self.message.setText("\n".join(lines))
            self.launch_editor.setVisible(True)
        else:
            self.setTitle("Installation stopped")
            self.message.setText(
                f"{self.inspection.name} was not fully installed.\n\n{self.progress.error_message}\n\n"
                "Open Technical details on the previous page to inspect the builder output."
            )
            self.launch_editor.setVisible(False)


class EditorInstallWizard(QWizard):
    """Calamares-like source ZIP installation flow for Suite Pythoine."""

    def __init__(
        self,
        parent,
        inspection: ZipEditorInspection,
        *,
        editors_root: Path,
        installed_dir: Path,
        config: ConfigService,
        launcher: RuntimeLauncher,
        register_callback: Callable[..., tuple[dict, Path]],
        refresh_desktop_callback: RefreshDesktopCallback,
        finished_callback: FinishedCallback,
        delete_archive_default: bool = False,
        existing_editor: EditorEntry | None = None,
    ) -> None:
        super().__init__(parent)
        self.inspection = inspection
        self.editors_root = editors_root
        self.installed_dir = installed_dir
        self.config = config
        self.launcher = launcher
        self.setWindowTitle(app_dialog_title(f"Install {inspection.name}"))
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setMinimumSize(820, 640)
        self.resize(980, 800)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)
        self.setOption(QWizard.WizardOption.NoBackButtonOnLastPage, True)

        pixmap = _inspection_pixmap(inspection, 128)
        if pixmap is not None:
            self.setWindowIcon(QIcon(pixmap))
            self.setPixmap(QWizard.WizardPixmap.LogoPixmap, pixmap)

        destination = portable_root(editors_root, inspection.name, inspection.version or inspection.builder_version)
        self.welcome_page = WelcomePage(inspection)
        self.options_page = OptionsPage(
            inspection, destination=destination, installed_dir=installed_dir, existing_editor=existing_editor
        )
        self.options_page.delete_zip.setChecked(bool(delete_archive_default))
        if delete_archive_default:
            self.options_page.delete_zip.setText("Delete the verified Store download after every selected step succeeds")
        self.review_page = ReviewPage(inspection, self.options_page, destination=destination, installed_dir=installed_dir)
        self.progress_page = ProgressPage(
            inspection,
            self.options_page,
            editors_root=editors_root,
            installed_dir=installed_dir,
            config=config,
            launcher=launcher,
            register_callback=register_callback,
            refresh_desktop_callback=refresh_desktop_callback,
            finished_callback=finished_callback,
        )
        self.finish_page = FinishPage(inspection, self.progress_page)
        self.addPage(self.welcome_page)
        self.addPage(self.options_page)
        self.addPage(self.review_page)
        self.addPage(self.progress_page)
        self.addPage(self.finish_page)

        self.setButtonText(QWizard.WizardButton.NextButton, "Continue")
        self.setButtonText(QWizard.WizardButton.FinishButton, "Finish")

    @property
    def launch_after_finish(self) -> bool:
        return bool(self.progress_page.succeeded and self.finish_page.launch_editor.isChecked())

    @property
    def installed_editor_id(self) -> str | None:
        return self.progress_page.editor.editor_id if self.progress_page.editor else None


def _human_bytes(value: int) -> str:
    size = float(max(0, value))
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024.0 or unit == "TiB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024.0
    return f"{value} B"


def _plain_label(text: str, *, wrap: bool = True) -> QLabel:
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    label.setWordWrap(wrap)
    label.setMinimumWidth(0)
    label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    return label


def _inspection_pixmap(inspection: ZipEditorInspection, size: int) -> QPixmap | None:
    if not inspection.icon_bytes:
        return None
    pixmap = QPixmap()
    if not pixmap.loadFromData(inspection.icon_bytes):
        return None
    return pixmap.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def _editor_override(config: ConfigService, editor_id: str) -> dict:
    overrides = config.get("editor_overrides", {})
    if not isinstance(overrides, dict):
        overrides = {}
        config.set("editor_overrides", overrides)
    override = overrides.setdefault(editor_id, {})
    if not isinstance(override, dict):
        override = {}
        overrides[editor_id] = override
    return override
