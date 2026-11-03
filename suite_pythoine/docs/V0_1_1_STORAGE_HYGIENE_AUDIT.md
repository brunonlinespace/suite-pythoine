# Suite Pythoine 0.1.1 — storage hygiene audit

The 0.1.1 change makes application identity the primary filesystem unit. One user-owned root contains every editor version and both portable/AppImage forms.

## Canonical layout

```text
~/Suite Pythoine Editors/<Application>/<Version>/Portable/
~/Suite Pythoine Editors/<Application>/<Version>/AppImage/
```

AppImage form:

```text
<Application>-<Version>-<Architecture>.AppImage
<Application>-<Version>-<Architecture>.AppImage.suite-pythoine.json
<application-key>-icon.png|svg
```

Host Desktop Entries remain under `~/.local/share/applications` because that is the freedesktop-standard host integration location.

## Compatibility

Old portable/installed config keys are read only as migration inputs. Default migration is opt-in and copy-first. Legacy portable discovery remains available when migration is declined. The 0.1.0 publisher/application-ID confusion is normalized on config load.

## Safety

The release gate verifies nested removal boundaries, exact registered uninstall, versioned naming, migration copy-before-delete behavior, Desktop ID normalization, silent routing and the existing ZIP/build security controls.
