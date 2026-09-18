#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROGRAM_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd -P)"
VERSION="0.3.3"
ARCH="${ARCH:-$(uname -m)}"
APPIMAGE="${1:-${PROGRAM_ROOT}/dist/Suite-Pythoine-${VERSION}-${ARCH}.AppImage}"
SHA_FILE="${APPIMAGE}.sha256"

[[ -x "$APPIMAGE" ]] || { echo "Missing executable AppImage: $APPIMAGE" >&2; exit 1; }
[[ -f "$SHA_FILE" ]] && (cd "$(dirname "$APPIMAGE")" && sha256sum -c "$(basename "$SHA_FILE")")

"$APPIMAGE" --appimage-extract-and-run --version | grep -F "Suite Pythoine ${VERSION}"
SMOKE_HOME="$(mktemp -d)"
trap 'rm -rf "$SMOKE_HOME"' EXIT
mkdir -p "$SMOKE_HOME/.config" "$SMOKE_HOME/Documents"
timeout 30s env \
    HOME="$SMOKE_HOME" \
    XDG_CONFIG_HOME="$SMOKE_HOME/.config" \
    QT_QPA_PLATFORM=offscreen \
    QT_QUICK_BACKEND=software \
    "$APPIMAGE" --appimage-extract-and-run --suite-pythoine-smoke-test \
    | grep -F 'GUI smoke test passed.'
printf 'Suite Pythoine %s AppImage post-build tests passed.\n' "$VERSION"
