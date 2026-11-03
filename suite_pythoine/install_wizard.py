from __future__ import annotations

from pathlib import Path
import os
import copy
import shutil
import stat
import sys
import traceback
import uuid
from typing import Callable

from PyQt6.QtCore import QProcess, QTimer, Qt
from PyQt6.QtGui import QFontDatabase, QIcon, QPixmap, QTextCursor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QFormLayout,
    QFrame,
    QMessageBox,
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
from .catalogue.component_policy import is_backend_only_component
from .install_inspection import ZipEditorInspection
from .installer import (
    InstallError,
    build_script_version,
    clean_build_dirs,
    find_appimage_build_script,
    find_built_appimage,
    desktop_entry_path,
    import_zip,
    install_appimage,
    install_icon,
    sha256_file,
    snapshot_appimages,
    uninstall_registered_appimage_integration,
    synchronize_desktop_integration,
    synchronize_portable_desktop_integration,
)
from .registry import EditorEntry, UnknownComponentError, inspect_editor_root
from .recovery import retain_recovery_archive, install_portable_with_recovery, _load_recovery_info
from .runtime.runtime_launcher import RuntimeLauncher
from .versioning import compare_versions, version_from_filename, version_sort_key
from .version_management import classify_install, versions_to_remove
from .ui_titles import app_dialog_title
from .installation_state import (
    desktop_id_for, get_managed_versions, remove_managed_version,
    set_active_version, set_desktop_version, set_managed_installation,
)
from .storage_layout import appimage_root, is_within, portable_root, prune_empty_parents, recovery_root, version_root


RegisterCallback = Callable[[EditorEntry, Path, Path, Path | None], tuple[dict, Path]]
RefreshDesktopCallback = Callable[[Path], None]
FinishedCallback = Callable[[], None]


STEP_LABELS = (
    ("source", "Prepare portable source"),
    ("identity", "Verify application identity"),
    ("recovery", "Retain Recovery archive"),
    ("prepare", "Prepare AppImage build"),
    ("build", "Build AppImage"),
    ("verify", "Verify new AppImage"),
    ("appimage", "Install managed AppImage"),
    ("icon", "Install application icon"),
    ("registry", "Verify installation identity"),
    ("versions", "Apply version-management policy"),
    ("desktop", "Synchronize active desktop launcher"),
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
    def __init__(self, inspection: ZipEditorInspection, *, developer_mode: bool = False) -> None:
        super().__init__(inspection, f"Install {inspection.name}", "Suite Pythoine has inspected the application archive without executing it.")
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
        details.addRow("Application ID:", _plain_label(inspection.publisher_id or "Not declared", wrap=False))
        details.addRow("Source folder:", _plain_label(inspection.source_folder_name, wrap=False))
        formats = ", ".join(inspection.extensions) if inspection.extensions else "Not declared"
        details.addRow("Supported formats:", _plain_label(formats, wrap=True))
        if developer_mode:
            builder = inspection.builder_relative or "No AppImage builder detected"
            details.addRow("AppImage builder:", _plain_label(builder, wrap=False))
        icon_source = inspection.icon_relative or "No suitable application icon detected"
        icon_label = _plain_label(icon_source, wrap=False)
        icon_label.setToolTip(icon_source)
        details.addRow("Wizard icon source:", icon_label)
        layout.addLayout(details)

        note = QLabel(
            "The application logo and metadata are used only to brand this installation wizard. "
            "Suite Pythoine does not import or execute the application GUI/About-dialog code."
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
        developer_mode: bool = False,
    ) -> None:
        super().__init__(inspection, "Installation options", "Choose how Suite Pythoine should install this application.")
        self.destination = destination
        self.installed_dir = installed_dir
        self.existing_editor = existing_editor
        self.developer_mode = bool(developer_mode)
        self.backend_only = is_backend_only_component(inspection)
        self.incoming_version = inspection.version or inspection.builder_version or "Unknown"
        self._relation: int | None = None
        layout = _scrollable_page_layout(self)
        layout.addWidget(self.branding_header())

        group = QGroupBox("Applications")
        box = QVBoxLayout(group)
        self.portable = QCheckBox(
            "Preserve the existing Portable source in the Applications folder" if destination.exists()
            else "Install portable source in the Applications folder"
        )
        self.portable.setChecked(True)
        self.portable.setEnabled(False)
        box.addWidget(self.portable)

        self.build_appimage = QCheckBox("Build and install a managed AppImage")
        self._linux_appimage_available = sys.platform.startswith("linux")
        self._archive_can_build = bool(inspection.has_builder)
        self._existing_builder = find_appimage_build_script(destination) if destination.is_dir() else None
        can_build = self._linux_appimage_available and (bool(self._existing_builder) if destination.exists() else self._archive_can_build)
        # Normal installation is available in both modes. Developer Mode adds
        # an OPTIONAL build step; it is never selected automatically.
        self.build_appimage.setChecked(False)
        self.build_appimage.setEnabled(self.developer_mode and can_build)
        self.build_appimage.setVisible(self.developer_mode)
        if not self._linux_appimage_available:
            self.build_appimage.setToolTip("Managed AppImage building is available on Linux.")
        elif destination.exists() and self._existing_builder is None:
            self.build_appimage.setToolTip("The existing Portable source has no detected AppImage builder. Replace it from the archive to build from the incoming source.")
        elif not inspection.has_builder and not self._existing_builder:
            self.build_appimage.setToolTip("No AppImage build script was detected in this source.")
        else:
            self.build_appimage.setToolTip("Build from the existing managed Portable source unless replacement from the archive is selected.")
        box.addWidget(self.build_appimage)

        self.keep_failed_build_files = QCheckBox("Keep temporary AppImage build/output files if the build fails (for troubleshooting)")
        self.keep_failed_build_files.setChecked(False)
        self.keep_failed_build_files.setEnabled(False)
        self.keep_failed_build_files.setVisible(self.developer_mode)
        self.keep_failed_build_files.setToolTip("Normally Suite removes temporary build environments and generated dist output after a failed build to avoid wasting disk space.")
        box.addWidget(self.keep_failed_build_files)

        self.install_icon = QCheckBox("Install the application logo with the managed AppImage")
        self.install_icon.setChecked(False)
        self.install_icon.setEnabled(False)
        self.install_icon.setVisible(self.developer_mode)
        box.addWidget(self.install_icon)

        self.desktop = QCheckBox("Create or update the application-menu launcher for the active version")
        self.desktop.setChecked(not self.backend_only)
        self.desktop.setEnabled(False)
        self.desktop.setVisible(not self.backend_only)
        box.addWidget(self.desktop)

        self.prefer_installed = QCheckBox("Use the verified installed AppImage as this application's launch runtime")
        preserve_portable = existing_editor is not None and existing_editor.launch_mode == "portable"
        self.prefer_installed.setChecked(False)
        self.prefer_installed.setEnabled(False)
        self.prefer_installed.setVisible(self.developer_mode)
        box.addWidget(self.prefer_installed)

        self.delete_zip = QCheckBox("Delete the original ZIP after every selected step succeeds")
        self.delete_zip.setChecked(False)
        self.delete_zip.setToolTip("When this archive installs/replaces the Portable source, Suite retains an exact managed Recovery copy before the original ZIP can be deleted.")
        box.addWidget(self.delete_zip)
        layout.addWidget(group)

        self.operation_group = QButtonGroup(self)
        self.operation_radios: dict[str, QRadioButton] = {}
        self.make_active = QCheckBox("Make this version active after installation")
        self.make_active.setChecked(True)
        self.make_active.setToolTip(
            "Uncheck to install alongside without changing the current active version."
            if self.backend_only else
            "Uncheck to install alongside without changing the current active version or desktop launcher."
        )
        box.addWidget(self.make_active)

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
                self.make_active.setChecked(True)
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
                self.make_active.setChecked(True)
                version_box.addWidget(self.make_active)
            else:
                add_mode("alongside", "Install alongside existing versions", True)
                self.make_active.setChecked(True)
                version_box.addWidget(self.make_active)
            layout.addWidget(version_group)
        else:
            self.make_active.setChecked(True)
            self.make_active.setEnabled(True)

        if destination.exists():
            replace_group = QGroupBox("Existing copy of this version")
            replace_layout = QVBoxLayout(replace_group)
            existing_note = (
                " If replacement is not selected, Suite preserves this Portable source and uses it for any selected AppImage build."
                if self.developer_mode else
                " If replacement is not selected, Suite preserves this Portable source."
            )
            warning = QLabel(
                f"{destination} already exists. The archive will not be merged into it."
                f"{existing_note} Replacement is staged and rolled back if the source-copy operation fails."
            )
            warning.setTextFormat(Qt.TextFormat.PlainText)
            warning.setWordWrap(True)
            replace_layout.addWidget(warning)
            self.replace_existing = QCheckBox("Replace/reinstall this portable version with the archive")
            self.replace_existing.setChecked(False)
            self.replace_existing.stateChanged.connect(self._sync_source_choice)
            replace_layout.addWidget(self.replace_existing)
            layout.addWidget(replace_group)
        else:
            self.replace_existing = QCheckBox()
            self.replace_existing.setChecked(True)
            self.replace_existing.hide()

        paths = QGroupBox("Destination")
        form = QFormLayout(paths)
        form.addRow("Portable source:", _plain_label(str(destination)))
        if self.developer_mode:
            form.addRow("Managed AppImage folder:", _plain_label(str(appimage_root(installed_dir, inspection.name, self.incoming_version))))
        layout.addWidget(paths)
        layout.addStretch(1)

        self.build_appimage.toggled.connect(self._sync_build_options)
        self.build_appimage.toggled.connect(lambda _checked: self.completeChanged.emit())
        if not self.backend_only:
            self.make_active.toggled.connect(lambda checked: self.desktop.setChecked(bool(checked)))
        self._sync_source_choice()
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
        if mode in {"upgrade_remove", "downgrade_remove"}:
            return True  # Deleting the previous version requires an active replacement.
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
            self.make_active.setToolTip("Removing the previous active version requires an active replacement.")
        elif mode == "reinstall" and self.existing_editor is not None and self.incoming_version == self.existing_editor.active_version:
            self.make_active.setChecked(True)
            self.make_active.setEnabled(False)
            self.make_active.setToolTip("Reinstalling the currently active version preserves its active desktop target.")
        else:
            self.make_active.setEnabled(True)
            self.make_active.setToolTip(
                "Uncheck to install alongside without changing the current active version."
                if self.backend_only else
                "Uncheck to install alongside without changing the current active version or desktop launcher."
            )
        self.completeChanged.emit()

    @property
    def uses_existing_portable(self) -> bool:
        return self.destination.exists() and not self.replace_existing.isChecked()

    def _sync_source_choice(self, _state: int | None = None) -> None:
        if not self._linux_appimage_available:
            can_build = False
        elif self.uses_existing_portable:
            can_build = self._existing_builder is not None
        else:
            can_build = self._archive_can_build
        self.build_appimage.setEnabled(self.developer_mode and can_build)
        if not self.developer_mode:
            self.build_appimage.setChecked(False)
        if not can_build:
            self.build_appimage.setChecked(False)
        elif self.uses_existing_portable:
            self.build_appimage.setToolTip("Build from the already-installed Portable source without replacing it from the archive.")
        else:
            self.build_appimage.setToolTip("Build from the Portable source installed from this archive.")
        self._sync_build_options(self.build_appimage.isChecked())
        self.completeChanged.emit()

    def _sync_build_options(self, checked: bool) -> None:
        self.install_icon.setChecked(checked)
        self.desktop.setChecked(self.make_active_after_install and not self.backend_only)
        self.prefer_installed.setEnabled(checked)
        self.keep_failed_build_files.setEnabled(checked)
        if not checked:
            self.prefer_installed.setChecked(False)
            self.keep_failed_build_files.setChecked(False)

    def isComplete(self) -> bool:  # noqa: N802 - Qt API
        if not self.destination.exists() or self.replace_existing.isChecked():
            return True
        return bool(self.build_appimage.isChecked() and self._existing_builder is not None)


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
        if self.options.uses_existing_portable:
            portable_action = "— Preserve existing Portable source (archive replacement not selected)"
        elif self.destination.exists():
            portable_action = "✓ Replace existing Portable source from the archive"
        else:
            portable_action = "✓ Install Portable source from the archive"
        lines = [
            f"Version action: {operation_labels.get(self.options.operation_mode, self.options.operation_mode)}",
            f"Active after install: {'Yes' if self.options.make_active_after_install else 'No'}",
            "",
            portable_action,
            f"  {self.destination}",
        ]
        if self.options.uses_existing_portable:
            lines.append("— Recovery archive unchanged because this ZIP is not replacing the existing Portable")
        else:
            lines.extend([
                "✓ Retain the validated original ZIP as this exact version's managed Recovery archive",
                f"  SHA-256: {self.inspection.archive_sha256}",
            ])
        if self.options.build_appimage.isChecked():
            lines.extend(
                [
                    (f"✓ Build from existing Portable source using {self.options._existing_builder.relative_to(self.destination) if self.options.uses_existing_portable and self.options._existing_builder else self.inspection.builder_relative}"),
                    ("— Keep temporary build files if the builder fails" if self.options.keep_failed_build_files.isChecked() else "✓ Remove temporary build files if the builder fails"),
                    "✓ Accept only an AppImage created or changed by this build",
                    "✓ Verify source/build version identity",
                    f"✓ Install managed AppImage under {appimage_root(self.installed_dir, self.inspection.name, self.inspection.version or self.inspection.builder_version)}",
                    "✓ Install the detected application logo",
                    ("— No standalone application-menu launcher (Suite-integrated backend)" if self.options.backend_only
                     else ("✓ Create/update the per-user application-menu launcher" if self.options.make_active_after_install else "— Preserve the existing desktop-integrated version")),
                    "✓ Write AppImage artifact identity and integrity metadata",
                    f"✓ Preferred launch mode: {'Installed when verified' if self.options.prefer_installed.isChecked() else 'Portable'}",
                ]
            )
        elif self.options.developer_mode:
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
        self.recovery_archive: Path | None = None
        self.recovery_metadata: Path | None = None
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
            # QListWidgetItem visibility only becomes reliable once the item is
            # owned by the list. Hide the Developer-only AppImage build path
            # *after* insertion so normal Portable installs never display it.
            if not self.options.developer_mode and key in {"prepare", "build", "verify", "appimage", "icon"}:
                item.setHidden(True)
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
            self._log(f"[suite] Source archive: {self.inspection.zip_path}")
            self._log(f"[suite] Archive SHA-256: {self.inspection.archive_sha256}")
            if self.options.uses_existing_portable:
                self.command_label.setText(f"Command: use existing Portable {self.options.destination}")
                self.editor_root = self.options.destination.expanduser().resolve(strict=False)
                if not self.editor_root.is_dir() or self.editor_root.is_symlink():
                    raise InstallError(f"Existing Portable source is missing or unsafe: {self.editor_root}")
                self._set_step("source", "done", "existing Portable preserved")
                self._log(f"[suite] Preserving existing Portable source: {self.editor_root}")
            else:
                current_archive_sha256 = sha256_file(self.inspection.zip_path)
                if current_archive_sha256.casefold() != self.inspection.archive_sha256.casefold():
                    raise InstallError("The source ZIP changed after inspection; installation was refused before Portable extraction.")
                self.command_label.setText(f"Command: import {self.inspection.zip_path}")
                # Different archive bytes under the SAME declared version must
                # not silently replace the former verified Recovery snapshot.
                retained = recovery_root(self.editors_root, self.inspection.name, self.options.incoming_version)
                if retained.exists():
                    old_info = _load_recovery_info(retained)
                    if old_info.sha256.casefold() != self.inspection.archive_sha256.casefold():
                        reply = QMessageBox.warning(
                            self, app_dialog_title('Same Version, Different Source ZIP'),
                            f'{self.inspection.name} {self.options.incoming_version} already has a different retained source ZIP.\n\n'
                            'Replace its Portable AND Recovery archive with this ZIP? The previous files will be staged '
                            'together and restored if import or retention fails. Its AppImage will be untouched.',
                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                            QMessageBox.StandardButton.No)
                        if reply != QMessageBox.StandardButton.Yes:
                            raise InstallError('Replacement cancelled; existing Portable and Recovery remain unchanged.')
                self.editor_root, self.editor, self.recovery_archive, self.recovery_metadata = install_portable_with_recovery(
                    self.inspection.zip_path, self.options.destination,
                    editors_root=self.editors_root, editor_id=self.inspection.editor_id,
                    name=self.inspection.name, version=self.options.incoming_version,
                    expected_sha256=self.inspection.archive_sha256,
                    config=self.config.as_dict(), installed_dir=self.installed_dir,
                    python_executable=self.launcher.python_executable(),
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
                    f"Component identity changed after source selection: expected {self.inspection.editor_id}, got {self.editor.editor_id}."
                )
            if self.options.uses_existing_portable and self.editor.source_version and self.options.incoming_version != "Unknown":
                if self.editor.source_version.casefold() != self.options.incoming_version.casefold():
                    raise InstallError(
                        f"Existing Portable version mismatch: expected {self.options.incoming_version}, got {self.editor.source_version}."
                    )
            self._set_step("identity", "done", self.editor.source_version or "version unknown")
            self._log(f"[suite] Identified {self.editor.name} ({self.editor.editor_id})")

            failure_step = "recovery"
            if self.options.uses_existing_portable:
                self._set_step("recovery", "skip", "existing Portable preserved; incoming ZIP not adopted")
            else:
                self._set_step("recovery", "active")
                recovery_version = self.editor.source_version or self.inspection.version or self.inspection.builder_version
                if not recovery_version:
                    raise InstallError("Cannot retain a Recovery archive without an exact source version.")
                recovery_dir = recovery_root(self.editors_root, self.editor.name, recovery_version)
                if recovery_dir.parent.resolve(strict=False) != self.editor_root.parent.resolve(strict=False):
                    raise InstallError("Recovery path does not match the installed Portable version folder.")
                if not self.recovery_archive or not self.recovery_metadata:
                    raise InstallError('Portable/Recovery atomic installation was incomplete.')
                self._set_step("recovery", "done", str(self.recovery_archive))
                self._log(f"[suite] Retained Recovery archive: {self.recovery_archive}")
                self._log(f"[suite] Recovery SHA-256: {self.inspection.archive_sha256}")

            if not self.options.build_appimage.isChecked():
                for key in ("prepare", "build", "verify", "appimage", "icon"):
                    self._set_step(key, "skip")
                if not self.options.make_active_after_install:
                    self._set_step("registry", "skip", "inactive version; desktop ownership preserved")
                original_preferences = copy.deepcopy(self.config.as_dict())
                desktop_file = desktop_entry_path(self.editor.editor_id)
                desktop_existed = desktop_file.is_file() and not desktop_file.is_symlink()
                desktop_bytes = desktop_file.read_bytes() if desktop_existed else None
                desktop_mode = desktop_file.stat().st_mode if desktop_existed else None
                self._set_active_launch_preference()
                self._force_safe_portable_preference_if_needed()
                failure_step = 'desktop'
                try:
                    self._synchronize_active_desktop()
                except (InstallError, OSError) as desktop_exc:
                    rollback_note = ''
                    try:
                        if desktop_existed and desktop_bytes is not None:
                            desktop_file.parent.mkdir(parents=True, exist_ok=True)
                            desktop_file.write_bytes(desktop_bytes)
                            if desktop_mode is not None:
                                desktop_file.chmod(desktop_mode)
                        elif not desktop_existed and desktop_file.is_file() and not desktop_file.is_symlink():
                            desktop_file.unlink()
                    except OSError as rollback_exc:
                        rollback_note = f' Desktop rollback also failed: {rollback_exc}.'
                    data = self.config.as_dict()
                    data.clear(); data.update(original_preferences)
                    self.config.save()
                    self._fail('desktop',
                        f'Portable and its Recovery ZIP are installed successfully, but desktop integration failed: {desktop_exc}. '
                        'The previous active selection is preserved. Use Repair Desktop Integration.' + rollback_note)
                    return
                failure_step = 'versions'
                self._apply_version_policy()
                self._finalize_success()
                return

            failure_step = "prepare"
            self._set_step("prepare", "active")
            self._build_script = find_appimage_build_script(self.editor_root)
            if self._build_script is None:
                source_label = "existing Portable" if self.options.uses_existing_portable else "installed Portable"
                raise InstallError(f"No AppImage builder is present in the {source_label} source selected for this build.")
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
        except Exception as exc:
            self._log("[suite] INTERNAL INSTALLER ERROR:\n" + "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            ))
            self._fail(
                failure_step,
                f"Unexpected installer error ({type(exc).__name__}): {exc}",
            )

    def _set_active_launch_preference(self) -> None:
        if self.editor is None or not self.options.make_active_after_install:
            return
        override = _editor_override(self.config, self.editor.editor_id)
        override["active_version"] = self.installed_version or self.editor.source_version or self.options.incoming_version
        override["launch_mode"] = "installed" if self.options.prefer_installed.isChecked() else "portable"
        self.config.save()

    def _synchronize_active_desktop(self, installed_icon: Path | None = None) -> Path | None:
        if self.editor is None:
            return None
        if self.options.backend_only:
            self._set_step("desktop", "skip", "Suite-integrated backend; no standalone launcher")
            if self.options.make_active_after_install:
                version = str(self.editor.source_version or self.options.incoming_version or "").strip()
                if version and version != "Unknown":
                    set_active_version(self.config.as_dict(), self.editor.editor_id, version)
                set_desktop_version(self.config.as_dict(), self.editor.editor_id, None)
            return None
        if not self.options.make_active_after_install:
            self._set_step("desktop", "skip", "existing active desktop integration preserved")
            return None
        self._set_step("desktop", "active")
        if self.options.prefer_installed.isChecked():
            if self.installed_appimage is None or not self.installed_appimage.is_file():
                raise InstallError("Installed AppImage is selected as the launch runtime, but no verified AppImage is available for this version.")
            desktop = synchronize_desktop_integration(
                self.editor.name,
                self.editor.editor_id,
                self.installed_appimage,
                installed_icon,
                self.editor.root,
            )
            runtime_label = "AppImage"
        else:
            if not self.editor.portable_command:
                raise InstallError("Portable is selected as the launch runtime, but this version has no Portable command.")
            desktop = synchronize_portable_desktop_integration(
                self.editor.name,
                self.editor.editor_id,
                self.editor.portable_command,
                installed_icon or self.editor.icon,
                self.editor.root,
            )
            runtime_label = "Portable"
        self.refresh_desktop_callback(desktop.parent)
        if runtime_label == "Portable":
            # synchronize_portable_desktop_integration() has already written and
            # verified the real launcher. Give that exact Portable version the
            # verified active selection too; the actual launcher remains authoritative.
            self._set_step("registry", "active")
            version = str(self.editor.source_version or self.options.incoming_version or "").strip()
            if not version or version == "Unknown":
                # Do not fabricate a managed version when identity is unknown.
                set_desktop_version(self.config.as_dict(), self.editor.editor_id, None)
                self._set_step("registry", "skip", "no exact version identity")
            else:
                existing = get_managed_versions(self.config.as_dict(), self.editor.editor_id).get(version, {})
                record = dict(existing)  # Retain any same-version AppImage/hash.
                icon = installed_icon or self.editor.icon
                record.update({
                    "schema": 2,
                    "editor_id": self.editor.editor_id,
                    "application_id": self.editor.editor_id,
                    "name": self.editor.name,
                    "version": version,
                    "desktop_file_path": str(desktop),
                    "desktop_id": desktop_id_for(self.editor.editor_id),
                    "icon_path": str(icon) if icon else None,
                    "source_version": version,
                    "extensions": list(self.editor.extensions),
                    "description": self.editor.description,
                    "publisher_id": self.editor.publisher_id,
                })
                self.registry_record = set_managed_installation(
                    self.config.as_dict(), record, set_active=True, desktop_integrated=True,
                )
            if not self.config.save():
                raise InstallError("Could not save verified Portable desktop ownership in Suite Pythoine preferences.")
            if version and version != "Unknown":
                self._set_step("registry", "done", f"{version} owns the desktop launcher")
        self._set_step("desktop", "done", f"{runtime_label}: {desktop.name}")
        self._log(f"[suite] Active desktop launcher synchronized to {runtime_label} runtime: {desktop}")
        return desktop

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
                    clean_build_dirs(self.editor_root, self._build_script, include_dist=True)
                    cleanup_note = " Temporary build directories and generated dist output were removed to reclaim storage."
                    self._log("[suite] Removed temporary build directories and generated dist output after the failed AppImage build.")
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
                "If you successfully build the AppImage separately, drag that .AppImage onto Suite Pythoine or use Tools → Install Application… to adopt it.",
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

        # Register the verified AppImage before version-policy cleanup, but do
        # not claim the shared desktop launcher yet. Older active versions may
        # still own that singleton file and can legitimately remove it while
        # they are being retired. Desktop ownership is synchronized last.
        self._set_step("registry", "active")
        record, metadata = self.register_callback(
            self.editor,
            installed,
            None,
            installed_icon,
            version=self.installed_version,
            source_artifact=artifact,
            build_script=self._build_script,
            set_active=self.options.make_active_after_install,
            desktop_integrated=False,
        )
        self.registry_record = record
        override = _editor_override(self.config, self.editor.editor_id)
        for key in ("installed_path", "installed_version", "installed_source_version", "installed_sha256", "built_artifact", "build_script"):
            override.pop(key, None)
        self._set_active_launch_preference()
        self.config.save()
        self._set_step("registry", "done", metadata.name)

        clean_build_dirs(self.editor_root, self._build_script, include_dist=True)
        self._log("[suite] Removed temporary build directories and generated dist output after managed AppImage installation.")

        # Version retirement happens before desktop synchronization. This is
        # essential when the previous version owned the single .desktop file:
        # removing that older version must never erase the newly active launcher's
        # final state or force the user to run Repair afterwards.
        desktop = self._synchronize_active_desktop(installed_icon)
        self._apply_version_policy()

        if desktop is not None and self.options.prefer_installed.isChecked():
            record, metadata = self.register_callback(
                self.editor,
                installed,
                desktop,
                installed_icon,
                version=self.installed_version,
                source_artifact=artifact,
                build_script=self._build_script,
                set_active=True,
                desktop_integrated=True,
            )
            self.registry_record = record
            self.config.save()
        self._finalize_success()

    def _remove_managed_version_now(self, version: str) -> None:
        """Retire an exact superseded version only after boundary/launcher checks.

        The old 0.8.0 version of this helper deleted a full folder without
        checking for unrelated root files and consulted a registry projection.
        """
        if self.editor is None:
            return
        from .storage_layout import validate_version_boundary
        from .installation_state import desktop_selection
        container = version_root(self.editors_root, self.editor.name, version)
        if not container.exists() and not container.is_symlink():
            return
        validate_version_boundary(container, self.editors_root)
        # Inspect the post-install inventory, not the pre-install wizard card:
        # it must include the newly integrated replacement version too.
        from .registry import discover_editors
        current = next((e for e in discover_editors(self.editors_root, self.installed_dir,
            self.config.as_dict(), python_executable=self.launcher.python_executable())
            if e.editor_id == self.editor.editor_id), None)
        if current is None:
            raise InstallError('Could not verify newly installed component inventory before cleanup.')
        selection, active, _runtime = desktop_selection(
            self.editor.editor_id, {v.version: v for v in current.versions}, self.editors_root)
        if selection != 'ready':
            raise InstallError('The incoming desktop runtime is not independently verified; superseded version preserved.')
        if selection == 'ready' and active == version:
            raise InstallError(f'Cannot retire {version}: its current desktop integration has not been handed off.')
        if selection in ('broken', 'legacy-launcher', 'external-target'):
            raise InstallError(f'Cannot retire {version} while desktop integration requires explicit repair.')
        staged = container.with_name('.' + container.name + '.upgrade-remove-' + uuid.uuid4().hex[:10])
        if staged.exists() or staged.is_symlink():
            raise InstallError(f'Version cleanup staging collision: {staged}')
        os.replace(container, staged)
        try:
            shutil.rmtree(staged)
        except OSError as exc:
            try:
                os.replace(staged, container)
            except OSError as rollback_exc:
                raise InstallError(f'Cleanup failed: {exc}; rollback incomplete, staged version: {staged}: {rollback_exc}') from exc
            raise InstallError(f'Could not delete superseded {version}; original version restored: {exc}') from exc
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
        if self.editor is None or not self.options.make_active_after_install:
            return  # A test installation must never alter the active runtime preference.
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
            if self.progress.recovery_archive:
                lines.append(f"\nRecovery archive:\n{self.progress.recovery_archive}")
                lines.append(f"Recovery SHA-256: {self.inspection.archive_sha256}")
            if self.progress.installed_appimage:
                lines.append(f"\nAppImage file:\n{self.progress.installed_appimage}")
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
        advanced = bool(getattr(getattr(parent, 'developer_config', None), 'enabled', False))
        self.welcome_page = WelcomePage(inspection, developer_mode=advanced)
        self.options_page = OptionsPage(
            inspection, destination=destination, installed_dir=installed_dir,
            existing_editor=existing_editor, developer_mode=advanced,
        )
        self.options_page.make_active.setChecked(True)
        self.options_page.make_active.setVisible(True)
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
