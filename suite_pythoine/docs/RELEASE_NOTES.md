# Suite Pythoine 1.0.0-x2.6 — Missing GitHub Catalogue Repositories

**Baseline:** issued `1.0.0-x2.5`. This is a catalogue metadata correction only, not a Wave 2 module relocation.

- Added the eight previously absent `repository` declarations in `components.json`: Texypad, Kapitulindo, Beespector Lite, Crawlindo, Youlindo, Sbookypad, gitten, and Python Lair.
- Repository owner remains `brunonlinespace`; single-word application slugs are lowercase, and names with two words are joined by a hyphen.
- Increased `catalog_revision` from 11 to 12, so older cached revision-11 catalogues do not override the newly corrected bundled catalogue. Equal- or higher-revision user catalogues retain their original precedence.
- Left every existing repository declaration untouched, including the incomplete LinSpectacles entry and Nuxpad's legacy identifier. Those are outside the approved missing-links-only scope.
- All application logic, Store contracts, installation, download handling, dispatch, Recovery, Purge and Prune remain unchanged.
- The repository-root `README.md`, `LICENSE`, `COPYING` and all artwork remain byte-identical.
- The x2.6 catalogue regression freezes all non-repository component fields, all pre-existing repository values, and the exact eight authorized additions. Historical catalogue revision regression accepts monotonic evolution from revision 11; x2.6 pins revision 12.
- Fedora/KDE GUI operation and live GitHub availability are not established by this headless release.

---

# Suite Pythoine 1.0.0-x2.5 — Routing/Runtime CODE PRESERVATION TRANSFER

**Baseline:** issued `1.0.0-x2.4`. No improvements, rewrites, or operational changes are authorized.

- Moved `routing_index.py`, `routing_chooser.py`, and `silent_dispatch.py` to `routing/`; moved `runtime_launcher.py` and `runtime_paths.py` to `runtime/`.
- Added two empty package initializers. Only necessary import-depth/importer adaptations, version metadata and QA source-location pointers changed. No relative resource paths were adjusted.
- Preserved pre-GUI dispatch, routing index schema and cache, chooser, configuration/migration behavior, process-launch sanitization, and runtime path detection.
- `docs/WAVE2_X25_TRANSFER.json` freezes the precise source edits and all 74 prior production SHA-256 digests; the new x2.5 regression reconstructs all original source bytes after reversing just those permitted changes.
- The immutable GitHub README, LICENSE, COPYING, assets and unrelated operational code remain unchanged.

Full static QA and fresh-extraction validation required. Fedora/KDE GUI and performance acceptance remain pending.

---

## 1.0.0-x2.4 — Developer module CODE PRESERVATION TRANSFER

- Branches directly from the issued `1.0.0-x2.3` source ZIP.
- Relocates `developer_intake.py`, `developer_archive.py`, `developer_intake_vault.py`, and `developer_policy.py` into the `developer/` package without rewriting any executable logic.
- Developer Intake changes only the original package-relative imports and the `__file__`-relative icon lookup to continue addressing the original package assets directory. Developer Archive changes only import depth; Vault and Policy are byte-identical.
- Adjusts four imports in `app.py`, one in `main.py`, and one in Preferences to the new modules. No other non-version runtime modifications.
- Keeps all installation, validation, retained-archive, ZIP, trust, vault, filesystem and user-interface algorithms intact.
- Historical QA points at the moved modules without weakening original checks; new strict transfer verification reverses the closed list of import and resource adaptations and checks all 73 original production Python sources against immutable x2.3 hashes.
- Immutable GitHub README, LICENSE, application data and assets remain untouched. Fedora/KDE runtime still requires on-device verification.

## 1.0.0-x2.4 — Developer module CODE PRESERVATION TRANSFER

- Branches directly from the issued `1.0.0-x2.3` source ZIP.
- Relocates `developer_intake.py`, `developer_archive.py`, `developer_intake_vault.py`, and `developer_policy.py` into the `developer/` package without rewriting any executable logic.
- Developer Intake changes only the original package-relative imports and the `__file__`-relative icon lookup to continue addressing the original package assets directory. Developer Archive changes only import depth; Vault and Policy are byte-identical.
- Adjusts four imports in `app.py`, one in `main.py`, and one in Preferences to the new modules. No other non-version runtime modifications.
- Keeps all installation, validation, retained-archive, ZIP, trust, vault, filesystem and user-interface algorithms intact.
- Historical QA points at the moved modules without weakening original checks; new strict transfer verification reverses the closed list of import and resource adaptations and checks all 73 original production Python sources against immutable x2.3 hashes.
- Immutable GitHub README, LICENSE, application data and assets remain untouched. Fedora/KDE runtime still requires on-device verification.

## 1.0.0-x2.4 — Developer module CODE PRESERVATION TRANSFER

- Branches directly from the issued `1.0.0-x2.3` source ZIP.
- Relocates `developer_intake.py`, `developer_archive.py`, `developer_intake_vault.py`, and `developer_policy.py` into the `developer/` package without rewriting any executable logic.
- Developer Intake changes only the original package-relative imports and the `__file__`-relative icon lookup to continue addressing the original package assets directory. Developer Archive changes only import depth; Vault and Policy are byte-identical.
- Adjusts four imports in `app.py`, one in `main.py`, and one in Preferences to the new modules. No other non-version runtime modifications.
- Keeps all installation, validation, retained-archive, ZIP, trust, vault, filesystem and user-interface algorithms intact.
- Historical QA points at the moved modules without weakening original checks; new strict transfer verification reverses the closed list of import and resource adaptations and checks all 73 original production Python sources against immutable x2.3 hashes.
- Immutable GitHub README, LICENSE, application data and assets remain untouched. Fedora/KDE runtime still requires on-device verification.

## 1.0.0-x2.3 — Store code preservation transfer

- Branches directly from the issued `1.0.0-x2.2` source archive.
- Relocates `store_bridge.py` and `store_content.py` to `suite_pythoine/store/` without modifying function bodies, conditions or logic.
- Relocation-only exceptions: nine relative imports in Store Bridge (including the deferred wizard import), one in Store Content, three Store-consumer imports, and the source-root fallback from `__file__.parents[1]` to `parents[2]` in Store Bridge.
- Leaves Store protocol, installed-state reporting, screenshots, file validation, catalogue contracts, and installation transaction ownership unchanged.
- Adds byte-for-byte reconstruction guard and immutable x2.2 hashes in `WAVE2_X23_TRANSFER.json`, plus location-aligned historical QA.
- Root GitHub README and LICENSE are unchanged. Fedora/KDE runtime remains to be verified separately.

## 1.0.0-x2.3 — Store code preservation transfer

- Branches directly from the issued `1.0.0-x2.2` source archive.
- Relocates `store_bridge.py` and `store_content.py` to `suite_pythoine/store/` without modifying function bodies, conditions or logic.
- Relocation-only exceptions: nine relative imports in Store Bridge (including the deferred wizard import), one in Store Content, four Store-consumer imports (including the portable entry point), and the source-root fallback from `__file__.parents[1]` to `parents[2]` in Store Bridge.
- Leaves Store protocol, installed-state reporting, screenshots, file validation, catalogue contracts, and installation transaction ownership unchanged.
- Adds byte-for-byte reconstruction guard and immutable x2.2 hashes in `WAVE2_X23_TRANSFER.json`, plus location-aligned historical QA.
- Root GitHub README and LICENSE are unchanged. Fedora/KDE runtime remains to be verified separately.

## 1.0.0-x2.2 — Catalogue relocation (code preservation transfer)

Moved component_catalog.py and component_policy.py into catalogue/. Only required importer paths and two file-relative resource paths changed. No operational implementation redesign. See WAVE2_X22_DIFF.md for exact allowed changes.

# Suite Pythoine 1.0.0-x2.1 — UI module relocation (strict mechanical move)

**Starting point:** issued `1.0.0-x2.0`; `0.12.3` remains the behavior authority.

- Moved exactly seven established UI implementation files: `dashboard.py`, `dashboard_model.py`, `suite_theme.py`, `sidebar_launcher.py`, `sidebar_search.py` to `ui/shell/`, and `quick_tour.py`, `shortcuts_dialog.py` to `ui/dialogs/`. No implementations were rewritten, reformatted or reorganized.
- Four relocated files are **byte-for-byte identical**. Only the required relative-import statements in `dashboard.py`, `dashboard_model.py`, and `quick_tour.py` changed, plus the five caller imports in `app.py`. No `__file__`-relative resources in the seven modules required path adaptations; none were made.
- Kept `operation_ui.py` and `ui_titles.py` at package root because moving either would unnecessarily affect operational importers.
- Updated historical source-location checks and the one optional Qt GUI smoke test to load the new paths; retained their actual assertions. Historical fixed-hash checks retain their enforcement against the *new* source locations. Added `qa/wave2_x21_regressions.py`, which reverse-applies **only** authorized import changes to **every** production Python module and verifies the exact frozen original source SHA-256 for each.
- `docs/WAVE2_X21_DIFF.md` enumerates every permitted production relocation and import exception against the x2.0 baseline. Root `README.md`, `LICENSE`, other operational modules, Dashboard construction/replacement order, lifecycle and Store code are unchanged.
- Version metadata and the strict `SOURCE_MANIFEST.sha256` have been synchronized to `1.0.0-x2.1`. This remains a headless-verified structural release pending real Fedora/KDE GUI, AppImage, and performance acceptance.

---

# Suite Pythoine 1.0.0-x2.0 — Wave 2 dependency and ownership baseline

**Starting point:** issued `1.0.0-x1.8`; `0.12.3` remains the behavior authority. This is a **no-move** baseline release: no navigation/controller extraction and no alteration to the retained x1.8 Dashboard replacement order.

- Added `tools/wave2_dependencies.py`, a read-only, Qt-free AST importer/`__file__` review-cue inventory of the **original x1.8 production Python modules**. Its frozen output and original per-module source hashes are stored in `docs/WAVE2_DEPENDENCIES.json` (70 files including `main.py` and `__init__.py`). The inventory does **not** claim to find all runtime/dynamic imports or packaging/resource references.
- Added `docs/WAVE2_OWNERSHIP_BASELINE.md`, mapping dependency hotspots, relative-path hazards and the provisional x2.1–x2.15 migration order. It establishes no new module ownership and changes no imports or service contracts.
- Added `docs/WAVE2_ACCEPTANCE.md` with explicit Fedora/KDE disposable-fixture GUI and opt-in x1.8 versus x2.0 trace-comparison steps, and with desktop/performance acceptance **PENDING**. The original 0.12.3 can be behavior-tested but cannot yield equivalent in-app diagnostic traces.
- Added `qa/wave2_x20_regressions.py`, locking the original snapshot checksum and checking that every current x2.0 production module is byte-identical to x1.8 **except** `__init__.py`, which contains the required release-version update. Retained x1 historical regressions and strict source-manifest checks remain enabled.
- Only version identity, release notes and in-app documentation are changed outside these new audit/QA/tool files. Root `README.md` and `LICENSE` remain byte-identical, and **no production application logic or operational module has changed**.

Headless QA and metadata checks do **not** constitute Fedora/KDE GUI, AppImage execution, or measured performance parity; those acceptance tasks remain outstanding.

---

# Suite Pythoine 1.0.0-x1.8 — repository front page and license

**Starting point:** issued `1.0.0-x1.7`; behavior authority remains `0.12.3`.

- Added the user-supplied GitHub `README.md` at repository root. The only edits to that source text were the expressly approved renames **Markopad → MaqaronyPad**, **Marko Plus → MaqaronyDesk**, **Ricopad → RiqatonyPad**, **Rico Plus → RiqatonyDesk**, their GitHub slugs, and generic **Plus → Desk** references. The resulting front page is locked byte-for-byte using a SHA-256 regression guard. Do not edit it in future releases without explicit new authorization.
- Added the supplied root `LICENSE` byte-for-byte. Kept the existing operational `COPYING` untouched (the two files are identical).
- Added a minimal root `.gitignore` for generated caches, local virtual environments, build outputs and editor temporary files. No authored assets, screenshots, or documentation moved or replaced.
- Added `qa/decoupling_x18_regressions.py` and updated the release gate / strict source manifest for these additions. In-application `suite_pythoine/docs/README.md` remains at its established path.
- Only synchronized version identity to `1.0.0-x1.8`; no operational, GUI, installer, routing, Recovery, Purge, Store or lifecycle logic changes.

Desktop GUI and comparative performance acceptance against `0.12.3` remain pending, as before.

---

# Suite Pythoine 1.0.0-x1.7 — tracing-default and UI-helper closure

**Starting point:** issued `1.0.0-x1.6`. This is a narrow Wave 1 corrective release; `0.12.3` remains the behavior authority.

- Finding C: `SUITE_PYTHOINE_PERF` is evaluated once, on module import, and defaults OFF. In normal launches the tracing decorators return the original callable directly, `begin_operation` returns a shared inert handle and `trace_span` returns a shared no-op context. There is no context-variable lookup, timing, trace-record allocation, JSON serialization or log I/O on those disabled paths. Explicit opt-in **before launching the process** retains the original diagnostics. There are still trivial no-op instrumentation callsites, so zero overall performance overhead is not claimed.
- Finding B: the three byte/AST-equivalent UI helpers (`_diagnostic_canvas`, `_populate_diagnostic_canvas`, `_style_destructive_button`) now have **one** implementation in `ui/diagnostic_helpers.py`. Both `app.py` and `ui/dialogs/preferences.py` import the same functions. Styling, callbacks, and function bodies remain unchanged.
- Historical QA checking the former helper locations now checks the shared owner. The new `qa/decoupling_x17_regressions.py` independently checks helper AST fidelity, unchanged `SuiteWindow` AST, the default-off/no-log state in a subprocess and opt-in trace output in a separate subprocess. Retained x1.6 production hashes keep all unrelated modules frozen.
- No installer, AppImage, Recovery, Purge, Prune, asset removal, Store, routing, active-version, desktop integration, theme, sidebar, controller, or user-facing behavior change is intended.

Full headless QA does not replace Fedora/KDE Qt desktop and representative performance acceptance. No measured parity is claimed.

---

# Suite Pythoine 1.0.0-x1.6 — Wave 1 convergence and hardening

**Starting point:** the issued `1.0.0-x1.5` source. `0.12.3` remains the functional/behavioral authority; this is the final Wave 1 presentation-decoupling release, not the beginning of the x2 ownership refactor.

## Exact scope

- Removed 20 unused/stale imports from `app.py` whose actual consumers were moved in prior x1 presentation extractions. There is no change to any callable behavior or body, widget construction, signal connection, routing, or lifecycle handler.
- Preserved all 212 `SuiteWindow` entry-point methods and all x1.1–x1.5 extracted builder bodies. The full x1.5 AST fidelity tests remain in force, including tracing decorators and historical QA reading the **current** extracted code.
- Retained one canonical owner for each existing page builder. Existing Installed Applications and Application Page share the identity-header delegate; Application Page uses the existing Store-enrichment delegate. No second Store-specific installed Application Page was introduced. Apparent similarities between installed and uninstalled pages were not deduplicated where doing so would change callbacks/layout or require new orchestration.
- Updated the historical x1.1 regression's import-location assertions, **without dropping** its widget/helper AST and shell-method coverage. This keeps checks pointed at the real module rather than an obsolete import site.
- Added `qa/decoupling_x16_regressions.py`, which enforces unique builders and forwarding ownership, forbids stale shell imports, freezes 63 other production Python files against the issued x1.5 baseline and unit-checks the performance-trace comparator.
- Added Qt-free `tools/performance_compare.py` to summarize the opt-in JSONL timing probes introduced in x1.0, comparing median and p95 per named operation. Insufficient samples are explicitly flagged as INCOMPLETE. It does not silently assert that latency is unchanged.

**Frozen:** Installer and AppImage behavior, Recovery, Purge, Prune, asset removal, Store backend/download/publisher, routing and active versions, desktop integration, themes, sidebar, navigation, preferences semantics and all other source behavior.

## Validation boundary

Full retained **headless** QA, Python compilation, executable/shell checks, strict authored-source manifest, code-ownership guards and a verified release archive are required. Real performance equivalence and Qt GUI behavior cannot be measured by these checks alone. This environment has no PyQt6 or x1.0/0.12.3 GUI trace dataset; no empirical GUI-performance claim is made.

**Wave 1 is code-complete, subject to Fedora/KDE acceptance testing.** Do not begin the x2 controller/orchestration wave merely because static QA is green. x2 should be considered only after representative desktop validation and review.
