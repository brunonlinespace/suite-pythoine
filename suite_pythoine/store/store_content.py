from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath

from ..catalogue.component_catalog import COMPONENT_PROFILES, TRUSTED_PUBLISHER_ID

STORE_CONTENT_SCHEMAS = frozenset({1, 2, 3})
PUBLISHED_FILENAME = "store-content.json"
MAX_SCREENSHOTS = 8
MAX_MEDIA_BYTES = 20 * 1024 * 1024
MAX_PACKAGE_BYTES = 768 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class StoreScreenshot:
    relative_path: str
    sha256: str
    caption: str | None = None


@dataclass(frozen=True, slots=True)
class StoreContentEntry:
    component_id: str
    latest_version: str | None = None
    release_date: str | None = None
    release_notes: str | None = None
    extended_description: str | None = None
    highlights: tuple[str, ...] = ()
    screenshots: tuple[StoreScreenshot, ...] = ()
    download_url: str | None = None
    sha256: str | None = None
    package_size: int | None = None
    package_type: str | None = None
    icon_url: str | None = None
    release_url: str | None = None
    check_status: str | None = None
    check_error: str | None = None


def store_data_dir() -> Path:
    raw = os.environ.get("XDG_DATA_HOME", "").strip()
    base = Path(raw).expanduser() if raw else Path.home() / ".local" / "share"
    return base / "brunonlinespace" / "store-pythoine"


def published_manifest_path() -> Path:
    return store_data_dir() / PUBLISHED_FILENAME


def _optional_text(raw: object) -> str | None:
    value = str(raw or "").strip()
    return value or None


def _valid_sha256(value: str) -> bool:
    return len(value) == 64 and all(ch in "0123456789abcdef" for ch in value)


def _safe_media_relative(raw: object) -> str:
    text = str(raw or "").strip().replace("\\", "/")
    rel = PurePosixPath(text)
    if (not text or rel.is_absolute() or any(part in {"", ".", ".."} for part in rel.parts)
            or not rel.parts or rel.parts[0] != "media"):
        raise ValueError("Store screenshot path must be a safe relative media/ path.")
    if rel.suffix.casefold() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ValueError("Store screenshots must be PNG, JPEG or WebP files.")
    return rel.as_posix()


def _string_list(raw: object, *, limit: int) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list) or len(raw) > limit:
        raise ValueError("Store rich-text list is malformed or exceeds its safety limit.")
    result: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if not text or len(text) > 500:
            raise ValueError("Store rich-text list entries must be non-empty and bounded.")
        result.append(text)
    return tuple(result)


def _parse_screenshots(raw: object) -> tuple[StoreScreenshot, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list) or len(raw) > MAX_SCREENSHOTS:
        raise ValueError("Store screenshot list is malformed or exceeds its safety limit.")
    result: list[StoreScreenshot] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("Invalid Store screenshot entry.")
        relative = _safe_media_relative(item.get("path"))
        if relative in seen:
            raise ValueError("Store screenshot paths must be unique within an application.")
        seen.add(relative)
        digest = str(item.get("sha256") or "").strip().casefold()
        if not _valid_sha256(digest):
            raise ValueError("Store screenshot SHA-256 is invalid.")
        caption = _optional_text(item.get("caption"))
        if caption is not None and len(caption) > 500:
            raise ValueError("Store screenshot caption exceeds its safety limit.")
        result.append(StoreScreenshot(relative, digest, caption))
    return tuple(result)


def _parse(payload: object) -> dict[str, StoreContentEntry]:
    if not isinstance(payload, dict) or payload.get("schema") not in STORE_CONTENT_SCHEMAS:
        raise ValueError("Unsupported Store Pythoine content schema.")
    if payload.get("publisher_id") != TRUSTED_PUBLISHER_ID:
        raise ValueError("Store Pythoine content publisher is not trusted.")
    revision = payload.get("store_revision", 0)
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise ValueError("Store content revision must be a non-negative integer.")
    rows = payload.get("components", [])
    if not isinstance(rows, list):
        raise ValueError("Store content components must be a list.")

    result: dict[str, StoreContentEntry] = {}
    for raw in rows:
        if not isinstance(raw, dict):
            raise ValueError("Invalid Store content entry.")
        component_id = str(raw.get("id") or "").strip().casefold()
        if not component_id or component_id in result:
            raise ValueError("Store content entries require unique component IDs.")
        # Store may enrich only identities already trusted by the active Suite
        # catalogue. Unknown IDs never create new application identity here.
        if component_id not in COMPONENT_PROFILES:
            continue
        download_url = _optional_text(raw.get("download_url"))
        icon_url = _optional_text(raw.get("icon_url"))
        release_url = _optional_text(raw.get("release_url"))
        for label, url in (("download", download_url), ("icon", icon_url), ("release", release_url)):
            if url is not None and not url.startswith("https://"):
                raise ValueError(f"Store {label} URL must use HTTPS: {component_id}")
        sha256 = _optional_text(raw.get("sha256"))
        if sha256 is not None:
            sha256 = sha256.casefold()
            if not _valid_sha256(sha256):
                raise ValueError(f"Store SHA-256 is invalid: {component_id}")
        package_size = raw.get("package_size")
        if package_size is not None:
            if isinstance(package_size, bool) or not isinstance(package_size, int) or package_size <= 0 or package_size > MAX_PACKAGE_BYTES:
                raise ValueError(f"Store package size is invalid: {component_id}")
        package_type = _optional_text(raw.get("package_type"))
        if package_type is not None:
            package_type = package_type.casefold()
            if package_type not in {"source-zip", "appimage"}:
                raise ValueError(f"Store package type is invalid: {component_id}")
        check_status = _optional_text(raw.get("check_status"))
        if check_status is not None and check_status not in {"ok", "error", "unavailable", "unchecked"}:
            raise ValueError(f"Store repository check status is invalid: {component_id}")
        check_error = _optional_text(raw.get("check_error"))
        if check_error is not None and len(check_error) > 500:
            raise ValueError(f"Store repository check error is too long: {component_id}")
        result[component_id] = StoreContentEntry(
            component_id=component_id,
            latest_version=_optional_text(raw.get("latest_version")),
            release_date=_optional_text(raw.get("release_date")),
            release_notes=_optional_text(raw.get("release_notes")),
            extended_description=_optional_text(raw.get("extended_description")),
            highlights=_string_list(raw.get("highlights"), limit=12),
            screenshots=_parse_screenshots(raw.get("screenshots")),
            download_url=download_url,
            sha256=sha256,
            package_size=package_size,
            package_type=package_type,
            icon_url=icon_url,
            release_url=release_url,
            check_status=check_status,
            check_error=check_error,
        )
    return result


def load_store_content(path: Path | None = None) -> dict[str, StoreContentEntry]:
    source = (path or published_manifest_path()).expanduser()
    if not source.is_file() or source.is_symlink():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise ValueError(f"Store content could not be read: {exc}") from exc
    return _parse(payload)


def trusted_repository_snapshot_path() -> Path:
    return store_data_dir() / "suite-trusted-components.json"


def publish_trusted_repository_snapshot(*, suite_version: str) -> Path:
    """Publish Suite's trusted identity/repository projection for Store refresh.

    This local bridge is generated by Suite and is never a second identity
    authority. Store may query only repositories present in this snapshot.
    """
    rows = []
    for profile in sorted(COMPONENT_PROFILES.values(), key=lambda item: item.component_id):
        rows.append({
            "id": profile.component_id,
            "name": profile.name,
            "publisher_id": profile.publisher_id,
            "repository": profile.repository,
            "lifecycle": profile.lifecycle,
        })
    payload = {
        "schema": 1,
        "publisher_id": TRUSTED_PUBLISHER_ID,
        "suite_version": suite_version,
        "components": rows,
    }
    target = trusted_repository_snapshot_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(target)
    return target


def resolve_store_screenshot(screenshot: StoreScreenshot) -> Path | None:
    """Return one verified local screenshot path, never an arbitrary manifest path."""
    base = store_data_dir().resolve(strict=False)
    candidate = (base / screenshot.relative_path).resolve(strict=False)
    try:
        candidate.relative_to(base)
    except ValueError:
        return None
    if not candidate.is_file() or candidate.is_symlink():
        return None
    try:
        if candidate.stat().st_size > MAX_MEDIA_BYTES:
            return None
        digest = hashlib.sha256()
        with candidate.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    if digest.hexdigest().casefold() != screenshot.sha256.casefold():
        return None
    return candidate
