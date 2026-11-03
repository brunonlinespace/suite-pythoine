"""0.11-exp5.3 explicit online Store refresh/acquisition regressions (Qt-free)."""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations

import ast
import json
import os
from pathlib import Path
import tempfile

from suite_pythoine.catalogue.component_catalog import COMPONENT_PROFILES
from suite_pythoine.store.store_content import load_store_content, published_manifest_path

PACKAGE = Path(__file__).resolve().parent.parent


def _method_source(tree: ast.AST, source: str, name: str) -> str:
    node = next((item for item in ast.walk(tree) if isinstance(item, ast.FunctionDef) and item.name == name), None)
    return ast.get_source_segment(source, node) or "" if node is not None else ""


def run_regressions(errors: list[str]) -> None:
    prefix = "0.11-exp5.3 Store acquisition: "

    def check(condition: bool, message: str) -> None:
        if not condition:
            errors.append(prefix + message)

    source = read_app_with_presentations()
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        errors.append(prefix + f"app.py syntax error: {exc}")
        return

    catalogue = _method_source(tree, source, "_catalogue_page")
    for token in (
        'QPushButton("Refresh Store Online")',
        '("updates", "Updates")',
        'requested_state == "updates"',
        'self._store_update_available(component_id, entry)',
    ):
        check(token in catalogue, f"integrated Store refresh/update filtering missing: {token}")
    for forbidden in ("urllib", "requests.", "urlopen(", "QNetworkAccessManager"):
        check(forbidden not in catalogue, f"normal Store page opening performs network work: {forbidden}")

    online = _method_source(tree, source, "_refresh_store_online")
    check('["--refresh-online"]' in online, "explicit online refresh does not delegate to Store backend")

    backend = _method_source(tree, source, "_start_store_backend_operation")
    check("QProcess(self)" in backend and "process.start()" in backend,
          "Store backend operations are not isolated in a separate process")

    acquire = _method_source(tree, source, "_acquire_store_component")
    check('["--download-component", profile.component_id]' in acquire,
          "Store acquisition does not request the selected trusted component ID")
    check("entry.download_url" in acquire and "entry.sha256" in acquire,
          "Store acquisition is offered without verified package metadata")

    install = _method_source(tree, source, "_install_acquired_store_package")
    for token in (
        "sha256_file(candidate)",
        "candidate.stat().st_size",
        "Store Package Type Mismatch",
        "inspection.editor_id != profile.component_id",
        "Store Package Version Mismatch",
        "inspect_editor_zip(candidate",
        "inspect_appimage(candidate)",
        "install_editor_zip(candidate, store_download=True)",
        "install_editor_appimage(candidate)",
    ):
        check(token in install, f"Suite-side verified acquisition guard missing: {token}")

    inactive = _method_source(tree, source, "_catalog_component_page")
    check('QPushButton("Install from Store…")' in inactive,
          "inactive canonical App Page lacks Store acquisition action")
    check('"Install Local Package…"' in inactive,
          "local package installation fallback was lost")

    enrichment = _method_source(tree, source, "_add_store_enrichment")
    check('QPushButton("Update from Store…")' in enrichment,
          "installed canonical App Page lacks Store update action")

    update_check = _method_source(tree, source, "_store_update_available")
    check("_store_highest_installed_version" in update_check,
          "update availability still treats an older active version as if a newer installed version were absent")

    known_id = next(component_id for component_id in COMPONENT_PROFILES if component_id not in {"suite-pythoine", "store-pythoine"})
    old_data = os.environ.get("XDG_DATA_HOME")
    with tempfile.TemporaryDirectory(prefix="suite-exp53-store-acquisition-") as folder:
        os.environ["XDG_DATA_HOME"] = str(Path(folder) / "data")
        try:
            manifest = published_manifest_path()
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(json.dumps({
                "schema": 2,
                "publisher_id": "brunonlinespace",
                "store_revision": 53,
                "components": [{
                    "id": known_id,
                    "latest_version": "9.9.9",
                    "download_url": "https://example.invalid/application.zip",
                    "sha256": "a" * 64,
                    "package_size": 12345,
                    "package_type": "source-zip",
                }],
            }), encoding="utf-8")
            loaded = load_store_content()
            entry = loaded.get(known_id)
            check(
                entry is not None
                and entry.download_url == "https://example.invalid/application.zip"
                and entry.sha256 == "a" * 64
                and entry.package_size == 12345
                and entry.package_type == "source-zip",
                "Suite did not retain bounded HTTPS/SHA-256/size/type acquisition metadata",
            )

            manifest.write_text(json.dumps({
                "schema": 2,
                "publisher_id": "brunonlinespace",
                "store_revision": 54,
                "components": [{
                    "id": known_id,
                    "download_url": "http://example.invalid/application.zip",
                    "sha256": "b" * 64,
                }],
            }), encoding="utf-8")
            try:
                load_store_content()
            except ValueError:
                pass
            else:
                errors.append(prefix + "Suite accepted a non-HTTPS Store package URL")
        finally:
            if old_data is None:
                os.environ.pop("XDG_DATA_HOME", None)
            else:
                os.environ["XDG_DATA_HOME"] = old_data

    for method_name in ('purge_editor', '_prune_editor', 'remove_editor_version',
                        'remove_portable_runtime', 'uninstall_appimage_runtime'):
        check(bool(_method_source(tree, source, method_name)), f"lifecycle method missing: {method_name}")

    print("PASS: 0.11-exp5.3 explicit online Store/acquisition regression contract"
          if not any(error.startswith(prefix) for error in errors)
          else "CHECK: 0.11-exp5.3 Store acquisition regressions")


if __name__ == "__main__":
    problems: list[str] = []
    run_regressions(problems)
    if problems:
        for problem in problems:
            print("FAIL:", problem)
        raise SystemExit(1)
    print("PASS: 0.11-exp5.3 explicit online Store/acquisition regressions")
