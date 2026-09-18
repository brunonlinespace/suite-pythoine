from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Iterable

from .component_catalog import catalog_fingerprint
from .component_policy import component_capabilities

ROUTING_INDEX_SCHEMA = 4


@dataclass(frozen=True, slots=True)
class RoutingTarget:
    component_id: str
    name: str
    kind: str
    extensions: tuple[str, ...]
    launch_mode: str
    portable_command: tuple[str, ...] | None
    installed_command: tuple[str, ...] | None
    portable_root: Path | None
    active_version: str | None
    capabilities: tuple[str, ...] = ()

    @property
    def available(self) -> bool:
        # Availability follows the selected runtime. An explicit Portable or
        # AppImage preference is strict; only Automatic may fall back.
        return self.command() is not None

    def command(self) -> tuple[str, ...] | None:
        if self.launch_mode == "portable":
            return self.portable_command
        if self.launch_mode == "installed":
            return self.installed_command
        return self.installed_command or self.portable_command


def _command_valid(command: tuple[str, ...] | None) -> bool:
    if not command:
        return False
    executable = Path(command[0]).expanduser()
    if executable.is_absolute():
        return executable.exists()
    return True


def target_from_component(component: object) -> RoutingTarget:
    portable_root = getattr(component, "root", None) if getattr(component, "portable_command", None) else None
    return RoutingTarget(
        component_id=str(getattr(component, "editor_id", "")),
        name=str(getattr(component, "name", "")),
        kind=str(getattr(component, "component_kind", "editor") or "editor"),
        extensions=tuple(str(value) for value in getattr(component, "extensions", ())),
        launch_mode=str(getattr(component, "launch_mode", "auto") or "auto"),
        portable_command=tuple(getattr(component, "portable_command", ()) or ()) or None,
        installed_command=tuple(getattr(component, "installed_command", ()) or ()) or None,
        portable_root=Path(portable_root).expanduser().resolve(strict=False) if portable_root else None,
        active_version=str(getattr(component, "active_version", "") or "") or None,
        capabilities=tuple(sorted(component_capabilities(component))),
    )


def inventory_stamp(components_root: Path) -> str:
    """Return a cheap shallow stamp for the managed component inventory.

    The file-routing hot path must not recursively inspect application source.
    A shallow canonical-tree stamp catches component/version/runtime additions,
    removals, launcher/manifest replacement, and AppImage changes. If it moves,
    the cached routing index is discarded and authoritative discovery rebuilds
    it.
    """
    root = components_root.expanduser().resolve(strict=False)
    if not root.is_dir():
        return "missing"
    records: list[str] = []

    def add(path: Path) -> None:
        try:
            stat = path.stat()
            relative = path.relative_to(root).as_posix()
            records.append(f"{relative}|{stat.st_mtime_ns}|{stat.st_size}|{int(path.is_dir())}")
        except (OSError, ValueError):
            records.append(f"!{path.name}")

    add(root)
    try:
        applications = sorted((item for item in root.iterdir() if item.is_dir() and not item.is_symlink() and not item.name.startswith(".")), key=lambda item: item.name.casefold())
    except OSError:
        return "unreadable"
    for application in applications:
        add(application)
        try:
            versions = sorted((item for item in application.iterdir() if item.is_dir() and not item.is_symlink() and not item.name.startswith(".")), key=lambda item: item.name.casefold())
        except OSError:
            continue
        for version in versions:
            add(version)
            portable = version / "Portable"
            if portable.is_dir() and not portable.is_symlink():
                add(portable)
                for name in ("main.py", "suite-pythoine.json", "editor.json", "suite-pythoine-component.json"):
                    candidate = portable / name
                    if candidate.is_file() and not candidate.is_symlink():
                        add(candidate)
            appimage = version / "AppImage"
            if appimage.is_dir() and not appimage.is_symlink():
                add(appimage)
                try:
                    artifacts = sorted((item for item in appimage.iterdir() if item.is_file() and not item.is_symlink() and (item.suffix.casefold() == ".appimage" or item.name.endswith(".suite-pythoine.json"))), key=lambda item: item.name.casefold())
                except OSError:
                    artifacts = []
                for artifact in artifacts:
                    add(artifact)
    payload = "\n".join(records).encode("utf-8", errors="surrogateescape")
    return hashlib.sha256(payload).hexdigest()


def build_index_payload(components: Iterable[object], components_root: Path) -> dict:
    items = []
    for component in components:
        target = target_from_component(component)
        items.append({
            "id": target.component_id,
            "name": target.name,
            "kind": target.kind,
            "extensions": list(target.extensions),
            "launch_mode": target.launch_mode,
            "portable_command": list(target.portable_command) if target.portable_command else None,
            "installed_command": list(target.installed_command) if target.installed_command else None,
            "portable_root": str(target.portable_root) if target.portable_root else None,
            "active_version": target.active_version,
            "capabilities": list(target.capabilities),
        })
    root = components_root.expanduser().resolve(strict=False)
    return {
        "schema": ROUTING_INDEX_SCHEMA,
        "components_root": str(root),
        "inventory_stamp": inventory_stamp(root),
        "catalog_fingerprint": catalog_fingerprint(),
        "components": items,
    }


def load_index(config: dict, components_root: Path) -> list[RoutingTarget] | None:
    raw = config.get("routing_index") if isinstance(config, dict) else None
    if not isinstance(raw, dict) or raw.get("schema") != ROUTING_INDEX_SCHEMA:
        return None
    resolved_root = components_root.expanduser().resolve(strict=False)
    if str(raw.get("components_root") or "") != str(resolved_root):
        return None
    cached_stamp = raw.get("inventory_stamp")
    if not isinstance(cached_stamp, str) or cached_stamp != inventory_stamp(resolved_root):
        return None
    cached_catalog = raw.get("catalog_fingerprint")
    if not isinstance(cached_catalog, str) or cached_catalog != catalog_fingerprint():
        return None
    values = raw.get("components")
    if not isinstance(values, list):
        return None
    result: list[RoutingTarget] = []
    for value in values:
        if not isinstance(value, dict):
            return None
        component_id = str(value.get("id") or "").strip()
        name = str(value.get("name") or "").strip()
        kind = str(value.get("kind") or "").strip().casefold()
        if not component_id or not name or kind not in {"hub", "editor", "reader", "extension"}:
            return None
        def command(key: str) -> tuple[str, ...] | None:
            raw_command = value.get(key)
            if not isinstance(raw_command, list) or not raw_command or not all(isinstance(part, str) for part in raw_command):
                return None
            return tuple(raw_command)
        portable = command("portable_command")
        installed = command("installed_command")
        # A cached index is used only while its concrete absolute launchers still
        # exist. Otherwise discovery rebuilds it on the next full Suite launch.
        if portable and not _command_valid(portable):
            portable = None
        if installed and not _command_valid(installed):
            installed = None
        root_value = value.get("portable_root")
        portable_root = Path(root_value).expanduser().resolve(strict=False) if isinstance(root_value, str) and root_value else None
        extensions_raw = value.get("extensions")
        extensions = tuple(str(item).strip().casefold() for item in extensions_raw if str(item).strip()) if isinstance(extensions_raw, list) else ()
        capabilities_raw = value.get("capabilities")
        capabilities = tuple(str(item).strip().casefold() for item in capabilities_raw if str(item).strip()) if isinstance(capabilities_raw, list) else ()
        result.append(RoutingTarget(
            component_id=component_id,
            name=name,
            kind=kind,
            extensions=extensions,
            launch_mode=str(value.get("launch_mode") or "auto"),
            portable_command=portable,
            installed_command=installed,
            portable_root=portable_root,
            active_version=str(value.get("active_version") or "") or None,
            capabilities=capabilities,
        ))
    return result
