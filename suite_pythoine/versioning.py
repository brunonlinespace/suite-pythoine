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
_BASE_VERSION = re.compile(r"(?<![A-Za-z0-9.])(\d+(?:\.\d+)+)")
_RELEASE_MARKER = re.compile(
    r"(?:r|exp|rc|alpha|beta|pre|preview|dev)\d*(?:\.\d+)*$",
    re.IGNORECASE,
)
_PACKAGING_TOKENS = frozenset({
    "source", "tree", "code", "portable", "branded", "modular",
    "appimage", "release", "src",
})
_ARCH_TOKENS = frozenset({"x86_64", "aarch64", "arm64", "amd64"})


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


def version_from_artifact_name(path: Path | str) -> str | None:
    """Return the complete release token carried by an artifact/folder name.

    Suite-managed projects commonly distinguish debug/revision builds with
    suffixes such as ``-r6`` or ``-exp2-r1`` even when an older internal
    manifest still reports only the base release.  Preserve those suffixes.
    Packaging-only tails such as ``-source`` / ``-source-tree`` /
    ``-portable`` and AppImage architecture suffixes are not part of the
    application version.
    """
    name = Path(path).name
    lowered = name.casefold()
    for suffix in (".appimage", ".tar.gz", ".tar.xz", ".tar.bz2", ".zip"):
        if lowered.endswith(suffix):
            name = name[:-len(suffix)]
            break
    # Packaging descriptors are not release qualifiers.  In particular, names
    # such as ``LinSpectacles-0.0.4-Branded-Modular-Portable`` must remain
    # version 0.0.4 rather than being promoted to a fictitious
    # ``0.0.4-Modular`` release.  Artifact-name refinement is intentionally
    # conservative: recover only explicit project release markers (r/exp/rc
    # etc.), plus a single descriptive token immediately attached to such a
    # marker (for established forms such as ``retro-exp1`` / ``theme-exp4``).
    matches = list(_BASE_VERSION.finditer(name))
    if not matches:
        return None
    match = matches[-1]
    base = match.group(1)
    tail = name[match.end():].lstrip("-_.")
    if not tail:
        return base

    raw_tokens = [token for token in re.split(r"[-_]", tail) if token]
    tokens: list[str] = []
    for token in raw_tokens:
        lowered = token.casefold()
        if lowered in _ARCH_TOKENS or lowered in _PACKAGING_TOKENS:
            break
        tokens.append(token)

    release_tokens: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if _RELEASE_MARKER.fullmatch(token):
            release_tokens.append(token)
            index += 1
            continue
        # Allow one established descriptor only when it is immediately paired
        # with a real release marker; arbitrary words such as Modular/Branded
        # are never treated as version suffixes.
        if index + 1 < len(tokens) and _RELEASE_MARKER.fullmatch(tokens[index + 1]):
            release_tokens.extend((token, tokens[index + 1]))
            index += 2
            continue
        break

    return base + ("-" + "-".join(release_tokens) if release_tokens else "")


def refine_version(declared_version: str | None, artifact_version: str | None) -> str | None:
    """Prefer a compatible, more-specific release identity.

    A package named ``Foo-1.2.3-r6`` legitimately refines a manifest that says
    ``1.2.3``.  A conflicting package name (for example manifest ``1.2.3`` but
    filename ``1.2.4-r1``) must *not* silently override declared metadata.
    """
    declared = normalize_version(declared_version)
    artifact = normalize_version(artifact_version)
    if declared is None:
        return artifact
    if artifact is None or declared.casefold() == artifact.casefold():
        return declared
    declared_cf = declared.casefold()
    artifact_cf = artifact.casefold()
    if artifact_cf.startswith(declared_cf) and artifact_cf[len(declared_cf):len(declared_cf) + 1] in {"-", "_", "."}:
        return artifact
    if declared_cf.startswith(artifact_cf) and declared_cf[len(artifact_cf):len(artifact_cf) + 1] in {"-", "_", "."}:
        return declared
    return declared


def version_from_filename(path: Path) -> str | None:
    # Compatibility name retained for AppImage callers. The generalized parser
    # now also understands source ZIP/folder naming and packaging-only suffixes.
    return version_from_artifact_name(path)


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
    """Detect the application release without executing source.

    An explicit manifest version is authoritative and is returned verbatim after
    whitespace normalization.  Source-folder names, managed-version paths, build
    scripts and Python assignments are fallback evidence only for legacy sources
    that do not declare a version.
    """
    declared = normalize_version(manifest.get("version")) if isinstance(manifest, dict) else None
    if declared:
        return declared
    path_hint = None
    try:
        if root.name.casefold() == "portable":
            path_hint = version_from_artifact_name(root.parent.name)
        else:
            path_hint = version_from_artifact_name(root.name)
    except OSError:
        path_hint = None
    resolved = path_hint

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
            resolved = refine_version(resolved, value)
            break
    if resolved:
        return resolved
    for _score, path in sorted(python_candidates, key=lambda item: item[0], reverse=True):
        value = _version_from_file(path)
        if value:
            return refine_version(resolved, value)
    return resolved


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
