"""0.9.0: standalone safety, selection and UI-contract tests (no Qt needed)."""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations

import ast
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
import tempfile
from unittest.mock import patch

from suite_pythoine.suite_uninstall_worker import (
    UnsafePlan, _signature, _stat_identity, execute_plan, validate_plan,
)

PACKAGE = Path(__file__).resolve().parents[1]


def run_regressions(errors: list[str]) -> None:
    def check(ok, message):
        if not ok:
            errors.append('0.9.0 uninstall: ' + message)

    with tempfile.TemporaryDirectory(prefix='suite090-uninstall-') as folder:
        base = Path(folder)
        root = base / 'applications'; root.mkdir()
        desktop_dir = base / 'desktop'; desktop_dir.mkdir()
        config_base = base / 'configs'; config_base.mkdir()
        config_dir = config_base / 'suite-pythoine'; config_dir.mkdir()
        config_file = config_dir / 'suite-pythoine.json'
        config_file.write_text(json.dumps({'editors_root':str(root),'editor_overrides': {
            'suite-pythoine':{'launch_mode':'portable'}, 'ricopad': {'active_version':'0.8.0'},
            'markopad': {'active_version':'0.1.0'}},
            'extension_preferences':{'.rtf':'ricopad','.md':'markopad'},
            'last_selected_editor':'ricopad', 'routing_index':{'test':1}}))
        roots = {}
        for app, version in [('Suite Pythoine','0.9.0'),('Ricopad','0.8.0'),('Markopad','0.1.0')]:
            target = root / app / version
            (target / 'Portable').mkdir(parents=True)
            (target / 'Portable' / 'main.py').write_text('print(1)')
            (target / 'Recovery').mkdir()
            (target / 'Recovery' / 'source.zip').write_bytes(b'archive')
            roots[app] = target
        ricopad_prefs = config_base / 'ricopad'; ricopad_prefs.mkdir()
        (ricopad_prefs / 'ricopad.json').write_text('{}')
        mimeapps = base / 'mimeapps.list'
        mimeapps.write_text('[Default Applications]\napplication/pdf=io.github.brunonlinespace.suite-pythoine.desktop;org.example.Reader.desktop;\napplication/rtf=io.github.brunonlinespace.ricopad.desktop;\n[Added Associations]\napplication/rtf=io.github.brunonlinespace.ricopad.desktop;io.github.brunonlinespace.markopad.desktop;\n[Unrelated]\nValue=io.github.brunonlinespace.ricopad.desktop;\n')
        desktop = desktop_dir / 'io.github.brunonlinespace.suite-pythoine.desktop'
        desktop.write_text('[Desktop Entry]\nName=Suite Pythoine\n')
        def plan(mode='hub', ids=('suite-pythoine',), app_prefs=False, hub_prefs=False):
            links = [('suite-pythoine',roots['Suite Pythoine'])]
            if 'ricopad' in ids: links.append(('ricopad',roots['Ricopad']))
            if 'markopad' in ids: links.append(('markopad',roots['Markopad']))
            targets = []
            for key, path in links:
                target = _signature(path,'version'); target.update(component_id=key, version=path.name)
                targets.append(target)
            target = _signature(desktop, 'desktop'); target['component_id'] = 'suite-pythoine'; targets.append(target)
            if app_prefs:
                target = _signature(ricopad_prefs,'component-preferences'); target['component_id']='ricopad'; targets.append(target)
            if hub_prefs:
                targets.append(_signature(config_file,'hub-preferences'))
            selected_desktop_ids = [f'io.github.brunonlinespace.{name}.desktop' for name in ids]
            mime = (_signature(mimeapps, 'mimeapps') if any(token in mimeapps.read_text() for token in selected_desktop_ids) else None)
            return dict(schema=1,mode=mode,root=str(root),root_identity=_stat_identity(root),
                        root_entries=sorted(p.name for p in root.iterdir()), selected_ids=list(ids),targets=targets,desktop_dir=str(desktop_dir),
                        bridge_dir=str(base/'bin'),mimeapps=mime,
                        config_dir=str(config_dir),component_config_base=str(config_base),
                        config_file=str(config_file),remove_hub_preferences=hub_prefs,
                        remove_component_preferences=app_prefs,report_path=str(base/'report.txt'))
        current = plan()
        check(len(validate_plan(current)) == 2, 'Hub Only preflight must select only Hub version/desktop')
        # Hub Only should not rewrite retained Hub preferences, even to clear
        # a cache; compare exact original bytes after a real dry fixture purge.
        from suite_pythoine.suite_uninstall_worker import _clear_removed_component_choices
        original_config = config_file.read_bytes()
        _clear_removed_component_choices(current)
        check(config_file.read_bytes() == original_config, 'Hub Only rewrote preserved Hub preferences')
        config_file.write_bytes(b'{malformed preserved preferences')
        _clear_removed_component_choices(current)
        check(config_file.read_bytes() == b'{malformed preserved preferences', 'Hub Only parsed or modified malformed retained preferences')
        config_file.write_bytes(original_config)
        # Changed inode after review must stop without changing any other entry.
        snapshot = plan()
        renamed = root/'Suite Pythoine'/'hold'
        roots['Suite Pythoine'].rename(renamed)
        roots['Suite Pythoine'].mkdir()
        try:
            validate_plan(snapshot)
            check(False, 'changed physical version after review accepted')
        except UnsafePlan:
            pass
        roots['Suite Pythoine'].rmdir(); renamed.rename(roots['Suite Pythoine'])
        # Unexpected content must block the whole component, not be guessed.
        unexpected = roots['Suite Pythoine']/'personal-notes.txt'; unexpected.write_text('preserve')
        try:
            validate_plan(plan())
            check(False,'unknown file inside exact version root accepted')
        except UnsafePlan:
            pass
        unexpected.unlink()
        # Unknown extra version must also block a claimed whole-component purge.
        extra = root/'Suite Pythoine'/'unknown-version'; extra.mkdir()
        try:
            validate_plan(plan())
            check(False,'unreviewed sibling version accepted')
        except UnsafePlan:
            pass
        extra.rmdir()
        # A purported Hub Only plan must not include any non-Hub component.
        try:
            validate_plan(plan('hub',('suite-pythoine','ricopad')))
            check(False,'Hub Only widened to another application')
        except UnsafePlan:
            pass
        # Explicit zero-extra selective removal is allowed.
        check(len(validate_plan(plan('selective'))) == 2, 'zero-extra Selective must match Hub Only')
        # Check actual isolated destructive code; skip /proc lookup in deterministic fixture.
        with patch('suite_pythoine.suite_uninstall_worker._running_selected_processes', return_value=[]):
            report = execute_plan(plan('selective',('suite-pythoine','ricopad'),True,False))
        check('SUCCESS:' in report, 'Selective cleanup failed')
        check(not roots['Suite Pythoine'].exists() and not roots['Ricopad'].exists()
              and roots['Markopad'].is_dir(), 'Selective removal touched unselected Markopad')
        check(not ricopad_prefs.exists() and config_file.is_file(),
              'selected app preferences or preserved Hub preferences incorrect')
        updated = json.loads(config_file.read_text())
        check('ricopad' not in updated['editor_overrides'] and 'markopad' in updated['editor_overrides'] and
              '.rtf' not in updated['extension_preferences'] and '.md' in updated['extension_preferences'],
              'retained Hub configuration still routes purged applications')
        check(not desktop.exists() and root.is_dir() and config_base.is_dir(),
              'verified desktop target or parent-boundary safety incorrect')
        new_mime = mimeapps.read_text()
        check('application/pdf=org.example.Reader.desktop;' in new_mime and
              'application/rtf=io.github.brunonlinespace.markopad.desktop;' in new_mime and
              '[Unrelated]\nValue=io.github.brunonlinespace.ricopad.desktop;' in new_mime and
              'application/rtf=io.github.brunonlinespace.ricopad.desktop;' not in new_mime,
              'selected MIME defaults not safely retired while preserving alternatives and unrelated sections')

    # End-to-end FULL purge through the genuine copied worker. Keeping the
    # parent's pipe open MUST keep all targets untouched, even after the helper
    # starts. Releasing it simulates Hub process exit, without a GUI or sudo.
    with tempfile.TemporaryDirectory(prefix='suite090-postexit-') as folder:
        base = Path(folder)
        root = base/'applications'; root.mkdir()
        targets = []
        for app_id, display in (('suite-pythoine','Suite Pythoine'), ('ricopad','Ricopad')):
            version = root/display/'0.9.0'
            (version/'Portable').mkdir(parents=True)
            (version/'Portable'/'main.py').write_text('print(1)')
            (version/'Recovery').mkdir()
            (version/'Recovery'/'original.zip').write_bytes(b'byte-for-byte recovery')
            target = _signature(version, 'version')
            target.update(component_id=app_id, version='0.9.0')
            targets.append(target)
        unmanaged = root/'External Documents'; unmanaged.mkdir()
        (unmanaged/'document.txt').write_text('NEVER DELETE')
        desktop = base/'desktop'; desktop.mkdir()
        cfgbase = base/'cfg'; cfgbase.mkdir()
        cfgdir = cfgbase/'suite-pythoine'; cfgdir.mkdir()
        bridge = base/'bin'; bridge.mkdir()
        plan = dict(schema=1, mode='full', root=str(root), root_identity=_stat_identity(root),
                    root_entries=sorted(path.name for path in root.iterdir()),
                    selected_ids=['suite-pythoine', 'ricopad'], targets=targets,
                    desktop_dir=str(desktop), config_dir=str(cfgdir), bridge_dir=str(bridge),
                    component_config_base=str(cfgbase), config_file=str(cfgdir/'suite-pythoine.json'),
                    mimeapps=None, remove_hub_preferences=False, remove_component_preferences=False,
                    report_path=str(base/'last-uninstall-report.txt'))
        private = base/'private-helper'; private.mkdir(mode=0o700)
        source_worker = PACKAGE/'suite_uninstall_worker.py'
        script = private/'worker.py'; shutil.copyfile(source_worker,script)
        plan_file = private/'reviewed-plan.json'; plan_file.write_text(json.dumps(plan))
        reader, writer = os.pipe()
        worker = subprocess.Popen([sys.executable,'-I',str(script),str(plan_file),str(reader)],
                                  pass_fds=(reader,), stdin=subprocess.DEVNULL,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        os.close(reader)
        try:
            time.sleep(0.12)
            check(worker.poll() is None and all(Path(t['path']).exists() for t in targets),
                  'copied helper ran while Hub exit pipe remained open')
        finally:
            os.close(writer)
        _stdout, stderr = worker.communicate(timeout=15)
        report = (base/'last-uninstall-report.txt').read_text() if (base/'last-uninstall-report.txt').is_file() else ''
        check(worker.returncode == 0 and 'SUCCESS:' in report and all(not Path(t['path']).exists() for t in targets),
              'FULL post-exit independent helper failed: ' + stderr.decode(errors='replace')[:300])
        check((unmanaged/'document.txt').read_text() == 'NEVER DELETE' and root.is_dir(),
              'FULL purge deleted an unrelated Applications-root item or the root itself')

    app = read_app_with_presentations()
    preferences = (PACKAGE/'ui/dialogs/preferences.py').read_text()
    source = (PACKAGE/'suite_uninstall.py').read_text()
    tour = (PACKAGE/'ui/dialogs/quick_tour.py').read_text()
    config = (PACKAGE/'config.py').read_text()
    package = (PACKAGE/'packaging/fedora/build-appimage.sh').read_text()
    check(all(token in source for token in ('Uninstall Hub Only','Selective Suite Purge','Full Suite Purge',
          'Nothing else is selected by default', 'remove_hub_preferences','remove_component_preferences',
          'confirm.setChecked(False)', 'full_confirm.setChecked(False)', 'pass_fds=(read_fd,)',
          'start_new_session=True', 'self.handoff_ready = True')),
          'wizard mode/confirmation/helper handoff contract missing')
    check('QAction("Quick Tour…", self)' in app and 'setShortcut("Shift+F1")' in app and
          app.index('help_menu.addAction(self.documentation_action)') < app.index('help_menu.addAction(self.quick_tour_action)') <
          app.index('help_menu.addAction(self.shortcuts_action)') and
          'QTimer.singleShot(0, window.show_quick_tour)' in app and
          '"show_quick_tour_on_startup": True' in config and
          'self.show_quick_tour_on_startup.isChecked()' in preferences and
          "config.set('show_quick_tour_on_startup'" in tour,
          'first-launch Quick Tour, opt-out and Shift+F1 Help integration missing')
    check('Hub Preferences…' in app and 'app_dialog_title("Hub Preferences")' in preferences and
          'self.uninstall_suite_button = QPushButton("Uninstall Suite…")' in preferences and
          'removal_button = QPushButton("Uninstall Suite…")' in app and
          'removal_button.clicked.connect(self.show_uninstall_suite)' in app and
          'self.preferences_action = QAction("Hub Preferences…", self)' in app and
          'tools.addAction(self.uninstall_suite_action)' not in app,
          'two allowed destructive entry points or Hub Preferences naming regressed')
    check('_begin_post_exit_shutdown(preserve_reviewed_preferences=True)' in app and
          'if self._suite_uninstall_exiting:' in app and
          app.index('if self._suite_uninstall_exiting:', app.index('def closeEvent(')) <
          app.index('self._save_inventory_table_layout()', app.index('def closeEvent(')),
          'reviewed uninstall handoff does not preserve the confirmed preference snapshot')
    check("if mode == 'full'" in source and "if mode == 'selective' else False" in source,
          'FULL must offer optional selected-application preferences removal')
    check('suite_uninstall_worker.py:suite_pythoine' in package, 'frozen build missing standalone worker source')
    check(len(ast.literal_eval(next(n.value for n in ast.parse(tour).body
           if isinstance(n,ast.AnnAssign) and isinstance(n.target,ast.Name) and n.target.id=='CHAPTERS'))) == 12,
          'Quick Tour chapter coverage incomplete')
    print('PASS: 0.9.0 exact uninstall safety, selective isolation, preference retention, Quick Tour/GUI contracts'
          if not any(e.startswith('0.9.0 uninstall:') for e in errors) else 'CHECK: 0.9.0 uninstall regression suite')
