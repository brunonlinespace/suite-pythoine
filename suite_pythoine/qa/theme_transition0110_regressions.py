"""0.11.0 menu placement and theme-transition regressions (Qt-free)."""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations

from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

PACKAGE = Path(__file__).resolve().parents[1]


def run_regressions(errors: list[str]) -> None:
    def check(ok: bool, message: str) -> None:
        if not ok:
            errors.append(f"0.11.0: {message}")

    app = read_app_with_presentations()
    dashboard = (PACKAGE / "ui/shell/dashboard.py").read_text(encoding="utf8")
    launcher = (PACKAGE / "ui/shell/sidebar_launcher.py").read_text(encoding="utf8")
    theme = (PACKAGE / "ui/shell/suite_theme.py").read_text(encoding="utf8")

    view = app.split('view = self.menuBar().addMenu("View")', 1)[-1].split(
        'tools = self.menuBar().addMenu("Tools")', 1)[0]
    tools = app.split('tools = self.menuBar().addMenu("Tools")', 1)[-1].split(
        'help_menu = self.menuBar().addMenu("Help")', 1)[0]
    between_dashboard = view.split('view.addAction(self.dashboard_action)', 1)[-1].split(
        'dashboard_settings = view.addMenu("Dashboard Settings")', 1)[0]
    check('dashboard_settings = view.addMenu("Dashboard Settings")' in view and
          'view.addSeparator()' not in between_dashboard and
          'view.addAction(' not in between_dashboard,
          "Dashboard and Dashboard Settings are not adjacent")
    check('view.addAction(self.refresh_action)' not in view,
          "Refresh Applications remains in View")
    check('view.addSeparator()\n        view.addAction(self.fullscreen_action)' in view,
          "separator immediately before Full Screen is missing")
    check(tools.lstrip().startswith('tools.addAction(self.refresh_action)\n        tools.addSeparator()'),
          "Refresh Applications is not the first Tools command with following separator")
    check('self.refresh_action.setShortcut("F5")' in app and
          'self.refresh_action.triggered.connect(self.refresh_editors)' in app,
          "Refresh Applications F5/handler has changed")

    check('app.style().standardPalette()' in theme and 'app.setStyleSheet("")' in theme,
          "fresh platform palette/reset missing")
    check('_SYSTEM_PALETTE' not in theme, "stale native-palette snapshot remains")
    theme_method = app.split('def _set_theme(self, theme: str)', 1)[-1].split(
        'def _toggle_fullscreen(', 1)[0]
    check('self.dashboard.refresh_theme()' in theme_method and
          'self._sidebar_launcher.refresh_theme()' in theme_method and
          'button.property("suite_destructive")' in theme_method,
          "live theme change fails to update persistent surfaces")
    dash_method = dashboard.split('def refresh_theme(self)', 1)[-1].split(
        'def set_components(', 1)[0]
    check('self.drop_bar' in dash_method and 'self.findChildren(EditorCard)' in dash_method and
          '_replace_card_bodies' not in dash_method,
          "Dashboard theme change rebuilds cards or skips QSS refresh")
    launcher_method = launcher.split('def refresh_theme(self)', 1)[-1].split(
        'def set_entries(', 1)[0]
    check('self.search' in launcher_method and 'self.entries' in launcher_method and
          'set_entries(' not in launcher_method,
          "launcher theme change recreates or reloads inventory")

    # Execute the real palette function using minimal Qt fakes, without
    # importing QWidget or requiring Qt/PyQt6 in the release-check runtime.
    class Roles:
        pass
    for name in ('Window','WindowText','Base','AlternateBase','ToolTipBase',
                 'ToolTipText','Text','Button','ButtonText','Light','Midlight',
                 'Mid','Dark','Shadow','Highlight','HighlightedText',
                 'PlaceholderText','Link','LinkVisited'):
        setattr(Roles, name, name)

    class FakePalette:
        ColorRole = Roles
        def __init__(self, other=None):
            self.colors = dict(other.colors) if other is not None else {}
        def setColor(self, role, color):
            self.colors[role] = color
        def color(self, role):
            return self.colors.get(role)

    class FakeColor:
        def __init__(self, value):
            self.value = value
        def __eq__(self, other):
            return isinstance(other, FakeColor) and self.value == other.value

    class FakeApp:
        def __init__(self):
            self.desktop = FakePalette()
            self.desktop.setColor(Roles.Window, FakeColor("desktop-initial"))
            self.current = None
            self.stylesheet = "other"
        def style(self):
            return SimpleNamespace(standardPalette=lambda: FakePalette(self.desktop))
        def setStyleSheet(self, value):
            self.stylesheet = value
        def setPalette(self, value):
            self.current = FakePalette(value)

    qt = ModuleType('PyQt6')
    gui = ModuleType('PyQt6.QtGui')
    gui.QColor, gui.QPalette = FakeColor, FakePalette
    widgets = ModuleType('PyQt6.QtWidgets')
    widgets.QApplication = FakeApp
    ns = {'__name__': 'suite_theme_test'}
    try:
        with patch.dict(sys.modules, {'PyQt6': qt, 'PyQt6.QtGui': gui,
                                      'PyQt6.QtWidgets': widgets}):
            exec(compile(theme, str(PACKAGE / 'ui/shell/suite_theme.py'), 'exec'), ns)
        sample = FakeApp()
        ns['apply_theme'](sample, 'dark')
        check(sample.current.color(Roles.Highlight) == FakeColor('#F08A24'),
              'dark accent did not match Suite orange')
        sample.desktop.setColor(Roles.Window, FakeColor('desktop-updated'))
        ns['apply_theme'](sample, 'light')
        check(sample.current.color(Roles.Highlight) == FakeColor('#C05800'),
              'light accent did not match Suite orange')
        ns['apply_theme'](sample, 'system')
        check(sample.current.color(Roles.Window) == FakeColor('desktop-updated'),
              'System restored stale startup KDE window color')
        check(sample.current.color(Roles.Highlight) is None,
              'System still has the app-specific orange palette override')
        check(sample.stylesheet == '', 'application-level QSS reset not applied')
    except Exception as exc:
        check(False, f'headless palette transition test raised {type(exc).__name__}: {exc}')
