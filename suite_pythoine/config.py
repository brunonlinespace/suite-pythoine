from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from .storage_layout import legacy_editors_root_default


MARKDOWN_FAMILY = frozenset({".md", ".markdown", ".mdown", ".mkd"})


def default_config_path() -> Path:
    """Return Suite's normal preference path without importing any GUI module."""
    import os
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / "brunonlinespace" / "suite-pythoine" / "suite-pythoine.json"
    return Path.home() / ".config" / "brunonlinespace" / "suite-pythoine" / "suite-pythoine.json"


def apply_routing_compatibility_migrations(data: dict[str, Any]) -> bool:
    """Normalize routing state that must also be safe on the pre-GUI hot path.

    Keep this helper dependency-light: silent_dispatch calls it before consulting
    remembered routes or doing component discovery, so catalogue transitions can
    take effect without constructing the Hub GUI.
    """
    changed = False
    overrides = data.get("editor_overrides")
    if not isinstance(overrides, dict):
        overrides = {}
        data["editor_overrides"] = overrides

    # Repair the one historic publisher/application identity mix-up wherever it
    # can influence routing. The full managed-installation migration remains in
    # ConfigService.load().
    if "brunonlinespace" in overrides and "suite-pythoine" not in overrides:
        overrides["suite-pythoine"] = overrides.pop("brunonlinespace")
        changed = True

    preferences = data.get("extension_preferences")
    if not isinstance(preferences, dict):
        preferences = {}
        data["extension_preferences"] = preferences
    for extension, component_id in list(preferences.items()):
        if component_id == "brunonlinespace":
            preferences[extension] = "suite-pythoine"
            changed = True
        elif component_id == "gitten-pad":
            preferences[extension] = "gitten"
            changed = True

    # Gitten's canonical component ID is now ``gitten``. Keep the dependency-
    # light routing/startup path coherent before the full ConfigService migration.
    if "gitten-pad" in overrides:
        old_value = overrides.pop("gitten-pad")
        if "gitten" not in overrides:
            overrides["gitten"] = old_value
        elif isinstance(old_value, dict) and isinstance(overrides.get("gitten"), dict):
            merged = dict(old_value)
            merged.update(overrides["gitten"])
            overrides["gitten"] = merged
        changed = True

    # Linspectacles supersedes the former Linspector/Linspector Suite identity.
    # Keep old IDs only as migration/recognition aliases; canonical state is
    # always written under ``linspectacles``.
    for old_id in ("linspector-suite", "linspector"):
        if old_id in overrides:
            old_value = overrides.pop(old_id)
            if "linspectacles" not in overrides:
                overrides["linspectacles"] = old_value
            elif isinstance(old_value, dict) and isinstance(overrides.get("linspectacles"), dict):
                merged = dict(old_value)
                merged.update(overrides["linspectacles"])
                overrides["linspectacles"] = merged
            changed = True
    for extension, component_id in list(preferences.items()):
        if component_id in {"linspector-suite", "linspector"}:
            preferences[extension] = "linspectacles"
            changed = True

    # PSTS Pad never existed; discard the stale placeholder identity wherever
    # it could survive into the pre-GUI routing path.
    if "psts-pad" in overrides:
        overrides.pop("psts-pad", None)
        changed = True
    for extension, component_id in list(preferences.items()):
        if component_id == "psts-pad":
            preferences.pop(extension, None)
            changed = True

    # 0.3.1 transfers the Markdown family from Ricopad to Markopad. 0.3.0 could
    # snapshot Ricopad's then-default extensions into editor_overrides merely
    # when Launch runtime was saved. Strip that obsolete family while retaining
    # unrelated deliberate additions and RTF.
    ricopad_override = overrides.get("ricopad")
    if isinstance(ricopad_override, dict) and isinstance(ricopad_override.get("extensions"), list):
        cleaned: list[str] = []
        for value in ricopad_override.get("extensions", []):
            extension = str(value or "").strip().casefold()
            if extension and not extension.startswith("."):
                extension = f".{extension}"
            if extension and extension not in MARKDOWN_FAMILY and extension not in cleaned:
                cleaned.append(extension)
        if ".rtf" not in cleaned:
            cleaned.append(".rtf")
        if cleaned != ricopad_override.get("extensions"):
            ricopad_override["extensions"] = cleaned
            changed = True

    for extension in MARKDOWN_FAMILY:
        if preferences.get(extension) == "ricopad":
            preferences.pop(extension, None)
            changed = True

    if changed:
        data["routing_index"] = {}
    return changed


class ConfigService:
    """Small JSON preference store with atomic replacement and typed reads."""

    DEFAULTS: dict[str, Any] = {
        "editors_root": None,
        "legacy_my_editors_dir": None,
        "legacy_installed_editors_dir": None,
        "storage_layout_version": 3,
        "storage_migration_dismissed": False,
        "canonical_root_transition_dismissed": False,
        "editor_overrides": {},
        "managed_installations": {},
        "extension_preferences": {},
        "inspector_fallback_preference": "__ask_every_time__",
        "routing_index": {},
        "dashboard_view": "list",
        "dashboard_sort": "title_az",
        "dashboard_search": "",
        "window_width": 1180,
        "window_height": 760,
        "window_maximized": False,
        "splitter_sizes": [250, 930],
        "installed_apps_table_layout": {},
        "sidebar_visible": True,
        "dashboard_show_icons": True,
        "dashboard_drop_bar_visible": True,
        "last_selected_editor": None,
        "pending_self_cleanup": None,
    }

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve(strict=False)
        self._data: dict[str, Any] = dict(self.DEFAULTS)
        # Mutable defaults must not be shared.
        self._data["editor_overrides"] = {}
        self._data["managed_installations"] = {}
        self._data["extension_preferences"] = {}
        self._data["routing_index"] = {}
        self._data["installed_apps_table_layout"] = {}
        self._data["splitter_sizes"] = list(self.DEFAULTS["splitter_sizes"])
        self.load()

    def load(self) -> None:
        defaults = dict(self.DEFAULTS)
        defaults["editor_overrides"] = {}
        defaults["managed_installations"] = {}
        defaults["extension_preferences"] = {}
        defaults["routing_index"] = {}
        defaults["installed_apps_table_layout"] = {}
        defaults["splitter_sizes"] = list(self.DEFAULTS["splitter_sizes"])
        self._data = defaults
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            return
        if not isinstance(loaded, dict):
            return
        for key, value in loaded.items():
            if key in {"editor_overrides", "managed_installations", "extension_preferences", "routing_index", "installed_apps_table_layout"}:
                if isinstance(value, dict):
                    self._data[key].update(value)
            elif key == "window" and isinstance(value, dict):
                # One-time compatibility with Suite Pythoine r1 preferences.
                if "width" in value:
                    self._data["window_width"] = value["width"]
                if "height" in value:
                    self._data["window_height"] = value["height"]
                if "sidebar" in value:
                    self._data["splitter_sizes"] = [value["sidebar"], 930]
            elif key == "my_editors_dir":
                # 0.1.0 and earlier had separate portable/installed roots. Keep
                # custom values only as migration inputs; new installs use one root.
                if isinstance(value, str) and value.strip():
                    self._data["legacy_my_editors_dir"] = value
            elif key == "installed_editors_dir":
                if isinstance(value, str) and value.strip():
                    self._data["legacy_installed_editors_dir"] = value
            elif key == "store_state":
                # 0.3.3 decouples the online Store into standalone Store Pythoine.
                # Retire the old built-in Store toggle instead of persisting it.
                continue
            else:
                self._data[key] = value

        # 0.3.0 changes the canonical default managed root from
        # ~/Suite Pythoine Editors to ~/Suite Pythoine. If an older config
        # explicitly persisted the old default, treat it as a one-time migration
        # source rather than continuing to scan both roots indefinitely.
        configured_root = self._data.get("editors_root")
        if isinstance(configured_root, str) and configured_root.strip():
            try:
                configured_path = Path(configured_root).expanduser().resolve(strict=False)
            except OSError:
                configured_path = None
            legacy_default = legacy_editors_root_default()
            if configured_path == legacy_default:
                self._data["legacy_installed_editors_dir"] = str(legacy_default)
                self._data["editors_root"] = None
                self._data["canonical_root_transition_dismissed"] = False

        # 0.1.0 briefly confused the publisher name with Suite Pythoine's
        # application/editor identity. Repair that one known identity on load.
        managed = self._data.get("managed_installations", {})
        if isinstance(managed, dict) and "brunonlinespace" in managed and "suite-pythoine" not in managed:
            record = managed.get("brunonlinespace")
            if isinstance(record, dict) and str(record.get("name", "")).casefold() == "suite pythoine":
                fixed = dict(record)
                fixed["editor_id"] = "suite-pythoine"
                fixed["application_id"] = "suite-pythoine"
                managed["suite-pythoine"] = fixed
                managed.pop("brunonlinespace", None)
        overrides = self._data.get("editor_overrides", {})
        if isinstance(overrides, dict) and "brunonlinespace" in overrides and "suite-pythoine" not in overrides:
            overrides["suite-pythoine"] = overrides.pop("brunonlinespace")

        # Gitten 0.0.1-r4 renamed the canonical product identity from
        # ``gitten-pad`` / "Gitten Pad" to lowercase ``gitten``. Preserve
        # existing Suite state under the new trusted ID instead of exposing two
        # logical components. New-ID values win when both happen to exist.
        old_id, new_id = "gitten-pad", "gitten"
        overrides = self._data.get("editor_overrides", {})
        if isinstance(overrides, dict) and old_id in overrides:
            old_value = overrides.pop(old_id)
            if new_id not in overrides:
                overrides[new_id] = old_value
            elif isinstance(old_value, dict) and isinstance(overrides.get(new_id), dict):
                merged = dict(old_value)
                merged.update(overrides[new_id])
                overrides[new_id] = merged

        managed = self._data.get("managed_installations", {})
        if isinstance(managed, dict) and old_id in managed:
            old_group = managed.pop(old_id)
            if new_id not in managed and isinstance(old_group, dict):
                fixed_group = dict(old_group)
                fixed_group["editor_id"] = new_id
                fixed_group["application_id"] = new_id
                if str(fixed_group.get("name") or "").casefold() == "gitten pad":
                    fixed_group["name"] = "gitten"
                if str(fixed_group.get("desktop_id") or "") == "io.github.brunonlinespace.gitten-pad":
                    fixed_group["desktop_id"] = "io.github.brunonlinespace.gitten"
                raw_desktop = fixed_group.get("desktop_file_path")
                if isinstance(raw_desktop, str) and raw_desktop.endswith("/io.github.brunonlinespace.gitten-pad.desktop"):
                    fixed_group["desktop_file_path"] = raw_desktop.rsplit("/", 1)[0] + "/io.github.brunonlinespace.gitten.desktop"
                versions = fixed_group.get("versions")
                if isinstance(versions, dict):
                    fixed_versions = {}
                    for version, record in versions.items():
                        if isinstance(record, dict):
                            fixed = dict(record)
                            fixed["editor_id"] = new_id
                            fixed["application_id"] = new_id
                            if str(fixed.get("name") or "").casefold() == "gitten pad":
                                fixed["name"] = "gitten"
                            if str(fixed.get("desktop_id") or "") == "io.github.brunonlinespace.gitten-pad":
                                fixed["desktop_id"] = "io.github.brunonlinespace.gitten"
                            raw_desktop = fixed.get("desktop_file_path")
                            if isinstance(raw_desktop, str) and raw_desktop.endswith("/io.github.brunonlinespace.gitten-pad.desktop"):
                                fixed["desktop_file_path"] = raw_desktop.rsplit("/", 1)[0] + "/io.github.brunonlinespace.gitten.desktop"
                            fixed_versions[version] = fixed
                        else:
                            fixed_versions[version] = record
                    fixed_group["versions"] = fixed_versions
                managed[new_id] = fixed_group

        preferences = self._data.get("extension_preferences", {})
        if isinstance(preferences, dict):
            for extension, component_id in list(preferences.items()):
                if component_id == old_id:
                    preferences[extension] = new_id
        if self._data.get("last_selected_editor") == old_id:
            self._data["last_selected_editor"] = new_id

        # Linspectacles replaces the former Linspector/Linspector Suite product
        # identity. Preserve existing managed/preferences state under the new
        # trusted ID and canonical desktop identity.
        linspect_new = "linspectacles"
        overrides = self._data.get("editor_overrides", {})
        if isinstance(overrides, dict):
            for linspect_old in ("linspector-suite", "linspector"):
                if linspect_old not in overrides:
                    continue
                old_value = overrides.pop(linspect_old)
                if linspect_new not in overrides:
                    overrides[linspect_new] = old_value
                elif isinstance(old_value, dict) and isinstance(overrides.get(linspect_new), dict):
                    merged = dict(old_value)
                    merged.update(overrides[linspect_new])
                    overrides[linspect_new] = merged

        managed = self._data.get("managed_installations", {})
        if isinstance(managed, dict):
            for linspect_old in ("linspector-suite", "linspector"):
                if linspect_old not in managed:
                    continue
                old_group = managed.pop(linspect_old)
                if linspect_new in managed or not isinstance(old_group, dict):
                    continue
                fixed_group = dict(old_group)
                fixed_group["editor_id"] = linspect_new
                fixed_group["application_id"] = linspect_new
                if str(fixed_group.get("name") or "").casefold() in {"linspector", "linspector suite"}:
                    fixed_group["name"] = "Linspectacles"
                if str(fixed_group.get("desktop_id") or "") in {"io.github.brunonlinespace.linspector-suite", "io.github.brunonlinespace.linspector"}:
                    fixed_group["desktop_id"] = "io.github.brunonlinespace.linspectacles"
                raw_desktop = fixed_group.get("desktop_file_path")
                if isinstance(raw_desktop, str) and raw_desktop.rsplit("/", 1)[-1] in {"io.github.brunonlinespace.linspector-suite.desktop", "io.github.brunonlinespace.linspector.desktop"}:
                    fixed_group["desktop_file_path"] = raw_desktop.rsplit("/", 1)[0] + "/io.github.brunonlinespace.linspectacles.desktop"
                versions = fixed_group.get("versions")
                if isinstance(versions, dict):
                    fixed_versions = {}
                    for version, record in versions.items():
                        if not isinstance(record, dict):
                            fixed_versions[version] = record
                            continue
                        fixed = dict(record)
                        fixed["editor_id"] = linspect_new
                        fixed["application_id"] = linspect_new
                        if str(fixed.get("name") or "").casefold() in {"linspector", "linspector suite"}:
                            fixed["name"] = "Linspectacles"
                        if str(fixed.get("desktop_id") or "") in {"io.github.brunonlinespace.linspector-suite", "io.github.brunonlinespace.linspector"}:
                            fixed["desktop_id"] = "io.github.brunonlinespace.linspectacles"
                        raw_desktop = fixed.get("desktop_file_path")
                        if isinstance(raw_desktop, str) and raw_desktop.rsplit("/", 1)[-1] in {"io.github.brunonlinespace.linspector-suite.desktop", "io.github.brunonlinespace.linspector.desktop"}:
                            fixed["desktop_file_path"] = raw_desktop.rsplit("/", 1)[0] + "/io.github.brunonlinespace.linspectacles.desktop"
                        fixed_versions[version] = fixed
                    fixed_group["versions"] = fixed_versions
                managed[linspect_new] = fixed_group

        preferences = self._data.get("extension_preferences", {})
        if isinstance(preferences, dict):
            for extension, component_id in list(preferences.items()):
                if component_id in {"linspector-suite", "linspector"}:
                    preferences[extension] = linspect_new
        if self._data.get("last_selected_editor") in {"linspector-suite", "linspector"}:
            self._data["last_selected_editor"] = linspect_new

        # PSTS Pad was a catalogue typo rather than a real application. Remove
        # any state created while the placeholder existed so it cannot remain as
        # a ghost component after the trusted catalogue drops it in 0.3.3.
        overrides = self._data.get("editor_overrides", {})
        if isinstance(overrides, dict):
            overrides.pop("psts-pad", None)
        managed = self._data.get("managed_installations", {})
        if isinstance(managed, dict):
            managed.pop("psts-pad", None)
        preferences = self._data.get("extension_preferences", {})
        if isinstance(preferences, dict):
            for extension, component_id in list(preferences.items()):
                if component_id == "psts-pad":
                    preferences.pop(extension, None)
        if self._data.get("last_selected_editor") == "psts-pad":
            self._data["last_selected_editor"] = None

        # Routing-affecting migrations also run in silent_dispatch before any
        # GUI import, so file launches and full-Hub launches agree immediately.
        apply_routing_compatibility_migrations(self._data)

    def save(self) -> bool:
        temporary: Path | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                json.dump(self._data, handle, indent=2, sort_keys=True)
                handle.write("\n")
                temporary = Path(handle.name)
            temporary.replace(self.path)
            return True
        except OSError:
            return False
        finally:
            if temporary is not None and temporary.exists():
                try:
                    temporary.unlink()
                except OSError:
                    pass

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any, *, save: bool = False) -> None:
        self._data[key] = value
        if save:
            self.save()

    def update(self, values: dict[str, Any], *, save: bool = False) -> None:
        self._data.update(values)
        if save:
            self.save()

    def get_int(self, key: str, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
        try:
            value = int(self._data.get(key, default))
        except (TypeError, ValueError):
            value = default
        if minimum is not None:
            value = max(minimum, value)
        if maximum is not None:
            value = min(maximum, value)
        return value

    def get_int_list(self, key: str, default: list[int], *, length: int | None = None) -> list[int]:
        raw = self._data.get(key, default)
        if not isinstance(raw, list) or (length is not None and len(raw) != length):
            return list(default)
        try:
            return [max(0, int(item)) for item in raw]
        except (TypeError, ValueError):
            return list(default)

    def as_dict(self) -> dict[str, Any]:
        return self._data
