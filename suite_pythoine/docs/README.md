# Suite Pythoine 0.3.3

**Friendly. Fast. Focused.**

Suite Pythoine is a lightweight file-routing and component-management Hub. Version 0.3.3 preserves the validated routing model while decoupling online discovery into the optional Store Pythoine companion.

## Component families

### Editors

Editors route/open supported documents and can create new files.

| Editor | Routed formats |
| --- | --- |
| Markopad | `.md`, `.markdown`, `.mdown`, `.mkd` |
| Nuxpad 2 | `.txt`, `.log`, `.ini`, `.cfg`, `.conf` |
| Ricopad | `.rtf` |
| Texypad | `.tex`, `.bib` |
| Sheepy Pad | `.py`, `.sh` |
| Timblee Pad | `.html`, `.htm`, `.css` |
| JSTS Pad | `.js`, `.mjs`, `.cjs`, `.ts`, `.mts`, `.cts`, `.jsx`, `.tsx` |

### Readers

Readers open/inspect content but do not create new files. A Reader participates in normal OS/document routing only when its trusted catalogue profile explicitly advertises routed formats; Beespector and Beespector Lite intentionally do not.

| Reader | Routed formats |
| --- | --- |
| Kapitulindo | `.epub` |
| Portapad | `.pdf` |
| Beespector | none — inspection/open only; explicit drop override |
| Beespector Lite | none — inspection/open only |

### Extensions

Extensions are Suite-managed standalone tools. They never participate in document routing and advertise no routed file types.

- Crawlindo
- Youlindo
- Sbookypad
- gitten
- Python Lair
- Linspectacles
- Marko Plus
- Rico Plus
- Store Pythoine

Suite Pythoine itself remains the sole **Hub** component.

## Dashboard and sidebar

Installed components are grouped under **Editors**, **Readers**, and **Extensions**. Editor cards provide **New… / Open… / Details**; the redundant generic Launch action is intentionally omitted because New enters the Editor-owned untitled workflow. Reader cards retain Launch/Open/Details; Extension cards retain Launch/Details. The sidebar uses the same three groups.

## Preferences and routing

There is one Suite-Pythoine-specific `Preferences — Suite Pythoine` dialog with five tabs:

- **General** — Components folder, Open Components Folder, and Developer Intake controls.
- **File Routing** — per-format routing choices for routable Editors and Readers.
- **Runtime** — Suite Launch runtime plus Portable/Installed folder and Desktop Integration recovery actions.
- **Versions** — retained-version launch, activation, removal, and folder actions.
- **Information** — the same complete Hub status text shown on Suite Details.

Suite Details retains the full Hub management surface. Installed Applications is a separate Suite page with a sortable inventory whose table expands to use the available page height. Resize columns by dragging separators, reorder them by dragging headings, and right-click a heading to show/hide columns; the layout is remembered. The page also provides Install Component… beside Refresh Inventory.

- One eligible application → silent launch.
- Several eligible applications + remembered choice → silent launch.
- Several eligible applications + no remembered choice → compact **Choose Application** chooser.
- No eligible routed application → optional internal Beespector/Beespector Lite inspection fallback; if neither is available, full Hub/no-handler fallback.
- Beespector fallback is evaluated only **after** validated routing returns zero candidates. Beespector/Lite remain `routing=false` and never acquire OS MIME ownership from this feature.
- Non-routing Readers, Extensions and the Hub are never normal document-routing candidates.

`python3 main.py --diagnose-routing <file>` exposes the dependency-light pre-GUI decision.

## Shortcuts

- Dashboard — `Ctrl+W`
- Refresh Components — `F5`
- Open Components Folder — `Ctrl+Shift+O`
- Install Component… — `Ctrl+Shift+N`
- Show Sidebar — `F9`
- Toggle List/Grid View — `Ctrl+Alt+Shift+D` (keyboard-only; not a menu entry)
- Show Dashboard Icons — `Ctrl+Alt+Shift+I`
- Show Drop Bar — `Ctrl+Alt+Shift+B`
- Focus Dashboard Search — `Ctrl+F`
- Preferences… — `Ctrl+/`
- Keyboard Shortcuts — `Ctrl+Shift+/`
- Developer Intake Mode — `F12`
- Previous Suite page/card — `Backspace`
- Beespector file-drop override — hold `Ctrl+Shift+B` while dropping a file
- Youlindo URL-drop override — hold `Ctrl+Shift+Y` while dropping a URL
- Crawlindo URL-drop override — hold `Ctrl+Shift+C` while dropping a URL

List View and Grid View are mutually exclusive choices under **View → Dashboard Settings** and return to the Dashboard before applying the selected view. Dashboard Settings also contains Show Dashboard Icons and Show Drop Bar.

## Suite desktop runtime ownership

The active Suite Pythoine runtime owns the single managed desktop entry directly. If the active Suite version is configured for Portable, the desktop entry invokes that exact Portable `main.py`; if configured for AppImage, it invokes that exact AppImage. The same catalogue-derived MIME union and `%F` forwarding are preserved in either case, so OS routing and the special Drop Bar/keyboard overrides remain independent of runtime ownership. Explicit historical runtime launches are not redirected to the current active version.

## Store Pythoine boundary

Online discovery and downloads are no longer built into Suite. **Get More…** launches the optional standalone **Store Pythoine** Extension when installed; otherwise Suite offers the existing local **Install Extension…** route. Store Pythoine runs only when intentionally opened. It queries Suite through the short-lived `suite-pythoine` control bridge and may request package inspection or the installed-runtime inventory without writing Suite state directly. Install/update requests always invoke Suite's **full existing installation wizard**. Suite's trusted catalogue, package validation, routing, managed registry, active-runtime and desktop-integration logic remain authoritative.

The Store-facing control protocol is intentionally small:

- `--store-protocol-version`
- `--managed-list --json`
- `--inspect-package <package> --json`
- `--install-package <package> --source store --wizard`

## Developer Intake release notes

Developer Intake keeps its separate configuration and existing Action workflow. The Markdown release-note area also provides **Paste** to insert the current clipboard text directly before README creation.

## Managed component root

The canonical default remains `~/Suite Pythoine/`, with `<Component>/<Version>/Portable/` and `<Component>/<Version>/AppImage/` leaves.

