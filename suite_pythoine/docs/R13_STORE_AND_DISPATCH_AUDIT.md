# Suite Pythoine 0.0.1-r13 — online catalogue and silent-dispatch audit

## Scope

r13 adds two independent behaviours on top of the rc11 managed-install/AppImage baseline:

1. an opt-in **Get More Editors** page for the five official brunonlinespace pad repositories; and
2. a **silent document-dispatch path** used when Suite is invoked with files through desktop associations.

## Store privacy states

The catalogue has three states:

- `available` — default; Store UI exists, but no network request is made;
- `enabled` — user opted in; GitHub is contacted only when Get More Editors is opened/refreshed or a selected release is downloaded;
- `disabled` — Store page/action/button are not constructed.

Terminal controls do not require PyQt6:

```text
suite-pythoine --store-status
suite-pythoine --disable-store
suite-pythoine --enable-store
```

`--enable-store` returns the feature to `available`; it does not silently restore network consent. `SUITE_PYTHOINE_DISABLE_STORE=1` is a non-persistent environment override that wins over preferences for that run.

## Official catalogue

The built-in catalogue contains only:

- `brunonlinespace/nuxpad`
- `brunonlinespace/ricopad`
- `brunonlinespace/portapad`
- `brunonlinespace/sheepy-pad`
- `brunonlinespace/timblee-pad`

Suite does not enumerate arbitrary account repositories. It reads published GitHub Releases, including prereleases, selects a source ZIP release asset, and requires a SHA-256 identity supplied either by GitHub's release-asset digest or a companion `<asset>.sha256` release asset. The verified ZIP is then passed to the existing installation wizard; no second installer path exists.

## Silent dispatch

When Suite is launched with ordinary document paths and `--show` is not supplied, `main.py` tries the pure-Python dispatcher before importing the PyQt6 main window.

For a uniquely routable/preferred extension the dispatcher:

- reads Suite preferences and managed registrations;
- discovers portable and installed editors;
- selects the same `EditorEntry.command()` policy used by the GUI;
- restores/sanitizes the host environment when Suite itself is an AppImage;
- starts the final pad detached; and
- exits without constructing `SuiteWindow`.

Unknown extensions, ZIPs, ambiguous editor choices, missing files, or launch failures remain unresolved and fall back to the normal interactive Suite UI. `--show <file>` explicitly requests the old visible-hub routing behaviour.
