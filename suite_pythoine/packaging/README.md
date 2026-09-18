# Suite Pythoine AppImage packaging

Suite Pythoine 0.3.3 follows the current Pad-family AppImage layout:

```text
suite_pythoine/
├── packaging/
│   ├── appimage/
│   │   ├── AppRun
│   │   ├── suite-pythoine.desktop
│   │   ├── suite-pythoine.png
│   │   └── io.github.brunonlinespace.suite-pythoine.metainfo.xml
│   ├── fedora/
│   │   ├── build-appimage.sh
│   │   └── test-appimage.sh
│   └── pyinstaller/
│       └── build-requirements.txt
├── qa/
│   └── static-qa.sh
├── build/                 # generated, not shipped in release source
└── dist/                  # generated, not shipped in release source
```

## Build

From any working directory:

```bash
bash suite_pythoine/packaging/fedora/build-appimage.sh
```

The builder targets Fedora 43/44 by default, supports native `x86_64` and `aarch64`, and is deliberately **non-privileged**. It does not invoke `sudo`, `dnf`, `su`, `pkexec`, or any system package installer. If a required host command or Python `venv` support is missing, it stops with a diagnostic. Python, PyInstaller and PyQt6 build dependencies are installed only inside `suite_pythoine/build/.../venv`.

The sequence is:

1. validate version/source/packaging inputs;
2. run Suite's static/release/security QA;
3. check host prerequisites without elevation;
4. create an isolated venv and record `pip freeze --all`;
5. freeze Suite with minimal PyInstaller collection;
6. dynamically assemble the AppDir;
7. validate Desktop Entry and AppStream metadata when host validators are available;
8. verify Qt platform payload and smoke-test the AppDir off-screen;
9. obtain appimagetool from `APPIMAGETOOL_PATH` or a bounded user cache/download;
10. ELF-check and optionally SHA-256-pin appimagetool;
11. build the AppImage using `--appimage-extract-and-run` so appimagetool itself does not require FUSE;
12. smoke-test the **finished AppImage** off-screen;
13. verify `--version` and emit AppImage SHA-256, build-info and Python-lock records.

Outputs are placed under:

```text
suite_pythoine/dist/
```

For a release build, set:

```bash
SUITE_PYTHOINE_RELEASE_BUILD=1 \
APPIMAGETOOL_SHA256=<trusted-64-hex-sha256> \
bash suite_pythoine/packaging/fedora/build-appimage.sh
```

`APPIMAGETOOL_PATH=/trusted/path/appimagetool-<arch>.AppImage` may be used to provide the tool explicitly; release mode still requires its expected SHA-256.

## File routing advertised by the AppImage

The AppImage Desktop Entry uses `Exec=suite-pythoine %F` and advertises the MIME union for all built-in Pad-family formats. When Nuxpad 2, Markopad, Ricopad, Texypad, Portapad, Kapitulindo, Sheepy Pad, Timblee Pad and JSTS Pad are loaded/registered in Suite, command-line/Open-With files are routed using Suite's routable Editor/Reader registry.

The built-in extension union is:

```text
.txt .log .ini .cfg .conf
.md .markdown .mdown .mkd
.rtf
.tex .bib
.pdf
.epub
.py .sh
.html .htm .css
.js .mjs .cjs .ts .mts .cts .jsx .tsx
```

This MIME/extension set remains based on the current complete Pad implementations used by Suite Pythoine: Portapad rc10 is PDF-only, and Sheepy Pad r1 accepts `.py` and `.sh`. Earlier/planned `.epub` and `.bash` associations are not advertised.

The Desktop Entry advertises the corresponding MIME union:

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
application/javascript
text/javascript
text/typescript
application/typescript
```

Desktop metadata only makes Suite eligible as an Open-With target; successful routing still requires a matching editor to be loaded or registered in Suite.
