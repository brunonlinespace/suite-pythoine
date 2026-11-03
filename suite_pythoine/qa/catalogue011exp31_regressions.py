"""0.11-exp3.1 catalogue visual completion / installed-state transition regressions (Qt-free)."""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations

import ast
import json
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent


def _method_source(tree: ast.AST, source: str, name: str) -> str:
    node = next((item for item in ast.walk(tree) if isinstance(item, ast.FunctionDef) and item.name == name), None)
    return ast.get_source_segment(source, node) or "" if node is not None else ""


def run_regressions(errors: list[str]) -> None:
    prefix = "0.11-exp3.1 catalogue hardening: "
    app_source = read_app_with_presentations()
    catalog_source = (PACKAGE / "catalogue/component_catalog.py").read_text(encoding="utf8")
    try:
        app_tree = ast.parse(app_source)
        catalog_tree = ast.parse(catalog_source)
    except SyntaxError as exc:
        errors.append(prefix + f"Python syntax error: {exc}")
        return

    def check(condition: bool, message: str) -> None:
        if not condition:
            errors.append(prefix + message)

    mapping = None
    for node in catalog_tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "_BUNDLED_CATALOG_ICONS" for target in node.targets):
            try:
                mapping = ast.literal_eval(node.value)
            except Exception:
                mapping = None
            break
    check(isinstance(mapping, dict), "curated catalogue icon mapping is missing or not static")
    payload = json.loads((PACKAGE / "components.json").read_text(encoding="utf8"))
    expected_ids = {str(item.get("id")) for item in payload.get("components", []) if item.get("kind") != "hub"}
    mapped_ids = set(mapping or {})
    check(mapped_ids == expected_ids,
          f"curated icon coverage mismatch: missing={sorted(expected_ids-mapped_ids)} extra={sorted(mapped_ids-expected_ids)}")
    if isinstance(mapping, dict):
        for component_id, filename in mapping.items():
            icon = PACKAGE / "assets" / "catalog" / str(filename)
            check(icon.is_file() and icon.stat().st_size > 0,
                  f"missing/empty curated catalogue icon for {component_id}: {filename}")

    required_new = {
        "linspectacles": "linspectacles.png",
        "crawlindo": "crawlindo.png",
        "youlindo": "youlindo.png",
        "sbookypad": "sbookypad.png",
        "gitten": "gitten.png",
        "store-pythoine": "store-pythoine.png",
    }
    for component_id, filename in required_new.items():
        check((mapping or {}).get(component_id) == filename,
              f"wrong curated icon mapping for {component_id}")

    refresh = _method_source(app_tree, app_source, "refresh_editors")
    check('selected_component_id = current.property("suite_component_id")' in refresh,
          "refresh does not retain canonical component identity across installed-state transitions")
    check('self._rebuild_editor_pages(selected_root, selected_version, selected_component_id)' in refresh,
          "refresh does not pass canonical component identity into page rebuild")

    rebuild = _method_source(app_tree, app_source, "_rebuild_editor_pages")
    for token in (
        'selected_component_id: object = None',
        'COMPONENT_PROFILES.get(str(selected_component_id or ""))',
        'self._ensure_catalog_component_page(profile) if profile is not None else self._ensure_catalogue_page()',
    ):
        check(token in rebuild, f"installed→inactive canonical page fallback missing: {token}")

    editor_page = _method_source(app_tree, app_source, "_ensure_editor_page")
    history_page = _method_source(app_tree, app_source, "_ensure_version_history_page")
    inactive_page = _method_source(app_tree, app_source, "_ensure_catalog_component_page")
    check('page.setProperty("suite_component_id", editor.editor_id)' in editor_page,
          "installed App Page does not retain canonical component identity")
    check('page.setProperty("suite_component_id", editor.editor_id)' in history_page,
          "Version History does not retain canonical component identity")
    check('page.setProperty("suite_component_id", profile.component_id)' in inactive_page,
          "inactive App Page does not retain canonical component identity")

    catalogue = _method_source(app_tree, app_source, "_catalogue_page")
    check('bundled_catalog_icon_path(profile.component_id)' in catalogue,
          "Get More list no longer uses curated icons")
    inactive = _method_source(app_tree, app_source, "_catalog_component_page")
    check('bundled_catalog_icon_path(profile.component_id)' in inactive,
          "inactive App Page no longer uses curated icons")

    print("PASS: 0.11-exp3.1 catalogue visual completion / state transition regression contract"
          if not any(error.startswith(prefix) for error in errors)
          else "CHECK: 0.11-exp3.1 catalogue hardening regressions")
