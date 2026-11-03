# Suite Pythoine 0.0.1-r4 — build identity audit

## Trigger

Ricopad 0.3.3-rc3 could be loaded as a portable editor, but Suite Pythoine r3 could fail to offer its real AppImage builder and could subsequently associate the source with an older AppImage already present in the managed installation folder.

## Root cause

r3's builder detector required the path to contain a literal `packaging` directory. That assumption matched Sheepy Pad and Timblee Pad but not the Nuxpad/Ricopad/older-Portapad AppImage lineage.

The inspected Ricopad 0.3.3-rc3 tree uses:

```text
Ricopad-0.3.3-rc3-source-tree/
├── main.py
└── ricopad/
    ├── appimage/
    │   └── build-fedora-appimage.sh
    └── dist/
```

Its builder declares:

```text
APP_VERSION="0.3.3-rc3"
```

and creates:

```text
ricopad/dist/Ricopad-0.3.3-rc3-<arch>.AppImage
```

The r3 post-build search was also too broad: it selected the best-looking AppImage anywhere under the editor tree. If no fresh build had actually been identified, an older `dist/` artifact could be mistaken for the result.

## r4 correction

### Builder discovery

Builder discovery now scores real build scripts and supports both known layouts:

```text
*/packaging/fedora/build-appimage.sh
*/appimage/build-fedora-appimage.sh
```

`test-appimage.sh` and installer helpers are not treated as builders. Future/custom scripts can be recognised only when their name/location plus AppImage-building content provides sufficient evidence.

### Build-bound artifact selection

Before launching a builder, Suite records each existing AppImage's path, size and nanosecond modification time. After a successful builder exit it considers only AppImages whose signature is new or changed.

Selection then prefers:

1. the source/build version;
2. the `dist/` directory implied by the selected builder layout;
3. final `dist`/`output` locations;
4. the newest changed artifact.

If nothing changed, Suite reports **New build output not found** and deliberately ignores all old AppImages.

### Version gate

Suite detects a portable/source version without executing the editor. Packaging `APP_VERSION`, manifest `version`, and canonical Python version assignments are supported.

The newly built AppImage version is taken from its filename where possible and otherwise from the builder's `APP_VERSION`. If source/build and artifact versions conflict, Suite refuses installation and leaves the existing managed AppImage untouched.

### Managed identity

A successful Suite build/install now writes:

```text
~/Suite Pythoine Editors/<editor-id>.AppImage
~/Suite Pythoine Editors/<editor-id>.AppImage.suite-pythoine.json
```

The sidecar records the version, SHA-256, original build artifact and builder path. The user preference record also keeps the installed version and source version used for that build.

### Launch safety

When both portable and installed variants exist:

- matching versions: Automatic may prefer installed;
- mismatched versions: Automatic uses portable;
- known portable version + unverified installed version: Automatic uses portable;
- explicit Installed mode remains available, but loading a conflicting source prompts the user to switch to Portable.

This means a legacy r3 stable AppImage with no version metadata is no longer silently preferred over a source tree whose version can be identified.

## Scope deliberately not changed

r4 does not yet add direct `.AppImage` import. That is intentionally deferred until build identity and managed-version semantics are trustworthy. The existing source-ZIP workflow, r3 desktop repair/uninstall, and no-embedded-editor boundary remain intact.
