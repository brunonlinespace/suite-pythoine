"""Application Page presentation extracted in Suite Pythoine 1.0.0-x1.4.

Keep SuiteWindow orchestration/actions as owners. These builders construct only the
existing widgets and connect their callbacks to the original SuiteWindow.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Callable
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget
from ...registry import EditorEntry, EditorVersionInfo
from ...catalogue.component_policy import is_backend_only_component
from ...catalogue.component_catalog import profile_for_id
from ...storage_layout import editor_root, is_within, recovery_root
from ...recovery import recovery_available
if TYPE_CHECKING:
    from ...app import SuiteWindow

def add_details_identity_header(layout: QVBoxLayout, name: str, kind: str, icon_path: Path | None, *, lifecycle: str = "current", APP_ICON_PATH: Path) -> None:
    """Identical logo/name/type header for Details and Installed Applications."""
    title_row = QHBoxLayout()
    if kind == "hub" and (icon_path is None or not icon_path.is_file()):
        icon_path = APP_ICON_PATH
    if icon_path and icon_path.is_file():
        icon = QLabel()
        icon.setPixmap(QIcon(str(icon_path)).pixmap(56, 56))
        title_row.addWidget(icon)
    title = QLabel(name)
    title.setTextFormat(Qt.TextFormat.PlainText)
    font = title.font()
    font.setPointSize(max(font.pointSize() + 6, 16))
    font.setBold(True)
    title.setFont(font)
    title_block = QVBoxLayout()
    title_block.setSpacing(2)
    title_block.addWidget(title)
    kind_label = {"hub": "Hub", "editor": "Editor", "reader": "Reader", "extension": "Extension"}.get(
        kind, kind.title())
    type_subtitle = QLabel(f"{kind_label} · Legacy" if lifecycle == "legacy" else kind_label)
    type_subtitle.setTextFormat(Qt.TextFormat.PlainText)
    type_font = type_subtitle.font(); type_font.setPointSize(max(type_font.pointSize() - 1, 9))
    type_subtitle.setFont(type_font)
    title_block.addWidget(type_subtitle)
    title_row.addLayout(title_block)
    title_row.addStretch(1)
    layout.addLayout(title_row)


def build_current_version_frame(self: SuiteWindow, editor: EditorEntry, version_info: EditorVersionInfo) -> QFrame:
    """Compact current-version control surface; full administration remains in Version History."""
    frame = QFrame()
    frame.setFrameShape(QFrame.Shape.StyledPanel)
    body = QVBoxLayout(frame)
    body.setContentsMargins(10, 8, 10, 8)

    labels = [version_info.version, "Active"]
    if version_info.desktop_integrated or (
            editor.desktop_issue == "ready" and version_info.version == editor.desktop_version):
        labels.append("Desktop integrated")
    title = QLabel(" — ".join(labels))
    title_font = title.font(); title_font.setBold(True)
    title.setFont(title_font)
    body.addWidget(title)

    runtime = QLabel(f"Active runtime: {self._current_version_runtime_text(editor, version_info)}")
    runtime.setTextFormat(Qt.TextFormat.PlainText)
    body.addWidget(runtime)
    if version_info.validation_issue:
        warning = QLabel("Identity/version mismatch — " + version_info.validation_issue)
        warning.setWordWrap(True)
        body.addWidget(warning)
    elif version_info.legacy:
        legacy = QLabel("Legacy identification: version established using compatibility fallback metadata.")
        legacy.setWordWrap(True)
        body.addWidget(legacy)

    def add_runtime_row(label: str, status: str, buttons: tuple[QPushButton, ...]) -> None:
        row = QHBoxLayout()
        heading = QLabel(f"{label}: {status}")
        heading_font = heading.font(); heading_font.setBold(True)
        heading.setFont(heading_font)
        row.addWidget(heading)
        row.addStretch(1)
        for button in buttons:
            row.addWidget(button)
        body.addLayout(row)

    launch_portable = QPushButton("Launch")
    launch_portable.setEnabled(version_info.has_portable and not version_info.validation_issue)
    launch_portable.setVisible(not is_backend_only_component(editor))
    launch_portable.setToolTip("Launch the current version's Portable runtime.")
    launch_portable.clicked.connect(
        lambda _checked=False, item=version_info: self.launch_editor_version(editor, item, "portable")
    )
    open_portable = QPushButton("Open Folder")
    portable_root = version_info.portable_root
    open_portable.setEnabled(bool(portable_root and portable_root.is_dir() and not portable_root.is_symlink()))
    if portable_root is not None:
        open_portable.clicked.connect(lambda _checked=False, target=portable_root: self.launcher.open_path(target))
    add_runtime_row("Portable", "Installed" if version_info.has_portable else "Not installed", (launch_portable, open_portable))

    launch_appimage = QPushButton("Launch")
    launch_appimage.setEnabled(version_info.has_appimage and not version_info.validation_issue)
    launch_appimage.setVisible(not is_backend_only_component(editor))
    launch_appimage.setToolTip("Launch the current version's AppImage runtime.")
    launch_appimage.clicked.connect(
        lambda _checked=False, item=version_info: self.launch_editor_version(editor, item, "appimage")
    )
    appimage_folder = version_info.appimage_path.parent if version_info.appimage_path is not None else None
    open_appimage = QPushButton("Open Folder")
    open_appimage.setEnabled(bool(appimage_folder and appimage_folder.is_dir() and not appimage_folder.is_symlink()))
    if appimage_folder is not None:
        open_appimage.clicked.connect(lambda _checked=False, target=appimage_folder: self.launcher.open_path(target))
    add_runtime_row("AppImage", "Installed" if version_info.has_appimage else "Not installed", (launch_appimage, open_appimage))

    recovery_dir = version_info.recovery_dir or recovery_root(self.editors_root, editor.name, version_info.version)
    has_recovery = recovery_available(recovery_dir)
    restore = QPushButton("Restore Portable…")
    restore.setEnabled(has_recovery and not version_info.validation_issue)
    restore.setToolTip("Restore this current version's Portable runtime from its managed Recovery archive.")
    restore.clicked.connect(
        lambda _checked=False, item=version_info: self.restore_portable_from_recovery_action(editor, item)
    )
    add_runtime_row("Recovery", "Available" if has_recovery else "Unavailable", (restore,))

    return frame


def populate_editor_details(self: SuiteWindow, layout: QVBoxLayout, editor: EditorEntry, *, include_description: bool = True, _style_destructive_button: Callable[[QPushButton], None]) -> None:
    """Render the application-first installed App Page carried into 0.11-exp3.1."""
    profile = profile_for_id(editor.editor_id)
    lifecycle = profile.lifecycle if profile is not None else "current"
    self._add_details_identity_header(layout, editor.name, editor.component_kind, editor.icon, lifecycle=lifecycle)

    portable_root = self._portable_root_for(editor)
    managed = self._managed_record(editor) if sys.platform.startswith("linux") else {}
    component_folder = editor_root(self.editors_root, editor.name)
    component_folder_available = bool(
        component_folder.is_dir() and not component_folder.is_symlink()
        and is_within(component_folder, self.editors_root)
    )
    has_assets = bool(portable_root or editor.installed_command or managed or any(
        item.recovery_dir is not None or item.has_appimage for item in editor.versions
    ))

    if include_description and editor.description:
        description = QLabel(editor.description)
        description.setTextFormat(Qt.TextFormat.PlainText)
        description.setWordWrap(True)
        layout.addWidget(description)
    overview_text = self._application_overview_text(editor)
    if overview_text:
        overview = QLabel(overview_text)
        overview.setTextFormat(Qt.TextFormat.PlainText)
        overview.setWordWrap(True)
        overview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(overview)
    if editor.component_kind != "hub":
        self._add_store_enrichment(layout, editor.editor_id)

    def add_separator() -> None:
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(separator)

    def add_section(section_title: str, actions: tuple[tuple, ...]) -> None:
        if not actions:
            return
        heading = QLabel(section_title)
        heading_font = heading.font()
        heading_font.setBold(True)
        heading_font.setPointSize(max(heading_font.pointSize() + 1, 10))
        heading.setFont(heading_font)
        layout.addWidget(heading)
        row = QHBoxLayout()
        for action in actions:
            button_text, callback, enabled, tooltip = action[:4]
            developer_only = bool(action[4]) if len(action) > 4 else False
            button = QPushButton(button_text)
            button.setEnabled(enabled)
            if tooltip:
                button.setToolTip(tooltip)
            if developer_only:
                button.setProperty("suite_developer_only", True)
                button.setVisible(self.developer_config.enabled)
            button.clicked.connect(callback)
            row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)

    component_repair_actions = ((
        "Repair Desktop Integration", lambda: self.repair_component_desktop_integration(editor),
        bool(any(not item.validation_issue and (item.has_portable or item.has_appimage) for item in editor.versions)),
        "Retarget the verified desktop launcher to the active version and selected runtime; choose a target explicitly when none is active.",
    ),) if sys.platform.startswith("linux") else ()
    hub_repair_actions = ((
        "Repair Desktop Integration", lambda: self.repair_suite_desktop_integration(editor),
        bool(any(not item.validation_issue and (item.has_portable or item.has_appimage) for item in editor.versions)),
        "Repair the verified Suite application-menu and file-routing launcher; choose a target explicitly when none is active.",
    ),) if sys.platform.startswith("linux") else ()
    technical_actions = ((
        "Technical Details…", lambda: self._show_editor_technical_details(editor), True,
        "View and copy active-version paths, Desktop ID and launcher diagnostics.", True,
    ),)

    application_actions: tuple[tuple, ...]
    settings_actions: tuple[tuple, ...]
    if editor.component_kind == "editor":
        application_actions = (
            ("New File…", lambda: self.create_file_for_editor(editor), editor.available, ""),
            ("Open File…", lambda: self.open_with_editor_prompt(editor), editor.available, ""),
            *technical_actions,
        )
        settings_actions = (
            *component_repair_actions,
            ("Open Editor Folder", lambda: self.launcher.open_path(component_folder), component_folder_available,
             "Open this editor's application folder inside the managed Applications root."),
            ("Open Config Folder", lambda: self.open_component_config_folder(editor), self._component_config_folder(editor) is not None,
             "Open this application's user configuration folder."),
            ("Preferences…", lambda: self.editor_preferences(editor), True, ""),
        )
    elif editor.component_kind == "reader":
        application_actions = (
            ("Launch", lambda: self.launch_editor(editor), editor.available, ""),
            ("Open File…", lambda: self.open_with_editor_prompt(editor), editor.available, ""),
            *technical_actions,
        )
        settings_actions = (
            *component_repair_actions,
            ("Open Reader Folder", lambda: self.launcher.open_path(component_folder), component_folder_available,
             "Open this reader's application folder inside the managed Applications root."),
            ("Open Config Folder", lambda: self.open_component_config_folder(editor), self._component_config_folder(editor) is not None,
             "Open this application's user configuration folder."),
            ("Preferences…", lambda: self.editor_preferences(editor), True, ""),
        )
    elif editor.component_kind == "hub":
        application_actions = ()
        settings_actions = (
            ("Installed Applications", self.show_installed_applications, True,
             "Open the existing Installed Applications page."),
            *hub_repair_actions,
            ("Open Config Folder", lambda: self.open_component_config_folder(editor), self._component_config_folder(editor) is not None,
             "Open Suite Pythoine's user configuration folder."),
            ("Hub Preferences…", self.general_preferences, True, "Open Suite Pythoine Hub Preferences."),
        )
    elif is_backend_only_component(editor):
        application_actions = (
            ("Launch", self.show_store, True,
             "Open the integrated Store Pythoine frontend inside Suite."),
            *technical_actions,
        )
        settings_actions = (
            ("Open Extension Folder", lambda: self.launcher.open_path(component_folder), component_folder_available,
             "Open Store Pythoine's managed backend folder."),
        )
    else:
        application_actions = (
            ("Launch", lambda: self.launch_editor(editor), editor.available, ""),
            *technical_actions,
        )
        settings_actions = (
            *component_repair_actions,
            ("Open Extension Folder", lambda: self.launcher.open_path(component_folder), component_folder_available,
             "Open this extension's application folder inside the managed Applications root."),
            ("Open Config Folder", lambda: self.open_component_config_folder(editor), self._component_config_folder(editor) is not None,
             "Open this extension's user configuration folder."),
            ("Preferences…", lambda: self.editor_preferences(editor), True, ""),
        )

    if application_actions:
        add_separator()
        add_section("Application", application_actions)

    add_separator()
    current_heading = QLabel("Current Version")
    current_font = current_heading.font()
    current_font.setBold(True)
    current_font.setPointSize(max(current_font.pointSize() + 1, 10))
    current_heading.setFont(current_font)
    layout.addWidget(current_heading)
    current_version = next((item for item in editor.versions if item.version == editor.active_version), None)
    if current_version is not None:
        layout.addWidget(self._current_version_frame(editor, current_version))
    else:
        current_note = QLabel(
            "No active version is selected. Choose one in Version History." if editor.versions
            else "No managed versions are currently available."
        )
        current_note.setWordWrap(True)
        layout.addWidget(current_note)
        if editor.versions:
            choose_current_row = QHBoxLayout()
            choose_current_row.addStretch(1)
            choose_current = QPushButton("Choose Current Version…")
            choose_current.setToolTip("Open Version History to select and activate an installed version intentionally.")
            choose_current.clicked.connect(
                lambda _checked=False, target=editor: self.show_version_history(target)
            )
            choose_current_row.addWidget(choose_current)
            layout.addLayout(choose_current_row)

    history_heading = QLabel("Version History")
    history_font = history_heading.font(); history_font.setBold(True)
    history_heading.setFont(history_font)
    layout.addWidget(history_heading)
    history_row = QHBoxLayout()
    history_count = QLabel(f"{len(editor.versions)} installed version{'s' if len(editor.versions) != 1 else ''}.")
    history_count.setTextFormat(Qt.TextFormat.PlainText)
    history_row.addWidget(history_count)
    history_row.addStretch(1)
    history_button = QPushButton("Version History…")
    history_button.setEnabled(bool(editor.versions))
    history_button.setToolTip("Browse historical versions and expose full exact-version management only for the selected version.")
    history_button.clicked.connect(lambda _checked=False, target=editor: self.show_version_history(target))
    history_row.addWidget(history_button)
    layout.addLayout(history_row)

    add_separator()
    settings_heading = QLabel("Settings")
    settings_font = settings_heading.font(); settings_font.setBold(True); settings_font.setPointSize(max(settings_font.pointSize() + 1, 10))
    settings_heading.setFont(settings_font)
    layout.addWidget(settings_heading)
    desktop_status = QLabel(self._desktop_integration_summary(editor))
    desktop_status.setTextFormat(Qt.TextFormat.PlainText)
    layout.addWidget(desktop_status)
    settings_row = QHBoxLayout()
    for action in settings_actions:
        button_text, callback, enabled, tooltip = action[:4]
        button = QPushButton(button_text)
        button.setEnabled(enabled)
        if tooltip:
            button.setToolTip(tooltip)
        button.clicked.connect(callback)
        settings_row.addWidget(button)
    settings_row.addStretch(1)
    layout.addLayout(settings_row)

    add_separator()
    maintenance_heading = QLabel("Maintenance")
    maintenance_font = maintenance_heading.font(); maintenance_font.setBold(True); maintenance_font.setPointSize(max(maintenance_font.pointSize() + 1, 10))
    maintenance_heading.setFont(maintenance_font)
    layout.addWidget(maintenance_heading)
    maintenance_row = QHBoxLayout()
    removal_button: QPushButton | None = None
    if editor.component_kind == "hub":
        maintenance_note = QLabel("Remove Hub alone, selected managed applications, or the full validated Suite installation.")
        maintenance_note.setWordWrap(True)
        layout.addWidget(maintenance_note)
        removal_button = QPushButton("Uninstall Suite…")
        removal_button.clicked.connect(self.show_uninstall_suite)
    elif editor.component_kind == "editor":
        removal_button = QPushButton("Purge Editor…")
        removal_button.setEnabled(has_assets)
        removal_button.setToolTip("Remove this editor's managed copies and Suite preferences through a guided purge.")
        removal_button.clicked.connect(lambda _checked=False: self.purge_editor(editor))
    elif editor.component_kind == "reader":
        removal_button = QPushButton("Purge Reader…")
        removal_button.setEnabled(has_assets)
        removal_button.setToolTip("Remove this reader's managed copies and Suite preferences through a guided purge.")
        removal_button.clicked.connect(lambda _checked=False: self.purge_editor(editor))
    elif editor.component_kind == "extension":
        removal_button = QPushButton("Purge Extension…")
        removal_button.setEnabled(has_assets)
        removal_button.setToolTip("Remove this extension's managed copies and Suite preferences through a guided purge.")
        removal_button.clicked.connect(lambda _checked=False: self.purge_editor(editor))
    prune_button = QPushButton("Prune…")
    prune_button.setToolTip(
        "Developer Mode: review additive Prune to This App / Prune to Active Version scopes before removing managed assets."
    )
    prune_button.setProperty("suite_developer_only", True)
    prune_button.setVisible(self.developer_config.enabled)
    prune_button.clicked.connect(lambda _checked=False, target=editor: self._prune_editor(target))
    _style_destructive_button(prune_button)
    maintenance_row.addWidget(prune_button)
    if removal_button is not None:
        _style_destructive_button(removal_button)
        maintenance_row.addWidget(removal_button)
    maintenance_row.addStretch(1)
    layout.addLayout(maintenance_row)


def build_application_page(self: SuiteWindow, editor: EditorEntry) -> QWidget:
    page = QScrollArea()
    page.setWidgetResizable(True)
    content = QWidget()
    page.setWidget(content)
    layout = QVBoxLayout(content)
    layout.setContentsMargins(28, 28, 28, 28)
    layout.setSpacing(12)
    self._populate_editor_details(layout, editor)
    layout.addStretch(1)
    return page


