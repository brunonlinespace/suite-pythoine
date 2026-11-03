"""Suite Pythoine 1.0.0-x2.6 Wave-2 entry source/security release gate (Qt-free).

The pre-0.8.1 gate tested the now-retired central registry as a contract. This
replacement exercises the live filesystem/launcher/Recovery contract instead.
"""
from __future__ import annotations
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

from suite_pythoine import __version__
from suite_pythoine.catalogue.component_catalog import load_catalog, catalog_revision, extension_union, mime_type_union
from suite_pythoine.qa.p1_regressions import run_regressions as lifecycle_tests
from suite_pythoine.qa.developer_archive_regressions import run_regressions as developer_tests
from suite_pythoine.qa.runtime_drop_regressions import run_regressions as runtime_drop_tests
from suite_pythoine.qa.build_source_regressions import run_regressions as build_source_tests
from suite_pythoine.qa.polish085_regressions import run_regressions as polish085_tests
from suite_pythoine.qa.corrections086_regressions import run_regressions as corrections086_tests
from suite_pythoine.qa.corrections087_regressions import run_regressions as corrections087_tests
from suite_pythoine.qa.polish088_regressions import run_regressions as polish088_tests
from suite_pythoine.qa.polish089_regressions import run_regressions as polish089_tests
from suite_pythoine.qa.uninstall090_regressions import run_regressions as uninstall090_tests
from suite_pythoine.qa.corrections091_regressions import run_regressions as corrections091_tests
from suite_pythoine.qa.corrections092_regressions import run_regressions as corrections092_tests
from suite_pythoine.qa.corrections093_regressions import run_regressions as corrections093_tests
from suite_pythoine.qa.developer100_regressions import run_regressions as developer100_tests
from suite_pythoine.qa.polish101_regressions import run_regressions as polish101_tests
from suite_pythoine.qa.polish102_regressions import run_regressions as polish102_tests
from suite_pythoine.qa.polish103_regressions import run_regressions as polish103_tests
from suite_pythoine.qa.removal104_regressions import run_regressions as removal104_tests
from suite_pythoine.qa.polish105_regressions import run_regressions as polish105_tests
from suite_pythoine.qa.polish106_regressions import run_regressions as polish106_tests
from suite_pythoine.qa.polish107_regressions import run_regressions as polish107_tests
from suite_pythoine.qa.polish108_regressions import run_regressions as polish108_tests
from suite_pythoine.qa.polish109_regressions import run_regressions as polish109_tests
from suite_pythoine.qa.polish1010_regressions import run_regressions as polish1010_tests
from suite_pythoine.qa.performance1011_regressions import run_regressions as performance1011_tests
from suite_pythoine.qa.version_history011exp1_regressions import run_regressions as version_history011exp1_tests
from suite_pythoine.qa.hardening011exp11_regressions import run_regressions as hardening011exp11_tests
from suite_pythoine.qa.app_page011exp20_regressions import run_regressions as app_page011exp20_tests
from suite_pythoine.qa.hardening011exp21_regressions import run_regressions as hardening011exp21_tests
from suite_pythoine.qa.catalogue011exp30_regressions import run_regressions as catalogue011exp30_tests
from suite_pythoine.qa.catalogue011exp31_regressions import run_regressions as catalogue011exp31_tests
from suite_pythoine.qa.store_backend011exp40_regressions import run_regressions as store_backend011exp40_tests
from suite_pythoine.qa.store_frontend011exp50_regressions import run_regressions as store_frontend011exp50_tests
from suite_pythoine.qa.store_frontend011exp51_regressions import run_regressions as store_frontend011exp51_tests
from suite_pythoine.qa.store_frontend011exp52_regressions import run_regressions as store_frontend011exp52_tests
from suite_pythoine.qa.store_frontend011exp53_regressions import run_regressions as store_frontend011exp53_tests
from suite_pythoine.qa.store_backend011exp60_regressions import run_regressions as store_backend011exp60_tests
from suite_pythoine.qa.theme0110_regressions import run_regressions as theme0110_tests
from suite_pythoine.qa.theme_transition0110_regressions import run_regressions as theme_transition0110_tests
from suite_pythoine.qa.sidebar0110_regressions import run_regressions as sidebar0110_tests
from suite_pythoine.qa.dashboard_launcher0110_regressions import run_regressions as dashboard_launcher0110_tests
from suite_pythoine.qa.catalogue0111_regressions import run_regressions as catalogue0111_tests
from suite_pythoine.qa.theme0112_regressions import run_regressions as theme0112_tests
from suite_pythoine.qa.convergence0120_regressions import run_regressions as convergence0120_tests
from suite_pythoine.qa.corrections0121_regressions import run_regressions as corrections0121_tests
from suite_pythoine.qa.store_repository0122_regressions import run_regressions as store_repository0122_tests
from suite_pythoine.qa.corrections0123_regressions import run_regressions as corrections0123_tests
from suite_pythoine.qa.decoupling_x10_regressions import run_regressions as decoupling_x10_tests
from suite_pythoine.qa.decoupling_x11_regressions import run_regressions as decoupling_x11_tests
from suite_pythoine.qa.decoupling_x12_regressions import run_regressions as decoupling_x12_tests
from suite_pythoine.qa.decoupling_x13_regressions import run_regressions as decoupling_x13_tests
from suite_pythoine.qa.decoupling_x14_regressions import run_regressions as decoupling_x14_tests
from suite_pythoine.qa.decoupling_x15_regressions import run_regressions as decoupling_x15_tests
from suite_pythoine.qa.decoupling_x16_regressions import run_regressions as decoupling_x16_tests
from suite_pythoine.qa.decoupling_x17_regressions import run_regressions as decoupling_x17_tests
from suite_pythoine.qa.decoupling_x18_regressions import run_regressions as decoupling_x18_tests
from suite_pythoine.qa.wave2_x20_regressions import run_regressions as wave2_x20_tests
from suite_pythoine.qa.wave2_x21_regressions import run_regressions as wave2_x21_tests
from suite_pythoine.qa.wave2_x22_regressions import run_regressions as wave2_x22_tests
from suite_pythoine.qa.wave2_x23_regressions import run_regressions as wave2_x23_tests
from suite_pythoine.qa.wave2_x24_regressions import run_regressions as wave2_x24_tests
from suite_pythoine.qa.wave2_x25_regressions import run_regressions as wave2_x25_tests
from suite_pythoine.qa.catalogue_x26_regressions import run_regressions as catalogue_x26_tests

VERSION = '1.0.0-x2.6'
PACKAGE = Path(__file__).resolve().parent.parent
ROOT = PACKAGE.parent
EXCLUDED = {'.git', '.venv', 'venv', 'env', 'ENV', 'build', 'dist', '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache'}

def audit(errors: list[str]) -> None:
    def require(truth: bool, message: str) -> None:
        if not truth:
            errors.append(message)
    require(__version__ == VERSION, 'Python version is not the release version')
    manifest = json.loads((ROOT / 'suite-pythoine.json').read_text(encoding='utf8'))
    require(manifest.get('version') == VERSION, 'root package manifest version mismatch')
    require(manifest.get('id') == 'suite-pythoine', 'unexpected root identity')
    require(not (PACKAGE/'managed_registry.py').exists() and not (PACKAGE/'registry_persistence.py').exists(),
            'obsolete central registry implementation still packaged')
    require((PACKAGE/'installation_state.py').is_file() and (PACKAGE/'registry_retirement.py').is_file(),
            'filesystem state/obsolete-registry retirement missing')
    preferences = (PACKAGE/'config.py').read_text(encoding='utf8')
    dispatch = (PACKAGE/'routing/silent_dispatch.py').read_text(encoding='utf8')
    require('retire_registry(' in preferences and 'retire_registry(' in dispatch,
            'GUI or silent entry point does not retire obsolete registry')
    require('"managed_installations":' not in preferences and "'managed_installations':" not in preferences,
            'preferences still serialize central ownership records')
    for file in PACKAGE.rglob('*.py'):
        if file.name == 'release_check.py':
            continue
        source = file.read_text(encoding='utf8')
        try:
            tree = ast.parse(source, filename=str(file))
        except SyntaxError as ex:
            errors.append(f'Python syntax: {file}: {ex}')
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.split('.')[-1] in ('managed_registry','registry_persistence'):
                errors.append(f'production code imports obsolete central registry: {file}')
            if isinstance(node, ast.Import):
                for entry in node.names:
                    if entry.name.split('.')[-1] in ('managed_registry','registry_persistence'):
                        errors.append(f'production code imports obsolete central registry: {file}')
    components = load_catalog()
    require('suite-pythoine' in components and components['suite-pythoine'].kind == 'hub', 'catalogue Hub identity')
    require('markopad' in components and components['markopad'].is_routable, 'Markdown Editor routing missing')
    require('portapad' in components and components['portapad'].kind == 'reader', 'Reader taxonomy missing')
    require('gitten' in components and components['gitten'].kind == 'extension', 'gitten taxonomy missing')
    require('psts-pad' not in components, 'retired PSTS profile resurrected')
    require('.md' in extension_union() and '.rtf' in extension_union(), 'catalogue extension union regressed')
    require('application/pdf' in mime_type_union(), 'Reader MIME union regressed')
    require(catalog_revision(PACKAGE/'components.json') >= 1, 'catalogue revision regressed')
    build = (PACKAGE/'packaging/fedora/build-appimage.sh').read_text(encoding='utf8')
    test = (PACKAGE/'packaging/fedora/test-appimage.sh').read_text(encoding='utf8')
    require(f'APP_VERSION="{VERSION}"' in build and f'VERSION="{VERSION}"' in test, 'Fedora script versions')
    for token in ('umask 022', 'check_non_privileged_policy', 'SOURCE_MANIFEST', 'BUILD_REQUIREMENTS', 'SUITE_PYTHOINE_ALLOW_ROOT_BUILD'):
        require(token in build, f'Builder safeguard removed: {token}')
    require(not re.search(r'(^|[\s;])(?:sudo|pkexec|dnf)\s+(?:install|update|upgrade)', build, re.M),
            'system-level package installation introduced to user builder')
    req = (PACKAGE/'packaging/pyinstaller/build-requirements.txt').read_text(encoding='utf8')
    require('\\n' not in req and any(line.strip().startswith('PyInstaller') for line in req.splitlines()),
            'PyInstaller build requirement absent or malformed')
    metadata = ET.parse(PACKAGE/'packaging/appimage/io.github.brunonlinespace.suite-pythoine.metainfo.xml').getroot()
    releases = metadata.find('releases')
    require(releases is not None and len(releases) == 1 and releases[0].attrib.get('version') == VERSION,
            'AppStream current-only release version mismatch')
    for rel in ('install_wizard.py', 'app.py', 'version_history.py', 'registry.py', 'routing/routing_index.py', 'recovery.py', 'purge_wizard.py', 'asset_removal.py', 'prune_policy.py', 'operation_ui.py', 'developer/developer_intake_vault.py', 'editor_watcher.py', 'store/store_content.py'):
        require((PACKAGE/rel).is_file(), f'Missing required production module: {rel}')
    wizard = (PACKAGE/'install_wizard.py').read_text(encoding='utf8')
    app = (PACKAGE/'app.py').read_text(encoding='utf8')
    recovery = (PACKAGE/'recovery.py').read_text(encoding='utf8')
    require('install_portable_with_recovery(' in wizard, 'ZIP wizard does not stage Portable and Recovery together')
    require('allow_checksum_mismatch' in recovery and 'allow_checksum_mismatch' in app,
            'explicit checksum-only Restore override missing')
    require('build_appimage.setVisible(self.developer_config.enabled)' in (PACKAGE/'ui/pages/version_history_page.py').read_text(encoding='utf8'),
            'normal version cards show direct AppImage builder')
    require('def _resolve_desktop_questions(' in app, 'launcher conflict/first discovery prompts missing')
    require('validate_version_boundary(' in app and 'validate_version_boundary(' in (PACKAGE/'purge_wizard.py').read_text(encoding='utf8'),
            'Uninstall Version / Purge unrecognised-file safety missing')
    # Strict manifest: exactly the authored tree; no bytecode, temp output or silent payload.
    manifest_path = PACKAGE/'SOURCE_MANIFEST.sha256'
    listed: dict[str,str] = {}
    for line in manifest_path.read_text(encoding='ascii').splitlines():
        try:
            digest, relative = line.split('  ',1)
        except ValueError:
            errors.append('malformed SOURCE_MANIFEST entry'); continue
        if relative in listed:
            errors.append(f'duplicate SOURCE_MANIFEST entry {relative}')
        listed[relative] = digest
    actual: dict[str,Path] = {}
    for path in ROOT.rglob('*'):
        relative = path.relative_to(ROOT)
        if path.is_symlink():
            errors.append(f'source release contains symlink: {relative}'); continue
        if any(part in EXCLUDED for part in relative.parts):
            if path.is_file():
                errors.append(f'source release contains generated/excluded file: {relative}')
            continue
        if not path.is_file() or path == manifest_path:
            continue
        if path.suffix in ('.pyc','.pyo'):
            errors.append(f'source release contains Python bytecode: {relative}'); continue
        actual[relative.as_posix()] = path
    require(set(listed) == set(actual), f'SOURCE_MANIFEST mismatch: missing={sorted(set(listed)-set(actual))} extra={sorted(set(actual)-set(listed))}')
    for name,path in actual.items():
        if name in listed:
            require(hashlib.sha256(path.read_bytes()).hexdigest() == listed[name], f'SOURCE_MANIFEST checksum mismatch: {name}')
    print('PASS: version, trusted catalogue, packaging, registry-free boundaries, strict source manifest')
    lifecycle_tests(errors)
    print('PASS: filesystem lifecycle regression suite' if not errors else 'CHECK: filesystem lifecycle regression suite')
    developer_tests(errors)
    print('PASS: Developer-only ZIP retention regression suite' if not errors else 'CHECK: Developer-only ZIP retention regression suite')
    runtime_drop_tests(errors)
    print('PASS: saved-runtime and Developer Intake/Shift-install/Ctrl-retain drop regressions' if not errors else 'CHECK: runtime/drop regressions')
    build_source_tests(errors)
    print('PASS: verified AppImage source staging regressions' if not errors else 'CHECK: builder-source regressions')
    polish085_tests(errors)
    corrections086_tests(errors)
    corrections087_tests(errors)
    polish088_tests(errors)
    polish089_tests(errors)
    uninstall090_tests(errors)
    corrections091_tests(errors)
    corrections092_tests(errors)
    corrections093_tests(errors)
    developer100_tests(errors)
    polish101_tests(errors)
    polish102_tests(errors)
    polish103_tests(errors)
    removal104_tests(errors)
    polish105_tests(errors)
    polish106_tests(errors)
    polish107_tests(errors)
    polish108_tests(errors)
    polish109_tests(errors)
    polish1010_tests(errors)
    performance1011_tests(errors)
    version_history011exp1_tests(errors)
    hardening011exp11_tests(errors)
    app_page011exp20_tests(errors)
    hardening011exp21_tests(errors)
    catalogue011exp30_tests(errors)
    catalogue011exp31_tests(errors)
    store_backend011exp40_tests(errors)
    store_frontend011exp50_tests(errors)
    store_frontend011exp51_tests(errors)
    store_frontend011exp52_tests(errors)
    store_frontend011exp53_tests(errors)
    store_backend011exp60_tests(errors)
    theme0110_tests(errors)
    theme_transition0110_tests(errors)
    sidebar0110_tests(errors)
    dashboard_launcher0110_tests(errors)
    catalogue0111_tests(errors)
    theme0112_tests(errors)
    convergence0120_tests(errors)
    corrections0121_tests(errors)
    store_repository0122_tests(errors)
    corrections0123_tests(errors)
    print('PASS: 0.12.3 Store backend installation completion regression contract' if not errors else 'CHECK: 0.12.3 Store backend installation completion regressions')
    decoupling_x10_tests(errors)
    print('PASS: 1.0.0-x1.0 dormant diagnostics/decoupling baseline contract' if not errors else 'CHECK: 1.0.0-x1.0 diagnostics baseline regressions')
    decoupling_x11_tests(errors)
    print('PASS: 1.0.0-x1.1 independent helper/widget extraction contract' if not errors else 'CHECK: 1.0.0-x1.1 helper/widget extraction regressions')
    decoupling_x12_tests(errors)
    print('PASS: 1.0.0-x1.2 Preferences-dialog extraction contract' if not errors else 'CHECK: 1.0.0-x1.2 Preferences-dialog extraction regressions')
    decoupling_x13_tests(errors)
    print('PASS: 1.0.0-x1.3 Installed Applications presentation extraction contract' if not errors else 'CHECK: 1.0.0-x1.3 Installed Applications extraction regressions')
    decoupling_x14_tests(errors)
    print('PASS: 1.0.0-x1.4 Application Page + Version History presentation extraction contract' if not errors else 'CHECK: 1.0.0-x1.4 presentation extraction regressions')
    decoupling_x15_tests(errors)
    print('PASS: 1.0.0-x1.5 Store/catalogue presentation extraction contract' if not errors else 'CHECK: 1.0.0-x1.5 Store/catalogue presentation extraction regressions')
    decoupling_x16_tests(errors)
    decoupling_x17_tests(errors)
    decoupling_x18_tests(errors)
    wave2_x20_tests(errors)
    wave2_x21_tests(errors)
    wave2_x22_tests(errors)
    wave2_x23_tests(errors)
    wave2_x24_tests(errors)
    wave2_x25_tests(errors)
    catalogue_x26_tests(errors)
    print('PASS: 1.0.0-x2.5 frozen x1.8 production dependencies/ownership baseline' if not errors else 'CHECK: x2.0 dependency baseline')
    print('PASS: 1.0.0-x1.8 immutable README/LICENSE/repository-root regression' if not errors else 'CHECK: 1.0.0-x1.8 repository regression')
    print('PASS: 1.0.0-x1.8 tracing-default and shared Qt helper regression' if not errors else 'CHECK: 1.0.0-x1.8 regressions')
    print('PASS: 1.0.0-x1.6 Wave-1 convergence/import/ownership/performance-tool regressions' if not errors else 'CHECK: 1.0.0-x1.6 Wave-1 convergence regressions')


def main() -> int:
    errors: list[str] = []
    try:
        audit(errors)
    except Exception as exc:
        errors.append(f'release gate exception: {type(exc).__name__}: {exc}')
    if errors:
        for error in errors:
            print('FAIL:', error, file=sys.stderr)
        return 1
    print(f'PASS: Suite Pythoine {VERSION} security/source release gate')
    return 0

if __name__ == '__main__':
    sys.exit(main())
