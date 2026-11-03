# Suite Pythoine 0.3.1 — Markopad and catalogue invalidation audit

0.3.1 is a focused family/catalogue update on the 0.3.0 architecture.

## Canonical editor split

- `markopad` is an Editor for `.md`, `.markdown`, `.mdown`, `.mkd` and `text/markdown`.
- `ricopad` is an Editor for `.rtf` only and retains `text/rtf` plus `application/rtf`.
- Suite Pythoine remains the OS-level Hub for the unchanged union, but only the relevant Editor is an internal candidate.

The Markopad 0.0.2-r1 canonical source supplied for this release was inspected directly: it declares `APP_ID = "markopad"`, `APP_NAME = "Markopad"`, desktop ID `io.github.brunonlinespace.markopad`, repository `brunonlinespace/markopad`, and `SUPPORTED_EXTENSIONS = {".md", ".markdown", ".mdown", ".mkd"}`.

## Upgrade hygiene

0.3.0 could write the visible extension list into `editor_overrides` whenever an Editor Preferences dialog was saved, even if only Launch runtime changed. 0.3.1 removes obsolete Markdown entries from Ricopad overrides and remembered Ricopad Markdown routes, while retaining RTF and unrelated custom extensions. Future Preferences saves do not persist an extension override when it exactly matches the trusted catalogue.

Current trusted catalogue capabilities also take precedence over stale managed AppImage/source metadata, preventing an older Ricopad record from resurrecting Markdown routing.

## Catalogue-only updates

The routing index now contains a digest of the active trusted component catalogue in addition to the shallow Components-folder inventory stamp. Any verified catalogue-only component/capability change therefore rejects the old routing index immediately and falls back to authoritative dependency-light discovery. The open Store also requests an inventory refresh after a successful catalogue check.

Catalogue payloads now carry a monotonic `catalog_revision`. Legacy schema-1 payloads without the field are revision 0. The bundled 0.3.1 catalogue is revision 2, so it automatically supersedes a stale cached 0.3.0 catalogue. Future independently published catalogues must increment the revision; downgrade attempts and changed content under the same revision are rejected.

The pre-GUI dispatcher applies the Ricopad/Markopad routing migration in memory before reading preferences or discovering components. This prevents a stale 0.3.0 Ricopad override from affecting a file double-click even before the full Hub has had a chance to save migrated preferences.

This closes the remaining gap in the 0.3.0 goal that future Editors can be introduced through the verified catalogue when the existing schema is sufficient, without requiring a Hub code release merely to teach Suite a new component identity.


## Alongside-install activation choice

A retained-version install and an activation decision are separate. For `upgrade_alongside`, both source-ZIP and direct-AppImage wizards now leave **Make this version active after installation** enabled (checked by default). If the user clears it, the incoming version is installed and retained but the previous Active/Desktop-integrated version remains unchanged. Remove-older upgrade/downgrade modes continue to require activation because the previous active release may be removed.
