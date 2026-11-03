"""Shared diagnostic-view and native destructive-button presentation helpers.

Their implementations are retained verbatim from Suite Pythoine 1.0.0-x1.6.
No dialog or application-page ownership is moved by this module.
"""
from __future__ import annotations

from PyQt6.QtGui import QColor, QPalette, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import QApplication, QPushButton, QTextEdit, QWidget


def _diagnostic_canvas(parent: QWidget | None = None) -> QTextEdit:
    """Read-only, selectable canvas matching Systemd Inspector Sources styling."""
    canvas = QTextEdit(parent)
    canvas.setReadOnly(True)
    canvas.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
    canvas.setStyleSheet(
        "QTextEdit { background-color: #151719; color: #dcdcdc; "
        "border: 1px solid #333333; }"
    )
    return canvas


def _populate_diagnostic_canvas(canvas: QTextEdit, report: str) -> None:
    """Keep debug text literal, highlighting only labels and section titles."""
    sections = {"Identity", "Runtime selection", "Desktop integration",
                "Active-version runtime paths", "Other validation warnings"}
    key_format = QTextCharFormat()
    key_format.setForeground(QColor("#9cdcfe"))
    key_format.setFontWeight(600)
    value_format = QTextCharFormat()
    value_format.setForeground(QColor("#dcdcdc"))
    canvas.clear()
    cursor = canvas.textCursor()
    for index, line in enumerate(report.splitlines()):
        if index:
            cursor.insertText("\n", value_format)
        if line in sections:
            cursor.insertText(line, key_format)
        elif ": " in line:
            label, value = line.split(": ", 1)
            cursor.insertText(label + ": ", key_format)
            cursor.insertText(value, value_format)
        else:
            cursor.insertText(line, value_format)
    cursor.movePosition(QTextCursor.MoveOperation.Start)
    canvas.setTextCursor(cursor)


def _style_destructive_button(button: QPushButton) -> None:
    """Keep the native Qt/KDE button frame while adding a restrained danger tint."""
    app = QApplication.instance()
    palette = QPalette(app.palette() if app is not None else button.palette())
    base = palette.color(QPalette.ColorRole.Button)
    accent = QColor("#dc6262")
    mix = 0.07
    tint = QColor(
        round(base.red() * (1.0 - mix) + accent.red() * mix),
        round(base.green() * (1.0 - mix) + accent.green() * mix),
        round(base.blue() * (1.0 - mix) + accent.blue() * mix),
    )
    palette.setColor(QPalette.ColorRole.Button, tint)
    palette.setColor(QPalette.ColorRole.ButtonText, accent)
    button.setPalette(palette)
    button.setProperty("suite_destructive", True)
    # Text colour only: do not override border/shape, which belongs to the native theme.
    button.setStyleSheet("QPushButton { color: #dc6262; }")
