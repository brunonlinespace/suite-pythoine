# Suite Pythoine — Wave 2 dependency and ownership baseline

**Release:** `1.0.0-x2.0`  
**Source authority:** issued `1.0.0-x1.8`; behavior authority: `0.12.3`.  
**Scope:** map and verify the existing code, *without relocating modules or changing operational/UI behavior*.

## Reproducible source evidence

- `WAVE2_DEPENDENCIES.json` is a frozen, machine-readable AST/import/source-hash snapshot of **the original x1.8 production tree**, before the `x2.0` release-identity update.
- It covers **70 Python entry/module files**, including `main.py`, the package `__init__.py`, and the extracted Wave-1 UI modules. It deliberately excludes QA, tools, packaging, docs and build artifacts from its production-module graph.
- `python3 -m suite_pythoine.tools.wave2_dependencies --root .` regenerates a **current** read-only JSON view of the tree for comparison, without importing Qt or application code.
- `qa/wave2_x20_regressions.py` locks the source map checksum and proves all production Python files in `x2.0`, except release-version-only `__init__.py`, are **byte-for-byte identical to x1.8**. The regular release check separately locks the root GitHub `README.md` and supplied `LICENSE`.

The graph only captures statically resolvable Python imports. Dynamic imports, package-resource references, shell/worker spawning, Qt plugin loading, PyInstaller hidden imports, and filesystem paths are **not** proven safe by this graph. The `uses___file__` and dynamic-import flags are prompts for manual audit, not an exhaustive inventory of implicit path dependencies.

## Highly shared modules (static importers from this production-only snapshot)

| Current owner | Direct static importers | Wave-2 treatment |
|---|---:|---|
| `storage_layout.py` | 23 | Keep root/foundational; enforce path contracts |
| `installer.py` | 20 | High-coupling; migrate only in dedicated installation phase |
| `registry.py` | 18 | Keep inventory owner stable |
| `component_catalog.py` | 16 | Relocation requires resource-path audit |
| `installation_state.py` | 12 | Keep shared state owner stable |
| `versioning.py` | 12 | General utility; no forced movement |

The counts differ from earlier informal audits because this snapshot excludes QA and build tools and includes only statically resolvable direct imports; counts are *not* a measurement of runtime usage.

## Location-sensitive files requiring explicit review

The AST scan sees `__file__` in:

`main.py`, `app.py`, `component_catalog.py`, `developer_intake.py`, `self_restore.py`, `store_bridge.py`, `suite_self_restore_worker.py`, `suite_uninstall.py`, and `suite_uninstall_worker.py`.

Before relocating any of these, explicitly inspect image/catalogue-resource selection, worker-script paths, source/app directory traversal, packaging inclusions, and any relative assets. Additional modules without `__file__` may still rely on hard-coded sibling resources or dynamic paths.

## Planned ownership (not new implementation)

| Domain | Candidate group | Deferred until |
|---|---|---|
| UI infrastructure | `ui/` shell, dashboard, dialogs | x2.1 |
| Catalogue policy | `catalogue/` | x2.2 |
| Store backend | `store/` | x2.3 |
| Developer intake | `developer/` | x2.4 |
| File routing and launch | `routing/`, `runtime/` as appropriate | x2.5 |
| Source ZIP installation | `installation/` | x2.6 |
| AppImage | `appimage/` | x2.7 |
| Recovery | `lifecycle/` | x2.8 |
| Purge, Prune, removal | `lifecycle/` | x2.9 |
| Storage migration | dedicated migration group | x2.10 |
| Suite self-management | `self_management/` | x2.11 |
| Navigation, sidebar, version coordination | `controllers/` | x2.12–x2.13 |
| Main window | `ui/main_window.py` with compatible bootstrap | x2.14 |
| Convergence and acceptance | no new architectural scope | x2.15 |

These are **provisional** destinations, not permission to create compatibility reexports or change services. Resolve the real dependency edge and source-relative asset requirements at each release, or defer the move. No layout change is part of x2.0.

## Preservation boundaries

- The current **root `README.md` is immutable** (SHA-256 `392895da769ac770766a7338081f50be349e7af72892682758f26fe94d23ea95`). Internal `docs/README.md` stays available to the application's documentation action.
- Leave installer, AppImage, Recovery, Purge/Prune, registry, routing, component state, Store, theme, sidebar, dashboard and UI contracts as they are. **The x1.8 Dashboard sequencing is explicitly retained**, pending a separately authorized change.
- Migrations require a new version number, historical QA, before/after AST/function preservation evidence, source-manifest and resource-path checks, and desktop runtime acceptance proportional to risk.
- Do not confuse this Qt-free verification gate with measured GUI or performance parity. See `WAVE2_ACCEPTANCE.md`.
