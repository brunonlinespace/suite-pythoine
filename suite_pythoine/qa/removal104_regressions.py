"""0.10.4 Remove Assets / Purge-preferences / Developer-folder regressions."""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations

from pathlib import Path
import os
import sys
import tempfile

from suite_pythoine.asset_removal import RemovalAsset, remove_assets
from suite_pythoine.installer import InstallError, desktop_entry_path, write_portable_desktop_entry
from suite_pythoine.versioning import appimage_metadata_path

PACKAGE = Path(__file__).resolve().parents[1]


def run_regressions(errors: list[str]) -> None:
    prefix = "0.10.4 removal: "

    def check(condition: bool, message: str) -> None:
        if not condition:
            errors.append(prefix + message)

    app = read_app_with_presentations()
    inventory_page = (PACKAGE / "ui/pages/installed_applications.py").read_text(encoding="utf8")
    preferences = (PACKAGE / "ui/dialogs/preferences.py").read_text(encoding="utf8")
    purge = (PACKAGE / "purge_wizard.py").read_text(encoding="utf8")
    engine = (PACKAGE / "asset_removal.py").read_text(encoding="utf8")

    # User-facing terminology and table-level placement.
    check('remove_assets_button = QPushButton("Remove Assets…")' in inventory_page,
          "Installed Applications lacks the final Remove Assets wording")
    check('QPushButton("Clean Up' not in inventory_page and 'QPushButton("Manage Assets' not in inventory_page,
          "superseded cleanup/manage wording remains user-facing")
    search_pos = inventory_page.find('version_filter = QLineEdit()')
    remove_pos = inventory_page.find('remove_assets_button = QPushButton("Remove Assets…")', search_pos)
    settings_pos = inventory_page.find('inventory_row = QHBoxLayout()')
    check(search_pos >= 0 and remove_pos > search_pos and settings_pos < search_pos,
          "Remove Assets is not a table/search-level control")
    check('"Asset", "Active", "Size"' in app and 'record["asset"] == "Recovery"' in inventory_page,
          "asset view does not expose Recovery as a first-class Asset row")
    check('ItemIsUserCheckable' in inventory_page and '"Remove Selected…"' in inventory_page,
          "asset selection/removal controls missing")
    check('protection_reason="The currently running Hub Portable cannot remove itself."' in app and
          'protection_reason="The currently running Hub AppImage cannot remove itself."' in app,
          "currently running Hub runtime is not explicitly protected")

    # Shared low-level engine is exact-selection and rename-first.
    check('class RemovalAsset' in engine and 'def remove_assets(' in engine and 'pre_finalize' in engine,
          "shared transactional asset-removal engine missing")
    check('stage_portable_editor_folder' in engine and 'stage_recovery_folder' in engine and
          'stage_registered_appimage_integration' in engine,
          "asset engine bypasses established staging helpers")
    check('No replacement runtime is selected here.' in engine,
          "asset engine silently retargets surviving runtimes")

    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Applications"
            version = root / "Demo" / "1.0"
            portable = version / "Portable"
            recovery = version / "Recovery"
            appdir = version / "AppImage"
            portable.mkdir(parents=True)
            recovery.mkdir()
            appdir.mkdir()
            (portable / "main.py").write_text("print('demo')\n", encoding="utf8")
            (recovery / "original-source.zip").write_bytes(b"zip")
            appimage = appdir / "demo-1.0.AppImage"
            appimage.write_bytes(b"app")
            appimage_metadata_path(appimage).write_text("{}", encoding="utf8")

            portable_asset = RemovalAsset("demo", "Demo", "1.0", "Portable", portable)
            recovery_asset = RemovalAsset("demo", "Demo", "1.0", "Recovery", recovery)
            remove_assets([portable_asset, recovery_asset], editors_root=root)
            check(not portable.exists() and not recovery.exists() and appimage.is_file(),
                  "mixed Portable/Recovery removal did not preserve the unselected AppImage")

            # A callback failure occurs after staging and must restore exact assets.
            portable.mkdir()
            (portable / "main.py").write_text("print('again')\n", encoding="utf8")
            def fail_commit() -> None:
                raise InstallError("simulated preference save failure")
            try:
                remove_assets([RemovalAsset("demo", "Demo", "1.0", "Portable", portable)],
                              editors_root=root, pre_finalize=fail_commit)
            except InstallError:
                pass
            else:
                check(False, "pre-finalize failure did not abort removal")
            check(portable.is_dir() and (portable / "main.py").is_file(),
                  "pre-finalize failure did not roll back the staged Portable")

            # Protected targets are rejected before staging.
            protected = RemovalAsset("demo", "Demo", "1.0", "Portable", portable,
                                     protected=True, protection_reason="running")
            try:
                remove_assets([protected], editors_root=root)
            except InstallError:
                pass
            else:
                check(False, "protected running asset was removable")
            check(portable.is_dir(), "protected asset was changed")

            # If the exact Portable owns desktop integration, the launcher is
            # removed with it. Ownership must be established before staging the
            # Portable because the status helper requires its launcher to exist.
            old_xdg = os.environ.get("XDG_DATA_HOME")
            try:
                os.environ["XDG_DATA_HOME"] = str(Path(tmp) / "xdg-data")
                command = (sys.executable, str(portable / "main.py"))
                write_portable_desktop_entry("Demo", "demo", command)
                desktop = desktop_entry_path("demo")
                check(desktop.is_file(), "desktop ownership fixture was not created")
                remove_assets([RemovalAsset("demo", "Demo", "1.0", "Portable", portable,
                                            portable_command=command)], editors_root=root)
                check(not portable.exists() and not desktop.exists(),
                      "desktop-owning Portable removal left its verified launcher behind")
            finally:
                if old_xdg is None:
                    os.environ.pop("XDG_DATA_HOME", None)
                else:
                    os.environ["XDG_DATA_HOME"] = old_xdg

            # Exact AppImage removal leaves unrelated contents alone.
            unknown = appdir / "keep-me.txt"
            unknown.write_text("user/unknown", encoding="utf8")
            remove_assets([RemovalAsset("demo", "Demo", "1.0", "AppImage", appimage)], editors_root=root)
            check(not appimage.exists() and not appimage_metadata_path(appimage).exists() and unknown.is_file(),
                  "AppImage removal deleted an unrelated sibling or left its exact sidecar")
    except Exception as exc:
        errors.append(prefix + f"transactional engine regression exception: {type(exc).__name__}: {exc}")

    # Purge preserves application preferences unless explicitly opted in.
    check('QCheckBox("Also remove this application\'s preferences")' in purge and
          'self.remove_preferences.setChecked(False)' in purge,
          "Purge application-preferences option is missing or not opt-in")
    check('profile_for_id(editor.editor_id)' in purge and 'config_subdir' in purge and
          'preferences_stage' in purge,
          "Purge does not use the trusted catalogue config folder with rollback staging")
    check('Application preferences were preserved.' in purge and 'User documents' in purge,
          "Purge preference-preservation contract is not disclosed")

    # Hub Technical Details parity is Developer Mode only and reuses the same root model.
    check('self.open_suite_development_button = QPushButton("Open Development Folder")' in preferences and
          'label == "Technical Details" and bool(self.developer_config and self.developer_config.enabled)' in preferences,
          "Hub Preferences Technical Details Developer button visibility is wrong")
    check('self.controller._open_development_root("suite-pythoine", APP_NAME)' in preferences and
          'def _open_development_root(self, component_id: str, display_name: str)' in app,
          "Hub/app development-folder controls do not share the configured-root behavior")

    print("PASS: 0.10.4 Remove Assets, Purge preference opt-in and Developer-folder parity"
          if not any(e.startswith(prefix) for e in errors)
          else "CHECK: 0.10.4 removal regressions")


if __name__ == "__main__":
    failures: list[str] = []
    run_regressions(failures)
    for failure in failures:
        print("FAIL:", failure)
    raise SystemExit(1 if failures else 0)
