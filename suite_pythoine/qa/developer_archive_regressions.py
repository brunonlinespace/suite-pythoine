"""0.8.1 regression: Developer ZIP retention stays independent of installation."""
from __future__ import annotations
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch
import zipfile
from suite_pythoine.developer.developer_archive import exact_source_version, retain_developer_source_zip
from suite_pythoine.install_inspection import inspect_editor_zip
from suite_pythoine.installer import InstallError, sha256_file
from suite_pythoine.recovery import validate_recovery_archive, restore_portable_from_recovery
from suite_pythoine.registry import discover_editors
from suite_pythoine.storage_layout import recovery_root, portable_root


def source(path:Path, *,version:str='2.3.4', body:str='print(1)\n') -> None:
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('Ricopad-source/main.py',body)
        archive.writestr('Ricopad-source/suite-pythoine-component.json',json.dumps({
            'id':'ricopad','name':'Ricopad','version':version,'portable_command':['main.py']}))


def run_regressions(errors:list[str]) -> None:
    def check(result,message):
        if not result: errors.append('ZIP-retention: '+message)
    with TemporaryDirectory(prefix='suite081-devzip-') as td:
        base=Path(td); root=base/'Suite Pythoine'; root.mkdir()
        archive=base/'ricopad.zip'; source(archive); bytes_before=archive.read_bytes()
        inspection=inspect_editor_zip(archive)
        check(exact_source_version(inspection)=='2.3.4','inspected exact source version')
        result=retain_developer_source_zip(inspection,root)
        recovery=recovery_root(root,'Ricopad','2.3.4')
        check(result.archive==recovery/'original-source.zip' and result.archive.read_bytes()==bytes_before,
              'original archive was not retained exactly')
        check(not (recovery.parent/'Portable').exists() and not (recovery.parent/'AppImage').exists(),
              'Developer archive-only retention installed a runtime')
        check(archive.read_bytes()==bytes_before,'original download was consumed')
        check(not list(base.rglob('managed-registry.json')),'archive retention created a central registry')
        check(validate_recovery_archive(recovery,expected_editor_id='ricopad',expected_version='2.3.4')[0].sha256==sha256_file(archive),
              'archive cannot be validated as Recovery')
        found=next(e for e in discover_editors(root,root,{'editor_overrides':{}},python_executable=sys.executable)
                   if e.editor_id=='ricopad')
        check(found.versions[0].recovery_dir==recovery and not found.versions[0].has_portable,
              'retained-only version was not discovered without registry')
        before=result.metadata.read_bytes()
        again=retain_developer_source_zip(inspection,root)
        check(again.already_retained and result.metadata.read_bytes()==before,
              'idempotent retention overwrote metadata')
        collision=base/'different.zip';source(collision,body='print(2)\n')
        try:
            retain_developer_source_zip(inspect_editor_zip(collision),root)
            errors.append('ZIP-retention: different exact-version archive silently replaced existing Recovery')
        except InstallError: pass
        check(result.archive.read_bytes()==bytes_before,'collision modified retained ZIP')
        with patch('suite_pythoine.recovery.shutil.copyfile',side_effect=OSError('injected ENOSPC')):
            pending=base/'new.zip';source(pending,version='3.0')
            try:
                retain_developer_source_zip(inspect_editor_zip(pending),root)
                errors.append('ZIP-retention: injected copy failure was swallowed')
            except OSError: pass
        check(not recovery_root(root,'Ricopad','3.0').exists(),'failed copy left Recovery folder')
        restored,_=restore_portable_from_recovery(recovery,portable_root(root,'Ricopad','2.3.4'),
            editors_root=root,expected_editor_id='ricopad',expected_version='2.3.4',
            config={'editor_overrides':{}},installed_dir=root,python_executable=sys.executable)
        check((restored/'main.py').is_file() and result.archive.read_bytes()==bytes_before,
              'restoration failed or consumed retained ZIP')


if __name__=='__main__':
    failures=[];run_regressions(failures)
    for failure in failures:print('FAIL:',failure)
    if failures:raise SystemExit(f'{len(failures)} errors')
    print('PASS: Developer ZIP-only retention and Restore Portable regressions')
