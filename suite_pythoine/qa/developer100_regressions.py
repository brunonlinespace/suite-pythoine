"""0.10.0 Developer Mode / Developer Intake focused regressions (Qt-free)."""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations

import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory

from suite_pythoine.developer import developer_policy


def run_regressions(errors: list[str]) -> None:
    def require(truth: bool, message: str) -> None:
        if not truth:
            errors.append("0.10.0 Developer Mode: " + message)

    package = Path(__file__).resolve().parent.parent
    app = read_app_with_presentations()
    intake = (package / "developer/developer_intake.py").read_text(encoding="utf8")
    policy = (package / "developer/developer_policy.py").read_text(encoding="utf8")

    # Developer Intake itself is the Tools entry; choosing a ZIP belongs inside it.
    require(re.search(r'self\.developer_intake_action\.setShortcut\("Ctrl\+Alt\+Shift\+[A-Z]"\)', app) is not None,
            "Developer Intake four-modifier shortcut missing")
    require('self.retain_source_zip_action.setShortcut("Ctrl+Alt+Shift+R")' in app,
            "Recovery-only shortcut missing")
    require('def developer_intake_prompt(self)' in app and 'return self._run_developer_intake()' in app,
            "Tools Developer Intake still forces an outer ZIP chooser")
    require('QPushButton("Choose ZIP…")' in intake and 'def _choose_zip(self)' in intake,
            "Developer Intake lacks its internal ZIP chooser")

    # The former settings-only Layout tab is now on the intake front page.
    require('QGroupBox("Intake")' in intake, "Intake controls are not on the main dialog")
    require('tabs.addTab(layout_page, "Layout")' not in intake, "obsolete Layout tab remains")
    require('tabs.addTab(roots_page, "App Roots")' in intake and 'tabs.addTab(local_page, "Local Components")' in intake,
            "Developer configuration no longer contains the two intended management tabs")

    # Blank layout values are intentional and persistent; 0.10.3 keeps them inside the mandatory ZIP-derived intake folder.
    with TemporaryDirectory(prefix="suite0100-devcfg-") as td:
        cfg = Path(td) / "developer-intake.json"
        cfg.write_text(json.dumps({
            "schema": developer_policy.DEVELOPER_CONFIG_SCHEMA,
            "enabled": True,
            "app_roots": {},
            "source_relative": "",
            "notes_relative": "",
            "isolate_extracted": True,
            "delete_zip_after_success": False,
            "delete_original_after_success": False,
        }), encoding="utf8")
        loaded = developer_policy._load(cfg)
        require(loaded["source_relative"] == "" and loaded["notes_relative"] == "",
                "blank layout values are silently replaced by legacy defaults")
    require('dev_folder = root / path.stem' in intake and
            'source_folder = dev_folder if source_relative is None else dev_folder / source_relative' in intake,
            "blank Source folder escapes the mandatory ZIP-derived intake boundary")
    require('refuse_existing=True' in intake and 'target.exists()' in intake,
            "intake-folder extraction lacks existing-file collision protection")

    # Store-only remains first-class. 0.10.2 makes Action the commit point,
    # while preserving optional notes and retaining the development ZIP.
    for token in ('QRadioButton("Store ZIP only")', 'store_zip_only = self.store_only_radio.isChecked()',
                  'if prepared.store_zip_only:', 'source ZIP retained without extraction',
                  'delete_zip_after_success=bool(self.delete_box.isChecked()) and not store_zip_only'):
        require(token in intake, f"Store ZIP only contract missing: {token}")
    require('readme = self._write_release_notes(prepared)' in intake,
            "Store ZIP only no longer supports optional release-note output")

    # Stored trusted ZIP can hand back into the existing installer after Intake closes.
    require('QPushButton("Install Stored ZIP…")' in intake and 'self.install_requested_zip' in intake,
            "Install Stored ZIP action missing")
    require('return self.install_editor_zip(install_zip)' in app,
            "stored ZIP does not re-enter the existing guided installer")
    require('LOCAL Developer Intake identities cannot enter Suite\'s normal trusted installer.' in intake,
            "local-only identities can incorrectly enter the trusted installer")

    # Technical Details gains direct development-root access in Developer Mode.
    require('buttons.addButton("Open Development Folder", QDialogButtonBox.ButtonRole.ActionRole)' in app,
            "Technical Details development-folder action missing")
    require(
        'def _open_development_folder(self, editor: EditorEntry)' in app
        and (
            'self.developer_config.set_app_root(editor.editor_id, root)' in app
            or (
                'return self._open_development_root(editor.editor_id, editor.name)' in app
                and 'self.developer_config.set_app_root(component_id, root)' in app
            )
        ),
        "development-folder action cannot establish a missing per-app root",
    )

    # CLI terminology is now consistently Developer Mode.
    require('Developer Intake Mode enabled.' not in policy and 'Developer Intake Mode disabled.' not in policy,
            "legacy Developer Intake Mode CLI wording remains")
    require('Developer Mode enabled.' in policy and 'Developer Mode disabled.' in policy,
            "Developer Mode CLI wording missing")

    # No plain Ctrl+Alt developer shortcut: the approved four-modifier convention is used.
    dev_shortcuts = re.findall(r'setShortcut\("([^"]+)"\)', app)
    require("Ctrl+Alt+T" not in dev_shortcuts and "Ctrl+Alt+R" not in dev_shortcuts,
            "plain Ctrl+Alt Developer shortcut introduced")
    require(len(dev_shortcuts) == len(set(dev_shortcuts)), "duplicate QAction shortcut introduced")

    print("PASS: 0.10.0 Developer Intake front-page, store-only, shortcuts, dev-folder and installer handoff regressions")


if __name__ == "__main__":
    failures: list[str] = []
    run_regressions(failures)
    for failure in failures:
        print("FAIL:", failure)
    if failures:
        raise SystemExit(f"{len(failures)} regression(s) failed")
