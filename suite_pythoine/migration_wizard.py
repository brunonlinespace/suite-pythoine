from __future__ import annotations

from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QPlainTextEdit, QVBoxLayout, QWizard, QWizardPage

from .config import ConfigService
from .storage_migration import MigrationPlan, migrate_item
from .ui_titles import app_dialog_title


class MigrationReviewPage(QWizardPage):
    def __init__(self, plan: MigrationPlan) -> None:
        super().__init__()
        self.plan = plan
        self.setTitle("Organise existing editors")
        self.setSubTitle("Review the move to Suite Pythoine's single versioned Components folder.")
        layout = QVBoxLayout(self)
        intro = QLabel(
            f"Suite Pythoine now keeps portable sources and managed AppImages together under:\n{plan.editors_root}\n\n"
            "Existing files are copied into the new layout first. The old copy is removed only after the new copy is complete."
        )
        intro.setTextFormat(Qt.TextFormat.PlainText)
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.listing = QPlainTextEdit()
        self.listing.setReadOnly(True)
        lines: list[str] = []
        for item in plan.items:
            lines.append(f"{item.name} — {item.version or 'Unknown'}")
            if item.portable_source and item.portable_destination and item.portable_source != item.portable_destination:
                lines.append(f"  Portable:\n    {item.portable_source}\n    → {item.portable_destination}")
            if item.appimage_source and item.appimage_destination and item.appimage_source != item.appimage_destination:
                lines.append(f"  AppImage:\n    {item.appimage_source}\n    → {item.appimage_destination}")
            if item.old_desktop and item.new_desktop and item.old_desktop != item.new_desktop:
                lines.append(f"  Desktop entry:\n    {item.old_desktop}\n    → {item.new_desktop}")
            lines.append("")
        if plan.skipped:
            lines.append("Not automatically migrated:")
            lines.extend(f"  {line}" for line in plan.skipped)
        self.listing.setPlainText("\n".join(lines).rstrip())
        layout.addWidget(self.listing, 1)


class MigrationProgressPage(QWizardPage):
    def __init__(self, plan: MigrationPlan, config: ConfigService, finished_callback: Callable[[], None]) -> None:
        super().__init__()
        self.plan = plan
        self.config = config
        self.finished_callback = finished_callback
        self.started = False
        self.finished = False
        self.succeeded = False
        self.error_message = ""
        self.setTitle("Organising editors")
        self.setSubTitle("Suite Pythoine is moving each editor into the new versioned layout.")
        layout = QVBoxLayout(self)
        self.steps = QListWidget()
        self.items: list[QListWidgetItem] = []
        for migration in plan.items:
            item = QListWidgetItem(f"○  {migration.name} {migration.version or ''}".rstrip())
            self.steps.addItem(item)
            self.items.append(item)
        layout.addWidget(self.steps, 1)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)

    def initializePage(self) -> None:  # noqa: N802
        wizard = self.wizard()
        if wizard is not None:
            wizard.button(QWizard.WizardButton.BackButton).setEnabled(False)
            wizard.button(QWizard.WizardButton.CancelButton).setEnabled(False)
        if not self.started:
            self.started = True
            QTimer.singleShot(0, self._run)

    def isComplete(self) -> bool:  # noqa: N802
        return self.finished

    def _run(self) -> None:
        try:
            for index, migration in enumerate(self.plan.items):
                if not migration.has_work:
                    self.items[index].setText(f"—  {migration.name} {migration.version or ''} — already organised".rstrip())
                    continue
                self.items[index].setText(f"⟳  {migration.name} {migration.version or ''}".rstrip())
                self.steps.scrollToItem(self.items[index])
                migrate_item(migration, self.plan.editors_root, self.config.as_dict())
                self.items[index].setText(f"✓  {migration.name} {migration.version or ''}".rstrip())
            self.config.update(
                {
                    "editors_root": str(self.plan.editors_root),
                    "legacy_my_editors_dir": None,
                    "legacy_installed_editors_dir": None,
                    "storage_layout_version": 3,
                    "storage_migration_dismissed": bool(self.plan.skipped),
                },
                save=True,
            )
            self.succeeded = True
            self.status.setText("Existing components were organised successfully.")
        except Exception as exc:
            self.error_message = str(exc)
            self.status.setText(f"Migration stopped: {exc}\n\nExisting source files are retained when a copy step fails.")
        self.finished = True
        wizard = self.wizard()
        if wizard is not None:
            wizard.button(QWizard.WizardButton.CancelButton).setEnabled(True)
        self.finished_callback()
        self.completeChanged.emit()


class StorageMigrationWizard(QWizard):
    def __init__(self, parent, plan: MigrationPlan, config: ConfigService, finished_callback: Callable[[], None]) -> None:
        super().__init__(parent)
        self.plan = plan
        self.config = config
        self.setWindowTitle(app_dialog_title("Organise Existing Components"))
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.resize(860, 650)
        self.review = MigrationReviewPage(plan)
        self.progress = MigrationProgressPage(plan, config, finished_callback)
        self.addPage(self.review)
        self.addPage(self.progress)
        self.setButtonText(QWizard.WizardButton.NextButton, "Organise")
        self.setButtonText(QWizard.WizardButton.FinishButton, "Finish")
