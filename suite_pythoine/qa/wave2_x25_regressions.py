"""x2.5: strict CODE PRESERVATION TRANSFER from issued x2.4.

Restore original production-source bytes after undoing only ledgered import and
version changes. No test assertion is waived for the package moves.
"""
from __future__ import annotations
import ast
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from suite_pythoine.qa.wave2_x25_source import current_path, source_x24

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / 'suite_pythoine'
LEDGER = PKG / 'docs/WAVE2_X25_TRANSFER.json'
LEDGER_SHA256 = 'f68e65d9441d6542ace9f674d0430f97c5c873ec4eae29ab4e708ea6aa3ed2b8'
EXPECTED_MOVES = {
    **{f'suite_pythoine/{name}.py':f'suite_pythoine/routing/{name}.py'
       for name in ('routing_index','routing_chooser','silent_dispatch')},
    **{f'suite_pythoine/{name}.py':f'suite_pythoine/runtime/{name}.py'
       for name in ('runtime_launcher','runtime_paths')},
}
EXPECTED_EDITS = {
    'main.py','suite_pythoine/__init__.py','suite_pythoine/app.py',
    'suite_pythoine/appimage_build_wizard.py','suite_pythoine/install_wizard.py',
    'suite_pythoine/recovery_restore_wizard.py','suite_pythoine/self_bootstrap.py',
    'suite_pythoine/self_restore.py','suite_pythoine/ui/dialogs/preferences.py',
    'suite_pythoine/routing_index.py','suite_pythoine/routing_chooser.py',
    'suite_pythoine/silent_dispatch.py','suite_pythoine/runtime_paths.py',
}

def run_regressions(errors: list[str]) -> None:
    def check(value: bool, msg: str) -> None:
        if not value: errors.append('1.0.0-x2.5 CODE PRESERVATION TRANSFER: ' + msg)
    check(LEDGER.is_file(), 'missing transfer ledger')
    if not LEDGER.is_file(): return
    check(hashlib.sha256(LEDGER.read_bytes()).hexdigest() == LEDGER_SHA256,
          'ledger modified after release lock')
    data = json.loads(LEDGER.read_text(encoding='utf-8'))
    check((data['baseline_release'],data['release']) == ('1.0.0-x2.4','1.0.0-x2.5'),
          'incorrect lineage')
    check(data['moves'] == EXPECTED_MOVES,'unexpected moves')
    check(set(data['edits']) == EXPECTED_EDITS,'unexpected production edits')
    check(set(data['new_production_files']) == {'suite_pythoine/routing/__init__.py',
          'suite_pythoine/runtime/__init__.py'},'unexpected new production code')
    for init in data['new_production_files']:
        check((ROOT/init).is_file() and (ROOT/init).read_bytes() == b'',
              'nonempty initializer: ' + init)
    check(hashlib.sha256((ROOT/'README.md').read_bytes()).hexdigest() == data['immutable_root_readme'],
          'immutable GitHub README modified')
    check(hashlib.sha256((ROOT/'LICENSE').read_bytes()).hexdigest() == data['license_sha256'],
          'LICENSE modified')
    expected = {current_path(prior).relative_to(ROOT).as_posix()
                for prior in data['original_sha256']} | set(data['new_production_files'])
    actual = {'main.py'} | {p.relative_to(ROOT).as_posix() for p in PKG.rglob('*.py')
      if not any(part in ('qa','tools','packaging') for part in p.relative_to(PKG).parts)}
    check(expected == actual, 'production source inventory drift: missing='
          +str(sorted(expected-actual))+' extra='+str(sorted(actual-expected)))
    for prior,digest in data['original_sha256'].items():
        current = current_path(prior)
        if not current.is_file(): check(False, 'missing '+prior); continue
        try:
            restored = source_x24(current).encode('utf-8')
            check(hashlib.sha256(restored).hexdigest() == digest,
                  'unapproved code modification: '+prior)
        except (AssertionError,ValueError) as exc:
            check(False,'unreversible import adjustment '+prior+': '+str(exc))
    for prior,new in EXPECTED_MOVES.items():
        check(not (ROOT/prior).exists() and (ROOT/new).is_file(),
              'obsolete module or missing destination: '+prior)
    # Pre-GUI routing must remain available without importing QApplication.
    from suite_pythoine.routing.routing_index import ROUTING_INDEX_SCHEMA, RoutingTarget
    from suite_pythoine.routing.silent_dispatch import (DispatchResult, load_config,
        diagnose_routing, ASK_EVERY_TIME)
    check(ROUTING_INDEX_SCHEMA == 5 and ASK_EVERY_TIME == '__ask_every_time__',
          'routing schema/ask semantics modified')
    check(not DispatchResult((),(),(),(),()).fully_dispatched,
          'silent dispatch empty result changed')
    with TemporaryDirectory(prefix='suite-routing-x25-') as temporary:
        config_path=Path(temporary)/'settings.json'
        with patch('suite_pythoine.routing.silent_dispatch.default_config_path',
                   return_value=config_path):
            check(isinstance(load_config(),dict), 'pre-GUI config path failed')
    from suite_pythoine.runtime.runtime_paths import RuntimePaths
    from suite_pythoine.runtime.runtime_launcher import RuntimeLauncher, LaunchCommand
    check(RuntimePaths is not None and RuntimeLauncher is not None
          and LaunchCommand is not None, 'runtime imports failed')
    # No ghost absolute/relative imports of retired locations.
    for file in (ROOT/'main.py',PKG/'app.py',PKG/'self_bootstrap.py',
                 PKG/'ui/dialogs/preferences.py'):
        tree=ast.parse(file.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node,ast.ImportFrom) and node.module:
                check(not any(node.module==name or node.module.endswith('.'+name)
                    for name in ('routing_index','routing_chooser','silent_dispatch',
                                 'runtime_launcher','runtime_paths')
                    if not ('.routing.' in node.module or '.runtime.' in node.module or
                            node.module.startswith(('routing.','runtime.')))),
                    'obsolete import in '+file.name)
