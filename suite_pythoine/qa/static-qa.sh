#!/usr/bin/env bash
set -Eeuo pipefail
export PYTHONDONTWRITEBYTECODE=1
PROGRAM_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
PROJECT_ROOT="$(cd -- "$PROGRAM_ROOT/.." && pwd -P)"
VERSION="1.0.0-x2.6"
TEMP="$(mktemp -d -t suitex10-qa-XXXXXXXX)"
trap 'rm -rf -- "$TEMP"' EXIT
export XDG_CONFIG_HOME="$TEMP/xdg-config"
export XDG_DATA_HOME="$TEMP/xdg-data"
mkdir -p "$XDG_CONFIG_HOME" "$XDG_DATA_HOME"
PYTHONPYCACHEPREFIX="$TEMP/python-bytecode" python3 -m compileall -q "$PROJECT_ROOT/main.py" "$PROGRAM_ROOT"
echo 'PASS: Python source compilation'
(cd "$PROJECT_ROOT" && python3 main.py --version) | grep -Fx "Suite Pythoine $VERSION" >/dev/null
echo 'PASS: Portable version launcher'
bash -n "$PROGRAM_ROOT/packaging/fedora/build-appimage.sh"
bash -n "$PROGRAM_ROOT/packaging/fedora/test-appimage.sh"
bash -n "$PROGRAM_ROOT/portable/run-suite-pythoine.sh"
sh -n "$PROGRAM_ROOT/packaging/appimage/AppRun"
echo 'PASS: Shell script syntax'
(cd "$PROJECT_ROOT" && python3 -m suite_pythoine.tools.release_check)
echo 'PASS: Strict manifest and headless lifecycle/security gate'
printf 'PASS: Suite Pythoine %s static QA completed\n' "$VERSION"
