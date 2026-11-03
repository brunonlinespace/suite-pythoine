from __future__ import annotations

from pathlib import Path
import copy
import json
import html
import os
import shutil
import sys
import uuid

from PyQt6.QtCore import QEvent, QProcess, QSize, QTimer, Qt, QUrl
from PyQt6.QtGui import QAction, QActionGroup, QCloseEvent, QDragEnterEvent, QDropEvent, QIcon, QKeySequence, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
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
    QTableWidget,
    QVBoxLayout,
    QWizard,
    QWizardPage,
    QWidget,
)

from . import APP_NAME, __version__
from .perf_trace import begin_operation, process_start_perf, trace_set, trace_span, traced_operation
from .config import ConfigService
from .registry_retirement import RegistryRetirementError
from .ui.shell.dashboard import EditorDashboard
from .install_inspection import inspect_editor_zip
from .install_wizard import EditorInstallWizard
from .appimage_inspection import inspect_appimage
from .appimage_wizard import AppImageInstallWizard
from .appimage_build_wizard import ManagedAppImageBuildWizard
from .recovery_restore_wizard import RecoveryRestoreWizard
from .self_restore import HubSelfRestoreWizard
from .recovery import recovery_available, validate_recovery_archive
from .developer.developer_archive import exact_source_version, retain_developer_source_zip
from .developer.developer_policy import developer_intake_drop, developer_retain_drop
from .editor_watcher import EditorDirectoryWatcher
from .installer import (
    InstallError,
    desktop_applications_dir,
    desktop_entry_path,
    desktop_entry_status,
    desktop_entry_runtime,
    desktop_entry_exec_command,
    find_appimage_build_script,
    portable_desktop_entry_status,
    retire_managed_desktop_entry,
    install_icon,
    managed_appimages,
    sha256_file,
    uninstall_registered_appimage_integration,
    remove_portable_editor_folder,
    select_existing_icon_path,
    write_appimage_metadata,
    synchronize_desktop_integration,
    synchronize_portable_desktop_integration,
)
from .installation_state import (
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
from .registry import (EditorEntry, EditorVersionInfo, discover_editors,
                       saved_launch_mode, requested_version_runtime)
from .catalogue.component_policy import can_create_document, can_open_document, document_candidates, document_editors, document_readers, is_backend_only_component, is_hub, is_extension, routable_components
from .catalogue.component_catalog import (COMPONENT_PROFILES, ComponentProfile, bundled_catalog_icon_path, profile_for_id)
from .store.store_content import (
    StoreContentEntry,
    load_store_content,
    publish_trusted_repository_snapshot,
)
from .developer.developer_intake import (
    DeveloperComponentCatalog,
    DeveloperIntakeConfig,
    DeveloperIntakeDialog,
)
from .developer.developer_intake_vault import cleanup_stale_intake_vaults
from .routing.routing_index import build_index_payload
from .routing.silent_dispatch import ASK_EVERY_TIME, INSPECTOR_FALLBACK_ASK, INSPECTOR_FALLBACK_IDS
from .versioning import appimage_metadata_path, version_sort_key
from .runtime.runtime_launcher import LaunchCommand, RuntimeLauncher
from .runtime.runtime_paths import RuntimePaths
from .purge_wizard import PurgeEditorWizard
from .asset_removal import AssetRemovalFailure, RemovalAsset, remove_assets
from .prune_policy import select_prune_records
from .ui_titles import app_dialog_title
from .operation_ui import apply_operation_icon, configure_operation_window, operation_branding_header
from .gui_errors import install_gui_error_hook
from .storage_layout import editor_root, is_within, portable_root, prune_empty_parents, prune_empty_version_tree, recovery_root, version_root
from .storage_migration import build_migration_plan
from .ui.dialogs.shortcuts_dialog import ShortcutsDialog
from .migration_wizard import StorageMigrationWizard
from .ui.shell.suite_theme import apply_theme, normalize_theme
from .ui.helpers import _install_timestamp, _tree_size
from .ui.diagnostic_helpers import (
    _diagnostic_canvas, _populate_diagnostic_canvas, _style_destructive_button,
)
from .ui.widgets.prune import PruneScopePage
from .ui.dialogs.preferences import EditorPreferencesDialog, GeneralPreferencesDialog
from .ui.pages.installed_applications import build_installed_applications_page
from .ui.pages.application import (add_details_identity_header, build_current_version_frame,
    populate_editor_details, build_application_page)
from .ui.pages.version_history_page import (build_version_management_frame, build_version_history_page)
from .ui.pages.store_catalogue import (add_store_enrichment, build_catalogue_page, build_catalog_component_page)
from .ui.shell.sidebar_launcher import SidebarLauncher
from .ui.dialogs.quick_tour import QuickTourDialog
from .suite_uninstall import SuiteUninstallWizard
from .root_transition import transition_legacy_default_root


ASSETS_DIR = Path(__file__).resolve().parent / "assets"
APP_ICON_PATH = ASSETS_DIR / "suite-pythoine-256.png"
ABOUT_ICON_PATH = ASSETS_DIR / "suite-pythoine-128.png"
GITHUB_URL = "https://github.com/brunonlinespace/suite-pythoine"
ISSUES_URL = f"{GITHUB_URL}/issues"




class SuiteWindow(QMainWindow):
    def __init__(self, runtime: RuntimePaths, config: ConfigService, editors_root: Path) -> None:
        super().__init__()
        self.runtime = runtime
        self.config = config
        self.editors_root = editors_root
        with trace_span("window_cleanup_stale_intake_vaults"):
            cleanup_stale_intake_vaults()
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
        self.catalogue_page_index: int | None = None
        self.editor_pages: dict[str, int] = {}
        self.version_history_pages: dict[str, int] = {}
        self.catalog_component_pages: dict[str, int] = {}
        self.store_content: dict[str, StoreContentEntry] = {}
        self.store_content_error = ""
        self._store_backend_process: QProcess | None = None
        self._sidebar_application_keys: set[str] = set()
        self._version_filters: dict[QWidget, QLineEdit] = {}
        self.catalogue_search: QLineEdit | None = None
        self._managed_mutation_depth = 0
        self._managed_refresh_pending = False
        self._closing = False
        self._suite_uninstall_exiting = False
        self._drop_letter_key = ""
        self._drop_override_armed = ""
        self._navigation_history: list[str] = []
        self._navigation_current = "dashboard"
        self._navigation_back_in_progress = False
        self.about_dialog: QDialog | None = None
        self.shortcuts_dialog: ShortcutsDialog | None = None
        self._sidebar_launcher: SidebarLauncher | None = None
        self._sidebar_mode = "left"
        self._last_docked_side = "left"
        self._sidebar_requested_visible = True
        self._restored_sidebar_width = 250

        self.launcher = RuntimeLauncher(runtime, self)
        self.launcher.launch_error.connect(lambda message: QMessageBox.warning(self, app_dialog_title("Launch Failed"), message))
        self.launcher.status_message.connect(self._status)
        self.watcher = EditorDirectoryWatcher(parent=self)
        self.watcher.refresh_requested.connect(self._watcher_refresh_requested)

        self.setWindowTitle(app_dialog_title("Dashboard"))
        if APP_ICON_PATH.is_file():
            self.setWindowIcon(QIcon(str(APP_ICON_PATH)))
        self.setAcceptDrops(True)
        with trace_span("window_make_menu"):
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
        with trace_span("window_build_sidebar"):
            self.sidebar = self._build_sidebar()
        self.splitter.addWidget(self.sidebar)
        self.splitter.setCollapsible(0, True)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.dev_status_badge = QLabel("DEV MODE")
        self.dev_status_badge.setStyleSheet("QLabel { font-weight: bold; padding: 2px 7px; border: 1px solid palette(mid); border-radius: 4px; }")
        self.dev_status_badge.setToolTip("Developer Mode adds optional build controls. Drop ZIP normally for Intake, Shift+drop to install normally, or Ctrl+drop to retain Recovery.")
        self.statusBar().addPermanentWidget(self.dev_status_badge)
        self.stack = QStackedWidget()
        self.splitter.addWidget(self.stack)
        self.splitter.splitterMoved.connect(self._remember_sidebar_width)

        with trace_span("window_dashboard_construct"):
            self.dashboard = EditorDashboard(APP_NAME, self.editors_root, APP_ICON_PATH)
        self.dashboard.launch_requested.connect(self.launch_editor)
        self.dashboard.new_requested.connect(self.create_file_for_editor)
        self.dashboard.open_requested.connect(self.open_with_editor_prompt)
        self.dashboard.details_requested.connect(self.show_editor_details)
        self.dashboard.refresh_requested.connect(self.refresh_editors)
        self.dashboard.view_toggle_requested.connect(self._toggle_dashboard_view)
        self.dashboard.launch_prompt_requested.connect(self._show_dashboard_launcher)
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

        with trace_span("window_restore_state"):
            self._restore_window_state()
        self._prompted_discovery: set[tuple[str, str]] = set()
        self._resolving_desktop_questions = False
        with trace_span("window_sync_developer_mode"):
            self._sync_developer_mode_ui()
        with trace_span("window_initial_refresh"):
            self.refresh_editors()
        # Startup-only UI such as the first-run Quick Tour is scheduled by the
        # normal interactive main() path, not by generic SuiteWindow construction.
        # Store transactions and packaging smoke tests also construct this window.
        # No automatic desktop repair, including the Hub: a launcher is a
        # user-controlled executable target and must never be silently rewritten.
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
        file_menu.addSeparator()
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
        self.dashboard_action = QAction("Dashboard", self)
        self.dashboard_action.setShortcut("Ctrl+W")
        self.dashboard_action.triggered.connect(self.show_dashboard)
        view.addAction(self.dashboard_action)
        self.refresh_action = QAction("Refresh Applications", self)
        self.refresh_action.setShortcut("F5")
        self.refresh_action.triggered.connect(self.refresh_editors)
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

        current_theme = normalize_theme(self.config.get("app_theme", "system"))
        self.theme_actions: dict[str, QAction] = {}
        self.theme_group = QActionGroup(self)
        self.theme_group.setExclusive(True)
        for value, label in (("light", "Light"), ("dark", "Dark"), ("system", "System")):
            action = QAction(label, self, checkable=True)
            action.setChecked(value == current_theme)
            action.triggered.connect(
                lambda _checked=False, selected=value: self._set_theme(selected)
            )
            self.theme_group.addAction(action)
            self.theme_actions[value] = action

        # Keyboard-only toggle: intentionally not exposed as a menu entry.
        self.toggle_view_shortcut_action = QAction("Toggle List/Grid View", self)
        self.toggle_view_shortcut_action.setShortcut("Ctrl+Alt+Shift+V")
        self.toggle_view_shortcut_action.triggered.connect(self._toggle_dashboard_view)
        self.addAction(self.toggle_view_shortcut_action)

        view.addSeparator()
        theme_menu = view.addMenu("App Theme")
        for value in ("light", "dark", "system"):
            theme_menu.addAction(self.theme_actions[value])
        view.addSeparator()
        self.sidebar_action = QAction("Show Sidebar", self, checkable=True)
        self.sidebar_action.setShortcut("F9")
        self.sidebar_action.triggered.connect(self._toggle_sidebar)
        view.addAction(self.sidebar_action)
        position_menu = view.addMenu("Sidebar Position")
        self.sidebar_position_actions: dict[str, QAction] = {}
        position_group = QActionGroup(self)
        position_group.setExclusive(True)
        for position, label in (("left", "Dock Left"), ("right", "Dock Right"),
                                ("floating", "Floating Launcher")):
            action = QAction(label, self, checkable=True)
            action.triggered.connect(
                lambda _checked=False, choice=position: self._set_sidebar_mode(choice)
            )
            position_group.addAction(action)
            position_menu.addAction(action)
            self.sidebar_position_actions[position] = action
        self.toggle_sidebar_position_action = QAction("Toggle Sidebar Dock Side", self)
        self.toggle_sidebar_position_action.setShortcut("Shift+F9")
        self.toggle_sidebar_position_action.triggered.connect(self._toggle_sidebar_position)
        self.addAction(self.toggle_sidebar_position_action)
        self.fullscreen_action = QAction("Full Screen", self, checkable=True)
        self.fullscreen_action.setShortcut("F11")
        self.fullscreen_action.triggered.connect(self._toggle_fullscreen)
        view.addSeparator()
        view.addAction(self.fullscreen_action)

        self.search_action = QAction("Focus Search", self)
        self.search_action.setShortcut("Ctrl+F")
        self.search_action.triggered.connect(self._focus_contextual_search)
        self.addAction(self.search_action)

        self.previous_application_action = QAction("Previous Application", self)
        self.previous_application_action.setShortcut("Ctrl+Up")
        self.previous_application_action.triggered.connect(lambda _checked=False: self._navigate_sidebar_application(-1))
        self.addAction(self.previous_application_action)
        self.next_application_action = QAction("Next Application", self)
        self.next_application_action.setShortcut("Ctrl+Down")
        self.next_application_action.triggered.connect(lambda _checked=False: self._navigate_sidebar_application(1))
        self.addAction(self.next_application_action)

        tools = self.menuBar().addMenu("Tools")
        tools.addAction(self.refresh_action)
        tools.addSeparator()
        self.hub_details_action = QAction("Hub Details", self)
        self.hub_details_action.setShortcut("Ctrl+S")
        self.hub_details_action.triggered.connect(self.show_suite_details)
        tools.addAction(self.hub_details_action)
        self.open_components_folder_action = QAction("Open Applications Folder…", self)
        self.open_components_folder_action.setShortcut("Ctrl+Shift+O")
        self.open_components_folder_action.triggered.connect(lambda: self.launcher.open_path(self.editors_root))
        # Retain Ctrl+Shift+O without keeping the old Tools menu entry.
        self.addAction(self.open_components_folder_action)
        self.preferences_action = QAction("Hub Preferences…", self)
        self.preferences_action.setShortcut("Ctrl+/")
        self.preferences_action.triggered.connect(self.general_preferences)
        tools.addAction(self.preferences_action)
        tools.addSeparator()
        self.installed_applications_action = QAction("Installed Applications", self)
        self.installed_applications_action.setShortcut("Ctrl+I")
        self.installed_applications_action.triggered.connect(self.show_installed_applications)
        tools.addAction(self.installed_applications_action)
        self.install_action = QAction("Install Application…", self)
        self.install_action.setShortcut("Ctrl+Shift+I")
        self.install_action.triggered.connect(self.install_editor_prompt)
        tools.addAction(self.install_action)
        tools.addSeparator()
        self.store_action = QAction("Get More Applications…", self)
        self.store_action.triggered.connect(self.show_store)
        tools.addAction(self.store_action)
        tools.addSeparator()
        self.developer_action = QAction("Developer Mode", self, checkable=True)
        self.developer_action.setShortcut("F12")
        self.developer_action.setToolTip("Normal installation plus optional build controls; normal ZIP drop opens Intake, Shift+ZIP bypasses Intake to install, and Ctrl+ZIP retains Recovery. State persists.")
        self.developer_action.triggered.connect(self._toggle_developer_mode)
        tools.addAction(self.developer_action)
        self.developer_intake_action = QAction("Developer Intake…", self)
        self.developer_intake_action.setShortcut("Ctrl+Alt+Shift+D")
        self.developer_intake_action.setToolTip("Open Developer Intake; in Developer Mode a normal ZIP drop also opens Intake, while Shift+ZIP bypasses it for normal installation.")
        self.developer_intake_action.triggered.connect(lambda _checked=False: self.developer_intake_prompt())
        tools.addAction(self.developer_intake_action)
        self.retain_source_zip_action = QAction("Retain Source ZIP (Recovery Only)…", self)
        self.retain_source_zip_action.setShortcut("Ctrl+Alt+Shift+R")
        self.retain_source_zip_action.setToolTip(
            "Developer Mode only: retain an exact-version, trusted source ZIP in managed Recovery "
            "without installing Portable, building AppImage or changing the active version. "
            "Alternatively hold Ctrl while dropping a source ZIP."
        )
        self.retain_source_zip_action.triggered.connect(lambda _checked=False: self.retain_developer_source_zip_prompt())
        tools.addAction(self.retain_source_zip_action)

        help_menu = self.menuBar().addMenu("Help")
        self.documentation_action = QAction("Documentation", self)
        self.documentation_action.setShortcut("F1")
        self.documentation_action.triggered.connect(self.open_documentation)
        help_menu.addAction(self.documentation_action)
        help_menu.addSeparator()
        self.quick_tour_action = QAction("Quick Tour…", self)
        self.quick_tour_action.setShortcut("Shift+F1")
        self.quick_tour_action.triggered.connect(self.show_quick_tour)
        help_menu.addAction(self.quick_tour_action)
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
        title = QLabel("Applications")
        font = title.font()
        font.setBold(True)
        font.setPointSize(max(font.pointSize() + 2, 11))
        title.setFont(font)
        layout.addWidget(title)
        tip = QLabel("Drop a supported file to route it, or drop a recognized application ZIP/AppImage to install it.")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        dashboard = QPushButton("Dashboard")
        dashboard.clicked.connect(self.show_dashboard)
        layout.addWidget(dashboard)
        refresh_btn = QPushButton("Refresh Applications")
        refresh_btn.clicked.connect(self.refresh_editors)
        layout.addWidget(refresh_btn)

        self.editor_list = QListWidget()
        self.editor_list.setIconSize(QSize(26, 26))
        self.editor_list.setSpacing(1)
        self.editor_list.itemClicked.connect(self._sidebar_clicked)
        self.editor_list.currentItemChanged.connect(self._sidebar_current_changed)
        self.editor_list.itemDoubleClicked.connect(self._sidebar_double_clicked)
        # Enter is handled by the sidebar's KeyPress filter below, separate
        # from itemActivated (which can also fire on mouse double-click).
        layout.addWidget(self.editor_list, 1)

        self.store_button = QPushButton("Get More…")
        self.store_button.clicked.connect(self.show_store)
        layout.addWidget(self.store_button)

        self.dev_sidebar_badge = QLabel("DEV MODE ACTIVE")
        self.dev_sidebar_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.dev_sidebar_badge.setStyleSheet("QLabel { font-weight: bold; padding: 4px; border: 1px solid palette(mid); border-radius: 4px; }")
        self.dev_sidebar_badge.setToolTip("Normal ZIP drops open Developer Intake; hold Shift while dropping to bypass Intake and install normally.")
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
                app_dialog_title("Move Existing Applications"),
                "Suite Pythoine 0.3.0 uses a new canonical managed folder:\n\n"
                f"{self.editors_root}\n\n"
                f"Existing managed applications were found in:\n{legacy_unified}\n\n"
                "Move those version folders into the new applications root now? Existing destination versions are never overwritten.",
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
                    QMessageBox.information(self, app_dialog_title("Application Migration"), message)
                except Exception as exc:
                    QMessageBox.critical(self, app_dialog_title("Application Migration Failed"), str(exc))
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
            app_dialog_title("Organise Existing Applications"),
            "Older portable application files were found outside Suite Pythoine's canonical managed root.\n\n"
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
            self._status("Existing applications were organised into the managed root.")

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
        for action_name in ("developer_intake_action", "retain_source_zip_action"):
            if hasattr(self, action_name):
                action = getattr(self, action_name)
                action.setVisible(active)
                action.setEnabled(active)
        if hasattr(self, "dev_sidebar_badge"):
            self.dev_sidebar_badge.setVisible(active)
        if hasattr(self, "dev_status_badge"):
            self.dev_status_badge.setVisible(active)
        # App Pages are cached. Developer-only controls therefore exist in the
        # page once and are shown/hidden in place instead of forcing discovery
        # and wholesale App Page reconstruction on every F12 toggle.
        for control in self.findChildren(QWidget):
            if bool(control.property("suite_developer_only")):
                control.setVisible(active)
        self.setWindowTitle(app_dialog_title("Dashboard") + (" — Developer Mode" if active else ""))

    def _watcher_refresh_requested(self) -> None:
        """Coalesce watcher noise generated by Suite's own managed mutations."""
        if self._managed_mutation_depth > 0:
            self._managed_refresh_pending = True
            return
        self.refresh_editors(automatic=True)

    def _begin_managed_mutation(self) -> None:
        self._managed_mutation_depth += 1
        self.watcher.begin_suppression()

    def _end_managed_mutation(self) -> None:
        if self._managed_mutation_depth <= 0:
            return
        self._managed_mutation_depth -= 1
        # The installer performs one authoritative refresh immediately after
        # the modal transaction. Discard filesystem events caused by that same
        # transaction so a delayed watcher timer cannot rebuild everything again.
        self.watcher.end_suppression(discard_pending=True)
        if self._managed_mutation_depth == 0:
            self._managed_refresh_pending = False

    def _installed_dir(self) -> Path:
        # Compatibility name: managed AppImages now live below the same Editors root.
        return self.editors_root

    @staticmethod
    def _entry_key(editor: EditorEntry) -> str:
        return str(editor.root)

    @traced_operation("refresh_editors")
    def refresh_editors(self, automatic: bool = False) -> None:
        trace_set("automatic", bool(automatic))
        selected_root = None
        selected_version = None
        selected_component_id = None
        current = self.stack.currentWidget()
        if current is not None:
            selected_root = current.property("editor_root")
            selected_version = current.property("suite_selected_version")
            selected_component_id = current.property("suite_component_id")

        with trace_span("inventory_discovery"):
            components = discover_editors(
                self.editors_root,
                self._installed_dir(),
                self.config.as_dict(),
                python_executable=self.launcher.python_executable(),
            )
        trace_set("components", len(components))
        if sys.platform.startswith("linux"):
            retired_desktop = False
            backend_selection_migrated = False
            for component in components:
                if not is_backend_only_component(component):
                    continue
                override = self._editor_override(component)
                if component.active_version and override.get("active_version") != component.active_version:
                    override["active_version"] = component.active_version
                    backend_selection_migrated = True
                if component.launch_mode in {"portable", "installed"} and override.get("launch_mode") != component.launch_mode:
                    override["launch_mode"] = component.launch_mode
                    backend_selection_migrated = True
                try:
                    retired = retire_managed_desktop_entry(component.editor_id)
                except InstallError as exc:
                    self._status(f"Could not retire obsolete {component.name} desktop launcher: {exc}")
                    continue
                retired_desktop = retired_desktop or retired is not None
            if backend_selection_migrated:
                self.config.save()
            if retired_desktop:
                self._refresh_desktop_database(desktop_applications_dir())
        self.components = components
        self.suite_entry = next((entry for entry in components if is_hub(entry)), None)
        self.editors = document_editors(components)
        self.readers = document_readers(components)
        self.routable = routable_components(components)
        self.extensions = [entry for entry in components if is_extension(entry)]
        self._reload_store_content()
        self._sync_store_navigation()

        # The hot routing path consumes this compact local inventory instead of
        # scanning the managed tree on every file double-click. Full discovery
        # above remains authoritative and refreshes the cache whenever Suite is
        # already open.
        routing_index = build_index_payload(components, self.editors_root)
        if self.config.get("routing_index") != routing_index:
            self.config.set("routing_index", routing_index)
            self.config.save()

        self.dashboard.editors_root = self.editors_root
        with trace_span("dashboard_set_components"):
            self.dashboard.set_components([*self.editors, *self.readers, *self.extensions])
        with trace_span("rebuild_page_cache"):
            self._rebuild_editor_pages(selected_root, selected_version, selected_component_id)
        trace_set("editors", len(self.editors))
        trace_set("readers", len(self.readers))
        trace_set("extensions", len(self.extensions))
        self.watcher.watch([self.editors_root])
        if sys.platform.startswith('linux') and not self._resolving_desktop_questions:
            QTimer.singleShot(0, self._resolve_desktop_questions)
        prefix = "Updated" if automatic else "Found"
        self._status(
            f"{prefix} {len(self.editors)} editor{'s' if len(self.editors) != 1 else ''}, "
            f"{len(self.readers)} reader{'s' if len(self.readers) != 1 else ''}, and "
            f"{len(self.extensions)} extension{'s' if len(self.extensions) != 1 else ''} in the Applications folder."
        )

    def _resolve_desktop_questions(self) -> None:
        """One prompt per newly discovered component/state in this GUI session.

        Desktop failures cannot be resolved by guessing a newest version. This
        method never adopts external launchers or runs application code.
        """
        if self._resolving_desktop_questions:
            return
        self._resolving_desktop_questions = True
        try:
            for editor in list(self.components):
                state = editor.desktop_issue
                if state == 'missing' and editor.active_version:
                    continue  # remembered fallback works; user may select Repair
                overrides = self.config.get('editor_overrides', {})
                pref = overrides.get(editor.editor_id, {}) if isinstance(overrides, dict) else {}
                remembered = pref.get('active_version') if isinstance(pref, dict) else None
                if state == 'ready' and remembered and remembered != editor.active_version:
                    key = (editor.editor_id, 'preference-mismatch:' + str(editor.active_version))
                    if key not in self._prompted_discovery:
                        self._prompted_discovery.add(key)
                        answer = QMessageBox.question(
                            self, app_dialog_title('Active Version Disagreement'),
                            f"{editor.name}: the verified desktop launcher selects {editor.active_version}, "
                            f"but preferences remember {remembered}.\n\nUpdate the remembered fallback to match the actual launcher? "
                            'Declining does not change the launcher.',
                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                            QMessageBox.StandardButton.No)
                        if answer == QMessageBox.StandardButton.Yes:
                            self._editor_override(editor)['active_version'] = editor.active_version
                            self.config.save()
                    continue
                if state not in {'selection-required', 'broken', 'legacy-launcher', 'external-target'}:
                    continue
                key = (editor.editor_id, state)
                if key in self._prompted_discovery:
                    continue
                self._prompted_discovery.add(key)
                valid = [v for v in editor.versions if not v.validation_issue and (v.has_portable or v.has_appimage)]
                if state != 'selection-required':
                    descriptions = {'broken': 'the launcher points to a missing or unrecognised runtime',
                                    'legacy-launcher': 'the launcher lacks required Suite metadata',
                                    'external-target': 'the launcher targets an application outside Suite’s managed directory'}
                    answer = QMessageBox.warning(self, app_dialog_title('Desktop Integration Needs Attention'),
                        f"{editor.name}: {descriptions[state]}.\n\nNormal launch and file routing are paused. "
                        'The existing launcher will not be modified automatically.\n\nChoose a verified version and explicitly repair integration?',
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No)
                    if answer != QMessageBox.StandardButton.Yes:
                        continue
                if not valid:
                    QMessageBox.information(self, app_dialog_title('No Valid Runtime'),
                        f'{editor.name} has no verified launchable version to activate.')
                    continue
                choices = [(f'{v.version} — {kind}', v, kind) for v in valid
                           for kind in ('Portable', 'AppImage')
                           if (v.has_portable if kind == 'Portable' else v.has_appimage)]
                selected, accepted = QInputDialog.getItem(
                    self, app_dialog_title('Choose Active Installation'),
                    f'Choose {editor.name} version and runtime for desktop integration:',
                    [label for label, _v, _kind in choices], 0, False)
                if not accepted or not selected:
                    continue
                _label, chosen, runtime = next(item for item in choices if item[0] == selected)
                self.make_version_active(editor, chosen, preferred_runtime='portable' if runtime == 'Portable' else 'installed')
        finally:
            self._resolving_desktop_questions = False

    def _rebuild_editor_pages(
        self,
        selected_root: object = None,
        selected_version: object = None,
        selected_component_id: object = None,
    ) -> None:
        for index in range(self.stack.count() - 1, -1, -1):
            widget = self.stack.widget(index)
            if bool(widget.property("suite_editor_page")):
                self.stack.removeWidget(widget)
                widget.deleteLater()
        self.editor_list.clear()
        self.editor_pages.clear()
        self.version_history_pages.clear()
        self.catalog_component_pages.clear()
        self.catalogue_page_index = None
        self._sidebar_application_keys.clear()
        self._version_filters.clear()
        self.catalogue_search = None

        # Preserve in-session disclosure state across refresh/rebuild.  The
        # QStackedWidget pages remain populated while sidebar rows are hidden.
        collapsed = getattr(self, "_collapsed_sidebar_groups", set())
        self._collapsed_sidebar_groups = collapsed
        self._sidebar_group_members: dict[str, list[QListWidgetItem]] = {}
        self._sidebar_group_headers: dict[str, QListWidgetItem] = {}

        def add_heading(label: str) -> None:
            heading = QListWidgetItem(("▸ " if label in collapsed else "▾ ") + label)
            heading.setData(Qt.ItemDataRole.UserRole, f"__group__:{label}")
            heading.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            heading.setToolTip("Click to expand or collapse this group.")
            heading_font = heading.font()
            heading_font.setBold(True)
            heading.setFont(heading_font)
            heading.setSizeHint(QSize(0, 30))
            self.editor_list.addItem(heading)
            self._sidebar_group_headers[label] = heading
            self._sidebar_group_members[label] = []

        def add_member(group: str, item: QListWidgetItem) -> None:
            self.editor_list.addItem(item)
            item.setHidden(group in collapsed)
            self._sidebar_group_members[group].append(item)

        def add_sidebar_group(label: str, entries: list[EditorEntry]) -> None:
            if not entries:
                return
            add_heading(label)
            for application in entries:
                sidebar_name = application.name if len(application.versions) <= 1 else f"{application.name}  ({len(application.versions)} versions)"
                item = QListWidgetItem(sidebar_name)
                item.setToolTip(
                    f"Active: {application.active_version or 'Not selected'}"
                    + (f" • Desktop: {application.desktop_version}" if application.desktop_version else "")
                )
                item.setData(Qt.ItemDataRole.UserRole, self._entry_key(application))
                if application.icon and application.icon.is_file():
                    item.setIcon(QIcon(str(application.icon)))
                item.setSizeHint(QSize(0, 38))
                add_member(label, item)
                self._sidebar_application_keys.add(self._entry_key(application))

        # Store Pythoine remains a managed component for installation/version
        # lifecycle, but once installed its normal user-facing navigation is the
        # dedicated integrated Store Pythoine button rather than a duplicate
        # managed-application row in the sidebar.
        add_sidebar_group("EDITORS", [entry for entry in self.editors if entry.editor_id != "store-pythoine"])
        add_sidebar_group("READERS", [entry for entry in self.readers if entry.editor_id != "store-pythoine"])
        add_sidebar_group("EXTENSIONS", [entry for entry in self.extensions if entry.editor_id != "store-pythoine"])

        self.suite_page_index = None
        self.installed_applications_page_index = None

        if selected_root == "__catalogue__":
            self.stack.setCurrentIndex(self._ensure_catalogue_page())
        elif isinstance(selected_root, str) and selected_root.startswith("__catalog__:"):
            component_id = selected_root.split(":", 1)[1]
            installed = next((entry for entry in self.components if entry.editor_id == component_id and not is_hub(entry)), None)
            if installed is not None:
                self.stack.setCurrentIndex(self._ensure_editor_page(installed))
            else:
                profile = COMPONENT_PROFILES.get(component_id)
                self.stack.setCurrentIndex(self._ensure_catalog_component_page(profile) if profile is not None else self._ensure_catalogue_page())
        elif selected_root == "__suite__":
            self.stack.setCurrentIndex(self._ensure_suite_page())
        elif selected_root == "__installed_applications__":
            self.stack.setCurrentIndex(self._ensure_installed_applications_page())
        elif isinstance(selected_root, str) and selected_root.startswith("__versions__:"):
            history_key = selected_root.split(":", 1)[1]
            history_editor = next((entry for entry in self.components
                                   if self._entry_key(entry) == history_key), None)
            if history_editor is not None:
                preferred = selected_version if isinstance(selected_version, str) else None
                self.stack.setCurrentIndex(self._ensure_version_history_page(history_editor, preferred_version=preferred))
            else:
                profile = COMPONENT_PROFILES.get(str(selected_component_id or ""))
                self.stack.setCurrentIndex(
                    self._ensure_catalog_component_page(profile) if profile is not None else self._ensure_catalogue_page()
                )
        elif selected_root:
            editor = next((entry for entry in [*self.editors, *self.readers, *self.extensions]
                           if self._entry_key(entry) == str(selected_root)), None)
            if editor is not None:
                self.stack.setCurrentIndex(self._ensure_editor_page(editor))
            else:
                profile = COMPONENT_PROFILES.get(str(selected_component_id or ""))
                self.stack.setCurrentIndex(
                    self._ensure_catalog_component_page(profile) if profile is not None else self._ensure_catalogue_page()
                )
        else:
            last_id = self.config.get("last_selected_editor")
            editor = next((entry for entry in [*self.editors, *self.readers, *self.extensions] if entry.editor_id == last_id), None)
            if editor:
                self.stack.setCurrentIndex(self._ensure_editor_page(editor))
            else:
                self.stack.setCurrentIndex(0)

        self._sync_launcher_inventory()

    def _ensure_editor_page(self, editor: EditorEntry) -> int:
        """Create one heavy App Page on first use and cache it until refresh."""
        key = self._entry_key(editor)
        existing = self.editor_pages.get(key)
        if existing is not None:
            return existing
        page = self._editor_page(editor)
        page.setProperty("editor_root", key)
        page.setProperty("suite_component_id", editor.editor_id)
        page.setProperty("suite_editor_page", True)
        index = self.stack.addWidget(page)
        self.editor_pages[key] = index
        return index

    def _ensure_version_history_page(self, editor: EditorEntry, *, preferred_version: str | None = None) -> int:
        """Create one lightweight Version History page on first use and cache it until refresh."""
        key = self._entry_key(editor)
        existing = self.version_history_pages.get(key)
        if existing is not None:
            return existing
        page = self._version_history_page(editor, preferred_version=preferred_version)
        page.setProperty("editor_root", f"__versions__:{key}")
        page.setProperty("suite_component_id", editor.editor_id)
        page.setProperty("suite_editor_page", True)
        index = self.stack.addWidget(page)
        self.version_history_pages[key] = index
        return index

    def _ensure_catalogue_page(self) -> int:
        """Create the lightweight offline Get More catalogue on first use."""
        if self.catalogue_page_index is None:
            page = self._catalogue_page()
            page.setProperty("editor_root", "__catalogue__")
            page.setProperty("suite_editor_page", True)
            self.catalogue_page_index = self.stack.addWidget(page)
        return self.catalogue_page_index

    def _ensure_catalog_component_page(self, profile: ComponentProfile) -> int:
        """Create one canonical inactive App Page for a trusted uninstalled identity."""
        existing = self.catalog_component_pages.get(profile.component_id)
        if existing is not None:
            return existing
        page = self._catalog_component_page(profile)
        page.setProperty("editor_root", f"__catalog__:{profile.component_id}")
        page.setProperty("suite_component_id", profile.component_id)
        page.setProperty("suite_editor_page", True)
        index = self.stack.addWidget(page)
        self.catalog_component_pages[profile.component_id] = index
        return index

    def _ensure_suite_page(self) -> int:
        if self.suite_page_index is None:
            page = self._suite_details_page()
            page.setProperty("editor_root", "__suite__")
            page.setProperty("suite_editor_page", True)
            self.suite_page_index = self.stack.addWidget(page)
        return self.suite_page_index

    def _ensure_installed_applications_page(self) -> int:
        if self.installed_applications_page_index is None:
            page = self._installed_applications_page()
            page.setProperty("editor_root", "__installed_applications__")
            page.setProperty("suite_editor_page", True)
            self.installed_applications_page_index = self.stack.addWidget(page)
        return self.installed_applications_page_index

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
        provenance: str | None = None,
        built_from_runtime: str | None = None,
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
            provenance=provenance,
            built_from_runtime=built_from_runtime,
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
        if managed_path is not None and managed_path.is_file() and is_within(managed_path, self.editors_root):
            return managed_path
        if editor.installed_command:
            path = Path(editor.installed_command[0]).expanduser().resolve(strict=False)
            if path.suffix.casefold() == ".appimage" and path.is_file() and is_within(path, self.editors_root):
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
        chosen = requested_version_runtime(mode, version)
        if chosen is None:
            raise InstallError(f"Suite Pythoine {version.version} has no available {mode} runtime.")
        return chosen

    def _component_runtime_for_version(self, editor: EditorEntry, version: EditorVersionInfo) -> tuple[str, tuple[str, ...]]:
        """Resolve an ordinary component runtime without leaving the selected version."""
        mode = str(editor.launch_mode or "auto")
        chosen = requested_version_runtime(mode, version)
        if chosen is None:
            raise InstallError(f"{editor.name} {version.version} has no available {mode} runtime.")
        return chosen

    def _sync_component_appimage_sidecars(
        self, editor: EditorEntry, version: EditorVersionInfo, desktop: Path, runtime: str
    ) -> None:
        """Mirror generic component desktop ownership into AppImage sidecars."""
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

    def _synchronize_component_desktop_to_version(
        self, editor: EditorEntry, version: EditorVersionInfo
    ) -> tuple[str, Path]:
        """Point one ordinary component's desktop launcher at its preferred runtime.

        The Suite Pythoine self-integration path is deliberately separate and
        remains authoritative for the Hub itself. This helper only closes the
        long-standing generic-component gap.
        """
        if is_hub(editor):
            raise InstallError("Suite Pythoine desktop integration must use the dedicated Suite synchronization path.")
        runtime, command = self._component_runtime_for_version(editor, version)
        desktop = desktop_entry_path(editor.editor_id)
        existing_record = self._managed_record(editor, version.version)
        managed_icon = record_paths(existing_record).get("icon") if existing_record else None
        icon = select_existing_icon_path(managed_icon, version.icon, editor.icon)

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
                raise InstallError("The selected AppImage runtime is unavailable.")
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

        data = self.config.as_dict()
        set_managed_installation(data, record, set_active=True, desktop_integrated=True)
        if not set_active_version(data, editor.editor_id, version.version):
            raise InstallError("Could not record the selected active version in the remembered active selection.")
        if not set_desktop_version(data, editor.editor_id, version.version, desktop):
            raise InstallError("Could not record the selected desktop-integrated version.")
        override = self._editor_override(editor)
        override["active_version"] = version.version
        self.config.set("routing_index", {})
        return runtime, desktop

    def _desktop_runtime_owns_version(self, editor: EditorEntry, version: EditorVersionInfo, runtime: str) -> bool:
        if is_hub(editor):
            if version.version != editor.desktop_version:
                return False
            actual = desktop_entry_runtime(desktop_entry_path(editor.editor_id))
            return actual == runtime.casefold()

        # Generic components now verify the actual shared launcher rather than
        # assuming that only an AppImage can own desktop integration.
        desktop = desktop_entry_path(editor.editor_id)
        if runtime == "Portable":
            return portable_desktop_entry_status(
                editor.editor_id,
                version.portable_command,
                desktop_path=desktop,
                desktop_id=desktop_id_for(editor.editor_id),
            ) == "ready"
        if runtime == "AppImage":
            return desktop_entry_status(
                editor.editor_id,
                version.appimage_path,
                desktop_path=desktop,
                desktop_id=desktop_id_for(editor.editor_id),
            ) == "ready"
        return False

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

        if not is_hub(editor) and editor.active_version:
            version = self._version_info(editor, editor.active_version)
            if version is not None:
                try:
                    runtime, command = self._component_runtime_for_version(editor, version)
                except InstallError:
                    return "Active runtime unavailable — choose/repair a valid application runtime"
                desktop = desktop_entry_path(editor.editor_id)
                record = self._managed_record(editor, version.version)
                managed_icon = record_paths(record).get("icon") if record else None
                icon = select_existing_icon_path(managed_icon, version.icon, editor.icon)
                if runtime == "Portable":
                    status = portable_desktop_entry_status(
                        editor.editor_id, command, desktop_path=desktop,
                        desktop_id=desktop_id_for(editor.editor_id), icon_path=icon,
                    )
                else:
                    status = desktop_entry_status(
                        editor.editor_id, version.appimage_path, desktop_path=desktop,
                        desktop_id=desktop_id_for(editor.editor_id), icon_path=icon,
                    )
                return {
                    "ready": f"Ready — active {runtime} runtime owns the desktop entry",
                    "missing": f"Desktop entry missing — Repair will attach the active {runtime} runtime",
                    "stale": f"Desktop entry points to a different runtime/version — Repair available",
                    "no-portable": "Active Portable runtime unavailable",
                    "no-appimage": "Active AppImage runtime unavailable",
                }.get(status, status)

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
            "no-appimage": "AppImage runtime unavailable",
        }.get(status, status) + (" — legacy/unregistered; Repair will adopt it" if appimage is not None and not managed else "")

    def _version_safety_text(self, editor: EditorEntry) -> str:
        if editor.version_status == "match":
            return "Portable and AppImage versions match"
        if editor.version_status == "mismatch":
            return "VERSION MISMATCH — Automatic mode uses portable"
        if editor.version_status == "unverified":
            return "AppImage version unverified — Automatic mode uses Portable"
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
            app_dialog_title("AppImage Version Mismatch"),
            f"{editor.name} is explicitly configured to launch its AppImage, but it cannot be safely matched to the Portable source you just loaded.\n\n"
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

    def _bootstrap_desktop_repair(self, editor: EditorEntry) -> bool:
        """Let the user explicitly establish a repair target when no active version exists."""
        candidates = [
            item for item in editor.versions
            if not item.validation_issue and (item.has_portable or item.has_appimage)
        ]
        if not candidates:
            QMessageBox.warning(
                self, app_dialog_title("Runtime Unavailable"),
                f"{editor.name} has no validated runtime available for Desktop Integration.",
            )
            return False
        selected = candidates[0]
        if len(candidates) > 1:
            labels = [item.version for item in candidates]
            choice, accepted = QInputDialog.getItem(
                self, app_dialog_title("Select Version for Desktop Integration"),
                f"Which {editor.name} version should become active and own the desktop launcher?",
                labels, 0, False,
            )
            if not accepted:
                return False
            selected = candidates[labels.index(choice)]
        # Reuse the established Make Active runtime chooser and transaction.
        # When both runtimes exist it explicitly asks Portable vs AppImage.
        self.make_version_active(editor, selected)
        refreshed = self.suite_entry if is_hub(editor) else next(
            (entry for entry in self.components if entry.editor_id == editor.editor_id), None
        )
        return bool(refreshed is not None and refreshed.active_version == selected.version)

    def repair_component_desktop_integration(self, editor: EditorEntry, *, show_dialog: bool = True) -> bool:
        """Repair an ordinary component launcher to its active preferred runtime."""
        if is_backend_only_component(editor):
            if show_dialog:
                QMessageBox.information(
                    self, app_dialog_title("Not Applicable"),
                    "Store Pythoine is a Suite-integrated backend and intentionally has no standalone desktop launcher.",
                )
            return False
        if is_hub(editor):
            return self.repair_suite_desktop_integration(editor, show_dialog=show_dialog)
        if not sys.platform.startswith("linux"):
            if show_dialog:
                QMessageBox.information(self, app_dialog_title("Not Applicable"), "Desktop integration is a Linux feature.")
            return False
        if not editor.active_version:
            return self._bootstrap_desktop_repair(editor) if show_dialog else False
        version = self._version_info(editor, editor.active_version)
        if version is None:
            if show_dialog:
                QMessageBox.warning(self, app_dialog_title("Runtime Unavailable"), "The active application version is not present in the inventory.")
            return False

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
            runtime, desktop = self._synchronize_component_desktop_to_version(editor, version)
            if not self.config.save():
                raise InstallError("Could not save component desktop integration state.")
        except (InstallError, OSError, ValueError) as exc:
            data.clear()
            data.update(snapshot)
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
            if show_dialog:
                QMessageBox.critical(self, app_dialog_title("Repair Failed"), str(exc))
            else:
                self._status(f"Desktop integration could not follow the active {editor.name} runtime: {exc}")
            return False

        self._sync_component_appimage_sidecars(editor, version, desktop, runtime)
        self._refresh_desktop_database(desktop.parent)
        self.refresh_editors(automatic=not show_dialog)
        if show_dialog:
            QMessageBox.information(
                self, app_dialog_title("Integration Repaired"),
                f"{editor.name} desktop integration now launches {version.version} [{runtime}] directly.\n\n{desktop}",
            )
        else:
            self._status(f"Desktop integration now follows {editor.name} {version.version} [{runtime}].")
        return True

    def repair_appimage_integration(self, editor: EditorEntry) -> None:
        if not sys.platform.startswith("linux"):
            QMessageBox.information(self, app_dialog_title("Not Applicable"), "AppImage desktop integration is a Linux feature.")
            return
        appimage = self._primary_managed_appimage(editor)
        if appimage is None or not appimage.is_file():
            QMessageBox.warning(
                self,
                app_dialog_title("AppImage Not Found"),
                f"No AppImage for {editor.name} was found in the configured Applications folder:\n\n{self._installed_dir()}",
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
            # Remove obsolete override mirrors; validated filesystem assets are authoritative.
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
                    "Use Repair Desktop Integration first. Repair verifies the actual runtime and launcher. "
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
            app_dialog_title("Remove AppImage"),
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
        # Generic Details action must obey the same active-runtime and verified
        # desktop safeguards as the exact-version Remove Portable action.
        portable = self._portable_root_for(editor)
        selected = next((version for version in editor.versions
            if portable is not None and version.portable_root is not None
            and version.portable_root.resolve(strict=False) == portable.resolve(strict=False)), None)
        if selected is not None:
            self.remove_portable_runtime(editor, selected)
            return
        if portable is not None:
            QMessageBox.warning(self, app_dialog_title('Unverified Portable'),
                'This Portable source does not match an independently validated exact version. '
                'It cannot be removed through ordinary application management.')
            return
        portable_root = self._portable_root_for(editor)
        if portable_root is None:
            QMessageBox.information(
                self,
                app_dialog_title("Portable Editor Not Present"),
                f"No removable Portable runtime is present for {editor.name} in the configured Applications folder.",
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
        if portable_root is None and not managed and not any(
            item.recovery_dir is not None or (recovery_root(self.editors_root, editor.name, item.version).is_dir())
            or item.has_appimage for item in editor.versions
        ):
            QMessageBox.information(
                self,
                app_dialog_title("Nothing to Purge"),
                f"No Portable, AppImage or retained Recovery asset is present for {editor.name}.",
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
            finished_callback=lambda: None,
        )
        self._begin_managed_mutation()
        try:
            wizard.exec()
        finally:
            self._end_managed_mutation()
        self.refresh_editors()
        if wizard.progress_page.succeeded:
            self._status(f"Purged {editor.name} from Suite Pythoine.")
        elif wizard.progress_page.started and wizard.progress_page.finished:
            self._status(f"Purge of {editor.name} stopped: {wizard.progress_page.error_message}")

    def _version_info(self, editor: EditorEntry, version: str) -> EditorVersionInfo | None:
        return next((item for item in editor.versions if item.version == version), None)

    def launch_editor_version(self, editor: EditorEntry, version: EditorVersionInfo, mode: str) -> None:
        if is_backend_only_component(editor):
            self.show_store()
            return
        if version.validation_issue:
            QMessageBox.warning(self, app_dialog_title('Unverified Version'), version.validation_issue)
            return
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

    def _make_suite_version_active(self, editor: EditorEntry, version: EditorVersionInfo, prior_mode: str | None = None) -> None:
        data = self.config.as_dict()
        snapshot = copy.deepcopy(data)
        snapshot.setdefault("editor_overrides", {}).setdefault(editor.editor_id, {})["launch_mode"] = prior_mode or "auto"
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
            editor.launch_mode = prior_mode or "auto"
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

    def repair_suite_desktop_integration(self, editor: EditorEntry, *, show_dialog: bool = True) -> bool:
        if not sys.platform.startswith("linux"):
            if show_dialog:
                QMessageBox.information(self, app_dialog_title("Not Applicable"), "Desktop integration is a Linux feature.")
            return False
        if not editor.active_version:
            return self._bootstrap_desktop_repair(editor) if show_dialog else False
        version = self._version_info(editor, editor.active_version)
        if version is None:
            if show_dialog:
                QMessageBox.warning(self, app_dialog_title("Runtime Unavailable"), "The active Suite Pythoine version is not present in the application inventory.")
            return False
        data = self.config.as_dict()
        snapshot = copy.deepcopy(data)
        target = desktop_entry_path(editor.editor_id)
        existed = target.exists() or target.is_symlink()
        prior_bytes: bytes | None = None
        prior_mode: int | None = None
        if existed:
            try:
                # Do not overwrite an unreadable launcher without a rollback copy.
                if target.is_symlink() or not target.is_file():
                    raise OSError('The existing desktop entry is not a regular file.')
                prior_bytes = target.read_bytes()
                prior_mode = target.stat().st_mode
            except OSError as exc:
                if show_dialog:
                    QMessageBox.critical(self, app_dialog_title('Repair Failed'), str(exc))
                return False
        try:
            runtime, desktop = self._synchronize_suite_desktop_to_version(editor, version)
            if not self.config.save():
                raise InstallError("Could not save Suite Pythoine desktop integration state.")
        except (InstallError, OSError, ValueError) as exc:
            data.clear()
            data.update(snapshot)
            try:
                if existed and prior_bytes is not None:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(prior_bytes)
                    if prior_mode is not None:
                        target.chmod(prior_mode)
                elif not existed and (target.exists() or target.is_symlink()):
                    target.unlink()
            except OSError as rollback_error:
                exc = InstallError(f'{exc}; desktop rollback failed: {rollback_error}')
            self.config.save()
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

    def make_version_active(self, editor: EditorEntry, version: EditorVersionInfo, *, preferred_runtime: str | None = None) -> None:
        if version.validation_issue:
            QMessageBox.warning(self, app_dialog_title('Identity Mismatch'), version.validation_issue)
            return
        if not (version.has_portable or version.has_appimage):
            QMessageBox.information(
                self, app_dialog_title("Runtime Unavailable"),
                f"{editor.name} {version.version} has Recovery only. Restore Portable before making this version active.",
            )
            return
        if preferred_runtime is None and version.has_portable and version.has_appimage:
            prompt = (f'Which {editor.name} {version.version} runtime should Suite use for backend operations?'
                      if is_backend_only_component(editor) else
                      f'Which {editor.name} {version.version} runtime should own the desktop launcher?')
            label, accepted = QInputDialog.getItem(
                self, app_dialog_title('Select Active Runtime'),
                prompt,
                ['Portable', 'AppImage'], 0, False)
            if not accepted:
                return
            preferred_runtime = 'portable' if label == 'Portable' else 'installed'
        if preferred_runtime is None:
            preferred_runtime = 'portable' if version.has_portable else 'installed'
        if (preferred_runtime == 'portable' and not version.has_portable) or (
                preferred_runtime == 'installed' and not version.has_appimage):
            QMessageBox.warning(self, app_dialog_title('Runtime Unavailable'),
                                'The selected installation has no matching runtime.')
            return
        # The runtime preference is part of the rollback snapshot made below,
        # but must be set BEFORE resolving the desktop command. Preserve it on
        # successful Make Active and restore it on failure.
        prior_mode = self._editor_override(editor).get('launch_mode')
        self._editor_override(editor)['launch_mode'] = preferred_runtime
        editor.launch_mode = preferred_runtime
        if is_backend_only_component(editor):
            data = self.config.as_dict()
            snapshot = copy.deepcopy(data)
            try:
                override = self._editor_override(editor)
                override['active_version'] = version.version
                override['launch_mode'] = preferred_runtime
                managed_versions = self._managed_versions(editor)
                if version.version in managed_versions:
                    set_active_version(data, editor.editor_id, version.version)
                set_desktop_version(data, editor.editor_id, None)
                if not self.config.save():
                    raise InstallError("Could not save the active backend version.")
                if sys.platform.startswith("linux"):
                    retired = retire_managed_desktop_entry(editor.editor_id)
                    if retired is not None:
                        self._refresh_desktop_database(retired.parent)
            except (InstallError, OSError, ValueError) as exc:
                data.clear(); data.update(snapshot)
                editor.launch_mode = prior_mode or 'auto'
                self.config.save()
                QMessageBox.critical(self, app_dialog_title("Make Active Failed"), str(exc))
                return
            self.refresh_editors()
            QMessageBox.information(
                self, app_dialog_title("Active Version Changed"),
                f"{editor.name} {version.version} is now the active backend version.\n\n"
                f"Suite will use its {'Portable' if preferred_runtime == 'portable' else 'AppImage'} runtime for Store operations.",
            )
            return
        if is_hub(editor):
            self._make_suite_version_active(editor, version, prior_mode)
            return
        """Make one ordinary component version active and align its desktop launcher.

        0.3.8 retains Suite Pythoine's dedicated self-integration
        path untouched. Generic components now use the same existing verified
        Portable/AppImage writers according to their own launch preference.
        """
        data = self.config.as_dict()
        snapshot = copy.deepcopy(data)
        snapshot.setdefault("editor_overrides", {}).setdefault(editor.editor_id, {})["launch_mode"] = prior_mode or "auto"
        desktop: Path | None = None
        desktop_backup: bytes | None = None
        desktop_existed = False
        desktop_mode: int | None = None
        runtime: str | None = None

        try:
            if sys.platform.startswith("linux"):
                desktop = desktop_entry_path(editor.editor_id)
                if desktop.exists():
                    desktop_existed = True
                    desktop_backup = desktop.read_bytes()
                    desktop_mode = desktop.stat().st_mode
                runtime, desktop = self._synchronize_component_desktop_to_version(editor, version)
            else:
                group = self._managed_group(editor)
                if group and version.version in self._managed_versions(editor):
                    if not set_active_version(data, editor.editor_id, version.version):
                        raise InstallError("Could not record the selected active version in the remembered active selection.")
                override = self._editor_override(editor)
                override["active_version"] = version.version
                self.config.set("routing_index", {})

            if not self.config.save():
                raise InstallError("Could not save Suite Pythoine preferences.")

        except (InstallError, OSError, ValueError) as exc:
            data.clear()
            data.update(snapshot)
            editor.launch_mode = prior_mode or "auto"
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

        if sys.platform.startswith("linux") and runtime is not None and desktop is not None:
            self._sync_component_appimage_sidecars(editor, version, desktop, runtime)
            self._refresh_desktop_database(desktop.parent)

        self.refresh_editors()
        desktop_note = (
            f"Desktop integration now launches {version.version} [{runtime}] directly."
            if runtime else "The active version was updated."
        )
        QMessageBox.information(
            self,
            app_dialog_title("Active Version Changed"),
            f"{editor.name} {version.version} is now the active version.\n\n{desktop_note}",
        )

    def _active_runtime_for_desktop_handoff(self, editor: EditorEntry, version: EditorVersionInfo) -> tuple[str, tuple[str, ...]]:
        """Resolve the runtime the active version already uses; do not change preference."""
        if is_hub(editor):
            return self._suite_runtime_for_version(editor, version)
        selected = editor.command()
        if selected and version.portable_command and selected == version.portable_command:
            return "Portable", version.portable_command
        if selected and version.installed_command and selected == version.installed_command:
            return "AppImage", version.installed_command
        raise InstallError(
            f"The active {editor.name} {version.version} runtime is unavailable, so desktop integration cannot be transferred safely."
        )

    def _handoff_desktop_before_version_removal(
        self, editor: EditorEntry, removing: EditorVersionInfo
    ) -> tuple[str, Path]:
        """Move the existing launcher to the already-active version and verify it.

        This is intentionally removal-scoped. 0.3.5 does not change normal
        Make Active/startup behaviour; it only prevents a retained desktop owner
        from trapping an otherwise removable non-active version.
        """
        if not editor.active_version or editor.active_version == removing.version:
            raise InstallError("Choose another active version before removing the desktop-integrated version.")
        active = self._version_info(editor, editor.active_version)
        if active is None:
            raise InstallError("The active version could not be found in the managed version inventory.")
        runtime, command = self._active_runtime_for_desktop_handoff(editor, active)

        data = self.config.as_dict()
        snapshot = copy.deepcopy(data)
        desktop = desktop_entry_path(editor.editor_id)
        desktop_existed = desktop.exists()
        desktop_backup: bytes | None = None
        desktop_mode: int | None = None
        if desktop_existed:
            desktop_backup = desktop.read_bytes()
            desktop_mode = desktop.stat().st_mode

        try:
            target_record = self._managed_record(editor, active.version)
            managed_icon = record_paths(target_record).get("icon") if target_record else None
            icon = select_existing_icon_path(managed_icon, active.icon, editor.icon)
            if runtime == "Portable":
                desktop = synchronize_portable_desktop_integration(
                    editor.name,
                    editor.editor_id,
                    command,
                    icon,
                    active.portable_root or editor.root,
                    desktop_path=desktop,
                    desktop_id=desktop_id_for(editor.editor_id),
                )
            else:
                appimage = active.appimage_path
                if appimage is None or not appimage.is_file():
                    raise InstallError("The active AppImage runtime is unavailable.")
                desktop = synchronize_desktop_integration(
                    editor.name,
                    editor.editor_id,
                    appimage,
                    icon,
                    active.portable_root or editor.root,
                    desktop_path=desktop,
                    desktop_id=desktop_id_for(editor.editor_id),
                )

            # Use only ephemeral runtime information for handoff. The actual
            # verified desktop launcher, not this compatibility projection, is authoritative.
            record = dict(target_record) if target_record else {}
            record.update({
                "schema": 2,
                "editor_id": editor.editor_id,
                "application_id": editor.editor_id,
                "name": editor.name,
                "version": active.version,
                "desktop_file_path": str(desktop),
                "desktop_id": desktop_id_for(editor.editor_id),
                "icon_path": str(icon) if icon else None,
                "source_version": active.version if active.has_portable else editor.source_version,
                "extensions": list(editor.extensions),
                "description": editor.description,
                "publisher_id": editor.publisher_id,
            })
            if active.appimage_path is not None and active.appimage_path.is_file():
                appimage = active.appimage_path.expanduser().resolve(strict=False)
                record["appimage_path"] = str(appimage)
                record["appimage_sha256"] = str(record.get("appimage_sha256") or sha256_file(appimage))
            set_managed_installation(data, record, set_active=True, desktop_integrated=True)
            if not set_active_version(data, editor.editor_id, active.version):
                raise InstallError("Could not preserve the selected active version during desktop handoff.")
            if not set_desktop_version(data, editor.editor_id, active.version, desktop):
                raise InstallError("Could not record the transferred desktop integration ownership.")
            override = self._editor_override(editor)
            override["active_version"] = active.version
            if not self.config.save():
                raise InstallError("Could not save the desktop integration handoff.")
        except (InstallError, OSError, ValueError) as exc:
            data.clear()
            data.update(snapshot)
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
            if isinstance(exc, InstallError):
                raise
            raise InstallError(str(exc)) from exc

        # Sidecars are mirrors, not transaction authority. Keep an active
        # AppImage sidecar truthful when AppImage owns the launcher; when
        # Portable owns it the AppImage remains installed but not integrated.
        if active.appimage_path is not None and active.appimage_path.is_file():
            try:
                target_record = self._managed_record(editor, active.version)
                write_appimage_metadata(
                    active.appimage_path,
                    editor_id=editor.editor_id,
                    application_id=str(target_record.get("application_id") or editor.editor_id),
                    publisher_id=editor.publisher_id,
                    name=editor.name,
                    version=active.version,
                    desktop_file=desktop if runtime == "AppImage" else None,
                    desktop_id=desktop_id_for(editor.editor_id),
                    desktop_integrated=runtime == "AppImage",
                    icon=record_paths(target_record).get("icon") or active.icon or editor.icon,
                )
            except (OSError, ValueError):
                pass
        self._refresh_desktop_database(desktop.parent)
        return runtime, desktop

    def _confirm_uninstall_version(
        self, editor: EditorEntry, version: EditorVersionInfo, assets: list[str],
    ) -> bool:
        """Canonical full-size exact-version confirmation wizard."""
        wizard = QWizard(self)
        wizard.setWindowTitle(app_dialog_title("Uninstall Version"))
        wizard.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        configure_operation_window(wizard)
        wizard.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)
        icon_path = editor.icon
        if is_hub(editor) and (icon_path is None or not icon_path.is_file()):
            icon_path = APP_ICON_PATH
        pixmap = apply_operation_icon(wizard, icon_path, 128)
        if pixmap is not None:
            wizard.setPixmap(QWizard.WizardPixmap.LogoPixmap, pixmap)

        page = QWizardPage()
        page.setTitle("Uninstall Version")
        page.setSubTitle("Review the complete managed version before Suite Pythoine removes it.")
        page_layout = QVBoxLayout(page)
        page_layout.addWidget(operation_branding_header(
            editor.name, f"Version {version.version}",
            description=editor.description or "Complete managed version",
            icon_path=icon_path,
        ))
        explanation = QLabel(
            "This removes the complete managed version and every recognised asset listed below. "
            "Other versions of the application are not removed."
        )
        explanation.setWordWrap(True)
        page_layout.addWidget(explanation)
        inventory = QPlainTextEdit()
        inventory.setReadOnly(True)
        inventory.setPlainText("\n".join(assets) if assets else "No recognised managed assets were reported.")
        inventory.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        page_layout.addWidget(inventory, 1)
        warning = QLabel(
            "Retained Recovery for this version is included when present. This operation cannot be undone from this wizard."
        )
        warning.setWordWrap(True)
        page_layout.addWidget(warning)
        wizard.addPage(page)
        wizard.setButtonText(QWizard.WizardButton.FinishButton, "Uninstall Version")
        uninstall = wizard.button(QWizard.WizardButton.FinishButton)
        _style_destructive_button(uninstall)
        return wizard.exec() == QDialog.DialogCode.Accepted

    def remove_editor_version(self, editor: EditorEntry, version: EditorVersionInfo) -> None:
        """Remove one exact version by staging its entire verified directory.

        Desktop handoff is explicit. No central registry, sidecar adoption, or
        sequential deletion of runtimes; Recovery remains part of Uninstall Version.
        """
        from .storage_layout import validate_version_boundary, prune_empty_parents
        from .installation_state import desktop_selection
        root = self.editors_root.expanduser().resolve(strict=False)
        container = version_root(root, editor.name, version.version)
        if is_hub(editor) and version.version == __version__:
            QMessageBox.warning(self, app_dialog_title('Running Suite Version'),
                                'The currently running Suite version cannot remove itself.')
            return
        if version.validation_issue:
            QMessageBox.warning(self, app_dialog_title('Unverified Version'), version.validation_issue)
            return
        try:
            validate_version_boundary(container, root)
            if not container.is_dir() or container.is_symlink():
                raise InstallError('Selected version directory does not exist or is unsafe.')
            if version.version != container.name:
                raise InstallError('The selected exact version and destination folder disagree.')
        except (OSError, ValueError, InstallError) as exc:
            QMessageBox.warning(self, app_dialog_title('Unsafe Version Content'), str(exc))
            return
        assets = [f'{name}: {container / name}' for name in ('Portable', 'AppImage', 'Recovery')
                  if (container / name).exists()]
        if not self._confirm_uninstall_version(editor, version, assets):
            return
        desktop_state, desktop_version, _desktop_runtime = desktop_selection(editor.editor_id,
                                                                            {v.version: v for v in editor.versions}, root)
        owns_desktop = desktop_state == 'ready' and desktop_version == version.version
        # If an existing launcher is unrecognised, never overwrite/delete it.
        if editor.desktop_issue in {'broken', 'legacy-launcher', 'external-target'}:
            QMessageBox.warning(self, app_dialog_title('Desktop Integration Conflict'),
                                'The existing desktop launcher needs explicit repair before destructive removal.')
            return
        desktop = desktop_entry_path(editor.editor_id)
        desktop_stage = desktop.with_name('.' + desktop.name + '.remove-stage-' + uuid.uuid4().hex[:10])
        dir_stage = container.with_name('.' + container.name + '.remove-stage-' + uuid.uuid4().hex[:10])
        backup_preferences = copy.deepcopy(self.config.as_dict())
        staged_desktop = False
        staged_container = False
        handed_off = False
        try:
            if owns_desktop:
                choices = [('Remove desktop integration (leave remaining versions inactive)', None, None)]
                for other in editor.versions:
                    if other.version == version.version or other.validation_issue:
                        continue
                    if other.has_portable:
                        choices.append((f'{other.version} — Portable', other, 'portable'))
                    if other.has_appimage:
                        choices.append((f'{other.version} — AppImage', other, 'installed'))
                selection, accepted = QInputDialog.getItem(
                    self, app_dialog_title('Replace Active Installation'),
                    f'{editor.name} {version.version} currently owns desktop integration. Choose a replacement:',
                    [c[0] for c in choices], 0, False)
                if not accepted:
                    return
                _label, successor, runtime = next(c for c in choices if c[0] == selection)
                if successor is not None:
                    self.make_version_active(editor, successor, preferred_runtime=runtime)
                    # Make Active reports its own errors; independently VERIFY
                    # actual desktop handoff before touching the old files.
                    after, target, target_runtime = desktop_selection(editor.editor_id,
                        {v.version: v for v in editor.versions}, root)
                    if after != 'ready' or target != successor.version or target_runtime != runtime:
                        raise InstallError('Replacement desktop integration was not verified; version removal stopped.')
                    handed_off = True
                else:
                    if not desktop.is_file() or desktop.is_symlink():
                        raise InstallError('The previously verified desktop launcher changed before removal.')
                    os.replace(desktop, desktop_stage)
                    staged_desktop = True
            # Re-check the boundary after all user interaction, before moving.
            validate_version_boundary(container, root)
            if dir_stage.exists() or dir_stage.is_symlink():
                raise InstallError('Temporary removal destination is not free.')
            os.replace(container, dir_stage)
            staged_container = True
            overrides = self.config.as_dict().get('editor_overrides', {})
            override = overrides.get(editor.editor_id, {}) if isinstance(overrides, dict) else {}
            if isinstance(override, dict) and override.get('active_version') == version.version:
                override.pop('active_version', None)
                if not handed_off:
                    override.pop('launch_mode', None)
            self.config.set('routing_index', {})
            if not self.config.save():
                raise InstallError('Could not save preferences following version removal.')
            # The irreversible cleanup is last. If cleanup fails, stop reporting
            # completion, retain the staged directory for explicit recovery.
            shutil.rmtree(dir_stage)
            staged_container = False
            if staged_desktop:
                desktop_stage.unlink()
                staged_desktop = False
            prune_empty_parents(container.parent, root)
        except (InstallError, OSError, ValueError) as exc:
            notes = []
            if staged_container and dir_stage.exists():
                try:
                    if container.exists():
                        notes.append(f'Original location is occupied; staged files preserved at {dir_stage}')
                    else:
                        os.replace(dir_stage, container)
                except OSError as rollback_exc:
                    notes.append(f'Version rollback failed; staged files remain at {dir_stage}: {rollback_exc}')
            if staged_desktop and desktop_stage.exists():
                try:
                    os.replace(desktop_stage, desktop)
                except OSError as rollback_exc:
                    notes.append(f'Desktop rollback failed; staged launcher: {desktop_stage}: {rollback_exc}')
            if not handed_off:
                data = self.config.as_dict()
                data.clear(); data.update(backup_preferences)
                self.config.save()
            QMessageBox.critical(self, app_dialog_title('Uninstall Version Failed'),
                                 str(exc) + ('\n\n' + '\n'.join(notes) if notes else ''))
            self.refresh_editors(automatic=True)
            return
        self.refresh_editors(automatic=True)
        self._refresh_desktop_database(desktop.parent)
        QMessageBox.information(self, app_dialog_title('Version Uninstalled'),
                                f'Uninstalled {editor.name} {version.version}, including Recovery.')

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
        """Compact debug report; Versions is the sole full runtime inventory.

        Paths are reported only for the explicitly active version.  Never pick
        the first discovered AppImage or describe an inactive runtime as active.
        """
        active = self._version_info(editor, editor.active_version) if editor.active_version else None
        desktop = (desktop_entry_path(editor.editor_id)
                   if sys.platform.startswith("linux") and not is_backend_only_component(editor) else None)
        saved_mode = saved_launch_mode(self.config.as_dict(), editor.editor_id)
        pref_label = {"auto": "Automatic", "portable": "Portable", "installed": "AppImage"}[saved_mode]
        status = str(editor.desktop_issue or "missing").replace("_", " ") if desktop else "Not applicable"
        effective_runtime = ({"portable": "Portable", "appimage": "AppImage"}.get(
            editor.desktop_runtime) if editor.desktop_issue == "ready" and active
            and editor.desktop_version == editor.active_version else None)
        if effective_runtime is None and active and is_backend_only_component(editor):
            effective_runtime = ("Portable" if saved_mode == "portable" and active.has_portable
                                 else "AppImage" if saved_mode == "installed" and active.has_appimage
                                 else "Not selected / not verified")
        elif effective_runtime is None and active and editor.desktop_issue == "missing":
            # A remembered active version may be used without a desktop entry,
            # but this is not proof that a launcher exists or is integrated.
            effective_runtime = ("Portable" if saved_mode == "portable" and active.has_portable
                                 else "AppImage" if saved_mode == "installed" and active.has_appimage
                                 else "Not verified")
        lines = [
            "Identity",
            f"Component ID: {editor.editor_id}",
            f"Desktop ID: {desktop_id_for(editor.editor_id) if desktop else 'Not applicable'}",
            f"Application directory: {editor_root(self.editors_root, editor.name)}",
            "",
            "Runtime selection",
            f"Active version: {editor.active_version or 'Not selected'}",
            f"Active runtime: {effective_runtime or 'Not selected / not verified'}",
            f"Saved runtime preference: {pref_label}",
            "",
            "Desktop integration",
            f"Desktop entry: {desktop if desktop is not None else 'Not applicable'}",
            f"Validation: {status}",
            f"Desktop target version: {editor.desktop_version or 'No verified target'}",
            f"Desktop target runtime: " + ({"portable":"Portable", "appimage":"AppImage"}.get(
                editor.desktop_runtime, "No verified target") if editor.desktop_issue == "ready" else "No verified target"),
        ]
        if desktop is not None:
            if desktop.is_file() and not desktop.is_symlink():
                command = desktop_entry_exec_command(desktop)
                lines.append(f"Desktop Exec (parsed): {' '.join(command) if command else 'Missing or unreadable'}")
            elif desktop.is_symlink():
                lines.append("Desktop Exec: Not read (symbolic link)")
            else:
                lines.append("Desktop Exec: No desktop entry")
        lines.extend(("", "Active-version runtime paths"))
        if active is None:
            lines.append("None — no active version selected")
        else:
            lines.append(f"Active version: {active.version}")
            lines.append(f"Active version — Portable directory: {active.portable_root if active.has_portable else 'Not available'}")
            lines.append(f"Active version — AppImage file: {active.appimage_path if active.has_appimage else 'Not available'}")
            if active.validation_issue:
                lines.append(f"Validation warning: {active.validation_issue}")
            if active.legacy:
                lines.append("Legacy identification: verified only through compatibility metadata")
        problems = [f"{version.version}: {version.validation_issue}" for version in editor.versions if version.validation_issue]
        if problems:
            lines.extend(("", "Other validation warnings", *problems))
        return "\n".join(lines)

    def _editor_summary_text(self, editor: EditorEntry) -> str:
        """Actual state for users; counts span Versions, never an arbitrary runtime."""
        active = self._version_info(editor, editor.active_version) if editor.active_version else None
        good = [item for item in editor.versions if not item.validation_issue]
        portable_count = sum(item.has_portable for item in good)
        appimage_count = sum(item.has_appimage for item in good)
        recovery_count = sum(bool(item.recovery_dir and recovery_available(item.recovery_dir)) for item in editor.versions)
        runtime = None
        if active is not None and is_backend_only_component(editor):
            saved = saved_launch_mode(self.config.as_dict(), editor.editor_id)
            if saved == "portable" and active.has_portable:
                runtime = "Portable"
            elif saved == "installed" and active.has_appimage:
                runtime = "AppImage"
        elif active is not None and editor.desktop_issue == "ready" and editor.desktop_version == active.version:
            runtime = {"portable": "Portable", "appimage": "AppImage"}.get(editor.desktop_runtime)
        elif active is not None and editor.desktop_issue == "missing":
            saved = saved_launch_mode(self.config.as_dict(), editor.editor_id)
            if saved == "portable" and active.has_portable:
                runtime = "Portable (remembered; desktop missing)"
            elif saved == "installed" and active.has_appimage:
                runtime = "AppImage (remembered; desktop missing)"
        if is_backend_only_component(editor):
            desktop_text = "Not applicable — Suite-integrated backend"
        elif sys.platform.startswith("linux"):
            issue = str(editor.desktop_issue or "missing").casefold()
            if issue == "ready":
                desktop_text = f"Ready — {editor.desktop_version or 'Unknown'} · " + {
                    "portable": "Portable", "appimage": "AppImage"}.get(editor.desktop_runtime, "Unknown runtime")
            elif issue == "missing":
                desktop_text = "Missing — Repair available" if active is not None else "No verified active target"
            else:
                desktop_text = f"{issue.replace('_', ' ').title()} — attention required"
        else:
            desktop_text = "Not applicable"
        lines = [
            f"Active: {active.version + ' · ' + (runtime or 'runtime not verified') if active else 'Not selected'}",
            f"Versions found: {len(editor.versions)}",
            f"Runtimes: {portable_count} Portable · {appimage_count} AppImage",
            f"Desktop shortcut: {desktop_text}",
            f"Recovery: Available for {recovery_count} version{'s' if recovery_count != 1 else ''}",
        ]
        if can_open_document(editor):
            lines.append(f"Formats: {', '.join(editor.extensions) or 'Not configured'}")
        elif is_extension(editor):
            lines.append("Role: Suite extension")
        issues = [f"{v.version}: {v.validation_issue}" for v in editor.versions if v.validation_issue]
        if issues:
            lines.append("Warning — version validation: " + "; ".join(issues))
        if active is not None and active.legacy:
            lines.append("Legacy — version identified through compatibility metadata")
        return "\n".join(lines)

    def _application_overview_text(self, editor: EditorEntry) -> str:
        """Application-first App Page facts; historical inventory belongs in Version History."""
        lines: list[str] = []
        profile = profile_for_id(editor.editor_id)
        if profile is not None and profile.lifecycle == "legacy":
            lines.append("Product lifecycle: Legacy — installation, launching and routing remain supported")
        if editor.extensions:
            lines.append(f"Supported formats: {', '.join(editor.extensions)}")
        capability_labels = {
            "create": "Create",
            "open": "Open",
            "routing": "File routing",
        }
        capabilities = [capability_labels.get(value, value.replace("_", " ").title()) for value in editor.capabilities]
        if capabilities:
            lines.append("Capabilities: " + " · ".join(capabilities))
        issues = [f"{version.version}: {version.validation_issue}" for version in editor.versions if version.validation_issue]
        if issues:
            lines.append("Warning — version validation: " + "; ".join(issues))
        active = self._version_info(editor, editor.active_version) if editor.active_version else None
        if active is not None and active.legacy:
            lines.append("Legacy — current version identified through compatibility metadata")
        return "\n".join(lines)

    def _desktop_integration_summary(self, editor: EditorEntry) -> str:
        if is_backend_only_component(editor):
            return "Desktop integration: Not applicable — Store Pythoine is integrated into Suite"
        if not sys.platform.startswith("linux"):
            return "Desktop integration: Not applicable"
        issue = str(editor.desktop_issue or "missing").casefold()
        if issue == "ready":
            runtime = {"portable": "Portable", "appimage": "AppImage"}.get(editor.desktop_runtime, "Unknown runtime")
            return f"Desktop integration: Ready — {editor.desktop_version or 'Unknown'} · {runtime}"
        if issue == "missing":
            return "Desktop integration: Missing — Repair available" if editor.active_version else "Desktop integration: No verified active target"
        return f"Desktop integration: {issue.replace('_', ' ').title()} — attention required"

    def _current_version_runtime_text(self, editor: EditorEntry, version_info: EditorVersionInfo) -> str:
        if is_backend_only_component(editor):
            saved = saved_launch_mode(self.config.as_dict(), editor.editor_id)
            if saved == "portable" and version_info.has_portable:
                return "Portable"
            if saved == "installed" and version_info.has_appimage:
                return "AppImage"
            return "Not selected / not verified"
        if (editor.desktop_issue == "ready" and editor.desktop_version == version_info.version
                and editor.desktop_runtime in {"portable", "appimage"}):
            return {"portable": "Portable", "appimage": "AppImage"}[editor.desktop_runtime]
        if editor.desktop_issue == "missing":
            saved = saved_launch_mode(self.config.as_dict(), editor.editor_id)
            if saved == "portable" and version_info.has_portable:
                return "Portable (remembered; desktop missing)"
            if saved == "installed" and version_info.has_appimage:
                return "AppImage (remembered; desktop missing)"
        return "Not selected / not verified"

    def _current_version_frame(self, editor: EditorEntry, version_info: EditorVersionInfo) -> QFrame:
        return build_current_version_frame(self, editor, version_info)

    def _open_development_root(self, component_id: str, display_name: str) -> bool:
        """Open one configured Developer Intake root, prompting once when absent."""
        root = self.developer_config.app_root(component_id)
        if root is None:
            selected = QFileDialog.getExistingDirectory(
                self, app_dialog_title(f"Choose {display_name} Development Root"), str(Path.home())
            )
            if not selected:
                return False
            root = Path(selected).expanduser().resolve(strict=False)
            self.developer_config.set_app_root(component_id, root)
            if not self.developer_config.save():
                QMessageBox.critical(
                    self, app_dialog_title("Developer Mode Error"),
                    f"Could not remember the development root in {self.developer_config.path}",
                )
                return False
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.critical(self, app_dialog_title("Open Development Folder Failed"), str(exc))
            return False
        if not root.is_dir():
            QMessageBox.critical(
                self, app_dialog_title("Open Development Folder Failed"),
                f"Development root is not a folder: {root}",
            )
            return False
        result = self.launcher.open_path(root)
        return result is not False

    def _open_development_folder(self, editor: EditorEntry) -> bool:
        return self._open_development_root(editor.editor_id, editor.name)

    def _show_editor_technical_details(self, editor: EditorEntry) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(app_dialog_title(f"{editor.name} — Technical Details"))
        dialog.setMinimumSize(660, 410)
        details_layout = QVBoxLayout(dialog)
        header = QLabel(f"{editor.name} — Technical Details")
        header.setTextFormat(Qt.TextFormat.PlainText)
        header_font = header.font(); header_font.setBold(True)
        header.setFont(header_font)
        details_layout.addWidget(header)
        information = _diagnostic_canvas(dialog)
        _populate_diagnostic_canvas(information, self._editor_information_text(editor))
        information.setToolTip("Select and copy paths and diagnostic values from this view.")
        details_layout.addWidget(information)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=dialog)
        copy_button = buttons.addButton("Copy Details", QDialogButtonBox.ButtonRole.ActionRole)
        copy_button.clicked.connect(lambda _checked=False: QApplication.clipboard().setText(information.toPlainText()))
        if self.developer_config.enabled:
            development_button = buttons.addButton("Open Development Folder", QDialogButtonBox.ButtonRole.ActionRole)
            development_button.clicked.connect(lambda _checked=False: self._open_development_folder(editor))
        buttons.rejected.connect(dialog.reject)
        details_layout.addWidget(buttons)
        dialog.exec()

    def _version_management_frame(self, editor: EditorEntry, version_info: EditorVersionInfo) -> QFrame:
        return build_version_management_frame(self, editor, version_info)

    @staticmethod
    def _add_details_identity_header(layout: QVBoxLayout, name: str, kind: str, icon_path: Path | None, *, lifecycle: str = "current") -> None:
        return add_details_identity_header(layout, name, kind, icon_path, lifecycle=lifecycle, APP_ICON_PATH=APP_ICON_PATH)

    def _populate_editor_details(self, layout: QVBoxLayout, editor: EditorEntry, *, include_description: bool = True) -> None:
        return populate_editor_details(self, layout, editor, include_description=include_description, _style_destructive_button=_style_destructive_button)

    def _store_is_installed(self) -> bool:
        return any(entry.editor_id == "store-pythoine" for entry in self.components)

    def _store_component_entry(self) -> EditorEntry | None:
        return next((entry for entry in self.components if entry.editor_id == "store-pythoine"), None)

    def _reload_store_content(self) -> None:
        """Load Store's published local enrichment without importing Store code."""
        self.store_content = {}
        self.store_content_error = ""
        if not self._store_is_installed():
            return
        try:
            self.store_content = load_store_content()
        except ValueError as exc:
            self.store_content_error = str(exc)

    def _sync_store_navigation(self) -> None:
        """Switch Get More to the integrated Store identity when Store is installed."""
        store_mode = self._store_is_installed()
        icon_path = bundled_catalog_icon_path("store-pythoine") if store_mode else None
        if hasattr(self, "store_action"):
            self.store_action.setText("Store Pythoine" if store_mode else "Get More Applications…")
            self.store_action.setIcon(QIcon(str(icon_path)) if icon_path is not None else QIcon())
        if hasattr(self, "store_button"):
            self.store_button.setText("Store Pythoine" if store_mode else "Get More…")
            self.store_button.setIcon(QIcon(str(icon_path)) if icon_path is not None else QIcon())
            self.store_button.setToolTip(
                "Open Store Pythoine inside Suite." if store_mode
                else "Browse Suite's lightweight offline catalogue."
            )
        if self._sidebar_launcher is not None:
            self._sidebar_launcher.set_store_mode(store_mode, icon_path)

    def _store_catalog_profiles(self) -> tuple[ComponentProfile, ...]:
        """Trusted catalogue identities shown by the integrated Store frontend."""
        kind_order = {"editor": 0, "reader": 1, "extension": 2}
        profiles = [profile for profile in COMPONENT_PROFILES.values()
                    if profile.kind != "hub" and profile.component_id != "store-pythoine"]
        profiles.sort(key=lambda profile: (kind_order.get(profile.kind, 99), profile.name.casefold()))
        return tuple(profiles)

    def _store_enrichment(self, component_id: str) -> StoreContentEntry | None:
        if not self._store_is_installed():
            return None
        return self.store_content.get(component_id)

    @staticmethod
    def _store_entry_has_content(entry: StoreContentEntry | None) -> bool:
        return bool(entry and any((
            entry.latest_version,
            entry.release_date,
            entry.release_notes,
            entry.extended_description,
            entry.highlights,
            entry.screenshots,
            entry.download_url and entry.sha256,
            entry.release_url,
            entry.check_status,
        )))

    def _store_installed_version(self, component_id: str) -> str | None:
        component = next((entry for entry in self.components if entry.editor_id == component_id), None)
        if component is None:
            return None
        if component.active_version:
            return component.active_version
        versions = [version.version for version in component.versions if version.version]
        return max(versions, key=version_sort_key) if versions else None

    def _store_highest_installed_version(self, component_id: str) -> str | None:
        component = next((entry for entry in self.components if entry.editor_id == component_id), None)
        if component is None:
            return None
        versions = [version.version for version in component.versions if version.version]
        return max(versions, key=version_sort_key) if versions else None

    def _store_update_available(self, component_id: str, entry: StoreContentEntry | None) -> bool:
        if entry is None or not entry.latest_version or entry.check_status in {"error", "unavailable"}:
            return False
        # Update availability is about acquisition, not which already-installed
        # version happens to be active. Do not offer a download when the Store
        # version is already installed alongside an older active version.
        installed = self._store_highest_installed_version(component_id)
        return bool(installed and version_sort_key(installed) < version_sort_key(entry.latest_version))

    def _add_store_enrichment(self, layout: QVBoxLayout, component_id: str) -> bool:
        return add_store_enrichment(self, layout, component_id)

    def _publish_installed_store_content(self) -> None:
        """Ask the installed Store backend to publish its local content contract; never contacts the network."""
        store = self._store_component_entry()
        if store is None or not store.available:
            QMessageBox.information(
                self,
                app_dialog_title("Store Content Unavailable"),
                "Store Pythoine is installed but has no active runtime available to publish local content.",
            )
            return
        parts = store.command()
        if not parts:
            return
        working_directory = self._portable_root_for(store)
        command = LaunchCommand(parts[0], tuple([*parts[1:], "--publish-content"]), working_directory)
        process = QProcess(self)
        self.launcher.configure_process(process, command)
        process.start()
        if not process.waitForStarted(3000) or not process.waitForFinished(10000) or process.exitCode() != 0:
            error = bytes(process.readAllStandardError()).decode("utf-8", errors="replace").strip()
            QMessageBox.warning(
                self,
                app_dialog_title("Store Content Could Not Be Published"),
                error or "The installed Store backend did not complete its local content publication step.",
            )
            return
        self._status("Reloaded local Store Pythoine content.")
        self.refresh_editors(automatic=True)

    def _start_store_backend_operation(
        self,
        arguments: list[str],
        *,
        busy_message: str,
        failure_title: str,
        completed,
    ) -> None:
        """Run one explicit Store backend action without importing Store code.

        Normal Store browsing never calls this helper. Only a deliberate online
        refresh or package-acquisition action launches the Store process.
        """
        if self._store_backend_process is not None:
            QMessageBox.information(
                self,
                app_dialog_title("Store Operation In Progress"),
                "Another Store Pythoine operation is already in progress.",
            )
            return
        store = self._store_component_entry()
        if store is None or not store.available:
            QMessageBox.information(
                self,
                app_dialog_title("Store Pythoine Unavailable"),
                "Store Pythoine is installed but has no active runtime available for this operation.",
            )
            return
        parts = store.command()
        if not parts:
            return
        working_directory = self._portable_root_for(store)
        process = QProcess(self)
        command = LaunchCommand(parts[0], tuple([*parts[1:], *arguments]), working_directory)
        self.launcher.configure_process(process, command)
        self._store_backend_process = process

        def finished(exit_code: int, _exit_status) -> None:
            stdout = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace").strip()
            stderr = bytes(process.readAllStandardError()).decode("utf-8", errors="replace").strip()
            if self._store_backend_process is process:
                self._store_backend_process = None
            process.deleteLater()
            if exit_code != 0:
                QMessageBox.warning(
                    self,
                    app_dialog_title(failure_title),
                    stderr or stdout or "Store Pythoine did not complete the requested operation.",
                )
                self._status("Store Pythoine operation failed.")
                return
            try:
                payload = json.loads(stdout)
            except (TypeError, ValueError):
                QMessageBox.warning(
                    self,
                    app_dialog_title(failure_title),
                    "Store Pythoine returned an invalid control response.",
                )
                self._status("Store Pythoine operation returned invalid data.")
                return
            completed(payload)

        process.finished.connect(finished)
        self._status(busy_message)
        process.start()
        if not process.waitForStarted(3000):
            error = process.errorString().strip()
            self._store_backend_process = None
            process.deleteLater()
            QMessageBox.warning(
                self,
                app_dialog_title(failure_title),
                error or "Store Pythoine could not be started.",
            )
            self._status("Store Pythoine operation could not start.")

    def _refresh_store_online(self) -> None:
        """Explicitly check Suite-authorised GitHub repositories, then reload the local snapshot."""
        try:
            publish_trusted_repository_snapshot(suite_version=__version__)
        except OSError as exc:
            QMessageBox.warning(
                self,
                app_dialog_title("Store Repository Check Could Not Start"),
                f"Suite could not publish its trusted repository snapshot for Store Pythoine.\n\n{exc}",
            )
            return

        def completed(payload: object) -> None:
            checked = payload.get("checked") if isinstance(payload, dict) else None
            failed = payload.get("failed") if isinstance(payload, dict) else None
            unavailable = payload.get("unavailable") if isinstance(payload, dict) else None
            self._reload_store_content()
            if isinstance(checked, int) and isinstance(failed, int) and isinstance(unavailable, int):
                self._status(
                    f"Store repository check complete: {checked} checked, {failed} failed, {unavailable} without a supported repository."
                )
            else:
                self._status("Store repository check complete.")
            self.refresh_editors(automatic=True)

        self._start_store_backend_operation(
            ["--refresh-online"],
            busy_message="Checking authorised application repositories…",
            failure_title="Store Repository Check Failed",
            completed=completed,
        )

    def _acquire_store_component(self, profile: ComponentProfile) -> None:
        """Ask Store to download+hash one package; Suite still owns inspection/install."""
        entry = self._store_enrichment(profile.component_id)
        if entry is None or not entry.download_url or not entry.sha256:
            QMessageBox.information(
                self,
                app_dialog_title("Store Package Unavailable"),
                f"{profile.name} does not currently advertise a verified Store package.",
            )
            return
        expected_version = entry.latest_version
        expected_sha256 = entry.sha256
        expected_size = entry.package_size
        expected_type = entry.package_type

        def completed(payload: object) -> None:
            if not isinstance(payload, dict) or payload.get("status") != "verified":
                QMessageBox.warning(self, app_dialog_title("Store Download Failed"), "Store Pythoine did not return a verified package response.")
                return
            if str(payload.get("component_id") or "").strip().casefold() != profile.component_id:
                QMessageBox.warning(self, app_dialog_title("Store Package Identity Mismatch"), "Store Pythoine returned a package for a different application. No installation was started.")
                return
            path = Path(str(payload.get("path") or "")).expanduser().resolve(strict=False)
            self._install_acquired_store_package(
                profile, path, expected_version, expected_sha256, expected_size, expected_type
            )

        self._start_store_backend_operation(
            ["--download-component", profile.component_id],
            busy_message=f"Downloading and verifying {profile.name} from Store Pythoine…",
            failure_title="Store Download Failed",
            completed=completed,
        )

    def _install_acquired_store_package(
        self,
        profile: ComponentProfile,
        candidate: Path,
        expected_version: str | None,
        expected_sha256: str | None,
        expected_size: int | None,
        expected_type: str | None,
    ) -> None:
        """Independently verify Store's downloaded bytes before normal managed install."""
        if not candidate.is_file():
            QMessageBox.warning(self, app_dialog_title("Store Package Missing"), "The verified Store package is no longer available. No installation was started.")
            return
        if expected_size is not None:
            try:
                actual_size = candidate.stat().st_size
            except OSError as exc:
                QMessageBox.warning(self, app_dialog_title("Store Package Could Not Be Verified"), str(exc))
                return
            if actual_size != expected_size:
                QMessageBox.warning(
                    self,
                    app_dialog_title("Store Package Verification Failed"),
                    "The downloaded package size does not match Store metadata. No installation was started.",
                )
                return
        if expected_sha256:
            try:
                actual_sha256 = sha256_file(candidate).casefold()
            except OSError as exc:
                QMessageBox.warning(self, app_dialog_title("Store Package Could Not Be Verified"), str(exc))
                return
            if actual_sha256 != expected_sha256.casefold():
                QMessageBox.warning(
                    self,
                    app_dialog_title("Store Package Verification Failed"),
                    "The downloaded package changed after Store verification or no longer matches the advertised SHA-256. "
                    "No installation was started.",
                )
                return
        try:
            if candidate.suffix.casefold() == ".appimage":
                inspection = inspect_appimage(candidate)
                inspected_version = inspection.version
            elif candidate.suffix.casefold() == ".zip":
                inspection = inspect_editor_zip(candidate, python_executable=self.launcher.python_executable())
                inspected_version = inspection.version or inspection.builder_version
            else:
                raise InstallError("Store Pythoine may supply only a source ZIP or AppImage package.")
        except (InstallError, OSError) as exc:
            QMessageBox.critical(self, app_dialog_title("Store Package Could Not Be Inspected"), str(exc))
            return
        actual_type = "appimage" if candidate.suffix.casefold() == ".appimage" else "source-zip"
        if expected_type and actual_type != expected_type:
            QMessageBox.warning(
                self,
                app_dialog_title("Store Package Type Mismatch"),
                f"Store metadata advertises a {expected_type} package, but the downloaded artifact is {actual_type}. "
                "No installation was started.",
            )
            return
        if inspection.editor_id != profile.component_id:
            QMessageBox.warning(
                self,
                app_dialog_title("Store Package Identity Mismatch"),
                f"Store metadata requested {profile.name}, but the verified package identifies as {inspection.name}. "
                "No installation was started.",
            )
            return
        if expected_version and inspected_version and str(inspected_version) != str(expected_version):
            QMessageBox.warning(
                self,
                app_dialog_title("Store Package Version Mismatch"),
                f"Store metadata advertises version {expected_version}, but the verified package identifies as "
                f"{inspected_version}. No installation was started.",
            )
            return
        self._status(f"Verified Store package for {profile.name}. Opening Suite's managed installer…")
        if candidate.suffix.casefold() == ".appimage":
            self.install_editor_appimage(candidate)
        else:
            self.install_editor_zip(candidate, store_download=True)

    def _uninstalled_catalog_profiles(self) -> tuple[ComponentProfile, ...]:
        installed_ids = {entry.editor_id for entry in self.components}
        kind_order = {"editor": 0, "reader": 1, "extension": 2}
        profiles = [profile for profile in COMPONENT_PROFILES.values()
                    if profile.kind != "hub" and profile.component_id not in installed_ids]
        profiles.sort(key=lambda profile: (kind_order.get(profile.kind, 99), profile.name.casefold()))
        return tuple(profiles)

    @traced_operation("page_catalogue")
    def _catalogue_page(self) -> QWidget:
        return build_catalogue_page(self)

    @traced_operation("page_catalog_component")
    def _catalog_component_page(self, profile: ComponentProfile) -> QWidget:
        return build_catalog_component_page(self, profile)

    def install_catalog_component(self, profile: ComponentProfile) -> None:
        """Choose a local package and require its trusted identity to match the inactive App Page."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            app_dialog_title(f"Install {profile.name}"),
            str(Path.home()),
            "Application packages (*.zip *.AppImage *.appimage);;Source ZIP archives (*.zip);;AppImage bundles (*.AppImage *.appimage)",
        )
        if not path:
            return
        candidate = Path(path)
        try:
            if candidate.suffix.casefold() == ".appimage":
                inspection = inspect_appimage(candidate)
            else:
                inspection = inspect_editor_zip(candidate, python_executable=self.launcher.python_executable())
        except (InstallError, OSError) as exc:
            QMessageBox.critical(self, app_dialog_title("Package Could Not Be Inspected"), str(exc))
            return
        if inspection.editor_id != profile.component_id:
            QMessageBox.warning(
                self,
                app_dialog_title("Different Application Selected"),
                f"This page is for {profile.name}, but the selected package identifies as {inspection.name}. "
                "No installation was started.",
            )
            return
        if candidate.suffix.casefold() == ".appimage":
            self.install_editor_appimage(candidate)
        else:
            self.install_editor_zip(candidate)

    @traced_operation("page_application")
    def _editor_page(self, editor: EditorEntry) -> QWidget:
        return build_application_page(self, editor)

    @traced_operation("page_version_history")
    def _version_history_page(self, editor: EditorEntry, *, preferred_version: str | None = None) -> QWidget:
        return build_version_history_page(self, editor, preferred_version=preferred_version)

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
                if is_current_suite_version and (version.has_portable or version.has_appimage):
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
        # Applications root. It still belongs in the Installed Apps-style inventory
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

    def _asset_inventory_records(self, *, include_running_suite: bool = False) -> list[dict]:
        """Return exact selectable Portable/AppImage/Recovery assets.

        Recovery-only versions appear here even though they are intentionally
        absent from the normal runtime-oriented Installed Applications table.
        """
        records: list[dict] = []
        running_appimage: Path | None = None
        if self.runtime.running_as_appimage:
            raw = os.environ.get("APPIMAGE", "").strip()
            if raw:
                running_appimage = Path(raw).expanduser().resolve(strict=False)
        running_portable = self.runtime.launcher_root.expanduser().resolve(strict=False)

        for editor in self.components:
            if editor.publisher_id and editor.publisher_id != "brunonlinespace":
                continue
            for version in editor.versions:
                if version.has_portable and version.portable_root is not None:
                    location = version.portable_root.expanduser().resolve(strict=False)
                    protected = bool(
                        is_hub(editor) and not self.runtime.running_as_appimage
                        and location == running_portable
                    )
                    asset = RemovalAsset(
                        editor.editor_id, editor.name, version.version, "Portable", location,
                        portable_command=version.portable_command, protected=protected,
                        protection_reason="The currently running Hub Portable cannot remove itself." if protected else "",
                    )
                    if protected and not include_running_suite:
                        continue
                    records.append({
                        "editor": editor, "version_info": version, "component_id": editor.editor_id,
                        "name": editor.name, "version": version.version, "asset": "Portable",
                        "active": self._version_runtime_is_active(editor, version, "Portable"),
                        "desktop": self._desktop_runtime_owns_version(editor, version, "Portable"),
                        "size": _tree_size(location), "timestamp": _install_timestamp([location]),
                        "locations": [location], "protected": protected,
                        "protection_reason": asset.protection_reason, "removal_asset": asset,
                    })

                if version.has_appimage and version.appimage_path is not None:
                    location = version.appimage_path.expanduser().resolve(strict=False)
                    protected = bool(
                        is_hub(editor) and self.runtime.running_as_appimage
                        and running_appimage is not None and location == running_appimage
                    )
                    icon: Path | None = None
                    raw_icon = version.managed_record.get("icon_path") if isinstance(version.managed_record, dict) else None
                    if isinstance(raw_icon, str) and raw_icon.strip():
                        candidate = Path(raw_icon).expanduser().resolve(strict=False)
                        if candidate.parent == location.parent and candidate.is_file() and not candidate.is_symlink():
                            icon = candidate
                    if icon is None:
                        try:
                            candidates = [item for item in location.parent.glob("*-icon.*")
                                          if item.is_file() and not item.is_symlink()]
                        except OSError:
                            candidates = []
                        if len(candidates) == 1:
                            icon = candidates[0].expanduser().resolve(strict=False)
                    asset = RemovalAsset(
                        editor.editor_id, editor.name, version.version, "AppImage", location,
                        appimage_icon=icon, protected=protected,
                        protection_reason="The currently running Hub AppImage cannot remove itself." if protected else "",
                    )
                    if protected and not include_running_suite:
                        continue
                    records.append({
                        "editor": editor, "version_info": version, "component_id": editor.editor_id,
                        "name": editor.name, "version": version.version, "asset": "AppImage",
                        "active": self._version_runtime_is_active(editor, version, "AppImage"),
                        "desktop": self._desktop_runtime_owns_version(editor, version, "AppImage"),
                        "size": _tree_size(location), "timestamp": _install_timestamp([location]),
                        "locations": [location], "protected": protected,
                        "protection_reason": asset.protection_reason, "removal_asset": asset,
                    })

                recovery = version.recovery_dir or recovery_root(self.editors_root, editor.name, version.version)
                if recovery_available(recovery):
                    location = recovery.expanduser().resolve(strict=False)
                    asset = RemovalAsset(editor.editor_id, editor.name, version.version, "Recovery", location)
                    records.append({
                        "editor": editor, "version_info": version, "component_id": editor.editor_id,
                        "name": editor.name, "version": version.version, "asset": "Recovery",
                        "active": False, "desktop": False, "size": _tree_size(location),
                        "timestamp": _install_timestamp([location]), "locations": [location],
                        "protected": False, "protection_reason": "", "removal_asset": asset,
                    })
        return records

    def _commit_asset_removal_preferences(self, records: list[dict], all_assets: list[dict]) -> None:
        """Clear only Suite selections that would become invalid after removal."""
        selected_keys = {(str(r["component_id"]), str(r["version"]), str(r["asset"])) for r in records}
        selected_ids = {str(r["component_id"]) for r in records}
        data = self.config.as_dict()
        snapshot = copy.deepcopy(data)
        overrides = data.get("editor_overrides", {})
        if not isinstance(overrides, dict):
            overrides = {}
            data["editor_overrides"] = overrides
        prefs = data.get("extension_preferences", {})
        if not isinstance(prefs, dict):
            prefs = {}
            data["extension_preferences"] = prefs
        changed = False

        for component_id in selected_ids:
            component_records = [r for r in all_assets if str(r["component_id"]) == component_id]
            component_keys = {(component_id, str(r["version"]), str(r["asset"])) for r in component_records}
            runtime_records = [r for r in component_records if r["asset"] in {"Portable", "AppImage"}]
            surviving = [r for r in runtime_records
                         if (component_id, str(r["version"]), str(r["asset"])) not in selected_keys]
            selected_runtime = [r for r in records if str(r["component_id"]) == component_id
                                and r["asset"] in {"Portable", "AppImage"}]
            invalidates_active = any(bool(r.get("active")) or bool(r.get("desktop")) for r in selected_runtime)
            override = overrides.get(component_id)
            if invalidates_active and isinstance(override, dict):
                # Never silently promote a surviving runtime after a bulk removal.
                # The user may explicitly Make Active / Repair from the App Page.
                override["launch_mode"] = "auto"
                override.pop("active_version", None)
                changed = True
            removing_all_assets = bool(component_keys) and component_keys <= selected_keys
            if not surviving and (selected_runtime or removing_all_assets):
                if component_id in overrides:
                    overrides.pop(component_id, None)
                    changed = True
                for extension in list(prefs):
                    if prefs.get(extension) == component_id:
                        prefs.pop(extension, None)
                        changed = True
                if data.get("last_selected_editor") == component_id:
                    data["last_selected_editor"] = None
                    changed = True
        if not changed:
            return
        data["routing_index"] = {}
        if not self.config.save():
            data.clear()
            data.update(snapshot)
            self.config.save()
            raise InstallError("Could not save Suite preference cleanup; selected assets were restored.")

    def _remove_asset_records(self, records: list[dict], all_assets: list[dict]) -> None:
        """Review, execute and report one exact multi-asset removal transaction."""
        if not records:
            QMessageBox.information(self, app_dialog_title("Remove Assets"), "Select one or more managed assets first.")
            return
        if any(bool(record.get("protected")) for record in records):
            # Remove Assets mode filters the running Suite asset out entirely.
            # Keep this defensive check for callers/tests that bypass the table.
            QMessageBox.information(
                self, app_dialog_title("Protected Runtime"),
                "The currently running Suite asset cannot be removed from this workflow."
            )
            return

        counts = {kind: sum(1 for r in records if r["asset"] == kind)
                  for kind in ("Portable", "AppImage", "Recovery")}
        wizard = QWizard(self)
        wizard.setWindowTitle(app_dialog_title("Remove Selected Assets"))
        wizard.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        configure_operation_window(wizard)
        wizard.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)
        wizard.setOption(QWizard.WizardOption.NoBackButtonOnLastPage, True)
        pixmap = apply_operation_icon(wizard, APP_ICON_PATH, 128)
        if pixmap is not None:
            wizard.setPixmap(QWizard.WizardPixmap.LogoPixmap, pixmap)

        review = QWizardPage()
        review.setTitle("Remove Selected Assets")
        review.setSubTitle("Review the exact Portable, AppImage and Recovery assets before Suite Pythoine changes anything.")
        review.setCommitPage(True)
        review_layout = QVBoxLayout(review)
        review_layout.addWidget(operation_branding_header(
            APP_NAME, "Managed application assets",
            description="Only the checked assets from Installed Applications are included.",
            icon_path=APP_ICON_PATH,
        ))
        summary = QLabel(
            f"{len(records)} selected asset{'s' if len(records) != 1 else ''}: "
            f"{counts['Portable']} Portable, {counts['AppImage']} AppImage, {counts['Recovery']} Recovery."
        )
        summary.setWordWrap(True)
        review_layout.addWidget(summary)
        details = QPlainTextEdit()
        details.setReadOnly(True)
        details.setPlainText("\n".join(
            f"{r['name']} {r['version']} — {r['asset']}\n  {r['locations'][0]}" for r in records
        ))
        details.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        review_layout.addWidget(details, 1)
        note = QLabel(
            "If a selected runnable asset owns the verified desktop launcher, that launcher is removed with it; "
            "Suite does not silently activate another asset. The currently running Suite asset is filtered out of "
            "Remove Assets mode and cannot be selected."
        )
        note.setWordWrap(True)
        review_layout.addWidget(note)

        result_page = QWizardPage()
        result_page.setTitle("Removal result")
        result_page.setSubTitle("Suite Pythoine reports the completed transaction before this wizard closes.")
        result_layout = QVBoxLayout(result_page)
        result_layout.addWidget(operation_branding_header(
            APP_NAME, "Managed application assets",
            description="Removal result", icon_path=APP_ICON_PATH,
        ))
        result_heading = QLabel("Waiting to remove selected assets…")
        result_font = result_heading.font(); result_font.setBold(True); result_font.setPointSize(max(result_font.pointSize() + 2, 12))
        result_heading.setFont(result_font)
        result_heading.setWordWrap(True)
        result_layout.addWidget(result_heading)
        result_report = QPlainTextEdit()
        result_report.setReadOnly(True)
        result_report.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        result_layout.addWidget(result_report, 1)

        review_id = wizard.addPage(review)
        result_id = wizard.addPage(result_page)
        wizard.setStartId(review_id)
        wizard.setButtonText(QWizard.WizardButton.NextButton, "Continue")
        wizard.setButtonText(QWizard.WizardButton.CommitButton, "Remove Selected…")
        wizard.setButtonText(QWizard.WizardButton.FinishButton, "Close")
        remove_button = wizard.button(QWizard.WizardButton.CommitButton)
        _style_destructive_button(remove_button)

        state = {"executed": False, "success": False, "refresh_desktop": False, "message": ""}

        def perform_removal() -> None:
            if state["executed"]:
                return
            state["executed"] = True
            wizard.button(QWizard.WizardButton.BackButton).setEnabled(False)
            wizard.button(QWizard.WizardButton.CancelButton).setEnabled(False)
            finish = wizard.button(QWizard.WizardButton.FinishButton)
            finish.setEnabled(False)
            result_heading.setText("Removing selected assets…")
            result_report.setPlainText("The reviewed transaction is in progress.")
            QApplication.processEvents()
            try:
                result = remove_assets(
                    [record["removal_asset"] for record in records],
                    editors_root=self.editors_root,
                    pre_finalize=lambda: self._commit_asset_removal_preferences(records, all_assets),
                )
                state["success"] = True
                state["refresh_desktop"] = bool(result.desktop_components)
                removed_counts = {kind: sum(1 for asset in result.removed_assets if asset.asset_type == kind)
                                  for kind in ("Portable", "AppImage", "Recovery")}
                lines = [
                    "Completed successfully.",
                    "",
                    f"Removed: {len(result.removed_assets)} assets",
                    f"  Portable: {removed_counts['Portable']}",
                    f"  AppImage: {removed_counts['AppImage']}",
                    f"  Recovery: {removed_counts['Recovery']}",
                ]
                affected = sorted({f"{asset.name} {asset.version}" for asset in result.removed_assets})
                if affected:
                    lines.extend(["", "Affected application versions:", *[f"  {item}" for item in affected]])
                if result.pruned_directories:
                    lines.extend(["", "Empty managed directories pruned:",
                                  *[f"  {path}" for path in result.pruned_directories]])
                else:
                    lines.extend(["", "Empty managed directories pruned: none"])
                result_heading.setText("Completed successfully")
                result_report.setPlainText("\n".join(lines))
                state["message"] = (
                    f"Removed {len(result.removed_assets)} selected managed "
                    f"asset{'s' if len(result.removed_assets) != 1 else ''}."
                )
            except (InstallError, OSError, ValueError) as exc:
                partial = isinstance(exc, AssetRemovalFailure) and exc.partial
                result_heading.setText("Completed with issues" if partial else "Removal failed")
                lines = [str(exc)]
                rollback_status = getattr(exc, "rollback_status", "No selected asset was reported as finalized.")
                lines.extend(["", f"Transaction status: {rollback_status}"])
                lines.extend(["", "Reviewed assets:", *[
                    f"  {r['name']} {r['version']} — {r['asset']}" for r in records
                ]])
                result_report.setPlainText("\n".join(lines))
                state["message"] = "Asset removal completed with issues." if partial else "Asset removal failed."
            finally:
                finish.setEnabled(True)
                finish.setFocus()

        def page_changed(page_id: int) -> None:
            if page_id == result_id and not state["executed"]:
                QTimer.singleShot(0, perform_removal)

        wizard.currentIdChanged.connect(page_changed)
        wizard.exec()
        if state["executed"]:
            if state["refresh_desktop"]:
                self._refresh_desktop_database()
            self.refresh_editors(automatic=True)
            if state["message"]:
                self._status(str(state["message"]))

    def _prune_editor(self, editor: EditorEntry) -> None:
        """Developer Mode Prune presets, executed by the shared asset-removal engine."""
        if not self.developer_config.enabled:
            QMessageBox.information(
                self, app_dialog_title("Developer Mode Required"),
                "Prune is available only in Developer Mode (F12)."
            )
            return

        asset_records = self._asset_inventory_records()
        all_asset_records = self._asset_inventory_records(include_running_suite=True)
        has_other_apps = any(
            str(record.get("component_id")) not in {editor.editor_id, "suite-pythoine"}
            for record in asset_records
        )
        has_other_versions = bool(editor.active_version) and any(
            str(record.get("component_id")) == editor.editor_id
            and str(record.get("version")) != str(editor.active_version)
            for record in asset_records
        )
        if not has_other_apps and not has_other_versions:
            QMessageBox.information(
                self, app_dialog_title("Nothing to Prune"),
                "There are no eligible managed assets outside the scopes this application already keeps."
            )
            return

        icon_path = editor.icon if editor.icon is not None and editor.icon.is_file() else APP_ICON_PATH
        wizard = QWizard(self)
        wizard.setWindowTitle(app_dialog_title(f"{editor.name} — Prune"))
        wizard.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        configure_operation_window(wizard)
        wizard.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)
        wizard.setOption(QWizard.WizardOption.NoBackButtonOnLastPage, True)
        pixmap = apply_operation_icon(wizard, icon_path, 128)
        if pixmap is not None:
            wizard.setPixmap(QWizard.WizardPixmap.LogoPixmap, pixmap)

        scope = PruneScopePage(
            editor, icon_path=icon_path, has_other_apps=has_other_apps, has_other_versions=has_other_versions
        )

        review = QWizardPage()
        review.setTitle("Review Prune")
        review.setSubTitle("Review the exact managed assets selected by the Developer Mode prune scopes.")
        review.setCommitPage(True)
        review_layout = QVBoxLayout(review)
        review_layout.addWidget(operation_branding_header(
            editor.name, "Developer Mode · Prune",
            description="Only the exact assets listed below will be passed to the shared removal engine.",
            icon_path=icon_path,
        ))
        scope_summary = QLabel()
        scope_summary.setWordWrap(True)
        review_layout.addWidget(scope_summary)
        review_inventory = QPlainTextEdit()
        review_inventory.setReadOnly(True)
        review_inventory.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        review_layout.addWidget(review_inventory, 1)
        review_note = QLabel(
            "The currently executing Suite Pythoine asset is never included. Prune does not remove application preferences; "
            "it removes only the reviewed Portable, AppImage and Recovery assets."
        )
        review_note.setWordWrap(True)
        review_layout.addWidget(review_note)

        result_page = QWizardPage()
        result_page.setTitle("Prune result")
        result_page.setSubTitle("Suite Pythoine reports the completed Developer Mode prune transaction before this wizard closes.")
        result_layout = QVBoxLayout(result_page)
        result_layout.addWidget(operation_branding_header(
            editor.name, "Developer Mode · Prune", description="Prune result", icon_path=icon_path
        ))
        result_heading = QLabel("Waiting to prune managed assets…")
        result_font = result_heading.font()
        result_font.setBold(True)
        result_font.setPointSize(max(result_font.pointSize() + 2, 12))
        result_heading.setFont(result_font)
        result_heading.setWordWrap(True)
        result_layout.addWidget(result_heading)
        result_report = QPlainTextEdit()
        result_report.setReadOnly(True)
        result_report.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        result_layout.addWidget(result_report, 1)

        scope_id = wizard.addPage(scope)
        review_id = wizard.addPage(review)
        result_id = wizard.addPage(result_page)
        wizard.setStartId(scope_id)
        wizard.setButtonText(QWizard.WizardButton.NextButton, "Review")
        wizard.setButtonText(QWizard.WizardButton.CommitButton, "Prune…")
        wizard.setButtonText(QWizard.WizardButton.FinishButton, "Close")
        _style_destructive_button(wizard.button(QWizard.WizardButton.CommitButton))

        state: dict[str, object] = {
            "records": [], "executed": False, "refresh_desktop": False, "message": ""
        }

        def selected_records() -> list[dict]:
            return select_prune_records(
                asset_records,
                current_component_id=editor.editor_id,
                active_version=editor.active_version,
                prune_to_this_app=scope.prune_this_app.isChecked(),
                keep_this_recovery=scope.keep_this_recovery.isChecked(),
                prune_to_active_version=scope.prune_active_version.isChecked(),
                keep_active_recovery=scope.keep_active_recovery.isChecked(),
            )

        def populate_review() -> None:
            records = selected_records()
            state["records"] = records
            summaries: list[str] = []
            if scope.prune_this_app.isChecked():
                summaries.append(
                    "Prune to This App — " + (
                        "keep Recovery files" if scope.keep_this_recovery.isChecked() else "remove Recovery files"
                    )
                )
            if scope.prune_active_version.isChecked():
                summaries.append(
                    "Prune to Active Version — " + (
                        "keep Recovery files" if scope.keep_active_recovery.isChecked() else "remove Recovery files"
                    )
                )
            counts = {kind: sum(1 for record in records if record.get("asset") == kind)
                      for kind in ("Portable", "AppImage", "Recovery")}
            scope_summary.setText(
                "Selected scopes: " + "; ".join(summaries) + "\n"
                f"Proposed removal: {len(records)} asset{'s' if len(records) != 1 else ''} — "
                f"{counts['Portable']} Portable, {counts['AppImage']} AppImage, {counts['Recovery']} Recovery."
            )
            if records:
                review_inventory.setPlainText("\n".join(
                    f"{record['name']} {record['version']} — {record['asset']}\n  {record['locations'][0]}"
                    for record in records
                ))
            else:
                review_inventory.setPlainText(
                    "No managed assets match these prune options. Go Back and change the selected scope or Recovery retention."
                )
            wizard.button(QWizard.WizardButton.CommitButton).setEnabled(bool(records))

        def perform_prune() -> None:
            if bool(state["executed"]):
                return
            records = list(state.get("records") or [])
            if not records:
                result_heading.setText("Nothing to prune")
                result_report.setPlainText("No managed assets were selected by the reviewed prune options.")
                return
            state["executed"] = True
            wizard.button(QWizard.WizardButton.BackButton).setEnabled(False)
            wizard.button(QWizard.WizardButton.CancelButton).setEnabled(False)
            finish = wizard.button(QWizard.WizardButton.FinishButton)
            finish.setEnabled(False)
            result_heading.setText("Pruning managed assets…")
            result_report.setPlainText("The reviewed prune transaction is in progress.")
            QApplication.processEvents()
            try:
                result = remove_assets(
                    [record["removal_asset"] for record in records],
                    editors_root=self.editors_root,
                    pre_finalize=lambda: self._commit_asset_removal_preferences(records, all_asset_records),
                )
                state["refresh_desktop"] = bool(result.desktop_components)
                removed_counts = {kind: sum(1 for asset in result.removed_assets if asset.asset_type == kind)
                                  for kind in ("Portable", "AppImage", "Recovery")}
                lines = [
                    "Completed successfully.", "",
                    f"Removed: {len(result.removed_assets)} assets",
                    f"  Portable: {removed_counts['Portable']}",
                    f"  AppImage: {removed_counts['AppImage']}",
                    f"  Recovery: {removed_counts['Recovery']}",
                ]
                affected = sorted({f"{asset.name} {asset.version}" for asset in result.removed_assets})
                if affected:
                    lines.extend(["", "Affected application versions:", *[f"  {item}" for item in affected]])
                if result.pruned_directories:
                    lines.extend(["", "Empty managed directories pruned:",
                                  *[f"  {path}" for path in result.pruned_directories]])
                else:
                    lines.extend(["", "Empty managed directories pruned: none"])
                result_heading.setText("Completed successfully")
                result_report.setPlainText("\n".join(lines))
                state["message"] = f"Pruned {len(result.removed_assets)} managed asset{'s' if len(result.removed_assets) != 1 else ''}."
            except (InstallError, OSError, ValueError) as exc:
                partial = isinstance(exc, AssetRemovalFailure) and exc.partial
                result_heading.setText("Completed with issues" if partial else "Prune failed")
                rollback_status = getattr(exc, "rollback_status", "No selected asset was reported as finalized.")
                lines = [str(exc), "", f"Transaction status: {rollback_status}", "", "Reviewed assets:",
                         *[f"  {record['name']} {record['version']} — {record['asset']}" for record in records]]
                result_report.setPlainText("\n".join(lines))
                state["message"] = "Prune completed with issues." if partial else "Prune failed."
            finally:
                finish.setEnabled(True)
                finish.setFocus()

        def page_changed(page_id: int) -> None:
            if page_id == review_id:
                populate_review()
            elif page_id == result_id and not bool(state["executed"]):
                QTimer.singleShot(0, perform_prune)

        wizard.currentIdChanged.connect(page_changed)
        wizard.exec()
        if bool(state["executed"]):
            if bool(state["refresh_desktop"]):
                self._refresh_desktop_database()
            self.refresh_editors(automatic=True)
            if state["message"]:
                self._status(str(state["message"]))

    def _inventory_launch_runtime(self, record: dict) -> None:
        """Launch exactly the runtime represented by one Installed Applications row."""
        editor = record.get("editor")
        version = record.get("version_info")
        runtime = str(record.get("runtime") or record.get("asset") or "")
        if not isinstance(editor, EditorEntry):
            return
        if is_backend_only_component(editor):
            self.show_store()
            return
        if isinstance(version, EditorVersionInfo):
            if runtime == "Portable":
                self.launch_editor_version(editor, version, "portable")
                return
            if runtime == "AppImage":
                self.launch_editor_version(editor, version, "appimage")
                return
        # The current unmanaged/running Hub row has no EditorVersionInfo. Its
        # canonical command is still launchable through the normal Hub entry.
        self.launch_editor(editor)

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

    def _reconcile_direct_built_appimage_desktop(
        self, editor: EditorEntry, version: EditorVersionInfo, before_command: tuple[str, ...] | None
    ) -> tuple[str | None, Path | None, bool]:
        """Developer builds do not create or silently retarget desktop launchers."""
        return None, None, False

    def _finalize_direct_built_appimage_desktop(
        self, editor: EditorEntry, version: EditorVersionInfo, runtime: str | None,
        desktop: Path | None, changed: bool
    ) -> None:
        """Mirror committed direct-build desktop ownership into sidecars/database."""
        if runtime is None or desktop is None or not desktop.is_file():
            return
        if is_hub(editor):
            self._sync_suite_appimage_sidecars(editor, version, desktop, runtime)
        else:
            self._sync_component_appimage_sidecars(editor, version, desktop, runtime)
        if changed:
            self._refresh_desktop_database(desktop.parent)

    def build_appimage_from_portable(self, editor: EditorEntry, version: EditorVersionInfo) -> None:
        """Build/rebuild one exact managed AppImage from its managed Portable."""
        if not self.developer_config.enabled:
            QMessageBox.information(self, app_dialog_title('Developer Mode Required'),
                                    'AppImage Build/Rebuild is available only in Developer Mode (F12).')
            return
        if version.validation_issue:
            QMessageBox.warning(self, app_dialog_title('Unverified Version'), version.validation_issue)
            return
        if not sys.platform.startswith("linux"):
            QMessageBox.information(self, app_dialog_title("AppImage Not Supported"), "Managed AppImage building is available only on Linux.")
            return
        if is_hub(editor) and version.version == __version__ and self.runtime.running_as_appimage and version.has_appimage and version.managed_record:
            QMessageBox.information(
                self, app_dialog_title("Running AppImage"),
                "The currently running Suite Pythoine AppImage cannot rebuild itself. Launch the Portable runtime or another Suite version first."
            )
            return
        if not version.has_portable or version.portable_root is None:
            QMessageBox.information(self, app_dialog_title("Portable Source Unavailable"), f"{editor.name} {version.version} has no buildable Portable source.")
            return
        builder = find_appimage_build_script(version.portable_root)
        if builder is None:
            QMessageBox.information(
                self, app_dialog_title("AppImage Builder Not Found"),
                f"No supported AppImage builder was found inside {editor.name} {version.version} Portable."
            )
            return

        self._close_about_dialog()
        try:
            wizard = ManagedAppImageBuildWizard(
                self, editor, version,
                editors_root=self.editors_root,
                installed_dir=self._installed_dir(),
                config=self.config,
                launcher=self.launcher,
                register_callback=self._register_managed_installation,
                reconcile_callback=self._reconcile_direct_built_appimage_desktop,
                finalize_desktop_callback=self._finalize_direct_built_appimage_desktop,
                refresh_desktop_callback=self._refresh_desktop_database,
                finished_callback=lambda: None,
            )
        except (InstallError, OSError, ValueError) as exc:
            QMessageBox.critical(self, app_dialog_title("Build AppImage Failed"), str(exc))
            return
        wizard.exec()
        self.refresh_editors(automatic=True)
        if wizard.succeeded:
            verb = "Rebuilt" if wizard.rebuild else "Built"
            self._status(f"{verb} managed AppImage for {editor.name} {version.version} from its exact Portable source.")
        elif wizard.started and wizard.finished:
            self._status(f"AppImage build for {editor.name} {version.version} stopped: {wizard.error_message}")

    def restore_portable_from_recovery_action(self, editor: EditorEntry, version: EditorVersionInfo) -> None:
        """Restore one exact Portable from its retained managed Recovery archive."""
        recovery_dir = version.recovery_dir or recovery_root(self.editors_root, editor.name, version.version)
        if not recovery_available(recovery_dir):
            QMessageBox.information(
                self,
                app_dialog_title("Recovery Unavailable"),
                f"No managed Recovery archive is available for {editor.name} {version.version}.",
            )
            return
        running_suite_portable = bool(
            is_hub(editor) and version.version == __version__ and not self.runtime.running_as_appimage
        )
        # The discovered Recovery folder is the exact version's location even
        # if an older retained version has a different historical display name.
        target = recovery_dir.parent / "Portable"
        try:
            checksum_override = False
            try:
                info, inspection = validate_recovery_archive(
                    recovery_dir,
                    expected_editor_id=editor.editor_id,
                    expected_version=version.version,
                    python_executable=self.launcher.python_executable(),
                )
            except InstallError as checksum_error:
                if 'no longer matches its recorded SHA-256' not in str(checksum_error):
                    raise
                answer = QMessageBox.warning(self, app_dialog_title('Recovery Integrity Warning'),
                    f'{checksum_error}\n\nThe retained ZIP has changed. Override the recorded checksum? '
                    'Archive safety and exact identity/version validation remain mandatory; the original checksum will not be rewritten.',
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No)
                if answer != QMessageBox.StandardButton.Yes:
                    return
                checksum_override = True
                info, inspection = validate_recovery_archive(
                    recovery_dir, expected_editor_id=editor.editor_id,
                    expected_version=version.version,
                    python_executable=self.launcher.python_executable(), allow_checksum_mismatch=True)
            wizard_class = HubSelfRestoreWizard if running_suite_portable else RecoveryRestoreWizard
            wizard = wizard_class(
                self,
                inspection,
                info,
                target,
                editors_root=self.editors_root,
                installed_dir=self._installed_dir(),
                config=self.config,
                launcher=self.launcher,
                allow_checksum_mismatch=checksum_override,
            )
        except (InstallError, OSError, ValueError) as exc:
            QMessageBox.critical(self, app_dialog_title("Restore Portable Failed"), str(exc))
            return
        wizard.exec()
        if running_suite_portable:
            if getattr(wizard, "handoff_ready", False):
                self._begin_post_exit_shutdown(preserve_reviewed_preferences=False)
            return
        if wizard.succeeded:
            self.refresh_editors(automatic=True)
            self._status(f"Restored Portable runtime for {editor.name} {version.version} from managed Recovery.")
            active_other = bool(editor.active_version and
                (editor.active_version != version.version or editor.desktop_runtime == 'appimage'))
            choice = QMessageBox.question(self, app_dialog_title('Activate Restored Portable?'),
                'Portable restoration succeeded. Make the restored Portable active and desktop-integrated? '
                + ('The working current desktop runtime will remain unchanged if you decline.' if active_other else
                   'Declining leaves desktop integration unchanged.'),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if choice == QMessageBox.StandardButton.Yes:
                refreshed = next((e for e in self.components if e.editor_id == editor.editor_id), None)
                selected = self._version_info(refreshed, version.version) if refreshed else None
                if selected is not None:
                    self._editor_override(refreshed)['launch_mode'] = 'portable'
                    self.make_version_active(refreshed, selected)

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
            QMessageBox.information(self, app_dialog_title("Active AppImage Runtime"), "Choose another active runtime before removing this AppImage runtime.")
            return
        if self._desktop_runtime_owns_version(editor, version, "AppImage"):
            QMessageBox.information(self, app_dialog_title("Desktop-Integrated Runtime"), "Make another runtime active before removing this desktop-integrated AppImage runtime.")
            return
        if is_hub(editor) and version.version == __version__ and self.runtime.running_as_appimage:
            QMessageBox.information(self, app_dialog_title("Running Runtime"), "The currently running Suite Pythoine AppImage cannot remove itself.")
            return
        reply = QMessageBox.warning(self, app_dialog_title("Remove AppImage"), f"Remove the AppImage runtime for {editor.name} {version.version}?\n\n{version.appimage_path}\n\nThe Portable runtime, if present, will be preserved.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
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
            QMessageBox.critical(self, app_dialog_title("Remove AppImage Failed"), str(exc)); return
        self.refresh_editors(); self._status(f"Removed AppImage runtime for {editor.name} {version.version}.")

    @staticmethod
    def _inventory_column_labels() -> list[str]:
        # "Asset" is deliberately scoped to Installed Applications: Portable and
        # AppImage are the normal rows, while Recovery joins the same table only
        # during Remove Assets mode. Other Suite UI keeps its existing runtime
        # terminology.
        return [
            "Application", "Version", "Asset", "Active", "Size",
            "Install date", "Location", "Quick actions",
        ]

    def _inventory_layout_state(self) -> dict:
        state = self.config.get("installed_apps_table_layout", {})
        if not isinstance(state, dict):
            return {}
        # Preserve historical user layout while the Installed Applications-only
        # label evolves from Installed as -> Runtime -> Asset.
        migrated = copy.deepcopy(state)
        aliases = {"Installed as": "Asset", "Runtime": "Asset"}
        order = migrated.get("order")
        if isinstance(order, list):
            normalised: list[str] = []
            for item in order:
                label = aliases.get(str(item), str(item))
                if label not in normalised:
                    normalised.append(label)
            migrated["order"] = normalised
        widths = migrated.get("widths")
        if isinstance(widths, dict):
            for old_label in ("Installed as", "Runtime"):
                if old_label in widths and "Asset" not in widths:
                    widths["Asset"] = widths[old_label]
                widths.pop(old_label, None)
        hidden = migrated.get("hidden")
        if isinstance(hidden, list):
            normalised_hidden: list[str] = []
            for item in hidden:
                label = aliases.get(str(item), str(item))
                if label not in normalised_hidden:
                    normalised_hidden.append(label)
            migrated["hidden"] = normalised_hidden
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
            if table.columnCount() > 6:
                table.setColumnWidth(6, min(max(table.columnWidth(6), 240), 360))
            if table.columnCount() > 7:
                table.setColumnWidth(7, max(table.columnWidth(7), 170))

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

    @traced_operation("page_suite_details")
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
                f"Applications folder: {self.editors_root}\n"
                f"Normal preferences: {self.runtime.config_path}"
            )
            information.setTextFormat(Qt.TextFormat.PlainText)
            information.setWordWrap(True)
            information.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(information)
        layout.addStretch(1)
        return page

    def _show_installed_applications_guidance(self) -> None:
        """Structured guidance for the Installed Applications table and Remove Assets mode."""
        dialog = QDialog(self)
        dialog.setWindowTitle(app_dialog_title("Installed Applications — Detailed Guidance"))
        dialog.setMinimumSize(680, 460)
        layout = QVBoxLayout(dialog)
        header = QLabel("Installed Applications — Detailed Guidance")
        header.setTextFormat(Qt.TextFormat.PlainText)
        header_font = header.font(); header_font.setBold(True)
        header.setFont(header_font)
        layout.addWidget(header)
        guidance = _diagnostic_canvas(dialog)
        guidance.setToolTip("Select and copy guidance from this view.")
        guidance.document().setDefaultStyleSheet(
            "body, p { color: #dcdcdc; } "
            "h1, h2, h3, h4, strong { color: #9cdcfe; } "
            "a { color: #9cdcfe; }"
        )
        guidance.setHtml(
            "<h3>Table controls</h3>"
            "<p>Click a heading to sort. Drag headings to reorder them, drag separators to resize columns, "
            "or right-click a heading to choose which normal columns are visible.</p>"
            "<h3>Rows and dates</h3>"
            "<p>Portable and AppImage assets normally have their own rows. The Install date uses the managed "
            "version/asset folder timestamp where an explicit install timestamp is not available. The Active "
            "column identifies the runnable asset Suite currently prefers for that application.</p>"
            "<h3>Quick actions</h3>"
            "<p>Launch opens the exact runnable asset represented by that row. App Page opens the application page. "
            "Build, repair and individual runtime-removal controls remain on the App Page. Recovery rows have no "
            "Launch action because a Recovery archive is not runnable.</p>"
            "<h3>Remove Assets</h3>"
            "<p>Remove Assets keeps this same table, adds a checkbox column at the far left, and makes Recovery assets "
            "visible. You may select Portable, AppImage and Recovery assets across applications and versions. The "
            "currently running Suite Pythoine asset is filtered out of this mode entirely; other Suite assets remain "
            "available where safe. Removing every visible asset for a version can allow now-empty managed directories "
            "to be pruned, but the operation remains exact asset removal rather than Uninstall Version or Purge.</p>"
            "<p>Remove Selected opens a reviewed, branded removal wizard and always reports success, partial completion "
            "or failure before it closes.</p>"
        )
        layout.addWidget(guidance, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=dialog)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    @traced_operation("page_installed_applications")
    def _installed_applications_page(self) -> QWidget:
        return build_installed_applications_page(
            self, APP_ICON_PATH=APP_ICON_PATH, _style_destructive_button=_style_destructive_button
        )


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
                if target == "catalogue":
                    self.show_store()
                    return
                if target.startswith("catalog:"):
                    component_id = target.split(":", 1)[1]
                    profile = COMPONENT_PROFILES.get(component_id)
                    if profile is not None:
                        self.show_catalog_component(profile)
                        return
                if target.startswith("versions:"):
                    component_id = target.split(":", 1)[1]
                    editor = next((entry for entry in self.components if entry.editor_id == component_id), None)
                    if editor is not None:
                        self.show_version_history(editor)
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
        self._record_navigation("suite")
        self.stack.setCurrentIndex(self._ensure_suite_page())
        current = self.editor_list.currentItem()
        if current is None or current.data(Qt.ItemDataRole.UserRole) != "__suite__":
            self.editor_list.clearSelection()
        self.config.set("last_selected_editor", None)

    def show_installed_applications(self) -> None:
        self._record_navigation("installed-applications")
        self.stack.setCurrentIndex(self._ensure_installed_applications_page())
        current = self.editor_list.currentItem()
        if current is None or current.data(Qt.ItemDataRole.UserRole) != "__installed_applications__":
            self.editor_list.clearSelection()
        self.config.set("last_selected_editor", None)

    def _navigate_sidebar_application(self, direction: int) -> None:
        """Move to the previous/next visible application in current sidebar order."""
        step = -1 if direction < 0 else 1
        applications: list[QListWidgetItem] = []
        for row in range(self.editor_list.count()):
            item = self.editor_list.item(row)
            if item is None or item.isHidden():
                continue
            key = item.data(Qt.ItemDataRole.UserRole)
            if key in self._sidebar_application_keys:
                applications.append(item)
        if not applications:
            return
        current = self.editor_list.currentItem()
        if current not in applications:
            target = applications[-1] if step < 0 else applications[0]
        else:
            index = applications.index(current) + step
            if index < 0 or index >= len(applications):
                return
            target = applications[index]
        if self.editor_list.currentItem() is not target:
            self.editor_list.setCurrentItem(target)
        else:
            self._sidebar_activated(target)

    def _sidebar_clicked(self, item: QListWidgetItem) -> None:
        if item is None:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(key, str) and key.startswith("__group__:"):
            label = key.split(":", 1)[1]
            collapsed = self._collapsed_sidebar_groups
            if label in collapsed:
                collapsed.remove(label)
            else:
                collapsed.add(label)
            header = self._sidebar_group_headers.get(label)
            if header is not None:
                header.setText(("▸ " if label in collapsed else "▾ ") + label)
            for member in self._sidebar_group_members.get(label, ()):
                member.setHidden(label in collapsed)
            # Group headings are disclosure controls, not page destinations.
            self.editor_list.clearSelection()
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        if key in self._sidebar_application_keys and self.stack.currentWidget() is not None \
                and self.stack.currentWidget().property("editor_root") == key:
            return
        self._sidebar_activated(item)

    def _sidebar_current_changed(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        # Moving with Up/Down must display the focused application's page.
        if current is None:
            return
        key = current.data(Qt.ItemDataRole.UserRole)
        if key in self._sidebar_application_keys:
            widget = self.stack.currentWidget()
            if widget is None or widget.property("editor_root") != key:
                self._sidebar_activated(current)

    def _sidebar_activated(self, item: QListWidgetItem) -> None:
        if item is None or not (item.flags() & Qt.ItemFlag.ItemIsEnabled):
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        if key == "__installed_applications__":
            self.show_installed_applications()
            return
        if key == "__suite__":
            self.show_suite_details()
            return
        if isinstance(key, str) and key.startswith("__group__:"):
            return
        application = next((entry for entry in [*self.editors, *self.readers, *self.extensions]
                            if self._entry_key(entry) == key), None)
        if application is not None:
            self.show_editor_details(application)

    def _sidebar_double_clicked(self, item: QListWidgetItem) -> None:
        if item is None or not (item.flags() & Qt.ItemFlag.ItemIsEnabled):
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        if not key or (isinstance(key, str) and key.startswith("__")):
            # Hub navigation and disclosure rows are not executable applications.
            return
        application = next((entry for entry in [*self.editors, *self.readers, *self.extensions]
                            if self._entry_key(entry) == key), None)
        if application is not None:
            self.launch_editor(application)

    def show_dashboard(self) -> None:
        self._record_navigation("dashboard")
        self.stack.setCurrentWidget(self.dashboard)
        self.editor_list.clearSelection()
        self.config.set("last_selected_editor", None)

    def show_store(self) -> None:
        """Open Get More or the integrated Store frontend, entirely from local data."""
        self._record_navigation("catalogue")
        self.stack.setCurrentIndex(self._ensure_catalogue_page())
        self.editor_list.clearSelection()

    def show_catalog_component(self, profile: ComponentProfile) -> None:
        """Open the canonical inactive App Page for one trusted component."""
        installed = next((entry for entry in self.components
                          if entry.editor_id == profile.component_id and not is_hub(entry)), None)
        if installed is not None:
            self.show_editor_details(installed)
            return
        self._record_navigation(f"catalog:{profile.component_id}")
        self.stack.setCurrentIndex(self._ensure_catalog_component_page(profile))
        self.editor_list.clearSelection()

    def show_version_history(self, editor: EditorEntry, *, preferred_version: str | None = None) -> None:
        """Open Version History and optionally select one exact version intentionally."""
        if editor not in self.components:
            editor = next((entry for entry in self.components if entry.editor_id == editor.editor_id), editor)
        index = self._ensure_version_history_page(editor, preferred_version=preferred_version)
        page = self.stack.widget(index)
        if preferred_version and page is not None:
            table = page.findChild(QTableWidget, "versionHistoryTable")
            if table is not None:
                for row in range(table.rowCount()):
                    item = table.item(row, 0)
                    if item is not None and item.data(Qt.ItemDataRole.UserRole) == preferred_version:
                        table.setCurrentCell(row, 0)
                        table.selectRow(row)
                        page.setProperty("suite_selected_version", preferred_version)
                        break
        self._record_navigation(f"versions:{editor.editor_id}")
        self.stack.setCurrentIndex(index)
        self.config.set("last_selected_editor", editor.editor_id if not is_hub(editor) else None)
        if is_hub(editor):
            self.editor_list.clearSelection()
            return
        key = self._entry_key(editor)
        for row in range(self.editor_list.count()):
            item = self.editor_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == key:
                if self.editor_list.currentItem() is not item:
                    self.editor_list.blockSignals(True)
                    try:
                        self.editor_list.setCurrentItem(item)
                    finally:
                        self.editor_list.blockSignals(False)
                break

    def show_editor_details(self, editor: EditorEntry) -> None:
        key = self._entry_key(editor)
        if key not in self._sidebar_application_keys and not is_backend_only_component(editor):
            return
        index = self._ensure_editor_page(editor)
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
        if is_backend_only_component(editor):
            self.show_store()
            return
        parts = editor.command()
        if not parts:
            QMessageBox.warning(self, app_dialog_title("Application Unavailable"), f"No launchable version of {editor.name} was found.")
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
        candidates = [component for component in self.components
                      if not is_hub(component) and not is_backend_only_component(component) and component.available]
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
                f"No installed Editor or Reader application is configured for {extension or 'files without an extension'}, "
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
        old_mode = saved_launch_mode(self.config.as_dict(), editor.editor_id)
        editor_id = editor.editor_id
        dialog = EditorPreferencesDialog(self, editor, self.config)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            requested_mode = str(dialog.mode.currentData() or 'auto')
            dialog.apply()
            self.refresh_editors()
            refreshed = next((entry for entry in self.components if entry.editor_id == editor_id), None)
            self._apply_runtime_preference(refreshed, old_mode, requested_mode)

    def _apply_runtime_preference(self, editor: EditorEntry | None, old_mode: str, requested: str) -> None:
        """Commit an explicit preference without discovery cancelling the user's choice.

        Normal launch is desktop-authoritative. The preference dialog deliberately
        reads the SAVED mode, then retargets a verified existing launcher using a
        one-operation copy of the entry with the newly requested mode. Only after
        that operation completes may a discovery refresh reconcile the states.
        """
        if editor is None or requested not in {'auto', 'portable', 'installed'}:
            return
        changed = old_mode != requested
        version = self._version_info(editor, editor.active_version) if editor.active_version else None
        selection = requested_version_runtime(requested, version) if version is not None else None
        requested_desktop = selection[0].casefold() if selection else None

        def restore_mode(message: str) -> None:
            override = self._editor_override(editor)
            if old_mode == 'auto':
                override.pop('launch_mode', None)
            else:
                override['launch_mode'] = old_mode
            self.config.save()
            self.refresh_editors(automatic=True)
            QMessageBox.warning(self, app_dialog_title('Launch Runtime Not Changed'), message)

        # Unchanged Automatic is not an instruction to change the currently
        # verified desktop launcher. Saving an explicit mismatching choice IS.
        if not changed and not (requested in {'portable', 'installed'}
                                and editor.desktop_issue == 'ready'
                                and editor.desktop_runtime != requested_desktop):
            return
        if editor.active_version and selection is None:
            restore_mode(f'{editor.name} {editor.active_version} does not have the requested {requested} runtime. '
                         'The previous choice and desktop launcher were preserved.')
            return
        if not sys.platform.startswith('linux') or editor.desktop_issue in {'missing', 'selection-required'}:
            # A missing launcher does not prohibit a remembered selection or
            # implicitly authorise creating desktop integration.
            return
        if editor.desktop_issue != 'ready':
            restore_mode('The desktop launcher must be explicitly resolved or repaired before changing '
                         'this runtime. No conflicting or external launcher was overwritten.')
            return
        if selection is None or requested_desktop == editor.desktop_runtime:
            return  # The verified launcher already satisfies the saved choice.

        selected_entry = copy.copy(editor)
        selected_entry.launch_mode = requested
        if is_hub(editor):
            success = self.repair_suite_desktop_integration(selected_entry, show_dialog=False)
        else:
            success = self.repair_component_desktop_integration(selected_entry, show_dialog=False)
        if not success:
            restore_mode('The requested runtime could not be integrated. The previous preference was restored; '
                         'inspect or repair desktop integration before trying again.')

    def general_preferences(self) -> None:
        self._close_about_dialog()
        old_suite_mode = saved_launch_mode(self.config.as_dict(), 'suite-pythoine')
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
        requested_suite_mode = str(dialog.suite_runtime.currentData() or 'auto')
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
            QMessageBox.critical(self, app_dialog_title("Applications Folder Unavailable"), str(exc))
            self.editors_root = self.runtime.ensure_writable_directory(self.runtime.default_editors_root)
            self.config.set("editors_root", str(self.editors_root), save=True)
        self.dashboard.editors_root = self.editors_root
        self.refresh_editors()
        self._apply_runtime_preference(self.suite_entry, old_suite_mode, requested_suite_mode)

    def install_editor_prompt(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            app_dialog_title("Install Application"),
            str(Path.home()),
            "Application packages (*.zip *.AppImage *.appimage);;Source ZIP archives (*.zip);;AppImage bundles (*.AppImage *.appimage)",
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
        path, _ = QFileDialog.getOpenFileName(self, app_dialog_title("Install Application from ZIP"), str(Path.home()), "ZIP archives (*.zip)")
        if path:
            self.install_editor_zip(Path(path))

    @traced_operation("appimage_install_handoff")
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
        def refreshed_after_appimage_install() -> None:
            # This callback runs while the installer wizard is still open. Mark
            # an intentionally inactive install before the one authoritative
            # post-wizard refresh schedules first-discovery handling.
            if not wizard.options.make_active_after_install:
                self._prompted_discovery.add((inspection.editor_id, 'selection-required'))
        wizard = AppImageInstallWizard(
            self,
            inspection,
            editors_root=self.editors_root,
            config=self.config,
            existing_editor=existing_editor,
            register_callback=self._register_managed_installation,
            refresh_desktop_callback=self._refresh_desktop_database,
            finished_callback=refreshed_after_appimage_install,
        )
        self._begin_managed_mutation()
        try:
            result = wizard.exec()
        finally:
            self._end_managed_mutation()
        if wizard.progress.succeeded and not wizard.options.make_active_after_install:
            self._prompted_discovery.add((inspection.editor_id, 'selection-required'))
        self.refresh_editors()
        if (
            wizard.progress.succeeded
            and inspection.editor_id == "suite-pythoine"
            and wizard.options.make_active_after_install
            and self.suite_entry is not None
            and sys.platform.startswith("linux")
        ):
            self.repair_suite_desktop_integration(self.suite_entry, show_dialog=False)
        if wizard.progress.succeeded:
            self._show_component_after_install(inspection.editor_id)
        if result == QDialog.DialogCode.Accepted and wizard.launch_after_finish:
            application = next((entry for entry in self.components if entry.editor_id == inspection.editor_id), None)
            version = self._version_info(application, inspection.version) if application is not None else None
            if version is not None:
                self.launch_editor_version(application, version, "appimage")
            else:
                QMessageBox.warning(self, app_dialog_title("Launch After Installation"),
                                    "The newly installed AppImage could not be verified for launching.")
        if wizard.progress.succeeded:
            self._status(f"Installed {inspection.name} {inspection.version} AppImage through the guided installer.")
        elif wizard.progress.started and wizard.progress.finished:
            self._status(f"AppImage installation of {inspection.name} stopped: {wizard.progress.error_message}")
        return bool(wizard.progress.succeeded)

    def retain_developer_source_zip_prompt(self, zip_path: Path | None = None) -> bool:
        """Menu or Ctrl+ZIP drop into Recovery only, without installing a runtime."""
        if not self.developer_config.enabled:
            return False
        if zip_path is None:
            selected, _ = QFileDialog.getOpenFileName(
                self, app_dialog_title("Retain Source ZIP — Recovery Only"),
                str(Path.home()), "Source ZIP archives (*.zip)",
            )
            if not selected:
                return False
            zip_path = Path(selected)
        try:
            inspection = inspect_editor_zip(
                zip_path, python_executable=self.launcher.python_executable(),
            )
            version = exact_source_version(inspection)
            destination = recovery_root(self.editors_root, inspection.name, version)
        except (InstallError, OSError, ValueError) as exc:
            QMessageBox.critical(self, app_dialog_title("Cannot Retain Source ZIP"), str(exc))
            return False
        response = QMessageBox.question(
            self, app_dialog_title("Retain Source ZIP — Recovery Only"),
            f"Application: {inspection.name} ({inspection.editor_id})\n"
            f"Exact version: {version}\n"
            f"Source ZIP: {inspection.zip_path}\n"
            f"SHA-256: {inspection.archive_sha256}\n\n"
            f"Managed destination:\n{destination}\n\n"
            "Only the validated original ZIP and its Recovery metadata will be retained. "
            "No Portable will be extracted, no AppImage built, no desktop integration "
            "changed, and no version made active. Existing Recovery is never overwritten.\n\n"
            "Retain this source ZIP?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if response != QMessageBox.StandardButton.Yes:
            return False
        try:
            result = retain_developer_source_zip(inspection, self.editors_root)
        except (InstallError, OSError, ValueError) as exc:
            QMessageBox.critical(self, app_dialog_title("Cannot Retain Source ZIP"), str(exc))
            return False
        self.refresh_editors(automatic=True)
        outcome = "Already retained" if result.already_retained else "Retained"
        self._status(f"{outcome}: {inspection.name} {version} source ZIP (Recovery only).")
        QMessageBox.information(
            self, app_dialog_title("Source ZIP Retained"),
            f"{outcome} in managed Recovery:\n{result.archive}\n\n"
            "The source ZIP was not installed or extracted. Restore Portable… "
            "remains available from the exact-version App Page.",
        )
        return True

    def _show_component_after_install(self, component_id: str) -> bool:
        """Navigate to the canonical destination for one successfully installed component."""
        if component_id == "suite-pythoine":
            self.show_suite_details()
            return True
        application = next((entry for entry in self.components if entry.editor_id == component_id and not is_hub(entry)), None)
        if application is None:
            return False
        self.show_editor_details(application)
        return True

    @traced_operation("zip_install_handoff")
    def install_editor_zip(self, zip_path: Path, *, store_download: bool = False) -> bool:
        """Open the guided installer for a source ZIP.

        Inspection is read-only and happens before the wizard is shown.  The
        component is not copied into the Applications folder until the user reaches the
        Progress page after reviewing the full install plan.
        """
        zip_path = zip_path.expanduser().resolve(strict=False)
        # This method always runs the normal guided installer. Developer Mode
        # drop policy is resolved by the caller: ordinary ZIP drop enters Intake,
        # while Shift+ZIP bypasses Intake and reaches this installer.
        try:
            inspection = inspect_editor_zip(
                zip_path,
                python_executable=self.launcher.python_executable(),
            )
        except (InstallError, OSError) as exc:
            QMessageBox.critical(self, app_dialog_title("Application Archive Could Not Be Inspected"), str(exc))
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
            finished_callback=lambda: None,
            delete_archive_default=store_download,
            existing_editor=existing_editor,
        )
        self._begin_managed_mutation()
        try:
            result = wizard.exec()
        finally:
            self._end_managed_mutation()
        if wizard.progress_page.succeeded and not wizard.options_page.make_active_after_install:
            self._prompted_discovery.add((inspection.editor_id, 'selection-required'))
        self.refresh_editors()
        if (
            wizard.progress_page.succeeded
            and inspection.editor_id == "suite-pythoine"
            and wizard.options_page.make_active_after_install
            and self.suite_entry is not None
            and sys.platform.startswith("linux")
        ):
            self.repair_suite_desktop_integration(self.suite_entry, show_dialog=False)
        if wizard.progress_page.succeeded:
            self._show_component_after_install(inspection.editor_id)
        if result == QDialog.DialogCode.Accepted and wizard.launch_after_finish:
            application = next((entry for entry in self.components if entry.editor_id == inspection.editor_id), None)
            version = self._version_info(application, inspection.version or inspection.builder_version) if application is not None else None
            if version is not None:
                self.launch_editor_version(application, version, "portable")
            else:
                QMessageBox.warning(self, app_dialog_title("Launch After Installation"),
                                    "The newly installed Portable version could not be verified for launching.")
        if wizard.progress_page.succeeded:
            self._status(f"Installed {inspection.name} through the guided installer.")
        elif wizard.progress_page.started and wizard.progress_page.finished:
            self._status(f"Installation of {inspection.name} stopped: {wizard.progress_page.error_message}")
        return bool(wizard.progress_page.succeeded)

    def _run_developer_intake(self, zip_path: Path | None = None) -> bool:
        """Open Developer Intake itself, optionally preloading a Developer Mode ZIP drop."""
        if not self.developer_config.enabled:
            return False
        if zip_path is not None and zip_path.suffix.casefold() != '.zip':
            return False
        self._close_about_dialog()
        dialog = DeveloperIntakeDialog(
            self, self.developer_config, self.developer_catalog,
            open_path_callback=self.launcher.open_path,
        )
        if zip_path is not None and not dialog.load_zip(zip_path.expanduser().resolve(strict=False)):
            return False
        dialog.exec()
        install_zip = dialog.install_requested_zip
        try:
            if install_zip is not None:
                return self.install_editor_zip(install_zip)
            return True
        finally:
            # Keep the private exact archive alive through the synchronous guided
            # installer handoff, then remove it on success, failure or cancel.
            dialog.cleanup_session_vault()

    def developer_intake_prompt(self) -> bool:
        """Open Developer Intake without forcing a ZIP chooser first."""
        return self._run_developer_intake()

    def _open_developer_intake_zip(self, zip_path: Path) -> bool:
        """Open a Developer Mode ZIP drop in Intake; Shift+ZIP bypass is handled before this call."""
        return self._run_developer_intake(zip_path)

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
                if forced == "beespector":
                    self._launch_component_argument("beespector", str(path.resolve(strict=False)), "Beespector")
                elif developer_intake_drop(
                    self.developer_config.enabled, path.name, modifier_value,
                    shift_mask=int(Qt.KeyboardModifier.ShiftModifier.value),
                    other_modifiers=int((Qt.KeyboardModifier.ControlModifier
                                         | Qt.KeyboardModifier.AltModifier
                                         | Qt.KeyboardModifier.MetaModifier).value),
                    forced_override=bool(forced),
                ):
                    self._open_developer_intake_zip(path)
                elif developer_retain_drop(
                    self.developer_config.enabled, path.name, modifier_value,
                    ctrl_mask=int(Qt.KeyboardModifier.ControlModifier.value),
                    other_modifiers=int((Qt.KeyboardModifier.ShiftModifier
                                         | Qt.KeyboardModifier.AltModifier
                                         | Qt.KeyboardModifier.MetaModifier).value),
                    forced_override=bool(forced),
                ):
                    self.retain_developer_source_zip_prompt(path)
                else:
                    self.route_file(path)
            else:
                self._route_url(url, forced=forced if forced in {"youlindo", "crawlindo"} else None)

    def eventFilter(self, watched, event) -> bool:
        if (event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape
                and self.isActiveWindow()):
            version_filter = self._version_filters.get(self.stack.currentWidget())
            if version_filter is not None:
                version_filter.clear()
                event.accept()
                return True
            current_widget = self.stack.currentWidget()
            if (current_widget is not None and current_widget.property("editor_root") == "__catalogue__"
                    and self.catalogue_search is not None):
                self.catalogue_search.clear()
                event.accept()
                return True
            if self.stack.currentWidget() is self.dashboard:
                self.dashboard.search.clear()
                event.accept()
                return True
        if (watched is self.editor_list and event.type() == QEvent.Type.KeyPress
            and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and event.modifiers() == Qt.KeyboardModifier.NoModifier):
            selected = self.editor_list.currentItem()
            key = selected.data(Qt.ItemDataRole.UserRole) if selected is not None else None
            if isinstance(key, str) and key.startswith("__group__:"):
                self._sidebar_clicked(selected)
            else:
                self._sidebar_double_clicked(selected)
            event.accept()
            return True
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
        if mime.hasUrls() or mime.hasText():
            # Especially with Shift held, KDE file managers may propose MOVE.
            # Suite only reads paths and must never consume the source file.
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else: event.ignore()

    def dragMoveEvent(self, event) -> None:
        mime = event.mimeData()
        if mime.hasUrls() or mime.hasText():
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        mime = event.mimeData()
        payloads = list(mime.urls()) if mime.hasUrls() else []
        if not payloads and mime.hasText():
            text = mime.text().strip()
            if text: payloads = [QUrl.fromUserInput(text)]
        if not payloads:
            event.ignore(); return
        self._handle_drop_payloads(payloads, int(event.modifiers().value))
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()

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

    def _focus_contextual_search(self) -> None:
        current_widget = self.stack.currentWidget()
        version_filter = self._version_filters.get(current_widget)
        if version_filter is not None:
            version_filter.setFocus(Qt.FocusReason.ShortcutFocusReason)
            version_filter.selectAll()
            return
        if (current_widget is not None and current_widget.property("editor_root") == "__catalogue__"
                and self.catalogue_search is not None):
            self.catalogue_search.setFocus(Qt.FocusReason.ShortcutFocusReason)
            self.catalogue_search.selectAll()
            return
        # 0.8.8 made Ctrl+F on an App Page focus its version filter. With
        # version filtering intentionally moved to Version History, preserve
        # that user contract by opening the dedicated page and focusing there.
        current_root = current_widget.property("editor_root") if current_widget is not None else None
        target: EditorEntry | None = None
        if current_root == "__suite__":
            target = self.suite_entry
        elif isinstance(current_root, str) and current_root and not current_root.startswith("__"):
            target = next((entry for entry in self.components if self._entry_key(entry) == current_root), None)
        if target is not None and target.versions:
            self.show_version_history(target)
            history_filter = self._version_filters.get(self.stack.currentWidget())
            if history_filter is not None:
                history_filter.setFocus(Qt.FocusReason.ShortcutFocusReason)
                history_filter.selectAll()
            return
        # Preserve Dashboard search behavior everywhere else.
        self.show_dashboard()
        self.dashboard.search.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def _sync_view_actions(self, mode: str) -> None:
        self.list_action.setChecked(mode == "list")
        self.grid_action.setChecked(mode == "grid")

    @traced_operation("developer_mode_toggle")
    def _toggle_developer_mode(self, checked: bool) -> None:
        if not self.developer_config.set_enabled(bool(checked), save=True):
            QMessageBox.critical(self, app_dialog_title("Developer Mode Error"), f"Could not save Developer Intake state to {self.developer_config.path}")
            self._sync_developer_mode_ui(); return
        self._sync_developer_mode_ui()
        self._status("Developer Mode enabled (ZIP Intake; Shift+ZIP install; Ctrl+ZIP retain Recovery)." if checked else "Developer Mode disabled.")

    def _toggle_dashboard_icons(self, checked: bool) -> None:
        self.dashboard.set_show_icons(bool(checked))
        self.config.set("dashboard_show_icons", bool(checked), save=True)

    def _toggle_drop_bar(self, checked: bool) -> None:
        self.dashboard.set_drop_bar_visible(bool(checked))
        self.config.set("dashboard_drop_bar_visible", bool(checked), save=True)

    @staticmethod
    def _normalize_sidebar_mode(value: object) -> str:
        return value if value in {"left", "right", "floating"} else "left"

    def _logical_splitter_sizes(self) -> list[int]:
        """Persist sidebar-first sizes independent of left/right placement."""
        sizes = list(self.splitter.sizes())
        if len(sizes) != 2:
            return [self._restored_sidebar_width, max(1, self.splitter.width() - self._restored_sidebar_width)]
        if self.splitter.indexOf(self.sidebar) == 1:
            sizes.reverse()
        if not self.sidebar.isVisible() and self._restored_sidebar_width > 0:
            sizes[0] = self._restored_sidebar_width
        return sizes

    def _remember_sidebar_width(self, _position: int, _index: int) -> None:
        if self._sidebar_mode == "floating" or not self.sidebar.isVisible():
            return
        size = self._logical_splitter_sizes()[0]
        if size > 0:
            self._restored_sidebar_width = min(250, size)

    def _apply_sidebar_width(self, requested: int) -> None:
        sidebar_width = max(0, min(250, int(requested)))
        # Unlike the Plus editors, Suite intentionally permits dragging its
        # 250px-capped sidebar all the way shut. Retain that existing contract.
        sizes = [sidebar_width, max(1, self.splitter.width() - sidebar_width)]
        if self.splitter.indexOf(self.sidebar) == 1:
            sizes.reverse()
        self.splitter.setSizes(sizes)

    def _sync_sidebar_position_actions(self) -> None:
        for value, action in self.sidebar_position_actions.items():
            action.blockSignals(True)
            action.setChecked(value == self._sidebar_mode)
            action.blockSignals(False)

    def _set_sidebar_mode(self, mode: str, *, persist: bool = True, reveal: bool = True) -> None:
        """Move the same splitter sidebar or show a separate modeless launcher."""
        mode = self._normalize_sidebar_mode(mode)
        previous = self._sidebar_mode
        if previous != "floating":
            widths = self._logical_splitter_sizes()
            if widths[0] > 0 and self.sidebar.isVisible():
                self._restored_sidebar_width = min(250, widths[0])
        self._sidebar_mode = mode
        if mode in {"left", "right"}:
            self._last_docked_side = mode
            target = 0 if mode == "left" else 1
            if self.splitter.indexOf(self.sidebar) != target:
                self.splitter.insertWidget(target, self.sidebar)
            for widget, stretch in ((self.sidebar, 0), (self.stack, 1)):
                index = self.splitter.indexOf(widget)
                self.splitter.setStretchFactor(index, stretch)
                self.splitter.setCollapsible(index, widget is self.sidebar)
            if self._sidebar_launcher is not None:
                self._sidebar_launcher.hide()
            if reveal or previous == "floating":
                self.sidebar.show()
            self._apply_sidebar_width(self._restored_sidebar_width)
        else:
            self.sidebar.hide()
        self._sync_sidebar_position_actions()
        self.dashboard.set_launcher_button_visible(mode == "floating")
        if persist:
            self.config.set("sidebar_position", mode, save=True)
        self._set_sidebar_visible(True if reveal else self._sidebar_requested_visible,
                                  persist=persist)

    def _show_dashboard_launcher(self) -> None:
        """Use the Dashboard Launch button to reveal/focus its floating sidebar."""
        if self._sidebar_mode == "floating":
            self._set_sidebar_visible(True)

    def _toggle_sidebar_position(self) -> None:
        # The same Shift+F9 left/right parity used by both Plus applications.
        current = self._sidebar_mode if self._sidebar_mode != "floating" else self._last_docked_side
        self._set_sidebar_mode("right" if current == "left" else "left")

    def _ensure_sidebar_launcher(self) -> SidebarLauncher:
        if self._sidebar_launcher is None:
            launcher = SidebarLauncher(self)
            launcher.page_requested.connect(self._launcher_open_page)
            launcher.launch_requested.connect(self._launcher_launch)
            launcher.dashboard_requested.connect(self.show_dashboard)
            launcher.refresh_requested.connect(self.refresh_editors)
            launcher.store_requested.connect(self.show_store)
            launcher.visibility_changed.connect(self._launcher_visibility_changed)
            self._sidebar_launcher = launcher
            self._sync_launcher_inventory()
            self._sync_store_navigation()
        return self._sidebar_launcher

    def _sync_launcher_inventory(self) -> None:
        launcher = self._sidebar_launcher
        if launcher is None:
            return
        launcher.set_entries([
            (label, [(self._entry_key(entry), entry) for entry in group
                     if entry.editor_id != "store-pythoine"])
            for label, group in (("EDITORS", self.editors), ("READERS", self.readers),
                                 ("EXTENSIONS", self.extensions))
        ])

    def _launcher_entry(self, key: str) -> EditorEntry | None:
        return next((entry for entry in (*self.editors, *self.readers, *self.extensions)
                     if self._entry_key(entry) == key), None)

    def _launcher_open_page(self, key: str) -> None:
        entry = self._launcher_entry(key)
        if entry is not None:
            self.show_editor_details(entry)
            self.raise_()
            self.activateWindow()

    def _launcher_launch(self, key: str) -> None:
        entry = self._launcher_entry(key)
        if entry is not None:
            self.launch_editor(entry)

    def _launcher_visibility_changed(self, visible: bool) -> None:
        if self._closing or self._sidebar_mode != "floating":
            return
        self._sidebar_requested_visible = bool(visible)
        self.sidebar_action.blockSignals(True)
        self.sidebar_action.setChecked(bool(visible))
        self.sidebar_action.blockSignals(False)
        self.config.set("sidebar_visible", bool(visible), save=True)

    def _set_sidebar_visible(self, visible: bool, *, persist: bool = True) -> None:
        self._sidebar_requested_visible = bool(visible)
        if self._sidebar_mode == "floating":
            self.sidebar.hide()
            if visible and self.isVisible() and not self._closing:
                launcher = self._ensure_sidebar_launcher()
                launcher.show()
                launcher.raise_()
                launcher.activateWindow()
                launcher.focus_search()
            elif not visible and self._sidebar_launcher is not None:
                self._sidebar_launcher.hide()
        else:
            self.sidebar.setVisible(bool(visible))
        self.sidebar_action.blockSignals(True)
        self.sidebar_action.setChecked(bool(visible))
        self.sidebar_action.blockSignals(False)
        if persist:
            self.config.set("sidebar_visible", bool(visible), save=True)

    def _toggle_sidebar(self, checked: bool) -> None:
        self._set_sidebar_visible(bool(checked))

    def _show_initial_floating_launcher(self) -> None:
        if self.isVisible() and not self._closing and self._sidebar_mode == "floating" \
                and self._sidebar_requested_visible:
            self._set_sidebar_visible(True, persist=False)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._sidebar_mode == "floating" and self._sidebar_requested_visible:
            QTimer.singleShot(0, self._show_initial_floating_launcher)

    def _set_theme(self, theme: str) -> None:
        theme = normalize_theme(theme)
        self.config.set("app_theme", theme, save=True)
        apply_theme(QApplication.instance(), theme)
        # Qt propagates the application palette to ordinary child widgets.
        # Dashboard borders paint from the palette, never descendant QSS.
        self.dashboard.refresh_theme()
        for widget in (self.dev_status_badge, self.dev_sidebar_badge):
            style = widget.style()
            style.unpolish(widget)
            style.polish(widget)
            widget.update()
        if self._sidebar_launcher is not None:
            self._sidebar_launcher.refresh_theme()
        for value, action in self.theme_actions.items():
            action.blockSignals(True)
            action.setChecked(value == theme)
            action.blockSignals(False)
        # Destructive buttons intentionally carry a custom danger palette;
        # rebase that palette so they follow the newly selected shell theme.
        for button in self.findChildren(QPushButton):
            if bool(button.property("suite_destructive")):
                _style_destructive_button(button)
        label = "System" if theme == "system" else theme.title()
        self._status(f"App Theme: {label}.")

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
        # Store sizes in sidebar-first logical order so switching to the right
        # cannot invert the next launch's restored sidebar width.
        self._restored_sidebar_width = max(0, min(int(sizes[0]), 250))
        self._sidebar_requested_visible = bool(self.config.get("sidebar_visible", True))
        self._set_sidebar_mode(
            self._normalize_sidebar_mode(self.config.get("sidebar_position", "left")),
            persist=False, reveal=False,
        )
        self._apply_sidebar_width(self._restored_sidebar_width)
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
                ("Refresh Applications", self.refresh_action),
                ("Toggle List/Grid View", self.toggle_view_shortcut_action),
                ("Show Sidebar", self.sidebar_action),
                ("Dock Sidebar Left", self.sidebar_position_actions["left"]),
                ("Dock Sidebar Right", self.sidebar_position_actions["right"]),
                ("Floating Applications Launcher", self.sidebar_position_actions["floating"]),
                ("Toggle Sidebar Dock Side", self.toggle_sidebar_position_action),
                ("App Theme — Light", self.theme_actions["light"]),
                ("App Theme — Dark", self.theme_actions["dark"]),
                ("App Theme — System", self.theme_actions["system"]),
                ("Show Dashboard Icons", self.icons_action),
                ("Show Drop Bar", self.drop_bar_action),
                ("Focus Dashboard / Version History / Installed Applications search", self.search_action),
                ("Clear contextual Dashboard / Version History / Installed Applications search", "Esc"),
                ("Full Screen", self.fullscreen_action),
                ("Previous Suite Page/Card", "Backspace"),
                ("Previous Application", self.previous_application_action),
                ("Next Application", self.next_application_action),
            ],
            "Tools": [
                ("Hub Details", self.hub_details_action),
                ("Hub Preferences", self.preferences_action),
                ("Installed Applications", self.installed_applications_action),
                ("Install Application", self.install_action),
                ("Store Pythoine" if self._store_is_installed() else "Get More Applications", self.store_action),
                ("Developer Mode", self.developer_action),
                ("Developer Intake", self.developer_intake_action),
                ("Retain Source ZIP (Recovery Only)", self.retain_source_zip_action),
                ("Open Applications Folder (keyboard-only)", self.open_components_folder_action),
            ],
            "Drop Bar": [
                ("Beespector Drop Override", "Ctrl+Shift+B"),
                ("Youlindo URL Drop Override", "Ctrl+Shift+Y"),
                ("Crawlindo URL Drop Override", "Ctrl+Shift+C"),
            ],
            "Help": [
                ("Documentation", self.documentation_action),
                ("Quick Tour", self.quick_tour_action),
                ("Keyboard Shortcuts", self.shortcuts_action),
            ],
        }

    def show_quick_tour(self) -> None:
        dialog = QuickTourDialog(self.config, self)
        dialog.exec()

    def _begin_post_exit_shutdown(self, *, preserve_reviewed_preferences: bool) -> None:
        """Deterministically leave the event loop after a reviewed external handoff."""
        if preserve_reviewed_preferences:
            self._suite_uninstall_exiting = True
        self.close()
        application = QApplication.instance()
        if application is not None:
            application.quit()

    def show_uninstall_suite(self) -> None:
        if not sys.platform.startswith("linux"):
            QMessageBox.information(self, app_dialog_title("Not Available"),
                "The independent post-exit Suite uninstaller currently supports Linux only.")
            return
        wizard = SuiteUninstallWizard(self)
        wizard.exec()
        if wizard.handoff_ready:
            self._begin_post_exit_shutdown(preserve_reviewed_preferences=True)

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
            "A lightweight hub for installing, managing and launching brunonlinespace "
            "Editors, Readers and Extensions. Handles file routing, Portable and AppImage "
            "runtimes, Recovery and desktop integration. A little Python, sweetly caffeinated.",
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
        # Open About at the same default width as Quick Tour while preserving
        # About's existing content-derived height and minimum-height behavior.
        dialog.adjustSize()
        dialog.resize(940, dialog.height())
        dialog.show()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._closing:
            event.accept()
            return
        self._closing = True
        self.watcher.stop()
        if self._suite_uninstall_exiting:
            # The reviewed helper plan captured exact preference file identities.
            # A normal exit would atomically resave preferences and invalidate
            # that confirmed snapshot. Preserve the reviewed on-disk state.
            event.accept()
            return
        self._save_inventory_table_layout()
        self.config.update(
            {
                "window_width": self.width(),
                "window_height": self.height(),
                "window_maximized": self.isMaximized(),
                "splitter_sizes": self._logical_splitter_sizes(),
                "sidebar_visible": self._sidebar_requested_visible,
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

    install_gui_error_hook()
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
    try:
        config = ConfigService(runtime.config_path)
    except RegistryRetirementError as exc:
        QMessageBox.critical(
            None,
            app_dialog_title("Managed Registry Unavailable"),
            "Suite Pythoine could not retire its obsolete pre-0.8.1 registry file. "
            "No owned installation records have been intentionally discarded.\n\n"
            f"{exc}\n\nCheck file permissions for the obsolete registry location before starting Suite again.",
        )
        return 1
    apply_theme(app, normalize_theme(config.get("app_theme", "system")))

    requested = runtime.resolve_editors_root(config.get("editors_root"))
    try:
        editors_root = runtime.ensure_writable_directory(requested)
    except OSError as exc:
        try:
            editors_root = runtime.ensure_writable_directory(runtime.default_editors_root)
        except OSError as fallback_exc:
            print(f"Applications folder unavailable ({exc}); fallback also failed ({fallback_exc}).", file=sys.stderr)
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
    startup_trace = begin_operation("startup", start_perf=process_start_perf(), version=__version__)
    if "--version" in sys.argv:
        print(f"{APP_NAME} {__version__}")
        startup_trace.finish(exit="version")
        return 0

    install_gui_error_hook()
    smoke_test = "--suite-pythoine-smoke-test" in sys.argv
    startup_trace.set("smoke_test", bool(smoke_test))
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
    try:
        config = ConfigService(runtime.config_path)
    except RegistryRetirementError as exc:
        QMessageBox.critical(
            None,
            app_dialog_title("Managed Registry Unavailable"),
            "Suite Pythoine could not retire its obsolete pre-0.8.1 registry file. "
            "No owned installation records have been intentionally discarded.\n\n"
            f"{exc}\n\nCheck file permissions for the obsolete registry location before starting Suite again.",
        )
        return 1

    apply_theme(app, normalize_theme(config.get("app_theme", "system")))

    requested = runtime.resolve_editors_root(config.get("editors_root"))
    try:
        editors_root = runtime.ensure_writable_directory(requested)
    except OSError as exc:
        fallback = runtime.ensure_writable_directory(runtime.default_editors_root)
        editors_root = fallback
        config.set("editors_root", str(fallback), save=True)
        print(f"Applications folder '{requested}' was unavailable ({exc}); using '{fallback}'.", file=sys.stderr)

    window = SuiteWindow(runtime, config, editors_root)
    window.show()
    startup_trace.finish()
    # 0.8.1: never offer to import/move installations outside the one managed root.
    # Previously configured legacy roots and external files remain untouched.

    if smoke_test:
        # AppImage packaging smoke test: construct the real main window, allow
        # one Qt event cycle, then close cleanly.  The builder supplies a
        # temporary HOME/XDG_CONFIG_HOME and QT_QPA_PLATFORM=offscreen.
        # Startup-only dialogs are deliberately not scheduled on this path.
        app.processEvents()
        window.close()
        app.processEvents()
        print(f"{APP_NAME} {__version__} GUI smoke test passed.")
        return 0

    if bool(config.get("show_quick_tour_on_startup", True)):
        QTimer.singleShot(0, window.show_quick_tour)

    startup_paths = [Path(arg) for arg in sys.argv[1:] if not arg.startswith("-") and Path(arg).expanduser().exists()]
    if startup_paths:
        QTimer.singleShot(0, lambda: window.handle_startup_paths(startup_paths))
    return app.exec()
