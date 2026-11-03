# Wave 2 — x2.0 versus x2.1 source relocation diff

## Provenance and control

- Baseline: independently issued `suite-pythoine-1.0.0-x2.0-source.zip`.
- All seven original modules have exactly one destination. No original copy or runtime compatibility stub remains.
- Reversing only whitelisted import changes reconstructs the **exact original bytes** for all production Python files, checked by `qa/wave2_x21_regressions.py` against the frozen x2.0 dependency fingerprints.
- No resource-path edits were necessary. All imports changed are documented below.

## Relocated production modules

| Old path under `suite_pythoine/` | New path under `suite_pythoine/` | Byte identical? |
|---|---|---|
| `dashboard.py` | `ui/shell/dashboard.py` | No — relative imports only |
| `dashboard_model.py` | `ui/shell/dashboard_model.py` | No — relative imports only |
| `suite_theme.py` | `ui/shell/suite_theme.py` | Yes |
| `sidebar_launcher.py` | `ui/shell/sidebar_launcher.py` | Yes |
| `sidebar_search.py` | `ui/shell/sidebar_search.py` | Yes |
| `quick_tour.py` | `ui/dialogs/quick_tour.py` | No — relative imports only |
| `shortcuts_dialog.py` | `ui/dialogs/shortcuts_dialog.py` | Yes |

## Only permitted production-source adjustments

- `app.py`: five imports now target the new `ui.shell` and `ui.dialogs` owners.
- `ui/shell/dashboard.py`: four relative imports use `...` to reach original root-level dependencies. Its `.dashboard_model` sibling import stays unchanged.
- `ui/shell/dashboard_model.py`: one relative import uses `...registry`.
- `ui/dialogs/quick_tour.py`: one relative import uses `... import APP_NAME`.
- `ui/shell/__init__.py`: new package marker with only a module docstring.
- `__init__.py`: version identifier only; no other production method/body/constant changed.
- No resource lookup/path adaptation was necessary; no existing `__file__` usage or assets moved.

## QA and metadata

- Historical tests now read relocated files and updated caller import paths. Historical check logic remains in force.
- Frozen digest expectations for **authorized relocated files only** now point to their new locations/current hashes, while the new x2.1 guard independently proves byte-equivalence after reversing the authorized import statements.
- `qa/theme0112_qt.py` points to relocated classes; the test itself is unchanged and must be run on a Qt-capable machine.
- The old dependency baseline JSON remains byte-for-byte frozen.
- Manifest, distribution metadata, versioned script identities, release documentation, and the new regression are the other authorized changes.

## Acceptance boundary

- Static/manifest/packaging QA: must pass before issuing.
- GUI, AppImage and measured performance parity: **not yet verified** on Fedora/KDE.
