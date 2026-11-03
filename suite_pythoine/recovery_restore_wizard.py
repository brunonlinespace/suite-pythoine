from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QFontDatabase, QIcon, QTextCursor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFormLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWizard,
)

from .config import ConfigService
from .install_inspection import ZipEditorInspection
from .install_wizard import BrandedPage, _inspection_pixmap, _plain_label
from .installer import InstallError
from .recovery import RecoveryInfo, restore_portable_from_recovery
from .runtime.runtime_launcher import RuntimeLauncher
from .ui_titles import app_dialog_title

RESTORE_STEPS = (
    ("validate", "Validate Recovery archive"),
    ("extract", "Extract recovered Portable to staging"),
    ("verify", "Verify recovered Portable"),
    ("replace", "Replace managed Portable"),
    ("done", "Refresh restored runtime"),
)


class RestorePlanPage(BrandedPage):
    def __init__(self, inspection: ZipEditorInspection, info: RecoveryInfo, portable_target: Path) -> None:
        super().__init__(
            inspection,
            "Restore Portable",
            "Suite Pythoine will recreate this exact Portable from its retained managed Recovery archive.",
        )
        layout = QVBoxLayout(self)
        layout.addWidget(self.branding_header())
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        archive = _plain_label(info.archive_path.name, wrap=False)
        archive.setToolTip(str(info.archive_path))
        form.addRow("Recovery archive:", archive)
        form.addRow("Original filename:", _plain_label(info.original_filename, wrap=False))
        form.addRow("Retained:", _plain_label(info.retained_at or "Unknown", wrap=False))
        checksum = _plain_label(info.sha256, wrap=True)
        checksum.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("SHA-256:", checksum)
        target = _plain_label(str(portable_target), wrap=True)
        target.setToolTip(str(portable_target))
        form.addRow("Target:", target)
        current = "Present" if portable_target.is_dir() and not portable_target.is_symlink() else "Missing"
        form.addRow("Current Portable:", _plain_label(current, wrap=False))
        operation = (
            "Replace Portable from retained Recovery archive"
            if current == "Present"
            else "Recreate Portable from retained Recovery archive"
        )
        form.addRow("Operation:", _plain_label(operation, wrap=True))
        layout.addLayout(form)
        note = QLabel(
            "The existing Portable, if present, remains untouched until the recovered replacement has been "
            "fully extracted and verified. This operation does not change the active version, Launch runtime "
            "preference, AppImage, Recovery archive, routing, or desktop integration."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)


class RestoreProgressPage(BrandedPage):
    def __init__(
        self,
        inspection: ZipEditorInspection,
        info: RecoveryInfo,
        portable_target: Path,
        *,
        editors_root: Path,
        installed_dir: Path,
        config: ConfigService,
        launcher: RuntimeLauncher,
        allow_checksum_mismatch: bool = False,
    ) -> None:
        super().__init__(
            inspection,
            f"Restoring {inspection.name}",
            "The checklist is the restore state; technical details remain available below.",
        )
        self.info = info
        self.portable_target = portable_target
        self.editors_root = editors_root
        self.installed_dir = installed_dir
        self.config = config
        self.launcher = launcher
        self.allow_checksum_mismatch = allow_checksum_mismatch
        self.started = False
        self.finished = False
        self.succeeded = False
        self.error_message = ""
        self.restored_path: Path | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(self.branding_header())
        self.steps = QListWidget()
        self.steps.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.step_items: dict[str, QListWidgetItem] = {}
        for key, label in RESTORE_STEPS:
            item = QListWidgetItem(f"○  {label}")
            self.step_items[key] = item
            self.steps.addItem(item)
        self.steps.setMinimumHeight(180)
        self.steps.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.steps, 1)

        self.result_label = QLabel()
        self.result_label.setTextFormat(Qt.TextFormat.PlainText)
        self.result_label.setWordWrap(True)
        self.result_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        layout.addWidget(self.result_label)

        self.command_label = QLabel(f"Recovery archive: {self.info.archive_path}")
        self.command_label.setTextFormat(Qt.TextFormat.PlainText)
        self.command_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.command_label.setWordWrap(True)
        layout.addWidget(self.command_label)

        self.toggle_output = QPushButton("Show technical details")
        self.toggle_output.setCheckable(True)
        self.toggle_output.toggled.connect(self._toggle_output)
        layout.addWidget(self.toggle_output)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setVisible(False)
        self.output.setMinimumHeight(150)
        self.output.setMaximumHeight(260)
        self.output.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.output.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        layout.addWidget(self.output, 1)
        self._collapsed_wizard_size = None
        self._collapsed_steps_height = None

    def initializePage(self) -> None:  # noqa: N802 - Qt API
        wizard = self.wizard()
        if wizard is not None:
            wizard.button(QWizard.WizardButton.BackButton).setEnabled(False)
            wizard.button(QWizard.WizardButton.CancelButton).setEnabled(False)
        if not self.started:
            self.started = True
            QTimer.singleShot(0, self._start)

    def isComplete(self) -> bool:  # noqa: N802 - Qt API
        return self.finished

    def _set_step(self, key: str, state: str, detail: str | None = None) -> None:
        item = self.step_items[key]
        label = dict(RESTORE_STEPS)[key]
        prefix = {"pending": "○", "active": "⟳", "done": "✓", "skip": "—", "fail": "✕"}[state]
        text = f"{prefix}  {label}"
        if detail:
            text += f" — {detail}"
        item.setText(text)
        self.steps.scrollToItem(item)
        QApplication.processEvents()

    def _log(self, text: str) -> None:
        if not text:
            return
        self.output.moveCursor(QTextCursor.MoveOperation.End)
        self.output.insertPlainText(text if text.endswith("\n") else text + "\n")
        self.output.moveCursor(QTextCursor.MoveOperation.End)

    def _progress(self, stage: str, detail: str = "") -> None:
        if stage == "done":
            self._set_step("done", "active", detail)
            return
        for key, _label in RESTORE_STEPS:
            if key == stage:
                self._set_step(key, "active", detail)
                return

    def _toggle_output(self, checked: bool) -> None:
        wizard = self.wizard()
        if checked:
            self._collapsed_steps_height = max(180, self.steps.height())
            self.steps.setMinimumHeight(self._collapsed_steps_height)
            if wizard is not None:
                self._collapsed_wizard_size = wizard.size()
            self.output.setVisible(True)
            self.toggle_output.setText("Hide technical details")
            QTimer.singleShot(0, self._grow_wizard_for_output)
        else:
            self.output.setVisible(False)
            self.steps.setMinimumHeight(180)
            self.toggle_output.setText("Show technical details")
            if wizard is not None and self._collapsed_wizard_size is not None:
                wizard.resize(self._collapsed_wizard_size)
            self._collapsed_wizard_size = None
            self._collapsed_steps_height = None

    def _grow_wizard_for_output(self) -> None:
        wizard = self.wizard()
        if wizard is None or self._collapsed_wizard_size is None or not self.output.isVisible():
            return
        extra = max(170, min(260, self.output.sizeHint().height()))
        target_height = self._collapsed_wizard_size.height() + extra
        screen = wizard.screen()
        if screen is not None:
            available = screen.availableGeometry()
            target_height = min(target_height, max(self._collapsed_wizard_size.height(), available.height() - 32))
        wizard.resize(self._collapsed_wizard_size.width(), target_height)

    def _start(self) -> None:
        self._log(f"[suite] Recovery archive: {self.info.archive_path}")
        self._log(f"[suite] Recorded SHA-256: {self.info.sha256}")
        self._log(f"[suite] Portable target: {self.portable_target}")
        try:
            restored_path, _restored = restore_portable_from_recovery(
                self.info.recovery_dir,
                self.portable_target,
                editors_root=self.editors_root,
                expected_editor_id=self.info.editor_id,
                expected_version=self.info.version,
                config=self.config.as_dict(),
                installed_dir=self.installed_dir,
                python_executable=self.launcher.python_executable(),
                progress_callback=self._progress,
                allow_checksum_mismatch=self.allow_checksum_mismatch,
            )
            self.restored_path = restored_path
            for key, _label in RESTORE_STEPS:
                self._set_step(key, "done")
            self.result_label.setText(
                f"Portable restored successfully to {restored_path}. Active version, Launch runtime preference, "
                "AppImage, Recovery archive and desktop integration were not changed."
            )
            self._log(f"[suite] Portable restored successfully: {restored_path}")
            self.succeeded = True
        except (InstallError, OSError, ValueError) as exc:
            self.error_message = str(exc)
            active_key = next((key for key, _label in RESTORE_STEPS if self.step_items[key].text().startswith("⟳")), "validate")
            self._set_step(active_key, "fail", self.error_message)
            self.result_label.setText(f"Restore failed: {self.error_message}")
            self._log(f"[suite] ERROR: {self.error_message}")
        finally:
            self.finished = True
            self.completeChanged.emit()
            wizard = self.wizard()
            if wizard is not None:
                wizard.button(QWizard.WizardButton.CancelButton).setEnabled(True)


class RestoreFinishPage(BrandedPage):
    def __init__(self, inspection: ZipEditorInspection, progress: RestoreProgressPage) -> None:
        super().__init__(inspection, "Restore complete", "Suite Pythoine has finished the managed Recovery operation.")
        self.progress = progress
        layout = QVBoxLayout(self)
        layout.addWidget(self.branding_header())
        self.summary = QLabel()
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        layout.addStretch(1)

    def initializePage(self) -> None:  # noqa: N802 - Qt API
        if self.progress.succeeded and self.progress.restored_path is not None:
            self.summary.setText(
                f"Portable restored successfully.\n\n{self.progress.restored_path}\n\n"
                "The retained Recovery archive remains available for future use."
            )
        else:
            self.summary.setText(f"Restore did not complete successfully.\n\n{self.progress.error_message}")


class RecoveryRestoreWizard(QWizard):
    """Installer-family wizard for one exact managed Recovery → Portable restore."""

    def __init__(
        self,
        parent,
        inspection: ZipEditorInspection,
        info: RecoveryInfo,
        portable_target: Path,
        *,
        editors_root: Path,
        installed_dir: Path,
        config: ConfigService,
        launcher: RuntimeLauncher,
        allow_checksum_mismatch: bool = False,
    ) -> None:
        super().__init__(parent)
        self.inspection = inspection
        self.info = info
        self.portable_target = portable_target
        self.setWindowTitle(app_dialog_title(f"Restore {inspection.name}"))
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setMinimumSize(820, 640)
        self.resize(980, 800)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)
        self.setOption(QWizard.WizardOption.NoBackButtonOnLastPage, True)
        pixmap = _inspection_pixmap(inspection, 128)
        if pixmap is not None:
            self.setWindowIcon(QIcon(pixmap))
            self.setPixmap(QWizard.WizardPixmap.LogoPixmap, pixmap)

        self.plan_page = RestorePlanPage(inspection, info, portable_target)
        self.progress_page = RestoreProgressPage(
            inspection,
            info,
            portable_target,
            editors_root=editors_root,
            installed_dir=installed_dir,
            config=config,
            launcher=launcher,
            allow_checksum_mismatch=allow_checksum_mismatch,
        )
        self.finish_page = RestoreFinishPage(inspection, self.progress_page)
        self.addPage(self.plan_page)
        self.addPage(self.progress_page)
        self.addPage(self.finish_page)
        self.setButtonText(QWizard.WizardButton.NextButton, "Continue")
        self.setButtonText(QWizard.WizardButton.FinishButton, "Finish")

    @property
    def succeeded(self) -> bool:
        return self.progress_page.succeeded
