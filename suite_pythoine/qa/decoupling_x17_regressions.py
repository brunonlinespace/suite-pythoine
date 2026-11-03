"""1.0.0-x1.7: opt-in tracer and single-owner diagnostic UI helpers (Qt-free)."""
from __future__ import annotations

import ast
import hashlib
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / 'suite_pythoine'
EXPECTED_HELPERS = {
    '_diagnostic_canvas': 'aad08fdee00d1c261a6b6e457e78cf569c60f82fe9b0406d5b2f570d65ca5cc4',
    '_populate_diagnostic_canvas': '82d2738ca68efaf11d3ede094ea4a6805ba44fdac52732fa062fc717649ced10',
    '_style_destructive_button': '6891898930b2aef73ed87cb9211346b78c4ba88903f1aa8b97f27a096195bafc',
}
WINDOW_AST = '1821f6da0d3898aaab5b3ca7cd9b135ed63de3ef5652eb676e76c6ec0c15224c'


def _digest(node: ast.AST) -> str:
    return hashlib.sha256(ast.dump(node, include_attributes=False).encode('utf8')).hexdigest()


def run_regressions(errors: list[str]) -> None:
    label = '1.0.0-x1.7 trace/helper closure: '
    def check(condition: bool, reason: str) -> None:
        if not condition:
            errors.append(label + reason)

    app = (PACKAGE / 'app.py').read_text(encoding='utf8')
    preferences = (PACKAGE / 'ui/dialogs/preferences.py').read_text(encoding='utf8')
    shared_file = PACKAGE / 'ui/diagnostic_helpers.py'
    check(shared_file.is_file(), 'shared diagnostic helper module missing')
    if shared_file.is_file():
        shared = ast.parse(shared_file.read_text(encoding='utf8'))
        app_tree = ast.parse(app)
        pref_tree = ast.parse(preferences)
        for name, expected in EXPECTED_HELPERS.items():
            found = [n for n in shared.body if isinstance(n, ast.FunctionDef) and n.name == name]
            check(len(found) == 1 and _digest(found[0]) == expected,
                  f'helper {name} changed, duplicated, or missing')
            check(not any(isinstance(n, ast.FunctionDef) and n.name == name for n in app_tree.body),
                  f'{name} still implemented in shell')
            check(not any(isinstance(n, ast.FunctionDef) and n.name == name for n in pref_tree.body),
                  f'{name} still implemented in preferences')
        check('from .ui.diagnostic_helpers import (' in app
              and 'from ..diagnostic_helpers import (' in preferences,
              'both callers must use the one shared owner')
        suite = next(n for n in app_tree.body if isinstance(n, ast.ClassDef) and n.name == 'SuiteWindow')
        check(_digest(suite) == WINDOW_AST, 'SuiteWindow changed during helper/tracing cleanup')

    # Each process reads the opt-in flag *at import*. Verify normal execution never
    # wraps decorated code, accesses an active operation or writes trace output.
    script = '''
import json
from pathlib import Path
from suite_pythoine import perf_trace as p

def example():
    return 42

wrapped = p.traced_operation("probe_operation")(example)
duration = p.traced_duration("probe_duration")(example)
path = p.log_path()
if MODE == "off":
    assert not p.enabled()
    assert wrapped is example and duration is example
    assert p.begin_operation("startup") is p.begin_operation("other")
    assert p.process_start_perf() == 0.0
    assert p.trace_span("first") is p.trace_span("second")
    p.trace_counter("noop")
    p.trace_set("noop", True)
    with p.trace_span("noop"):
        assert wrapped() == 42 and duration() == 42
    assert not path.exists(), "disabled process wrote a performance trace"
else:
    assert p.enabled() and p.process_start_perf() > 0
    assert wrapped is not example and duration is not example
    with p.trace_operation("outer") as operation:
        assert duration() == 42
        p.trace_counter("counter", 3)
        with p.trace_span("span"):
            assert wrapped() == 42
        operation.set("field", "ok")
    assert path.exists(), "opted-in tracer did not write"
    records = [json.loads(line) for line in path.read_text().splitlines()]
    assert any(r["operation"] == "outer" and r["counters"].get("counter") == 3 for r in records)
    assert any(r["operation"] == "probe_operation" for r in records)
'''
    for mode in ('off', 'on'):
        with TemporaryDirectory(prefix=f'suite-x17-perf-{mode}-') as temp:
            env = os.environ.copy()
            env['PYTHONDONTWRITEBYTECODE'] = '1'
            env['XDG_CACHE_HOME'] = temp
            if mode == 'off':
                env.pop('SUITE_PYTHOINE_PERF', None)
            else:
                env['SUITE_PYTHOINE_PERF'] = '1'
            code = f'MODE = {mode!r}\n' + script
            proc = subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=env,
                                  text=True, capture_output=True, timeout=20, check=False)
            check(proc.returncode == 0, f'{mode} trace subprocess failed: {proc.stderr.strip()}')
