"""0.11-exp5.2 rich offline Store-content regressions (Qt-free)."""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations

import ast
import hashlib
import json
import os
from pathlib import Path
import tempfile

from suite_pythoine.catalogue.component_catalog import COMPONENT_PROFILES
from suite_pythoine.store.store_content import load_store_content, published_manifest_path, resolve_store_screenshot

PACKAGE = Path(__file__).resolve().parent.parent


def _method_source(tree: ast.AST, source: str, name: str) -> str:
    node = next((item for item in ast.walk(tree) if isinstance(item, ast.FunctionDef) and item.name == name), None)
    return ast.get_source_segment(source, node) or "" if node is not None else ""


def run_regressions(errors: list[str]) -> None:
    prefix = "0.11-exp5.2 rich Store: "

    def check(condition: bool, message: str) -> None:
        if not condition:
            errors.append(prefix + message)

    source = read_app_with_presentations()
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        errors.append(prefix + f"app.py syntax error: {exc}")
        return

    enrichment = _method_source(tree, source, "_add_store_enrichment")
    for token in (
        'QLabel("Highlights")',
        'QLabel("Release Notes")',
        'QLabel("Screenshots")',
        'resolve_store_screenshot(screenshot)',
        'QPixmap(str(path))',
        'Update available',
        'Installed version:',
        ('Latest Store version:' if 'Latest Store version:' in enrichment else 'Available version:'),
    ):
        check(token in enrichment, f"canonical App Page rich-content rendering missing: {token}")

    listing = _method_source(tree, source, "_catalogue_page")
    for token in (
        'Current: {current_version}',
        ('Store: {entry.latest_version}' if 'Store: {entry.latest_version}' in listing else 'Available: {entry.latest_version}'),
        'Update available',
        'entry.highlights',
        'Release notes:',
    ):
        check(token in listing, f"integrated Store card/version enrichment missing: {token}")
    for forbidden in ('urllib', 'requests.', 'urlopen(', 'QNetworkAccessManager'):
        check(forbidden not in listing, f"rich Store page introduced implicit network work: {forbidden}")

    update_check = _method_source(tree, source, "_store_update_available")
    check('version_sort_key(installed) < version_sort_key(entry.latest_version)' in update_check,
          "Update available marker does not require the Store version to be newer")

    known_id = next(component_id for component_id in COMPONENT_PROFILES if component_id not in {"suite-pythoine", "store-pythoine"})
    old_data = os.environ.get("XDG_DATA_HOME")
    with tempfile.TemporaryDirectory(prefix="suite-exp52-store-content-") as folder:
        os.environ["XDG_DATA_HOME"] = str(Path(folder) / "data")
        try:
            media_bytes = b"verified-offline-store-screenshot-fixture"
            digest = hashlib.sha256(media_bytes).hexdigest()
            manifest = published_manifest_path()
            media = manifest.parent / "media" / known_id / "window.png"
            media.parent.mkdir(parents=True, exist_ok=True)
            media.write_bytes(media_bytes)
            manifest.write_text(json.dumps({
                "schema": 2,
                "publisher_id": "brunonlinespace",
                "store_revision": 52,
                "components": [{
                    "id": known_id,
                    "latest_version": "9.9.9",
                    "extended_description": "Longer local description",
                    "highlights": ["First highlight", "Second highlight"],
                    "screenshots": [{"path": f"media/{known_id}/window.png", "sha256": digest, "caption": "Main window"}],
                }],
            }), encoding="utf-8")
            loaded = load_store_content()
            check(set(loaded) == {known_id}, "schema-2 rich content did not preserve trusted-ID authority")
            entry = loaded.get(known_id)
            check(entry is not None and entry.highlights == ("First highlight", "Second highlight"),
                  "Store highlights were not parsed as bounded local content")
            check(entry is not None and len(entry.screenshots) == 1 and entry.screenshots[0].caption == "Main window",
                  "Store screenshot metadata was not parsed")
            if entry is not None and entry.screenshots:
                check(resolve_store_screenshot(entry.screenshots[0]) == media.resolve(),
                      "verified Store screenshot did not resolve inside the Store XDG data root")
                media.write_bytes(b"tampered")
                check(resolve_store_screenshot(entry.screenshots[0]) is None,
                      "tampered Store screenshot passed SHA-256 verification")

            manifest.write_text(json.dumps({
                "schema": 2,
                "publisher_id": "brunonlinespace",
                "store_revision": 53,
                "components": [{
                    "id": known_id,
                    "screenshots": [{"path": "../escape.png", "sha256": "0" * 64}],
                }],
            }), encoding="utf-8")
            try:
                load_store_content()
            except ValueError:
                pass
            else:
                errors.append(prefix + "Store screenshot contract accepted a path traversal")
        finally:
            if old_data is None:
                os.environ.pop("XDG_DATA_HOME", None)
            else:
                os.environ["XDG_DATA_HOME"] = old_data

    # Established lifecycle engines remain untouched by this presentation/content experiment.
    for method_name in ('purge_editor', '_prune_editor', 'remove_editor_version',
                        'remove_portable_runtime', 'uninstall_appimage_runtime'):
        check(bool(_method_source(tree, source, method_name)), f"lifecycle method missing: {method_name}")

    print("PASS: 0.11-exp5.2 rich offline Store-content regression contract"
          if not any(error.startswith(prefix) for error in errors)
          else "CHECK: 0.11-exp5.2 rich Store regressions")


if __name__ == "__main__":
    problems: list[str] = []
    run_regressions(problems)
    if problems:
        for problem in problems:
            print("FAIL:", problem)
        raise SystemExit(1)
    print("PASS: 0.11-exp5.2 rich offline Store-content regressions")
