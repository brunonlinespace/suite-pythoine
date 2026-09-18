from __future__ import annotations

import json
import os
from pathlib import Path
import re
from typing import Iterable

IGNORED_DIRS = frozenset({".git", ".hg", ".svn", "__pycache__", ".venv", "venv", "node_modules", "build", "dist"})

_VERSION_ASSIGNMENTS = (
    re.compile(r"(?m)^\s*APP_VERSION\s*=\s*['\"]([^'\"]+)['\"]"),
    re.compile(r"(?m)^\s*__version__\s*=\s*['\"]([^'\"]+)['\"]"),
    re.compile(r"(?m)^\s*VERSION\s*=\s*['\"]([^'\"]+)['\"]"),
)
_APPIMAGE_ARCH_SUFFIX = re.compile(r"-(?:x86_64|aarch64|arm64|amd64)$", re.IGNORECASE)
_FILENAME_VERSION = re.compile(
    r"(?<!\d)(\d+(?:\.\d+)+(?:[-_.][A-Za-z0-9]+)*)$",
    re.IGNORECASE,
)


def normalize_version(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def parse_version_text(text: str) -> str | None:
    for pattern in _VERSION_ASSIGNMENTS:
        match = pattern.search(text)
        if match:
            return normalize_version(match.group(1))
    return None


def version_from_filename(path: Path) -> str | None:
    # Pad-family artifacts use names such as:
    #   Kapitulindo-0.0.1-exp3.2.1-x86_64.AppImage
    #   Ricopad-0.3.3-retro-exp1-x86_64.AppImage
    # Preserve the complete release suffix instead of truncating at the base
    # numeric version. Strip only the AppImage extension and known architecture
    # suffix, then take the trailing version token.
    name = path.name
    if name.casefold().endswith(".appimage"):
        name = name[:-len(".AppImage")]
    name = _APPIMAGE_ARCH_SUFFIX.sub("", name)
    match = _FILENAME_VERSION.search(name)
    return normalize_version(match.group(1)) if match else None


def _bounded_files(root: Path, *, max_depth: int = 5) -> Iterable[Path]:
    base_depth = len(root.parts)
    for current, dirs, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        depth = len(current_path.parts) - base_depth
        dirs[:] = [
            name
            for name in dirs
            if depth < max_depth
            and name.casefold() not in IGNORED_DIRS
            and not (current_path / name).is_symlink()
        ]
        for name in files:
            path = current_path / name
            if not path.is_symlink():
                yield path


def _version_from_file(path: Path) -> str | None:
    try:
        if path.stat().st_size > 2 * 1024 * 1024:
            return None
        return parse_version_text(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None


def detect_source_version(root: Path, manifest: dict | None = None) -> str | None:
    """Detect the application version without executing editor source.

    Packaging metadata is preferred because it defines the artifact being built.
    Manifests and canonical Python version assignments are fallback sources.
    """
    if isinstance(manifest, dict):
        value = normalize_version(manifest.get("version"))
        if value:
            return value

    build_candidates: list[tuple[int, Path]] = []
    python_candidates: list[tuple[int, Path]] = []
    for path in _bounded_files(root, max_depth=5):
        relative = path.relative_to(root)
        lower_name = path.name.casefold()
        parts = {part.casefold() for part in relative.parts}
        if path.suffix.casefold() == ".sh" and "appimage" in lower_name and lower_name.startswith("build"):
            score = 0
            if lower_name == "build-fedora-appimage.sh":
                score += 40
            elif lower_name == "build-appimage.sh":
                score += 35
            if "appimage" in parts:
                score += 20
            if "packaging" in parts:
                score += 20
            build_candidates.append((score - len(relative.parts), path))
        elif path.suffix.casefold() == ".py":
            score = 0
            if path.name == "__init__.py":
                score += 30
            if path.name == "main.py":
                score += 25
            if path.parent.name.casefold() == "source":
                score += 20
            python_candidates.append((score - len(relative.parts), path))

    for _score, path in sorted(build_candidates, key=lambda item: item[0], reverse=True):
        value = _version_from_file(path)
        if value:
            return value
    for _score, path in sorted(python_candidates, key=lambda item: item[0], reverse=True):
        value = _version_from_file(path)
        if value:
            return value
    return None


def appimage_metadata_path(appimage: Path) -> Path:
    return appimage.with_name(appimage.name + ".suite-pythoine.json")


def read_appimage_metadata(appimage: Path) -> dict:
    path = appimage_metadata_path(appimage)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def installed_version_for_appimage(appimage: Path | None, override: dict | None = None) -> str | None:
    if appimage is None:
        return None
    if isinstance(override, dict):
        configured_path = override.get("installed_path")
        configured_version = normalize_version(override.get("installed_version"))
        if configured_version and isinstance(configured_path, str):
            try:
                if Path(configured_path).expanduser().resolve(strict=False) == appimage.expanduser().resolve(strict=False):
                    return configured_version
            except OSError:
                pass
    metadata = read_appimage_metadata(appimage)
    value = normalize_version(metadata.get("version"))
    if value:
        return value
    return version_from_filename(appimage)


def versions_match(source_version: str | None, installed_version: str | None) -> bool | None:
    if source_version is None or installed_version is None:
        return None
    return source_version.casefold() == installed_version.casefold()


def version_sort_key(value: str | None) -> tuple:
    """Natural-ish ordering for pad-family release strings.

    This deliberately stays dependency-free. Numeric components sort numerically
    while rc/r/alpha/beta text remains stable enough for the project's version
    conventions (for example 0.3.3-rc4.2 > 0.3.3-rc4.1).
    """
    text = (value or "").casefold().strip()
    parts = re.split(r"(\d+)", text)
    return tuple((1, int(part)) if part.isdigit() else (0, part) for part in parts)


def compare_versions(left: str | None, right: str | None) -> int | None:
    """Return -1/0/1 when both versions are known, otherwise ``None``."""
    left_n = normalize_version(left)
    right_n = normalize_version(right)
    if left_n is None or right_n is None:
        return None
    lk = version_sort_key(left_n)
    rk = version_sort_key(right_n)
    return (lk > rk) - (lk < rk)
