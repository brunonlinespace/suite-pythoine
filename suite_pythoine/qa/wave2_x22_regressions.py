"""x2.2 strict, byte-level preservation across the catalogue source relocation.

Record comparisons are against immutable x2.1 SHA-256 hashes. Every allowed
import/resource-path adaptation is an exact reversible single-line edit.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from suite_pythoine.qa.wave2_x25_source import old_relative
from suite_pythoine.qa.wave2_x23_regressions import original_x22_path, x22_source

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / 'suite_pythoine'
TRANSFER = PKG / 'docs/WAVE2_X22_TRANSFER.json'
TRANSFER_SHA256 = 'e7656f5ef875c4ca52565c79d9d1d095c6d03204ebc604d5304cd4eb7ff28d25'


def preserved_sha256(path: Path) -> str:
    """Historical SHA checks see the x2.1 source, reversing only approved edits."""
    text = x22_source(path)
    data = json.loads(TRANSFER.read_text(encoding='utf-8'))
    current = old_relative(path.relative_to(ROOT).as_posix())
    current = {v:k for k,v in json.loads(
        (PKG/'docs/WAVE2_X23_TRANSFER.json').read_text(encoding='utf-8'))['moves'].items()}.get(current,current)
    old_paths = {new: old for old, new in data['moves'].items()}
    # Recover pre-x2.4 module key before looking up the x2.2 import ledger.
    current = {v:k for k,v in json.loads((PKG/'docs/WAVE2_X24_TRANSFER.json').read_text(encoding='utf-8'))['moves'].items()}.get(current,current)
    original = old_paths.get(current,current)
    for before, after in data['edits'].get(original, []):
        assert text.count(after) == 1, (current, after)
        text = text.replace(after,before)
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def run_regressions(errors: list[str]) -> None:
    def check(truth: bool, message: str) -> None:
        if not truth:
            errors.append('1.0.0-x2.2 STRICT catalogue relocation: ' + message)

    check(TRANSFER.is_file(), 'transfer inventory missing')
    if not TRANSFER.is_file():
        return
    check(hashlib.sha256(TRANSFER.read_bytes()).hexdigest() == TRANSFER_SHA256,
          'transfer inventory modified')
    data = json.loads(TRANSFER.read_text(encoding='utf-8'))
    check(data['baseline_release'] == '1.0.0-x2.1', 'baseline version changed')
    sources = data['original_sha256']
    moves = data['moves']
    edits = data['edits']
    expected = {original_x22_path(moves.get(p,p)).relative_to(ROOT).as_posix() for p in sources} | set(data['new_production_files']) | {'suite_pythoine/store/__init__.py', 'suite_pythoine/developer/__init__.py','suite_pythoine/routing/__init__.py','suite_pythoine/runtime/__init__.py'}
    current = {'main.py'} | {p.relative_to(ROOT).as_posix() for p in PKG.rglob('*.py')
                         if not any(part in ('qa','tools','packaging') for part in p.relative_to(PKG).parts)}
    check(expected == current,
          'production path mismatch: removed=' + str(sorted(expected-current))
          + ' added=' + str(sorted(current-expected)))
    check(set(moves) == {'suite_pythoine/component_catalog.py', 'suite_pythoine/component_policy.py'},
          'unexpected source move')
    check(hashlib.sha256((ROOT/'README.md').read_bytes()).hexdigest() == data['immutable_root_readme'],
          'immutable GitHub README modified')
    check((PKG/'catalogue/__init__.py').read_bytes() == b'',
          'catalogue package initializer must have no implementation')
    for oldpath, expected_sha in sources.items():
        dest = original_x22_path(moves.get(oldpath,oldpath))
        if not dest.is_file():
            check(False,'missing original/relocated module: ' + str(dest))
            continue
        body = x22_source(dest)
        for before, after in edits.get(oldpath, []):
            check(body.count(after) == 1, f'{dest}: expected authorized edit exactly once: {after}')
            body=body.replace(after,before)
        check(hashlib.sha256(body.encode('utf-8')).hexdigest() == expected_sha,
              'unapproved implementation change: ' + dest.relative_to(ROOT).as_posix())
        if oldpath in moves:
            check(not (ROOT/oldpath).exists(), 'duplicate old module at ' + oldpath)
    # Catalogue files still remain at the original package-root location.
    from suite_pythoine.catalogue.component_catalog import (
        BUNDLED_CATALOG_PATH, BUNDLED_CATALOG_ICON_DIR, COMPONENT_PROFILES,
        load_catalog, bundled_catalog_icon_path, catalog_revision,
    )
    check(BUNDLED_CATALOG_PATH == (PKG/'components.json'), 'bundled JSON path drift')
    check(BUNDLED_CATALOG_ICON_DIR == (PKG/'assets/catalog'), 'bundled icon directory drift')
    check(BUNDLED_CATALOG_PATH.is_file() and BUNDLED_CATALOG_ICON_DIR.is_dir(),
          'bundled catalogue resources missing')
    check('suite-pythoine' in load_catalog() and bool(COMPONENT_PROFILES),
          'bundled profiles not loaded')
    check(catalog_revision(BUNDLED_CATALOG_PATH) >= 1, 'catalogue revision regressed')
    check(bundled_catalog_icon_path('nuxpad') is not None,
          'bundled catalogue icon resolution broken')
