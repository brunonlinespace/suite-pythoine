"""0.8.1 live installation state; deliberately NO ownership registry or writes.

The managed root is an ownership boundary, not an authenticity certificate. Records
returned here are transient compatibility projections of real version files and a
verified desktop launcher. Never persist these records or infer AppImage ownership
from the existence of a Portable desktop entry.
"""
from __future__ import annotations

from pathlib import Path
import re
from typing import Any, MutableMapping

from .catalogue.component_catalog import COMPONENT_PROFILES
from .installer import (desktop_entry_path, desktop_entry_status,
                        portable_desktop_entry_status, desktop_entry_runtime,
                        desktop_entry_exec_command)
from .storage_layout import editors_root_default, application_folder_name, version_folder_name
from .versioning import read_appimage_metadata, version_from_filename


def _safe_id(value: str) -> str:
    return re.sub(r'[^A-Za-z0-9._-]+', '-', str(value)).strip('-._') or 'editor'


def desktop_id_for(editor_id: str) -> str:
    return f'io.github.brunonlinespace.{_safe_id(editor_id)}'


def _root(data: dict) -> Path:
    raw = data.get('_inventory_root') or data.get('editors_root')
    return Path(raw).expanduser().resolve(strict=False) if isinstance(raw, str) and raw.strip() else editors_root_default()


def _application_dirs(root: Path, editor_id: str) -> list[Path]:
    profile = COMPONENT_PROFILES.get(editor_id)
    if profile is None or not root.is_dir() or root.is_symlink():
        return []
    aliases = (profile.name, editor_id, *profile.identity_hints)
    def key(value: str) -> str:
        return re.sub(r'[^a-z0-9]+', '', str(value).casefold())
    keys = {key(a) for a in aliases if a}
    try:
        return [p for p in root.iterdir() if p.is_dir() and not p.is_symlink()
                and not p.name.startswith('.') and key(p.name) in keys]
    except OSError:
        return []


def _desktop_matches(editor_id: str, version_dir: Path, appimage: Path | None) -> tuple[bool, Path | None]:
    desktop = desktop_entry_path(editor_id)
    if not desktop.is_file() or desktop.is_symlink():
        return False, None
    runtime = desktop_entry_runtime(desktop)
    desktop_id = desktop_id_for(editor_id)
    if runtime == 'appimage' and appimage is not None:
        ready = desktop_entry_status(editor_id, appimage, desktop_id=desktop_id) == 'ready'
    elif runtime == 'portable':
        command = desktop_entry_exec_command(desktop)
        # Desktop writer stores the Portable's exact main.py command, which
        # must remain within this version rather than merely having a matching name.
        ready = (len(command) >= 2 and Path(command[-1]).expanduser().resolve(strict=False).is_file()
                 and Path(command[-1]).expanduser().resolve(strict=False).is_relative_to(version_dir / 'Portable')
                 and portable_desktop_entry_status(editor_id, command, desktop_id=desktop_id) == 'ready')
    else:
        ready = False
    return ready, desktop if ready else None


def _version_projection(editor_id: str, version_dir: Path) -> dict[str, Any]:
    profile = COMPONENT_PROFILES[editor_id]
    version = version_dir.name
    app_dir = version_dir / 'AppImage'
    matches: list[Path] = []
    if app_dir.is_dir() and not app_dir.is_symlink():
        try:
            matches = sorted(p for p in app_dir.iterdir() if p.is_file() and not p.is_symlink()
                             and p.suffix.casefold() == '.appimage')
        except OSError:
            pass
    appimage: Path | None = None
    metadata: dict = {}
    # Never choose an arbitrary one of several conflicting AppImages.
    if len(matches) == 1:
        candidate = matches[0]
        metadata = read_appimage_metadata(candidate)
        declared_id = str(metadata.get('editor_id') or '').strip()
        declared_version = str(metadata.get('version') or '').strip()
        filename_version = version_from_filename(candidate)
        if (not declared_id or declared_id == editor_id) and (not declared_version or version_folder_name(declared_version) == version_dir.name):
            # A renamed folder cannot fabricate version identity. Require an
            # explicit sidecar or an eligible legacy filename version.
            if declared_version or (filename_version and version_folder_name(filename_version) == version_dir.name):
                appimage = candidate
    portable = version_dir / 'Portable'
    ready_desktop, desktop = _desktop_matches(editor_id, version_dir, appimage)
    if appimage is None and not ready_desktop:
        return {}  # Portable-only versions are discovered by source inspection.
    icon = next((p for p in app_dir.glob('*-icon.*') if p.is_file() and not p.is_symlink()), None) if app_dir.is_dir() else None
    return {
        'schema': 2, 'editor_id': editor_id, 'application_id': editor_id,
        'name': profile.name, 'version': version,
        'appimage_path': str(appimage.resolve(strict=False)) if appimage else None,
        'appimage_sha256': (metadata.get('appimage_sha256') or metadata.get('sha256')) if appimage else None,
        'icon_path': str(icon.resolve(strict=False)) if icon else None,
        'desktop_id': desktop_id_for(editor_id),
        'desktop_file_path': str(desktop) if desktop else None,
        'desktop_integrated': ready_desktop,
        'publisher_id': profile.publisher_id,
        'extensions': list(profile.extensions), 'description': profile.description,
    }


def get_managed_versions(config_data: dict, editor_id: str) -> dict[str, dict[str, Any]]:
    """Legacy API spelling, computed on every call from the current filesystem."""
    versions: dict[str, dict] = {}
    for app in _application_dirs(_root(config_data), editor_id):
        try:
            children = list(app.iterdir())
        except OSError:
            continue
        for version_dir in children:
            if not version_dir.is_dir() or version_dir.is_symlink() or version_dir.name.startswith('.'):
                continue
            record = _version_projection(editor_id, version_dir)
            if record:
                versions[record['version']] = record
    return versions


def get_managed_group(config_data: dict, editor_id: str) -> dict[str, Any]:
    versions = get_managed_versions(config_data, editor_id)
    if not versions:
        return {}
    overrides = config_data.get('editor_overrides', {})
    override = overrides.get(editor_id, {}) if isinstance(overrides, dict) else {}
    remembered = override.get('active_version') if isinstance(override, dict) else None
    desktop_version = next((v for v, r in versions.items() if r.get('desktop_integrated')), None)
    return {
        'schema': 2, 'editor_id': editor_id, 'name': COMPONENT_PROFILES[editor_id].name,
        'active_version': desktop_version or (remembered if remembered in versions else None),
        'desktop_version': desktop_version, 'versions': versions,
        'publisher_id': COMPONENT_PROFILES[editor_id].publisher_id,
    }


def get_managed_installation(config_data: dict, editor_id: str, version: str | None = None) -> dict[str, Any]:
    group = get_managed_group(config_data, editor_id)
    wanted = version or group.get('active_version')
    return dict(group.get('versions', {}).get(wanted, {}))


def ensure_registry(config_data: MutableMapping[str, Any]) -> dict:
    """Retired API: installation ownership is never materialised into config."""
    return {}


def set_managed_installation(config_data: MutableMapping[str, Any], record: dict[str, Any], *,
                             set_active: bool = True, desktop_integrated: bool | None = None) -> dict[str, Any]:
    """Compatibility return for installers; actual registration is placing files in root."""
    editor_id = str(record.get('editor_id') or '').strip()
    version = str(record.get('version') or '').strip()
    if not editor_id or not version or editor_id not in COMPONENT_PROFILES:
        raise ValueError('Unrecognised component identity or exact version')
    result = dict(record)
    result.setdefault('application_id', editor_id)
    result.setdefault('desktop_id', desktop_id_for(editor_id))
    result['desktop_integrated'] = bool(desktop_integrated if desktop_integrated is not None else record.get('desktop_file_path'))
    if set_active:
        set_active_version(config_data, editor_id, version)
    return result


def set_active_version(config_data: MutableMapping[str, Any], editor_id: str, version: str) -> bool:
    if not version or editor_id not in COMPONENT_PROFILES:
        return False
    overrides = config_data.setdefault('editor_overrides', {})
    if not isinstance(overrides, dict):
        return False
    override = overrides.setdefault(editor_id, {})
    if not isinstance(override, dict):
        return False
    override['active_version'] = version
    return True


def set_desktop_version(config_data: MutableMapping[str, Any], editor_id: str, version: str | None,
                        desktop_path: Path | str | None = None) -> bool:
    """The desktop entry, not another persistent record, owns this fact."""
    if version is None:
        return True
    if desktop_path is not None and not Path(desktop_path).is_file():
        return False
    return True  # Writers verify the real desktop target before invoking this.


def remove_managed_version(config_data: MutableMapping[str, Any], editor_id: str, version: str) -> dict:
    # File deletion happens in the caller's staged filesystem transaction.
    return get_managed_installation(config_data, editor_id, version)


def remove_managed_installation(config_data: MutableMapping[str, Any], editor_id: str) -> dict:
    return get_managed_installation(config_data, editor_id)


def record_paths(record: dict[str, Any]) -> dict[str, Path | None]:
    return {key: Path(record[value]).expanduser().resolve(strict=False) if isinstance(record.get(value), str) and record[value] else None
            for key, value in (('appimage', 'appimage_path'), ('desktop', 'desktop_file_path'), ('icon', 'icon_path'))}


def record_is_complete(record: dict[str, Any]) -> bool:
    return bool(record.get('editor_id') and record.get('version') and record.get('appimage_path'))


def desktop_selection(editor_id: str, versions: dict, root: Path) -> tuple[str, str | None, str | None]:
    """Return (state, exact_version, runtime) from the actual desktop entry.

    No executable is started. Even a Suite-marked launcher is not authoritative
    unless its command matches a validated managed runtime in the managed root.
    """
    desktop = desktop_entry_path(editor_id)
    if not desktop.exists() and not desktop.is_symlink():
        return 'missing', None, None
    if desktop.is_symlink() or not desktop.is_file():
        return 'broken', None, None
    from .installer import _primary_desktop_values  # parser only, never executes
    values = _primary_desktop_values(desktop)
    command = desktop_entry_exec_command(desktop)
    runtime = desktop_entry_runtime(desktop)
    if not command:
        return 'broken', None, None
    target = Path(command[0] if runtime == 'appimage' else command[-1]).expanduser().resolve(strict=False)
    if not target.is_relative_to(root.resolve(strict=False)):
        return 'external-target', None, None
    if (values.get('X-Suite-Pythoine-Managed', '').casefold() != 'true'
            or values.get('X-Suite-Pythoine-ApplicationId') != _safe_id(editor_id)
            or values.get('X-Suite-Pythoine-DesktopId') != desktop_id_for(editor_id)
            or runtime not in ('portable', 'appimage')):
        return 'legacy-launcher', None, None
    for version, info in versions.items():
        if runtime == 'portable' and info.has_portable and info.portable_command:
            if portable_desktop_entry_status(editor_id, info.portable_command, desktop_id=desktop_id_for(editor_id)) == 'ready':
                return 'ready', version, runtime
        if runtime == 'appimage' and info.has_appimage and info.appimage_path:
            if desktop_entry_status(editor_id, info.appimage_path, desktop_id=desktop_id_for(editor_id)) == 'ready':
                return 'ready', version, runtime
    return 'broken', None, None
