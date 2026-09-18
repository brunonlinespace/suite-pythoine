# Marko Plus
# Copyright (C) 2026 Bruno Machado
# SPDX-License-Identifier: GPL-3.0-or-later
"""Markopad-style searchable keyboard-shortcuts reference."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import re

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


ShortcutEntry = tuple[str, QAction | str]

_SHORTCUT_TOKEN_RE = re.compile(r"[a-z0-9]+|[^\w\s+]", re.IGNORECASE)
_SHORTCUT_TOKEN_ALIASES = {
    "control": "ctrl",
    "ctrl": "ctrl",
    "ctl": "ctrl",
}


def _shortcut_tokens(value: str) -> tuple[str, ...]:
    """Return comparable shortcut tokens without imposing modifier order."""
    return tuple(
        _SHORTCUT_TOKEN_ALIASES.get(token, token)
        for token in _SHORTCUT_TOKEN_RE.findall(value.casefold())
    )


def _shortcut_query_matches(query: str, shortcut_tokens: tuple[str, ...]) -> bool:
    """Match aliases, optional plus signs and reordered shortcut modifiers."""
    query_tokens = _shortcut_tokens(query)
    return bool(query_tokens) and all(
        token in shortcut_tokens for token in query_tokens
    )


class ShortcutsDialog(QDialog):
    """Show real assigned shortcuts in Markopad's filtered table style."""

    def __init__(
        self,
        catalog: Mapping[str, Sequence[ShortcutEntry]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setWindowTitle("Keyboard Shortcuts — Suite Pythoine")
        if parent is not None:
            self.setWindowIcon(parent.windowIcon())
        self.setModal(False)
        self.resize(700, 560)

        outer = QVBoxLayout(self)
        filter_row = QHBoxLayout()
        self.search = QLineEdit(self)
        self.search.setPlaceholderText("Search commands or shortcuts")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Search keyboard shortcuts")
        self.category = QComboBox(self)
        self.category.setAccessibleName("Shortcut menu")
        self.category.addItems(["All", *catalog.keys()])
        self.category.setCurrentIndex(0)
        filter_row.addWidget(self.search, 1)
        filter_row.addWidget(QLabel("Menu:", self))
        filter_row.addWidget(self.category)
        outer.addLayout(filter_row)

        self.rows: list[tuple[str, str, str, str, tuple[str, ...]]] = []
        seen: set[tuple[str, str]] = set()
        for menu_name, entries in catalog.items():
            for label, action_or_shortcut in entries:
                shortcut = (
                    action_or_shortcut.shortcut().toString(
                        QKeySequence.SequenceFormat.NativeText
                    )
                    if isinstance(action_or_shortcut, QAction)
                    else str(action_or_shortcut).strip()
                )
                clean_label = (
                    label.replace("&", "").replace("…", "").strip()
                )
                if (
                    not shortcut
                    or not clean_label
                    or (clean_label, shortcut) in seen
                ):
                    continue
                seen.add((clean_label, shortcut))
                self.rows.append(
                    (
                        menu_name,
                        clean_label,
                        shortcut,
                        clean_label.casefold(),
                        _shortcut_tokens(shortcut),
                    )
                )
        self.rows.sort(key=lambda row: row[1].casefold())

        self.table = QTableWidget(len(self.rows), 2, self)
        self.table.setHorizontalHeaderLabels(["Command", "Shortcut"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        for row_index, (
            _menu_name,
            label,
            shortcut,
            _label_search,
            _shortcut_search,
        ) in enumerate(self.rows):
            self.table.setItem(row_index, 0, QTableWidgetItem(label))
            self.table.setItem(row_index, 1, QTableWidgetItem(shortcut))
        self.table.resizeColumnsToContents()
        outer.addWidget(self.table, 1)

        self.no_matches = QLabel("No matching shortcuts.", self)
        self.no_matches.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.no_matches.hide()
        outer.addWidget(self.no_matches)

        self.search.textChanged.connect(self._apply_filter)
        self.category.currentTextChanged.connect(self._apply_filter)
        self._apply_filter()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, self)
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setText("OK")
        buttons.accepted.connect(self.close)
        outer.addWidget(buttons)

    def _apply_filter(self) -> None:
        query = self.search.text().strip().casefold()
        selected = self.category.currentText()
        any_visible = False
        for row_index, (
            menu_name,
            _label,
            _shortcut,
            label_search,
            shortcut_tokens,
        ) in enumerate(self.rows):
            row_visible = (
                (selected == "All" or selected == menu_name)
                and (
                    not query
                    or query in label_search
                    or _shortcut_query_matches(query, shortcut_tokens)
                )
            )
            self.table.setRowHidden(row_index, not row_visible)
            any_visible = any_visible or row_visible
        self.table.setVisible(any_visible)
        self.no_matches.setVisible(not any_visible)
