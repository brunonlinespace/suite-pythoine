from __future__ import annotations

from pathlib import Path
import os
import shutil
import uuid

from .installer import synchronize_desktop_integration
from .managed_registry import ensure_registry, set_desktop_version
from .storage_layout import is_within


class RootTransitionError(RuntimeError):
    pass


def _copy_version(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise RootTransitionError(f"Destination already exists: {destination}")
    staged = destination.parent / f".{destination.name}.root-migration-{uuid.uuid4().hex[:10]}"
    try:
        shutil.copytree(source, staged, symlinks=False)
        os.replace(staged, destination)
    finally:
        if staged.exists():
            shutil.rmtree(staged, ignore_errors=True)


def _mapped_path(path_value: object, old_root: Path, new_root: Path) -> str | None:
    if not isinstance(path_value, str) or not path_value.strip():
        return path_value if isinstance(path_value, str) else None
    path = Path(path_value).expanduser().resolve(strict=False)
    if not is_within(path, old_root):
        return str(path)
    relative = path.relative_to(old_root)
    mapped = (new_root / relative).resolve(strict=False)
    return str(mapped)


def transition_legacy_default_root(old_root: Path, new_root: Path, config_data: dict) -> tuple[tuple[Path, ...], tuple[str, ...]]:
    """Copy the old unified root into the 0.3 canonical root, then retire copies.

    Existing destination versions are never merged or overwritten. The old
    version remains in place when a collision or copy failure occurs.
    """
    old_root = old_root.expanduser().resolve(strict=False)
    new_root = new_root.expanduser().resolve(strict=False)
    if old_root == new_root or not old_root.is_dir():
        return (), ()
    new_root.mkdir(parents=True, exist_ok=True)

    copied_sources: list[Path] = []
    skipped: list[str] = []
    try:
        applications = sorted(
            (path for path in old_root.iterdir() if path.is_dir() and not path.is_symlink() and not path.name.startswith(".")),
            key=lambda path: path.name.casefold(),
        )
    except OSError as exc:
        raise RootTransitionError(str(exc)) from exc

    for application in applications:
        try:
            versions = sorted(
                (path for path in application.iterdir() if path.is_dir() and not path.is_symlink() and not path.name.startswith(".")),
                key=lambda path: path.name.casefold(),
            )
        except OSError as exc:
            skipped.append(f"{application.name}: {exc}")
            continue
        for version in versions:
            destination = new_root / application.name / version.name
            if destination.exists():
                skipped.append(f"{application.name} {version.name}: destination already exists")
                continue
            try:
                _copy_version(version, destination)
                copied_sources.append(version)
            except (OSError, RootTransitionError) as exc:
                skipped.append(f"{application.name} {version.name}: {exc}")

    # Rewrite exact managed paths only after the corresponding new path exists.
    registry = ensure_registry(config_data)
    for component_id, group in list(registry.items()):
        versions = group.get("versions", {}) if isinstance(group, dict) else {}
        if not isinstance(versions, dict):
            continue
        for version, record in versions.items():
            if not isinstance(record, dict):
                continue
            for key in ("appimage_path", "icon_path", "build_script"):
                mapped = _mapped_path(record.get(key), old_root, new_root)
                if mapped and Path(mapped).exists():
                    record[key] = mapped
            appimage_value = record.get("appimage_path")
            if isinstance(appimage_value, str) and appimage_value and Path(appimage_value).is_file():
                record["desktop_integrated"] = bool(group.get("desktop_version") == version)
        registry[component_id] = group

    # Advanced external launcher overrides can also point into the old root.
    overrides = config_data.get("editor_overrides")
    if isinstance(overrides, dict):
        for override in overrides.values():
            if not isinstance(override, dict):
                continue
            mapped = _mapped_path(override.get("installed_path"), old_root, new_root)
            if mapped and Path(mapped).exists():
                override["installed_path"] = mapped

    # Recreate the single desktop integration for each component from the
    # rewritten exact registry path. This makes the root transition self-healing.
    for component_id, group in list(registry.items()):
        if not isinstance(group, dict):
            continue
        desktop_version = group.get("desktop_version")
        versions = group.get("versions", {})
        if not isinstance(desktop_version, str) or not isinstance(versions, dict):
            continue
        record = versions.get(desktop_version)
        if not isinstance(record, dict):
            continue
        raw_appimage = record.get("appimage_path")
        if not isinstance(raw_appimage, str) or not Path(raw_appimage).is_file():
            continue
        appimage = Path(raw_appimage).resolve(strict=False)
        icon = Path(record["icon_path"]).resolve(strict=False) if isinstance(record.get("icon_path"), str) and Path(record["icon_path"]).is_file() else None
        name = str(group.get("name") or record.get("name") or component_id)
        portable = appimage.parent.parent / "Portable"
        desktop = synchronize_desktop_integration(name, component_id, appimage, icon, portable if portable.is_dir() else None)
        record["desktop_file_path"] = str(desktop)
        set_desktop_version(config_data, component_id, desktop_version, desktop)

    config_data["editors_root"] = str(new_root)
    config_data["legacy_installed_editors_dir"] = None
    config_data["storage_layout_version"] = 3
    config_data["canonical_root_transition_dismissed"] = not bool(skipped)
    config_data["routing_index"] = {}

    # New copies and integration are now complete. Remove only versions that
    # were successfully copied; collided/failed versions remain untouched.
    for source in copied_sources:
        try:
            shutil.rmtree(source)
            parent = source.parent
            if parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
        except OSError:
            skipped.append(f"Could not remove migrated source: {source}")
    try:
        if old_root.is_dir() and not any(old_root.iterdir()):
            old_root.rmdir()
    except OSError:
        pass
    return tuple(copied_sources), tuple(skipped)
