"""0.8.8-only scope checks; all GUI checks work without Qt on the build host."""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations
import ast
import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from unittest.mock import patch
from suite_pythoine.config import apply_routing_compatibility_migrations
from suite_pythoine.storage_layout import editors_root_default
from suite_pythoine.catalogue.component_catalog import load_catalog

PACKAGE = Path(__file__).resolve().parents[1]
PREFERENCES = PACKAGE / 'ui' / 'dialogs' / 'preferences.py'


def method(source: str, cls: str, name: str) -> str:
    if cls in {'EditorPreferencesDialog', 'GeneralPreferencesDialog'}:
        source = PREFERENCES.read_text(encoding='utf8')
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls)
    return ast.get_source_segment(source, next(n for n in node.body if isinstance(n, ast.FunctionDef) and n.name == name))


def run_regressions(errors: list[str]) -> None:
    def check(ok: bool, message: str) -> None:
        if not ok:
            errors.append('0.8.8 polish: ' + message)

    app = read_app_with_presentations()
    config = (PACKAGE / 'config.py').read_text(encoding='utf8')
    registry = (PACKAGE / 'registry.py').read_text(encoding='utf8')
    purge = (PACKAGE / 'purge_wizard.py').read_text(encoding='utf8')
    general = method(app, 'GeneralPreferencesDialog', '__init__')
    app_pref = method(app, 'EditorPreferencesDialog', '__init__')
    app_apply = method(app, 'EditorPreferencesDialog', 'apply')
    details = method(app, 'SuiteWindow', '_populate_editor_details')
    history = method(app, 'SuiteWindow', '_version_history_page')
    menu = method(app, 'SuiteWindow', '_make_menu')
    shortcuts = method(app, 'SuiteWindow', '_shortcut_catalog')
    event = method(app, 'SuiteWindow', 'eventFilter')
    focus = method(app, 'SuiteWindow', '_focus_contextual_search')

    # The default is resolved at invocation; relative XDG_DATA_HOME is invalid.
    with TemporaryDirectory(prefix='suite088-xdg-') as tmp:
        home = Path(tmp)
        with patch('pathlib.Path.home', return_value=home):
            for value, expected in ((None, home / '.local/share/suite-pythoine'),
                                    ('relative/location', home / '.local/share/suite-pythoine'),
                                    ('', home / '.local/share/suite-pythoine'),
                                    (str(home / 'custom/data'), home / 'custom/data/suite-pythoine')):
                with patch.dict(os.environ, {'XDG_DATA_HOME': value} if value is not None else {}, clear=False):
                    if value is None:
                        with patch.dict(os.environ, {'XDG_DATA_HOME': ''}):
                            actual = editors_root_default()
                    else:
                        actual = editors_root_default()
                check(actual == expected, f'XDG default/fallback for {value!r}')
    check('resolve_editors_root' in (PACKAGE / 'runtime/runtime_paths.py').read_text(encoding='utf8') and
          'if isinstance(configured, str) and configured.strip():' in (PACKAGE / 'runtime/runtime_paths.py').read_text(encoding='utf8'),
          'explicitly configured Applications root no longer takes precedence')
    check(general.index('general_layout.addWidget(info)') < general.index('form.addRow("Applications folder:"') and
          'runtime.default_editors_root' in general,
          'resolved default directory explanation must precede folder selector')
    check(all(s in general for s in ('QGroupBox("Runtime")', 'QLabel("Launch:")',
                                  'QPushButton("Repair Desktop Integration")', 'QPushButton("Portable Folder")',
                                  'QPushButton("AppImage Folder")')) and
          general.index('runtime_row.addWidget(self.suite_runtime, 1)') <
          general.index('runtime_row.addWidget(self.repair_desktop_button)') <
          general.index('runtime_row.addWidget(self.open_portable_button)') <
          general.index('runtime_row.addWidget(self.open_installed_button)') <
          general.index('general_layout.addWidget(runtime_group)') < general.index('QGroupBox("Dashboard")') and
          'QGroupBox("Portable Runtime")' not in general and 'QGroupBox("AppImage Runtime")' not in general,
          'single-row runtime section/order')

    check('QLineEdit()' in history and 'Filter versions…' in history and
          'version_filter.setMaximumWidth(220)' in history and 'filter_timer.setInterval(150)' in history and
          'query not in version' in history and 'table.setRowHidden' in history and
          'if not value.strip():' in history and 'apply_filter()' in history and
          'refresh_editors(' not in history,
          'Version History live, non-rescanning partial-match filter')
    check('self._version_filters[page] = version_filter' in history and
          'show_version_history' in focus and
          'version_filter.setFocus(Qt.FocusReason.ShortcutFocusReason)' in focus and
          'version_filter.selectAll()' in focus and
          'self.show_dashboard()' in focus and
          'version_filter.clear()' in event and 'self.dashboard.search.clear()' in event and
          'refresh_editors(' not in event,
          'contextual Ctrl+F/Esc must not change inventory or active version')
    check('self.search_action.setShortcut("Ctrl+F")' in menu and
          'self.search_action.triggered.connect(self._focus_contextual_search)' in menu and
          'self.hub_details_action.setShortcut("Ctrl+S")' in menu and
          'self.hub_details_action.triggered.connect(self.show_suite_details)' in menu and
          menu.index('tools.addAction(self.hub_details_action)') <
          menu.index('tools.addAction(self.preferences_action)') <
          menu.index('tools.addAction(self.installed_applications_action)') <
          menu.index('tools.addAction(self.install_action)') <
          menu.index('tools.addAction(self.store_action)') < menu.index('tools.addAction(self.developer_action)'),
          'superseding 0.8.9 Tools opening order or Ctrl+S Hub Details binding')
    check('("Hub Details", self.hub_details_action)' in shortcuts and
          'Dashboard / Version History / Installed Applications search' in shortcuts and '"Esc"' in shortcuts,
          'Keyboard Shortcuts missing contextual/Hub entries')
    # The existing shortcut search must still match fuzzy modifier/key order.
    shortcut_source = (PACKAGE / 'ui/dialogs/shortcuts_dialog.py').read_text(encoding='utf8')
    shortcut_tree = ast.parse(shortcut_source)
    matching = [n for n in shortcut_tree.body if isinstance(n, ast.FunctionDef) and
                n.name in ('_shortcut_tokens', '_shortcut_query_matches')]
    scope = {'re': re, '_SHORTCUT_TOKEN_RE': re.compile(r'[a-z0-9]+|[^\w\s+]', re.I),
             '_SHORTCUT_TOKEN_ALIASES': {'control': 'ctrl', 'ctrl': 'ctrl', 'ctl': 'ctrl'}}
    exec(compile(ast.fix_missing_locations(ast.Module(body=matching, type_ignores=[])), 'ui/dialogs/shortcuts_dialog.py', 'exec'), scope)
    tokens = scope['_shortcut_tokens']('Ctrl+Shift+O')
    match = scope['_shortcut_query_matches']
    check(match('shift ctrl o', tokens) and match('control+o', tokens) and
          not match('ctrl+s', tokens) and 'or _shortcut_query_matches(query, shortcut_tokens)' in shortcut_source,
          'existing fuzzy shortcuts search regressed')

    # File-extension editing is retired even for Dev Mode; previously saved keys
    # must be removed before both GUI and silent-route inventory discovery.
    check('File extensions:' not in app_pref and 'self.extensions' not in app_pref and
          'override.pop("extensions", None)' in app_apply and
          'override.get("extensions")' not in registry and
          '"extensions" in override' not in registry and
          'for key in ("installed_path", "extensions")' in config,
          'manual format override still editable or read as capability')
    old = {'editor_overrides': {'markopad': {'extensions': ['.fake'], 'launch_mode': 'portable'},
                                'portapad': {'extensions': ['.other']}}}
    check(apply_routing_compatibility_migrations(old) and old['editor_overrides'] ==
          {'markopad': {'launch_mode': 'portable'}, 'portapad': {}},
          'historical extension override not removed while preserving launch mode')
    check('.md' in load_catalog()['markopad'].extensions and '.rtf' in load_catalog()['ricopad'].extensions,
          'trusted catalogue capabilities inadvertently changed')

    expected_hub = ['"Installed Applications", self.show_installed_applications',
                    '*hub_repair_actions', '"Open Config Folder", lambda:',
                    '"Hub Preferences…", self.general_preferences']
    hub_details = details[details.index('elif editor.component_kind == "hub":'):]
    check(all(s in hub_details for s in expected_hub) and
          [hub_details.index(s) for s in expected_hub] == sorted(hub_details.index(s) for s in expected_hub),
          'Hub Settings button order')
    check('"Uninstall Version, Remove Portable or Remove AppImage."' in purge and
          '"Remove Version, Uninstall Portable or Uninstall AppImage."' not in purge and
          'self.setMinimumSize(820, 640)' in purge and 'self.resize(980, 800)' in purge,
          'Purge precise terminology or window dimensions')
    # Keep the deferred installer completion code byte-for-byte in the source
    # comparison rather than attempting to regress the known unfinished workflow.

    print('PASS: 0.8.8 XDG, UI, format-override and unchanged fuzzy shortcut regressions'
          if not any(e.startswith('0.8.8 polish:') for e in errors) else 'CHECK: 0.8.8 regressions')
