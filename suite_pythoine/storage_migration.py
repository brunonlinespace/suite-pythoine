from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import uuid

from .installer import (
    InstallError,
    desktop_entry_path,
    install_icon,
    sha256_file,
    write_appimage_metadata,
    synchronize_desktop_integration,
)
from .managed_registry import desktop_id_for, get_managed_installation, set_managed_installation
from .registry import inspect_editor_root
from .storage_layout import appimage_filename, appimage_root, architecture_from_appimage, icon_filename, portable_root, is_within
from .versioning import appimage_metadata_path, installed_version_for_appimage, read_appimage_metadata


@dataclass(frozen=True, slots=True)
class MigrationItem:
    editor_id: str
    name: str
    version: str | None
    portable_source: Path | None
    portable_destination: Path | None
    appimage_source: Path | None
    appimage_destination: Path | None
    icon_source: Path | None
    icon_destination: Path | None
    old_desktop: Path | None
    new_desktop: Path | None

    @property
    def has_work(self) -> bool:
        return bool(
            (self.portable_source and self.portable_destination and self.portable_source != self.portable_destination)
            or (self.appimage_source and self.appimage_destination and self.appimage_source != self.appimage_destination)
            or (self.old_desktop and self.new_desktop and self.old_desktop != self.new_desktop)
        )


@dataclass(frozen=True, slots=True)
class MigrationPlan:
    editors_root: Path
    legacy_portable_root: Path | None
    items: tuple[MigrationItem, ...]
    skipped: tuple[str, ...] = ()

    @property
    def has_work(self) -> bool:
        return any(item.has_work for item in self.items)


def _legacy_portable_folders(root: Path | None) -> list[Path]:
    if root is None or not root.is_dir():
        return []
    try:
        return sorted(
            (p for p in root.iterdir() if p.is_dir() and not p.is_symlink() and not p.name.startswith(".")),
            key=lambda p: p.name.casefold(),
        )
    except OSError:
        return []


def _registered_old_appimage(config: dict, editor_id: str, editors_root: Path, legacy_installed_root: Path | None = None) -> tuple[Path | None, Path | None, Path | None]:
    record = get_managed_installation(config, editor_id)
    if not record:
        return None, None, None
    raw = record.get("appimage_path")
    if not isinstance(raw, str) or not raw.strip():
        return None, None, None
    appimage = Path(raw).expanduser().resolve(strict=False)
    allowed = is_within(appimage, editors_root) or (legacy_installed_root is not None and is_within(appimage, legacy_installed_root))
    if not appimage.is_file() or not allowed:
        return None, None, None
    # New-layout artifacts already live in .../<Version>/AppImage/. Old custom
    # installed roots may be outside the new Editors root and are still valid
    # explicit migration inputs.
    if is_within(appimage, editors_root):
        try:
            rel = appimage.relative_to(editors_root)
        except ValueError:
            rel = None
        if rel is not None and len(rel.parts) >= 4 and rel.parts[-2].casefold() == "appimage":
            return None, None, None
    icon = None
    raw_icon = record.get("icon_path")
    if isinstance(raw_icon, str) and raw_icon.strip():
        candidate = Path(raw_icon).expanduser().resolve(strict=False)
        if candidate.is_file() and (is_within(candidate, editors_root) or (legacy_installed_root is not None and is_within(candidate, legacy_installed_root))):
            icon = candidate
    desktop = None
    raw_desktop = record.get("desktop_file_path")
    if isinstance(raw_desktop, str) and raw_desktop.strip():
        desktop = Path(raw_desktop).expanduser().resolve(strict=False)
    return appimage, icon, desktop


def build_migration_plan(
    editors_root: Path,
    legacy_portable_root: Path | None,
    config: dict,
    *,
    python_executable: str | None,
    legacy_installed_root: Path | None = None,
) -> MigrationPlan:
    root = editors_root.expanduser().resolve(strict=False)
    legacy = legacy_portable_root.expanduser().resolve(strict=False) if legacy_portable_root else None
    legacy_installed = legacy_installed_root.expanduser().resolve(strict=False) if legacy_installed_root else None
    items_by_id: dict[str, MigrationItem] = {}
    skipped: list[str] = []

    for folder in _legacy_portable_folders(legacy):
        # Do not interpret the new application/version hierarchy as legacy.
        if root == legacy and not ((folder / "main.py").is_file() or (folder / "editor.json").is_file() or (folder / "suite-pythoine.json").is_file()):
            continue
        try:
            editor = inspect_editor_root(folder, config=config, installed_dir=root, python_executable=python_executable)
        except Exception as exc:
            skipped.append(f"Could not inspect {folder}: {exc}")
            continue
        version = editor.source_version or "Unknown"
        portable_dest = portable_root(root, editor.name, version).resolve(strict=False)
        appimage, icon, old_desktop = _registered_old_appimage(config, editor.editor_id, root, legacy_installed)
        appimage_dest = None
        icon_dest = None
        if appimage is not None:
            managed_record = get_managed_installation(config, editor.editor_id)
            managed_version = managed_record.get("version") if managed_record else None
            version_for_app = str(managed_version).strip() if isinstance(managed_version, str) and managed_version.strip() else (editor.installed_version or version)
            target_dir = appimage_root(root, editor.name, version_for_app).resolve(strict=False)
            appimage_dest = target_dir / appimage_filename(editor.name, version_for_app, architecture_from_appimage(appimage))
            if icon is not None:
                icon_dest = target_dir / icon_filename(editor.name, icon.suffix.casefold() or ".png")
        new_desktop = desktop_entry_path(editor.editor_id) if appimage is not None else None
        items_by_id[editor.editor_id] = MigrationItem(
            editor.editor_id,
            editor.name,
            editor.source_version or editor.installed_version,
            folder.resolve(strict=False),
            portable_dest,
            appimage,
            appimage_dest,
            icon,
            icon_dest,
            old_desktop,
            new_desktop,
        )

    # Managed installed-only records may have no portable source to identify them.
    managed = config.get("managed_installations", {}) if isinstance(config, dict) else {}
    if isinstance(managed, dict):
        for editor_id in sorted((str(k) for k in managed), key=str.casefold):
            if editor_id in items_by_id:
                continue
            record = get_managed_installation(config, editor_id)
            if not record:
                continue
            appimage, icon, old_desktop = _registered_old_appimage(config, editor_id, root, legacy_installed)
            if appimage is None:
                continue
            name = str(record.get("name") or editor_id)
            version = str(record.get("version") or installed_version_for_appimage(appimage, {}) or "Unknown")
            target_dir = appimage_root(root, name, version).resolve(strict=False)
            appimage_dest = target_dir / appimage_filename(name, version, architecture_from_appimage(appimage))
            icon_dest = target_dir / icon_filename(name, icon.suffix.casefold() or ".png") if icon else None
            items_by_id[editor_id] = MigrationItem(
                editor_id,
                name,
                version,
                None,
                None,
                appimage,
                appimage_dest,
                icon,
                icon_dest,
                old_desktop,
                desktop_entry_path(editor_id),
            )

    return MigrationPlan(root, legacy, tuple(items_by_id.values()), tuple(skipped))


def _copy_tree_transactional(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise InstallError(f"Migration destination already exists: {destination}")
    staged = destination.parent / f".{destination.name}.migrating-{uuid.uuid4().hex[:10]}"
    try:
        shutil.copytree(source, staged)
        os.replace(staged, destination)
    finally:
        if staged.exists():
            shutil.rmtree(staged, ignore_errors=True)


def _copy_file_transactional(source: Path, destination: Path, *, executable: bool = False) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise InstallError(f"Migration destination already exists: {destination}")
    staged = destination.parent / f".{destination.name}.migrating-{uuid.uuid4().hex[:10]}"
    try:
        shutil.copy2(source, staged)
        if executable:
            staged.chmod(staged.stat().st_mode | 0o100)
        os.replace(staged, destination)
    finally:
        if staged.exists():
            staged.unlink(missing_ok=True)


def migrate_item(item: MigrationItem, editors_root: Path, config: dict) -> dict:
    """Migrate one editor while retaining originals until new files are valid."""
    root = editors_root.expanduser().resolve(strict=False)
    created: list[Path] = []
    try:
        if item.portable_source and item.portable_destination and item.portable_source != item.portable_destination:
            if not is_within(item.portable_destination, root):
                raise InstallError("Portable migration destination escaped the Components folder.")
            _copy_tree_transactional(item.portable_source, item.portable_destination)
            created.append(item.portable_destination)

        new_app = None
        new_icon = None
        new_desktop = None
        if item.appimage_source and item.appimage_destination:
            if not is_within(item.appimage_destination, root):
                raise InstallError("AppImage migration destination escaped the Components folder.")
            _copy_file_transactional(item.appimage_source, item.appimage_destination, executable=True)
            created.append(item.appimage_destination)
            new_app = item.appimage_destination
            if item.icon_source and item.icon_destination:
                _copy_file_transactional(item.icon_source, item.icon_destination)
                created.append(item.icon_destination)
                new_icon = item.icon_destination

            template_root = item.portable_destination if item.portable_destination and item.portable_destination.is_dir() else None
            new_desktop = synchronize_desktop_integration(
                item.name,
                item.editor_id,
                new_app,
                new_icon,
                template_root,
                desktop_path=item.new_desktop,
            )
            created.append(new_desktop)
            previous = get_managed_installation(config, item.editor_id)
            managed_version = item.appimage_destination.parent.parent.name
            record = {
                "schema": 1,
                "editor_id": item.editor_id,
                "application_id": item.editor_id,
                "name": item.name,
                "version": managed_version,
                "appimage_path": str(new_app),
                "appimage_sha256": sha256_file(new_app),
                "desktop_file_path": str(new_desktop),
                "desktop_id": desktop_id_for(item.editor_id),
                "icon_path": str(new_icon) if new_icon else None,
                "source_version": previous.get("source_version") or item.version,
                "extensions": previous.get("extensions", []),
                "description": previous.get("description", ""),
            }
            registered = set_managed_installation(config, record)
            write_appimage_metadata(
                new_app,
                editor_id=item.editor_id,
                application_id=registered["application_id"],
                name=item.name,
                version=managed_version,
                desktop_file=new_desktop,
                desktop_id=registered["desktop_id"],
                icon=new_icon,
            )

        # New copies and registry are complete; only now remove old assets.
        if item.portable_source and item.portable_destination and item.portable_source != item.portable_destination:
            shutil.rmtree(item.portable_source)
        if item.appimage_source and item.appimage_destination and item.appimage_source != item.appimage_destination:
            old_meta = appimage_metadata_path(item.appimage_source)
            item.appimage_source.unlink(missing_ok=True)
            old_meta.unlink(missing_ok=True)
        if item.icon_source and item.icon_destination and item.icon_source != item.icon_destination:
            item.icon_source.unlink(missing_ok=True)
        if item.old_desktop and item.new_desktop and item.old_desktop != item.new_desktop:
            item.old_desktop.unlink(missing_ok=True)
        return get_managed_installation(config, item.editor_id)
    except Exception:
        # Originals have not been removed until the end. Best-effort cleanup of
        # newly created copies makes failure non-destructive.
        for path in reversed(created):
            try:
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    path.unlink(missing_ok=True)
            except OSError:
                pass
        raise
