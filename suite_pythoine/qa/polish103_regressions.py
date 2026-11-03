"""0.10.3 corrective Developer Intake / removal / Preferences regressions."""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations

from pathlib import Path

from suite_pythoine.developer.developer_policy import developer_intake_drop, developer_retain_drop

PACKAGE = Path(__file__).resolve().parents[1]


def run_regressions(errors: list[str]) -> None:
    def check(condition: bool, message: str) -> None:
        if not condition:
            errors.append("0.10.3 polish: " + message)

    app = read_app_with_presentations()
    shared = (PACKAGE / "ui/diagnostic_helpers.py").read_text(encoding="utf8")
    preferences = (PACKAGE / "ui/dialogs/preferences.py").read_text(encoding="utf8")
    intake = (PACKAGE / "developer/developer_intake.py").read_text(encoding="utf8")
    purge = (PACKAGE / "purge_wizard.py").read_text(encoding="utf8")

    # Developer Intake uses a mandatory ZIP/version container in both modes.
    planned_start = intake.index("    def _planned_intake(")
    planned_end = intake.index("    def _refresh_prepared_preview", planned_start)
    planned = intake[planned_start:planned_end]
    check("dev_folder = root / path.stem" in planned,
          "every intake does not begin inside a ZIP-derived container")
    check("source_folder = dev_folder if source_relative is None else dev_folder / source_relative" in planned,
          "blank Source folder does not resolve to the intake/version folder")
    check("notes_folder = dev_folder if notes_relative is None else dev_folder / notes_relative" in planned,
          "blank Release Notes folder does not resolve to the intake/version folder")
    check('QCheckBox("Keep extracted files in a ZIP-named subfolder")' not in intake,
          "obsolete optional ZIP-subfolder extraction control remains")
    check("protected_paths=tuple(protected_items), refuse_existing=True" in intake,
          "direct extraction into the intake Source folder is not collision protected")

    # README filename is user-configurable, persistent, and blank safely defaults.
    check('DEFAULT_README_FILENAME = "README.md"' in intake and 'QLabel("Notes file:")' in intake,
          "notes filename control/default missing")
    check('self.config.data["readme_filename"] = self._readme_filename()' in intake,
          "README filename is not persisted")
    check('self.readme_filename_edit.text().strip() or DEFAULT_README_FILENAME' in intake,
          "blank README filename does not fall back to README.md")
    check('if not text.strip():\n            return None' in intake,
          "empty README content can still generate a file")
    check('prepared.notes_folder / prepared.readme_filename' in intake,
          "README output ignores the configured filename")
    check('suite-pythoine-128.png' in intake and 'configure_operation_window(self)' in intake and
          'operation_branding_header(' in intake,
          "Developer Intake lacks the agreed Suite-branded dialog treatment")

    # Developer Mode drop default is Intake; Shift bypasses to the normal installer; Ctrl retains Recovery.
    SHIFT, CTRL, ALT, META = (1, 2, 4, 8)
    check(developer_intake_drop(True, "Ricopad.zip", 0, shift_mask=SHIFT,
                                other_modifiers=CTRL | ALT | META),
          "unmodified Developer Mode ZIP drop does not enter Intake")
    check(not developer_intake_drop(True, "Ricopad.zip", SHIFT, shift_mask=SHIFT,
                                    other_modifiers=CTRL | ALT | META),
          "Shift+ZIP does not bypass Developer Intake")
    check(developer_retain_drop(True, "Ricopad.zip", CTRL, ctrl_mask=CTRL,
                                other_modifiers=SHIFT | ALT | META),
          "Ctrl+ZIP Recovery-only retention regressed")
    check("Normal ZIP drops open Developer Intake; Shift+ZIP bypasses Intake" in preferences,
          "Developer Mode user-facing drop contract was not updated")

    # Purge version inventory must scroll independently instead of clipping long histories.
    check("inventory_scroll = QScrollArea()" in purge and
          "layout.addWidget(inventory_scroll, 1)" in purge and
          "inventory_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)" in purge,
          "Purge review inventory is still non-scrollable")

    # AppImage removal must inspect exact runtime desktop ownership, not version-level desktop flags.
    remove_start = app.index("    def uninstall_appimage_runtime(")
    remove_end = app.index("    @staticmethod\n    def _inventory_column_labels", remove_start)
    remove = app[remove_start:remove_end]
    check('if self._desktop_runtime_owns_version(editor, version, "AppImage"):' in remove,
          "AppImage removal does not use exact runtime desktop ownership")
    check("version.desktop_integrated or version.version == editor.desktop_version" not in remove,
          "AppImage removal still blocks a sibling AppImage because Portable owns the same version")

    # Preferences uses one contextual left footer action beside right-aligned Save/Cancel.
    check("footer.addWidget(self.routing_reset_button)" in preferences and
          "footer.addWidget(self.uninstall_suite_button)" in preferences and
          "footer.addStretch(1)" in preferences and "footer.addWidget(buttons)" in preferences,
          "Hub Preferences contextual actions are not in the shared footer")
    check('self.routing_reset_button.setVisible(label == "File Routing")' in preferences and
          'self.uninstall_suite_button.setVisible(label == "Hub Versions")' in preferences,
          "Hub Preferences footer does not switch action by active tab")
    check('routing_outer.addWidget(reset' not in preferences and 'versions_outer.addLayout(uninstall_versions_row)' not in preferences,
          "legacy per-tab contextual button placement remains")

    # Destructive styling keeps native shape while slightly improving contrast.
    check('accent = QColor("#dc6262")' in shared and "mix = 0.07" in shared and
          'button.setStyleSheet("QPushButton { color: #dc6262; }")' in shared,
          "destructive button contrast was not adjusted as agreed")
    check("border:" not in shared[shared.index("def _style_destructive_button"):],
          "destructive helper reintroduced custom border geometry")

    print("PASS: 0.10.3 intake boundary, drop policy, purge/appimage and Preferences polish"
          if not any(e.startswith("0.10.3 polish:") for e in errors)
          else "CHECK: 0.10.3 polish regressions")


if __name__ == "__main__":
    failures: list[str] = []
    run_regressions(failures)
    for failure in failures:
        print("FAIL:", failure)
    if failures:
        raise SystemExit(f"{len(failures)} regression(s) failed")
