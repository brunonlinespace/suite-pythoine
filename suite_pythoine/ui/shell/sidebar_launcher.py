"""Modeless Suite application launcher for the optional floating sidebar mode.

Uses only the already-discovered inventory supplied by SuiteWindow. Filtering and
selection never inspect the filesystem or construct application detail pages.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QSize, QEvent, pyqtSignal
from .sidebar_search import matches_application
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout,
)


class SidebarLauncher(QDialog):
    page_requested = pyqtSignal(str)
    launch_requested = pyqtSignal(str)
    dashboard_requested = pyqtSignal()
    refresh_requested = pyqtSignal()
    store_requested = pyqtSignal()
    visibility_changed = pyqtSignal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # A tool dialog belongs to the Suite window, but remains modeless: a
        # user can continue using the Dashboard while the launcher is open.
        self.setWindowFlag(Qt.WindowType.Tool, True)
        self.setWindowTitle("Applications Launcher — Suite Pythoine")
        self.resize(430, 590)
        self.setMinimumSize(340, 370)
        self._groups: list[tuple[str, list[tuple[str, object]]]] = []
        self._icons: dict[str, QIcon] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(9)
        title = QLabel("Applications")
        font = title.font()
        font.setBold(True)
        font.setPointSize(max(font.pointSize() + 2, 11))
        title.setFont(font)
        layout.addWidget(title)

        self.search = QLineEdit(self)
        self.search.setPlaceholderText("Search applications, formats or descriptions…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter_entries)
        self.search.returnPressed.connect(self._launch_selected)
        layout.addWidget(self.search)

        self.entries = QListWidget(self)
        self.entries.setIconSize(QSize(26, 26))
        self.entries.setSpacing(1)
        self.entries.currentItemChanged.connect(lambda *_: self._sync_buttons())
        self.entries.itemDoubleClicked.connect(self._launch_item)
        self.entries.installEventFilter(self)
        layout.addWidget(self.entries, 1)

        buttons = QHBoxLayout()
        self.page_button = QPushButton("Open Page", self)
        self.page_button.clicked.connect(self._open_selected)
        self.launch_button = QPushButton("Launch", self)
        self.launch_button.clicked.connect(self._launch_selected)
        buttons.addWidget(self.page_button)
        buttons.addWidget(self.launch_button)
        layout.addLayout(buttons)

        navigation = QHBoxLayout()
        dashboard = QPushButton("Dashboard", self)
        dashboard.clicked.connect(self._open_dashboard)
        refresh = QPushButton("Refresh", self)
        refresh.clicked.connect(lambda _checked=False: self.refresh_requested.emit())
        self.store_button = QPushButton("Get More…", self)
        self.store_button.clicked.connect(self._open_store)
        navigation.addWidget(dashboard)
        navigation.addWidget(refresh)
        navigation.addWidget(self.store_button)
        layout.addLayout(navigation)
        self._sync_buttons()


    def set_store_mode(self, installed: bool, icon_path=None) -> None:
        """Keep the floating launcher's Store entry in parity with Suite navigation."""
        self.store_button.setText("Store Pythoine" if installed else "Get More…")
        self.store_button.setIcon(QIcon(str(icon_path)) if installed and icon_path is not None else QIcon())
        self.store_button.setToolTip(
            "Open Store Pythoine inside Suite." if installed
            else "Browse Suite's lightweight offline catalogue."
        )

    def refresh_theme(self) -> None:
        """Refresh the existing tool dialog after changing application chrome.

        In particular, keep the search and result list in the same palette as
        the Hub without recreating the launcher or refreshing its inventory.
        """
        for widget in (self, self.search, self.entries):
            style = widget.style()
            style.unpolish(widget)
            style.polish(widget)
            widget.update()

    def set_entries(self, groups: list[tuple[str, list[tuple[str, object]]]]) -> None:
        """Accept an in-memory inventory; avoid triggering discovery on searches."""
        self._groups = groups
        # Probe icon paths only when the Suite inventory changes, never for
        # every keystroke in the launcher's search field.
        self._icons = {}
        for _group, members in groups:
            for key, entry in members:
                icon = getattr(entry, "icon", None)
                if icon is not None and icon.is_file():
                    self._icons[key] = QIcon(str(icon))
        self._filter_entries()

    def focus_search(self) -> None:
        self.search.setFocus()
        self.search.selectAll()

    def _filter_entries(self, *_args) -> None:
        query = self.search.text().strip().casefold()
        current = self._selected_key()
        self.entries.blockSignals(True)
        self.entries.clear()
        restore = None
        first = None
        for group, members in self._groups:
            matches = []
            for key, entry in members:
                if matches_application(entry, group, query):
                    matches.append((key, entry))
            if not matches:
                continue
            heading = QListWidgetItem(group)
            heading.setFlags(Qt.ItemFlag.NoItemFlags)
            font = heading.font()
            font.setBold(True)
            heading.setFont(font)
            heading.setSizeHint(QSize(0, 28))
            self.entries.addItem(heading)
            for key, entry in matches:
                label = str(getattr(entry, "name", key))
                versions = getattr(entry, "versions", ()) or ()
                if len(versions) > 1:
                    label += f"  ({len(versions)} versions)"
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, key)
                icon = self._icons.get(key)
                if icon is not None:
                    item.setIcon(icon)
                item.setToolTip(
                    f"{getattr(entry, 'description', '')}\n"
                    f"Formats: {', '.join(getattr(entry, 'extensions', ()) or ())}"
                )
                item.setSizeHint(QSize(0, 39))
                self.entries.addItem(item)
                if first is None:
                    first = item
                if key == current:
                    restore = item
        if first is not None:
            self.entries.setCurrentItem(restore or first)
        self.entries.blockSignals(False)
        self._sync_buttons()

    def _selected_key(self) -> str | None:
        item = self.entries.currentItem()
        if item is None:
            return None
        key = item.data(Qt.ItemDataRole.UserRole)
        return key if isinstance(key, str) else None

    def _sync_buttons(self) -> None:
        available = self._selected_key() is not None
        self.page_button.setEnabled(available)
        self.launch_button.setEnabled(available)

    def _open_selected(self) -> None:
        key = self._selected_key()
        if key is not None:
            self.hide()
            self.page_requested.emit(key)

    def _launch_selected(self) -> None:
        key = self._selected_key()
        if key is not None:
            self.hide()
            self.launch_requested.emit(key)

    def _launch_item(self, item: QListWidgetItem) -> None:
        if item is not None and item.data(Qt.ItemDataRole.UserRole) is not None:
            self.entries.setCurrentItem(item)
            self._launch_selected()

    def _open_dashboard(self) -> None:
        self.hide()
        self.dashboard_requested.emit()

    def _open_store(self) -> None:
        self.hide()
        self.store_requested.emit()

    def eventFilter(self, watched, event) -> bool:
        # Explicit Enter handling avoids platform-specific itemActivated mouse
        # semantics and guarantees a double-click never launches twice.
        if (watched is self.entries and event.type() == QEvent.Type.KeyPress
                and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)):
            self._launch_selected()
            return True
        return super().eventFilter(watched, event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.visibility_changed.emit(True)
        self.focus_search()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self.visibility_changed.emit(False)
