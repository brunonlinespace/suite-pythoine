# Suite Pythoine 0.1.0 — AppImage apparatus audit

r8 adds Suite Pythoine's own complete AppImage build/test apparatus while preserving the r7 editor-management UI and the rule that Suite manages editors rather than embedding them.

## Inputs reviewed

The design was reconciled against the supplied standardized builders for Nuxpad, Ricopad, Portapad, Sheepy Pad and Timblee Pad, then updated to the newer Ricopad 0.3.3-rc4.2 packaging contract. The newer Ricopad line is the stronger reference because it moved to the Pad-family `packaging/appimage`, `packaging/fedora`, `packaging/pyinstaller` hierarchy, runs static/security QA before freezing, supports native x86_64/aarch64, uses a bounded user cache for appimagetool, final-AppImage smoke tests, and is intentionally non-privileged.

## Non-privileged builder policy

`suite_pythoine/packaging/fedora/build-appimage.sh` never invokes `sudo`, `dnf`, `su`, `pkexec` or another system package installer. It checks host prerequisites and Python venv/ensurepip support and exits with a diagnostic when something is missing. Runtime/build Python packages are installed only into `suite_pythoine/build/appimage-fedora-<arch>/venv`.

The builder supports `APPIMAGETOOL_PATH`, `APPIMAGETOOL_URL` and `APPIMAGETOOL_SHA256`. Downloaded appimagetool is bounded to 200 MiB, written to a `.part` file, ELF-checked before promotion, and cached under `${XDG_CACHE_HOME:-~/.cache}/suite-pythoine-appimage-tools`. `SUITE_PYTHOINE_RELEASE_BUILD=1` requires a trusted `APPIMAGETOOL_SHA256`.

## Build/QA sequence

1. Validate source/version/packaging inputs and native architecture.
2. Run `qa/static-qa.sh`, which includes the Python release/security gate.
3. Check required host commands without elevation.
4. Create a clean isolated venv and install Suite runtime requirements plus PyInstaller build requirements.
5. Record `pip freeze --all`.
6. Freeze the real `main.py` with PyInstaller and only the required Suite assets/docs.
7. Dynamically assemble an AppDir with Desktop Entry, icons, AppStream metadata and documentation.
8. Run built-in Desktop Entry checks and optional host `desktop-file-validate` / `appstreamcli validate --no-net`.
9. Check the Qt XCB payload, warn when Wayland support is absent or WebEngine appears unexpectedly, and construct the real Suite main window off-screen through `--suite-pythoine-smoke-test`.
10. Obtain/verify appimagetool and build using `--appimage-extract-and-run`.
11. Smoke-test the finished AppImage, then verify its `--version` path.
12. Emit AppImage SHA-256, build-info and frozen Python lock in `suite_pythoine/dist/`.

## Pad-family routing contract

The AppImage Desktop Entry uses `Exec=suite-pythoine %F`, allowing a desktop environment to hand multiple files to the hub. Suite routes command-line/startup paths through its routable Editor/Reader registry. r8 expands the release gate to verify every built-in pad-family extension, not only representative PDF/Python/HTML cases.

The complete built-in extension union is:

```text
Nuxpad 2:   .txt .log .ini .cfg .conf
Historical Ricopad assignment at the time of this audit: .md .markdown .mdown .mkd .rtf
Current 0.3.2-exp4 assignment: Markopad = .md .markdown .mdown .mkd; Ricopad = .rtf; Texypad = .tex .bib
Kapitulindo:.epub
Portapad:   .pdf
Sheepy Pad: .py .sh
Timblee Pad:.html .htm .css
```

This is the current-source union used by r8. Inspection of the complete Portapad rc10 source shows PDF-only command-line/open support, while Sheepy Pad r1 explicitly limits script suffixes to `.py` and `.sh`. Suite therefore removes the earlier/planned `.epub` and `.bash` defaults rather than advertising formats the current applications reject.

The Desktop Entry and AppStream metadata advertise the matching MIME union:

```text
text/plain
text/x-log
text/markdown
text/rtf
application/rtf
text/x-tex
text/x-bibtex
application/pdf
application/epub+zip
text/x-python
text/x-python3
application/x-shellscript
text/html
application/xhtml+xml
text/css
```

This makes an integrated Suite AppImage eligible as an Open-With target for the family. Successful routing still depends on the corresponding pad being loaded/registered; Suite does not contain fallback document editors.

## Outputs

The canonical build command is:

```bash
bash suite_pythoine/packaging/fedora/build-appimage.sh
```

Expected outputs:

```text
suite_pythoine/dist/Suite-Pythoine-0.1.0-<arch>.AppImage
suite_pythoine/dist/Suite-Pythoine-0.1.0-<arch>.AppImage.sha256
suite_pythoine/dist/Suite-Pythoine-0.1.0-<arch>.build-info.txt
suite_pythoine/dist/Suite-Pythoine-0.1.0-<arch>.build-python-lock.txt
```
