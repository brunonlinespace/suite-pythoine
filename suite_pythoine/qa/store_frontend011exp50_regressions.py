"""0.11-exp5.0 integrated Store frontend v1 regressions (Qt-free)."""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent


def _method_source(tree: ast.AST, source: str, name: str) -> str:
    node = next((item for item in ast.walk(tree) if isinstance(item, ast.FunctionDef) and item.name == name), None)
    return ast.get_source_segment(source, node) or "" if node is not None else ""


def run_regressions(errors: list[str]) -> None:
    prefix = "0.11-exp5.0 Store frontend: "
    source = read_app_with_presentations()
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        errors.append(prefix + f"app.py syntax error: {exc}")
        return

    def check(condition: bool, message: str) -> None:
        if not condition:
            errors.append(prefix + message)

    installed = _method_source(tree, source, "_store_is_installed")
    check('entry.editor_id == "store-pythoine"' in installed,
          "Store installed-state detection is not bound to canonical component identity")

    navigation = _method_source(tree, source, "_sync_store_navigation")
    for token in (
        'self.store_action.setText("Store Pythoine" if store_mode else "Get More Applications…")',
        'self.store_button.setText("Store Pythoine" if store_mode else "Get More…")',
        'bundled_catalog_icon_path("store-pythoine")',
    ):
        check(token in navigation, f"Get More → Store navigation transition missing: {token}")

    refresh = _method_source(tree, source, "refresh_editors")
    check('self._reload_store_content()' in refresh and 'self._sync_store_navigation()' in refresh,
          "normal inventory refresh does not update Store content/navigation state")

    profiles = _method_source(tree, source, "_store_catalog_profiles")
    check('COMPONENT_PROFILES.values()' in profiles and 'profile.kind != "hub"' in profiles,
          "integrated Store does not browse Suite-authoritative trusted identities")
    check('profile.component_id != "store-pythoine"' in profiles,
          "integrated Store recursively lists its own backend module")

    page = _method_source(tree, source, "_catalogue_page")
    for token in (
        'store_mode = self._store_is_installed()',
        'QLabel("Store Pythoine")',
        'self._store_catalog_profiles() if store_mode else self._uninstalled_catalog_profiles()',
        'status = "Installed" if installed else "Not installed"',
        'self._store_enrichment(profile.component_id)',
        'self.show_catalog_component(profile)',
        'Reload Local Content',
        'self._publish_installed_store_content()',
        'catalogueSearch',
    ):
        check(token in page, f"integrated Store catalogue surface missing: {token}")
    for forbidden in ('urllib', 'requests.', 'urlopen(', 'QNetworkAccessManager'):
        check(forbidden not in page, f"opening integrated Store performs forbidden network work: {forbidden}")

    enrichment = _method_source(tree, source, "_add_store_enrichment")
    for token in ('Store Information', 'extended_description', 'latest_version', 'release_date', 'release_notes'):
        check(token in enrichment, f"canonical App Page enrichment missing: {token}")

    installed_page = _method_source(tree, source, "_populate_editor_details")
    check('self._add_store_enrichment(layout, editor.editor_id)' in installed_page,
          "installed App Pages do not consume optional Store enrichment")
    inactive_page = _method_source(tree, source, "_catalog_component_page")
    check('self._add_store_enrichment(layout, profile.component_id)' in inactive_page,
          "inactive App Pages do not consume optional Store enrichment")
    check('Back to Store' in inactive_page and 'Back to Get More Applications' in inactive_page,
          "canonical inactive App Page does not adapt its back action to Store availability")

    publisher = _method_source(tree, source, "_publish_installed_store_content")
    for token in ('"--publish-content"', 'QProcess(self)', 'self.launcher.configure_process(process, command)',
                  'self.refresh_editors(automatic=True)'):
        check(token in publisher, f"local Store-content publication bridge missing: {token}")
    for forbidden in ('urllib', 'urlopen(', 'requests.'):
        check(forbidden not in publisher, f"local Store-content publication unexpectedly performs network work: {forbidden}")

    focus = _method_source(tree, source, "_focus_contextual_search")
    events = _method_source(tree, source, "eventFilter")
    check('current_widget.property("editor_root") == "__catalogue__"' in focus and 'self.catalogue_search.selectAll()' in focus,
          "Ctrl+F does not target integrated Store/Get More search")
    check('current_widget.property("editor_root") == "__catalogue__"' in events and 'self.catalogue_search.clear()' in events,
          "Esc does not clear integrated Store/Get More search")

    # Experiment 5 is presentation/integration only: established destructive lifecycle engines remain present.
    for method_name in ('purge_editor', '_prune_editor', 'remove_editor_version',
                        'remove_portable_runtime', 'uninstall_appimage_runtime'):
        check(bool(_method_source(tree, source, method_name)), f"lifecycle method missing: {method_name}")

    print("PASS: 0.11-exp5.0 integrated Store frontend regression contract"
          if not any(error.startswith(prefix) for error in errors)
          else "CHECK: 0.11-exp5.0 Store frontend regressions")


if __name__ == "__main__":
    problems: list[str] = []
    run_regressions(problems)
    if problems:
        for problem in problems:
            print("FAIL:", problem)
        raise SystemExit(1)
    print("PASS: 0.11-exp5.0 integrated Store frontend regressions")
