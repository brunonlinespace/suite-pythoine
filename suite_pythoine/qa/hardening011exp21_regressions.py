"""0.11-exp2.1 App Page state-hardening regressions (Qt-free)."""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations

import ast
from pathlib import Path
from tempfile import TemporaryDirectory

from suite_pythoine.registry import EditorEntry, EditorVersionInfo
from suite_pythoine.version_history import build_version_history_rows

PACKAGE = Path(__file__).resolve().parent.parent


def _method_source(tree: ast.AST, source: str, name: str) -> str:
    node = next((item for item in ast.walk(tree) if isinstance(item, ast.FunctionDef) and item.name == name), None)
    return ast.get_source_segment(source, node) or "" if node is not None else ""


def run_regressions(errors: list[str]) -> None:
    prefix = "0.11-exp2.1 hardening: "
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
    check('QPushButton("Choose Current Version…")' in details,
          "no-active-version state is not actionable")
    check('"No active version is selected. Choose one in Version History."' in details,
          "no-active-version guidance regressed")
    check('self.show_version_history(target)' in details,
          "no-active-version action no longer opens Version History")
    check('if editor.versions:' in details,
          "Choose Current Version must not appear when no managed versions exist")

    current = _method_source(tree, source, "_current_version_frame")
    check('editor.desktop_issue == "ready"' in current,
          "compact Current Version can label stale desktop ownership as integrated")
    for token in (
        'add_runtime_row("Portable", "Installed" if version_info.has_portable else "Not installed"',
        'add_runtime_row("AppImage", "Installed" if version_info.has_appimage else "Not installed"',
        'add_runtime_row("Recovery", "Available" if has_recovery else "Unavailable"',
    ):
        check(token in current, f"current-version state row missing: {token}")

    refresh = _method_source(tree, source, "refresh_editors")
    check('selected_version = current.property("suite_selected_version")' in refresh,
          "refresh no longer captures the selected Version History row")
    check('self._rebuild_editor_pages(selected_root, selected_version, selected_component_id)' in refresh,
          "refresh no longer passes selected Version History state into rebuild")

    rebuild = _method_source(tree, source, "_rebuild_editor_pages")
    check('preferred = selected_version if isinstance(selected_version, str) else None' in rebuild,
          "Version History selected version is not restored after refresh")
    check('self._ensure_version_history_page(history_editor, preferred_version=preferred)' in rebuild,
          "Version History refresh does not apply the preserved selected version")

    history = _method_source(tree, source, "_version_history_page")
    check('for target_version in (preferred_version, editor.active_version):' in history,
          "Version History fallback order must be preserved-version -> active-version -> first row")
    check('initial_row = 0 if rows else -1' in history,
          "Version History lacks safe first-row/empty fallback")

    # Every mutation that can alter the compact Current Version / History state
    # must rediscover inventory before leaving the user with a stale page.
    mutation_refresh_contract = {
        "make_version_active": "self.refresh_editors()",
        "build_appimage_from_portable": "self.refresh_editors(automatic=True)",
        "restore_portable_from_recovery_action": "self.refresh_editors(automatic=True)",
        "remove_portable_runtime": "self.refresh_editors()",
        "uninstall_appimage_runtime": "self.refresh_editors()",
        "remove_editor_version": "self.refresh_editors(automatic=True)",
    }
    for name, token in mutation_refresh_contract.items():
        method = _method_source(tree, source, name)
        check(token in method, f"{name} no longer refreshes App Page/History state")

    # Functional, Qt-free row-state coverage for the permutations the compact
    # page summarizes: Portable-only, AppImage-only, both, Recovery and active.
    try:
        with TemporaryDirectory(prefix="suite-exp21-") as tmp:
            root = Path(tmp)
            app_root = root / "Sample"
            versions = []
            # Portable-only
            p1 = app_root / "1.0" / "Portable"
            p1.mkdir(parents=True)
            versions.append(EditorVersionInfo(version="1.0", portable_root=p1, portable_command=("python3", "main.py")))
            # AppImage-only
            a2 = app_root / "2.0" / "AppImage" / "sample.AppImage"
            a2.parent.mkdir(parents=True)
            a2.write_bytes(b"appimage")
            versions.append(EditorVersionInfo(version="2.0", appimage_path=a2, installed_command=(str(a2),)))
            # Both + structurally available Recovery, active.
            p3 = app_root / "3.0" / "Portable"
            p3.mkdir(parents=True)
            a3 = app_root / "3.0" / "AppImage" / "sample.AppImage"
            a3.parent.mkdir(parents=True)
            a3.write_bytes(b"appimage")
            r3 = app_root / "3.0" / "Recovery"
            r3.mkdir(parents=True)
            (r3 / "original-source.zip").write_bytes(b"zip")
            (r3 / "recovery.json").write_text("{}", encoding="utf8")
            versions.append(EditorVersionInfo(
                version="3.0", portable_root=p3, portable_command=("python3", "main.py"),
                appimage_path=a3, installed_command=(str(a3),), recovery_dir=r3,
            ))
            editor = EditorEntry(
                editor_id="sample", name="Sample", root=app_root,
                versions=tuple(versions), active_version="3.0", desktop_version="3.0",
                desktop_issue="ready", desktop_runtime="portable",
            )
            rows = build_version_history_rows(editor, root)
            row1, row2, row3 = rows
            check(row1.has_portable and not row1.has_appimage and not row1.has_recovery,
                  "Portable-only history state is wrong")
            check(row2.has_appimage and not row2.has_portable and not row2.has_recovery,
                  "AppImage-only history state is wrong")
            check(row3.has_portable and row3.has_appimage and row3.has_recovery and row3.active,
                  "combined runtime/Recovery/active history state is wrong")
    except Exception as exc:
        errors.append(prefix + f"functional state fixture failed: {type(exc).__name__}: {exc}")

    print("PASS: 0.11-exp2.1 App Page state-hardening regression contract"
          if not any(error.startswith(prefix) for error in errors)
          else "CHECK: 0.11-exp2.1 hardening regressions")
