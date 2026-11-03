# Suite Pythoine 0.2.1 — direct AppImage adoption audit

0.2.1 completes the direct-AppImage path discussed during the 0.2.0 version-management work. An `.AppImage` is treated as an application package, never as a document extension.

## Identification

Suite validates that the file is an ordinary ELF AppImage-sized artifact, calculates SHA-256, checks filename/ELF architecture consistency, and identifies the official pad family from a trusted Suite sidecar or canonical application/version/architecture filename. Experimental version text such as `0.3.3-retro-exp1` is preserved. The editor GUI is not launched for identification.

## Managed adoption

The AppImage wizard copies the artifact atomically to `<Editors Root>/<Application>/<Version>/AppImage/`, reuses a matching portable/source icon when available, optionally makes the version Active/Desktop-integrated, writes the normal managed sidecar/registry record, and applies the same Install/Upgrade/Downgrade/Reinstall policy as source ZIP installation.

## Builder failure recovery

The source ZIP installer remains conservative: a non-zero editor build script exit or failed artifact verification cannot be silently accepted. The Portable copy remains installed. A user who successfully builds the AppImage separately can now drag it onto Suite or use **File → Install Editor…** to adopt it through the managed path.

## UI

Technical-details expansion preserves the checklist height and attempts to grow the wizard within the current screen's available geometry; hiding details restores the previous window size.
