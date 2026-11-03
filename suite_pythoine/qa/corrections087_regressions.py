"""0.8.7 scoped UI/discovery regression checks, including real keyboard dispatch."""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations
import ast
from pathlib import Path
from types import SimpleNamespace
from suite_pythoine.config import apply_routing_compatibility_migrations

ROOT = Path(__file__).resolve().parents[1]
PREFERENCES = ROOT / 'ui' / 'dialogs' / 'preferences.py'


def _class_source(cls_name: str) -> str:
    path = PREFERENCES if cls_name in {'EditorPreferencesDialog', 'GeneralPreferencesDialog'} else ROOT / 'app.py'
    return path.read_text(encoding='utf8') if path == PREFERENCES else read_app_with_presentations()


def _method(cls_name: str, name: str):
    source = _class_source(cls_name)
    tree = ast.parse(source)
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == cls_name)
    return next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == name)


def _method_source(cls_name: str, name: str) -> str:
    source = _class_source(cls_name)
    return ast.get_source_segment(source, _method(cls_name, name))


def run_regressions(errors: list[str]) -> None:
    def check(condition: bool, message: str) -> None:
        if not condition:
            errors.append('0.8.7 correction: ' + message)

    app = read_app_with_presentations()
    dash = (ROOT / 'ui/shell/dashboard.py').read_text(encoding='utf8')
    registry = (ROOT / 'registry.py').read_text(encoding='utf8')
    pref = _method_source('GeneralPreferencesDialog', '__init__')
    app_pref = _method_source('EditorPreferencesDialog', '__init__')
    app_apply = _method_source('EditorPreferencesDialog', 'apply')
    details = _method_source('SuiteWindow', '_populate_editor_details')
    inventory = (ROOT / 'ui/pages/installed_applications.py').read_text(encoding='utf8')

    # Exact request: change only 'your' in the existing two-sentence introduction.
    check('"A simple hub for brunonlinespace applications. Editors and Readers handle supported files; Extensions offer standalone tools. "' in dash and
          '"Suite Pythoine manages these applications without embedding their functionality."' in dash,
          'Dashboard introduction was truncated or rewritten')
    check('icon.setPixmap(QIcon(str(app_icon)).pixmap(56, 56))' in dash and
          'QIcon(str(editor.icon)).pixmap(34, 34)' in dash and
          'installed_applications = QPushButton("Installed Applications")' not in dash and
          'details = QPushButton("Hub Details")' in dash,
          'only Dashboard header Suite icon should change; card icons unaffected and inventory button removed')

    # General is scrollable so Runtime+Dashboard+Developer remain accessible.
    check('self.tabs.addTab(runtime_page, "Runtime")' not in pref and
          'self.tabs.addTab(general_scroll, "General")' in pref and
          pref.index('runtime_row.addWidget(self.suite_runtime, 1)') <
          pref.index('runtime_row.addWidget(self.repair_desktop_button)') <
          pref.index('general_layout.addWidget(runtime_group)') < pref.index('QGroupBox("Dashboard")'),
          'Runtime must remain in scrollable General with Repair alongside its selector')
    check('self.tabs.addTab(versions_page, "Hub Versions")' in pref and
          pref.index('folder_actions.addWidget(open_components)') <
          pref.index('folder_actions.addWidget(open_config)') and
          'self.controller.launcher.open_path(self.runtime.config_path.parent)' in pref and
          'Open Applications Folder  (Ctrl+Shift+O)' in pref,
          'Hub Versions or two exact Preferences folder actions regressed')
    check('"AppImage file:"' not in app_pref and 'self.installed_path' not in app_pref and
          'def _browse_installed' not in app and 'override.pop("installed_path", None)' in app_apply and
          'installed_override = override.get("installed_path")' not in registry and
          'raw = override.get("installed_path")' not in app,
          'obsolete manual AppImage-path field or live discovery override remains')

    old_config = {'editor_overrides': {'markopad': {'installed_path': '/old/legacy.AppImage', 'launch_mode': 'portable'},
                                       'portapad': {'installed_path': '/other/legacy.AppImage', 'extensions': ['.pdf']}}}
    changed = apply_routing_compatibility_migrations(old_config)
    check(changed and old_config['editor_overrides'] == {
        'markopad': {'launch_mode': 'portable'}, 'portapad': {}},
        'retired path/format migration must preserve other per-application preferences')

    check(details.count('*technical_actions') == 4 and
          details.count('*component_repair_actions') == 3 and
          details.count('settings_actions = (') == 5 and
          details.count('elif is_backend_only_component(editor):') == 1 and
          'QLabel("Settings")' in details and 'QLabel("Maintenance")' in details and
          'Purge Editor…' in details and 'Purge Reader…' in details and 'Purge Extension…' in details,
          'App Pages must preserve role-specific purge, Developer-only technical and Repair-first Settings')
    store_branch = details[details.index('elif is_backend_only_component(editor):'):details.index('else:', details.index('elif is_backend_only_component(editor):'))]
    check('*component_repair_actions' not in store_branch and
          '("Launch", self.show_store' in store_branch,
          'Store backend exception must not weaken desktop-repair requirements for ordinary applications')
    check(inventory.index('inventory_row.addWidget(hub_details)') <
          inventory.index('inventory_row.addWidget(refresh)') <
          inventory.index('inventory_row.addWidget(open_folder)') <
          inventory.index('inventory_row.addWidget(install_component)') <
          inventory.index('layout.addLayout(inventory_row)') and
          'hub_details.clicked.connect(self.show_suite_details)' in inventory,
          'Installed Applications button order superseded by 0.8.9')

    # Compile/exercise actual sidebar Return handler with Qt-free event doubles.
    handler = _method('SuiteWindow', 'eventFilter')
    fake_qt = SimpleNamespace(Key=SimpleNamespace(Key_Return=13, Key_Enter=10, Key_Escape=27),
                              KeyboardModifier=SimpleNamespace(NoModifier=0),
                              ItemDataRole=SimpleNamespace(UserRole=32))
    fake_event_type = SimpleNamespace(KeyPress='key-press')
    namespace = {'Qt': fake_qt, 'QEvent': SimpleNamespace(Type=fake_event_type)}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[handler], type_ignores=[])), 'app.py', 'exec'), namespace)
    fn = namespace['eventFilter']
    calls: list[tuple] = []
    class FakeItem:
        def __init__(self, key): self.key = key
        def data(self, _): return self.key
    class FakeEvent:
        def type(self): return 'key-press'
        def key(self): return 13
        def modifiers(self): return 0
        def accept(self): calls.append(('accepted',))
    for key, expected in [('__group__:EDITORS', 'toggle'), ('__group__:READERS', 'toggle'),
                          ('markopad', 'launch'), ('gitten', 'launch')]:
        calls.clear()
        item = FakeItem(key)
        sidebar = SimpleNamespace(currentItem=lambda: item)
        fake = SimpleNamespace(editor_list=sidebar,
                               _sidebar_clicked=lambda selected: calls.append(('toggle', selected.key)),
                               _sidebar_double_clicked=lambda selected: calls.append(('launch', selected.key)))
        check(fn(fake, sidebar, FakeEvent()) is True and calls == [(expected, key), ('accepted',)],
              'Enter/Return: wrong group disclosure versus application launch for ' + key)

    print('PASS: 0.8.7 focused Dashboard/Preferences/discovery/sidebar regression checks'
          if not any(e.startswith('0.8.7 correction:') for e in errors) else 'CHECK: 0.8.7 correction regressions')
