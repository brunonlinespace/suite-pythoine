# Suite Pythoine 1.0.0-x1.0 decoupling baseline

1.0.0-x1.0 begins Wave 1 of the experimental decoupling line. 0.12.3 is the behavioral authority. This release moves no UI ownership and deliberately makes no feature, layout, shortcut, lifecycle, Store, installer, theme, sidebar, routing, Recovery, Purge or Prune change.

Static source baseline inherited from 0.12.3 before diagnostics were added:

- `suite_pythoine/app.py`: 8,093 lines, 421,458 bytes.
- `SuiteWindow`: 6,976 lines, 212 methods.
- QA Python scripts: 49 total; 42 reference `app.py`, `SuiteWindow`, or `suite_pythoine.app`.

The x1 wave uses these preservation rules:

1. Move ownership, not behavior.
2. Preserve existing `SuiteWindow` entry points initially through thin delegates.
3. Do not relocate or redesign installation, active-version switching, desktop integration, Recovery, Purge, Prune, routing, removal, Store backend contracts or filesystem ownership during presentation extraction.
4. Each x1 release must pass the complete retained gate, an extraction-specific regression, a production diff audit, and performance comparison where a live Qt capture is available.
5. No release identifier is reused for a changed source state.

Planned Wave 1 sequence after this baseline: x1.1 independent helpers/widgets; x1.2 Preferences dialogs; x1.3 Installed Applications presentation; x1.4 App Page and Version History presentation; x1.5 Store/catalogue presentation; x1.6 convergence/hardening.
