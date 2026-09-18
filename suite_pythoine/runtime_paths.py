from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

from PyQt6.QtCore import QStandardPaths

from .storage_layout import editors_root_default, legacy_editors_root_default

COMPONENTS_ROOT_ENVIRONMENT_VARIABLE = "SUITE_PYTHOINE_COMPONENTS_ROOT"
EDITORS_ROOT_ENVIRONMENT_VARIABLE = "SUITE_PYTHOINE_EDITORS_ROOT"  # compatibility alias
LEGACY_MY_EDITORS_ENVIRONMENT_VARIABLE = "SUITE_PYTHOINE_MY_EDITORS"
APPIMAGE_ENVIRONMENT_VARIABLE = "APPIMAGE"


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    """Resolve Suite-owned writable paths without depending on shell cwd.

    Since 0.1.2, both portable editor sources and managed AppImages share one
    user-facing Components root. The legacy locations are retained only so the
    migration wizard can identify older default installations safely.
    """

    launcher_root: Path
    package_root: Path
    config_root: Path
    default_editors_root: Path
    legacy_default_my_editors: Path
    legacy_default_installed_editors: Path
    running_as_appimage: bool
    running_frozen: bool

    @classmethod
    def detect(cls, launcher_file: str | Path) -> "RuntimePaths":
        launcher_root = Path(launcher_file).resolve().parent
        running_as_appimage = bool(os.environ.get(APPIMAGE_ENVIRONMENT_VARIABLE))
        running_frozen = bool(getattr(sys, "frozen", False))

        frozen_root_value = getattr(sys, "_MEIPASS", None)
        frozen_root = Path(frozen_root_value).resolve() if frozen_root_value else launcher_root
        source_package_root = launcher_root / "suite_pythoine"
        bundled_package_root = frozen_root / "suite_pythoine"
        package_root = bundled_package_root if bundled_package_root.exists() else source_package_root

        if os.name == "nt":
            base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
            config_root = base / "brunonlinespace" / "suite-pythoine"
        else:
            config_root = Path.home() / ".config" / "brunonlinespace" / "suite-pythoine"

        override = (
            os.environ.get(COMPONENTS_ROOT_ENVIRONMENT_VARIABLE, "").strip()
            or os.environ.get(EDITORS_ROOT_ENVIRONMENT_VARIABLE, "").strip()
        )
        if override:
            default_editors_root = Path(override).expanduser().resolve(strict=False)
        else:
            default_editors_root = editors_root_default()

        # Historical default portable locations, used only for migration.
        if not running_as_appimage and not running_frozen:
            legacy_my_editors = launcher_root / "my editors"
        else:
            documents = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
            documents_root = Path(documents).expanduser().resolve(strict=False) if documents else Path.home() / "Documents"
            legacy_my_editors = documents_root / "Suite Pythoine" / "My Editors"

        return cls(
            launcher_root=launcher_root,
            package_root=package_root,
            config_root=config_root,
            default_editors_root=default_editors_root,
            legacy_default_my_editors=legacy_my_editors.resolve(strict=False),
            legacy_default_installed_editors=legacy_editors_root_default(),
            running_as_appimage=running_as_appimage,
            running_frozen=running_frozen,
        )

    @property
    def config_path(self) -> Path:
        return self.config_root / "suite-pythoine.json"

    @property
    def developer_intake_config_path(self) -> Path:
        return self.config_root / "developer-intake.json"

    @property
    def developer_component_catalog_path(self) -> Path:
        return self.config_root / "developer-components.json"

    @property
    def store_cache_dir(self) -> Path:
        if os.name == "nt":
            base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
            return base / "brunonlinespace" / "suite-pythoine" / "downloads"
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
        return base / "suite-pythoine" / "downloads"

    @property
    def runtime_label(self) -> str:
        if self.running_as_appimage:
            return "AppImage"
        if self.running_frozen:
            return "Frozen bundle"
        return "Portable source"

    def resolve_editors_root(self, configured: object) -> Path:
        if isinstance(configured, str) and configured.strip():
            return Path(configured).expanduser().resolve(strict=False)
        return self.default_editors_root.resolve(strict=False)

    # Compatibility aliases used by older code paths while loading old config.
    @property
    def default_my_editors(self) -> Path:
        return self.default_editors_root

    @property
    def default_installed_editors(self) -> Path:
        return self.default_editors_root

    def resolve_my_editors(self, configured: object) -> Path:
        return self.resolve_editors_root(configured)

    @staticmethod
    def ensure_writable_directory(path: str | Path) -> Path:
        target = Path(path).expanduser().resolve(strict=False)
        target.mkdir(parents=True, exist_ok=True)
        probe_path: Path | None = None
        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=target,
                prefix=".suite-pythoine-write-test-",
                delete=False,
            ) as handle:
                handle.write("ok")
                probe_path = Path(handle.name)
        finally:
            if probe_path is not None:
                try:
                    probe_path.unlink()
                except OSError:
                    pass
        return target
