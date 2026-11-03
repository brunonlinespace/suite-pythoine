"""Branded active-Hub Portable Recovery with post-exit replacement."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout, QWizard

from .install_wizard import BrandedPage, _plain_label, _inspection_pixmap
from .installer import InstallError
from .recovery import RecoveryInfo, prepare_portable_restore_staging
from .runtime.runtime_launcher import RuntimeLauncher
from .ui_titles import app_dialog_title

_EXIT_GATES: list[int] = []


def _state_report_path() -> Path:
    value = os.environ.get("XDG_STATE_HOME", "")
    root = Path(value) if value and Path(value).is_absolute() else Path.home() / ".local" / "state"
    return root / "suite-pythoine" / "last-self-restore-report.txt"


class SelfRestoreReviewPage(BrandedPage):
    def __init__(self, inspection, info: RecoveryInfo, target: Path) -> None:
        super().__init__(inspection, "Restore running Hub Portable",
                         "The recovered replacement will be prepared now and installed only after Suite Pythoine exits.")
        layout = QVBoxLayout(self)
        layout.addWidget(self.branding_header())
        text = QLabel(
            f"Recovery archive: {info.archive_path.name}\nTarget: {target}\n\n"
            "Suite Pythoine will not replace files beneath the running process. Continue to extract and verify the "
            "replacement in a sibling staging folder. Finish will then close Hub, perform the reviewed atomic handoff, "
            "and request a relaunch of the restored Portable. Recovery remains intact."
        )
        text.setTextFormat(Qt.TextFormat.PlainText); text.setWordWrap(True)
        layout.addWidget(text); layout.addStretch(1)


class SelfRestorePreparePage(BrandedPage):
    def __init__(self, wizard, inspection) -> None:
        super().__init__(inspection, "Prepare recovered Portable", "No live Hub file is replaced on this page.")
        self.owner = wizard
        layout = QVBoxLayout(self)
        layout.addWidget(self.branding_header())
        self.message = QLabel("Ready to prepare the recovered Portable.")
        self.message.setWordWrap(True); layout.addWidget(self.message)
        self.details = QPlainTextEdit(); self.details.setReadOnly(True); layout.addWidget(self.details, 1)

    def initializePage(self) -> None:  # noqa: N802
        if self.owner.staged is not None:
            return
        try:
            staged, _restored = prepare_portable_restore_staging(
                self.owner.info.recovery_dir, self.owner.target,
                editors_root=self.owner.editors_root,
                expected_editor_id=self.owner.info.editor_id,
                expected_version=self.owner.info.version,
                config=self.owner.config.as_dict(),
                installed_dir=self.owner.installed_dir,
                python_executable=self.owner.launcher.python_executable(),
                allow_checksum_mismatch=self.owner.allow_checksum_mismatch,
            )
            self.owner.staged = staged
            self.message.setText("Recovered Portable extracted and verified. Continue to review the post-exit handoff.")
            self.details.setPlainText(f"Prepared staging folder:\n{staged}\n\nRunning target remains untouched:\n{self.owner.target}")
        except Exception as exc:
            self.owner.error_message = str(exc)
            self.message.setText("Preparation failed. No running Hub file was replaced.")
            self.details.setPlainText(str(exc))
        self.completeChanged.emit()

    def isComplete(self) -> bool:  # noqa: N802
        return self.owner.staged is not None


class SelfRestoreFinishPage(BrandedPage):
    def __init__(self, wizard, inspection) -> None:
        super().__init__(inspection, "Ready for self-restore",
                         "Finish will close Suite Pythoine so the independent helper can replace the running Portable safely.")
        self.owner = wizard
        layout = QVBoxLayout(self); layout.addWidget(self.branding_header())
        label = QLabel("The prepared replacement has been verified. Finish closes Hub, performs the post-exit replacement, and requests a relaunch. A state report is retained if anything fails.")
        label.setWordWrap(True); layout.addWidget(label); layout.addStretch(1)
        self.setFinalPage(True)


class HubSelfRestoreWizard(QWizard):
    def __init__(self, parent, inspection, info: RecoveryInfo, target: Path, *, editors_root: Path,
                 installed_dir: Path, config, launcher: RuntimeLauncher, allow_checksum_mismatch: bool = False) -> None:
        super().__init__(parent)
        self.inspection = inspection; self.info = info; self.target = target.expanduser().resolve(strict=False)
        self.editors_root = editors_root.expanduser().resolve(strict=False)
        self.installed_dir = installed_dir.expanduser().resolve(strict=False)
        self.config = config; self.launcher = launcher; self.allow_checksum_mismatch = allow_checksum_mismatch
        self.staged: Path | None = None; self.error_message = ""; self.handoff_ready = False
        self.setWindowTitle(app_dialog_title("Restore Suite Pythoine"))
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle); self.setMinimumSize(820, 640); self.resize(980, 800)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)
        pixmap = _inspection_pixmap(inspection, 128)
        if pixmap is not None:
            from PyQt6.QtGui import QIcon
            self.setWindowIcon(QIcon(pixmap)); self.setPixmap(QWizard.WizardPixmap.LogoPixmap, pixmap)
        self.addPage(SelfRestoreReviewPage(inspection, info, self.target))
        self.addPage(SelfRestorePreparePage(self, inspection))
        self.addPage(SelfRestoreFinishPage(self, inspection))
        self.setButtonText(QWizard.WizardButton.NextButton, "Continue")
        self.setButtonText(QWizard.WizardButton.FinishButton, "Finish")

    def _plan(self) -> dict:
        if self.staged is None or not self.staged.is_dir() or self.staged.is_symlink():
            raise InstallError("The prepared recovered Portable is unavailable.")
        target_exists = self.target.is_dir() and not self.target.is_symlink()
        return {
            "schema": 1,
            "target": str(self.target),
            "target_exists": target_exists,
            "target_identity": ([self.target.lstat().st_dev, self.target.lstat().st_ino] if target_exists else None),
            "staged": str(self.staged),
            "staged_identity": [self.staged.lstat().st_dev, self.staged.lstat().st_ino],
            "python": self.launcher.python_executable(),
            "report_path": str(_state_report_path()),
        }

    def accept(self) -> None:
        try:
            launch_self_restore_helper(self._plan())
        except Exception as exc:
            self.error_message = str(exc)
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(self, app_dialog_title("Restore Not Started"), str(exc))
            return
        self.handoff_ready = True
        super().accept()

    def reject(self) -> None:
        if not self.handoff_ready and self.staged is not None and self.staged.is_dir() and not self.staged.is_symlink():
            shutil.rmtree(self.staged, ignore_errors=True)
        super().reject()


def launch_self_restore_helper(plan: dict) -> None:
    if os.name != "posix":
        raise InstallError("Active Hub self-restore currently requires Linux/POSIX.")
    python = shutil.which("python3")
    if not python:
        raise InstallError("Independent system Python 3 is required for post-exit Recovery.")
    source = Path(__file__).with_name("suite_self_restore_worker.py")
    if not source.is_file() or source.is_symlink():
        raise InstallError("Bundled standalone self-restore helper is unavailable.")
    temporary = Path(tempfile.mkdtemp(prefix="suite-pythoine-self-restore-"))
    script = temporary / "worker.py"; plan_file = temporary / "reviewed-plan.json"
    read_fd = write_fd = None
    try:
        script.write_bytes(source.read_bytes()); plan_file.write_text(json.dumps(plan, indent=2), encoding="utf-8")
        script.chmod(0o600); plan_file.chmod(0o600)
        read_fd, write_fd = os.pipe()
        subprocess.Popen([python, "-I", str(script), str(plan_file), str(read_fd)], pass_fds=(read_fd,),
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True, close_fds=True)
        os.close(read_fd); read_fd = None
        _EXIT_GATES.append(write_fd); write_fd = None
    except Exception:
        if read_fd is not None: os.close(read_fd)
        if write_fd is not None: os.close(write_fd)
        shutil.rmtree(temporary, ignore_errors=True)
        raise
