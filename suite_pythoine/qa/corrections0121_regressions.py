"""0.12.1 floating-launcher Store parity regressions (Qt-free)."""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations

import json
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent
ROOT = PACKAGE.parent


def run_regressions(errors: list[str]) -> None:
    prefix = "0.12.1 correction: "

    def check(condition: bool, message: str) -> None:
        if not condition:
            errors.append(prefix + message)

    app = read_app_with_presentations()
    launcher = (PACKAGE / "ui/shell/sidebar_launcher.py").read_text(encoding="utf-8")
    check('if entry.editor_id != "store-pythoine"' in app,
          "floating launcher inventory does not exclude Store Pythoine from ordinary app groups")
    check('self._sidebar_launcher.set_store_mode(store_mode, icon_path)' in app,
          "Store navigation state is not propagated to the floating launcher")
    check('self._sync_launcher_inventory()\n            self._sync_store_navigation()' in app,
          "new floating launcher instances are not immediately synchronized with Store state")
    check('self.store_button = QPushButton("Get More…", self)' in launcher,
          "floating launcher Store button is not retained for synchronization")
    check('def set_store_mode(self, installed: bool, icon_path=None)' in launcher,
          "floating launcher has no Store-mode synchronization API")
    check('self.store_button.setText("Store Pythoine" if installed else "Get More…")' in launcher,
          "floating launcher Store/Get More label parity is missing")
    check('"Open Store Pythoine inside Suite." if installed' in launcher and
          '"Browse Suite\'s lightweight offline catalogue."' in launcher,
          "floating launcher Store/Get More tooltip parity is missing")
    check('store = QPushButton("Get More…", self)' not in launcher,
          "unsynchronized local Store button implementation remains")

    print("PASS: 0.12.1 floating-launcher Store parity regressions" if not errors
          else "CHECK: 0.12.1 floating-launcher Store parity regressions")


if __name__ == "__main__":
    failures: list[str] = []
    run_regressions(failures)
    if failures:
        for failure in failures:
            print("FAIL:", failure)
        raise SystemExit(1)
