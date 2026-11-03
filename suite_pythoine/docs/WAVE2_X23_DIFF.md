# 1.0.0-x2.3 — CODE PRESERVATION TRANSFER

**Reference source:** `1.0.0-x2.2` (issued archive; 72 original production Python files SHA-256 fingerprinted). The authoritative exact-change ledger is `WAVE2_X23_TRANSFER.json`.

## Relocation

| x2.2 | x2.3 |
|---|---|
| `suite_pythoine/store_bridge.py` | `suite_pythoine/store/store_bridge.py` |
| `suite_pythoine/store_content.py` | `suite_pythoine/store/store_content.py` |

New `store/__init__.py` is strictly empty. No legacy duplicate module or re-export was added.

## Only permitted production adjustments

- `store/store_bridge.py`: eight top-level relative imports, **one lazy import inside the `--install-package` branch** (`from .app` → `from ..app`), and one file-relative fallback (`parents[1]` → `parents[2]`) required to continue identifying the repository-root `main.py`.
- `store/store_content.py`: one relative catalogue import.
- `app.py`: one Store Content import.
- `suite_uninstall.py`: one Store Bridge import.
- `ui/pages/store_catalogue.py`: one Store Content import.
- `__init__.py`: release identity, `x2.2` → `x2.3`.

No resource paths inside Store Content required adjustment: its content paths are based on `XDG_DATA_HOME`, not `__file__`. No production statements were reordered, renamed or refactored.

## Preservation proof

`wave2_x23_regressions.py` checks that every production Python source from x2.2 can be recovered byte-for-byte by reversing **only** the explicit edits in the transfer JSON. It rejects unlisted edits, added or missing modules and changes to the immutable GitHub README and LICENSE. Older tests continue to check their original hash contracts against the reconstructed historical versions.

Historical source-location/import assertions are aligned to the new addresses without dropping their tested functionality. Runtime GUI acceptance is not implied by headless static QA.
