from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import QCheckBox, QFrame, QLabel, QVBoxLayout, QWizardPage

from ...operation_ui import operation_branding_header
from ...registry import EditorEntry


class PruneScopePage(QWizardPage):
    """Developer-only additive Prune scopes with per-scope Recovery retention."""

    def __init__(
        self,
        editor: EditorEntry,
        *,
        icon_path: Path | None,
        has_other_apps: bool,
        has_other_versions: bool,
    ) -> None:
        super().__init__()
        self.editor = editor
        self.setTitle("Prune")
        self.setSubTitle("Choose one or both Developer Mode prune scopes. Recovery is removed by default unless you explicitly keep it.")
        layout = QVBoxLayout(self)
        layout.addWidget(operation_branding_header(
            editor.name, "Developer Mode · Prune",
            description="Prune is a reviewed shortcut over Suite Pythoine's existing managed-asset removal engine.",
            icon_path=icon_path,
        ))

        # Keep each additive scope selector as an ordinary left-aligned checkbox.
        # The subordinate explanation/Recovery option lives in its own native
        # StyledPanel so Breeze can distinguish scopes without centring or
        # otherwise restyling the actual Prune control.
        self.prune_active_version = QCheckBox("Prune to Active Version")
        self.prune_active_version.setChecked(False)
        self.prune_active_version.setEnabled(has_other_versions and bool(editor.active_version))
        layout.addWidget(self.prune_active_version)
        active_panel = QFrame()
        active_panel.setFrameShape(QFrame.Shape.StyledPanel)
        active_box = QVBoxLayout(active_panel)
        active_box.setContentsMargins(14, 10, 14, 10)
        active_text = editor.active_version or "no active version selected"
        active_note = QLabel(f"Keep the active {editor.name} version ({active_text}); remove this application's other versions.")
        active_note.setWordWrap(True)
        active_box.addWidget(active_note)
        self.keep_active_recovery = QCheckBox("Keep Recovery Files")
        self.keep_active_recovery.setChecked(False)
        self.keep_active_recovery.setToolTip("Unchecked removes Recovery within this prune scope; checked preserves it.")
        active_box.addWidget(self.keep_active_recovery)
        active_panel.setEnabled(False)
        if editor.active_version:
            self.prune_active_version.setToolTip(
                f"Keep {editor.name} {editor.active_version}; target this application's other versions."
                if has_other_versions else "This application has no other version assets to prune."
            )
        else:
            self.prune_active_version.setToolTip("Select an active version before using this prune scope.")
        layout.addWidget(active_panel)

        self.prune_this_app = QCheckBox("Prune to This App")
        self.prune_this_app.setChecked(False)
        self.prune_this_app.setEnabled(has_other_apps)
        layout.addWidget(self.prune_this_app)
        this_panel = QFrame()
        this_panel.setFrameShape(QFrame.Shape.StyledPanel)
        this_box = QVBoxLayout(this_panel)
        this_box.setContentsMargins(14, 10, 14, 10)
        this_note = QLabel(f"Keep {editor.name} and Suite Pythoine; remove managed assets belonging to other applications.")
        this_note.setWordWrap(True)
        this_box.addWidget(this_note)
        self.keep_this_recovery = QCheckBox("Keep Recovery Files")
        self.keep_this_recovery.setChecked(False)
        self.keep_this_recovery.setToolTip("Unchecked removes Recovery within this prune scope; checked preserves it.")
        this_box.addWidget(self.keep_this_recovery)
        this_panel.setEnabled(False)
        self.prune_this_app.setToolTip(
            f"Keep {editor.name} and Suite Pythoine; target managed assets belonging to other applications."
            if has_other_apps else "No other application assets are currently available to prune."
        )
        layout.addWidget(this_panel)

        warning = QLabel(
            "The two prune scopes are additive. Nothing is removed until the exact proposed assets are reviewed on the next page."
        )
        warning.setWordWrap(True)
        layout.addWidget(warning)
        layout.addStretch(1)

        self.prune_this_app.toggled.connect(this_panel.setEnabled)
        self.prune_active_version.toggled.connect(active_panel.setEnabled)
        self.prune_this_app.toggled.connect(lambda _checked: self.completeChanged.emit())
        self.prune_active_version.toggled.connect(lambda _checked: self.completeChanged.emit())

    def isComplete(self) -> bool:  # noqa: N802 - Qt API
        return self.prune_this_app.isChecked() or self.prune_active_version.isChecked()
