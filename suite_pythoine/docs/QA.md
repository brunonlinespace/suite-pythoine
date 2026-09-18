# Suite Pythoine 0.3.3 QA

## 0.3.3 release gate

- Confirm application/package/AppStream/build identity is exactly **0.3.3**, with no `-exp` or `-r` suffix.
- Confirm the trusted catalogue has no PSTS component and still contains JSTS Pad.
- Confirm Timblee Pad remains routed only for `.html`, `.htm`, `.css`; `.svg` must not enter Timblee or the Suite MIME/extension union.
- Confirm Editor Dashboard cards expose **New… / Open… / Details** and Editor Details expose **New File… / Open File…**, with no generic Editor **Launch**; Readers/Extensions and per-version **Launch Portable/AppImage** actions are unchanged.
- Confirm built-in Store browser/network modules are absent. **Get More…** launches installed Store Pythoine or offers only local **Install Extension…** when absent.
- Confirm Store Pythoine is a trusted non-routing Extension and has no routed extensions/MIME ownership.
- Confirm `--store-protocol-version`, `--managed-list --json`, and `--inspect-package ... --json` run without the full Suite GUI.
- Confirm `--install-package <package> --source store --wizard` opens Suite's complete existing ZIP/AppImage installation wizard, even when Developer Intake is enabled, and does not silently install.
- Confirm Store queries/install transactions work through the active Suite runtime bridge with no resident daemon/background Suite process.
- Re-run the complete validated routing matrix and Developer Intake/Beespector/drop-override gates to prove the Store decoupling did not alter them.

## exp8 UI-layout checks

- Confirm a version that has both Portable and AppImage appears as two Installed Applications rows and that the column header is **Runtime**.
- Confirm each runtime row reports only that runtime's size/location/desktop/managed state.
- Confirm existing Installed Applications width/order/visibility preferences survive the `Installed as` → `Runtime` rename.
- Confirm the Components sidebar never grows beyond the established 250 px default, including with long component names, while the splitter can still be dragged narrower/all the way closed.
- Installed Applications column width/order/visibility persistence remains covered by static source assertions.
- Developer Intake Configuration retains its bounded 780×600 default/minimum geometry with a scrollable App Roots list.

## Experimental UI/component gate

1. Confirm Dashboard and sidebar group installed applications into **Editors**, **Readers**, and **Extensions**.
2. Confirm Editor cards offer New/Open/Details with no generic Launch button; Reader/Extension Launch controls remain present where previously defined.
3. Confirm the sidebar button reads exactly **Get More...**.
4. Confirm Tools → Preferences and Suite Pythoine Hub Details → Preferences open the same `Preferences — Suite Pythoine` experience. Confirm its tabs are General, File Routing, Runtime, Versions, Information; General has Open Components Folder and no Launch runtime row; Runtime owns Launch runtime and Portable/Installed management actions.
5. Confirm Ricopad/Markopad/etc. continue to use their own component Preferences actions rather than being merged into the Hub dialog.
6. Confirm title bars retain `<Window> — Suite Pythoine`.

## Shortcut gate

Verify:

- Dashboard `Ctrl+W`
- Refresh Components `F5`
- Open Components Folder `Ctrl+Shift+O`
- Install Component… `Ctrl+Shift+N`
- Show Sidebar `F9`
- Show Dashboard Icons `Ctrl+Alt+Shift+I`
- Show Drop Bar `Ctrl+Alt+Shift+B`
- Focus Dashboard Search `Ctrl+F`
- Preferences `Ctrl+/`
- Keyboard Shortcuts `Ctrl+Shift+/`


## 0.3.3-r4 clarified dashboard/keymap polish gate

1. Confirm `Ctrl+Alt+Shift+D` toggles Dashboard List/Grid view from either current presentation and returns to Dashboard, while no Toggle List/Grid action appears in View, Dashboard Settings, or the Dashboard action row.
2. Confirm **View** begins with **Refresh Components**, then one separator, then **Dashboard** and **Dashboard Settings** with no separator between those two.
3. Confirm **Dashboard Settings** still contains exclusive **List View** / **Grid View**, then one separator, **Show Dashboard Icons**, and **Show Drop Bar**.
4. Confirm Preferences → General → Dashboard explicitly shows the `Ctrl+Alt+Shift+D` toggle shortcut in addition to the icon/drop-bar shortcuts.
5. Confirm Keyboard Shortcuts uses the Marko Plus 0.0.2 matcher semantics: command substring matching plus shortcut token aliases (`control`, `ctrl`, `ctl`), optional plus signs, and reordered modifier tokens.

## 0.3.3-r3 dashboard/inventory polish gate

1. Installed Applications: resize/maximize the window and confirm the table consumes all available vertical space between its summary and footnote rather than staying at a fixed 360 px height.
2. Confirm **Install Component…** is present in the Installed Applications heading row immediately beside **Refresh Inventory** and opens the established installer flow.
3. Confirm **View** contains, consecutively and without separators, **Dashboard**, **Refresh Components**, and **Dashboard Settings**.
4. Confirm **Dashboard Settings** contains exclusive **List View** / **Grid View** choices, then one separator, **Show Dashboard Icons**, and **Show Drop Bar**.
5. Confirm there is no Dashboard List/Grid toggle button, no top-level View List/Grid actions, and no `Ctrl+Alt+Shift+D` binding.
6. Confirm Preferences explicitly shows `Ctrl+Shift+O` for Open Components Folder, `Ctrl+Alt+Shift+I` for Dashboard icons, `Ctrl+Alt+Shift+B` for Drop Bar, and `F12` for Developer Intake Mode.

## Catalogue/classification gate

Editors: Markopad, Nuxpad 2, Ricopad, Texypad, Sheepy Pad, Timblee Pad, JSTS Pad.

Readers: Kapitulindo, Portapad, Beespector, Beespector Lite.

Extensions: Linspectacles, Marko Plus, Rico Plus, Crawlindo, Youlindo, Sbookypad, gitten, Python Lair, Store Pythoine.

1. Confirm `catalog_revision` is 9.
2. Confirm every Extension has an empty trusted extension list and is excluded from routing candidates. Confirm Beespector/Beespector Lite are Readers with open=true, create=false, routing=false and no routed formats.
3. Confirm Texypad owns `.tex` and `.bib` and Suite advertises `text/x-tex` and `text/x-bibtex` at the OS level.
4. Confirm retired aliases such as former Pad names are absent from the canonical catalogue.

## Routing regression gate

With Suite as the OS opener, repeat the 0.3.1 routing matrix in both Portable and AppImage modes. Add `.tex → Texypad`. The Suite window must not appear on a resolvable route. Multi-editor ambiguity must still use only the compact chooser. Extensions must never appear in that chooser.

## Existing 0.3.1 gates

Re-run Make Active/Desktop Integration synchronization, direct Suite Portable/AppImage desktop ownership, canonical `~/Suite Pythoine/` storage transition, source/AppImage install policy, Store Pythoine decoupling/control-bridge checks, AppImage hardening, source cleanliness, and final-ZIP manifest verification.

## Suite management restoration gate

1. Open Suite Pythoine Details and confirm the complete Hub information block is present from Type through Desktop Integration.
2. Confirm retained version cards expose Launch Portable, Launch AppImage, Make Active, Remove Version…, and Open Version Folder.
3. Confirm Hub, Portable Runtime, and Integration action sections remain present.
4. Confirm Installed Applications is a separate Suite page; its table expands vertically to fill the available page space and retains sorting/column layout behavior. Confirm Install Component… appears beside Refresh Inventory.
5. Open Preferences and confirm the Runtime, Versions, and Information content mirrors the same underlying Suite state/actions. Confirm shortcut-bearing General controls display their shortcuts explicitly.
6. Confirm View menu order is Dashboard → Refresh Components → Dashboard Settings with no separators between those three entries. Inside Dashboard Settings confirm exclusive List View/Grid View choices, then a separator, Show Dashboard Icons, and Show Drop Bar. Confirm no standalone Toggle List/Grid View action/button remains.
## 0.3.2-exp9-r1 nested component identity

| ID | Area | Procedure | Expected result |
|---|---|---|---|
| ID-R1-01 | Python Lair | Install a ZIP whose portable root is `main.py` + `python_lair2/`, with `python_lair2/python-lair.json`. | Post-import **Verify component identity** resolves `python-lair`; no third root manifest is required. |
| ID-R1-02 | Sheepy Pad | Inspect/install a two-item Sheepy root with `sheepy_pad/sheepy-pad.json`. | Nested identity resolves `sheepy-pad`, proving the behavior is Pad-family generic. |
| ID-R1-03 | Trust | Put an unrelated JSON file in an immediate child package. | It is ignored unless its identity resolves to the trusted catalogue. |
| ID-R1-04 | Error state | Force an unknown component during post-import verification. | Wizard fails **Verify component identity** cleanly; it does not report AppImage preparation. |

## 0.3.2-exp9-r2 active-runtime / identity review

| ID | Area | Procedure | Expected result |
|---|---|---|---|
| R2-01 | Suite active Portable | Make a Portable-capable Suite version active with Launch runtime = Portable. Inspect `io.github.brunonlinespace.suite-pythoine.desktop`. | `Exec=` targets that exact Portable Python/main.py command with `%F`; runtime marker is Portable; MIME union is unchanged. |
| R2-02 | Suite active AppImage | Switch Launch runtime/active version to an AppImage-capable Suite version and repair/make active. | Desktop `Exec=` targets that exact AppImage directly; no older retained AppImage bootstrap is required. |
| R2-03 | Explicit history | Use a Versions card **Launch AppImage** on a retained historical Suite AppImage. | The selected AppImage remains the selected version/runtime; current shared Portable preference does not hijack it. |
| R2-04 | Routing preservation | Open a normally routed document through the OS in both direct Portable and direct AppImage Suite desktop states. | Same routed target/chooser behavior as exp9; Suite MIME union and `%F` forwarding are unchanged. |
| R2-05 | Special drops | Exercise Ctrl+Shift+B file drop, Ctrl+Shift+Y URL drop and Ctrl+Shift+C URL drop. | Beespector/Youlindo/Crawlindo overrides remain unchanged and do not alter OS routing. |
| R2-06 | Backspace | Navigate Dashboard → component Details → another Suite surface and press Backspace. Also type/edit in a text field. | Backspace returns through Suite navigation history when handled by the window; editable fields still delete text normally. |
| R2-07 | gitten install | Inspect/install a canonical `gitten` source package (`main.py` + `gitten/`, nested trusted gitten manifest). | Resolves canonical component ID/name `gitten`; legacy `gitten-pad` is not required. |
| R2-08 | gitten migration | Start from preferences/managed state keyed by `gitten-pad`. | State is exposed under `gitten`, including Developer Intake root and canonical desktop identity, without a duplicate logical component. |
| R2-09 | Beespector semantics | Inspect Dashboard/sidebar/Details and routing candidates for Beespector + Lite. | Both appear under Readers and use Reader-family management; neither gains OS/document routing automatically. |
| R2-10 | Developer Intake Paste | Open Developer Intake with a ZIP loaded, copy Markdown text, press **Paste**, then Action. | Clipboard text appears in release notes and becomes README content; success remains status-only. |


## 0.3.2-exp9-r3 inspection fallback / icon-quality review

| ID | Area | Procedure | Expected result |
|---|---|---|---|
| R3-01 | Validated routing boundary | Install Markopad plus Beespector/Lite and open a normally routed Markdown file through Suite. | Markopad route is unchanged; neither inspector is considered or shown. |
| R3-02 | Unsupported file / both inspectors | Open an unsupported file with Suite while Beespector and Beespector Lite are both installed and fallback is Ask every time. | Compact inspection chooser offers only Beespector and Beespector Lite; normal routing chooser is not reused/contaminated. |
| R3-03 | Remember fallback | Choose Beespector/Lite and tick Remember, then open another unsupported file. | Remembered inspector opens directly; File Routing Preferences reflects the saved choice and Reset Routing Choices restores Ask every time. |
| R3-04 | Availability change | Remember Beespector, remove it while Lite remains, then open an unsupported file. | Lite is used as the sole remaining fallback; no stale preference failure. |
| R3-05 | No inspectors | Remove/disable both Beespector variants and open an unsupported file. | Existing no-handler/full-Hub message path remains; no MIME/routing capability is invented. |
| R3-06 | Startup path | Use the OS/Open-With path to send an unsupported file to Suite. | The dependency-light pre-GUI route follows the same zero-candidate-only fallback and does not construct the full Hub when the inspector launch/chooser handles the file. |
| R3-07 | Icon quality | Inspect a source ZIP containing a small `app.png` and a canonical/master 512/1024 raster or SVG. | Wizard chooses the better canonical/high-resolution source and reports its archive path as **Wizard icon source**. |
| R3-08 | Manifest icon | Provide an explicit manifest icon path, including a path relative to a nested application package. | Declared icon remains authoritative and its resolved source path is reported. |

