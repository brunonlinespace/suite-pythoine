"""x2.3 strict source relocation gate, anchored to immutable issued x2.2 hashes.

All 72 original production Python files are covered, with only a short closed
list of exact reversible import/path edits and version identity permitted.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from suite_pythoine.qa.wave2_x24_regressions import original_x23_path, x23_source

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT/'suite_pythoine'
LEDGER = PKG/'docs/WAVE2_X23_TRANSFER.json'
LEDGER_SHA256 = 'f57feec1a2025fc5fae605c015fdc94b3add7479b123dddd92fda0ea33b42e82'


def original_x22_path(relative: str) -> Path:
    """Resolve only x2.3 Store moves; previous relocations use their own ledgers."""
    if relative == 'suite_pythoine/store_bridge.py':
        relative = 'suite_pythoine/store/store_bridge.py'
    elif relative == 'suite_pythoine/store_content.py':
        relative = 'suite_pythoine/store/store_content.py'
    return original_x23_path(relative)


def x22_source(path: Path) -> str:
    """Undo exactly the x2.3 edits, yielding the identical x2.2 source."""
    relative = path.relative_to(ROOT).as_posix()
    data = json.loads(LEDGER.read_text(encoding='utf-8'))
    reverse = {v:k for k,v in data['moves'].items()}
    prior = reverse.get(relative,relative)
    source = x23_source(path)
    for before, after in data['edits'].get(prior,[]):
        assert source.count(after) == 1, (relative,after)
        source = source.replace(after,before)
    return source


def run_regressions(errors: list[str]) -> None:
    def check(condition: bool, message: str) -> None:
        if not condition:
            errors.append('1.0.0-x2.3 CODE PRESERVATION TRANSFER: '+message)
    if not LEDGER.is_file():
        check(False,'missing frozen x2.2 transfer inventory')
        return
    check(hashlib.sha256(LEDGER.read_bytes()).hexdigest() == LEDGER_SHA256,
          'frozen x2.2 inventory modified')
    data = json.loads(LEDGER.read_text(encoding='utf-8'))
    check(data['baseline_release']=='1.0.0-x2.2' and data['release']=='1.0.0-x2.3',
          'wrong source lineage')
    moves=data['moves']
    check(moves == {
        'suite_pythoine/store_bridge.py':'suite_pythoine/store/store_bridge.py',
        'suite_pythoine/store_content.py':'suite_pythoine/store/store_content.py'},
          'unexpected relocated file')
    check(set(data['new_production_files']) == {'suite_pythoine/store/__init__.py'},
          'unexpected new production file')
    check((PKG/'store/__init__.py').is_file()
          and (PKG/'store/__init__.py').read_bytes()==b'',
          'Store package initializer must have no implementation')
    check(not (PKG/'store_bridge.py').exists() and not (PKG/'store_content.py').exists(),
          'obsolete Store module copy remains')
    check(hashlib.sha256((ROOT/'README.md').read_bytes()).hexdigest()
          ==data['immutable_root_readme'], 'immutable root README changed')
    check(hashlib.sha256((ROOT/'LICENSE').read_bytes()).hexdigest()
          ==data['license_sha256'], 'original LICENSE changed')
    original=data['original_sha256']
    expected={original_x23_path(moves.get(rel,rel)).relative_to(ROOT).as_posix() for rel in original} | set(data['new_production_files']) | {'suite_pythoine/developer/__init__.py','suite_pythoine/routing/__init__.py','suite_pythoine/runtime/__init__.py'}
    current={'main.py'} | {p.relative_to(ROOT).as_posix()
        for p in PKG.rglob('*.py')
        if not any(k in p.relative_to(PKG).parts for k in ('qa','tools','packaging'))}
    check(current==expected, 'production source inventory differs: missing='
          +str(sorted(expected-current))+' extra='+str(sorted(current-expected)))
    check(set(data['edits'])=={
        'suite_pythoine/store_bridge.py','suite_pythoine/store_content.py',
        'suite_pythoine/app.py','suite_pythoine/suite_uninstall.py','main.py',
        'suite_pythoine/ui/pages/store_catalogue.py','suite_pythoine/__init__.py'},
          'unauthorized changed production module')
    for prior, digest in original.items():
        path=original_x23_path(moves.get(prior,prior))
        if not path.is_file():
            check(False,'missing '+path.relative_to(ROOT).as_posix())
            continue
        try:
            restored=x22_source(path).encode('utf-8')
            check(hashlib.sha256(restored).hexdigest()==digest,
                  'unapproved code change in '+path.relative_to(ROOT).as_posix())
        except (ValueError,AssertionError) as exc:
            check(False,f'non-exact change in {prior}: {exc}')
    # Direct, Qt-free imports and resource ownership test.
    from suite_pythoine.store.store_bridge import (STORE_PROTOCOL_VERSION,managed_inventory,
                                                     trusted_catalogue_projection)
    from suite_pythoine.store.store_content import (load_store_content, published_manifest_path,
                                                      StoreContentEntry)
    check(STORE_PROTOCOL_VERSION == 2 and isinstance(trusted_catalogue_projection(),dict),
          'Store bridge contract changed')
    with TemporaryDirectory(prefix='suite-store-x23-') as folder:
        root=Path(folder)
        with patch.dict('os.environ',{'XDG_DATA_HOME':str(root)}):
            check(published_manifest_path()==root/'brunonlinespace/store-pythoine/store-content.json',
                  'Store content location changed')
            check(load_store_content()=={},'absent Store overlay contract changed')
        # Recovery for relative __file__ change: moved Store bridge must still
        # identify the unchanged project root for a direct source runtime.
        with patch('suite_pythoine.store.store_bridge.editors_root_default',return_value=root/'absent'):
            with patch('suite_pythoine.store.store_bridge.ConfigService') as config_cls:
                config_cls.return_value.get.return_value=''
                result=managed_inventory()
        expected=str(ROOT)
        found=[v for v in result['runtimes'] if v['component_id']=='suite-pythoine']
        check(len(found)==1 and found[0]['path']==expected,
              'unmanaged Suite source launcher root changed after relocation')
    for src in (PKG/'app.py',PKG/'suite_uninstall.py',PKG/'ui/pages/store_catalogue.py'):
        tree=ast.parse(src.read_text(encoding='utf-8'))
        imports=[n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
        check(not any(m in ('store_bridge','store_content') for m in imports if m),
              'old Store import retained in '+src.name)
