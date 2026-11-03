"""Bounded, rename-first staging of Purge-only managed-version assets.

Individual Portable/AppImage removal never calls these Recovery helpers. The
candidate must be an exact three-level <Component>/<Version>/Recovery child of
the selected managed root; a symlink is never traversed or removed as a folder.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import uuid

from .installer import InstallError, desktop_applications_dir
from .storage_layout import is_within, version_folder_name


def _verify_recovery(path: Path, editors_root: Path, version: str) -> Path:
    root = editors_root.expanduser().resolve(strict=False)
    candidate = path.expanduser().absolute()
    if candidate.is_symlink() or not candidate.is_dir():
        raise InstallError(f"Recovery directory is absent or unsafe: {candidate}")
    if any(part.is_symlink() for part in (candidate.parent, candidate.parent.parent)):
        raise InstallError(f"Refusing to traverse symbolic-link Recovery parents: {candidate}")
    if not is_within(candidate, root):
        raise InstallError(f"Recovery directory is outside the Applications folder: {candidate}")
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise InstallError(f"Recovery directory does not belong to this Applications folder: {candidate}") from exc
    if (len(relative.parts) != 3 or relative.parts[-1] != "Recovery"
            or relative.parts[1] != version_folder_name(version)):
        raise InstallError(f"Refusing to purge a non-versioned Recovery path: {candidate}")
    return candidate


def stage_recovery_folder(path: Path, editors_root: Path, version: str) -> tuple[Path, Path]:
    original = _verify_recovery(path, editors_root, version)
    staged = original.parent / f".Recovery.purging-{uuid.uuid4().hex[:12]}"
    os.replace(original, staged)
    return original, staged


def _verify_stage(original: Path, staged: Path, editors_root: Path) -> None:
    root = editors_root.expanduser().resolve(strict=False)
    if (not is_within(original, root) or not is_within(staged, root)
            or original.name != "Recovery" or staged.parent != original.parent
            or not staged.name.startswith(".Recovery.purging-") or staged.is_symlink()):
        raise InstallError(f"Invalid staged Recovery folder: {staged}")


def restore_staged_recovery_folder(original: Path, staged: Path, editors_root: Path) -> None:
    _verify_stage(original, staged, editors_root)
    if original.exists() or original.is_symlink():
        raise InstallError(f"Cannot restore Recovery over an existing target: {original}")
    if staged.exists():
        os.replace(staged, original)


def delete_staged_recovery_folder(original: Path, staged: Path, editors_root: Path) -> None:
    _verify_stage(original, staged, editors_root)
    if staged.exists():
        try:
            shutil.rmtree(staged)
        except OSError as exc:
            raise InstallError(f"Could not finalize Recovery purge {staged}: {exc}") from exc


def stage_unregistered_version_file(path: Path, container: Path, editors_root: Path) -> tuple[Path, Path] | None:
    """Stage only an exact discovered unregistered artifact in its version root."""
    root = editors_root.expanduser().resolve(strict=False)
    folder = container.expanduser().resolve(strict=False)
    original = path.expanduser().absolute()
    if (not is_within(folder, root) or original.is_symlink()
            or not is_within(original, folder)):
        raise InstallError(f"Refusing to purge unregistered artifact outside its version folder: {original}")
    if not original.exists():
        return None
    if not original.is_file():
        raise InstallError(f"Expected regular unregistered artifact: {original}")
    staged = original.parent / f".{original.name}.purging-{uuid.uuid4().hex[:12]}"
    os.replace(original, staged)
    return original, staged


def stage_managed_portable_desktop_entry(record: dict) -> tuple[Path, Path] | None:
    """Stage the exact Suite-owned launcher even for a Portable-only owner.

    0.7.2/0.7.3 made Portable desktop ownership a genuine managed record with
    no AppImage path. The AppImage-specific integration helper cannot stage it.
    """
    if not record.get("desktop_integrated") or record.get("appimage_path"):
        return None
    raw = record.get("desktop_file_path")
    if not isinstance(raw, str) or not raw.strip():
        raise InstallError("Portable-integrated managed record has no Desktop Entry path.")
    original = Path(raw).expanduser().absolute()
    if original.parent.resolve(strict=False) != desktop_applications_dir().expanduser().resolve(strict=False):
        raise InstallError(f"Portable Desktop Entry is outside Suite's user applications folder: {original}")
    if original.is_symlink():
        raise InstallError(f"Refusing symbolic-link Portable Desktop Entry: {original}")
    if not original.exists():
        return None
    if not original.is_file():
        raise InstallError(f"Managed Portable Desktop Entry is not a regular file: {original}")
    staged = original.parent / f".{original.name}.purging-{uuid.uuid4().hex[:12]}"
    os.replace(original, staged)
    return original, staged
