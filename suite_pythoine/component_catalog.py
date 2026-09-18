from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterable

CATALOG_SCHEMA = 1
ALLOWED_KINDS = frozenset({"hub", "editor", "reader", "extension"})
TRUSTED_PUBLISHER_ID = "brunonlinespace"
BUNDLED_CATALOG_PATH = Path(__file__).resolve().with_name("components.json")
USER_CATALOG_FILENAME = "components.json"

_CAPABILITY_DEFAULTS = {
    "hub": (),
    "editor": ("routing", "open", "create"),
    "reader": ("routing", "open"),
    "extension": (),
}
_CAPABILITY_KEYS = frozenset({"routing", "open", "create"})


@dataclass(frozen=True, slots=True)
class ComponentProfile:
    component_id: str
    name: str
    kind: str
    publisher_id: str
    description: str
    extensions: tuple[str, ...]
    mime_types: tuple[str, ...]
    identity_hints: tuple[str, ...]
    appimage_prefixes: tuple[str, ...]
    repository: str | None = None
    capabilities: tuple[str, ...] = ()
    config_subdir: str | None = None
    url_schemes: tuple[str, ...] = ()
    url_hosts: tuple[str, ...] = ()
    url_fallback: bool = False

    @property
    def is_editor(self) -> bool:
        return self.kind == "editor"

    @property
    def is_reader(self) -> bool:
        return self.kind == "reader"

    @property
    def is_routable(self) -> bool:
        return "routing" in self.capabilities and "open" in self.capabilities

    @property
    def can_create(self) -> bool:
        return "create" in self.capabilities


def default_user_catalog_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return (base / "brunonlinespace" / "suite-pythoine" / USER_CATALOG_FILENAME).resolve(strict=False)
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return (base / "brunonlinespace" / "suite-pythoine" / USER_CATALOG_FILENAME).resolve(strict=False)


def _normalize_extension(value: object) -> str:
    text = str(value or "").strip().casefold()
    if not text:
        return ""
    return text if text.startswith(".") else f".{text}"


def _normalize_mime(value: object) -> str:
    text = str(value or "").strip().casefold()
    if not text or "/" not in text or ";" in text or any(ch.isspace() for ch in text):
        return ""
    return text


def _load_payload(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") != CATALOG_SCHEMA:
        raise ValueError("Unsupported Suite Pythoine component catalogue schema.")
    if data.get("publisher_id") != TRUSTED_PUBLISHER_ID:
        raise ValueError("Component catalogue publisher is not trusted.")
    revision = data.get("catalog_revision", 0)
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise ValueError("Component catalogue revision must be a non-negative integer.")
    return data


def catalog_revision(path: Path) -> int:
    """Return the monotonic revision of a trusted catalogue payload.

    Schema-1 catalogues released before 0.3.1 did not carry a revision and are
    treated as revision 0. A newer bundled catalogue therefore supersedes an
    older cached user catalogue, while future independently published revisions
    can still supersede the bundled copy without a Hub release.
    """
    return int(_load_payload(path).get("catalog_revision", 0))


def load_catalog(path: Path | None = None) -> dict[str, ComponentProfile]:
    payload = _load_payload(path or BUNDLED_CATALOG_PATH)
    raw_components = payload.get("components")
    if not isinstance(raw_components, list):
        raise ValueError("Component catalogue does not contain a components list.")
    result: dict[str, ComponentProfile] = {}
    for raw in raw_components:
        if not isinstance(raw, dict):
            raise ValueError("Invalid component entry in catalogue.")
        component_id = str(raw.get("id") or "").strip().casefold()
        name = str(raw.get("name") or "").strip()
        kind = str(raw.get("kind") or "").strip().casefold()
        publisher_id = str(raw.get("publisher_id") or "").strip()
        if not component_id or not name or kind not in ALLOWED_KINDS or publisher_id != TRUSTED_PUBLISHER_ID:
            raise ValueError(f"Invalid or untrusted component profile: {component_id or name or '<unknown>'}")
        if component_id in result:
            raise ValueError(f"Duplicate component ID in catalogue: {component_id}")
        extensions = tuple(dict.fromkeys(filter(None, (_normalize_extension(value) for value in raw.get("extensions", [])))))
        mime_types = tuple(dict.fromkeys(filter(None, (_normalize_mime(value) for value in raw.get("mime_types", [])))))
        identity_hints = tuple(str(value).strip() for value in raw.get("identity_hints", []) if str(value).strip())
        appimage_prefixes = tuple(str(value).strip() for value in raw.get("appimage_prefixes", []) if str(value).strip())
        repository = str(raw.get("repository") or "").strip() or None
        config_subdir = str(raw.get("config_subdir") or "").strip() or None
        url_capabilities = raw.get("url_capabilities", {})
        if url_capabilities is None:
            url_capabilities = {}
        if not isinstance(url_capabilities, dict):
            raise ValueError(f"Invalid URL capabilities for component profile: {component_id}")
        url_schemes = tuple(dict.fromkeys(str(value).strip().casefold() for value in url_capabilities.get("schemes", []) if str(value).strip()))
        url_hosts = tuple(dict.fromkeys(str(value).strip().casefold() for value in url_capabilities.get("hosts", []) if str(value).strip()))
        url_fallback = bool(url_capabilities.get("fallback", False))
        raw_capabilities = raw.get("capabilities")
        if raw_capabilities is None:
            capabilities = _CAPABILITY_DEFAULTS[kind]
        else:
            if not isinstance(raw_capabilities, dict) or any(key not in _CAPABILITY_KEYS for key in raw_capabilities):
                raise ValueError(f"Invalid capabilities for component profile: {component_id}")
            if any(not isinstance(value, bool) for value in raw_capabilities.values()):
                raise ValueError(f"Component capabilities must be boolean: {component_id}")
            capabilities = tuple(key for key in ("routing", "open", "create") if raw_capabilities.get(key, False))
        result[component_id] = ComponentProfile(
            component_id=component_id,
            name=name,
            kind=kind,
            publisher_id=publisher_id,
            description=str(raw.get("description") or "").strip(),
            extensions=extensions,
            mime_types=mime_types,
            identity_hints=identity_hints,
            appimage_prefixes=appimage_prefixes,
            repository=repository,
            capabilities=tuple(capabilities),
            config_subdir=config_subdir,
            url_schemes=url_schemes,
            url_hosts=url_hosts,
            url_fallback=url_fallback,
        )
    if "suite-pythoine" not in result or result["suite-pythoine"].kind != "hub":
        raise ValueError("Component catalogue must define Suite Pythoine as the hub.")
    return result


def _initial_catalog() -> dict[str, ComponentProfile]:
    bundled_revision = catalog_revision(BUNDLED_CATALOG_PATH)
    user_path = default_user_catalog_path()
    if user_path.is_file():
        try:
            user_revision = catalog_revision(user_path)
            if user_revision >= bundled_revision:
                return load_catalog(user_path)
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    return load_catalog(BUNDLED_CATALOG_PATH)


# Kept as one mutable mapping so modules that imported COMPONENT_PROFILES keep
# seeing independently refreshed catalogue data in the same process.
COMPONENT_PROFILES: dict[str, ComponentProfile] = _initial_catalog()


def reload_catalog(path: Path | None = None) -> dict[str, ComponentProfile]:
    profiles = load_catalog(path or default_user_catalog_path())
    COMPONENT_PROFILES.clear()
    COMPONENT_PROFILES.update(profiles)
    return COMPONENT_PROFILES


def install_verified_catalog(source: Path, destination: Path | None = None) -> Path:
    """Validate a pre-verified catalogue payload and atomically install it.

    Network provenance/digest verification belongs to the external Store Pythoine discovery/download layer. This
    function enforces the trusted publisher/schema/content boundary before the
    user catalogue replaces the previous cached catalogue.
    """
    source = source.expanduser().resolve(strict=True)
    load_catalog(source)
    source_revision = catalog_revision(source)
    target = (destination or default_user_catalog_path()).expanduser().resolve(strict=False)

    reference_path = BUNDLED_CATALOG_PATH
    reference_revision = catalog_revision(reference_path)
    if target.is_file():
        try:
            target_revision = catalog_revision(target)
            if target_revision > reference_revision:
                reference_revision = target_revision
                reference_path = target
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    if source_revision < reference_revision:
        raise ValueError("Component catalogue update is older than the active trusted catalogue.")
    if source_revision == reference_revision and source.read_bytes() != reference_path.read_bytes():
        raise ValueError("Component catalogue content changed without increasing catalog_revision.")

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile("wb", dir=target.parent, prefix=f".{target.name}.", suffix=".tmp", delete=False) as handle:
            handle.write(source.read_bytes())
            temporary = Path(handle.name)
        load_catalog(temporary)
        temporary.replace(target)
        reload_catalog(target)
        return target
    finally:
        if temporary is not None and temporary.exists():
            try:
                temporary.unlink()
            except OSError:
                pass


def profile_for_id(component_id: str) -> ComponentProfile | None:
    return COMPONENT_PROFILES.get(str(component_id).strip().casefold())


def profiles_of_kind(kind: str) -> tuple[ComponentProfile, ...]:
    target = str(kind).strip().casefold()
    return tuple(profile for profile in COMPONENT_PROFILES.values() if profile.kind == target)


def editor_profiles() -> tuple[ComponentProfile, ...]:
    return profiles_of_kind("editor")


def reader_profiles() -> tuple[ComponentProfile, ...]:
    return profiles_of_kind("reader")


def routable_profiles() -> tuple[ComponentProfile, ...]:
    return tuple(profile for profile in COMPONENT_PROFILES.values() if profile.is_routable)


def catalog_fingerprint(profiles: dict[str, ComponentProfile] | None = None) -> str:
    """Return a stable digest for the active trusted component catalogue.

    The fast routing cache includes this digest so a verified catalogue-only
    update can change component kinds/formats without waiting for a filesystem
    inventory change or a full Hub launch.
    """
    source = profiles if profiles is not None else COMPONENT_PROFILES
    payload = [
        {
            "id": profile.component_id,
            "name": profile.name,
            "kind": profile.kind,
            "publisher_id": profile.publisher_id,
            "description": profile.description,
            "extensions": list(profile.extensions),
            "mime_types": list(profile.mime_types),
            "identity_hints": list(profile.identity_hints),
            "appimage_prefixes": list(profile.appimage_prefixes),
            "repository": profile.repository,
            "capabilities": list(profile.capabilities),
            "config_subdir": profile.config_subdir,
            "url_schemes": list(profile.url_schemes),
            "url_hosts": list(profile.url_hosts),
            "url_fallback": profile.url_fallback,
        }
        for _component_id, profile in sorted(source.items())
    ]
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def extension_union(profiles: Iterable[ComponentProfile] | None = None) -> tuple[str, ...]:
    source = profiles if profiles is not None else routable_profiles()
    return tuple(dict.fromkeys(ext for profile in source for ext in profile.extensions))


def mime_type_union(profiles: Iterable[ComponentProfile] | None = None) -> tuple[str, ...]:
    source = profiles if profiles is not None else routable_profiles()
    return tuple(dict.fromkeys(mime for profile in source for mime in profile.mime_types))
