"""Optional REAL PyQt6 offscreen smoke test for the Dashboard theme regression.

Run with `QT_QPA_PLATFORM=offscreen python3 -m suite_pythoine.qa.theme0112_qt`
in an environment with PyQt6. The static release gate remains independent of Qt.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys


def contrast(foreground, background) -> float:
    def linear(channel):
        value = channel / 255.0
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    def brightness(color):
        return sum(weight * linear(value) for weight, value in zip(
            (0.2126, 0.7152, 0.0722), (color.red(), color.green(), color.blue())))
    a, b = sorted((brightness(foreground), brightness(background)))
    return (b + 0.05) / (a + 0.05)


def run() -> None:
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PyQt6.QtGui import QPalette
    from PyQt6.QtWidgets import QApplication, QLabel, QPushButton
    from suite_pythoine.ui.shell.dashboard import DropBar, EditorCard, EditorDashboard
    from suite_pythoine.registry import EditorEntry
    from suite_pythoine.ui.shell.sidebar_launcher import SidebarLauncher
    from suite_pythoine.ui.shell.suite_theme import apply_theme

    app = QApplication.instance() or QApplication(['suite-theme-smoke'])
    dashboard = EditorDashboard('Suite Pythoine', Path('/nonexistent'))
    editor = EditorEntry(editor_id='maqaronypad', name='Theme Smoke Entry',
                         root=Path('/nonexistent'), component_kind='editor',
                         extensions=('.md',), portable_command=('test',))
    dashboard.set_components([editor])
    launcher = SidebarLauncher()
    dashboard.resize(940, 750)
    dashboard.show()
    launcher.show()

    for position, mode in (('list','dark'), ('grid','light'), ('list','dark'),
                           ('grid','system'), ('list','light'), ('grid','dark')):
        dashboard.set_view_mode(position)
        apply_theme(app, mode)
        dashboard.refresh_theme()
        launcher.refresh_theme()
        app.processEvents()
        cards = dashboard.findChildren(EditorCard)
        assert cards, f'{position}: cards disappeared on {mode} theme'
        for card in cards:
            assert not card.styleSheet(), f'{mode}: card inherited local stylesheet'
            background = card.palette().color(QPalette.ColorRole.Button)
            labels = card.findChildren(QLabel)
            assert labels
            for label in labels:
                assert not label.styleSheet(), f'{mode}: stale stylesheet on child label'
                text = label.palette().color(QPalette.ColorRole.WindowText)
                assert contrast(text, background) >= 4.5, f'{mode}: label contrast {contrast(text, background):.2f}'
            for button in card.findChildren(QPushButton):
                assert not button.styleSheet(), f'{mode}: stale stylesheet on card button'
                palette = button.palette()
                fg = palette.color(QPalette.ColorRole.ButtonText)
                bg = palette.color(QPalette.ColorRole.Button)
                assert contrast(fg, bg) >= 4.5, f'{mode}: button contrast {contrast(fg, bg):.2f}'
        assert not dashboard.drop_bar.styleSheet(), 'DropBar local stylesheet returned'
        assert contrast(dashboard.drop_bar.label.palette().color(QPalette.ColorRole.WindowText),
                        dashboard.drop_bar.palette().color(QPalette.ColorRole.Button)) >= 4.5
        assert contrast(launcher.search.palette().color(QPalette.ColorRole.Text),
                        launcher.search.palette().color(QPalette.ColorRole.Base)) >= 4.5
        print(f'PASS: Qt {mode} / {position}, {len(cards)} real cards; labels, buttons, DropBar, launcher')

    apply_theme(app, 'system')
    app.processEvents()
    for role in (QPalette.ColorRole.Window, QPalette.ColorRole.WindowText, QPalette.ColorRole.Button):
        assert app.palette().color(role) == app.style().standardPalette().color(role), 'System native palette mismatch'
    launcher.close()
    dashboard.close()
    print('PASS: real PyQt6 offscreen theme-transition GUI smoke test')


if __name__ == '__main__':
    try:
        run()
    except ImportError as exc:
        print(f'Qt GUI test cannot run: {exc}', file=sys.stderr)
        sys.exit(2)
