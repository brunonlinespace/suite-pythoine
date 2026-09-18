from __future__ import annotations

from pathlib import Path
import copy
import html
import os
import sys

from PyQt6.QtCore import QEvent, QSize, QTimer, Qt, QUrl
from PyQt6.QtGui import QAction, QActionGroup, QCloseEvent, QDragEnterEvent, QDropEvent, QIcon, QKeySequence, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import APP_NAME, __version__
from .config import ConfigService
from .dashboard import EditorDashboard
from .install_inspection import inspect_editor_zip
from .install_wizard import EditorInstallWizard
from .appimage_inspection import inspect_appimage
from .appimage_wizard import AppImageInstallWizard
from .editor_watcher import EditorDirectoryWatcher
from .installer import (
    InstallError,
    desktop_applications_dir,
    desktop_entry_path,
    desktop_entry_status,
    desktop_entry_runtime,
    portable_desktop_entry_status,
    install_icon,
    installed_icon_candidates,
    managed_appimages,
    sha256_file,
    uninstall_registered_appimage_integration,
    remove_portable_editor_folder,
    write_appimage_metadata,
    synchronize_desktop_integration,
    synchronize_portable_desktop_integration,
)
from .managed_registry import (
    desktop_id_for,
    get_managed_group,
    get_managed_installation,
    get_managed_versions,
    record_paths,
    remove_managed_installation,
    remove_managed_version,
    set_active_version,
    set_desktop_version,
    set_managed_installation,
)
from .registry import EditorEntry, EditorVersionInfo, discover_editors, normalize_extension
from .component_policy import can_create_document, can_open_document, document_candidates, document_editors, document_readers, is_hub, is_extension, routable_components
from .component_catalog import profile_for_id
from .developer_intake import (
    DeveloperComponentCatalog,
    DeveloperIntakeConfig,
    DeveloperIntakeDialog,
    DeveloperSettingsDialog,
)
from .routing_index import build_index_payload
from .silent_dispatch import ASK_EVERY_TIME, INSPECTOR_FALLBACK_ASK, INSPECTOR_FALLBACK_IDS
from .versioning import appimage_metadata_path, read_appimage_metadata
from .runtime_launcher import LaunchCommand, RuntimeLauncher
from .runtime_paths import RuntimePaths
from .purge_wizard import PurgeEditorWizard
from .ui_titles import app_dialog_title
from .storage_layout import is_within, prune_empty_parents, prune_empty_version_tree, version_root
from .storage_migration import build_migration_plan
from .shortcuts_dialog import ShortcutsDialog
from .migration_wizard import StorageMigrationWizard
from .root_transition import transition_legacy_default_root


ASSETS_DIR = Path(__file__).resolve().parent / "assets"
APP_ICON_PATH = ASSETS_DIR / "suite-pythoine-256.png"
ABOUT_ICON_PATH = ASSETS_DIR / "suite-pythoine-128.png"
GITHUB_URL = "https://github.com/brunonlinespace/suite-pythoine"
ISSUES_URL = f"{GITHUB_URL}/issues"


class SortableTableItem(QTableWidgetItem):
    """QTableWidget item that sorts by a hidden UserRole value when present."""

    def __lt__(self, other: QTableWidgetItem) -> bool:
        left = self.data(Qt.ItemDataRole.UserRole)
        right = other.data(Qt.ItemDataRole.UserRole)
        if left is not None and right is not None and type(left) is type(right):
            try:
                return left < right
            except TypeError:
                pass
        return super().__lt__(other)


def _human_size(value: int) -> str:
    size = float(max(0, value))
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024.0 or unit == "TiB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{int(value)} B"


def _tree_size(path: Path | None) -> int:
    if path is None:
        return 0
    target = path.expanduser().resolve(strict=False)
    try:
        if target.is_file() and not target.is_symlink():
            return target.stat().st_size
    except OSError:
        return 0
    total = 0
    if not target.is_dir():
        return 0
    for root, dirs, files in os.walk(target, followlinks=False):
        root_path = Path(root)
        dirs[:] = [name for name in dirs if not (root_path / name).is_symlink()]
        for name in files:
            candidate = root_path / name
            try:
                if not candidate.is_symlink():
                    total += candidate.stat().st_size
            except OSError:
                continue
    return total


def _install_timestamp(paths: list[Path]) -> float:
    stamps: list[float] = []
    for path in paths:
        try:
            # Version/runtime container mtime best approximates when Suite created
            # the managed installation. Linux does not expose a portable birthtime.
            target = path.parent if path.is_file() else path
            stamps.append(target.stat().st_mtime)
        except OSError:
            continue
    return min(stamps) if stamps else 0.0


def _format_timestamp(value: float) -> str:
    if not value:
        return "Unknown"
    try:
        from datetime import datetime
        return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M")
    except (OSError, OverflowError, ValueError):
        return "Unknown"


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
        self.mode.addItem("Installed AppImage", "installed")
        self.mode.setCurrentIndex(max(0, self.mode.findData(editor.launch_mode)))
        form.addRow("Launch runtime:", self.mode)

        self.extensions: QLineEdit | None = None
        self.installed_path: QLineEdit | None = None
        if can_open_document(editor):
            self.extensions = QLineEdit(", ".join(editor.extensions))
            self.extensions.setPlaceholderText(".txt, .md, .pdf")
            form.addRow("File extensions:", self.extensions)

            overrides = config.get("editor_overrides", {})
            override = overrides.get(editor.editor_id, {}) if isinstance(overrides, dict) else {}
            if not isinstance(override, dict):
                override = {}
            installed_row = QHBoxLayout()
            default_path = editor.installed_command[0] if editor.installed_command else ""
            self.installed_path = QLineEdit(str(override.get("installed_path", "") or default_path))
            browse = QPushButton("Browse…")
            browse.clicked.connect(self._browse_installed)
            installed_row.addWidget(self.installed_path, 1)
            installed_row.addWidget(browse)
            form.addRow("Installed launcher:", installed_row)

        layout.addLayout(form)
        if is_hub(editor):
            info = QLabel(
                "This controls the active Suite Pythoine runtime. On Linux, desktop integration follows that active runtime directly, "
                "so application-menu launches and OS-routed files use the same Suite generation. "
                "Document and special drop routing remain independent of this preference."
            )
        else:
            info = QLabel("Launch-runtime changes affect routing immediately after the component inventory is refreshed.")
        info.setWordWrap(True)
        layout.addWidget(info)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse_installed(self) -> None:
        if self.installed_path is None:
            return
        path, _ = QFileDialog.getOpenFileName(self, app_dialog_title("Choose Installed Launcher"), str(Path.home()))
        if path:
            self.installed_path.setText(path)

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
        if self.extensions is not None:
            extensions = tuple(dict.fromkeys(
                item for item in (normalize_extension(value) for value in self.extensions.text().replace(";", ",").split(",")) if item
            ))
            profile = profile_for_id(self.editor.editor_id)
            canonical = tuple(profile.extensions) if profile is not None else ()
            if canonical and extensions == canonical:
                # Do not freeze a copy of today's catalogue defaults into the
                # user's preferences merely because they changed Launch runtime.
                # This keeps future verified catalogue-only capability changes live.
                override.pop("extensions", None)
            else:
                override["extensions"] = list(extensions)
        if self.installed_path is not None:
            path = self.installed_path.text().strip()
            managed_path = self.editor.managed_installation.get("appimage_path") if self.editor.managed_installation else None
            same_as_managed = False
            if path and isinstance(managed_path, str) and managed_path.strip():
                same_as_managed = Path(path).expanduser().resolve(strict=False) == Path(managed_path).expanduser().resolve(strict=False)
            if path and not same_as_managed:
                override["installed_path"] = path
            else:
                override.pop("installed_path", None)
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
        self.editors = list(editors)
        self.suite_entry = suite_entry
        self.developer_config = developer_config
        self.developer_catalog = developer_catalog
        self.routing_boxes: dict[str, QComboBox] = {}
        self.setWindowTitle(app_dialog_title("Preferences"))
        self.setMinimumSize(820, 640)
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        # 1. General: component storage and Developer Intake only. Launch runtime
        # deliberately lives on the dedicated Runtime tab.
        general = QWidget()
        general_layout = QVBoxLayout(general)
        form = QFormLayout()
        root_row = QHBoxLayout()
        self.editors_root = QLineEdit(str(editors_root))
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_editors_root)
        root_row.addWidget(self.editors_root, 1)
        root_row.addWidget(browse)
        form.addRow("Components folder:", root_row)
        general_layout.addLayout(form)

        open_components = QPushButton("Open Components Folder  (Ctrl+Shift+O)")
        open_components.clicked.connect(self._open_components_folder)
        general_layout.addWidget(open_components, 0, Qt.AlignmentFlag.AlignLeft)

        dashboard_group = QGroupBox("Dashboard")
        dashboard_layout = QVBoxLayout(dashboard_group)
        self.show_dashboard_icons = QCheckBox("Show application icons on Dashboard  (Ctrl+Alt+Shift+I)")
        self.show_dashboard_icons.setChecked(bool(config.get("dashboard_show_icons", True)))
        dashboard_layout.addWidget(self.show_dashboard_icons)
        self.show_drop_bar = QCheckBox("Show Drop Bar  (Ctrl+Alt+Shift+B)")
        self.show_drop_bar.setChecked(bool(config.get("dashboard_drop_bar_visible", True)))
        dashboard_layout.addWidget(self.show_drop_bar)
        dashboard_view_shortcut = QLabel("Toggle List/Grid view: Ctrl+Alt+Shift+D")
        dashboard_layout.addWidget(dashboard_view_shortcut)
        general_layout.addWidget(dashboard_group)

        info = QLabel(
            f"Default Components folder: {runtime.default_editors_root}\n"
            "Portable sources and managed AppImages share this one managed component root.\n"
            f"Normal preferences: {runtime.config_path}"
        )
        info.setTextFormat(Qt.TextFormat.PlainText)
        info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        info.setWordWrap(True)
        general_layout.addWidget(info)

        developer_group = QGroupBox("Developer")
        developer_layout = QVBoxLayout(developer_group)
        self.developer_enabled = QCheckBox("Enable Developer Intake Mode  (F12)")
        self.developer_enabled.setChecked(bool(developer_config.enabled) if developer_config is not None else False)
        self.developer_enabled.setToolTip(
            "When active, manually opened or dropped source ZIPs bypass the normal guided installer and go to Developer Intake. "
            "AppImages, Store Pythoine transactions, component management, and OS file routing are unchanged."
        )
        developer_layout.addWidget(self.developer_enabled)
        self.developer_note = QLabel(
            "Developer Intake keeps its own configuration. Manual source ZIPs are diverted before the production installer; "
            "Store Pythoine hands packages to Suite through the normal full wizard, and document routing remains unchanged."
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
        self.tabs.addTab(general, "General")

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

        reset = QPushButton("Reset Routing Choices")
        reset.clicked.connect(self._reset_routing)
        routing_outer.addWidget(reset, 0, Qt.AlignmentFlag.AlignRight)
        self.tabs.addTab(routing_page, "File Routing")

        # 3. Runtime: launch preference plus the same direct runtime/integration
        # management actions formerly exposed only on Suite Details.
        runtime_page = QWidget()
        runtime_layout = QVBoxLayout(runtime_page)
        runtime_group = QGroupBox("Launch runtime")
        runtime_group_layout = QFormLayout(runtime_group)
        self.suite_runtime = QComboBox()
        self.suite_runtime.addItem("Automatic", "auto")
        self.suite_runtime.addItem("Portable / source", "portable")
        self.suite_runtime.addItem("Installed AppImage", "installed")
        overrides = config.get("editor_overrides", {})
        suite_override = overrides.get("suite-pythoine", {}) if isinstance(overrides, dict) else {}
        current_suite_mode = (suite_entry.launch_mode if suite_entry is not None else str(suite_override.get("launch_mode") or "auto"))
        self.suite_runtime.setCurrentIndex(max(0, self.suite_runtime.findData(current_suite_mode)))
        self.suite_runtime.setToolTip("Controls the runtime used for interactive Suite Pythoine launches. Document routing is decided first.")
        runtime_group_layout.addRow("Launch runtime:", self.suite_runtime)
        runtime_layout.addWidget(runtime_group)

        portable_group = QGroupBox("Portable")
        portable_layout = QHBoxLayout(portable_group)
        self.open_portable_button = QPushButton("Open Portable Folder")
        self.open_portable_button.clicked.connect(self._open_portable_folder)
        portable_layout.addWidget(self.open_portable_button)
        portable_layout.addStretch(1)
        runtime_layout.addWidget(portable_group)

        installed_group = QGroupBox("Installed")
        installed_layout = QHBoxLayout(installed_group)
        self.repair_desktop_button = QPushButton("Repair Desktop Integration")
        self.repair_desktop_button.clicked.connect(self._repair_desktop_integration)
        installed_layout.addWidget(self.repair_desktop_button)
        self.open_installed_button = QPushButton("Open Installed Folder")
        self.open_installed_button.clicked.connect(self._open_installed_folder)
        installed_layout.addWidget(self.open_installed_button)
        installed_layout.addStretch(1)
        runtime_layout.addWidget(installed_group)
        runtime_layout.addStretch(1)
        self.tabs.addTab(runtime_page, "Runtime")

        # 4. Versions: the same per-version launch/activation/removal/folder
        # controls as Suite Details.
        versions_page = QWidget()
        versions_outer = QVBoxLayout(versions_page)
        versions_note = QLabel("Installed Suite Pythoine versions. Runtime copies remain independently launchable; Make Active changes the managed active version.")
        versions_note.setWordWrap(True)
        versions_outer.addWidget(versions_note)
        self.versions_scroll = QScrollArea()
        self.versions_scroll.setWidgetResizable(True)
        self.versions_scroll.setFrameShape(QFrame.Shape.NoFrame)
        versions_outer.addWidget(self.versions_scroll, 1)
        self.tabs.addTab(versions_page, "Versions")

        # 5. Information: exact management/status text used on the restored
        # Details page, from Type through Desktop integration.
        information_page = QWidget()
        information_layout = QVBoxLayout(information_page)
        self.information_label = QLabel()
        self.information_label.setTextFormat(Qt.TextFormat.PlainText)
        self.information_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.information_label.setWordWrap(True)
        information_layout.addWidget(self.information_label)
        information_layout.addStretch(1)
        self.tabs.addTab(information_page, "Information")

        self._refresh_suite_management_views()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

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
            self.information_label.setText("Suite Pythoine component information is unavailable until the component inventory is refreshed.")
            body = QWidget(); body_layout = QVBoxLayout(body); body_layout.addWidget(QLabel("No Suite Pythoine version inventory is currently available.")); body_layout.addStretch(1)
            self.versions_scroll.setWidget(body)
            return

        portable_root = self.controller._portable_root_for(editor)
        appimage = self.controller._primary_managed_appimage(editor) if sys.platform.startswith("linux") else None
        self.open_portable_button.setEnabled(portable_root is not None)
        active_info = next((item for item in editor.versions if item.version == editor.active_version), None)
        self.repair_desktop_button.setEnabled(bool(sys.platform.startswith("linux") and active_info is not None and (active_info.has_portable or active_info.has_appimage)))
        self.open_installed_button.setEnabled(bool(sys.platform.startswith("linux") and appimage is not None))
        self.information_label.setText(self.controller._editor_information_text(editor))

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
        state = QLabel(
            f"Portable: {'Yes' if version_info.has_portable else 'No'}   "
            f"AppImage: {'Yes' if version_info.has_appimage else 'No'}   "
            f"Registry: {'Registered' if version_info.managed_record else ('Unregistered' if version_info.has_appimage else '—')}   "
            f"Desktop: {'Active' if version_info.desktop_integrated else 'No'}"
        )
        state.setTextFormat(Qt.TextFormat.PlainText)
        frame_layout.addWidget(state)
        actions = QHBoxLayout()

        launch_portable = QPushButton("Launch Portable")
        launch_portable.setEnabled(version_info.has_portable)
        launch_portable.clicked.connect(lambda _checked=False, item=version_info: self.controller.launch_editor_version(editor, item, "portable"))
        actions.addWidget(launch_portable)

        launch_appimage = QPushButton("Launch AppImage")
        launch_appimage.setEnabled(version_info.has_appimage)
        launch_appimage.clicked.connect(lambda _checked=False, item=version_info: self.controller.launch_editor_version(editor, item, "appimage"))
        actions.addWidget(launch_appimage)

        make_active = QPushButton("Make Active")
        make_active.setEnabled(version_info.version != editor.active_version)
        make_active.clicked.connect(lambda _checked=False, item=version_info: self._make_version_active(item))
        actions.addWidget(make_active)

        remove_version = QPushButton("Remove Version…")
        remove_version.setEnabled(version_info.version != editor.active_version and not version_info.desktop_integrated)
        remove_version.clicked.connect(lambda _checked=False, item=version_info: self._remove_version(item))
        actions.addWidget(remove_version)

        open_folder = QPushButton("Open Version Folder")
        folder: Path | None = None
        if version_info.portable_root is not None and version_info.portable_root.is_dir():
            folder = version_info.portable_root.parent
        elif version_info.appimage_path is not None:
            folder = version_info.appimage_path.parent.parent
        open_folder.setEnabled(folder is not None)
        if folder is not None:
            open_folder.clicked.connect(lambda _checked=False, target=folder: self.controller.launcher.open_path(target))
        actions.addWidget(open_folder)
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
        path = QFileDialog.getExistingDirectory(self, app_dialog_title("Choose Components Folder"), self.editors_root.text())
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
        portable_root = self.controller._portable_root_for(editor)
        if portable_root is not None:
            self.controller.launcher.open_path(portable_root)

    def _repair_desktop_integration(self) -> None:
        editor = self._current_suite_entry()
        if editor is None:
            return
        self.controller.repair_suite_desktop_integration(editor)
        self._refresh_suite_management_views()

    def _open_installed_folder(self) -> None:
        editor = self._current_suite_entry()
        if editor is None:
            return
        appimage = self.controller._primary_managed_appimage(editor) if sys.platform.startswith("linux") else None
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
        self.config.save()
        if self.developer_config is not None:
            if not self.developer_config.set_enabled(self.developer_enabled.isChecked(), save=True):
                raise OSError(f"Could not save Developer Intake mode to {self.developer_config.path}")


class SuiteWindow(QMainWindow):
    def __init__(self, runtime: RuntimePaths, config: ConfigService, editors_root: Path) -> None:
        super().__init__()
        self.runtime = runtime
        self.config = config
        self.editors_root = editors_root
        self.developer_config = DeveloperIntakeConfig(runtime.developer_intake_config_path)
        self.developer_catalog = DeveloperComponentCatalog(runtime.developer_component_catalog_path)
        self.components: list[EditorEntry] = []
        self.editors: list[EditorEntry] = []
        self.readers: list[EditorEntry] = []
        self.routable: list[EditorEntry] = []
        self.extensions: list[EditorEntry] = []
        self.suite_entry: EditorEntry | None = None
        self.suite_page_index: int | None = None
        self.installed_applications_page_index: int | None = None
        self.editor_pages: dict[str, int] = {}
        self._closing = False
        self._drop_letter_key = ""
        self._drop_override_armed = ""
        self._navigation_history: list[str] = []
        self._navigation_current = "dashboard"
        self._navigation_back_in_progress = False
        self.about_dialog: QDialog | None = None
        self.shortcuts_dialog: ShortcutsDialog | None = None

        self.launcher = RuntimeLauncher(runtime, self)
        self.launcher.launch_error.connect(lambda message: QMessageBox.warning(self, app_dialog_title("Launch Failed"), message))
        self.launcher.status_message.connect(self._status)
        self.watcher = EditorDirectoryWatcher(parent=self)
        self.watcher.refresh_requested.connect(lambda: self.refresh_editors(automatic=True))

        self.setWindowTitle(app_dialog_title("Dashboard"))
        if APP_ICON_PATH.is_file():
            self.setWindowIcon(QIcon(str(APP_ICON_PATH)))
        self.setAcceptDrops(True)
        self._make_menu()
        self._drop_shortcuts = []
        for sequence, target in (("Ctrl+Shift+B", "beespector"), ("Ctrl+Shift+Y", "youlindo"), ("Ctrl+Shift+C", "crawlindo")):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(lambda value=target: self._arm_drop_override(value))
            self._drop_shortcuts.append(shortcut)

        central = QWidget()
        self.setCentralWidget(central)
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(self.splitter)
        self.sidebar = self._build_sidebar()
        self.splitter.addWidget(self.sidebar)
        self.splitter.setCollapsible(0, True)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.dev_status_badge = QLabel("DEV MODE")
        self.dev_status_badge.setStyleSheet("QLabel { font-weight: bold; padding: 2px 7px; border: 1px solid palette(mid); border-radius: 4px; }")
        self.dev_status_badge.setToolTip("Developer Intake Mode is active — manually opened/dropped source ZIPs bypass the normal guided installer.")
        self.statusBar().addPermanentWidget(self.dev_status_badge)
        self.stack = QStackedWidget()
        self.splitter.addWidget(self.stack)

        self.dashboard = EditorDashboard(APP_NAME, self.editors_root, APP_ICON_PATH)
        self.dashboard.launch_requested.connect(self.launch_editor)
        self.dashboard.new_requested.connect(self.create_file_for_editor)
        self.dashboard.open_requested.connect(self.open_with_editor_prompt)
        self.dashboard.details_requested.connect(self.show_editor_details)
        self.dashboard.refresh_requested.connect(self.refresh_editors)
        self.dashboard.launch_prompt_requested.connect(self.launch_prompt)
        self.dashboard.new_file_requested.connect(self.new_file_prompt)
        self.dashboard.open_file_requested.connect(self.open_file_prompt)
        self.dashboard.install_editor_requested.connect(self.install_editor_prompt)
        self.dashboard.installed_applications_requested.connect(self.show_installed_applications)
        self.dashboard.suite_details_requested.connect(self.show_suite_details)
        self.dashboard.sort_changed.connect(lambda mode: self.config.set("dashboard_sort", mode))
        self.dashboard.search_changed.connect(lambda text: self.config.set("dashboard_search", text))
        self.dashboard.drop_payload_requested.connect(self._handle_drop_payloads)
        self.dashboard.url_choice_requested.connect(lambda component_id, url: self._launch_component_argument(component_id, url, next((e.name for e in self.components if e.editor_id == component_id), component_id)))
        self.stack.addWidget(self.dashboard)
        QApplication.instance().installEventFilter(self)

        self._restore_window_state()
        self._sync_developer_mode_ui()
        self.refresh_editors()
        # exp9-r2 migrates the old "retained AppImage as bootstrap" state the
        # first time the new Hub starts. Only repair when the current desktop
        # entry does not already point at the active version/runtime directly.
        if sys.platform.startswith("linux"):
            QTimer.singleShot(0, self._ensure_suite_direct_desktop_integration)
        bootstrap_warning = os.environ.pop("SUITE_PYTHOINE_BOOTSTRAP_WARNING", "").strip()
        if bootstrap_warning:
            QTimer.singleShot(0, lambda message=bootstrap_warning: QMessageBox.warning(
                self, app_dialog_title("Launch Runtime Unavailable"), message
            ))

    def _make_menu(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        self.launch_action = QAction("Launch…", self)
        self.launch_action.setShortcut("F4")
        self.launch_action.triggered.connect(self.launch_prompt)
        file_menu.addAction(self.launch_action)
        self.new_action = QAction("New File…", self)
        self.new_action.setShortcut("Ctrl+N")
        self.new_action.triggered.connect(self.new_file_prompt)
        file_menu.addAction(self.new_action)
        self.open_action = QAction("Open File…", self)
        self.open_action.setShortcut("Ctrl+O")
        self.open_action.triggered.connect(self.open_file_prompt)
        file_menu.addAction(self.open_action)
        file_menu.addSeparator()
        self.exit_action = QAction("Exit", self)
        self.exit_action.setShortcut("Ctrl+Q")
        self.exit_action.triggered.connect(self.close)
        file_menu.addAction(self.exit_action)

        view = self.menuBar().addMenu("View")
        self.refresh_action = QAction("Refresh Components", self)
        self.refresh_action.setShortcut("F5")
        self.refresh_action.triggered.connect(self.refresh_editors)
        view.addAction(self.refresh_action)
        view.addSeparator()

        self.dashboard_action = QAction("Dashboard", self)
        self.dashboard_action.setShortcut("Ctrl+W")
        self.dashboard_action.triggered.connect(self.show_dashboard)
        view.addAction(self.dashboard_action)

        dashboard_settings = view.addMenu("Dashboard Settings")
        self.list_action = QAction("List View", self, checkable=True)
        self.grid_action = QAction("Grid View", self, checkable=True)
        group = QActionGroup(self)
        group.setExclusive(True)
        group.addAction(self.list_action)
        group.addAction(self.grid_action)
        self.list_action.triggered.connect(lambda: self._set_dashboard_view("list"))
        self.grid_action.triggered.connect(lambda: self._set_dashboard_view("grid"))
        dashboard_settings.addAction(self.list_action)
        dashboard_settings.addAction(self.grid_action)
        dashboard_settings.addSeparator()

        self.icons_action = QAction("Show Dashboard Icons", self, checkable=True)
        self.icons_action.setShortcut("Ctrl+Alt+Shift+I")
        self.icons_action.triggered.connect(self._toggle_dashboard_icons)
        dashboard_settings.addAction(self.icons_action)
        self.drop_bar_action = QAction("Show Drop Bar", self, checkable=True)
        self.drop_bar_action.setShortcut("Ctrl+Alt+Shift+B")
        self.drop_bar_action.triggered.connect(self._toggle_drop_bar)
        dashboard_settings.addAction(self.drop_bar_action)

        # Keyboard-only toggle: intentionally not exposed as a menu entry.
        self.toggle_view_shortcut_action = QAction("Toggle List/Grid View", self)
        self.toggle_view_shortcut_action.setShortcut("Ctrl+Alt+Shift+D")
        self.toggle_view_shortcut_action.triggered.connect(self._toggle_dashboard_view)
        self.addAction(self.toggle_view_shortcut_action)

        view.addSeparator()
        self.sidebar_action = QAction("Show Sidebar", self, checkable=True)
        self.sidebar_action.setShortcut("F9")
        self.sidebar_action.triggered.connect(self._toggle_sidebar)
        view.addAction(self.sidebar_action)
        self.fullscreen_action = QAction("Full Screen", self, checkable=True)
        self.fullscreen_action.setShortcut("F11")
        self.fullscreen_action.triggered.connect(self._toggle_fullscreen)
        view.addAction(self.fullscreen_action)

        self.search_action = QAction("Focus Dashboard Search", self)
        self.search_action.setShortcut("Ctrl+F")
        self.search_action.triggered.connect(self._focus_dashboard_search)
        self.addAction(self.search_action)

        tools = self.menuBar().addMenu("Tools")
        self.open_components_folder_action = QAction("Open Components Folder", self)
        self.open_components_folder_action.setShortcut("Ctrl+Shift+O")
        self.open_components_folder_action.triggered.connect(lambda: self.launcher.open_path(self.editors_root))
        tools.addAction(self.open_components_folder_action)
        self.install_action = QAction("Install Component…", self)
        self.install_action.setShortcut("Ctrl+Shift+N")
        self.install_action.triggered.connect(self.install_editor_prompt)
        tools.addAction(self.install_action)
        tools.addSeparator()
        self.store_action = QAction("Get More Components", self)
        self.store_action.triggered.connect(self.show_store)
        tools.addAction(self.store_action)
        tools.addSeparator()
        self.developer_action = QAction("Developer Intake Mode", self, checkable=True)
        self.developer_action.setShortcut("F12")
        self.developer_action.setToolTip("Toggle Developer Intake Mode. The state persists across restarts.")
        self.developer_action.triggered.connect(self._toggle_developer_mode)
        tools.addAction(self.developer_action)
        self.preferences_action = QAction("Preferences…", self)
        self.preferences_action.setShortcut("Ctrl+/")
        self.preferences_action.triggered.connect(self.general_preferences)
        tools.addAction(self.preferences_action)

        help_menu = self.menuBar().addMenu("Help")
        self.documentation_action = QAction("Documentation", self)
        self.documentation_action.setShortcut("F1")
        self.documentation_action.triggered.connect(self.open_documentation)
        help_menu.addAction(self.documentation_action)
        self.shortcuts_action = QAction("Keyboard Shortcuts", self)
        self.shortcuts_action.setShortcut("Ctrl+Shift+/")
        self.shortcuts_action.triggered.connect(self.show_shortcuts)
        help_menu.addAction(self.shortcuts_action)
        help_menu.addSeparator()
        self.github_action = QAction("GitHub Repository", self)
        self.github_action.triggered.connect(self.open_github_repository)
        help_menu.addAction(self.github_action)
        self.issue_action = QAction("Report an Issue", self)
        self.issue_action.triggered.connect(self.report_an_issue)
        help_menu.addAction(self.issue_action)
        help_menu.addSeparator()
        self.about_action = QAction(f"About {APP_NAME}", self)
        self.about_action.triggered.connect(self.about)
        self.about_action.setMenuRole(QAction.MenuRole.AboutRole)
        help_menu.addAction(self.about_action)


    def _build_sidebar(self) -> QFrame:
        frame = QFrame()
        # Keep the established 250 px sidebar as a hard upper bound. Long/new
        # component names must scroll/elide inside the sidebar rather than making
        # it wider. The splitter remains collapsible, so the user can still drag
        # the handle all the way left to close the sidebar visually.
        frame.setMinimumWidth(0)
        frame.setMaximumWidth(250)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 18, 12, 16)
        title = QLabel("Components")
        font = title.font()
        font.setBold(True)
        font.setPointSize(max(font.pointSize() + 2, 11))
        title.setFont(font)
        layout.addWidget(title)
        tip = QLabel("Drop a supported file to route it, or drop a recognized component ZIP/AppImage to install it.")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        dashboard = QPushButton("Dashboard")
        dashboard.clicked.connect(self.show_dashboard)
        layout.addWidget(dashboard)
        refresh_btn = QPushButton("Refresh Components")
        refresh_btn.clicked.connect(self.refresh_editors)
        layout.addWidget(refresh_btn)

        self.editor_list = QListWidget()
        self.editor_list.setIconSize(QSize(26, 26))
        self.editor_list.setSpacing(1)
        self.editor_list.itemActivated.connect(self._sidebar_activated)
        self.editor_list.itemClicked.connect(self._sidebar_activated)
        self.editor_list.currentItemChanged.connect(lambda current, _previous: self._sidebar_activated(current) if current is not None else None)
        layout.addWidget(self.editor_list, 1)

        store_btn = QPushButton("Get More...")
        store_btn.clicked.connect(self.show_store)
        layout.addWidget(store_btn)

        self.dev_sidebar_badge = QLabel("DEV MODE ACTIVE")
        self.dev_sidebar_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.dev_sidebar_badge.setStyleSheet("QLabel { font-weight: bold; padding: 4px; border: 1px solid palette(mid); border-radius: 4px; }")
        self.dev_sidebar_badge.setToolTip("Developer Intake Mode is active — manual source ZIPs are diverted from the normal installer.")
        layout.addWidget(self.dev_sidebar_badge)

        self.status = QLabel("Ready.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        return frame

    def _legacy_portable_root(self) -> Path | None:
        raw = self.config.get("legacy_my_editors_dir")
        if isinstance(raw, str) and raw.strip():
            candidate = Path(raw).expanduser().resolve(strict=False)
        else:
            candidate = self.runtime.legacy_default_my_editors
        if candidate == self.editors_root:
            return None
        return candidate

    def _legacy_installed_root(self) -> Path | None:
        raw = self.config.get("legacy_installed_editors_dir")
        if isinstance(raw, str) and raw.strip():
            candidate = Path(raw).expanduser().resolve(strict=False)
        else:
            candidate = self.runtime.legacy_default_installed_editors
        if candidate == self.editors_root:
            return None
        return candidate

    def _merge_legacy_entries(self, primary: list[EditorEntry]) -> list[EditorEntry]:
        legacy_root = self._legacy_portable_root()
        if legacy_root is None or not legacy_root.is_dir():
            return primary
        legacy = discover_editors(
            legacy_root,
            self.editors_root,
            self.config.as_dict(),
            python_executable=self.launcher.python_executable(),
        )
        by_id = {entry.editor_id: entry for entry in primary}
        for entry in legacy:
            current = by_id.get(entry.editor_id)
            if current is None or (current.portable_command is None and entry.portable_command is not None):
                by_id[entry.editor_id] = entry
            elif current.portable_command and entry.portable_command:
                # Prefer a newer-looking version; mtime is a deterministic tie-break.
                current_key = (current.source_version or "", current.modified)
                legacy_key = (entry.source_version or "", entry.modified)
                if legacy_key > current_key:
                    by_id[entry.editor_id] = entry
        return sorted(by_id.values(), key=lambda entry: (entry.name.casefold(), entry.editor_id.casefold()))

    def maybe_offer_storage_migration(self) -> None:
        # 0.3.0 canonical-root transition is independent from older migration
        # dismissal state. A user who dismissed an old flat-source migration
        # must still be offered the new canonical-root transition once.

        # 0.3.0 canonical-root transition: the former default
        # ~/Suite Pythoine Editors is a one-time migration source only. It is
        # never merged into normal discovery after this point.
        legacy_unified = self._legacy_installed_root()
        if (
            not bool(self.config.get("canonical_root_transition_dismissed", False))
            and legacy_unified is not None
            and legacy_unified.is_dir()
            and legacy_unified != self.editors_root
        ):
            reply = QMessageBox.question(
                self,
                app_dialog_title("Move Existing Components"),
                "Suite Pythoine 0.3.0 uses a new canonical managed folder:\n\n"
                f"{self.editors_root}\n\n"
                f"Existing managed components were found in:\n{legacy_unified}\n\n"
                "Move those version folders into the new component root now? Existing destination versions are never overwritten.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes:
                try:
                    moved, skipped = transition_legacy_default_root(legacy_unified, self.editors_root, self.config.as_dict())
                    self.config.save()
                    self._refresh_desktop_database()
                    self.refresh_editors(automatic=True)
                    message = f"Moved {len(moved)} version folder{'s' if len(moved) != 1 else ''} into {self.editors_root}."
                    if skipped:
                        message += "\n\nNot moved automatically:\n" + "\n".join(f"• {item}" for item in skipped)
                    QMessageBox.information(self, app_dialog_title("Component Migration"), message)
                except Exception as exc:
                    QMessageBox.critical(self, app_dialog_title("Component Migration Failed"), str(exc))
                return
            self.config.set("canonical_root_transition_dismissed", True, save=True)
            return

        if bool(self.config.get("storage_migration_dismissed", False)):
            return

        # Retain the older flat-source migration wizard only as an explicit
        # one-time recovery path; it is not part of routine component discovery.
        legacy_root = self._legacy_portable_root()
        plan = build_migration_plan(
            self.editors_root,
            legacy_root,
            self.config.as_dict(),
            python_executable=self.launcher.python_executable(),
            legacy_installed_root=None,
        )
        if not plan.has_work:
            return
        reply = QMessageBox.question(
            self,
            app_dialog_title("Organise Existing Components"),
            "Older portable component files were found outside Suite Pythoine's canonical managed root.\n\n"
            f"They can be organised under:\n{self.editors_root}\n\n"
            "Review and perform the migration now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            self.config.set("storage_migration_dismissed", True, save=True)
            return
        self._close_about_dialog()
        wizard = StorageMigrationWizard(self, plan, self.config, self._after_storage_migration)
        wizard.exec()
        if wizard.progress.succeeded:
            self._status("Existing components were organised into the managed root.")

    def _after_storage_migration(self) -> None:
        self.config.save()
        self._refresh_desktop_database()
        self.refresh_editors(automatic=True)

    def _status(self, text: str) -> None:
        self.status.setText(f"Status: {text}")
        self.statusBar().showMessage(text, 8000)

    def _sync_developer_mode_ui(self) -> None:
        active = self.developer_config.enabled
        if hasattr(self, "developer_action"):
            self.developer_action.blockSignals(True)
            self.developer_action.setChecked(active)
            self.developer_action.blockSignals(False)
        if hasattr(self, "dev_sidebar_badge"):
            self.dev_sidebar_badge.setVisible(active)
        if hasattr(self, "dev_status_badge"):
            self.dev_status_badge.setVisible(active)
        self.setWindowTitle(app_dialog_title("Dashboard") + (" — Developer Mode" if active else ""))

    def _installed_dir(self) -> Path:
        # Compatibility name: managed AppImages now live below the same Editors root.
        return self.editors_root

    @staticmethod
    def _entry_key(editor: EditorEntry) -> str:
        return str(editor.root)

    def refresh_editors(self, automatic: bool = False) -> None:
        selected_root = None
        current = self.stack.currentWidget()
        if current is not None:
            selected_root = current.property("editor_root")

        components = discover_editors(
            self.editors_root,
            self._installed_dir(),
            self.config.as_dict(),
            python_executable=self.launcher.python_executable(),
        )
        if self._migrate_r4_managed_records(components):
            self.config.save()
            components = discover_editors(
                self.editors_root,
                self._installed_dir(),
                self.config.as_dict(),
                python_executable=self.launcher.python_executable(),
            )

        self.components = components
        self.suite_entry = next((entry for entry in components if is_hub(entry)), None)
        self.editors = document_editors(components)
        self.readers = document_readers(components)
        self.routable = routable_components(components)
        self.extensions = [entry for entry in components if is_extension(entry)]

        # The hot routing path consumes this compact local inventory instead of
        # scanning the managed tree on every file double-click. Full discovery
        # above remains authoritative and refreshes the cache whenever Suite is
        # already open.
        routing_index = build_index_payload(components, self.editors_root)
        if self.config.get("routing_index") != routing_index:
            self.config.set("routing_index", routing_index)
            self.config.save()

        self.dashboard.editors_root = self.editors_root
        self.dashboard.set_components([*self.editors, *self.readers, *self.extensions])
        self._rebuild_editor_pages(selected_root)
        self.watcher.watch([self.editors_root])
        prefix = "Updated" if automatic else "Found"
        self._status(
            f"{prefix} {len(self.editors)} editor{'s' if len(self.editors) != 1 else ''}, "
            f"{len(self.readers)} reader{'s' if len(self.readers) != 1 else ''}, and "
            f"{len(self.extensions)} extension{'s' if len(self.extensions) != 1 else ''} in the Components folder."
        )

    def _rebuild_editor_pages(self, selected_root: object = None) -> None:
        for index in range(self.stack.count() - 1, -1, -1):
            widget = self.stack.widget(index)
            if bool(widget.property("suite_editor_page")):
                self.stack.removeWidget(widget)
                widget.deleteLater()
        self.editor_list.clear()
        self.editor_pages.clear()

        def add_sidebar_group(label: str, entries: list[EditorEntry]) -> None:
            if not entries:
                return
            heading = QListWidgetItem(label)
            heading.setFlags(Qt.ItemFlag.NoItemFlags)
            heading_font = heading.font()
            heading_font.setBold(True)
            heading.setFont(heading_font)
            heading.setSizeHint(QSize(0, 30))
            self.editor_list.addItem(heading)
            for component in entries:
                sidebar_name = component.name if len(component.versions) <= 1 else f"{component.name}  ({len(component.versions)} versions)"
                item = QListWidgetItem(sidebar_name)
                item.setToolTip(
                    f"Active: {component.active_version or 'Unknown'}"
                    + (f" • Desktop: {component.desktop_version}" if component.desktop_version else "")
                )
                item.setData(Qt.ItemDataRole.UserRole, self._entry_key(component))
                if component.icon and component.icon.is_file():
                    item.setIcon(QIcon(str(component.icon)))
                item.setSizeHint(QSize(0, 38))
                self.editor_list.addItem(item)

                page = self._editor_page(component)
                key = self._entry_key(component)
                page.setProperty("editor_root", key)
                page.setProperty("suite_editor_page", True)
                self.editor_pages[key] = self.stack.addWidget(page)

        add_sidebar_group("EDITORS", self.editors)
        add_sidebar_group("READERS", self.readers)
        add_sidebar_group("EXTENSIONS", self.extensions)

        self.suite_page_index = None
        self.installed_applications_page_index = None
        suite_page = self._suite_details_page()
        suite_page.setProperty("editor_root", "__suite__")
        suite_page.setProperty("suite_editor_page", True)
        self.suite_page_index = self.stack.addWidget(suite_page)

        installed_applications_page = self._installed_applications_page()
        installed_applications_page.setProperty("editor_root", "__installed_applications__")
        installed_applications_page.setProperty("suite_editor_page", True)
        self.installed_applications_page_index = self.stack.addWidget(installed_applications_page)

        if selected_root == "__suite__" and self.suite_page_index is not None:
            self.stack.setCurrentIndex(self.suite_page_index)
        elif selected_root == "__installed_applications__" and self.installed_applications_page_index is not None:
            self.stack.setCurrentIndex(self.installed_applications_page_index)
        elif selected_root in self.editor_pages:
            self.stack.setCurrentIndex(self.editor_pages[str(selected_root)])
        elif selected_root:
            self.stack.setCurrentIndex(0)
        else:
            last_id = self.config.get("last_selected_editor")
            editor = next((entry for entry in [*self.editors, *self.readers, *self.extensions] if entry.editor_id == last_id), None)
            if editor:
                self.show_editor_details(editor)
            else:
                self.stack.setCurrentIndex(0)

    def _editor_override(self, editor: EditorEntry) -> dict:
        overrides = self.config.get("editor_overrides", {})
        if not isinstance(overrides, dict):
            overrides = {}
            self.config.set("editor_overrides", overrides)
        override = overrides.setdefault(editor.editor_id, {})
        if not isinstance(override, dict):
            override = {}
            overrides[editor.editor_id] = override
        return override

    def _managed_record(self, editor: EditorEntry, version: str | None = None) -> dict:
        return get_managed_installation(self.config.as_dict(), editor.editor_id, version)

    def _managed_group(self, editor: EditorEntry) -> dict:
        return get_managed_group(self.config.as_dict(), editor.editor_id)

    def _managed_versions(self, editor: EditorEntry) -> dict[str, dict]:
        return get_managed_versions(self.config.as_dict(), editor.editor_id)

    def _migrate_r4_managed_records(self, editors: list[EditorEntry]) -> bool:
        """Migrate r4 sidecars into the r5 explicit managed-install registry.

        Migration is intentionally conservative: an AppImage is adopted only
        when its sidecar already identifies it as Suite Pythoine-managed.  A
        filename resemblance by itself is never sufficient.
        """
        changed = False
        installed_dir = self._installed_dir()
        for editor in editors:
            managed = self._managed_record(editor)
            if managed:
                # r7 enriches older managed records while the portable source is
                # still available.  This preserves custom-editor routing and
                # presentation if the user later removes that portable folder.
                enriched = dict(managed)
                if editor.extensions and not enriched.get("extensions"):
                    enriched["extensions"] = list(editor.extensions)
                if editor.description and not enriched.get("description"):
                    enriched["description"] = editor.description
                if editor.source_version and not enriched.get("source_version"):
                    enriched["source_version"] = editor.source_version
                if enriched != managed:
                    set_managed_installation(self.config.as_dict(), enriched)
                    changed = True
                continue
            override = self._editor_override(editor)
            raw = override.get("installed_path")
            if not isinstance(raw, str) or not raw.strip():
                continue
            appimage = Path(raw).expanduser().resolve(strict=False)
            if not appimage.is_file() or appimage.suffix.casefold() != ".appimage" or not is_within(appimage, installed_dir):
                continue
            metadata = read_appimage_metadata(appimage)
            if metadata.get("managed_by") != "Suite Pythoine" or metadata.get("editor_id") != editor.editor_id:
                continue
            icons = installed_icon_candidates(installed_dir, editor.editor_id)
            icon = icons[0] if icons else None
            desktop = desktop_entry_path(editor.editor_id)
            version = metadata.get("version") if isinstance(metadata.get("version"), str) else editor.installed_version
            record = {
                "schema": 1,
                "editor_id": editor.editor_id,
                "application_id": str(metadata.get("application_id") or editor.editor_id),
                "name": editor.name,
                "version": version,
                "appimage_path": str(appimage),
                "appimage_sha256": str(metadata.get("appimage_sha256") or metadata.get("sha256") or sha256_file(appimage)),
                "desktop_file_path": str(desktop),
                "desktop_id": str(metadata.get("desktop_id") or desktop_id_for(editor.editor_id)),
                "icon_path": str(icon) if icon else None,
                "publisher_id": editor.publisher_id,
            }
            for key in ("source_artifact", "build_script"):
                value = metadata.get(key)
                if isinstance(value, str) and value.strip():
                    record[key] = value.strip()
            if editor.source_version:
                record["source_version"] = editor.source_version
            record["extensions"] = list(editor.extensions)
            if editor.description:
                record["description"] = editor.description
            registered = set_managed_installation(self.config.as_dict(), record, set_active=True, desktop_integrated=True)
            write_appimage_metadata(
                appimage,
                editor_id=editor.editor_id,
                application_id=registered["application_id"],
                publisher_id=editor.publisher_id,
                name=editor.name,
                version=registered.get("version"),
                desktop_file=Path(registered["desktop_file_path"]),
                desktop_id=registered["desktop_id"],
                icon=Path(registered["icon_path"]) if registered.get("icon_path") else None,
            )
            # r5 no longer duplicates managed identity in editor_overrides.
            for key in ("installed_path", "installed_version", "installed_source_version", "installed_sha256", "built_artifact", "build_script"):
                override.pop(key, None)
            changed = True
        return changed

    def _register_managed_installation(
        self,
        editor: EditorEntry,
        appimage: Path,
        desktop: Path | None,
        icon: Path | None,
        *,
        version: str | None,
        source_artifact: Path | None = None,
        build_script: Path | None = None,
        set_active: bool = True,
        desktop_integrated: bool | None = None,
    ) -> tuple[dict, Path]:
        appimage = appimage.expanduser().resolve(strict=False)
        desktop = desktop.expanduser().resolve(strict=False) if desktop is not None else None
        icon = icon.expanduser().resolve(strict=False) if icon is not None else None
        record = {
            "schema": 1,
            "editor_id": editor.editor_id,
            "application_id": editor.editor_id,
            "name": editor.name,
            "version": version,
            "appimage_path": str(appimage),
            "appimage_sha256": sha256_file(appimage),
            "desktop_file_path": str(desktop) if desktop is not None else None,
            "desktop_id": desktop_id_for(editor.editor_id),
            "icon_path": str(icon) if icon else None,
            "source_version": editor.source_version,
            "extensions": list(editor.extensions),
            "description": editor.description,
            "publisher_id": editor.publisher_id,
        }
        if source_artifact is not None:
            record["source_artifact"] = source_artifact.name
        if build_script is not None:
            try:
                record["build_script"] = str(build_script.relative_to(editor.root))
            except ValueError:
                record["build_script"] = str(build_script)
        registered = set_managed_installation(
            self.config.as_dict(),
            record,
            set_active=set_active,
            desktop_integrated=bool(desktop) if desktop_integrated is None else desktop_integrated,
        )
        is_desktop_integrated = bool(desktop) if desktop_integrated is None else bool(desktop_integrated)
        metadata = write_appimage_metadata(
            appimage,
            editor_id=editor.editor_id,
            application_id=registered["application_id"],
            publisher_id=editor.publisher_id,
            name=editor.name,
            version=registered.get("version"),
            desktop_file=desktop,
            desktop_id=registered["desktop_id"],
            desktop_integrated=is_desktop_integrated,
            icon=icon,
            source_artifact=source_artifact,
            build_script=build_script,
        )
        if is_desktop_integrated:
            active_version = str(registered.get("version") or "")
            for other_version, other_record in get_managed_versions(self.config.as_dict(), editor.editor_id).items():
                if other_version == active_version:
                    continue
                raw_other = other_record.get("appimage_path")
                if not isinstance(raw_other, str) or not raw_other.strip():
                    continue
                other_appimage = Path(raw_other).expanduser().resolve(strict=False)
                if not other_appimage.is_file():
                    continue
                write_appimage_metadata(
                    other_appimage,
                    editor_id=editor.editor_id,
                    application_id=str(other_record.get("application_id") or editor.editor_id),
                    publisher_id=editor.publisher_id,
                    name=editor.name,
                    version=other_version,
                    desktop_file=None,
                    desktop_id=desktop_id_for(editor.editor_id),
                    desktop_integrated=False,
                    icon=record_paths(other_record).get("icon"),
                )
        return registered, metadata

    def _explicit_installed_appimage(self, editor: EditorEntry) -> Path | None:
        managed = self._managed_record(editor)
        paths = record_paths(managed) if managed else {}
        managed_path = paths.get("appimage") if paths else None
        if managed_path is not None and managed_path.is_file():
            return managed_path
        override = self._editor_override(editor)
        raw = override.get("installed_path")
        if isinstance(raw, str) and raw.strip():
            path = Path(raw).expanduser().resolve(strict=False)
            if path.suffix.casefold() == ".appimage":
                return path
        if editor.installed_command:
            path = Path(editor.installed_command[0]).expanduser().resolve(strict=False)
            if path.suffix.casefold() == ".appimage":
                return path
        return None

    def _managed_appimages_for(self, editor: EditorEntry) -> list[Path]:
        return managed_appimages(
            self._installed_dir(),
            editor.editor_id,
            editor.name,
            explicit_path=self._explicit_installed_appimage(editor),
        )

    def _primary_managed_appimage(self, editor: EditorEntry) -> Path | None:
        managed = self._managed_record(editor)
        if managed:
            appimage = record_paths(managed).get("appimage")
            if appimage is not None:
                return appimage
        candidates = self._managed_appimages_for(editor)
        return candidates[0] if candidates else None

    def _portable_root_for(self, editor: EditorEntry) -> Path | None:
        root = editor.root.expanduser().resolve(strict=False)
        try:
            managed_root = self.editors_root.expanduser().resolve(strict=False)
            if not root.is_dir() or root.is_symlink() or not is_within(root, managed_root):
                return None
            rel = root.relative_to(managed_root)
            if (len(rel.parts) == 3 and rel.parts[-1].casefold() == "portable") or len(rel.parts) == 1:
                return root
        except (OSError, ValueError):
            return None
        return None

    def _suite_runtime_for_version(self, editor: EditorEntry, version: EditorVersionInfo) -> tuple[str, tuple[str, ...]]:
        """Resolve the runtime that should own Suite Pythoine desktop integration."""
        mode = str(editor.launch_mode or "auto")
        if mode == "portable":
            if not version.has_portable or not version.portable_command:
                raise InstallError(f"Suite Pythoine {version.version} has no Portable runtime, but Launch runtime is set to Portable.")
            return "Portable", version.portable_command
        if mode == "installed":
            if not version.has_appimage or not version.installed_command:
                raise InstallError(f"Suite Pythoine {version.version} has no AppImage runtime, but Launch runtime is set to Installed AppImage.")
            return "AppImage", version.installed_command
        # Automatic keeps the established preference for a verified AppImage,
        # otherwise the available Portable runtime owns the desktop entry.
        if version.has_appimage and version.installed_command:
            return "AppImage", version.installed_command
        if version.has_portable and version.portable_command:
            return "Portable", version.portable_command
        raise InstallError(f"Suite Pythoine {version.version} has no launchable runtime.")

    def _desktop_runtime_owns_version(self, editor: EditorEntry, version: EditorVersionInfo, runtime: str) -> bool:
        if version.version != editor.desktop_version:
            return False
        if not is_hub(editor):
            return runtime == "AppImage" and bool(version.desktop_integrated)
        actual = desktop_entry_runtime(desktop_entry_path(editor.editor_id))
        return actual == runtime.casefold()

    def _integration_status_text(self, editor: EditorEntry, appimage: Path | None) -> str:
        if is_hub(editor) and editor.active_version:
            version = self._version_info(editor, editor.active_version)
            if version is not None:
                try:
                    runtime, command = self._suite_runtime_for_version(editor, version)
                except InstallError:
                    return "Active runtime unavailable — choose/repair a valid Suite runtime"
                desktop = desktop_entry_path(editor.editor_id)
                if runtime == "Portable":
                    status = portable_desktop_entry_status(
                        editor.editor_id,
                        command,
                        desktop_path=desktop,
                        desktop_id=desktop_id_for(editor.editor_id),
                        icon_path=version.icon or editor.icon,
                    )
                else:
                    target = version.appimage_path
                    status = desktop_entry_status(
                        editor.editor_id,
                        target,
                        desktop_path=desktop,
                        desktop_id=desktop_id_for(editor.editor_id),
                        icon_path=version.icon or editor.icon,
                    )
                text = {
                    "ready": f"Ready — active {runtime} runtime owns the desktop entry",
                    "missing": f"Desktop entry missing — Repair will attach the active {runtime} runtime",
                    "stale": f"Desktop entry points to a different runtime/version — Repair available",
                    "no-portable": "Active Portable runtime unavailable",
                    "no-appimage": "Active AppImage runtime unavailable",
                }.get(status, status)
                return text

        managed = self._managed_record(editor)
        paths = record_paths(managed) if managed else {}
        status = desktop_entry_status(
            editor.editor_id,
            appimage,
            desktop_path=paths.get("desktop") if paths else None,
            desktop_id=managed.get("desktop_id") if managed else None,
            icon_path=paths.get("icon") if paths else None,
        )
        return {
            "ready": "Ready",
            "missing": "Desktop entry missing — Repair available",
            "stale": "Desktop entry points to the wrong AppImage — Repair available",
            "no-appimage": "No managed AppImage installed",
        }.get(status, status) + (" — legacy/unregistered; Repair will adopt it" if appimage is not None and not managed else "")

    def _version_safety_text(self, editor: EditorEntry) -> str:
        if editor.version_status == "match":
            return "Portable and installed versions match"
        if editor.version_status == "mismatch":
            return "VERSION MISMATCH — Automatic mode uses portable"
        if editor.version_status == "unverified":
            return "Installed version unverified — Automatic mode uses portable"
        if editor.source_version or editor.installed_version:
            return "Only one version is currently available"
        return "Version metadata unavailable"

    def _warn_explicit_installed_mismatch(self, editor: EditorEntry) -> None:
        if editor.launch_mode != "installed" or editor.version_status not in {"mismatch", "unverified"}:
            return
        installed = editor.installed_version or "unknown"
        portable = editor.source_version or "unknown"
        reply = QMessageBox.warning(
            self,
            app_dialog_title("Installed Version Mismatch"),
            f"{editor.name} is explicitly configured to launch the installed copy, but that copy cannot be safely matched to the portable source you just loaded.\n\n"
            f"Portable source: {portable}\nInstalled AppImage: {installed}\n\n"
            "Switch the preferred launch runtime to Portable until you rebuild/install a matching AppImage?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply == QMessageBox.StandardButton.Yes:
            override = self._editor_override(editor)
            override["launch_mode"] = "portable"
            self.config.save()
            self.refresh_editors()

    def _refresh_desktop_database(self, applications_dir: Path | None = None) -> None:
        if not sys.platform.startswith("linux"):
            return
        applications = applications_dir or desktop_applications_dir()
        command = self.launcher.command_for_parts(("update-desktop-database", str(applications)))
        if command is not None:
            self.launcher.start_detached(command)

    def repair_appimage_integration(self, editor: EditorEntry) -> None:
        if not sys.platform.startswith("linux"):
            QMessageBox.information(self, app_dialog_title("Not Applicable"), "AppImage desktop integration is a Linux feature.")
            return
        appimage = self._primary_managed_appimage(editor)
        if appimage is None or not appimage.is_file():
            QMessageBox.warning(
                self,
                app_dialog_title("AppImage Not Found"),
                f"No AppImage for {editor.name} was found in the configured Components folder:\n\n{self._installed_dir()}",
            )
            return

        managed = self._managed_record(editor)
        existing_paths = record_paths(managed) if managed else {}
        desktop = existing_paths.get("desktop") if existing_paths else None
        icon = existing_paths.get("icon") if existing_paths else None

        # A legacy r3/r4 install can be explicitly adopted by Repair. Once
        # adopted, future repair/uninstall operations use only the registered
        # exact paths and never a name-based scan.
        if desktop is None:
            desktop = desktop_entry_path(editor.editor_id)
        if managed:
            installed_root = self._installed_dir().expanduser().resolve(strict=False)
            applications_root = desktop_applications_dir().expanduser().resolve(strict=False)
            if not is_within(appimage, installed_root):
                QMessageBox.critical(self, app_dialog_title("Repair Refused"), f"Registered AppImage is outside Suite's managed folder:\n\n{appimage}")
                return
            if desktop.parent != applications_root:
                QMessageBox.critical(self, app_dialog_title("Repair Refused"), f"Registered Desktop Entry is outside the per-user applications folder:\n\n{desktop}")
                return
            if icon is not None and not is_within(icon, installed_root):
                QMessageBox.critical(self, app_dialog_title("Repair Refused"), f"Registered icon is outside Suite's managed folder:\n\n{icon}")
                return
        try:
            if icon is None or not icon.is_file():
                icon = install_icon(editor.icon, self._installed_dir(), editor.editor_id, name=editor.name, version=editor.installed_version or editor.source_version)
            desktop = synchronize_desktop_integration(
                editor.name,
                editor.editor_id,
                appimage,
                icon,
                editor.root,
                desktop_path=desktop,
                desktop_id=desktop_id_for(editor.editor_id),
            )
            version = editor.installed_version
            if managed and isinstance(managed.get("version"), str):
                version = managed.get("version") or version
            registered, _metadata = self._register_managed_installation(
                editor,
                appimage,
                desktop,
                icon,
                version=version,
            )
            override = self._editor_override(editor)
            # Managed identity lives only in managed_installations now.
            for key in ("installed_path", "installed_version", "installed_source_version", "installed_sha256", "built_artifact", "build_script"):
                override.pop(key, None)
            self.config.save()
            self._refresh_desktop_database(Path(registered["desktop_file_path"]).parent)
        except (InstallError, OSError, ValueError) as exc:
            QMessageBox.critical(self, app_dialog_title("Repair Failed"), str(exc))
            return
        self.refresh_editors()
        QMessageBox.information(
            self,
            app_dialog_title("Integration Repaired"),
            f"The registered desktop entry for {editor.name} now points to:\n\n{appimage}\n\nDesktop entry:\n{desktop}",
        )

    def uninstall_editor_appimage(self, editor: EditorEntry) -> None:
        if not sys.platform.startswith("linux"):
            QMessageBox.information(self, app_dialog_title("Not Applicable"), "AppImage uninstall is a Linux feature.")
            return
        managed = self._managed_record(editor)
        if not managed:
            appimage = self._primary_managed_appimage(editor)
            if appimage is not None:
                QMessageBox.information(
                    self,
                    app_dialog_title("Repair Before Uninstall"),
                    f"{editor.name} has an older/unregistered AppImage installation.\n\n"
                    "Use Repair AppImage Integration first. Repair adopts the exact AppImage, desktop and icon paths into Suite's managed registry. "
                    "Uninstall can then remove only those registered files without guessing from filenames.",
                )
            else:
                QMessageBox.information(self, app_dialog_title("Nothing to Uninstall"), f"No registered Suite-managed AppImage installation was found for {editor.name}.")
            return

        paths = record_paths(managed)
        lines = []
        for key, label in (("appimage", "AppImage"), ("desktop", "Desktop entry"), ("icon", "Icon")):
            path = paths.get(key)
            if path is not None:
                lines.append(f"{label}: {path}")
        details = "\n".join(lines)
        reply = QMessageBox.warning(
            self,
            app_dialog_title("Uninstall AppImage"),
            f"Remove the registered Suite-managed AppImage installation for {editor.name}?\n\n"
            f"The portable editor source will NOT be removed.\n\n{details}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            removed = uninstall_registered_appimage_integration(
                managed,
                installed_dir=self._installed_dir(),
            )
            managed_version = str(managed.get("version") or editor.active_version or "").strip()
            if managed_version:
                remove_managed_version(self.config.as_dict(), editor.editor_id, managed_version)
            else:
                remove_managed_installation(self.config.as_dict(), editor.editor_id)
            override = self._editor_override(editor)
            for key in ("installed_path", "installed_version", "installed_source_version", "installed_sha256", "built_artifact", "build_script"):
                override.pop(key, None)
            if override.get("launch_mode") == "installed":
                override["launch_mode"] = "portable" if editor.portable_command else "auto"
            self.config.save()
            desktop = paths.get("desktop")
            self._refresh_desktop_database(desktop.parent if desktop is not None else None)
            app_path = paths.get("appimage")
            if app_path is not None:
                prune_empty_version_tree(app_path.parent.parent, self.editors_root)
        except (InstallError, OSError, ValueError) as exc:
            QMessageBox.critical(self, app_dialog_title("Uninstall Failed"), str(exc))
            return
        self.refresh_editors()
        QMessageBox.information(
            self,
            app_dialog_title("AppImage Uninstalled"),
            f"Removed {len(removed)} registered managed file{'s' if len(removed) != 1 else ''}.\n\n"
            "The portable editor source was left untouched.",
        )

    def remove_portable_folder(self, editor: EditorEntry) -> None:
        portable_root = self._portable_root_for(editor)
        if portable_root is None:
            QMessageBox.information(
                self,
                app_dialog_title("Portable Editor Not Present"),
                f"No removable portable folder is present for {editor.name} in the configured Components folder.",
            )
            return

        managed = self._managed_record(editor)
        managed_paths = record_paths(managed) if managed else {}
        managed_appimage = managed_paths.get("appimage") if managed_paths else None
        installed_remains = bool(managed_appimage is not None and managed_appimage.is_file())
        consequence = (
            "The registered installed AppImage will remain available, so the editor will stay on the Dashboard."
            if installed_remains
            else "No registered installed AppImage will remain, so the editor will disappear from the Dashboard until it is added again."
        )
        reply = QMessageBox.warning(
            self,
            app_dialog_title("Remove Portable Folder"),
            f"Remove the portable folder for {editor.name}?\n\n{portable_root}\n\n"
            f"{consequence}\n\nThis does not uninstall a registered AppImage or its desktop launcher.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            removed = remove_portable_editor_folder(portable_root, self.editors_root)
            prune_empty_version_tree(removed.parent, self.editors_root)
        except (InstallError, OSError) as exc:
            QMessageBox.critical(self, app_dialog_title("Remove Portable Folder Failed"), str(exc))
            return
        self.refresh_editors()
        QMessageBox.information(
            self,
            app_dialog_title("Portable Folder Removed"),
            f"Removed the portable editor folder:\n\n{removed}\n\n{consequence}",
        )

    def purge_editor(self, editor: EditorEntry) -> None:
        portable_root = self._portable_root_for(editor)
        managed = self._managed_record(editor)
        if editor.installed_command and not managed:
            QMessageBox.information(
                self,
                app_dialog_title("Repair Before Purge"),
                f"{editor.name} has an installed launcher that is not yet owned by Suite Pythoine's managed registry.\n\n"
                "Run Repair AppImage Integration first so Suite can adopt the exact AppImage, desktop entry and icon paths. "
                "Purge will then be able to remove them without guessing from filenames.",
            )
            return
        if portable_root is None and not managed:
            QMessageBox.information(
                self,
                app_dialog_title("Nothing to Purge"),
                f"No portable folder or Suite-managed installed copy is present for {editor.name}.",
            )
            return

        self._close_about_dialog()
        wizard = PurgeEditorWizard(
            self,
            editor,
            portable_root=portable_root,
            editors_root=self.editors_root,
            installed_dir=self._installed_dir(),
            config=self.config,
            refresh_desktop_callback=self._refresh_desktop_database,
            finished_callback=lambda: self.refresh_editors(automatic=True),
        )
        wizard.exec()
        self.refresh_editors()
        if wizard.progress_page.succeeded:
            self._status(f"Purged {editor.name} from Suite Pythoine.")
        elif wizard.progress_page.started and wizard.progress_page.finished:
            self._status(f"Purge of {editor.name} stopped: {wizard.progress_page.error_message}")

    def _version_info(self, editor: EditorEntry, version: str) -> EditorVersionInfo | None:
        return next((item for item in editor.versions if item.version == version), None)

    def launch_editor_version(self, editor: EditorEntry, version: EditorVersionInfo, mode: str) -> None:
        parts = version.portable_command if mode == "portable" else version.installed_command
        if parts and is_hub(editor) and mode == "appimage":
            # Historical Suite AppImages that understand --show must remain the
            # exact version the user explicitly selected rather than redirecting
            # themselves through the global Portable preference.
            parts = (*parts, "--show")
        if not parts:
            QMessageBox.information(
                self,
                app_dialog_title("Version Unavailable"),
                f"{editor.name} {version.version} has no {'portable source' if mode == 'portable' else 'AppImage'} to launch.",
            )
            return
        working_directory = version.portable_root if mode == "portable" else (version.appimage_path.parent if version.appimage_path else None)
        command = LaunchCommand(parts[0], tuple(parts[1:]), working_directory)
        if self.launcher.start_detached(command):
            self._status(f"Launched {editor.name} {version.version} [{mode.title()}].")
        else:
            QMessageBox.critical(
                self,
                app_dialog_title("Launch Error"),
                f"Could not launch {editor.name} {version.version} [{mode.title()}].",
            )

    def _sync_suite_appimage_sidecars(self, editor: EditorEntry, version: EditorVersionInfo, desktop: Path, runtime: str) -> None:
        try:
            for other_version, other_record in self._managed_versions(editor).items():
                raw_other = other_record.get("appimage_path")
                if not isinstance(raw_other, str) or not raw_other.strip():
                    continue
                other_appimage = Path(raw_other).expanduser().resolve(strict=False)
                if not other_appimage.is_file():
                    continue
                integrated = runtime == "AppImage" and other_version == version.version
                write_appimage_metadata(
                    other_appimage,
                    editor_id=editor.editor_id,
                    application_id=str(other_record.get("application_id") or editor.editor_id),
                    publisher_id=editor.publisher_id,
                    name=editor.name,
                    version=other_version,
                    desktop_file=desktop if integrated else None,
                    desktop_id=desktop_id_for(editor.editor_id),
                    desktop_integrated=integrated,
                    icon=record_paths(other_record).get("icon"),
                )
        except (OSError, ValueError):
            pass

    def _synchronize_suite_desktop_to_version(self, editor: EditorEntry, version: EditorVersionInfo) -> tuple[str, Path]:
        """Make the selected Suite version/runtime the actual desktop executable."""
        runtime, command = self._suite_runtime_for_version(editor, version)
        desktop = desktop_entry_path(editor.editor_id)
        existing_record = self._managed_record(editor, version.version)
        icon = record_paths(existing_record).get("icon") if existing_record else None
        icon = icon or version.icon or editor.icon
        if runtime == "Portable":
            desktop = synchronize_portable_desktop_integration(
                editor.name,
                editor.editor_id,
                command,
                icon,
                version.portable_root or editor.root,
                desktop_path=desktop,
                desktop_id=desktop_id_for(editor.editor_id),
            )
        else:
            appimage = version.appimage_path
            if appimage is None or not appimage.is_file():
                raise InstallError("The selected Suite AppImage is unavailable.")
            desktop = synchronize_desktop_integration(
                editor.name,
                editor.editor_id,
                appimage,
                icon,
                version.portable_root or editor.root,
                desktop_path=desktop,
                desktop_id=desktop_id_for(editor.editor_id),
            )

        record = dict(existing_record) if existing_record else {}
        record.update({
            "schema": 2,
            "editor_id": editor.editor_id,
            "application_id": editor.editor_id,
            "name": editor.name,
            "version": version.version,
            "desktop_file_path": str(desktop),
            "desktop_id": desktop_id_for(editor.editor_id),
            "icon_path": str(icon) if icon else None,
            "source_version": version.version if version.has_portable else editor.source_version,
            "extensions": list(editor.extensions),
            "description": editor.description,
            "publisher_id": editor.publisher_id,
        })
        if version.appimage_path is not None and version.appimage_path.is_file():
            appimage = version.appimage_path.expanduser().resolve(strict=False)
            record["appimage_path"] = str(appimage)
            record["appimage_sha256"] = str(record.get("appimage_sha256") or sha256_file(appimage))
        set_managed_installation(self.config.as_dict(), record, set_active=True, desktop_integrated=True)
        if not set_active_version(self.config.as_dict(), editor.editor_id, version.version):
            raise InstallError("Could not record the selected active Suite version.")
        if not set_desktop_version(self.config.as_dict(), editor.editor_id, version.version, desktop):
            raise InstallError("Could not record Suite desktop integration ownership.")
        override = self._editor_override(editor)
        override["active_version"] = version.version
        self.config.set("routing_index", {})
        self._sync_suite_appimage_sidecars(editor, version, desktop, runtime)
        self._refresh_desktop_database(desktop.parent)
        return runtime, desktop

    def _make_suite_version_active(self, editor: EditorEntry, version: EditorVersionInfo) -> None:
        data = self.config.as_dict()
        snapshot = copy.deepcopy(data)
        desktop = desktop_entry_path(editor.editor_id)
        desktop_existed = desktop.exists()
        desktop_backup: bytes | None = None
        desktop_mode: int | None = None
        if desktop_existed:
            try:
                desktop_backup = desktop.read_bytes()
                desktop_mode = desktop.stat().st_mode
            except OSError:
                desktop_backup = None
        try:
            runtime, _desktop = self._synchronize_suite_desktop_to_version(editor, version)
            if not self.config.save():
                raise InstallError("Could not save Suite Pythoine preferences.")
        except (InstallError, OSError, ValueError) as exc:
            data.clear(); data.update(snapshot)
            try:
                if desktop_existed and desktop_backup is not None:
                    desktop.parent.mkdir(parents=True, exist_ok=True)
                    desktop.write_bytes(desktop_backup)
                    if desktop_mode is not None:
                        desktop.chmod(desktop_mode)
                elif not desktop_existed and desktop.exists():
                    desktop.unlink()
            except OSError:
                pass
            self.config.save()
            QMessageBox.critical(self, app_dialog_title("Make Active Failed"), str(exc))
            return
        self.refresh_editors()
        QMessageBox.information(
            self,
            app_dialog_title("Active Version Changed"),
            f"{editor.name} {version.version} is now active.\n\nDesktop integration now launches that version's {runtime} runtime directly.",
        )

    def _ensure_suite_direct_desktop_integration(self) -> None:
        """Quietly migrate/repair Suite's desktop entry to its active runtime.

        This is deliberately Suite-only. Component desktop entries, document
        routing, MIME ownership, Developer Intake and drop overrides are not
        touched by the migration.
        """
        editor = self.suite_entry
        if editor is None or not editor.active_version:
            return
        version = self._version_info(editor, editor.active_version)
        if version is None:
            return
        try:
            runtime, command = self._suite_runtime_for_version(editor, version)
        except InstallError as exc:
            self._status(f"Active Suite runtime cannot own desktop integration yet: {exc}")
            return
        desktop = desktop_entry_path(editor.editor_id)
        if runtime == "Portable":
            status = portable_desktop_entry_status(
                editor.editor_id, command, desktop_path=desktop,
                desktop_id=desktop_id_for(editor.editor_id),
                icon_path=version.icon or editor.icon,
            )
        else:
            status = desktop_entry_status(
                editor.editor_id, version.appimage_path, desktop_path=desktop,
                desktop_id=desktop_id_for(editor.editor_id),
                icon_path=version.icon or editor.icon,
            )
        if status != "ready":
            self.repair_suite_desktop_integration(editor, show_dialog=False)

    def repair_suite_desktop_integration(self, editor: EditorEntry, *, show_dialog: bool = True) -> bool:
        if not sys.platform.startswith("linux"):
            if show_dialog:
                QMessageBox.information(self, app_dialog_title("Not Applicable"), "Desktop integration is a Linux feature.")
            return False
        if not editor.active_version:
            if show_dialog:
                QMessageBox.warning(self, app_dialog_title("Runtime Unavailable"), "Suite Pythoine has no active version to integrate.")
            return False
        version = self._version_info(editor, editor.active_version)
        if version is None:
            if show_dialog:
                QMessageBox.warning(self, app_dialog_title("Runtime Unavailable"), "The active Suite Pythoine version is not present in the component inventory.")
            return False
        try:
            runtime, desktop = self._synchronize_suite_desktop_to_version(editor, version)
            if not self.config.save():
                raise InstallError("Could not save Suite Pythoine desktop integration state.")
        except (InstallError, OSError, ValueError) as exc:
            if show_dialog:
                QMessageBox.critical(self, app_dialog_title("Repair Failed"), str(exc))
            else:
                self._status(f"Desktop integration could not follow the active Suite runtime: {exc}")
            return False
        self.refresh_editors(automatic=True)
        if show_dialog:
            QMessageBox.information(
                self,
                app_dialog_title("Integration Repaired"),
                f"Suite Pythoine desktop integration now launches {version.version} [{runtime}] directly.\n\n{desktop}",
            )
        else:
            self._status(f"Desktop integration now follows Suite Pythoine {version.version} [{runtime}].")
        return True

    def make_version_active(self, editor: EditorEntry, version: EditorVersionInfo) -> None:
        if is_hub(editor):
            self._make_suite_version_active(editor, version)
            return
        """Make one retained version active and synchronize desktop integration.

        0.3.0 treats this as one user operation. When the target version has a
        managed/canonical AppImage, the single per-user Desktop Entry must point
        to that exact AppImage before success is reported. Repair remains a
        recovery action, not a required second step after Make Active.
        """
        data = self.config.as_dict()
        snapshot = copy.deepcopy(data)
        desktop_note = "This version has no AppImage, so the existing AppImage desktop bootstrap was left unchanged."
        desktop: Path | None = None
        desktop_backup: bytes | None = None
        desktop_existed = False
        desktop_mode: int | None = None

        try:
            if version.appimage_path is not None and version.appimage_path.is_file():
                appimage = version.appimage_path.expanduser().resolve(strict=False)
                existing_record = self._managed_record(editor, version.version)
                icon = record_paths(existing_record).get("icon") if existing_record else version.icon
                desktop = desktop_entry_path(editor.editor_id)
                if desktop.exists():
                    desktop_existed = True
                    desktop_backup = desktop.read_bytes()
                    desktop_mode = desktop.stat().st_mode

                desktop = synchronize_desktop_integration(
                    editor.name,
                    editor.editor_id,
                    appimage,
                    icon,
                    version.portable_root or editor.root,
                    desktop_path=desktop,
                    desktop_id=desktop_id_for(editor.editor_id),
                )

                record = dict(existing_record) if existing_record else {}
                record.update({
                    "schema": 2,
                    "editor_id": editor.editor_id,
                    "application_id": editor.editor_id,
                    "name": editor.name,
                    "version": version.version,
                    "appimage_path": str(appimage),
                    "appimage_sha256": str(record.get("appimage_sha256") or sha256_file(appimage)),
                    "desktop_file_path": str(desktop),
                    "desktop_id": desktop_id_for(editor.editor_id),
                    "icon_path": str(icon) if icon else None,
                    "source_version": editor.source_version,
                    "extensions": list(editor.extensions),
                    "description": editor.description,
                    "publisher_id": editor.publisher_id,
                })
                set_managed_installation(data, record, set_active=True, desktop_integrated=True)
                if not set_active_version(data, editor.editor_id, version.version):
                    raise InstallError("Could not record the selected active version in the managed registry.")
                if not set_desktop_version(data, editor.editor_id, version.version, desktop):
                    raise InstallError("Could not record the selected desktop-integrated version.")

                desktop_note = f"Desktop integration now points to {version.version}."
            else:
                group = self._managed_group(editor)
                if group and version.version in self._managed_versions(editor):
                    if not set_active_version(data, editor.editor_id, version.version):
                        raise InstallError("Could not record the selected active version in the managed registry.")

            override = self._editor_override(editor)
            override["active_version"] = version.version
            self.config.set("routing_index", {})
            if not self.config.save():
                raise InstallError("Could not save Suite Pythoine preferences.")

        except (InstallError, OSError, ValueError) as exc:
            data.clear()
            data.update(snapshot)
            if desktop is not None:
                try:
                    if desktop_existed and desktop_backup is not None:
                        desktop.parent.mkdir(parents=True, exist_ok=True)
                        desktop.write_bytes(desktop_backup)
                        if desktop_mode is not None:
                            desktop.chmod(desktop_mode)
                    elif not desktop_existed and desktop.exists():
                        desktop.unlink()
                except OSError:
                    pass
            self.config.save()
            QMessageBox.critical(self, app_dialog_title("Make Active Failed"), str(exc))
            return

        # Sidecars mirror the committed registry/desktop state. Failure here does
        # not undo a verified integration; Repair can recreate a damaged sidecar.
        if version.appimage_path is not None and version.appimage_path.is_file() and desktop is not None:
            try:
                for other_version, other_record in self._managed_versions(editor).items():
                    raw_other = other_record.get("appimage_path")
                    if not isinstance(raw_other, str) or not raw_other.strip():
                        continue
                    other_appimage = Path(raw_other).expanduser().resolve(strict=False)
                    if not other_appimage.is_file():
                        continue
                    other_icon = record_paths(other_record).get("icon")
                    write_appimage_metadata(
                        other_appimage,
                        editor_id=editor.editor_id,
                        application_id=str(other_record.get("application_id") or editor.editor_id),
                        publisher_id=editor.publisher_id,
                        name=editor.name,
                        version=other_version,
                        desktop_file=desktop if other_version == version.version else None,
                        desktop_id=desktop_id_for(editor.editor_id),
                        desktop_integrated=other_version == version.version,
                        icon=other_icon,
                    )
            except (OSError, ValueError):
                pass
            self._refresh_desktop_database(desktop.parent)

        self.refresh_editors()
        QMessageBox.information(
            self,
            app_dialog_title("Active Version Changed"),
            f"{editor.name} {version.version} is now the active version.\n\n{desktop_note}",
        )

    def remove_editor_version(self, editor: EditorEntry, version: EditorVersionInfo) -> None:
        if version.version == editor.active_version:
            QMessageBox.information(
                self,
                app_dialog_title("Active Version"),
                "Choose another version with Make Active before removing this version.",
            )
            return
        if version.desktop_integrated or version.version == editor.desktop_version:
            QMessageBox.information(
                self,
                app_dialog_title("Desktop-Integrated Version"),
                "This version currently owns desktop integration. Make another AppImage version active first.",
            )
            return
        components = []
        if version.has_portable:
            components.append(f"Portable: {version.portable_root}")
        if version.has_appimage:
            components.append(f"AppImage: {version.appimage_path}")
        reply = QMessageBox.warning(
            self,
            app_dialog_title("Remove Version"),
            f"Remove {editor.name} {version.version} from Suite Pythoine?\n\n" + "\n".join(components),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            if version.has_appimage and version.managed_record:
                uninstall_registered_appimage_integration(version.managed_record, installed_dir=self._installed_dir())
                remove_managed_version(self.config.as_dict(), editor.editor_id, version.version)
            elif version.has_appimage and version.appimage_path is not None:
                container = version_root(self.editors_root, editor.name, version.version)
                for target in (version.appimage_path, appimage_metadata_path(version.appimage_path), version.icon):
                    if target is None or not target.exists():
                        continue
                    target = target.expanduser().resolve(strict=False)
                    if not is_within(target, container) or target.is_symlink():
                        raise InstallError(f"Refusing to remove unregistered artifact outside the version folder: {target}")
                    target.unlink()
            if version.has_portable and version.portable_root is not None:
                removed = remove_portable_editor_folder(version.portable_root, self.editors_root)
                prune_empty_version_tree(removed.parent, self.editors_root)
            version_container = version_root(self.editors_root, editor.name, version.version)
            prune_empty_version_tree(version_container, self.editors_root)
            self.config.save()
        except (InstallError, OSError, ValueError) as exc:
            QMessageBox.critical(self, app_dialog_title("Remove Version Failed"), str(exc))
            return
        self.refresh_editors()
        QMessageBox.information(self, app_dialog_title("Version Removed"), f"Removed {editor.name} {version.version}.")

    def _component_config_folder(self, editor: EditorEntry) -> Path | None:
        profile = profile_for_id(editor.editor_id)
        if profile is None or not profile.config_subdir:
            return None
        if os.name == "nt":
            base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        else:
            base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        return (base / "brunonlinespace" / profile.config_subdir).expanduser().resolve(strict=False)

    def open_component_config_folder(self, editor: EditorEntry) -> None:
        target = self._component_config_folder(editor)
        if target is None:
            QMessageBox.information(self, app_dialog_title("Config Folder Unknown"), f"Suite Pythoine has no trusted config-folder metadata for {editor.name}.")
            return
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.critical(self, app_dialog_title("Config Folder Error"), str(exc)); return
        self.launcher.open_path(target)

    def _editor_information_text(self, editor: EditorEntry) -> str:
        portable_root = self._portable_root_for(editor)
        appimage = self._primary_managed_appimage(editor) if sys.platform.startswith("linux") else None
        managed = self._managed_record(editor) if sys.platform.startswith("linux") else {}
        extra = ""
        if sys.platform.startswith("linux"):
            managed_paths = record_paths(managed) if managed else {}
            extra = (
                f"\nManaged registry: {'Registered' if managed else ('Unregistered' if appimage else 'Not installed')}\n"
                f"Managed AppImage: {appimage if appimage else 'Not installed'}\n"
                f"Desktop entry: {managed_paths.get('desktop') if managed_paths.get('desktop') else (desktop_entry_path(editor.editor_id) if appimage else 'Not installed')}\n"
                f"Desktop ID: {managed.get('desktop_id') if managed else 'Not registered'}\n"
                f"Managed SHA-256: {managed.get('appimage_sha256') if managed else 'Not registered'}\n"
                f"Desktop integration: {self._integration_status_text(editor, appimage)}"
            )
        runtime_label = {"portable": "Portable / source", "installed": "Installed AppImage", "auto": "Automatic"}.get(editor.launch_mode, editor.launch_mode)
        kind_label = {"hub": "Hub", "editor": "Editor", "reader": "Reader", "extension": "Extension"}.get(editor.component_kind, editor.component_kind.title())
        lines = [
            f"Type: {kind_label}",
            f"Active version: {editor.active_version or 'Unknown'}",
            f"Launch runtime: {runtime_label}",
            f"Desktop-integrated version: {editor.desktop_version or 'None'}",
            f"Versions present: {len(editor.versions)}",
            f"Portable root (active): {portable_root if portable_root else 'Not installed'}",
        ]
        if can_open_document(editor):
            lines.append(f"Formats: {', '.join(editor.extensions) or 'Not configured'}")
        elif editor.component_kind == "hub":
            lines.append("Role: File routing and component management")
        elif editor.component_kind == "extension":
            lines.append("Role: Functional Suite Pythoine extension")
        lines.extend([
            f"Portable version (active): {editor.source_version or ('Unknown' if portable_root else 'Not installed')}",
            f"Installed version (active): {editor.installed_version or ('Unknown' if editor.installed_command else 'Not installed')}",
            f"Available runtimes: {editor.source_kind}",
        ])
        return "\n".join(lines) + extra

    def _version_management_frame(self, editor: EditorEntry, version_info: EditorVersionInfo) -> QFrame:
        version_frame = QFrame()
        version_frame.setFrameShape(QFrame.Shape.StyledPanel)
        version_layout = QVBoxLayout(version_frame)
        version_layout.setContentsMargins(10, 8, 10, 8)
        labels = [version_info.version]
        if version_info.version == editor.active_version:
            labels.append("Active")
        if version_info.desktop_integrated or version_info.version == editor.desktop_version:
            labels.append("Desktop integrated")
        version_title = QLabel(" — ".join(labels))
        title_font = version_title.font()
        title_font.setBold(True)
        version_title.setFont(title_font)
        version_layout.addWidget(version_title)
        state = QLabel(
            f"Portable: {'Yes' if version_info.has_portable else 'No'}   "
            f"AppImage: {'Yes' if version_info.has_appimage else 'No'}   "
            f"Registry: {'Registered' if version_info.managed_record else ('Unregistered' if version_info.has_appimage else '—')}   "
            f"Desktop: {'Active' if version_info.desktop_integrated else 'No'}"
        )
        state.setTextFormat(Qt.TextFormat.PlainText)
        version_layout.addWidget(state)
        actions = QHBoxLayout()
        launch_portable = QPushButton("Launch Portable")
        launch_portable.setEnabled(version_info.has_portable)
        launch_portable.clicked.connect(lambda _checked=False, item=version_info: self.launch_editor_version(editor, item, "portable"))
        actions.addWidget(launch_portable)
        launch_appimage = QPushButton("Launch AppImage")
        launch_appimage.setEnabled(version_info.has_appimage)
        launch_appimage.clicked.connect(lambda _checked=False, item=version_info: self.launch_editor_version(editor, item, "appimage"))
        actions.addWidget(launch_appimage)
        make_active = QPushButton("Make Active")
        make_active.setEnabled(version_info.version != editor.active_version)
        make_active.clicked.connect(lambda _checked=False, item=version_info: self.make_version_active(editor, item))
        actions.addWidget(make_active)
        remove_version = QPushButton("Remove Version…")
        remove_version.setEnabled(version_info.version != editor.active_version and not version_info.desktop_integrated)
        remove_version.clicked.connect(lambda _checked=False, item=version_info: self.remove_editor_version(editor, item))
        actions.addWidget(remove_version)
        open_folder = QPushButton("Open Version Folder")
        folder: Path | None = None
        if version_info.portable_root is not None and version_info.portable_root.is_dir():
            folder = version_info.portable_root.parent
        elif version_info.appimage_path is not None:
            folder = version_info.appimage_path.parent.parent
        open_folder.setEnabled(folder is not None)
        if folder is not None:
            open_folder.clicked.connect(lambda _checked=False, target=folder: self.launcher.open_path(target))
        actions.addWidget(open_folder)
        actions.addStretch(1)
        version_layout.addLayout(actions)
        return version_frame

    def _populate_editor_details(self, layout: QVBoxLayout, editor: EditorEntry, *, include_description: bool = True) -> None:
        title_row = QHBoxLayout()
        if editor.icon and editor.icon.is_file():
            icon = QLabel()
            icon.setPixmap(QIcon(str(editor.icon)).pixmap(48, 48))
            title_row.addWidget(icon)
        title = QLabel(editor.name)
        title.setTextFormat(Qt.TextFormat.PlainText)
        font = title.font()
        font.setPointSize(max(font.pointSize() + 6, 16))
        font.setBold(True)
        title.setFont(font)
        title_row.addWidget(title)
        title_row.addStretch(1)
        layout.addLayout(title_row)

        portable_root = self._portable_root_for(editor)
        appimage = self._primary_managed_appimage(editor) if sys.platform.startswith("linux") else None
        managed = self._managed_record(editor) if sys.platform.startswith("linux") else {}

        information = QLabel(self._editor_information_text(editor))
        information.setTextFormat(Qt.TextFormat.PlainText)
        information.setWordWrap(True)
        information.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(information)

        versions_heading = QLabel("Versions")
        versions_font = versions_heading.font()
        versions_font.setBold(True)
        versions_font.setPointSize(max(versions_font.pointSize() + 1, 10))
        versions_heading.setFont(versions_font)
        layout.addWidget(versions_heading)
        for version_info in editor.versions:
            layout.addWidget(self._version_management_frame(editor, version_info))

        def add_section(section_title: str, actions: tuple[tuple[str, object, bool, str], ...]) -> None:
            heading = QLabel(section_title)
            heading_font = heading.font()
            heading_font.setBold(True)
            heading_font.setPointSize(max(heading_font.pointSize() + 1, 10))
            heading.setFont(heading_font)
            layout.addWidget(heading)
            row = QHBoxLayout()
            for button_text, callback, enabled, tooltip in actions:
                button = QPushButton(button_text)
                button.setEnabled(enabled)
                if tooltip:
                    button.setToolTip(tooltip)
                button.clicked.connect(callback)
                row.addWidget(button)
            row.addStretch(1)
            layout.addLayout(row)

        if editor.component_kind == "editor":
            add_section("File", (
                ("New File…", lambda: self.create_file_for_editor(editor), editor.available, ""),
                ("Open File…", lambda: self.open_with_editor_prompt(editor), editor.available, ""),
            ))
            add_section("Settings", (
                ("Open Config Folder", lambda: self.open_component_config_folder(editor), self._component_config_folder(editor) is not None, "Open this component's user configuration folder."),
                ("Preferences…", lambda: self.editor_preferences(editor), True, ""),
                ("Purge Editor…", lambda: self.purge_editor(editor), bool(portable_root or editor.installed_command or managed),
                 "Remove this editor's managed copies and Suite preferences through a guided purge."),
            ))
            add_section("Portable Editor", (
                ("Remove Portable Folder", lambda: self.remove_portable_folder(editor), portable_root is not None,
                 "Remove only the portable editor folder; a managed AppImage remains available."),
                ("Open Portable Folder", lambda: self.launcher.open_path(portable_root) if portable_root else None, portable_root is not None, ""),
            ))
            if sys.platform.startswith("linux"):
                add_section("Installed Editor", (
                    ("Repair AppImage Integration", lambda: self.repair_appimage_integration(editor), appimage is not None,
                     "Recreate the registered host integration from exact managed paths."),
                    ("Uninstall AppImage", lambda: self.uninstall_editor_appimage(editor), bool(managed),
                     "Remove the exact managed AppImage integration while preserving portable source."),
                    ("Open Installed Folder", lambda: self.launcher.open_path(appimage.parent if appimage else self._installed_dir()), appimage is not None, ""),
                ))
        elif editor.component_kind == "reader":
            add_section("File", (
                ("Launch", lambda: self.launch_editor(editor), editor.available, ""),
                ("Open File…", lambda: self.open_with_editor_prompt(editor), editor.available, ""),
            ))
            add_section("Settings", (
                ("Open Config Folder", lambda: self.open_component_config_folder(editor), self._component_config_folder(editor) is not None, "Open this component's user configuration folder."),
                ("Preferences…", lambda: self.editor_preferences(editor), True, ""),
                ("Purge Reader…", lambda: self.purge_editor(editor), bool(portable_root or editor.installed_command or managed),
                 "Remove this reader's managed copies and Suite preferences through a guided purge."),
            ))
            add_section("Portable Reader", (
                ("Remove Portable Folder", lambda: self.remove_portable_folder(editor), portable_root is not None,
                 "Remove only the portable reader folder; a managed AppImage remains available."),
                ("Open Portable Folder", lambda: self.launcher.open_path(portable_root) if portable_root else None, portable_root is not None, ""),
            ))
            if sys.platform.startswith("linux"):
                add_section("Installed Reader", (
                    ("Repair AppImage Integration", lambda: self.repair_appimage_integration(editor), appimage is not None,
                     "Recreate the registered host integration from exact managed paths."),
                    ("Uninstall AppImage", lambda: self.uninstall_editor_appimage(editor), bool(managed),
                     "Remove the exact managed AppImage integration while preserving portable source."),
                    ("Open Installed Folder", lambda: self.launcher.open_path(appimage.parent if appimage else self._installed_dir()), appimage is not None, ""),
                ))
        elif editor.component_kind == "hub":
            add_section("Hub", (
                ("Open Config Folder", lambda: self.open_component_config_folder(editor), self._component_config_folder(editor) is not None, "Open Suite Pythoine's user configuration folder."),
                ("Preferences…", self.general_preferences, True, "Open Suite Pythoine Preferences."),
                ("Open Components Folder", lambda: self.launcher.open_path(self.editors_root), True, ""),
            ))
            add_section("Portable Runtime", (
                ("Open Portable Folder", lambda: self.launcher.open_path(portable_root) if portable_root else None, portable_root is not None, ""),
            ))
            if sys.platform.startswith("linux"):
                add_section("Integration", (
                    ("Repair Desktop Integration", lambda: self.repair_suite_desktop_integration(editor), bool(editor.active_version and self._version_info(editor, editor.active_version)),
                     "Recovery action: make the application-menu/file-routing launcher point directly to the active Suite runtime."),
                    ("Open Installed Folder", lambda: self.launcher.open_path(appimage.parent if appimage else self._installed_dir()), appimage is not None, ""),
                ))
        else:
            add_section("Extension", (
                ("Launch", lambda: self.launch_editor(editor), editor.available, ""),
                ("Open Config Folder", lambda: self.open_component_config_folder(editor), self._component_config_folder(editor) is not None, "Open this extension's user configuration folder."),
                ("Preferences…", lambda: self.editor_preferences(editor), True, ""),
                ("Purge Extension…", lambda: self.purge_editor(editor), bool(portable_root or editor.installed_command or managed),
                 "Remove this extension's managed copies and Suite preferences through a guided purge."),
            ))
            add_section("Portable Extension", (
                ("Open Portable Folder", lambda: self.launcher.open_path(portable_root) if portable_root else None, portable_root is not None, ""),
            ))
            if sys.platform.startswith("linux"):
                add_section("Installed Extension", (
                    ("Repair AppImage Integration", lambda: self.repair_appimage_integration(editor), appimage is not None, ""),
                    ("Open Installed Folder", lambda: self.launcher.open_path(appimage.parent if appimage else self._installed_dir()), appimage is not None, ""),
                ))

        if include_description and editor.description:
            description = QLabel(editor.description)
            description.setTextFormat(Qt.TextFormat.PlainText)
            description.setWordWrap(True)
            layout.addWidget(description)

    def _editor_page(self, editor: EditorEntry) -> QWidget:
        page = QScrollArea()
        page.setWidgetResizable(True)
        content = QWidget()
        page.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(12)
        self._populate_editor_details(layout, editor)
        layout.addStretch(1)
        return page

    def _version_runtime_is_active(self, editor: EditorEntry, version: EditorVersionInfo, runtime: str) -> bool:
        if version.version != editor.active_version:
            return False
        if is_hub(editor) and version.version == __version__:
            if runtime == "AppImage":
                return self.runtime.running_as_appimage
            if runtime == "Portable":
                return not self.runtime.running_as_appimage
        selected = editor.command()
        if runtime == "Portable":
            return bool(version.portable_command and selected == version.portable_command)
        if runtime == "AppImage":
            return bool(version.installed_command and selected == version.installed_command)
        return False

    def _inventory_records(self) -> list[dict]:
        """Return one Installed Applications record per runtime, not per version.

        A version that has both a Portable source runtime and an AppImage therefore
        contributes two independent rows. This keeps size, install timestamp,
        location, desktop state and managed state specific to the runtime shown.
        """
        records: list[dict] = []
        current_suite_present = False
        for editor in self.components:
            if editor.publisher_id and editor.publisher_id != "brunonlinespace":
                continue
            for version in editor.versions:
                is_current_suite_version = is_hub(editor) and version.version == __version__
                if is_current_suite_version:
                    current_suite_present = True
                if version.has_portable and version.portable_root is not None:
                    location = version.portable_root
                    running_suite = is_current_suite_version and not self.runtime.running_as_appimage
                    records.append({
                        "editor": editor,
                        "version_info": version,
                        "component_id": editor.editor_id,
                        "name": editor.name,
                        "version": version.version,
                        "runtime": "Portable",
                        "active": self._version_runtime_is_active(editor, version, "Portable"),
                        "desktop": self._desktop_runtime_owns_version(editor, version, "Portable"),
                        "size": _tree_size(location),
                        "timestamp": _install_timestamp([location]),
                        "managed": "Suite portable",
                        "locations": [location],
                        "running_suite": running_suite,
                    })

                if version.has_appimage and version.appimage_path is not None:
                    location = version.appimage_path
                    running_suite = is_current_suite_version and self.runtime.running_as_appimage
                    records.append({
                        "editor": editor,
                        "version_info": version,
                        "component_id": editor.editor_id,
                        "name": editor.name,
                        "version": version.version,
                        "runtime": "AppImage",
                        "active": self._version_runtime_is_active(editor, version, "AppImage"),
                        "desktop": self._desktop_runtime_owns_version(editor, version, "AppImage") if is_hub(editor) else bool(version.desktop_integrated or version.version == editor.desktop_version),
                        "size": _tree_size(location),
                        "timestamp": _install_timestamp([location]),
                        "managed": "Suite managed AppImage" if version.managed_record else "Unregistered AppImage",
                        "locations": [location],
                        "running_suite": running_suite,
                    })

        # A source/standalone Suite instance may not itself live below the managed
        # Components root. It still belongs in the Installed Apps-style inventory
        # because this page must always account for the currently running Hub.
        if not current_suite_present:
            runtime_path: Path | None = None
            runtime_type = self.runtime.runtime_label
            if self.runtime.running_as_appimage:
                raw = os.environ.get("APPIMAGE", "").strip()
                if raw:
                    runtime_path = Path(raw).expanduser().resolve(strict=False)
            else:
                runtime_path = self.runtime.launcher_root
            locations = [runtime_path] if runtime_path is not None else []
            records.append({
                "editor": self.suite_entry,
                "version_info": None,
                "component_id": "suite-pythoine",
                "name": APP_NAME,
                "version": __version__,
                "runtime": f"{runtime_type} (running)",
                "active": True,
                "desktop": bool(self.runtime.running_as_appimage),
                "size": _tree_size(runtime_path) if runtime_path is not None else 0,
                "timestamp": _install_timestamp(locations),
                "managed": "Current running Hub",
                "locations": locations,
                "running_suite": True,
            })
        return records

    def _inventory_open_component(self, record: dict) -> None:
        editor = record.get("editor")
        if isinstance(editor, EditorEntry) and not is_hub(editor):
            self.show_editor_details(editor)
        else:
            self.show_suite_details()

    def _inventory_remove_runtime(self, record: dict) -> None:
        editor = record.get("editor")
        version = record.get("version_info")
        runtime = str(record.get("runtime") or "")
        if not isinstance(editor, EditorEntry) or not isinstance(version, EditorVersionInfo):
            return
        if runtime == "Portable":
            self.remove_portable_runtime(editor, version)
        elif runtime == "AppImage":
            self.uninstall_appimage_runtime(editor, version)

    def remove_portable_runtime(self, editor: EditorEntry, version: EditorVersionInfo) -> None:
        root = version.portable_root
        if root is None or not version.has_portable:
            return
        if self._version_runtime_is_active(editor, version, "Portable"):
            QMessageBox.information(self, app_dialog_title("Active Portable Runtime"), "Choose another active runtime before removing this Portable runtime.")
            return
        if self._desktop_runtime_owns_version(editor, version, "Portable"):
            QMessageBox.information(self, app_dialog_title("Desktop-Integrated Runtime"), "Make another Suite runtime active before removing this desktop-integrated Portable runtime.")
            return
        if is_hub(editor) and version.version == __version__ and not self.runtime.running_as_appimage:
            QMessageBox.information(self, app_dialog_title("Running Runtime"), "The currently running Suite Pythoine Portable runtime cannot remove itself.")
            return
        reply = QMessageBox.warning(self, app_dialog_title("Remove Portable"), f"Remove the Portable runtime for {editor.name} {version.version}?\n\n{root}\n\nThe AppImage runtime, if present, will be preserved.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes: return
        try:
            removed = remove_portable_editor_folder(root, self.editors_root)
            prune_empty_version_tree(removed.parent, self.editors_root)
        except (InstallError, OSError) as exc:
            QMessageBox.critical(self, app_dialog_title("Remove Portable Failed"), str(exc)); return
        self.refresh_editors(); self._status(f"Removed Portable runtime for {editor.name} {version.version}.")

    def uninstall_appimage_runtime(self, editor: EditorEntry, version: EditorVersionInfo) -> None:
        if not sys.platform.startswith("linux") or not version.has_appimage or version.appimage_path is None:
            return
        if self._version_runtime_is_active(editor, version, "AppImage"):
            QMessageBox.information(self, app_dialog_title("Active AppImage Runtime"), "Choose another active runtime before uninstalling this AppImage runtime.")
            return
        if (self._desktop_runtime_owns_version(editor, version, "AppImage") if is_hub(editor) else (version.desktop_integrated or version.version == editor.desktop_version)):
            QMessageBox.information(self, app_dialog_title("Desktop-Integrated Runtime"), "Make another runtime active before uninstalling this desktop-integrated AppImage runtime.")
            return
        if is_hub(editor) and version.version == __version__ and self.runtime.running_as_appimage:
            QMessageBox.information(self, app_dialog_title("Running Runtime"), "The currently running Suite Pythoine AppImage cannot uninstall itself.")
            return
        reply = QMessageBox.warning(self, app_dialog_title("Uninstall AppImage"), f"Uninstall the AppImage runtime for {editor.name} {version.version}?\n\n{version.appimage_path}\n\nThe Portable runtime, if present, will be preserved.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes: return
        try:
            if version.managed_record:
                uninstall_registered_appimage_integration(version.managed_record, installed_dir=self._installed_dir())
                remove_managed_version(self.config.as_dict(), editor.editor_id, version.version)
            else:
                container = version_root(self.editors_root, editor.name, version.version)
                for target in (version.appimage_path, appimage_metadata_path(version.appimage_path), version.icon):
                    if target is None or not target.exists(): continue
                    target = target.expanduser().resolve(strict=False)
                    if not is_within(target, container) or target.is_symlink():
                        raise InstallError(f"Refusing to remove unregistered artifact outside the version folder: {target}")
                    target.unlink()
            self.config.save()
            prune_empty_version_tree(version_root(self.editors_root, editor.name, version.version), self.editors_root)
        except (InstallError, OSError, ValueError) as exc:
            QMessageBox.critical(self, app_dialog_title("Uninstall AppImage Failed"), str(exc)); return
        self.refresh_editors(); self._status(f"Uninstalled AppImage runtime for {editor.name} {version.version}.")

    @staticmethod
    def _inventory_column_labels() -> list[str]:
        return [
            "Application", "Version", "Runtime", "Active", "Desktop", "Size",
            "Install date", "Managed", "Location", "Quick actions",
        ]

    def _inventory_layout_state(self) -> dict:
        state = self.config.get("installed_apps_table_layout", {})
        if not isinstance(state, dict):
            return {}
        # exp7 persisted layout keys by visible header label. Preserve the user's
        # existing layout while migrating the renamed "Installed as" column.
        migrated = copy.deepcopy(state)
        old_label = "Installed as"
        new_label = "Runtime"
        order = migrated.get("order")
        if isinstance(order, list):
            migrated["order"] = [new_label if str(item) == old_label else item for item in order]
        widths = migrated.get("widths")
        if isinstance(widths, dict) and old_label in widths and new_label not in widths:
            widths[new_label] = widths.pop(old_label)
        hidden = migrated.get("hidden")
        if isinstance(hidden, list):
            migrated["hidden"] = [new_label if str(item) == old_label else item for item in hidden]
        return migrated

    def _save_inventory_table_layout(self) -> None:
        table = getattr(self, "inventory_table", None)
        if not isinstance(table, QTableWidget) or getattr(self, "_inventory_restoring_layout", False):
            return
        header = table.horizontalHeader()
        labels = self._inventory_column_labels()
        order: list[str] = []
        for visual in range(header.count()):
            logical = header.logicalIndex(visual)
            if 0 <= logical < len(labels):
                order.append(labels[logical])
        widths = {labels[column]: int(table.columnWidth(column)) for column in range(min(table.columnCount(), len(labels)))}
        hidden = [labels[column] for column in range(min(table.columnCount(), len(labels))) if table.isColumnHidden(column)]
        self.config.set(
            "installed_apps_table_layout",
            {"order": order, "widths": widths, "hidden": hidden},
            save=True,
        )

    def _schedule_inventory_table_layout_save(self, *_args) -> None:
        if getattr(self, "_inventory_restoring_layout", False):
            return
        timer = getattr(self, "_inventory_layout_save_timer", None)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._save_inventory_table_layout)
            self._inventory_layout_save_timer = timer
        timer.start(250)

    def _set_inventory_column_visible(self, table: QTableWidget, column: int, visible: bool) -> None:
        table.setColumnHidden(column, not visible)
        self._save_inventory_table_layout()

    def _inventory_header_context_menu(self, table: QTableWidget, position) -> None:
        header = table.horizontalHeader()
        menu = QMenu(header)
        labels = self._inventory_column_labels()
        for column, label in enumerate(labels):
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(not table.isColumnHidden(column))
            action.toggled.connect(
                lambda checked, col=column, target=table: self._set_inventory_column_visible(target, col, checked)
            )
        menu.exec(header.mapToGlobal(position))

    def _restore_inventory_table_layout(self, table: QTableWidget) -> None:
        labels = self._inventory_column_labels()
        header = table.horizontalHeader()
        self._inventory_restoring_layout = True
        try:
            # First-run defaults mirror exp6's compact presentation, but every
            # section becomes interactive immediately afterwards.
            table.resizeColumnsToContents()
            if table.columnCount() > 8:
                table.setColumnWidth(8, min(max(table.columnWidth(8), 240), 360))
            if table.columnCount() > 9:
                table.setColumnWidth(9, max(table.columnWidth(9), 170))

            state = self._inventory_layout_state()
            raw_order = state.get("order", []) if isinstance(state, dict) else []
            order = [str(item) for item in raw_order if str(item) in labels]
            for label in labels:
                if label not in order:
                    order.append(label)
            for target_visual, label in enumerate(order):
                logical = labels.index(label)
                current_visual = header.visualIndex(logical)
                if current_visual >= 0 and current_visual != target_visual:
                    header.moveSection(current_visual, target_visual)

            raw_widths = state.get("widths", {}) if isinstance(state, dict) else {}
            if isinstance(raw_widths, dict):
                for column, label in enumerate(labels):
                    try:
                        width = int(raw_widths.get(label, 0))
                    except (TypeError, ValueError):
                        width = 0
                    if width >= 32:
                        table.setColumnWidth(column, width)

            raw_hidden = state.get("hidden", []) if isinstance(state, dict) else []
            hidden = {str(item) for item in raw_hidden if str(item) in labels}
            for column, label in enumerate(labels):
                table.setColumnHidden(column, label in hidden)
        finally:
            self._inventory_restoring_layout = False

    def _suite_details_page(self) -> QWidget:
        # Suite Details remains the full management surface, while the installed
        # application inventory now has its own dedicated Suite page.
        page = QScrollArea()
        page.setWidgetResizable(True)
        content = QWidget()
        page.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(12)

        if self.suite_entry is not None:
            self._populate_editor_details(layout, self.suite_entry)
        else:
            title = QLabel(APP_NAME)
            font = title.font(); font.setPointSize(max(font.pointSize() + 6, 16)); font.setBold(True); title.setFont(font)
            layout.addWidget(title)
            information = QLabel(
                f"Running version: {__version__} [{self.runtime.runtime_label}]\n"
                f"Components folder: {self.editors_root}\n"
                f"Normal preferences: {self.runtime.config_path}"
            )
            information.setTextFormat(Qt.TextFormat.PlainText)
            information.setWordWrap(True)
            information.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(information)
        layout.addStretch(1)
        return page

    def _installed_applications_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(12)

        inventory_row = QHBoxLayout()
        inventory_heading = QLabel("Installed Applications")
        inventory_font = inventory_heading.font()
        inventory_font.setBold(True)
        inventory_font.setPointSize(max(inventory_font.pointSize() + 2, 12))
        inventory_heading.setFont(inventory_font)
        inventory_row.addWidget(inventory_heading)
        inventory_row.addStretch(1)
        install_component = QPushButton("Install Component…")
        install_component.clicked.connect(self.install_editor_prompt)
        inventory_row.addWidget(install_component)
        refresh = QPushButton("Refresh Inventory")
        refresh.clicked.connect(lambda: self.refresh_editors(automatic=True))
        inventory_row.addWidget(refresh)
        layout.addLayout(inventory_row)

        records = self._inventory_records()
        total_size = sum(int(record.get("size", 0)) for record in records)
        component_count = len({str(record.get("component_id")) for record in records})
        summary = QLabel(
            f"Installed application inventory — {component_count} application{'s' if component_count != 1 else ''}, "
            f"{len(records)} runtime installation{'s' if len(records) != 1 else ''}, {_human_size(total_size)} total. "
            "Each Portable/AppImage runtime has its own row. Click a heading to sort; drag headings to reorder, "
            "drag separators to resize, or right-click a heading to choose visible columns."
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)

        table = QTableWidget(0, 10)
        table.setHorizontalHeaderLabels(self._inventory_column_labels())
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setSortingEnabled(False)
        table.verticalHeader().setVisible(False)
        table.setWordWrap(False)
        # This is a dedicated inventory page: let the table consume all remaining
        # vertical space after the heading, summary, and footnote.
        table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        def text_item(text: str, sort_value=None) -> SortableTableItem:
            item = SortableTableItem(text)
            item.setData(Qt.ItemDataRole.UserRole, text.casefold() if sort_value is None else sort_value)
            return item

        for record in records:
            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, 0, text_item(str(record["name"])))
            table.setItem(row, 1, text_item(str(record["version"])))
            table.setItem(row, 2, text_item(str(record["runtime"])))
            table.setItem(row, 3, text_item("Yes" if record["active"] else "No", 1 if record["active"] else 0))
            table.setItem(row, 4, text_item("Yes" if record["desktop"] else "No", 1 if record["desktop"] else 0))
            table.setItem(row, 5, text_item(_human_size(int(record["size"])), int(record["size"])))
            table.setItem(row, 6, text_item(_format_timestamp(float(record["timestamp"])), float(record["timestamp"])))
            table.setItem(row, 7, text_item(str(record["managed"])))
            location_text = " | ".join(str(path) for path in record["locations"]) or "—"
            location_item = text_item(location_text)
            location_item.setToolTip(location_text)
            table.setItem(row, 8, location_item)

            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(2, 1, 2, 1)
            action_layout.setSpacing(4)
            app_page = QPushButton("App Page")
            app_page.clicked.connect(lambda _checked=False, item=record: self._inventory_open_component(item))
            action_layout.addWidget(app_page)
            runtime_name = str(record.get("runtime") or "")
            remove = QPushButton("Remove Portable…" if runtime_name == "Portable" else "Uninstall AppImage…")
            editor_obj = record.get("editor")
            version_obj = record.get("version_info")
            removable = isinstance(editor_obj, EditorEntry) and isinstance(version_obj, EditorVersionInfo) and not bool(record.get("running_suite"))
            if runtime_name == "Portable" and removable:
                removable = not bool(record.get("active"))
            elif runtime_name == "AppImage" and removable:
                removable = not bool(record.get("active")) and not bool(record.get("desktop"))
            else:
                removable = False
            remove.setEnabled(removable)
            if not removable:
                remove.setToolTip("This runtime is active, running, or desktop-integrated and must be switched away from before removal.")
            remove.clicked.connect(lambda _checked=False, item=record: self._inventory_remove_runtime(item))
            action_layout.addWidget(remove)
            table.setCellWidget(row, 9, action_widget)

        header = table.horizontalHeader()
        header.setSectionsMovable(True)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(lambda pos, target=table: self._inventory_header_context_menu(target, pos))
        header.sectionMoved.connect(self._schedule_inventory_table_layout_save)
        header.sectionResized.connect(self._schedule_inventory_table_layout_save)
        self.inventory_table = table
        self._restore_inventory_table_layout(table)
        table.setSortingEnabled(True)
        table.sortItems(0, Qt.SortOrder.AscendingOrder)
        layout.addWidget(table, 1)

        footnote = QLabel(
            "Install date uses the managed version/runtime folder timestamp where an explicit install timestamp is not available. "
            "Removal is runtime-specific here: Portable rows remove only Portable; AppImage rows uninstall only AppImage. Whole-version removal remains on each app's Versions card."
        )
        footnote.setWordWrap(True)
        layout.addWidget(footnote)
        return page


    def _record_navigation(self, target: str) -> None:
        if target == self._navigation_current:
            return
        if not self._navigation_back_in_progress and self._navigation_current:
            self._navigation_history.append(self._navigation_current)
            if len(self._navigation_history) > 64:
                del self._navigation_history[:-64]
        self._navigation_current = target

    def _navigate_back(self) -> None:
        while self._navigation_history:
            target = self._navigation_history.pop()
            if target == self._navigation_current:
                continue
            self._navigation_back_in_progress = True
            try:
                if target == "dashboard":
                    self.show_dashboard()
                    return
                if target == "suite":
                    self.show_suite_details()
                    return
                if target == "installed-applications":
                    self.show_installed_applications()
                    return
                if target.startswith("editor:"):
                    component_id = target.split(":", 1)[1]
                    editor = next((entry for entry in [*self.editors, *self.readers, *self.extensions] if entry.editor_id == component_id), None)
                    if editor is not None:
                        self.show_editor_details(editor)
                        return
            finally:
                self._navigation_back_in_progress = False

    def show_suite_details(self) -> None:
        if self.suite_page_index is not None:
            self._record_navigation("suite")
            self.stack.setCurrentIndex(self.suite_page_index)
            self.editor_list.clearSelection()
            self.config.set("last_selected_editor", None)

    def show_installed_applications(self) -> None:
        if self.installed_applications_page_index is not None:
            self._record_navigation("installed-applications")
            self.stack.setCurrentIndex(self.installed_applications_page_index)
            self.editor_list.clearSelection()
            self.config.set("last_selected_editor", None)

    def _sidebar_activated(self, item: QListWidgetItem) -> None:
        if item is None or not (item.flags() & Qt.ItemFlag.ItemIsEnabled):
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        editor = next((entry for entry in [*self.editors, *self.readers, *self.extensions] if self._entry_key(entry) == key), None)
        if editor is not None:
            self.show_editor_details(editor)

    def show_dashboard(self) -> None:
        self._record_navigation("dashboard")
        self.stack.setCurrentWidget(self.dashboard)
        self.editor_list.clearSelection()
        self.config.set("last_selected_editor", None)

    def show_store(self) -> None:
        """Launch the optional standalone Store Pythoine extension on demand.

        Suite contains no remote catalogue/browser anymore. If Store Pythoine is
        absent, offer only the normal local Extension installation route.
        """
        store = next((entry for entry in self.extensions if entry.editor_id == "store-pythoine" and entry.available), None)
        if store is not None:
            self.launch_editor(store)
            return

        box = QMessageBox(self)
        box.setWindowTitle(app_dialog_title("Store Pythoine Not Installed"))
        box.setIcon(QMessageBox.Icon.Information)
        box.setText("Store Pythoine is not installed.")
        box.setInformativeText(
            "Store Pythoine is the optional, independently launched catalogue companion. "
            "Suite Pythoine itself does not contact an online catalogue. Install the Store extension manually to use Get More…."
        )
        install_button = box.addButton("Install Extension…", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Close)
        box.exec()
        if box.clickedButton() is install_button:
            self.install_extension_prompt()

    def show_editor_details(self, editor: EditorEntry) -> None:
        key = self._entry_key(editor)
        index = self.editor_pages.get(key)
        if index is not None:
            self._record_navigation(f"editor:{editor.editor_id}")
            self.stack.setCurrentIndex(index)
            self.config.set("last_selected_editor", editor.editor_id)
            for row in range(self.editor_list.count()):
                item = self.editor_list.item(row)
                if item.data(Qt.ItemDataRole.UserRole) == key:
                    if self.editor_list.currentItem() is not item:
                        self.editor_list.setCurrentItem(item)
                    break

    def launch_editor(self, editor: EditorEntry, file_path: Path | None = None) -> None:
        parts = editor.command()
        if not parts:
            QMessageBox.warning(self, app_dialog_title("Editor Unavailable"), f"No launchable version of {editor.name} was found.")
            return

        arguments = list(parts[1:])
        if file_path is not None:
            arguments.append(str(file_path.resolve(strict=False)))
        portable_root = self._portable_root_for(editor)
        working_directory = portable_root
        if working_directory is None and editor.installed_command:
            installed_program = Path(editor.installed_command[0]).expanduser().resolve(strict=False)
            working_directory = installed_program.parent if installed_program.parent.is_dir() else None
        command = LaunchCommand(parts[0], tuple(arguments), working_directory)
        if self.launcher.start_detached(command):
            suffix = f" with {file_path.name}" if file_path is not None else ""
            self._status(f"Launched {editor.name}{suffix}.")
        else:
            QMessageBox.critical(self, app_dialog_title("Launch Error"), f"Could not launch {editor.name}.\n\nCommand: {parts[0]}")

    def launch_prompt(self) -> None:
        candidates = [component for component in self.components if not is_hub(component) and component.available]
        if not candidates:
            QMessageBox.information(
                self,
                app_dialog_title("No Application Available"),
                "No installed application is currently available to launch.",
            )
            return
        labels = [component.name for component in candidates]
        chosen, ok = QInputDialog.getItem(
            self,
            app_dialog_title("Launch"),
            "Launch application:",
            labels,
            0,
            False,
        )
        if ok and chosen:
            self.launch_editor(candidates[labels.index(chosen)])

    def new_file_prompt(self) -> None:
        candidates = [editor for editor in self.components if can_create_document(editor) and editor.available]
        if not candidates:
            QMessageBox.information(
                self,
                app_dialog_title("No Editor Available"),
                "No installed editor is currently available to create a new file.",
            )
            return
        labels = [editor.name for editor in candidates]
        chosen, ok = QInputDialog.getItem(
            self,
            app_dialog_title("New File"),
            "Create the new file with:",
            labels,
            0,
            False,
        )
        if ok and chosen:
            self.create_file_for_editor(candidates[labels.index(chosen)])

    def open_file_prompt(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, app_dialog_title("Open File"), str(Path.home()), "All files (*)")
        if path:
            self.route_file(Path(path))

    def _choose_routing_editor(self, path: Path, candidates: list[EditorEntry]) -> tuple[EditorEntry | None, bool]:
        dialog = QDialog(self)
        dialog.setWindowTitle(app_dialog_title("Choose Application"))
        dialog.setMinimumWidth(430)
        layout = QVBoxLayout(dialog)
        label = QLabel(f"Open {path.name} with:")
        label.setWordWrap(True)
        layout.addWidget(label)
        combo = QComboBox()
        for candidate in candidates:
            combo.addItem(candidate.name, candidate.editor_id)
        layout.addWidget(combo)
        remember = QCheckBox(f"Remember my choice for {path.suffix.casefold() or 'this file type'} files")
        remember.setChecked(False)
        layout.addWidget(remember)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Open | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None, False
        component_id = str(combo.currentData() or "")
        return next((candidate for candidate in candidates if candidate.editor_id == component_id), None), remember.isChecked()

    def _inspector_fallback_candidates(self) -> list[EditorEntry]:
        by_id = {entry.editor_id: entry for entry in self.components}
        return [
            by_id[component_id]
            for component_id in INSPECTOR_FALLBACK_IDS
            if component_id in by_id
            and by_id[component_id].available
            and can_open_document(by_id[component_id])
        ]

    def _choose_inspector_fallback(
        self, path: Path, candidates: list[EditorEntry]
    ) -> tuple[EditorEntry | None, bool, bool]:
        dialog = QDialog(self)
        dialog.setWindowTitle(app_dialog_title("Inspect Unsupported File"))
        dialog.setMinimumWidth(440)
        layout = QVBoxLayout(dialog)
        label = QLabel(
            f"No dedicated Editor or routed Reader is installed for {path.name}.\n"
            "Inspect it with:"
        )
        label.setWordWrap(True)
        layout.addWidget(label)
        combo = QComboBox()
        for candidate in candidates:
            combo.addItem(candidate.name, candidate.editor_id)
        layout.addWidget(combo)
        remember = QCheckBox("Remember my inspection fallback choice")
        remember.setChecked(False)
        layout.addWidget(remember)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Open | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None, False, True
        component_id = str(combo.currentData() or "")
        chosen = next((candidate for candidate in candidates if candidate.editor_id == component_id), None)
        return chosen, remember.isChecked(), False

    def _try_inspector_fallback(self, path: Path) -> bool:
        """Handle unsupported files only after validated routing found zero candidates."""
        candidates = self._inspector_fallback_candidates()
        if not candidates:
            return False
        preference = str(self.config.get("inspector_fallback_preference") or INSPECTOR_FALLBACK_ASK)
        preferred = next((entry for entry in candidates if entry.editor_id == preference), None)
        if preferred is not None:
            self.launch_editor(preferred, path)
            return True
        if len(candidates) == 1:
            self.launch_editor(candidates[0], path)
            return True
        chosen, remember, cancelled = self._choose_inspector_fallback(path, candidates)
        if cancelled:
            return True
        if chosen is None:
            return True
        if remember:
            self.config.set("inspector_fallback_preference", chosen.editor_id, save=True)
        self.launch_editor(chosen, path)
        return True

    def route_file(self, path: Path) -> None:
        path = path.expanduser().resolve(strict=False)
        if not path.is_file():
            QMessageBox.warning(self, app_dialog_title("File Not Found"), str(path))
            return
        if path.suffix.casefold() == ".zip":
            self.install_editor_zip(path)
            return
        if path.suffix.casefold() == ".appimage":
            self.install_editor_appimage(path)
            return

        extension = path.suffix.casefold()
        candidates = document_candidates(self.components, extension)
        if not candidates:
            # Strict post-routing fallback: Beespector/Lite remain routing=false
            # and are considered only after the validated candidate set is empty.
            if self._try_inspector_fallback(path):
                return
            QMessageBox.information(
                self,
                app_dialog_title("No Application Configured"),
                f"No installed Editor or Reader component is configured for {extension or 'files without an extension'}, "
                "and neither Beespector nor Beespector Lite is available for inspection.\n\n"
                "Install the appropriate application or adjust File Routing in Preferences.",
            )
            return

        preferences = self.config.get("extension_preferences", {})
        preferred_id = preferences.get(extension) if isinstance(preferences, dict) else None
        preferred = None if preferred_id == ASK_EVERY_TIME else next((entry for entry in candidates if entry.editor_id == preferred_id), None)
        if preferred is not None:
            self.launch_editor(preferred, path)
            return
        if len(candidates) == 1:
            self.launch_editor(candidates[0], path)
            return

        editor, remember = self._choose_routing_editor(path, candidates)
        if editor is None:
            return
        if remember:
            if not isinstance(preferences, dict):
                preferences = {}
                self.config.set("extension_preferences", preferences)
            preferences[extension] = editor.editor_id
            self.config.save()
        self.launch_editor(editor, path)

    def _filter_for_editor(self, editor: EditorEntry) -> str:
        if not editor.extensions:
            return "All files (*)"
        masks = " ".join(f"*{extension}" for extension in editor.extensions)
        return f"{editor.name} files ({masks});;All files (*)"

    def create_file_for_editor(self, editor: EditorEntry) -> None:
        if not can_create_document(editor):
            QMessageBox.information(self, app_dialog_title("Creation Not Supported"), f"{editor.name} is a Reader and cannot create new files.")
            return
        # Suite facilitates New but never creates or names an editor's document.
        # The selected editor owns its native clean Untitled workflow and Save As.
        self.launch_editor(editor)

    def open_with_editor_prompt(self, editor: EditorEntry) -> None:
        path, _ = QFileDialog.getOpenFileName(self, app_dialog_title(f"Open with {editor.name}"), str(Path.home()), self._filter_for_editor(editor))
        if path:
            self.launch_editor(editor, Path(path))

    def editor_preferences(self, editor: EditorEntry) -> None:
        if is_hub(editor):
            self.general_preferences()
            return
        self._close_about_dialog()
        dialog = EditorPreferencesDialog(self, editor, self.config)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            dialog.apply()
            self.refresh_editors()

    def general_preferences(self) -> None:
        self._close_about_dialog()
        old_suite_mode = self.suite_entry.launch_mode if self.suite_entry is not None else None
        dialog = GeneralPreferencesDialog(
            self,
            self.config,
            self.runtime,
            self.editors_root,
            self.components,
            self.suite_entry,
            self.developer_config,
            self.developer_catalog,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            dialog.apply()
        except OSError as exc:
            QMessageBox.critical(self, app_dialog_title("Preferences Could Not Be Saved"), str(exc))
            return
        self._sync_developer_mode_ui()
        self.dashboard.set_show_icons(bool(self.config.get("dashboard_show_icons", True)))
        self.dashboard.set_drop_bar_visible(bool(self.config.get("dashboard_drop_bar_visible", True)))
        self.icons_action.setChecked(bool(self.config.get("dashboard_show_icons", True)))
        self.drop_bar_action.setChecked(bool(self.config.get("dashboard_drop_bar_visible", True)))
        requested = self.runtime.resolve_editors_root(self.config.get("editors_root"))
        try:
            self.editors_root = self.runtime.ensure_writable_directory(requested)
        except OSError as exc:
            QMessageBox.critical(self, app_dialog_title("Components Folder Unavailable"), str(exc))
            self.editors_root = self.runtime.ensure_writable_directory(self.runtime.default_editors_root)
            self.config.set("editors_root", str(self.editors_root), save=True)
        self.dashboard.editors_root = self.editors_root
        self.refresh_editors()
        if sys.platform.startswith("linux") and self.suite_entry is not None and old_suite_mode != self.suite_entry.launch_mode:
            self.repair_suite_desktop_integration(self.suite_entry, show_dialog=False)

    def install_editor_prompt(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            app_dialog_title("Install Component"),
            str(Path.home()),
            "Component packages (*.zip *.AppImage *.appimage);;Source ZIP archives (*.zip);;AppImage bundles (*.AppImage *.appimage)",
        )
        if path:
            candidate = Path(path)
            if candidate.suffix.casefold() == ".appimage":
                self.install_editor_appimage(candidate)
            else:
                self.install_editor_zip(candidate)

    def install_extension_prompt(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            app_dialog_title("Install Extension"),
            str(Path.home()),
            "Extension packages (*.zip *.AppImage *.appimage);;Source ZIP archives (*.zip);;AppImage bundles (*.AppImage *.appimage)",
        )
        if path:
            candidate = Path(path)
            if candidate.suffix.casefold() == ".appimage":
                self.install_editor_appimage(candidate)
            else:
                self.install_editor_zip(candidate)

    def install_zip_prompt(self) -> None:
        # Compatibility helper retained for older actions/plugins.
        path, _ = QFileDialog.getOpenFileName(self, app_dialog_title("Install Component from ZIP"), str(Path.home()), "ZIP archives (*.zip)")
        if path:
            self.install_editor_zip(Path(path))

    def install_editor_appimage(self, appimage_path: Path) -> bool:
        """Adopt an already-built Pad-family AppImage into managed storage.

        This is intentionally a separate package-install path rather than file
        routing. A dropped .AppImage is an application artifact, not a document.
        """
        if not sys.platform.startswith("linux"):
            QMessageBox.information(self, app_dialog_title("AppImage Not Supported"), "Managed AppImage installation is available on Linux.")
            return False
        appimage_path = appimage_path.expanduser().resolve(strict=False)
        try:
            inspection = inspect_appimage(appimage_path)
        except (InstallError, OSError) as exc:
            QMessageBox.critical(self, app_dialog_title("AppImage Could Not Be Inspected"), str(exc))
            return False
        self._close_about_dialog()
        existing_editor = next((entry for entry in self.components if entry.editor_id == inspection.editor_id), None)
        wizard = AppImageInstallWizard(
            self,
            inspection,
            editors_root=self.editors_root,
            config=self.config,
            existing_editor=existing_editor,
            register_callback=self._register_managed_installation,
            refresh_desktop_callback=self._refresh_desktop_database,
            finished_callback=lambda: self.refresh_editors(automatic=True),
        )
        result = wizard.exec()
        self.refresh_editors()
        if (
            wizard.progress.succeeded
            and inspection.editor_id == "suite-pythoine"
            and wizard.options.make_active_after_install
            and self.suite_entry is not None
            and sys.platform.startswith("linux")
        ):
            self.repair_suite_desktop_integration(self.suite_entry, show_dialog=False)
        if result == QDialog.DialogCode.Accepted and wizard.launch_after_finish:
            editor = next((entry for entry in self.editors if entry.editor_id == inspection.editor_id), None)
            if editor is not None:
                version = next((item for item in editor.versions if item.version == inspection.version), None)
                if version is not None:
                    self.launch_editor_version(editor, version, "installed")
                else:
                    self.launch_editor(editor)
        if wizard.progress.succeeded:
            self._status(f"Installed {inspection.name} {inspection.version} AppImage through the guided installer.")
        elif wizard.progress.started and wizard.progress.finished:
            self._status(f"AppImage installation of {inspection.name} stopped: {wizard.progress.error_message}")
        return bool(wizard.progress.succeeded)

    def install_editor_zip(self, zip_path: Path, *, store_download: bool = False) -> bool:
        """Open the guided installer for a source ZIP.

        Inspection is read-only and happens before the wizard is shown.  The
        component is not copied into the Components folder until the user reaches the
        Progress page after reviewing the full install plan.
        """
        zip_path = zip_path.expanduser().resolve(strict=False)
        # Developer Intake is a strict manual-ZIP bypass, not an alternate normal
        # installer. Store Pythoine transactions use the production full wizard
        # even while Developer Mode is active.
        if self.developer_config.enabled and not store_download:
            self._close_about_dialog()
            dialog = DeveloperIntakeDialog(
                self,
                self.developer_config,
                self.developer_catalog,
                open_path_callback=self.launcher.open_path,
            )
            if dialog.load_zip(zip_path):
                dialog.exec()
            return False
        try:
            inspection = inspect_editor_zip(
                zip_path,
                python_executable=self.launcher.python_executable(),
            )
        except (InstallError, OSError) as exc:
            QMessageBox.critical(self, app_dialog_title("Editor Archive Could Not Be Inspected"), str(exc))
            return False

        self._close_about_dialog()
        existing_editor = next((entry for entry in self.components if entry.editor_id == inspection.editor_id), None)
        wizard = EditorInstallWizard(
            self,
            inspection,
            editors_root=self.editors_root,
            installed_dir=self._installed_dir(),
            config=self.config,
            launcher=self.launcher,
            register_callback=self._register_managed_installation,
            refresh_desktop_callback=self._refresh_desktop_database,
            finished_callback=lambda: self.refresh_editors(automatic=True),
            delete_archive_default=store_download,
            existing_editor=existing_editor,
        )
        result = wizard.exec()
        self.refresh_editors()
        if (
            wizard.progress_page.succeeded
            and inspection.editor_id == "suite-pythoine"
            and wizard.options.make_active_after_install
            and self.suite_entry is not None
            and sys.platform.startswith("linux")
        ):
            self.repair_suite_desktop_integration(self.suite_entry, show_dialog=False)
        if result == QDialog.DialogCode.Accepted and wizard.launch_after_finish:
            editor_id = wizard.installed_editor_id
            editor = next((entry for entry in self.components if entry.editor_id == editor_id), None)
            if editor is not None:
                self.launch_editor(editor)
        if wizard.progress_page.succeeded:
            self._status(f"Installed {inspection.name} through the guided installer.")
        elif wizard.progress_page.started and wizard.progress_page.finished:
            self._status(f"Installation of {inspection.name} stopped: {wizard.progress_page.error_message}")
        return bool(wizard.progress_page.succeeded)

    def _arm_drop_override(self, target: str) -> None:
        self._drop_override_armed = target
        token = target
        QTimer.singleShot(5000, lambda: setattr(self, "_drop_override_armed", "") if self._drop_override_armed == token else None)
        self._status(f"{target.title()} drop override armed for the next drop.")

    @staticmethod
    def _drop_override_from_modifiers(modifiers: Qt.KeyboardModifier, key_hint: str = "") -> str | None:
        required = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
        if modifiers & required != required:
            return None
        key = key_hint.casefold()
        return {"b": "beespector", "y": "youlindo", "c": "crawlindo"}.get(key)

    def _launch_component_argument(self, component_id: str, value: str, label: str) -> bool:
        editor = next((entry for entry in self.components if entry.editor_id == component_id), None)
        if editor is None or not editor.available:
            QMessageBox.critical(self, app_dialog_title(f"{label} Unavailable"), f"No active {label} runtime is available in Suite Pythoine.")
            return False
        parts = editor.command()
        if not parts:
            return False
        working_directory = self._portable_root_for(editor)
        command = LaunchCommand(parts[0], tuple([*parts[1:], value]), working_directory)
        if self.launcher.start_detached(command):
            self._status(f"Sent item to {label}."); return True
        QMessageBox.critical(self, app_dialog_title("Launch Error"), f"Could not launch {label}.")
        return False

    def _url_candidates(self, url: QUrl) -> list[EditorEntry]:
        scheme = url.scheme().casefold()
        host = url.host().casefold()
        matches, fallbacks = [], []
        for entry in self.extensions:
            profile = profile_for_id(entry.editor_id)
            if profile is None or not entry.available or scheme not in profile.url_schemes:
                continue
            host_match = any(host == allowed or host.endswith("." + allowed) for allowed in profile.url_hosts)
            if host_match: matches.append(entry)
            elif profile.url_fallback: fallbacks.append(entry)
        return [*matches, *[item for item in fallbacks if item not in matches]]

    def _route_url(self, url: QUrl, *, forced: str | None = None) -> None:
        text = url.toString().strip()
        if not text or url.scheme().casefold() not in {"http", "https"}:
            QMessageBox.warning(self, app_dialog_title("Unsupported URL"), text or "The dropped value is not a supported HTTP/HTTPS URL.")
            return
        if forced in {"youlindo", "crawlindo"}:
            self._launch_component_argument(forced, text, "Youlindo" if forced == "youlindo" else "Crawlindo"); return
        candidates = self._url_candidates(url)
        if len(candidates) == 1:
            self._launch_component_argument(candidates[0].editor_id, text, candidates[0].name); return
        if len(candidates) > 1:
            self.show_dashboard()
            self.dashboard.show_url_choices(text, [(item.editor_id, item.name) for item in candidates])
            self._status("Choose a URL tool from the Drop Bar.")
            return
        self.launcher.open_url(text)

    def _handle_drop_payloads(self, payloads: object, modifier_value: int = 0) -> None:
        modifiers = Qt.KeyboardModifier(modifier_value)
        # Letter-key state is tracked while the Suite window has focus. The Drop Bar
        # remains the discoverable non-keyboard path when an external drag source
        # does not deliver letter key events to the target application.
        key_hint = getattr(self, "_drop_letter_key", "")
        forced = self._drop_override_armed or self._drop_override_from_modifiers(modifiers, key_hint)
        self._drop_override_armed = ""
        for raw in payloads if isinstance(payloads, list) else []:
            url = raw if isinstance(raw, QUrl) else QUrl.fromUserInput(str(raw))
            if url.isLocalFile():
                path = Path(url.toLocalFile())
                if forced == "beespector": self._launch_component_argument("beespector", str(path.resolve(strict=False)), "Beespector")
                else: self.route_file(path)
            else:
                self._route_url(url, forced=forced if forced in {"youlindo", "crawlindo"} else None)

    def eventFilter(self, watched, event) -> bool:
        if (
            event.type() == QEvent.Type.MouseButtonPress
            and self.isActiveWindow()
            and event.button() == Qt.MouseButton.BackButton
        ):
            self._navigate_back()
            event.accept()
            return True
        if (
            event.type() == QEvent.Type.KeyPress
            and self.isActiveWindow()
            and self.stack.currentWidget() is self.dashboard
            and self.dashboard.search is not QApplication.focusWidget()
        ):
            modifiers = event.modifiers()
            blocked = (
                Qt.KeyboardModifier.ControlModifier
                | Qt.KeyboardModifier.AltModifier
                | Qt.KeyboardModifier.MetaModifier
            )
            text = event.text()
            if not (modifiers & blocked) and text and text.isprintable() and not text.isspace():
                self.dashboard.search.setFocus(Qt.FocusReason.OtherFocusReason)
                self.dashboard.search.insert(text)
                event.accept()
                return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Backspace:
            # Editable child widgets consume Backspace themselves; when the key
            # reaches the main window it acts as browser-style navigation back.
            self._navigate_back()
            event.accept()
            return
        if event.key() in (Qt.Key.Key_B, Qt.Key.Key_Y, Qt.Key.Key_C):
            self._drop_letter_key = {Qt.Key.Key_B:"b", Qt.Key.Key_Y:"y", Qt.Key.Key_C:"c"}[event.key()]
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_B, Qt.Key.Key_Y, Qt.Key.Key_C):
            self._drop_letter_key = ""
        super().keyReleaseEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        mime = event.mimeData()
        if mime.hasUrls() or mime.hasText(): event.acceptProposedAction()
        else: event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        mime = event.mimeData()
        payloads = list(mime.urls()) if mime.hasUrls() else []
        if not payloads and mime.hasText():
            text = mime.text().strip()
            if text: payloads = [QUrl.fromUserInput(text)]
        if not payloads:
            event.ignore(); return
        self._handle_drop_payloads(payloads, int(event.modifiers().value))
        event.acceptProposedAction()

    def handle_startup_paths(self, paths: list[Path]) -> None:
        for path in paths:
            self.route_file(path)

    def _set_dashboard_view(self, mode: str) -> None:
        self.show_dashboard()
        self.dashboard.set_view_mode(mode)
        self.config.set("dashboard_view", mode)
        self._sync_view_actions(mode)

    def _toggle_dashboard_view(self) -> None:
        next_mode = "grid" if self.dashboard.view_mode() == "list" else "list"
        self._set_dashboard_view(next_mode)

    def _focus_dashboard_search(self) -> None:
        self.show_dashboard()
        self.dashboard.search.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def _sync_view_actions(self, mode: str) -> None:
        self.list_action.setChecked(mode == "list")
        self.grid_action.setChecked(mode == "grid")

    def _toggle_developer_mode(self, checked: bool) -> None:
        if not self.developer_config.set_enabled(bool(checked), save=True):
            QMessageBox.critical(self, app_dialog_title("Developer Mode Error"), f"Could not save Developer Intake state to {self.developer_config.path}")
            self._sync_developer_mode_ui(); return
        self._sync_developer_mode_ui()
        self._status("Developer Intake Mode enabled." if checked else "Developer Intake Mode disabled.")

    def _toggle_dashboard_icons(self, checked: bool) -> None:
        self.dashboard.set_show_icons(bool(checked))
        self.config.set("dashboard_show_icons", bool(checked), save=True)

    def _toggle_drop_bar(self, checked: bool) -> None:
        self.dashboard.set_drop_bar_visible(bool(checked))
        self.config.set("dashboard_drop_bar_visible", bool(checked), save=True)

    def _toggle_sidebar(self, checked: bool) -> None:
        self.sidebar.setVisible(checked)
        self.config.set("sidebar_visible", checked)

    def _toggle_fullscreen(self, checked: bool) -> None:
        if checked:
            self.showFullScreen()
        else:
            self.showNormal()

    def _restore_window_state(self) -> None:
        width = self.config.get_int("window_width", 1180, minimum=850)
        height = self.config.get_int("window_height", 760, minimum=560)
        self.resize(width, height)
        sizes = self.config.get_int_list("splitter_sizes", [250, 930], length=2)
        # exp8 caps only the sidebar side of the splitter. Keep a previously
        # collapsed/narrow value, but do not restore any historic oversized width.
        sidebar_size = max(0, min(int(sizes[0]), 250))
        content_size = max(int(sizes[1]), 1)
        self.splitter.setSizes([sidebar_size, content_size])
        sidebar_visible = bool(self.config.get("sidebar_visible", True))
        self.sidebar.setVisible(sidebar_visible)
        self.sidebar_action.setChecked(sidebar_visible)
        view_mode = str(self.config.get("dashboard_view", "list"))
        sort_mode = str(self.config.get("dashboard_sort", "title_az"))
        search_text = str(self.config.get("dashboard_search", ""))
        self.dashboard.set_view_mode(view_mode)
        self.dashboard.set_sort_mode(sort_mode)
        self.dashboard.set_search_text(search_text)
        show_icons = bool(self.config.get("dashboard_show_icons", True))
        show_drop_bar = bool(self.config.get("dashboard_drop_bar_visible", True))
        self.dashboard.set_show_icons(show_icons)
        self.dashboard.set_drop_bar_visible(show_drop_bar)
        self.icons_action.setChecked(show_icons)
        self.drop_bar_action.setChecked(show_drop_bar)
        self._sync_view_actions(view_mode)
        if bool(self.config.get("window_maximized", False)):
            QTimer.singleShot(0, self.showMaximized)

    def _documentation_path(self) -> Path | None:
        candidates = (
            self.runtime.package_root / "docs" / "README.md",
            Path(__file__).resolve().parent / "docs" / "README.md",
        )
        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve(strict=False)
        return None

    def open_documentation(self) -> None:
        documentation = self._documentation_path()
        if documentation is None:
            QMessageBox.warning(
                self,
                app_dialog_title("Documentation Not Found"),
                "Suite Pythoine's bundled documentation could not be found.",
            )
            return
        self.launcher.open_path(documentation)

    def open_github_repository(self) -> None:
        self.launcher.open_url(GITHUB_URL)

    def report_an_issue(self) -> None:
        self.launcher.open_url(ISSUES_URL)

    def _shortcut_catalog(self) -> dict[str, list[tuple[str, QAction | str]]]:
        """Return every real Suite Pythoine shortcut in functional groups."""
        return {
            "File": [
                ("Launch", self.launch_action),
                ("New File", self.new_action),
                ("Open File", self.open_action),
                ("Exit", self.exit_action),
            ],
            "View": [
                ("Dashboard", self.dashboard_action),
                ("Refresh Components", self.refresh_action),
                ("Toggle List/Grid View", self.toggle_view_shortcut_action),
                ("Show Sidebar", self.sidebar_action),
                ("Show Dashboard Icons", self.icons_action),
                ("Show Drop Bar", self.drop_bar_action),
                ("Focus Dashboard Search", self.search_action),
                ("Full Screen", self.fullscreen_action),
                ("Previous Suite Page/Card", "Backspace"),
            ],
            "Tools": [
                ("Open Components Folder", self.open_components_folder_action),
                ("Install Component", self.install_action),
                ("Developer Intake Mode", self.developer_action),
                ("Preferences", self.preferences_action),
            ],
            "Drop Bar": [
                ("Beespector Drop Override", "Ctrl+Shift+B"),
                ("Youlindo URL Drop Override", "Ctrl+Shift+Y"),
                ("Crawlindo URL Drop Override", "Ctrl+Shift+C"),
            ],
            "Help": [
                ("Documentation", self.documentation_action),
                ("Keyboard Shortcuts", self.shortcuts_action),
            ],
        }

    def show_shortcuts(self) -> None:
        if self.shortcuts_dialog is not None:
            self.shortcuts_dialog.show()
            self.shortcuts_dialog.raise_()
            self.shortcuts_dialog.activateWindow()
            return
        dialog = ShortcutsDialog(self._shortcut_catalog(), self)
        dialog.finished.connect(
            lambda _result: setattr(self, "shortcuts_dialog", None)
        )
        self.shortcuts_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        dialog.search.setFocus(Qt.FocusReason.ShortcutFocusReason)


    def _close_about_dialog(self) -> None:
        dialog = self.about_dialog
        if dialog is None:
            return
        self.about_dialog = None
        try:
            dialog.close()
            dialog.deleteLater()
        except RuntimeError:
            pass

    def about(self) -> None:
        if self.about_dialog is not None:
            try:
                self.about_dialog.show()
                self.about_dialog.raise_()
                self.about_dialog.activateWindow()
                return
            except RuntimeError:
                self.about_dialog = None

        # If a modal wizard is active, parent About to that wizard so the
        # dialog remains interactive instead of being visible-but-blocked by
        # the modal window. Otherwise keep the normal modeless pad-family About.
        dialog_parent = QApplication.activeModalWidget() or self
        dialog = QDialog(dialog_parent)
        dialog.setWindowTitle(app_dialog_title("About"))
        dialog.setWindowIcon(self.windowIcon())
        dialog.setModal(False)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.setMinimumWidth(390)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(10)

        if ABOUT_ICON_PATH.is_file():
            logo = QLabel(dialog)
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pixmap = QPixmap(str(ABOUT_ICON_PATH))
            if not pixmap.isNull():
                logo.setPixmap(
                    pixmap.scaled(
                        112, 112,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                layout.addWidget(logo)

        title = QLabel(f"<h2>{html.escape(APP_NAME)}</h2>", dialog)
        title.setTextFormat(Qt.TextFormat.RichText)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        runtime_badge = "AppImage" if self.runtime.running_as_appimage else ("Portable" if not self.runtime.running_frozen else "Frozen")
        version = QLabel(f"Version {html.escape(__version__)} [{runtime_badge}]", dialog)
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)
        tagline = QLabel("<b>Friendly. Fast. Focused.</b>", dialog)
        tagline.setTextFormat(Qt.TextFormat.RichText)
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(tagline)
        description = QLabel(
            "A lightweight hub for installing, managing, launching and routing files to "
            "brunonlinespace editors. Suite Pythoine: a little Python, sweetly caffeinated.",
            dialog,
        )
        description.setWordWrap(True)
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(description)
        details = QLabel(
            f"<a href='{GITHUB_URL}'>{GITHUB_URL}</a><br>"
            "Built on Python and PyQt6, with the shared brunonlinespace pad-family interface.<br>"
            f"<b>Preferences:</b> {html.escape(str(self.runtime.config_path))}<br><br>"
            "Copyright © 2026 Bruno Machado<br>"
            "[<a href='https://github.com/brunonlinespace/'>https://github.com/brunonlinespace/</a>]<br>"
            "Licensed under the GNU General Public License v3 or later.",
            dialog,
        )
        details.setTextFormat(Qt.TextFormat.RichText)
        details.setAlignment(Qt.AlignmentFlag.AlignCenter)
        details.setOpenExternalLinks(False)
        details.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        details.linkActivated.connect(self.launcher.open_url)
        layout.addWidget(details)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, dialog)
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setText("OK")
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)
        def clear_about_reference(_result: int) -> None:
            if self.about_dialog is dialog:
                self.about_dialog = None

        dialog.finished.connect(clear_about_reference)
        self.about_dialog = dialog
        dialog.show()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._closing:
            event.accept()
            return
        self._closing = True
        self.watcher.stop()
        self._save_inventory_table_layout()
        self.config.update(
            {
                "window_width": self.width(),
                "window_height": self.height(),
                "window_maximized": self.isMaximized(),
                "splitter_sizes": self.splitter.sizes(),
                "sidebar_visible": self.sidebar.isVisible(),
                "dashboard_view": self.dashboard.view_mode(),
                "dashboard_sort": str(self.dashboard.sort.currentData()),
                "dashboard_search": self.dashboard.search.text(),
                "dashboard_show_icons": self.icons_action.isChecked(),
                "dashboard_drop_bar_visible": self.drop_bar_action.isChecked(),
            },
            save=True,
        )
        event.accept()



def run_store_install_wizard(package: Path, *, launcher_file: str | Path | None = None) -> int:
    """Run Suite's full normal installer wizard for one Store Pythoine package.

    Store Pythoine is independently launchable and Suite's main window need not
    already be running. This short-lived process constructs the real Suite
    management context but never shows the Hub window; only the same full source
    ZIP/AppImage wizard used by manual Suite installation is presented.
    """
    package = Path(package).expanduser().resolve(strict=False)
    if not package.is_file():
        print(f"Store package not found: {package}", file=sys.stderr)
        return 2

    app = QApplication.instance()
    owns_application = app is None
    if app is None:
        app = QApplication([sys.argv[0]])
        app.setApplicationName("suite-pythoine")
        app.setApplicationDisplayName(APP_NAME)
        app.setApplicationVersion(__version__)
        app.setOrganizationName("brunonlinespace")
        app.setOrganizationDomain("github.com/brunonlinespace")
        app.setDesktopFileName("io.github.brunonlinespace.suite-pythoine")
        if APP_ICON_PATH.is_file():
            app.setWindowIcon(QIcon(str(APP_ICON_PATH)))

    launcher = Path(launcher_file).resolve() if launcher_file else Path(__file__).resolve().parents[1] / "main.py"
    runtime = RuntimePaths.detect(launcher)
    config = ConfigService(runtime.config_path)
    requested = runtime.resolve_editors_root(config.get("editors_root"))
    try:
        editors_root = runtime.ensure_writable_directory(requested)
    except OSError as exc:
        try:
            editors_root = runtime.ensure_writable_directory(runtime.default_editors_root)
        except OSError as fallback_exc:
            print(f"Components folder unavailable ({exc}); fallback also failed ({fallback_exc}).", file=sys.stderr)
            return 1
        config.set("editors_root", str(editors_root), save=True)

    window = SuiteWindow(runtime, config, editors_root)
    outcome = {"code": 1}

    def transact() -> None:
        suffix = package.suffix.casefold()
        if suffix == ".zip":
            succeeded = window.install_editor_zip(package, store_download=True)
        elif suffix == ".appimage":
            succeeded = window.install_editor_appimage(package)
        else:
            QMessageBox.critical(
                window,
                app_dialog_title("Unsupported Store Package"),
                "Store Pythoine may hand Suite Pythoine only a source ZIP or AppImage package.",
            )
            succeeded = False
        outcome["code"] = 0 if succeeded else 1
        app.exit(outcome["code"])

    QTimer.singleShot(0, transact)
    if owns_application:
        app.exec()
    else:
        transact()
    window.close()
    return int(outcome["code"])

def main(launcher_file: str | Path | None = None) -> int:
    if "--version" in sys.argv:
        print(f"{APP_NAME} {__version__}")
        return 0

    smoke_test = "--suite-pythoine-smoke-test" in sys.argv
    qt_argv = [arg for arg in sys.argv if arg != "--suite-pythoine-smoke-test"]
    app = QApplication(qt_argv)
    app.setApplicationName("suite-pythoine")
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("brunonlinespace")
    app.setOrganizationDomain("github.com/brunonlinespace")
    app.setDesktopFileName("io.github.brunonlinespace.suite-pythoine")
    if APP_ICON_PATH.is_file():
        app.setWindowIcon(QIcon(str(APP_ICON_PATH)))

    launcher = Path(launcher_file).resolve() if launcher_file else Path(__file__).resolve().parents[1] / "main.py"
    runtime = RuntimePaths.detect(launcher)
    config = ConfigService(runtime.config_path)

    requested = runtime.resolve_editors_root(config.get("editors_root"))
    try:
        editors_root = runtime.ensure_writable_directory(requested)
    except OSError as exc:
        fallback = runtime.ensure_writable_directory(runtime.default_editors_root)
        editors_root = fallback
        config.set("editors_root", str(fallback), save=True)
        print(f"Components folder '{requested}' was unavailable ({exc}); using '{fallback}'.", file=sys.stderr)

    window = SuiteWindow(runtime, config, editors_root)
    window.show()
    if not smoke_test:
        QTimer.singleShot(0, window.maybe_offer_storage_migration)

    if smoke_test:
        # AppImage packaging smoke test: construct the real main window, allow
        # one Qt event cycle, then close cleanly.  The builder supplies a
        # temporary HOME/XDG_CONFIG_HOME and QT_QPA_PLATFORM=offscreen.
        app.processEvents()
        window.close()
        app.processEvents()
        print(f"{APP_NAME} {__version__} GUI smoke test passed.")
        return 0

    startup_paths = [Path(arg) for arg in sys.argv[1:] if not arg.startswith("-") and Path(arg).expanduser().exists()]
    if startup_paths:
        QTimer.singleShot(0, lambda: window.handle_startup_paths(startup_paths))
    return app.exec()
