"""Persist uncaught GUI callback tracebacks before a Qt binding may abort.

This is diagnostic reporting, not a claim to correct an as-yet-unreproduced
checkbox exception. It deliberately does not display GUI from an exception hook.
"""
from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import sys
import traceback


def gui_error_log_path() -> Path:
    state = Path(os.environ.get('XDG_STATE_HOME') or (Path.home() / '.local' / 'state')).expanduser()
    return state / 'brunonlinespace' / 'suite-pythoine' / 'gui-errors.log'


def install_gui_error_hook() -> None:
    """Retain exception type, Python frame and timestamp for a fatal Qt slot."""
    if getattr(sys.excepthook, '_suite_pythoine_gui_errors', False):
        return

    def report(exc_type, value, tb) -> None:
        trace = ''.join(traceback.format_exception(exc_type, value, tb))
        record = f'\n=== {datetime.now(timezone.utc).isoformat()} UTC / Suite Pythoine GUI ===\n{trace}\n'
        try:
            sys.stderr.write(record)
            sys.stderr.flush()
        except (OSError, ValueError):
            pass
        try:
            path = gui_error_log_path()
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if path.is_symlink():
                return
            if path.is_file() and path.stat().st_size > 1_048_576:
                # A diagnostic log must not grow without bound.
                path.write_text('', encoding='utf-8')
            with path.open('a', encoding='utf-8') as log:
                log.write(record)
        except (OSError, ValueError):
            pass

    report._suite_pythoine_gui_errors = True  # type: ignore[attr-defined]
    sys.excepthook = report
