"""0.11-exp5.1 integrated Store navigation/polish regressions (Qt-free)."""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent


def _method_source(tree: ast.AST, source: str, name: str) -> str:
    node = next((item for item in ast.walk(tree) if isinstance(item, ast.FunctionDef) and item.name == name), None)
    return ast.get_source_segment(source, node) or "" if node is not None else ""


def run_regressions(errors: list[str]) -> None:
    prefix = "0.11-exp5.1 Store polish: "
    source = read_app_with_presentations()
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        errors.append(prefix + f"app.py syntax error: {exc}")
        return

    def check(condition: bool, message: str) -> None:
        if not condition:
            errors.append(prefix + message)

    navigation = _method_source(tree, source, "_sync_store_navigation")
    check('self.store_action.setText("Store Pythoine" if store_mode else "Get More Applications…")' in navigation,
          "Tools navigation does not use the full Store Pythoine identity")
    check('self.store_button.setText("Store Pythoine" if store_mode else "Get More…")' in navigation,
          "sidebar navigation does not use the full Store Pythoine identity")

    rebuild = _method_source(tree, source, "_rebuild_editor_pages")
    for group in ("EDITORS", "READERS", "EXTENSIONS"):
        token = f'add_sidebar_group("{group}", [entry for entry in self.'
        check(token in rebuild, f"{group} sidebar group is not explicitly filtered")
    check(rebuild.count('entry.editor_id != "store-pythoine"') >= 3,
          "Store Pythoine is still eligible for an ordinary managed-application sidebar row")

    # Store remains managed underneath: hiding it from ordinary navigation must not
    # erase it from authoritative inventory or lifecycle lookup.
    installed = _method_source(tree, source, "_store_is_installed")
    component = _method_source(tree, source, "_store_component_entry")
    check('self.components' in installed and 'entry.editor_id == "store-pythoine"' in installed,
          "Store installed-state no longer uses managed inventory")
    check('self.components' in component and 'entry.editor_id == "store-pythoine"' in component,
          "Store lifecycle lookup was removed instead of only hiding duplicate navigation")

    page = _method_source(tree, source, "_catalogue_page")
    for token in (
        'QButtonGroup(content)',
        '(("all", "All"), ("installed", "Installed"), ("not-installed", "Not Installed"))',
        'state_filter["value"]',
        'requested_state == "installed" and installed',
        'requested_state == "not-installed" and not installed',
        'text_matches = not query or query in searchable',
        'item.setHidden(not (state_matches and text_matches))',
        'set_state_filter(selected)',
    ):
        check(token in page, f"Store installation-state filter contract missing: {token}")
    check('if store_mode:' in page and 'state_filter_buttons' in page,
          "installation-state controls are not scoped to integrated Store mode")

    for method_name in ('purge_editor', '_prune_editor', 'remove_editor_version',
                        'remove_portable_runtime', 'uninstall_appimage_runtime'):
        check(bool(_method_source(tree, source, method_name)), f"lifecycle method missing: {method_name}")

    print("PASS: 0.11-exp5.1 integrated Store navigation/polish regression contract"
          if not any(error.startswith(prefix) for error in errors)
          else "CHECK: 0.11-exp5.1 Store polish regressions")


if __name__ == "__main__":
    problems: list[str] = []
    run_regressions(problems)
    if problems:
        for problem in problems:
            print("FAIL:", problem)
        raise SystemExit(1)
    print("PASS: 0.11-exp5.1 integrated Store navigation/polish regressions")
