"""0.8.9-specific navigation/inventory regression checks, runnable without PyQt6."""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations

import ast
from pathlib import Path
from types import SimpleNamespace

PACKAGE = Path(__file__).resolve().parents[1]

def _method(source: str, name: str) -> ast.FunctionDef:
    tree = ast.parse(source)
    suite = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'SuiteWindow')
    return next(n for n in suite.body if isinstance(n, ast.FunctionDef) and n.name == name)


def _actual_method(source: str, name: str, namespace: dict):
    node = _method(source, name)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])),
                 'app.py', 'exec'), namespace)
    return namespace[name]


def run_regressions(errors: list[str]) -> None:
    def check(ok: bool, message: str) -> None:
        if not ok:
            errors.append('0.8.9 polish: ' + message)

    source = read_app_with_presentations()
    menu = ast.get_source_segment(source, _method(source, '_make_menu'))
    details = ast.get_source_segment(source, _method(source, '_populate_editor_details'))
    page_source = (PACKAGE / 'ui/pages/installed_applications.py').read_text(encoding='utf8')
    page_fn = next(n for n in ast.parse(page_source).body if isinstance(n, ast.FunctionDef)
                   and n.name == 'build_installed_applications_page')
    inventory = ast.get_source_segment(page_source, page_fn)
    guidance = ast.get_source_segment(source, _method(source, '_show_installed_applications_guidance'))
    shortcuts = ast.get_source_segment(source, _method(source, '_shortcut_catalog'))
    focus = ast.get_source_segment(source, _method(source, '_focus_contextual_search'))
    event = ast.get_source_segment(source, _method(source, 'eventFilter'))
    identity = ast.get_source_segment(source, _method(source, '_add_details_identity_header'))

    tools = menu[menu.index('tools = self.menuBar().addMenu("Tools")'):menu.index('help_menu =')]
    actions = [line.strip() for line in tools.splitlines()
               if line.strip().startswith('tools.addAction(') or line.strip() == 'tools.addSeparator()']
    check(actions == [
        'tools.addAction(self.refresh_action)',
        'tools.addSeparator()',
        'tools.addAction(self.hub_details_action)',
        'tools.addAction(self.preferences_action)',
        'tools.addSeparator()',
        'tools.addAction(self.installed_applications_action)',
        'tools.addAction(self.install_action)',
        'tools.addSeparator()',
        'tools.addAction(self.store_action)',
        'tools.addSeparator()',
        'tools.addAction(self.developer_action)',
        'tools.addAction(self.developer_intake_action)',
        'tools.addAction(self.retain_source_zip_action)',
    ], 'exact Tools commands/separators/order')
    check('self.installed_applications_action.setShortcut("Ctrl+I")' in tools and
          'self.installed_applications_action.triggered.connect(self.show_installed_applications)' in tools and
          'QAction("Get More Applications…", self)' in tools and
          'self.install_action.setShortcut("Ctrl+Shift+I")' in tools and
          'self.open_components_folder_action.setShortcut("Ctrl+Shift+O")' in tools and
          'self.addAction(self.open_components_folder_action)' in tools,
          'Ctrl+I navigation, ellipsis, installer shortcut or keyboard-only folder shortcut')
    check('("Installed Applications", self.installed_applications_action)' in shortcuts and
          'Installed Applications search' in shortcuts and
          'Clear contextual Dashboard / Version History / Installed Applications search' in shortcuts and
          '("Open Applications Folder (keyboard-only)", self.open_components_folder_action)' in shortcuts and
          'self._version_filters.get(self.stack.currentWidget())' in focus and
          'self._version_filters.get(self.stack.currentWidget())' in event,
          'shortcut documentation or contextual search registration')

    hub = details[details.index('elif editor.component_kind == "hub":'):]
    labels = ['("Installed Applications", self.show_installed_applications',
              '*hub_repair_actions', '("Open Config Folder", lambda:',
              '("Hub Preferences…", self.general_preferences']
    check(all(token in hub for token in labels) and
          [hub.index(token) for token in labels] == sorted(hub.index(token) for token in labels) and
          '("Open Applications Folder", lambda:' not in hub,
          'Hub Settings order or duplicated folder button')

    check('self._add_details_identity_header(layout, editor.name, editor.component_kind, editor.icon, lifecycle=lifecycle)' in details and
          'self._add_details_identity_header(' in inventory and
          'self.suite_entry.name if self.suite_entry is not None else APP_NAME' in inventory and
          'self.suite_entry.icon if self.suite_entry is not None else APP_ICON_PATH' in inventory and
          'pixmap(56, 56)' in identity and 'QLabel(f"{kind_label} · Legacy" if lifecycle == "legacy" else kind_label)' in identity and
          'font.setPointSize(max(font.pointSize() + 6, 16))' in identity,
          'Installed header must reuse precisely the Hub title/logo/type renderer')

    button_tokens = [
        'hub_details = QPushButton("Hub Details")',
        'refresh = QPushButton("Refresh Inventory")',
        'open_folder = QPushButton("Open Applications Folder")',
        'install_component = QPushButton("Install Application…")',
    ]
    check(all(t in inventory for t in button_tokens) and
          [inventory.index(t) for t in button_tokens] == sorted(inventory.index(t) for t in button_tokens) and
          inventory.index('layout.addWidget(summary)') < inventory.index('layout.addWidget(settings_heading)') <
          inventory.index('layout.addLayout(inventory_row)') < inventory.index('layout.addLayout(inventory_search_row)') <
          inventory.index('table = QTableWidget(0, 9)') and
          'open_folder.setEnabled(self.editors_root.is_dir())' in inventory and
          'open_folder.clicked.connect(lambda: self.launcher.open_path(self.editors_root))' in inventory and
          'hub_details.clicked.connect(self.show_suite_details)' in inventory and
          'refresh.clicked.connect(lambda: self.refresh_editors(automatic=True))' in inventory and
          'install_component.clicked.connect(self.install_editor_prompt)' in inventory,
          'existing summary and Hub-positioned action buttons are not in exact requested order')
    check('Installed Applications shows {component_count} application' in inventory and
          '<a href=\\"guidance\\">Detailed guidance…</a>' in inventory and
          'Click a heading to sort' in guidance and 'Drag headings to reorder' in guidance and
          'drag separators to resize columns' in guidance and
          'right-click a heading to choose which normal columns are visible' in guidance,
          'inventory summary/guidance contract was lost')

    # Later approved releases broadened search, removed redundant columns and
    # made Remove Assets a transient ninth-column mode of the same table.
    check('table = QTableWidget(0, 9)' in inventory and
          'table.setHorizontalHeaderLabels([*self._inventory_column_labels(), ""])' in inventory and
          'table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)' in inventory and
          'header.setSectionsMovable(True)' in inventory and
          'header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)' in inventory and
          'launch = QPushButton("Launch")' in inventory and
          'app_page = QPushButton("App Page")' in inventory,
          'inventory table interaction or quick actions regressed')
    check('self._version_filters[page] = version_filter' in inventory and
          'version_filter.setMaximumWidth(220)' in inventory and
          'filter_timer.setInterval(150)' in inventory and
          'for column in (0, 1, 2, 3):' in inventory and
          'table.setRowHidden(row, bool(query and not any(query in value for value in searchable)))' in inventory and
          'table.model().layoutChanged.connect(lambda *_args: apply_filter())' in inventory and
          'refresh_editors(' not in inventory[inventory.index('def apply_filter()') : inventory.index('def set_asset_controls')],
          'expanded filter registration/debounce or no-rescan contract')

    # Exercise the actual nested filter callbacks from the production AST, not
    # a parallel fake filtering algorithm. Rows are evaluated in their current
    # (potentially user-sorted) table positions.
    node = page_fn
    actual_callbacks = [n for n in ast.walk(node) if isinstance(n, ast.FunctionDef) and
                        n.name in ('apply_filter', 'schedule_filter')]
    class FakeTable:
        def __init__(self):
            self.rows = [
                ['Ricopad', '0.8.9', 'Portable', 'Yes'],
                ['Markopad', '1.2.3', 'AppImage', 'No'],
                ['Nuxpad', '0.8.0-R3', 'Portable', 'No'],
                ['Texypad', '0.7.4', 'AppImage', 'Yes'],
            ]
            self.hidden = {}
        def rowCount(self): return len(self.rows)
        def item(self, row, col):
            return SimpleNamespace(text=lambda: self.rows[row][col])
        def setRowHidden(self, row, value): self.hidden[row] = value
    class FakeTimer:
        def __init__(self): self.started = False; self.stopped = False
        def stop(self): self.started = False; self.stopped = True
        def start(self): self.started = True
    table = FakeTable()
    timer = FakeTimer()
    search = SimpleNamespace(_text='0.8', text=lambda: search._text)
    scope = {'table': table, 'filter_timer': timer, 'version_filter': search, 'sync_selection_header': lambda: None}
    exec(compile(ast.fix_missing_locations(ast.Module(body=actual_callbacks, type_ignores=[])),
                 'app.py', 'exec'), scope)
    schedule, apply = scope['schedule_filter'], scope['apply_filter']
    schedule('0.8')
    check(timer.started and not table.hidden, 'typing must debounce without an immediate row rescan')
    apply()
    check([table.hidden[i] for i in range(4)] == [False, True, False, True],
          'case-insensitive partial filtering across installed-application fields')
    table.rows = table.rows[::-1]  # Simulate a user changing the table's sort order.
    apply()
    check([table.hidden[i] for i in range(4)] == [True, False, True, False],
          'filter must inspect current rows after sorting, not stale record indexes')
    search._text = ''
    schedule('')
    check(timer.stopped and not timer.started and all(not table.hidden[i] for i in range(4)),
          'clearing filter must immediately reveal all table rows')

    # Exercise Ctrl+F and Escape on Installed Applications using the same
    # production contextual handlers used on App Pages and Dashboard.
    actions = []
    inventory_page, dashboard_page = object(), object()
    focus_filter = SimpleNamespace(
        setFocus=lambda reason: actions.append(('focus', reason)),
        selectAll=lambda: actions.append(('select',)),
        clear=lambda: actions.append(('clear',)),
    )
    fake_qt = SimpleNamespace(FocusReason=SimpleNamespace(ShortcutFocusReason=123),
                              Key=SimpleNamespace(Key_Escape=27))
    focus_scope = {'Qt': fake_qt}
    focus_handler = _actual_method(source, '_focus_contextual_search', focus_scope)
    window = SimpleNamespace(stack=SimpleNamespace(currentWidget=lambda: inventory_page),
                             _version_filters={inventory_page: focus_filter},
                             show_dashboard=lambda: actions.append(('dashboard',)),
                             dashboard=SimpleNamespace(search=SimpleNamespace(
                                 setFocus=lambda *_: actions.append(('dashfocus',)))))
    focus_handler(window)
    check(actions == [('focus', 123), ('select',)], 'Ctrl+F must select Installed Applications search in place')
    # Esc is caught before all other event-filter paths, so only model the
    # KeyPress/Escape branch and its event acceptance.
    esc_node = _method(source, 'eventFilter')
    esc_source = ast.get_source_segment(source, esc_node)
    check('version_filter.clear()' in esc_source and
          esc_source.index('version_filter.clear()') < esc_source.index('self.dashboard.search.clear()'),
          'Esc must first check the current page-specific search')

    print('PASS: 0.8.9 exact menu/header/buttons/table and exercised contextual search callbacks'
          if not any(e.startswith('0.8.9 polish:') for e in errors) else 'CHECK: 0.8.9 regressions')
