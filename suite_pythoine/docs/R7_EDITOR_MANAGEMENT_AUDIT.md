# Suite Pythoine 0.0.1-r7 — editor-management and pad-family UI audit

## Scope

r7 aligns Suite Pythoine's application chrome and editor-management Details page with the recent brunonlinespace pad family while preserving the managed-AppImage ownership model introduced in r5 and the guided installer introduced in r6.

## Menu contract

Tools:

```text
Open My Editors Folder
Open Installed Editors Folder
-----------------------
Preferences…
```

Help:

```text
Documentation
-----------------------
GitHub
Report an Issue
-----------------------
About Suite Pythoine
```

Documentation is bound to F1. Repository links are:

```text
https://github.com/brunonlinespace/suite-pythoine
https://github.com/brunonlinespace/suite-pythoine/issues
```

## Pad-family title and About contract

Suite-owned windows use:

```text
Window — Suite Pythoine
```

`ui_titles.app_dialog_title()` removes a trailing application name before adding the canonical suffix, preventing duplicate titles such as `About Suite Pythoine — Suite Pythoine`.

The modeless About dialog follows the recent pad-family visual structure: centered 112 px application mark, application name, version, bold slogan, centered description, project/preferences/licence details and OK. Suite Pythoine's slogan is:

```text
Friendly. Fast. Focused.
```

## Details page contract

Each editor Details page presents:

```text
File
  Launch | New File… | Open File…

Settings
  Editor Preferences… | Purge Editor…

Portable Editor
  Remove Portable Folder | Open Portable Folder

Installed Editor
  Repair AppImage Integration | Uninstall AppImage | Open Installed Folder
```

Unavailable operations remain visibly disabled rather than disappearing unexpectedly.

## Portable removal

`Remove Portable Folder` is deliberately narrower than Purge:

1. validate that the target is a direct ordinary child of the configured My Editors folder;
2. refuse symbolic links and out-of-root paths;
3. atomically rename the folder to a hidden staging path;
4. recursively remove the staged folder;
5. restore the original folder if deletion fails.

A registered AppImage, Desktop Entry, managed icon and registry record are not touched.

## Installed-only Dashboard entries

The managed registry is now sufficient to reconstruct an editor when no portable source exists. An installed-only entry retains:

- application/editor ID;
- display name;
- installed version;
- managed AppImage command;
- registered icon where valid;
- supported extensions;
- description.

Built-in profiles provide compatibility fallbacks for old records. New/updated registry records persist extensions and description explicitly. This means file routing and Dashboard management remain available after intentional portable-source removal.

## Purge Editor wizard

Purge is broader and intentionally guided. It reviews exact paths first, then requires a destructive-operation checkbox before the Purge commit button is enabled.

The transaction stages:

- the direct portable editor folder, if present;
- the exact registered AppImage;
- AppImage provenance sidecar;
- exact registered managed icon;
- exact registered host Desktop Entry.

Only after staging succeeds does Suite remove the editor's managed-installation record, editor override, extension preferences pointing at that editor, and last-selected state. Physical cleanup follows the configuration commit.

If staging or configuration commit fails, staged data is restored. If physical deletion fails after the registry commit, Suite keeps the editor logically purged rather than resurrecting stale registry ownership for files that may already have been partially deleted; any surviving purge staging remains hidden/unregistered for manual cleanup.

A legacy/unregistered installed launcher cannot be purged by filename resemblance. Repair must first adopt its exact paths into the managed registry.

## Preserved boundary

Suite Pythoine continues to manage editor applications only. It contains no embedded document/code editor and does not execute another editor's GUI/About code for branding.
