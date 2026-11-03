"""x2.4: enforce byte-exact CODE PRESERVATION TRANSFER from x2.3.

Reconstruct every original production Python source, rejecting any executable
modification outside the finite documented set of module moves and import/path
adjustments. This test is headless and makes no changes to user state.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from suite_pythoine.qa.wave2_x25_source import current_path, source_x24

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / 'suite_pythoine'
TRANSFER = PKG / 'docs/WAVE2_X24_TRANSFER.json'
TRANSFER_SHA256 = '6c08c98325a7cd3761fec259b8323e0667ac7d0fe238df3ed17376d066c2a79b'
EXPECTED_MOVES = {f'suite_pythoine/{name}.py': f'suite_pythoine/developer/{name}.py'
    for name in ('developer_intake', 'developer_archive', 'developer_intake_vault', 'developer_policy')}
EXPECTED_EDIT_FILES = {
    'main.py', 'suite_pythoine/app.py', 'suite_pythoine/__init__.py',
    'suite_pythoine/ui/dialogs/preferences.py',
    'suite_pythoine/developer_intake.py', 'suite_pythoine/developer_archive.py',
}


def original_x23_path(relative: str) -> Path:
    """Look up a path from x2.3 at its current x2.4 location."""
    return current_path(EXPECTED_MOVES.get(relative, relative))


def x23_source(path: Path) -> str:
    """Undo exactly x2.4 source edits to yield original x2.3 bytes."""
    document = json.loads(TRANSFER.read_text(encoding='utf-8'))
    current = path.relative_to(ROOT).as_posix()
    prior = {v: k for k,v in document['moves'].items()}.get(current,current)
    value = source_x24(path)
    for before,after in document['edits'].get(prior,[]):
        assert before != after and value.count(after) == 1, (current,after)
        value=value.replace(after,before)
    return value


def run_regressions(errors: list[str]) -> None:
    def check(value: bool, message: str) -> None:
        if not value:
            errors.append('1.0.0-x2.4 CODE PRESERVATION TRANSFER: '+message)
    if not TRANSFER.is_file():
        check(False,'missing transfer ledger'); return
    check(hashlib.sha256(TRANSFER.read_bytes()).hexdigest()==TRANSFER_SHA256,'transfer ledger modified')
    doc = json.loads(TRANSFER.read_text(encoding='utf-8'))
    check(doc['baseline_release']=='1.0.0-x2.3' and doc['release']=='1.0.0-x2.4', 'wrong version lineage')
    check(doc['moves']==EXPECTED_MOVES, 'unexpected module moves')
    check(set(doc['edits'])==EXPECTED_EDIT_FILES, 'unexpected source modifications')
    check(doc['new_production_files']==['suite_pythoine/developer/__init__.py'], 'unexpected added production file')
    check((PKG/'developer/__init__.py').read_bytes()==b'', 'initializer may not add code')
    for prior, current in EXPECTED_MOVES.items():
        check(not (ROOT/prior).exists() and (ROOT/current).is_file(), 'module duplication/missing: '+prior)
    check(hashlib.sha256((ROOT/'README.md').read_bytes()).hexdigest()==doc['immutable_root_readme'], 'GitHub README changed')
    check(hashlib.sha256((ROOT/'LICENSE').read_bytes()).hexdigest()==doc['license_sha256'], 'LICENSE changed')
    expected = {current_path(EXPECTED_MOVES.get(p,p)).relative_to(ROOT).as_posix() for p in doc['original_sha256']} | set(doc['new_production_files']) | {'suite_pythoine/routing/__init__.py','suite_pythoine/runtime/__init__.py'}
    actual = {'main.py'} | {p.relative_to(ROOT).as_posix() for p in PKG.rglob('*.py')
        if not any(k in p.relative_to(PKG).parts for k in ('qa','tools','packaging'))}
    check(actual==expected, 'production module inventory drift: '+str(sorted(actual^expected)))
    for prior, digest in doc['original_sha256'].items():
        current=original_x23_path(prior)
        if not current.is_file():check(False, 'missing '+prior);continue
        try:
            reconstructed=x23_source(current).encode('utf-8')
            check(hashlib.sha256(reconstructed).hexdigest()==digest,
                'unauthorized implementation change: '+current.relative_to(ROOT).as_posix())
        except (ValueError,AssertionError) as err:
            check(False, f'unreversible difference: {prior}: {err}')
    # The original icon stays in assets at the pre-move location.
    relocated=(PKG/'developer/developer_intake.py').read_text(encoding='utf-8')
    check('Path(__file__).resolve().parent.parent / "assets" / "suite-pythoine-128.png"' in relocated,
          'Developer Intake logo no longer points to original package assets')
    check((PKG/'assets/suite-pythoine-128.png').is_file(), 'original logo missing')
    # Import consumers and no old path imports, including suspended imports.
    for src in (ROOT/'main.py',PKG/'app.py',PKG/'ui/dialogs/preferences.py'):
        tree=ast.parse(src.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node,ast.ImportFrom) and node.module:
                check(not (node.module.startswith('developer_') or node.module.startswith('suite_pythoine.developer_')),
                      'stale developer import in '+src.name)
    from suite_pythoine.developer.developer_archive import exact_source_version
    from suite_pythoine.developer.developer_policy import DEVELOPER_CONFIG_SCHEMA
    from suite_pythoine.developer.developer_intake_vault import DeveloperIntakeSessionVault
    check(callable(exact_source_version) and DEVELOPER_CONFIG_SCHEMA==1 and DeveloperIntakeSessionVault is not None,
          'headless Developer imports/contracts unavailable')
