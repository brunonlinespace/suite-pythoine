"""0.10.10 Developer Intake ephemeral exact-ZIP vault regressions (Qt-free)."""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import zipfile

from suite_pythoine.developer.developer_intake_vault import (
    DeveloperIntakeSessionVault,
    VAULT_MARKER,
    VAULT_SCHEMA,
    cleanup_stale_intake_vaults,
)


def run_regressions(errors: list[str]) -> None:
    prefix = "0.10.10 vault: "

    def check(condition: bool, message: str) -> None:
        if not condition:
            errors.append(prefix + message)

    package = Path(__file__).resolve().parent.parent
    intake = (package / "developer/developer_intake.py").read_text(encoding="utf-8")
    app = read_app_with_presentations()
    vault_source = (package / "developer/developer_intake_vault.py").read_text(encoding="utf-8")

    check("DeveloperIntakeSessionVault" in intake,
          "Developer Intake does not own a session ZIP vault")
    check("if prepared.delete_zip_after_success:" in intake and
          "self.session_vault.stage_exact_copy(stored)" in intake,
          "exact ZIP is not staged before development-ZIP deletion")
    check("stored if stored.is_file() else self.session_vault.archive_path" in intake,
          "Install Stored ZIP does not fall back to the exact session archive")
    check('self.zip_label.setText("Deleted after extraction" if dev_zip_deleted else str(stored))' in intake,
          "private vault leaks into the user-facing Development ZIP summary")
    check("cleanup_stale_intake_vaults()" in app,
          "Suite startup does not clean abandoned Intake vaults")
    check("finally:" in app and "dialog.cleanup_session_vault()" in app,
          "vault does not survive installer handoff and clean up afterward")
    check("XDG_RUNTIME_DIR" in vault_source and "tempfile.gettempdir()" in vault_source,
          "vault has no XDG runtime / temp fallback policy")
    check("copied_digest != source_digest" in vault_source,
          "vault copy is not SHA-256 verified")

    with TemporaryDirectory(prefix="suite1010-vault-test-") as temp:
        root = Path(temp)
        source = root / "ricopad-9.9.zip"
        with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("ricopad/main.py", "print('vault-test')\n")
        original_bytes = source.read_bytes()
        base = root / "vaults"
        vault = DeveloperIntakeSessionVault(base=base)
        retained = vault.stage_exact_copy(source)
        check(retained.is_file() and retained.read_bytes() == original_bytes,
              "session vault did not retain a byte-identical ZIP")
        source.unlink()
        check(vault.archive_path is not None and vault.archive_path.read_bytes() == original_bytes,
              "session archive did not survive deletion of the visible original")
        retained_parent = retained.parent
        vault.cleanup()
        check(not retained_parent.exists() and vault.archive_path is None,
              "session cleanup did not remove the private archive")

        # Next-start cleanup removes only Suite-marked abandoned vaults.
        stale = base / "99999999-stale"
        stale.mkdir(parents=True)
        (stale / VAULT_MARKER).write_text(json.dumps({
            "schema": VAULT_SCHEMA,
            "pid": 99999999,
            "complete": True,
        }), encoding="utf-8")
        (stale / "old.zip").write_bytes(b"stale")
        removed = cleanup_stale_intake_vaults(base)
        check(removed == 1 and not stale.exists(),
              "stale Suite-owned Intake vault was not removed")

    print("PASS: 0.10.10 Developer Intake ephemeral ZIP vault regressions"
          if not any(error.startswith(prefix) for error in errors)
          else "CHECK: 0.10.10 Developer Intake vault regressions")
