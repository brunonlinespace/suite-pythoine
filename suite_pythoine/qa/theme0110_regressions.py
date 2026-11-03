"""0.11.0 dependency-light theme integration regressions."""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]


def run_regressions(errors: list[str]) -> None:
    def check(ok: bool, message: str) -> None:
        if not ok:
            errors.append(f"0.11.0 theme: {message}")

    config = (PACKAGE / "config.py").read_text(encoding="utf-8")
    app = read_app_with_presentations()
    theme = (PACKAGE / "ui/shell/suite_theme.py").read_text(encoding="utf-8")
    shared = (PACKAGE / "ui/diagnostic_helpers.py").read_text(encoding="utf-8")

    check('"app_theme": "system"' in config, "System-preserving default missing")
    check('from .ui.shell.suite_theme import apply_theme, normalize_theme' in app, "theme integration import missing")
    check('apply_theme(app, normalize_theme(config.get("app_theme", "system")))' in app,
          "persisted theme is not applied before SuiteWindow construction")
    check('theme_menu = view.addMenu("App Theme")' in app, "App Theme menu missing")
    for value in ("light", "dark", "system"):
        check(f'("{value}", ' in app or f'["{value}"]' in app, f"{value} theme action missing")
    check('self.config.set("app_theme", theme, save=True)' in app, "theme choice is not persisted")
    check('QColor("#C05800")' in theme and 'QColor("#F08A24")' in theme,
          "Suite orange accent pair missing")
    for colour in ("#D4D4D4", "#F4F4F4", "#E4E4E4", "#202326", "#151719", "#292D31"):
        check(colour in theme, f"neutral Plus-family surface {colour} missing")
    check('QPalette.ColorRole.Highlight' in theme and 'QPalette.ColorRole.Link' in theme,
          "orange accent is not connected to selection/link palette roles")
    check('app.style().standardPalette()' in theme and
          'app.setPalette(palette)' in theme and
          'if theme == "system":' in theme,
          "System theme does not restore the current native Qt style palette")
    check('button.setProperty("suite_destructive", True)' in shared and
          'button.property("suite_destructive")' in app,
          "danger buttons are not rethemed after live palette changes")
