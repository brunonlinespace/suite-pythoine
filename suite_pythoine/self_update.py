from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
from tempfile import NamedTemporaryFile

from .managed_registry import remove_managed_version
from .storage_layout import editors_root_default, is_within, prune_empty_parents, version_root


def _config_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / "brunonlinespace" / "suite-pythoine" / "suite-pythoine.json"
    return Path.home() / ".config" / "brunonlinespace" / "suite-pythoine" / "suite-pythoine.json"


def _atomic_save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
            temporary = Path(handle.name)
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            try:
                temporary.unlink()
            except OSError:
                pass


def complete_pending_self_cleanup(current_version: str, launcher_file: str | Path) -> tuple[str, ...]:
    """Complete a deferred Suite self-update only from the verified new copy.

    0.2.0 never deletes the Suite version that is executing the update wizard.
    The new active version proves it can start by reaching this function from
    its own managed Portable/AppImage directory; only then are superseded Suite
    version directories removed.
    """
    path = _config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return ()
    if not isinstance(data, dict):
        return ()
    pending = data.get("pending_self_cleanup")
    if not isinstance(pending, dict):
        return ()
    target = str(pending.get("target_version") or "").strip()
    if not target or target.casefold() != str(current_version).casefold():
        return ()
    application_name = str(pending.get("application_name") or "Suite Pythoine").strip() or "Suite Pythoine"
    raw_root = pending.get("editors_root") or data.get("editors_root")
    root = Path(str(raw_root)).expanduser().resolve(strict=False) if isinstance(raw_root, str) and raw_root.strip() else editors_root_default()
    target_root = version_root(root, application_name, target).resolve(strict=False)

    # Prove the process that reached the cleanup hook is the new managed copy.
    appimage_env = os.environ.get("APPIMAGE", "").strip()
    if appimage_env:
        running = Path(appimage_env).expanduser().resolve(strict=False)
        if not is_within(running, target_root / "AppImage"):
            return ()
    else:
        running = Path(launcher_file).expanduser().resolve(strict=False)
        if not is_within(running, target_root / "Portable"):
            return ()

    raw_versions = pending.get("remove_versions")
    versions = [str(value).strip() for value in raw_versions] if isinstance(raw_versions, list) else []
    remaining: list[str] = []
    removed: list[str] = []
    for version in versions:
        if not version or version.casefold() == target.casefold():
            continue
        container = version_root(root, application_name, version).resolve(strict=False)
        try:
            if container.exists():
                if container.is_symlink() or not is_within(container, root):
                    raise OSError(f"unsafe self-update cleanup path: {container}")
                shutil.rmtree(container)
                prune_empty_parents(container.parent, root)
            remove_managed_version(data, "suite-pythoine", version)
            removed.append(version)
        except (OSError, ValueError):
            remaining.append(version)

    if remaining:
        pending["remove_versions"] = remaining
        data["pending_self_cleanup"] = pending
    else:
        data.pop("pending_self_cleanup", None)
    try:
        _atomic_save(path, data)
    except OSError:
        return tuple(removed)
    return tuple(removed)
