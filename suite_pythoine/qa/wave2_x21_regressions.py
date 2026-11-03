"""Wave 2 x2.1: enforce source-only UI moves against the frozen x1.8/x2.0 code.

This checks that moving a source module and changing exactly authorized import
statements reconstructs the original bytes when the changes are reversed.
It also fails on added/removed *unrelated* production modules.
No Qt dependency, GUI launch, or runtime mutation.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from suite_pythoine.qa.wave2_x23_regressions import x22_source

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / 'suite_pythoine'
BASELINE = PKG / 'docs/WAVE2_DEPENDENCIES.json'
BASELINE_DIGEST = '31eb6f7e40c4546c4d83ac5ed4935c9b2b46ca567a4d68d618c873252024db29'
MOVES = {
    'dashboard.py': 'ui/shell/dashboard.py',
    'dashboard_model.py': 'ui/shell/dashboard_model.py',
    'suite_theme.py': 'ui/shell/suite_theme.py',
    'sidebar_launcher.py': 'ui/shell/sidebar_launcher.py',
    'sidebar_search.py': 'ui/shell/sidebar_search.py',
    'quick_tour.py': 'ui/dialogs/quick_tour.py',
    'shortcuts_dialog.py': 'ui/dialogs/shortcuts_dialog.py',
}
# Deliberately explicit, reversible whitelist of *only* necessary imports.
CHANGES = {
    'app.py': {
        'from .dashboard import EditorDashboard': 'from .ui.shell.dashboard import EditorDashboard',
        'from .suite_theme import apply_theme, normalize_theme': 'from .ui.shell.suite_theme import apply_theme, normalize_theme',
        'from .sidebar_launcher import SidebarLauncher': 'from .ui.shell.sidebar_launcher import SidebarLauncher',
        'from .quick_tour import QuickTourDialog': 'from .ui.dialogs.quick_tour import QuickTourDialog',
        'from .shortcuts_dialog import ShortcutsDialog': 'from .ui.dialogs.shortcuts_dialog import ShortcutsDialog',
        'from .component_policy import': 'from .catalogue.component_policy import',
        'from .component_catalog import': 'from .catalogue.component_catalog import',
    },
    'dashboard.py': {
        'from .component_policy import': 'from ...catalogue.component_policy import',
        'from .component_catalog import': 'from ...catalogue.component_catalog import',
        'from .perf_trace import': 'from ...perf_trace import',
        'from .registry import': 'from ...registry import',
    },
    'dashboard_model.py': {'from .registry import': 'from ...registry import'},
    'quick_tour.py': {'from . import APP_NAME': 'from ... import APP_NAME'},
    'appimage_inspection.py': {'from .component_catalog import COMPONENT_PROFILES': 'from .catalogue.component_catalog import COMPONENT_PROFILES'},
    'appimage_wizard.py': {'from .component_policy import is_backend_only_component': 'from .catalogue.component_policy import is_backend_only_component', 'from .component_catalog import bundled_catalog_icon_path': 'from .catalogue.component_catalog import bundled_catalog_icon_path'},
    'developer_intake.py': {'from .component_catalog import COMPONENT_PROFILES, ComponentProfile': 'from .catalogue.component_catalog import COMPONENT_PROFILES, ComponentProfile'},
    'install_wizard.py': {'from .component_policy import is_backend_only_component': 'from .catalogue.component_policy import is_backend_only_component'},
    'installation_state.py': {'from .component_catalog import COMPONENT_PROFILES': 'from .catalogue.component_catalog import COMPONENT_PROFILES'},
    'installer.py': {'from .component_catalog import mime_type_union': 'from .catalogue.component_catalog import mime_type_union'},
    'purge_wizard.py': {'from .component_catalog import profile_for_id': 'from .catalogue.component_catalog import profile_for_id'},
    'registry.py': {'from .component_catalog import COMPONENT_PROFILES, extension_union, mime_type_union': 'from .catalogue.component_catalog import COMPONENT_PROFILES, extension_union, mime_type_union', 'from .component_policy import is_backend_only_component': 'from .catalogue.component_policy import is_backend_only_component'},
    'routing_index.py': {'from .component_catalog import catalog_fingerprint': 'from .catalogue.component_catalog import catalog_fingerprint', 'from .component_policy import component_capabilities': 'from .catalogue.component_policy import component_capabilities'},
    'silent_dispatch.py': {'from .component_policy import document_candidates': 'from .catalogue.component_policy import document_candidates'},
    'store_bridge.py': {'from .component_catalog import COMPONENT_PROFILES': 'from .catalogue.component_catalog import COMPONENT_PROFILES'},
    'store_content.py': {'from .component_catalog import COMPONENT_PROFILES, TRUSTED_PUBLISHER_ID': 'from .catalogue.component_catalog import COMPONENT_PROFILES, TRUSTED_PUBLISHER_ID'},
    'suite_uninstall.py': {'from .component_catalog import profile_for_id': 'from .catalogue.component_catalog import profile_for_id'},
    'ui/dialogs/preferences.py': {'from ...component_policy import document_candidates, is_backend_only_component, is_hub': 'from ...catalogue.component_policy import document_candidates, is_backend_only_component, is_hub'},
    'ui/pages/application.py': {'from ...component_policy import is_backend_only_component': 'from ...catalogue.component_policy import is_backend_only_component', 'from ...component_catalog import profile_for_id': 'from ...catalogue.component_catalog import profile_for_id'},
    'ui/pages/store_catalogue.py': {'from ...component_catalog import COMPONENT_PROFILES, ComponentProfile, bundled_catalog_icon_path': 'from ...catalogue.component_catalog import COMPONENT_PROFILES, ComponentProfile, bundled_catalog_icon_path'},
    'ui/pages/version_history_page.py': {'from ...component_policy import is_backend_only_component, is_hub': 'from ...catalogue.component_policy import is_backend_only_component, is_hub', 'from ...component_catalog import profile_for_id': 'from ...catalogue.component_catalog import profile_for_id'},
}
NEW_INIT = b'"""Dashboard, theme and optional sidebar presentation."""\n'


def run_regressions(errors: list[str]) -> None:
    def check(truth: bool, problem: str) -> None:
        if not truth:
            errors.append('1.0.0-x2.1 STRICT move-only: ' + problem)

    check(BASELINE.is_file(), 'missing original source baseline')
    if not BASELINE.is_file():
        return
    check(hashlib.sha256(BASELINE.read_bytes()).hexdigest() == BASELINE_DIGEST,
          'original baseline fingerprint was changed')
    original = json.loads(BASELINE.read_text(encoding='utf-8'))['modules']
    prior_paths = {row['path'] for row in original}
    new_module = 'suite_pythoine/ui/shell/__init__.py'
    expected_paths = {('suite_pythoine/' + MOVES[p.removeprefix('suite_pythoine/')]
                       if p.removeprefix('suite_pythoine/') in MOVES else p)
                      for p in prior_paths} | {new_module}
    expected_paths = {('suite_pythoine/catalogue/' + p.removeprefix('suite_pythoine/')
                       if p in ('suite_pythoine/component_catalog.py', 'suite_pythoine/component_policy.py')
                       else p) for p in expected_paths} | {'suite_pythoine/catalogue/__init__.py'}
    expected_paths = {('suite_pythoine/store/' + p.removeprefix('suite_pythoine/')
                       if p in ('suite_pythoine/store_bridge.py','suite_pythoine/store_content.py')
                       else p) for p in expected_paths} | {'suite_pythoine/store/__init__.py'}
    expected_paths = {('suite_pythoine/developer/' + p.removeprefix('suite_pythoine/')
                       if p in ('suite_pythoine/developer_intake.py', 'suite_pythoine/developer_archive.py',
                                'suite_pythoine/developer_intake_vault.py', 'suite_pythoine/developer_policy.py')
                       else p) for p in expected_paths} | {'suite_pythoine/developer/__init__.py'}
    expected_paths = {('suite_pythoine/routing/' + p.removeprefix('suite_pythoine/')
                       if p in ('suite_pythoine/routing_index.py','suite_pythoine/routing_chooser.py','suite_pythoine/silent_dispatch.py')
                       else 'suite_pythoine/runtime/' + p.removeprefix('suite_pythoine/')
                       if p in ('suite_pythoine/runtime_launcher.py','suite_pythoine/runtime_paths.py')
                       else p) for p in expected_paths} | {'suite_pythoine/routing/__init__.py','suite_pythoine/runtime/__init__.py'}
    current_paths = {'main.py'} | {
        p.relative_to(ROOT).as_posix()
        for p in PKG.rglob('*.py')
        if not any(part in ('qa', 'tools', 'packaging') for part in p.relative_to(PKG).parts)
    }
    check(expected_paths == current_paths,
          f'production Python module set changed: removed={sorted(expected_paths-current_paths)} '
          f'added={sorted(current_paths-expected_paths)}')
    check((ROOT / 'suite_pythoine/catalogue/__init__.py').read_bytes() == b'',
          'new catalogue initializer must remain empty')
    check((ROOT / new_module).read_bytes() == NEW_INIT,
          'new UI shell initializer contains more than its permitted package docstring')

    for row in original:
        old = row['path']
        name = old.removeprefix('suite_pythoine/') if old.startswith('suite_pythoine/') else old
        actual = ('suite_pythoine/' + MOVES[name]) if name in MOVES else old
        if name in ('component_catalog.py', 'component_policy.py'):
            actual = 'suite_pythoine/catalogue/' + name
        if name in ('store_bridge.py', 'store_content.py'):
            actual = 'suite_pythoine/store/' + name
        if name in ('developer_intake.py', 'developer_archive.py', 'developer_intake_vault.py', 'developer_policy.py'):
            actual = 'suite_pythoine/developer/' + name
        if name in ('routing_index.py','routing_chooser.py','silent_dispatch.py'):
            actual = 'suite_pythoine/routing/' + name
        if name in ('runtime_launcher.py','runtime_paths.py'):
            actual = 'suite_pythoine/runtime/' + name
        file = ROOT / actual
        if not file.is_file():
            check(False, f'missing relocated source {actual}')
            continue
        text = x22_source(file)
        # Undo only the exact authorized import statements, then compare the
        # entire original source byte for byte, not just its declarations.
        for prior, now in CHANGES.get(name, {}).items():
            check(text.count(now) == 1, f'{actual}: missing/duplicated authorized import {now}')
            text = text.replace(now, prior)
        if name == 'component_catalog.py':
            text = text.replace('Path(__file__).resolve().parent.parent / "components.json"',
                                'Path(__file__).resolve().with_name("components.json")')
            text = text.replace('Path(__file__).resolve().parent.parent / "assets" / "catalog"',
                                'Path(__file__).resolve().parent / "assets" / "catalog"')
        if old == 'suite_pythoine/__init__.py':
            check(text.count('1.0.0-x2.2') == 1, 'release identity mismatch')
            text = text.replace('1.0.0-x2.2', '1.0.0-x1.8')
        digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
        check(digest == row['sha256'], f'unapproved source-code change: {actual}')
        if name in MOVES:
            check(not (ROOT / old).exists(), f'former module was left duplicated at {old}')

    # Documentation/repository identities must remain unchanged.
    check(hashlib.sha256((ROOT/'README.md').read_bytes()).hexdigest()
          == '392895da769ac770766a7338081f50be349e7af72892682758f26fe94d23ea95',
          'immutable GitHub README was modified')
