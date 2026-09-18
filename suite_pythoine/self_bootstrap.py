from __future__ import annotations

import os
from pathlib import Path
import sys

from .managed_registry import get_managed_group
from .routing_index import load_index
from .silent_dispatch import components_root, host_python, load_config, process_environment

SUITE_ID = "suite-pythoine"
SUITE_NAME = "Suite Pythoine"


def _preferred_runtime(config: dict) -> str:
    overrides = config.get("editor_overrides")
    override = overrides.get(SUITE_ID, {}) if isinstance(overrides, dict) else {}
    mode = str(override.get("launch_mode") or "auto") if isinstance(override, dict) else "auto"
    return mode if mode in {"auto", "portable", "installed"} else "auto"


def _active_version(config: dict) -> str | None:
    overrides = config.get("editor_overrides")
    override = overrides.get(SUITE_ID, {}) if isinstance(overrides, dict) else {}
    requested = str(override.get("active_version") or "").strip() if isinstance(override, dict) else ""
    if requested:
        return requested
    group = get_managed_group(config, SUITE_ID)
    value = group.get("active_version") if group else None
    return str(value).strip() if isinstance(value, str) and value.strip() else None


def _portable_command(config: dict) -> tuple[str, ...] | None:
    root = components_root(config)
    cached = load_index(config, root)
    if cached:
        suite = next((item for item in cached if item.component_id == SUITE_ID), None)
        if suite is not None and suite.portable_command:
            return suite.portable_command
    version = _active_version(config)
    python = host_python()
    if not version or not python:
        return None
    main_py = root / SUITE_NAME / version / "Portable" / "main.py"
    if main_py.is_file():
        return (python, str(main_py.resolve(strict=False)))
    return None


def maybe_exec_preferred_portable() -> str | None:
    """Legacy compatibility helper; normal Suite startup no longer calls this.

    Since exp9-r2 the active Suite runtime owns the desktop entry directly.
    Explicit historical AppImage launches must therefore remain exact-version
    launches rather than being redirected through current shared preferences.
    The helper is retained only so older external integrations importing it do
    not fail; callers must explicitly opt into the legacy bootstrap contract.
    """
    if os.environ.get("SUITE_PYTHOINE_LEGACY_BOOTSTRAP") != "1":
        return None
    if not (bool(os.environ.get("APPIMAGE")) or bool(getattr(sys, "frozen", False))):
        return None
    config = load_config()
    if _preferred_runtime(config) != "portable":
        return None
    command = _portable_command(config)
    if not command:
        return "Portable/source is the preferred Suite Pythoine launch runtime, but the active Portable copy is unavailable. The AppImage is being opened so you can repair the setting."
    environment = process_environment()
    environment["SUITE_PYTHOINE_BOOTSTRAPPED_FROM_APPIMAGE"] = "1"
    try:
        os.execvpe(command[0], list(command), environment)
    except OSError as exc:
        return f"Could not start the preferred Portable Suite Pythoine runtime: {exc}. The AppImage is being opened so you can repair the setting."
