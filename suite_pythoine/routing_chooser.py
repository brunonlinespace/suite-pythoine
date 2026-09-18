from __future__ import annotations

import sys

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QVBoxLayout,
)

from . import APP_NAME, __version__
from .silent_dispatch import ChoiceRequest, InspectorFallbackRequest, launch_choice, launch_inspector_fallback
from .ui_titles import app_dialog_title


def _choose_one(choice: ChoiceRequest) -> tuple[bool, bool]:
    dialog = QDialog()
    dialog.setWindowTitle(app_dialog_title("Choose Application"))
    dialog.setMinimumWidth(430)
    layout = QVBoxLayout(dialog)
    label = QLabel(f"Open {choice.path.name} with:")
    label.setWordWrap(True)
    layout.addWidget(label)
    combo = QComboBox()
    for candidate in choice.candidates:
        combo.addItem(candidate.name, candidate.component_id)
    layout.addWidget(combo)
    remember = QCheckBox(
        f"Remember my choice for {choice.extension or 'this file type'} files"
    )
    remember.setChecked(False)
    layout.addWidget(remember)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Open | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return False, True
    component_id = str(combo.currentData() or "")
    ok, error = launch_choice(choice, component_id, remember=remember.isChecked())
    if error:
        QMessageBox.warning(dialog, app_dialog_title("Routing Warning"), error)
    return ok, False


def run_routing_choices(choices: tuple[ChoiceRequest, ...] | list[ChoiceRequest]) -> bool:
    """Run only the compact chooser UI; never construct SuiteWindow.

    Returns True when every request was either launched or explicitly cancelled.
    Cancellation is considered handled so the full hub does not appear behind a
    user's intentional pseudo-silent choice dialog.
    """
    app = QApplication.instance()
    owns_app = app is None
    if app is None:
        app = QApplication([sys.argv[0]])
        app.setApplicationName("suite-pythoine")
        app.setApplicationDisplayName(APP_NAME)
        app.setApplicationVersion(__version__)
        app.setOrganizationName("brunonlinespace")
        app.setDesktopFileName("io.github.brunonlinespace.suite-pythoine")
    all_handled = True
    for choice in choices:
        ok, cancelled = _choose_one(choice)
        if not ok and not cancelled:
            all_handled = False
    if owns_app:
        app.processEvents()
    return all_handled


def _choose_inspector_fallback(request: InspectorFallbackRequest) -> tuple[bool, bool]:
    dialog = QDialog()
    dialog.setWindowTitle(app_dialog_title("Inspect Unsupported File"))
    dialog.setMinimumWidth(440)
    layout = QVBoxLayout(dialog)
    label = QLabel(
        f"No dedicated Editor or routed Reader is installed for {request.path.name}.\n"
        "Inspect it with:"
    )
    label.setWordWrap(True)
    layout.addWidget(label)
    combo = QComboBox()
    for candidate in request.candidates:
        combo.addItem(candidate.name, candidate.component_id)
    layout.addWidget(combo)
    remember = QCheckBox("Remember my inspection fallback choice")
    remember.setChecked(False)
    layout.addWidget(remember)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Open | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return False, True
    component_id = str(combo.currentData() or "")
    ok, error = launch_inspector_fallback(request, component_id, remember=remember.isChecked())
    if error:
        QMessageBox.warning(dialog, app_dialog_title("Routing Warning"), error)
    return ok, False


def run_inspector_fallback_choices(
    choices: tuple[InspectorFallbackRequest, ...] | list[InspectorFallbackRequest],
) -> bool:
    """Run compact Beespector fallback chooser(s) without constructing SuiteWindow."""
    app = QApplication.instance()
    owns_app = app is None
    if app is None:
        app = QApplication([sys.argv[0]])
        app.setApplicationName("suite-pythoine")
        app.setApplicationDisplayName(APP_NAME)
        app.setApplicationVersion(__version__)
        app.setOrganizationName("brunonlinespace")
        app.setDesktopFileName("io.github.brunonlinespace.suite-pythoine")
    all_handled = True
    for choice in choices:
        ok, cancelled = _choose_inspector_fallback(choice)
        if not ok and not cancelled:
            all_handled = False
    if owns_app:
        app.processEvents()
    return all_handled
