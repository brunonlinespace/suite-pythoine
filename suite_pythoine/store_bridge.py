from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import shutil
import stat
import sys
from tempfile import NamedTemporaryFile

from . import APP_NAME, __version__
from .config import ConfigService, default_config_path
from .install_inspection import inspect_editor_zip
from .appimage_inspection import inspect_appimage
from .installer import InstallError
from .registry import discover_editors
from .storage_layout import editors_root_default

STORE_PROTOCOL_VERSION = 1
CONTROL_BRIDGE_NAME = "suite-pythoine"
DESKTOP_ID = "io.github.brunonlinespace.suite-pythoine"



def _components_root(config: ConfigService) -> Path:
    raw = config.get("editors_root")
    if isinstance(raw, str) and raw.strip():
        return Path(raw).expanduser().resolve(strict=False)
    return editors_root_default()


def _host_python() -> str | None:
    override = os.environ.get("SUITE_PYTHOINE_PYTHON", "").strip()
    if override:
        return shutil.which(override) or (str(Path(override).expanduser().resolve(strict=False)) if Path(override).expanduser().is_file() else None)
    if not os.environ.get("APPIMAGE") and not getattr(sys, "frozen", False):
        return str(Path(sys.executable).resolve())
    return shutil.which("python3") or shutil.which("python")


def managed_inventory(*, launcher_file: str | Path | None = None) -> dict:
    """Return Store-facing installed state without granting Store write access.

    This is a read-only projection of Suite's own discovery/managed state. Store
    Pythoine consumes the JSON; it never reads or edits Suite's registry files.
    """
    config = ConfigService(default_config_path())
    root = _components_root(config)
    components = []
    if root.is_dir():
        components = discover_editors(root, root, config.as_dict(), python_executable=_host_python())

    rows: list[dict] = []
    running_suite_present = False
    for component in components:
        selected = component.command()
        for version in component.versions:
            if version.has_portable and version.portable_root is not None:
                active = bool(version.version == component.active_version and version.portable_command and selected == version.portable_command)
                rows.append({
                    "component_id": component.editor_id,
                    "name": component.name,
                    "version": version.version,
                    "runtime": "Portable",
                    "active": active,
                    "path": str(version.portable_root),
                })
                if component.editor_id == "suite-pythoine" and version.version == __version__:
                    running_suite_present = True
            if version.has_appimage and version.appimage_path is not None:
                active = bool(version.version == component.active_version and version.installed_command and selected == version.installed_command)
                rows.append({
                    "component_id": component.editor_id,
                    "name": component.name,
                    "version": version.version,
                    "runtime": "AppImage",
                    "active": active,
                    "path": str(version.appimage_path),
                })
                if component.editor_id == "suite-pythoine" and version.version == __version__:
                    running_suite_present = True

    # A directly-run source/AppImage may sit outside the managed Components tree.
    # Store must still see the Suite runtime that is servicing the query.
    if not running_suite_present:
        if os.environ.get("APPIMAGE"):
            runtime = "AppImage"
            path = str(Path(os.environ["APPIMAGE"]).expanduser().resolve(strict=False))
        else:
            runtime = "Portable"
            launcher = Path(launcher_file).resolve(strict=False) if launcher_file else Path(__file__).resolve().parents[1] / "main.py"
            path = str(launcher.parent)
        rows.append({
            "component_id": "suite-pythoine",
            "name": APP_NAME,
            "version": __version__,
            "runtime": runtime,
            "active": True,
            "path": path,
        })

    rows.sort(key=lambda row: (str(row["name"]).casefold(), str(row["version"]).casefold(), str(row["runtime"]).casefold()))
    return {"protocol": STORE_PROTOCOL_VERSION, "suite_version": __version__, "runtimes": rows}


def inspect_package(package: str | Path) -> dict:
    path = Path(package).expanduser().resolve(strict=False)
    if not path.is_file():
        raise InstallError(f"Package not found: {path}")
    suffix = path.suffix.casefold()
    if suffix == ".zip":
        inspection = inspect_editor_zip(path, python_executable=_host_python())
        return {
            "protocol": STORE_PROTOCOL_VERSION,
            "package_type": "source-zip",
            "component_id": inspection.editor_id,
            "name": inspection.name,
            "version": inspection.version or inspection.builder_version,
            "publisher_id": inspection.publisher_id,
            "path": str(path),
        }
    if suffix == ".appimage":
        inspection = inspect_appimage(path)
        return {
            "protocol": STORE_PROTOCOL_VERSION,
            "package_type": "appimage",
            "component_id": inspection.editor_id,
            "name": inspection.name,
            "version": inspection.version,
            "publisher_id": inspection.publisher_id,
            "path": str(path),
        }
    raise InstallError("Store Pythoine may hand Suite only a source ZIP or AppImage package.")


def control_bridge_path() -> Path | None:
    if not sys.platform.startswith("linux"):
        return None
    return Path.home() / ".local" / "bin" / CONTROL_BRIDGE_NAME


def _bridge_script() -> str:
    # Deliberately dependency-free. The bridge never validates packages or edits
    # Suite state; it only execs the runtime named by Suite's direct desktop entry.
    return r'''#!/usr/bin/env python3
from pathlib import Path
import os
import shlex
import sys

DESKTOP_ID = "io.github.brunonlinespace.suite-pythoine"
FIELD_CODES = {"%f", "%F", "%u", "%U", "%d", "%D", "%n", "%N", "%i", "%c", "%k", "%v", "%m"}
SANITIZE = {
    "APPDIR", "APPIMAGE", "ARGV0", "OWD", "LD_LIBRARY_PATH", "PYTHONHOME", "PYTHONPATH",
    "PYTHONEXECUTABLE", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QML2_IMPORT_PATH", "QML_IMPORT_PATH",
}

base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
desktop = base / "applications" / f"{DESKTOP_ID}.desktop"
try:
    lines = desktop.read_text(encoding="utf-8").splitlines()
except OSError as exc:
    print(f"Suite Pythoine control bridge could not read {desktop}: {exc}", file=sys.stderr)
    raise SystemExit(1)

in_primary = False
exec_value = ""
for raw in lines:
    line = raw.strip()
    if line.startswith("[") and line.endswith("]"):
        in_primary = line == "[Desktop Entry]"
        continue
    if in_primary and line.startswith("Exec="):
        exec_value = line[5:].strip()
        break
if not exec_value:
    print("Suite Pythoine desktop integration has no Exec command. Open Suite and use Repair Desktop Integration.", file=sys.stderr)
    raise SystemExit(1)

try:
    command = [token for token in shlex.split(exec_value) if token not in FIELD_CODES]
except ValueError as exc:
    print(f"Suite Pythoine desktop Exec command is invalid: {exc}", file=sys.stderr)
    raise SystemExit(1)
if not command:
    print("Suite Pythoine desktop integration has no executable command.", file=sys.stderr)
    raise SystemExit(1)

env = dict(os.environ)
for name in SANITIZE:
    env.pop(name, None)
for name in ("LD_LIBRARY_PATH", "PYTHONHOME", "PYTHONPATH"):
    original = os.environ.get(f"APPIMAGE_ORIGINAL_{name}")
    if original is not None:
        env[name] = original
    env.pop(f"APPIMAGE_ORIGINAL_{name}", None)

os.execvpe(command[0], [*command, *sys.argv[1:]], env)
'''


def ensure_control_bridge() -> Path | None:
    target = control_bridge_path()
    if target is None:
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    desired = _bridge_script()
    try:
        if target.is_file() and target.read_text(encoding="utf-8") == desired:
            mode = target.stat().st_mode
            if mode & stat.S_IXUSR:
                return target
        temporary: Path | None = None
        with NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, prefix=f".{target.name}.", suffix=".tmp", delete=False) as handle:
            handle.write(desired)
            temporary = Path(handle.name)
        temporary.chmod(0o755)
        temporary.replace(target)
        return target
    except OSError:
        return None


def _value_after(arguments: list[str], flag: str) -> str | None:
    try:
        index = arguments.index(flag)
    except ValueError:
        return None
    return arguments[index + 1] if index + 1 < len(arguments) else ""


def handle_store_protocol_cli(arguments: list[str], *, launcher_file: str | Path | None = None) -> int | None:
    """Handle Store Pythoine's deliberately small Suite control protocol.

    Query/inspection commands remain non-GUI. Installation is the one exception:
    it launches Suite's full normal wizard and never a Store-specific installer.
    """
    recognised = any(flag in arguments for flag in ("--store-protocol-version", "--managed-list", "--inspect-package", "--install-package"))
    if not recognised:
        return None

    if "--store-protocol-version" in arguments:
        if len([flag for flag in ("--managed-list", "--inspect-package", "--install-package") if flag in arguments]):
            print("Use one Store Pythoine protocol command at a time.", file=sys.stderr)
            return 2
        print(STORE_PROTOCOL_VERSION)
        return 0

    if "--managed-list" in arguments:
        if "--json" not in arguments:
            print("--managed-list currently requires --json.", file=sys.stderr)
            return 2
        print(json.dumps(managed_inventory(launcher_file=launcher_file), indent=2, sort_keys=True))
        return 0

    inspect_value = _value_after(arguments, "--inspect-package")
    if inspect_value is not None:
        if not inspect_value or "--json" not in arguments:
            print("Usage: --inspect-package <package> --json", file=sys.stderr)
            return 2
        try:
            payload = inspect_package(inspect_value)
        except (InstallError, OSError) as exc:
            print(json.dumps({"protocol": STORE_PROTOCOL_VERSION, "error": str(exc)}))
            return 1
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    install_value = _value_after(arguments, "--install-package")
    if install_value is not None:
        source = _value_after(arguments, "--source")
        if not install_value or source != "store" or "--wizard" not in arguments:
            print("Store installation requires: --install-package <package> --source store --wizard", file=sys.stderr)
            return 2
        # Import Qt/the main window only for the explicit full-wizard transaction.
        from .app import run_store_install_wizard
        return run_store_install_wizard(Path(install_value), launcher_file=launcher_file)

    return 2
