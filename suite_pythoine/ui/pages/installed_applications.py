"""Installed Applications presentation (Wave 1 x1.3).

Only UI construction lives here. SuiteWindow retains inventory discovery, state,
layout persistence, navigation, running-asset filtering and removal operations.
The two shell-owned rendering resources are injected to avoid cyclic imports.
"""
from __future__ import annotations

import html
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPushButton, QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from ... import APP_NAME
from ...versioning import version_sort_key
from ..helpers import _format_timestamp, _human_size
from ..widgets.inventory import AssetSelectionHeader, SortableTableItem

if TYPE_CHECKING:
    from ...app import SuiteWindow


def build_installed_applications_page(
    self: SuiteWindow,
    *,
    APP_ICON_PATH: Path,
    _style_destructive_button: Callable[[QPushButton], None],
) -> QWidget:
    """Render the existing table, search and transient removal selector unchanged."""
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(28, 28, 28, 28)
    layout.setSpacing(12)

    # Mirror the Hub Details identity header, using the same logo and type.
    self._add_details_identity_header(
        layout,
        self.suite_entry.name if self.suite_entry is not None else APP_NAME,
        "hub",
        self.suite_entry.icon if self.suite_entry is not None else APP_ICON_PATH,
    )

    records = self._inventory_records()
    # The display list filters only the exact running Suite asset; the full
    # list is retained for preference-cleanup semantics so a surviving hidden
    # running asset is never mistaken for a fully removed application.
    asset_records = self._asset_inventory_records()
    all_asset_records = self._asset_inventory_records(include_running_suite=True)
    total_size = sum(int(record.get("size", 0)) for record in records)
    component_count = len({str(record.get("component_id")) for record in records})
    summary = QLabel()
    summary.setTextFormat(Qt.TextFormat.RichText)
    summary.setWordWrap(True)
    summary.setOpenExternalLinks(False)
    summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
    active_line = "Active: Not selected"
    if self.suite_entry is not None:
        active_line = self._editor_summary_text(self.suite_entry).splitlines()[0]
    summary.setText(
        f"{html.escape(active_line)}<br>"
        f"Installed Applications shows {component_count} application{'s' if component_count != 1 else ''}, "
        f"{len(records)} Portable/AppImage asset{'s' if len(records) != 1 else ''}, {_human_size(total_size)} total. "
        "Recovery assets become visible in Remove Assets mode. "
        "<a href=\"guidance\">Detailed guidance…</a>"
    )
    summary.linkActivated.connect(lambda _link: self._show_installed_applications_guidance())
    layout.addWidget(summary)

    # Match Hub Details: Settings actions remain stable. Install Application
    # deliberately stays in its established location.
    settings_heading = QLabel("Settings")
    settings_font = settings_heading.font()
    settings_font.setBold(True)
    settings_font.setPointSize(max(settings_font.pointSize() + 1, 10))
    settings_heading.setFont(settings_font)
    layout.addWidget(settings_heading)
    inventory_row = QHBoxLayout()
    hub_details = QPushButton("Hub Details")
    hub_details.clicked.connect(self.show_suite_details)
    inventory_row.addWidget(hub_details)
    refresh = QPushButton("Refresh Inventory")
    refresh.clicked.connect(lambda: self.refresh_editors(automatic=True))
    inventory_row.addWidget(refresh)
    open_folder = QPushButton("Open Applications Folder")
    open_folder.setEnabled(self.editors_root.is_dir())
    open_folder.clicked.connect(lambda: self.launcher.open_path(self.editors_root))
    inventory_row.addWidget(open_folder)
    install_component = QPushButton("Install Application…")
    install_component.clicked.connect(self.install_editor_prompt)
    inventory_row.addWidget(install_component)
    inventory_row.addStretch(1)
    layout.addLayout(inventory_row)

    inventory_search_row = QHBoxLayout()
    inventory_heading = QLabel("Installed Applications")
    inventory_font = inventory_heading.font()
    inventory_font.setBold(True)
    inventory_font.setPointSize(max(inventory_font.pointSize() + 1, 10))
    inventory_heading.setFont(inventory_font)
    inventory_search_row.addWidget(inventory_heading)
    inventory_search_row.addStretch(1)
    version_filter = QLineEdit()
    version_filter.setPlaceholderText("Search installed applications…")
    version_filter.setAccessibleName("Search installed applications")
    version_filter.setClearButtonEnabled(True)
    version_filter.setMaximumWidth(220)
    inventory_search_row.addWidget(version_filter)
    remove_assets_button = QPushButton("Remove Assets…")
    inventory_search_row.addWidget(remove_assets_button)
    remove_selected_button = QPushButton("Remove Selected…")
    _style_destructive_button(remove_selected_button)
    cancel_assets_button = QPushButton("Cancel")
    for button in (remove_selected_button, cancel_assets_button):
        button.setVisible(False)
        inventory_search_row.addWidget(button)
    layout.addLayout(inventory_search_row)

    # One table serves both normal Installed Applications and Remove Assets.
    # Logical columns 0..7 are the user's persistent normal layout; logical
    # column 8 is a transient checkbox column that is hidden normally and
    # always moved to the first visual position during Remove Assets mode.
    table = QTableWidget(0, 9)
    selection_header = AssetSelectionHeader(Qt.Orientation.Horizontal, table)
    selection_header.set_selection_section(8)
    table.setHorizontalHeader(selection_header)
    table.setHorizontalHeaderLabels([*self._inventory_column_labels(), ""])
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.setSortingEnabled(False)
    table.verticalHeader().setVisible(False)
    table.setWordWrap(False)
    table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    layout.addWidget(table, 1)

    def text_item(text: str, sort_value=None) -> SortableTableItem:
        item = SortableTableItem(text)
        item.setData(Qt.ItemDataRole.UserRole, text.casefold() if sort_value is None else sort_value)
        return item

    record_role = int(Qt.ItemDataRole.UserRole) + 1
    mode = {"assets": False, "repositioning": False}

    def add_quick_actions(row: int, record: dict, *, recovery: bool = False) -> None:
        action_widget = QWidget()
        action_layout = QHBoxLayout(action_widget)
        action_layout.setContentsMargins(2, 1, 2, 1)
        action_layout.setSpacing(4)
        if not recovery:
            record_editor = record.get("editor")
            launch = QPushButton("Launch")
            launch.clicked.connect(lambda _checked=False, item=record: self._inventory_launch_runtime(item))
            action_layout.addWidget(launch)
        app_page = QPushButton("App Page")
        app_page.clicked.connect(lambda _checked=False, item=record: self._inventory_open_component(item))
        action_layout.addWidget(app_page)
        action_layout.addStretch(1)
        table.setCellWidget(row, 7, action_widget)

    def current_sort() -> tuple[int, Qt.SortOrder]:
        header = table.horizontalHeader()
        logical = header.sortIndicatorSection()
        if logical < 0 or logical > 7:
            logical = 0
        return logical, header.sortIndicatorOrder()

    def populate_normal() -> None:
        sort_column, sort_order = current_sort()
        table.setSortingEnabled(False)
        table.clearContents()
        table.setRowCount(0)
        for record in records:
            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, 0, text_item(str(record["name"])))
            table.setItem(row, 1, text_item(str(record["version"]), version_sort_key(str(record["version"]))))
            table.setItem(row, 2, text_item(str(record["runtime"])))
            table.setItem(row, 3, text_item("Yes" if record["active"] else "No", 1 if record["active"] else 0))
            table.setItem(row, 4, text_item(_human_size(int(record["size"])), int(record["size"])))
            table.setItem(row, 5, text_item(_format_timestamp(float(record["timestamp"])), float(record["timestamp"])))
            location_text = " | ".join(str(path) for path in record["locations"]) or "—"
            location_item = text_item(location_text)
            location_item.setToolTip(location_text)
            table.setItem(row, 6, location_item)
            add_quick_actions(row, record)
        table.setColumnHidden(8, True)
        table.setSortingEnabled(True)
        table.sortItems(sort_column, sort_order)

    def populate_assets() -> None:
        sort_column, sort_order = current_sort()
        table.setSortingEnabled(False)
        table.clearContents()
        table.setRowCount(0)
        for record_index, record in enumerate(asset_records):
            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, 0, text_item(str(record["name"])))
            table.setItem(row, 1, text_item(str(record["version"]), version_sort_key(str(record["version"]))))
            table.setItem(row, 2, text_item(str(record["asset"])))
            active_text = "—" if record["asset"] == "Recovery" else ("Yes" if record["active"] else "No")
            table.setItem(row, 3, text_item(active_text, 1 if record["active"] else 0))
            table.setItem(row, 4, text_item(_human_size(int(record["size"])), int(record["size"])))
            table.setItem(row, 5, text_item(_format_timestamp(float(record["timestamp"])), float(record["timestamp"])))
            location_text = " | ".join(str(path) for path in record["locations"]) or "—"
            location_item = text_item(location_text)
            location_item.setToolTip(location_text)
            table.setItem(row, 6, location_item)
            add_quick_actions(row, record, recovery=record["asset"] == "Recovery")
            selection = QTableWidgetItem()
            selection.setFlags(selection.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            selection.setCheckState(Qt.CheckState.Unchecked)
            selection.setData(record_role, record_index)
            selection.setToolTip(f"Select {record['name']} {record['version']} {record['asset']} for removal")
            table.setItem(row, 8, selection)
        table.setColumnHidden(8, False)
        table.setColumnWidth(8, 42)
        table.setSortingEnabled(True)
        table.sortItems(sort_column, sort_order)

    header = table.horizontalHeader()
    header.setSectionsMovable(True)
    header.setSectionsClickable(True)
    header.setSortIndicatorShown(True)
    # A fresh Installed Applications page always starts in the sane,
    # predictable Application A–Z order. User header clicks then own the
    # sort state for the lifetime of this page, including Remove Assets.
    header.setSortIndicator(0, Qt.SortOrder.AscendingOrder)
    header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    header.setSectionResizeMode(8, QHeaderView.ResizeMode.Fixed)
    header.setStretchLastSection(True)
    header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    header.customContextMenuRequested.connect(lambda pos, target=table: self._inventory_header_context_menu(target, pos))
    header.sectionMoved.connect(self._schedule_inventory_table_layout_save)
    header.sectionResized.connect(self._schedule_inventory_table_layout_save)
    self.inventory_table = table
    self._restore_inventory_table_layout(table)
    table.setColumnHidden(8, True)
    populate_normal()

    def ensure_selection_first(*_args) -> None:
        if not mode["assets"] or mode["repositioning"]:
            return
        visual = header.visualIndex(8)
        if visual == 0:
            return
        mode["repositioning"] = True
        try:
            header.moveSection(visual, 0)
        finally:
            mode["repositioning"] = False

    header.sectionMoved.connect(lambda *_args: QTimer.singleShot(0, ensure_selection_first))

    filter_timer = QTimer(version_filter)
    filter_timer.setSingleShot(True)
    filter_timer.setInterval(150)

    def sync_selection_header() -> None:
        if not mode["assets"]:
            selection_header.set_selection_state(Qt.CheckState.Unchecked)
            return
        states: list[Qt.CheckState] = []
        for row in range(table.rowCount()):
            if table.isRowHidden(row):
                continue
            item = table.item(row, 8)
            if item is not None and item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                states.append(item.checkState())
        if states and all(state == Qt.CheckState.Checked for state in states):
            state = Qt.CheckState.Checked
        elif any(state == Qt.CheckState.Checked for state in states):
            state = Qt.CheckState.PartiallyChecked
        else:
            state = Qt.CheckState.Unchecked
        selection_header.set_selection_state(state)

    def apply_filter() -> None:
        query = version_filter.text().strip().casefold()
        # Search remains the same table contract in either mode.
        for row in range(table.rowCount()):
            searchable = []
            for column in (0, 1, 2, 3):
                item = table.item(row, column)
                searchable.append(item.text().casefold() if item is not None else "")
            table.setRowHidden(row, bool(query and not any(query in value for value in searchable)))
        sync_selection_header()

    def schedule_filter(text: str) -> None:
        filter_timer.stop()
        if not text.strip():
            apply_filter()
        else:
            filter_timer.start()

    def set_asset_controls(active: bool) -> None:
        active = bool(active)
        if active == mode["assets"]:
            return
        if active:
            self._save_inventory_table_layout()
            mode["assets"] = True
            populate_assets()
            ensure_selection_first()
            table.setColumnWidth(8, 42)
            # Do not let Qt/Breeze invent a current-cell focus decoration
            # on the first checkbox row when the transient column appears.
            table.clearSelection()
            table.setCurrentCell(-1, -1)
            # Keep keyboard focus on the mode controls/search instead of
            # allowing Breeze to paint an arbitrary first-row current-cell
            # capsule after the transient checkbox column is inserted.
            version_filter.setFocus(Qt.FocusReason.OtherFocusReason)
        else:
            mode["assets"] = False
            table.setColumnHidden(8, True)
            populate_normal()
            self._restore_inventory_table_layout(table)
            table.setColumnHidden(8, True)
        remove_assets_button.setVisible(not active)
        for button in (remove_selected_button, cancel_assets_button):
            button.setVisible(active)
        apply_filter()

    def set_all_assets(checked: bool) -> None:
        if not mode["assets"]:
            return
        for row in range(table.rowCount()):
            if table.isRowHidden(row):
                continue
            item = table.item(row, 8)
            if item is not None and item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        sync_selection_header()

    def selection_item_changed(item: QTableWidgetItem) -> None:
        if mode["assets"] and item.column() == 8:
            sync_selection_header()

    def selected_asset_records() -> list[dict]:
        selected: list[dict] = []
        if not mode["assets"]:
            return selected
        for row in range(table.rowCount()):
            item = table.item(row, 8)
            if item is None or item.checkState() != Qt.CheckState.Checked:
                continue
            index = item.data(record_role)
            if isinstance(index, int) and 0 <= index < len(asset_records):
                selected.append(asset_records[index])
        return selected

    remove_assets_button.clicked.connect(lambda: set_asset_controls(True))
    cancel_assets_button.clicked.connect(lambda: set_asset_controls(False))
    selection_header.toggleSelectionRequested.connect(set_all_assets)
    table.itemChanged.connect(selection_item_changed)
    remove_selected_button.clicked.connect(
        lambda: self._remove_asset_records(selected_asset_records(), all_asset_records)
    )
    version_filter.textChanged.connect(schedule_filter)
    filter_timer.timeout.connect(apply_filter)
    table.model().layoutChanged.connect(lambda *_args: apply_filter())
    self._version_filters[page] = version_filter

    return page

