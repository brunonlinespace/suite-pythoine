"""Shared presentation helpers for Suite Pythoine install/removal workflows.

The canonical operation family uses the same 820x640 minimum / 980x800
working size and the same 96px identity header proportions as the guided
install, purge and Suite-uninstall wizards.  Compact exact-runtime Remove
Portable/AppImage confirmations intentionally remain outside this family.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

OPERATION_MIN_SIZE = (820, 640)
OPERATION_SIZE = (980, 800)


def configure_operation_window(widget: QWidget) -> None:
    widget.setMinimumSize(*OPERATION_MIN_SIZE)
    widget.resize(*OPERATION_SIZE)


def load_operation_pixmap(icon_path: Path | None, size: int = 88) -> QPixmap | None:
    if icon_path is None or not icon_path.is_file():
        return None
    pixmap = QPixmap(str(icon_path))
    if pixmap.isNull():
        return None
    return pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)


def apply_operation_icon(widget: QWidget, icon_path: Path | None, size: int = 128) -> QPixmap | None:
    pixmap = load_operation_pixmap(icon_path, size)
    if pixmap is not None:
        widget.setWindowIcon(QIcon(pixmap))
    return pixmap


def operation_branding_header(
    name: str,
    secondary: str,
    *,
    description: str = "",
    icon_path: Path | None = None,
) -> QFrame:
    """Return the same identity-header proportions used by guided wizards."""
    frame = QFrame()
    row = QHBoxLayout(frame)
    row.setContentsMargins(0, 0, 0, 8)
    pixmap = load_operation_pixmap(icon_path, 88)
    if pixmap is not None:
        icon = QLabel()
        icon.setPixmap(pixmap)
        icon.setFixedSize(96, 96)
        icon.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        row.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
    text = QVBoxLayout()
    name_label = QLabel(name)
    font = name_label.font()
    font.setBold(True)
    font.setPointSize(max(font.pointSize() + 4, 15))
    name_label.setFont(font)
    name_label.setTextFormat(Qt.TextFormat.PlainText)
    text.addWidget(name_label)
    secondary_label = QLabel(secondary)
    secondary_label.setTextFormat(Qt.TextFormat.PlainText)
    secondary_label.setWordWrap(True)
    text.addWidget(secondary_label)
    if description:
        description_label = QLabel(description)
        description_label.setTextFormat(Qt.TextFormat.PlainText)
        description_label.setWordWrap(True)
        text.addWidget(description_label)
    text.addStretch(1)
    row.addLayout(text, 1)
    return frame


def operation_title_block(title: str, subtitle: str) -> QFrame:
    """QDialog counterpart to QWizardPage title/subtitle presentation."""
    frame = QFrame()
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(0, 0, 0, 8)
    layout.setSpacing(4)
    heading = QLabel(title)
    font = heading.font()
    font.setBold(True)
    font.setPointSize(max(font.pointSize() + 3, 13))
    heading.setFont(font)
    heading.setTextFormat(Qt.TextFormat.PlainText)
    layout.addWidget(heading)
    note = QLabel(subtitle)
    note.setTextFormat(Qt.TextFormat.PlainText)
    note.setWordWrap(True)
    layout.addWidget(note)
    return frame
