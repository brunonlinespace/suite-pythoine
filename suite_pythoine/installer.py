from __future__ import annotations

import errno
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import stat
import uuid
import zipfile

from .versioning import appimage_metadata_path, parse_version_text, read_appimage_metadata, version_from_filename
from .component_catalog import mime_type_union
from .storage_layout import appimage_filename, appimage_root, architecture_from_appimage, icon_filename, is_within

MAX_ARCHIVE_MEMBERS = 50_000
MAX_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
MAX_MEMBER_BYTES = 512 * 1024 * 1024
SCAN_IGNORED_DIRS = frozenset({".git", ".hg", ".svn", "__pycache__", ".venv", "venv", "node_modules", "build"})


class InstallError(RuntimeError):
    pass


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_ISLNK(mode)


def _read_symlink_target(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> PurePosixPath:
    try:
        raw_target = archive.read(info).decode("utf-8", errors="strict").strip()
    except Exception as exc:
        raise InstallError(f"Could not read symbolic-link target in archive: {info.filename}") from exc
    pure = PurePosixPath(raw_target.replace("\\", "/"))
    if not raw_target or pure.is_absolute() or ".." in pure.parts or (pure.parts and pure.parts[0].endswith(":")):
        raise InstallError(f"Unsafe symbolic-link target in editor archive: {info.filename}")
    return pure


def validate_zip(path: Path) -> list[zipfile.ZipInfo]:
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise InstallError(f"Invalid ZIP archive: {exc}") from exc

    with archive:
        members = archive.infolist()
        if len(members) > MAX_ARCHIVE_MEMBERS:
            raise InstallError("Archive contains too many files.")
        total = sum(max(0, item.file_size) for item in members)
        if total > MAX_UNCOMPRESSED_BYTES:
            raise InstallError("Archive is too large when unpacked.")
        member_names = {PurePosixPath(item.filename.replace("\\", "/")) for item in members}
        for item in members:
            if item.file_size > MAX_MEMBER_BYTES:
                raise InstallError(f"Archive member is too large: {item.filename}")
            raw = item.filename.replace("\\", "/")
            pure = PurePosixPath(raw)
            if pure.is_absolute() or ".." in pure.parts or (pure.parts and pure.parts[0].endswith(":")):
                raise InstallError(f"Unsafe archive path: {item.filename}")
            if _is_symlink(item):
                target = _read_symlink_target(archive, item)
                resolved = PurePosixPath(*pure.parts[:-1], *target.parts)
                if resolved.is_absolute() or ".." in resolved.parts or (resolved.parts and resolved.parts[0].endswith(":")):
                    raise InstallError(f"Unsafe symbolic-link target in editor archive: {item.filename}")
                if resolved not in member_names:
                    raise InstallError(f"Symbolic-link target is missing in editor archive: {item.filename}")
        return members



def archive_editor_root_parts(members: list[zipfile.ZipInfo]) -> tuple[str, ...]:
    """Identify the portable editor root inside an archive without extraction."""
    files = [PurePosixPath(item.filename.replace("\\", "/")) for item in members if not item.is_dir()]
    if not files:
        raise InstallError("Editor archive is empty.")

    # Root-level launchers/manifests mean the archive itself is the editor root.
    root_names = {path.as_posix().casefold() for path in files if len(path.parts) == 1}
    if root_names & {"main.py", "editor.json", "suite-pythoine.json"}:
        return ()

    # The canonical Pad archives all have one enclosing source folder. Prefer it
    # because it also handles two-item layouts whose application package owns
    # the actual implementation beneath the root launcher.
    top_level = {path.parts[0] for path in files if path.parts}
    if len(top_level) == 1:
        return (next(iter(top_level)),)

    # Compatibility fallback for unusual archives containing unrelated top-level
    # material: locate a unique shallow main.py or manifest parent.
    candidates: set[tuple[str, ...]] = set()
    for path in files:
        if path.name.casefold() in {"main.py", "editor.json", "suite-pythoine.json"} and len(path.parts) <= 3:
            candidates.add(tuple(path.parts[:-1]))
    if len(candidates) == 1:
        return next(iter(candidates))
    raise InstallError("Could not identify a single portable editor root. Expected main.py or an editor manifest.")


def archive_source_folder_name(zip_path: Path, members: list[zipfile.ZipInfo] | None = None) -> str:
    members = members if members is not None else validate_zip(zip_path)
    root = archive_editor_root_parts(members)
    return root[-1] if root else zip_path.stem


def _archive_relative_path(info: zipfile.ZipInfo, root_parts: tuple[str, ...]) -> PurePosixPath | None:
    pure = PurePosixPath(info.filename.replace("\\", "/"))
    if root_parts:
        if tuple(pure.parts[: len(root_parts)]) != root_parts:
            return None
        relative = PurePosixPath(*pure.parts[len(root_parts) :])
    else:
        relative = pure
    if not relative.parts:
        return None
    return relative


def archive_expanded_bytes(zip_path: Path, members: list[zipfile.ZipInfo] | None = None) -> int:
    """Estimate bytes written by a direct managed extraction.

    Safe internal symlinks are materialized as ordinary files/directories, so a
    linked file contributes the target's size once more to the estimate.
    """
    members = members if members is not None else validate_zip(zip_path)
    by_path = {PurePosixPath(item.filename.replace("\\", "/")): item for item in members}
    total = sum(max(0, item.file_size) for item in members if not item.is_dir() and not _is_symlink(item))
    with zipfile.ZipFile(zip_path) as archive:
        for item in members:
            if not _is_symlink(item):
                continue
            pure = PurePosixPath(item.filename.replace("\\", "/"))
            target = _read_symlink_target(archive, item)
            resolved = PurePosixPath(*pure.parts[:-1], *target.parts)
            target_info = by_path.get(resolved)
            if target_info is not None and not target_info.is_dir():
                total += max(0, target_info.file_size)
    return total


def _nearest_existing_parent(path: Path) -> Path:
    candidate = path.expanduser().resolve(strict=False)
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate


def _format_bytes(value: int) -> str:
    size = float(max(0, value))
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024.0 or unit == "TiB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024.0
    return f"{value} B"


def preflight_archive_install(zip_path: Path, destination: Path, *, members: list[zipfile.ZipInfo] | None = None) -> tuple[int, int]:
    """Check ordinary free space before writing a portable source tree.

    Filesystem free-space APIs cannot see every per-user quota implementation;
    EDQUOT is therefore also translated if the write itself reaches a quota.
    """
    members = members if members is not None else validate_zip(zip_path)
    expanded = archive_expanded_bytes(zip_path, members)
    reserve = max(64 * 1024 * 1024, min(512 * 1024 * 1024, expanded // 5))
    required = expanded + reserve
    probe_root = _nearest_existing_parent(destination.parent)
    try:
        available = shutil.disk_usage(probe_root).free
    except OSError:
        return required, -1
    if available < required:
        raise InstallError(
            "Not enough storage space to install this component.\n\n"
            f"Estimated source/staging requirement: {_format_bytes(required)}\n"
            f"Available on {probe_root}: {_format_bytes(available)}\n"
            f"Destination: {destination}\n\n"
            "Remove unused component versions/build files or choose a Components folder with more free space, then try again."
        )
    return required, available


def _raise_storage_install_error(exc: OSError, destination: Path) -> None:
    if exc.errno == errno.EDQUOT:
        raise InstallError(
            "Your storage quota was reached while installing this editor.\n\n"
            f"Destination: {destination}\n\n"
            "Suite Pythoine stopped the staged installation without replacing the existing version. "
            "Free quota/storage (including old editor build folders if no longer needed) and try again."
        ) from exc
    if exc.errno == errno.ENOSPC:
        raise InstallError(
            "The filesystem ran out of free space while installing this editor.\n\n"
            f"Destination: {destination}\n\n"
            "Suite Pythoine stopped the staged installation without replacing the existing version. "
            "Free storage space and try again."
        ) from exc
    raise exc


def extract_editor_zip_to_staging(
    zip_path: Path,
    destination: Path,
    *,
    members: list[zipfile.ZipInfo] | None = None,
    root_parts: tuple[str, ...] | None = None,
) -> None:
    """Extract exactly one editor root directly into a managed staging folder."""
    members = members if members is not None else validate_zip(zip_path)
    root_parts = root_parts if root_parts is not None else archive_editor_root_parts(members)
    destination.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(zip_path) as archive:
        for item in members:
            if _is_symlink(item):
                continue
            relative = _archive_relative_path(item, root_parts)
            if relative is None:
                continue
            target = destination.joinpath(*relative.parts)
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(item, "r") as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)
            mode = (item.external_attr >> 16) & 0o777
            if mode:
                try:
                    target.chmod(mode)
                except OSError:
                    pass

        # Materialize only safe links whose targets remain inside the selected
        # editor root. This retains Portapad's .DirIcon semantics without
        # creating filesystem symlinks from an untrusted archive.
        for item in members:
            if not _is_symlink(item):
                continue
            relative = _archive_relative_path(item, root_parts)
            if relative is None:
                continue
            pure = PurePosixPath(item.filename.replace("\\", "/"))
            link_target = _read_symlink_target(archive, item)
            resolved_archive = PurePosixPath(*pure.parts[:-1], *link_target.parts)
            if root_parts:
                if tuple(resolved_archive.parts[: len(root_parts)]) != root_parts:
                    raise InstallError(f"Symbolic link escapes the editor root: {item.filename}")
                resolved_relative = PurePosixPath(*resolved_archive.parts[len(root_parts) :])
            else:
                resolved_relative = resolved_archive
            link_path = destination.joinpath(*relative.parts)
            target_path = destination.joinpath(*resolved_relative.parts)
            link_path.parent.mkdir(parents=True, exist_ok=True)
            if target_path.is_dir():
                shutil.copytree(target_path, link_path, dirs_exist_ok=True)
            elif target_path.is_file():
                shutil.copy2(target_path, link_path)
            else:
                raise InstallError(f"Symbolic-link target could not be materialized from editor archive: {item.filename}")


def safe_extract_zip(zip_path: Path, destination: Path) -> None:
    members = validate_zip(zip_path)
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        for item in members:
            if not _is_symlink(item):
                archive.extract(item, destination)
        for item in members:
            if not _is_symlink(item):
                continue
            pure = PurePosixPath(item.filename.replace("\\", "/"))
            target = _read_symlink_target(archive, item)
            link_path = destination.joinpath(*pure.parts)
            target_path = destination.joinpath(*PurePosixPath(*pure.parts[:-1], *target.parts).parts)
            link_path.parent.mkdir(parents=True, exist_ok=True)
            if target_path.is_dir():
                shutil.copytree(target_path, link_path, dirs_exist_ok=True)
            elif target_path.is_file():
                shutil.copy2(target_path, link_path)
            else:
                raise InstallError(f"Symbolic-link target could not be materialized from editor archive: {item.filename}")


def locate_editor_root(extracted: Path) -> Path:
    if (extracted / "main.py").is_file():
        return extracted

    try:
        direct_children = [path for path in extracted.iterdir() if path.is_dir()]
    except OSError as exc:
        raise InstallError(f"Could not inspect extracted archive: {exc}") from exc

    viable = [
        path
        for path in direct_children
        if (path / "main.py").is_file()
        or (path / "editor.json").is_file()
        or (path / "suite-pythoine.json").is_file()
    ]
    if len(viable) == 1:
        return viable[0]

    mains = [path.parent for path in extracted.glob("*/*/main.py")]
    unique = list(dict.fromkeys(mains))
    if len(unique) == 1:
        return unique[0]
    raise InstallError("Could not identify a single portable editor root. Expected main.py or an editor manifest.")


def import_zip(
    zip_path: Path,
    my_editors_dir: Path,
    replace_existing: bool = False,
    *,
    destination: Path | None = None,
) -> Path:
    """Extract one editor root directly into a sibling staging directory.

    0.2.3 deliberately avoids the old temporary-extract + copytree cycle. The
    archive is validated once, expanded once beside the final Portable folder,
    and atomically renamed into place only after extraction succeeds.
    """
    zip_path = zip_path.expanduser().resolve(strict=False)
    my_editors_dir = my_editors_dir.expanduser().resolve(strict=False)
    members = validate_zip(zip_path)
    root_parts = archive_editor_root_parts(members)
    source_name = root_parts[-1] if root_parts else zip_path.stem
    target = destination.expanduser().resolve(strict=False) if destination is not None else (my_editors_dir / source_name).resolve(strict=False)
    if not is_within(target, my_editors_dir):
        raise InstallError(f"Refusing to install portable editor outside the configured Components folder: {target}")
    if target.exists() and not replace_existing:
        raise FileExistsError(target)

    preflight_archive_install(zip_path, target, members=members)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        _raise_storage_install_error(exc, target)
    token = uuid.uuid4().hex[:10]
    staged = target.parent / f".{target.name}.importing-{token}"
    backup = target.parent / f".{target.name}.backup-{token}"
    try:
        extract_editor_zip_to_staging(zip_path, staged, members=members, root_parts=root_parts)
        if target.exists():
            os.replace(target, backup)
        os.replace(staged, target)
    except OSError as exc:
        try:
            if target.exists() and backup.exists():
                shutil.rmtree(target)
            if backup.exists() and not target.exists():
                os.replace(backup, target)
        finally:
            if staged.exists():
                shutil.rmtree(staged, ignore_errors=True)
        _raise_storage_install_error(exc, target)
    except Exception:
        try:
            if target.exists() and backup.exists():
                shutil.rmtree(target)
            if backup.exists() and not target.exists():
                os.replace(backup, target)
        finally:
            if staged.exists():
                shutil.rmtree(staged, ignore_errors=True)
        raise
    else:
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)
    return target.resolve(strict=False)

def _portable_editor_path(editor_root: Path, my_editors_dir: Path) -> Path:
    """Validate a removable versioned Portable directory beneath Editors root."""
    managed_root = my_editors_dir.expanduser().resolve(strict=False)
    candidate = editor_root.expanduser()
    if not candidate.is_absolute():
        candidate = candidate.absolute()
    if candidate.is_symlink() or not candidate.is_dir():
        raise InstallError(f"Portable editor folder does not exist or is unsafe: {candidate}")
    resolved = candidate.resolve(strict=False)
    if not is_within(resolved, managed_root):
        raise InstallError(f"Refusing to remove portable editor outside Components folder: {candidate}")
    try:
        rel = resolved.relative_to(managed_root)
    except ValueError as exc:
        raise InstallError(f"Refusing to remove unsafe portable editor path: {candidate}") from exc
    # New layout: <Application>/<Version>/Portable. Legacy direct children are
    # still accepted so an older custom layout can be cleaned up explicitly.
    if not ((len(rel.parts) == 3 and rel.parts[-1].casefold() == "portable") or len(rel.parts) == 1):
        raise InstallError(f"Refusing to remove non-portable directory: {candidate}")
    for parent in resolved.parents:
        if parent == managed_root:
            break
        if parent.is_symlink():
            raise InstallError(f"Refusing to remove portable editor through symbolic-link parent: {candidate}")
    return resolved


def stage_portable_editor_folder(editor_root: Path, my_editors_dir: Path) -> tuple[Path, Path]:
    """Atomically move a portable editor to a hidden purge staging path."""
    original = _portable_editor_path(editor_root, my_editors_dir)
    token = uuid.uuid4().hex[:10]
    staged = original.parent / f".{original.name}.purging-{token}"
    os.replace(original, staged)
    return original, staged


def restore_staged_portable_folder(original: Path, staged: Path, my_editors_dir: Path) -> None:
    managed_root = my_editors_dir.expanduser().resolve(strict=False)
    original = original.expanduser()
    staged = staged.expanduser()
    if not is_within(original, managed_root) or staged.parent.resolve(strict=False) != original.parent.resolve(strict=False):
        raise InstallError("Refusing to restore a portable editor outside Components folder.")
    if not staged.name.startswith(f".{original.name}.purging-"):
        raise InstallError("Portable-editor staging identity is invalid.")
    if original.exists():
        raise InstallError(f"Cannot restore portable editor because the destination already exists: {original}")
    if staged.exists():
        os.replace(staged, original)


def delete_staged_portable_folder(original: Path, staged: Path, my_editors_dir: Path) -> None:
    managed_root = my_editors_dir.expanduser().resolve(strict=False)
    original = original.expanduser()
    staged = staged.expanduser()
    if not is_within(staged, managed_root) or staged.parent.resolve(strict=False) != original.parent.resolve(strict=False) or not staged.name.startswith(f".{original.name}.purging-"):
        raise InstallError(f"Refusing to delete invalid purge staging path: {staged}")
    if staged.is_symlink():
        raise InstallError(f"Refusing to delete symbolic-link purge staging path: {staged}")
    if staged.exists():
        try:
            shutil.rmtree(staged)
        except OSError as exc:
            raise InstallError(f"Could not remove portable editor folder: {exc}") from exc


def remove_portable_editor_folder(editor_root: Path, my_editors_dir: Path) -> Path:
    """Remove a portable editor with rename-first rollback on deletion failure."""
    original, staged = stage_portable_editor_folder(editor_root, my_editors_dir)
    try:
        delete_staged_portable_folder(original, staged, my_editors_dir)
    except Exception:
        if staged.exists() and not original.exists():
            try:
                restore_staged_portable_folder(original, staged, my_editors_dir)
            except Exception:
                pass
        raise
    return original.resolve(strict=False)


def _bounded_tree_files(editor_root: Path, *, max_depth: int = 6):
    """Walk editor packaging trees without following symlinks or unbounded recursion."""
    base_depth = len(editor_root.parts)
    for root, dirs, files in os.walk(editor_root, followlinks=False):
        root_path = Path(root)
        depth = len(root_path.parts) - base_depth
        dirs[:] = [
            name
            for name in dirs
            if depth < max_depth
            and name.casefold() not in SCAN_IGNORED_DIRS
            and not (root_path / name).is_symlink()
        ]
        for name in files:
            path = root_path / name
            if not path.is_symlink():
                yield path


def _read_small_text(path: Path, *, limit: int = 512 * 1024) -> str:
    try:
        if path.stat().st_size > limit:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _build_script_score(editor_root: Path, path: Path) -> int:
    if path.suffix.casefold() != ".sh":
        return -1
    name = path.name.casefold()
    if name.startswith("test") or name.startswith("install"):
        return -1
    try:
        relative = path.relative_to(editor_root)
    except ValueError:
        return -1
    parts = tuple(part.casefold() for part in relative.parts)
    part_set = set(parts)

    score = 0
    if name == "build-fedora-appimage.sh":
        score += 100
    elif name == "build-appimage.sh":
        score += 90
    elif name.startswith("build") and "appimage" in name:
        score += 75

    # Support both project lineages used by the pad family:
    #   */packaging/fedora/build-appimage.sh  (Sheepy/Timblee/current Ricopad)
    #   */appimage/build-fedora-appimage.sh   (Nuxpad/legacy Ricopad/Portapad)
    if "appimage" in part_set:
        score += 45
    if "packaging" in part_set:
        score += 35
    if "fedora" in part_set:
        score += 10

    # A future/custom builder can still be recognised by content, but a generic
    # shell helper is never accepted merely because it lives near packaging.
    if score < 75:
        text = _read_small_text(path)
        lowered = text.casefold()
        if "appimagetool" in lowered and ".appimage" in lowered:
            score += 55
        if "pyinstaller" in lowered:
            score += 10

    return score


def find_appimage_build_script(editor_root: Path) -> Path | None:
    scored: list[tuple[int, int, str, Path]] = []
    for path in _bounded_tree_files(editor_root, max_depth=6):
        score = _build_script_score(editor_root, path)
        if score < 75:
            continue
        relative = path.relative_to(editor_root)
        scored.append((score, -len(relative.parts), path.name.casefold(), path))
    if not scored:
        return None
    return max(scored, key=lambda item: (item[0], item[1], item[2]))[3]


def build_script_version(script: Path | None) -> str | None:
    if script is None:
        return None
    return parse_version_text(_read_small_text(script))


def _appimage_signature(path: Path) -> tuple[int, int] | None:
    try:
        info = path.stat()
    except OSError:
        return None
    return info.st_size, info.st_mtime_ns


def snapshot_appimages(editor_root: Path) -> dict[str, tuple[int, int]]:
    snapshot: dict[str, tuple[int, int]] = {}
    for path in _bounded_tree_files(editor_root, max_depth=6):
        if path.suffix.casefold() != ".appimage" or not path.is_file():
            continue
        signature = _appimage_signature(path)
        if signature is not None:
            snapshot[str(path.resolve(strict=False))] = signature
    return snapshot


def expected_build_output_dirs(editor_root: Path, build_script: Path | None) -> list[Path]:
    if build_script is None:
        return [editor_root / "dist"]
    try:
        relative = build_script.relative_to(editor_root)
    except ValueError:
        return [editor_root / "dist"]
    parts = list(relative.parts)
    lowered = [part.casefold() for part in parts]
    roots: list[Path] = []
    for marker in ("packaging", "appimage"):
        if marker in lowered:
            index = lowered.index(marker)
            program_root = editor_root.joinpath(*parts[:index]) if index else editor_root
            roots.append(program_root / "dist")
    roots.append(editor_root / "dist")
    unique: list[Path] = []
    for path in roots:
        resolved = path.resolve(strict=False)
        if resolved not in unique:
            unique.append(resolved)
    return unique


def find_built_appimage(
    editor_root: Path,
    *,
    build_script: Path | None = None,
    before: dict[str, tuple[int, int]] | None = None,
    expected_version: str | None = None,
) -> Path | None:
    """Return the artifact produced/changed by this build, never an arbitrary stale AppImage."""
    candidates: list[Path] = []
    for path in _bounded_tree_files(editor_root, max_depth=6):
        if path.suffix.casefold() != ".appimage" or not path.is_file():
            continue
        resolved = path.resolve(strict=False)
        if before is not None:
            old = before.get(str(resolved))
            current = _appimage_signature(path)
            if current is None or old == current:
                continue
        candidates.append(resolved)
    if not candidates:
        return None

    output_dirs = expected_build_output_dirs(editor_root, build_script)

    def under(path: Path, parent: Path) -> bool:
        try:
            path.relative_to(parent)
            return True
        except ValueError:
            return False

    def key(path: Path):
        version = version_from_filename(path)
        version_score = 2 if expected_version and version and version.casefold() == expected_version.casefold() else 0
        expected_dir_score = max((3 if under(path, directory) else 0 for directory in output_dirs), default=0)
        try:
            relative = path.relative_to(editor_root)
            parts = {part.casefold() for part in relative.parts}
        except ValueError:
            parts = set()
        final_score = 2 if "dist" in parts else 1 if "output" in parts else 0
        signature = _appimage_signature(path) or (0, 0)
        return version_score, expected_dir_score, final_score, signature[1], -len(path.parts)

    return max(candidates, key=key)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_appimage_metadata(
    appimage: Path,
    *,
    editor_id: str,
    name: str,
    version: str | None,
    application_id: str | None = None,
    publisher_id: str | None = None,
    desktop_file: Path | None = None,
    desktop_id: str | None = None,
    desktop_integrated: bool | None = None,
    icon: Path | None = None,
    source_artifact: Path | None = None,
    build_script: Path | None = None,
) -> Path:
    """Write the recovery/provenance mirror for one managed AppImage.

    The configuration registry is the normal source of truth.  This sidecar is
    deliberately kept beside the AppImage so a damaged/missing preference file
    can be reconstructed during Repair without guessing from versioned filenames.
    Existing provenance is merged rather than discarded by a later repair.
    """
    appimage = appimage.expanduser().resolve(strict=False)
    metadata = read_appimage_metadata(appimage)
    if not isinstance(metadata, dict):
        metadata = {}
    metadata.update({
        "schema": 2,
        "managed_by": "Suite Pythoine",
        "editor_id": editor_id,
        "application_id": application_id or editor_id,
        "publisher_id": publisher_id or metadata.get("publisher_id") or None,
        "name": name,
        "version": version,
        "appimage": str(appimage),
        "appimage_path": str(appimage),
        "sha256": sha256_file(appimage),
        "appimage_sha256": sha256_file(appimage),
    })
    if desktop_integrated is None:
        desktop_integrated = desktop_file is not None
    metadata["desktop_integrated"] = bool(desktop_integrated)
    if desktop_file is not None:
        metadata["desktop_file_path"] = str(desktop_file.expanduser().resolve(strict=False))
    elif desktop_integrated is False:
        metadata["desktop_file_path"] = None
    if desktop_id is not None:
        metadata["desktop_id"] = desktop_id
    if icon is not None:
        metadata["icon_path"] = str(icon.expanduser().resolve(strict=False))
    elif "icon_path" not in metadata:
        metadata["icon_path"] = None
    if source_artifact is not None:
        metadata["source_artifact"] = source_artifact.name
    if build_script is not None:
        metadata["build_script"] = str(build_script.resolve(strict=False))
    target = appimage_metadata_path(appimage)
    _atomic_write_text(target, json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    return target.resolve(strict=False)


def clean_build_dirs(editor_root: Path) -> None:
    """Remove only shallow build directories produced by packaged editor builders."""
    candidates: list[Path] = []
    base_depth = len(editor_root.parts)
    for root, dirs, _files in os.walk(editor_root, topdown=True, followlinks=False):
        root_path = Path(root)
        depth = len(root_path.parts) - base_depth
        dirs[:] = [name for name in dirs if depth < 3 and not (root_path / name).is_symlink()]
        for name in list(dirs):
            path = root_path / name
            if name.casefold() == "build" and len(path.relative_to(editor_root).parts) <= 3:
                candidates.append(path)
                dirs.remove(name)
    for path in sorted(candidates, key=lambda item: len(item.parts), reverse=True):
        shutil.rmtree(path, ignore_errors=True)


def preflight_file_install(source: Path, target: Path) -> tuple[int, int]:
    """Check free space before copying a standalone managed artifact."""
    try:
        payload = max(0, source.stat().st_size)
    except OSError:
        return 0, -1
    reserve = max(32 * 1024 * 1024, min(256 * 1024 * 1024, payload // 10))
    required = payload + reserve
    probe_root = _nearest_existing_parent(target.parent)
    try:
        available = shutil.disk_usage(probe_root).free
    except OSError:
        return required, -1
    if available < required:
        raise InstallError(
            "Not enough storage space to install this artifact.\n\n"
            f"Estimated copy/staging requirement: {_format_bytes(required)}\n"
            f"Available on {probe_root}: {_format_bytes(available)}\n"
            f"Destination: {target}"
        )
    return required, available


def _atomic_copy(source: Path, target: Path, *, executable: bool = False) -> None:
    preflight_file_install(source, target)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        _raise_storage_install_error(exc, target)
    temporary = target.with_name(f".{target.name}.installing-{uuid.uuid4().hex[:10]}")
    try:
        shutil.copy2(source, temporary)
        if executable:
            temporary.chmod(temporary.stat().st_mode | stat.S_IXUSR)
        os.replace(temporary, target)
    except OSError as exc:
        _raise_storage_install_error(exc, target)
    finally:
        if temporary.exists():
            try:
                temporary.unlink()
            except OSError:
                pass

def _safe_stem(value: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    return stem or "editor"


def install_appimage(
    appimage: Path,
    installed_dir: Path,
    *,
    editor_id: str | None = None,
    name: str | None = None,
    version: str | None = None,
    architecture: str | None = None,
) -> Path:
    """Atomically install a versioned AppImage beneath the single Editors root."""
    if name and version:
        target_dir = appimage_root(installed_dir, name, version)
        filename = appimage_filename(name, version, architecture or architecture_from_appimage(appimage))
    else:
        # Compatibility path for older callers.
        target_dir = installed_dir
        filename = appimage.name if not editor_id else f"{_safe_stem(editor_id)}.AppImage"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / filename
    _atomic_copy(appimage, target, executable=True)
    return target.resolve(strict=False)


def install_icon(
    icon: Path | None,
    installed_dir: Path,
    editor_id: str,
    *,
    name: str | None = None,
    version: str | None = None,
) -> Path | None:
    if not icon or not icon.is_file():
        return None
    target_dir = appimage_root(installed_dir, name, version) if name and version else installed_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    suffix = icon.suffix.lower() or ".png"
    target = target_dir / icon_filename(name or editor_id, suffix)
    _atomic_copy(icon, target)
    return target.resolve(strict=False)


def desktop_applications_dir() -> Path:
    return Path.home() / ".local" / "share" / "applications"


def desktop_entry_path(editor_id: str, applications_dir: Path | None = None) -> Path:
    applications = applications_dir or desktop_applications_dir()
    return applications / f"io.github.brunonlinespace.{_safe_stem(editor_id)}.desktop"


def _desktop_template(editor_root: Path | None, editor_id: str) -> Path | None:
    if not editor_root or not editor_root.is_dir():
        return None
    candidates: list[tuple[int, int, Path]] = []
    for path in _bounded_tree_files(editor_root, max_depth=6):
        if path.suffix.casefold() != ".desktop":
            continue
        try:
            relative = path.relative_to(editor_root)
        except ValueError:
            continue
        compact_id = editor_id.replace("-", "")
        compact_stem = path.stem.casefold().replace("-", "").replace("_", "")
        score = 1 if compact_id in compact_stem else 0
        candidates.append((score, -len(relative.parts), path))
    return max(candidates, key=lambda item: (item[0], item[1]))[2] if candidates else None


def _desktop_exec_quote(path: Path) -> str:
    value = str(path.resolve(strict=False)).replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"')
    return f'"{value}"'


def _desktop_exec_token(value: str) -> str:
    text = str(value).replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def _desktop_exec_command(parts: tuple[str, ...]) -> str:
    if not parts:
        raise InstallError("Desktop integration command is empty.")
    return " ".join(_desktop_exec_token(part) for part in parts)


def _desktop_plain_value(path: Path) -> str:
    # Desktop Entry string values are not shell commands. Spaces are literal;
    # surrounding quotes would become part of Icon=/TryExec= and can make the
    # desktop shell treat the value as invalid.
    return str(path.resolve(strict=False)).replace("\n", " ").replace("\r", " ")


def _atomic_write_text(path: Path, text: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        _raise_storage_install_error(exc, path)
    temporary = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex[:10]}")
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    except OSError as exc:
        _raise_storage_install_error(exc, path)
    finally:
        if temporary.exists():
            try:
                temporary.unlink()
            except OSError:
                pass

def _rewrite_primary_desktop_group(
    original: list[str],
    *,
    name: str,
    editor_id: str,
    appimage: Path,
    icon: Path | None,
    mime_types: tuple[str, ...] | None = None,
) -> list[str]:
    """Canonicalise only [Desktop Entry], leaving Desktop Action groups alone."""
    primary_start = next((i for i, line in enumerate(original) if line.strip() == "[Desktop Entry]"), None)
    if primary_start is None:
        primary = ["[Desktop Entry]", "Type=Application", f"Name={name}", "Terminal=false", "Categories=Utility;TextEditor;"]
        remainder: list[str] = []
    else:
        next_group = next(
            (i for i in range(primary_start + 1, len(original)) if original[i].strip().startswith("[") and original[i].strip().endswith("]")),
            len(original),
        )
        prefix = original[:primary_start]
        primary = original[primary_start:next_group]
        remainder = original[next_group:]
        if prefix:
            # Comments before the main group are retained.
            primary = prefix + primary

    managed_keys = {
        "exec",
        "tryexec",
        "icon",
        "nodisplay",
        "hidden",
        "onlyshowin",
        "notshowin",
        "dbusactivatable",
        "x-suite-pythoine-managed",
        "x-suite-pythoine-appimage",
        "x-suite-pythoine-portablemain",
        "x-suite-pythoine-runtime",
        "x-suite-pythoine-applicationid",
        "x-suite-pythoine-desktopid",
    }
    if mime_types is not None:
        managed_keys.add("mimetype")
    cleaned: list[str] = []
    seen_type = False
    seen_name = False
    for line in primary:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            cleaned.append(line)
            continue
        key = stripped.split("=", 1)[0].casefold() if "=" in stripped else ""
        if key in managed_keys:
            continue
        if key == "type":
            seen_type = True
        if key == "name":
            seen_name = True
        cleaned.append(line)

    if not any(line.strip() == "[Desktop Entry]" for line in cleaned):
        cleaned.append("[Desktop Entry]")
    if not seen_type:
        cleaned.append("Type=Application")
    if not seen_name:
        cleaned.append(f"Name={name.replace(chr(10), ' ').replace(chr(13), ' ')}")
    # Managed entries must be visible and must execute the AppImage directly on
    # Plasma/XFCE/GNOME rather than relying on a source template's desktop-only
    # visibility or D-Bus activation policy.
    cleaned.append("NoDisplay=false")
    cleaned.append("Hidden=false")
    cleaned.append("DBusActivatable=false")
    cleaned.append(f"Exec={_desktop_exec_quote(appimage)} %F")
    if icon:
        cleaned.append(f"Icon={_desktop_plain_value(icon)}")
    if mime_types is not None:
        cleaned.append("MimeType=" + "".join(f"{value};" for value in mime_types))
    cleaned.append("X-Suite-Pythoine-Managed=true")
    cleaned.append("X-Suite-Pythoine-Runtime=appimage")
    cleaned.append(f"X-Suite-Pythoine-AppImage={_desktop_plain_value(appimage)}")
    cleaned.append(f"X-Suite-Pythoine-ApplicationId={_safe_stem(editor_id)}")
    cleaned.append(f"X-Suite-Pythoine-DesktopId=io.github.brunonlinespace.{_safe_stem(editor_id)}")
    return cleaned + remainder


def write_desktop_entry(
    name: str,
    editor_id: str,
    appimage: Path,
    icon: Path | None = None,
    editor_root: Path | None = None,
    *,
    applications_dir: Path | None = None,
    desktop_path: Path | None = None,
) -> Path:
    """Write/repair the per-user desktop entry for a Suite-managed AppImage.

    r2 copied TryExec/Icon using Exec-style quotes. TryExec and Icon are ordinary
    Desktop Entry string values; those quotes can make menu discovery fail on
    some desktops. r3 deliberately omits TryExec and writes an absolute Icon path
    without shell quoting while retaining correct Exec quoting.
    """
    appimage = appimage.expanduser().resolve(strict=False)
    if not appimage.is_file():
        raise InstallError(f"Cannot create a desktop entry because the AppImage is missing: {appimage}")
    try:
        appimage.chmod(appimage.stat().st_mode | stat.S_IXUSR)
    except OSError as exc:
        raise InstallError(f"Could not make AppImage executable: {exc}") from exc

    desktop = (desktop_path.expanduser().resolve(strict=False) if desktop_path is not None else desktop_entry_path(editor_id, applications_dir))
    desktop.parent.mkdir(parents=True, exist_ok=True)
    template = _desktop_template(editor_root, editor_id)
    if template:
        try:
            original = template.read_text(encoding="utf-8").splitlines()
        except OSError:
            original = []
    else:
        original = []

    lines = _rewrite_primary_desktop_group(original, name=name, editor_id=editor_id, appimage=appimage, icon=icon, mime_types=mime_type_union() if editor_id == "suite-pythoine" else None)
    # If the template did not provide the common main-group fields, add sensible
    # defaults before the first Desktop Action section.
    first_secondary = next((i for i, line in enumerate(lines) if i and line.strip().startswith("[") and line.strip() != "[Desktop Entry]"), len(lines))
    primary_text = "\n".join(lines[:first_secondary])
    insertions: list[str] = []
    if "\nTerminal=" not in "\n" + primary_text:
        insertions.append("Terminal=false")
    if "\nCategories=" not in "\n" + primary_text:
        insertions.append("Categories=Utility;TextEditor;")
    if insertions:
        lines[first_secondary:first_secondary] = insertions

    text = "\n".join(lines).rstrip() + "\n"
    _atomic_write_text(desktop, text)
    desktop.chmod(desktop.stat().st_mode | stat.S_IXUSR)
    return desktop.resolve(strict=False)



def _rewrite_primary_desktop_group_portable(
    original: list[str],
    *,
    name: str,
    editor_id: str,
    command: tuple[str, ...],
    icon: Path | None,
    mime_types: tuple[str, ...] | None = None,
) -> list[str]:
    """Canonicalise a managed Desktop Entry whose active runtime is Portable."""
    primary_start = next((i for i, line in enumerate(original) if line.strip() == "[Desktop Entry]"), None)
    if primary_start is None:
        primary = ["[Desktop Entry]", "Type=Application", f"Name={name}", "Terminal=false", "Categories=Utility;TextEditor;"]
        remainder: list[str] = []
    else:
        next_group = next(
            (i for i in range(primary_start + 1, len(original)) if original[i].strip().startswith("[") and original[i].strip().endswith("]")),
            len(original),
        )
        prefix = original[:primary_start]
        primary = original[primary_start:next_group]
        remainder = original[next_group:]
        if prefix:
            primary = prefix + primary

    managed_keys = {
        "exec", "tryexec", "icon", "nodisplay", "hidden", "onlyshowin", "notshowin", "dbusactivatable",
        "x-suite-pythoine-managed", "x-suite-pythoine-appimage", "x-suite-pythoine-portablemain",
        "x-suite-pythoine-runtime", "x-suite-pythoine-applicationid", "x-suite-pythoine-desktopid",
    }
    if mime_types is not None:
        managed_keys.add("mimetype")
    cleaned: list[str] = []
    seen_type = False
    seen_name = False
    for line in primary:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            cleaned.append(line)
            continue
        key = stripped.split("=", 1)[0].casefold() if "=" in stripped else ""
        if key in managed_keys:
            continue
        if key == "type":
            seen_type = True
        if key == "name":
            seen_name = True
        cleaned.append(line)

    if not any(line.strip() == "[Desktop Entry]" for line in cleaned):
        cleaned.append("[Desktop Entry]")
    if not seen_type:
        cleaned.append("Type=Application")
    if not seen_name:
        cleaned.append(f"Name={name.replace(chr(10), ' ').replace(chr(13), ' ')}")
    cleaned.append("NoDisplay=false")
    cleaned.append("Hidden=false")
    cleaned.append("DBusActivatable=false")
    cleaned.append(f"Exec={_desktop_exec_command(command)} %F")
    if icon:
        cleaned.append(f"Icon={_desktop_plain_value(icon)}")
    if mime_types is not None:
        cleaned.append("MimeType=" + "".join(f"{value};" for value in mime_types))
    cleaned.append("X-Suite-Pythoine-Managed=true")
    cleaned.append("X-Suite-Pythoine-Runtime=portable")
    # The final Python/script argument is the stable Portable launcher identity.
    cleaned.append(f"X-Suite-Pythoine-PortableMain={str(Path(command[-1]).expanduser().resolve(strict=False))}")
    cleaned.append(f"X-Suite-Pythoine-ApplicationId={_safe_stem(editor_id)}")
    cleaned.append(f"X-Suite-Pythoine-DesktopId=io.github.brunonlinespace.{_safe_stem(editor_id)}")
    return cleaned + remainder


def write_portable_desktop_entry(
    name: str,
    editor_id: str,
    command: tuple[str, ...],
    icon: Path | None = None,
    editor_root: Path | None = None,
    *,
    applications_dir: Path | None = None,
    desktop_path: Path | None = None,
) -> Path:
    """Write the managed Desktop Entry directly to an active Portable runtime.

    This is primarily used by Suite Pythoine itself so a Portable-only active
    Hub owns application-menu launching and OS document delivery instead of
    relying on an older retained AppImage as a behavioural bootstrap.
    """
    command = tuple(str(part) for part in command if str(part))
    if len(command) < 2:
        raise InstallError("Portable desktop integration requires an executable and a launcher script.")
    executable = Path(command[0]).expanduser().resolve(strict=False)
    launcher = Path(command[-1]).expanduser().resolve(strict=False)
    if not executable.is_file():
        raise InstallError(f"Portable runtime executable is missing: {executable}")
    if not launcher.is_file():
        raise InstallError(f"Portable runtime launcher is missing: {launcher}")
    normalized = (str(executable), *command[1:-1], str(launcher))

    desktop = desktop_path.expanduser().resolve(strict=False) if desktop_path is not None else desktop_entry_path(editor_id, applications_dir)
    desktop.parent.mkdir(parents=True, exist_ok=True)
    template = _desktop_template(editor_root, editor_id)
    if template:
        try:
            original = template.read_text(encoding="utf-8").splitlines()
        except OSError:
            original = []
    else:
        original = []
    lines = _rewrite_primary_desktop_group_portable(
        original,
        name=name,
        editor_id=editor_id,
        command=tuple(normalized),
        icon=icon,
        mime_types=mime_type_union() if editor_id == "suite-pythoine" else None,
    )
    first_secondary = next((i for i, line in enumerate(lines) if i and line.strip().startswith("[") and line.strip() != "[Desktop Entry]"), len(lines))
    primary_text = "\n".join(lines[:first_secondary])
    insertions: list[str] = []
    if "\nTerminal=" not in "\n" + primary_text:
        insertions.append("Terminal=false")
    if "\nCategories=" not in "\n" + primary_text:
        insertions.append("Categories=Utility;TextEditor;")
    if insertions:
        lines[first_secondary:first_secondary] = insertions
    _atomic_write_text(desktop, "\n".join(lines).rstrip() + "\n")
    desktop.chmod(desktop.stat().st_mode | stat.S_IXUSR)
    return desktop.resolve(strict=False)


def _primary_desktop_values(desktop: Path) -> dict[str, str]:
    try:
        lines = desktop.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    values: dict[str, str] = {}
    in_primary = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_primary = stripped == "[Desktop Entry]"
            continue
        if in_primary and "=" in line and not stripped.startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def desktop_entry_exec_target(desktop: Path) -> Path | None:
    value = _primary_desktop_values(desktop).get("Exec", "")
    if not value:
        return None
    try:
        parts = shlex.split(value, posix=True)
    except ValueError:
        return None
    if not parts:
        return None
    executable = parts[0].replace("%%", "%")
    return Path(executable).expanduser().resolve(strict=False)



def desktop_entry_exec_command(desktop: Path) -> tuple[str, ...]:
    value = _primary_desktop_values(desktop).get("Exec", "")
    if not value:
        return ()
    try:
        parts = shlex.split(value, posix=True)
    except ValueError:
        return ()
    return tuple(part.replace("%%", "%") for part in parts if part not in {"%f", "%F", "%u", "%U"})


def desktop_entry_runtime(desktop: Path) -> str | None:
    values = _primary_desktop_values(desktop)
    runtime = values.get("X-Suite-Pythoine-Runtime", "").strip().casefold()
    if runtime in {"portable", "appimage"}:
        return runtime
    # Compatibility with pre-r2 managed entries.
    if values.get("X-Suite-Pythoine-AppImage"):
        return "appimage"
    if values.get("X-Suite-Pythoine-PortableMain"):
        return "portable"
    return None


def portable_desktop_entry_status(
    editor_id: str,
    command: tuple[str, ...] | None,
    *,
    applications_dir: Path | None = None,
    desktop_path: Path | None = None,
    desktop_id: str | None = None,
    icon_path: Path | None = None,
) -> str:
    if not command:
        return "no-portable"
    expected = tuple(str(part) for part in command)
    if len(expected) < 2:
        return "no-portable"
    executable = Path(expected[0]).expanduser().resolve(strict=False)
    launcher = Path(expected[-1]).expanduser().resolve(strict=False)
    if not executable.is_file() or not launcher.is_file():
        return "no-portable"
    expected = (str(executable), *expected[1:-1], str(launcher))
    desktop = desktop_path.expanduser().resolve(strict=False) if desktop_path is not None else desktop_entry_path(editor_id, applications_dir)
    if not desktop.is_file():
        return "missing"
    if desktop_id is not None and desktop.stem != desktop_id:
        return "stale"
    if desktop_entry_exec_command(desktop) != tuple(expected):
        return "stale"
    values = _primary_desktop_values(desktop)
    if values.get("X-Suite-Pythoine-Managed", "").casefold() != "true":
        return "stale"
    if desktop_entry_runtime(desktop) != "portable":
        return "stale"
    raw_launcher = values.get("X-Suite-Pythoine-PortableMain", "")
    if not raw_launcher or Path(raw_launcher).expanduser().resolve(strict=False) != launcher:
        return "stale"
    if desktop_id is not None and values.get("X-Suite-Pythoine-DesktopId", "") != desktop_id:
        return "stale"
    if icon_path is not None:
        expected_icon = icon_path.expanduser().resolve(strict=False)
        if not expected_icon.is_file():
            return "stale"
        raw_icon = values.get("Icon", "")
        if not raw_icon or Path(raw_icon).expanduser().resolve(strict=False) != expected_icon:
            return "stale"
    return "ready"


def desktop_entry_status(
    editor_id: str,
    appimage: Path | None,
    *,
    applications_dir: Path | None = None,
    desktop_path: Path | None = None,
    desktop_id: str | None = None,
    icon_path: Path | None = None,
) -> str:
    """Return ready, missing, stale, or no-appimage for integration UI.

    Registered installs pass their exact Desktop Entry and icon paths here.
    The deterministic editor-id path remains only as a legacy/recovery fallback.
    """
    if appimage is None or not appimage.is_file():
        return "no-appimage"
    desktop = desktop_path.expanduser().resolve(strict=False) if desktop_path is not None else desktop_entry_path(editor_id, applications_dir)
    if not desktop.is_file():
        return "missing"
    if desktop_id is not None and desktop.stem != desktop_id:
        return "stale"
    target = desktop_entry_exec_target(desktop)
    if target != appimage.expanduser().resolve(strict=False):
        return "stale"
    values = _primary_desktop_values(desktop)
    if values.get("X-Suite-Pythoine-Managed", "").casefold() != "true":
        return "stale"
    if desktop_entry_runtime(desktop) != "appimage":
        return "stale"
    registered_appimage = values.get("X-Suite-Pythoine-AppImage", "")
    if not registered_appimage or Path(registered_appimage).expanduser().resolve(strict=False) != appimage.expanduser().resolve(strict=False):
        return "stale"
    if desktop_id is not None and values.get("X-Suite-Pythoine-DesktopId", "") != desktop_id:
        return "stale"
    if icon_path is not None:
        expected_icon = icon_path.expanduser().resolve(strict=False)
        if not expected_icon.is_file():
            return "stale"
        raw_icon = values.get("Icon", "")
        if not raw_icon or Path(raw_icon).expanduser().resolve(strict=False) != expected_icon:
            return "stale"
    return "ready"


def synchronize_desktop_integration(
    name: str,
    editor_id: str,
    appimage: Path,
    icon: Path | None = None,
    component_root: Path | None = None,
    *,
    applications_dir: Path | None = None,
    desktop_path: Path | None = None,
    desktop_id: str | None = None,
) -> Path:
    """Write and immediately verify one managed Desktop Entry.

    Make Active and Repair intentionally share this primitive so normal version
    selection and recovery cannot drift into different integration behavior.
    """
    expected_id = desktop_id or f"io.github.brunonlinespace.{_safe_stem(editor_id)}"
    desktop = write_desktop_entry(
        name,
        editor_id,
        appimage,
        icon,
        component_root,
        applications_dir=applications_dir,
        desktop_path=desktop_path,
    )
    status = desktop_entry_status(
        editor_id,
        appimage,
        applications_dir=applications_dir,
        desktop_path=desktop,
        desktop_id=expected_id,
        icon_path=icon,
    )
    if status != "ready":
        raise InstallError(f"Desktop integration verification returned {status!r}.")
    return desktop



def synchronize_portable_desktop_integration(
    name: str,
    editor_id: str,
    command: tuple[str, ...],
    icon: Path | None = None,
    component_root: Path | None = None,
    *,
    applications_dir: Path | None = None,
    desktop_path: Path | None = None,
    desktop_id: str | None = None,
) -> Path:
    """Write and verify one managed Desktop Entry for a Portable runtime."""
    expected_id = desktop_id or f"io.github.brunonlinespace.{_safe_stem(editor_id)}"
    desktop = write_portable_desktop_entry(
        name,
        editor_id,
        command,
        icon,
        component_root,
        applications_dir=applications_dir,
        desktop_path=desktop_path,
    )
    status = portable_desktop_entry_status(
        editor_id,
        command,
        applications_dir=applications_dir,
        desktop_path=desktop,
        desktop_id=expected_id,
        icon_path=icon,
    )
    if status != "ready":
        raise InstallError(f"Portable desktop integration verification returned {status!r}.")
    return desktop


def _tokenise_name(value: str) -> set[str]:
    return {token for token in re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-").split("-") if token}


def managed_appimages(
    installed_dir: Path,
    editor_id: str,
    name: str,
    *,
    explicit_path: Path | None = None,
) -> list[Path]:
    """Find AppImages belonging to one editor inside Suite's managed folder."""
    installed_dir = installed_dir.expanduser().resolve(strict=False)
    candidates: dict[str, Path] = {}
    if explicit_path is not None:
        path = explicit_path.expanduser().resolve(strict=False)
        try:
            managed_path = is_within(path, installed_dir)
        except OSError:
            managed_path = False
        if managed_path and path.is_file() and path.suffix.casefold() == ".appimage":
            candidates[str(path)] = path

    if installed_dir.is_dir():
        target_tokens = _tokenise_name(editor_id) | _tokenise_name(name)
        meaningful = {token for token in target_tokens if token not in {"pad", "editor", "2"} and not token.isdigit()}
        canonical = installed_dir / f"{_safe_stem(editor_id)}.AppImage"
        if canonical.is_file():
            candidates[str(canonical.resolve(strict=False))] = canonical.resolve(strict=False)
        for pattern in ("*.AppImage", "*.appimage", "*/*/AppImage/*.AppImage", "*/*/AppImage/*.appimage"):
            for path in installed_dir.glob(pattern):
                tokens = _tokenise_name(path.stem)
                if meaningful and meaningful & tokens:
                    candidates[str(path.resolve(strict=False))] = path.resolve(strict=False)

    def key(path: Path):
        canonical_score = int(path.name == f"{_safe_stem(editor_id)}.AppImage")
        try:
            modified = path.stat().st_mtime
        except OSError:
            modified = 0.0
        return (-canonical_score, -modified, path.name.casefold())

    return sorted(candidates.values(), key=key)


def installed_icon_candidates(installed_dir: Path, editor_id: str) -> list[Path]:
    if not installed_dir.is_dir():
        return []
    prefix = f"{_safe_stem(editor_id)}-icon."
    candidates = [
        path.resolve(strict=False)
        for path in installed_dir.glob("*/*/AppImage/*-icon.*")
        if path.is_file() and path.name.casefold().startswith(prefix.casefold())
    ]
    candidates.extend(path.resolve(strict=False) for path in installed_dir.iterdir() if path.is_file() and path.name.casefold().startswith(prefix.casefold()))
    return sorted(dict.fromkeys(candidates), key=lambda path: path.name.casefold())


def uninstall_appimage_integration(
    editor_id: str,
    name: str,
    installed_dir: Path,
    *,
    explicit_path: Path | None = None,
    applications_dir: Path | None = None,
) -> list[Path]:
    """Remove only Suite-managed AppImages/icons plus this editor's desktop entry."""
    installed_dir = installed_dir.expanduser().resolve(strict=False)
    removed: list[Path] = []
    appimages = managed_appimages(installed_dir, editor_id, name, explicit_path=explicit_path)
    targets = list(appimages)
    targets.extend(appimage_metadata_path(path) for path in appimages)
    targets.extend(installed_icon_candidates(installed_dir, editor_id))
    targets.append(desktop_entry_path(editor_id, applications_dir))

    for target in dict.fromkeys(targets):
        target = target.expanduser().resolve(strict=False)
        # AppImages/icons must be direct children of the configured managed
        # directory. Desktop entries must be direct children of applications_dir.
        allowed_parent = desktop_entry_path(editor_id, applications_dir).parent.resolve(strict=False) if target.suffix == ".desktop" else installed_dir
        if target.parent != allowed_parent:
            raise InstallError(f"Refusing to remove an unmanaged path: {target}")
        if target.exists() or target.is_symlink():
            try:
                target.unlink()
            except OSError as exc:
                raise InstallError(f"Could not remove {target}: {exc}") from exc
            removed.append(target)
    return removed


def stage_registered_appimage_integration(
    record: dict,
    *,
    installed_dir: Path,
    applications_dir: Path | None = None,
) -> list[tuple[Path, Path]]:
    """Rename exact registered integration files to hidden staging names.

    The returned ``(original, staged)`` pairs can be restored if a later purge
    step fails, or finalized after the configuration transaction commits.
    """
    installed_dir = installed_dir.expanduser().resolve(strict=False)
    applications_root = (applications_dir or desktop_applications_dir()).expanduser().resolve(strict=False)
    appimage_raw = record.get("appimage_path") or record.get("appimage")
    desktop_raw = record.get("desktop_file_path")
    icon_raw = record.get("icon_path")
    if not isinstance(appimage_raw, str) or not appimage_raw.strip():
        raise InstallError("Managed installation registry has no AppImage path.")
    desktop_required = bool(record.get("desktop_integrated"))
    if desktop_required and (not isinstance(desktop_raw, str) or not desktop_raw.strip()):
        raise InstallError("Desktop-integrated managed installation has no Desktop Entry path.")

    appimage = Path(appimage_raw).expanduser().resolve(strict=False)
    desktop = Path(desktop_raw).expanduser().resolve(strict=False) if isinstance(desktop_raw, str) and desktop_raw.strip() else None
    icon = Path(icon_raw).expanduser().resolve(strict=False) if isinstance(icon_raw, str) and icon_raw.strip() else None
    metadata = appimage_metadata_path(appimage).expanduser().resolve(strict=False)
    if not is_within(appimage, installed_dir) or not is_within(metadata, installed_dir):
        raise InstallError("Refusing to stage registered AppImage data outside the Components folder.")
    if icon is not None and not is_within(icon, installed_dir):
        raise InstallError("Refusing to stage registered icon outside the Components folder.")
    if desktop is not None and desktop.parent != applications_root:
        raise InstallError("Refusing to stage registered Desktop Entry outside the applications folder.")

    token = uuid.uuid4().hex[:10]
    pairs: list[tuple[Path, Path]] = []
    try:
        for original in (appimage, metadata, icon, desktop):
            if original is None or not (original.exists() or original.is_symlink()):
                continue
            staged = original.parent / f".{original.name}.purging-{token}"
            os.replace(original, staged)
            pairs.append((original, staged))
    except Exception:
        for original, staged in reversed(pairs):
            if staged.exists() and not original.exists():
                try:
                    os.replace(staged, original)
                except OSError:
                    pass
        raise
    return pairs


def restore_staged_registered_integration(pairs: list[tuple[Path, Path]]) -> None:
    for original, staged in reversed(pairs):
        if staged.exists() and not original.exists():
            try:
                os.replace(staged, original)
            except OSError as exc:
                raise InstallError(f"Could not restore staged integration file {original}: {exc}") from exc


def finalize_staged_registered_integration(pairs: list[tuple[Path, Path]]) -> list[Path]:
    removed: list[Path] = []
    for original, staged in pairs:
        if staged.exists() or staged.is_symlink():
            try:
                staged.unlink()
            except OSError as exc:
                raise InstallError(f"Could not finalize removal of {original}: {exc}") from exc
            removed.append(original)
    return removed


def uninstall_registered_appimage_integration(
    record: dict,
    *,
    installed_dir: Path,
    applications_dir: Path | None = None,
) -> list[Path]:
    """Remove exactly the paths recorded for one Suite-managed installation.

    This is the normal r5 uninstall path.  It deliberately does not scan for
    similarly named AppImages or icons.  That prevents an unrelated file from
    being deleted just because its filename resembles an editor name.
    """
    installed_dir = installed_dir.expanduser().resolve(strict=False)
    applications_root = (applications_dir or desktop_applications_dir()).expanduser().resolve(strict=False)
    appimage_raw = record.get("appimage_path") or record.get("appimage")
    desktop_raw = record.get("desktop_file_path")
    icon_raw = record.get("icon_path")
    if not isinstance(appimage_raw, str) or not appimage_raw.strip():
        raise InstallError("Managed installation registry has no AppImage path.")
    desktop_required = bool(record.get("desktop_integrated"))
    if desktop_required and (not isinstance(desktop_raw, str) or not desktop_raw.strip()):
        raise InstallError("Desktop-integrated managed installation has no Desktop Entry path.")

    appimage = Path(appimage_raw).expanduser().resolve(strict=False)
    desktop = Path(desktop_raw).expanduser().resolve(strict=False) if isinstance(desktop_raw, str) and desktop_raw.strip() else None
    icon = Path(icon_raw).expanduser().resolve(strict=False) if isinstance(icon_raw, str) and icon_raw.strip() else None
    metadata = appimage_metadata_path(appimage).expanduser().resolve(strict=False)

    if not is_within(appimage, installed_dir):
        raise InstallError(f"Refusing to remove registered AppImage outside the Components folder: {appimage}")
    if not is_within(metadata, installed_dir):
        raise InstallError(f"Refusing to remove metadata outside the Components folder: {metadata}")
    if icon is not None and not is_within(icon, installed_dir):
        raise InstallError(f"Refusing to remove registered icon outside the Components folder: {icon}")
    if desktop is not None and desktop.parent != applications_root:
        raise InstallError(f"Refusing to remove registered Desktop Entry outside the applications folder: {desktop}")

    removed: list[Path] = []
    for target in (appimage, metadata, icon, desktop):
        if target is None:
            continue
        if target.exists() or target.is_symlink():
            try:
                target.unlink()
            except OSError as exc:
                raise InstallError(f"Could not remove {target}: {exc}") from exc
            removed.append(target)
    return removed
