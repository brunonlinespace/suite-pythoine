"""0.8.5 Qt-free regression checks for explicit runtime and drop policies.

The GUI needs a real Qt session for full acceptance. This suite tests the actual
Qt-independent selection/drop functions and checks that both GUI handlers wire
those functions to the production synchronization and installer entry points.
"""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations

import ast
import copy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import sys

from suite_pythoine.developer.developer_policy import developer_intake_drop, developer_retain_drop
from suite_pythoine.registry import (EditorEntry, EditorVersionInfo, saved_launch_mode,
                                     requested_version_runtime)


def run_regressions(errors: list[str]) -> None:
    def check(condition: bool, description: str) -> None:
        if not condition:
            errors.append('0.8.5: ' + description)

    scratch = TemporaryDirectory(prefix='suite085-runtime-')
    base = Path(scratch.name)
    (base / 'Portable').mkdir()
    (base / 'Portable' / 'main.py').write_text('print(1)\n')
    (base / 'AppImage').mkdir()
    (base / 'AppImage' / 'example.AppImage').write_bytes(b'fixture')
    version = EditorVersionInfo(
        version='0.2.0',
        portable_root=base / 'Portable',
        portable_command=('python3', str(base / 'Portable' / 'main.py')),
        appimage_path=base / 'AppImage' / 'example.AppImage',
        installed_command=(str(base / 'AppImage' / 'example.AppImage'),),
    )
    for component_kind, component_id in (('hub', 'suite-pythoine'), ('editor', 'markopad')):
        for pref, desktop, expected in (
            ('installed', 'portable', 'AppImage'),
            ('portable', 'appimage', 'Portable'),
        ):
            # Discovery may rightly use a real launcher for current launching,
            # but the preference dialog must still show the SAVED choice.
            cfg = {'editor_overrides': {component_id: {'launch_mode': pref}}}
            entry = EditorEntry(
                editor_id=component_id, name=component_id, root=version.portable_root,
                component_kind=component_kind,
                portable_command=version.portable_command,
                installed_command=version.installed_command,
                launch_mode='portable' if desktop == 'portable' else 'installed',
                desktop_issue='ready', desktop_runtime=desktop,
                versions=(version,), active_version=version.version,
            )
            check(saved_launch_mode(cfg, component_id) == pref,
                  f'{component_id}: desktop {desktop} overwrote saved {pref} preference')
            check(entry.command() == (version.portable_command if desktop == 'portable' else version.installed_command),
                  f'{component_id}: verified desktop stopped being authoritative before explicit change')
            selected = requested_version_runtime(saved_launch_mode(cfg, component_id), version)
            check(selected is not None and selected[0] == expected,
                  f'{component_id}: preference {pref} cannot retarget desktop {desktop}')
            entry.launch_mode = pref  # same one-operation copy the GUI uses
            check(entry.command() == selected[1],
                  f'{component_id}: selected {pref} resolves to wrong executable')
        check(saved_launch_mode({'editor_overrides': {}}, component_id) == 'auto',
              f'{component_id}: absent preference not automatic')
    portable_only = EditorVersionInfo(version='0.3.0', portable_root=base / 'Portable',
                                       portable_command=('python3', str(base / 'Portable' / 'main.py')))
    image_only = EditorVersionInfo(version='0.3.0', installed_command=version.installed_command,
                                    appimage_path=version.appimage_path)
    check(requested_version_runtime('installed', portable_only) is None,
          'AppImage preference silently fell back to Portable')
    check(requested_version_runtime('portable', image_only) is None,
          'Portable preference silently fell back to AppImage')
    check(requested_version_runtime('auto', portable_only)[0] == 'Portable',
          'Automatic mode fails Portable-only installations')
    check(requested_version_runtime('auto', image_only)[0] == 'AppImage',
          'Automatic mode fails AppImage-only installations')

    SHIFT, CTRL, ALT, META = (1, 2, 4, 8)  # supplied masks, no Qt import
    blocked = CTRL | ALT | META
    for enabled, filename, modifiers, override, expected in (
        (False, 'Markopad.zip', 0, False, False),
        (True, 'Markopad.zip', 0, False, True),
        (True, 'Markopad.ZIP', 0, False, True),
        (True, 'Markopad.zip', SHIFT, False, False),
        (True, 'Markopad.AppImage', 0, False, False),
        (True, 'document.md', 0, False, False),
        (True, 'Markopad.zip', CTRL | SHIFT, False, False),
        (True, 'Markopad.zip', ALT, False, False),
        (True, 'Markopad.zip', META, False, False),
        (True, 'Markopad.zip', 0, True, False),
    ):
        actual = developer_intake_drop(enabled, filename, modifiers,
                                        shift_mask=SHIFT, other_modifiers=blocked,
                                        forced_override=override)
        check(actual == expected,
              f'wrong drop route for enabled={enabled}, file={filename}, modifiers={modifiers}, override={override}')

    for enabled, filename, modifiers, override, expected in (
        (False, 'Markopad.zip', CTRL, False, False),
        (True, 'Markopad.zip', 0, False, False),
        (True, 'Markopad.zip', CTRL, False, True),
        (True, 'Markopad.ZIP', CTRL, False, True),
        (True, 'Markopad.AppImage', CTRL, False, False),
        (True, 'document.md', CTRL, False, False),
        (True, 'Markopad.zip', CTRL | SHIFT, False, False),
        (True, 'Markopad.zip', CTRL | ALT, False, False),
        (True, 'Markopad.zip', CTRL | META, False, False),
        (True, 'Markopad.zip', CTRL, True, False),
    ):
        actual = developer_retain_drop(enabled, filename, modifiers,
                                       ctrl_mask=CTRL, other_modifiers=SHIFT | ALT | META,
                                       forced_override=override)
        check(actual == expected,
              f'wrong Ctrl retain drop route: enabled={enabled}, file={filename}, modifiers={modifiers}')

    package = Path(__file__).resolve().parent.parent
    app_tree = ast.parse(read_app_with_presentations())
    wizard_tree = ast.parse((package / 'install_wizard.py').read_text(encoding='utf8'))
    dashboard_tree = ast.parse((package / 'ui/shell/dashboard.py').read_text(encoding='utf8'))

    def method(tree: ast.AST, name: str) -> ast.FunctionDef:
        methods = [node for node in ast.walk(tree)
                   if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name]
        assert len(methods) == 1, f'expected exactly one {name}, got {len(methods)}'
        return methods[0]

    def calls(node: ast.AST) -> set[str]:
        return {ast.unparse(item.func) for item in ast.walk(node) if isinstance(item, ast.Call)}

    try:
        component = method(app_tree, 'editor_preferences')
        suite = method(app_tree, 'general_preferences')
        change = method(app_tree, '_apply_runtime_preference')
        guided = method(app_tree, 'install_editor_zip')
        drops = method(app_tree, '_handle_drop_payloads')
        intake = method(app_tree, '_run_developer_intake')
        intake_drop = method(app_tree, '_open_developer_intake_zip')
        intake_prompt = method(app_tree, 'developer_intake_prompt')
        retain = method(app_tree, 'retain_developer_source_zip_prompt')
        details = method(app_tree, '_populate_editor_details')
        options = method(wizard_tree, '_sync_source_choice')
        for label, node in (('component', component), ('Hub', suite)):
            check('self._apply_runtime_preference' in calls(node),
                  f'{label} preferences do not invoke explicit runtime synchronization')
        check({'requested_version_runtime', 'copy.copy', 'self.repair_suite_desktop_integration',
               'self.repair_component_desktop_integration'} <= calls(change),
              'runtime change no longer checks exact-version choice and retargets both launcher families')
        check('DeveloperIntakeDialog' not in calls(guided),
              'Developer Mode still diverts ordinary ZIP installation into Intake')
        check('self.route_file' in calls(drops) and 'developer_intake_drop' in calls(drops)
              and 'self._open_developer_intake_zip' in calls(drops)
              and 'developer_retain_drop' in calls(drops)
              and 'self.retain_developer_source_zip_prompt' in calls(drops),
              'drop routing no longer distinguishes Developer Intake / Shift install bypass / Ctrl retain')
        check('DeveloperIntakeDialog' in calls(intake)
              and 'self._run_developer_intake' in calls(intake_drop)
              and 'self._run_developer_intake' in calls(intake_prompt),
              'Developer Mode ZIP drop or Tools menu no longer opens Developer Intake')
        check('inspect_editor_zip' in calls(retain), 'retained ZIP does not undergo standard source inspection')
        check(('self._editor_summary_text' in calls(details) or 'self._application_overview_text' in calls(details))
              and 'self._show_editor_technical_details' in calls(details),
              'shared Details page lost application overview or Technical Details')
        check('self._populate_editor_details' in calls(method(app_tree, '_editor_page'))
              and 'self._populate_editor_details' in calls(method(app_tree, '_suite_details_page')),
              'Editor/Reader/Extension and Hub no longer share the same Details renderer')
        assert ast.unparse(details).index('layout.addWidget(description)') < ast.unparse(details).index('layout.addWidget(current_heading)'), \
            'Description must remain above the Current Version section'
        menu = method(app_tree, '_make_menu')
        menu_source = ast.unparse(menu)
        check(menu_source.index('view.addAction(self.dashboard_action)') < menu_source.index("view.addMenu('Dashboard Settings')")
              and menu_source.index('tools.addAction(self.refresh_action)') < menu_source.index('tools.addAction(self.hub_details_action)'),
              'Dashboard / Dashboard Settings or Tools-first Refresh placement regressed')
        check(menu_source.index('tools.addAction(self.developer_action)') < menu_source.index('tools.addAction(self.developer_intake_action)')
              < menu_source.index('tools.addAction(self.retain_source_zip_action)'),
              'Developer Mode / Intake / Retain Source Tools order regressed')
        check('self.build_appimage.setEnabled' in calls(options)
              and 'self.developer_mode' in ast.unparse(options),
              'installer build enhancement is no longer gated by Developer Mode and builder availability')
        # Shift may make Plasma's drag source propose a MOVE. Neither drop
        # target is permitted to tell the source file manager to delete its ZIP.
        for label, tree in (('main window', app_tree), ('Drop Bar', dashboard_tree)):
            for event_name in ('dragEnterEvent', 'dragMoveEvent', 'dropEvent'):
                handler = method(tree, event_name)
                check('Qt.DropAction.CopyAction' in ast.unparse(handler)
                      and 'event.acceptProposedAction' not in calls(handler),
                      f'{label} {event_name} can accept a Shift-proposed Move action')

        # Execute the REAL preference-handler body with lightweight substitutes
        # for Qt/config/desktop IO. This catches the original 0.8.1 regression:
        # refreshed discovery masked the user's new choice before repair.
        extracted = ast.fix_missing_locations(ast.Module(
            body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0),
                  change], type_ignores=[]))
        warnings: list[str] = []
        scope = {
            'copy': copy, 'sys': sys, 'EditorEntry': EditorEntry,
            'requested_version_runtime': requested_version_runtime,
            'is_hub': lambda entry: entry.component_kind == 'hub',
            'QMessageBox': SimpleNamespace(warning=lambda _parent, _title, message: warnings.append(message)),
            'app_dialog_title': lambda title: title,
        }
        exec(compile(extracted, str(package / 'app.py'), 'exec'), scope)
        apply_runtime = scope['_apply_runtime_preference']

        class FakeConfig:
            def __init__(self, component_id: str, requested: str):
                self.overrides = {component_id: {'launch_mode': requested}}
                self.saved = 0
            def save(self):
                self.saved += 1
                return True

        class FakeController:
            def __init__(self, entry, selected_version, requested, fail=False):
                self.entry, self.version, self.requested = entry, selected_version, requested
                self.config = FakeConfig(entry.editor_id, requested)
                self.fail = fail
                self.repaired: list[tuple[str, str]] = []
                self.refreshed = 0
            def _version_info(self, _editor, exact_version):
                return self.version if exact_version == self.version.version else None
            def _editor_override(self, editor):
                return self.config.overrides.setdefault(editor.editor_id, {})
            def refresh_editors(self, automatic=False):
                self.refreshed += 1
            def repair_component_desktop_integration(self, editor, *, show_dialog):
                check(editor is not self.entry, 'preference retarget mutated the discovered entry')
                self.repaired.append(('component', editor.launch_mode))
                return not self.fail
            def repair_suite_desktop_integration(self, editor, *, show_dialog):
                check(editor is not self.entry, 'Hub preference retarget mutated the discovered entry')
                self.repaired.append(('Hub', editor.launch_mode))
                return not self.fail

        for kind, cid in (('hub', 'suite-pythoine'), ('editor', 'markopad')):
            for before, after, actual in (('portable', 'installed', 'portable'),
                                          ('installed', 'portable', 'appimage')):
                e = EditorEntry(editor_id=cid, name=cid, root=version.portable_root,
                    component_kind=kind, active_version=version.version,
                    versions=(version,), desktop_issue='ready', desktop_runtime=actual,
                    launch_mode=before)
                dummy = FakeController(e, version, after)
                apply_runtime(dummy, e, before, after)
                check(dummy.repaired == [(('Hub' if kind == 'hub' else 'component'), after)],
                      f'{cid}: saving {after} did not retarget the verified {actual} launcher')
                check(dummy.config.overrides[cid]['launch_mode'] == after,
                      f'{cid}: successful {after} choice did not remain saved')
                dummy_fail = FakeController(e, version, after, fail=True)
                apply_runtime(dummy_fail, e, before, after)
                check(dummy_fail.config.overrides[cid].get('launch_mode') == before
                      and dummy_fail.refreshed > 0,
                      f'{cid}: failed {after} retarget did not restore prior preference')
        e = EditorEntry(editor_id='markopad', name='Markopad', root=version.portable_root,
            active_version=version.version, versions=(version,), desktop_issue='ready',
            desktop_runtime='portable', launch_mode='portable')
        already_saved = FakeController(e, version, 'installed')
        apply_runtime(already_saved, e, 'installed', 'installed')
        check(already_saved.repaired == [('component', 'installed')],
              'saving an already-stored explicit choice cannot correct a contradictory desktop launcher')
        blocked = FakeController(e, version, 'installed')
        e.desktop_issue = 'external-target'
        apply_runtime(blocked, e, 'portable', 'installed')
        check(not blocked.repaired and blocked.config.overrides['markopad'].get('launch_mode') == 'portable',
              'runtime preference silently replaced an external/broken desktop launcher')
        e.desktop_issue = 'missing'
        missing = FakeController(e, version, 'installed')
        apply_runtime(missing, e, 'portable', 'installed')
        check(not missing.repaired and missing.config.overrides['markopad']['launch_mode'] == 'installed',
              'missing launcher either blocked remembered choice or created integration silently')
    except (AssertionError, ValueError, SyntaxError) as exc:
        errors.append('0.8.5: GUI wiring audit failed: ' + str(exc))
    scratch.cleanup()


if __name__ == '__main__':
    failures: list[str] = []
    run_regressions(failures)
    for failure in failures:
        print('FAIL:', failure)
    if failures:
        raise SystemExit(f'{len(failures)} regression(s) failed')
    print('PASS: preference/desktop and Developer Intake/Shift-install/Ctrl-retain drop regressions')
