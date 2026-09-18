# Python Lair 2 → Suite Pythoine 0.0.1-r2 port audit

## Source inspected

The implementation review used the current `python-lair-2-3.1-asset-build.zip` tree. The 3.1 package is an asset update over the mature Python Lair 2 application architecture, so the review covered the current packaged source rather than relying on the earlier legacy single-file launcher.

The principal Python Lair files inspected were:

| Python Lair 2 area | Approx. lines | Relevance to Suite |
|---|---:|---|
| `services/runtime_paths.py` | 159 | Runtime/portable/AppImage path boundary |
| `services/config_service.py` | 129 | Atomic, typed preferences |
| `services/runtime_launcher.py` | 500 | Host Python and environment sanitisation |
| `services/filesystem_watcher.py` | 226 | Debounced external-change refresh |
| `services/module_scanner.py` | 207 | Bounded/symlink-conscious scanning concepts |
| `widgets/dashboard.py` | 734 | Search, sorting, List/Grid and state patterns |
| `widgets/main_window.py` | 776 | Window/sidebar state and shutdown persistence |
| `controllers/file_actions.py` | 914 | Staging/conflict/data-safety patterns |
| `tools/release_check.py` | 332 | Release-gate structure and safety assertions |

## Ported and adapted

### 1. Runtime-aware writable paths

**Python Lair idea:** source mode may keep its workspace beside the launcher, while AppImage/frozen modes must never write user data into a read-only bundle.

**Suite adaptation:** source mode keeps `my editors/` beside `main.py`. A future Suite AppImage/frozen build defaults to `Documents/Suite Pythoine/My Editors`. `SUITE_PYTHOINE_MY_EDITORS` can explicitly override it. A real unique temporary-file probe confirms that the selected directory is writable.

### 2. Host-safe editor launching

This is the most important port. Suite r1 used `sys.executable` for portable editor `main.py` files and inherited Suite's process environment. That is correct for source mode but unsafe once Suite itself is frozen: `sys.executable` can be the Suite binary, and bundled Qt/Python library variables can break the editor or desktop host applications.

r2 introduces `RuntimeLauncher`:

- portable source uses the exact interpreter that launched Suite, preserving a venv;
- AppImage/frozen mode resolves host `python3`/`python` instead;
- `SUITE_PYTHOINE_PYTHON` can explicitly select a host interpreter;
- detached editors receive a host-safe environment with AppImage/PyInstaller Qt, QML, Python and library variables removed/restored as appropriate;
- the same boundary is used for host folder opening and editor AppImage build processes.

### 3. Atomic preferences and recovery

r1 wrote a fixed `.tmp` file. r2 uses a uniquely named temporary file in the target config directory and atomically replaces the JSON preference file. Invalid/corrupt JSON falls back to defaults instead of blocking startup. The r1 `window.width`, `window.height` and sidebar-width values migrate forward.

### 4. Persistent dashboard/window state

r2 adopts the useful Python Lair dashboard behaviors without its script repository:

- case-insensitive editor search;
- List/Grid dashboard modes;
- title A–Z, title Z–A and recently changed sorting;
- persisted search, sort and view;
- persisted window size/maximized state;
- persisted splitter width/sidebar visibility and last selected editor;
- F11 full screen and a stable Dashboard shortcut.

### 5. Debounced filesystem watching

Manual Refresh remains available, but r2 watches My Editors and the installed-editor directory. Rapid changes are coalesced by a single-shot timer, avoiding repeated immediate rebuilds. Suite intentionally uses a light watcher rather than Python Lair's recursive background scanner because it is discovering editor application roots, not thousands of documents.

### 6. Bounded, symlink-conscious discovery

Icon, packaging and AppImage scans use bounded `os.walk(..., followlinks=False)` traversal and prune generated/irrelevant directories. This applies Python Lair's scanner discipline to Suite's much smaller discovery problem.

### 7. Staged editor replacement with rollback

r1 removed an existing editor directory before copying its replacement. r2 first copies the new editor into a hidden staging directory. Only after staging succeeds does it rename the current editor to a backup and atomically move the staged editor into place. If the final replacement fails, the previous editor is restored. Regression tests inject a failure at that exact point.

### 8. Atomic installed artifacts

AppImages, icons and desktop-entry text are written/copy-staged beside the final target and atomically renamed into place. AppImage execute permission is applied to the staged file before replacement.

### 9. Safer UI text and file creation

Editor/manifest-derived labels are forced to Qt PlainText so an editor name/path cannot become accidental rich text. New-file handoff uses exclusive creation (`xb`) rather than a check-then-create sequence.

### 10. Startup file routing

Suite can now receive existing files as command-line arguments in addition to Open and drag-and-drop. This makes future desktop integration useful: a Suite launcher can hand a file directly to the configured editor without embedding any editor itself.

### 11. Release gate

r2 includes `python -m suite_pythoine.tools.release_check`. It performs source-structure/static safety checks plus non-GUI functional tests for all five built-in editors, generic manifests, extension routing, ZIP traversal/symlink rejection, injected replacement rollback, atomic AppImage installation and r1 preference migration.

## Deliberately not ported

The following Python Lair capabilities were reviewed but rejected as inappropriate for Suite Pythoine r2:

- the embedded Python code editor, syntax highlighting, line numbers, find/replace and dirty-document model;
- recursive Python-module repository/indexing and `.python-lair-ignore` semantics;
- folder mini-dashboards and script move/rename/delete operations;
- script Launch/Terminal/Stop/Force Stop process ownership;
- terminal session wrappers/process-group supervision;
- executable-bit controls for user scripts;
- Python-specific external-editor workflows;
- Python Lair's first-run workspace assistant in its current form.

Those features solve IDE/workspace problems. Suite's architectural rule remains: **Suite Pythoine manages editor applications; the editors manage documents.**

## Additional r1 defects corrected during the port

- Portable editors no longer rely blindly on Suite's own executable when Suite is frozen.
- Editor ZIP replacement is no longer destructive before the replacement is ready.
- AppImage/icon installation no longer writes directly to the final artifact path.
- Recursive asset/build searches are bounded and do not follow symlink directories.
- Manifest-derived labels no longer opt into Qt rich-text interpretation.
- New-file creation no longer uses a race-prone exists-then-write sequence.

## Validation boundary

The release checker and Python compilation can run without PyQt6. A real desktop still must test the GUI itself, `QFileSystemWatcher`, detached editor launch, desktop environment integration, actual editor AppImage builders and behavior on Fedora/Windows. No live GUI pass is claimed from the build container used for this revision.
