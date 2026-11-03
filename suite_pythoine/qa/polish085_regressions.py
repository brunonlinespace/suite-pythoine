"""Qt-free 0.8.5 proof for activation, accurate details, sidebar and GUI diagnostics."""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations

import ast
from contextlib import redirect_stderr
from io import StringIO
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from suite_pythoine.gui_errors import gui_error_log_path, install_gui_error_hook

ROOT = Path(__file__).resolve().parents[1]


def _method(filename: str, classname: str, name: str):
    tree = ast.parse((ROOT / filename).read_text(encoding='utf8'))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == classname)
    return next(node for node in cls.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name)


def run_regressions(errors: list[str]) -> None:
    def check(ok: bool, msg: str) -> None:
        if not ok:
            errors.append('0.8.5 polish: ' + msg)

    app = read_app_with_presentations()
    zip_wizard = (ROOT / 'install_wizard.py').read_text(encoding='utf8')
    image_wizard = (ROOT / 'appimage_wizard.py').read_text(encoding='utf8')
    dashboard = (ROOT / 'ui/shell/dashboard.py').read_text(encoding='utf8')
    for expected in ('Ctrl+Shift+I', 'Get More Applications', 'Refresh Applications',
                     'Installed Applications', '"__group__:',
                     'itemClicked.connect(self._sidebar_clicked)',
                     'itemDoubleClicked.connect(self._sidebar_double_clicked)',
                     'self.launch_editor(application)', 'pixmap(56, 56)',
                     'buttons.addButton("Copy Details"', 'Desktop ID:',
                     'Active version — Portable directory:', 'Active version — AppImage file:'):
        check(expected in app, 'missing actual UI action: ' + expected)
    check('Hub Details' in dashboard, 'Dashboard Hub Details destination missing')
    check('self.install_action.setShortcut("Ctrl+Shift+N")' not in app, 'obsolete installer shortcut')
    check('currentItemChanged.connect(self._sidebar_current_changed)' in app, 'keyboard sidebar selection does not open page')
    check('self._sidebar_activated(item)' in app and 'member.setHidden(label in collapsed)' in app,
          'single-click disclosure/action contract')
    check('add_heading("HUB")' not in app, 'obsolete Hub group remains in sidebar')
    for expected in ('Make this version active after installation',
                     'self.make_active_after_install', 'self.make_active.setChecked(True)',
                     'if not self.options.make_active_after_install:',
                     'return  # A test installation must never alter the active runtime preference.'):
        check(expected in zip_wizard, 'ZIP activation: ' + expected)
    for expected in ('self.options.make_active.setVisible(True)',
                     'def make_active_after_install(self)',
                     'self.make_active.setChecked(True)'):
        check(expected in image_wizard, 'AppImage activation: ' + expected)
    # Both wizards must treat install-as-inactive as an independent explicit choice.
    for filename, klass in (('install_wizard.py', 'OptionsPage'),
                            ('appimage_wizard.py', 'AppImageOptionsPage')):
        method = _method(filename, klass, 'make_active_after_install')
        property_fn = ast.FunctionDef(name=method.name, args=method.args, body=method.body,
                                      decorator_list=[], returns=None, type_comment=None)
        namespace = {}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[property_fn], type_ignores=[])),
                     str(ROOT / filename), 'exec'), namespace)
        fn = namespace[method.name]
        for mode, value, expected in (('install', False, False), ('alongside', False, False),
                                      ('upgrade_remove', False, True), ('downgrade_remove', False, True),
                                      ('install', True, True)):
            fake = SimpleNamespace(operation_mode=mode, make_active=SimpleNamespace(isChecked=lambda: value))
            check(fn(fake) is expected, f'{filename}: activation for {mode}={value}')
    # AppImage import still refreshes while its wizard is open, so an inactive
    # import must suppress first-discovery activation before that callback. ZIP
    # installation was deliberately moved to one post-wizard refresh in 0.9.2.
    local = app.index('        def refreshed_after_appimage_install() -> None:')
    marker = app.index("self._prompted_discovery.add((inspection.editor_id, 'selection-required'))", local)
    refresh = app.index('self.refresh_editors(automatic=True)', local)
    check(local < marker < refresh, 'AppImage prompt suppression must precede in-wizard refresh')
    zip_start = app.index('    def install_editor_zip(')
    zip_end = app.index('    def developer_intake_prompt(', zip_start)
    zip_install = app[zip_start:zip_end]
    check('finished_callback=lambda: None' in zip_install and 'refreshed_after_zip_install' not in zip_install,
          'ZIP installer still performs an unsafe in-wizard inventory refresh')
    result_pos = zip_install.index('result = wizard.exec()')
    marker_pos = zip_install.index("self._prompted_discovery.add((inspection.editor_id, 'selection-required'))", result_pos)
    refresh_pos = zip_install.index('self.refresh_editors()', marker_pos)
    check(result_pos < marker_pos < refresh_pos, 'ZIP inactive-selection suppression must precede post-wizard refresh')
    for expected in ('application = next((entry for entry in self.components',
                     'self.launch_editor_version(application, version, "appimage")',
                     'self.launch_editor_version(application, version, "portable")'):
        check(expected in app, 'exact-version post-install launch: ' + expected)
    check('self.editors if entry.editor_id == inspection.editor_id' not in app,
          'Suite-specific launch still erroneously looks only at Editors')
    for expected in ('Showing {len(matched)} of {total} application',
                     'A simple hub for brunonlinespace applications'):
        check(expected in dashboard, 'dashboard application wording: ' + expected)

    # Execute the real info methods with a simulated 3-AppImage inventory and no
    # active version.  Neither text function may fabricate a primary AppImage.
    members = [_method('app.py', 'SuiteWindow', name)
               for name in ('_editor_information_text', '_editor_summary_text')]
    fake_desktop = SimpleNamespace(is_file=lambda: False, is_symlink=lambda: False)
    namespace = {'sys': SimpleNamespace(platform='linux'), 'desktop_entry_path': lambda _id: fake_desktop,
                 'saved_launch_mode': lambda *_: 'installed', 'desktop_id_for': lambda _id: 'real.desktop',
                 'editor_root': lambda *_: Path('/Suite/Example'),
                 'recovery_available': lambda _path: True, 'can_open_document': lambda _: True,
                 'is_backend_only_component': lambda _: False,
                 'is_hub': lambda _: False, 'is_extension': lambda _: False}
    exec(compile(ast.fix_missing_locations(ast.Module(body=members, type_ignores=[])),
                 str(ROOT / 'app.py'), 'exec'), namespace)
    class FakeWindow:
        editors_root = Path('/Suite')
        config = SimpleNamespace(as_dict=lambda: {})
        def _version_info(self, editor, v):
            return next((i for i in editor.versions if i.version == v), None)
    FakeWindow._editor_information_text = namespace['_editor_information_text']
    FakeWindow._editor_summary_text = namespace['_editor_summary_text']
    window = FakeWindow()
    versions = [SimpleNamespace(version=str(i), validation_issue='', has_portable=i == 1,
                 has_appimage=True, recovery_dir=Path('/fake') if i < 3 else None,
                 portable_root=Path(f'/Suite/Example/{i}/Portable'),
                 appimage_path=Path(f'/Suite/Example/{i}/AppImage/{i}.AppImage'), legacy=False)
                for i in (1, 2, 3)]
    component = SimpleNamespace(editor_id='example', name='Example', active_version=None,
                 desktop_issue='missing', desktop_runtime=None, desktop_version=None,
                 versions=versions, extensions=['.txt'])
    basic = window._editor_summary_text(component)
    details = window._editor_information_text(component)
    check('Active: Not selected' in basic and 'Versions found: 3' in basic and
          'Runtimes: 1 Portable · 3 AppImage' in basic and 'Recovery: Available for 2 versions' in basic,
          'no-active default information counts')
    check('Desktop ID: real.desktop' in details and 'None — no active version selected' in details and
          '/Suite/Example/1/AppImage/' not in details and '/Suite/Example/2/AppImage/' not in details,
          'technical details selected arbitrary inactive AppImage')
    component.active_version = '2'
    basic = window._editor_summary_text(component)
    details = window._editor_information_text(component)
    check('Active version: 2' in details and '/Suite/Example/2/AppImage/2.AppImage' in details and
          '/Suite/Example/1/AppImage/' not in details and 'desktop missing' in basic.lower(),
          'active path scope / no false desktop proof')

    # Preserve traceback from an uncaught GUI slot, rather than diagnosing the
    # historical Fedora SIGABRT from an incomplete systemd backtrace.
    saved_hook = sys.excepthook
    old_state = os.environ.get('XDG_STATE_HOME')
    try:
        with TemporaryDirectory(prefix='suite085-gui-errors-') as temp:
            os.environ['XDG_STATE_HOME'] = temp
            install_gui_error_hook()
            try:
                raise ValueError('checkbox callback diagnostic fixture')
            except ValueError:
                exc = sys.exc_info()
                with redirect_stderr(StringIO()):
                    sys.excepthook(*exc)
            content = gui_error_log_path().read_text(encoding='utf8')
            check('ValueError: checkbox callback diagnostic fixture' in content and
                  'polish085_regressions.py' in content, 'GUI traceback hook failed to persist actual Python frame')
    finally:
        sys.excepthook = saved_hook
        if old_state is None:
            os.environ.pop('XDG_STATE_HOME', None)
        else:
            os.environ['XDG_STATE_HOME'] = old_state
    print('PASS: 0.8.5 activation/sidebar/information/GUI-diagnostic regressions'
          if not errors else 'CHECK: 0.8.5 polish regressions')
