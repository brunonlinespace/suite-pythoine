"""Suite Pythoine application palettes with a restrained orange accent.

The neutral surface treatment follows the proven Rico Plus / Marko Plus
System-Dark-Light pattern, while Suite keeps its own orange product identity.
"""
from __future__ import annotations

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

THEMES = {"system", "dark", "light"}
LIGHT_ACCENT = QColor("#C05800")
DARK_ACCENT = QColor("#F08A24")


def normalize_theme(theme: object) -> str:
    value = str(theme or "system").strip().lower()
    return value if value in THEMES else "system"


def apply_theme(app: QApplication, theme: str) -> None:
    """Apply a fresh System/Dark/Light Qt palette on every transition.

    Like Rico and Marko, the platform QStyle is the system-palette authority.
    A startup snapshot can become stale after KDE changes its appearance, so
    always start from the current standardPalette instead of a past app palette.
    Do not retain previous custom palette roles across theme transitions.
    """
    theme = normalize_theme(theme)
    # Clear only the application-level stylesheet (Suite does not define one).
    # Widget-local diagnostic/danger/card styles are intentionally unaffected.
    app.setStyleSheet("")
    # Explicitly clear the previous application palette before building a new
    # one. This is how the Plus applications avoid retaining custom roles when
    # going Dark -> Light -> System under KDE's native Qt style.
    app.setPalette(app.style().standardPalette())
    if theme == "system":
        return
    palette = QPalette(app.style().standardPalette())

    if theme == "dark":
        palette.setColor(QPalette.ColorRole.Window, QColor("#202326"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#F1F3F4"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#151719"))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#202326"))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#292D31"))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#F1F3F4"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#F1F3F4"))
        palette.setColor(QPalette.ColorRole.Button, QColor("#292D31"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("#F1F3F4"))
        palette.setColor(QPalette.ColorRole.Light, QColor("#3A3F44"))
        palette.setColor(QPalette.ColorRole.Midlight, QColor("#33383D"))
        palette.setColor(QPalette.ColorRole.Mid, QColor("#4C535A"))
        palette.setColor(QPalette.ColorRole.Dark, QColor("#111315"))
        palette.setColor(QPalette.ColorRole.Shadow, QColor("#090A0B"))
        palette.setColor(QPalette.ColorRole.Highlight, DARK_ACCENT)
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#151719"))
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#9AA1A8"))
        palette.setColor(QPalette.ColorRole.Link, QColor("#FFB15C"))
        palette.setColor(QPalette.ColorRole.LinkVisited, QColor("#FFB15C"))
    else:
        # Calmer Plus-family light surfaces: neutral shell, brighter content
        # canvas, and orange only where an accent is useful.
        palette.setColor(QPalette.ColorRole.Window, QColor("#D4D4D4"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#2A2A2A"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#F4F4F4"))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#E4E4E4"))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#F4F4F4"))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#2A2A2A"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#2A2A2A"))
        palette.setColor(QPalette.ColorRole.Button, QColor("#E4E4E4"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("#2A2A2A"))
        palette.setColor(QPalette.ColorRole.Light, QColor("#F4F4F4"))
        palette.setColor(QPalette.ColorRole.Midlight, QColor("#D0D0D0"))
        palette.setColor(QPalette.ColorRole.Mid, QColor("#B2B2B2"))
        palette.setColor(QPalette.ColorRole.Dark, QColor("#767676"))
        palette.setColor(QPalette.ColorRole.Shadow, QColor("#545454"))
        palette.setColor(QPalette.ColorRole.Highlight, LIGHT_ACCENT)
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#767676"))
        palette.setColor(QPalette.ColorRole.Link, QColor("#A94D00"))
        palette.setColor(QPalette.ColorRole.LinkVisited, QColor("#A94D00"))
    app.setPalette(palette)
