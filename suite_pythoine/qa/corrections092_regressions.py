"""0.9.2 scoped corrections: installer completion, smoke startup, inventory cleanup and AppImage diagnostics."""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]


def _suite_method(source: str, name: str) -> str:
    tree = ast.parse(source)
    suite = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'SuiteWindow')
    method = next(node for node in suite.body if isinstance(node, ast.FunctionDef) and node.name == name)
    return ast.get_source_segment(source, method) or ''


def _top_function(source: str, name: str) -> str:
    tree = ast.parse(source)
    method = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
    return ast.get_source_segment(source, method) or ''


def run_regressions(errors: list[str]) -> None:
    def check(ok: bool, message: str) -> None:
        if not ok:
            errors.append('0.9.2 corrections: ' + message)

    app = read_app_with_presentations()
    appimage = (PACKAGE / 'appimage_wizard.py').read_text(encoding='utf-8')

    labels = _suite_method(app, '_inventory_column_labels')
    inventory = (PACKAGE / 'ui/pages/installed_applications.py').read_text(encoding='utf8')
    menu = _suite_method(app, '_make_menu')
    zip_install = _suite_method(app, 'install_editor_zip')
    init = _suite_method(app, '__init__')
    main = _top_function(app, 'main')

    check('\"Desktop\"' not in labels and '\"Managed\"' not in labels and
          all(token in labels for token in ('\"Application\"', '\"Version\"', '\"Asset\"', '\"Active\"', '\"Size\"', '\"Install date\"', '\"Location\"', '\"Quick actions\"')) and
          '\"Runtime\"' not in labels,
          'Installed Applications core columns are not the approved eight-column set')
    check('QTableWidget(0, 9)' in inventory and
          'setHorizontalHeaderLabels([*self._inventory_column_labels(), \"\"])' in inventory and
          'setCellWidget(row, 7, action_widget)' in inventory and 'table.setColumnHidden(8, True)' in inventory,
          'Installed Applications core eight columns plus transient removal selector are not mapped correctly')
    check('for column in (0, 1, 2, 3):' in inventory and 'for column in (0, 1, 2, 3, 4):' not in inventory,
          'Installed Applications search still includes removed Desktop state')

    tools = menu[menu.index('tools = self.menuBar().addMenu("Tools")'):menu.index('help_menu =')]
    install_pos = tools.index('tools.addAction(self.install_action)')
    separator_pos = tools.index('tools.addSeparator()', install_pos)
    store_pos = tools.index('tools.addAction(self.store_action)')
    check(install_pos < separator_pos < store_pos,
          'Tools separator is not immediately before Get More Applications')
    help_block = menu[menu.index('help_menu ='):]
    doc_pos = help_block.index('help_menu.addAction(self.documentation_action)')
    help_sep_pos = help_block.index('help_menu.addSeparator()', doc_pos)
    tour_pos = help_block.index('help_menu.addAction(self.quick_tour_action)')
    check(doc_pos < help_sep_pos < tour_pos,
          'Help separator is not immediately after Documentation')

    check('QTimer.singleShot(0, self.show_quick_tour)' not in init,
          'generic SuiteWindow construction still schedules first-run Quick Tour')
    smoke_pos = main.index('if smoke_test:')
    smoke_return = main.index('return 0', smoke_pos)
    tour_schedule = main.index('QTimer.singleShot(0, window.show_quick_tour)')
    check(smoke_pos < smoke_return < tour_schedule,
          'Quick Tour is still scheduled on the packaging smoke-test path')

    check('finished_callback=lambda: None' in zip_install and 'refreshed_after_zip_install' not in zip_install,
          'ZIP wizard still invokes the unsafe in-wizard inventory refresh callback')
    check('wizard.options.make_active_after_install' not in zip_install and
          'wizard.options_page.make_active_after_install' in zip_install,
          'ZIP post-wizard activation policy still dereferences QWizard.options instead of OptionsPage')
    exec_pos = zip_install.index('result = wizard.exec()')
    inactive_pos = zip_install.index("self._prompted_discovery.add((inspection.editor_id, 'selection-required'))", exec_pos)
    refresh_pos = zip_install.index('self.refresh_editors()', inactive_pos)
    check(exec_pos < inactive_pos < refresh_pos,
          'ZIP inventory refresh is not deferred until after wizard completion')

    for token in (
        'QPlainTextEdit', 'QFontDatabase', 'QTextCursor',
        'QPushButton("Show technical details")', 'def _log(self, text: str)',
        'def _toggle_output(self, checked: bool)', 'def _grow_wizard_for_output(self)',
        'Command: waiting for AppImage installation to begin',
        '[suite] Source AppImage:', '[suite] AppImage SHA-256:',
        '[suite] Installation metadata:', '[suite] AppImage provenance: imported',
        'Command: installation complete', '[suite] Installation complete',
    ):
        check(token in appimage, f'AppImage Technical Details parity missing: {token}')
