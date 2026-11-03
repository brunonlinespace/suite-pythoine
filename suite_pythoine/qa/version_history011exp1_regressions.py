"""0.11-exp1.0 Version History extraction regressions (Qt-free)."""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations

import ast
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from suite_pythoine.version_history import build_version_history_rows

PACKAGE = Path(__file__).resolve().parent.parent


def _method_source(tree: ast.AST, source: str, name: str) -> str:
    node = next((item for item in ast.walk(tree) if isinstance(item, ast.FunctionDef) and item.name == name), None)
    return ast.get_source_segment(source, node) or "" if node is not None else ""


def run_regressions(errors: list[str]) -> None:
    prefix = "0.11-exp1.0 Version History: "
    app_source = read_app_with_presentations()
    try:
        tree = ast.parse(app_source)
    except SyntaxError as exc:
        errors.append(prefix + f"app.py syntax error: {exc}")
        return

    details = _method_source(tree, app_source, "_populate_editor_details")
    if 'QLabel("Current Version")' not in details:
        errors.append(prefix + "normal App Page does not expose Current Version")
    if 'QPushButton("Version History…")' not in details:
        errors.append(prefix + "normal App Page has no intentional Version History entry")
    if "for item in editor.versions" in details and "current_version = next" not in details:
        errors.append(prefix + "normal App Page appears to rebuild all historical version cards")
    current_renderers = details.count("self._version_management_frame(") + details.count("self._current_version_frame(")
    if current_renderers != 1:
        errors.append(prefix + "normal App Page must construct exactly one current-version renderer")

    history = _method_source(tree, app_source, "_version_history_page")
    for token in ("build_version_history_rows", "QTableWidget", '"Filter versions…"', "itemSelectionChanged", "selected_version_info"):
        if token not in history:
            errors.append(prefix + f"Version History page missing lightweight history contract: {token}")
    if history.count("self._version_management_frame(") != 1:
        errors.append(prefix + "Version History must construct only the selected version management frame")
    if "for row_index, row in enumerate(rows)" not in history:
        errors.append(prefix + "Version History row model is not rendered as lightweight rows")

    ensure = _method_source(tree, app_source, "_ensure_version_history_page")
    if "self.version_history_pages" not in ensure or "self._version_history_page(" not in ensure:
        errors.append(prefix + "Version History page is not lazy/cached")

    focus = _method_source(tree, app_source, "_focus_contextual_search")
    if "show_version_history" not in focus:
        errors.append(prefix + "Ctrl+F App Page contract was not redirected to Version History filtering")

    with TemporaryDirectory(prefix="suite011exp1-history-") as tmp:
        root = Path(tmp)
        rec = root / "Example" / "0.2.0" / "Recovery"
        rec.mkdir(parents=True)
        (rec / "original-source.zip").write_bytes(b"fixture")
        (rec / "recovery.json").write_text('{"schema":1}', encoding='utf8')
        version_a = SimpleNamespace(
            version="0.2.0", has_portable=True, has_appimage=False,
            recovery_dir=rec, desktop_integrated=True, legacy=False,
            validation_issue=""
        )
        version_b = SimpleNamespace(
            version="0.1.9", has_portable=False, has_appimage=True,
            recovery_dir=None, desktop_integrated=False, legacy=True,
            validation_issue="identity mismatch"
        )
        editor = SimpleNamespace(
            name="Example", versions=[version_a, version_b],
            active_version="0.2.0", desktop_version="0.2.0"
        )
        rows = build_version_history_rows(editor, root)
        if len(rows) != 2:
            errors.append(prefix + "row model does not preserve version count")
        else:
            if not (rows[0].active and rows[0].desktop_integrated and rows[0].has_recovery):
                errors.append(prefix + "active/Desktop/Recovery state missing from current history row")
            if rows[1].state_text != "Needs attention":
                errors.append(prefix + "validation issue does not dominate lightweight history row state")
            if rows[1].version_info is not version_b:
                errors.append(prefix + "row model lost exact EditorVersionInfo identity")

    print("PASS: 0.11-exp1.0 current-version / lazy Version History extraction regressions"
          if not any(error.startswith(prefix) for error in errors)
          else "CHECK: 0.11-exp1.0 Version History regressions")
