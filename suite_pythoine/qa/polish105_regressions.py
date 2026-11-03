"""0.10.5 Installed Applications / operation-wizard consistency regressions."""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations

from pathlib import Path
import tempfile

from suite_pythoine.asset_removal import AssetRemovalFailure, RemovalAsset, remove_assets
from suite_pythoine.installer import InstallError

PACKAGE = Path(__file__).resolve().parents[1]


def run_regressions(errors: list[str]) -> None:
    prefix = "0.10.5 polish: "

    def check(condition: bool, message: str) -> None:
        if not condition:
            errors.append(prefix + message)

    app = read_app_with_presentations()
    intake = (PACKAGE / "developer/developer_intake.py").read_text(encoding="utf8")
    install = (PACKAGE / "install_wizard.py").read_text(encoding="utf8")
    purge = (PACKAGE / "purge_wizard.py").read_text(encoding="utf8")
    operation_ui = (PACKAGE / "operation_ui.py").read_text(encoding="utf8")

    page = (PACKAGE / "ui/pages/installed_applications.py").read_text(encoding="utf8")

    # Remove Assets is a mode of the one Installed Applications table, not a second page/table.
    check('inventory_heading = QLabel("Installed Applications")' in page and '"Managed Assets"' not in page,
          "Remove Assets still renames Installed Applications")
    check('table = QTableWidget(0, 9)' in page and 'asset_table = QTableWidget' not in page and
          'QStackedWidget' not in page,
          "Remove Assets is still implemented as a separate table/page")
    check('"Application", "Version", "Asset", "Active", "Size"' in app,
          "Installed Applications did not scope Runtime -> Asset to its own column model")
    check('selection_header = AssetSelectionHeader(' in page and
          'header.moveSection(visual, 0)' in page and
          'header.setSectionResizeMode(8, QHeaderView.ResizeMode.Fixed)' in page and
          'table.setColumnWidth(8, 42)' in page,
          "selection checkbox is not a narrow transient first visual column")
    check('self._save_inventory_table_layout()' in page and 'self._restore_inventory_table_layout(table)' in page,
          "Remove Assets does not preserve the user's established table layout")
    check('add_quick_actions(row, record, recovery=record["asset"] == "Recovery")' in page,
          "Quick Actions disappear in Remove Assets mode")
    check('header.setStretchLastSection(True)' in page,
          "Installed Applications does not consume available visible table width")

    # Exact running Suite asset is filtered from Remove Assets, while hidden state remains visible to semantics.
    inventory_start = app.index("    def _asset_inventory_records")
    inventory_end = app.index("    def _commit_asset_removal_preferences", inventory_start)
    inventory = app[inventory_start:inventory_end]
    check('include_running_suite: bool = False' in inventory and
          'if protected and not include_running_suite:' in inventory and 'continue' in inventory,
          "running Suite asset is not filtered out of Remove Assets")
    check('all_asset_records = self._asset_inventory_records(include_running_suite=True)' in page,
          "hidden running Suite asset is not retained for safe preference-cleanup semantics")
    check('"Protection"' not in page,
          "obsolete Protection column remains in Remove Assets")

    # Detailed guidance is a link at the end of the stable page description; Install Application stays put.
    check('<a href=\\"guidance\\">Detailed guidance…</a>' in page and
          'summary.linkActivated.connect' in page,
          "Detailed guidance is not a text link in the page description")
    settings_pos = page.find('inventory_row = QHBoxLayout()')
    install_pos = page.find('install_component = QPushButton("Install Application…")')
    search_pos = page.find('inventory_search_row = QHBoxLayout()')
    check(settings_pos >= 0 and settings_pos < install_pos < search_pos,
          "Install Application moved out of its established Settings action row")
    guidance_start = app.index("    def _show_installed_applications_guidance")
    guidance_end = app.index("    def _installed_applications_page", guidance_start)
    guidance = app[guidance_start:guidance_end]
    for text in ("Click a heading to sort", "Quick actions", "Remove Assets", "currently running Suite Pythoine asset is filtered out"):
        check(text in guidance, f"Detailed guidance lost required content: {text}")

    # Canonical substantial-operation presentation: same size, branded headers, scrollable/elastic inventories.
    check('OPERATION_MIN_SIZE = (820, 640)' in operation_ui and 'OPERATION_SIZE = (980, 800)' in operation_ui,
          "canonical operation dimensions are not shared")
    uninstall_start = app.index("    def _confirm_uninstall_version")
    uninstall_end = app.index("    def remove_editor_version", uninstall_start)
    uninstall = app[uninstall_start:uninstall_end]
    check('wizard = QWizard(self)' in uninstall and 'configure_operation_window(wizard)' in uninstall and
          'operation_branding_header(' in uninstall and 'inventory = QPlainTextEdit()' in uninstall and
          'page_layout.addWidget(inventory, 1)' in uninstall,
          "Uninstall Version is not a full-size branded wizard with elastic inventory")
    remove_start = app.index("    def _remove_asset_records")
    remove_end = app.index("    def _inventory_launch_runtime", remove_start)
    remove = app[remove_start:remove_end]
    check('wizard = QWizard(self)' in remove and 'configure_operation_window(wizard)' in remove and
          'operation_branding_header(' in remove and 'review_layout.addWidget(details, 1)' in remove,
          "Remove Selected Assets is not in the canonical wizard family")
    check('result_page = QWizardPage()' in remove and 'Completed successfully' in remove and
          'Completed with issues' in remove and 'Removal failed' in remove and
          'wizard.setButtonText(QWizard.WizardButton.FinishButton, "Close")' in remove,
          "Remove Selected Assets lacks an explicit success/partial/failure result page")
    check('configure_operation_window(self)' in intake and
          'operation_branding_header(' in intake and 'class DeveloperIntakeDialog(QDialog)' in intake,
          "Developer Intake is not a single-surface member of the operation visual family")

    review_start = purge.index("class PurgeReviewPage")
    review_end = purge.index("class PurgeConfirmPage", review_start)
    purge_review = purge[review_start:review_end]
    check('layout.addWidget(inventory_scroll, 1)' in purge_review and
          'layout.addStretch(1)' not in purge_review[purge_review.rfind('layout.addWidget(note)'):],
          "Purge inventory is not using the remaining wizard height elastically")

    # Normal Portable install copy does not advertise Developer-only AppImage building.
    check('def __init__(self, inspection: ZipEditorInspection, *, developer_mode: bool = False)' in install and
          'if developer_mode:\n            builder = inspection.builder_relative' in install,
          "Portable welcome page still exposes AppImage builder details outside Developer Mode")
    check('elif self.options.developer_mode:\n            lines.append("— AppImage build/integration will be skipped")' in install and
          'if not self.options.developer_mode and key in {"prepare", "build", "verify", "appimage", "icon"}' in install,
          "normal installer still advertises Developer-only AppImage build steps")

    # Result engine exposes exact pruned paths and reportable rollback status.
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Applications"
            version = root / "Demo" / "1.0"
            recovery = version / "Recovery"
            recovery.mkdir(parents=True)
            (recovery / "source.zip").write_bytes(b"zip")
            result = remove_assets([RemovalAsset("demo", "Demo", "1.0", "Recovery", recovery)], editors_root=root)
            check(version in result.pruned_directories and version.parent in result.pruned_directories,
                  "successful asset removal does not report pruned version/application directories")

            version = root / "Demo" / "1.1"
            portable = version / "Portable"
            portable.mkdir(parents=True)
            (portable / "main.py").write_text("print('demo')\n", encoding="utf8")
            try:
                remove_assets(
                    [RemovalAsset("demo", "Demo", "1.1", "Portable", portable)],
                    editors_root=root,
                    pre_finalize=lambda: (_ for _ in ()).throw(InstallError("simulated")),
                )
            except AssetRemovalFailure as exc:
                check(not exc.partial and "Rollback completed" in exc.rollback_status,
                      "pre-finalize failure does not expose successful rollback status")
            else:
                check(False, "pre-finalize failure did not raise AssetRemovalFailure")
    except Exception as exc:
        errors.append(prefix + f"engine reporting regression exception: {type(exc).__name__}: {exc}")

    print("PASS: 0.10.5 Installed Applications and operation-wizard consistency"
          if not any(e.startswith(prefix) for e in errors)
          else "CHECK: 0.10.5 polish regressions")


if __name__ == "__main__":
    failures: list[str] = []
    run_regressions(failures)
    for failure in failures:
        print("FAIL:", failure)
    raise SystemExit(1 if failures else 0)
