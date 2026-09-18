from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
import struct

from .installer import InstallError
from .component_catalog import COMPONENT_PROFILES
from .storage_layout import normalized_architecture
from .versioning import read_appimage_metadata

MAX_APPIMAGE_BYTES = 2 * 1024 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class AppImageInspection:
    appimage_path: Path
    appimage_sha256: str
    editor_id: str
    component_kind: str
    publisher_id: str
    name: str
    version: str
    architecture: str
    description: str
    extensions: tuple[str, ...]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _elf_architecture(path: Path) -> str:
    try:
        with path.open("rb") as handle:
            header = handle.read(64)
    except OSError as exc:
        raise InstallError(f"Could not read AppImage: {exc}") from exc
    if len(header) < 20 or header[:4] != b"\x7fELF":
        raise InstallError("The selected file is not an ELF AppImage executable.")
    data_encoding = header[5] if len(header) > 5 else 1
    endian = ">" if data_encoding == 2 else "<"
    machine = struct.unpack(endian + "H", header[18:20])[0]
    return {
        62: "x86_64",
        183: "aarch64",
        3: "i386",
        40: "armhf",
    }.get(machine, "unknown")


def _strip_architecture(stem: str) -> tuple[str, str | None]:
    match = re.search(r"(?:[-_.])(x86_64|amd64|aarch64|arm64|i386|i686|armhf)$", stem, re.IGNORECASE)
    if not match:
        return stem, None
    return stem[: match.start()], normalized_architecture(match.group(1))


def _known_specs() -> list[tuple[str, str, str, str, tuple[str, ...], str, tuple[str, ...]]]:
    specs: list[tuple[str, str, str, str, tuple[str, ...], str, tuple[str, ...]]] = []
    for component_id, profile in COMPONENT_PROFILES.items():
        specs.append(
            (
                component_id,
                profile.kind,
                profile.name,
                profile.publisher_id,
                profile.appimage_prefixes or (profile.name.replace(" ", "-"),),
                profile.description,
                profile.extensions,
            )
        )
    return specs


def _identity_from_filename(path: Path) -> tuple[str, str, str, str, str, tuple[str, ...], str] | None:
    stem = path.name[:-9] if path.name.casefold().endswith(".appimage") else path.stem
    stem_without_arch, _arch = _strip_architecture(stem)
    choices: list[tuple[int, str, str, str, str, str, tuple[str, ...]]] = []
    for component_id, kind, name, publisher, prefixes, description, extensions in _known_specs():
        for prefix in prefixes:
            token = prefix + "-"
            if not stem_without_arch.casefold().startswith(token.casefold()):
                continue
            version = stem_without_arch[len(token):].strip("-_. ")
            if not version or not version[0].isdigit():
                continue
            choices.append((len(prefix), component_id, kind, name, publisher, version, extensions))
    if not choices:
        return None
    _length, component_id, kind, name, publisher, version, extensions = max(choices, key=lambda item: item[0])
    description = next(spec[5] for spec in _known_specs() if spec[0] == component_id)
    return component_id, kind, name, publisher, version, extensions, description


def inspect_appimage(path: Path) -> AppImageInspection:
    path = path.expanduser().resolve(strict=False)
    if not path.is_file() or path.is_symlink():
        raise InstallError(f"AppImage does not exist or is not an ordinary file: {path}")
    if path.suffix.casefold() != ".appimage":
        raise InstallError("The selected file is not an .AppImage file.")
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise InstallError(f"Could not inspect AppImage: {exc}") from exc
    if size <= 0 or size > MAX_APPIMAGE_BYTES:
        raise InstallError("The AppImage is empty or exceeds Suite Pythoine's 2 GiB import limit.")

    elf_arch = _elf_architecture(path)
    stem = path.name[:-9]
    _without_arch, filename_arch = _strip_architecture(stem)
    architecture = filename_arch or elf_arch
    if filename_arch and elf_arch != "unknown" and filename_arch != elf_arch:
        raise InstallError(f"AppImage architecture mismatch: filename says {filename_arch}, ELF says {elf_arch}.")

    digest = _sha256(path)
    metadata = read_appimage_metadata(path)
    metadata_hash = metadata.get("appimage_sha256") or metadata.get("sha256")
    if isinstance(metadata_hash, str) and metadata_hash.strip() and metadata_hash.casefold() != digest.casefold():
        raise InstallError("The AppImage does not match the SHA-256 recorded in its Suite Pythoine sidecar.")

    editor_id = str(metadata.get("editor_id") or "").strip()
    name = str(metadata.get("name") or "").strip()
    publisher = str(metadata.get("publisher_id") or "").strip()
    version = str(metadata.get("version") or "").strip()
    extensions_value = metadata.get("extensions")
    description = str(metadata.get("description") or "").strip()
    extensions: tuple[str, ...] = ()
    if isinstance(extensions_value, (list, tuple)):
        extensions = tuple(str(value).strip() for value in extensions_value if str(value).strip())

    profile = COMPONENT_PROFILES.get(editor_id) if editor_id else None
    if editor_id and profile is None:
        raise InstallError(f"Suite Pythoine does not recognize component identity {editor_id!r}.")
    component_kind = profile.kind if profile is not None else "editor"
    known = _identity_from_filename(path)
    if not (editor_id and name and version):
        if known is None:
            raise InstallError(
                "Suite Pythoine could not identify this AppImage from a trusted Suite sidecar or a known Pad-family filename. "
                "Use an AppImage named with the application, version and architecture, for example Ricopad-0.3.3-x86_64.AppImage."
            )
        known_id, known_kind, known_name, known_publisher, known_version, known_extensions, known_description = known
        editor_id = editor_id or known_id
        component_kind = known_kind
        name = name or known_name
        publisher = publisher or known_publisher
        version = version or known_version
        extensions = extensions or known_extensions
        description = description or known_description
    else:
        # Do not let a sidecar silently re-label a known Pad-family filename.
        if known is not None and editor_id != known[0]:
            raise InstallError(f"AppImage identity mismatch: sidecar says {editor_id}, filename identifies {known[0]}.")
        if known is not None:
            component_kind = known[1]
            extensions = extensions or known[5]
            description = description or known[6]
            publisher = publisher or known[3]
        elif profile is not None:
            component_kind = profile.kind
            name = profile.name
            publisher = profile.publisher_id
            extensions = extensions or profile.extensions
            description = description or profile.description

    return AppImageInspection(
        appimage_path=path,
        appimage_sha256=digest,
        editor_id=editor_id,
        component_kind=component_kind,
        publisher_id=publisher or "brunonlinespace",
        name=name,
        version=version,
        architecture=architecture,
        description=description,
        extensions=extensions,
    )
