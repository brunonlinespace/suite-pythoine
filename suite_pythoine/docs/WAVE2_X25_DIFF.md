# x2.4 → x2.5 — Strict Routing and Runtime Code Preservation Transfer

**Starting authority:** issued `suite-pythoine-1.0.0-x2.4-source.zip`.

## Exactly five module moves

| Old path | New path |
|---|---|
| `suite_pythoine/routing_chooser.py` | `suite_pythoine/routing/routing_chooser.py` |
| `suite_pythoine/routing_index.py` | `suite_pythoine/routing/routing_index.py` |
| `suite_pythoine/runtime_launcher.py` | `suite_pythoine/runtime/runtime_launcher.py` |
| `suite_pythoine/runtime_paths.py` | `suite_pythoine/runtime/runtime_paths.py` |
| `suite_pythoine/silent_dispatch.py` | `suite_pythoine/routing/silent_dispatch.py` |

The two new package `__init__.py` files are **empty**. There are no shims, proxies, or original-path copies.

## Exact permitted source adaptations

Only imports made invalid by module relocation and the mandatory release identity were modified. No path-relative asset/data correction was needed. Both relocated modules that import siblings (`routing_chooser.py`/`silent_dispatch.py` and `runtime_launcher.py`/`runtime_paths.py`) continue using the same sibling imports where they still resolve correctly.

The immutable, machine-verifiable ledger `WAVE2_X25_TRANSFER.json` contains SHA-256 fingerprints for all **74** original production `.py` files (including `main.py`) plus every reversible edit. Its file set and modifications are enforced by `qa/wave2_x25_regressions.py`.

| Previously existing source file | Authorized literal import/version adjustments |
|---|---:|
| `main.py` | 2 |
| `suite_pythoine/__init__.py` | 1 |
| `suite_pythoine/app.py` | 4 |
| `suite_pythoine/appimage_build_wizard.py` | 1 |
| `suite_pythoine/install_wizard.py` | 1 |
| `suite_pythoine/recovery_restore_wizard.py` | 1 |
| `suite_pythoine/routing_chooser.py` | 2 |
| `suite_pythoine/routing_index.py` | 1 |
| `suite_pythoine/runtime_paths.py` | 1 |
| `suite_pythoine/self_bootstrap.py` | 2 |
| `suite_pythoine/self_restore.py` | 1 |
| `suite_pythoine/silent_dispatch.py` | 5 |
| `suite_pythoine/ui/dialogs/preferences.py` | 2 |

`main.py` retains its pre-GUI silent dispatch routing; its two distinct chooser imports use one common prefix substitution. The routing index retains its existing schema and caching logic. Developer, installer, self-restore, Store and desktop behaviors are untouched.

## QA relocation maintenance

Existing tests continue to enforce their original fingerprints and assertions. Only source locations, test imports, a shared historical source-reader, and necessary version/manifest/release metadata were updated. None of the historical tests was removed.

## Acceptance scope

- Full `qa/static-qa.sh` (compilation, portable version launcher, shell syntax, historical security/lifecycle tests and strict source manifest)
- New x2.5 byte-by-byte reconstruction from the frozen x2.4 source after reversing the exact listed import/version changes
- No old modules remaining, no unexpected production files, README and LICENSE SHA-256 invariance
- Fresh archive extraction, source manifest, ZIP checksum and UNIX executable-permission comparison

Fedora/KDE GUI and representative performance parity remain unmeasured; headless regression success is not a substitute for that acceptance.
