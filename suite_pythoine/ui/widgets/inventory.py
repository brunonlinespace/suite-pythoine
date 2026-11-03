from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHeaderView, QStyle, QStyleOptionButton, QTableWidgetItem, QWidget


class SortableTableItem(QTableWidgetItem):
    """QTableWidget item that sorts by a hidden UserRole value when present."""

    def __lt__(self, other: QTableWidgetItem) -> bool:
        left = self.data(Qt.ItemDataRole.UserRole)
        right = other.data(Qt.ItemDataRole.UserRole)
        if left is not None and right is not None and type(left) is type(right):
            try:
                return left < right
            except TypeError:
                pass
        return super().__lt__(other)


class AssetSelectionHeader(QHeaderView):
    """Header with one tri-state selection checkbox for Remove Assets mode."""

    toggleSelectionRequested = pyqtSignal(bool)

    def __init__(self, orientation: Qt.Orientation, parent: QWidget | None = None) -> None:
        super().__init__(orientation, parent)
        self._selection_section = -1
        self._selection_state = Qt.CheckState.Unchecked

    def set_selection_section(self, logical: int) -> None:
        self._selection_section = int(logical)
        self.viewport().update()

    def set_selection_state(self, state: Qt.CheckState) -> None:
        if state == self._selection_state:
            return
        self._selection_state = state
        self.viewport().update()

    def paintSection(self, painter, rect, logical_index: int) -> None:  # noqa: N802 - Qt API
        super().paintSection(painter, rect, logical_index)
        if logical_index != self._selection_section:
            return
        option = QStyleOptionButton()
        option.state = QStyle.StateFlag.State_Enabled
        if self._selection_state == Qt.CheckState.Checked:
            option.state |= QStyle.StateFlag.State_On
        elif self._selection_state == Qt.CheckState.PartiallyChecked:
            option.state |= QStyle.StateFlag.State_NoChange
        else:
            option.state |= QStyle.StateFlag.State_Off
        indicator = self.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, option, self)
        indicator.moveCenter(rect.center())
        option.rect = indicator
        self.style().drawControl(QStyle.ControlElement.CE_CheckBox, option, painter, self)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        logical = self.logicalIndexAt(event.position().toPoint())
        if logical == self._selection_section and not self.isSectionHidden(logical):
            self.toggleSelectionRequested.emit(self._selection_state != Qt.CheckState.Checked)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API
        # The transient selection header is a checkbox, not a sortable column.
        # Swallow its release as well as its press so Qt cannot reinterpret the
        # click as a sort request; every normal heading stays fully native.
        logical = self.logicalIndexAt(event.position().toPoint())
        if logical == self._selection_section and not self.isSectionHidden(logical):
            event.accept()
            return
        super().mouseReleaseEvent(event)
