# Suite Pythoine 0.3.2-exp2 — experimental component UI audit

0.3.2-exp2 forks from the 0.3.1 main line so the expanded component model can be tested without replacing the current release.

## Scope

- Add the approved Editor/Extension family profiles to trusted catalogue revision 3.
- Keep routing Editor-only.
- Add Texypad `.tex`/`.bib` ownership and corresponding Hub OS MIME coverage.
- Render Editors and Extensions as separate Dashboard/sidebar groups.
- Keep Extension cards free of New/Open document actions.
- Rename only the sidebar catalogue button to **Get More...**.
- Merge only Suite Pythoine's two Preferences entry points into one Hub Preferences dialog.
- Apply the approved shortcut map.

## Rollback boundary

No 0.3.1 files or behavior are replaced in-place. The experimental source uses its own `0.3.2-exp2` version identity and can be installed alongside 0.3.1 using Suite's existing multi-version management.


## exp2 stabilization note

The first exp1 field test exposed a Dashboard card-construction defect: `EditorCard` created two top-level `QVBoxLayout(self)` instances. That code path is reached when a real component card is first rendered, explaining why the Hub could start empty and then fail when Nuxpad was added. Exp2 removes the duplicate layout, adds release/static guards that require exactly one card layout, and increases sidebar component rows/icons modestly for readability.
