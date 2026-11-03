"""0.11-exp3.0 lightweight catalogue / inactive App Page regressions (Qt-free)."""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent


def _method_source(tree: ast.AST, source: str, name: str) -> str:
    node = next((item for item in ast.walk(tree) if isinstance(item, ast.FunctionDef) and item.name == name), None)
    return ast.get_source_segment(source, node) or "" if node is not None else ""


def run_regressions(errors: list[str]) -> None:
    prefix = "0.11-exp3.0 catalogue: "
    source = read_app_with_presentations()
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        errors.append(prefix + f"app.py syntax error: {exc}")
        return

    def check(condition: bool, message: str) -> None:
        if not condition:
            errors.append(prefix + message)

    current = _method_source(tree, source, "_current_version_frame")
    check('Manage Current Version…' not in current,
          "redundant Manage Current Version button remains on installed App Page")
    check('add_runtime_row("Portable"' in current and 'add_runtime_row("AppImage"' in current
          and 'add_runtime_row("Recovery"' in current,
          "compact Current Version runtime/recovery surface regressed")

    show_store = _method_source(tree, source, "show_store")
    check('self._ensure_catalogue_page()' in show_store and 'self.launch_editor(store)' not in show_store,
          "Get More still launches standalone Store instead of Suite's lightweight catalogue")

    profiles = _method_source(tree, source, "_uninstalled_catalog_profiles")
    check('profile.kind != "hub"' in profiles and 'profile.component_id not in installed_ids' in profiles,
          "Get More catalogue is not limited to trusted uninstalled non-Hub identities")
    check('COMPONENT_PROFILES.values()' in profiles,
          "Get More catalogue does not use Suite's authoritative trusted component catalogue")

    page = _method_source(tree, source, "_catalogue_page")
    for token in ('QLabel("Get More Applications")', 'QLineEdit()', 'QListWidget()',
                  'getMoreApplicationsList', 'self._uninstalled_catalog_profiles()',
                  'self.show_catalog_component(profile)'):
        check(token in page, f"lightweight catalogue front door missing: {token}")
    for forbidden in ('urllib', 'requests.', 'urlopen(', 'QNetworkAccessManager', 'refresh_catalogue'):
        check(forbidden not in page, f"Get More performs forbidden implicit network work: {forbidden}")

    inactive = _method_source(tree, source, "_catalog_component_page")
    for token in ('Status: Not installed', 'Supported formats:', 'Capabilities:',
                  'QPushButton("Install…")', 'self.install_catalog_component(target)',
                  'Back to Get More Applications'):
        check(token in inactive, f"inactive canonical App Page missing: {token}")
    check('_add_details_identity_header' in inactive and 'bundled_catalog_icon_path(profile.component_id)' in inactive,
          "inactive App Page does not use Suite identity presentation / curated catalogue icon")

    targeted = _method_source(tree, source, "install_catalog_component")
    for token in ('inspect_appimage(candidate)', 'inspect_editor_zip(candidate',
                  'inspection.editor_id != profile.component_id',
                  'No installation was started.', 'self.install_editor_appimage(candidate)',
                  'self.install_editor_zip(candidate)'):
        check(token in targeted, f"targeted inactive-page install safety missing: {token}")

    show_component = _method_source(tree, source, "show_catalog_component")
    check('self.show_editor_details(installed)' in show_component,
          "canonical inactive page does not converge to installed App Page when component is present")

    rebuild = _method_source(tree, source, "_rebuild_editor_pages")
    for token in ('selected_root == "__catalogue__"', 'selected_root.startswith("__catalog__:")',
                  'self._ensure_editor_page(installed)', 'self._ensure_catalog_component_page(profile)'):
        check(token in rebuild, f"refresh/install canonical-page transition missing: {token}")

    # Experiment 3 is frontend/catalogue-only. Established lifecycle engines must remain present.
    for method_name in ('purge_editor', '_prune_editor', 'remove_editor_version',
                        'remove_portable_runtime', 'uninstall_appimage_runtime'):
        check(bool(_method_source(tree, source, method_name)), f"lifecycle method missing: {method_name}")

    print("PASS: 0.11-exp3.0 lightweight catalogue / inactive App Page regression contract"
          if not any(error.startswith(prefix) for error in errors)
          else "CHECK: 0.11-exp3.0 catalogue regressions")
