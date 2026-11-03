"""0.10.6 Developer Prune and UI-consistency regressions (Qt-free)."""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations

from pathlib import Path

from suite_pythoine.prune_policy import select_prune_records

PACKAGE = Path(__file__).resolve().parents[1]


def _key(record: dict) -> tuple[str, str, str]:
    return str(record["component_id"]), str(record["version"]), str(record["asset"])


def run_regressions(errors: list[str]) -> None:
    prefix = "0.10.6 polish: "

    def check(condition: bool, message: str) -> None:
        if not condition:
            errors.append(prefix + message)

    app = read_app_with_presentations()
    intake = (PACKAGE / "developer/developer_intake.py").read_text(encoding="utf8")
    prune_widget = (PACKAGE / "ui" / "widgets" / "prune.py").read_text(encoding="utf8")

    # Prune stays Developer-only, uses two additive parent checkboxes, and gives
    # each scope its own opt-in Recovery retention (unchecked = Recovery removed).
    details_start = app.index("    def _populate_editor_details")
    details_end = app.index("    def _editor_page", details_start)
    details = app[details_start:details_end]
    check('QPushButton("Prune…")' in details and 'suite_developer_only' in details and
          'prune_button.setVisible(self.developer_config.enabled)' in details,
          "Prune is not exposed only through Developer Mode Details presentation")
    check('class PruneScopePage(QWizardPage)' in prune_widget and
          ('QCheckBox("Prune to This App")' in prune_widget or 'QGroupBox("Prune to This App")' in prune_widget) and
          ('QCheckBox("Prune to Active Version")' in prune_widget or 'QGroupBox("Prune to Active Version")' in prune_widget) and
          prune_widget.count('QCheckBox("Keep Recovery Files")') >= 2,
          "Prune additive scopes / nested Recovery retention controls are missing")
    check('self.keep_this_recovery.setChecked(False)' in prune_widget and
          'self.keep_active_recovery.setChecked(False)' in prune_widget,
          "Recovery retention is not independently nested and default-off")
    prune_start = app.index("    def _prune_editor")
    prune_end = app.index("    def _inventory_launch_runtime", prune_start)
    prune = app[prune_start:prune_end]
    check('configure_operation_window(wizard)' in prune and 'operation_branding_header(' in prune and
          'review_layout.addWidget(review_inventory, 1)' in prune,
          "Prune is not in the canonical full-size/elastic operation family")
    check('result_page = QWizardPage()' in prune and 'Completed successfully' in prune and
          'Completed with issues' in prune and 'Prune failed' in prune,
          "Prune lacks explicit success/partial/failure reporting")
    check('result = remove_assets(' in prune and 'select_prune_records(' in prune,
          "Prune bypasses the shared asset-removal engine or Qt-free scope policy")

    records: list[dict] = []
    for component_id in ("current", "other", "suite-pythoine"):
        for version in ("1.0", "2.0"):
            for asset in ("Portable", "AppImage", "Recovery"):
                records.append({
                    "component_id": component_id,
                    "version": version,
                    "asset": asset,
                    "locations": [f"/{component_id}/{version}/{asset}"],
                })

    this_app = select_prune_records(
        records, current_component_id="current", active_version="2.0",
        prune_to_this_app=True, keep_this_recovery=False,
        prune_to_active_version=False, keep_active_recovery=False,
    )
    this_keys = {_key(record) for record in this_app}
    check(this_keys == {
        ("other", version, asset)
        for version in ("1.0", "2.0") for asset in ("Portable", "AppImage", "Recovery")
    }, "Prune to This App does not keep both current app and Suite while removing Recovery by default")

    active_only = select_prune_records(
        records, current_component_id="current", active_version="2.0",
        prune_to_this_app=False, keep_this_recovery=False,
        prune_to_active_version=True, keep_active_recovery=True,
    )
    check({_key(record) for record in active_only} == {
        ("current", "1.0", "Portable"), ("current", "1.0", "AppImage")
    }, "Prune to Active Version does not independently honour Keep Recovery Files")

    both = select_prune_records(
        records, current_component_id="current", active_version="2.0",
        prune_to_this_app=True, keep_this_recovery=True,
        prune_to_active_version=True, keep_active_recovery=False,
    )
    both_keys = {_key(record) for record in both}
    check(("other", "1.0", "Recovery") not in both_keys and
          ("current", "1.0", "Recovery") in both_keys and
          not any(component == "suite-pythoine" for component, _version, _asset in both_keys),
          "additive Prune scopes do not keep separate Recovery policies / Suite preservation")

    # Remove Assets selection management lives in the checkbox header; the old
    # dedicated Select All / Clear Selection buttons do not return.
    page = (PACKAGE / "ui/pages/installed_applications.py").read_text(encoding="utf8")
    check('selection_header = AssetSelectionHeader(' in page and
          'selection_header.toggleSelectionRequested.connect(set_all_assets)' in page and
          'Qt.CheckState.PartiallyChecked' in page and
          'if table.isRowHidden(row):' in page,
          "Remove Assets lacks tri-state visible-row selection in its header")
    check('QPushButton("Select All")' not in page and 'QPushButton("Clear Selection")' not in page,
          "dedicated Select All / Clear Selection buttons remain")

    # Guidance uses the same dark diagnostic colour vocabulary as Technical Details.
    guidance_start = app.index("    def _show_installed_applications_guidance")
    guidance_end = app.index("    def _installed_applications_page", guidance_start)
    guidance = app[guidance_start:guidance_end]
    check('guidance = _diagnostic_canvas(dialog)' in guidance and
          '#dcdcdc' in guidance and '#9cdcfe' in guidance and
          'setDefaultStyleSheet' in guidance,
          "Detailed guidance does not match Technical Details/Sources text colours")

    # Hub Details drops the redundant Role line, while Installed Applications
    # keeps the same leading Active line before its concise page description.
    summary_start = app.index("    def _editor_summary_text")
    summary_end = app.index("    def _open_development_root", summary_start)
    summary = app[summary_start:summary_end]
    check('Role: File routing and application management' not in summary,
          "Hub Details still shows the redundant Role line")
    check('active_line = "Active: Not selected"' in page and
          'self._editor_summary_text(self.suite_entry).splitlines()[0]' in page,
          "Installed Applications lost Hub-style Active status")

    # Developer Intake has one simplified operation-family header and the agreed
    # control order; Open Version Folder opens the mandatory ZIP-derived folder.
    check('operation_title_block(' not in intake and
          'f"{APP_NAME} — Developer Intake"' in intake and
          'f"Version {__version__} • Developer Mode"' in intake,
          "Developer Intake still duplicates its title/header identity")
    choose_pos = intake.index('choose_button = QPushButton("Choose ZIP…")')
    configure_pos = intake.index('configure = QPushButton("Configure…")')
    layout_group_pos = intake.index('layout_group = QGroupBox("Intake")')
    check(choose_pos < configure_pos < layout_group_pos,
          "Configure is not immediately beside Choose ZIP")
    check('QPushButton("Clear / Reset")' in intake and
          'QPushButton("Open Version Folder")' in intake and
          'QPushButton("Install Stored ZIP…")' in intake,
          "Developer Intake session/output controls are missing")
    check('target = prepared.dev_folder if prepared is not None else self.extracted_folder' in intake and
          'Open Extracted Folder' not in intake and 'Open Development Folder" if planned.store_zip_only' not in intake,
          "Developer Intake Open Version Folder still resolves to mode-specific subfolders")
    # The later ephemeral session ZIP idea is deliberately not part of 0.10.6.

    print("PASS: 0.10.6 Prune and UI-consistency regressions"
          if not any(error.startswith(prefix) for error in errors)
          else "CHECK: 0.10.6 polish regressions")


if __name__ == "__main__":
    failures: list[str] = []
    run_regressions(failures)
    for failure in failures:
        print("FAIL:", failure)
    raise SystemExit(1 if failures else 0)
