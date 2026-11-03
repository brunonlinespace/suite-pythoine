# x2.3 → x2.4 — Strict Developer Code Preservation Transfer

**Source authority:** issued `suite-pythoine-1.0.0-x2.3-source.zip`, never an inferred working tree. The machine-verifiable whitelist and original file checksums are in `WAVE2_X24_TRANSFER.json`.

## Relocation only

| x2.3 path | x2.4 path |
|---|---|
| `suite_pythoine/developer_intake.py` | `suite_pythoine/developer/developer_intake.py` |
| `suite_pythoine/developer_archive.py` | `suite_pythoine/developer/developer_archive.py` |
| `suite_pythoine/developer_intake_vault.py` | `suite_pythoine/developer/developer_intake_vault.py` |
| `suite_pythoine/developer_policy.py` | `suite_pythoine/developer/developer_policy.py` |

Only an empty `suite_pythoine/developer/__init__.py` is added; there are no duplicate root modules or compatibility proxies.

## Necessitated adjustments

- Developer Intake: seven package-relative imports move up one level; sibling Vault import remains byte-identical. One icon path expression gains `.parent` because it must continue resolving `suite_pythoine/assets/suite-pythoine-128.png`.
- Developer Archive: four package-relative import depths change; no business logic.
- Vault and Policy: no code changes whatsoever.
- `app.py`: four Developer import paths (Intake, Archive, Policy, Vault).
- `main.py`: one Developer Policy import path (pre-Qt CLI).
- `ui/dialogs/preferences.py`: one Developer Intake import path.
- `__init__.py`: version identity x2.3 → x2.4.
- Release metadata, source inventory, historical QA relocation pointers and release notes: packaging/test-only updates.

**Unchanged**: every other production implementation and original README/Licence/asset. The strict x2.4 regression reconstructs all original production Python bytes by reversing only listed changes. The full textual diff is distributed alongside the ZIP.

Headless QA cannot replace native Fedora/KDE runtime assessment.
