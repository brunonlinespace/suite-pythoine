from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QRect, QSize, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QScroller,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .component_policy import can_create_document, can_open_document, component_kind
from .dashboard_model import filter_and_sort_editors
from .registry import EditorEntry


class FlowLayout(QLayout):
    """Small wrapping layout derived from the mature Python Lair dashboard."""

    def __init__(self, parent=None, margin: int = 0, spacing: int = 12) -> None:
        super().__init__(parent)
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self._items = []

    def addItem(self, item) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        x = rect.x()
        y = rect.y()
        line_height = 0
        spacing = self.spacing()
        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + spacing
            if next_x - spacing > rect.right() and x > rect.x():
                x = rect.x()
                y += line_height + spacing
                next_x = x + hint.width() + spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(x, y, hint.width(), hint.height()))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y()


class FlowContainer(QWidget):
    """Height-for-width wrapper so grouped grid sections resize cleanly."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.flow = FlowLayout(self, spacing=12)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return max(1, self.flow.heightForWidth(max(1, width)))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.setMinimumHeight(self.heightForWidth(event.size().width()))


class DropBar(QFrame):
    payload_dropped = pyqtSignal(object, int)
    url_choice_selected = pyqtSignal(str, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("QFrame { background: palette(button); border: 1px solid palette(mid); border-radius: 6px; }")
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 7, 10, 7)
        self.label = QLabel("Drop file / URL here   •   Ctrl+Shift+B → Beespector   •   Ctrl+Shift+Y → Youlindo   •   Ctrl+Shift+C → Crawlindo")
        self.label.setStyleSheet("border: none;")
        self.label.setWordWrap(True)
        row.addWidget(self.label, 1)
        self.choice_host = QWidget(self)
        self.choice_layout = QHBoxLayout(self.choice_host)
        self.choice_layout.setContentsMargins(0, 0, 0, 0)
        self.choice_layout.setSpacing(4)
        self.choice_host.hide()
        row.addWidget(self.choice_host)


    def clear_choices(self) -> None:
        while self.choice_layout.count():
            item = self.choice_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.choice_host.hide()
        self.label.show()

    def show_url_choices(self, url: str, choices: list[tuple[str, str]]) -> None:
        self.clear_choices()
        self.label.hide()
        prompt = QLabel("Open URL with:")
        prompt.setStyleSheet("border: none;")
        self.choice_layout.addWidget(prompt)
        for component_id, name in choices:
            button = QPushButton(name)
            button.clicked.connect(lambda _checked=False, cid=component_id, value=url: self._choose_url(cid, value))
            self.choice_layout.addWidget(button)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.clear_choices)
        self.choice_layout.addWidget(cancel)
        self.choice_host.show()

    def _choose_url(self, component_id: str, url: str) -> None:
        self.clear_choices()
        self.url_choice_selected.emit(component_id, url)

    def dragEnterEvent(self, event) -> None:
        mime = event.mimeData()
        if mime.hasUrls() or mime.hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        mime = event.mimeData()
        payloads = []
        if mime.hasUrls():
            payloads.extend(mime.urls())
        if not payloads and mime.hasText():
            text = mime.text().strip()
            if text:
                payloads.append(QUrl.fromUserInput(text))
        if not payloads:
            event.ignore(); return
        self.payload_dropped.emit(payloads, int(event.modifiers().value))
        event.acceptProposedAction()


class EditorCard(QFrame):
    """Role-aware component card; name retained for source compatibility."""

    launch_requested = pyqtSignal(object)
    new_requested = pyqtSignal(object)
    open_requested = pyqtSignal(object)
    details_requested = pyqtSignal(object)

    def __init__(self, editor: EditorEntry, *, grid: bool, show_icon: bool = True, parent=None) -> None:
        super().__init__(parent)
        self.editor = editor
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("QFrame { border: 1px solid palette(mid); border-radius: 6px; }")
        if grid:
            self.setFixedSize(310, 190)
        else:
            self.setMinimumHeight(142)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(7)

        header = QHBoxLayout()
        if show_icon and editor.icon and editor.icon.is_file():
            icon_label = QLabel()
            icon_label.setPixmap(QIcon(str(editor.icon)).pixmap(34, 34))
            icon_label.setStyleSheet("border: none;")
            header.addWidget(icon_label)
        title = QLabel(editor.name)
        title.setTextFormat(Qt.TextFormat.PlainText)
        font = title.font()
        font.setBold(True)
        title.setFont(font)
        title.setStyleSheet("border: none;")
        header.addWidget(title, 1)
        role = QLabel({"editor": "Editor", "reader": "Reader", "extension": "Extension"}.get(component_kind(editor), component_kind(editor).title()))
        role.setStyleSheet("border: none;")
        header.addWidget(role)
        root.addLayout(header)

        version_line = f"\n{editor.version_note}" if editor.version_note else ""
        inventory_line = (
            f"\nActive: {editor.active_version or 'Unknown'}"
            f" · {len(editor.versions)} version{'s' if len(editor.versions) != 1 else ''}"
        )
        if editor.desktop_version:
            inventory_line += f" · Desktop: {editor.desktop_version}"
        if can_open_document(editor):
            formats = ", ".join(editor.extensions) if editor.extensions else "Not configured"
            detail_text = f"Formats: {formats}\n{editor.source_kind}{inventory_line}{version_line}"
        else:
            detail_text = f"{editor.source_kind}{inventory_line}{version_line}"
        details = QLabel(detail_text)
        details.setTextFormat(Qt.TextFormat.PlainText)
        details.setWordWrap(True)
        details.setStyleSheet("border: none;")
        root.addWidget(details)
        root.addStretch(1)

        buttons = QHBoxLayout()
        # Editors enter their native untitled workflow through New…; a separate
        # generic Launch action is intentionally redundant for Editors. Readers
        # and Extensions retain Launch because they do not own document creation.
        actions = []
        if can_create_document(editor):
            actions.append(("New…", self.new_requested))
        else:
            actions.append(("Launch", self.launch_requested))
        if can_open_document(editor):
            actions.append(("Open…", self.open_requested))
        actions.append(("Details", self.details_requested))
        for text, signal in actions:
            button = QPushButton(text)
            button.clicked.connect(lambda _checked=False, sig=signal: sig.emit(self.editor))
            buttons.addWidget(button)
        root.addLayout(buttons)


class EditorDashboard(QWidget):
    """Dashboard for installed Editors, Readers and Extensions.

    The historical class/signal names are retained to keep the 0.3.1 call sites
    stable while the visible model becomes component-oriented.
    """

    launch_requested = pyqtSignal(object)
    new_requested = pyqtSignal(object)
    open_requested = pyqtSignal(object)
    details_requested = pyqtSignal(object)
    refresh_requested = pyqtSignal()
    launch_prompt_requested = pyqtSignal()
    new_file_requested = pyqtSignal()
    open_file_requested = pyqtSignal()
    install_editor_requested = pyqtSignal()
    installed_applications_requested = pyqtSignal()
    suite_details_requested = pyqtSignal()
    sort_changed = pyqtSignal(str)
    search_changed = pyqtSignal(str)
    drop_payload_requested = pyqtSignal(object, int)
    url_choice_requested = pyqtSignal(str, str)

    def __init__(self, app_name: str, editors_root: Path, app_icon: Path | None = None, parent=None) -> None:
        super().__init__(parent)
        self.app_name = app_name
        self.editors_root = editors_root
        self.app_icon = app_icon
        self._components: list[EditorEntry] = []
        self._view_mode = "list"
        self._sort_mode = "title_az"
        self._show_icons = True

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 28)
        root.setSpacing(12)

        heading = QHBoxLayout()
        if app_icon and app_icon.is_file():
            icon = QLabel()
            icon.setPixmap(QIcon(str(app_icon)).pixmap(48, 48))
            heading.addWidget(icon)
        title = QLabel(app_name)
        font = title.font()
        font.setPointSize(max(font.pointSize() + 8, 18))
        font.setBold(True)
        title.setFont(font)
        heading.addWidget(title)
        heading.addStretch(1)
        root.addLayout(heading)

        intro = QLabel(
            "A simple hub for your components. Editors can own routed file types; Extensions launch as standalone tools. "
            "Suite Pythoine manages both without embedding their functionality."
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        self.summary = QLabel()
        root.addWidget(self.summary)

        self.drop_bar = DropBar(self)
        self.drop_bar.payload_dropped.connect(self.drop_payload_requested)
        self.drop_bar.url_choice_selected.connect(self.url_choice_requested)
        root.addWidget(self.drop_bar)

        controls = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search components or formats…")
        self.search.setClearButtonEnabled(True)
        controls.addWidget(self.search, 1)

        self.sort = QComboBox()
        self.sort.addItem("Title (A–Z)", "title_az")
        self.sort.addItem("Title (Z–A)", "title_za")
        self.sort.addItem("Recently Changed", "modified")
        controls.addWidget(self.sort)

        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh_requested)
        controls.addWidget(refresh)
        root.addLayout(controls)

        self.pages = QStackedWidget()
        root.addWidget(self.pages, 1)

        actions = QHBoxLayout()
        actions.addStretch(1)
        launch = QPushButton("Launch…")
        launch.clicked.connect(self.launch_prompt_requested.emit)
        actions.addWidget(launch)
        new_file = QPushButton("New File…")
        new_file.clicked.connect(self.new_file_requested.emit)
        actions.addWidget(new_file)
        open_file = QPushButton("Open File…")
        open_file.clicked.connect(self.open_file_requested.emit)
        actions.addWidget(open_file)
        install_editor = QPushButton("Install Component…")
        install_editor.clicked.connect(self.install_editor_requested.emit)
        actions.addWidget(install_editor)
        installed_applications = QPushButton("Installed Applications")
        installed_applications.clicked.connect(self.installed_applications_requested.emit)
        actions.addWidget(installed_applications)
        details = QPushButton("Details")
        details.clicked.connect(self.suite_details_requested.emit)
        actions.addWidget(details)
        root.addLayout(actions)

        self.list_scroll = QScrollArea()
        self.list_scroll.setWidgetResizable(True)
        self.pages.addWidget(self.list_scroll)

        self.grid_scroll = QScrollArea()
        self.grid_scroll.setWidgetResizable(True)
        self.pages.addWidget(self.grid_scroll)
        for scroll in (self.list_scroll, self.grid_scroll):
            QScroller.grabGesture(scroll.viewport(), QScroller.ScrollerGestureType.TouchGesture)

        self.search.textChanged.connect(self._search_now)
        self.sort.currentIndexChanged.connect(self._sort_now)
        self._replace_card_bodies([])

    def set_components(self, components: list[EditorEntry]) -> None:
        self._components = list(components)
        self._apply()

    def set_editors(self, editors: list[EditorEntry]) -> None:
        # Compatibility alias for older call sites/tests.
        self.set_components(editors)

    def set_search_text(self, text: str) -> None:
        if self.search.text() != text:
            self.search.blockSignals(True)
            self.search.setText(text)
            self.search.blockSignals(False)
        self._apply()

    def set_sort_mode(self, mode: str) -> None:
        index = self.sort.findData(mode)
        if index < 0:
            index = self.sort.findData("title_az")
        self.sort.blockSignals(True)
        self.sort.setCurrentIndex(max(0, index))
        self.sort.blockSignals(False)
        self._sort_mode = str(self.sort.currentData())
        self._apply()

    def set_view_mode(self, mode: str) -> None:
        self._view_mode = "grid" if mode == "grid" else "list"
        self.pages.setCurrentIndex(1 if self._view_mode == "grid" else 0)

    def view_mode(self) -> str:
        return self._view_mode

    def set_show_icons(self, visible: bool) -> None:
        visible = bool(visible)
        if self._show_icons != visible:
            self._show_icons = visible
            self._apply()

    def set_drop_bar_visible(self, visible: bool) -> None:
        self.drop_bar.setVisible(bool(visible))

    def show_url_choices(self, url: str, choices: list[tuple[str, str]]) -> None:
        self.drop_bar.show_url_choices(url, choices)

    def _search_now(self, text: str) -> None:
        self._apply()
        self.search_changed.emit(text)

    def _sort_now(self, _index: int) -> None:
        self._sort_mode = str(self.sort.currentData())
        self._apply()
        self.sort_changed.emit(self._sort_mode)

    def _wire_card(self, card: EditorCard) -> None:
        card.launch_requested.connect(self.launch_requested)
        card.new_requested.connect(self.new_requested)
        card.open_requested.connect(self.open_requested)
        card.details_requested.connect(self.details_requested)

    @staticmethod
    def _heading(text: str, parent: QWidget) -> QLabel:
        heading = QLabel(text, parent)
        font = heading.font()
        font.setBold(True)
        font.setPointSize(max(font.pointSize() + 2, 11))
        heading.setFont(font)
        return heading

    @staticmethod
    def _groups(components: list[EditorEntry]) -> tuple[tuple[str, list[EditorEntry]], ...]:
        editors = [item for item in components if component_kind(item) == "editor"]
        readers = [item for item in components if component_kind(item) == "reader"]
        extensions = [item for item in components if component_kind(item) == "extension"]
        groups = []
        if editors:
            groups.append(("Editors", editors))
        if readers:
            groups.append(("Readers", readers))
        if extensions:
            groups.append(("Extensions", extensions))
        return tuple(groups)

    def _new_list_body(self, components: list[EditorEntry]) -> QWidget:
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        for group_name, members in self._groups(components):
            layout.addWidget(self._heading(group_name, body))
            for component in members:
                card = EditorCard(component, grid=False, show_icon=self._show_icons, parent=body)
                self._wire_card(card)
                layout.addWidget(card)
            layout.addSpacing(6)
        layout.addStretch(1)
        return body

    def _new_grid_body(self, components: list[EditorEntry]) -> QWidget:
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        for group_name, members in self._groups(components):
            layout.addWidget(self._heading(group_name, body))
            flow_host = FlowContainer(body)
            for component in members:
                card = EditorCard(component, grid=True, show_icon=self._show_icons, parent=flow_host)
                self._wire_card(card)
                flow_host.flow.addWidget(card)
            flow_host.setMinimumHeight(190)
            layout.addWidget(flow_host)
            layout.addSpacing(6)
        layout.addStretch(1)
        return body

    @staticmethod
    def _swap_scroll_widget(scroll: QScrollArea, body: QWidget) -> None:
        old = scroll.takeWidget()
        scroll.setWidget(body)
        if old is not None:
            old.hide()
            old.deleteLater()

    def _replace_card_bodies(self, components: list[EditorEntry]) -> None:
        self._swap_scroll_widget(self.list_scroll, self._new_list_body(components))
        self._swap_scroll_widget(self.grid_scroll, self._new_grid_body(components))

    def _apply(self) -> None:
        matched = filter_and_sort_editors(self._components, self.search.text(), self._sort_mode)
        self._replace_card_bodies(matched)
        total = len(self._components)
        editor_count = sum(1 for item in self._components if component_kind(item) == "editor")
        reader_count = sum(1 for item in self._components if component_kind(item) == "reader")
        extension_count = sum(1 for item in self._components if component_kind(item) == "extension")
        self.summary.setText(
            f"Showing {len(matched)} of {total} component{'s' if total != 1 else ''} "
            f"({editor_count} editor{'s' if editor_count != 1 else ''}, {reader_count} reader{'s' if reader_count != 1 else ''}, "
            f"{extension_count} extension{'s' if extension_count != 1 else ''})"
        )
        if total == 0:
            self.summary.setText(
                "No components are loaded yet. Drop a recognized component ZIP/AppImage here or copy one into the Components folder:\n"
                f"{self.editors_root}"
            )
        elif not matched:
            self.summary.setText("No components match the current search.")
