# Suite Pythoine 0.0.1-r3 — maintenance audit

## Scope

r3 is a focused maintenance/integration revision of r2. It keeps Suite Pythoine as a launcher/router/installer with **no embedded editor**.

The revision responds to four observed issues:

1. AppImage desktop integration needed a repair/uninstall lifecycle.
2. Existing r2 `.desktop` generation could make desktop discovery unreliable.
3. Dashboard sorting did not reliably reorder visible editor cards.
4. Search could leave stale/overlapping cards in the dashboard.

It also promotes the approved Pythoine/caffeine artwork as the application identity: a dark notebook with a friendly python drinking coffee.

## AppImage integration changes

### Stable managed AppImage path

When r3 builds an editor AppImage itself, the resulting artifact is installed under the configured **Installed Editors folder** with a stable per-editor name:

```text
<Installed Editors>/<editor-id>.AppImage
```

Examples:

```text
~/Suite Pythoine Editors/ricopad.AppImage
~/Suite Pythoine Editors/sheepy-pad.AppImage
```

This prevents the `.desktop` file from becoming stale merely because the upstream editor's build artifact changes versioned filename.

r3 remains compatible with r2/versioned AppImages already present in the same managed folder and can repair their integration in place.

### Desktop Entry correction

r2 adapted editor desktop templates but wrote `TryExec=` and `Icon=` using the same quoting helper as `Exec=`. `Exec=` is a command field and supports command quoting; `TryExec=` and `Icon=` are ordinary Desktop Entry string values. Quoting an absolute path there can make some desktop shells treat the value as invalid, especially when `TryExec` is used to decide whether an application should be shown.

r3 therefore:

- removes `TryExec` from Suite-managed desktop entries;
- writes `Exec="/absolute/path/to/editor.AppImage" %F`;
- writes `Icon=/absolute/path/to/icon.png` without shell-style quotes;
- removes source-template `OnlyShowIn` / `NotShowIn` restrictions, forces `NoDisplay=false` / `Hidden=false`, and disables `DBusActivatable` so the AppImage `Exec` path is authoritative;
- marks managed entries with `X-Suite-Pythoine-Managed=true`;
- records the AppImage with `X-Suite-Pythoine-AppImage=...`;
- rewrites only the main `[Desktop Entry]` group and leaves `Desktop Action` command groups untouched;
- writes to the standard per-user directory `~/.local/share/applications`;
- requests `update-desktop-database` when that host utility is available.

### Repair

Each editor detail page on Linux now shows the managed AppImage path and desktop-integration state.

**Repair AppImage Integration**:

- locates the actual managed AppImage;
- restores executable permission;
- reuses or installs the editor icon;
- regenerates the `.desktop` file with the actual absolute AppImage path;
- updates the saved installed-path override;
- refreshes the desktop database when possible.

This works when the AppImage exists but the desktop entry is missing or stale.

### Uninstall

**Uninstall AppImage…** removes only Suite-managed installed artifacts:

- the current managed AppImage;
- older matching AppImage artifacts left in the configured Installed Editors folder;
- the Suite-managed icon copy;
- `~/.local/share/applications/suite-pythoine-<editor-id>.desktop`.

The portable editor under `My Editors` is deliberately preserved. If the editor was forced to `installed` launch mode, r3 changes it back to portable when a portable copy exists.

Safety checks refuse to unlink AppImages/icons outside the configured Installed Editors directory.

## Dashboard fix

r2 kept card widgets alive and repeatedly detached/re-added their layout items while a delayed search timer and sorting could both request a relayout. On the observed UI this could leave multiple editor cards sharing the same geometry, producing the overlapping titles/formats visible in the bug screenshot. The same widget-reuse path made sorting appear ineffective.

r3 replaces that mechanism with:

- a pure `dashboard_model.filter_and_sort_editors()` model;
- deterministic A–Z, Z–A and Recently Changed sorting;
- immediate tokenized search rather than a delayed timer;
- complete replacement of the list/grid scroll-body widgets after each filter/sort operation;
- hidden/deferred deletion of the old body before it can overlap the new one;
- a minimum list-card height;
- a clear button in the search field.

Search terms are ANDed, so `pad html` matches Timblee Pad while `.sh` matches Sheepy Pad.

## Branding

The approved dark-notebook / coffee-drinking-python logo is stored as the canonical transparent 1024×1024 PNG and regenerated at 16, 24, 32, 48, 64, 128, 256 and 512 px.

The icon is used for:

- the QApplication/window icon;
- the dashboard heading;
- the About dialog.

## Automated validation

The r3 non-GUI release checker covers:

- all five built-in editor profiles and future manifest-based editors;
- document routing;
- A–Z/Z–A/Recently Changed dashboard sorting;
- multi-term and format search;
- ZIP path traversal and symlink rejection;
- staged editor replacement rollback;
- stable AppImage installation and executable bit;
- Desktop Entry Exec/Icon/TryExec rules;
- missing/stale desktop detection and repair;
- current + legacy managed AppImage discovery;
- AppImage/icon/desktop uninstall;
- preference migration/corruption recovery;
- icon-family dimensions/alpha PNG format;
- source-manifest hashes;
- Python syntax and basic dangerous-primitive scans.

A real Fedora desktop remains required for live PyQt rendering, application-menu refresh behavior and actual editor AppImage launching.
