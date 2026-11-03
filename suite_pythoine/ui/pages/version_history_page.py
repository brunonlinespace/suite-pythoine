"""Version History presentation extracted in Suite Pythoine 1.0.0-x1.4.

The selected-version frame continues to dispatch actions to SuiteWindow.
Lifecycle/removal/version selection ownership is not migrated here.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QAbstractItemView, QFrame, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget)
from ... import __version__
from ...registry import EditorEntry, EditorVersionInfo
from ...catalogue.component_policy import is_backend_only_component, is_hub
from ...catalogue.component_catalog import profile_for_id
from ...installer import find_appimage_build_script
from ...storage_layout import recovery_root
from ...recovery import recovery_available
from ...version_history import build_version_history_rows
if TYPE_CHECKING:
    from ...app import SuiteWindow

def build_version_management_frame(self: SuiteWindow, editor: EditorEntry, version_info: EditorVersionInfo) -> QFrame:
    version_frame = QFrame()
    version_frame.setFrameShape(QFrame.Shape.StyledPanel)
    version_layout = QVBoxLayout(version_frame)
    version_layout.setContentsMargins(10, 8, 10, 8)
    labels = [version_info.version]
    if version_info.version == editor.active_version:
        labels.append("Active")
    if version_info.desktop_integrated or version_info.version == editor.desktop_version:
        labels.append("Desktop integrated")
    version_title = QLabel(" — ".join(labels))
    title_font = version_title.font()
    title_font.setBold(True)
    version_title.setFont(title_font)
    version_layout.addWidget(version_title)
    recovery_dir = version_info.recovery_dir or recovery_root(self.editors_root, editor.name, version_info.version)
    has_recovery = recovery_available(recovery_dir)
    state = QLabel(
        f"Portable: {'Yes' if version_info.has_portable else 'No'}   "
        f"AppImage: {'Yes' if version_info.has_appimage else 'No'}   "
        f"Recovery: {'Available' if has_recovery else 'Unavailable'}   "
        f"Desktop: {'Active' if version_info.desktop_integrated else 'No'}"
    )
    state.setTextFormat(Qt.TextFormat.PlainText)
    version_layout.addWidget(state)
    if version_info.legacy:
        version_layout.addWidget(QLabel('Legacy identification: version established using compatibility fallback metadata.'))
    if version_info.validation_issue:
        warning = QLabel('Identity/version mismatch — ' + version_info.validation_issue)
        warning.setWordWrap(True)
        version_layout.addWidget(warning)
    # Each action belongs to the exact version shown above it.  Keeping
    # version/Portable/AppImage controls in three distinct rows also avoids
    # conflating the active runtime with the component-wide Details actions.
    def add_action_row(label: str | None, buttons: tuple[QPushButton, ...]) -> None:
        if label:
            heading = QLabel(label)
            heading_font = heading.font()
            heading_font.setBold(True)
            heading.setFont(heading_font)
            version_layout.addWidget(heading)
        row = QHBoxLayout()
        for button in buttons:
            row.addWidget(button)
        row.addStretch(1)
        version_layout.addLayout(row)

    launch_portable = QPushButton("Launch Portable")
    launch_portable.setEnabled(version_info.has_portable and not version_info.validation_issue)
    launch_portable.setVisible(not is_backend_only_component(editor))
    launch_portable.clicked.connect(lambda _checked=False, item=version_info: self.launch_editor_version(editor, item, "portable"))
    launch_appimage = QPushButton("Launch AppImage")
    launch_appimage.setEnabled(version_info.has_appimage and not version_info.validation_issue)
    launch_appimage.setVisible(not is_backend_only_component(editor))
    launch_appimage.clicked.connect(lambda _checked=False, item=version_info: self.launch_editor_version(editor, item, "appimage"))

    portable_folder = version_info.portable_root
    open_portable = QPushButton("Open Portable Folder")
    open_portable.setEnabled(bool(portable_folder and portable_folder.is_dir() and not portable_folder.is_symlink()))
    if portable_folder is not None:
        open_portable.clicked.connect(
            lambda _checked=False, target=portable_folder: self.launcher.open_path(target)
        )
    uninstall_portable = QPushButton("Remove Portable")
    uninstall_portable.setEnabled(version_info.has_portable and not version_info.validation_issue)
    uninstall_portable.setToolTip("Remove only this exact Portable runtime; AppImage and Recovery remain untouched. An active or running runtime is protected.")
    uninstall_portable.clicked.connect(
        lambda _checked=False, target=version_info: self.remove_portable_runtime(editor, target)
    )

    appimage_folder = version_info.appimage_path.parent if version_info.appimage_path is not None else None
    open_appimage = QPushButton("Open AppImage Folder")
    open_appimage.setEnabled(bool(appimage_folder and appimage_folder.is_dir() and not appimage_folder.is_symlink()))
    if appimage_folder is not None:
        open_appimage.clicked.connect(
            lambda _checked=False, target=appimage_folder: self.launcher.open_path(target)
        )
    uninstall_appimage = QPushButton("Remove AppImage")
    uninstall_appimage.setEnabled(
        sys.platform.startswith("linux") and version_info.has_appimage and not version_info.validation_issue
    )
    uninstall_appimage.setToolTip("Remove only this exact AppImage runtime; Portable and Recovery remain untouched. An active or running runtime is protected.")
    uninstall_appimage.clicked.connect(
        lambda _checked=False, target=version_info: self.uninstall_appimage_runtime(editor, target)
    )

    rebuild = bool(version_info.has_appimage)
    build_appimage = QPushButton("Rebuild AppImage…" if rebuild else "Build AppImage…")
    builder = (find_appimage_build_script(portable_folder)
               if version_info.has_portable and portable_folder is not None else None)
    running_suite_appimage_rebuild = bool(
        is_hub(editor) and rebuild and version_info.version == __version__
        and self.runtime.running_as_appimage
    )
    build_enabled = bool(
        sys.platform.startswith("linux") and builder is not None
        and not running_suite_appimage_rebuild and not version_info.validation_issue
    )
    build_appimage.setEnabled(build_enabled)
    if not build_enabled:
        if running_suite_appimage_rebuild:
            build_appimage.setToolTip("The currently running Suite AppImage cannot rebuild itself. Launch another runtime first.")
        elif not sys.platform.startswith("linux"):
            build_appimage.setToolTip("Managed AppImage building is available only on Linux.")
        elif version_info.validation_issue:
            build_appimage.setToolTip("Resolve this exact version's identity/validation problem before building.")
        else:
            build_appimage.setToolTip("No supported AppImage builder was found inside this exact Portable version.")
    build_appimage.clicked.connect(
        lambda _checked=False, target=version_info: self.build_appimage_from_portable(editor, target)
    )
    build_appimage.setProperty("suite_developer_only", True)
    build_appimage.setVisible(self.developer_config.enabled)

    restore_portable = QPushButton("Restore Portable…")
    running_suite_portable = bool(
        is_hub(editor)
        and version_info.version == __version__
        and not self.runtime.running_as_appimage
    )
    restore_portable.setEnabled(has_recovery and not version_info.validation_issue)
    if not has_recovery:
        restore_portable.setToolTip("No managed Recovery archive is available for this exact version.")
    elif running_suite_portable:
        restore_portable.setToolTip("Restore this running Hub Portable through the safe post-exit self-restore handoff.")
    restore_portable.clicked.connect(
        lambda _checked=False, target=version_info: self.restore_portable_from_recovery_action(editor, target)
    )
    make_active = QPushButton("Make Active")
    make_active.setEnabled(
        not version_info.validation_issue and version_info.version != editor.active_version
        and (version_info.has_portable or version_info.has_appimage)
    )
    make_active.clicked.connect(lambda _checked=False, item=version_info: self.make_version_active(editor, item))
    remove_version = QPushButton("Uninstall Version…")
    remove_version.setEnabled(not version_info.validation_issue)
    remove_version.clicked.connect(lambda _checked=False, item=version_info: self.remove_editor_version(editor, item))
    open_folder = QPushButton("Open Version Folder")
    folder: Path | None = None
    if version_info.portable_root is not None and version_info.portable_root.is_dir():
        folder = version_info.portable_root.parent
    elif version_info.appimage_path is not None:
        folder = version_info.appimage_path.parent.parent
    elif has_recovery:
        folder = recovery_dir.parent
    open_folder.setEnabled(folder is not None)
    if folder is not None:
        open_folder.clicked.connect(lambda _checked=False, target=folder: self.launcher.open_path(target))
    add_action_row(None, (make_active, open_folder, remove_version))
    add_action_row("Portable Runtime", (launch_portable, open_portable, restore_portable, uninstall_portable))
    add_action_row("AppImage Runtime", (launch_appimage, open_appimage, build_appimage, uninstall_appimage))
    return version_frame


def build_version_history_page(self: SuiteWindow, editor: EditorEntry, *, preferred_version: str | None = None) -> QWidget:
    page = QScrollArea()
    page.setWidgetResizable(True)
    content = QWidget()
    page.setWidget(content)
    layout = QVBoxLayout(content)
    layout.setContentsMargins(28, 28, 28, 28)
    layout.setSpacing(12)

    profile = profile_for_id(editor.editor_id)
    lifecycle = profile.lifecycle if profile is not None else "current"
    self._add_details_identity_header(layout, editor.name, editor.component_kind, editor.icon, lifecycle=lifecycle)
    heading = QLabel("Version History")
    heading_font = heading.font()
    heading_font.setBold(True)
    heading_font.setPointSize(max(heading_font.pointSize() + 3, 13))
    heading.setFont(heading_font)
    layout.addWidget(heading)

    guidance = QLabel(
        "Browse installed versions here. Select one row to expose the existing exact-version management controls. "
        "Only the selected version's management panel is constructed."
    )
    guidance.setWordWrap(True)
    layout.addWidget(guidance)

    top_row = QHBoxLayout()
    back_button = QPushButton(f"Back to {editor.name}")
    if is_hub(editor):
        back_button.clicked.connect(self.show_suite_details)
    else:
        back_button.clicked.connect(lambda _checked=False, target=editor: self.show_editor_details(target))
    top_row.addWidget(back_button)
    top_row.addStretch(1)
    version_filter = QLineEdit()
    version_filter.setPlaceholderText("Filter versions…")
    version_filter.setAccessibleName("Filter versions")
    version_filter.setClearButtonEnabled(True)
    version_filter.setMaximumWidth(220)
    top_row.addWidget(version_filter)
    layout.addLayout(top_row)

    rows = build_version_history_rows(editor, self.editors_root)
    table = QTableWidget(len(rows), 5)
    table.setObjectName("versionHistoryTable")
    table.setHorizontalHeaderLabels(["Version", "Portable", "AppImage", "Recovery", "State"])
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
    table.setMinimumHeight(min(420, max(150, 42 + 31 * min(len(rows), 10))))

    version_role = Qt.ItemDataRole.UserRole
    for row_index, row in enumerate(rows):
        values = (
            row.version,
            "Yes" if row.has_portable else "No",
            "Yes" if row.has_appimage else "No",
            "Available" if row.has_recovery else "No",
            row.state_text,
        )
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setData(version_role, row.version)
            if row.validation_issue:
                item.setToolTip(row.validation_issue)
            table.setItem(row_index, column, item)
    layout.addWidget(table)

    selection_heading = QLabel("Selected Version")
    selection_font = selection_heading.font()
    selection_font.setBold(True)
    selection_font.setPointSize(max(selection_font.pointSize() + 1, 10))
    selection_heading.setFont(selection_font)
    layout.addWidget(selection_heading)
    action_host = QVBoxLayout()
    layout.addLayout(action_host)
    selected_frame: QFrame | None = None

    def clear_action_host() -> None:
        nonlocal selected_frame
        if selected_frame is not None:
            action_host.removeWidget(selected_frame)
            selected_frame.deleteLater()
            selected_frame = None

    def selected_version_info() -> EditorVersionInfo | None:
        row_index = table.currentRow()
        if row_index < 0:
            return None
        item = table.item(row_index, 0)
        version = item.data(version_role) if item is not None else None
        if not isinstance(version, str):
            return None
        return next((candidate for candidate in editor.versions if candidate.version == version), None)

    def render_selected() -> None:
        nonlocal selected_frame
        clear_action_host()
        selected = selected_version_info()
        page.setProperty("suite_selected_version", selected.version if selected is not None else None)
        if selected is None:
            note = QFrame()
            note_layout = QVBoxLayout(note)
            note_layout.addWidget(QLabel("Select a version to manage it."))
            selected_frame = note
        else:
            selected_frame = self._version_management_frame(editor, selected)
        action_host.addWidget(selected_frame)

    def first_visible_row() -> int:
        for row_index in range(table.rowCount()):
            if not table.isRowHidden(row_index):
                return row_index
        return -1

    filter_timer = QTimer(version_filter)
    filter_timer.setSingleShot(True)
    filter_timer.setInterval(150)

    def apply_filter() -> None:
        query = version_filter.text().strip().casefold()
        current = table.currentRow()
        for row_index in range(table.rowCount()):
            item = table.item(row_index, 0)
            version = item.text().casefold() if item is not None else ""
            table.setRowHidden(row_index, bool(query and query not in version))
        if current < 0 or table.isRowHidden(current):
            replacement = first_visible_row()
            if replacement >= 0:
                table.selectRow(replacement)
            else:
                table.clearSelection()
                render_selected()

    def schedule_filter(value: str) -> None:
        filter_timer.stop()
        if not value.strip():
            apply_filter()
        else:
            filter_timer.start()

    version_filter.textChanged.connect(schedule_filter)
    filter_timer.timeout.connect(apply_filter)
    table.itemSelectionChanged.connect(render_selected)
    self._version_filters[page] = version_filter

    initial_row = 0 if rows else -1
    for target_version in (preferred_version, editor.active_version):
        if not target_version:
            continue
        match = next((row_index for row_index, row in enumerate(rows) if row.version == target_version), None)
        if match is not None:
            initial_row = match
            break
    if initial_row >= 0:
        table.selectRow(initial_row)
    else:
        render_selected()
    layout.addStretch(1)
    return page


