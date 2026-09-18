# Suite Pythoine 0.3.3-r4 — hidden view toggle, direct fuzzy keymap search, View-menu polish

Application version remains **0.3.3**. This surgical source revision builds directly on 0.3.3-r3 and changes only the clarified Dashboard view shortcut, Keyboard Shortcuts search parity, and requested View-menu ordering.

- Restores **Ctrl+Alt+Shift+D** as the keyboard-only **Toggle List/Grid View** shortcut. It is deliberately **not exposed as a View-menu entry or Dashboard button**; the visible Dashboard Settings submenu continues to use the explicit **List View** / **Grid View** radio choices.
- Makes that keyboard-only view toggle explicit in **Preferences → General → Dashboard** and in the Keyboard Shortcuts reference.
- Ports Marko Plus 0.0.2's Keyboard Shortcuts search implementation directly, preserving its command substring matching and shortcut-token matching semantics (`control` / `ctrl` / `ctl`, optional plus signs, and reordered modifiers). Suite-specific window branding is the only implementation-level adaptation.
- Reorders **View** so **Refresh Components** is the first entry, followed by a separator, then **Dashboard** and **Dashboard Settings** together. The existing separator after Dashboard Settings remains before the other View controls.

No Dashboard layout, routing, component catalogue, installer, Installed Applications behavior, or unrelated shortcut changes are included.

# Suite Pythoine 0.3.3-r3 — Dashboard Settings and inventory sizing polish

Application version remains **0.3.3**. This surgical source revision builds directly on 0.3.3-r2 and changes only the requested Installed Applications sizing/actions, Preferences shortcut labels, and Dashboard view/settings placement.

- The dedicated **Installed Applications** table now expands vertically to consume the available page space instead of retaining the former fixed 360 px height. Existing sorting, movable/resizable headers, column visibility persistence, App Page actions, and runtime-specific removal behavior are unchanged.
- Restores **Install Component…** to the Installed Applications heading row beside **Refresh Inventory**, using the established Suite installer flow.
- Removes the standalone **Toggle List/Grid View** action, its `Ctrl+Alt+Shift+D` shortcut, and the Dashboard's List/Grid toggle button.
- Reorganizes the **View** menu so **Dashboard**, **Refresh Components**, and the new **Dashboard Settings** submenu are consecutive with no separators between them. **Dashboard Settings** contains exclusive **List View** / **Grid View** choices, one separator, then **Show Dashboard Icons** and **Show Drop Bar**.
- Makes shortcuts explicit beside shortcut-bearing controls in **Preferences → General**: Open Components Folder (`Ctrl+Shift+O`), Show application icons on Dashboard (`Ctrl+Alt+Shift+I`), Show Drop Bar (`Ctrl+Alt+Shift+B`), and Developer Intake Mode (`F12`).

No component catalogue, routing, installer behavior, Installed Applications data model, Dashboard card behavior, or unrelated shortcut changes are included.

# Suite Pythoine 0.3.3-r2 — launch/navigation and Installed Applications split

Application version remains **0.3.3**. This surgical source revision builds directly on 0.3.3-r1 and changes only the requested navigation, global launch, and Suite-page organization.

- Adds browser-style **mouse Back button** navigation when the pointing device/Qt platform reports `BackButton`, using the same Suite navigation history as the existing Backspace behavior.
- Adds global **Launch…** to the **File** menu on **F4** and to the Dashboard immediately before **New File…**. The dialog deliberately parallels the existing New File chooser, lists available installed non-Hub components, and launches the selected component's active runtime without changing file-routing ownership or restoring redundant per-Editor Launch buttons.
- Splits Suite Pythoine's management UI into two separate pages: **Details** keeps the existing Suite details/management surface, while **Installed Applications** receives the complete existing installed-runtime inventory unchanged in behavior (summary, sortable/movable/resizable columns, column visibility persistence, App Page actions, runtime-specific removal, and Refresh Inventory).
- Adds the Dashboard **Installed Applications** button exactly between **Install Component…** and **Details**. The new page participates in Suite navigation history and survives component refreshes as the current page.

No component classification, routing, New File ownership, install/update mechanics, version management, Developer Intake, Store bridge, Dashboard card behavior, or unrelated shortcuts are changed.

# Suite Pythoine 0.3.3-r1 — dashboard/keymap and extension identity polish

Application version remains **0.3.3**. This surgical source revision changes only the requested Dashboard shortcuts/search polish, shortcut reference, installation wording, and trusted Extension identities.

- Renames the trusted Linux inspection Extension from **Linspector Suite / `linspector-suite`** to **Linspectacles / `linspectacles`**, retaining the old Linspector spellings only as recognition aliases. Catalogue revision advances to **9**.
- Registers **Marko Plus** and **Rico Plus** as trusted **Extensions** with no routing/open/create capabilities and no document extensions, so they cannot compete with the normal Pad Editors/Readers for OS document routing.
- Dashboard/navigation shortcuts are now **Ctrl+W Dashboard**, **F5 Refresh Components**, **F9 Show Sidebar**, **Ctrl+Alt+Shift+D Toggle List/Grid View**, **Ctrl+Alt+Shift+I Show Dashboard Icons**, **Ctrl+Alt+Shift+B Show Drop Bar**, **Ctrl+F Focus Dashboard Search**, and **Ctrl+/ Preferences**. Existing special drop overrides and other unrelated shortcuts are retained.
- Adds **Keyboard Shortcuts** on **Ctrl+Shift+/** using the Marko Plus searchable/filterable table implementation, including command substring matching plus shortcut token aliases (`control`/`ctrl`/`ctl`), optional plus signs, and reordered modifier matching.
- Typing a printable non-whitespace character while the Dashboard owns the active Suite window now focuses the Dashboard search field and inserts that character, even when the search field was not previously focused.
- Relabels the Dashboard/Tools installation action and live package picker from **Install Editor…** to **Install Component…**.

No document ownership, existing-file routing, installer mechanics, Developer Intake, Store bridge, runtime/version management, or component-card behavior is otherwise changed.

# Suite Pythoine 0.3.3

0.3.3 is the first unsuffixed release after the 0.3.2-exp9 review line. It is based directly on canonical 0.3.2-exp9-r4 and intentionally limits changes to the agreed next-version work.

- **Store Pythoine decoupling:** removes Suite's built-in online Store browser/network implementation. Store Pythoine is now an optional, independently launchable, non-routing Extension. **Get More…** launches it when installed; otherwise Suite offers the existing local **Install Extension…** path.
- **Trusted Store bridge:** adds a small short-lived Store-facing protocol for managed-inventory queries, package inspection and Store-requested installs. Store never writes Suite's registry/routing/config directly. The bridge follows Suite's active Portable/AppImage runtime without reviving the historical retained-AppImage bootstrap model.
- **Full wizard remains authoritative:** Store-requested ZIP/AppImage installs always use Suite's complete existing installation wizard. Developer Intake does not intercept Store transactions. There is no background Store/Suite daemon.
- **Catalogue cleanup:** removes the nonexistent PSTS Pad typo identity; JSTS Pad remains. Store Pythoine is added as a trusted non-routing Extension. Catalogue revision is **8**.
- **Timblee routing held constant:** Timblee Pad remains `.html`, `.htm`, `.css` only; `.svg` is explicitly excluded.
- **Editor action cleanup:** removes the redundant generic **Launch** action from Editor Dashboard/Details surfaces and keeps **New… / New File…** as the intentional entry into each Editor's own untitled-document workflow. Reader/Extension Launch actions, existing-file Open behavior, routing, and per-version Launch Portable/AppImage actions are unchanged.

All canonical r4 document-creation ownership, routing, Developer Intake, Beespector fallback, active-runtime desktop ownership, gitten migration, icon-selection, navigation and version-management behavior is retained unless explicitly listed above.

# Suite Pythoine 0.3.2-exp9-r4 — editor-owned New documents

Application version remains **0.3.2-exp9**. This surgical source revision changes only the shared Editor **New File…** handoff.

- Dashboard, File-menu, component-card and component-details New actions now launch the selected create-capable Editor without a filepath. The Editor exclusively owns its native clean Untitled document and later Save/Save As workflow.
- Suite no longer asks for a destination, creates directories, creates a zero-byte placeholder, or opens an existing file from the New pathway.
- Launch, Open File, per-component Open, OS/startup routing, drag-and-drop, URL routing, installation and component-management pathways are unchanged.

# Suite Pythoine 0.3.2-exp9-r3 — inspection fallback and icon-quality review

Application version remains **0.3.2-exp9**. This review supersedes exp9-r2 and preserves r2 active-runtime desktop ownership, validated routing, Developer Intake, special drop overrides, component identities/families and management behavior unless explicitly listed below.

- Adds a strict **unsupported-file inspection fallback** for files explicitly opened with Suite Pythoine. The existing validated Editor/Reader routing candidate calculation runs first and is unchanged. Only when it returns **zero installed eligible candidates** may Suite consider Beespector/Beespector Lite; both remain `routing=false`, gain no MIME associations, and never appear in the normal routing candidate chooser.
- If both inspection Readers are available, Suite uses a compact chooser with **Remember my inspection fallback choice**. The remembered preference is exposed/resettable under **Preferences → File Routing** as Ask every time / Beespector / Beespector Lite. If the remembered inspector disappears, Suite uses the sole remaining inspector or asks again when appropriate. If neither inspector is installed, the normal no-handler/full-Hub path remains.
- The same post-routing fallback works on the dependency-light startup/file-association path and on the full Hub **Open File** path; normal routes and launch-failure recovery are not converted into inspection fallbacks. `--diagnose-routing` reports the fallback decision separately.
- Improves source-ZIP application-icon selection. An explicit manifest icon remains authoritative (including nested package-relative layouts); otherwise the inspector now considers canonical/master naming plus PNG/ICO dimensions and SVG vector quality so a tiny raster derivative does not beat a better application logo merely because its basename is exact.
- Portable-source icon discovery uses the same quality-aware principles so a good source icon can also be carried into managed AppImage/desktop integration. The install wizard records and displays **Wizard icon source** for QA/debugging.
- QA adds zero-candidate boundary tests proving Beespector cannot override a valid routed application, remembered/unavailable/no-inspector fallback cases, and synthetic low-resolution-vs-master/manifest icon-selection fixtures.

# Suite Pythoine 0.3.2-exp9-r2 — active-runtime desktop ownership and identity review

Application version remains **0.3.2-exp9**. This review supersedes exp9-r1 while preserving exp9's routing, Developer Intake, Drop Bar, Store, runtime inventory and management behavior unless explicitly listed below.

- **Suite desktop integration now follows the active runtime directly.** Making/repairing an active Suite version writes the single managed desktop entry to that exact Portable launcher or AppImage, preserving the same catalogue-derived MIME union and `%F` document forwarding. A retained older AppImage is no longer the intended behavioral bootstrap for a newer Portable-active Hub.
- On first r2 GUI startup, Suite quietly checks that its managed desktop entry actually matches the active Suite version/runtime and repairs the legacy retained-AppImage bootstrap state only when needed.
- New Suite AppImages no longer auto-redirect through the global Portable preference on ordinary startup. Explicit **Launch AppImage** therefore remains an exact-version/runtime launch; the legacy bootstrap helper is compatibility-only and requires an explicit opt-in environment marker.
- Changing Suite **Launch runtime** re-synchronizes the desktop entry to the active version's selected runtime. Source/AppImage install paths that make Suite active likewise repair the direct desktop target. Normal OS file routing, Developer Intake ZIP diversion, and the Ctrl+Shift+B/Y/C drop overrides remain separate and unchanged.
- Adds browser-style **Backspace** navigation between Suite Dashboard/Details/Store/component surfaces when the key reaches the main window; editable controls keep their ordinary Backspace behavior.
- Migrates the trusted component identity from **Gitten Pad / `gitten-pad`** to canonical lowercase **`gitten`**. Legacy aliases remain recognition/migration hints. Existing overrides, managed records, remembered routes/selection and Developer Intake roots migrate to `gitten`; legacy desktop IDs/paths are canonicalized for repair.
- Reclassifies **Beespector** and **Beespector Lite** from Extensions to **Readers**. They remain inspection/open-capable, create no documents, and deliberately retain **no normal OS/document-routing formats**; Ctrl+Shift+B remains the explicit dropped-file override. Reader-family management semantics such as **Purge Reader…** now apply.
- Developer Intake adds a simple **Paste** button beside the Markdown release-note field so clipboard content (for example release notes copied from ChatGPT) can be inserted directly before **Action** creates the README. No success popup is added.
- Trusted bundled catalogue revision advances to **7**.
- QA now covers direct Portable/AppImage desktop ownership transitions, unchanged MIME/file forwarding, exact AppImage launch architecture, canonical gitten ZIP recognition/migration, Beespector no-routing Reader semantics, Backspace/Paste wiring, and preservation of the special drop overrides.

# Suite Pythoine 0.3.2-exp9-r1 — nested Pad identity hotfix

Application version remains **0.3.2-exp9**. This source hotfix changes only post-import component identity verification and its QA coverage.

- recognises trusted Pad-family manifests stored inside the immediate application package, including `python_lair2/python-lair.json` and `sheepy_pad/sheepy-pad.json`;
- preserves root-level `suite-pythoine-component.json`, `suite-pythoine.json` and `editor.json` compatibility;
- nested manifests remain identity hints only: Suite's trusted component catalogue still decides component kind, capabilities and routing;
- changes the checklist wording to **Verify component identity**;
- catches identity failures at the identity step instead of allowing an uncaught `UnknownComponentError` or mislabelling them as AppImage preparation failures;
- adds executable regression fixtures for Python Lair and Sheepy Pad two-item portable trees.

# Suite Pythoine 0.3.2-exp9

## Experimental Reader/capability branch

## exp9 Developer shortcuts, Drop Bar and runtime-aware management

- Developer Intake remains off by default, persists independently, and can now be toggled with **F12** or controlled without PyQt via `--enable-developer-mode`, `--disable-developer-mode`, and `--developer-mode-status`. The Store default is likewise persistently disabled until explicitly enabled.
- Adds a persistent Dashboard **Drop Bar** (visible by default) that reuses Suite routing/intake handlers for files and URLs. URL capability metadata is catalogue-driven: Youlindo advertises YouTube hosts, Crawlindo advertises general HTTP/HTTPS fallback, and ambiguous matches use an inline Drop Bar chooser rather than a modal prompt.
- Adds drop overrides **Ctrl+Shift+B** → Beespector file inspection, **Ctrl+Shift+Y** → Youlindo URL intake, and **Ctrl+Shift+C** → Crawlindo URL intake without changing OS routing.
- Dashboard application icons can be hidden persistently, and list/grid scroll areas use Qt touch scrolling for one-finger panning. Sidebar keyboard/current-item navigation now changes the displayed component card as the selection moves.
- Installed Applications removal is runtime-specific: Portable rows expose **Remove Portable…** and AppImage rows expose **Uninstall AppImage…**. Whole-version removal remains on version-management cards. The Active column now reflects the selected runtime, not merely the active version.
- Component Details expose trusted **Open Config Folder** metadata before Preferences where known, and Extension cards restore **Purge Extension…** parity with Editors/Readers.
- Trusted catalogue revision is **6** to carry config-folder and URL-capability metadata; file/MIME routing capabilities are otherwise unchanged.

## exp8 per-runtime inventory rows and bounded sidebar

- Details → Installed Applications now uses one row per runtime. A version that has both Portable and AppImage is represented by two rows rather than a combined `Portable + AppImage` row.
- The **Installed as** column is renamed **Runtime**. Existing exp7 persisted table layout is migrated by label so widths, order and visibility survive the rename.
- Size, install timestamp, location, desktop state and managed state are calculated per runtime row instead of being combined at version level.
- The inventory summary now reports runtime installations rather than calling the row count a version count.
- The main Components sidebar keeps its established 250 px width as a hard upper bound, so long/new component names cannot make it expand automatically. The horizontal splitter remains collapsible and users may still drag the sidebar narrower or fully closed. Previously saved narrower/collapsed splitter widths are retained; oversized historic widths are clamped to 250 px.
- No Developer Intake, normal install, Store/self-update, AppImage management, component catalogue, Preferences management, or OS file-routing behaviour changes from exp7.

## exp7 Installed Applications table layout controls

- Keeps the restored exp6 Suite management Details page and Developer Intake baseline unchanged.
- The Details → Installed Applications table no longer grows vertically as more installed versions are discovered; it keeps the established 360 px inventory height and scrolls internally.
- Column widths are user-resizable and persist across launches.
- Column order is user-defined by dragging header sections and persists across launches.
- Right-clicking any Installed Applications header opens a checkmarked column-visibility menu; hidden/visible choices persist across launches.
- The Developer Intake Configuration dialog explicitly opens at its established 780×600 default/minimum size, so adding more catalogue entries is absorbed by the existing App Roots scroll area instead of making the dialog progressively larger.
- No install, routing, Store/self-update, Developer Intake trust-boundary, catalogue, or AppImage behaviour changes from exp6.

## exp6 Suite management restoration and Preferences management tabs

- Restores the full pre-exp5 Suite Pythoine management Details surface: complete Hub information, retained-version cards, Preferences/Open Components Folder, Portable folder access, and Desktop Integration repair/open-folder actions.
- Keeps the exp5 Windows-style Installed Applications inventory and appends it below the restored Suite management surface instead of replacing it.
- Reorganises Suite Preferences into five tabs: **General**, **File Routing**, **Runtime**, **Versions**, and **Information**.
- General owns the Components folder, **Open Components Folder**, and the persistent Developer Intake controls; Launch runtime is intentionally moved out of General.
- Runtime owns **Launch runtime**, Portable **Open Portable Folder**, and Installed **Repair Desktop Integration** / **Open Installed Folder** actions.
- Versions mirrors Suite's retained-version controls with **Launch Portable**, **Launch AppImage**, **Make Active**, **Remove Version…**, and **Open Version Folder** per version.
- Information mirrors the complete Suite status text from **Type** through **Desktop integration**.
- No Developer Intake, Store/self-update, normal install, component-catalogue, or OS file-routing behaviour is changed from exp5. Bundled catalogue revision remains **5** because this is a management-UI correction, not a catalogue change.

## exp5 Developer Intake and installed-app inventory

- Adds persistent **Developer Intake Mode** under Suite Preferences. Its enabled state and all intake settings live in a separate `developer-intake.json`, not in Suite's normal preferences.
- When Developer Intake is active, manually opened/dropped source ZIPs are diverted before the guided production installer. Store downloads, protected Suite self-update, AppImage adoption, component/version management and OS document routing remain on their existing paths.
- Developer Intake preserves the proven Dev Drop workflow: per-app development roots, configurable `1 Source` / `2 Release Notes` relative paths, ZIP-named extraction isolation on by default, optional post-success ZIP deletion off by default, Markdown `README.md`, Clear / Reset and Open Extracted Folder.
- Adds a separate `developer-components.json` for optional `local:` Developer Intake identities. Local entries cannot override trusted IDs/aliases and never participate in normal install, Store, routing or desktop integration.
- Developer Mode is persistent and visibly marked in the window title, sidebar and status bar while active.
- Suite **Details** now contains a sortable Installed Apps-style inventory of every recognised brunonlinespace version present as Portable/AppImage, including the running Suite itself, with Active/Desktop state, size, install timestamp, managed state, location, App Page and protected Remove actions.
- Adds JSTS Pad as a routed Editor for `.js`, `.mjs`, `.cjs`, `.ts`, `.mts`, `.cts`, `.jsx` and `.tsx`. Adds Beespector, Beespector Lite and Linspector Suite as non-routing Extensions. Sbookypad remains an acknowledged Extension.
- Trusted bundled catalogue revision is now **5**.

0.3.2-exp9 extends the 0.3.2 experimental component-family work while retaining the exp5 Developer Intake baseline. The stable rollback/main baseline remains 0.3.1.

### Shortcut and Dashboard fixes retained from exp3 scope

- **Show Sidebar** is now `Ctrl+Alt+S`.
- **List View** is now `Ctrl+Alt+L`.
- **Grid View** is now `Ctrl+Alt+G`.
- Invoking List View or Grid View from the View actions first returns to the Dashboard and then applies the requested view, so the shortcuts work predictably from component Details pages.

### AppImage build validation fix

- The Fedora/AppImage builder's AppStream MIME validation now includes Texypad's `text/x-tex` and `text/x-bibtex` entries. The desktop/AppStream payload already advertised them; the old validator omitted them and could terminate the build with exit code 1.
- Static/release QA now guards the exact MIME union so the validator cannot silently drift from packaged metadata again.

### First-class Reader components

- Adds `reader` as a trusted first-class component kind.
- **Editors:** Markopad, Nuxpad 2, Ricopad, Texypad, Sheepy Pad, Timblee Pad.
- **Readers:** Kapitulindo (EPUB), Portapad (PDF), Beespector and Beespector Lite (inspection-only; no normal routed extensions).
- **Extensions:** Crawlindo, Youlindo, Sbookypad, gitten, Python Lair, Linspector Suite.
- Component capabilities are explicit: Editors route/open/create; Readers route/open but do not create; Extensions and the Hub do not become document-routing candidates.
- Dashboard and sidebar now group **Editors**, **Readers**, and **Extensions** separately.
- Reader cards expose **Launch**, **Open…**, and **Details** with no **New…** action.
- Reader Details pages likewise omit **New File…** while retaining launch, open, preferences, version management, and AppImage integration actions.
- File Routing Preferences, silent dispatch, and the routing chooser include both Editors and Readers. The chooser is titled **Choose Application**.
- **New File…** remains Editor-only and has a defensive capability check even if called directly.
- The default extension/MIME union is derived from all routable profiles, not only Editors, so `.pdf`/`application/pdf` and `.epub`/`application/epub+zip` remain registered at OS level.
- Trusted component catalogue revision for the exp4 reader baseline was **4**; exp5 advances it to **5**.

### Compatibility

- Historical Editor-oriented class/function names are retained where changing them would create needless compatibility churn; policy decisions are capability-based.
- The canonical managed folder, version-management model, trusted catalogue/update boundary, and non-privileged AppImage builder policy are retained.
