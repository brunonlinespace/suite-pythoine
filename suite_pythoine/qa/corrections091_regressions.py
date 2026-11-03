"""0.9.1 scoped corrections: inventory search, provenance, repair bootstrap and post-exit handoffs."""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations

import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

from suite_pythoine.installer import write_appimage_metadata
from suite_pythoine.versioning import read_appimage_metadata
from suite_pythoine.suite_self_restore_worker import execute as execute_self_restore

PACKAGE = Path(__file__).resolve().parents[1]


def run_regressions(errors: list[str]) -> None:
    def check(ok, message):
        if not ok:
            errors.append('0.9.1 corrections: ' + message)

    app = read_app_with_presentations()
    inventory_page = (PACKAGE / "ui/pages/installed_applications.py").read_text(encoding="utf8")
    uninstall = (PACKAGE / 'suite_uninstall.py').read_text(encoding='utf-8')
    uninstall_worker = (PACKAGE / 'suite_uninstall_worker.py').read_text(encoding='utf-8')
    builder = (PACKAGE / 'packaging/fedora/build-appimage.sh').read_text(encoding='utf-8')

    check('Search installed applications…' in inventory_page, 'Installed Applications placeholder not broadened')
    check('for column in (0, 1, 2, 3' in inventory_page,
          'Installed Applications search does not cover name/version/runtime/active')
    check(app.count('Install date uses the managed ') == 1 and
          'version/asset folder timestamp where an explicit install timestamp is not available' in app and
          'def _show_installed_applications_guidance' in app,
          'install-date guidance was lost from Installed Applications detailed guidance')
    check('def _bootstrap_desktop_repair' in app and
          'return self._bootstrap_desktop_repair(editor) if show_dialog else False' in app,
          'Repair Desktop Integration cannot bootstrap an explicit target when no active version exists')
    check('any(not item.validation_issue and (item.has_portable or item.has_appimage) for item in editor.versions)' in app,
          'Repair button still requires a pre-existing active selection')
    check('HubSelfRestoreWizard' in app and 'Restore this running Hub Portable through the safe post-exit self-restore handoff.' in app,
          'running Hub Portable Recovery remains blocked')
    check('QTimer.singleShot(0, self._exit_hub)' not in uninstall and 'self.handoff_ready = True' in uninstall,
          'uninstaller still relies on the fragile wizard-owned zero-delay shutdown callback')
    check('if wizard.handoff_ready:' in app and '_begin_post_exit_shutdown(preserve_reviewed_preferences=True)' in app,
          'main window does not own deterministic uninstall shutdown')
    check('_suite_pixmap(128)' in uninstall and 'branding_header()' in uninstall,
          'uninstall wizard does not use the Suite logo/branded page contract')
    check("'notify-send'" in uninstall_worker or '"notify-send"' in uninstall_worker,
          'post-exit uninstall has no desktop success/failure notification attempt')
    check('suite_self_restore_worker.py:suite_pythoine' in builder,
          'frozen build omits readable standalone self-restore worker')

    # Provenance is artifact-sidecar state and must survive later metadata refreshes.
    with tempfile.TemporaryDirectory(prefix='suite091-provenance-') as folder:
        appimage = Path(folder) / 'Example.AppImage'
        appimage.write_bytes(b'fake-appimage')
        write_appimage_metadata(appimage, editor_id='example', name='Example', version='1.0',
                                provenance='built', built_from_runtime='Portable',
                                created_at='2026-09-30T06:00:00+00:00')
        first = read_appimage_metadata(appimage)
        check(first.get('provenance') == 'built' and first.get('built_from_runtime') == 'Portable' and
              first.get('created_at') == '2026-09-30T06:00:00+00:00', 'built provenance not written')
        write_appimage_metadata(appimage, editor_id='example', name='Example', version='1.0')
        refreshed = read_appimage_metadata(appimage)
        check(refreshed.get('provenance') == 'built' and refreshed.get('built_from_runtime') == 'Portable' and
              refreshed.get('created_at') == first.get('created_at'), 'metadata refresh destroyed existing provenance')
        write_appimage_metadata(appimage, editor_id='example', name='Example', version='1.0',
                                provenance='imported', built_from_runtime=None,
                                created_at='2026-09-30T06:30:00+00:00')
        imported = read_appimage_metadata(appimage)
        check(imported.get('provenance') == 'imported' and imported.get('built_from_runtime') is None,
              'imported provenance incorrectly claims a build runtime')

    # Exercise the post-exit swap itself against disposable directories. The
    # relaunch process is mocked; file replacement/rollback boundaries are real.
    with tempfile.TemporaryDirectory(prefix='suite091-selfrestore-') as folder:
        base = Path(folder)
        target = base / 'Portable'; target.mkdir(); (target / 'old.txt').write_text('old')
        staged = base / '.Portable.self-restore-staging-test'; staged.mkdir()
        (staged / 'main.py').write_text('print("restored")')
        plan = {
            'schema': 1,
            'target': str(target), 'target_exists': True,
            'target_identity': [target.lstat().st_dev, target.lstat().st_ino],
            'staged': str(staged), 'staged_identity': [staged.lstat().st_dev, staged.lstat().st_ino],
            'python': sys.executable, 'report_path': str(base / 'report.txt'),
        }
        with patch('suite_pythoine.suite_self_restore_worker.subprocess.Popen') as popen:
            report = execute_self_restore(plan)
        check(report.startswith('SUCCESS:') and target.is_dir() and (target / 'main.py').is_file() and
              not (target / 'old.txt').exists() and not staged.exists(), 'self-restore worker did not atomically replace target')
        check(popen.called, 'self-restore worker did not request Hub relaunch')
