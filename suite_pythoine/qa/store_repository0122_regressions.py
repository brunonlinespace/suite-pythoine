"""0.12.2 repository-authoritative Store MVP regressions (Qt-free)."""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations

import ast
import json
import os
from pathlib import Path
import tempfile

from suite_pythoine import __version__
from suite_pythoine.catalogue.component_catalog import COMPONENT_PROFILES
from suite_pythoine.store.store_content import (
    STORE_CONTENT_SCHEMAS,
    load_store_content,
    publish_trusted_repository_snapshot,
    trusted_repository_snapshot_path,
)

PACKAGE = Path(__file__).resolve().parent.parent
ROOT = PACKAGE.parent


def _method_source(tree: ast.AST, source: str, name: str) -> str:
    node = next((item for item in ast.walk(tree) if isinstance(item, ast.FunctionDef) and item.name == name), None)
    return ast.get_source_segment(source, node) or "" if node is not None else ""


def run_regressions(errors: list[str]) -> None:
    prefix = "0.12.2 Store repository MVP: "

    def check(condition: bool, message: str) -> None:
        if not condition:
            errors.append(prefix + message)

    root_manifest = json.loads((ROOT / "suite-pythoine.json").read_text(encoding="utf-8"))
    check(root_manifest.get("version") == __version__, "root manifest version does not match Suite Python version")
    check(3 in STORE_CONTENT_SCHEMAS, "Suite does not accept Store repository snapshot schema 3")

    app_source = read_app_with_presentations()
    try:
        tree = ast.parse(app_source)
    except SyntaxError as exc:
        errors.append(prefix + f"app.py syntax error: {exc}")
        return

    refresh = _method_source(tree, app_source, "_refresh_store_online")
    for token in (
        "publish_trusted_repository_snapshot",
        'suite_version=__version__',
        '["--refresh-online"]',
        "Checking authorised application repositories",
    ):
        check(token in refresh, f"trusted repository refresh contract missing: {token}")
    check("store_revision" not in refresh,
          "Suite still presents Store content revision as the online version authority")

    update = _method_source(tree, app_source, "_store_update_available")
    check('entry.check_status in {"error", "unavailable"}' in update,
          "failed repository checks can still produce Update Available")
    check("_store_highest_installed_version" in update,
          "repository update check no longer compares against highest installed version")

    enrichment = _method_source(tree, app_source, "_add_store_enrichment")
    for token in ('QPushButton("View Release")', "entry.release_url", "QDesktopServices.openUrl", '"Could not check"'):
        check(token in enrichment, f"canonical App Page repository status/action missing: {token}")

    catalogue = _method_source(tree, app_source, "_catalogue_page")
    for token in ('f"Available: {entry.latest_version}"', 'version_bits.append("Current")',
                  'version_bits.append("Could not check")', '("updates", "Updates")'):
        check(token in catalogue, f"integrated Store repository state missing: {token}")

    old_data = os.environ.get("XDG_DATA_HOME")
    with tempfile.TemporaryDirectory(prefix="suite-0122-store-trusted-") as folder:
        os.environ["XDG_DATA_HOME"] = str(Path(folder) / "data")
        try:
            target = publish_trusted_repository_snapshot(suite_version="0.12.2")
            check(target == trusted_repository_snapshot_path() and target.is_file(),
                  "Suite did not publish the Store trusted repository bridge to XDG data")
            payload = json.loads(target.read_text(encoding="utf-8"))
            check(payload.get("schema") == 1 and payload.get("publisher_id") == "brunonlinespace",
                  "trusted repository bridge schema/publisher mismatch")
            rows = {row.get("id"): row for row in payload.get("components", []) if isinstance(row, dict)}
            check(set(rows) == set(COMPONENT_PROFILES),
                  "trusted repository bridge does not project exactly Suite's trusted identities")
            for component_id, profile in COMPONENT_PROFILES.items():
                row = rows.get(component_id, {})
                check(row.get("repository") == profile.repository,
                      f"trusted repository bridge changed repository authority for {component_id}")
                check(row.get("publisher_id") == profile.publisher_id,
                      f"trusted repository bridge changed publisher authority for {component_id}")

            # Schema-3 repository status is normalized local Store data only.
            manifest = target.parent / "store-content.json"
            manifest.write_text(json.dumps({
                "schema": 3,
                "publisher_id": "brunonlinespace",
                "store_revision": 6,
                "components": [{
                    "id": "nuxpad",
                    "latest_version": "2.1.1",
                    "release_url": "https://github.com/brunonlinespace/nuxpad/releases",
                    "check_status": "ok",
                }],
            }), encoding="utf-8")
            loaded = load_store_content(manifest)
            nuxpad = loaded.get("nuxpad")
            check(nuxpad is not None and nuxpad.latest_version == "2.1.1" and nuxpad.check_status == "ok"
                  and nuxpad.release_url == "https://github.com/brunonlinespace/nuxpad/releases",
                  "Suite did not retain repository-authoritative Store snapshot fields")
        finally:
            if old_data is None:
                os.environ.pop("XDG_DATA_HOME", None)
            else:
                os.environ["XDG_DATA_HOME"] = old_data

    # Store remains backend-only and its management App Page/Launch fixes from
    # 0.12.0/0.12.1 must survive this discovery-only release.
    show_details = _method_source(tree, app_source, "show_editor_details")
    launch = _method_source(tree, app_source, "launch_editor")
    check("is_backend_only_component(editor)" in show_details,
          "Store backend management App Page guard regressed")
    check("is_backend_only_component(editor)" in launch and "self.show_store()" in launch,
          "Store Launch no longer routes to the integrated frontend")

    print("PASS: 0.12.2 repository-authoritative Store MVP regressions"
          if not any(error.startswith(prefix) for error in errors)
          else "CHECK: 0.12.2 Store repository MVP regressions")


if __name__ == "__main__":
    problems: list[str] = []
    run_regressions(problems)
    if problems:
        for problem in problems:
            print("FAIL:", problem)
        raise SystemExit(1)
    print("PASS: 0.12.2 repository-authoritative Store MVP regressions")
