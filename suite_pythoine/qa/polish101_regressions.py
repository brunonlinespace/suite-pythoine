"""0.10.1 App Page removal hierarchy / terminology regressions (Qt-free)."""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations

from pathlib import Path


PACKAGE = Path(__file__).resolve().parents[1]


def run_regressions(errors: list[str]) -> None:
    def check(condition: bool, message: str) -> None:
        if not condition:
            errors.append("0.10.1 polish: " + message)

    app = read_app_with_presentations()
    purge = (PACKAGE / "purge_wizard.py").read_text(encoding="utf8")
    tour = (PACKAGE / "ui/dialogs/quick_tour.py").read_text(encoding="utf8")

    check('QPushButton("Uninstall Version…")' in app and 'QPushButton("Remove Version…")' not in app,
          "exact-version action terminology")
    check('QPushButton("Remove Portable")' in app and 'QPushButton("Uninstall Portable")' not in app,
          "Portable runtime action terminology")
    check('QPushButton("Remove AppImage")' in app and 'QPushButton("Uninstall AppImage")' not in app,
          "AppImage runtime action terminology")

    details_start = app.index("def _populate_editor_details")
    details_end = app.index("def _editor_page", details_start)
    details = app[details_start:details_end]
    maintenance_pos = details.index('maintenance_heading = QLabel("Maintenance")')
    settings_area = details[:maintenance_pos]
    check('QPushButton("Purge Editor…")' not in settings_area and 'QPushButton("Purge Reader…")' not in settings_area
          and 'QPushButton("Purge Extension…")' not in settings_area,
          "whole-application Purge must not remain in Settings")
    check('maintenance_heading = QLabel("Maintenance")' in details and
          'maintenance_font.setPointSize(max(maintenance_font.pointSize() + 1, 10))' in details,
          "Maintenance heading must match major-section typography")
    check(details.index('layout.addLayout(history_row)') < maintenance_pos,
          "Maintenance section must follow Current Version / Version History entry")
    check(all(label in details for label in ('QPushButton("Purge Editor…")', 'QPushButton("Purge Reader…")',
                                             'QPushButton("Purge Extension…")', 'QPushButton("Uninstall Suite…")')),
          "role-specific Purge / Suite uninstall buttons missing")
    check('_style_destructive_button(removal_button)' in details,
          "Removal actions lost destructive treatment")
    check('Suite Maintenance' not in details,
          "obsolete Suite Maintenance heading remains")

    check('Uninstall Version, Remove Portable or Remove AppImage.' in purge,
          "Purge scope explanation does not use current removal vocabulary")
    check('Remove Portable removes one runtime; Remove AppImage removes another. Uninstall Version removes one complete managed version' in tour,
          "Quick Tour does not explain the current Remove / Uninstall / Purge hierarchy")

    print("PASS: 0.10.1 App Page Removal hierarchy and terminology regressions"
          if not any(e.startswith("0.10.1 polish:") for e in errors)
          else "CHECK: 0.10.1 App Page polish regressions")
