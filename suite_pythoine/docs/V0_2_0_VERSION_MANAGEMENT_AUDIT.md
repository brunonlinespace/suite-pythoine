# Suite Pythoine 0.2.0 — intelligent version-management audit

## Purpose

0.2.0 completes the multi-version model introduced by the unified Editors-folder layout. Retaining a version now means retaining a version that Suite can see, launch and manage; an older directory is no longer merely filesystem clutter hidden behind the newest application card.

## Application and version model

The Dashboard and sidebar keep one logical entry per application. Each entry contains a version inventory sourced from the canonical filesystem and the managed registry:

```text
<Application>/
├── <Version A>/
│   ├── Portable/
│   └── AppImage/
└── <Version B>/
    ├── Portable/
    └── AppImage/
```

`EditorEntry.versions` exposes every retained version. One `active_version` is the normal Suite launch target. One `desktop_version` identifies the AppImage used by the host Desktop Entry. These values may differ when the active version has only a portable source.

The sidebar indicates when an application has multiple versions. Details lists every version and whether Portable, AppImage and desktop integration are present.

## Managed registry schema 2

`managed_installations` is version-aware. Each application group contains `active_version`, `desktop_version`, and a `versions` mapping. Older 0.1.x flattened records are promoted lazily on read.

Only one version may be marked `desktop_integrated`. Switching the active AppImage rewrites the single host Desktop Entry rather than creating one launcher per retained release.

The canonical versioned filesystem is also inventoried. This recovers AppImages retained by 0.1.x even when the older single-version registry had forgotten them. Such artifacts are shown as **Unregistered**, remain directly launchable through Suite, and can be deliberately adopted through **Make Active**.

## Details actions

Each retained version exposes appropriate controls:

- **Launch Portable**
- **Launch AppImage**
- **Make Active**
- **Remove Version…**
- **Open Version Folder**

The active version cannot be removed until another version is made active. The desktop-integrated version cannot be removed until desktop ownership is moved or removed safely.

## Install, update, downgrade and reinstall

The installation wizard classifies an incoming archive against the versions already present.

- First version: **Install**.
- Same version: **Reinstall/repair**.
- Newer version: **Upgrade**. Default is **Upgrade and remove older managed versions after the new version is verified**; **Install alongside older versions** is available.
- Older version: **Downgrade**. Default is **Install alongside current version**; destructive replacement of newer managed versions is an explicit alternative.

Cleanup happens only after the incoming source/AppImage and registry state have succeeded. Alongside installations remain visible and launchable.

## Protected Suite self-update

Suite Pythoine's own update pathway is locked to a verified archive identifying all of:

- application key `suite-pythoine`;
- publisher `brunonlinespace`;
- application name `Suite Pythoine`.

When an update policy would remove the Suite version currently executing the wizard, deletion is deferred. The newly installed target version must start from its own managed Portable/AppImage directory before `self_update.py` removes the superseded running version. This avoids deleting the code that is performing the update and gives the new version a startup proof point.

A 0.1.2 process cannot retroactively acquire the 0.2.0 wizard semantics while it is already running. If 0.1.2 installs 0.2.0, the first 0.2.0 launch inventories any retained 0.1.x version and exposes it in Details; subsequent 0.2.x self-updates use the protected workflow.

## Runtime identity in About

About describes the copy that is actually running, not merely the active managed version:

- `Version 0.2.0 [AppImage]`
- `Version 0.2.0 [Portable]`

A frozen non-AppImage fallback is labelled `[Frozen]`.

## Purge

**Purge Editor…** reviews and removes all retained managed versions of the selected application, including every portable source and registered AppImage integration. Canonical unregistered versioned AppImages are also shown/removed only within the exact editor/version hierarchy after the destructive review.
