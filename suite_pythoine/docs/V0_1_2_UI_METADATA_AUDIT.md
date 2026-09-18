# Suite Pythoine 0.1.2 — UI/metadata maintenance audit

## Purpose

0.1.2 is a focused follow-up to the 0.1.1 storage-hygiene release. It does not change the unified Editors-folder architecture.

## Corrections

- The wizard's **Editor ID** is the publisher identity (`brunonlinespace`) for the official pad family. Internal application keys remain separate for routing/registry/desktop IDs.
- `ZipEditorInspection` and `EditorEntry` carry publisher identity explicitly; managed records retain it for installed-only representation.
- The Welcome form uses expanding fields and non-wrapping identity/path rows, avoiding the Suite-specific `suite-` clipping seen in 0.1.1.
- Installer branding icons are top-aligned with text.
- Linux `GenericName` is **File Editor Hub**.
- About text ends with `Suite Pythoine: a little Python, sweetly caffeinated.`
- About is parented to an active modal widget when invoked during a wizard and uses delete-on-close/accept semantics. Existing About is closed before Suite enters its own modal installation/migration/purge/preferences dialogs.

## Preserved architecture

Unified application/version/type storage, versioned AppImage naming, exact managed registry paths, Repair/Uninstall/Purge, opt-in Store with terminal hard-disable, silent file dispatch, safe Portapad internal ZIP links and no-sudo/no-dnf AppImage building are unchanged.
