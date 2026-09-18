#!/usr/bin/env bash
set -Eeuo pipefail
umask 022

# Suite Pythoine AppImage builder.
# Deliberately non-privileged: no sudo, su, pkexec, dnf or other system-package
# installation is performed. Python build dependencies live only in the
# isolated build virtualenv; missing host tools are reported and the build stops.

APP_NAME="Suite Pythoine"
APP_ID="suite-pythoine"
APP_VERSION="0.3.3"
DESKTOP_ID="io.github.brunonlinespace.suite-pythoine"
PUBLISHER_ID="brunonlinespace"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROGRAM_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd -P)"
PROJECT_ROOT="$(cd -- "${PROGRAM_ROOT}/.." && pwd -P)"
SOURCE_ENTRY="${PROJECT_ROOT}/main.py"
PACKAGE_INIT="${PROGRAM_ROOT}/__init__.py"
PROJECT_MANIFEST="${PROJECT_ROOT}/suite-pythoine.json"
COMPONENT_CATALOG="${PROGRAM_ROOT}/components.json"
SOURCE_MANIFEST="${PROGRAM_ROOT}/SOURCE_MANIFEST.sha256"
RUNTIME_REQUIREMENTS="${PROGRAM_ROOT}/requirements.txt"
APPIMAGE_PAYLOAD="${PROGRAM_ROOT}/packaging/appimage"
BUILD_REQUIREMENTS="${PROGRAM_ROOT}/packaging/pyinstaller/build-requirements.txt"
STATIC_QA="${PROGRAM_ROOT}/qa/static-qa.sh"
ASSET_DIR="${PROGRAM_ROOT}/assets"
DOCS_DIR="${PROGRAM_ROOT}/docs"

HOST_ARCH_RAW="$(uname -m)"
case "$HOST_ARCH_RAW" in
    x86_64) HOST_ARCH="x86_64" ;;
    aarch64|arm64) HOST_ARCH="aarch64" ;;
    *) printf 'Error: unsupported build architecture: %s\n' "$HOST_ARCH_RAW" >&2; exit 2 ;;
esac
ARCH="${ARCH:-$HOST_ARCH}"

FEDORA_RELEASE="unknown"
HOST_NAME="unknown Linux"
OS_ID="unknown"
if [[ -r /etc/os-release ]]; then
    mapfile -d '' -t OS_RELEASE_VALUES < <(
        set +u
        # shellcheck disable=SC1091
        source /etc/os-release
        printf '%s\0%s\0%s\0' "${ID:-unknown}" "${VERSION_ID:-unknown}" "${PRETTY_NAME:-unknown Linux}"
    )
    OS_ID="${OS_RELEASE_VALUES[0]:-unknown}"
    FEDORA_RELEASE="${OS_RELEASE_VALUES[1]:-unknown}"
    HOST_NAME="${OS_RELEASE_VALUES[2]:-unknown Linux}"
fi

BUILD_ROOT="${BUILD_ROOT:-${PROGRAM_ROOT}/build/appimage-fedora${FEDORA_RELEASE}-${ARCH}}"
VENV="${BUILD_ROOT}/venv"
PYI_WORK="${BUILD_ROOT}/pyinstaller-work"
PYI_DIST="${BUILD_ROOT}/pyinstaller-dist"
FINAL_APPDIR="${BUILD_ROOT}/Suite-Pythoine.AppDir"
SMOKE_HOME="${BUILD_ROOT}/smoke-home"
DIST_DIR="${OUTPUT_DIR:-${PROGRAM_ROOT}/dist}"
CACHE_DIR="${XDG_CACHE_HOME:-${HOME}/.cache}/suite-pythoine-appimage-tools"

APPIMAGE="${DIST_DIR}/Suite-Pythoine-${APP_VERSION}-${ARCH}.AppImage"
SHA_FILE="${APPIMAGE}.sha256"
BUILD_INFO="${DIST_DIR}/Suite-Pythoine-${APP_VERSION}-${ARCH}.build-info.txt"
PYTHON_LOCK="${DIST_DIR}/Suite-Pythoine-${APP_VERSION}-${ARCH}.build-python-lock.txt"
APPIMAGETOOL_RESOLVED=""
MAX_TOOL_BYTES=$((200 * 1024 * 1024))

export PYTHONDONTWRITEBYTECODE=1

log() { printf '\n==> %s\n' "$*"; }
die() { printf 'Error: %s\n' "$*" >&2; exit 1; }
require_file() { [[ -f "$1" ]] || die "Missing file: $1"; }

clean_source_python_caches() {
    while IFS= read -r -d '' cache_dir; do
        rm -rf -- "$cache_dir"
    done < <(
        find "$PROJECT_ROOT" \
            \( -path "$PROJECT_ROOT/.git" \
               -o -path "$PROJECT_ROOT/.venv" \
               -o -path "$PROJECT_ROOT/venv" \
               -o -path "$PROGRAM_ROOT/build" \
               -o -path "$PROGRAM_ROOT/dist" \) -prune \
            -o -type d -name '__pycache__' -print0
    )
    while IFS= read -r -d '' bytecode_file; do
        rm -f -- "$bytecode_file"
    done < <(
        find "$PROJECT_ROOT" \
            \( -path "$PROJECT_ROOT/.git" \
               -o -path "$PROJECT_ROOT/.venv" \
               -o -path "$PROJECT_ROOT/venv" \
               -o -path "$PROGRAM_ROOT/build" \
               -o -path "$PROGRAM_ROOT/dist" \) -prune \
            -o -type f \( -name '*.pyc' -o -name '*.pyo' \) -print0
    )
}

cleanup() {
    rm -rf "$SMOKE_HOME"
    clean_source_python_caches
}
trap cleanup EXIT

check_non_privileged_policy() {
    if grep -Eq '^[[:space:]]*(sudo|dnf|pkexec|su)([[:space:]]|$)' "$0"; then
        die "Privilege-elevation or host-package-install command detected in builder."
    fi
}

check_host_prerequisites() {
    log "Checking non-privileged host prerequisites"
    local missing=() command_name
    for command_name in python3 bash timeout sha256sum od stat find grep cp ln chmod install mktemp \
        rm mkdir mv tr awk cut date uname readlink sort env wc; do
        command -v "$command_name" >/dev/null 2>&1 || missing+=("$command_name")
    done
    if ! command -v curl >/dev/null 2>&1 && ! command -v wget >/dev/null 2>&1; then
        missing+=("curl-or-wget")
    fi
    if ((${#missing[@]})); then
        die "Missing required host command(s): ${missing[*]}. The builder will not install system packages; provide them and rerun."
    fi
    python3 - <<'PYVENV' >/dev/null 2>&1 || \
        die "This Python cannot create virtual environments. Provide Python with venv/ensurepip support and rerun."
import ensurepip, venv
PYVENV
}

check_inputs() {
    if (( EUID == 0 )) && [[ "${SUITE_PYTHOINE_ALLOW_ROOT_BUILD:-0}" != "1" ]]; then
        die "Do not run the Suite Pythoine AppImage builder with sudo/root."
    fi
    case "$ARCH" in x86_64|aarch64) ;; *) die "Unsupported AppImage architecture: ${ARCH}" ;; esac
    [[ "$ARCH" == "$HOST_ARCH" ]] || die "Requested ${ARCH}, but host is ${HOST_ARCH_RAW}; cross-building is unsupported."
    if [[ "$OS_ID" != "fedora" || ! "$FEDORA_RELEASE" =~ ^(43|44)$ ]]; then
        if [[ "${SUITE_PYTHOINE_ALLOW_UNSUPPORTED_HOST:-0}" != "1" ]]; then
            die "Validated for Fedora 43/44. Detected ${HOST_NAME}. Set SUITE_PYTHOINE_ALLOW_UNSUPPORTED_HOST=1 only for intentional testing."
        fi
        printf 'Warning: continuing on unsupported host: %s\n' "$HOST_NAME" >&2
    fi

    for path in \
        "$SOURCE_ENTRY" "$PACKAGE_INIT" "$PROJECT_MANIFEST" "$COMPONENT_CATALOG" "$SOURCE_MANIFEST" \
        "$RUNTIME_REQUIREMENTS" "$BUILD_REQUIREMENTS" "$STATIC_QA" \
        "${APPIMAGE_PAYLOAD}/AppRun" "${APPIMAGE_PAYLOAD}/suite-pythoine.desktop" \
        "${APPIMAGE_PAYLOAD}/suite-pythoine.png" \
        "${APPIMAGE_PAYLOAD}/io.github.brunonlinespace.suite-pythoine.metainfo.xml" \
        "${PROJECT_ROOT}/COPYING" "${DOCS_DIR}/README.md" "${DOCS_DIR}/QA.md" "${DOCS_DIR}/RELEASE_NOTES.md"; do
        require_file "$path"
    done
    for size in 16 24 32 48 64 128 256 512; do
        require_file "${ASSET_DIR}/suite-pythoine-${size}.png"
    done

    grep -Fq "__version__ = \"${APP_VERSION}\"" "$PACKAGE_INIT" \
        || die "Suite Pythoine source version mismatch."
    python3 - "$PROJECT_MANIFEST" "$APP_NAME" "$APP_ID" "$APP_VERSION" "$PUBLISHER_ID" "$DESKTOP_ID" <<'PYIDENT'
import json
from pathlib import Path
import sys
path=Path(sys.argv[1]); name, app_id, version, publisher, desktop_id=sys.argv[2:]
data=json.loads(path.read_text(encoding='utf-8'))
assert data.get('name') == name, 'application name mismatch'
assert data.get('id') == app_id, 'application ID mismatch'
assert data.get('version') == version, 'application version mismatch'
assert data.get('publisher_id') == publisher, 'publisher ID mismatch'
assert data.get('desktop_id') == desktop_id, 'desktop ID mismatch'
PYIDENT
}

run_release_qa() {
    log "Running Suite Pythoine release/static/security QA"
    # Invoke nested QA through Bash so ZIP/file-manager extraction does not
    # need to preserve the helper's executable bit.
    bash "$STATIC_QA"
}

validate_desktop_entry_basic() {
    local desktop="$1"
    grep -Fqx '[Desktop Entry]' "$desktop" || die "Invalid desktop entry: $desktop"
    grep -Eq '^Type=Application$' "$desktop" || die "Desktop Entry requires Type=Application"
    grep -Eq '^Name=Suite Pythoine$' "$desktop" || die "Desktop Entry requires Name=Suite Pythoine"
    grep -Eq '^Exec=suite-pythoine([[:space:]]|$)' "$desktop" || die "Desktop Entry requires Exec=suite-pythoine"
    grep -Eq '^Icon=suite-pythoine$' "$desktop" || die "Desktop Entry requires Icon=suite-pythoine"
    grep -Eq '^MimeType=.*text/plain.*text/markdown.*application/pdf.*application/epub\+zip.*text/x-python.*application/x-shellscript.*text/html.*text/css.*application/javascript.*text/javascript.*text/typescript.*application/typescript' "$desktop" \
        || die "Desktop Entry does not advertise the complete pad-family MIME set"
}

validate_appstream_basic() {
    local metainfo="$1"
    python3 - "$metainfo" "$APP_VERSION" <<'PYXML'
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
path=Path(sys.argv[1]); version=sys.argv[2]
root=ET.parse(path).getroot()
def txt(tag):
    node=root.find(tag)
    return (node.text or '').strip() if node is not None else ''
assert txt('id') == 'io.github.brunonlinespace.suite-pythoine'
assert txt('project_license') == 'GPL-3.0-or-later'
assert txt('name') == 'Suite Pythoine'
assert txt("launchable[@type='desktop-id']") == 'suite-pythoine.desktop'
expected={
    'text/plain','text/x-log','text/markdown','text/rtf','application/rtf','text/x-tex','text/x-bibtex',
    'application/pdf','application/epub+zip','text/x-python','text/x-python3',
    'application/x-shellscript','text/html','application/xhtml+xml','text/css','application/javascript','text/javascript','text/typescript','application/typescript',
}
actual={(node.text or '').strip() for node in root.findall('./provides/mediatype')}
assert actual == expected, (actual, expected)
assert any(node.attrib.get('version') == version for node in root.findall('./releases/release'))
PYXML
}

prepare_environment() {
    log "Preparing isolated build environment"
    rm -rf "$BUILD_ROOT"
    clean_source_python_caches
    mkdir -p "$BUILD_ROOT" "$DIST_DIR" "$CACHE_DIR"
    chmod 0700 "$CACHE_DIR"
    python3 -m venv "$VENV"
    "$VENV/bin/python" -m pip install --upgrade pip wheel setuptools
    "$VENV/bin/python" -m pip install -r "$RUNTIME_REQUIREMENTS" -r "$BUILD_REQUIREMENTS"
    PYTHONPYCACHEPREFIX="${BUILD_ROOT}/pycache" \
        "$VENV/bin/python" -m compileall -q "$SOURCE_ENTRY" "$PROGRAM_ROOT"
    "$VENV/bin/python" -m pip check
    "$VENV/bin/python" -m pip freeze --all > "$PYTHON_LOCK"
}

freeze_application() {
    log "Freezing Suite Pythoine with PyInstaller"
    "$VENV/bin/pyinstaller" \
        --noconfirm --clean --onedir --optimize 1 \
        --name "$APP_ID" \
        --paths "$PROJECT_ROOT" \
        --distpath "$PYI_DIST" --workpath "$PYI_WORK" --specpath "$BUILD_ROOT" \
        --add-data "${ASSET_DIR}:suite_pythoine/assets" \
        --add-data "${DOCS_DIR}:suite_pythoine/docs" \
        --add-data "${COMPONENT_CATALOG}:suite_pythoine" \
        "$SOURCE_ENTRY"
}

assemble_appdir() {
    log "Dynamically assembling AppDir"
    rm -rf "$FINAL_APPDIR"
    mkdir -p \
        "$FINAL_APPDIR/usr/lib/suite-pythoine" \
        "$FINAL_APPDIR/usr/bin" \
        "$FINAL_APPDIR/usr/share/applications" \
        "$FINAL_APPDIR/usr/share/icons/hicolor/scalable/apps" \
        "$FINAL_APPDIR/usr/share/metainfo" \
        "$FINAL_APPDIR/usr/share/doc/suite-pythoine"

    cp -a "${PYI_DIST}/${APP_ID}/." "$FINAL_APPDIR/usr/lib/suite-pythoine/"
    ln -s ../lib/suite-pythoine/suite-pythoine "$FINAL_APPDIR/usr/bin/suite-pythoine"
    install -m 0755 "${APPIMAGE_PAYLOAD}/AppRun" "$FINAL_APPDIR/AppRun"
    install -m 0644 "${APPIMAGE_PAYLOAD}/suite-pythoine.desktop" "$FINAL_APPDIR/suite-pythoine.desktop"
    install -m 0644 "${APPIMAGE_PAYLOAD}/suite-pythoine.desktop" "$FINAL_APPDIR/usr/share/applications/suite-pythoine.desktop"
    install -m 0644 "${APPIMAGE_PAYLOAD}/suite-pythoine.png" "$FINAL_APPDIR/suite-pythoine.png"
    ln -s suite-pythoine.png "$FINAL_APPDIR/.DirIcon"
    install -m 0644 "${APPIMAGE_PAYLOAD}/io.github.brunonlinespace.suite-pythoine.metainfo.xml" \
        "$FINAL_APPDIR/usr/share/metainfo/io.github.brunonlinespace.suite-pythoine.metainfo.xml"

    for size in 16 24 32 48 64 128 256 512; do
        target="$FINAL_APPDIR/usr/share/icons/hicolor/${size}x${size}/apps"
        mkdir -p "$target"
        install -m 0644 "${ASSET_DIR}/suite-pythoine-${size}.png" "$target/suite-pythoine.png"
    done

    install -m 0644 "${PROJECT_ROOT}/COPYING" "$FINAL_APPDIR/usr/share/doc/suite-pythoine/COPYING"
    install -m 0644 "${DOCS_DIR}/README.md" "$FINAL_APPDIR/usr/share/doc/suite-pythoine/README.md"
    install -m 0644 "${DOCS_DIR}/QA.md" "$FINAL_APPDIR/usr/share/doc/suite-pythoine/QA.md"
    install -m 0644 "${DOCS_DIR}/RELEASE_NOTES.md" "$FINAL_APPDIR/usr/share/doc/suite-pythoine/RELEASE_NOTES.md"
    chmod 0755 "$FINAL_APPDIR/usr/lib/suite-pythoine/suite-pythoine"

    validate_desktop_entry_basic "$FINAL_APPDIR/suite-pythoine.desktop"
    validate_desktop_entry_basic "$FINAL_APPDIR/usr/share/applications/suite-pythoine.desktop"
    validate_appstream_basic "$FINAL_APPDIR/usr/share/metainfo/io.github.brunonlinespace.suite-pythoine.metainfo.xml"
    if command -v desktop-file-validate >/dev/null 2>&1; then
        desktop-file-validate "$FINAL_APPDIR/suite-pythoine.desktop"
        desktop-file-validate "$FINAL_APPDIR/usr/share/applications/suite-pythoine.desktop"
    else
        printf 'Info: desktop-file-validate unavailable; built-in checks passed.\n' >&2
    fi
    if command -v appstreamcli >/dev/null 2>&1; then
        appstreamcli validate --no-net \
            "$FINAL_APPDIR/usr/share/metainfo/io.github.brunonlinespace.suite-pythoine.metainfo.xml"
    else
        printf 'Info: appstreamcli unavailable; built-in AppStream checks passed.\n' >&2
    fi
}

run_smoke_test() {
    local label="$1"; shift
    local smoke_log status
    rm -rf "$SMOKE_HOME"
    mkdir -p "$SMOKE_HOME/.config" "$SMOKE_HOME/.cache" "$SMOKE_HOME/.local/share" "$SMOKE_HOME/Documents"
    smoke_log="$(mktemp "${TMPDIR:-/tmp}/suite-pythoine-smoke.XXXXXX.log")"
    log "Running ${label} off-screen GUI smoke test"
    set +e
    timeout 30s env \
        HOME="$SMOKE_HOME" \
        XDG_CONFIG_HOME="$SMOKE_HOME/.config" \
        XDG_CACHE_HOME="$SMOKE_HOME/.cache" \
        XDG_DATA_HOME="$SMOKE_HOME/.local/share" \
        QT_QPA_PLATFORM=offscreen \
        QT_QUICK_BACKEND=software \
        "$@" --suite-pythoine-smoke-test >"$smoke_log" 2>&1
    status=$?
    set -e
    if [[ "$status" -ne 0 ]] || ! grep -Fq 'GUI smoke test passed.' "$smoke_log"; then
        cat "$smoke_log" >&2
        rm -f "$smoke_log"
        die "${label} GUI smoke test failed with exit code ${status}."
    fi
    rm -f "$smoke_log"
}

run_version_smoke_test() {
    local label="$1"; shift
    local smoke_log expected status
    expected="${APP_NAME} ${APP_VERSION}"
    smoke_log="$(mktemp "${TMPDIR:-/tmp}/suite-pythoine-version.XXXXXX.log")"
    log "Running ${label} version smoke test"
    set +e
    timeout 30s env QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software \
        "$@" --version >"$smoke_log" 2>&1
    status=$?
    set -e
    if [[ "$status" -ne 0 ]] || ! grep -Fxq "$expected" "$smoke_log"; then
        cat "$smoke_log" >&2
        rm -f "$smoke_log"
        die "${label} version smoke test failed with exit code ${status}."
    fi
    rm -f "$smoke_log"
}

validate_bundle() {
    log "Validating Qt bundle"
    find "$FINAL_APPDIR/usr/lib/suite-pythoine" -name 'libqxcb.so' -print -quit | grep -q . \
        || die "Qt XCB platform plugin was not bundled."
    find "$FINAL_APPDIR/usr/lib/suite-pythoine" \
        \( -name 'libqwayland*.so' -o -name '*wayland*.so' \) -print -quit | grep -q . \
        || printf 'Warning: Qt Wayland plugin was not detected; test XWayland carefully.\n' >&2
    if find "$FINAL_APPDIR/usr/lib/suite-pythoine" -iname '*WebEngine*' -print -quit | grep -q .; then
        die "Qt WebEngine was bundled unexpectedly; Suite Pythoine does not require it."
    fi
    run_smoke_test "AppDir" "$FINAL_APPDIR/AppRun"
    run_version_smoke_test "AppDir" "$FINAL_APPDIR/AppRun"
}

elf_sanity_check() {
    local tool="$1" magic size
    require_file "$tool"
    size="$(stat -c %s "$tool")"
    [[ "$size" -gt 0 && "$size" -le "$MAX_TOOL_BYTES" ]] \
        || die "appimagetool invalid size: ${size} bytes."
    magic="$(od -An -tx1 -N4 "$tool" | tr -d ' \n')"
    [[ "$magic" == "7f454c46" ]] || die "appimagetool is not an ELF executable: $tool"
}

download_tool() {
    local url="$1"
    local destination="$2"
    local part="${destination}.part"
    [[ "$url" == https://* ]] || die "appimagetool URL must use HTTPS."
    rm -f "$part"
    if command -v curl >/dev/null 2>&1; then
        curl --proto '=https' --tlsv1.2 --fail --location --retry 3 --retry-all-errors \
            --connect-timeout 30 --max-time 300 --max-filesize "$MAX_TOOL_BYTES" \
            --output "$part" "$url"
    else
        wget --https-only --tries=3 --timeout=30 --output-document="$part" "$url"
    fi
    [[ -f "$part" ]] || die "appimagetool download produced no file."
    elf_sanity_check "$part"
    chmod 0755 "$part"
    mv -f "$part" "$destination"
}

prepare_appimagetool() {
    local tool url
    mkdir -p "$CACHE_DIR"
    chmod 0700 "$CACHE_DIR"
    if [[ -n "${APPIMAGETOOL_PATH:-}" ]]; then
        tool="$(readlink -f -- "$APPIMAGETOOL_PATH")"
        [[ -x "$tool" ]] || die "APPIMAGETOOL_PATH is not executable: $tool"
        log "Using appimagetool supplied through APPIMAGETOOL_PATH"
    else
        tool="${CACHE_DIR}/appimagetool-${ARCH}.AppImage"
        url="${APPIMAGETOOL_URL:-https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${ARCH}.AppImage}"
        if [[ ! -x "$tool" ]]; then
            log "Downloading official appimagetool"
            download_tool "$url" "$tool"
        else
            log "Using cached appimagetool"
        fi
    fi
    elf_sanity_check "$tool"
    if [[ -n "${APPIMAGETOOL_SHA256:-}" ]]; then
        [[ "$APPIMAGETOOL_SHA256" =~ ^[[:xdigit:]]{64}$ ]] \
            || die "APPIMAGETOOL_SHA256 must be 64 hexadecimal characters."
        printf '%s  %s\n' "$APPIMAGETOOL_SHA256" "$tool" | sha256sum --check --status \
            || die "appimagetool SHA-256 verification failed."
    elif [[ "${SUITE_PYTHOINE_RELEASE_BUILD:-0}" == "1" ]]; then
        die "SUITE_PYTHOINE_RELEASE_BUILD=1 requires APPIMAGETOOL_SHA256."
    else
        printf 'Warning: APPIMAGETOOL_SHA256 not supplied; resolved hash will be recorded.\n' >&2
    fi
    APPIMAGETOOL_RESOLVED="$tool"
}

build_appimage() {
    prepare_appimagetool
    log "Creating ${APPIMAGE##*/}"
    rm -f "$APPIMAGE" "$SHA_FILE"
    ARCH="$ARCH" VERSION="$APP_VERSION" \
        "$APPIMAGETOOL_RESOLVED" --appimage-extract-and-run "$FINAL_APPDIR" "$APPIMAGE"
    [[ -s "$APPIMAGE" ]] || die "appimagetool did not create expected output."
    chmod 0755 "$APPIMAGE"
    run_smoke_test "final AppImage" "$APPIMAGE" --appimage-extract-and-run
    run_version_smoke_test "final AppImage" "$APPIMAGE" --appimage-extract-and-run
    (cd "$DIST_DIR" && sha256sum "${APPIMAGE##*/}" > "${SHA_FILE##*/}")
}

write_build_info() {
    {
        echo "Suite Pythoine AppImage build"
        echo "Version: ${APP_VERSION}"
        echo "Architecture: ${ARCH}"
        echo "Release mode: ${SUITE_PYTHOINE_RELEASE_BUILD:-0}"
        echo "Built: $(date --iso-8601=seconds)"
        echo "Host: ${HOST_NAME}"
        echo "Fedora release: ${FEDORA_RELEASE}"
        echo "Privilege policy: non-privileged; no sudo/dnf/su/pkexec"
        echo "System Python: $(python3 --version 2>&1)"
        echo "Build Python: $("$VENV/bin/python" --version 2>&1)"
        echo "PyInstaller: $("$VENV/bin/pyinstaller" --version)"
        "$VENV/bin/python" - <<'PYVERS'
from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR
print(f"PyQt6: {PYQT_VERSION_STR}")
print(f"Qt: {QT_VERSION_STR}")
PYVERS
        echo "main.py SHA-256: $(sha256sum "$SOURCE_ENTRY" | awk '{print $1}')"
        echo "SOURCE_MANIFEST.sha256 SHA-256: $(sha256sum "$SOURCE_MANIFEST" | awk '{print $1}')"
        echo "Runtime requirements SHA-256: $(sha256sum "$RUNTIME_REQUIREMENTS" | awk '{print $1}')"
        echo "Build requirements SHA-256: $(sha256sum "$BUILD_REQUIREMENTS" | awk '{print $1}')"
        echo "Builder SHA-256: $(sha256sum "$0" | awk '{print $1}')"
        echo "appimagetool: ${APPIMAGETOOL_RESOLVED}"
        echo "appimagetool SHA-256: $(sha256sum "$APPIMAGETOOL_RESOLVED" | awk '{print $1}')"
        echo "Output: ${APPIMAGE##*/}"
        echo "Output SHA-256: $(sha256sum "$APPIMAGE" | awk '{print $1}')"
        echo "Desktop routing: complete pad-family MIME union"
        echo "Smoke tests: AppDir GUI PASS + version PASS; final AppImage GUI PASS + version PASS"
        echo "Source cleanliness: __pycache__/pyc/pyo removed before QA/build and at exit"
    } > "$BUILD_INFO"
}

main() {
    check_non_privileged_policy
    check_host_prerequisites
    check_inputs
    clean_source_python_caches
    run_release_qa
    clean_source_python_caches
    prepare_environment
    freeze_application
    assemble_appdir
    validate_bundle
    build_appimage
    write_build_info
    clean_source_python_caches
    log "Build complete"
    printf 'AppImage: %s\nChecksum: %s\nBuild information: %s\nPython lock: %s\n' \
        "$APPIMAGE" "$SHA_FILE" "$BUILD_INFO" "$PYTHON_LOCK"
}

main "$@"
