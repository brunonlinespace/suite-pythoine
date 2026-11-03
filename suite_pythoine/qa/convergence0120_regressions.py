"""0.12.0 branch-convergence regressions (Qt-free)."""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations

import json
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent
ROOT = PACKAGE.parent


def run_regressions(errors: list[str]) -> None:
    prefix = "0.12.0 convergence: "

    def check(condition: bool, message: str) -> None:
        if not condition:
            errors.append(prefix + message)

    app = read_app_with_presentations()
    inventory_page = (PACKAGE / "ui/pages/installed_applications.py").read_text(encoding="utf8")
    config = (PACKAGE / "config.py").read_text(encoding="utf-8")
    policy = (PACKAGE / "catalogue/component_policy.py").read_text(encoding="utf-8")
    bridge = (PACKAGE / "store/store_bridge.py").read_text(encoding="utf-8")
    manifest = json.loads((ROOT / "suite-pythoine.json").read_text(encoding="utf-8"))
    catalogue = json.loads((PACKAGE / "components.json").read_text(encoding="utf-8"))
    components = {item["id"]: item for item in catalogue.get("components", [])}

    check(manifest.get("id") == "suite-pythoine", "root manifest identity changed after convergence")
    check('from .ui.shell.suite_theme import apply_theme, normalize_theme' in app,
          "0.11.2 theme system was not carried forward")
    check('from .ui.shell.sidebar_launcher import SidebarLauncher' in app and
          '"sidebar_position": "left"' in config and '"app_theme": "system"' in config,
          "0.11.2 sidebar/theme configuration was not carried forward")
    check(all(component_id in components for component_id in
              ("maqaronypad", "riqatonypad", "maqaronydesk", "riqatonydesk")),
          "0.11.2 Pad/Desk catalogue identities are missing")
    check(all(components[component_id].get("lifecycle") == "legacy" for component_id in
              ("markopad", "ricopad", "marko-plus", "rico-plus")),
          "legacy lifecycle catalogue state was not preserved")
    check('"lifecycle": profile.lifecycle' in bridge,
          "catalogue lifecycle is not projected to Store identity data")

    check('_BACKEND_ONLY_COMPONENT_IDS = frozenset({"store-pythoine"})' in policy,
          "exp6 Store backend-only policy was lost")
    check('def show_store(' in app and 'def _store_catalog_profiles(' in app,
          "exp6 integrated Store frontend was lost")
    check('if key not in self._sidebar_application_keys and not is_backend_only_component(editor):' in app,
          "Store management App Page is still blocked by sidebar visibility")
    check('("Launch", self.show_store' in app,
          "Store App Page does not use Launch to open the integrated Store frontend")
    check('launch = QPushButton("Launch")' in inventory_page,
          "Installed Applications does not use the normal Launch label for Store")
    check('if is_backend_only_component(editor):\n            self.show_store()' in app,
          "Store Launch no longer routes to the integrated frontend")

    print("PASS: 0.12.0 theme/sidebar/catalogue + exp6 Store convergence regressions" if not errors
          else "CHECK: 0.12.0 convergence regressions")


if __name__ == "__main__":
    failures: list[str] = []
    run_regressions(failures)
    if failures:
        for failure in failures:
            print("FAIL:", failure)
        raise SystemExit(1)
