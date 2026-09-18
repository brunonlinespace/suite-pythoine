#!/usr/bin/env bash
set -Eeuo pipefail
export PYTHONDONTWRITEBYTECODE=1

PROGRAM_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
PROJECT_ROOT="$(cd -- "$PROGRAM_ROOT/.." && pwd -P)"
VERSION="0.3.3"
BUILD_SCRIPT="$PROGRAM_ROOT/packaging/fedora/build-appimage.sh"
TEST_SCRIPT="$PROGRAM_ROOT/packaging/fedora/test-appimage.sh"
APPRUN="$PROGRAM_ROOT/packaging/appimage/AppRun"
DESKTOP="$PROGRAM_ROOT/packaging/appimage/suite-pythoine.desktop"
METAINFO="$PROGRAM_ROOT/packaging/appimage/io.github.brunonlinespace.suite-pythoine.metainfo.xml"

pass() { printf 'PASS: %s\n' "$1"; }

PYCACHE_TMP="$(mktemp -d)"
trap 'rm -rf "$PYCACHE_TMP"' EXIT
export XDG_CONFIG_HOME="$PYCACHE_TMP/xdg-config"
mkdir -p "$XDG_CONFIG_HOME"
PYTHONPYCACHEPREFIX="$PYCACHE_TMP" python3 -m compileall -q "$PROJECT_ROOT/main.py" "$PROGRAM_ROOT"
pass "Python compilation"

(cd "$PROJECT_ROOT" && PYTHONDONTWRITEBYTECODE=1 python3 main.py --version) \
    | grep -Fx "Suite Pythoine ${VERSION}" >/dev/null
pass "Portable version launcher"

(cd "$PROJECT_ROOT" && PYTHONDONTWRITEBYTECODE=1 python3 -m suite_pythoine.tools.release_check)
pass "Release/security gate"

bash -n "$BUILD_SCRIPT"
bash -n "$TEST_SCRIPT"
sh -n "$APPRUN"
pass "Shell syntax"

python3 - "$PROGRAM_ROOT" "$DESKTOP" "$METAINFO" <<'PYQA'
import ast
import json
import pathlib
import re
import sys
import xml.etree.ElementTree as ET

root = pathlib.Path(sys.argv[1])
desktop_path = pathlib.Path(sys.argv[2])
metainfo_path = pathlib.Path(sys.argv[3])
sys.path.insert(0, str(root.parent))

expected_editors = {"markopad", "nuxpad", "ricopad", "texypad", "sheepy-pad", "timblee-pad", "jsts-pad"}
expected_readers = {"kapitulindo", "portapad", "beespector-lite", "beespector"}
expected_extensions_ids = {"linspectacles", "marko-plus", "rico-plus", "crawlindo", "youlindo", "sbookypad", "gitten", "python-lair", "store-pythoine"}
expected_ids = {"suite-pythoine", *expected_editors, *expected_readers, *expected_extensions_ids}
expected_extensions = {
    ".txt", ".log", ".ini", ".cfg", ".conf", ".md", ".markdown", ".mdown", ".mkd", ".rtf",
    ".tex", ".bib", ".pdf", ".epub", ".py", ".sh", ".html", ".htm", ".css",
    ".js", ".mjs", ".cjs", ".ts", ".mts", ".cts", ".jsx", ".tsx",
}
expected_mimes = {
    "text/plain", "text/x-log", "text/markdown", "text/rtf", "application/rtf", "application/pdf",
    "text/x-tex", "text/x-bibtex", "application/epub+zip", "text/x-python", "text/x-python3", "application/x-shellscript", "text/html",
    "application/xhtml+xml", "text/css", "application/javascript", "text/javascript", "text/typescript", "application/typescript",
}

from suite_pythoine.component_catalog import COMPONENT_PROFILES, BUNDLED_CATALOG_PATH, catalog_fingerprint, catalog_revision, extension_union, mime_type_union
from suite_pythoine.component_policy import can_create_document, can_open_document, can_route_document, is_document_editor, is_hub, is_reader
from suite_pythoine.registry import PAD_FAMILY_EXTENSIONS, PAD_FAMILY_MIME_TYPES
from suite_pythoine.managed_registry import REGISTRY_SCHEMA

assert set(COMPONENT_PROFILES) == expected_ids
assert COMPONENT_PROFILES["suite-pythoine"].kind == "hub"
assert all(COMPONENT_PROFILES[key].kind == "editor" for key in expected_editors)
assert all(COMPONENT_PROFILES[key].kind == "reader" for key in expected_readers)
assert all(COMPONENT_PROFILES[key].kind == "extension" for key in expected_extensions_ids)
assert COMPONENT_PROFILES["markopad"].extensions == (".md", ".markdown", ".mdown", ".mkd")
assert COMPONENT_PROFILES["markopad"].mime_types == ("text/markdown",)
assert COMPONENT_PROFILES["ricopad"].extensions == (".rtf",)
assert "psts-pad" not in COMPONENT_PROFILES
assert COMPONENT_PROFILES["timblee-pad"].extensions == (".html", ".htm", ".css")
assert ".svg" not in COMPONENT_PROFILES["timblee-pad"].extensions
assert COMPONENT_PROFILES["store-pythoine"].kind == "extension" and not COMPONENT_PROFILES["store-pythoine"].is_routable
assert COMPONENT_PROFILES["texypad"].extensions == (".tex", ".bib")
assert all(not COMPONENT_PROFILES[key].extensions for key in expected_extensions_ids)
assert set(COMPONENT_PROFILES["ricopad"].mime_types) == {"text/rtf", "application/rtf"}
assert is_hub(type("X", (), {"component_kind":"hub"})())
assert not is_document_editor(type("X", (), {"kind":"hub"})())
assert is_reader(type("X", (), {"kind":"reader"})())
assert can_route_document(COMPONENT_PROFILES["portapad"]) and can_open_document(COMPONENT_PROFILES["portapad"]) and not can_create_document(COMPONENT_PROFILES["portapad"])
assert can_create_document(COMPONENT_PROFILES["markopad"])
assert set(extension_union()) == expected_extensions
assert set(mime_type_union()) == expected_mimes
assert set(PAD_FAMILY_EXTENSIONS) == expected_extensions
assert set(PAD_FAMILY_MIME_TYPES) == expected_mimes
assert len(catalog_fingerprint()) == 64
assert catalog_revision(BUNDLED_CATALOG_PATH) == 9
assert REGISTRY_SCHEMA == 2

init_text = (root / "__init__.py").read_text(encoding="utf-8")
assert '__version__ = "0.3.3"' in init_text
suite_manifest = json.loads((root.parent / "suite-pythoine.json").read_text(encoding="utf-8"))
assert suite_manifest["id"] == "suite-pythoine"
assert suite_manifest["publisher_id"] == "brunonlinespace"
assert suite_manifest["desktop_id"] == "io.github.brunonlinespace.suite-pythoine"
assert suite_manifest["version"] == "0.3.3"

main_source = (root.parent / "main.py").read_text(encoding="utf-8")
assert main_source.index("dispatch_paths_silently") < main_source.index("from suite_pythoine.app import main")
assert "--diagnose-routing" in main_source
assert "maybe_exec_preferred_portable" not in main_source
assert "handle_store_protocol_cli" in main_source and "ensure_control_bridge" in main_source
store_bridge_text = (root / "store_bridge.py").read_text(encoding="utf-8")
for flag in ("--store-protocol-version", "--managed-list", "--inspect-package", "--install-package", "--source", "store", "--wizard"):
    assert flag in store_bridge_text
assert "os.execvpe" in store_bridge_text and 'DESKTOP_ID = "io.github.brunonlinespace.suite-pythoine"' in store_bridge_text and 'f"{DESKTOP_ID}.desktop"' in store_bridge_text
assert not (root / "store_page.py").exists() and not (root / "store_policy.py").exists() and not (root / "catalog_service.py").exists()

app_text = (root / "app.py").read_text(encoding="utf-8")
assert 'runtime_group_layout.addRow("Launch runtime:"' in app_text
assert 'self.tabs.addTab(routing_page, "File Routing")' in app_text
assert 'Reset Routing Choices' in app_text
assert 'self.tabs.addTab(general, "General")' in app_text
assert 'self.tabs.addTab(runtime_page, "Runtime")' in app_text
assert 'self.tabs.addTab(versions_page, "Versions")' in app_text
assert 'self.tabs.addTab(information_page, "Information")' in app_text
assert 'Open Components Folder' in app_text
assert 'Repair Desktop Integration' in app_text
assert 'Open Installed Folder' in app_text
assert 'Open Version Folder' in app_text
assert 'self._populate_editor_details(layout, self.suite_entry)' in app_text
assert 'inventory_heading = QLabel("Installed Applications")' in app_text
assert 'header.setSectionsMovable(True)' in app_text
assert 'QHeaderView.ResizeMode.Interactive' in app_text
assert 'Qt.ContextMenuPolicy.CustomContextMenu' in app_text
assert 'installed_apps_table_layout' in app_text
assert 'table.setMaximumHeight(360)' not in app_text
assert 'table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)' in app_text
assert 'layout.addWidget(table, 1)' in app_text
assert 'install_component = QPushButton("Install Component…")' in app_text
assert '"Application", "Version", "Runtime"' in app_text
assert '"runtime": "Portable"' in app_text and '"runtime": "AppImage"' in app_text
assert 'old_label = "Installed as"' in app_text and 'new_label = "Runtime"' in app_text
assert 'frame.setMaximumWidth(250)' in app_text
assert 'self.splitter.setCollapsible(0, True)' in app_text
assert 'sidebar_size = max(0, min(int(sizes[0]), 250))' in app_text
assert 'QAction("Open Components Folder"' in app_text
assert 'self.dashboard_action.setShortcut("Ctrl+W")' in app_text
assert 'self.refresh_action = QAction("Refresh Components"' in app_text and 'self.refresh_action.setShortcut("F5")' in app_text
assert 'self.open_components_folder_action.setShortcut("Ctrl+Shift+O")' in app_text
assert 'self.install_action.setShortcut("Ctrl+Shift+N")' in app_text and 'QAction("Install Component…"' in app_text
assert 'self.sidebar_action.setShortcut("F9")' in app_text
assert 'self.toggle_view_shortcut_action = QAction("Toggle List/Grid View", self)' in app_text
assert 'self.toggle_view_shortcut_action.setShortcut("Ctrl+Alt+Shift+D")' in app_text
assert 'view.addAction(self.toggle_view_shortcut_action)' not in app_text and 'dashboard_settings.addAction(self.toggle_view_shortcut_action)' not in app_text
assert 'Toggle List/Grid view: Ctrl+Alt+Shift+D' in app_text
assert 'dashboard_settings = view.addMenu("Dashboard Settings")' in app_text
assert app_text.index('view.addAction(self.refresh_action)') < app_text.index('view.addAction(self.dashboard_action)') < app_text.index('dashboard_settings = view.addMenu("Dashboard Settings")')
assert 'dashboard_settings.addAction(self.list_action)' in app_text and 'dashboard_settings.addAction(self.grid_action)' in app_text
assert 'dashboard_settings.addAction(self.icons_action)' in app_text and 'dashboard_settings.addAction(self.drop_bar_action)' in app_text
assert 'self.icons_action.setShortcut("Ctrl+Alt+Shift+I")' in app_text
assert 'self.drop_bar_action.setShortcut("Ctrl+Alt+Shift+B")' in app_text
assert 'self.preferences_action.setShortcut("Ctrl+/")' in app_text
assert 'self.search_action.setShortcut("Ctrl+F")' in app_text
assert 'self.shortcuts_action.setShortcut("Ctrl+Shift+/")' in app_text
assert 'store_btn = QPushButton("Get More...")' in app_text
assert 'self.editor_list.setIconSize(QSize(26, 26))' in app_text
assert 'item.setSizeHint(QSize(0, 38))' in app_text
dashboard_text = (root / "dashboard.py").read_text(encoding="utf-8")
card_text = dashboard_text.split("class EditorCard", 1)[1].split("class EditorDashboard", 1)[0]
assert card_text.count("root = QVBoxLayout(self)") == 1
assert '("Readers", readers)' in dashboard_text
assert 'can_create_document(editor)' in card_text and 'can_open_document(editor)' in card_text
assert 'actions.append(("New…", self.new_requested))' in card_text
assert 'else:\n            actions.append(("Launch", self.launch_requested))' in card_text
# Editor Details has New/Open only; Reader/Extension Launch remains available.
editor_branch = app_text.split('if editor.component_kind == "editor":', 1)[1].split('elif editor.component_kind == "reader":', 1)[0]
assert '("New File…"' in editor_branch and '("Open File…"' in editor_branch and '("Launch"' not in editor_branch
assert '("Launch", lambda: self.launch_editor(editor)' in app_text.split('elif editor.component_kind == "reader":', 1)[1]
assert 'add_sidebar_group("READERS", self.readers)' in app_text
assert 'self.show_dashboard()\n        self.dashboard.set_view_mode(mode)' in app_text
assert 'app_dialog_title("Choose Application")' in app_text
assert 'app_dialog_title("Choose Application")' in (root / "routing_chooser.py").read_text(encoding="utf-8")
assert '("Preferences…", self.general_preferences' in app_text
assert 'GitHub Repository' in app_text
assert 'document_candidates(self.components, extension)' in app_text
assert 'catalogue_refreshed.connect' not in app_text
assert 'from .store_page import' not in app_text and 'from .catalog_service import' not in app_text
assert 'Store Pythoine is not installed.' in app_text and 'Install Extension…' in app_text
assert 'DeveloperIntakeConfig' in app_text and 'DeveloperIntakeDialog' in app_text
assert 'self.developer_action.setShortcut("F12")' in app_text
assert 'Ctrl+Shift+B' in app_text and 'Ctrl+Shift+Y' in app_text and 'Ctrl+Shift+C' in app_text
assert 'Purge Extension…' in app_text and 'Open Config Folder' in app_text
assert 'Remove Portable…' in app_text and 'Uninstall AppImage…' in app_text
assert '_inventory_remove_runtime' in app_text
assert 'currentItemChanged.connect' in app_text
assert 'dashboard_show_icons' in app_text and 'dashboard_drop_bar_visible' in app_text
assert 'show_url_choices' in app_text
assert 'QScroller.grabGesture' in dashboard_text and 'class DropBar' in dashboard_text
assert 'Qt.Key.Key_Backspace' in app_text and 'self._navigate_back()' in app_text
assert 'synchronize_portable_desktop_integration' in app_text
installer_text = (root / 'installer.py').read_text(encoding='utf-8')
assert 'def write_portable_desktop_entry' in installer_text and 'X-Suite-Pythoine-Runtime=portable' in installer_text
assert 'X-Suite-Pythoine-Runtime=appimage' in installer_text
dev_policy = (root / 'developer_policy.py').read_text(encoding='utf-8')
assert '--enable-developer-mode' in dev_policy and '--disable-developer-mode' in dev_policy and '--developer-mode-status' in dev_policy
assert main_source.index('handle_developer_cli') < main_source.index('from suite_pythoine.app import main')
assert 'if self.developer_config.enabled and not store_download:' in app_text
assert 'DEV MODE' in app_text
dev_text = (root / "developer_intake.py").read_text(encoding="utf-8")
assert 'developer-only' in dev_text and 'local:' in dev_text
assert 'Delete ZIP after successful extraction' in dev_text
assert 'Keep extracted files in a ZIP-named subfolder' in dev_text
assert 'self.resize(780, 600)' in dev_text
assert 'paste_button = QPushButton("Paste")' in dev_text and 'self.notes.paste()' in dev_text
assert 'gitten-pad' in dev_text and 'clean_roots.setdefault("gitten"' in dev_text
assert 'linspector-suite' in dev_text and 'clean_roots.setdefault("linspectacles"' in dev_text
assert 'clean_roots.pop("psts-pad", None)' in dev_text
from suite_pythoine.config import ConfigService
assert 'store_state' not in ConfigService.DEFAULTS
assert COMPONENT_PROFILES['beespector'].kind == 'reader' and not COMPONENT_PROFILES['beespector'].is_routable
assert COMPONENT_PROFILES['beespector-lite'].kind == 'reader' and not COMPONENT_PROFILES['beespector-lite'].is_routable
assert COMPONENT_PROFILES['gitten'].name == 'gitten'
assert COMPONENT_PROFILES['linspectacles'].name == 'Linspectacles' and 'linspector-suite' in COMPONENT_PROFILES['linspectacles'].identity_hints
assert all(COMPONENT_PROFILES[key].kind == 'extension' and not COMPONENT_PROFILES[key].is_routable and not COMPONENT_PROFILES[key].can_create for key in ('marko-plus', 'rico-plus'))
shortcuts_text = (root / 'shortcuts_dialog.py').read_text(encoding='utf-8')
assert '_SHORTCUT_TOKEN_ALIASES' in shortcuts_text and '"control": "ctrl"' in shortcuts_text and '"ctl": "ctrl"' in shortcuts_text
assert 'token in shortcut_tokens for token in query_tokens' in shortcuts_text
assert 'self.category.setAccessibleName("Shortcut menu")' in shortcuts_text and 'QLabel("Menu:", self)' in shortcuts_text
assert '_SHORTCUT_TOKEN_RE = re.compile(r"[a-z0-9]+|[^\\w\\s+]", re.IGNORECASE)' in shortcuts_text
assert 'QApplication.instance().installEventFilter(self)' in app_text and 'self.dashboard.search.insert(text)' in app_text
assert 'Desktop integration now points to' in app_text
assert 'synchronize_desktop_integration' in (root / 'install_wizard.py').read_text(encoding='utf-8')
assert 'synchronize_desktop_integration' in (root / 'appimage_wizard.py').read_text(encoding='utf-8')
assert app_text.count('synchronize_desktop_integration(') >= 2
assert 'Type: {kind_label}' in app_text
assert 'Suite Pythoine: a little Python, sweetly caffeinated.' in app_text

storage = (root / "storage_layout.py").read_text(encoding="utf-8")
assert 'DEFAULT_COMPONENTS_FOLDER_NAME = "Suite Pythoine"' in storage
assert 'LEGACY_DEFAULT_EDITORS_FOLDER_NAME = "Suite Pythoine Editors"' in storage
runtime_paths = (root / "runtime_paths.py").read_text(encoding="utf-8")
assert 'SUITE_PYTHOINE_COMPONENTS_ROOT' in runtime_paths

registry_text = (root / "registry.py").read_text(encoding="utf-8")
assert "def _trusted_package_manifest_names()" in registry_text
assert "def _trusted_manifest_component_id(data: dict)" in registry_text
assert "immediate app package" in registry_text
assert 'f"{component_id}.json"' in registry_text

install_wizard_text = (root / "install_wizard.py").read_text(encoding="utf-8")
assert '("identity", "Verify component identity")' in install_wizard_text
assert "UnknownComponentError" in install_wizard_text
assert 'failure_step = "identity"' in install_wizard_text
assert "Component identity changed after import" in install_wizard_text
assert "Verify editor identity" not in install_wizard_text

for wizard_name in ("install_wizard.py", "appimage_wizard.py"):
    wizard = (root / wizard_name).read_text(encoding="utf-8")
    assert "QScrollArea" in wizard
    assert "_scrollable_page_layout" in wizard
    assert "resize(980" in wizard.replace(" ", "") or "resize(980,800)" in wizard.replace(" ", "")
    assert 'mode == "upgrade_alongside"' in wizard
    assert 'self.make_active.setEnabled(True)' in wizard

desktop = desktop_path.read_text(encoding="utf-8")
assert "GenericName=File Editor Hub" in desktop
assert "Exec=suite-pythoine %F" in desktop
assert "StartupNotify=false" in desktop
mime_line = next(line for line in desktop.splitlines() if line.startswith("MimeType="))
assert {v for v in mime_line.split("=",1)[1].split(";") if v} == expected_mimes
component = ET.parse(metainfo_path).getroot()
assert component.findtext("id") == "io.github.brunonlinespace.suite-pythoine"
assert {node.text for node in component.findall("./provides/mediatype") if node.text} == expected_mimes
assert any(node.attrib.get("version") == "0.3.3" for node in component.findall("./releases/release"))

build = (root / "packaging/fedora/build-appimage.sh").read_text(encoding="utf-8")
for needle in [
    'APP_VERSION="0.3.3"', 'umask 022', 'check_non_privileged_policy', 'SUITE_PYTHOINE_ALLOW_ROOT_BUILD',
    'validate_appstream_basic', 'APPIMAGETOOL_SHA256', 'MAX_TOOL_BYTES', 'elf_sanity_check',
    '[[ "$url" == https://* ]]', '--connect-timeout 30', '--max-time 300', 'chmod 0700 "$CACHE_DIR"',
    'export PYTHONDONTWRITEBYTECODE=1', 'clean_source_python_caches', "-name '__pycache__'", "-name '*.pyc'",
    "-name '*.pyo'", 'install -m 0755', 'install -m 0644', 'run_smoke_test "AppDir"',
    'run_version_smoke_test "AppDir"', 'run_smoke_test "final AppImage"', 'run_version_smoke_test "final AppImage"',
    'Build requirements SHA-256:', 'Builder SHA-256:', '${COMPONENT_CATALOG}:suite_pythoine',
]:
    assert needle in build, needle
for shell_file in root.rglob("*.sh"):
    shell = shell_file.read_text(encoding="utf-8")
    assert not re.search(r"(?m)^\s*(?:sudo|dnf|pkexec|su)(?:\s|$)", shell), shell_file

# r3 Dashboard toggle removal / Preferences shortcut-label guard
assert 'self.view_button = QPushButton' not in dashboard_text
assert 'Open Components Folder  (Ctrl+Shift+O)' in app_text
assert 'Show application icons on Dashboard  (Ctrl+Alt+Shift+I)' in app_text
assert 'Show Drop Bar  (Ctrl+Alt+Shift+B)' in app_text
assert 'Enable Developer Intake Mode  (F12)' in app_text

print("PASS: 0.3.3 component/routing model, Store decoupling, and hardened AppImage apparatus")
PYQA
pass "Component/routing metadata and no-privilege policy"

if [[ -f "$PROGRAM_ROOT/SOURCE_MANIFEST.sha256" ]]; then
    (cd "$PROJECT_ROOT" && sha256sum -c suite_pythoine/SOURCE_MANIFEST.sha256 >/dev/null)
    pass "SOURCE_MANIFEST.sha256"
fi

printf 'Suite Pythoine %s static QA completed successfully.\n' "$VERSION"
