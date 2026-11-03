"""0.11-exp1.1 Version History/install hand-off hardening regressions (Qt-free)."""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent


def _method_source(tree: ast.AST, source: str, name: str) -> str:
    node = next((item for item in ast.walk(tree) if isinstance(item, ast.FunctionDef) and item.name == name), None)
    return ast.get_source_segment(source, node) or "" if node is not None else ""


def run_regressions(errors: list[str]) -> None:
    prefix = "0.11-exp1.1 hardening: "
    source = read_app_with_presentations()
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        errors.append(prefix + f"app.py syntax error: {exc}")
        return

    refresh = _method_source(tree, source, "refresh_editors")
    if 'current.property("suite_selected_version")' not in refresh:
        errors.append(prefix + "refresh does not preserve the selected Version History row")
    if "self._rebuild_editor_pages(selected_root, selected_version, selected_component_id)" not in refresh:
        errors.append(prefix + "selected Version History row is not handed into page reconstruction")

    rebuild = _method_source(tree, source, "_rebuild_editor_pages")
    if "preferred_version=preferred" not in rebuild:
        errors.append(prefix + "Version History reconstruction does not receive the preserved version")

    history = _method_source(tree, source, "_version_history_page")
    for token in ('preferred_version: str | None = None', 'page.setProperty("suite_selected_version"', '(preferred_version, editor.active_version)'):
        if token not in history:
            errors.append(prefix + f"Version History selection hardening missing: {token}")

    landing = _method_source(tree, source, "_show_component_after_install")
    if 'component_id == "suite-pythoine"' not in landing or "self.show_suite_details()" not in landing:
        errors.append(prefix + "Suite self-install does not land on Hub Details")
    if "self.show_editor_details(application)" not in landing:
        errors.append(prefix + "ordinary successful install does not land on the canonical App Page")

    zip_install = _method_source(tree, source, "install_editor_zip")
    if "if wizard.progress_page.succeeded:" not in zip_install or "self._show_component_after_install(inspection.editor_id)" not in zip_install:
        errors.append(prefix + "ZIP success hand-off is missing")
    if zip_install.find("self._show_component_after_install(inspection.editor_id)") < zip_install.find("self.refresh_editors()"):
        errors.append(prefix + "ZIP hand-off occurs before the authoritative inventory refresh")

    appimage_install = _method_source(tree, source, "install_editor_appimage")
    if "if wizard.progress.succeeded:" not in appimage_install or "self._show_component_after_install(inspection.editor_id)" not in appimage_install:
        errors.append(prefix + "AppImage success hand-off is missing")
    if appimage_install.find("self._show_component_after_install(inspection.editor_id)") < appimage_install.find("self.refresh_editors()"):
        errors.append(prefix + "AppImage hand-off occurs before the authoritative inventory refresh")

    purge = _method_source(tree, source, "purge_editor")
    if "finished_callback=lambda: None" not in purge:
        errors.append(prefix + "Purge still refreshes from inside the modal wizard")
    if "self._begin_managed_mutation()" not in purge or "self._end_managed_mutation()" not in purge:
        errors.append(prefix + "Purge is not coalescing its own filesystem watcher events")
    if purge.count("self.refresh_editors(") != 1:
        errors.append(prefix + "Purge must have exactly one authoritative post-wizard refresh")

    print("PASS: 0.11-exp1.1 selection, post-install landing and Purge refresh hardening"
          if not any(error.startswith(prefix) for error in errors)
          else "CHECK: 0.11-exp1.1 hardening regressions")
