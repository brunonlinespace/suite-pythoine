# Suite Pythoine 0.0.1-r5 — managed installation registry audit

## Purpose

r5 implements the Suite-specific recommendation from the pad-family AppImage audit: individual editor build scripts build artifacts; **Suite Pythoine owns installation, repair and uninstall state**.

The normal managed AppImage lifecycle no longer decides ownership by searching for filenames that resemble an editor name.

## Registry contract

The atomic Suite preference file now contains a `managed_installations` mapping. Each registered editor record contains:

```text
application ID
version
AppImage absolute path
AppImage SHA-256
desktop file absolute path
desktop ID
icon absolute path (or null when no icon is available)
```

The record also retains useful optional provenance such as source version, original build artifact and build script.

The managed registry is the normal source of truth. `<editor-id>.AppImage.suite-pythoine.json` remains beside the AppImage as a recovery/provenance mirror rather than a competing registry.

## Install

After a successful editor build Suite:

1. atomically copies the exact newly built artifact to the stable managed AppImage path;
2. marks it executable;
3. copies the selected icon to the managed editor directory;
4. writes the host `.desktop` file with the AppImage's exact absolute path;
5. records all exact paths, IDs, version and SHA-256 in `managed_installations`;
6. writes the same essential identity into the AppImage sidecar;
7. optionally refreshes the host desktop database.

Managed identity is no longer duplicated in ordinary `editor_overrides`. That area remains for user preferences such as launch mode, formats and an explicitly chosen external launcher.

## Repair

For a registered installation Repair reads the exact AppImage/Desktop Entry/icon paths from the registry. It verifies/recreates the integration using those paths and refreshes the SHA-256/metadata mirror.

A legacy r3/r4 AppImage can be adopted through Repair. r4 installations carrying a Suite-managed sidecar are migrated automatically and conservatively. A filename resemblance alone is not sufficient for automatic adoption.

## Uninstall

Registered uninstall removes only:

- the registered AppImage;
- that AppImage's sidecar;
- the registered icon path, when present;
- the registered Desktop Entry path.

It does **not** scan for or delete similarly named AppImages. An older unregistered installation must first be adopted by Repair. This is deliberate: exact registry ownership is safer than filename heuristics.

Portable source in `My Editors` is never removed by AppImage uninstall.

## Compatibility

The legacy filename scanner remains only for discovery/recovery of pre-registry installs and arbitrary user-configured external launchers. It is not the r5 managed uninstall authority.

r4 sidecars are migrated to full registry records on refresh when:

- the recorded AppImage is inside the configured managed editor directory;
- the sidecar says `managed_by: Suite Pythoine`;
- the sidecar editor ID matches the loaded editor.

After migration, old managed identity fields are removed from `editor_overrides`.

## Validation

The non-GUI release gate verifies:

- all required registry fields;
- registered AppImage selection outranks a misleading similarly named AppImage;
- exact Desktop Entry path and icon validation;
- metadata sidecar mirrors registry identity;
- registered uninstall removes only exact registered paths;
- a similarly named but unregistered AppImage survives uninstall;
- existing builder identity, version mismatch, ZIP safety and rollback checks continue to pass.

A live Fedora desktop remains required for visible PyQt behavior, menu-cache refresh and actual editor AppImage builds.
