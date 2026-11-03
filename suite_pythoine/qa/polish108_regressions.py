"""0.10.8 focused live-UI regression corrections (Qt-free)."""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations

from pathlib import Path

from suite_pythoine.versioning import version_sort_key

PACKAGE = Path(__file__).resolve().parents[1]


def run_regressions(errors: list[str]) -> None:
    prefix = "0.10.8 polish: "

    def check(condition: bool, message: str) -> None:
        if not condition:
            errors.append(prefix + message)

    app = read_app_with_presentations()
    inventory_page = (PACKAGE / "ui/pages/installed_applications.py").read_text(encoding="utf8")
    prune_widget = (PACKAGE / "ui" / "widgets" / "prune.py").read_text(encoding="utf8")
    intake = (PACKAGE / "developer/developer_intake.py").read_text(encoding="utf8")
    wizard = (PACKAGE / "install_wizard.py").read_text(encoding="utf8")

    # 0.10.9 supersedes the style-dependent QGroupBox-title alignment with
    # ordinary left-side scope checkboxes above native StyledPanel content.
    prune = prune_widget
    check('QCheckBox("Prune to Active Version")' in prune and
          'QCheckBox("Prune to This App")' in prune and
          prune.count('QFrame.Shape.StyledPanel') >= 2,
          "Prune scopes lost the left-side checkbox/native-panel presentation")

    # Installed Applications Version must sort naturally/semantically, not as
    # plain text (where 0.10 incorrectly falls between 0.1 and 0.3/0.9).
    versions = ["0.3.8", "0.9.0", "0.10.3", "0.10.8", "0.4.0"]
    check(sorted(versions, key=version_sort_key) == ["0.3.8", "0.4.0", "0.9.0", "0.10.3", "0.10.8"],
          "version_sort_key no longer provides numeric component ordering")
    check(inventory_page.count('text_item(str(record["version"]), version_sort_key(str(record["version"])))') >= 2,
          "Installed Applications does not use semantic version sort values in both normal and Remove Assets modes")

    # QListWidgetItem::setHidden must run after ownership by the list. The old
    # pre-insertion call left AppImage build checklist rows visible on Breeze.
    progress_start = wizard.index("class ProgressPage")
    progress_end = wizard.index("class ", progress_start + 10)
    progress = wizard[progress_start:progress_end]
    add_pos = progress.index("self.steps.addItem(item)")
    hide_pos = progress.index("item.setHidden(True)")
    check(add_pos < hide_pos and 'not self.options.developer_mode' in progress[add_pos:hide_pos + 80],
          "normal Portable install does not reliably hide Developer-only AppImage checklist rows after insertion")

    # Intake Summary must wrap long version/ZIP paths instead of clipping them.
    # 0.10.9 replaces the QFormLayout with a dynamic grid because the live
    # Breeze form rows still clipped wrapped continuation lines.
    check('value.setWordWrap(True)' in intake and
          'QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred' in intake and
          'summary_grid = QGridLayout(self.info_group)' in intake and
          'value.setMinimumWidth(0)' in intake,
          "Developer Intake summary is not configured to wrap long paths/status text")

    # About opens at Quick Tour's 940px default width. Do not introduce or alter
    # a minimum-height contract for About; its content-derived height remains.
    about_start = app.index("    def about(self) -> None:")
    about_end = app.index("    def closeEvent", about_start)
    about = app[about_start:about_end]
    check("dialog.resize(940, dialog.height())" in about,
          "About does not open at the Quick Tour default width")
    check("setMinimumHeight(" not in about and "setMinimumSize(" not in about,
          "About minimum-height behavior was changed while widening the default window")

    # The deferred private ZIP/session-vault feature remains out of this release.

    print("PASS: 0.10.8 focused UI regression corrections"
          if not any(error.startswith(prefix) for error in errors)
          else "CHECK: 0.10.8 polish regressions")


if __name__ == "__main__":
    failures: list[str] = []
    run_regressions(failures)
    for failure in failures:
        print("FAIL:", failure)
    raise SystemExit(1 if failures else 0)
