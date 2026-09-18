from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
import re
import struct
import zipfile

from .installer import (
    InstallError,
    archive_editor_root_parts,
    archive_expanded_bytes,
    archive_source_folder_name,
    sha256_file,
    validate_zip,
)
from .registry import MANIFEST_NAMES, builtin_profiles, normalize_extension, slugify
from .versioning import parse_version_text

MAX_METADATA_TEXT = 512 * 1024
MAX_MANIFEST_BYTES = 256 * 1024
MAX_ICON_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ZipEditorInspection:
    zip_path: Path
    archive_sha256: str
    source_folder_name: str
    editor_id: str
    component_kind: str
    publisher_id: str
    name: str
    version: str | None
    description: str
    extensions: tuple[str, ...]
    icon_bytes: bytes | None
    icon_suffix: str | None
    icon_relative: str | None
    builder_relative: str | None
    builder_version: str | None
    expanded_bytes: int = 0

    @property
    def has_builder(self) -> bool:
        return bool(self.builder_relative)


def _relative_name(info: zipfile.ZipInfo, root_parts: tuple[str, ...]) -> PurePosixPath | None:
    pure = PurePosixPath(info.filename.replace("\\", "/"))
    if root_parts:
        if tuple(pure.parts[: len(root_parts)]) != root_parts:
            return None
        relative = PurePosixPath(*pure.parts[len(root_parts) :])
    else:
        relative = pure
    return relative if relative.parts else None


def _read_small_text(archive: zipfile.ZipFile, info: zipfile.ZipInfo, limit: int = MAX_METADATA_TEXT) -> str:
    if info.file_size < 0 or info.file_size > limit:
        return ""
    try:
        return archive.read(info).decode("utf-8", errors="replace")
    except (OSError, KeyError, RuntimeError):
        return ""


def _manifest_from_archive(
    archive: zipfile.ZipFile,
    members: list[zipfile.ZipInfo],
    root_parts: tuple[str, ...],
) -> dict:
    for manifest_name in MANIFEST_NAMES:
        for info in members:
            relative = _relative_name(info, root_parts)
            if relative is None or relative.as_posix().casefold() != manifest_name.casefold():
                continue
            if info.file_size > MAX_MANIFEST_BYTES:
                return {}
            try:
                data = json.loads(archive.read(info).decode("utf-8"))
            except (OSError, UnicodeDecodeError, ValueError, TypeError):
                return {}
            return data if isinstance(data, dict) else {}
    return {}


def _profile_for_archive(source_folder_name: str, manifest: dict, members: list[zipfile.ZipInfo], root_parts: tuple[str, ...]) -> tuple[str, dict]:
    requested = str(manifest.get("id", "")).strip().lower()
    name_hints = [source_folder_name, requested, str(manifest.get("name", ""))]
    child_dirs: set[str] = set()
    for info in members:
        relative = _relative_name(info, root_parts)
        if relative is not None and len(relative.parts) >= 2:
            child_dirs.add(relative.parts[0])
    name_hints.extend(sorted(child_dirs))
    normalized_hints = {slugify(value) for value in name_hints if value}

    for editor_id, profile in builtin_profiles().items():
        aliases = {slugify(alias) for alias in profile["aliases"]}
        aliases.add(slugify(profile["name"]))
        if requested == editor_id or normalized_hints & aliases:
            return editor_id, profile
        if any(any(hint.startswith(alias + "-") for alias in aliases) for hint in normalized_hints):
            return editor_id, profile

    raise InstallError(
        f"Suite Pythoine does not recognize {manifest.get('name') or source_folder_name!s} as a trusted component. "
        "Install a component listed in Suite's trusted component catalogue."
    )


def _builder_score(relative: PurePosixPath, text: str) -> int:
    if relative.suffix.casefold() != ".sh":
        return -1
    name = relative.name.casefold()
    if name.startswith("test") or name.startswith("install"):
        return -1
    parts = {part.casefold() for part in relative.parts}
    score = 0
    if name == "build-fedora-appimage.sh":
        score += 100
    elif name == "build-appimage.sh":
        score += 90
    elif name.startswith("build") and "appimage" in name:
        score += 75
    if "appimage" in parts:
        score += 45
    if "packaging" in parts:
        score += 35
    if "fedora" in parts:
        score += 10
    lowered = text.casefold()
    if score < 75 and "appimage" in lowered and ("appimagetool" in lowered or "appdir" in lowered):
        score += 75
    return score - len(relative.parts)


def _find_builder(
    archive: zipfile.ZipFile,
    members: list[zipfile.ZipInfo],
    root_parts: tuple[str, ...],
) -> tuple[str | None, str | None]:
    candidates: list[tuple[int, str, str | None]] = []
    for info in members:
        relative = _relative_name(info, root_parts)
        if relative is None or info.is_dir() or relative.suffix.casefold() != ".sh":
            continue
        name = relative.name.casefold()
        if "appimage" not in name and "packaging" not in {part.casefold() for part in relative.parts}:
            continue
        text = _read_small_text(archive, info)
        score = _builder_score(relative, text)
        if score >= 0:
            candidates.append((score, relative.as_posix(), parse_version_text(text)))
    if not candidates:
        return None, None
    _score, relative, version = max(candidates, key=lambda item: (item[0], -len(item[1]), item[1].casefold()))
    return relative, version


def _find_source_version(
    archive: zipfile.ZipFile,
    members: list[zipfile.ZipInfo],
    root_parts: tuple[str, ...],
    manifest: dict,
    builder_version: str | None,
) -> str | None:
    value = manifest.get("version") if isinstance(manifest, dict) else None
    if isinstance(value, str) and value.strip():
        return value.strip()
    if builder_version:
        return builder_version

    candidates: list[tuple[int, zipfile.ZipInfo]] = []
    for info in members:
        relative = _relative_name(info, root_parts)
        if relative is None or info.is_dir() or relative.suffix.casefold() != ".py" or info.file_size > MAX_METADATA_TEXT:
            continue
        score = -len(relative.parts)
        if relative.name == "__init__.py":
            score += 30
        if relative.name == "main.py":
            score += 25
        if relative.parent.name.casefold() == "source":
            score += 20
        candidates.append((score, info))
    for _score, info in sorted(candidates, key=lambda item: item[0], reverse=True):
        version = parse_version_text(_read_small_text(archive, info))
        if version:
            return version
    return None


def _icon_score(relative: PurePosixPath, *, editor_id: str, app_name: str, source_folder_name: str) -> int:
    identity = {slugify(value) for value in (editor_id, app_name, source_folder_name) if value}
    parts = tuple(part.casefold() for part in relative.parts)
    part_set = set(parts)
    stem_slug = slugify(relative.stem)
    score = 0
    if stem_slug in identity:
        score += 45
    elif any(stem_slug.startswith(token + "-") or token.startswith(stem_slug + "-") for token in identity if token):
        score += 30
    if "assets" in part_set and "icons" in part_set:
        score += 18
    if "hicolor" in part_set and "apps" in part_set:
        score += 14
    # A canonical/master asset should beat a small runtime derivative with the
    # exact application basename. Pixel/vector quality is considered separately.
    if "master" in stem_slug:
        score += 24
    if "about" in stem_slug:
        score += 4
    if "logo" in stem_slug:
        score += 4
    if "icon" in stem_slug:
        score += 2
    if "docs" in part_set:
        score -= 20
    if "ribbon-icons" in part_set or "toolbar" in part_set:
        score -= 35
    return score


def _png_dimensions(header: bytes) -> tuple[int, int] | None:
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        return None
    try:
        width, height = struct.unpack(">II", header[16:24])
    except struct.error:
        return None
    return (width, height) if width > 0 and height > 0 else None


def _ico_dimensions(header: bytes) -> tuple[int, int] | None:
    # ICO directory: reserved(2), type(2), count(2), then 16-byte entries.
    if len(header) < 22 or header[:4] != b"\x00\x00\x01\x00":
        return None
    try:
        count = struct.unpack("<H", header[4:6])[0]
    except struct.error:
        return None
    if count < 1:
        return None
    best = (0, 0)
    for index in range(min(count, (len(header) - 6) // 16)):
        offset = 6 + index * 16
        width = header[offset] or 256
        height = header[offset + 1] or 256
        if width * height > best[0] * best[1]:
            best = (width, height)
    return best if best != (0, 0) else None


def _icon_quality_bonus(archive: zipfile.ZipFile, info: zipfile.ZipInfo, relative: PurePosixPath) -> int:
    suffix = relative.suffix.casefold()
    if suffix == ".svg":
        # Vector artwork is resolution-independent, but only after the identity/
        # location score has established that it is a plausible application icon.
        return 26
    try:
        with archive.open(info) as handle:
            header = handle.read(4096)
    except (OSError, KeyError, RuntimeError):
        return -20
    dimensions = _png_dimensions(header) if suffix == ".png" else _ico_dimensions(header) if suffix == ".ico" else None
    if dimensions is None:
        return 0
    maximum = max(dimensions)
    if maximum >= 1024:
        return 26
    if maximum >= 512:
        return 22
    if maximum >= 256:
        return 16
    if maximum >= 128:
        return 10
    if maximum >= 64:
        return 3
    return -12


def _manifest_icon_member(
    members: list[zipfile.ZipInfo],
    root_parts: tuple[str, ...],
    icon_value: str,
) -> tuple[zipfile.ZipInfo, PurePosixPath] | None:
    wanted = PurePosixPath(icon_value.replace("\\", "/").lstrip("./"))
    exact: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
    suffix_matches: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
    for info in members:
        relative = _relative_name(info, root_parts)
        if relative is None or info.is_dir() or info.file_size < 0 or info.file_size > MAX_ICON_BYTES:
            continue
        if relative == wanted:
            exact.append((info, relative))
        elif tuple(relative.parts[-len(wanted.parts):]) == tuple(wanted.parts):
            suffix_matches.append((info, relative))
    if exact:
        return exact[0]
    if suffix_matches:
        # Package manifests sometimes describe the icon relative to the nested
        # application module rather than archive root. Prefer the shallowest
        # unambiguous suffix match rather than ignoring the explicit manifest.
        suffix_matches.sort(key=lambda item: (len(item[1].parts), item[1].as_posix().casefold()))
        return suffix_matches[0]
    return None


def _find_icon_bytes(
    archive: zipfile.ZipFile,
    members: list[zipfile.ZipInfo],
    root_parts: tuple[str, ...],
    manifest: dict,
    *,
    editor_id: str,
    app_name: str,
    source_folder_name: str,
) -> tuple[bytes | None, str | None, str | None]:
    icon_value = manifest.get("icon") if isinstance(manifest, dict) else None
    if isinstance(icon_value, str) and icon_value.strip():
        match = _manifest_icon_member(members, root_parts, icon_value.strip())
        if match is not None:
            info, relative = match
            try:
                return archive.read(info), relative.suffix.casefold(), relative.as_posix()
            except (OSError, KeyError, RuntimeError):
                pass

    candidates: list[tuple[int, int, int, str, zipfile.ZipInfo, PurePosixPath]] = []
    for info in members:
        relative = _relative_name(info, root_parts)
        if relative is None or info.is_dir() or relative.suffix.casefold() not in {".png", ".svg", ".ico"}:
            continue
        if info.file_size < 0 or info.file_size > MAX_ICON_BYTES:
            continue
        identity_score = _icon_score(relative, editor_id=editor_id, app_name=app_name, source_folder_name=source_folder_name)
        if identity_score <= 0:
            continue
        quality = _icon_quality_bonus(archive, info, relative)
        # Identity remains the primary trust/relevance signal; quality breaks ties
        # and lets a canonical master beat a tiny equivalent derivative.
        total = identity_score + quality
        candidates.append((total, identity_score, -len(relative.parts), relative.as_posix().casefold(), info, relative))
    if not candidates:
        return None, None, None
    _total, _identity, _depth, _name, info, relative = max(candidates, key=lambda item: (item[0], item[1], item[2], item[3]))
    try:
        return archive.read(info), relative.suffix.casefold(), relative.as_posix()
    except (OSError, KeyError, RuntimeError):
        return None, None, None

def inspect_editor_zip(zip_path: Path, *, python_executable: str | None = None) -> ZipEditorInspection:
    """Inspect editor identity directly from ZIP metadata without extracting it.

    0.2.3 deliberately avoids the previous full temporary extraction just to
    render the wizard Welcome page. Only bounded manifest/version/builder text
    and the selected application logo are read into memory; no editor code is
    imported or executed.
    """
    del python_executable  # Kept for API compatibility; inspection is non-executing.
    zip_path = zip_path.expanduser().resolve(strict=False)
    members = validate_zip(zip_path)
    root_parts = archive_editor_root_parts(members)
    source_folder_name = archive_source_folder_name(zip_path, members)

    try:
        archive = zipfile.ZipFile(zip_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise InstallError(f"Invalid ZIP archive: {exc}") from exc
    with archive:
        manifest = _manifest_from_archive(archive, members, root_parts)
        editor_id, profile = _profile_for_archive(source_folder_name, manifest, members, root_parts)
        component_kind = str(profile.get("component_kind") or "editor")
        name = str(profile.get("name") or manifest.get("name") or source_folder_name)
        publisher_id = str(profile.get("publisher_id") or "").strip()
        ext_source = profile.get("extensions", ())
        if isinstance(ext_source, str):
            ext_source = [item for item in re.split(r"[,;\s]+", ext_source) if item]
        if not isinstance(ext_source, (list, tuple)):
            ext_source = ()
        extensions = tuple(dict.fromkeys(filter(None, (normalize_extension(str(item)) for item in ext_source))))
        description = str(profile.get("description") or manifest.get("description") or "")
        builder_relative, builder_version = _find_builder(archive, members, root_parts)
        version = _find_source_version(archive, members, root_parts, manifest, builder_version)
        icon_bytes, icon_suffix, icon_relative = _find_icon_bytes(
            archive,
            members,
            root_parts,
            manifest,
            editor_id=editor_id,
            app_name=name,
            source_folder_name=source_folder_name,
        )

    return ZipEditorInspection(
        zip_path=zip_path,
        archive_sha256=sha256_file(zip_path),
        source_folder_name=source_folder_name,
        editor_id=editor_id,
        component_kind=component_kind,
        publisher_id=publisher_id,
        name=name,
        version=version,
        description=description,
        extensions=extensions,
        icon_bytes=icon_bytes,
        icon_suffix=icon_suffix,
        icon_relative=icon_relative,
        builder_relative=builder_relative,
        builder_version=builder_version,
        expanded_bytes=archive_expanded_bytes(zip_path, members),
    )
