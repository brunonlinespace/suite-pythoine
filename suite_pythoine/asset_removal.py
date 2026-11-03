"""Transactional removal of explicitly selected managed runtime/Recovery assets.

0.10.4 exposes this engine through Installed Applications → Remove Assets….
It deliberately operates on exact assets, not whole applications.  The same
Qt-free engine is intended to back Developer-mode Prune presets later.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import os
import shutil
import uuid

from .installer import (
    InstallError,
    delete_staged_portable_folder,
    desktop_entry_path,
    desktop_entry_status,
    finalize_staged_registered_integration,
    portable_desktop_entry_status,
    restore_staged_portable_folder,
    restore_staged_registered_integration,
    stage_portable_editor_folder,
    stage_registered_appimage_integration,
)
from .installation_state import desktop_id_for
from .purge_assets import (
    delete_staged_recovery_folder,
    restore_staged_recovery_folder,
    stage_recovery_folder,
)
from .storage_layout import prune_empty_version_tree, validate_version_boundary

ASSET_TYPES = frozenset({"Portable", "AppImage", "Recovery"})


@dataclass(frozen=True, slots=True)
class RemovalAsset:
    component_id: str
    name: str
    version: str
    asset_type: str
    path: Path
    portable_command: tuple[str, ...] | None = None
    appimage_icon: Path | None = None
    protected: bool = False
    protection_reason: str = ""


@dataclass(frozen=True, slots=True)
class RemovalResult:
    removed_assets: tuple[RemovalAsset, ...]
    desktop_components: tuple[str, ...]
    version_roots: tuple[Path, ...]
    pruned_directories: tuple[Path, ...]


class AssetRemovalFailure(InstallError):
    """Transactional removal failure with user-reportable rollback state."""

    def __init__(self, message: str, *, rollback_status: str, partial: bool) -> None:
        super().__init__(message)
        self.rollback_status = rollback_status
        self.partial = bool(partial)


def _version_root(asset: RemovalAsset) -> Path:
    path = asset.path.expanduser().absolute()
    if asset.asset_type in {"Portable", "Recovery"}:
        return path.parent
    if asset.asset_type == "AppImage":
        return path.parent.parent
    raise InstallError(f"Unsupported managed asset type: {asset.asset_type}")


def _validate_asset(asset: RemovalAsset, editors_root: Path) -> Path:
    if asset.asset_type not in ASSET_TYPES:
        raise InstallError(f"Unsupported managed asset type: {asset.asset_type}")
    if asset.protected:
        reason = asset.protection_reason or "This managed asset is protected."
        raise InstallError(f"{asset.name} {asset.version} {asset.asset_type}: {reason}")
    if not asset.component_id or not asset.version:
        raise InstallError("Managed asset identity is incomplete.")

    root = editors_root.expanduser().resolve(strict=False)
    version_dir = _version_root(asset)
    validate_version_boundary(version_dir, root)
    if version_dir.name != asset.version or version_dir.parent.parent.resolve(strict=False) != root:
        raise InstallError(f"Unexpected exact-version boundary: {version_dir}")

    path = asset.path.expanduser().absolute()
    if asset.asset_type == "Portable":
        if path.name != "Portable" or path.parent != version_dir or path.is_symlink() or not path.is_dir():
            raise InstallError(f"Portable asset is absent or unsafe: {path}")
    elif asset.asset_type == "Recovery":
        if path.name != "Recovery" or path.parent != version_dir or path.is_symlink() or not path.is_dir():
            raise InstallError(f"Recovery asset is absent or unsafe: {path}")
    else:
        if (path.parent.name != "AppImage" or path.parent.parent != version_dir
                or path.is_symlink() or not path.is_file()):
            raise InstallError(f"AppImage asset is absent or unsafe: {path}")
    return version_dir


def _portable_owns_desktop(asset: RemovalAsset) -> bool:
    if not asset.portable_command:
        return False
    return portable_desktop_entry_status(
        asset.component_id,
        asset.portable_command,
        desktop_path=desktop_entry_path(asset.component_id),
        desktop_id=desktop_id_for(asset.component_id),
    ) == "ready"


def _appimage_owns_desktop(asset: RemovalAsset) -> bool:
    return desktop_entry_status(
        asset.component_id,
        asset.path,
        desktop_path=desktop_entry_path(asset.component_id),
        desktop_id=desktop_id_for(asset.component_id),
    ) == "ready"


def _stage_portable_desktop(asset: RemovalAsset) -> tuple[Path, Path] | None:
    if not _portable_owns_desktop(asset):
        return None
    original = desktop_entry_path(asset.component_id).expanduser().absolute()
    if original.is_symlink() or not original.is_file():
        raise InstallError(f"Verified desktop entry changed before removal: {original}")
    staged = original.parent / f".{original.name}.asset-removal-{uuid.uuid4().hex[:10]}"
    os.replace(original, staged)
    return original, staged


def _restore_file_pair(pair: tuple[Path, Path]) -> None:
    original, staged = pair
    if staged.exists() and not original.exists():
        os.replace(staged, original)


def _finalize_file_pair(pair: tuple[Path, Path]) -> None:
    _original, staged = pair
    if staged.exists() or staged.is_symlink():
        staged.unlink()


def remove_assets(
    assets: list[RemovalAsset] | tuple[RemovalAsset, ...],
    *,
    editors_root: Path,
    pre_finalize: Callable[[], None] | None = None,
) -> RemovalResult:
    """Remove only the selected exact assets, staging every target before cleanup.

    If a selected runtime currently owns Suite's verified desktop launcher, that
    launcher is staged with the runtime so removal never leaves a launcher that
    points at a deleted executable.  No replacement runtime is selected here.
    """
    selected = tuple(assets)
    if not selected:
        raise InstallError("No managed assets were selected for removal.")

    seen: set[tuple[str, str, str]] = set()
    version_roots: list[Path] = []
    for asset in selected:
        key = (asset.component_id, asset.version, asset.asset_type)
        if key in seen:
            raise InstallError(f"Duplicate selected asset: {asset.name} {asset.version} {asset.asset_type}")
        seen.add(key)
        version_dir = _validate_asset(asset, editors_root)
        if version_dir not in version_roots:
            version_roots.append(version_dir)

    staged_portables: list[tuple[RemovalAsset, Path, Path]] = []
    staged_recoveries: list[tuple[RemovalAsset, Path, Path]] = []
    staged_appimages: list[tuple[RemovalAsset, list[tuple[Path, Path]]]] = []
    staged_desktops: list[tuple[str, tuple[Path, Path]]] = []
    desktop_components: set[str] = set()
    cleanup_started = False

    try:
        for asset in selected:
            if asset.asset_type == "Portable":
                # Verify/stage an owning launcher while the Portable runtime is
                # still at its exact path. portable_desktop_entry_status()
                # intentionally requires the executable/launcher to exist.
                desktop_pair = _stage_portable_desktop(asset)
                if desktop_pair is not None:
                    staged_desktops.append((asset.component_id, desktop_pair))
                    desktop_components.add(asset.component_id)
                original, staged = stage_portable_editor_folder(asset.path, editors_root)
                staged_portables.append((asset, original, staged))
            elif asset.asset_type == "Recovery":
                original, staged = stage_recovery_folder(asset.path, editors_root, asset.version)
                staged_recoveries.append((asset, original, staged))
            else:
                owns_desktop = _appimage_owns_desktop(asset)
                record = {
                    "appimage_path": str(asset.path),
                    "icon_path": str(asset.appimage_icon) if asset.appimage_icon is not None else None,
                    "desktop_integrated": owns_desktop,
                    "desktop_file_path": str(desktop_entry_path(asset.component_id)) if owns_desktop else None,
                }
                pairs = stage_registered_appimage_integration(record, installed_dir=editors_root)
                staged_appimages.append((asset, pairs))
                if owns_desktop:
                    desktop_components.add(asset.component_id)

        if pre_finalize is not None:
            pre_finalize()
        cleanup_started = True
        for _asset, original, staged in staged_portables:
            delete_staged_portable_folder(original, staged, editors_root)
        for _asset, original, staged in staged_recoveries:
            delete_staged_recovery_folder(original, staged, editors_root)
        for _asset, pairs in staged_appimages:
            finalize_staged_registered_integration(pairs)
        for _component_id, pair in staged_desktops:
            _finalize_file_pair(pair)

        pruned_directories: list[Path] = []
        app_roots = {version_dir.parent for version_dir in version_roots}
        for version_dir in sorted(version_roots, key=lambda path: len(path.parts), reverse=True):
            prune_empty_version_tree(version_dir, editors_root)
            if not version_dir.exists():
                pruned_directories.append(version_dir)
        for app_root in sorted(app_roots, key=lambda path: len(path.parts), reverse=True):
            if not app_root.exists():
                pruned_directories.append(app_root)
    except Exception as exc:
        if not cleanup_started:
            rollback_errors: list[str] = []
            for _component_id, pair in reversed(staged_desktops):
                try:
                    _restore_file_pair(pair)
                except OSError as restore_exc:
                    rollback_errors.append(str(restore_exc))
            for _asset, pairs in reversed(staged_appimages):
                try:
                    restore_staged_registered_integration(pairs)
                except Exception as restore_exc:
                    rollback_errors.append(str(restore_exc))
            for asset, original, staged in reversed(staged_recoveries):
                try:
                    restore_staged_recovery_folder(original, staged, editors_root)
                except Exception as restore_exc:
                    rollback_errors.append(f"{asset.name} {asset.version} Recovery: {restore_exc}")
            for asset, original, staged in reversed(staged_portables):
                try:
                    restore_staged_portable_folder(original, staged, editors_root)
                except Exception as restore_exc:
                    rollback_errors.append(f"{asset.name} {asset.version} Portable: {restore_exc}")
            if rollback_errors:
                raise AssetRemovalFailure(
                    f"Asset removal stopped: {exc}",
                    rollback_status="Rollback incomplete: " + "; ".join(rollback_errors),
                    partial=True,
                ) from exc
            raise AssetRemovalFailure(
                f"Asset removal stopped: {exc}",
                rollback_status="Rollback completed before irreversible cleanup; selected assets were restored.",
                partial=False,
            ) from exc
        raise AssetRemovalFailure(
            f"Asset removal stopped during final cleanup: {exc}",
            rollback_status="Final cleanup had already begun, so automatic rollback was not attempted; some selected assets may already be removed.",
            partial=True,
        ) from exc

    return RemovalResult(
        selected, tuple(sorted(desktop_components)), tuple(version_roots), tuple(pruned_directories)
    )
