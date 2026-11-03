"""0.11.0 independent sidebar/layout/launcher regression contract (Qt-free)."""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations

import ast
from pathlib import Path
from types import SimpleNamespace

from suite_pythoine.ui.shell.sidebar_search import matches_application

PACKAGE = Path(__file__).resolve().parents[1]


def _method(source: str, name: str) -> str:
    root = ast.parse(source)
    node = next((obj for obj in ast.walk(root) if isinstance(obj, ast.FunctionDef) and obj.name == name), None)
    return (ast.get_source_segment(source, node) or "") if node else ""


def run_regressions(errors: list[str]) -> None:
    prefix = "0.11.0 sidebar: "

    def check(test: bool, message: str) -> None:
        if not test:
            errors.append(prefix + message)

    app = read_app_with_presentations()
    config = (PACKAGE / "config.py").read_text(encoding="utf8")
    launcher = (PACKAGE / "ui/shell/sidebar_launcher.py").read_text(encoding="utf8")
    search = (PACKAGE / "ui/shell/sidebar_search.py").read_text(encoding="utf8")
    for name, text in (("app", app), ("launcher", launcher), ("search", search)):
        try:
            ast.parse(text)
        except SyntaxError as error:
            check(False, f"{name} cannot parse: {error}")
    check('"sidebar_position": "left"' in config, "default left dock position missing")
    check('"sidebar_visible": True' in config, "existing visibility default changed")
    check('"app_theme": "system"' in config, "exp1 System theme default lost")
    check('("left", "Dock Left")' in app and '("right", "Dock Right")' in app and
          '("floating", "Floating Launcher")' in app, "three exclusive sidebar choices missing")
    check('position_group.setExclusive(True)' in app, "sidebar position must be exclusive")
    check('setShortcut("F9")' in app and 'setShortcut("Shift+F9")' in app,
          "Suite F9 and Plus Shift+F9 shortcuts not retained")
    move = _method(app, "_set_sidebar_mode")
    check('self.splitter.insertWidget(target, self.sidebar)' in move,
          "left/right must move one existing sidebar")
    check('self.splitter.setStretchFactor(' in move and 'self.splitter.setCollapsible(' in move,
          "splitter layout/stretches not reconfigured")
    check('self._sync_sidebar_position_actions()' in move and
          'self.config.set("sidebar_position", mode, save=True)' in move,
          "radio action sync or preference persistence absent")
    check('self.sidebar.hide()' in move, "floating must detach docked sidebar from view")
    logical = _method(app,"_logical_splitter_sizes")
    check('sizes.reverse()' in logical and 'self._restored_sidebar_width' in logical,
          "right-side logical size persistence missing")
    restore = _method(app,"_restore_window_state")
    check('self._normalize_sidebar_mode(self.config.get("sidebar_position", "left"))' in restore,
          "startup does not restore mode with safe default")
    check('self._logical_splitter_sizes()' in _method(app,"closeEvent"),
          "shutdown must not persist inverted physical splitter sizes")
    check('"sidebar_visible": self._sidebar_requested_visible' in _method(app,"closeEvent"),
          "floating visibility not persisted with same setting")
    check('self._sync_launcher_inventory()' in _method(app,"_rebuild_editor_pages"),
          "the launcher is not refreshed from authoritative discovery")
    ensure = _method(app,"_ensure_sidebar_launcher")
    check('self._sidebar_launcher is None' in ensure and 'SidebarLauncher(self)' in ensure,
          "launcher must be created lazily exactly once")
    check('launcher.page_requested.connect(self._launcher_open_page)' in ensure and
          'launcher.launch_requested.connect(self._launcher_launch)' in ensure,
          "launcher actions not connected to existing Suite entry points")
    check('self.show_editor_details(entry)' in _method(app,"_launcher_open_page") and
          'self.launch_editor(entry)' in _method(app,"_launcher_launch"),
          "launcher bypasses normal application workflow")
    check('self._sidebar_mode == "floating"' in _method(app,"_show_initial_floating_launcher") and
          'self.isVisible()' in _method(app,"_show_initial_floating_launcher"),
          "background Store integration must not display stray launcher")
    check('class SidebarLauncher(QDialog):' in launcher and
          'self.setWindowFlag(Qt.WindowType.Tool, True)' in launcher,
          "floating view is not a modeless tool dialog")
    check('self.search.textChanged.connect(self._filter_entries)' in launcher and
          'self.search.returnPressed.connect(self._launch_selected)' in launcher,
          "live type-to-search and Enter-to-launch missing")
    filtering = _method(launcher,"_filter_entries")
    check('matches_application(entry, group, query)' in filtering and
          'discover_editors' not in filtering and '.is_file()' not in filtering and
          '_editor_page(' not in filtering,
          "typing must filter cached metadata only; no disk scanning/page creation")
    check('self._icons = {}' in _method(launcher,"set_entries") and
          'item.setIcon(icon)' in filtering,
          "launcher icons must be cached per refresh rather than on every search")
    check('self.hide()' in _method(launcher,"_open_selected") and
          'self.hide()' in _method(launcher,"_launch_selected"),
          "Open Page/Launch should dismiss the launcher")
    sample=SimpleNamespace(name="Ricopad", editor_id="ricopad", description="rich text editor",
                           extensions=(".rtf",),capabilities=("new", "open"))
    for term in ("rico", ".RTF", "Rich Text", "EDITOR", "Open", ""):
        check(matches_application(sample,"EDITORS",term),f"cached search fails {term!r}")
    check(not matches_application(sample,"EDITORS","not-registered"), "cached search false match")
    # Important: the lightweight search helper must not import the PyQt GUI or registry.
    check('PyQt6' not in search and 'os.scandir' not in search,
          "search helper unexpectedly depends on a GUI or filesystem")
    print('PASS: 0.11.0 three-position/launcher regression suite'
          if not any(error.startswith(prefix) for error in errors)
          else 'CHECK: 0.11.0 sidebar regressions')
