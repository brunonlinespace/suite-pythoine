"""Qt-free proof that generated build/dist output cannot contaminate AppImage QA."""
from __future__ import annotations
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from suite_pythoine.tools.build_source import stage_verified_source


def run_regressions(errors: list[str]) -> None:
    def check(ok: bool, label: str) -> None:
        if not ok:
            errors.append('0.8.5 builder: ' + label)

    with TemporaryDirectory(prefix='suite085-build-source-') as tmp:
        base = Path(tmp)
        source = base / 'Installed Portable'
        (source / 'suite_pythoine').mkdir(parents=True)
        entries = {
            'main.py': b'print("clean")\n',
            'suite-pythoine.json': b'{"version":"0.8.5"}\n',
            'suite_pythoine/__init__.py': b'__version__ = "0.8.5"\n',
        }
        lines = []
        for name, data in entries.items():
            location = source / name
            location.parent.mkdir(parents=True, exist_ok=True)
            location.write_bytes(data)
            lines.append(f'{hashlib.sha256(data).hexdigest()}  {name}')
        (source / 'suite_pythoine' / 'SOURCE_MANIFEST.sha256').write_text('\n'.join(lines) + '\n')
        # Exactly the original failing condition: a build script populates the
        # installed Portable with an isolated venv, bytecode and dist outputs.
        generated = source / 'suite_pythoine' / 'build' / 'venv' / 'lib64'
        generated.mkdir(parents=True)
        (generated / 'fake.pyc').write_bytes(b'not source')
        (source / 'suite_pythoine' / 'dist').mkdir()
        (source / 'suite_pythoine' / 'dist' / 'build-python-lock.txt').write_text('pip==26\n')
        snapshot = base / 'Verified source'
        check(stage_verified_source(source, snapshot) == len(entries), 'unexpected verified file count')
        check((snapshot / 'main.py').read_bytes() == entries['main.py'], 'source copy changed')
        check(not (snapshot / 'suite_pythoine' / 'build').exists()
              and not (snapshot / 'suite_pythoine' / 'dist').exists(),
              'generated venv/dist leaked into verified source snapshot')
        check((snapshot / 'suite_pythoine' / 'SOURCE_MANIFEST.sha256').is_file(),
              'verified snapshot lacks source release manifest')
        (source / 'main.py').write_text('changed\n')
        try:
            stage_verified_source(source, base / 'Should reject')
        except ValueError:
            pass
        else:
            check(False, 'stager accepted source not matching authored manifest')
    print('PASS: 0.8.5 generated-output isolation and verified-source regression'
          if not errors else 'CHECK: 0.8.5 build-source regressions')
