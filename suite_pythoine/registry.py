from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import struct
from typing import Iterable

from .managed_registry import get_managed_group, get_managed_installation, get_managed_versions
from .component_catalog import COMPONENT_PROFILES, extension_union, mime_type_union
from .versioning import detect_source_version, installed_version_for_appimage, read_appimage_metadata, version_from_filename, versions_match, version_sort_key
from .storage_layout import is_within, iter_portable_roots

MANIFEST_NAMES = ("suite-pythoine-component.json", "suite-pythoine.json", "editor.json")
SCAN_IGNORED_DIRS = frozenset({".git", ".hg", ".svn", "__pycache__", ".venv", "venv", "node_modules", "build", "dist"})

def builtin_profiles() -> dict[str, dict]:
    """Return a compatibility profile view over the live component catalogue."""
    return {
        component_id: {
            "name": profile.name,
            "aliases": profile.identity_hints,
            "extensions": profile.extensions,
            "description": profile.description,
            "publisher_id": profile.publisher_id,
            "component_kind": profile.kind,
            "appimage_prefixes": profile.appimage_prefixes,
            "repository": profile.repository,
            "capabilities": profile.capabilities,
        }
        for component_id, profile in COMPONENT_PROFILES.items()
    }


# Compatibility snapshot for external QA/importers. Internal discovery calls
# builtin_profiles() so a verified cached catalogue can take effect without a
# Suite binary update.
BUILTIN_PROFILES = builtin_profiles()


PAD_FAMILY_EXTENSIONS = extension_union()

# Freedesktop MIME types advertised by Suite Pythoine's AppImage Desktop Entry.
# Several pad-family filename extensions share a MIME type (for example .txt,
# .log, .ini, .cfg and .conf are all represented by text/plain).
PAD_FAMILY_MIME_TYPES = mime_type_union()


def slugify(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return value or "editor"


def normalize_extension(ext: str) -> str:
    ext = ext.strip().lower()
    if not ext:
        return ""
    return ext if ext.startswith(".") else f".{ext}"


def _managed_path_allowed(path: Path, installed_root: Path, config: dict) -> bool:
    if is_within(path, installed_root):
        return True
    raw = config.get("legacy_installed_editors_dir") if isinstance(config, dict) else None
    if isinstance(raw, str) and raw.strip():
        return is_within(path, Path(raw).expanduser().resolve(strict=False))
    return False

@dataclass(slots=True)
class EditorVersionInfo:
    version: str
    portable_root: Path | None = None
    portable_command: tuple[str, ...] | None = None
    appimage_path: Path | None = None
    installed_command: tuple[str, ...] | None = None
    icon: Path | None = None
    managed_record: dict = field(default_factory=dict)
    desktop_integrated: bool = False
    modified: float = 0.0

    @property
    def has_portable(self) -> bool:
        return bool(self.portable_command and self.portable_root and self.portable_root.is_dir())

    @property
    def has_appimage(self) -> bool:
        return bool(self.installed_command and self.appimage_path and self.appimage_path.is_file())

    @property
    def availability_text(self) -> str:
        parts = []
        if self.has_portable:
            parts.append("Portable")
        if self.has_appimage:
            parts.append("AppImage")
        return " + ".join(parts) if parts else "Unavailable"


@dataclass(slots=True)
class EditorEntry:
    editor_id: str
    name: str
    root: Path
    component_kind: str = "editor"
    publisher_id: str = ""
    extensions: tuple[str, ...] = field(default_factory=tuple)
    portable_command: tuple[str, ...] | None = None
    installed_command: tuple[str, ...] | None = None
    launch_mode: str = "auto"
    description: str = ""
    icon: Path | None = None
    manifest_path: Path | None = None
    modified: float = 0.0
    source_version: str | None = None
    installed_version: str | None = None
    managed_installation: dict = field(default_factory=dict)
    versions: tuple[EditorVersionInfo, ...] = field(default_factory=tuple)
    active_version: str | None = None
    desktop_version: str | None = None
    capabilities: tuple[str, ...] = field(default_factory=tuple)

    @property
    def available(self) -> bool:
        # Availability follows the selected runtime. An explicit Portable or
        # AppImage preference is strict; only Automatic may fall back.
        return self.command() is not None

    @property
    def version_status(self) -> str:
        if not (self.portable_command and self.installed_command):
            return "single"
        matched = versions_match(self.source_version, self.installed_version)
        if matched is True:
            return "match"
        if matched is False:
            return "mismatch"
        if self.source_version and not self.installed_version:
            return "unverified"
        return "unknown"

    @property
    def version_note(self) -> str:
        if self.version_status == "mismatch":
            return f"Version mismatch: portable {self.source_version or 'unknown'}, installed {self.installed_version or 'unknown'}"
        if self.version_status == "unverified":
            return f"Installed version unverified; portable is {self.source_version}"
        return ""

    def command(self, preferred: str | None = None) -> tuple[str, ...] | None:
        mode = preferred or self.launch_mode
        if mode == "portable":
            return self.portable_command
        if mode == "installed":
            return self.installed_command
        # Automatic mode is conservative: never silently prefer an installed
        # artifact that is known to disagree with, or cannot be verified against,
        # the portable source currently loaded in the Components folder.
        if self.portable_command and self.installed_command and self.version_status in {"mismatch", "unverified"}:
            return self.portable_command
        return self.installed_command or self.portable_command

    @property
    def source_kind(self) -> str:
        if self.installed_command and self.portable_command:
            return "Installed + Portable"
        if self.installed_command:
            return "Installed"
        if self.portable_command:
            return "Portable"
        return "Unavailable"


def _read_json_manifest(path: Path) -> dict | None:
    """Read one deliberately small JSON manifest without following symlinks."""
    try:
        if not path.is_file() or path.is_symlink():
            return None
        if path.stat().st_size > 256 * 1024:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _trusted_manifest_component_id(data: dict) -> str | None:
    """Resolve a package manifest claim only against the trusted catalogue."""
    requested = str(data.get("id", "")).strip().casefold()
    name = str(data.get("name", "")).strip()
    normalized_name = slugify(name) if name else ""
    for component_id, profile in builtin_profiles().items():
        if requested == component_id:
            return component_id
        aliases = {
            slugify(str(value))
            for value in (
                *profile.get("aliases", ()),
                profile.get("name") or component_id,
                component_id,
            )
            if value
        }
        if normalized_name and normalized_name in aliases:
            return component_id
    return None


def _trusted_package_manifest_names() -> tuple[str, ...]:
    """Return trusted component-specific manifest names for Pad-style packages."""
    names: set[str] = set(MANIFEST_NAMES)
    for component_id, profile in builtin_profiles().items():
        slugs = {
            slugify(component_id),
            slugify(str(profile.get("name") or component_id)),
        }
        for alias in profile.get("aliases", ()):
            if alias:
                slugs.add(slugify(str(alias)))
        for value in slugs:
            if not value:
                continue
            names.add(f"{value}.json")
            names.add(f"{value.replace('-', '_')}.json")
    return tuple(sorted(names))


def _read_manifest(folder: Path) -> tuple[dict, Path | None]:
    """Read trusted metadata from the portable root or immediate app package.

    Root compatibility manifests retain priority. Pad-family portable source
    trees may keep their identity manifest inside the application package, for
    example ``python_lair2/python-lair.json`` or
    ``sheepy_pad/sheepy-pad.json``. Nested scanning is deliberately bounded to
    immediate child packages and trusted manifest filenames; the package JSON
    remains only an identity hint and never grants catalogue trust/capabilities.
    """
    for name in MANIFEST_NAMES:
        manifest_path = folder / name
        if not manifest_path.is_file():
            continue
        data = _read_json_manifest(manifest_path)
        if data is not None:
            return data, manifest_path
        return {}, manifest_path

    try:
        children = sorted(
            (
                child for child in folder.iterdir()
                if child.is_dir()
                and not child.is_symlink()
                and not child.name.startswith(".")
                and child.name not in SCAN_IGNORED_DIRS
            ),
            key=lambda child: child.name.casefold(),
        )
    except OSError:
        return {}, None

    candidates: list[tuple[str, Path, dict]] = []
    seen: set[Path] = set()
    for child in children:
        for name in _trusted_package_manifest_names():
            manifest_path = child / name
            if manifest_path in seen or not manifest_path.is_file():
                continue
            seen.add(manifest_path)
            data = _read_json_manifest(manifest_path)
            if data is None:
                continue
            component_id = _trusted_manifest_component_id(data)
            if component_id is not None:
                candidates.append((component_id, manifest_path, data))

    if not candidates:
        return {}, None
    component_ids = {component_id for component_id, _, _ in candidates}
    if len(component_ids) != 1:
        return {}, None
    component_id = next(iter(component_ids))
    candidates.sort(key=lambda item: (
        item[1].name.casefold() != f"{component_id}.json",
        len(item[1].parts),
        item[1].as_posix().casefold(),
    ))
    _, manifest_path, data = candidates[0]
    return data, manifest_path


class UnknownComponentError(ValueError):
    pass


def _profile_for(folder: Path, manifest: dict) -> tuple[str, dict]:
    requested = str(manifest.get("id", "")).strip().casefold()
    name_hints = [folder.name, requested, str(manifest.get("name", ""))]
    try:
        name_hints.extend(p.name for p in folder.iterdir() if p.is_dir())
    except OSError:
        pass
    normalized_hints = {slugify(value) for value in name_hints if value}

    for component_id, profile in builtin_profiles().items():
        hints = {slugify(value) for value in profile.get("aliases", ())}
        hints.add(slugify(str(profile.get("name") or component_id)))
        if requested == component_id or normalized_hints & hints:
            return component_id, profile
        if any(any(hint.startswith(alias + "-") for alias in hints) for hint in normalized_hints):
            return component_id, profile

    raise UnknownComponentError(
        f"Suite Pythoine does not recognize {manifest.get('name') or folder.name!s} as a trusted component."
    )


def _resolve_manifest_command(folder: Path, value, python_executable: str | None) -> tuple[str, ...] | None:
    if not value:
        return None
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not value or not all(isinstance(x, str) for x in value):
        return None

    parts: list[str] = []
    for index, part in enumerate(value):
        candidate = Path(part)
        if index == 0 and not candidate.is_absolute() and (folder / candidate).exists():
            resolved = (folder / candidate).resolve()
            if resolved.suffix.lower() == ".py":
                if not python_executable:
                    return None
                parts.extend([python_executable, str(resolved)])
            else:
                parts.append(str(resolved))
        else:
            parts.append(part)
    return tuple(parts)


def _find_portable_command(folder: Path, manifest: dict, python_executable: str | None) -> tuple[str, ...] | None:
    command = _resolve_manifest_command(folder, manifest.get("portable_command") or manifest.get("command"), python_executable)
    if command:
        return command

    main_py = folder / "main.py"
    if main_py.is_file() and python_executable:
        return (python_executable, str(main_py.resolve()))

    child_mains = [p for p in folder.glob("*/main.py") if p.is_file()]
    if len(child_mains) == 1 and python_executable:
        return (python_executable, str(child_mains[0].resolve()))

    if os.name == "nt":
        exes = sorted(p for p in folder.glob("*.exe") if p.is_file())
        if exes:
            return (str(exes[0].resolve()),)
    else:
        appimages = sorted([p for p in folder.glob("*.AppImage") if p.is_file()] + [p for p in folder.glob("*.appimage") if p.is_file()])
        if appimages:
            return (str(appimages[0].resolve()),)
    return None


def _find_installed_command(editor_id: str, name: str, installed_dir: Path, manifest: dict, folder: Path, python_executable: str | None) -> tuple[str, ...] | None:
    command = _resolve_manifest_command(folder, manifest.get("installed_command"), python_executable)
    if command:
        return command
    if not installed_dir.is_dir():
        return None

    target_tokens = set(slugify(editor_id).split("-")) | set(slugify(name).split("-"))
    primary_tokens = {token for token in target_tokens if token not in {"pad", "editor", "2"} and not token.isdigit()}
    candidates: list[Path] = []
    patterns = ("*.exe",) if os.name == "nt" else ("*.AppImage", "*.appimage")
    # New storage layout nests artifacts under <Application>/<Version>/AppImage.
    # Keep direct-root scanning as compatibility for pre-0.1.2 managed folders.
    for pattern in patterns:
        candidates.extend(installed_dir.glob(pattern))
        candidates.extend(installed_dir.glob(f"*/*/AppImage/{pattern}"))

    scored: list[tuple[int, float, Path]] = []
    for path in candidates:
        tokens = set(slugify(path.stem).split("-"))
        if primary_tokens and not (primary_tokens & tokens):
            continue
        score = len(target_tokens & tokens)
        if not score:
            continue
        try:
            modified = path.stat().st_mtime
        except OSError:
            modified = 0.0
        scored.append((score, modified, path))
    if not scored:
        return None
    return (str(max(scored, key=lambda item: (item[0], item[1]))[2].resolve()),)


def _bounded_files(folder: Path, *, max_depth: int = 5) -> Iterable[Path]:
    """Yield ordinary files without following symlinked or generated subtrees."""
    base_depth = len(folder.parts)
    for root, dirs, files in os.walk(folder, followlinks=False):
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


def _filesystem_icon_quality(path: Path) -> int:
    suffix = path.suffix.casefold()
    if suffix == ".svg":
        return 26
    try:
        header = path.read_bytes()[:4096]
    except OSError:
        return -20
    dimensions: tuple[int, int] | None = None
    if suffix == ".png" and len(header) >= 24 and header[:8] == b"\x89PNG\r\n\x1a\n" and header[12:16] == b"IHDR":
        try:
            dimensions = struct.unpack(">II", header[16:24])
        except struct.error:
            dimensions = None
    elif suffix == ".ico" and len(header) >= 22 and header[:4] == b"\x00\x00\x01\x00":
        try:
            count = struct.unpack("<H", header[4:6])[0]
        except struct.error:
            count = 0
        best = (0, 0)
        for index in range(min(count, (len(header) - 6) // 16)):
            offset = 6 + index * 16
            width = header[offset] or 256
            height = header[offset + 1] or 256
            if width * height > best[0] * best[1]:
                best = (width, height)
        dimensions = best if best != (0, 0) else None
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


def _find_icon(folder: Path, manifest: dict, *, editor_id: str = "", app_name: str = "") -> Path | None:
    """Find the best application identity icon, preferring declared/master quality."""
    icon_value = manifest.get("icon")
    if isinstance(icon_value, str) and icon_value.strip():
        wanted = Path(icon_value.strip())
        if wanted.is_absolute():
            if wanted.is_file() and not wanted.is_symlink():
                return wanted.resolve()
        else:
            direct = folder / wanted
            if direct.is_file() and not direct.is_symlink():
                return direct.resolve()
            wanted_parts = tuple(part.casefold() for part in wanted.parts if part not in {".", ""})
            suffix_matches: list[Path] = []
            if wanted_parts:
                for candidate in _bounded_files(folder, max_depth=5):
                    try:
                        relative = candidate.relative_to(folder)
                    except ValueError:
                        continue
                    relative_parts = tuple(part.casefold() for part in relative.parts)
                    if len(relative_parts) >= len(wanted_parts) and relative_parts[-len(wanted_parts):] == wanted_parts:
                        suffix_matches.append(candidate)
            if suffix_matches:
                suffix_matches.sort(key=lambda item: (len(item.relative_to(folder).parts), item.as_posix().casefold()))
                return suffix_matches[0].resolve()

    identity = {slugify(value) for value in (editor_id, app_name, folder.name) if value}
    candidates: list[tuple[int, int, int, str, Path]] = []
    for path in _bounded_files(folder, max_depth=5):
        if path.suffix.casefold() not in {".png", ".svg", ".ico"}:
            continue
        try:
            relative = path.relative_to(folder)
        except ValueError:
            continue
        parts = tuple(part.casefold() for part in relative.parts)
        part_set = set(parts)
        stem_slug = slugify(path.stem)
        score = 0
        if stem_slug in identity:
            score += 45
        elif any(stem_slug.startswith(token + "-") or token.startswith(stem_slug + "-") for token in identity if token):
            score += 30
        if "assets" in part_set and "icons" in part_set:
            score += 18
        if "hicolor" in part_set and "apps" in part_set:
            score += 14
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
        if score <= 0:
            continue
        total = score + _filesystem_icon_quality(path)
        candidates.append((total, score, -len(relative.parts), relative.as_posix().casefold(), path))
    if not candidates:
        return None
    best = max(candidates, key=lambda item: (item[0], item[1], item[2], item[3]))
    return best[4].resolve()

def inspect_editor_root(
    folder: Path,
    *,
    config: dict | None = None,
    installed_dir: Path | None = None,
    python_executable: str | None = None,
) -> EditorEntry:
    """Inspect one portable editor root without importing or executing it.

    This is used by the r6 installation wizard to show the editor's identity,
    formats, version and logo before anything is copied into My Editors.
    """
    config = config if isinstance(config, dict) else {}
    installed_dir = (installed_dir or (folder.parent / ".suite-no-installed")).expanduser().resolve(strict=False)
    overrides = config.get("editor_overrides", {}) if isinstance(config, dict) else {}
    manifest, manifest_path = _read_manifest(folder)
    editor_id, profile = _profile_for(folder, manifest)
    override = overrides.get(editor_id, {}) if isinstance(overrides, dict) else {}
    if not isinstance(override, dict):
        override = {}

    name = str(override.get("name") or manifest.get("name") or profile.get("name") or folder.name)
    publisher_id = str(
        manifest.get("publisher_id")
        or manifest.get("publisher")
        or profile.get("publisher_id")
        or ""
    ).strip()
    # The trusted component catalogue is the canonical capability source.
    # A user override remains possible, but stale package/registry metadata must
    # not resurrect formats that the current official profile no longer owns.
    ext_source = override.get("extensions") if "extensions" in override else profile.get("extensions", manifest.get("extensions", ()))
    if isinstance(ext_source, str):
        ext_source = [x for x in re.split(r"[,;\s]+", ext_source) if x]
    if not isinstance(ext_source, (list, tuple)):
        ext_source = ()
    extensions = tuple(dict.fromkeys(filter(None, (normalize_extension(str(x)) for x in ext_source))))
    source_version = detect_source_version(folder, manifest)
    portable = _find_portable_command(folder, manifest, python_executable)

    managed = get_managed_installation(config, editor_id, source_version) if source_version else get_managed_installation(config, editor_id)
    managed_path = None
    raw_managed_path = managed.get("appimage_path") if managed else None
    if isinstance(raw_managed_path, str) and raw_managed_path.strip():
        candidate = Path(raw_managed_path).expanduser().resolve(strict=False)
        if candidate.is_file() and _managed_path_allowed(candidate, installed_dir, config):
            managed_path = candidate

    installed = (str(managed_path),) if managed_path is not None else _find_installed_command(
        editor_id, name, installed_dir, manifest, folder, python_executable
    )
    launch_mode = str(override.get("launch_mode", "auto"))
    if launch_mode not in {"auto", "portable", "installed"}:
        launch_mode = "auto"

    installed_override = override.get("installed_path")
    if installed_override:
        path = Path(str(installed_override)).expanduser().resolve(strict=False)
        if path.is_file() and (managed_path is None or path != managed_path):
            installed = (str(path),)

    installed_path = Path(installed[0]).expanduser().resolve(strict=False) if installed else None
    if managed_path is not None and installed_path == managed_path:
        value = managed.get("version")
        installed_version = str(value).strip() if isinstance(value, str) and value.strip() else installed_version_for_appimage(installed_path, override)
    else:
        installed_version = installed_version_for_appimage(installed_path, override)

    try:
        modified = folder.stat().st_mtime
    except OSError:
        modified = 0.0

    description = str(manifest.get("description") or profile.get("description") or "")
    return EditorEntry(
        editor_id=editor_id,
        name=name,
        root=folder.resolve(strict=False),
        component_kind=str(profile.get("component_kind") or "editor"),
        publisher_id=publisher_id,
        capabilities=tuple(profile.get("capabilities") or ()),
        extensions=extensions,
        portable_command=portable,
        installed_command=installed,
        launch_mode=launch_mode,
        description=description,
        icon=_find_icon(folder, manifest, editor_id=editor_id, app_name=name),
        manifest_path=manifest_path,
        modified=modified,
        source_version=source_version,
        installed_version=installed_version,
        managed_installation=managed,
    )


def _managed_version_info(
    editor_id: str,
    version: str,
    record: dict,
    *,
    installed_dir: Path,
    config: dict,
) -> EditorVersionInfo | None:
    raw_appimage = record.get("appimage_path")
    appimage = None
    installed_command = None
    if isinstance(raw_appimage, str) and raw_appimage.strip():
        candidate = Path(raw_appimage).expanduser().resolve(strict=False)
        if candidate.is_file() and _managed_path_allowed(candidate, installed_dir, config):
            appimage = candidate
            installed_command = (str(candidate),)
    icon = None
    raw_icon = record.get("icon_path")
    if isinstance(raw_icon, str) and raw_icon.strip():
        candidate = Path(raw_icon).expanduser().resolve(strict=False)
        if candidate.is_file() and _managed_path_allowed(candidate, installed_dir, config):
            icon = candidate
    modified = 0.0
    for candidate in (appimage, icon):
        if candidate is not None:
            try:
                modified = max(modified, candidate.stat().st_mtime)
            except OSError:
                pass
    if appimage is None and icon is None:
        return None
    return EditorVersionInfo(
        version=version,
        appimage_path=appimage,
        installed_command=installed_command,
        icon=icon,
        managed_record=dict(record),
        desktop_integrated=bool(record.get("desktop_integrated")),
        modified=modified,
    )


def _version_for_portable(entry: EditorEntry) -> str:
    if entry.source_version:
        return entry.source_version
    try:
        if entry.root.name.casefold() == "portable":
            return entry.root.parent.name
    except OSError:
        pass
    return "Unknown"


def _active_version_for(editor_id: str, versions: dict[str, EditorVersionInfo], config: dict, managed_group: dict) -> str:
    overrides = config.get("editor_overrides", {}) if isinstance(config, dict) else {}
    override = overrides.get(editor_id, {}) if isinstance(overrides, dict) else {}
    requested = override.get("active_version") if isinstance(override, dict) else None
    if isinstance(requested, str) and requested in versions:
        return requested
    managed_active = managed_group.get("active_version") if managed_group else None
    if isinstance(managed_active, str) and managed_active in versions:
        return managed_active
    return max(versions, key=version_sort_key)


def _discover_unregistered_appimages(editors_root: Path, config: dict) -> dict[str, list[tuple[str, EditorVersionInfo, dict]]]:
    """Inventory versioned AppImages even when an older registry was overwritten.

    The 0.1.x registry could remember only one AppImage version, while the new
    filesystem already retained older version directories. 0.2.0 therefore
    treats the canonical ``<Application>/<Version>/AppImage`` hierarchy as
    trustworthy inventory and uses sidecar/profile metadata only for identity.
    Nothing is automatically deleted or desktop-integrated by this scan.
    """
    root = editors_root.expanduser().resolve(strict=False)
    result: dict[str, list[tuple[str, EditorVersionInfo, dict]]] = {}
    if not root.is_dir():
        return result
    managed_paths = {
        Path(record["appimage_path"]).expanduser().resolve(strict=False)
        for editor_id in (config.get("managed_installations", {}) if isinstance(config, dict) else {})
        for record in get_managed_versions(config, str(editor_id)).values()
        if isinstance(record.get("appimage_path"), str) and record.get("appimage_path")
    }
    try:
        applications = [path for path in root.iterdir() if path.is_dir() and not path.is_symlink() and not path.name.startswith(".")]
    except OSError:
        return result
    for application in applications:
        try:
            versions = [path for path in application.iterdir() if path.is_dir() and not path.is_symlink() and not path.name.startswith(".")]
        except OSError:
            continue
        for version_dir in versions:
            app_dir = version_dir / "AppImage"
            if not app_dir.is_dir() or app_dir.is_symlink():
                continue
            try:
                candidates = sorted(
                    [path for path in app_dir.iterdir() if path.is_file() and not path.is_symlink() and path.suffix.casefold() == ".appimage"],
                    key=lambda path: path.name.casefold(),
                )
            except OSError:
                continue
            for appimage in candidates:
                resolved = appimage.resolve(strict=False)
                if resolved in managed_paths:
                    continue
                metadata = read_appimage_metadata(appimage)
                manifest_hint = {
                    "id": metadata.get("editor_id") or "",
                    "name": metadata.get("name") or application.name,
                }
                editor_id, profile = _profile_for(application, manifest_hint)
                version = str(metadata.get("version") or version_from_filename(appimage) or version_dir.name).strip() or version_dir.name
                icon = None
                for candidate in sorted(app_dir.glob("*-icon.*")):
                    if candidate.is_file() and not candidate.is_symlink() and candidate.suffix.casefold() in {".png", ".svg", ".ico"}:
                        icon = candidate.resolve(strict=False)
                        break
                info = EditorVersionInfo(
                    version=version,
                    appimage_path=resolved,
                    installed_command=(str(resolved),),
                    icon=icon,
                    managed_record={},
                    desktop_integrated=False,
                    modified=appimage.stat().st_mtime if appimage.exists() else 0.0,
                )
                identity = {
                    "name": str(metadata.get("name") or profile.get("name") or application.name),
                    "publisher_id": str(metadata.get("publisher_id") or profile.get("publisher_id") or ""),
                    "extensions": metadata.get("extensions") or profile.get("extensions", ()),
                    "description": str(metadata.get("description") or profile.get("description") or ""),
                }
                result.setdefault(editor_id, []).append((version, info, identity))
    return result


def discover_editors(
    my_editors_dir: Path,
    installed_dir: Path,
    config: dict,
    *,
    python_executable: str | None,
) -> list[EditorEntry]:
    """Discover one application card while retaining every managed version.

    0.2.0 deliberately separates *application discovery* from *version
    inventory*. The Dashboard/sidebar still has one entry per application, but
    ``EditorEntry.versions`` contains every portable/AppImage version that is
    actually present. ``active_version`` chooses the normal launch target and
    ``desktop_version`` records which AppImage owns the single host launcher.
    """
    my_editors_dir.mkdir(parents=True, exist_ok=True)
    portable_entries: list[EditorEntry] = []
    for folder in iter_portable_roots(my_editors_dir) or ():
        try:
            portable_entries.append(
                inspect_editor_root(
                    folder,
                    config=config,
                    installed_dir=installed_dir,
                    python_executable=python_executable,
                )
            )
        except UnknownComponentError:
            continue

    # Compatibility for a manually placed legacy portable tree.
    try:
        direct = sorted(
            (p for p in my_editors_dir.iterdir() if p.is_dir() and not p.is_symlink() and not p.name.startswith(".")),
            key=lambda p: p.name.casefold(),
        )
    except OSError:
        direct = []
    managed_portable_paths = {entry.root.resolve(strict=False) for entry in portable_entries}
    for folder in direct:
        if folder.resolve(strict=False) in managed_portable_paths:
            continue
        if (folder / "main.py").is_file() or (folder / "editor.json").is_file() or (folder / "suite-pythoine.json").is_file():
            try:
                portable_entries.append(
                    inspect_editor_root(folder, config=config, installed_dir=installed_dir, python_executable=python_executable)
                )
            except UnknownComponentError:
                continue

    grouped: dict[str, list[EditorEntry]] = {}
    for entry in portable_entries:
        grouped.setdefault(entry.editor_id, []).append(entry)

    managed_raw = config.get("managed_installations", {}) if isinstance(config, dict) else {}
    managed_ids = {str(key) for key in managed_raw} if isinstance(managed_raw, dict) else set()
    unregistered = _discover_unregistered_appimages(my_editors_dir, config)
    editor_ids = set(grouped) | managed_ids | set(unregistered)
    result: list[EditorEntry] = []
    installed_root = installed_dir.expanduser().resolve(strict=False)

    for editor_id in sorted(editor_ids, key=str.casefold):
        portable_group = grouped.get(editor_id, [])
        managed_group = get_managed_group(config, editor_id)
        managed_versions = get_managed_versions(config, editor_id)
        versions: dict[str, EditorVersionInfo] = {}

        # Portable roots are authoritative for source commands and source icon.
        for source in portable_group:
            version = _version_for_portable(source)
            managed = managed_versions.get(version, {})
            appimage = None
            installed_command = None
            raw_appimage = managed.get("appimage_path") if managed else None
            if isinstance(raw_appimage, str) and raw_appimage.strip():
                candidate = Path(raw_appimage).expanduser().resolve(strict=False)
                if candidate.is_file() and _managed_path_allowed(candidate, installed_root, config):
                    appimage = candidate
                    installed_command = (str(candidate),)
            icon = source.icon
            if icon is None and managed:
                raw_icon = managed.get("icon_path")
                if isinstance(raw_icon, str) and raw_icon.strip():
                    candidate = Path(raw_icon).expanduser().resolve(strict=False)
                    if candidate.is_file() and _managed_path_allowed(candidate, installed_root, config):
                        icon = candidate
            versions[version] = EditorVersionInfo(
                version=version,
                portable_root=source.root,
                portable_command=source.portable_command,
                appimage_path=appimage,
                installed_command=installed_command,
                icon=icon,
                managed_record=dict(managed),
                desktop_integrated=bool(managed and managed.get("desktop_integrated")),
                modified=source.modified,
            )

        # A retained AppImage version must remain visible even if its portable
        # source was removed. Merge it into an existing version record if needed.
        for version, record in managed_versions.items():
            managed_info = _managed_version_info(editor_id, version, record, installed_dir=installed_root, config=config)
            if managed_info is None:
                continue
            if version in versions:
                current = versions[version]
                current.appimage_path = managed_info.appimage_path
                current.installed_command = managed_info.installed_command
                current.managed_record = managed_info.managed_record
                current.desktop_integrated = managed_info.desktop_integrated
                current.modified = max(current.modified, managed_info.modified)
                if current.icon is None:
                    current.icon = managed_info.icon
            else:
                versions[version] = managed_info

        unregistered_identity: dict = {}
        for version, unmanaged_info, identity in unregistered.get(editor_id, []):
            unregistered_identity = identity or unregistered_identity
            if version in versions:
                current = versions[version]
                if current.appimage_path is None:
                    current.appimage_path = unmanaged_info.appimage_path
                    current.installed_command = unmanaged_info.installed_command
                if current.icon is None:
                    current.icon = unmanaged_info.icon
                current.modified = max(current.modified, unmanaged_info.modified)
            else:
                versions[version] = unmanaged_info

        if not versions:
            continue
        active_version = _active_version_for(editor_id, versions, config, managed_group)
        active = versions[active_version]

        # Presentation metadata can come from any portable source, otherwise the
        # active managed record/profile keeps installed-only editors useful.
        base = next((entry for entry in portable_group if _version_for_portable(entry) == active_version), None)
        if base is None and portable_group:
            base = max(portable_group, key=lambda entry: version_sort_key(_version_for_portable(entry)))
        profile = builtin_profiles().get(editor_id, {})
        managed_active = managed_versions.get(active_version, {})
        name = str((base.name if base else None) or managed_group.get("name") or managed_active.get("name") or unregistered_identity.get("name") or profile.get("name") or editor_id)
        publisher_id = str((base.publisher_id if base else None) or managed_group.get("publisher_id") or managed_active.get("publisher_id") or unregistered_identity.get("publisher_id") or profile.get("publisher_id") or "").strip()
        overrides = config.get("editor_overrides", {}) if isinstance(config, dict) else {}
        override = overrides.get(editor_id, {}) if isinstance(overrides, dict) else {}
        if not isinstance(override, dict):
            override = {}
        if "extensions" in override:
            extension_source = override.get("extensions") or ()
        elif profile.get("extensions"):
            extension_source = profile.get("extensions", ())
        elif base and base.extensions:
            extension_source = base.extensions
        else:
            extension_source = managed_active.get("extensions") or unregistered_identity.get("extensions") or ()
        extensions = tuple(dict.fromkeys(
            normalize_extension(str(value)) for value in extension_source if normalize_extension(str(value))
        ))
        description = str(profile.get("description") or (base.description if base else None) or managed_active.get("description") or unregistered_identity.get("description") or "")
        launch_mode = str(override.get("launch_mode", "auto"))
        if launch_mode not in {"auto", "portable", "installed"}:
            launch_mode = "auto"

        logical_root = active.portable_root or (my_editors_dir / name / active_version / "Portable")
        sorted_versions = tuple(sorted(versions.values(), key=lambda item: version_sort_key(item.version), reverse=True))
        desktop_version = managed_group.get("desktop_version") if managed_group else None
        result.append(EditorEntry(
            editor_id=editor_id,
            name=name,
            root=logical_root.resolve(strict=False),
            component_kind=str(profile.get("component_kind") or (base.component_kind if base else "editor")),
            publisher_id=publisher_id,
            capabilities=tuple(profile.get("capabilities") or (base.capabilities if base else ())),
            extensions=extensions,
            portable_command=active.portable_command,
            installed_command=active.installed_command,
            launch_mode=launch_mode,
            description=description,
            icon=active.icon or (base.icon if base else None),
            manifest_path=base.manifest_path if base else None,
            modified=max((item.modified for item in sorted_versions), default=0.0),
            source_version=active_version if active.has_portable else None,
            installed_version=active_version if active.has_appimage else None,
            managed_installation=dict(active.managed_record),
            versions=sorted_versions,
            active_version=active_version,
            desktop_version=str(desktop_version) if isinstance(desktop_version, str) else None,
        ))

    return sorted(result, key=lambda entry: (entry.name.casefold(), entry.editor_id.casefold()))


def editors_for_extension(editors: Iterable[EditorEntry], extension: str) -> list[EditorEntry]:
    extension = normalize_extension(extension)
    return [entry for entry in editors if extension in entry.extensions and entry.available]
