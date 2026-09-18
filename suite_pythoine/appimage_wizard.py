from __future__ import annotations

from pathlib import Path
import shutil
from typing import Callable

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWizard,
    QWizardPage,
    QWidget,
)

from . import __version__
from .appimage_inspection import AppImageInspection
from .config import ConfigService
from .installer import (
    InstallError,
    install_appimage,
    install_icon,
    uninstall_registered_appimage_integration,
    synchronize_desktop_integration,
)
from .managed_registry import get_managed_versions, remove_managed_version
from .registry import EditorEntry, EditorVersionInfo
from .storage_layout import appimage_root, is_within, prune_empty_parents, version_root
from .ui_titles import app_dialog_title
from .version_management import classify_install, versions_to_remove
from .versioning import compare_versions, version_sort_key


RegisterCallback = Callable[..., tuple[dict, Path]]
RefreshDesktopCallback = Callable[[Path], None]
FinishedCallback = Callable[[], None]


class AppImagePage(QWizardPage):
    def __init__(self, inspection: AppImageInspection, title: str, subtitle: str = "", icon_path: Path | None = None) -> None:
        super().__init__()
        self.inspection = inspection
        self.icon_path = icon_path
        self.setTitle(title)
        self.setSubTitle(subtitle)

    def branding_header(self) -> QFrame:
        frame = QFrame()
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 8)
        if self.icon_path is not None and self.icon_path.is_file():
            icon = QLabel()
            icon.setPixmap(QIcon(str(self.icon_path)).pixmap(88, 88))
            icon.setFixedSize(96, 96)
            icon.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        text = QVBoxLayout()
        name = QLabel(self.inspection.name)
        font = name.font(); font.setBold(True); font.setPointSize(max(font.pointSize() + 4, 15)); name.setFont(font)
        text.addWidget(name)
        text.addWidget(QLabel(f"Version {self.inspection.version}"))
        if self.inspection.description:
            description = QLabel(self.inspection.description); description.setWordWrap(True); description.setTextFormat(Qt.TextFormat.PlainText)
            text.addWidget(description)
        text.addStretch(1)
        layout.addLayout(text, 1)
        return frame


class AppImageWelcomePage(AppImagePage):
    def __init__(self, inspection: AppImageInspection, icon_path: Path | None) -> None:
        super().__init__(inspection, f"Install {inspection.name} AppImage", "Suite Pythoine has inspected this AppImage without launching the editor.", icon_path)
        layout = QVBoxLayout(self)
        layout.addWidget(self.branding_header())
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        artifact = _plain_label(inspection.appimage_path.name, wrap=False); artifact.setToolTip(str(inspection.appimage_path))
        form.addRow("AppImage:", artifact)
        form.addRow("Editor ID:", _plain_label(inspection.publisher_id, wrap=False))
        form.addRow("Application:", _plain_label(inspection.name, wrap=False))
        form.addRow("Version:", _plain_label(inspection.version, wrap=False))
        form.addRow("Architecture:", _plain_label(inspection.architecture, wrap=False))
        form.addRow("Supported formats:", _plain_label(", ".join(inspection.extensions) or "Not declared", wrap=True))
        form.addRow("SHA-256:", _plain_label(inspection.appimage_sha256, wrap=True))
        layout.addLayout(form)
        note = QLabel(
            "The AppImage is copied into Suite Pythoine's managed version folder. It is never treated as a document to open. "
            "If this version becomes Active, Suite updates the single desktop launcher to point to it."
        )
        note.setWordWrap(True); layout.addWidget(note); layout.addStretch(1)


def _scrollable_page_layout(page: QWizardPage) -> QVBoxLayout:
    outer = QVBoxLayout(page)
    outer.setContentsMargins(0, 0, 0, 0)
    scroll = QScrollArea(page)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    body = QWidget()
    layout = QVBoxLayout(body)
    layout.setContentsMargins(8, 6, 8, 6)
    layout.setSpacing(10)
    scroll.setWidget(body)
    outer.addWidget(scroll)
    page._suite_scroll = scroll
    return layout


class AppImageOptionsPage(AppImagePage):
    def __init__(self, inspection: AppImageInspection, existing_editor: EditorEntry | None, destination: Path, icon_path: Path | None) -> None:
        super().__init__(inspection, "AppImage installation options", "Choose how this already-built AppImage should join the managed editor inventory.", icon_path)
        self.existing_editor = existing_editor
        self.destination = destination
        layout = _scrollable_page_layout(self); layout.addWidget(self.branding_header())
        components = QGroupBox("Components"); box = QVBoxLayout(components)
        managed = QCheckBox("Copy this AppImage into the managed Components folder"); managed.setChecked(True); managed.setEnabled(False); box.addWidget(managed)
        self.make_active = QCheckBox("Make this version active and update its application-menu launcher"); self.make_active.setChecked(True); box.addWidget(self.make_active)
        self.delete_original = QCheckBox("Delete the original AppImage after successful installation"); self.delete_original.setChecked(False); box.addWidget(self.delete_original)
        layout.addWidget(components)

        self.operation_group = QButtonGroup(self); self.operation_radios: dict[str, QRadioButton] = {}
        if existing_editor is not None and existing_editor.versions:
            version_group = QGroupBox("Version management"); version_box = QVBoxLayout(version_group)
            active = existing_editor.active_version
            context_group = QWidget()
            context_form = QFormLayout(context_group)
            context_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            context_form.addRow("Currently available:", _plain_label(', '.join(item.version for item in existing_editor.versions)))
            context_form.addRow("Active version:", _plain_label(active or 'Unknown'))
            context_form.addRow("Incoming AppImage:", _plain_label(inspection.version))
            version_box.addWidget(context_group)
            decision = classify_install(inspection.version, active, [item.version for item in existing_editor.versions])
            relation = compare_versions(inspection.version, active)

            def add_mode(key: str, label: str, checked: bool = False) -> None:
                radio = QRadioButton(label); radio.setChecked(checked); radio.toggled.connect(self._sync_choice)
                self.operation_group.addButton(radio); self.operation_radios[key] = radio; version_box.addWidget(radio)

            if decision.exact_present:
                add_mode("reinstall", f"Reinstall/repair AppImage {inspection.version}", True)
                self.make_active.setChecked(inspection.version == active)
                if inspection.version == active:
                    # Reinstalling the active version must not orphan the existing
                    # single desktop integration by registering it as inactive.
                    self.make_active.setEnabled(False)
            elif relation is not None and relation > 0:
                add_mode("upgrade_remove", "Upgrade and remove older managed versions after this AppImage is verified", True)
                add_mode("upgrade_alongside", "Install alongside older versions")
                self.make_active.setChecked(True); self.make_active.setEnabled(False)
            elif relation is not None and relation < 0:
                add_mode("downgrade_alongside", "Install this older AppImage alongside the current version", True)
                add_mode("downgrade_remove", "Downgrade and remove newer managed versions after verification")
                self.make_active.setChecked(False)
            else:
                add_mode("alongside", "Install alongside existing versions", True)
                self.make_active.setChecked(False)
            version_box.addWidget(self.make_active); layout.addWidget(version_group)

        destination_group = QGroupBox("Destination"); form = QFormLayout(destination_group)
        form.addRow("Managed AppImage folder:", _plain_label(str(destination)))
        layout.addWidget(destination_group); layout.addStretch(1); self._sync_choice()

    @property
    def operation_mode(self) -> str:
        for key, radio in self.operation_radios.items():
            if radio.isChecked(): return key
        return "install"

    @property
    def make_active_after_install(self) -> bool:
        if self.operation_mode in {"install", "upgrade_remove", "downgrade_remove"}:
            return True
        return self.make_active.isChecked()

    def _sync_choice(self) -> None:
        mode = self.operation_mode
        if mode in {"upgrade_remove", "downgrade_remove"}:
            self.make_active.setChecked(True); self.make_active.setEnabled(False)
        elif mode == "upgrade_alongside":
            self.make_active.setChecked(True); self.make_active.setEnabled(True)
        else:
            self.make_active.setEnabled(True)
        self.completeChanged.emit()


class AppImageReviewPage(AppImagePage):
    def __init__(self, inspection: AppImageInspection, options: AppImageOptionsPage, icon_path: Path | None) -> None:
        super().__init__(inspection, "Ready to install AppImage", "Review the operation before Suite Pythoine changes anything.", icon_path)
        self.options = options
        layout = QVBoxLayout(self); layout.addWidget(self.branding_header())
        self.summary = QLabel(); self.summary.setTextFormat(Qt.TextFormat.PlainText); self.summary.setWordWrap(True); self.summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.summary); layout.addStretch(1)

    def initializePage(self) -> None:  # noqa: N802
        labels = {
            "install": "Install as the first managed version",
            "reinstall": "Reinstall/repair this AppImage version",
            "upgrade_remove": "Upgrade and remove older managed versions after verification",
            "upgrade_alongside": "Upgrade and keep older versions available",
            "downgrade_alongside": "Install older version alongside the active version",
            "downgrade_remove": "Downgrade and remove newer managed versions after verification",
            "alongside": "Install alongside existing versions",
        }
        self.summary.setText("\n".join([
            f"Version action: {labels.get(self.options.operation_mode, self.options.operation_mode)}",
            f"Active/Desktop-integrated after install: {'Yes' if self.options.make_active_after_install else 'No'}",
            "",
            f"✓ Verify ELF/AppImage identity and SHA-256",
            f"✓ Copy to {self.options.destination}",
            "✓ Register the exact AppImage path and checksum",
            "✓ Update the application-menu launcher" if self.options.make_active_after_install else "— Preserve current desktop-integrated version",
            "✓ Apply the selected version-management policy",
            "✓ Delete original after success" if self.options.delete_original.isChecked() else "— Keep original AppImage",
        ]))


APPIMAGE_STEPS = (
    ("verify", "Verify AppImage"),
    ("copy", "Install managed AppImage"),
    ("icon", "Install application icon"),
    ("desktop", "Create application-menu launcher"),
    ("registry", "Register managed installation"),
    ("versions", "Apply version-management policy"),
    ("cleanup", "Finalise installation"),
)


class AppImageProgressPage(AppImagePage):
    def __init__(self, inspection: AppImageInspection, options: AppImageOptionsPage, *, editors_root: Path, config: ConfigService, existing_editor: EditorEntry | None, icon_path: Path | None, register_callback: RegisterCallback, refresh_desktop_callback: RefreshDesktopCallback, finished_callback: FinishedCallback) -> None:
        super().__init__(inspection, f"Installing {inspection.name} AppImage", "The existing binary is adopted into the same managed version system as locally built AppImages.", icon_path)
        self.options=options; self.editors_root=editors_root; self.config=config; self.existing_editor=existing_editor; self.icon_path=icon_path
        self.register_callback=register_callback; self.refresh_desktop_callback=refresh_desktop_callback; self.finished_callback=finished_callback
        self.started=False; self.finished=False; self.succeeded=False; self.error_message=""; self.installed_appimage: Path|None=None
        layout=QVBoxLayout(self); layout.addWidget(self.branding_header())
        self.steps=QListWidget(); self.items={}
        for key,label in APPIMAGE_STEPS:
            item=QListWidgetItem(f"○  {label}"); self.items[key]=item; self.steps.addItem(item)
        layout.addWidget(self.steps,1)
        self.result=QLabel(); self.result.setWordWrap(True); self.result.setTextFormat(Qt.TextFormat.PlainText); layout.addWidget(self.result)

    def initializePage(self) -> None:  # noqa: N802
        wizard=self.wizard()
        if wizard:
            wizard.button(QWizard.WizardButton.BackButton).setEnabled(False); wizard.button(QWizard.WizardButton.CancelButton).setEnabled(False)
        if not self.started:
            self.started=True; QTimer.singleShot(0,self._start)

    def isComplete(self) -> bool:  # noqa: N802
        return self.finished

    def _step(self,key,state,detail=""):
        prefix={"active":"⟳","done":"✓","skip":"—","fail":"✕"}[state]; label=dict(APPIMAGE_STEPS)[key]
        self.items[key].setText(f"{prefix}  {label}" + (f" — {detail}" if detail else "")); self.steps.scrollToItem(self.items[key])

    def _source_icon(self) -> Path | None:
        if self.icon_path is not None and self.icon_path.is_file(): return self.icon_path
        return None

    def _editor_for_registration(self, installed: Path) -> EditorEntry:
        exact: EditorVersionInfo | None = None
        if self.existing_editor is not None:
            exact = next((item for item in self.existing_editor.versions if item.version == self.inspection.version), None)
        root = exact.portable_root if exact and exact.portable_root else installed.parent
        return EditorEntry(
            editor_id=self.inspection.editor_id,
            name=self.inspection.name,
            root=root,
            component_kind=self.inspection.component_kind,
            publisher_id=self.inspection.publisher_id,
            extensions=self.inspection.extensions,
            portable_command=exact.portable_command if exact else None,
            installed_command=(str(installed),),
            launch_mode="installed",
            description=self.inspection.description,
            icon=self._source_icon(),
            source_version=self.inspection.version if exact and exact.portable_root else None,
            installed_version=self.inspection.version,
        )

    def _remove_version_now(self, version: str) -> None:
        records=get_managed_versions(self.config.as_dict(), self.inspection.editor_id); record=records.get(version,{})
        if record and record.get("appimage_path"):
            uninstall_registered_appimage_integration(record, installed_dir=self.editors_root); remove_managed_version(self.config.as_dict(), self.inspection.editor_id, version)
        container=version_root(self.editors_root,self.inspection.name,version)
        if container.exists():
            if container.is_symlink() or not is_within(container,self.editors_root): raise InstallError(f"Refusing to remove unsafe managed version folder: {container}")
            shutil.rmtree(container); prune_empty_parents(container.parent,self.editors_root)

    def _start(self) -> None:
        try:
            self._step("verify","active")
            # Inspection already performed ELF/architecture/hash checks before the wizard opened.
            if not self.inspection.appimage_path.is_file(): raise InstallError("The selected AppImage disappeared before installation began.")
            self._step("verify","done",f"{self.inspection.version} / {self.inspection.architecture}")
            self._step("copy","active")
            installed=install_appimage(self.inspection.appimage_path,self.editors_root,editor_id=self.inspection.editor_id,name=self.inspection.name,version=self.inspection.version,architecture=self.inspection.architecture)
            self.installed_appimage=installed; self._step("copy","done",installed.name)
            editor=self._editor_for_registration(installed)
            self._step("icon","active")
            installed_icon=install_icon(self._source_icon(),self.editors_root,self.inspection.editor_id,name=self.inspection.name,version=self.inspection.version)
            self._step("icon","done",installed_icon.name) if installed_icon else self._step("icon","skip","no portable/source icon available")
            desktop=None
            if self.options.make_active_after_install:
                self._step("desktop","active")
                desktop=synchronize_desktop_integration(editor.name,editor.editor_id,installed,installed_icon,editor.root if editor.root.is_dir() else None)
                self._step("desktop","done",desktop.name)
            else:
                self._step("desktop","skip","existing active desktop integration preserved")
            self._step("registry","active")
            _record, metadata=self.register_callback(editor,installed,desktop,installed_icon,version=self.inspection.version,source_artifact=self.inspection.appimage_path,build_script=None,set_active=self.options.make_active_after_install,desktop_integrated=bool(desktop))
            override=_editor_override(self.config,self.inspection.editor_id)
            if self.options.make_active_after_install:
                # Active version, desktop integration and launch runtime are
                # independent. Adopting/making an AppImage active must not
                # silently overwrite an existing Portable runtime preference.
                override["active_version"] = self.inspection.version
            self._step("registry","done",metadata.name)
            if desktop is not None: self.refresh_desktop_callback(desktop.parent)
            self._step("versions","active")
            existing_versions=[item.version for item in self.existing_editor.versions] if self.existing_editor else []
            remove=list(versions_to_remove(existing_versions,self.inspection.version,self.options.operation_mode)); deferred=[]
            for version in sorted(set(remove),key=version_sort_key):
                if self.inspection.editor_id=="suite-pythoine" and version.casefold()==__version__.casefold(): deferred.append(version); continue
                self._remove_version_now(version)
            if deferred:
                self.config.set("pending_self_cleanup",{"editor_id":"suite-pythoine","target_version":self.inspection.version,"remove_versions":deferred,"editors_root":str(self.editors_root),"application_name":self.inspection.name})
            self._step("versions","done", f"removed {len(remove)-len(deferred)}, deferred {len(deferred)}" if remove else "inventory updated")
            self._step("cleanup","active")
            if self.options.delete_original.isChecked() and self.inspection.appimage_path.resolve(strict=False)!=installed.resolve(strict=False):
                self.inspection.appimage_path.unlink()
            self.config.save(); self._step("cleanup","done"); self.finished=True; self.succeeded=True; self.result.setText(f"{self.inspection.name} {self.inspection.version} AppImage was installed successfully.")
            self.finished_callback(); self._unlock(); self.completeChanged.emit()
        except (InstallError,OSError,shutil.Error,ValueError) as exc:
            active=next((key for key,item in self.items.items() if item.text().startswith("⟳")),"verify"); self._step(active,"fail",str(exc)); self.finished=True; self.error_message=str(exc); self.result.setText(f"Installation stopped: {exc}"); self.finished_callback(); self._unlock(); self.completeChanged.emit()

    def _unlock(self):
        wizard=self.wizard()
        if wizard: wizard.button(QWizard.WizardButton.CancelButton).setEnabled(True)


class AppImageFinishPage(AppImagePage):
    def __init__(self, inspection: AppImageInspection, progress: AppImageProgressPage, icon_path: Path | None) -> None:
        super().__init__(inspection,"AppImage installation complete","",icon_path); self.progress=progress
        layout=QVBoxLayout(self); layout.addWidget(self.branding_header()); self.message=QLabel(); self.message.setWordWrap(True); self.message.setTextFormat(Qt.TextFormat.PlainText); layout.addWidget(self.message)
        self.launch_editor=QCheckBox(f"Launch {inspection.name} when this wizard closes"); layout.addWidget(self.launch_editor); layout.addStretch(1)
    def initializePage(self) -> None:  # noqa: N802
        if self.progress.succeeded:
            self.setTitle(f"{self.inspection.name} AppImage installed"); self.message.setText(f"Managed AppImage:\n{self.progress.installed_appimage}") ; self.launch_editor.setVisible(True)
        else:
            self.setTitle("Installation stopped"); self.message.setText(self.progress.error_message); self.launch_editor.setVisible(False)


class AppImageInstallWizard(QWizard):
    def __init__(self,parent,inspection:AppImageInspection,*,editors_root:Path,config:ConfigService,existing_editor:EditorEntry|None,register_callback:RegisterCallback,refresh_desktop_callback:RefreshDesktopCallback,finished_callback:FinishedCallback) -> None:
        super().__init__(parent); self.inspection=inspection; self.setWindowTitle(app_dialog_title(f"Install {inspection.name} AppImage")); self.setWizardStyle(QWizard.WizardStyle.ModernStyle); self.setMinimumSize(820,640); self.resize(980,800)
        exact=next((item for item in existing_editor.versions if item.version==inspection.version),None) if existing_editor else None
        icon_path=(exact.icon if exact and exact.icon and exact.icon.is_file() else (existing_editor.icon if existing_editor and existing_editor.icon and existing_editor.icon.is_file() else None))
        if icon_path: self.setWindowIcon(QIcon(str(icon_path)))
        destination=appimage_root(editors_root,inspection.name,inspection.version)
        self.welcome=AppImageWelcomePage(inspection,icon_path); self.options=AppImageOptionsPage(inspection,existing_editor,destination,icon_path); self.review=AppImageReviewPage(inspection,self.options,icon_path)
        self.progress=AppImageProgressPage(inspection,self.options,editors_root=editors_root,config=config,existing_editor=existing_editor,icon_path=icon_path,register_callback=register_callback,refresh_desktop_callback=refresh_desktop_callback,finished_callback=finished_callback)
        self.finish=AppImageFinishPage(inspection,self.progress,icon_path)
        for page in (self.welcome,self.options,self.review,self.progress,self.finish): self.addPage(page)
        self.setButtonText(QWizard.WizardButton.NextButton,"Continue"); self.setButtonText(QWizard.WizardButton.FinishButton,"Finish")
    @property
    def launch_after_finish(self) -> bool: return bool(self.progress.succeeded and self.finish.launch_editor.isChecked())


def _editor_override(config: ConfigService, editor_id: str) -> dict:
    overrides=config.get("editor_overrides",{})
    if not isinstance(overrides,dict): overrides={}; config.set("editor_overrides",overrides)
    value=overrides.get(editor_id)
    if not isinstance(value,dict): value={}; overrides[editor_id]=value
    return value


def _plain_label(text: str, *, wrap: bool = True) -> QLabel:
    label=QLabel(str(text)); label.setTextFormat(Qt.TextFormat.PlainText); label.setWordWrap(wrap); label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label
