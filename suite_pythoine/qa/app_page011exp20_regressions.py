"""0.11-exp2.0 application-first App Page experiment regressions (Qt-free)."""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent


def _method_source(tree: ast.AST, source: str, name: str) -> str:
    node = next((item for item in ast.walk(tree) if isinstance(item, ast.FunctionDef) and item.name == name), None)
    return ast.get_source_segment(source, node) or "" if node is not None else ""


def run_regressions(errors: list[str]) -> None:
    prefix = "0.11-exp2.0 App Page: "
    source = read_app_with_presentations()
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        errors.append(prefix + f"app.py syntax error: {exc}")
        return

    def check(condition: bool, message: str) -> None:
        if not condition:
            errors.append(prefix + message)

    details = _method_source(tree, source, "_populate_editor_details")
    check('self._application_overview_text(editor)' in details,
          "App Page no longer uses the application-first overview")
    check('self._editor_summary_text(editor)' not in details,
          "historical inventory summary still dominates the App Page")
    check('self._current_version_frame(editor, current_version)' in details,
          "compact current-version panel is not used")
    check('self._version_management_frame(' not in details,
          "generic full exact-version administration leaked back onto App Page")
    for token in ('QLabel("Version History")', 'QPushButton("Version History…")',
                  'QLabel("Settings")', 'QLabel("Maintenance")',
                  'self._desktop_integration_summary(editor)'):
        check(token in details, f"new App Page hierarchy missing: {token}")
    # Description/identity -> Application -> Current -> History -> Settings -> Maintenance.
    for left, right, label in (
        ('layout.addWidget(description)', 'add_section("Application"', 'description before Application'),
        ('QLabel("Current Version")', 'QLabel("Version History")', 'Current Version before Version History'),
        ('QLabel("Version History")', 'QLabel("Settings")', 'Version History before Settings'),
        ('QLabel("Settings")', 'QLabel("Maintenance")', 'Settings before Maintenance'),
    ):
        if left in details and right in details:
            check(details.index(left) < details.index(right), label)
    check('f"{len(editor.versions)} installed version' in details,
          "Version History no longer owns the historical-version count")

    overview = _method_source(tree, source, "_application_overview_text")
    check('Supported formats:' in overview and 'Capabilities:' in overview,
          "identity area lacks supported formats/capabilities")
    check('Warning — version validation:' in overview,
          "important validation warnings were demoted")
    check('Versions found:' not in overview and 'Runtimes:' not in overview and 'Recovery: Available for' not in overview,
          "historical inventory counts remain in application overview")

    current = _method_source(tree, source, "_current_version_frame")
    for token in ('add_runtime_row("Portable"', 'add_runtime_row("AppImage"', 'add_runtime_row("Recovery"',
                  'self.launch_editor_version(editor, item, "portable")',
                  'self.launch_editor_version(editor, item, "appimage")',
                  'self.restore_portable_from_recovery_action(editor, item)'):
        check(token in current, f"compact current-version contract missing: {token}")
    for destructive in ('remove_portable_runtime', 'uninstall_appimage_runtime', 'remove_editor_version', 'build_appimage_from_portable'):
        check(destructive not in current,
              f"administrative action {destructive} should remain behind Version History")

    full = _method_source(tree, source, "_version_management_frame")
    for token in ('QPushButton("Make Active")', 'QPushButton("Uninstall Version…")',
                  'QPushButton("Remove Portable")', 'QPushButton("Remove AppImage")',
                  '"Rebuild AppImage…" if rebuild else "Build AppImage…"',
                  'QPushButton("Restore Portable…")'):
        check(token in full, f"Version History lost full exact-version action: {token}")

    history_page = _method_source(tree, source, "_version_history_page")
    check('table.setObjectName("versionHistoryTable")' in history_page,
          "Version History table cannot be targeted for explicit preferred-version selection")
    show_history = _method_source(tree, source, "show_version_history")
    for token in ('preferred_version: str | None = None', 'findChild(QTableWidget, "versionHistoryTable")',
                  'table.selectRow(row)'):
        check(token in show_history, f"preferred current-version hand-off missing: {token}")

    # Lifecycle engines remain separate from the presentation experiment.
    for method_name in ('purge_editor', '_prune_editor', 'remove_editor_version',
                        'remove_portable_runtime', 'uninstall_appimage_runtime'):
        check(bool(_method_source(tree, source, method_name)), f"lifecycle method missing: {method_name}")

    print("PASS: 0.11-exp2.0 application-first App Page regression contract"
          if not any(error.startswith(prefix) for error in errors)
          else "CHECK: 0.11-exp2.0 App Page regressions")
