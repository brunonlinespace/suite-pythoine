"""0.11-exp6.0 Store backend-only cutover regressions (Qt-free)."""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations

import os
from pathlib import Path
import tempfile

from suite_pythoine.catalogue.component_policy import is_backend_only_component, supports_desktop_integration
from suite_pythoine.installer import desktop_entry_path, retire_managed_desktop_entry

PACKAGE = Path(__file__).resolve().parent.parent


def run_regressions(errors: list[str]) -> None:
    prefix = "0.11-exp6.0 Store backend cutover: "

    def check(condition: bool, message: str) -> None:
        if not condition:
            errors.append(prefix + message)

    check(is_backend_only_component("store-pythoine"), "Store Pythoine is not classified as backend-only")
    check(not supports_desktop_integration("store-pythoine"), "Store Pythoine still claims desktop-integration support")
    check(not is_backend_only_component("rico-plus"), "ordinary components were incorrectly classified as backend-only")
    check(supports_desktop_integration("rico-plus"), "ordinary component desktop integration was disabled")

    old_data = os.environ.get("XDG_DATA_HOME")
    with tempfile.TemporaryDirectory(prefix="suite-exp6-desktop-") as folder:
        os.environ["XDG_DATA_HOME"] = str(Path(folder) / "data")
        try:
            desktop = desktop_entry_path("store-pythoine")
            desktop.parent.mkdir(parents=True, exist_ok=True)
            desktop.write_text(
                "[Desktop Entry]\n"
                "Type=Application\n"
                "Name=Store Pythoine\n"
                "Exec=/tmp/store-pythoine\n"
                "X-Suite-Pythoine-Managed=true\n"
                "X-Suite-Pythoine-DesktopId=io.github.brunonlinespace.store-pythoine\n",
                encoding="utf-8",
            )
            retired = retire_managed_desktop_entry("store-pythoine")
            check(retired == desktop.resolve(strict=False) and not desktop.exists(),
                  "Suite-managed legacy Store desktop launcher was not retired")

            desktop.write_text(
                "[Desktop Entry]\nType=Application\nName=Store Pythoine\nExec=/tmp/store-pythoine\n",
                encoding="utf-8",
            )
            retired = retire_managed_desktop_entry("store-pythoine")
            check(retired is None and desktop.exists(), "unmanaged Store desktop launcher was removed")
        finally:
            if old_data is None:
                os.environ.pop("XDG_DATA_HOME", None)
            else:
                os.environ["XDG_DATA_HOME"] = old_data

    policy = (PACKAGE / "catalogue/component_policy.py").read_text(encoding="utf-8")
    registry = (PACKAGE / "registry.py").read_text(encoding="utf-8")
    app = read_app_with_presentations()
    inventory_page = (PACKAGE / "ui/pages/installed_applications.py").read_text(encoding="utf8")
    wizard = (PACKAGE / "install_wizard.py").read_text(encoding="utf-8")
    appimage = (PACKAGE / "appimage_wizard.py").read_text(encoding="utf-8")

    check('_BACKEND_ONLY_COMPONENT_IDS = frozenset({"store-pythoine"})' in policy,
          "backend-only policy is not narrowly scoped to Store Pythoine")
    check("desktop_issue = 'not-applicable'" in registry,
          "Store discovery still models a standalone desktop launcher as required state")
    check("legacy_desktop_version" in registry and "legacy_desktop_runtime" in registry,
          "legacy Store desktop selection is not preserved during backend migration")
    check("retire_managed_desktop_entry(component.editor_id)" in app,
          "normal Suite refresh does not retire an obsolete managed Store launcher")
    check('("Launch", self.show_store' in app,
          "Store App Page still exposes the standalone launcher instead of the integrated frontend")
    check('launch = QPushButton("Launch")' in inventory_page,
          "Installed Applications does not redirect Store launch to the integrated frontend")
    check("not is_backend_only_component(component) and component.available" in app,
          "generic Launch chooser still lists backend-only Store Pythoine")
    check("self.show_store()" in app[app.index("def launch_editor_version"):app.index("def _sync_suite_appimage_sidecars")],
          "exact-version Store launch is not guarded")
    check("self.show_store()" in app[app.index("def launch_editor("):app.index("def launch_prompt")],
          "ordinary Store launch is not guarded")
    check("self.backend_only = is_backend_only_component(inspection)" in wizard,
          "ZIP installer does not recognise backend-only Store Pythoine")
    check('"Suite-integrated backend; no standalone launcher"' in wizard,
          "ZIP installer can still create a standalone Store launcher")
    check("self.backend_only = is_backend_only_component(inspection)" in appimage,
          "AppImage installer does not recognise backend-only Store Pythoine")
    check('"Suite-integrated backend; no standalone launcher"' in appimage,
          "AppImage installer can still create a standalone Store launcher")


if __name__ == "__main__":
    failures: list[str] = []
    run_regressions(failures)
    if failures:
        for failure in failures:
            print("FAIL:", failure)
        raise SystemExit(1)
    print("PASS: 0.11-exp6.0 Store backend-only cutover regressions")
