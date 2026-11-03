"""0.8.1 dependency-light filesystem/desktop/Recovery acceptance tests.

These are real temporary-file transactions, not checks that source contains a
particular string. Does not import Qt, execute components, or touch user data.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch
import zipfile

from suite_pythoine.config import ConfigService
from suite_pythoine.installation_state import desktop_selection, get_managed_versions
from suite_pythoine.installer import (InstallError, desktop_entry_path,
    sha256_file, synchronize_portable_desktop_integration, write_appimage_metadata)
from suite_pythoine.registry import discover_editors
from suite_pythoine.recovery import (install_portable_with_recovery, recovery_available,
    restore_portable_from_recovery, validate_recovery_archive)
from suite_pythoine.registry_retirement import retire_registry
from suite_pythoine.storage_layout import validate_version_boundary
from suite_pythoine.routing.routing_index import target_from_component
from suite_pythoine.routing.silent_dispatch import load_routing_targets


def source_zip(path: Path, *, version: str = '0.1.0', body: str = 'print(1)\n',
               component_id: str = 'markopad') -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('markopad-source/main.py', body)
        archive.writestr('markopad-source/suite-pythoine-component.json', json.dumps({
            'id': component_id, 'name':'Markopad', 'version': version,
            'publisher_id': 'brunonlinespace', 'portable_command': ['main.py']}))


def discover(root: Path, preferences: dict | None = None):
    prefs = preferences if preferences is not None else {'editor_overrides': {}}
    return discover_editors(root, root, prefs, python_executable=sys.executable)


def run_regressions(errors: list[str]) -> None:
    def check(ok, description):
        if not ok:
            errors.append('0.8.1: ' + description)

    with TemporaryDirectory(prefix='suite081-registryfree-') as temp:
        base = Path(temp)
        root = base / 'Suite Pythoine'
        root.mkdir()
        pref_path = base / 'prefs.json'
        obsolete = base / 'managed-registry.json'
        pref_path.write_text(json.dumps({'dashboard_view':'grid',
            'managed_installations': {'markopad': {'fake': True}},
            'editor_overrides': {'markopad': {'active_version':'0.1.0'}}}))
        obsolete.write_text(json.dumps({'broken':'old data'}))
        conf = ConfigService(pref_path, registry_path=obsolete)
        check(not obsolete.exists(), 'obsolete central registry was not deleted unconditionally')
        check(conf.get('dashboard_view') == 'grid', 'ordinary preferences lost on registry retirement')
        check('managed_installations' not in conf.as_dict(), 'legacy ownership data re-entered memory')
        check(conf.save() and 'managed_installations' not in json.loads(pref_path.read_text()),
              'preference save resurrected obsolete registry')
        check(not list(base.glob('*registry*')), 'registry retirement left a backup/database')
        # The exact path must be UNLINKED, not resolved through a symlink.
        outside = base / 'must-survive.json'
        outside.write_text('precious')
        link = base / 'old-registry-link.json'
        link.symlink_to(outside)
        retire_registry(link)
        check(outside.read_text() == 'precious' and not link.exists(),
              'registry retirement followed a symlink into unrelated user data')

        archive = base / 'markopad-0.1.0-source.zip'
        source_zip(archive)
        initial_hash = sha256_file(archive)
        portable = root / 'Markopad' / '0.1.0' / 'Portable'
        installed, editor, copied_zip, metadata = install_portable_with_recovery(
            archive, portable, editors_root=root, editor_id='markopad', name='Markopad',
            version='0.1.0', expected_sha256=initial_hash, config=conf.as_dict(),
            installed_dir=root, python_executable=sys.executable)
        check(installed == portable and editor.editor_id == 'markopad' and editor.source_version == '0.1.0',
              'ZIP did not install declared exact Portable')
        check(copied_zip.read_bytes() == archive.read_bytes() and recovery_available(copied_zip.parent),
              'ZIP installation did not retain original byte-for-byte Recovery')
        check(json.loads(metadata.read_text())['sha256'] == initial_hash,
              'Recovery integrity metadata mismatched copied original')
        check(not (portable.parent / 'AppImage').exists(),
              'normal ZIP installation unnecessarily built an AppImage')

        with patch.dict(os.environ, {'XDG_DATA_HOME': str(base / 'xdg-data')}):
            cfg = {'editor_overrides': {}}
            entries = discover(root, cfg)
            e = next(x for x in entries if x.editor_id == 'markopad')
            check(e.active_version is None and e.desktop_issue == 'selection-required',
                  'new manually placed installation was silently activated')
            check(len(e.versions) == 1 and e.versions[0].has_portable,
                  'valid version not discovered from files after registry deletion')
            check(not target_from_component(e).command(),
                  'file router could launch unselected manual installation')
            target = synchronize_portable_desktop_integration('Markopad','markopad',
                e.versions[0].portable_command, None, portable)
            e = next(x for x in discover(root, cfg) if x.editor_id == 'markopad')
            check(e.active_version == '0.1.0' and e.desktop_issue == 'ready'
                  and e.desktop_runtime == 'portable', 'real verified Portable desktop not authoritative')
            check(target_from_component(e).command() == e.versions[0].portable_command,
                  'router ignores authoritative Portable desktop selection')
            target.unlink()
            check(next(x for x in discover(root,cfg) if x.editor_id == 'markopad').desktop_issue == 'selection-required',
                  'missing desktop did not require selection when no preference exists')
            cfg['editor_overrides'] = {'markopad': {'active_version':'0.1.0', 'launch_mode':'portable'}}
            e = next(x for x in discover(root,cfg) if x.editor_id == 'markopad')
            check(e.desktop_issue == 'missing' and e.active_version == '0.1.0',
                  'missing desktop did not use remembered active selection')
            target = synchronize_portable_desktop_integration('Markopad','markopad',
                e.versions[0].portable_command, None, portable)
            original_launcher = target.read_text()
            target.write_text(original_launcher.replace('X-Suite-Pythoine-Managed=true',
                                                      'X-Suite-Pythoine-Managed=false'))
            e = next(x for x in discover(root,cfg) if x.editor_id == 'markopad')
            check(e.desktop_issue == 'legacy-launcher' and e.command() is None,
                  'old/unknown desktop marker was accepted for normal launching')
            target.write_text(original_launcher.replace(str(portable / 'main.py'),
                                                      str(base / 'missing-main.py')))
            e = next(x for x in discover(root,cfg) if x.editor_id == 'markopad')
            check(e.desktop_issue == 'external-target' and e.command() is None,
                  'external desktop target was silently adopted or routed')
            # A stale launcher inside managed root is broken, never inferred anew.
            target.write_text(original_launcher.replace('0.1.0/Portable/main.py','0.9.0/Portable/main.py'))
            e = next(x for x in discover(root,cfg) if x.editor_id == 'markopad')
            check(e.desktop_issue == 'broken' and e.command() is None,
                  'broken internal launcher was automatically bypassed')
            target.write_text(original_launcher)
            e = next(x for x in discover(root,cfg) if x.editor_id == 'markopad')
            check(e.desktop_issue == 'ready' and e.available,
                  'restoring verified launcher did not restore normal launch')
            # Cached routing is forbidden from masking edits to an external desktop file.
            target.unlink()
            cached = {'editor_overrides': {},'routing_index': {'schema':999, 'components':[{'fake':True}]}}
            targets,_,from_cache = load_routing_targets({'editors_root':str(root), **cached})
            marko = next(x for x in targets if x.component_id=='markopad')
            check(not from_cache and marko.command() is None,
                  'silent dispatch reused a stale cache after desktop launcher deletion')

        # Same-version new ZIP replaces both Portable+Recovery but NOT AppImage.
        app_dir = portable.parent / 'AppImage'
        app_dir.mkdir()
        existing_appimage = app_dir / 'Markopad-0.1.0-x86_64.AppImage'
        existing_appimage.write_bytes(b'test artifact stays untouched')
        other = base / 'markopad-0.1.0-reissue.zip'
        source_zip(other, body='print(2)\n')
        second_hash = sha256_file(other)
        check(second_hash != initial_hash, 'test reissue unexpectedly has identical hash')
        old_portable = (portable/'main.py').read_bytes()
        old_recovery = copied_zip.read_bytes()
        with patch('suite_pythoine.recovery.retain_recovery_archive', side_effect=OSError('injected retention failure')):
            try:
                install_portable_with_recovery(other, portable, editors_root=root, editor_id='markopad',
                    name='Markopad', version='0.1.0', expected_sha256=second_hash,
                    config=conf.as_dict(), installed_dir=root, python_executable=sys.executable)
                errors.append('0.8.1: failed Recovery retention incorrectly completed ZIP replacement')
            except OSError:
                pass
        check((portable/'main.py').read_bytes() == old_portable
              and copied_zip.read_bytes() == old_recovery,
              'failed ZIP retention did not jointly roll back Portable and Recovery')
        check(existing_appimage.read_bytes() == b'test artifact stays untouched',
              'failed ZIP reinstall touched same-version AppImage')
        install_portable_with_recovery(other,portable,editors_root=root,editor_id='markopad',
            name='Markopad',version='0.1.0',expected_sha256=second_hash,
            config=conf.as_dict(),installed_dir=root,python_executable=sys.executable)
        check((portable/'main.py').read_text() == 'print(2)\n'
              and sha256_file(copied_zip) == second_hash,
              'confirmed same-version source replacement did not update Portable+Recovery together')
        check(existing_appimage.read_bytes() == b'test artifact stays untouched',
              'reissuing ZIP modified existing AppImage')
        # Recovery hash override only bypasses the prior checksum: identity and
        # ZIP structural checks remain mandatory.
        source_zip(copied_zip, body='print(3)\n')
        try:
            validate_recovery_archive(copied_zip.parent, expected_editor_id='markopad',expected_version='0.1.0')
            errors.append('0.8.1: checksum-altered Recovery accepted without override')
        except InstallError:
            pass
        info, inspection = validate_recovery_archive(copied_zip.parent,
            expected_editor_id='markopad',expected_version='0.1.0',allow_checksum_mismatch=True)
        check(info.sha256 == second_hash and inspection.archive_sha256 != info.sha256,
              'explicit override silently replaced stored Recovery SHA')
        try:
            validate_recovery_archive(copied_zip.parent,expected_editor_id='ricopad',
                expected_version='0.1.0',allow_checksum_mismatch=True)
            errors.append('0.8.1: checksum override also bypassed trusted component identity')
        except InstallError:
            pass
        restored, _ = restore_portable_from_recovery(copied_zip.parent,portable,editors_root=root,
            expected_editor_id='markopad',expected_version='0.1.0',allow_checksum_mismatch=True,
            config=conf.as_dict(),installed_dir=root,python_executable=sys.executable)
        check((restored/'main.py').read_text()=='print(3)\n' and info.sha256==second_hash,
              'checksum override cannot perform a valid explicitly authorised restore')
        # Q12: unexpected root file blocks Uninstall Version/Purge deletion.
        (portable.parent/'personal-notes.txt').write_text('keep me')
        try:
            validate_version_boundary(portable.parent,root)
            errors.append('0.8.1: unexpected version-root files were accepted for deletion')
        except ValueError:
            pass
        (portable.parent/'personal-notes.txt').unlink()
        validate_version_boundary(portable.parent,root)
        # Mismatch must not be legitimised solely by renaming the directory.
        mismatch = root/'Markopad'/'0.9.0'/'Portable'
        mismatch.mkdir(parents=True)
        (mismatch/'main.py').write_text("print('different')\n")
        (mismatch/'suite-pythoine-component.json').write_text(json.dumps({
            'id':'markopad','name':'Markopad','version':'0.1.0', 'portable_command':['main.py']}))
        entries=discover(root, {'editor_overrides': {}})
        marko=next(x for x in entries if x.editor_id=='markopad')
        check(any(v.version=='0.9.0' and v.validation_issue for v in marko.versions),
              'folder-versus-source version mismatch not visibly blocked')
        rogue = root/'Unrecognised'/'1.0'/'Portable'
        rogue.mkdir(parents=True)
        (rogue/'main.py').write_text('print(1)\n')
        (rogue/'suite-pythoine-component.json').write_text(json.dumps({'id':'unrecognised','version':'1.0'}))
        check(all(e.editor_id!='unrecognised' for e in discover(root)),
              'unknown third-party component was accepted as trusted')
        metadata = write_appimage_metadata(existing_appimage,editor_id='markopad',
            application_id='markopad',publisher_id='brunonlinespace',name='Markopad',
            version='0.1.0',desktop_file=None,desktop_id='io.github.brunonlinespace.markopad',
            desktop_integrated=False,icon=None)
        sidecar=json.loads(metadata.read_text())
        check('sha256' in sidecar or 'appimage_sha256' in sidecar,
              'AppImage verification metadata lost checksum')
        check(not {'desktop_integrated','desktop_file_path'} & set(sidecar),
              'AppImage sidecar still mirrors retired desktop ownership state')
        # Q24: filesystem inventory may show retained-only version without
        # requiring any AppImage, launcher or central record.
        portable.rename(portable.with_name('Portable-temporary'))
        try:
            (portable.with_name('Portable-temporary')).rename(portable)
        finally:
            pass


if __name__ == '__main__':
    failures: list[str] = []
    run_regressions(failures)
    for failure in failures:
        print('FAIL:',failure)
    if failures:
        raise SystemExit(f'{len(failures)} regression(s) failed')
    print('PASS: 0.8.1 live-filesystem ownership, desktop, ZIP+Recovery and retirement regressions')
