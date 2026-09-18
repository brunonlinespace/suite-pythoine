# Suite Pythoine 0.0.1-r6 — guided installation audit

## Goal

Replace the sequence of unrelated ZIP/build/install message boxes with a single guided installation experience while keeping build output visible and preserving the rule that Suite Pythoine owns installation state.

## Architecture

`install_inspection.py` is Qt-free. It safely extracts the ZIP to a temporary directory, identifies the portable root, reads source/build identity, selects a program-logo asset and copies only logo bytes/metadata into an immutable inspection record. No editor module or About dialog is imported.

`install_wizard.py` is the PyQt6 presentation/controller layer. It uses `QWizard`/`QWizardPage`, with Welcome, Options, Review, Progress and Finish pages. The r5 installer/registry functions remain the filesystem authority.

## Commit boundary

Welcome, Options and Review are inspection-only. The source tree is not copied into My Editors until the Progress page starts after the user has reviewed the plan.

If the destination already exists, the wizard requires explicit acknowledgement of replacement. `import_zip(..., replace_existing=True)` retains its stage/backup/atomic-rename rollback for that source-copy operation.

## Build output

The actual builder is launched through `QProcess` with `RuntimeLauncher.process_environment()`. Its command is always visible. Merged stdout/stderr is retained in a read-only `QPlainTextEdit` behind **Show technical details**. The old standalone BuildDialog is removed.

## Managed install

A selected AppImage build still follows the r4/r5 contract:

1. snapshot pre-existing AppImages;
2. run the detected builder;
3. accept only newly created/changed output;
4. verify version identity where available;
5. atomically copy to the stable Suite-managed AppImage path;
6. install the selected editor icon;
7. write the host Desktop Entry with the absolute AppImage path;
8. commit exact identity/path/checksum fields to `managed_installations` and mirror provenance to the sidecar.

## Branding

Known editor profiles provide a fallback description. Icon discovery gives high priority to filenames identifying the application and to `assets/icons` / hicolor `apps` locations. Documentation screenshots, ribbon icon trees and toolbar assets are penalised. A manifest `icon` remains authoritative.

## Failure semantics

Each filesystem operation remains individually safe/atomic. A later optional AppImage build failure does not erase a portable source copy that has already installed successfully; the progress checklist makes the completed and failed stages explicit. An existing managed AppImage is not replaced unless a new verified artifact reaches the managed-install step.

## Deliberate exclusions

- no editor GUI/About-dialog code execution;
- no standalone `.AppImage` import yet;
- Repair/Uninstall remain on the Details page rather than being converted to wizards in r6;
- no embedded document editor.
