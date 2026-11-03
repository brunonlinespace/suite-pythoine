"""0.11.2 Qt-free safeguards for the Dashboard palette inheritance fix."""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]


def run_regressions(errors: list[str]) -> None:
    prefix = "0.11.2 Dashboard theme: "

    def check(condition: bool, message: str) -> None:
        if not condition:
            errors.append(prefix + message)

    source = (PACKAGE / "ui/shell/dashboard.py").read_text(encoding="utf-8")
    theme = (PACKAGE / "ui/shell/suite_theme.py").read_text(encoding="utf-8")
    app = read_app_with_presentations()
    tree = ast.parse(source)
    classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
    for name in ("PalettePanel", "DropBar", "EditorCard", "EditorDashboard"):
        check(name in classes, f"missing {name} class")
    if not all(name in classes for name in ("PalettePanel", "DropBar", "EditorCard")):
        return
    for name in ("DropBar", "EditorCard"):
        node = classes[name]
        check(any(isinstance(base, ast.Name) and base.id == "PalettePanel" for base in node.bases),
              f"{name} no longer uses isolated PalettePanel")
        check(not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and
                      n.func.attr == "setStyleSheet" for n in ast.walk(node)),
              f"{name} sets widget-local CSS that can cascade to children")
    panel = classes["PalettePanel"]
    paint = next((n for n in panel.body if isinstance(n, ast.FunctionDef) and n.name == "paintEvent"), None)
    check(paint is not None, "palette-driven frame paintEvent missing")
    if paint is not None:
        drawn = ast.get_source_segment(source, paint) or ""
        for token in ("QPainter(self)", "QPalette.ColorRole.Button", "QPalette.ColorRole.Mid", "drawRoundedRect"):
            check(token in drawn, f"frame drawing missing {token}")
    check('setStyleSheet("border: none;")' not in source,
          "obsolete per-QLabel CSS still invokes the stylesheet engine")
    refresh = next((n for n in classes["EditorDashboard"].body if isinstance(n, ast.FunctionDef)
                    and n.name == "refresh_theme"), None)
    check(refresh is not None and 'self.drop_bar' in ast.get_source_segment(source, refresh) and
          'self.findChildren(EditorCard)' in ast.get_source_segment(source, refresh) and
          'widget.update()' in ast.get_source_segment(source, refresh),
          "theme refresh does not repaint existing Dashboard panels")
    if refresh is not None:
        check('unpolish' not in ast.get_source_segment(source, refresh),
              "stylesheet repolishing reintroduced in Dashboard refresh")
    method = ast.get_source_segment(theme, next(n for n in ast.parse(theme).body
                                    if isinstance(n, ast.FunctionDef) and n.name == 'apply_theme'))
    check('app.setPalette(app.style().standardPalette())' in method,
          "old custom palette not reset before new theme")
    check(method.index('app.setPalette(app.style().standardPalette())') < method.index('if theme == "system":'),
          "System must return only after resetting to platform palette")
    check('self.dashboard.refresh_theme()' in app, "theme controller no longer repaints Dashboard")
    print('PASS: 0.11.2 isolated palette-paint Dashboard theme regressions'
          if not any(e.startswith(prefix) for e in errors)
          else 'CHECK: 0.11.2 Dashboard theme regressions')
