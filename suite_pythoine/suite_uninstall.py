"""0.9.1: Hub-only, selected-component, and full Suite removal wizard.

The snapshot is derived from live discovery, never a persisted installation
registry. Destructive work is handed to the independent stdlib helper ONLY
when the user confirms and the Hub process has actually exited.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (QApplication, QCheckBox, QDialog, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton,
    QRadioButton, QScrollArea, QVBoxLayout, QWizard, QWizardPage, QWidget)

from .catalogue.component_catalog import profile_for_id
from .installation_state import desktop_selection
from .installer import desktop_applications_dir, desktop_entry_path
from .suite_uninstall_worker import UnsafePlan, _signature, _stat_identity, validate_plan
from .store.store_bridge import control_bridge_path, _bridge_script

HUB_ID = 'suite-pythoine'


def _suite_pixmap(size: int = 96):
    path = Path(__file__).with_name('assets') / 'suite-pythoine-master-1024.png'
    if not path.is_file():
        return None
    pixmap = QPixmap(str(path))
    if pixmap.isNull():
        return None
    return pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)


class SuiteUninstallPage(QWizardPage):
    def branding_header(self):
        frame = QWidget()
        row = QHBoxLayout(frame); row.setContentsMargins(0, 0, 0, 8)
        pixmap = _suite_pixmap(88)
        if pixmap is not None:
            icon = QLabel(); icon.setPixmap(pixmap); icon.setFixedSize(96, 96); icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row.addWidget(icon)
        text = QVBoxLayout()
        name = QLabel('Suite Pythoine'); font = name.font(); font.setBold(True); font.setPointSize(max(font.pointSize() + 4, 15)); name.setFont(font)
        text.addWidget(name); text.addWidget(QLabel('Hub')); text.addStretch(1); row.addLayout(text, 1)
        return frame


def available_components(entries) -> list:
    """Only currently discovered installed components, excluding the Hub."""
    return sorted((entry for entry in entries if entry.editor_id != HUB_ID and entry.versions),
                  key=lambda entry: (entry.component_kind, entry.name.casefold()))


def _existing_version_path(info) -> Path:
    if info.portable_root is not None:
        return info.portable_root.parent.absolute()
    if info.appimage_path is not None:
        return info.appimage_path.parent.parent.absolute()
    if info.recovery_dir is not None:
        return info.recovery_dir.parent.absolute()
    raise UnsafePlan(f'No exact physical version folder for {info.version}')


def _state_report_path() -> Path:
    value = os.environ.get('XDG_STATE_HOME', '')
    root = Path(value) if value and Path(value).is_absolute() else Path.home() / '.local' / 'state'
    return root / 'suite-pythoine' / 'last-uninstall-report.txt'


def build_uninstall_plan(controller, *, mode: str, selected: set[str],
                         remove_hub_preferences: bool, remove_component_preferences: bool) -> dict:
    """Build an exact, reviewed, stat-bound target list from the live inventory."""
    root = controller.editors_root.absolute()
    if not root.is_dir() or root.is_symlink() or not root.is_absolute():
        raise UnsafePlan('The managed Applications root is missing or is a symbolic link.')
    hub = controller.suite_entry
    if hub is None or not hub.versions:
        raise UnsafePlan('No validated managed Hub version exists. An unmanaged source checkout cannot be removed by this wizard.')
    available = {entry.editor_id: entry for entry in available_components(controller.components)}
    if mode == 'hub':
        selected = set()
    elif mode == 'full':
        selected = set(available)
    elif mode != 'selective' or not selected <= set(available):
        raise UnsafePlan('An unrecognised component was selected for removal.')
    ids = [HUB_ID, *sorted(selected)]
    entries = [hub, *(available[name] for name in sorted(selected))]
    targets: list[dict] = []
    desktop_dir = desktop_applications_dir().absolute()
    config_dir = controller.runtime.config_root.absolute()
    # Individual app config paths use profile-controlled subdirectory names.
    config_base = (Path(os.environ['APPDATA']) if os.name == 'nt' and os.environ.get('APPDATA')
                   else Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')) / 'brunonlinespace'
    config_base = config_base.absolute()
    for entry in entries:
        if entry.desktop_issue in {'broken','legacy-launcher','external-target','selection-required'}:
            raise UnsafePlan(f'{entry.name}: repair the existing desktop integration before Suite removal.')
        if not entry.versions:
            raise UnsafePlan(f'{entry.name}: no validated versions were discovered.')
        versions = {item.version: item for item in entry.versions}
        state, _version, _runtime = desktop_selection(entry.editor_id, versions, root)
        if state not in ('missing','ready'):
            raise UnsafePlan(f'{entry.name}: desktop integration is {state}; repair it before removal.')
        for info in entry.versions:
            if info.validation_issue:
                raise UnsafePlan(f'{entry.name} {info.version}: {info.validation_issue}')
            path = _existing_version_path(info)
            if path.parent.parent != root or path.name != info.version or path.parent.is_symlink():
                raise UnsafePlan(f'{entry.name}: unsafe or unexpected exact-version directory: {path}')
            target = _signature(path, 'version')
            target.update(component_id=entry.editor_id, version=info.version)
            targets.append(target)
        if state == 'ready':
            desktop = desktop_entry_path(entry.editor_id).absolute()
            if desktop.parent != desktop_dir:
                raise UnsafePlan(f'Unexpected desktop integration path: {desktop}')
            target = _signature(desktop, 'desktop')
            target['component_id'] = entry.editor_id
            targets.append(target)
        if remove_component_preferences and entry.editor_id != HUB_ID:
            profile = profile_for_id(entry.editor_id)
            subdir = profile.config_subdir if profile else None
            if subdir:
                # A catalogue subdir is a single basename, never a path supplied
                # by discovery or arbitrary user-entered profile data.
                if (Path(subdir).name != subdir or subdir in ('.','..','suite-pythoine')
                        or '/' in subdir or '\\' in subdir):
                    raise UnsafePlan(f'Unsafe configured preferences directory: {subdir}')
                config_folder = config_base / subdir
                if config_folder.exists() or config_folder.is_symlink():
                    target = _signature(config_folder, 'component-preferences')
                    target['component_id'] = entry.editor_id
                    targets.append(target)
    # Retire only exact Desktop IDs from the user's XDG MIME choices, if used.
    # This is a reviewed content-bound update, never deletion of mimeapps.list.
    mimeapps_file = config_base.parent / 'mimeapps.list'
    mimeapps = None
    if mimeapps_file.is_file() or mimeapps_file.is_symlink():
        identifiers = tuple(f'io.github.brunonlinespace.{name}.desktop' for name in ids)
        if any(identifier in mimeapps_file.read_text(encoding='utf-8') for identifier in identifiers):
            mimeapps = _signature(mimeapps_file, 'mimeapps')
    # The Store control bridge is Hub-owned, but belongs outside the managed
    # Applications root. Delete it only when its exact authored content matches.
    bridge = control_bridge_path()
    if bridge is not None and (bridge.exists() or bridge.is_symlink()):
        if (bridge.is_file() and not bridge.is_symlink()
                and bridge.read_text(encoding='utf-8') == _bridge_script()):
            targets.append(_signature(bridge.absolute(), 'bridge'))
    if remove_hub_preferences:
        for file in (controller.runtime.config_path, controller.runtime.developer_intake_config_path,
                     controller.runtime.developer_component_catalog_path):
            file = file.absolute()
            if file.is_file() or file.is_symlink():
                targets.append(_signature(file, 'hub-preferences'))
    plan = {
        'schema': 1, 'mode': mode, 'root': str(root), 'root_identity': _stat_identity(root),
        'root_entries': sorted(child.name for child in root.iterdir()),
        'selected_ids': ids, 'selected_names': [entry.name for entry in entries],
        'targets': targets, 'desktop_dir': str(desktop_dir), 'bridge_dir': str(Path.home() / '.local' / 'bin'), 'config_dir': str(config_dir),
        'component_config_base': str(config_base), 'config_file': str(controller.runtime.config_path.absolute()),
        'mimeapps': mimeapps,
        'remove_hub_preferences': bool(remove_hub_preferences),
        'remove_component_preferences': bool(remove_component_preferences),
        'report_path': str(_state_report_path()),
    }
    validate_plan(plan)
    return plan


class ModePage(SuiteUninstallPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle('Uninstall Suite Pythoine')
        self.setSubTitle('Hub is included in every removal mode. Nothing is deleted while reviewing options.')
        layout = QVBoxLayout(self)
        layout.addWidget(self.branding_header())
        self.hub = QRadioButton('Uninstall Hub Only')
        self.hub.setChecked(True)
        self.selective = QRadioButton('Selective Suite Purge')
        self.full = QRadioButton('Full Suite Purge')
        for button, helptext in (
            (self.hub, 'Remove validated managed Hub versions and integration; preserve all other applications.'),
            (self.selective, 'Remove Hub and individual components selected on the next screen.'),
            (self.full, 'Remove Hub and EVERY validated Suite-managed application, including retained Recovery archives.'),
        ):
            layout.addWidget(button)
            note = QLabel(helptext); note.setWordWrap(True)
            note.setContentsMargins(26, 0, 0, 12)
            layout.addWidget(note)
        layout.addStretch(1)

    def mode(self) -> str:
        return 'full' if self.full.isChecked() else 'selective' if self.selective.isChecked() else 'hub'

    def nextId(self) -> int:  # noqa: N802
        return 1 if self.selective.isChecked() else 2


class ComponentPage(SuiteUninstallPage):
    def __init__(self, controller) -> None:
        super().__init__()
        self.setTitle('Select managed applications')
        self.setSubTitle('Hub is mandatory. Nothing else is selected by default; selection is at whole-component level.')
        layout = QVBoxLayout(self)
        layout.addWidget(self.branding_header())
        layout.addWidget(QLabel('✓ Suite Pythoine — always included'))
        self.filter = QListWidget()
        for kind, caption in (('editor', 'Editors'),('reader','Readers'),('extension','Extensions')):
            members = [entry for entry in available_components(controller.components) if entry.component_kind == kind]
            if not members:
                continue
            header = QListWidgetItem(caption)
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            self.filter.addItem(header)
            for component in members:
                item = QListWidgetItem(f'    {component.name}  ({len(component.versions)} versions)')
                item.setData(Qt.ItemDataRole.UserRole, component.editor_id)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
                self.filter.addItem(item)
        self.filter.itemChanged.connect(lambda _item: self.completeChanged.emit())
        layout.addWidget(self.filter, 1)
        buttons = QHBoxLayout()
        select = QPushButton('Select All'); select.clicked.connect(lambda: self._change_all(Qt.CheckState.Checked))
        clear = QPushButton('Clear'); clear.clicked.connect(lambda: self._change_all(Qt.CheckState.Unchecked))
        buttons.addWidget(select); buttons.addWidget(clear); buttons.addStretch(1)
        layout.addLayout(buttons)
        note = QLabel('No component selected is permitted: that has the same removal scope as Hub Only. Unselected applications and Recovery folders remain untouched.')
        note.setWordWrap(True); layout.addWidget(note)

    def _change_all(self, checked) -> None:
        for index in range(self.filter.count()):
            item = self.filter.item(index)
            if item.data(Qt.ItemDataRole.UserRole):
                item.setCheckState(checked)

    def selected(self) -> set[str]:
        return {self.filter.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.filter.count())
                if self.filter.item(i).data(Qt.ItemDataRole.UserRole) and
                self.filter.item(i).checkState() == Qt.CheckState.Checked}


class OptionsPage(SuiteUninstallPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle('Optional preferences removal')
        self.setSubTitle('Each option is independent and starts unchecked.')
        layout = QVBoxLayout(self)
        layout.addWidget(self.branding_header())
        self.hub_preferences = QCheckBox('Also remove Hub preferences')
        self.app_preferences = QCheckBox('Also remove selected applications’ preferences')
        layout.addWidget(self.hub_preferences)
        hub_note = QLabel('Unchecked keeps the Hub configuration for a future reinstall. Checking removes only identified Hub preference files, never the whole configuration parent directory.')
        hub_note.setWordWrap(True); layout.addWidget(hub_note)
        layout.addWidget(self.app_preferences)
        app_note = QLabel('Only exact trusted configuration folders for the applications being purged are eligible. Other applications and personal documents outside managed installation roots are preserved.')
        app_note.setWordWrap(True); layout.addWidget(app_note)
        layout.addStretch(1)

    def initializePage(self) -> None:  # noqa: N802
        wizard = self.wizard()
        mode = wizard.mode_page.mode()
        has_components = (bool(available_components(wizard.controller.components)) if mode == 'full'
                          else bool(wizard.selected_ids()) if mode == 'selective' else False)
        self.app_preferences.setEnabled(has_components)
        if not has_components:
            self.app_preferences.setChecked(False)


class ReviewPage(SuiteUninstallPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle('Review exact removal targets')
        self.setSubTitle('All paths are derived from the live validated filesystem inventory. No file is removed on this screen.')
        layout = QVBoxLayout(self)
        layout.addWidget(self.branding_header())
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        layout.addWidget(self.details, 1)
        self.status = QLabel(); self.status.setWordWrap(True); layout.addWidget(self.status)

    def initializePage(self) -> None:  # noqa: N802
        wizard = self.wizard()
        wizard.plan = None
        try:
            plan = wizard.make_plan()
            lines = [f'Removal mode: {wizard.mode_page.mode()}',
                     'Always included: Suite Pythoine',
                     'Applications: ' + ', '.join(plan['selected_names']),
                     f'Hub preferences: {"REMOVE" if plan["remove_hub_preferences"] else "PRESERVE"}',
                     f'Selected app preferences: {"REMOVE" if plan["remove_component_preferences"] else "PRESERVE"}',
                     f'Exact validated targets ({len(plan["targets"])}):', '']
            lines += [f'{target["kind"]}: {target["path"]}' for target in plan['targets']]
            selected_folders = {Path(t['path']).parent.name for t in plan['targets'] if t['kind'] == 'version'}
            excluded = sorted(set(plan['root_entries']) - selected_folders)
            if plan.get('mimeapps'):
                lines += [f'MIME associations (remove only selected Desktop IDs): {plan["mimeapps"]["path"]}']
            lines += ['', 'Excluded / preserved Applications-root entries: ' + (', '.join(excluded) if excluded else 'none'),
                      'No other application, unrelated file, unmanaged installation, or parent root is eligible.',
                      'User files stored INSIDE selected managed version trees cannot be distinguished from installed files.',
                      'Any unknown version-root contents or changed/linked path stops the operation.',
                      f'Post-exit completion report: {plan["report_path"]}']
            wizard.plan = plan
            self.details.setPlainText('\n'.join(lines))
            self.status.setText('Every listed item is currently validated. Review carefully before proceeding.')
        except Exception as exc:
            self.details.setPlainText('Uninstall blocked: ' + str(exc))
            self.status.setText('Repair or remove the unsafe item explicitly, then reopen the wizard. No action has been taken.')
        self.completeChanged.emit()

    def isComplete(self) -> bool:  # noqa: N802
        return self.wizard().plan is not None


class ConfirmPage(SuiteUninstallPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle('Confirm Suite uninstallation')
        self.setSubTitle('The independent helper runs only after this Hub process exits.')
        self.setFinalPage(True)
        layout = QVBoxLayout(self)
        layout.addWidget(self.branding_header())
        warning = QLabel('This permanently removes the exact selected managed versions, associated Recovery archives, and verified launchers. Unselected applications remain untouched.')
        warning.setWordWrap(True); layout.addWidget(warning)
        self.confirm = QCheckBox('I understand that the reviewed Suite installation targets will be permanently removed.')
        self.confirm.toggled.connect(lambda _checked: self.completeChanged.emit())
        layout.addWidget(self.confirm)
        self.full_confirm = QCheckBox('I explicitly authorise Full Suite Purge of ALL discovered managed components.')
        self.full_confirm.toggled.connect(lambda _checked: self.completeChanged.emit())
        layout.addWidget(self.full_confirm)
        layout.addStretch(1)

    def initializePage(self) -> None:  # noqa: N802
        self.confirm.setChecked(False); self.full_confirm.setChecked(False)
        self.full_confirm.setVisible(self.wizard().mode_page.mode() == 'full')
        self.completeChanged.emit()

    def isComplete(self) -> bool:  # noqa: N802
        return self.confirm.isChecked() and (self.wizard().mode_page.mode() != 'full' or self.full_confirm.isChecked())


class SuiteUninstallWizard(QWizard):
    def __init__(self, controller) -> None:
        super().__init__(controller)
        self.controller = controller
        self.plan = None
        self.handoff_ready = False
        self.setWindowTitle('Uninstall Suite Pythoine')
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setMinimumSize(820, 640)
        self.resize(980, 800)
        pixmap = _suite_pixmap(128)
        if pixmap is not None:
            self.setWindowIcon(QIcon(pixmap))
            self.setPixmap(QWizard.WizardPixmap.LogoPixmap, pixmap)
        self.mode_page = ModePage(); self.component_page = ComponentPage(controller)
        self.options_page = OptionsPage(); self.review_page = ReviewPage(); self.confirm_page = ConfirmPage()
        for index, page in enumerate((self.mode_page,self.component_page,self.options_page,self.review_page,self.confirm_page)):
            self.setPage(index, page)
        self.setStartId(0)
        self.setButtonText(QWizard.WizardButton.FinishButton, 'Uninstall Suite…')

    def selected_ids(self) -> set[str]:
        return self.component_page.selected() if self.mode_page.mode() == 'selective' else set()

    def make_plan(self) -> dict:
        return build_uninstall_plan(self.controller, mode=self.mode_page.mode(),
            selected=self.selected_ids(), remove_hub_preferences=self.options_page.hub_preferences.isChecked(),
            remove_component_preferences=self.options_page.app_preferences.isChecked())

    def accept(self) -> None:
        if not self.confirm_page.isComplete() or self.plan is None:
            return
        try:
            # Detect changes in inventory, mode, options, file identities, or
            # selection after Review. Never silently widen the destructive plan.
            fresh = self.make_plan()
            if fresh != self.plan:
                raise UnsafePlan('The reviewed inventory or removal options changed; go Back to review a new plan.')
            launch_uninstall_helper(fresh)
        except Exception as exc:
            QMessageBox.critical(self, 'Uninstall Not Started', str(exc))
            return
        self.handoff_ready = True
        super().accept()


def launch_uninstall_helper(plan: dict) -> None:
    if os.name != 'posix':
        raise UnsafePlan('The independent Suite cleanup helper is currently supported on Linux/POSIX only.')
    python = shutil.which('python3')
    if not python:
        raise UnsafePlan('Independent system Python 3 is required for post-exit cleanup.')
    source = Path(__file__).with_name('suite_uninstall_worker.py')
    if not source.is_file() or source.is_symlink():
        raise UnsafePlan('Bundled standalone uninstall helper is unavailable.')
    temporary = Path(tempfile.mkdtemp(prefix='suite-pythoine-uninstall-'))
    script = temporary / 'worker.py'
    plan_file = temporary / 'reviewed-plan.json'
    read_fd = write_fd = None
    try:
        script.write_bytes(source.read_bytes())
        plan_file.write_text(json.dumps(plan, indent=2), encoding='utf-8')
        script.chmod(0o600); plan_file.chmod(0o600)
        read_fd, write_fd = os.pipe()
        subprocess.Popen([python, '-I', str(script), str(plan_file), str(read_fd)],
            pass_fds=(read_fd,), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True)
        os.close(read_fd); read_fd = None
        # Intentionally kept open in THIS process until it exits. This is not
        # an asynchronous Hub task: the independent helper owns completion.
        _EXIT_GATES.append(write_fd); write_fd = None
    except Exception:
        if read_fd is not None: os.close(read_fd)
        if write_fd is not None: os.close(write_fd)
        shutil.rmtree(temporary, ignore_errors=True)
        raise


_EXIT_GATES: list[int] = []
