"""0.11.0 Dashboard Launch/floating-sidebar contract (no Qt required)."""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations

import ast
from pathlib import Path
from types import SimpleNamespace

PACKAGE = Path(__file__).resolve().parents[1]


def _function(source: str, name: str):
    tree = ast.parse(source)
    node = next((item for item in ast.walk(tree)
                 if isinstance(item, ast.FunctionDef) and item.name == name), None)
    if node is None:
        raise LookupError(name)
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace: dict[str, object] = {}
    exec(compile(module, f'<isolated {name}>', 'exec'), namespace)
    return namespace[name]


def run_regressions(errors: list[str]) -> None:
    prefix = '0.11.0 Dashboard Launch: '

    def check(ok: bool, message: str) -> None:
        if not ok:
            errors.append(prefix + message)

    app = read_app_with_presentations()
    dashboard = (PACKAGE / 'ui/shell/dashboard.py').read_text(encoding='utf8')
    for name, text in (('app', app), ('dashboard', dashboard)):
        try:
            ast.parse(text)
        except SyntaxError as exception:
            check(False, f'{name} does not parse: {exception}')
            return

    check('self.launch_button = QPushButton("Launch…")' in dashboard,
          'Dashboard Launch must be retained as a persistent widget')
    check('self.launch_button.hide()' in dashboard,
          'Dashboard Launch must start hidden for default docked modes')
    check('self.launch_button.clicked.connect(self.launch_prompt_requested.emit)' in dashboard,
          'Dashboard Launch must retain a click signal')
    check('self.dashboard.launch_prompt_requested.connect(self._show_dashboard_launcher)' in app,
          'Dashboard Launch must open the floating sidebar, not launch_prompt')
    check('self.dashboard.launch_prompt_requested.connect(self.launch_prompt)' not in app,
          'old Dashboard selection prompt still connected')

    position = ast.get_source_segment(app, next(node for node in ast.walk(ast.parse(app))
                         if isinstance(node, ast.FunctionDef) and node.name == '_set_sidebar_mode'))
    check('self.dashboard.set_launcher_button_visible(mode == "floating")' in position,
          'mode transition must show Launch only for Floating Launcher')
    check('self._set_sidebar_mode(' in app and
          'self._normalize_sidebar_mode(self.config.get("sidebar_position", "left"))' in app,
          'startup must restore mode and apply Dashboard button visibility')
    check('self.launch_action.triggered.connect(self.launch_prompt)' in app,
          'File/F4 Launch command must remain unchanged')

    class Button:
        visible = None

        def setVisible(self, value):
            self.visible = value

    button = Button()
    try:
        _function(dashboard, 'set_launcher_button_visible')(SimpleNamespace(launch_button=button), True)
        check(button.visible is True, 'floating mode does not expose Dashboard Launch')
        _function(dashboard, 'set_launcher_button_visible')(SimpleNamespace(launch_button=button), False)
        check(button.visible is False, 'docked mode does not hide Dashboard Launch')
    except Exception as exception:
        check(False, f'Dashboard show/hide execution failed: {exception}')

    for mode, expected_calls in (('left', 0), ('right', 0), ('floating', 1)):
        calls: list[bool] = []
        controller = SimpleNamespace(_sidebar_mode=mode,
                                     _set_sidebar_visible=lambda shown: calls.append(shown))
        try:
            _function(app, '_show_dashboard_launcher')(controller)
            check(calls == ([True] if expected_calls else []),
                  f'{mode}: Dashboard Launch must only reveal floating sidebar')
        except Exception as exception:
            check(False, f'{mode}: open/focus dispatch failed: {exception}')

    show = ast.get_source_segment(app, next(node for node in ast.walk(ast.parse(app))
                  if isinstance(node, ast.FunctionDef) and node.name == '_set_sidebar_visible'))
    check('launcher.raise_()' in show and 'launcher.activateWindow()' in show and
          'launcher.focus_search()' in show,
          'reopening an existing launcher must raise and focus its search')
    check('self.config.set("sidebar_visible", bool(visible), save=True)' in show,
          'reopening launcher must restore normal persistent sidebar visibility')

    print('PASS: 0.11.0 Dashboard Launch visibility/routing regressions'
          if not any(error.startswith(prefix) for error in errors)
          else 'CHECK: 0.11.0 Dashboard Launch regressions')
