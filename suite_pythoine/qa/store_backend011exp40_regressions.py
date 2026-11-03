from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

from suite_pythoine.catalogue.component_catalog import COMPONENT_PROFILES
from suite_pythoine.store.store_bridge import STORE_PROTOCOL_VERSION, trusted_catalogue_projection
from suite_pythoine.store.store_content import load_store_content, published_manifest_path


def run_regressions(errors: list[str]) -> None:
    def check(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    check(STORE_PROTOCOL_VERSION == 2, "exp4 Store protocol version is not 2")
    projection = trusted_catalogue_projection()
    check(projection.get("protocol") == 2, "trusted catalogue projection protocol mismatch")
    rows = projection.get("components", [])
    check(isinstance(rows, list) and len(rows) == len(COMPONENT_PROFILES),
          "Store identity projection does not match Suite trusted catalogue")
    by_id = {row.get("component_id"): row for row in rows if isinstance(row, dict)}
    check(set(by_id) == set(COMPONENT_PROFILES), "Store identity projection changed trusted IDs")
    for component_id, profile in COMPONENT_PROFILES.items():
        row = by_id.get(component_id, {})
        check(row.get("name") == profile.name and row.get("kind") == profile.kind,
              f"Store identity projection diverged for {component_id}")
        check(row.get("publisher_id") == "brunonlinespace",
              f"Store identity projection publisher mismatch for {component_id}")

    with tempfile.TemporaryDirectory(prefix="suite-exp40-store-content-") as folder:
        root = Path(folder)
        old_data = os.environ.get("XDG_DATA_HOME")
        os.environ["XDG_DATA_HOME"] = str(root / "data")
        try:
            check(load_store_content() == {}, "absent Store content should be an empty overlay")
            path = published_manifest_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            known_id = next(component_id for component_id in COMPONENT_PROFILES if component_id != "suite-pythoine")
            payload = {
                "schema": 1,
                "publisher_id": "brunonlinespace",
                "store_revision": 1,
                "components": [
                    {"id": known_id, "latest_version": "9.9.9", "extended_description": "Rich content"},
                    {"id": "unknown-store-only-identity", "latest_version": "1.0.0"},
                ],
            }
            path.write_text(json.dumps(payload), encoding="utf-8")
            loaded = load_store_content()
            check(set(loaded) == {known_id}, "Store overlay created or retained an untrusted application identity")
            check(loaded[known_id].latest_version == "9.9.9", "Store overlay release metadata was not parsed")
            check(loaded[known_id].extended_description == "Rich content", "Store overlay rich description was not parsed")

            payload["components"] = [{"id": known_id, "download_url": "http://example.invalid/file.zip"}]
            path.write_text(json.dumps(payload), encoding="utf-8")
            try:
                load_store_content()
            except ValueError:
                pass
            else:
                errors.append("Store overlay accepted a non-HTTPS package URL")
        finally:
            if old_data is None:
                os.environ.pop("XDG_DATA_HOME", None)
            else:
                os.environ["XDG_DATA_HOME"] = old_data


if __name__ == "__main__":
    problems: list[str] = []
    run_regressions(problems)
    if problems:
        for problem in problems:
            print("FAIL:", problem)
        raise SystemExit(1)
    print("PASS: 0.11.0 Store backend/data contract regressions")
