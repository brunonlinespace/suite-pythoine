# Suite Pythoine 0.3.2-exp4 — Reader/capability audit

## Scope

This branch promotes Reader to a first-class component kind and applies the shortcut/AppImage corrections described for the preceding exp3 scope.

## Capability contract

| Kind | Route documents | Open documents | Create documents |
|---|---:|---:|---:|
| Hub | No | No | No |
| Editor | Yes | Yes | Yes |
| Reader | Yes | Yes | No |
| Extension | No | No | No |

The trusted catalogue carries these capabilities explicitly. Runtime policy consumes capabilities, while kind remains the descriptive taxonomy used by the Dashboard/sidebar.

## Reader classification

- Kapitulindo: Reader, `.epub`, `application/epub+zip`.
- Portapad: Reader, `.pdf`, `application/pdf`.

Readers remain eligible for File Routing Preferences, silent dispatch and Open File routing, but are excluded from all New File/create actions.

## UI contract

- Dashboard/sidebar groups: Editors, Readers, Extensions.
- Reader card: Launch / Open… / Details.
- Reader Details: no New File action.
- Routing ambiguity dialog title: Choose Application.
- List/Grid actions return to Dashboard before switching view.

## Packaging guard

The AppImage builder AppStream validator must match the complete routable MIME union, including `text/x-tex` and `text/x-bibtex`.

## Rollback boundary

0.3.1 remains the stable rollback/main baseline. 0.3.2-exp4 is experimental and may be installed alongside it through existing version management.
