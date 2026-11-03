"""Suite Pythoine x1.5 Store/catalogue presentation builders.

Only presentation is extracted here. SuiteWindow continues to own Store snapshot
publication, repository verification/download, installer orchestration, and
navigation. This module never contacts the network or mutates installations.
"""
from __future__ import annotations

from typing import TYPE_CHECKING
from PyQt6.QtCore import QSize, Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QIcon, QPixmap
from PyQt6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from ...catalogue.component_catalog import COMPONENT_PROFILES, ComponentProfile, bundled_catalog_icon_path
from ...store.store_content import published_manifest_path, resolve_store_screenshot
from ...ui.helpers import _human_size

if TYPE_CHECKING:
    from ...app import SuiteWindow

def add_store_enrichment(self: SuiteWindow, layout: QVBoxLayout, component_id: str) -> bool:
    """Render optional local Store enrichment on the canonical App Page."""
    entry = self._store_enrichment(component_id)
    if not self._store_entry_has_content(entry):
        return False
    assert entry is not None
    separator = QFrame(); separator.setFrameShape(QFrame.Shape.HLine); layout.addWidget(separator)
    heading = QLabel("Store Information")
    heading_font = heading.font(); heading_font.setBold(True); heading_font.setPointSize(max(heading_font.pointSize() + 1, 10))
    heading.setFont(heading_font)
    layout.addWidget(heading)
    if entry.extended_description:
        description = QLabel(entry.extended_description)
        description.setTextFormat(Qt.TextFormat.PlainText)
        description.setWordWrap(True)
        description.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(description)
    if entry.highlights:
        highlights_heading = QLabel("Highlights")
        highlights_font = highlights_heading.font(); highlights_font.setBold(True)
        highlights_heading.setFont(highlights_font)
        layout.addWidget(highlights_heading)
        highlights = QLabel("\n".join(f"• {value}" for value in entry.highlights))
        highlights.setTextFormat(Qt.TextFormat.PlainText)
        highlights.setWordWrap(True)
        highlights.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(highlights)
    meta: list[str] = []
    installed_version = self._store_installed_version(component_id)
    if installed_version:
        meta.append(f"Installed version: {installed_version}")
    if entry.latest_version:
        meta.append(f"Available version: {entry.latest_version}")
    if entry.check_status == "ok":
        if self._store_update_available(component_id, entry):
            meta.append("Update available")
        elif installed_version:
            meta.append("Current")
    elif entry.check_status in {"error", "unavailable"}:
        meta.append("Could not check")
    if entry.release_date:
        meta.append(f"Release date: {entry.release_date}")
    if entry.download_url and entry.sha256:
        package_bits = ["Verified Store package metadata available"]
        if entry.package_type:
            package_bits.append("AppImage" if entry.package_type == "appimage" else "Source ZIP")
        if entry.package_size:
            package_bits.append(_human_size(entry.package_size))
        meta.append(" · ".join(package_bits))
    if meta:
        label = QLabel(" · ".join(meta))
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        layout.addWidget(label)
    if entry.release_url:
        view_release = QPushButton("View Release")
        view_release.setToolTip("Open the authorised application repository's GitHub Releases page.")
        view_release.clicked.connect(
            lambda _checked=False, url=entry.release_url: QDesktopServices.openUrl(QUrl(url))
        )
        layout.addWidget(view_release, 0, Qt.AlignmentFlag.AlignLeft)
    if entry.check_status in {"error", "unavailable"} and entry.check_error:
        check_note = QLabel("Repository check: " + entry.check_error)
        check_note.setTextFormat(Qt.TextFormat.PlainText)
        check_note.setWordWrap(True)
        check_note.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(check_note)

    if self._store_update_available(component_id, entry) and entry.download_url and entry.sha256:
        profile = COMPONENT_PROFILES.get(component_id)
        if profile is not None:
            update_from_store = QPushButton("Update from Store…")
            update_from_store.setToolTip("Download the advertised Store package, verify its SHA-256 and identity, then open Suite's normal managed installer.")
            update_from_store.clicked.connect(lambda _checked=False, target=profile: self._acquire_store_component(target))
            layout.addWidget(update_from_store, 0, Qt.AlignmentFlag.AlignLeft)
    if entry.release_notes:
        release_heading = QLabel("Release Notes")
        release_font = release_heading.font(); release_font.setBold(True)
        release_heading.setFont(release_font)
        layout.addWidget(release_heading)
        release = QLabel(entry.release_notes)
        release.setTextFormat(Qt.TextFormat.PlainText)
        release.setWordWrap(True)
        release.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(release)
    verified_screenshots = []
    for screenshot in entry.screenshots:
        path = resolve_store_screenshot(screenshot)
        if path is not None:
            verified_screenshots.append((screenshot, path))
    if verified_screenshots:
        screenshots_heading = QLabel("Screenshots")
        screenshots_font = screenshots_heading.font(); screenshots_font.setBold(True)
        screenshots_heading.setFont(screenshots_font)
        layout.addWidget(screenshots_heading)
        for screenshot, path in verified_screenshots:
            pixmap = QPixmap(str(path))
            if pixmap.isNull():
                continue
            image = QLabel()
            image.setPixmap(pixmap.scaled(
                QSize(520, 320),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
            image.setAlignment(Qt.AlignmentFlag.AlignLeft)
            layout.addWidget(image)
            if screenshot.caption:
                caption = QLabel(screenshot.caption)
                caption.setTextFormat(Qt.TextFormat.PlainText)
                caption.setWordWrap(True)
                layout.addWidget(caption)
    return True


def build_catalogue_page(self: SuiteWindow) -> QWidget:
    """Render Get More when Store is absent, or Store's integrated local frontend when installed."""
    store_mode = self._store_is_installed()
    page = QScrollArea()
    page.setWidgetResizable(True)
    content = QWidget()
    page.setWidget(content)
    layout = QVBoxLayout(content)
    layout.setContentsMargins(28, 28, 28, 28)
    layout.setSpacing(12)

    if store_mode:
        title_row = QHBoxLayout()
        store_icon = bundled_catalog_icon_path("store-pythoine")
        if store_icon is not None:
            icon = QLabel(); icon.setPixmap(QIcon(str(store_icon)).pixmap(52, 52)); title_row.addWidget(icon)
        heading = QLabel("Store Pythoine")
        heading_font = heading.font(); heading_font.setBold(True); heading_font.setPointSize(max(heading_font.pointSize() + 5, 15))
        heading.setFont(heading_font)
        title_row.addWidget(heading); title_row.addStretch(1)
        local_refresh = QPushButton("Reload Local Content")
        local_refresh.setToolTip("Ask the installed Store backend to republish its bundled/cached local content. This does not contact the network.")
        local_refresh.clicked.connect(lambda _checked=False: self._publish_installed_store_content())
        title_row.addWidget(local_refresh)
        online_refresh = QPushButton("Refresh Store Online")
        online_refresh.setToolTip("Explicitly check the GitHub repositories authorised by Suite Pythoine and refresh the local Store snapshot. Normal Store browsing stays offline.")
        online_refresh.clicked.connect(lambda _checked=False: self._refresh_store_online())
        title_row.addWidget(online_refresh)
        layout.addLayout(title_row)
        guidance = QLabel(
            "Browse Suite's trusted application catalogue through the integrated Store frontend. "
            "Store data is read from the last local snapshot; opening this page does not contact the network. Refresh Online checks only repositories authorised by Suite Pythoine."
        )
    else:
        heading = QLabel("Get More Applications")
        heading_font = heading.font(); heading_font.setBold(True); heading_font.setPointSize(max(heading_font.pointSize() + 5, 15))
        heading.setFont(heading_font)
        layout.addWidget(heading)
        guidance = QLabel(
            "Browse applications known to Suite Pythoine that are not currently installed. "
            "This lightweight catalogue is local and does not contact the network."
        )
    guidance.setWordWrap(True)
    layout.addWidget(guidance)

    if store_mode:
        manifest = published_manifest_path()
        if self.store_content_error:
            state = QLabel("Store content warning: " + self.store_content_error)
            state.setWordWrap(True)
            layout.addWidget(state)
        elif not manifest.is_file():
            state = QLabel("Rich Store content has not been published locally yet. The trusted Suite catalogue remains available below.")
            state.setWordWrap(True)
            layout.addWidget(state)

    search = QLineEdit()
    search.setPlaceholderText("Search applications…")
    search.setClearButtonEnabled(True)
    search.setAccessibleName("Search Store Pythoine" if store_mode else "Search Get More Applications")
    search.setObjectName("catalogueSearch")
    self.catalogue_search = search
    layout.addWidget(search)

    state_filter = {"value": "all"}
    state_filter_buttons: dict[str, QPushButton] = {}
    if store_mode:
        filter_row = QHBoxLayout()
        filter_label = QLabel("Show:")
        filter_row.addWidget(filter_label)
        filter_group = QButtonGroup(content)
        filter_group.setExclusive(True)
        base_state_filters = (("all", "All"), ("installed", "Installed"), ("not-installed", "Not Installed"))
        for value, label in (*base_state_filters, ("updates", "Updates")):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setObjectName("catalogueStateFilter" + value.title().replace("-", ""))
            button.setAccessibleName(f"Show {label} applications")
            button.setToolTip(f"Show {label.lower()} applications in Store Pythoine.")
            filter_group.addButton(button)
            filter_row.addWidget(button)
            state_filter_buttons[value] = button
        state_filter_buttons["all"].setChecked(True)
        filter_row.addStretch(1)
        layout.addLayout(filter_row)

    profiles = self._store_catalog_profiles() if store_mode else self._uninstalled_catalog_profiles()
    installed_ids = {entry.editor_id for entry in self.components}
    listing = QListWidget()
    listing.setObjectName("storeApplicationsList" if store_mode else "getMoreApplicationsList")
    listing.setIconSize(QSize(36, 36))
    listing.setSpacing(2)
    for profile in profiles:
        kind_label = {"editor": "Editor", "reader": "Reader", "extension": "Extension"}.get(profile.kind, profile.kind.title())
        installed = profile.component_id in installed_ids
        status = "Installed" if installed else "Not installed"
        entry = self._store_enrichment(profile.component_id) if store_mode else None
        current_version = self._store_installed_version(profile.component_id) if installed else None
        version_bits: list[str] = []
        if current_version:
            version_bits.append(f"Current: {current_version}")
        if entry and entry.latest_version:
            version_bits.append(f"Available: {entry.latest_version}")
        if entry and entry.check_status == "ok":
            if self._store_update_available(profile.component_id, entry):
                version_bits.append("Update available")
            elif installed:
                version_bits.append("Current")
        elif entry and entry.check_status in {"error", "unavailable"}:
            version_bits.append("Could not check")
        if profile.lifecycle == "legacy":
            version_bits.append("Legacy")
        version_text = (" · " + " · ".join(version_bits)) if version_bits else ""
        item = QListWidgetItem(
            f"{profile.name} — {kind_label} — {status}{version_text}"
            if store_mode else
            f"{profile.name} — {kind_label}" + (" · Legacy" if profile.lifecycle == "legacy" else "")
        )
        item.setData(Qt.ItemDataRole.UserRole, profile.component_id)
        details = [profile.description]
        if entry and entry.extended_description:
            details.append(entry.extended_description)
        if entry and entry.highlights:
            details.extend(entry.highlights)
        if entry and entry.release_notes:
            details.append("Release notes: " + entry.release_notes)
        if entry and entry.check_error:
            details.append("Repository check: " + entry.check_error)
        if profile.extensions:
            details.append("Formats: " + ", ".join(profile.extensions))
        item.setToolTip("\n".join(part for part in details if part))
        icon_path = bundled_catalog_icon_path(profile.component_id)
        if icon_path is not None:
            item.setIcon(QIcon(str(icon_path)))
        item.setSizeHint(QSize(0, 46))
        listing.addItem(item)
    layout.addWidget(listing, 1)

    empty = QLabel(
        "No Store catalogue applications are available." if store_mode
        else "All applications in the trusted Suite catalogue are currently installed."
    )
    empty.setWordWrap(True)
    empty.setVisible(not bool(profiles))
    layout.addWidget(empty)

    controls = QHBoxLayout()
    controls.addStretch(1)
    open_page = QPushButton("Open App Page")
    open_page.setEnabled(bool(profiles))
    controls.addWidget(open_page)
    layout.addLayout(controls)

    def selected_profile() -> ComponentProfile | None:
        item = listing.currentItem()
        if item is None:
            return None
        return COMPONENT_PROFILES.get(str(item.data(Qt.ItemDataRole.UserRole) or ""))

    def open_selected() -> None:
        profile = selected_profile()
        if profile is not None:
            self.show_catalog_component(profile)

    def apply_filter(text: str) -> None:
        query = text.strip().casefold()
        requested_state = state_filter["value"] if store_mode else "not-installed"
        for row in range(listing.count()):
            item = listing.item(row)
            profile = COMPONENT_PROFILES.get(str(item.data(Qt.ItemDataRole.UserRole) or ""))
            entry = self._store_enrichment(profile.component_id) if (store_mode and profile is not None) else None
            searchable = " ".join((
                item.text(),
                profile.description if profile is not None else "",
                " ".join(profile.extensions) if profile is not None else "",
                " ".join(profile.capabilities) if profile is not None else "",
                entry.extended_description if entry and entry.extended_description else "",
                " ".join(entry.highlights) if entry and entry.highlights else "",
                entry.release_notes if entry and entry.release_notes else "",
                entry.latest_version if entry and entry.latest_version else "",
            )).casefold()
            component_id = profile.component_id if profile is not None else ""
            installed = component_id in installed_ids
            state_matches = (
                requested_state == "all"
                or (requested_state == "installed" and installed)
                or (requested_state == "not-installed" and not installed)
                or (requested_state == "updates" and self._store_update_available(component_id, entry))
            )
            text_matches = not query or query in searchable
            item.setHidden(not (state_matches and text_matches))

    def normalize_selection() -> None:
        visible_rows = [row for row in range(listing.count()) if not listing.item(row).isHidden()]
        current = listing.currentItem()
        if current is None or current.isHidden():
            listing.setCurrentRow(visible_rows[0] if visible_rows else -1)
        open_page.setEnabled(bool(visible_rows and listing.currentItem() is not None))

    def set_state_filter(value: str) -> None:
        state_filter["value"] = value
        apply_filter(search.text())
        normalize_selection()

    listing.currentItemChanged.connect(lambda current, _previous: open_page.setEnabled(current is not None and not current.isHidden()))
    listing.itemDoubleClicked.connect(lambda _item: open_selected())
    open_page.clicked.connect(lambda _checked=False: open_selected())
    search.textChanged.connect(lambda text: (apply_filter(text), normalize_selection()))
    for value, button in state_filter_buttons.items():
        button.clicked.connect(lambda checked, selected=value: checked and set_state_filter(selected))
    apply_filter(search.text())
    normalize_selection()
    return page


def build_catalog_component_page(self: SuiteWindow, profile: ComponentProfile) -> QWidget:
    """Canonical App Page for a trusted uninstalled application, optionally enriched by Store."""
    page = QScrollArea()
    page.setWidgetResizable(True)
    content = QWidget()
    page.setWidget(content)
    layout = QVBoxLayout(content)
    layout.setContentsMargins(28, 28, 28, 28)
    layout.setSpacing(12)

    self._add_details_identity_header(layout, profile.name, profile.kind, bundled_catalog_icon_path(profile.component_id), lifecycle=profile.lifecycle)
    if profile.description:
        description = QLabel(profile.description)
        description.setTextFormat(Qt.TextFormat.PlainText)
        description.setWordWrap(True)
        layout.addWidget(description)

    details: list[str] = ["Status: Not installed"]
    if profile.lifecycle == "legacy":
        details.append("Product lifecycle: Legacy — still available for installation and use")
    if profile.extensions:
        details.append("Supported formats: " + ", ".join(profile.extensions))
    labels = {"create": "Create", "open": "Open", "routing": "File routing"}
    if profile.capabilities:
        details.append("Capabilities: " + " · ".join(labels.get(value, value.replace("_", " ").title()) for value in profile.capabilities))
    overview = QLabel("\n".join(details))
    overview.setTextFormat(Qt.TextFormat.PlainText)
    overview.setWordWrap(True)
    overview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    layout.addWidget(overview)
    self._add_store_enrichment(layout, profile.component_id)

    separator = QFrame(); separator.setFrameShape(QFrame.Shape.HLine); layout.addWidget(separator)
    actions_heading = QLabel("Get This Application")
    actions_font = actions_heading.font(); actions_font.setBold(True); actions_font.setPointSize(max(actions_font.pointSize() + 1, 10))
    actions_heading.setFont(actions_font)
    layout.addWidget(actions_heading)
    note = QLabel(
        "Select a local Suite-compatible source ZIP or AppImage. Suite verifies that the package identity "
        "matches this application before opening the normal installation workflow."
    )
    note.setWordWrap(True)
    layout.addWidget(note)
    action_row = QHBoxLayout()
    back = QPushButton("Back to Store" if self._store_is_installed() else "Back to Get More Applications")
    back.clicked.connect(self.show_store)
    action_row.addWidget(back)
    action_row.addStretch(1)
    store_entry = self._store_enrichment(profile.component_id)
    if store_entry is not None and store_entry.download_url and store_entry.sha256:
        store_install = QPushButton("Install from Store…")
        store_install.setToolTip("Download the advertised package over HTTPS, verify its SHA-256 and identity, then open Suite's normal managed installer.")
        store_install.clicked.connect(lambda _checked=False, target=profile: self._acquire_store_component(target))
        action_row.addWidget(store_install)
    install = QPushButton("Install…")
    if self._store_is_installed():
        install.setText("Install Local Package…")
    install.clicked.connect(lambda _checked=False, target=profile: self.install_catalog_component(target))
    action_row.addWidget(install)
    layout.addLayout(action_row)
    layout.addStretch(1)
    return page


