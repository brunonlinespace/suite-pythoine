from __future__ import annotations

import ast
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import sys
import tempfile
from unittest.mock import patch
import zipfile

from suite_pythoine import APP_NAME, __version__
from suite_pythoine.component_catalog import COMPONENT_PROFILES, BUNDLED_CATALOG_PATH, catalog_fingerprint, catalog_revision, install_verified_catalog, load_catalog, extension_union, mime_type_union
from suite_pythoine.component_policy import can_create_document, can_open_document, can_route_document, document_candidates, is_hub, is_document_editor, is_reader
from suite_pythoine.config import ConfigService
from suite_pythoine.dashboard_model import filter_and_sort_editors
from suite_pythoine.install_inspection import inspect_editor_zip
from suite_pythoine.appimage_inspection import inspect_appimage
from suite_pythoine.installer import (
    InstallError,
    archive_expanded_bytes,
    build_script_version,
    clean_build_dirs,
    desktop_entry_exec_command,
    desktop_entry_exec_target,
    desktop_entry_path,
    desktop_entry_runtime,
    desktop_entry_status,
    portable_desktop_entry_status,
    find_appimage_build_script,
    find_built_appimage,
    import_zip,
    install_appimage,
    install_icon,
    preflight_archive_install,
    remove_portable_editor_folder,
    safe_extract_zip,
    snapshot_appimages,
    stage_registered_appimage_integration,
    restore_staged_registered_integration,
    finalize_staged_registered_integration,
    uninstall_registered_appimage_integration,
    write_appimage_metadata,
    write_desktop_entry,
    synchronize_desktop_integration,
    synchronize_portable_desktop_integration,
)
from suite_pythoine.managed_registry import (
    REGISTRY_SCHEMA,
    desktop_id_for,
    get_managed_group,
    get_managed_installation,
    get_managed_versions,
    record_is_complete,
    remove_managed_installation,
    remove_managed_version,
    set_active_version,
    set_desktop_version,
    set_managed_installation,
)
from suite_pythoine.registry import PAD_FAMILY_EXTENSIONS, PAD_FAMILY_MIME_TYPES, discover_editors, editors_for_extension, inspect_editor_root
from suite_pythoine.silent_dispatch import ASK_EVERY_TIME, INSPECTOR_FALLBACK_ASK, diagnose_routing, dispatch_paths_silently, load_config as load_dispatch_config
import suite_pythoine.silent_dispatch as silent_dispatch_module
from suite_pythoine.self_update import complete_pending_self_cleanup
from suite_pythoine.storage_layout import appimage_root, editors_root_default, legacy_editors_root_default, portable_root, prune_empty_version_tree, version_root
from suite_pythoine.storage_migration import build_migration_plan, migrate_item
from suite_pythoine.root_transition import transition_legacy_default_root
from suite_pythoine.routing_index import ROUTING_INDEX_SCHEMA, RoutingTarget, build_index_payload, inventory_stamp, load_index
from suite_pythoine.ui_titles import app_dialog_title
from suite_pythoine.store_bridge import STORE_PROTOCOL_VERSION, inspect_package, managed_inventory, _bridge_script
from suite_pythoine.versioning import appimage_metadata_path, detect_source_version, version_from_filename
from suite_pythoine.version_management import classify_install, versions_to_remove

EXPECTED_VERSION = "0.3.3"
ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "suite_pythoine"
GENERATED_PARTS = frozenset({"build", "dist", ".venv", "venv", "__pycache__"})


def check(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def is_generated_path(path: Path) -> bool:
    try:
        relative = path.resolve(strict=False).relative_to(ROOT.resolve(strict=False))
    except ValueError:
        return False
    return any(part in GENERATED_PARTS for part in relative.parts)


def png_info(path: Path) -> tuple[int, int, int] | None:
    try:
        data = path.read_bytes()[:33]
    except OSError:
        return None
    if len(data) < 33 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", data[16:24])
    return width, height, data[25]


def source_checks(errors: list[str]) -> None:
    required = (
        "main.py", "COPYING", "suite-pythoine.json",
        "suite_pythoine/__init__.py", "suite_pythoine/app.py", "suite_pythoine/config.py",
        "suite_pythoine/dashboard.py", "suite_pythoine/dashboard_model.py", "suite_pythoine/editor_watcher.py",
        "suite_pythoine/installer.py", "suite_pythoine/install_inspection.py", "suite_pythoine/install_wizard.py",
        "suite_pythoine/appimage_inspection.py", "suite_pythoine/appimage_wizard.py",
        "suite_pythoine/migration_wizard.py", "suite_pythoine/storage_layout.py", "suite_pythoine/storage_migration.py",
        "suite_pythoine/purge_wizard.py", "suite_pythoine/ui_titles.py", "suite_pythoine/managed_registry.py",
        "suite_pythoine/registry.py", "suite_pythoine/runtime_launcher.py", "suite_pythoine/runtime_paths.py",
        "suite_pythoine/silent_dispatch.py", "suite_pythoine/store_bridge.py",
        "suite_pythoine/versioning.py", "suite_pythoine/version_management.py",
        "suite_pythoine/self_update.py", "suite_pythoine/self_bootstrap.py",
        "suite_pythoine/component_catalog.py", "suite_pythoine/component_policy.py", "suite_pythoine/components.json",
        "suite_pythoine/routing_index.py", "suite_pythoine/routing_chooser.py", "suite_pythoine/root_transition.py",
        "suite_pythoine/component-manifest.example.json",
        "suite_pythoine/requirements.txt", "suite_pythoine/docs/README.md", "suite_pythoine/docs/QA.md",
        "suite_pythoine/docs/RELEASE_NOTES.md", "suite_pythoine/docs/ARCHITECTURE.md",
        "suite_pythoine/developer_intake.py",
        "suite_pythoine/docs/V0_1_2_UI_METADATA_AUDIT.md",
        "suite_pythoine/docs/V0_2_0_VERSION_MANAGEMENT_AUDIT.md",
        "suite_pythoine/docs/V0_2_1_APPIMAGE_IMPORT_AUDIT.md",
        "suite_pythoine/docs/V0_3_0_COMPONENT_ROUTING_RECOVERY_AUDIT.md",
        "suite_pythoine/docs/V0_3_1_MARKOPAD_CATALOGUE_AUDIT.md",
        "suite_pythoine/docs/V0_3_2_EXP2_COMPONENT_UI_AUDIT.md",
        "suite_pythoine/packaging/README.md", "suite_pythoine/packaging/appimage/AppRun",
        "suite_pythoine/packaging/appimage/suite-pythoine.desktop",
        "suite_pythoine/packaging/appimage/suite-pythoine.png",
        "suite_pythoine/packaging/appimage/io.github.brunonlinespace.suite-pythoine.metainfo.xml",
        "suite_pythoine/packaging/fedora/build-appimage.sh", "suite_pythoine/packaging/fedora/test-appimage.sh",
        "suite_pythoine/packaging/pyinstaller/build-requirements.txt", "suite_pythoine/qa/static-qa.sh",
        "suite_pythoine/SOURCE_MANIFEST.sha256",
    )
    for relative in required:
        check((ROOT / relative).is_file(), f"Missing required file: {relative}", errors)
    check(not (ROOT / "my editors").exists(), "Legacy source-tree 'my editors' folder is still shipped", errors)

    for size in (16, 24, 32, 48, 64, 128, 256, 512):
        info = png_info(PACKAGE / "assets" / f"suite-pythoine-{size}.png")
        check(info is not None and info[:2] == (size, size), f"Wrong/missing {size}px icon", errors)
        if info:
            check(info[2] in {4, 6}, f"{size}px icon is not alpha-capable PNG", errors)
    info = png_info(PACKAGE / "assets" / "suite-pythoine-master-1024.png")
    check(info is not None and info[:2] == (1024, 1024) and info[2] in {4, 6}, "Wrong/missing 1024px master icon", errors)

    check(APP_NAME == "Suite Pythoine", "Wrong application name", errors)
    check(__version__ == EXPECTED_VERSION, f"Wrong version: {__version__}", errors)
    try:
        suite_manifest = json.loads((ROOT / "suite-pythoine.json").read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"Suite manifest could not be read: {exc}")
        suite_manifest = {}
    check(suite_manifest.get("id") == "suite-pythoine", "Suite application ID is not suite-pythoine", errors)
    check(suite_manifest.get("publisher") == "brunonlinespace", "Suite publisher is not brunonlinespace", errors)
    check(suite_manifest.get("publisher_id") == "brunonlinespace", "Suite publisher/Editor ID is not brunonlinespace", errors)
    check(suite_manifest.get("desktop_id") == "io.github.brunonlinespace.suite-pythoine", "Suite desktop identity mismatch", errors)
    check(suite_manifest.get("version") == EXPECTED_VERSION, "Suite manifest version mismatch", errors)
    expected_editor_ids = {"markopad", "nuxpad", "ricopad", "texypad", "sheepy-pad", "timblee-pad", "jsts-pad"}
    expected_reader_ids = {"kapitulindo", "portapad", "beespector-lite", "beespector"}
    expected_extension_ids = {"linspectacles", "marko-plus", "rico-plus", "crawlindo", "youlindo", "sbookypad", "gitten", "python-lair", "store-pythoine"}
    check(set(COMPONENT_PROFILES) == {"suite-pythoine", *expected_editor_ids, *expected_reader_ids, *expected_extension_ids}, "Experimental component catalogue IDs mismatch", errors)
    check(all(COMPONENT_PROFILES[item].kind == "editor" for item in expected_editor_ids), "Editor component classification mismatch", errors)
    check(all(COMPONENT_PROFILES[item].kind == "reader" for item in expected_reader_ids), "Reader component classification mismatch", errors)
    check(all(COMPONENT_PROFILES[item].kind == "extension" and not COMPONENT_PROFILES[item].extensions for item in expected_extension_ids), "Extension component classification/routing boundary mismatch", errors)
    # Regression: post-import verification must understand the standard
    # two-item Pad-family portable root with identity inside the app package.
    nested_manifest_fixtures = (
        (
            "python_lair2",
            "python-lair.json",
            {"id": "python-lair", "name": "Python Lair", "version": "2.0.0", "publisher_id": "brunonlinespace"},
            "python-lair",
            "extension",
        ),
        (
            "sheepy_pad",
            "sheepy-pad.json",
            {"id": "sheepy-pad", "name": "Sheepy Pad", "version": "0.2.0", "publisher_id": "brunonlinespace"},
            "sheepy-pad",
            "editor",
        ),
    )
    for package_name, manifest_name, manifest_data, expected_id, expected_kind in nested_manifest_fixtures:
        with tempfile.TemporaryDirectory(prefix="suite-nested-identity-") as temp_dir:
            portable = Path(temp_dir) / "Portable"
            package_dir = portable / package_name
            package_dir.mkdir(parents=True)
            (portable / "main.py").write_text("# fixture\n", encoding="utf-8")
            manifest_path = package_dir / manifest_name
            manifest_path.write_text(json.dumps(manifest_data, indent=2) + "\n", encoding="utf-8")
            entry = inspect_editor_root(
                portable,
                config={},
                installed_dir=Path(temp_dir) / "Installed",
                python_executable="python3",
            )
            check(entry.editor_id == expected_id, f"Nested manifest identity failed for {expected_id}", errors)
            check(entry.component_kind == expected_kind, f"Nested manifest kind failed for {expected_id}", errors)
            check(entry.manifest_path == manifest_path.resolve(), f"Nested manifest path failed for {expected_id}", errors)
            check(entry.source_version == manifest_data["version"], f"Nested manifest version failed for {expected_id}", errors)

    check(COMPONENT_PROFILES["texypad"].extensions == (".tex", ".bib"), "Texypad routing formats mismatch", errors)
    check(COMPONENT_PROFILES["jsts-pad"].extensions == (".js", ".mjs", ".cjs", ".ts", ".mts", ".cts", ".jsx", ".tsx"), "JSTS Pad routing formats mismatch", errors)
    check("psts-pad" not in COMPONENT_PROFILES, "Removed PSTS typo identity is still present", errors)
    check(COMPONENT_PROFILES["timblee-pad"].extensions == (".html", ".htm", ".css") and ".svg" not in COMPONENT_PROFILES["timblee-pad"].extensions, "Timblee routing must remain HTML/HTM/CSS only", errors)
    check(COMPONENT_PROFILES["store-pythoine"].kind == "extension" and not COMPONENT_PROFILES["store-pythoine"].is_routable, "Store Pythoine trust/catalogue boundary mismatch", errors)
    check(can_route_document(COMPONENT_PROFILES["portapad"]) and can_open_document(COMPONENT_PROFILES["portapad"]) and not can_create_document(COMPONENT_PROFILES["portapad"]), "Reader capability boundary mismatch", errors)
    check(can_create_document(COMPONENT_PROFILES["markopad"]), "Editor create capability mismatch", errors)

    manifest_path = PACKAGE / "SOURCE_MANIFEST.sha256"
    if manifest_path.is_file():
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                expected, relative = line.split("  ", 1)
            except ValueError:
                errors.append(f"Malformed manifest line: {line}")
                continue
            target = ROOT / relative
            if not target.is_file():
                errors.append(f"Manifest target missing: {relative}")
            elif hashlib.sha256(target.read_bytes()).hexdigest() != expected:
                errors.append(f"Manifest mismatch: {relative}")

    for path in ROOT.rglob("*.py"):
        if is_generated_path(path):
            continue
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError) as exc:
            errors.append(f"Python parse failure in {path.relative_to(ROOT)}: {exc}")

    main_source = (ROOT / "main.py").read_text(encoding="utf-8")
    app = (PACKAGE / "app.py").read_text(encoding="utf-8")
    config_source = (PACKAGE / "config.py").read_text(encoding="utf-8")
    installer = (PACKAGE / "installer.py").read_text(encoding="utf-8")
    install_inspection = (PACKAGE / "install_inspection.py").read_text(encoding="utf-8")
    registry = (PACKAGE / "registry.py").read_text(encoding="utf-8")
    wizard = (PACKAGE / "install_wizard.py").read_text(encoding="utf-8")
    appimage_wizard = (PACKAGE / "appimage_wizard.py").read_text(encoding="utf-8")
    appimage_inspection = (PACKAGE / "appimage_inspection.py").read_text(encoding="utf-8")
    runtime_paths = (PACKAGE / "runtime_paths.py").read_text(encoding="utf-8")
    storage = (PACKAGE / "storage_layout.py").read_text(encoding="utf-8")
    migration = (PACKAGE / "storage_migration.py").read_text(encoding="utf-8")

    check("dispatch_paths_silently" in main_source and "from suite_pythoine.app import main" in main_source, "Silent-dispatch boundary missing", errors)
    check(main_source.index("dispatch_paths_silently") < main_source.index("from suite_pythoine.app import main"), "GUI import precedes silent dispatch", errors)
    check('"--diagnose-routing"' in main_source and "diagnose_routing" in main_source, "Permanent non-GUI routing diagnostic is missing", errors)
    check("maybe_exec_preferred_portable" not in main_source, "Legacy Suite self-runtime bootstrap is still active in main.py", errors)
    check('COMPONENTS_ROOT_ENVIRONMENT_VARIABLE = "SUITE_PYTHOINE_COMPONENTS_ROOT"' in runtime_paths, "Components-root override missing", errors)
    check('DEFAULT_COMPONENTS_FOLDER_NAME = "Suite Pythoine"' in storage and 'LEGACY_DEFAULT_EDITORS_FOLDER_NAME = "Suite Pythoine Editors"' in storage, "Canonical/legacy component-root boundary missing", errors)
    check('PORTABLE_FOLDER_NAME = "Portable"' in storage and 'APPIMAGE_FOLDER_NAME = "AppImage"' in storage, "Versioned storage leaves missing", errors)
    check("appimage_filename(" in storage and 'f"{artifact_application_name(name)}-{version_folder_name(version)}-{normalized_architecture(architecture)}.AppImage"' in storage, "Versioned AppImage naming missing", errors)
    check('return f"io.github.brunonlinespace.{_safe_id(editor_id)}"' in (PACKAGE / "managed_registry.py").read_text(encoding="utf-8"), "Full desktop ID convention missing", errors)
    check('return applications / f"io.github.brunonlinespace.{_safe_stem(editor_id)}.desktop"' in installer, "Desktop filename convention missing", errors)
    check('QAction("Open Components Folder"' in app and 'QAction("Open Installed Editors Folder"' not in app, "Tools menu component-root action missing", errors)
    check('form.addRow("Components folder:"' in app, "Preferences Components-folder row missing", errors)
    check('runtime_group_layout.addRow("Launch runtime:"' in app, "Launch runtime terminology missing from Runtime Preferences", errors)
    check('self.tabs.addTab(routing_page, "File Routing")' in app and "Reset Routing Choices" in app, "File Routing preferences/reset UI missing", errors)
    check('self.tabs.addTab(general, "General")' in app and 'self.tabs.addTab(runtime_page, "Runtime")' in app and 'self.tabs.addTab(versions_page, "Versions")' in app and 'self.tabs.addTab(information_page, "Information")' in app, "Five-tab Suite Preferences management surface missing", errors)
    suite_details_source = app.split("    def _suite_details_page", 1)[1].split("    def _installed_applications_page", 1)[0]
    installed_apps_source = app.split("    def _installed_applications_page", 1)[1].split("    def _record_navigation", 1)[0]
    check('self._populate_editor_details(layout, self.suite_entry)' in suite_details_source and 'Installed Applications' not in suite_details_source, "Suite Details did not split cleanly from Installed Applications", errors)
    check('inventory_heading = QLabel("Installed Applications")' in installed_apps_source and 'self._inventory_records()' in installed_apps_source and 'self.inventory_table = table' in installed_apps_source, "Dedicated Installed Applications inventory page is incomplete", errors)
    check('table.setMaximumHeight(360)' not in installed_apps_source and 'table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)' in installed_apps_source and 'layout.addWidget(table, 1)' in installed_apps_source, "Installed Applications table does not maximize available vertical space", errors)
    check('install_component = QPushButton("Install Component…")' in installed_apps_source and 'install_component.clicked.connect(self.install_editor_prompt)' in installed_apps_source and installed_apps_source.index('install_component = QPushButton("Install Component…")') < installed_apps_source.index('refresh = QPushButton("Refresh Inventory")'), "Installed Applications Install Component action missing beside Refresh Inventory", errors)
    check('"Application", "Version", "Runtime"' in app and '"runtime": "Portable"' in app and '"runtime": "AppImage"' in app, "Installed Applications is not split into per-runtime rows", errors)
    check('old_label = "Installed as"' in app and 'new_label = "Runtime"' in app, "Installed Applications header-layout migration missing", errors)
    check('frame.setMaximumWidth(250)' in app and 'self.splitter.setCollapsible(0, True)' in app and 'sidebar_size = max(0, min(int(sizes[0]), 250))' in app, "Sidebar 250 px upper-bound/collapse guard missing", errors)
    check('Open Components Folder' in app and 'Repair Desktop Integration' in app and 'Open Installed Folder' in app and 'Open Version Folder' in app, "Suite management quick actions missing from Details/Preferences", errors)
    check('self.launch_action = QAction("Launch…", self)' in app and 'self.launch_action.setShortcut("F4")' in app and 'self.launch_action.triggered.connect(self.launch_prompt)' in app, "Global Launch F4 action missing", errors)
    check('def launch_prompt(self)' in app and 'app_dialog_title("Launch")' in app and '"Launch application:"' in app and 'not is_hub(component)' in app, "Global Launch chooser contract missing", errors)
    check('self.dashboard_action.setShortcut("Ctrl+W")' in app, "Dashboard Ctrl+W shortcut missing", errors)
    check('self.refresh_action = QAction("Refresh Components"' in app and 'self.refresh_action.setShortcut("F5")' in app, "Refresh Components F5 shortcut missing", errors)
    check('self.open_components_folder_action.setShortcut("Ctrl+Shift+O")' in app, "Open Components Folder shortcut missing", errors)
    check('self.install_action.setShortcut("Ctrl+Shift+N")' in app and 'QAction("Install Component…"' in app, "Install Component shortcut/label missing", errors)
    check('self.sidebar_action.setShortcut("F9")' in app, "Show Sidebar F9 shortcut missing", errors)
    check('self.toggle_view_shortcut_action = QAction("Toggle List/Grid View", self)' in app and 'self.toggle_view_shortcut_action.setShortcut("Ctrl+Alt+Shift+D")' in app and 'view.addAction(self.toggle_view_shortcut_action)' not in app and 'dashboard_settings.addAction(self.toggle_view_shortcut_action)' not in app and 'self.view_button = QPushButton' not in (PACKAGE / "dashboard.py").read_text(encoding="utf-8"), "Keyboard-only List/Grid toggle contract is not preserved", errors)
    check('dashboard_settings = view.addMenu("Dashboard Settings")' in app and 'dashboard_settings.addAction(self.list_action)' in app and 'dashboard_settings.addAction(self.grid_action)' in app and 'dashboard_settings.addAction(self.icons_action)' in app and 'dashboard_settings.addAction(self.drop_bar_action)' in app, "Dashboard Settings submenu contract missing", errors)
    check(app.index('view.addAction(self.refresh_action)') < app.index('view.addAction(self.dashboard_action)') < app.index('dashboard_settings = view.addMenu("Dashboard Settings")'), "View menu Refresh/Dashboard/Dashboard Settings order is incorrect", errors)
    check('self.icons_action.setShortcut("Ctrl+Alt+Shift+I")' in app and 'self.drop_bar_action.setShortcut("Ctrl+Alt+Shift+B")' in app, "Dashboard icon/drop-bar shortcuts missing", errors)
    check('self.preferences_action.setShortcut("Ctrl+/")' in app, "Preferences Ctrl+/ shortcut missing", errors)
    check('Open Components Folder  (Ctrl+Shift+O)' in app and 'Show application icons on Dashboard  (Ctrl+Alt+Shift+I)' in app and 'Show Drop Bar  (Ctrl+Alt+Shift+B)' in app and 'Toggle List/Grid view: Ctrl+Alt+Shift+D' in app and 'Enable Developer Intake Mode  (F12)' in app, "Preferences does not expose applicable shortcuts explicitly", errors)
    check('self.search_action.setShortcut("Ctrl+F")' in app, "Dashboard search focus shortcut missing", errors)
    check('self.shortcuts_action.setShortcut("Ctrl+Shift+/")' in app, "Keyboard Shortcuts action missing", errors)
    check('store_btn = QPushButton("Get More...")' in app, "Sidebar Get More label missing", errors)
    check('self.show_dashboard()\n        self.dashboard.set_view_mode(mode)' in app, "List/Grid actions do not return to Dashboard", errors)
    check('app_dialog_title("Choose Application")' in app and 'app_dialog_title("Choose Application")' in (PACKAGE / "routing_chooser.py").read_text(encoding="utf-8"), "Routing chooser still uses Editor-only wording", errors)
    check('("Preferences…", self.general_preferences' in app and 'suite_override["launch_mode"]' in app, "Suite-specific Preferences experiences were not merged", errors)
    dashboard_source = (PACKAGE / "dashboard.py").read_text(encoding="utf-8")
    dashboard_actions_source = dashboard_source.split("        actions = QHBoxLayout()", 1)[1].split("        self.list_scroll = QScrollArea()", 1)[0]
    check('launch = QPushButton("Launch…")' in dashboard_actions_source and dashboard_actions_source.index('launch = QPushButton("Launch…")') < dashboard_actions_source.index('new_file = QPushButton("New File…")'), "Dashboard Launch button is missing or not immediately before New File", errors)
    check(dashboard_actions_source.index('install_editor = QPushButton("Install Component…")') < dashboard_actions_source.index('installed_applications = QPushButton("Installed Applications")') < dashboard_actions_source.index('details = QPushButton("Details")'), "Installed Applications button is not between Install Component and Details", errors)
    check('installed_applications_requested = pyqtSignal()' in dashboard_source and 'self.dashboard.installed_applications_requested.connect(self.show_installed_applications)' in app, "Installed Applications Dashboard signal/wiring missing", errors)
    check('installed_applications_page.setProperty("editor_root", "__installed_applications__")' in app and 'def show_installed_applications(self)' in app and 'self._record_navigation("installed-applications")' in app and 'if target == "installed-applications"' in app, "Installed Applications navigation/refresh preservation contract missing", errors)
    card_source = dashboard_source.split("class EditorCard", 1)[1].split("class EditorDashboard", 1)[0]
    check(card_source.count("root = QVBoxLayout(self)") == 1, "EditorCard installs more than one top-level layout", errors)
    check('actions.append(("New…", self.new_requested))' in card_source and 'else:\n            actions.append(("Launch", self.launch_requested))' in card_source, "Dashboard Editor New/non-Editor Launch split missing", errors)
    editor_details_source = app.split('if editor.component_kind == "editor":', 1)[1].split('elif editor.component_kind == "reader":', 1)[0]
    check('("New File…"' in editor_details_source and '("Open File…"' in editor_details_source and '("Launch"' not in editor_details_source, "Editor Details still exposes redundant Launch or lost New/Open", errors)
    check('("Launch", lambda: self.launch_editor(editor)' in app.split('elif editor.component_kind == "reader":', 1)[1], "Reader/Extension Launch was accidentally removed", errors)
    new_method = app.split("    def create_file_for_editor", 1)[1].split("    def open_with_editor_prompt", 1)[0]
    check("can_create_document(editor)" in new_method and "self.launch_editor(editor)" in new_method, "Editor New capability guard/native launch handoff missing", errors)
    check("QFileDialog" not in new_method and ".touch(" not in new_method and "mkdir(" not in new_method and "write_" not in new_method, "Suite Editor New path has regained document/file creation ownership", errors)
    check('("Editors", editors)' in dashboard_source and '("Readers", readers)' in dashboard_source and '("Extensions", extensions)' in dashboard_source, "Dashboard does not group Editors, Readers and Extensions", errors)
    check('self.editor_list.setIconSize(QSize(26, 26))' in app and 'item.setSizeHint(QSize(0, 38))' in app, "Larger sidebar component rows missing", errors)
    check('add_sidebar_group("EDITORS", self.editors)' in app and 'add_sidebar_group("READERS", self.readers)' in app and 'add_sidebar_group("EXTENSIONS", self.extensions)' in app, "Sidebar does not group Editors, Readers and Extensions", errors)
    check('app_dialog_title("Preferences")' in app and 'Preferences" if is_hub' not in app and 'f"{editor.name} Preferences"' not in app and 'app_dialog_title("Suite Pythoine Preferences")' not in app, "Preferences title does not follow the central window-title policy", errors)
    check('class StorageMigrationWizard(QWizard)' in (PACKAGE / "migration_wizard.py").read_text(encoding="utf-8"), "Storage migration wizard missing", errors)
    check("build_migration_plan(" in app and "maybe_offer_storage_migration" in app, "Storage migration is not wired into app startup", errors)
    check("Existing files are copied into the new layout first" in (PACKAGE / "migration_wizard.py").read_text(encoding="utf-8"), "Migration safety explanation missing", errors)
    check("destination=self.options.destination" in wizard, "Install wizard does not target versioned Portable directory", errors)
    check("name=self.editor.name" in wizard and "version=self.installed_version or self.editor.source_version" in wizard, "AppImage install does not use application/version identity", errors)
    check("class EditorVersionInfo" in registry and "_discover_unregistered_appimages" in registry and "active_version" in registry and "desktop_version" in registry, "Intelligent multi-version inventory missing", errors)
    check("REGISTRY_SCHEMA = 2" in (PACKAGE / "managed_registry.py").read_text(encoding="utf-8") and '"versions"' in (PACKAGE / "managed_registry.py").read_text(encoding="utf-8"), "Version-aware managed registry schema missing", errors)
    for label in ("Launch Portable", "Launch AppImage", "Make Active", "Remove Version…"):
        check(label in app, f"Version-management UI action missing: {label}", errors)
    for mode in ("upgrade_remove", "upgrade_alongside", "downgrade_alongside", "downgrade_remove"):
        check(mode in wizard, f"Install/update mode missing: {mode}", errors)
    check("Apply version-management policy" in wizard, "Version-management policy step missing", errors)
    check("TemporaryDirectory" not in install_inspection and "safe_extract_zip" not in install_inspection, "ZIP inspection still performs a full temporary extraction", errors)
    check("extract_editor_zip_to_staging" in installer and "preflight_archive_install" in installer and "shutil.copytree(source_root, staged)" not in installer, "Single-pass staged ZIP installation missing", errors)
    check("errno.EDQUOT" in installer and "errno.ENOSPC" in installer and "storage quota was reached" in installer, "Friendly quota/full-filesystem translation missing", errors)
    check("Keep temporary AppImage build files if the build fails" in wizard and "clean_build_dirs(self.editor_root)" in wizard, "Failed-build cleanup choice missing", errors)
    check("_scrollable_page_layout" in wizard and "_scrollable_page_layout" in appimage_wizard and "self.resize(980, 800)" in wizard and "self.resize(980,800)" in appimage_wizard, "Scroll-resilient default install-wizard geometry missing", errors)
    check("def prune_empty_version_tree" in storage and "prune_empty_version_tree(app_path.parent.parent" in app, "Empty AppImage/version container pruning missing", errors)
    check('runtime_badge = "AppImage" if self.runtime.running_as_appimage else ("Portable"' in app and '[{runtime_badge}]' in app, "About runtime-format bracket missing", errors)
    check("complete_pending_self_cleanup" in main_source and "pending_self_cleanup" in (PACKAGE / "self_update.py").read_text(encoding="utf-8"), "Protected self-update cleanup hook missing", errors)
    store_bridge_source = (PACKAGE / "store_bridge.py").read_text(encoding="utf-8")
    check("handle_store_protocol_cli" in main_source and "ensure_control_bridge" in main_source, "Store Pythoine control protocol is not wired before GUI startup", errors)
    for flag in ("--store-protocol-version", "--managed-list", "--inspect-package", "--install-package", "--source", "--wizard"):
        check(flag in store_bridge_source, f"Store protocol flag missing: {flag}", errors)
    check('source != "store"' in store_bridge_source and 'from .app import run_store_install_wizard' in store_bridge_source, "Store install protocol does not require the trusted Store source/full wizard path", errors)
    check("run_store_install_wizard" in app and "install_editor_zip(package, store_download=True)" in app and "install_editor_appimage(package)" in app, "Store transactions do not reuse Suite's full normal installers", errors)

    # Hub boundary and dangerous primitive scan.
    for forbidden in ("class CodeEditor", "QTextEdit(", "save_module_code", "has_unsaved_changes"):
        check(forbidden not in app and forbidden not in wizard and forbidden not in appimage_wizard, f"Embedded editor implementation found: {forbidden}", errors)
    check("self.output.setReadOnly(True)" in wizard, "Build output console is not read-only", errors)
    check("self.result_label.setSizePolicy" in wizard and "_grow_wizard_for_output" in wizard and "self.steps.setMaximumHeight(155)" not in wizard, "Progress-page technical-details geometry guard missing", errors)
    check('path.suffix.casefold() == ".appimage"' in app and "install_editor_appimage" in app, "Direct AppImage routing/install path missing", errors)
    check('QAction("Install Component…"' in app and 'app_dialog_title("Install Component")' in app and "AppImage bundles (*.AppImage *.appimage)" in app, "Combined ZIP/AppImage component install picker missing", errors)
    check("class AppImageInstallWizard(QWizard)" in appimage_wizard and "versions_to_remove" in appimage_wizard, "Direct AppImage wizard/version policy missing", errors)
    check("synchronize_desktop_integration" in wizard and "synchronize_desktop_integration" in appimage_wizard, "Install paths do not use verified desktop integration synchronization", errors)
    check("synchronize_portable_desktop_integration" in app and "repair_suite_desktop_integration" in app, "Suite active Portable runtime does not own desktop integration directly", errors)
    check("Qt.Key.Key_Backspace" in app and "_navigate_back" in app, "Backspace Suite navigation is missing", errors)
    dev_intake_source = (PACKAGE / "developer_intake.py").read_text(encoding="utf-8")
    check('paste_button = QPushButton("Paste")' in dev_intake_source and "self.notes.paste()" in dev_intake_source, "Developer Intake Paste action is missing", errors)
    check(COMPONENT_PROFILES["beespector"].kind == "reader" and not COMPONENT_PROFILES["beespector"].is_routable and can_open_document(COMPONENT_PROFILES["beespector"]), "Beespector Reader/no-routing semantics mismatch", errors)
    check(COMPONENT_PROFILES["beespector-lite"].kind == "reader" and not COMPONENT_PROFILES["beespector-lite"].is_routable and can_open_document(COMPONENT_PROFILES["beespector-lite"]), "Beespector Lite Reader/no-routing semantics mismatch", errors)
    check("inspector_fallback_preference" in config_source and "_try_inspector_fallback" in app and "if not candidates:" in app, "Unsupported-file Beespector fallback wiring missing", errors)
    check("icon_relative" in install_inspection and "_icon_quality_bonus" in install_inspection and "Wizard icon source:" in wizard, "Installer icon quality/source diagnostics missing", errors)
    check(COMPONENT_PROFILES["gitten"].name == "gitten" and "gitten-pad" in COMPONENT_PROFILES["gitten"].identity_hints, "gitten canonical/legacy identity boundary mismatch", errors)
    check(COMPONENT_PROFILES["linspectacles"].name == "Linspectacles" and "linspector-suite" in COMPONENT_PROFILES["linspectacles"].identity_hints, "Linspectacles canonical/legacy identity boundary mismatch", errors)
    check(all(COMPONENT_PROFILES[item].kind == "extension" and not COMPONENT_PROFILES[item].is_routable and not COMPONENT_PROFILES[item].can_create for item in ("marko-plus", "rico-plus")), "Plus applications unexpectedly participate in document routing/create", errors)
    shortcuts_source = (PACKAGE / "shortcuts_dialog.py").read_text(encoding="utf-8")
    check('"control": "ctrl"' in shortcuts_source and '"ctl": "ctrl"' in shortcuts_source and "token in shortcut_tokens for token in query_tokens" in shortcuts_source, "Marko Plus shortcut fuzzy/token matching was not preserved", errors)
    check("QApplication.instance().installEventFilter(self)" in app and "self.dashboard.search.insert(text)" in app, "Dashboard type-to-search wiring missing", errors)
    check('Use the verified installed AppImage as this component\'s launch runtime' in wizard and 'preserve_portable' in wizard, "Source installer does not preserve an explicit Portable launch runtime by default", errors)
    check('override["launch_mode"] = "installed"' not in appimage_wizard, "Direct AppImage adoption still overwrites the existing launch runtime preference", errors)
    check("could not identify this AppImage" in appimage_inspection and "appimage_sha256" in appimage_inspection, "Direct AppImage identity/hash inspection missing", errors)
    check('details.addRow("Editor ID:", _plain_label(inspection.publisher_id' in wizard, "Installer Editor ID does not display publisher identity", errors)
    check("def make_version_active" in app and app.count("synchronize_desktop_integration(") >= 2 and "set_desktop_version(" in app, "Make Active/Repair do not share verified desktop integration synchronization", errors)
    check('details.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)' in wizard, "Installer identity fields can collapse", errors)
    check('layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)' in wizard, "Installer branding icon is not top-aligned", errors)
    check('GenericName=File Editor Hub' in (PACKAGE / "packaging" / "appimage" / "suite-pythoine.desktop").read_text(encoding="utf-8"), "Desktop GenericName is not File Editor Hub", errors)
    check('Suite Pythoine: a little Python, sweetly caffeinated.' in app, "Updated About caffeine wording missing", errors)
    check('QApplication.activeModalWidget() or self' in app and 'WA_DeleteOnClose' in app and 'buttons.accepted.connect(dialog.accept)' in app, "About dialog modal-parent/cleanup fix missing", errors)
    check(not (PACKAGE / "store_page.py").exists() and not (PACKAGE / "store_policy.py").exists() and not (PACKAGE / "catalog_service.py").exists(), "Built-in Store implementation still ships inside Suite", errors)
    check((PACKAGE / "store_bridge.py").is_file(), "Store Pythoine control bridge module missing", errors)

    for path in PACKAGE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
                errors.append(f"Dynamic code primitive {node.func.id}() in {path.name}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "os" and node.func.attr == "system":
                    errors.append(f"os.system() in {path.name}")
                if node.func.attr in {"Popen", "run", "call", "check_call", "check_output"}:
                    for keyword in node.keywords:
                        if keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
                            errors.append(f"subprocess shell=True in {path.name}")

    for shell_file in PACKAGE.rglob("*.sh"):
        shell = shell_file.read_text(encoding="utf-8")
        check(not re.search(r"(?m)^\s*(?:sudo|dnf|pkexec|su)(?:\s|$)", shell), f"Privileged command in {shell_file.relative_to(ROOT)}", errors)

    expected_extensions = {
        ".txt", ".log", ".ini", ".cfg", ".conf", ".md", ".markdown", ".mdown", ".mkd", ".rtf",
        ".tex", ".bib", ".pdf", ".epub", ".py", ".sh", ".html", ".htm", ".css",
        ".js", ".mjs", ".cjs", ".ts", ".mts", ".cts", ".jsx", ".tsx",
    }
    check(set(PAD_FAMILY_EXTENSIONS) == expected_extensions, "Pad-family extension union changed", errors)
    desktop = (PACKAGE / "packaging/appimage/suite-pythoine.desktop").read_text(encoding="utf-8")
    check("Exec=suite-pythoine %F" in desktop and "StartupNotify=false" in desktop, "Suite AppImage desktop dispatch contract changed", errors)
    mime_line = next((line for line in desktop.splitlines() if line.startswith("MimeType=")), "")
    desktop_mimes = {x for x in mime_line.partition("=")[2].split(";") if x}
    check(desktop_mimes == set(PAD_FAMILY_MIME_TYPES), "AppImage desktop MIME union mismatch", errors)


def _write_portable_fixture(root: Path, name: str, version: str, editor_id: str, extensions: list[str], *, inner: str | None = None) -> Path:
    target = portable_root(root, name, version)
    target.mkdir(parents=True)
    (target / "main.py").write_text("print('fixture')\n", encoding="utf-8")
    if inner:
        (target / inner).mkdir()
    (target / "suite-pythoine.json").write_text(json.dumps({
        "id": editor_id, "name": name, "version": version, "extensions": extensions, "portable_command": ["main.py"]
    }), encoding="utf-8")
    return target


def functional_checks(errors: list[str]) -> None:
    with tempfile.TemporaryDirectory(prefix="suite-pythoine-release-check-") as temporary:
        base = Path(temporary)
        editors_root = base / "Suite Pythoine"
        applications = base / ".local/share/applications"
        editors_root.mkdir(parents=True)
        applications.mkdir(parents=True)

        check(app_dialog_title("About") == "About — Suite Pythoine", "Pad-family About title failed", errors)
        check(app_dialog_title("About Suite Pythoine") == "About — Suite Pythoine", "About title duplicated app name", errors)

        _write_portable_fixture(
            editors_root, "Suite Pythoine", EXPECTED_VERSION, "suite-pythoine",
            [".txt", ".log", ".ini", ".cfg", ".conf", ".md", ".markdown", ".mdown", ".mkd", ".rtf", ".tex", ".bib", ".pdf", ".epub", ".py", ".sh", ".html", ".htm", ".css", ".js", ".mjs", ".cjs", ".ts", ".mts", ".cts", ".jsx", ".tsx"],
        )
        _write_portable_fixture(editors_root, "Nuxpad 2", "2.7.2", "nuxpad", [".txt", ".log", ".ini", ".cfg", ".conf"])
        _write_portable_fixture(editors_root, "Markopad", "0.0.2", "markopad", [".md", ".markdown", ".mdown", ".mkd"], inner="markopad")
        rico = _write_portable_fixture(editors_root, "Ricopad", "0.6.7", "ricopad", [".rtf"], inner="ricopad")
        builder = rico / "ricopad/packaging/fedora/build-appimage.sh"
        builder.parent.mkdir(parents=True, exist_ok=True)
        builder.write_text('#!/usr/bin/env bash\nAPP_VERSION="0.6.7"\nAPPIMAGE="$DIST_DIR/Ricopad-${APP_VERSION}-x86_64.AppImage"\nappimagetool "$APPDIR" "$APPIMAGE"\n', encoding="utf-8")
        _write_portable_fixture(editors_root, "Portapad", "0.0.1-rc10", "portapad", [".pdf"])
        _write_portable_fixture(editors_root, "Kapitulindo", "0.0.1-exp3.2", "kapitulindo", [".epub"])
        _write_portable_fixture(editors_root, "Sheepy Pad", "0.0.1", "sheepy-pad", [".py", ".sh"])
        _write_portable_fixture(editors_root, "Timblee Pad", "0.0.1-r6", "timblee-pad", [".html", ".htm", ".css"])
        _write_portable_fixture(editors_root, "Texypad", "0.0.1-exp4", "texypad", [".tex", ".bib"])
        _write_portable_fixture(editors_root, "JSTS Pad", "0.0.1-exp1", "jsts-pad", [".js", ".mjs", ".cjs", ".ts", ".mts", ".cts", ".jsx", ".tsx"])
        _write_portable_fixture(editors_root, "Beespector", "0.0.1", "beespector", [])
        _write_portable_fixture(editors_root, "Beespector Lite", "0.0.1", "beespector-lite", [])
        _write_portable_fixture(editors_root, "Linspectacles", "0.0.3", "linspectacles", [])
        _write_portable_fixture(editors_root, "Marko Plus", "0.0.1-r3", "marko-plus", [])
        _write_portable_fixture(editors_root, "Rico Plus", "0.0.1-r4-r3", "rico-plus", [])
        _write_portable_fixture(editors_root, "Crawlindo", "0.1.1", "crawlindo", [])
        _write_portable_fixture(editors_root, "Youlindo", "0.0.1-exp18", "youlindo", [])
        _write_portable_fixture(editors_root, "Sbookypad", "0.1.0", "sbookypad", [])
        _write_portable_fixture(editors_root, "gitten", "0.0.1", "gitten", [])
        _write_portable_fixture(editors_root, "Python Lair", "3.1", "python-lair", [])
        _write_portable_fixture(editors_root, "Store Pythoine", "0.0.1-exp1", "store-pythoine", [])

        editors = discover_editors(editors_root, editors_root, {}, python_executable="/usr/bin/python3")
        check([e.name for e in editors] == ["Beespector", "Beespector Lite", "Crawlindo", "gitten", "JSTS Pad", "Kapitulindo", "Linspectacles", "Marko Plus", "Markopad", "Nuxpad 2", "Portapad", "Python Lair", "Rico Plus", "Ricopad", "Sbookypad", "Sheepy Pad", "Store Pythoine", "Suite Pythoine", "Texypad", "Timblee Pad", "Youlindo"], "Built-in component discovery mismatch", errors)
        suite_component = next(e for e in editors if e.editor_id == "suite-pythoine")
        check(is_hub(suite_component) and not is_document_editor(suite_component), "Suite is not classified exclusively as Hub", errors)
        expected_routes = {
            ".txt": "Nuxpad 2", ".log": "Nuxpad 2", ".ini": "Nuxpad 2", ".cfg": "Nuxpad 2", ".conf": "Nuxpad 2",
            ".md": "Markopad", ".markdown": "Markopad", ".mdown": "Markopad", ".mkd": "Markopad", ".rtf": "Ricopad",
            ".tex": "Texypad", ".bib": "Texypad", ".pdf": "Portapad", ".epub": "Kapitulindo", ".py": "Sheepy Pad", ".sh": "Sheepy Pad", ".html": "Timblee Pad", ".htm": "Timblee Pad", ".css": "Timblee Pad",
            ".js": "JSTS Pad", ".mjs": "JSTS Pad", ".cjs": "JSTS Pad", ".ts": "JSTS Pad", ".mts": "JSTS Pad", ".cts": "JSTS Pad", ".jsx": "JSTS Pad", ".tsx": "JSTS Pad",
        }
        for extension, expected in expected_routes.items():
            check([e.name for e in document_candidates(editors, extension)] == [expected], f"Routing mismatch for {extension}", errors)

        discovered_extensions = [entry for entry in editors if entry.component_kind == "extension"]
        check({entry.editor_id for entry in discovered_extensions} == {"linspectacles", "marko-plus", "rico-plus", "crawlindo", "youlindo", "sbookypad", "gitten", "python-lair", "store-pythoine"}, "Extension discovery/classification mismatch", errors)
        check(all(not entry.extensions for entry in discovered_extensions), "Extension discovery acquired routed formats", errors)
        discovered_readers = [entry for entry in editors if is_reader(entry)]
        check({entry.editor_id for entry in discovered_readers} == {"kapitulindo", "portapad", "beespector-lite", "beespector"}, "Reader discovery/classification mismatch", errors)
        check(all(can_open_document(entry) and not can_create_document(entry) for entry in discovered_readers), "Reader open/create capabilities mismatch", errors)
        check(all(not can_route_document(entry) for entry in discovered_readers if entry.editor_id in {"beespector", "beespector-lite"}), "Beespector readers unexpectedly acquired OS/document routing", errors)

        # Unsupported-file inspection fallback is strictly post-routing. A valid
        # routed component must win without Beespector ever entering candidates.
        routed_target = RoutingTarget(
            component_id="markopad", name="Markopad", kind="editor", extensions=(".fixture",),
            launch_mode="auto", portable_command=("/bin/true",), installed_command=None,
            portable_root=None, active_version="1", capabilities=("routing", "open", "create"),
        )
        bee_target = RoutingTarget(
            component_id="beespector", name="Beespector", kind="reader", extensions=(),
            launch_mode="auto", portable_command=("/bin/true",), installed_command=None,
            portable_root=None, active_version="1", capabilities=("open",),
        )
        lite_target = RoutingTarget(
            component_id="beespector-lite", name="Beespector Lite", kind="reader", extensions=(),
            launch_mode="auto", portable_command=("/bin/true",), installed_command=None,
            portable_root=None, active_version="1", capabilities=("open",),
        )
        routed_file = base / "normal.fixture"; routed_file.write_text("route", encoding="utf-8")
        unknown_file = base / "unknown.bin"; unknown_file.write_bytes(b"inspect")
        launched_ids: list[str] = []
        def fake_launch(target, path=None):
            launched_ids.append(target.component_id)
            return True, None
        with patch.object(silent_dispatch_module, "load_config", return_value={"inspector_fallback_preference": INSPECTOR_FALLBACK_ASK}), \
             patch.object(silent_dispatch_module, "load_routing_targets", return_value=([routed_target, bee_target, lite_target], editors_root, True)), \
             patch.object(silent_dispatch_module, "_launch", side_effect=fake_launch):
            dispatch = dispatch_paths_silently([routed_file])
        check(launched_ids == ["markopad"] and dispatch.launched == (routed_file.resolve(),) and not dispatch.inspector_choices, "Beespector fallback interfered with a valid routed candidate", errors)

        launched_ids.clear()
        with patch.object(silent_dispatch_module, "load_config", return_value={"inspector_fallback_preference": INSPECTOR_FALLBACK_ASK}), \
             patch.object(silent_dispatch_module, "load_routing_targets", return_value=([bee_target, lite_target], editors_root, True)), \
             patch.object(silent_dispatch_module, "_launch", side_effect=fake_launch):
            dispatch = dispatch_paths_silently([unknown_file])
        check(not launched_ids and len(dispatch.inspector_choices) == 1 and {c.component_id for c in dispatch.inspector_choices[0].candidates} == {"beespector", "beespector-lite"}, "Unsupported file did not produce the remembered-choice inspector fallback chooser", errors)

        launched_ids.clear()
        with patch.object(silent_dispatch_module, "load_config", return_value={"inspector_fallback_preference": "beespector"}), \
             patch.object(silent_dispatch_module, "load_routing_targets", return_value=([bee_target, lite_target], editors_root, True)), \
             patch.object(silent_dispatch_module, "_launch", side_effect=fake_launch):
            dispatch = dispatch_paths_silently([unknown_file])
        check(launched_ids == ["beespector"] and dispatch.launched == (unknown_file.resolve(),), "Remembered Beespector fallback was not honored", errors)

        launched_ids.clear()
        with patch.object(silent_dispatch_module, "load_config", return_value={"inspector_fallback_preference": "beespector"}), \
             patch.object(silent_dispatch_module, "load_routing_targets", return_value=([lite_target], editors_root, True)), \
             patch.object(silent_dispatch_module, "_launch", side_effect=fake_launch):
            dispatch = dispatch_paths_silently([unknown_file])
        check(launched_ids == ["beespector-lite"] and dispatch.launched == (unknown_file.resolve(),), "Unavailable remembered inspector did not fall back to the only available inspector", errors)

        with patch.object(silent_dispatch_module, "load_config", return_value={"inspector_fallback_preference": INSPECTOR_FALLBACK_ASK}), \
             patch.object(silent_dispatch_module, "load_routing_targets", return_value=([], editors_root, True)):
            dispatch = dispatch_paths_silently([unknown_file])
        check(dispatch.unresolved == (unknown_file.resolve(),) and not dispatch.inspector_choices, "No-inspector case did not retain the normal unresolved/full-Hub fallback", errors)

        # ZIP wizard icon selection: a canonical high-resolution/master asset
        # must beat a tiny exact-basename derivative when no manifest icon is set.
        icon_zip = base / "gitten-icon-selection.zip"
        def fake_png(width: int, height: int) -> bytes:
            return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", width, height) + b"\x08\x06\x00\x00\x00" + b"fixture"
        with zipfile.ZipFile(icon_zip, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("suite-pythoine.json", json.dumps({"id":"gitten", "name":"gitten", "version":"0.0.1"}))
            archive.writestr("main.py", "print('fixture')\n")
            archive.writestr("gitten/assets/icons/gitten.png", fake_png(32, 32))
            archive.writestr("gitten/assets/icons/gitten-master-1024.png", fake_png(1024, 1024))
        icon_inspection = inspect_editor_zip(icon_zip)
        check(icon_inspection.icon_relative == "gitten/assets/icons/gitten-master-1024.png", "Installer did not prefer the canonical high-resolution/master icon", errors)

        manifest_icon_zip = base / "gitten-manifest-icon-selection.zip"
        with zipfile.ZipFile(manifest_icon_zip, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("suite-pythoine.json", json.dumps({"id":"gitten", "name":"gitten", "version":"0.0.1", "icon":"icons/declared.png"}))
            archive.writestr("main.py", "print('fixture')\n")
            archive.writestr("gitten/icons/declared.png", fake_png(64, 64))
            archive.writestr("gitten/assets/icons/gitten-master-1024.png", fake_png(1024, 1024))
        manifest_icon_inspection = inspect_editor_zip(manifest_icon_zip)
        check(manifest_icon_inspection.icon_relative == "gitten/icons/declared.png", "Explicit manifest icon did not remain authoritative across nested package layout", errors)

        # Multiple versions coexist physically but remain one logical Dashboard card.
        _write_portable_fixture(editors_root, "Ricopad", "0.6.6", "ricopad", [".rtf"])
        multi = discover_editors(editors_root, editors_root, {}, python_executable="/usr/bin/python3")
        rico_entry = next(e for e in multi if e.editor_id == "ricopad")
        check(len([e for e in multi if e.editor_id == "ricopad"]) == 1 and rico_entry.source_version == "0.6.7", "Newest version was not selected as one logical editor", errors)
        check(len(rico_entry.versions) == 2 and {item.version for item in rico_entry.versions} == {"0.6.6", "0.6.7"}, "Retained portable versions are hidden from version inventory", errors)
        pinned = discover_editors(editors_root, editors_root, {"editor_overrides": {"ricopad": {"active_version": "0.6.6"}}}, python_executable="/usr/bin/python3")
        check(next(e for e in pinned if e.editor_id == "ricopad").source_version == "0.6.6", "Explicit active_version was ignored", errors)

        # Intelligent install classification and cleanup policy.
        decision = classify_install("2.0", "1.0", ["0.9", "1.0"])
        check(decision.kind == "upgrade" and decision.default_mode == "upgrade_remove", "Upgrade classification/default changed", errors)
        check(versions_to_remove(["0.9", "1.0", "2.0"], "2.0", "upgrade_remove") == ("0.9", "1.0"), "Upgrade cleanup selection failed", errors)
        down = classify_install("1.0", "2.0", ["2.0"])
        check(down.kind == "downgrade" and down.default_mode == "downgrade_alongside", "Downgrade default is not alongside", errors)
        check(versions_to_remove(["1.0", "2.0", "3.0"], "1.0", "downgrade_remove") == ("2.0", "3.0"), "Downgrade cleanup selection failed", errors)


        # Schema-2 registry retains several AppImages while exactly one owns desktop integration.
        mv_config = {"managed_installations": {}}
        mv_root = base / "multi-appimage-root"
        old_dir = appimage_root(mv_root, "Ricopad", "1.0"); old_dir.mkdir(parents=True)
        new_dir = appimage_root(mv_root, "Ricopad", "2.0"); new_dir.mkdir(parents=True)
        old_app = old_dir / "Ricopad-1.0-x86_64.AppImage"; old_app.write_bytes(b"old")
        new_app = new_dir / "Ricopad-2.0-x86_64.AppImage"; new_app.write_bytes(b"new")
        desktop_v2 = applications / "io.github.brunonlinespace.ricopad.desktop"
        desktop_v2.write_text("[Desktop Entry]\nName=Ricopad\n", encoding="utf-8")
        set_managed_installation(mv_config, {
            "editor_id":"ricopad", "application_id":"ricopad", "name":"Ricopad", "publisher_id":"brunonlinespace", "version":"1.0",
            "appimage_path":str(old_app), "appimage_sha256":hashlib.sha256(old_app.read_bytes()).hexdigest(),
            "desktop_file_path":None, "desktop_id":desktop_id_for("ricopad"), "icon_path":None, "extensions":[".md"],
        }, set_active=True, desktop_integrated=False)
        set_managed_installation(mv_config, {
            "editor_id":"ricopad", "application_id":"ricopad", "name":"Ricopad", "publisher_id":"brunonlinespace", "version":"2.0",
            "appimage_path":str(new_app), "appimage_sha256":hashlib.sha256(new_app.read_bytes()).hexdigest(),
            "desktop_file_path":str(desktop_v2), "desktop_id":desktop_id_for("ricopad"), "icon_path":None, "extensions":[".md"],
        }, set_active=True, desktop_integrated=True)
        group = get_managed_group(mv_config, "ricopad")
        versions = get_managed_versions(mv_config, "ricopad")
        check(REGISTRY_SCHEMA == 2 and set(versions) == {"1.0", "2.0"}, "Schema-2 registry did not retain both AppImage versions", errors)
        check(group.get("active_version") == "2.0" and group.get("desktop_version") == "2.0", "Active/desktop version ownership incorrect", errors)
        check(not versions["1.0"].get("desktop_integrated") and versions["2.0"].get("desktop_integrated"), "Desktop integration is not exclusive", errors)
        check(set_active_version(mv_config, "ricopad", "1.0"), "Could not change active version", errors)
        check(get_managed_group(mv_config, "ricopad").get("active_version") == "1.0", "Make-active registry state failed", errors)
        check(set_desktop_version(mv_config, "ricopad", "1.0", applications / "io.github.brunonlinespace.ricopad.desktop"), "Could not switch desktop version", errors)
        switched = get_managed_versions(mv_config, "ricopad")
        check(switched["1.0"].get("desktop_integrated") and not switched["2.0"].get("desktop_integrated"), "Desktop ownership did not move to selected version", errors)
        stale_rico = discover_editors(mv_root, mv_root, mv_config, python_executable="/usr/bin/python3")
        stale_rico_entry = next(e for e in stale_rico if e.editor_id == "ricopad")
        check(stale_rico_entry.extensions == (".rtf",), "Stale managed Ricopad Markdown metadata overrode the current RTF-only catalogue profile", errors)

        # Filesystem truth recovers an older canonical AppImage that a 0.1.x single-version registry forgot.
        lost_root = base / "lost-version-root"
        _write_portable_fixture(lost_root, "Suite Pythoine", "0.1.1", "suite-pythoine", [".txt"])
        _write_portable_fixture(lost_root, "Suite Pythoine", "0.1.2", "suite-pythoine", [".txt"])
        old_lost_dir = appimage_root(lost_root, "Suite Pythoine", "0.1.1"); old_lost_dir.mkdir(parents=True, exist_ok=True)
        old_lost = old_lost_dir / "Suite-Pythoine-0.1.1-x86_64.AppImage"; old_lost.write_bytes(b"old-suite")
        new_lost_dir = appimage_root(lost_root, "Suite Pythoine", "0.1.2"); new_lost_dir.mkdir(parents=True, exist_ok=True)
        new_lost = new_lost_dir / "Suite-Pythoine-0.1.2-x86_64.AppImage"; new_lost.write_bytes(b"new-suite")
        lost_cfg = {"managed_installations": {}}
        set_managed_installation(lost_cfg, {
            "editor_id":"suite-pythoine", "application_id":"suite-pythoine", "name":"Suite Pythoine", "publisher_id":"brunonlinespace", "version":"0.1.2",
            "appimage_path":str(new_lost), "appimage_sha256":hashlib.sha256(new_lost.read_bytes()).hexdigest(),
            "desktop_file_path":str(applications / "io.github.brunonlinespace.suite-pythoine.desktop"), "desktop_id":desktop_id_for("suite-pythoine"), "icon_path":None,
        }, set_active=True, desktop_integrated=True)
        lost = discover_editors(lost_root, lost_root, lost_cfg, python_executable="/usr/bin/python3")
        suite_entry = next(e for e in lost if e.editor_id == "suite-pythoine")
        check({item.version for item in suite_entry.versions} == {"0.1.1", "0.1.2"}, "Forgotten older AppImage version remained hidden", errors)
        old_info = next(item for item in suite_entry.versions if item.version == "0.1.1")
        check(old_info.has_appimage and not old_info.managed_record and not old_info.desktop_integrated, "Unregistered retained AppImage was not exposed honestly", errors)

        # Portable removal is confined to <Application>/<Version>/Portable and rolls back on deletion failure.
        removable = portable_root(editors_root, "Removable Editor", "1.0")
        removable.mkdir(parents=True)
        (removable / "main.py").write_text("print(1)\n", encoding="utf-8")
        removed = remove_portable_editor_folder(removable, editors_root)
        check(removed == removable.resolve(strict=False) and not removable.exists(), "Versioned portable removal failed", errors)
        outside = base / "outside"; outside.mkdir()
        try:
            remove_portable_editor_folder(outside, editors_root)
        except InstallError:
            pass
        else:
            errors.append("Portable removal accepted path outside Editors root")
        rollback = portable_root(editors_root, "Rollback", "1.0"); rollback.mkdir(parents=True); (rollback / "sentinel").write_text("keep")
        with patch("suite_pythoine.installer.shutil.rmtree", side_effect=OSError("injected")):
            try:
                remove_portable_editor_folder(rollback, editors_root)
            except InstallError:
                pass
        check(rollback.is_dir() and (rollback / "sentinel").read_text() == "keep", "Portable rollback failed", errors)

        # Builder discovery and stale-artifact rejection.
        check(find_appimage_build_script(rico) == builder, "Current Ricopad builder not detected", errors)
        check(build_script_version(builder) == "0.6.7", "Builder version not detected", errors)
        check(detect_source_version(rico) == "0.6.7", "Source version not detected", errors)
        build_root = base / "build-root"; script = build_root / "ricopad/packaging/fedora/build-appimage.sh"; script.parent.mkdir(parents=True)
        script.write_text('#!/bin/sh\nAPP_VERSION="1.2.3"\nappimagetool x y\n')
        dist = build_root / "ricopad/dist"; dist.mkdir(parents=True)
        stale = dist / "Ricopad-1.2.2-x86_64.AppImage"; stale.write_bytes(b"old")
        before = snapshot_appimages(build_root)
        fresh = dist / "Ricopad-1.2.3-x86_64.AppImage"; fresh.write_bytes(b"new")
        check(find_built_appimage(build_root, build_script=script, before=before, expected_version="1.2.3") == fresh.resolve(strict=False), "Fresh AppImage not selected", errors)
        check(version_from_filename(fresh) == "1.2.3", "AppImage filename version parsing failed", errors)
        check(version_from_filename(Path("Kapitulindo-0.0.1-exp3.2.1-x86_64.AppImage")) == "0.0.1-exp3.2.1", "Experimental AppImage version suffix was truncated", errors)
        check(version_from_filename(Path("Ricopad-0.3.3-retro-exp1-x86_64.AppImage")) == "0.3.3-retro-exp1", "Multi-part Pad-family version suffix was truncated", errors)
        check(version_from_filename(Path("Portapad-0.0.1-rc4.1-aarch64.AppImage")) == "0.0.1-rc4.1", "RC point version parsing failed", errors)

        # Dashboard search/sort remains pure.
        az = [e.name for e in filter_and_sort_editors(editors, "", "title_az")]
        check(az == sorted(az, key=str.casefold), "Dashboard A-Z sort failed", errors)
        check([e.name for e in filter_and_sort_editors(editors, "pad html", "title_az")] == ["Timblee Pad"], "Dashboard search failed", errors)

        # Store Pythoine is decoupled: Suite ships no online catalogue/browser,
        # and exposes only a small on-demand control protocol.
        check(STORE_PROTOCOL_VERSION == 1, "Store Pythoine protocol version mismatch", errors)
        check("store-pythoine" in COMPONENT_PROFILES and COMPONENT_PROFILES["store-pythoine"].kind == "extension", "Store Pythoine is not a trusted non-routing Extension", errors)
        check(not COMPONENT_PROFILES["store-pythoine"].is_routable and not COMPONENT_PROFILES["store-pythoine"].extensions, "Store Pythoine unexpectedly participates in file routing", errors)
        check("store_state" not in ConfigService.DEFAULTS, "Retired built-in Store preference is still a normal Suite default", errors)
        bridge_source = _bridge_script()
        check("io.github.brunonlinespace.suite-pythoine" in bridge_source and "os.execvpe" in bridge_source and "APPIMAGE" in bridge_source, "Runtime-agnostic Suite control bridge is incomplete", errors)

        # Component catalogue is trusted data rather than hard-coded ecosystem
        # branching. Verified catalogue installation validates schema/publisher
        # and can teach a running Suite about a new Editor without changing code.
        # Catalogue revisions are monotonic: a newer bundled profile supersedes
        # a legacy cached catalogue, while a newer independently published one
        # can supersede the bundled copy.
        check(catalog_revision(BUNDLED_CATALOG_PATH) == 9, "Bundled 0.3.3-r1 catalogue revision is not 9", errors)
        catalogue_source = base / "components-update.json"
        bundled_payload = json.loads((PACKAGE / "components.json").read_text(encoding="utf-8"))
        bundled_payload["catalog_revision"] = catalog_revision(BUNDLED_CATALOG_PATH) + 1
        extra = dict(bundled_payload["components"][-1])
        extra.update({"id": "future-editor", "name": "Future Editor", "kind": "editor", "extensions": [".future"], "mime_types": ["text/x-future"], "identity_hints": ["future-editor"], "appimage_prefixes": ["Future-Editor"], "repository": "brunonlinespace/future-editor", "capabilities": {"routing": True, "open": True, "create": True}})
        bundled_payload["components"] = list(bundled_payload["components"]) + [extra]
        catalogue_source.write_text(json.dumps(bundled_payload), encoding="utf-8")
        catalogue_destination = base / "catalogue-cache/components.json"
        original_profiles = dict(COMPONENT_PROFILES)
        pre_update_index = build_index_payload(editors, editors_root)
        pre_update_fingerprint = catalog_fingerprint()
        try:
            install_verified_catalog(catalogue_source, catalogue_destination)
            check("future-editor" in COMPONENT_PROFILES and ".future" in extension_union(), "Verified component catalogue update was not loaded dynamically", errors)
            check(catalog_fingerprint() != pre_update_fingerprint, "Verified catalogue update did not change the catalogue fingerprint", errors)
            check(load_index({"routing_index": pre_update_index}, editors_root) is None, "Routing index stayed valid after a catalogue-only capability change", errors)
            future_zip = base / "Future-Editor-1.0-source.zip"
            with zipfile.ZipFile(future_zip, "w") as archive:
                archive.writestr("Future-Editor-1.0/main.py", "print('future')\n")
                archive.writestr("Future-Editor-1.0/suite-pythoine-component.json", json.dumps({"id":"future-editor","name":"Future Editor","publisher":"brunonlinespace","version":"1.0","component_kind":"editor","extensions":[".future"]}))
            future_info = inspect_editor_zip(future_zip, python_executable="/usr/bin/python3")
            check(future_info.editor_id == "future-editor" and future_info.component_kind == "editor", "Updated component catalogue was not honored by ZIP inspection without a Hub code update", errors)
            legacy_catalogue = base / "legacy-components.json"
            legacy_payload = json.loads((PACKAGE / "components.json").read_text(encoding="utf-8"))
            legacy_payload.pop("catalog_revision", None)
            legacy_catalogue.write_text(json.dumps(legacy_payload), encoding="utf-8")
            try:
                install_verified_catalog(legacy_catalogue, catalogue_destination)
            except ValueError:
                pass
            else:
                errors.append("Component catalogue anti-downgrade accepted a legacy revision over the newer active catalogue")
        finally:
            COMPONENT_PROFILES.clear(); COMPONENT_PROFILES.update(original_profiles)

        # Explicit runtime choices are strict. Portable/AppImage preferences do
        # not silently substitute the other runtime when the requested form is
        # unavailable. Automatic mode remains the only fallback-capable mode.
        strict_portable = RoutingTarget("strict-portable", "Strict Portable", "editor", (".strict",), "portable", None, ("installed",), None, "1.0")
        strict_installed = RoutingTarget("strict-installed", "Strict Installed", "editor", (".strict",), "installed", ("portable",), None, None, "1.0")
        automatic = RoutingTarget("automatic", "Automatic", "editor", (".strict",), "auto", ("portable",), None, None, "1.0")
        check(strict_portable.command() is None and not strict_portable.available and strict_installed.command() is None and not strict_installed.available and automatic.command() == ("portable",) and automatic.available, "Explicit runtime preference still silently falls back to another runtime", errors)

        # Fresh-config silent dispatch must exclude the Hub even though Suite
        # advertises the OS MIME union. No remembered preference is required
        # when exactly one real Editor supports the file.
        dispatch_root = base / "dispatch-root"
        _write_portable_fixture(dispatch_root, "Suite Pythoine", EXPECTED_VERSION, "suite-pythoine", [".md", ".pdf"])
        _write_portable_fixture(dispatch_root, "Markopad", "0.0.2", "markopad", [".md"])
        target = base / "silent.md"; target.write_text("# silent")
        config_path = base / "dispatch-config.json"
        config_path.write_text(json.dumps({"editors_root": str(dispatch_root), "extension_preferences": {}}))
        calls = []
        class FakePopen:
            def __init__(self, args, **kwargs): calls.append((args, kwargs))
        with patch("suite_pythoine.silent_dispatch.default_config_path", return_value=config_path), patch("suite_pythoine.silent_dispatch.subprocess.Popen", FakePopen):
            result = dispatch_paths_silently([target], ROOT / "main.py")
        check(result.fully_dispatched and not result.choices and len(calls) == 1 and str(target.resolve()) in calls[0][0], "Fresh-config Hub exclusion/silent dispatch failed", errors)

        # The routing cache is fast but never blindly authoritative. A shallow
        # canonical-tree inventory stamp invalidates it when a component/version
        # is added or removed outside the running Hub.
        discovered_for_index = discover_editors(dispatch_root, dispatch_root, {"editor_overrides": {}, "managed_installations": {}}, python_executable="/usr/bin/python3")
        index_payload = build_index_payload(discovered_for_index, dispatch_root)
        check(load_index({"routing_index": index_payload}, dispatch_root) is not None, "Fresh routing index was rejected", errors)
        added = dispatch_root / "Portapad" / "1.0" / "Portable"; added.mkdir(parents=True); (added / "main.py").write_text("print('new')", encoding="utf-8")
        check(load_index({"routing_index": index_payload}, dispatch_root) is None, "Routing index did not invalidate after an out-of-band component change", errors)

        # Full 0.3.3 hot-path matrix: with the Hub registered for the OS MIME
        # union, each canonical file type still routes to the sole real Editor
        # without constructing the Hub. Repeat with both explicit runtime modes.
        matrix = {
            "nuxpad": ".txt",
            "markopad": ".md",
            "ricopad": ".rtf",
            "texypad": ".tex",
            "portapad": ".pdf",
            "kapitulindo": ".epub",
            "sheepy-pad": ".py",
            "timblee-pad": ".html",
        }
        matrix_root = base / "matrix-root"; matrix_root.mkdir()
        matrix_files = []
        for component_id, extension in matrix.items():
            file_path = base / f"matrix-{component_id}{extension}"; file_path.write_text("fixture", encoding="utf-8"); matrix_files.append(file_path)
        launchers = base / "matrix-launchers"; launchers.mkdir()
        def _matrix_config(mode: str) -> tuple[dict, dict[str, str]]:
            components = [{
                "id": "suite-pythoine", "name": "Suite Pythoine", "kind": "hub",
                "extensions": list(matrix.values()), "launch_mode": "auto",
                "portable_command": None, "installed_command": None, "portable_root": None, "active_version": EXPECTED_VERSION, "capabilities": [],
            }]
            expected_commands: dict[str, str] = {}
            for component_id, extension in matrix.items():
                profile = COMPONENT_PROFILES[component_id]
                portable_exe = launchers / f"{component_id}-portable"; portable_exe.write_text("portable", encoding="utf-8")
                installed_exe = launchers / f"{component_id}.AppImage"; installed_exe.write_text("installed", encoding="utf-8")
                components.append({
                    "id": component_id, "name": profile.name, "kind": profile.kind, "extensions": [extension],
                    "capabilities": list(profile.capabilities),
                    "launch_mode": mode, "portable_command": [str(portable_exe)], "installed_command": [str(installed_exe)],
                    "portable_root": str(matrix_root), "active_version": "1.0",
                })
                expected_commands[component_id] = str(portable_exe if mode == "portable" else installed_exe)
            return {
                "editors_root": str(matrix_root), "extension_preferences": {},
                "routing_index": {"schema": ROUTING_INDEX_SCHEMA, "components_root": str(matrix_root.resolve(strict=False)), "inventory_stamp": inventory_stamp(matrix_root), "catalog_fingerprint": catalog_fingerprint(), "components": components},
            }, expected_commands
        for matrix_mode in ("portable", "installed"):
            matrix_config, expected_commands = _matrix_config(matrix_mode)
            config_path.write_text(json.dumps(matrix_config), encoding="utf-8")
            calls.clear()
            with patch("suite_pythoine.silent_dispatch.default_config_path", return_value=config_path), patch("suite_pythoine.silent_dispatch.subprocess.Popen", FakePopen):
                matrix_result = dispatch_paths_silently(matrix_files)
            launched_commands = {str(args[0][0]) for args in calls}
            check(matrix_result.fully_dispatched and len(calls) == len(matrix) and launched_commands == set(expected_commands.values()), f"{matrix_mode} fresh-config routing matrix failed", errors)

        # Extensions are managed/launchable components but can never become routing candidates.
        extension_profile = COMPONENT_PROFILES["crawlindo"]
        check(extension_profile.kind == "extension" and extension_profile.extensions == (), "Extension catalogue routing boundary failed", errors)

        # Genuine multi-editor ambiguity uses the compact chooser contract.
        overlap_config = {
            "editors_root": str(dispatch_root),
            "editor_overrides": {"markopad": {"extensions": [".md"]}, "nuxpad": {"extensions": [".md"]}},
            "extension_preferences": {},
        }
        _write_portable_fixture(dispatch_root, "Nuxpad 2", "1.0", "nuxpad", [".txt"])
        config_path.write_text(json.dumps(overlap_config))
        calls.clear()
        with patch("suite_pythoine.silent_dispatch.default_config_path", return_value=config_path), patch("suite_pythoine.silent_dispatch.subprocess.Popen", FakePopen):
            ambiguous = dispatch_paths_silently([target])
        check(len(ambiguous.choices) == 1 and not ambiguous.launched and not calls, "Multi-editor request did not remain pseudo-silent", errors)
        overlap_config["extension_preferences"] = {".md": "markopad"}
        config_path.write_text(json.dumps(overlap_config))
        with patch("suite_pythoine.silent_dispatch.default_config_path", return_value=config_path), patch("suite_pythoine.silent_dispatch.subprocess.Popen", FakePopen):
            remembered = dispatch_paths_silently([target])
        check(remembered.fully_dispatched and len(calls) == 1, "Remembered multi-editor choice did not become silent", errors)
        overlap_config["extension_preferences"] = {".md": ASK_EVERY_TIME}
        config_path.write_text(json.dumps(overlap_config))
        calls.clear()
        with patch("suite_pythoine.silent_dispatch.default_config_path", return_value=config_path), patch("suite_pythoine.silent_dispatch.subprocess.Popen", FakePopen):
            ask_again = dispatch_paths_silently([target])
        check(len(ask_again.choices) == 1 and not calls, "Ask-every-time routing preference was ignored", errors)

        # ZIP inspection remains read-only and safe internal symlinks are materialized.
        wizard_zip = base / "Ricopad-source.zip"
        with zipfile.ZipFile(wizard_zip, "w") as archive:
            archive.writestr("Ricopad/main.py", "print(1)\n")
            archive.writestr("Ricopad/suite-pythoine.json", json.dumps({"id": "ricopad", "name": "Ricopad", "version": "2.0", "extensions": [".md"]}))
            archive.writestr("Ricopad/ricopad/packaging/fedora/build-appimage.sh", '#!/bin/sh\nAPP_VERSION="2.0"\nappimagetool x y\n')
        before_names = sorted(p.name for p in editors_root.iterdir())
        inspection = inspect_editor_zip(wizard_zip, python_executable="/usr/bin/python3")
        check(inspection.editor_id == "ricopad" and inspection.version == "2.0", "ZIP inspection identity failed", errors)
        check(inspection.extensions == (".rtf",), "ZIP inspection trusted stale Ricopad Markdown metadata over the RTF-only catalogue", errors)
        check(inspection.expanded_bytes > 0, "Metadata-only ZIP inspection did not report expanded size", errors)
        check(before_names == sorted(p.name for p in editors_root.iterdir()), "ZIP inspection mutated Editors root", errors)

        # Gitten r4 canonical identity is lowercase ``gitten`` with its manifest
        # inside the immediate application package. The legacy Gitten Pad alias
        # remains recognition-only and must not be required for installation.
        gitten_zip = base / "gitten-0.0.1-r4-source.zip"
        with zipfile.ZipFile(gitten_zip, "w") as archive:
            archive.writestr("gitten/main.py", "print('gitten')\n")
            archive.writestr("gitten/gitten/gitten.json", json.dumps({"id":"gitten","name":"gitten","version":"0.0.1","publisher_id":"brunonlinespace"}))
        gitten_info = inspect_editor_zip(gitten_zip, python_executable="/usr/bin/python3")
        check(gitten_info.editor_id == "gitten" and gitten_info.name == "gitten", "Canonical gitten source ZIP identity/install recognition failed", errors)
        check(gitten_info.component_kind == "extension", "Canonical gitten component family changed unexpectedly", errors)

        # Storage preflight reports useful capacity data without writing the archive.
        class _DiskUsage:
            free = 0
        with patch("suite_pythoine.installer.shutil.disk_usage", return_value=_DiskUsage()):
            try:
                preflight_archive_install(wizard_zip, portable_root(editors_root, "Ricopad", "2.0"))
            except InstallError as exc:
                check("Not enough storage space" in str(exc) and "Estimated source/staging requirement" in str(exc), "Free-space preflight error is not user-facing", errors)
            else:
                errors.append("Free-space preflight accepted zero available bytes")
        unsafe = base / "unsafe.zip"
        with zipfile.ZipFile(unsafe, "w") as archive: archive.writestr("../escape", "x")
        try: import_zip(unsafe, editors_root)
        except InstallError: pass
        else: errors.append("ZIP traversal was accepted")
        sym = base / "safe-symlink.zip"; info = zipfile.ZipInfo("Editor/assets/.DirIcon"); info.create_system = 3; info.external_attr = (0o120777 << 16)
        with zipfile.ZipFile(sym, "w") as archive:
            archive.writestr("Editor/main.py", "print(1)"); archive.writestr("Editor/assets/icon.png", b"PNGDATA"); archive.writestr(info, "icon.png")
        out = base / "symout"; safe_extract_zip(sym, out)
        materialized = out / "Editor/assets/.DirIcon"
        check(materialized.is_file() and not materialized.is_symlink() and materialized.read_bytes() == b"PNGDATA", "Safe ZIP symlink was not materialized", errors)

        # One-pass extraction writes directly to a sibling staging directory rather than copytree duplication.
        single_zip = base / "SinglePass.zip"
        with zipfile.ZipFile(single_zip, "w") as archive:
            archive.writestr("SinglePass/main.py", "print(1)\n")
            archive.writestr("SinglePass/editor.json", json.dumps({"id":"single-pass","name":"Single Pass","version":"1.0"}))
        single_dest = portable_root(editors_root, "Single Pass", "1.0")
        with patch("suite_pythoine.installer.shutil.copytree", side_effect=AssertionError("copytree must not be used for ordinary ZIP installation")):
            single_installed = import_zip(single_zip, editors_root, destination=single_dest)
        check((single_installed / "main.py").is_file(), "Single-pass staged extraction failed", errors)

        # A runtime quota failure is translated and the old destination is not replaced.
        quota_dest = portable_root(editors_root, "Quota Fixture", "1.0")
        quota_dest.mkdir(parents=True); (quota_dest / "sentinel").write_text("old", encoding="utf-8")
        with patch("suite_pythoine.installer.extract_editor_zip_to_staging", side_effect=OSError(errno.EDQUOT, "quota")):
            try:
                import_zip(single_zip, editors_root, replace_existing=True, destination=quota_dest)
            except InstallError as exc:
                check("storage quota was reached" in str(exc).casefold() and "Errno 122" not in str(exc), "EDQUOT was not translated cleanly", errors)
            else:
                errors.append("Injected EDQUOT did not stop ZIP installation")
        check((quota_dest / "sentinel").read_text(encoding="utf-8") == "old", "Quota failure replaced the existing portable version", errors)

        # Empty installation leaves are pruned before version/application containers.
        empty_version = version_root(editors_root, "Empty Cleanup", "1.0")
        (empty_version / "AppImage").mkdir(parents=True)
        prune_empty_version_tree(empty_version, editors_root)
        check(not empty_version.exists() and not empty_version.parent.exists(), "Empty AppImage/version/application containers were left behind", errors)
        mixed_version = version_root(editors_root, "Mixed Cleanup", "1.0")
        (mixed_version / "AppImage").mkdir(parents=True); (mixed_version / "Portable").mkdir(parents=True)
        (mixed_version / "Portable/main.py").write_text("print(1)", encoding="utf-8")
        prune_empty_version_tree(mixed_version, editors_root)
        check(not (mixed_version / "AppImage").exists() and (mixed_version / "Portable/main.py").is_file(), "Pruning removed a non-empty sibling installation type", errors)

        # Versioned import replacement retains rollback.
        good = base / "Example.zip"
        with zipfile.ZipFile(good, "w") as archive: archive.writestr("Example/main.py", "print(1)")
        dest = portable_root(editors_root, "Example Editor", "1.0")
        imported = import_zip(good, editors_root, destination=dest)
        (imported / "sentinel").write_text("old")
        original_replace = os.replace; count = {"n": 0}
        def injected(source, target):
            count["n"] += 1
            if count["n"] == 2: raise OSError("injected")
            return original_replace(source, target)
        try:
            with patch("suite_pythoine.installer.os.replace", side_effect=injected):
                import_zip(good, editors_root, replace_existing=True, destination=dest)
        except OSError: pass
        check((dest / "sentinel").read_text() == "old", "Versioned source replacement rollback failed", errors)

        # Direct AppImage inspection accepts an already-built Pad-family artifact
        # without launching it and preserves experimental version text.
        direct = base / "Ricopad-0.3.3-retro-exp1-x86_64.AppImage"
        elf = bytearray(64); elf[:4] = b"\x7fELF"; elf[4] = 2; elf[5] = 1; elf[18:20] = struct.pack("<H", 62); elf.extend(b"fixture")
        direct.write_bytes(elf)
        direct_info = inspect_appimage(direct)
        check(direct_info.editor_id == "ricopad" and direct_info.version == "0.3.3-retro-exp1" and direct_info.architecture == "x86_64", "Direct Ricopad AppImage inspection failed", errors)
        kapitulindo_direct = base / "Kapitulindo-1.0.0-x86_64.AppImage"
        kapitulindo_direct.write_bytes(elf)
        kapitulindo_info = inspect_appimage(kapitulindo_direct)
        check(kapitulindo_info.editor_id == "kapitulindo" and kapitulindo_info.name == "Kapitulindo" and kapitulindo_info.component_kind == "reader" and ".epub" in kapitulindo_info.extensions, "Canonical Kapitulindo AppImage identity failed", errors)
        direct_installed = install_appimage(direct, editors_root, editor_id=direct_info.editor_id, name=direct_info.name, version=direct_info.version, architecture=direct_info.architecture)
        check(direct_installed.name == "Ricopad-0.3.3-retro-exp1-x86_64.AppImage" and direct_installed.is_file(), "Direct AppImage managed copy failed", errors)

        # Managed AppImage naming/registry/desktop identity.
        source = base / "Example-Editor-9.1-x86_64.AppImage"; source.write_bytes(b"app")
        app = install_appimage(source, editors_root, editor_id="example-editor", name="Example Editor", version="9.1")
        expected_dir = appimage_root(editors_root, "Example Editor", "9.1")
        check(app.parent == expected_dir.resolve(strict=False), "AppImage installed outside version AppImage folder", errors)
        check(app.name == "Example-Editor-9.1-x86_64.AppImage", "Managed AppImage filename lost app/version/architecture", errors)
        icon_src = base / "example.svg"; icon_src.write_text("<svg/>")
        icon = install_icon(icon_src, editors_root, "example-editor", name="Example Editor", version="9.1")
        check(icon and icon.name == "example-editor-icon.svg" and icon.parent == expected_dir.resolve(strict=False), "Managed icon naming/location failed", errors)
        template = base / "template"; template.mkdir(); (template / "example.desktop").write_text("[Desktop Entry]\nName=Example Editor\nExec=old\nIcon=old\n")
        desktop = write_desktop_entry("Example Editor", "example-editor", app, icon, template, applications_dir=applications)
        check(desktop.name == "io.github.brunonlinespace.example-editor.desktop", "Desktop filename identity failed", errors)
        suite_appimage = base / "Suite-Pythoine-0.3.3-x86_64.AppImage"; suite_appimage.write_bytes(b"suite")
        suite_desktop = write_desktop_entry("Suite Pythoine", "suite-pythoine", suite_appimage, applications_dir=applications)
        suite_mime_line = next((line for line in suite_desktop.read_text(encoding="utf-8").splitlines() if line.startswith("MimeType=")), "")
        suite_mimes = {item for item in suite_mime_line.partition("=")[2].split(";") if item}
        check(suite_mimes == set(mime_type_union()), "Suite desktop integration does not derive its OS MIME union from the component catalogue", errors)
        check(desktop_entry_runtime(suite_desktop) == "appimage", "Suite AppImage desktop entry does not record AppImage runtime ownership", errors)

        # exp9-r2: the active Suite runtime owns the desktop entry directly.
        # Switching to Portable must preserve the exact MIME union and forward %F
        # to that exact Portable main.py; switching back must point directly to
        # the selected AppImage rather than relying on an older bootstrap binary.
        suite_portable_root = base / "suite-portable"
        suite_portable_root.mkdir()
        suite_portable_main = suite_portable_root / "main.py"
        suite_portable_main.write_text("# suite portable fixture\n", encoding="utf-8")
        suite_command = (sys.executable, str(suite_portable_main))
        portable_desktop = synchronize_portable_desktop_integration(
            "Suite Pythoine", "suite-pythoine", suite_command, None, suite_portable_root,
            applications_dir=applications, desktop_path=suite_desktop, desktop_id=desktop_id_for("suite-pythoine"),
        )
        portable_text = portable_desktop.read_text(encoding="utf-8")
        portable_mime_line = next((line for line in portable_text.splitlines() if line.startswith("MimeType=")), "")
        portable_mimes = {item for item in portable_mime_line.partition("=")[2].split(";") if item}
        check(desktop_entry_runtime(portable_desktop) == "portable", "Suite Portable desktop runtime marker missing", errors)
        check(desktop_entry_exec_command(portable_desktop) == (str(Path(sys.executable).resolve(strict=False)), str(suite_portable_main.resolve(strict=False))), "Suite Portable desktop entry does not target the exact active Portable runtime", errors)
        check("%F" in next((line for line in portable_text.splitlines() if line.startswith("Exec=")), ""), "Suite Portable desktop entry stopped forwarding OS file arguments", errors)
        check(portable_mimes == set(mime_type_union()), "Suite Portable desktop entry changed the OS MIME routing union", errors)
        check(portable_desktop_entry_status("suite-pythoine", suite_command, applications_dir=applications, desktop_path=portable_desktop, desktop_id=desktop_id_for("suite-pythoine")) == "ready", "Suite Portable desktop integration verification failed", errors)
        switched_back = synchronize_desktop_integration(
            "Suite Pythoine", "suite-pythoine", suite_appimage, None, None,
            applications_dir=applications, desktop_path=portable_desktop, desktop_id=desktop_id_for("suite-pythoine"),
        )
        check(desktop_entry_runtime(switched_back) == "appimage" and desktop_entry_exec_target(switched_back) == suite_appimage.resolve(strict=False), "Suite desktop integration did not switch directly back to the selected AppImage", errors)
        record = set_managed_installation({"managed_installations": {}}, {
            "editor_id": "example-editor", "application_id": "example-editor", "name": "Example Editor", "version": "9.1",
            "appimage_path": str(app), "appimage_sha256": hashlib.sha256(app.read_bytes()).hexdigest(),
            "desktop_file_path": str(desktop), "desktop_id": desktop_id_for("example-editor"), "icon_path": str(icon),
        })
        check(record_is_complete(record) and record["desktop_id"] == "io.github.brunonlinespace.example-editor", "Managed registry identity incomplete", errors)
        metadata = write_appimage_metadata(app, editor_id="example-editor", application_id="example-editor", name="Example Editor", version="9.1", desktop_file=desktop, desktop_id=record["desktop_id"], icon=icon)
        check(metadata.name == "Example-Editor-9.1-x86_64.AppImage.suite-pythoine.json", "Sidecar is not named after AppImage", errors)
        check(desktop_entry_exec_target(desktop) == app and desktop_entry_status("example-editor", app, applications_dir=applications, desktop_path=desktop, desktop_id=record["desktop_id"], icon_path=icon) == "ready", "Desktop integration not ready", errors)
        synchronized = synchronize_desktop_integration(
            "Example Editor", "example-editor", app, icon, template,
            applications_dir=applications, desktop_path=desktop, desktop_id=record["desktop_id"],
        )
        check(synchronized == desktop and desktop_entry_status("example-editor", app, applications_dir=applications, desktop_path=desktop, desktop_id=record["desktop_id"], icon_path=icon) == "ready", "Shared Make Active/Repair desktop synchronization primitive failed", errors)
        staged = stage_registered_appimage_integration(record, installed_dir=editors_root, applications_dir=applications)
        restore_staged_registered_integration(staged)
        check(app.exists() and desktop.exists(), "Nested integration restore failed", errors)
        staged = stage_registered_appimage_integration(record, installed_dir=editors_root, applications_dir=applications)
        finalize_staged_registered_integration(staged)
        check(not app.exists() and not desktop.exists(), "Nested integration purge failed", errors)

        # Storage migration: old flat portable + direct managed AppImage -> one master hierarchy.
        migration_root = base / "Migration Suite Pythoine Editors"; migration_root.mkdir()
        old_portables = base / "Documents/Suite Pythoine/My Editors"; old_portables.mkdir(parents=True)
        old_rico = old_portables / "Ricopad-0.3.3-rc4.2"; old_rico.mkdir(); (old_rico / "main.py").write_text("print(1)")
        (old_rico / "suite-pythoine.json").write_text(json.dumps({"id":"ricopad","name":"Ricopad","version":"0.3.3-rc4.2","extensions":[".md"]}))
        old_app = migration_root / "ricopad.AppImage"; old_app.write_bytes(b"oldapp")
        old_icon = migration_root / "ricopad-icon.png"; old_icon.write_bytes(b"icon")
        old_desktop = applications / "suite-pythoine-ricopad.desktop"; old_desktop.write_text("[Desktop Entry]\nName=Ricopad\n")
        migration_config = {"managed_installations": {}}
        set_managed_installation(migration_config, {
            "editor_id":"ricopad","application_id":"ricopad","name":"Ricopad","version":"0.3.3-rc4.2",
            "appimage_path":str(old_app),"appimage_sha256":hashlib.sha256(old_app.read_bytes()).hexdigest(),
            "desktop_file_path":str(old_desktop),"desktop_id":"suite-pythoine-ricopad","icon_path":str(old_icon),"extensions":[".md"],
        })
        # Patch the desktop applications directory used by migration to the fixture.
        with patch("suite_pythoine.storage_migration.desktop_entry_path", side_effect=lambda editor_id: applications / f"io.github.brunonlinespace.{editor_id}.desktop"):
            plan = build_migration_plan(migration_root, old_portables, migration_config, python_executable="/usr/bin/python3")
            check(plan.has_work and len(plan.items) == 1, "Legacy storage migration plan not detected", errors)
            migrated_record = migrate_item(plan.items[0], migration_root, migration_config)
        new_portable = portable_root(migration_root, "Ricopad", "0.3.3-rc4.2")
        new_appdir = appimage_root(migration_root, "Ricopad", "0.3.3-rc4.2")
        check(new_portable.is_dir() and not old_rico.exists(), "Portable source was not migrated", errors)
        check((new_appdir / "Ricopad-0.3.3-rc4.2-x86_64.AppImage").is_file(), "AppImage was not migrated to versioned path", errors)
        check(Path(migrated_record["desktop_file_path"]).name == "io.github.brunonlinespace.ricopad.desktop", "Migrated desktop identity not normalized", errors)

        # 0.3.0 default-root transition is one-time and transactional at the
        # version-folder level. Routine discovery uses only the new root after
        # migration; the old root is retired when every version moved cleanly.
        old_default_root = base / "old-default-root"
        old_version = old_default_root / "Portapad" / "1.0" / "Portable"
        old_version.mkdir(parents=True); (old_version / "main.py").write_text("print('old')", encoding="utf-8")
        new_default_root = base / "new-default-root"
        transition_config = {"managed_installations": {}, "editor_overrides": {}, "routing_index": {"stale": True}}
        moved_roots, transition_skips = transition_legacy_default_root(old_default_root, new_default_root, transition_config)
        check(not transition_skips and (new_default_root / "Portapad/1.0/Portable/main.py").is_file(), "Canonical component-root transition did not move a clean version", errors)
        check(not old_default_root.exists() and transition_config.get("editors_root") == str(new_default_root.resolve(strict=False)) and transition_config.get("routing_index") == {}, "Old default root remained active after successful one-time transition", errors)

        # Protected self-update cleanup runs only after the new managed Portable copy reaches startup.
        self_root = base / "Self Editors"
        old_self = version_root(self_root, "Suite Pythoine", "0.1.9"); (old_self / "Portable").mkdir(parents=True)
        (old_self / "Portable/main.py").write_text("old")
        new_self = version_root(self_root, "Suite Pythoine", "0.3.3"); (new_self / "Portable").mkdir(parents=True)
        new_launcher = new_self / "Portable/main.py"; new_launcher.write_text("new")
        self_cfg_path = base / "self-update-config.json"
        self_cfg = {
            "editors_root": str(self_root),
            "managed_installations": {},
            "pending_self_cleanup": {
                "editor_id":"suite-pythoine", "target_version":"0.3.3", "remove_versions":["0.1.9"],
                "editors_root":str(self_root), "application_name":"Suite Pythoine",
            },
        }
        self_cfg_path.write_text(json.dumps(self_cfg), encoding="utf-8")
        with patch("suite_pythoine.self_update._config_path", return_value=self_cfg_path), patch.dict(os.environ, {}, clear=False):
            os.environ.pop("APPIMAGE", None)
            removed_self = complete_pending_self_cleanup("0.3.3", new_launcher)
        check(removed_self == ("0.1.9",) and not old_self.exists() and new_self.exists(), "Deferred Suite self-update cleanup failed", errors)
        cleaned_self_cfg = json.loads(self_cfg_path.read_text(encoding="utf-8"))
        check("pending_self_cleanup" not in cleaned_self_cfg, "Completed self-update cleanup marker was not cleared", errors)

        # Config compatibility: old split-path keys are retained as migration inputs, and the 0.1.0 publisher-ID mistake is repaired.
        cfg_path = base / "config.json"
        cfg_path.write_text(json.dumps({
            "my_editors_dir": "/old/portable", "installed_editors_dir": "/old/installed",
            "managed_installations": {"brunonlinespace": {"editor_id":"brunonlinespace","name":"Suite Pythoine","appimage_path":"/x","desktop_file_path":"/y"}},
            "extension_preferences": {".md": "brunonlinespace"},
        }))
        cfg = ConfigService(cfg_path)
        check(cfg.get("legacy_my_editors_dir") == "/old/portable" and cfg.get("legacy_installed_editors_dir") == "/old/installed", "Legacy split paths were not retained for migration", errors)
        check("suite-pythoine" in cfg.get("managed_installations") and "brunonlinespace" not in cfg.get("managed_installations"), "0.1.0 Suite identity migration failed", errors)
        check(cfg.get("extension_preferences").get(".md") == "suite-pythoine", "Old Suite extension preference identity was not migrated", errors)

        retired_cfg_path = base / "retired-store-psts-config.json"
        retired_cfg_path.write_text(json.dumps({
            "store_state":"enabled",
            "editor_overrides":{"psts-pad":{"launch_mode":"portable"}, "markopad":{"launch_mode":"portable"}},
            "managed_installations":{"psts-pad":{"versions":{}}, "markopad":{"versions":{}}},
            "extension_preferences":{".ghost":"psts-pad", ".md":"markopad"},
            "last_selected_editor":"psts-pad",
        }), encoding="utf-8")
        retired_cfg = ConfigService(retired_cfg_path)
        check("store_state" not in retired_cfg.as_dict(), "Retired built-in Store toggle survived 0.3.3 config migration", errors)
        check("psts-pad" not in retired_cfg.get("editor_overrides") and "psts-pad" not in retired_cfg.get("managed_installations"), "Removed PSTS identity survived managed/config migration", errors)
        check(".ghost" not in retired_cfg.get("extension_preferences") and retired_cfg.get("extension_preferences").get(".md") == "markopad" and retired_cfg.get("last_selected_editor") is None, "Removed PSTS remembered routing/selection state survived migration", errors)

        gitten_cfg_path = base / "gitten-identity-transition.json"
        gitten_cfg_path.write_text(json.dumps({
            "editor_overrides": {"gitten-pad": {"launch_mode":"portable", "active_version":"0.0.1"}},
            "managed_installations": {
                "gitten-pad": {
                    "editor_id":"gitten-pad", "application_id":"gitten-pad", "name":"Gitten Pad",
                    "desktop_id":"io.github.brunonlinespace.gitten-pad",
                    "desktop_file_path":"/home/test/.local/share/applications/io.github.brunonlinespace.gitten-pad.desktop",
                    "versions": {"0.0.1": {
                        "editor_id":"gitten-pad", "application_id":"gitten-pad", "name":"Gitten Pad", "version":"0.0.1",
                        "desktop_id":"io.github.brunonlinespace.gitten-pad",
                        "desktop_file_path":"/home/test/.local/share/applications/io.github.brunonlinespace.gitten-pad.desktop"
                    }}
                }
            },
            "extension_preferences": {".fixture":"gitten-pad"},
            "last_selected_editor":"gitten-pad"
        }), encoding="utf-8")
        gitten_cfg = ConfigService(gitten_cfg_path)
        gitten_managed = gitten_cfg.get("managed_installations")
        check("gitten" in gitten_managed and "gitten-pad" not in gitten_managed, "Legacy Gitten Pad managed identity was not migrated", errors)
        gitten_group = gitten_managed.get("gitten", {})
        check(gitten_group.get("editor_id") == "gitten" and gitten_group.get("name") == "gitten", "Gitten managed group did not adopt canonical lowercase identity", errors)
        check(gitten_group.get("desktop_id") == "io.github.brunonlinespace.gitten" and str(gitten_group.get("desktop_file_path", "")).endswith("io.github.brunonlinespace.gitten.desktop"), "Gitten desktop identity migration failed", errors)
        check("gitten" in gitten_cfg.get("editor_overrides") and "gitten-pad" not in gitten_cfg.get("editor_overrides"), "Legacy Gitten Pad override identity was not migrated", errors)
        check(gitten_cfg.get("extension_preferences").get(".fixture") == "gitten" and gitten_cfg.get("last_selected_editor") == "gitten", "Legacy Gitten Pad remembered state was not migrated", errors)

        linspect_cfg_path = base / "linspectacles-identity-transition.json"
        linspect_cfg_path.write_text(json.dumps({
            "editor_overrides": {"linspector-suite": {"launch_mode":"portable"}},
            "managed_installations": {
                "linspector-suite": {
                    "editor_id":"linspector-suite", "application_id":"linspector-suite", "name":"Linspector Suite",
                    "desktop_id":"io.github.brunonlinespace.linspector-suite",
                    "desktop_file_path":"/home/test/.local/share/applications/io.github.brunonlinespace.linspector-suite.desktop",
                    "versions": {"0.0.2": {
                        "editor_id":"linspector-suite", "application_id":"linspector-suite", "name":"Linspector Suite", "version":"0.0.2",
                        "desktop_id":"io.github.brunonlinespace.linspector-suite",
                        "desktop_file_path":"/home/test/.local/share/applications/io.github.brunonlinespace.linspector-suite.desktop"
                    }}
                }
            },
            "extension_preferences": {".fixture":"linspector-suite"},
            "last_selected_editor":"linspector-suite"
        }), encoding="utf-8")
        linspect_cfg = ConfigService(linspect_cfg_path)
        linspect_managed = linspect_cfg.get("managed_installations")
        check("linspectacles" in linspect_managed and "linspector-suite" not in linspect_managed, "Legacy Linspector managed identity was not migrated", errors)
        linspect_group = linspect_managed.get("linspectacles", {})
        check(linspect_group.get("editor_id") == "linspectacles" and linspect_group.get("name") == "Linspectacles", "Linspectacles managed group did not adopt canonical identity", errors)
        check(linspect_group.get("desktop_id") == "io.github.brunonlinespace.linspectacles" and str(linspect_group.get("desktop_file_path", "")).endswith("io.github.brunonlinespace.linspectacles.desktop"), "Linspectacles desktop identity migration failed", errors)
        check("linspectacles" in linspect_cfg.get("editor_overrides") and "linspector-suite" not in linspect_cfg.get("editor_overrides"), "Legacy Linspector override identity was not migrated", errors)
        check(linspect_cfg.get("extension_preferences").get(".fixture") == "linspectacles" and linspect_cfg.get("last_selected_editor") == "linspectacles", "Legacy Linspector remembered state was not migrated", errors)

        rico_cfg_path = base / "ricopad-transition-config.json"
        rico_cfg_path.write_text(json.dumps({
            "editor_overrides": {"ricopad": {"launch_mode": "installed", "extensions": [".md", ".markdown", ".mdown", ".mkd", ".rtf"]}},
            "extension_preferences": {".md": "ricopad", ".markdown": "ricopad", ".rtf": "ricopad"},
            "routing_index": {"schema": 2, "stale": True},
        }), encoding="utf-8")
        rico_cfg = ConfigService(rico_cfg_path)
        check(rico_cfg.get("editor_overrides")["ricopad"]["extensions"] == [".rtf"], "Ricopad transition did not remove obsolete Markdown extension overrides", errors)
        check(".md" not in rico_cfg.get("extension_preferences") and ".markdown" not in rico_cfg.get("extension_preferences") and rico_cfg.get("extension_preferences").get(".rtf") == "ricopad", "Ricopad transition did not clear obsolete remembered Markdown routes", errors)
        check(rico_cfg.get("routing_index") == {}, "Ricopad/Markopad transition did not invalidate the routing index", errors)

        # The same transition must run before the GUI on the document-routing
        # hot path; otherwise an old 0.3.0 Ricopad override could resurrect
        # Markdown during a double-click even though the full Hub is correct.
        with patch("suite_pythoine.silent_dispatch.default_config_path", return_value=rico_cfg_path):
            hot_cfg = load_dispatch_config()
        check(hot_cfg.get("editor_overrides", {}).get("ricopad", {}).get("extensions") == [".rtf"], "Pre-GUI config normalization left Ricopad claiming Markdown", errors)
        check(".md" not in hot_cfg.get("extension_preferences", {}) and hot_cfg.get("routing_index") == {}, "Pre-GUI config normalization left stale Markdown routing state", errors)


def main() -> int:
    errors: list[str] = []
    source_checks(errors)
    functional_checks(errors)
    if errors:
        print(f"{APP_NAME} {EXPECTED_VERSION} release check FAILED:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"{APP_NAME} {EXPECTED_VERSION} release check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
