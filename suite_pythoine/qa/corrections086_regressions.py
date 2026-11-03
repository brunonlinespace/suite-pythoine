"""0.8.6 narrow UI/wiring corrections; inspect and execute real Qt-free handlers."""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations
import ast
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
PREFERENCES = ROOT / 'ui' / 'dialogs' / 'preferences.py'

def _class_source(klass):
    path = PREFERENCES if klass in {'EditorPreferencesDialog', 'GeneralPreferencesDialog'} else ROOT / 'app.py'
    return path.read_text(encoding='utf8') if path == PREFERENCES else read_app_with_presentations()

def _method(klass, name):
    source = _class_source(klass)
    tree = ast.parse(source)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == klass)
    return next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)

def _method_source(klass, name):
    source = _class_source(klass)
    return ast.get_source_segment(source, _method(klass, name))

def run_regressions(errors: list[str]) -> None:
    def check(ok, description):
        if not ok: errors.append('0.8.6 correction: ' + description)
    app = read_app_with_presentations()
    shared = (ROOT / "ui/diagnostic_helpers.py").read_text(encoding="utf8")
    dashboard = (ROOT/'ui/shell/dashboard.py').read_text(encoding='utf8')
    menu = app[app.index('    def _make_menu('):app.index('    def _build_sidebar(')]
    sidebar = app[app.index('    def _build_sidebar('):app.index('    def _legacy_portable_root(')]
    rebuild = ast.get_source_segment(app, _method('SuiteWindow', '_rebuild_editor_pages'))
    pref_source = PREFERENCES.read_text(encoding='utf8')
    pref = _method_source('GeneralPreferencesDialog', '__init__')
    version = _method_source('GeneralPreferencesDialog', '_preferences_version_frame')
    page = _method_source('SuiteWindow', '_populate_editor_details')

    check(menu.index('file_menu.addAction(self.launch_action)') < menu.index('file_menu.addSeparator()') < menu.index('self.new_action'),
          'File menu separator is not directly after Launch')
    check('QPushButton("Get More…")' in sidebar and 'QAction("Get More Applications…", self)' in menu,
          'sidebar and AppMenu Get More labels not distinct')
    check('add_heading("HUB")' not in rebuild and
          all('add_sidebar_group("' + name + '"' in rebuild for name in ('EDITORS', 'READERS', 'EXTENSIONS')),
          'extra Hub sidebar group or missing application groups')
    hub_page = page[page.index('elif editor.component_kind == "hub":'):]
    check(page.count('"Installed Applications", self.show_installed_applications') == 1 and
          '"Open Applications Folder", lambda:' not in hub_page and
          hub_page.index('"Installed Applications", self.show_installed_applications') < hub_page.index('*hub_repair_actions') <
          hub_page.index('"Open Config Folder", lambda:'),
          'Hub Details Settings: Installed Applications / Repair / Config order')
    check('QLabel("Settings")' in page and 'add_section("Hub"' not in page,
          'Suite Details should have Settings, not redundant Hub header')
    check(page.count('application_actions = (') == 5 and page.count('settings_actions = (') == 5 and
          'elif is_backend_only_component(editor):' in page and
          'add_section("File"' not in page and 'add_section("Extension"' not in page,
          'Editor/Reader/Extension plus Store-backend Application and Settings section contract')
    check('"Technical Details…"' in page and 'suite_developer_only' in page and
          'button.setVisible(self.developer_config.enabled)' in page and page.count('*technical_actions') == 4 and
          page.index('"Open File…", lambda: self.open_with_editor_prompt(editor)') < page.index('*technical_actions') < page.index('settings_actions = ('),
          'technical details must be Developer-only and finish Application actions')
    store_branch = page[page.index('elif is_backend_only_component(editor):'):page.index('else:', page.index('elif is_backend_only_component(editor):'))]
    check('("Launch", self.show_store' in store_branch and
          '*technical_actions' in store_branch and '*component_repair_actions' not in store_branch and
          'Open Extension Folder' in store_branch,
          'Store backend exception must be narrow and must not alter ordinary desktop-repair branches')
    check('self.tabs.addTab(information_page, "Technical Details")' in pref and
          'self.tabs.addTab(information_page, "Information")' not in pref and
          '_diagnostic_canvas(information_page)' in pref,
          'Suite only has Preferences Technical Details canvas')
    # 0.8.8 consolidates the 0.8.6 row/groups, preserving the repair callback.
    check(pref.index('runtime_row.addWidget(self.suite_runtime, 1)') <
          pref.index('runtime_row.addWidget(self.repair_desktop_button)') <
          pref.index('runtime_row.addWidget(self.open_portable_button)') <
          pref.index('runtime_row.addWidget(self.open_installed_button)') <
          pref.index('general_layout.addWidget(runtime_group)') < pref.index('QGroupBox("Dashboard")'),
          'repair must remain alongside selector before Dashboard')
    check('self.tabs.addTab(runtime_page, "Runtime")' not in pref and
          'QGroupBox("Portable Runtime")' not in pref and 'QGroupBox("AppImage Runtime")' not in pref,
          'retired separate Runtime controls have resurfaced')
    check(version.index('actions.addWidget(make_active)') < version.index('actions.addWidget(launch_portable)') and
          version.index('actions.addWidget(open_folder)') < version.index('actions.addWidget(remove_version)') <
          version.index('actions.addStretch(1)'), 'Suite Preferences version Make Active first / Uninstall Version last')
    check('QTextEdit { background-color: #151719; color: #dcdcdc;' in shared and
          'border: 1px solid #333333;' in shared and 'QColor("#9cdcfe")' in shared and
          '_populate_diagnostic_canvas(information, self._editor_information_text(editor))' in app and
          '_populate_diagnostic_canvas(self.information_label, self.controller._editor_information_text(editor))' in pref_source,
          'Inspector Sources canvas must style both technical views')
    check('buttons.addButton("Copy Details"' in app and 'information.toPlainText()' in app,
          'Copy Details must survive QTextEdit change')
    check('self.editor_list.currentItemChanged.connect(self._sidebar_current_changed)' in sidebar and
          'self.editor_list.itemDoubleClicked.connect(self._sidebar_double_clicked)' in sidebar and
          'itemActivated.connect' not in sidebar and
          'self._sidebar_double_clicked(selected)' in app and 'self._sidebar_clicked(selected)' in app and
          'Qt.Key.Key_Return, Qt.Key.Key_Enter' in app,
          'arrow selection, keyboard Enter and mouse double click must be separate')
    check('self.dashboard.view_toggle_requested.connect(self._toggle_dashboard_view)' in app and
          dashboard.index('controls.addWidget(self.sort)') < dashboard.index('controls.addWidget(self.view_toggle)') <
          dashboard.index('controls.addWidget(refresh)') and
          'self.view_toggle.setText(next_label)' in dashboard and
          'self.config.set("dashboard_view", mode)' in app,
          'Dashboard toggle must use and reflect existing persisted View setting')

    # Execute the actual repair callback without Qt: an unsaved launch choice
    # must not repair silently to the OLD runtime while the combo shows NEW.
    repair_method = _method('GeneralPreferencesDialog', '_repair_desktop_integration')
    namespace = {'saved_launch_mode': lambda *_: 'portable', 'QMessageBox': SimpleNamespace(
        information=lambda *_: calls.append('unsaved warned')),
        'app_dialog_title': lambda title: title}
    calls: list[str] = []
    exec(compile(ast.fix_missing_locations(ast.Module(body=[repair_method], type_ignores=[])),
                 'app.py', 'exec'), namespace)
    fn = namespace['_repair_desktop_integration']
    fake = SimpleNamespace(_current_suite_entry=lambda: object(),
                           suite_runtime=SimpleNamespace(currentData=lambda: 'installed'),
                           config=SimpleNamespace(as_dict=lambda: {}),
                           controller=SimpleNamespace(repair_suite_desktop_integration=lambda *_: calls.append('repaired')),
                           _refresh_suite_management_views=lambda: calls.append('refreshed'))
    fn(fake)
    check(calls == ['unsaved warned'], 'unsaved runtime choice must not cause repair to wrong runtime')
    calls.clear(); fake.suite_runtime.currentData = lambda: 'portable'; fn(fake)
    check(calls == ['repaired', 'refreshed'], 'saved runtime repair no longer delegates to original callback')
    print('PASS: 0.8.6 narrow UI/wiring and repair-regression checks' if not any(e.startswith('0.8.6 correction:') for e in errors)
          else 'CHECK: 0.8.6 correction regressions')
