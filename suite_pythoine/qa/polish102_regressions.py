"""0.10.2 Developer Intake transaction / navigation / removal-dialog regressions."""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations

from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]


def run_regressions(errors: list[str]) -> None:
    def check(condition: bool, message: str) -> None:
        if not condition:
            errors.append("0.10.2 polish: " + message)

    app = read_app_with_presentations()
    shared = (PACKAGE / "ui/diagnostic_helpers.py").read_text(encoding="utf8")
    intake = (PACKAGE / "developer/developer_intake.py").read_text(encoding="utf8")

    # Developer Intake is now preview-first; filesystem work belongs to Action.
    load_start = intake.index("    def load_zip(self, zip_path: Path) -> bool:")
    load_end = intake.index("    def reset(self) -> None:", load_start)
    load = intake[load_start:load_end]
    action_start = intake.index("    def _action(self) -> None:")
    action_end = intake.index("    def _request_install_stored", action_start)
    action = intake[action_start:action_end]
    check("shutil.copy2(" not in load and ".mkdir(" not in load,
          "selecting a ZIP still mutates the development filesystem before Action")
    check("shutil.copy2(incoming, stored)" in action and "prepared.configured_root.mkdir" in action,
          "Action is not the sole intake filesystem commit point")
    check("No development files have been copied or extracted yet." in load,
          "preview state does not communicate the transactional boundary")
    check("self.install_button.setEnabled(False)" in load,
          "Install Stored ZIP is enabled before Action creates a stored copy")

    # 0.10.3 supersedes Store-only special casing: every intake uses a ZIP-stem container.
    planned_start = intake.index("    def _planned_intake(")
    planned_end = intake.index("    def _refresh_prepared_preview", planned_start)
    planned = intake[planned_start:planned_end]
    check("dev_folder = root / path.stem" in planned and "dev_folder = root\n" not in planned,
          "mandatory ZIP-filename intake container is missing")

    # Original-vs-development ZIP deletion are separate contracts.
    check('QCheckBox("Delete original ZIP after successful intake")' in intake,
          "original ZIP deletion option missing")
    check('QCheckBox("Delete development ZIP after successful extraction")' in intake,
          "development ZIP deletion option missing")
    check("self.delete_box.setVisible(extraction)" in intake,
          "development ZIP deletion is still offered in Store ZIP only mode")
    check("delete_original_after_success=bool(self.delete_original_box.isChecked())" in planned,
          "original ZIP deletion is not captured for both intake modes")
    check("if prepared.delete_original_after_success:" in action,
          "original ZIP is not deleted only after successful Action work")
    check("if not text.strip():\n            return None" in intake,
          "empty release-note textbox can still generate a note file")

    # Sidebar application-only navigation.
    check('self.previous_application_action.setShortcut("Ctrl+Up")' in app and
          'self.next_application_action.setShortcut("Ctrl+Down")' in app,
          "Ctrl+Up/Down application navigation shortcuts missing")
    check("def _navigate_sidebar_application(self, direction: int)" in app and
          "if key in self._sidebar_application_keys:" in app and "if item is None or item.isHidden():" in app,
          "sidebar navigation does not follow visible application order")

    # Exact-version removal gets branded confirmation; runtime removal remains separate.
    check("def _confirm_uninstall_version(" in app and 'wizard = QWizard(self)' in app and
          'operation_branding_header(' in app and 'inventory = QPlainTextEdit()' in app and
          "self._confirm_uninstall_version(editor, version, assets)" in app,
          "Uninstall Version lost its branded reviewed confirmation")
    check('QMessageBox.warning(self, app_dialog_title(\'Uninstall Version\')' not in app,
          "legacy plain Uninstall Version QMessageBox remains")
    check('QPushButton("Remove Portable")' in app and 'QPushButton("Remove AppImage")' in app,
          "compact runtime-removal actions were unintentionally renamed/reworked")

    # Destructive treatment keeps the native button frame: no custom red border.
    check("def _style_destructive_button(button: QPushButton)" in shared and
          'button.setStyleSheet("QPushButton { color: #dc6262; }")' in shared and
          "QPalette.ColorRole.Button" in shared,
          "native-shape destructive tint helper missing")
    check("border: 1px solid #bc5050" not in app,
          "custom red border still overrides the native KDE/Qt button shape")

    print("PASS: 0.10.2 transactional Intake, sidebar navigation and removal-dialog polish"
          if not any(e.startswith("0.10.2 polish:") for e in errors)
          else "CHECK: 0.10.2 polish regressions")


if __name__ == "__main__":
    failures: list[str] = []
    run_regressions(failures)
    for failure in failures:
        print("FAIL:", failure)
    if failures:
        raise SystemExit(f"{len(failures)} regression(s) failed")
