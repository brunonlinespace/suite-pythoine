from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
from tempfile import NamedTemporaryFile
import zipfile

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QPlainTextEdit,
)

from .. import APP_NAME, __version__
from ..catalogue.component_catalog import COMPONENT_PROFILES, ComponentProfile
from ..install_inspection import inspect_editor_zip
from ..installer import InstallError, validate_zip
from ..registry import slugify
from ..ui_titles import app_dialog_title
from ..operation_ui import apply_operation_icon, configure_operation_window, operation_branding_header
from .developer_intake_vault import DeveloperIntakeSessionVault


DEVELOPER_CONFIG_SCHEMA = 1
LOCAL_CATALOG_SCHEMA = 1
DEFAULT_SOURCE_RELATIVE = "1 Source"
DEFAULT_NOTES_RELATIVE = "2 Release Notes"
DEFAULT_README_FILENAME = "README.md"
LOCAL_ID_PREFIX = "local:"


@dataclass(frozen=True, slots=True)
class DeveloperIdentity:
    component_id: str
    name: str
    official: bool


@dataclass(frozen=True, slots=True)
class LocalDeveloperComponent:
    component_id: str
    name: str
    identity_hints: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PreparedIntake:
    identity: DeveloperIdentity
    incoming_zip: Path
    configured_root: Path
    dev_folder: Path
    source_folder: Path
    notes_folder: Path
    stored_zip: Path
    source_relative: str
    notes_relative: str
    readme_filename: str
    delete_zip_after_success: bool
    delete_original_after_success: bool
    store_zip_only: bool


class DeveloperIntakeConfig:
    """Separate, deliberately tiny persistence store for Developer Intake.

    This file is intentionally not part of Suite Pythoine's normal ConfigService.
    Component identities come from Suite's trusted catalogue, while development
    destinations and layout preferences stay in a separate developer-only file.
    """

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve(strict=False)
        self.data = self._defaults()
        self.load()

    @staticmethod
    def _defaults() -> dict:
        return {
            "schema": DEVELOPER_CONFIG_SCHEMA,
            "enabled": False,
            "app_roots": {},
            "source_relative": DEFAULT_SOURCE_RELATIVE,
            "notes_relative": DEFAULT_NOTES_RELATIVE,
            "delete_zip_after_success": False,
            "delete_original_after_success": False,
            "store_zip_only": False,
            "readme_filename": DEFAULT_README_FILENAME,
        }

    def load(self) -> None:
        defaults = self._defaults()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8")) if self.path.is_file() else {}
        except (OSError, ValueError, TypeError):
            raw = {}
        if not isinstance(raw, dict) or raw.get("schema", DEVELOPER_CONFIG_SCHEMA) != DEVELOPER_CONFIG_SCHEMA:
            raw = {}
        roots = raw.get("app_roots")
        if not isinstance(roots, dict):
            roots = {}
        clean_roots: dict[str, str] = {}
        for key, value in roots.items():
            component_id = str(key).strip().casefold()
            text = str(value).strip() if isinstance(value, str) else ""
            if component_id and text:
                clean_roots[component_id] = text
        # Preserve the remembered development destination across the Gitten
        # product-identity migration. A deliberately configured new path wins.
        if "gitten-pad" in clean_roots:
            clean_roots.setdefault("gitten", clean_roots["gitten-pad"])
            clean_roots.pop("gitten-pad", None)
        for old_id in ("linspector-suite", "linspector"):
            if old_id in clean_roots:
                clean_roots.setdefault("linspectacles", clean_roots[old_id])
                clean_roots.pop(old_id, None)
        # PSTS Pad was a catalogue typo rather than a real application.
        clean_roots.pop("psts-pad", None)
        defaults.update({
            "enabled": bool(raw.get("enabled", False)),
            "app_roots": clean_roots,
            "source_relative": str(raw["source_relative"]) if isinstance(raw.get("source_relative"), str) else DEFAULT_SOURCE_RELATIVE,
            "notes_relative": str(raw["notes_relative"]) if isinstance(raw.get("notes_relative"), str) else DEFAULT_NOTES_RELATIVE,
            "delete_zip_after_success": bool(raw.get("delete_zip_after_success", False)),
            "delete_original_after_success": bool(raw.get("delete_original_after_success", False)),
            "store_zip_only": bool(raw.get("store_zip_only", False)),
            "readme_filename": str(raw["readme_filename"]) if isinstance(raw.get("readme_filename"), str) else DEFAULT_README_FILENAME,
        })
        self.data = defaults

    @property
    def enabled(self) -> bool:
        return bool(self.data.get("enabled", False))

    def set_enabled(self, value: bool, *, save: bool = True) -> bool:
        self.data["enabled"] = bool(value)
        return self.save() if save else True

    def app_root(self, component_id: str) -> Path | None:
        roots = self.data.get("app_roots", {})
        raw = roots.get(str(component_id).casefold()) if isinstance(roots, dict) else None
        if not isinstance(raw, str) or not raw.strip():
            return None
        return Path(raw).expanduser().resolve(strict=False)

    def set_app_root(self, component_id: str, root: Path | None) -> None:
        roots = self.data.setdefault("app_roots", {})
        if not isinstance(roots, dict):
            roots = {}
            self.data["app_roots"] = roots
        key = str(component_id).strip().casefold()
        if root is None:
            roots.pop(key, None)
        else:
            roots[key] = str(root.expanduser().resolve(strict=False))

    def save(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            payload = dict(self.data)
            payload["schema"] = DEVELOPER_CONFIG_SCHEMA
            with NamedTemporaryFile("w", encoding="utf-8", dir=self.path.parent, prefix=f".{self.path.name}.", suffix=".tmp", delete=False) as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
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


class DeveloperComponentCatalog:
    """Developer-only local identities.

    Local entries can help Developer Intake recognise experiments without a Suite
    rebuild. They are never merged into COMPONENT_PROFILES and therefore cannot
    participate in normal installation, routing, desktop integration, or Store
    behaviour. Official IDs/names/aliases are reserved and cannot be shadowed.
    """

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve(strict=False)
        self.components: list[LocalDeveloperComponent] = []
        self.load()

    @staticmethod
    def _official_aliases() -> set[str]:
        aliases: set[str] = set()
        for profile in COMPONENT_PROFILES.values():
            values = (profile.component_id, profile.name, *profile.identity_hints, *profile.appimage_prefixes)
            aliases.update(slugify(value) for value in values if value)
        return {value for value in aliases if value}

    @classmethod
    def validate_component(cls, component: LocalDeveloperComponent, *, existing: list[LocalDeveloperComponent] | None = None) -> None:
        cid = component.component_id.strip().casefold()
        if not cid.startswith(LOCAL_ID_PREFIX) or not re.fullmatch(r"local:[a-z0-9][a-z0-9-]*", cid):
            raise ValueError("Local component IDs must use the form local:my-component.")
        if not component.name.strip():
            raise ValueError("Local component name cannot be empty.")
        official_ids = set(COMPONENT_PROFILES)
        local_slug = cid[len(LOCAL_ID_PREFIX):]
        if local_slug in official_ids:
            raise ValueError("That ID is reserved by Suite Pythoine's trusted component catalogue.")
        official_aliases = cls._official_aliases()
        own_aliases = {slugify(component.name), slugify(local_slug)}
        own_aliases.update(slugify(value) for value in component.identity_hints if value)
        own_aliases.discard("")
        for value in own_aliases:
            if value in official_aliases or any(value.startswith(alias + "-") for alias in official_aliases):
                raise ValueError("This local identity could masquerade as an official Suite component. Choose a distinct name/recognition hint.")
        for other in existing or []:
            if other.component_id.casefold() == cid:
                continue
            other_aliases = {slugify(other.name), slugify(other.component_id[len(LOCAL_ID_PREFIX):])}
            other_aliases.update(slugify(value) for value in other.identity_hints)
            if own_aliases & other_aliases:
                raise ValueError(f"Recognition hints overlap another local component: {other.name}.")

    def load(self) -> None:
        self.components = []
        if not self.path.is_file():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return
        if not isinstance(raw, dict) or raw.get("schema") != LOCAL_CATALOG_SCHEMA or raw.get("scope") != "developer-only":
            return
        entries = raw.get("components")
        if not isinstance(entries, list):
            return
        accepted: list[LocalDeveloperComponent] = []
        for item in entries:
            if not isinstance(item, dict):
                continue
            component = LocalDeveloperComponent(
                component_id=str(item.get("id") or "").strip().casefold(),
                name=str(item.get("name") or "").strip(),
                identity_hints=tuple(str(value).strip() for value in item.get("identity_hints", []) if str(value).strip()),
            )
            try:
                self.validate_component(component, existing=accepted)
            except ValueError:
                continue
            accepted.append(component)
        self.components = accepted

    def save_components(self, components: list[LocalDeveloperComponent]) -> None:
        clean: list[LocalDeveloperComponent] = []
        seen: set[str] = set()
        for component in components:
            cid = component.component_id.strip().casefold()
            if cid in seen:
                raise ValueError(f"Duplicate local component ID: {cid}")
            normalized = LocalDeveloperComponent(cid, component.name.strip(), tuple(dict.fromkeys(h.strip() for h in component.identity_hints if h.strip())))
            self.validate_component(normalized, existing=clean)
            clean.append(normalized)
            seen.add(cid)
        payload = {
            "schema": LOCAL_CATALOG_SCHEMA,
            "scope": "developer-only",
            "components": [
                {"id": item.component_id, "name": item.name, "identity_hints": list(item.identity_hints)}
                for item in clean
            ],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with NamedTemporaryFile("w", encoding="utf-8", dir=self.path.parent, prefix=f".{self.path.name}.", suffix=".tmp", delete=False) as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
                temporary = Path(handle.name)
            temporary.replace(self.path)
            self.components = clean
        finally:
            if temporary is not None and temporary.exists():
                try:
                    temporary.unlink()
                except OSError:
                    pass

    def identity_for_zip(self, zip_path: Path) -> DeveloperIdentity | None:
        stem_slug = slugify(zip_path.stem)
        try:
            with zipfile.ZipFile(zip_path) as archive:
                member_hints = set()
                for info in archive.infolist()[:2000]:
                    pure = PurePosixPath(info.filename.replace("\\", "/"))
                    if pure.parts:
                        member_hints.add(slugify(pure.parts[0]))
                        if len(pure.parts) > 1:
                            member_hints.add(slugify(pure.parts[1]))
        except (OSError, zipfile.BadZipFile):
            return None
        hints = {stem_slug, *member_hints}
        matches: list[tuple[int, LocalDeveloperComponent]] = []
        for component in self.components:
            aliases = {slugify(component.name), slugify(component.component_id[len(LOCAL_ID_PREFIX):])}
            aliases.update(slugify(value) for value in component.identity_hints)
            aliases.discard("")
            score = 0
            for alias in aliases:
                for hint in hints:
                    if hint == alias:
                        score = max(score, 1000 + len(alias))
                    elif hint.startswith(alias + "-"):
                        score = max(score, 500 + len(alias))
            if score:
                matches.append((score, component))
        if not matches:
            return None
        matches.sort(key=lambda item: (item[0], item[1].name.casefold()), reverse=True)
        best = matches[0]
        if len(matches) > 1 and matches[1][0] == best[0]:
            return None
        return DeveloperIdentity(best[1].component_id, best[1].name, False)


def safe_relative_path(value: str, *, label: str) -> Path:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{label} cannot be empty.")
    path = Path(text)
    if path.is_absolute() or any(part == ".." for part in path.parts):
        raise ValueError(f"{label} must be a safe relative path below the development folder.")
    return path


def optional_relative_path(value: str, *, label: str) -> Path | None:
    """Return a validated relative layout path, or None for a flat root layout."""
    text = str(value).strip()
    if not text:
        return None
    return safe_relative_path(text, label=label)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_symlink_info(info: zipfile.ZipInfo) -> bool:
    unix_mode = (info.external_attr >> 16) & 0xFFFF
    return (unix_mode & 0o170000) == 0o120000


def safe_extract_zip(
    zip_path: Path, destination: Path, *, protected_paths: tuple[Path, ...] = (),
    refuse_existing: bool = False,
) -> int:
    destination = destination.expanduser().resolve(strict=False)
    destination.mkdir(parents=True, exist_ok=True)
    protected = {path.expanduser().resolve(strict=False) for path in protected_paths}
    count = 0
    with zipfile.ZipFile(zip_path) as archive:
        infos = archive.infolist()
        for info in infos:
            pure = PurePosixPath(info.filename.replace("\\", "/"))
            if not pure.parts or pure.is_absolute() or ".." in pure.parts or _is_symlink_info(info):
                raise InstallError(f"Developer Intake refused unsafe ZIP entry: {info.filename}")
            target = destination.joinpath(*pure.parts).resolve(strict=False)
            try:
                target.relative_to(destination)
            except ValueError as exc:
                raise InstallError(f"Developer Intake refused ZIP entry outside extraction folder: {info.filename}") from exc
            if target in protected:
                raise InstallError(f"Developer Intake refused to overwrite its stored source ZIP: {info.filename}")
            if refuse_existing and not (info.is_dir() or info.filename.endswith("/")) and target.exists():
                raise InstallError(
                    f"Developer Intake will not overwrite an existing file in the intake/version folder: {target}"
                )
        for info in infos:
            pure = PurePosixPath(info.filename.replace("\\", "/"))
            target = destination.joinpath(*pure.parts)
            if info.is_dir() or info.filename.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
            count += 1
    return count


class LocalComponentEditDialog(QDialog):
    def __init__(self, parent, component: LocalDeveloperComponent | None = None) -> None:
        super().__init__(parent)
        self.original = component
        self.setWindowTitle(app_dialog_title("Local Developer Component"))
        self.setMinimumWidth(500)
        layout = QVBoxLayout(self)
        note = QLabel("Local components are Developer Intake identities only. They can never replace official Suite components or participate in normal install/routing.")
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.name_edit = QLineEdit(component.name if component else "")
        self.id_edit = QLineEdit(component.component_id if component else "")
        self.id_edit.setPlaceholderText("local:my-component")
        if component is not None:
            self.id_edit.setReadOnly(True)
        self.hints_edit = QLineEdit(", ".join(component.identity_hints) if component else "")
        self.hints_edit.setPlaceholderText("My Component, my-component")
        form.addRow("Name:", self.name_edit)
        form.addRow("Local ID:", self.id_edit)
        form.addRow("ZIP recognition hints:", self.hints_edit)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def value(self) -> LocalDeveloperComponent:
        name = self.name_edit.text().strip()
        cid = self.id_edit.text().strip().casefold()
        if not cid and name:
            cid = LOCAL_ID_PREFIX + slugify(name)
        hints = tuple(dict.fromkeys(item.strip() for item in self.hints_edit.text().replace(";", ",").split(",") if item.strip()))
        return LocalDeveloperComponent(cid, name, hints)


class DeveloperSettingsDialog(QDialog):
    def __init__(self, parent, config: DeveloperIntakeConfig, local_catalog: DeveloperComponentCatalog) -> None:
        super().__init__(parent)
        self.config = config
        self.local_catalog = local_catalog
        self.local_components = list(local_catalog.components)
        self.root_edits: dict[str, QLineEdit] = {}
        self.setWindowTitle(app_dialog_title("Developer Intake Configuration"))
        self.setMinimumSize(780, 600)
        self.resize(780, 600)
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs, 1)

        roots_page = QWidget()
        roots_layout = QVBoxLayout(roots_page)
        root_note = QLabel("Saved development roots are managed here only. Empty a field to forget that component's root. Official and local developer identities use the same intake layout but separate per-app destinations.")
        root_note.setWordWrap(True)
        roots_layout.addWidget(root_note)
        self.roots_scroll = QScrollArea()
        self.roots_scroll.setWidgetResizable(True)
        self.roots_scroll.setFrameShape(QFrame.Shape.NoFrame)
        roots_layout.addWidget(self.roots_scroll, 1)
        tabs.addTab(roots_page, "App Roots")

        local_page = QWidget()
        local_layout = QVBoxLayout(local_page)
        local_note = QLabel("Optional local entries let you recognise a brand-new experiment without rebuilding Suite. They are always prefixed local:, are visibly local, and are never added to the trusted Suite catalogue or OS routing.")
        local_note.setWordWrap(True)
        local_layout.addWidget(local_note)
        self.local_table = QTableWidget(0, 3)
        self.local_table.setHorizontalHeaderLabels(["Local ID", "Name", "Recognition hints"])
        self.local_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.local_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.local_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.local_table.horizontalHeader().setStretchLastSection(True)
        self.local_table.doubleClicked.connect(self._edit_local)
        local_layout.addWidget(self.local_table, 1)
        local_actions = QHBoxLayout()
        add_local = QPushButton("Add…")
        add_local.clicked.connect(self._add_local)
        edit_local = QPushButton("Edit…")
        edit_local.clicked.connect(self._edit_local)
        remove_local = QPushButton("Remove")
        remove_local.clicked.connect(self._remove_local)
        local_actions.addWidget(add_local)
        local_actions.addWidget(edit_local)
        local_actions.addWidget(remove_local)
        local_actions.addStretch(1)
        local_layout.addLayout(local_actions)
        tabs.addTab(local_page, "Local Components")

        self._rebuild_local_table()
        self._rebuild_roots()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _all_root_identities(self) -> list[tuple[str, str, bool]]:
        official = [(profile.component_id, profile.name, True) for profile in COMPONENT_PROFILES.values()]
        local = [(item.component_id, item.name, False) for item in self.local_components]
        return sorted([*official, *local], key=lambda item: (item[1].casefold(), item[0]))

    def _rebuild_roots(self) -> None:
        old_values = {cid: edit.text().strip() for cid, edit in self.root_edits.items()}
        body = QWidget()
        form = QFormLayout(body)
        self.root_edits = {}
        for component_id, name, official in self._all_root_identities():
            row = QHBoxLayout()
            saved = old_values.get(component_id)
            if saved is None:
                root = self.config.app_root(component_id)
                saved = str(root) if root else ""
            edit = QLineEdit(saved)
            edit.setPlaceholderText("Not configured")
            browse = QPushButton("Browse…")
            browse.clicked.connect(lambda _checked=False, field=edit, title=name: self._browse_root(field, title))
            row.addWidget(edit, 1)
            row.addWidget(browse)
            suffix = "" if official else "  [LOCAL]"
            form.addRow(name + suffix + ":", row)
            self.root_edits[component_id] = edit
        self.roots_scroll.setWidget(body)

    def _browse_root(self, edit: QLineEdit, name: str) -> None:
        start = edit.text().strip() or str(Path.home())
        path = QFileDialog.getExistingDirectory(self, app_dialog_title(f"Choose {name} Development Root"), start)
        if path:
            edit.setText(path)

    def _rebuild_local_table(self) -> None:
        self.local_table.setRowCount(0)
        for component in sorted(self.local_components, key=lambda item: item.name.casefold()):
            row = self.local_table.rowCount()
            self.local_table.insertRow(row)
            values = (component.component_id, component.name, ", ".join(component.identity_hints))
            for column, value in enumerate(values):
                self.local_table.setItem(row, column, QTableWidgetItem(value))
            self.local_table.item(row, 0).setData(Qt.ItemDataRole.UserRole, component.component_id)
        self._rebuild_roots()

    def _selected_local(self) -> LocalDeveloperComponent | None:
        row = self.local_table.currentRow()
        if row < 0:
            return None
        item = self.local_table.item(row, 0)
        cid = str(item.data(Qt.ItemDataRole.UserRole) or "") if item else ""
        return next((entry for entry in self.local_components if entry.component_id == cid), None)

    def _add_local(self) -> None:
        dialog = LocalComponentEditDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        candidate = dialog.value()
        try:
            DeveloperComponentCatalog.validate_component(candidate, existing=self.local_components)
            if any(item.component_id == candidate.component_id for item in self.local_components):
                raise ValueError("That local component ID already exists.")
        except ValueError as exc:
            QMessageBox.critical(self, app_dialog_title("Invalid Local Component"), str(exc))
            return
        self.local_components.append(candidate)
        self._rebuild_local_table()

    def _edit_local(self, *_args) -> None:
        selected = self._selected_local()
        if selected is None:
            return
        dialog = LocalComponentEditDialog(self, selected)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        candidate = dialog.value()
        others = [item for item in self.local_components if item.component_id != selected.component_id]
        try:
            DeveloperComponentCatalog.validate_component(candidate, existing=others)
        except ValueError as exc:
            QMessageBox.critical(self, app_dialog_title("Invalid Local Component"), str(exc))
            return
        index = self.local_components.index(selected)
        self.local_components[index] = candidate
        self._rebuild_local_table()

    def _remove_local(self) -> None:
        selected = self._selected_local()
        if selected is None:
            return
        self.local_components = [item for item in self.local_components if item.component_id != selected.component_id]
        self.root_edits.pop(selected.component_id, None)
        self._rebuild_local_table()

    def _validate_and_accept(self) -> None:
        try:
            for component in self.local_components:
                DeveloperComponentCatalog.validate_component(component, existing=[item for item in self.local_components if item.component_id != component.component_id])
        except ValueError as exc:
            QMessageBox.critical(self, app_dialog_title("Developer Configuration Error"), str(exc))
            return
        self.accept()

    def apply(self) -> None:
        self.local_catalog.save_components(self.local_components)
        # A removed local entry should not leave an invisible destination behind.
        valid_ids = set(COMPONENT_PROFILES) | {item.component_id for item in self.local_components}
        roots = self.config.data.setdefault("app_roots", {})
        if isinstance(roots, dict):
            for cid in list(roots):
                if cid.startswith(LOCAL_ID_PREFIX) and cid not in valid_ids:
                    roots.pop(cid, None)
        for cid, edit in self.root_edits.items():
            text = edit.text().strip()
            self.config.set_app_root(cid, Path(text) if text else None)
        if not self.config.save():
            raise OSError(f"Could not save Developer Intake settings to {self.config.path}")


class DeveloperIntakeDialog(QDialog):
    def __init__(self, parent, config: DeveloperIntakeConfig, local_catalog: DeveloperComponentCatalog, *, open_path_callback) -> None:
        super().__init__(parent)
        self.config = config
        self.local_catalog = local_catalog
        self.open_path_callback = open_path_callback
        self.prepared: PreparedIntake | None = None
        self.extracted_folder: Path | None = None
        self.install_requested_zip: Path | None = None
        self.session_vault = DeveloperIntakeSessionVault()
        self.setWindowTitle(app_dialog_title("Developer Intake"))
        configure_operation_window(self)
        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        suite_logo = Path(__file__).resolve().parent.parent / "assets" / "suite-pythoine-128.png"
        apply_operation_icon(self, suite_logo, 128)
        layout.addWidget(operation_branding_header(
            f"{APP_NAME} — Developer Intake", f"Version {__version__} • Developer Mode",
            description=(
                "Prepare a development copy from a source ZIP without entering the paged guided installer. "
                "Choose or drop a source ZIP; Suite validates and previews the intake first, and Action is the filesystem commit point."
            ),
            icon_path=suite_logo,
        ))
        choose_row = QHBoxLayout()
        choose_button = QPushButton("Choose ZIP…")
        choose_button.clicked.connect(self._choose_zip)
        choose_row.addWidget(choose_button)
        configure = QPushButton("Configure…")
        configure.clicked.connect(self._configure)
        choose_row.addWidget(configure)
        choose_row.addStretch(1)
        layout.addLayout(choose_row)

        layout_group = QGroupBox("Intake")
        layout_form = QFormLayout(layout_group)

        mode_row = QHBoxLayout()
        self.extract_radio = QRadioButton("Extract source")
        self.store_only_radio = QRadioButton("Store ZIP only")
        remembered_store_only = bool(self.config.data.get("store_zip_only", False))
        self.store_only_radio.setChecked(remembered_store_only)
        self.extract_radio.setChecked(not remembered_store_only)
        self.extract_radio.toggled.connect(self._sync_intake_mode_controls)
        self.store_only_radio.toggled.connect(self._sync_intake_mode_controls)
        mode_row.addWidget(self.extract_radio)
        mode_row.addWidget(self.store_only_radio)
        mode_row.addStretch(1)
        layout_form.addRow("Action:", mode_row)

        self.delete_original_box = QCheckBox("Delete original ZIP after successful intake")
        self.delete_original_box.setChecked(bool(config.data.get("delete_original_after_success", False)))
        self.delete_box = QCheckBox("Delete development ZIP after successful extraction")
        self.delete_box.setChecked(bool(config.data.get("delete_zip_after_success", False)))
        layout_form.addRow("", self.delete_original_box)
        layout_form.addRow("", self.delete_box)

        source_value = self.config.data.get("source_relative", DEFAULT_SOURCE_RELATIVE)
        notes_value = self.config.data.get("notes_relative", DEFAULT_NOTES_RELATIVE)
        self.source_edit = QLineEdit(str(source_value) if isinstance(source_value, str) else DEFAULT_SOURCE_RELATIVE)
        self.source_edit.setPlaceholderText("Blank = intake/version folder")
        self.source_edit.textChanged.connect(self._sync_intake_mode_controls)
        self.notes_edit = QLineEdit(str(notes_value) if isinstance(notes_value, str) else DEFAULT_NOTES_RELATIVE)
        self.notes_edit.setPlaceholderText("Blank = intake/version folder")
        layout_form.addRow("Source folder:", self.source_edit)
        layout_form.addRow("Notes folder:", self.notes_edit)
        layout.addWidget(layout_group)

        notes_row = QHBoxLayout()
        notes_label = QLabel("Notes file:")
        notes_font = notes_label.font(); notes_font.setBold(True); notes_label.setFont(notes_font)
        notes_row.addWidget(notes_label)
        saved_readme = self.config.data.get("readme_filename", DEFAULT_README_FILENAME)
        self.readme_filename_edit = QLineEdit(str(saved_readme) if isinstance(saved_readme, str) else DEFAULT_README_FILENAME)
        self.readme_filename_edit.setPlaceholderText(DEFAULT_README_FILENAME)
        self.readme_filename_edit.setMaximumWidth(300)
        self.readme_filename_edit.setToolTip("Filename only. Blank uses README.md. No file is written when the text area is empty.")
        notes_row.addWidget(self.readme_filename_edit)
        notes_row.addStretch(1)
        paste_button = QPushButton("Paste")
        paste_button.setToolTip("Paste clipboard text into the notes field.")
        paste_button.clicked.connect(self._paste_notes)
        notes_row.addWidget(paste_button)
        self.action_button = QPushButton("Action")
        self.action_button.setEnabled(False)
        self.action_button.clicked.connect(self._action)
        notes_row.addWidget(self.action_button)
        layout.addLayout(notes_row)
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText("Paste or write notes / release-note content here…")
        layout.addWidget(self.notes, 1)

        self.info_group = QGroupBox("Intake Summary")
        summary_grid = QGridLayout(self.info_group)
        summary_grid.setColumnStretch(1, 1)
        summary_grid.setHorizontalSpacing(8)
        summary_grid.setVerticalSpacing(5)

        def summary_value() -> QLabel:
            value = QLabel("—")
            value.setTextFormat(Qt.TextFormat.PlainText)
            value.setWordWrap(True)
            value.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            value.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            value.setMinimumWidth(0)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            return value

        def add_summary_row(row: int, label_text: str, value: QLabel) -> None:
            label = QLabel(label_text)
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
            summary_grid.addWidget(label, row, 0, alignment=Qt.AlignmentFlag.AlignTop)
            summary_grid.addWidget(value, row, 1, alignment=Qt.AlignmentFlag.AlignTop)

        self.destination_label = summary_value()
        self.zip_label = summary_value()
        self.original_zip_label = summary_value()
        self.notes_status_label = summary_value()
        add_summary_row(0, "Version folder:", self.destination_label)
        add_summary_row(1, "Development ZIP:", self.zip_label)
        add_summary_row(2, "Original ZIP:", self.original_zip_label)
        add_summary_row(3, "Notes:", self.notes_status_label)
        layout.addWidget(self.info_group)

        self.status_label = QLabel("Choose or drop a ZIP to begin.")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        actions = QHBoxLayout()
        self.reset_button = QPushButton("Clear / Reset")
        self.reset_button.clicked.connect(self.reset)
        self.open_button = QPushButton("Open Version Folder")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self._open_result_folder)
        self.install_button = QPushButton("Install Stored ZIP…")
        self.install_button.setEnabled(False)
        self.install_button.setToolTip("Open Suite Pythoine's normal guided installer using the exact ZIP stored in this development environment.")
        self.install_button.clicked.connect(self._request_install_stored)
        actions.addWidget(self.reset_button)
        actions.addStretch(1)
        actions.addWidget(self.open_button)
        actions.addWidget(self.install_button)
        layout.addLayout(actions)
        self._layout_locked = False
        # Keep the pre-Action Intake Summary truthful as the user adjusts the
        # current intake. Action/delete choices are also remembered after a
        # successful commit via _save_layout_preferences().
        self.notes_edit.textChanged.connect(self._refresh_prepared_preview)
        self.readme_filename_edit.textChanged.connect(self._refresh_prepared_preview)
        self.delete_original_box.toggled.connect(self._refresh_prepared_preview)
        self.delete_box.toggled.connect(self._refresh_prepared_preview)
        self.notes.textChanged.connect(self._refresh_prepared_preview)
        self._sync_intake_mode_controls()

    def _paste_notes(self) -> None:
        self.notes.setFocus()
        self.notes.paste()

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)
        parent = self.parent()
        if parent is not None and hasattr(parent, "_status"):
            try:
                parent._status(text)
            except Exception:
                pass

    def _set_layout_locked(self, locked: bool) -> None:
        self._layout_locked = bool(locked)
        for widget in (
            self.source_edit, self.notes_edit, self.readme_filename_edit, self.extract_radio, self.store_only_radio,
            self.delete_original_box, self.delete_box,
        ):
            widget.setEnabled(not locked)
        if not locked:
            self._sync_intake_mode_controls()

    def _sync_intake_mode_controls(self) -> None:
        if getattr(self, "_layout_locked", False):
            return
        extraction = self.extract_radio.isChecked()
        self.delete_original_box.setEnabled(True)
        self.delete_box.setVisible(extraction)
        self.delete_box.setEnabled(extraction)
        self.delete_original_box.setToolTip("The original source ZIP is deleted only after the selected intake action succeeds.")
        self.delete_box.setToolTip("Applies only to the copied ZIP inside the development environment, after successful extraction.")
        self._refresh_prepared_preview()

    def _layout_preferences(self) -> tuple[str, str, Path | None, Path | None]:
        source_text = self.source_edit.text().strip()
        notes_text = self.notes_edit.text().strip()
        source_relative = optional_relative_path(source_text, label="Source folder")
        notes_relative = optional_relative_path(notes_text, label="Notes folder")
        return source_text, notes_text, source_relative, notes_relative

    def _readme_filename(self) -> str:
        text = self.readme_filename_edit.text().strip() or DEFAULT_README_FILENAME
        if text in {".", ".."} or "/" in text or "\\" in text or "\x00" in text:
            raise ValueError("Notes filename must be a filename only, not a path.")
        return text

    def _save_layout_preferences(self, source_text: str, notes_text: str) -> None:
        self.config.data["source_relative"] = source_text
        self.config.data["notes_relative"] = notes_text
        self.config.data["delete_zip_after_success"] = self.delete_box.isChecked()
        self.config.data["delete_original_after_success"] = self.delete_original_box.isChecked()
        self.config.data["store_zip_only"] = self.store_only_radio.isChecked()
        self.config.data["readme_filename"] = self._readme_filename()
        if not self.config.save():
            raise OSError(f"Could not save Developer Intake settings to {self.config.path}")

    def _choose_zip(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self, app_dialog_title("Developer Intake — Select Source ZIP"),
            str(Path.home()), "Source ZIP archives (*.zip)",
        )
        if selected:
            self.load_zip(Path(selected))

    def _identity_for_zip(self, path: Path) -> DeveloperIdentity:
        try:
            inspection = inspect_editor_zip(path)
            return DeveloperIdentity(inspection.editor_id, inspection.name, True)
        except (InstallError, OSError):
            local = self.local_catalog.identity_for_zip(path)
            if local is not None:
                return local
            raise InstallError(
                "Developer Intake does not recognise this ZIP. Add the experiment under Configure… → Local Components, "
                "or add it to Suite Pythoine's trusted catalogue before using the normal installer."
            )

    def _planned_intake(
        self, path: Path, identity: DeveloperIdentity, root: Path,
    ) -> PreparedIntake:
        source_text, notes_text, source_relative, notes_relative = self._layout_preferences()
        store_zip_only = self.store_only_radio.isChecked()

        # Every intake is isolated below one mandatory ZIP-derived container.
        # Optional Source/Notes folders only add organisation *inside*
        # that intake/version boundary; blank never means the persistent app root.
        dev_folder = root / path.stem
        source_folder = dev_folder if source_relative is None else dev_folder / source_relative
        notes_folder = dev_folder if notes_relative is None else dev_folder / notes_relative
        stored_zip = source_folder / path.name
        readme_filename = self._readme_filename()
        return PreparedIntake(
            identity=identity,
            incoming_zip=path,
            configured_root=root,
            dev_folder=dev_folder,
            source_folder=source_folder,
            notes_folder=notes_folder,
            stored_zip=stored_zip,
            source_relative=source_text,
            notes_relative=notes_text,
            readme_filename=readme_filename,
            delete_zip_after_success=bool(self.delete_box.isChecked()) and not store_zip_only,
            delete_original_after_success=bool(self.delete_original_box.isChecked()),
            store_zip_only=store_zip_only,
        )

    def _set_preview_summary(self, planned: PreparedIntake) -> None:
        action = "Store ZIP only" if planned.store_zip_only else "Extract source"
        local_suffix = " [LOCAL]" if not planned.identity.official else ""
        self.info_group.setTitle(f"Intake Summary — {planned.identity.name}{local_suffix} ({action})")
        self.destination_label.setText(str(planned.dev_folder))
        if planned.delete_zip_after_success:
            self.zip_label.setText(f"Delete after extraction — {planned.stored_zip}")
        else:
            self.zip_label.setText(f"Planned: {planned.stored_zip}")
        if planned.delete_original_after_success:
            self.original_zip_label.setText(f"Delete after intake — {planned.incoming_zip}")
        else:
            self.original_zip_label.setText(str(planned.incoming_zip))
        self.notes_status_label.setText(
            "Not written" if not self.notes.toPlainText().strip()
            else f"Planned: {planned.notes_folder / planned.readme_filename}"
        )
        self.open_button.setText("Open Version Folder")

    def _refresh_prepared_preview(self) -> None:
        prepared = self.prepared
        if prepared is None or getattr(self, "_layout_locked", False):
            return
        try:
            planned = self._planned_intake(prepared.incoming_zip, prepared.identity, prepared.configured_root)
        except ValueError:
            return
        self.prepared = planned
        self._set_preview_summary(planned)

    def load_zip(self, zip_path: Path) -> bool:
        path = zip_path.expanduser().resolve(strict=False)
        try:
            if path.suffix.casefold() != ".zip" or not path.is_file():
                raise InstallError("Developer Intake accepts source ZIP archives only.")
            validate_zip(path)
            identity = self._identity_for_zip(path)
            # Validate layout now, but do not persist it or touch the development
            # filesystem. Action is the sole filesystem commit point.
            self._layout_preferences()

            root = self.config.app_root(identity.component_id)
            if root is None:
                selected = QFileDialog.getExistingDirectory(
                    self, app_dialog_title(f"Choose {identity.name} Development Root"), str(Path.home())
                )
                if not selected:
                    self._set_status(f"No development root selected for {identity.name}.")
                    return False
                root = Path(selected).expanduser().resolve(strict=False)
                self.config.set_app_root(identity.component_id, root)
                if not self.config.save():
                    raise OSError(f"Could not remember the development root in {self.config.path}")

            planned = self._planned_intake(path, identity, root)
            self.session_vault.cleanup()
            self.prepared = planned
            self.extracted_folder = None
            self.install_requested_zip = None
            self.notes.clear()
            self._set_preview_summary(planned)
            self.action_button.setEnabled(True)
            self.open_button.setEnabled(False)
            self.open_button.setText("Open Version Folder")
            # A stored development copy does not exist until Action succeeds.
            self.install_button.setEnabled(False)
            if not identity.official:
                self.install_button.setToolTip("LOCAL Developer Intake identities cannot enter Suite's normal trusted installer.")
            else:
                self.install_button.setToolTip("Available after Action stores the validated ZIP in the development environment.")
            self._set_layout_locked(False)
            mode = "store the ZIP without extraction" if planned.store_zip_only else "extract the source"
            self._set_status(
                f"Ready for {identity.name} — Action will {mode}. No development files have been copied or extracted yet."
            )
            return True
        except (InstallError, OSError, ValueError, zipfile.BadZipFile) as exc:
            QMessageBox.critical(self, app_dialog_title("Developer Intake Error"), str(exc))
            self._set_status("Developer Intake could not prepare the source ZIP.")
            return False

    def reset(self) -> None:
        self.session_vault.cleanup()
        self.prepared = None
        self.extracted_folder = None
        self.install_requested_zip = None
        self.info_group.setTitle("Intake Summary")
        self.destination_label.setText("—")
        self.zip_label.setText("—")
        self.original_zip_label.setText("—")
        self.notes_status_label.setText("—")
        self.notes.clear()
        self.action_button.setEnabled(False)
        self.install_button.setEnabled(False)
        self.open_button.setEnabled(False)
        self.open_button.setText("Open Version Folder")
        self._set_layout_locked(False)
        self._set_status("Choose or drop a ZIP to begin.")

    def cleanup_session_vault(self) -> None:
        """Discard any private Intake-session ZIP retained for later install."""
        self.session_vault.cleanup()

    def _configure(self) -> None:
        dialog = DeveloperSettingsDialog(self, self.config, self.local_catalog)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            dialog.apply()
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, app_dialog_title("Developer Configuration Error"), str(exc))
            return
        self.local_catalog.load()
        if self.prepared is not None:
            self._set_status("Developer settings saved. The current prepared intake keeps its existing root and layout.")
        else:
            self._set_status("Developer settings saved.")

    def _write_release_notes(self, prepared: PreparedIntake) -> Path | None:
        text = self.notes.toPlainText()
        if not text.strip():
            return None
        prepared.notes_folder.mkdir(parents=True, exist_ok=True)
        readme = prepared.notes_folder / prepared.readme_filename
        readme.write_text(text, encoding="utf-8")
        return readme

    def _action(self) -> None:
        preview = self.prepared
        if preview is None:
            return
        try:
            # Revalidate immediately before committing. The selected ZIP may have
            # changed since preview, and layout/mode remain editable until Action.
            if not preview.incoming_zip.is_file():
                raise InstallError("The original source ZIP is no longer available.")
            validate_zip(preview.incoming_zip)
            identity_now = self._identity_for_zip(preview.incoming_zip)
            if identity_now.component_id != preview.identity.component_id:
                raise InstallError("The source ZIP identity changed after it was selected. Clear and choose it again.")

            source_text, notes_text, _source_relative, _notes_relative = self._layout_preferences()
            self._save_layout_preferences(source_text, notes_text)
            prepared = self._planned_intake(preview.incoming_zip, preview.identity, preview.configured_root)
            self.prepared = prepared
            action = "Store ZIP only" if prepared.store_zip_only else "Extract source"
            local_suffix = " [LOCAL]" if not prepared.identity.official else ""
            self.info_group.setTitle(f"Intake Summary — {prepared.identity.name}{local_suffix} ({action})")
            self.destination_label.setText(str(prepared.dev_folder))
            self.zip_label.setText(str(prepared.stored_zip))
            self.original_zip_label.setText(str(prepared.incoming_zip))

            prepared.configured_root.mkdir(parents=True, exist_ok=True)
            if not prepared.configured_root.is_dir():
                raise OSError(f"Development root is not a folder: {prepared.configured_root}")
            prepared.source_folder.mkdir(parents=True, exist_ok=True)

            incoming = prepared.incoming_zip.resolve(strict=False)
            stored = prepared.stored_zip.resolve(strict=False)
            if stored.exists():
                if not stored.is_file() or file_sha256(stored) != file_sha256(incoming):
                    raise InstallError(f"A different source ZIP already exists at {stored}")
            elif stored != incoming:
                shutil.copy2(incoming, stored)
            if not stored.is_file():
                raise InstallError("Developer Intake could not create the stored development ZIP.")

            # Extract mode may delete the development ZIP. Preserve one private,
            # exact, SHA-256-verified copy first so normal guided installation
            # remains possible for the rest of this Intake session. This is not
            # Recovery storage and never appears in the development tree.
            self.session_vault.cleanup()
            if prepared.delete_zip_after_success:
                self.session_vault.stage_exact_copy(stored)

            notes_target = prepared.notes_folder / prepared.readme_filename
            has_release_notes = bool(self.notes.toPlainText().strip())
            if has_release_notes and notes_target.exists():
                raise InstallError(
                    f"Developer Intake will not overwrite an existing notes file: {notes_target}. "
                    "Choose another filename/folder or move the existing file first."
                )

            if prepared.store_zip_only:
                readme = self._write_release_notes(prepared)
                original_note = ""
                if prepared.delete_original_after_success:
                    if incoming == stored:
                        original_note = " Original ZIP retained because it is already the stored development copy."
                    elif incoming.exists():
                        incoming.unlink()
                        original_note = " Original ZIP deleted after successful intake."
                self.extracted_folder = prepared.dev_folder
                self.action_button.setEnabled(False)
                self.open_button.setText("Open Version Folder")
                self.open_button.setEnabled(True)
                self.install_button.setEnabled(prepared.identity.official and stored.is_file())
                if self.install_button.isEnabled():
                    self.install_button.setToolTip("Open Suite Pythoine's normal guided installer using the exact ZIP stored in this development environment.")
                self._set_layout_locked(True)
                self.zip_label.setText(str(stored) if stored.is_file() else "Not retained")
                self.original_zip_label.setText("Deleted after intake" if prepared.delete_original_after_success and incoming != stored and not incoming.exists() else str(incoming))
                self.notes_status_label.setText(str(readme) if readme is not None else "Not written")
                notes_note = f" Notes saved to {readme}." if readme is not None else " No notes were written."
                self._set_status(f"Done — source ZIP retained without extraction.{notes_note}{original_note}")
                return

            extraction = prepared.source_folder
            protected_items = [stored]
            if has_release_notes and notes_target.parent == extraction:
                protected_items.append(notes_target)
            count = safe_extract_zip(
                stored, extraction,
                protected_paths=tuple(protected_items), refuse_existing=True,
            )
            readme = self._write_release_notes(prepared)

            dev_zip_deleted = False
            if prepared.delete_zip_after_success and stored.exists():
                stored.unlink()
                dev_zip_deleted = True

            original_deleted = False
            original_note = ""
            if prepared.delete_original_after_success:
                if incoming == stored:
                    if dev_zip_deleted:
                        original_deleted = True
                    else:
                        original_note = " Original ZIP retained because it is also the retained development ZIP."
                elif incoming.exists():
                    incoming.unlink()
                    original_deleted = True

            self.extracted_folder = prepared.dev_folder
            self.action_button.setEnabled(False)
            self.open_button.setText("Open Version Folder")
            self.open_button.setEnabled(True)
            install_source = stored if stored.is_file() else self.session_vault.archive_path
            self.install_button.setEnabled(prepared.identity.official and install_source is not None)
            if self.install_button.isEnabled():
                if stored.is_file():
                    self.install_button.setToolTip("Open Suite Pythoine's normal guided installer using the exact ZIP stored in this development environment.")
                else:
                    self.install_button.setToolTip("Open Suite Pythoine's normal guided installer using the exact validated ZIP retained privately for this Intake session.")
            self._set_layout_locked(True)
            zip_note = " Development ZIP deleted after extraction." if dev_zip_deleted else " Development ZIP retained."
            if original_deleted:
                original_note = " Original ZIP deleted after successful intake."
            self.zip_label.setText("Deleted after extraction" if dev_zip_deleted else str(stored))
            self.original_zip_label.setText("Deleted after intake" if original_deleted else str(incoming))
            self.notes_status_label.setText(str(readme) if readme is not None else "Not written")
            notes_note = f" Notes saved to {readme}." if readme is not None else " No notes were written."
            self._set_status(
                f"Done — extracted {count} file{'s' if count != 1 else ''}.{notes_note}{zip_note}{original_note}"
            )
        except (InstallError, OSError, ValueError, zipfile.BadZipFile) as exc:
            self.session_vault.cleanup()
            QMessageBox.critical(self, app_dialog_title("Developer Intake Failed"), str(exc))
            self._set_status("Developer Intake Action failed; the original ZIP was retained whenever possible.")

    def _request_install_stored(self) -> None:
        prepared = self.prepared
        if prepared is None or not prepared.identity.official:
            return
        install_source = prepared.stored_zip if prepared.stored_zip.is_file() else self.session_vault.archive_path
        if install_source is None or not install_source.is_file():
            QMessageBox.critical(
                self, app_dialog_title("Install Stored ZIP"),
                "No exact source ZIP remains available for this Intake session."
            )
            self.install_button.setEnabled(False)
            return
        self.install_requested_zip = install_source.resolve(strict=False)
        self.accept()

    def _open_result_folder(self) -> None:
        prepared = self.prepared
        target = prepared.dev_folder if prepared is not None else self.extracted_folder
        if target is None:
            return
        try:
            result = self.open_path_callback(target)
        except Exception as exc:
            QMessageBox.critical(self, app_dialog_title("Open Folder Failed"), str(exc))
            return
        if result is False:
            return

    def dragEnterEvent(self, event) -> None:
        urls = event.mimeData().urls() if event.mimeData() else []
        if len(urls) == 1 and urls[0].isLocalFile() and Path(urls[0].toLocalFile()).suffix.casefold() == ".zip":
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        urls = event.mimeData().urls() if event.mimeData() else []
        if len(urls) == 1 and urls[0].isLocalFile():
            if self.load_zip(Path(urls[0].toLocalFile())):
                event.acceptProposedAction()
                return
        event.ignore()
