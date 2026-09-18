from __future__ import annotations

from pathlib import Path
import re
from typing import Any, MutableMapping

REGISTRY_KEY = "managed_installations"
REGISTRY_SCHEMA = 2


def _safe_id(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value)).strip("-._")
    return text or "editor"


def desktop_id_for(editor_id: str) -> str:
    return f"io.github.brunonlinespace.{_safe_id(editor_id)}"


def _path_text(value: object) -> str | None:
    if not isinstance(value, (str, Path)):
        return None
    text = str(value).strip()
    if not text:
        return None
    return str(Path(text).expanduser().resolve(strict=False))


def _normalize_version_record(record: object, *, editor_id: str, version_hint: str | None = None) -> dict[str, Any]:
    if not isinstance(record, dict):
        return {}
    version_value = record.get("version") or version_hint
    version = str(version_value).strip() if isinstance(version_value, str) and version_value.strip() else None
    if not version:
        return {}
    result: dict[str, Any] = {
        "schema": REGISTRY_SCHEMA,
        "editor_id": editor_id,
        "application_id": str(record.get("application_id") or editor_id).strip() or editor_id,
        "name": str(record.get("name") or editor_id).strip() or editor_id,
        "version": version,
    }
    sha256 = record.get("appimage_sha256") or record.get("sha256")
    result["appimage_sha256"] = str(sha256).strip().lower() if isinstance(sha256, str) and sha256.strip() else None
    appimage = record.get("appimage_path") or record.get("appimage")
    result["appimage_path"] = _path_text(appimage)
    result["icon_path"] = _path_text(record.get("icon_path"))
    result["desktop_file_path"] = _path_text(record.get("desktop_file_path"))
    result["desktop_id"] = str(record.get("desktop_id") or desktop_id_for(editor_id)).strip()
    result["desktop_integrated"] = bool(record.get("desktop_integrated", bool(result["desktop_file_path"])))
    for key in ("source_artifact", "build_script", "source_version", "description", "publisher_id"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            result[key] = value.strip()
    extensions = record.get("extensions")
    if isinstance(extensions, (list, tuple)):
        cleaned = [str(value).strip() for value in extensions if str(value).strip()]
        if cleaned:
            result["extensions"] = cleaned
    return result


def _legacy_to_group(record: dict[str, Any], *, editor_id: str) -> dict[str, Any]:
    version_record = _normalize_version_record(record, editor_id=editor_id)
    if not version_record:
        return {}
    version = version_record["version"]
    integrated = bool(version_record.get("desktop_file_path"))
    version_record["desktop_integrated"] = integrated
    return {
        "schema": REGISTRY_SCHEMA,
        "editor_id": editor_id,
        "application_id": version_record.get("application_id") or editor_id,
        "name": version_record.get("name") or editor_id,
        "publisher_id": version_record.get("publisher_id") or "",
        "active_version": version,
        "desktop_version": version if integrated else None,
        "versions": {version: version_record},
    }


def normalize_group(record: object, *, editor_id: str | None = None) -> dict[str, Any]:
    if not isinstance(record, dict):
        return {}
    resolved_editor_id = str(record.get("editor_id") or editor_id or "").strip()
    if not resolved_editor_id:
        return {}
    # 0.1.x stored one flattened record per application. Promote it lazily.
    if not isinstance(record.get("versions"), dict):
        return _legacy_to_group(record, editor_id=resolved_editor_id)

    versions: dict[str, dict[str, Any]] = {}
    for key, value in record.get("versions", {}).items():
        version_key = str(key).strip()
        normalized = _normalize_version_record(value, editor_id=resolved_editor_id, version_hint=version_key)
        if normalized:
            versions[normalized["version"]] = normalized
    if not versions:
        return {}
    active_raw = record.get("active_version")
    active_version = str(active_raw).strip() if isinstance(active_raw, str) and str(active_raw).strip() in versions else None
    if active_version is None:
        active_version = next(iter(versions))
    desktop_raw = record.get("desktop_version")
    desktop_version = str(desktop_raw).strip() if isinstance(desktop_raw, str) and str(desktop_raw).strip() in versions else None
    if desktop_version is None:
        desktop_version = next((version for version, item in versions.items() if item.get("desktop_integrated")), None)
    for version, item in versions.items():
        item["desktop_integrated"] = bool(desktop_version and version == desktop_version)
        if not item["desktop_integrated"]:
            # The per-user .desktop belongs to one version only. Retain the
            # canonical desktop ID, but do not pretend this version owns the file.
            item["desktop_file_path"] = None

    result: dict[str, Any] = {
        "schema": REGISTRY_SCHEMA,
        "editor_id": resolved_editor_id,
        "application_id": str(record.get("application_id") or resolved_editor_id).strip() or resolved_editor_id,
        "name": str(record.get("name") or resolved_editor_id).strip() or resolved_editor_id,
        "active_version": active_version,
        "desktop_version": desktop_version,
        "versions": versions,
    }
    publisher = record.get("publisher_id")
    if isinstance(publisher, str) and publisher.strip():
        result["publisher_id"] = publisher.strip()
    return result


def normalize_record(record: object, *, editor_id: str | None = None, version: str | None = None) -> dict[str, Any]:
    """Compatibility view returning one version record.

    Existing callers that historically expected a flattened registry record see
    the requested version or the active version. New 0.2 code should use
    ``get_managed_group`` / ``get_managed_versions`` when it needs the complete
    inventory.
    """
    group = normalize_group(record, editor_id=editor_id)
    if not group:
        return {}
    requested = version or group.get("active_version")
    versions = group.get("versions", {})
    if requested in versions:
        return dict(versions[requested])
    return {}


def ensure_registry(config_data: MutableMapping[str, Any]) -> dict[str, dict[str, Any]]:
    raw = config_data.get(REGISTRY_KEY)
    if not isinstance(raw, dict):
        raw = {}
        config_data[REGISTRY_KEY] = raw
    for key in list(raw):
        normalized = normalize_group(raw.get(key), editor_id=str(key))
        if normalized:
            raw[str(key)] = normalized
        else:
            raw.pop(key, None)
    return raw  # type: ignore[return-value]


def get_managed_group(config_data: MutableMapping[str, Any] | dict[str, Any], editor_id: str) -> dict[str, Any]:
    raw = config_data.get(REGISTRY_KEY, {}) if isinstance(config_data, dict) else {}
    if not isinstance(raw, dict):
        return {}
    return normalize_group(raw.get(editor_id), editor_id=editor_id)


def get_managed_versions(config_data: MutableMapping[str, Any] | dict[str, Any], editor_id: str) -> dict[str, dict[str, Any]]:
    group = get_managed_group(config_data, editor_id)
    versions = group.get("versions", {}) if group else {}
    return {str(key): dict(value) for key, value in versions.items()} if isinstance(versions, dict) else {}


def get_managed_installation(
    config_data: MutableMapping[str, Any] | dict[str, Any], editor_id: str, version: str | None = None
) -> dict[str, Any]:
    group = get_managed_group(config_data, editor_id)
    if not group:
        return {}
    requested = version or group.get("active_version")
    versions = group.get("versions", {})
    if isinstance(requested, str) and isinstance(versions, dict) and requested in versions:
        return dict(versions[requested])
    return {}


def set_managed_installation(
    config_data: MutableMapping[str, Any], record: dict[str, Any], *, set_active: bool = True, desktop_integrated: bool | None = None
) -> dict[str, Any]:
    editor_id = str(record.get("editor_id") or "").strip()
    if not editor_id:
        raise ValueError("Managed installation record is missing editor_id")
    normalized = _normalize_version_record(record, editor_id=editor_id)
    if not normalized:
        raise ValueError("Managed installation record is missing version")
    registry = ensure_registry(config_data)
    group = normalize_group(registry.get(editor_id), editor_id=editor_id)
    if not group:
        group = {
            "schema": REGISTRY_SCHEMA,
            "editor_id": editor_id,
            "application_id": normalized.get("application_id") or editor_id,
            "name": normalized.get("name") or editor_id,
            "publisher_id": normalized.get("publisher_id") or "",
            "active_version": normalized["version"],
            "desktop_version": None,
            "versions": {},
        }
    group["application_id"] = normalized.get("application_id") or group.get("application_id") or editor_id
    group["name"] = normalized.get("name") or group.get("name") or editor_id
    if normalized.get("publisher_id"):
        group["publisher_id"] = normalized["publisher_id"]
    versions = dict(group.get("versions", {}))
    version = normalized["version"]
    if desktop_integrated is None:
        desktop_integrated = bool(normalized.get("desktop_file_path"))
    normalized["desktop_integrated"] = bool(desktop_integrated)
    versions[version] = normalized
    group["versions"] = versions
    if set_active or not group.get("active_version"):
        group["active_version"] = version
    if desktop_integrated:
        group["desktop_version"] = version
        for other_version, other in versions.items():
            other["desktop_integrated"] = other_version == version
            if other_version != version:
                other["desktop_file_path"] = None
    registry[editor_id] = normalize_group(group, editor_id=editor_id)
    return get_managed_installation(config_data, editor_id, version)


def set_active_version(config_data: MutableMapping[str, Any], editor_id: str, version: str) -> bool:
    registry = ensure_registry(config_data)
    group = normalize_group(registry.get(editor_id), editor_id=editor_id)
    versions = group.get("versions", {}) if group else {}
    if version not in versions:
        return False
    group["active_version"] = version
    registry[editor_id] = normalize_group(group, editor_id=editor_id)
    return True


def set_desktop_version(config_data: MutableMapping[str, Any], editor_id: str, version: str | None, desktop_path: Path | str | None = None) -> bool:
    registry = ensure_registry(config_data)
    group = normalize_group(registry.get(editor_id), editor_id=editor_id)
    if not group:
        return False
    versions = group.get("versions", {})
    if version is not None and version not in versions:
        return False
    group["desktop_version"] = version
    for ver, item in versions.items():
        item["desktop_integrated"] = bool(version and ver == version)
        if version and ver == version:
            if desktop_path is not None:
                item["desktop_file_path"] = _path_text(desktop_path)
        else:
            item["desktop_file_path"] = None
    registry[editor_id] = normalize_group(group, editor_id=editor_id)
    return True


def remove_managed_version(config_data: MutableMapping[str, Any], editor_id: str, version: str) -> dict[str, Any]:
    registry = ensure_registry(config_data)
    group = normalize_group(registry.get(editor_id), editor_id=editor_id)
    if not group:
        return {}
    versions = dict(group.get("versions", {}))
    removed = versions.pop(version, {})
    if not removed:
        return {}
    if not versions:
        registry.pop(editor_id, None)
        return dict(removed)
    group["versions"] = versions
    if group.get("active_version") == version:
        group["active_version"] = next(iter(versions))
    if group.get("desktop_version") == version:
        group["desktop_version"] = None
    registry[editor_id] = normalize_group(group, editor_id=editor_id)
    return dict(removed)


def remove_managed_installation(config_data: MutableMapping[str, Any], editor_id: str) -> dict[str, Any]:
    registry = ensure_registry(config_data)
    value = registry.pop(editor_id, {})
    group = normalize_group(value, editor_id=editor_id) if value else {}
    return normalize_record(group, editor_id=editor_id) if group else {}


def record_paths(record: dict[str, Any]) -> dict[str, Path | None]:
    if not isinstance(record, dict):
        return {"appimage": None, "desktop": None, "icon": None}
    editor_id = str(record.get("editor_id") or "").strip()
    normalized = _normalize_version_record(record, editor_id=editor_id) if editor_id else {}
    if not normalized:
        return {"appimage": None, "desktop": None, "icon": None}
    return {
        "appimage": Path(normalized["appimage_path"]) if normalized.get("appimage_path") else None,
        "desktop": Path(normalized["desktop_file_path"]) if normalized.get("desktop_file_path") else None,
        "icon": Path(normalized["icon_path"]) if normalized.get("icon_path") else None,
    }


def record_is_complete(record: dict[str, Any]) -> bool:
    if not isinstance(record, dict):
        return False
    editor_id = str(record.get("editor_id") or "").strip()
    normalized = _normalize_version_record(record, editor_id=editor_id) if editor_id else {}
    return bool(
        normalized
        and normalized.get("application_id")
        and normalized.get("version")
        and normalized.get("appimage_path")
        and normalized.get("appimage_sha256")
        and normalized.get("desktop_id")
        and "icon_path" in normalized
    )
