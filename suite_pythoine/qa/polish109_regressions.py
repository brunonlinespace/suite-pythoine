"""0.10.9 Prune and Developer Intake summary regressions (Qt-free)."""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations

from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]


def run_regressions(errors: list[str]) -> None:
    prefix = "0.10.9 polish: "

    def check(condition: bool, message: str) -> None:
        if not condition:
            errors.append(prefix + message)

    app = read_app_with_presentations()
    prune_widget = (PACKAGE / "ui" / "widgets" / "prune.py").read_text(encoding="utf8")
    intake = (PACKAGE / "developer/developer_intake.py").read_text(encoding="utf8")

    # Scope selectors are ordinary left-side checkboxes. Their subordinate
    # description/Recovery controls live inside two native StyledPanel frames,
    # avoiding Breeze's centred rendering of checkable QGroupBox titles.
    prune = prune_widget
    active = prune.index('QCheckBox("Prune to Active Version")')
    this_app = prune.index('QCheckBox("Prune to This App")')
    check(active < this_app, "Prune to Active Version is not the first scope")
    check('QGroupBox("Prune to Active Version")' not in prune and
          'QGroupBox("Prune to This App")' not in prune,
          "Prune scope selectors returned to style-dependent checkable group-box titles")
    check(prune.count('setFrameShape(QFrame.Shape.StyledPanel)') >= 2,
          "both Prune scopes do not have native StyledPanel separation")
    check('self.prune_active_version.toggled.connect(active_panel.setEnabled)' in prune and
          'self.prune_this_app.toggled.connect(this_panel.setEnabled)' in prune,
          "Prune framed details do not follow their scope checkbox state")
    check(prune.count('QCheckBox("Keep Recovery Files")') >= 2 and
          prune.count('setChecked(False)') >= 4,
          "Prune Recovery retention/default-off semantics changed")

    # Intake Summary carries identity + action in the title and keeps only the
    # useful path/result rows. The old Application/Action/Source rows are gone.
    check('self.info_group = QGroupBox("Intake Summary")' in intake and
          'self.info_group.setTitle(f"Intake Summary — {planned.identity.name}{local_suffix} ({action})")' in intake,
          "Intake Summary does not put application/action in its title")
    summary_start = intake.index('self.info_group = QGroupBox("Intake Summary")')
    summary_end = intake.index('self.status_label = QLabel(', summary_start)
    summary = intake[summary_start:summary_end]
    check('"Application:"' not in summary and '"Action:"' not in summary and '"Source:"' not in summary,
          "redundant Application/Action/Source rows remain in Intake Summary")
    for label in ('"Version folder:"', '"Development ZIP:"', '"Original ZIP:"', '"Notes:"'):
        check(label in summary, f"Intake Summary missing {label}")

    # Dynamic grid rows must grow with multi-line labels instead of clipping.
    check('summary_grid = QGridLayout(self.info_group)' in summary and
          'value.setWordWrap(True)' in summary and
          'QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred' in summary and
          'value.setMinimumWidth(0)' in summary and
          'Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop' in summary and
          'Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop' in summary,
          "Intake Summary does not use dynamic top-aligned wrapping grid rows")
    check('TextSelectableByMouse' in summary,
          "Intake Summary values are no longer mouse-selectable")

    # The session-vault work is still deliberately deferred.

    print("PASS: 0.10.9 Prune/Intake Summary regressions"
          if not any(error.startswith(prefix) for error in errors)
          else "CHECK: 0.10.9 polish regressions")


if __name__ == "__main__":
    failures: list[str] = []
    run_regressions(failures)
    for failure in failures:
        print("FAIL:", failure)
    raise SystemExit(1 if failures else 0)
