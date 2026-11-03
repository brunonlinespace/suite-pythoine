"""0.10.11 refresh/lazy-page performance architecture regressions (Qt-free)."""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent


def _function_source(tree: ast.AST, source: str, name: str) -> str:
    node = next((item for item in ast.walk(tree) if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name), None)
    if node is None:
        return ""
    return ast.get_source_segment(source, node) or ""


def run_regressions(errors: list[str]) -> None:
    prefix = "0.10.11 performance: "
    app_source = read_app_with_presentations()
    watcher_source = (PACKAGE / "editor_watcher.py").read_text(encoding="utf8")
    try:
        app_tree = ast.parse(app_source)
        ast.parse(watcher_source)
    except SyntaxError as exc:
        errors.append(prefix + f"syntax error: {exc}")
        return

    toggle = _function_source(app_tree, app_source, "_toggle_developer_mode")
    if "refresh_editors" in toggle:
        errors.append(prefix + "F12 Developer Mode still triggers full discovery/refresh")
    if "_sync_developer_mode_ui" not in toggle:
        errors.append(prefix + "Developer Mode no longer synchronizes existing UI controls")

    sync = _function_source(app_tree, app_source, "_sync_developer_mode_ui")
    if 'suite_developer_only' not in sync or "findChildren" not in sync:
        errors.append(prefix + "cached Developer-only controls are not toggled in place")
    if app_source.count('setProperty("suite_developer_only", True)') < 3:
        errors.append(prefix + "not all App Page Developer-only controls are persistently represented")

    rebuild = _function_source(app_tree, app_source, "_rebuild_editor_pages")
    for forbidden in ("self._editor_page(", "self._suite_details_page(", "self._installed_applications_page("):
        if forbidden in rebuild:
            errors.append(prefix + f"refresh still eagerly constructs page via {forbidden}")
    if "_sidebar_application_keys" not in rebuild:
        errors.append(prefix + "lazy sidebar/application identity map missing")

    ensure_editor = _function_source(app_tree, app_source, "_ensure_editor_page")
    if "self._editor_page(" not in ensure_editor or "self.editor_pages" not in ensure_editor:
        errors.append(prefix + "App Pages are not create-on-first-use and cached")
    ensure_suite = _function_source(app_tree, app_source, "_ensure_suite_page")
    if "self._suite_details_page(" not in ensure_suite:
        errors.append(prefix + "Hub Details is not lazy")
    ensure_inventory = _function_source(app_tree, app_source, "_ensure_installed_applications_page")
    if "self._installed_applications_page(" not in ensure_inventory:
        errors.append(prefix + "Installed Applications is not lazy")

    for installer in ("install_editor_zip", "install_editor_appimage"):
        body = _function_source(app_tree, app_source, installer)
        if "_begin_managed_mutation" not in body or "_end_managed_mutation" not in body:
            errors.append(prefix + f"{installer} does not suppress/coalesce managed watcher refreshes")
        if body.count("self.refresh_editors(") != 1:
            errors.append(prefix + f"{installer} does not have exactly one authoritative post-wizard refresh")

    callback = _function_source(app_tree, app_source, "refreshed_after_appimage_install")
    if "refresh_editors" in callback:
        errors.append(prefix + "AppImage wizard callback still refreshes while modal wizard is open")

    for token in ("def begin_suppression", "def end_suppression", "discard_pending", "_pending_while_suppressed"):
        if token not in watcher_source:
            errors.append(prefix + f"watcher coalescing contract missing: {token}")

    print("PASS: 0.10.11 lazy-page / refresh-coalescing regressions"
          if not any(error.startswith(prefix) for error in errors)
          else "CHECK: 0.10.11 performance regressions")
