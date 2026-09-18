from __future__ import annotations

from pathlib import Path
import platform
import re

PUBLISHER_ID = "brunonlinespace"
APPLICATION_KEY = "suite-pythoine"
DEFAULT_COMPONENTS_FOLDER_NAME = "Suite Pythoine"
LEGACY_DEFAULT_EDITORS_FOLDER_NAME = "Suite Pythoine Editors"
# Compatibility alias for existing internal call sites; the value is the new canonical root.
DEFAULT_EDITORS_FOLDER_NAME = DEFAULT_COMPONENTS_FOLDER_NAME
PORTABLE_FOLDER_NAME = "Portable"
APPIMAGE_FOLDER_NAME = "AppImage"


def safe_component(value: object, fallback: str = "Unknown") -> str:
    text = re.sub(r"[^A-Za-z0-9._ -]+", "-", str(value or "").strip()).strip(" .-_")
    return text or fallback


def application_folder_name(name: str) -> str:
    return safe_component(name, "Editor")


def version_folder_name(version: str | None) -> str:
    return safe_component(version or "Unknown", "Unknown")


def application_key(name: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
    return value or "editor"


def editors_root_default() -> Path:
    return (Path.home() / DEFAULT_COMPONENTS_FOLDER_NAME).resolve(strict=False)


def legacy_editors_root_default() -> Path:
    return (Path.home() / LEGACY_DEFAULT_EDITORS_FOLDER_NAME).resolve(strict=False)


def components_root_default() -> Path:
    return editors_root_default()


def editor_root(editors_root: Path, name: str) -> Path:
    return editors_root / application_folder_name(name)


def version_root(editors_root: Path, name: str, version: str | None) -> Path:
    return editor_root(editors_root, name) / version_folder_name(version)


def portable_root(editors_root: Path, name: str, version: str | None) -> Path:
    return version_root(editors_root, name, version) / PORTABLE_FOLDER_NAME


def appimage_root(editors_root: Path, name: str, version: str | None) -> Path:
    return version_root(editors_root, name, version) / APPIMAGE_FOLDER_NAME


def normalized_architecture(value: str | None = None) -> str:
    raw = (value or platform.machine() or "unknown").casefold().strip()
    return {
        "amd64": "x86_64",
        "x64": "x86_64",
        "x86-64": "x86_64",
        "arm64": "aarch64",
    }.get(raw, raw or "unknown")


def architecture_from_appimage(path: Path) -> str:
    stem = path.name[:-9] if path.name.casefold().endswith(".appimage") else path.stem
    match = re.search(r"(?:^|[-_.])(x86_64|amd64|aarch64|arm64)(?:$|[-_.])", stem, re.IGNORECASE)
    return normalized_architecture(match.group(1) if match else None)


def artifact_application_name(name: str) -> str:
    # Preserve the human-facing name while using hyphens in artifact filenames.
    value = re.sub(r"\s+", "-", safe_component(name, "Editor"))
    return value


def appimage_filename(name: str, version: str | None, architecture: str | None = None) -> str:
    return f"{artifact_application_name(name)}-{version_folder_name(version)}-{normalized_architecture(architecture)}.AppImage"


def icon_filename(name: str, suffix: str) -> str:
    ext = suffix if suffix.startswith(".") else f".{suffix}"
    return f"{application_key(name)}-icon{ext.casefold()}"


def is_within(path: Path, root: Path) -> bool:
    try:
        path.expanduser().resolve(strict=False).relative_to(root.expanduser().resolve(strict=False))
        return True
    except ValueError:
        return False


def iter_portable_roots(editors_root: Path):
    root = editors_root.expanduser().resolve(strict=False)
    if not root.is_dir():
        return
    try:
        applications = sorted((p for p in root.iterdir() if p.is_dir() and not p.is_symlink() and not p.name.startswith(".")), key=lambda p: p.name.casefold())
    except OSError:
        return
    for application in applications:
        try:
            versions = sorted((p for p in application.iterdir() if p.is_dir() and not p.is_symlink() and not p.name.startswith(".")), key=lambda p: p.name.casefold())
        except OSError:
            continue
        for version in versions:
            portable = version / PORTABLE_FOLDER_NAME
            if portable.is_dir() and not portable.is_symlink():
                yield portable


def prune_empty_parents(start: Path, editors_root: Path) -> None:
    """Best-effort removal of empty version/application containers."""
    root = editors_root.expanduser().resolve(strict=False)
    current = start.expanduser().resolve(strict=False)
    while current != root and is_within(current, root):
        try:
            if not current.is_dir() or any(current.iterdir()):
                break
            current.rmdir()
        except OSError:
            break
        current = current.parent

def prune_empty_version_tree(version_dir: Path, editors_root: Path) -> None:
    """Remove empty Portable/AppImage containers, then empty version/app folders."""
    root = editors_root.expanduser().resolve(strict=False)
    version = version_dir.expanduser().resolve(strict=False)
    if not is_within(version, root) or version == root:
        return
    for name in (PORTABLE_FOLDER_NAME, APPIMAGE_FOLDER_NAME):
        child = version / name
        try:
            if child.is_dir() and not child.is_symlink() and not any(child.iterdir()):
                child.rmdir()
        except OSError:
            pass
    prune_empty_parents(version, root)

