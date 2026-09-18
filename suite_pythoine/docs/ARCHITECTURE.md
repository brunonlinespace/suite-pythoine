# Suite Pythoine 0.3.3 architecture

## Component model

Suite Pythoine is a **Hub**. Managed applications are classified by trusted catalogue data as **Editor**, **Reader**, or **Extension**.

- Hub: receives OS file associations and manages components; never an internal document candidate.
- Editor: routable/open-capable and may create new documents.
- Reader: routable/open-capable but never creates new documents.
- Extension: managed and launchable, but never participates in File Routing and has no routed file formats.

The trusted catalogue carries explicit `routing`, `open`, and `create` capabilities. Component kind describes what an application is; capability policy determines what Suite may do with it.

## UI projection

The Dashboard/sidebar render the discovered non-Hub inventory in three groups: **Editors**, **Readers**, and **Extensions**. Editors expose New/Open/Details: New launches the selected Editor with no path and the Editor exclusively owns its native untitled document. Readers expose Launch/Open/Details but no New action. Extensions retain Launch/Details and do not inherit document actions. Suite's own Details remain a Hub-specific management surface and append the installed-application inventory rather than replacing Hub management controls.

The global Suite Preferences and Hub-card Preferences entry point resolve to one `GeneralPreferencesDialog`; other components continue to use their own component-specific preference action. The Hub dialog projects the same management state across General, File Routing, Runtime, Versions, and Information tabs while calling the existing SuiteWindow management methods rather than maintaining a second management backend.

## Fast routing boundary

Document launch remains pre-GUI and dependency-light:

1. Read local configuration/routing index.
2. Filter to available components with both `routing` and `open` capabilities.
3. Route silently when one application or a remembered application resolves the file.
4. Lazily load only the compact **Choose Application** chooser for genuine ambiguity.
5. Construct the full Hub only for unresolved/recovery cases.

Editors and Readers may enter step 2. Extensions and the Hub never do. The routing cache preserves capabilities and is invalidated by trusted catalogue fingerprint changes.

## OS MIME/extension union

Suite's default extension and MIME unions are derived from all routable profiles rather than Editors alone. Therefore PDF/EPUB associations remain present after Portapad and Kapitulindo move to Reader.

## Runtime and storage

The active Suite runtime owns the single managed desktop entry directly. Portable-active Suite versions point the desktop entry at that exact Portable launcher; AppImage-active versions point it at that exact AppImage. Historical runtimes are therefore not used as current routing bootstraps.

Canonical storage remains `~/Suite Pythoine/<Component>/<Version>/{Portable,AppImage}/`.

## Store Pythoine boundary

Store Pythoine is an optional, non-routing Extension and an independently launchable on-demand application. Suite contains no remote catalogue browser or background Store process. A small dependency-light control bridge resolves Suite's currently active runtime from Suite's own desktop integration, so Store does not need to know whether Suite is Portable or AppImage. Read-only inventory/package-inspection commands remain headless; install/update requests launch the same full Suite installation wizard used by manual installation. Store never writes Suite's registry, routing index, desktop integration or component configuration directly.
