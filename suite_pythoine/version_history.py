from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .recovery import recovery_available
from .registry import EditorEntry, EditorVersionInfo
from .storage_layout import recovery_root


@dataclass(frozen=True, slots=True)
class VersionHistoryRow:
    version_info: EditorVersionInfo
    version: str
    has_portable: bool
    has_appimage: bool
    has_recovery: bool
    active: bool
    desktop_integrated: bool
    legacy: bool
    validation_issue: str

    @property
    def state_text(self) -> str:
        labels: list[str] = []
        if self.active:
            labels.append("Active")
        if self.desktop_integrated:
            labels.append("Desktop integrated")
        if self.validation_issue:
            labels.append("Needs attention")
        elif self.legacy:
            labels.append("Legacy identification")
        return " · ".join(labels) if labels else "Available"


def build_version_history_rows(editor: EditorEntry, editors_root: Path) -> tuple[VersionHistoryRow, ...]:
    """Return lightweight row state without constructing per-version GUI controls."""
    rows: list[VersionHistoryRow] = []
    for version in editor.versions:
        recovery_dir = version.recovery_dir or recovery_root(editors_root, editor.name, version.version)
        rows.append(VersionHistoryRow(
            version_info=version,
            version=version.version,
            has_portable=bool(version.has_portable),
            has_appimage=bool(version.has_appimage),
            has_recovery=recovery_available(recovery_dir),
            active=version.version == editor.active_version,
            desktop_integrated=bool(version.desktop_integrated or version.version == editor.desktop_version),
            legacy=bool(version.legacy),
            validation_issue=str(version.validation_issue or ""),
        ))
    return tuple(rows)
