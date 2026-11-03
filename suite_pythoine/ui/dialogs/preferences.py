from __future__ import annotations

from pathlib import Path
import sys

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ... import APP_NAME
from ...catalogue.component_policy import document_candidates, is_backend_only_component, is_hub
from ...config import ConfigService
from ...developer.developer_intake import DeveloperComponentCatalog, DeveloperIntakeConfig, DeveloperSettingsDialog
from ...recovery import recovery_available
from ...registry import EditorEntry, EditorVersionInfo, saved_launch_mode
from ...runtime.runtime_paths import RuntimePaths
from ...routing.silent_dispatch import ASK_EVERY_TIME, INSPECTOR_FALLBACK_ASK
from ...storage_layout import recovery_root
from ...ui_titles import app_dialog_title
from ..diagnostic_helpers import (
    _diagnostic_canvas, _populate_diagnostic_canvas, _style_destructive_button,
)


class EditorPreferencesDialog(QDialog):
    def __init__(self, parent, editor: EditorEntry, config: ConfigService) -> None:
        super().__init__(parent)
        self.editor = editor
        self.config = config
        self.setWindowTitle(app_dialog_title("Preferences"))
        self.setMinimumWidth(580)

        layout = QVBoxLayout(self)
        heading = QLabel(editor.name)
        heading_font = heading.font()
        heading_font.setBold(True)
        heading.setFont(heading_font)
        layout.addWidget(heading)
        form = QFormLayout()

        self.mode = QComboBox()
        self.mode.addItem("Automatic", "auto")
        self.mode.addItem("Portable / source", "portable")
        self.mode.addItem("AppImage", "installed")
        self.mode.setCurrentIndex(max(0, self.mode.findData(saved_launch_mode(config.as_dict(), editor.editor_id))))
        form.addRow("Launch runtime:", self.mode)

        layout.addLayout(form)
        if is_hub(editor):
            info = QLabel(
                "This controls the active Suite Pythoine runtime. On Linux, desktop integration follows that active runtime directly, "
                "so application-menu launches and OS-routed files use the same Suite generation. "
                "Document and special drop routing remain independent of this preference."
            )
        else:
            info = QLabel(
                "Launch-runtime changes affect routing immediately. On Linux, Suite also retargets this application's "
                "desktop launcher to the active version using the selected runtime; Repair Desktop Integration can reapply that mapping."
            )
        info.setWordWrap(True)
        layout.addWidget(info)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def apply(self) -> None:
        overrides = self.config.get("editor_overrides", {})
        if not isinstance(overrides, dict):
            overrides = {}
            self.config.set("editor_overrides", overrides)
        override = overrides.setdefault(self.editor.editor_id, {})
        if not isinstance(override, dict):
            override = {}
            overrides[self.editor.editor_id] = override
        override["launch_mode"] = self.mode.currentData()
        # Retired manual path/format overrides cannot affect discovery or routing.
        override.pop("installed_path", None)
        override.pop("extensions", None)
        self.config.set("routing_index", {})
        self.config.save()


class GeneralPreferencesDialog(QDialog):
    AUTOMATIC = "__automatic__"

    def __init__(
        self,
        parent,
        config: ConfigService,
        runtime: RuntimePaths,
        editors_root: Path,
        editors: list[EditorEntry],
        suite_entry: EditorEntry | None = None,
        developer_config: DeveloperIntakeConfig | None = None,
        developer_catalog: DeveloperComponentCatalog | None = None,
    ) -> None:
        super().__init__(parent)
        self.controller = parent
        self.config = config
        self.runtime = runtime
        # The managed Applications folder is a Path; self.editors_root below is
        # its editable QLineEdit. Recovery lookup must not receive the widget.
        self._managed_editors_root = Path(editors_root)
        self.editors = list(editors)
        self.suite_entry = suite_entry
        self.developer_config = developer_config
        self.developer_catalog = developer_catalog
        self.routing_boxes: dict[str, QComboBox] = {}
        self.setWindowTitle(app_dialog_title("Hub Preferences"))
        self.setMinimumSize(820, 640)
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        # 1. General: application storage, launch runtime, Dashboard and Developer.
        general = QWidget()
        general_layout = QVBoxLayout(general)
        info = QLabel(
            f"Default Applications folder: {runtime.default_editors_root}\n"
            "Portable and AppImage runtimes share this one managed applications root.\n"
            f"Normal preferences: {runtime.config_path}"
        )
        info.setTextFormat(Qt.TextFormat.PlainText)
        info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        info.setWordWrap(True)
        general_layout.addWidget(info)

        form = QFormLayout()
        root_row = QHBoxLayout()
        self.editors_root = QLineEdit(str(editors_root))
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_editors_root)
        root_row.addWidget(self.editors_root, 1)
        root_row.addWidget(browse)
        form.addRow("Applications folder:", root_row)
        general_layout.addLayout(form)

        open_components = QPushButton("Open Applications Folder  (Ctrl+Shift+O)")
        open_components.clicked.connect(self._open_components_folder)
        folder_actions = QHBoxLayout()
        folder_actions.addWidget(open_components)
        open_config = QPushButton("Open Config Folder")
        open_config.clicked.connect(lambda: self.controller.launcher.open_path(self.runtime.config_path.parent))
        folder_actions.addWidget(open_config)
        folder_actions.addStretch(1)
        general_layout.addLayout(folder_actions)

        # The four Suite-only runtime controls share one row before Dashboard.
        runtime_group = QGroupBox("Runtime")
        runtime_row = QHBoxLayout(runtime_group)
        runtime_row.addWidget(QLabel("Launch:"))
        self.suite_runtime = QComboBox()
        self.suite_runtime.addItem("Automatic", "auto")
        self.suite_runtime.addItem("Portable / source", "portable")
        self.suite_runtime.addItem("AppImage", "installed")
        current_suite_mode = saved_launch_mode(config.as_dict(), "suite-pythoine")
        self.suite_runtime.setCurrentIndex(max(0, self.suite_runtime.findData(current_suite_mode)))
        self.suite_runtime.setToolTip("Controls the runtime used for interactive Suite Pythoine launches. Document routing is decided first.")
        runtime_row.addWidget(self.suite_runtime, 1)
        self.repair_desktop_button = QPushButton("Repair Desktop Integration")
        self.repair_desktop_button.clicked.connect(self._repair_desktop_integration)
        self.repair_desktop_button.setToolTip("Repair the verified Suite desktop launcher for the selected active version and saved runtime preference.")
        runtime_row.addWidget(self.repair_desktop_button)
        self.open_portable_button = QPushButton("Portable Folder")
        self.open_portable_button.clicked.connect(self._open_portable_folder)
        runtime_row.addWidget(self.open_portable_button)
        self.open_installed_button = QPushButton("AppImage Folder")
        self.open_installed_button.clicked.connect(self._open_installed_folder)
        runtime_row.addWidget(self.open_installed_button)
        general_layout.addWidget(runtime_group)

        dashboard_group = QGroupBox("Dashboard")
        dashboard_layout = QVBoxLayout(dashboard_group)
        self.show_dashboard_icons = QCheckBox("Show application icons on Dashboard  (Ctrl+Alt+Shift+I)")
        self.show_dashboard_icons.setChecked(bool(config.get("dashboard_show_icons", True)))
        dashboard_layout.addWidget(self.show_dashboard_icons)
        self.show_drop_bar = QCheckBox("Show Drop Bar  (Ctrl+Alt+Shift+B)")
        self.show_drop_bar.setChecked(bool(config.get("dashboard_drop_bar_visible", True)))
        dashboard_layout.addWidget(self.show_drop_bar)
        dashboard_view_shortcut = QLabel("Toggle List/Grid view: Ctrl+Alt+Shift+V")
        dashboard_layout.addWidget(dashboard_view_shortcut)
        general_layout.addWidget(dashboard_group)
        self.show_quick_tour_on_startup = QCheckBox("Show Quick Tour on startup  (Shift+F1 to open manually)")
        self.show_quick_tour_on_startup.setChecked(bool(config.get("show_quick_tour_on_startup", True)))
        general_layout.addWidget(self.show_quick_tour_on_startup)

        developer_group = QGroupBox("Developer")
        developer_layout = QVBoxLayout(developer_group)
        self.developer_enabled = QCheckBox("Enable Developer Mode  (F12)")
        self.developer_enabled.setChecked(bool(developer_config.enabled) if developer_config is not None else False)
        self.developer_enabled.setToolTip(
            "Normal ZIP/AppImage installation remains available with optional build enhancements. "
            "In Developer Mode, a normal ZIP drop opens Developer Intake; hold Shift to bypass Intake and install normally, "
            "or Ctrl+ZIP to retain Recovery only."
        )
        developer_layout.addWidget(self.developer_enabled)
        self.developer_note = QLabel(
            "Developer Mode adds optional AppImage building to the normal installation workflow. "
            "Normal ZIP drops open Developer Intake; Shift+ZIP bypasses Intake for the normal guided installer, "
            "and Ctrl+ZIP retains only the original source in Recovery. "
            "Store Pythoine and ordinary document routing remain unchanged."
        )
        self.developer_note.setWordWrap(True)
        developer_layout.addWidget(self.developer_note)
        self.developer_configure = QPushButton("Configure Developer Intake…")
        self.developer_configure.clicked.connect(self._configure_developer)
        developer_layout.addWidget(self.developer_configure, 0, Qt.AlignmentFlag.AlignLeft)
        self.developer_enabled.toggled.connect(self._sync_developer_controls)
        general_layout.addWidget(developer_group)
        self._sync_developer_controls(self.developer_enabled.isChecked())
        general_layout.addStretch(1)
        # Consolidated Runtime controls increase General's height; keep all
        # existing settings accessible at the dialog's established minimum size.
        general_scroll = QScrollArea()
        general_scroll.setWidgetResizable(True)
        general_scroll.setFrameShape(QFrame.Shape.NoFrame)
        general_scroll.setWidget(general)
        self.tabs.addTab(general_scroll, "General")

        # 2. File Routing: retained unchanged in purpose and kept independent of
        # Developer Intake.
        routing_page = QWidget()
        routing_outer = QVBoxLayout(routing_page)
        routing_note = QLabel(
            "Suite Pythoine remains the operating-system file handler. Editors and Readers that advertise supported formats appear here. "
            "Automatic routes directly when one application is eligible and asks with a compact chooser when several are eligible."
        )
        routing_note.setWordWrap(True)
        routing_outer.addWidget(routing_note)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        routing_body = QWidget()
        routing_form = QFormLayout(routing_body)
        preferences = config.get("extension_preferences", {})
        if not isinstance(preferences, dict):
            preferences = {}
        extensions = sorted({extension for editor in self.editors for extension in editor.extensions})
        for extension in extensions:
            candidates = document_candidates(self.editors, extension)
            if not candidates:
                continue
            combo = QComboBox()
            combo.addItem("Automatic", self.AUTOMATIC)
            if len(candidates) > 1:
                combo.addItem("Ask every time", ASK_EVERY_TIME)
            for candidate in candidates:
                combo.addItem(candidate.name, candidate.editor_id)
            current = preferences.get(extension)
            index = combo.findData(current) if current is not None else combo.findData(self.AUTOMATIC)
            combo.setCurrentIndex(max(0, index))
            combo.setToolTip("Eligible applications: " + ", ".join(candidate.name for candidate in candidates))
            routing_form.addRow(extension, combo)
            self.routing_boxes[extension] = combo
        scroll.setWidget(routing_body)
        routing_outer.addWidget(scroll, 1)

        fallback_group = QGroupBox("Unsupported-file inspection fallback")
        fallback_form = QFormLayout(fallback_group)
        self.inspector_fallback = QComboBox()
        self.inspector_fallback.addItem("Ask every time", INSPECTOR_FALLBACK_ASK)
        available_ids = {editor.editor_id for editor in self.editors if editor.available}
        self.inspector_fallback.addItem(
            "Beespector" + ("" if "beespector" in available_ids else " (not installed)"),
            "beespector",
        )
        self.inspector_fallback.addItem(
            "Beespector Lite" + ("" if "beespector-lite" in available_ids else " (not installed)"),
            "beespector-lite",
        )
        fallback_value = str(config.get("inspector_fallback_preference") or INSPECTOR_FALLBACK_ASK)
        fallback_index = self.inspector_fallback.findData(fallback_value)
        self.inspector_fallback.setCurrentIndex(max(0, fallback_index))
        self.inspector_fallback.setToolTip(
            "Used only after normal validated Editor/Reader routing finds zero installed eligible applications. "
            "It does not add MIME associations or make Beespector a normal routing candidate."
        )
        fallback_form.addRow("When no routed application is available:", self.inspector_fallback)
        fallback_note = QLabel(
            "Beespector fallback is internal to Suite Pythoine and is evaluated only after normal routing returns zero candidates."
        )
        fallback_note.setWordWrap(True)
        fallback_form.addRow("", fallback_note)
        routing_outer.addWidget(fallback_group)

        self.routing_reset_button = QPushButton("Reset Routing Choices")
        self.routing_reset_button.clicked.connect(self._reset_routing)
        self.tabs.addTab(routing_page, "File Routing")

        # 4. Versions: the same per-version launch/activation/removal/folder
        # controls as Suite Details.
        versions_page = QWidget()
        versions_outer = QVBoxLayout(versions_page)
        versions_note = QLabel("Available Suite Pythoine versions. Portable and AppImage runtimes are independently launchable; Make Active selects the version and runtime for desktop integration.")
        versions_note.setWordWrap(True)
        versions_outer.addWidget(versions_note)
        self.versions_scroll = QScrollArea()
        self.versions_scroll.setWidgetResizable(True)
        self.versions_scroll.setFrameShape(QFrame.Shape.NoFrame)
        versions_outer.addWidget(self.versions_scroll, 1)
        self.tabs.addTab(versions_page, "Hub Versions")
        self.uninstall_suite_button = QPushButton("Uninstall Suite…")
        _style_destructive_button(self.uninstall_suite_button)
        self.uninstall_suite_button.setToolTip("Choose Hub Only, Selective Suite Purge or Full Suite Purge in the reviewed wizard.")
        self.uninstall_suite_button.clicked.connect(self._open_suite_uninstaller)

        # Suite diagnostics belong only in Preferences, never a redundant App Page button.
        information_page = QWidget()
        information_layout = QVBoxLayout(information_page)
        self.information_label = _diagnostic_canvas(information_page)
        information_layout.addWidget(self.information_label, 1)
        self.tabs.addTab(information_page, "Technical Details")
        self.open_suite_development_button = QPushButton("Open Development Folder")
        self.open_suite_development_button.setToolTip("Open Suite Pythoine's configured Developer Intake root.")
        self.open_suite_development_button.clicked.connect(
            lambda _checked=False: self.controller._open_development_root("suite-pythoine", APP_NAME)
        )

        self._refresh_suite_management_views()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        footer = QHBoxLayout()
        footer.addWidget(self.routing_reset_button)
        footer.addWidget(self.uninstall_suite_button)
        footer.addWidget(self.open_suite_development_button)
        footer.addStretch(1)
        footer.addWidget(buttons)
        layout.addLayout(footer)
        self.tabs.currentChanged.connect(self._sync_contextual_footer)
        self._sync_contextual_footer(self.tabs.currentIndex())

    def _sync_contextual_footer(self, index: int) -> None:
        label = self.tabs.tabText(index) if 0 <= index < self.tabs.count() else ""
        self.routing_reset_button.setVisible(label == "File Routing")
        self.uninstall_suite_button.setVisible(label == "Hub Versions")
        self.open_suite_development_button.setVisible(
            label == "Technical Details" and bool(self.developer_config and self.developer_config.enabled)
        )

    def _open_suite_uninstaller(self) -> None:
        # Do not silently apply unsaved preferences while starting a destructive flow.
        self.reject()
        QTimer.singleShot(0, self.controller.show_uninstall_suite)

    def _current_suite_entry(self) -> EditorEntry | None:
        current = getattr(self.controller, "suite_entry", None)
        if isinstance(current, EditorEntry):
            self.suite_entry = current
        return self.suite_entry

    def _refresh_suite_management_views(self) -> None:
        editor = self._current_suite_entry()
        if editor is None:
            self.open_portable_button.setEnabled(False)
            self.repair_desktop_button.setEnabled(False)
            self.open_installed_button.setEnabled(False)
            _populate_diagnostic_canvas(self.information_label, "Suite Pythoine application information is unavailable until the application inventory is refreshed.")
            body = QWidget(); body_layout = QVBoxLayout(body); body_layout.addWidget(QLabel("No Suite Pythoine version inventory is currently available.")); body_layout.addStretch(1)
            self.versions_scroll.setWidget(body)
            return

        active_info = next((item for item in editor.versions if item.version == editor.active_version), None)
        portable_root = active_info.portable_root if active_info and active_info.has_portable else None
        appimage = active_info.appimage_path if sys.platform.startswith("linux") and active_info and active_info.has_appimage else None
        self.open_portable_button.setEnabled(portable_root is not None)
        self.repair_desktop_button.setEnabled(bool(
            sys.platform.startswith("linux") and any(
                not item.validation_issue and (item.has_portable or item.has_appimage) for item in editor.versions
            )
        ))
        self.open_installed_button.setEnabled(bool(sys.platform.startswith("linux") and appimage is not None))
        _populate_diagnostic_canvas(self.information_label, self.controller._editor_information_text(editor))

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(10)
        if not editor.versions:
            empty = QLabel("No managed Suite Pythoine versions are currently present.")
            empty.setWordWrap(True)
            body_layout.addWidget(empty)
        else:
            for version_info in editor.versions:
                body_layout.addWidget(self._preferences_version_frame(editor, version_info))
        body_layout.addStretch(1)
        self.versions_scroll.setWidget(body)

    def _preferences_version_frame(self, editor: EditorEntry, version_info: EditorVersionInfo) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(10, 8, 10, 8)
        labels = [version_info.version]
        if version_info.version == editor.active_version:
            labels.append("Active")
        if version_info.desktop_integrated or version_info.version == editor.desktop_version:
            labels.append("Desktop integrated")
        title = QLabel(" — ".join(labels))
        title_font = title.font(); title_font.setBold(True); title.setFont(title_font)
        frame_layout.addWidget(title)
        recovery_dir = version_info.recovery_dir or recovery_root(self._managed_editors_root, editor.name, version_info.version)
        has_recovery = recovery_available(recovery_dir)
        desktop_state = ("Not applicable" if is_backend_only_component(editor)
                         else ("Active" if version_info.desktop_integrated else "No"))
        state = QLabel(
            f"Portable: {'Yes' if version_info.has_portable else 'No'}   "
            f"AppImage: {'Yes' if version_info.has_appimage else 'No'}   "
            f"Recovery: {'Available' if has_recovery else 'Unavailable'}   "
            f"Desktop: {desktop_state}"
        )
        state.setTextFormat(Qt.TextFormat.PlainText)
        frame_layout.addWidget(state)
        actions = QHBoxLayout()

        make_active = QPushButton("Make Active")
        make_active.setEnabled(
            not version_info.validation_issue and version_info.version != editor.active_version
            and (version_info.has_portable or version_info.has_appimage)
        )
        make_active.clicked.connect(lambda _checked=False, item=version_info: self._make_version_active(item))
        actions.addWidget(make_active)

        launch_portable = QPushButton("Launch Portable")
        launch_portable.setEnabled(version_info.has_portable and not version_info.validation_issue)
        launch_portable.clicked.connect(lambda _checked=False, item=version_info: self.controller.launch_editor_version(editor, item, "portable"))
        actions.addWidget(launch_portable)

        launch_appimage = QPushButton("Launch AppImage")
        launch_appimage.setEnabled(version_info.has_appimage and not version_info.validation_issue)
        launch_appimage.clicked.connect(lambda _checked=False, item=version_info: self.controller.launch_editor_version(editor, item, "appimage"))
        actions.addWidget(launch_appimage)

        open_folder = QPushButton("Open Version Folder")
        folder: Path | None = None
        if version_info.portable_root is not None and version_info.portable_root.is_dir():
            folder = version_info.portable_root.parent
        elif version_info.appimage_path is not None:
            folder = version_info.appimage_path.parent.parent
        elif has_recovery:
            folder = recovery_dir.parent
        open_folder.setEnabled(folder is not None)
        if folder is not None:
            open_folder.clicked.connect(lambda _checked=False, target=folder: self.controller.launcher.open_path(target))
        actions.addWidget(open_folder)
        remove_version = QPushButton("Uninstall Version…")
        remove_version.setEnabled(not version_info.validation_issue)
        remove_version.clicked.connect(lambda _checked=False, item=version_info: self._remove_version(item))
        actions.addWidget(remove_version)

        actions.addStretch(1)
        frame_layout.addLayout(actions)
        return frame

    def _make_version_active(self, version_info: EditorVersionInfo) -> None:
        editor = self._current_suite_entry()
        if editor is None:
            return
        self.controller.make_version_active(editor, version_info)
        self._refresh_suite_management_views()

    def _remove_version(self, version_info: EditorVersionInfo) -> None:
        editor = self._current_suite_entry()
        if editor is None:
            return
        self.controller.remove_editor_version(editor, version_info)
        self._refresh_suite_management_views()

    def _sync_developer_controls(self, enabled: bool) -> None:
        self.developer_note.setVisible(bool(enabled))
        self.developer_configure.setVisible(bool(enabled))

    def _configure_developer(self) -> None:
        if self.developer_config is None or self.developer_catalog is None:
            return
        dialog = DeveloperSettingsDialog(self, self.developer_config, self.developer_catalog)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            dialog.apply()
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, app_dialog_title("Developer Configuration Error"), str(exc))

    def _browse_editors_root(self) -> None:
        path = QFileDialog.getExistingDirectory(self, app_dialog_title("Choose Applications Folder"), self.editors_root.text())
        if path:
            self.editors_root.setText(path)

    def _open_components_folder(self) -> None:
        raw = self.editors_root.text().strip()
        target = Path(raw).expanduser() if raw else self.runtime.default_editors_root
        self.controller.launcher.open_path(target)

    def _open_portable_folder(self) -> None:
        editor = self._current_suite_entry()
        if editor is None:
            return
        active_info = next((item for item in editor.versions if item.version == editor.active_version), None)
        portable_path = active_info.portable_root if active_info and active_info.has_portable else None
        if portable_path is not None:
            self.controller.launcher.open_path(portable_path)

    def _repair_desktop_integration(self) -> None:
        editor = self._current_suite_entry()
        if editor is None:
            return
        # This action repairs the SAVED launch preference. Do not silently use
        # an unsaved combo-box selection or repair to a contradictory runtime.
        selected = str(self.suite_runtime.currentData() or "auto")
        saved = saved_launch_mode(self.config.as_dict(), "suite-pythoine")
        if selected != saved:
            QMessageBox.information(
                self, app_dialog_title("Save Runtime Preference First"),
                "Save the changed Launch runtime preference, then reopen Preferences "
                "to repair Desktop Integration for the newly saved runtime."
            )
            return
        self.controller.repair_suite_desktop_integration(editor)
        self._refresh_suite_management_views()

    def _open_installed_folder(self) -> None:
        editor = self._current_suite_entry()
        if editor is None:
            return
        active_info = next((item for item in editor.versions if item.version == editor.active_version), None)
        appimage = active_info.appimage_path if active_info and active_info.has_appimage else None
        if appimage is not None:
            self.controller.launcher.open_path(appimage.parent)

    def _reset_routing(self) -> None:
        for combo in self.routing_boxes.values():
            index = combo.findData(self.AUTOMATIC)
            combo.setCurrentIndex(max(0, index))
        index = self.inspector_fallback.findData(INSPECTOR_FALLBACK_ASK)
        self.inspector_fallback.setCurrentIndex(max(0, index))

    def apply(self) -> None:
        self.config.set("editors_root", self.editors_root.text().strip() or None)
        overrides = self.config.get("editor_overrides", {})
        if not isinstance(overrides, dict):
            overrides = {}
            self.config.set("editor_overrides", overrides)
        suite_override = overrides.setdefault("suite-pythoine", {})
        if not isinstance(suite_override, dict):
            suite_override = {}
            overrides["suite-pythoine"] = suite_override
        suite_override["launch_mode"] = str(self.suite_runtime.currentData() or "auto")
        preferences: dict[str, str] = {}
        for extension, combo in self.routing_boxes.items():
            value = str(combo.currentData() or self.AUTOMATIC)
            if value != self.AUTOMATIC:
                preferences[extension] = value
        self.config.set("extension_preferences", preferences)
        self.config.set("inspector_fallback_preference", str(self.inspector_fallback.currentData() or INSPECTOR_FALLBACK_ASK))
        self.config.set("routing_index", {})
        self.config.set("dashboard_show_icons", self.show_dashboard_icons.isChecked())
        self.config.set("dashboard_drop_bar_visible", self.show_drop_bar.isChecked())
        self.config.set("show_quick_tour_on_startup", self.show_quick_tour_on_startup.isChecked())
        self.config.save()
        if self.developer_config is not None:
            if not self.developer_config.set_enabled(self.developer_enabled.isChecked(), save=True):
                raise OSError(f"Could not save Developer Intake mode to {self.developer_config.path}")
