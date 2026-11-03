"""One-time retirement of the obsolete (pre-0.8.1) registry file."""
from __future__ import annotations
from pathlib import Path
import os

class RegistryRetirementError(OSError):
    pass

def legacy_registry_path(preferences_path: Path, normal_preferences_path: Path) -> Path:
    if preferences_path.expanduser().resolve(strict=False) == normal_preferences_path.expanduser().resolve(strict=False):
        if os.name == 'nt':
            base = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local')
        else:
            value = os.environ.get('XDG_DATA_HOME', '').strip()
            base = Path(value).expanduser() if value and Path(value).expanduser().is_absolute() else Path.home() / '.local' / 'share'
        return base / 'brunonlinespace' / 'suite-pythoine' / 'managed-registry.json'
    return preferences_path.parent / f'{preferences_path.stem}.managed-registry.json'

def retire_registry(path: Path) -> None:
    """Unconditionally discard obsolete registry; never follows a symlink."""
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        raise RegistryRetirementError(f'Could not retire obsolete installation registry {path}: {exc}') from exc
