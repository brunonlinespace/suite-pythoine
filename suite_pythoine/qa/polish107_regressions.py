"""0.10.7 corrective UI/state regressions (Qt-free)."""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations

from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]


def run_regressions(errors: list[str]) -> None:
    prefix = "0.10.7 polish: "

    def check(condition: bool, message: str) -> None:
        if not condition:
            errors.append(prefix + message)

    app = read_app_with_presentations()
    inventory_page = (PACKAGE / "ui/pages/installed_applications.py").read_text(encoding="utf8")
    prune_widget = (PACKAGE / "ui" / "widgets" / "prune.py").read_text(encoding="utf8")
    inventory_widget = (PACKAGE / "ui" / "widgets" / "inventory.py").read_text(encoding="utf8")
    intake = (PACKAGE / "developer/developer_intake.py").read_text(encoding="utf8")
    wizard = (PACKAGE / "install_wizard.py").read_text(encoding="utf8")

    # Active Version remains the narrower first scope and Recovery retention
    # remains nested/default-off. 0.10.9 deliberately moves the scope checkbox
    # outside the native framed panel to avoid Breeze centring checkable titles.
    prune = prune_widget
    active_pos = prune.index('QCheckBox("Prune to Active Version")')
    this_pos = prune.index('QCheckBox("Prune to This App")')
    check(active_pos < this_pos, "Prune to Active Version is not presented before Prune to This App")
    check(prune.count('QFrame.Shape.StyledPanel') >= 2 and prune.count('QCheckBox("Keep Recovery Files")') >= 2,
          "Prune scopes no longer have native framed subordinate Recovery sections")
    check(prune.count("setChecked(False)") >= 4,
          "Prune scopes / nested Recovery controls are not default-off")

    # Developer Intake remembers action/delete choices and uses the agreed compact
    # terminology/order. Action sits beside Paste; the summary follows the notes.
    check('"store_zip_only": False' in intake and
          'bool(raw.get("store_zip_only", False))' in intake and
          'self.config.data["store_zip_only"] = self.store_only_radio.isChecked()' in intake,
          "Developer Intake does not persist/restore the last action mode")
    check('delete_zip_after_success' in intake and 'delete_original_after_success' in intake,
          "Developer Intake delete choices are not persisted")
    check('QGroupBox("Intake")' in intake and 'addRow("Action:", mode_row)' in intake and
          'addRow("Source folder:", self.source_edit)' in intake and
          'addRow("Notes folder:", self.notes_edit)' in intake and 'QLabel("Notes file:")' in intake,
          "Developer Intake terminology/order is not Intake / Action / Source folder / Notes folder / Notes file")
    paste_pos = intake.index('paste_button = QPushButton("Paste")')
    action_pos = intake.index('self.action_button = QPushButton("Action")')
    notes_widget_pos = intake.index('self.notes = QPlainTextEdit()')
    summary_pos = intake.index('info_group = QGroupBox("Intake Summary")')
    check(paste_pos < action_pos < notes_widget_pos < summary_pos,
          "Action is not beside Paste or Intake Summary is not below Notes")
    footer_start = intake.index("        actions = QHBoxLayout()", summary_pos)
    footer_end = intake.index("        layout.addLayout(actions)", footer_start)
    footer = intake[footer_start:footer_end]
    check('QPushButton("Clear / Reset")' in footer and 'QPushButton("Open Version Folder")' in footer and
          'QPushButton("Install Stored ZIP…")' in footer and 'QPushButton("Action")' not in footer,
          "Developer Intake footer does not retain Clear / Open Version Folder / Install Stored ZIP only")
    check('"Development ZIP:"' in intake and
          '"Deleted after extraction"' in intake and '"Deleted after intake"' in intake,
          "Intake Summary does not report Development ZIP / deletion outcomes truthfully")

    # Installed Applications custom header must not steal native sorting. Fresh
    # pages start Application A-Z; mode/filter repopulation reads the current sort.
    check('header.setSectionsClickable(True)' in inventory_page and 'header.setSortIndicatorShown(True)' in inventory_page and
          'header.setSortIndicator(0, Qt.SortOrder.AscendingOrder)' in inventory_page,
          "Installed Applications does not default to clickable Application A-Z sorting")
    check('def current_sort()' in inventory_page and inventory_page.count('table.sortItems(sort_column, sort_order)') >= 2,
          "Installed Applications does not preserve current sorting through both table modes")
    check('def mouseReleaseEvent(self, event)' in inventory_widget and
          'The transient selection header is a checkbox, not a sortable column.' in inventory_widget,
          "selection-header checkbox can still interfere with normal heading sorting")
    check('table.clearSelection()' in inventory_page and 'table.setCurrentCell(-1, -1)' in inventory_page and
          'version_filter.setFocus(Qt.FocusReason.OtherFocusReason)' in inventory_page,
          "Remove Assets still permits the stray first-row current-cell focus decoration")

    # Shortcut reassignment is exact: V toggles view, D opens Developer Intake;
    # T is no longer the Developer Intake shortcut.
    check('self.toggle_view_shortcut_action.setShortcut("Ctrl+Alt+Shift+V")' in app,
          "Grid/List toggle is not Ctrl+Alt+Shift+V")
    check('self.developer_intake_action.setShortcut("Ctrl+Alt+Shift+D")' in app and
          'self.developer_intake_action.setShortcut("Ctrl+Alt+Shift+T")' not in app,
          "Developer Intake shortcut is not Ctrl+Alt+Shift+D / old T shortcut remains")

    # Normal Portable installation must not advertise Developer-only AppImage
    # build UI. The managed AppImage destination row is conditional too.
    dest = 'form.addRow("Managed AppImage folder:", _plain_label(str(appimage_root(installed_dir, inspection.name, self.incoming_version))))'
    check('if self.developer_mode:\n            ' + dest in wizard,
          "normal Portable installer still exposes the managed AppImage destination")
    check('self.build_appimage.setVisible(self.developer_mode)' in wizard and
          'if developer_mode:\n            builder = inspection.builder_relative' in wizard,
          "Developer-only AppImage builder presentation is not gated by Developer Mode")

    print("PASS: 0.10.7 corrective UI/state regressions"
          if not any(error.startswith(prefix) for error in errors)
          else "CHECK: 0.10.7 polish regressions")


if __name__ == "__main__":
    failures: list[str] = []
    run_regressions(failures)
    for failure in failures:
        print("FAIL:", failure)
    raise SystemExit(1 if failures else 0)
