from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

DEVELOPER_CONFIG_SCHEMA = 1


def developer_intake_drop(enabled: bool, name: str, modifiers: int, *,
                          shift_mask: int, other_modifiers: int,
                          forced_override: bool = False) -> bool:
    """Route an unmodified ZIP drop into Developer Intake while Developer Mode is active.

    Shift deliberately bypasses Intake so the normal guided installer remains
    one gesture away; Ctrl is reserved for Recovery-only retention. Alt/Meta or
    legacy forced overrides also bypass this developer default.
    """
    blocked = int(shift_mask) | int(other_modifiers)
    return (bool(enabled) and str(name).casefold().endswith('.zip')
            and not bool(int(modifiers) & blocked)
            and not forced_override)

def developer_retain_drop(enabled: bool, name: str, modifiers: int, *,
                          ctrl_mask: int, other_modifiers: int,
                          forced_override: bool = False) -> bool:
    """Only unambiguous Ctrl+ZIP drop retains Recovery without installation."""
    return (bool(enabled) and str(name).casefold().endswith('.zip')
            and bool(modifiers & ctrl_mask)
            and not bool(modifiers & other_modifiers)
            and not forced_override)


def default_developer_config_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return (base / "brunonlinespace" / "suite-pythoine" / "developer-intake.json").resolve(strict=False)
    # Match RuntimePaths: Developer Intake deliberately lives beside Suite's normal config.
    return (Path.home() / ".config" / "brunonlinespace" / "suite-pythoine" / "developer-intake.json").resolve(strict=False)

def _load(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, ValueError, TypeError):
        raw = {}
    if not isinstance(raw, dict) or raw.get("schema", DEVELOPER_CONFIG_SCHEMA) != DEVELOPER_CONFIG_SCHEMA:
        raw = {}
    return {
        "schema": DEVELOPER_CONFIG_SCHEMA,
        "enabled": bool(raw.get("enabled", False)),
        "app_roots": raw.get("app_roots", {}) if isinstance(raw.get("app_roots", {}), dict) else {},
        "source_relative": str(raw["source_relative"]) if isinstance(raw.get("source_relative"), str) else "1 Source",
        "notes_relative": str(raw["notes_relative"]) if isinstance(raw.get("notes_relative"), str) else "2 Release Notes",
        "delete_zip_after_success": bool(raw.get("delete_zip_after_success", False)),
        "delete_original_after_success": bool(raw.get("delete_original_after_success", False)),
        "readme_filename": str(raw["readme_filename"]) if isinstance(raw.get("readme_filename"), str) else "README.md",
    }

def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
            temporary = Path(handle.name)
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            try: temporary.unlink()
            except OSError: pass

def handle_developer_cli(arguments: list[str]) -> int | None:
    options = {
        "--enable-developer-mode": True,
        "--disable-developer-mode": False,
        "--developer-mode-status": None,
    }
    requested = [arg for arg in arguments if arg in options]
    if not requested:
        return None
    if len(requested) > 1:
        print("Choose only one Developer Mode command.")
        return 2
    option = requested[0]
    path = default_developer_config_path()
    data = _load(path)
    if option == "--developer-mode-status":
        print("enabled" if data["enabled"] else "disabled")
        return 0
    data["enabled"] = bool(options[option])
    try:
        _save(path, data)
    except OSError as exc:
        print(f"Could not update Developer Intake configuration: {exc}")
        return 1
    print("Developer Mode enabled." if data["enabled"] else "Developer Mode disabled.")
    return 0
