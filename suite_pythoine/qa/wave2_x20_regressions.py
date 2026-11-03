"""x2.0 Wave-2 entry gate: x1.8 code freeze, deterministic dependency baseline.

No Qt imports, no source mutations. Later x2 releases keep this original
fingerprint, but impose their own relocation-specific preservation contracts.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from suite_pythoine import __version__
from suite_pythoine.tools.wave2_dependencies import build_inventory

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / 'suite_pythoine/docs/WAVE2_DEPENDENCIES.json'
BASELINE_SHA256 = '31eb6f7e40c4546c4d83ac5ed4935c9b2b46ca567a4d68d618c873252024db29'
EXCEPTION = 'suite_pythoine/__init__.py'  # release identity only


def run_regressions(errors: list[str]) -> None:
    def check(truth: bool, message: str) -> None:
        if not truth:
            errors.append('1.0.0-x2.0 dependency baseline: ' + message)

    check(BASELINE.is_file(), 'missing frozen original dependency map')
    if not BASELINE.is_file():
        return
    check(hashlib.sha256(BASELINE.read_bytes()).hexdigest() == BASELINE_SHA256,
          'the x1.8 dependency/source fingerprint changed')
    try:
        frozen = json.loads(BASELINE.read_text(encoding='utf-8'))
        entries = frozen['modules']
        check(frozen['schema'] == 1, 'unrecognized baseline map schema')
        check(len(entries) >= 60, 'incomplete original production module inventory')
        check(len({n['path'] for n in entries}) == len(entries), 'duplicate frozen path')
        check(all(len(n['sha256']) == 64 for n in entries), 'invalid frozen SHA-256 entry')
        check(any(n['module'] == 'suite_pythoine.component_catalog'
                  and n['uses___file__'] for n in entries),
              'missing location-sensitive catalogue migration warning')
        # This only applies to the x2.0 no-move release. Future x2 versions
        # retain the fingerprint and verify their authorized moves separately.
        if __version__ == '1.0.0-x2.0':
            actual = build_inventory(ROOT)['modules']
            frozen_by_path = {n['path']: n for n in entries}
            check(set(n['path'] for n in actual) == set(frozen_by_path),
                  'unexpected production Python module addition, removal or relocation')
            for item in actual:
                before = frozen_by_path.get(item['path'])
                if before is None:
                    continue
                check(item['imports'] == before['imports'],
                      f"static import behavior changed: {item['path']}")
                check(item['uses___file__'] == before['uses___file__'],
                      f"resource/path sensitivity changed: {item['path']}")
                if item['path'] != EXCEPTION:
                    check(item['sha256'] == before['sha256'],
                          f"production code changed outside version identity: {item['path']}")
            check((ROOT / 'suite_pythoine/docs/WAVE2_ACCEPTANCE.md').is_file(),
                  'missing desktop/behavior/performance acceptance checklist')
    except (KeyError, ValueError, TypeError, OSError, SyntaxError) as exc:
        errors.append(f'1.0.0-x2.0 dependency baseline cannot be audited: {exc}')
