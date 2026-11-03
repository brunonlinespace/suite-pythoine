"""Exercise the real shared App Page/current-version renderer with Qt-free layout doubles.

The release host need not have PyQt6 installed.  We compile only the two
unmodified method AST nodes from app.py, then record buttons, their order,
visibility, targets and enabled states without importing GUI dependencies.
"""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations

import ast
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from suite_pythoine.storage_layout import editor_root, is_within, recovery_root


class FakeFont:
    def __init__(self):
        self.points = 10
    def setBold(self, value):
        self.bold = value
    def pointSize(self):
        return self.points
    def setPointSize(self, value):
        self.points = value


class FakeWidget:
    def __init__(self, label='', *args, **kwargs):
        self.label = str(label) if isinstance(label, str) else ''
        self.font_object = FakeFont()
        self.enabled = True
        self.visible = True
        self._properties = {}
    def font(self):
        return self.font_object
    def setFont(self, font):
        self.font_object = font
    def setWordWrap(self, *_):
        pass
    def setTextFormat(self, *_):
        pass
    def setTextInteractionFlags(self, *_):
        pass
    def setFrameShape(self, *_):
        pass
    def setToolTip(self, value):
        self.tooltip = value
    def setStyleSheet(self, value):
        self.style = value
    def setEnabled(self, value):
        self.enabled = bool(value)
    def setVisible(self, value):
        self.visible = bool(value)
    def setProperty(self, name, value):
        self._properties[str(name)] = value
    def property(self, name):
        return self._properties.get(str(name))
    def setPixmap(self, *_):
        pass


class FakeSignal:
    def connect(self, callback):
        self.callback = callback


class FakeLineEdit(FakeWidget):
    def __init__(self, *args):
        super().__init__()
        self._text = ''
        self.textChanged = FakeSignal()
    def setPlaceholderText(self, text):
        self.placeholder = text
    def setAccessibleName(self, text):
        self.accessible_name = text
    def setClearButtonEnabled(self, enabled):
        self.clear_button = enabled
    def setMaximumWidth(self, width):
        self.maximum_width = width
    def text(self):
        return self._text
    def setText(self, text):
        self._text = text
        self.textChanged.callback(text)
    def clear(self):
        self.setText('')


class FakeTimer:
    instances = []
    def __init__(self, parent):
        self.parent = parent
        self.timeout = FakeSignal()
        self.interval = None
        self.started = False
        self.instances.append(self)
    def setSingleShot(self, value):
        self.single_shot = value
    def setInterval(self, value):
        self.interval = value
    def start(self):
        self.started = True
    def stop(self):
        self.started = False
    def fire(self):
        self.started = False
        self.timeout.callback()


class FakeButton(FakeWidget):
    def __init__(self, label):
        super().__init__(label)
        self.clicked = FakeSignal()


class FakeFrame(FakeWidget):
    Shape = SimpleNamespace(StyledPanel=1, HLine=2)


class FakeLayout:
    def __init__(self, *args):
        self.items = []
        if args and isinstance(args[0], FakeFrame):
            args[0]._recorded_layout = self
    def setContentsMargins(self, *_):
        pass
    def setSpacing(self, *_):
        pass
    def addWidget(self, widget):
        self.items.append(widget)
    def addLayout(self, layout):
        self.items.append(layout)
    def addStretch(self, *_):
        pass


def _renderers():
    app_path = Path(__file__).resolve().parents[1] / 'app.py'
    code = read_app_with_presentations()
    tree = ast.parse(code)
    suite = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'SuiteWindow')
    methods = {node.name: node for node in suite.body if isinstance(node, ast.FunctionDef)}
    required = ('_add_details_identity_header', '_version_management_frame', '_populate_editor_details')
    namespace = {
        'QFrame': FakeFrame, 'QLabel': FakeWidget, 'QPushButton': FakeButton,
        'QHBoxLayout': FakeLayout, 'QVBoxLayout': FakeLayout,
        'QLineEdit': FakeLineEdit, 'QTimer': FakeTimer,
        'Qt': SimpleNamespace(TextFormat=SimpleNamespace(PlainText=1),
                              TextInteractionFlag=SimpleNamespace(TextSelectableByMouse=2)),
         'sys': sys, '__version__': '0.9.0', 'APP_ICON_PATH': Path('/no-test-hub-icon.png'),
        'is_hub': lambda component: component.component_kind == 'hub',
        'recovery_root': recovery_root,
        'recovery_available': lambda path: path.is_dir() and not path.is_symlink(),
        'find_appimage_build_script': lambda root: (root / 'builder.sh') if (root / 'builder.sh').is_file() else None,
        'editor_root': editor_root, 'is_within': is_within,
        'can_open_document': lambda component: component.component_kind in ('editor', 'reader'),
        '_style_destructive_button': lambda button: setattr(button, 'style', '#bc5050 native-tint'),
    }
    # Deliberately compile the actual renderer methods, not a hand-made copy.
    selected = ast.Module(body=[methods[name] for name in required], type_ignores=[])
    selected = ast.fix_missing_locations(selected)
    exec(compile(selected, str(app_path), 'exec'), namespace)
    return namespace


def _row_buttons(layout):
    return [widget for widget in layout.items if isinstance(widget, FakeButton)]


def _visible_row_buttons(layout):
    return [widget for widget in _row_buttons(layout) if widget.visible]


def _headings_and_rows(layout):
    pairs = {}
    for index, item in enumerate(layout.items[:-1]):
        if isinstance(item, FakeWidget) and item.label in ('Portable Runtime', 'AppImage Runtime', 'Application', 'Settings', 'Current Version', 'Removal', 'Extension', 'Hub'):
            nxt = layout.items[index + 1]
            if item.label == 'Removal' and isinstance(nxt, FakeWidget) and index + 2 < len(layout.items):
                nxt = layout.items[index + 2]
            if isinstance(nxt, FakeLayout):
                pairs[item.label] = _visible_row_buttons(nxt)
    return pairs


def _card_rows(layout):
    rows = [item for item in layout.items if isinstance(item, FakeLayout) and _row_buttons(item)]
    if len(rows) != 3:
        return {}
    return {'Actions': _row_buttons(rows[0]), 'Portable Runtime': _row_buttons(rows[1]),
            'AppImage Runtime': _row_buttons(rows[2])}


def run_regressions(errors: list[str]) -> None:
    def check(condition, message):
        if not condition:
            errors.append('0.8.7 Details: ' + message)
    namespace = _renderers()
    with TemporaryDirectory(prefix='suite087-details-') as tmp:
        root = Path(tmp) / 'Components'
        root.mkdir()
        launched = []
        invoked = []

        class Window:
            editors_root = root
            launcher = SimpleNamespace(open_path=lambda path: launched.append(Path(path)))
            runtime = SimpleNamespace(running_as_appimage=False)
            developer_config = SimpleNamespace(enabled=False)
            def _editor_summary_text(self, editor):
                return 'Active: 0.2.0 · Portable\nDesktop: Ready'
            def _portable_root_for(self, editor):
                return editor.versions[0].portable_root if editor.versions else None
            def _managed_record(self, editor):
                return {}
            def _component_config_folder(self, editor):
                return root / 'config'
            def _version_info(self, editor, version):
                return next((v for v in editor.versions if v.version == version), None)
            def _show_editor_technical_details(self, editor):
                pass
            def general_preferences(self):
                pass
            def show_installed_applications(self):
                invoked.append(('installed_applications', None, None))
            def show_version_history(self, editor):
                invoked.append(('version_history', editor, None))
            def show_uninstall_suite(self):
                invoked.append(('uninstall_suite', None, None))
            def make_version_active(self, editor, version):
                invoked.append(('activate', editor, version))
            def remove_editor_version(self, editor, version):
                invoked.append(('remove_version', editor, version))
            def remove_portable_runtime(self, editor, version):
                invoked.append(('uninstall_portable', editor, version))
            def restore_portable_from_recovery_action(self, editor, version):
                invoked.append(('restore', editor, version))
            def build_appimage_from_portable(self, editor, version):
                invoked.append(('build', editor, version))
            def uninstall_appimage_runtime(self, editor, version):
                invoked.append(('uninstall_appimage', editor, version))

        Window._add_details_identity_header = staticmethod(namespace['_add_details_identity_header'])
        Window._version_management_frame = namespace['_version_management_frame']
        Window._populate_editor_details = namespace['_populate_editor_details']
        window = Window()
        version_root = root / 'Markopad' / '0.2.0'
        portable = version_root / 'Portable'
        app_folder = version_root / 'AppImage'
        recovery = version_root / 'Recovery'
        for folder in (portable, app_folder, recovery):
            folder.mkdir(parents=True)
        (portable / 'builder.sh').write_text('#!/bin/sh\n')
        binary = app_folder / 'Markopad.AppImage'
        binary.write_bytes(b'appimage fixture')

        def version(**changes):
            data = dict(version='0.2.0', has_portable=True, has_appimage=True,
                        portable_root=portable, appimage_path=binary,
                        recovery_dir=recovery, legacy=False, validation_issue='',
                        desktop_integrated=True, managed_record={})
            data.update(changes)
            return SimpleNamespace(**data)

        card = version()
        component = SimpleNamespace(name='Markopad', editor_id='markopad', icon=None,
                                    component_kind='editor', available=True,
                                    installed_command=None,
                                    description='A Markdown editor.', active_version='0.2.0',
                                    desktop_version='0.2.0', versions=[card])
        frame = window._version_management_frame(component, card)
        check(isinstance(frame, FakeFrame), 'version frame not rendered')
        groups = _card_rows(frame_layout_for(frame))
        expected = {
            'Actions': ['Make Active', 'Open Version Folder', 'Uninstall Version…'],
            'Portable Runtime': ['Launch Portable', 'Open Portable Folder', 'Restore Portable…', 'Remove Portable'],
            'AppImage Runtime': ['Launch AppImage', 'Open AppImage Folder', 'Rebuild AppImage…', 'Remove AppImage'],
        }
        check(list(groups) == list(expected), 'card does not contain exactly three ordered action rows')
        for heading, names in expected.items():
            check([button.label for button in groups.get(heading, [])] == names,
                  f'{heading} row order/labels changed')
        check(not groups['AppImage Runtime'][2].visible, 'direct build visible outside Developer Mode')
        groups['Actions'][1].clicked.callback(False)
        groups['Portable Runtime'][1].clicked.callback(False)
        groups['AppImage Runtime'][1].clicked.callback(False)
        check(launched == [version_root, portable, app_folder], 'folder buttons do not open exact-version targets')
        for group, index in [('Actions', 0), ('Actions', 2), ('Portable Runtime', 2),
                             ('Portable Runtime', 3), ('AppImage Runtime', 2), ('AppImage Runtime', 3)]:
            groups[group][index].clicked.callback(False)
        check([name for name, _, _ in invoked] == [
            'activate', 'remove_version', 'restore', 'uninstall_portable', 'build', 'uninstall_appimage'
        ] and all(target_editor is component and target_version is card
                  for _, target_editor, target_version in invoked),
              'buttons do not target their own exact version handlers')
        window.developer_config.enabled = True
        dev_groups = _card_rows(frame_layout_for(window._version_management_frame(component, card)))
        check(dev_groups['AppImage Runtime'][2].visible and dev_groups['AppImage Runtime'][2].enabled,
              'valid exact Portable does not expose enabled Developer build')
        check(not dev_groups['Actions'][0].enabled, 'already active version unexpectedly enables Make Active')
        app_only = version(has_portable=False, portable_root=None, recovery_dir=None)
        app_groups = _card_rows(frame_layout_for(window._version_management_frame(component, app_only)))
        check(not app_groups['Portable Runtime'][0].enabled and not app_groups['Portable Runtime'][3].enabled and not app_groups['AppImage Runtime'][2].enabled,
              'AppImage-only version presents executable Portable/build actions')
        recovery_only = version(has_portable=False, portable_root=None, has_appimage=False, appimage_path=None,
                                desktop_integrated=False)
        rec_groups = _card_rows(frame_layout_for(window._version_management_frame(component, recovery_only)))
        check(rec_groups['Portable Runtime'][2].enabled and not rec_groups['Actions'][0].enabled,
              'Recovery-only version cannot restore, or incorrectly activates')

        window.developer_config.enabled = False

        expected_sections = {
            'editor': {'Application': ['New File…', 'Open File…'],
                       'Settings': ['Repair Desktop Integration', 'Open Editor Folder', 'Open Config Folder',
                                    'Preferences…'],
                       'Removal': ['Purge Editor…']},
            'reader': {'Application': ['Launch', 'Open File…'],
                       'Settings': ['Repair Desktop Integration', 'Open Reader Folder', 'Open Config Folder',
                                    'Preferences…'],
                       'Removal': ['Purge Reader…']},
            'extension': {'Application': ['Launch'],
                          'Settings': ['Repair Desktop Integration', 'Open Extension Folder', 'Open Config Folder',
                                       'Preferences…'],
                          'Removal': ['Purge Extension…']},
            'hub': {'Settings': ['Installed Applications', 'Repair Desktop Integration',
                                  'Open Config Folder', 'Hub Preferences…'],
                    'Removal': ['Uninstall Suite…']},
        }
        for kind, spec in expected_sections.items():
            component.component_kind = kind
            component.name = {'editor': 'Markopad', 'reader': 'Portapad',
                              'extension': 'Gitten', 'hub': 'Suite Pythoine'}[kind]
            component.versions = []  # only test the top-level renderer here
            component.active_version = None
            component.desktop_version = None
            managed_folder = editor_root(root, component.name)
            managed_folder.mkdir(exist_ok=True)
            layout = FakeLayout()
            window._populate_editor_details(layout, component)
            rows = _headings_and_rows(layout)
            check(list(rows) == list(spec), f'{kind}: unexpected/obsolete Details section')
            for heading, expected_buttons in spec.items():
                check([button.label for button in rows.get(heading, [])] == expected_buttons,
                      f'{kind}: {heading} order/labels mismatch')
            if kind == 'hub':
                check('Hub' not in rows and all('Technical Details…' not in [b.label for b in buttons]
                                                    for buttons in rows.values()),
                      'Suite Hub header/duplicate Technical Details is still visible')
                rows['Settings'][0].clicked.callback()
                check(invoked[-1][0] == 'installed_applications',
                      'Hub Installed Applications is not wired to existing page')
            else:
                check(all('Technical Details…' not in [b.label for b in buttons]
                          for buttons in rows.values()), f'{kind}: developer-only diagnostics visible normally')
            labels = [item.label for item in layout.items if isinstance(item, FakeWidget)]
            current_heading_index = next((i for i, item in enumerate(layout.items)
                                          if isinstance(item, FakeWidget) and item.label == 'Current Version'), -1)
            history_rows = [item for item in layout.items if isinstance(item, FakeLayout)
                            and any(isinstance(child, FakeButton) and child.label == 'Version History…'
                                    for child in item.items)]
            check('A Markdown editor.' in labels and current_heading_index >= 0 and len(history_rows) == 1 and
                  current_heading_index >
                  max(i for i, item in enumerate(layout.items) if isinstance(item, FakeWidget) and item.label == 'A Markdown editor.'),
                  f'{kind}: description must remain before Current Version')
            check(isinstance(layout.items[-1], FakeLayout) and
                  [b.label for b in _visible_row_buttons(layout.items[-1])] == spec['Removal'] and
                  layout.items.index(layout.items[-1]) > layout.items.index(history_rows[0]),
                  f'{kind}: Removal action must be separated below Version History entry')
            removal_heading = next((item for item in layout.items
                                    if isinstance(item, FakeWidget) and item.label == 'Removal'), None)
            check(removal_heading is not None and removal_heading.font_object.points >= 11,
                  f'{kind}: Removal heading must match the major section typography')
            removal_button = _visible_row_buttons(layout.items[-1])[0]
            check('#bc5050' in getattr(removal_button, 'style', ''),
                  f'{kind}: Removal action must keep destructive treatment')
            folder_label = {'editor':'Open Editor Folder', 'reader':'Open Reader Folder',
                            'extension':'Open Extension Folder', 'hub':None}[kind]
            if folder_label is not None:
                folder_button = next((button for buttons in rows.values() for button in buttons
                                      if button.label == folder_label), None)
                check(folder_button is not None and folder_button.enabled, f'{kind}: top-level folder unavailable')
                if folder_button is not None and folder_button.enabled:
                    before = len(launched)
                    folder_button.clicked.callback()
                    check(launched[before] == managed_folder,
                          f'{kind}: top-level folder target mismatch')
            else:
                check(all(button.label != 'Open Applications Folder' for buttons in rows.values() for button in buttons),
                      'Hub must not duplicate Installed Applications folder button')
        # The normal App Page now constructs only the active/current version card.
        component.component_kind = 'editor'
        component.name = 'Markopad'
        current = version(version='0.2.0')
        historical = version(version='0.2.1-exp1')
        component.versions = [current, historical]
        component.active_version = '0.2.0'
        current_layout = FakeLayout()
        result = window._populate_editor_details(current_layout, component)
        frames = [entry for entry in current_layout.items if isinstance(entry, FakeFrame)
                  and hasattr(entry, '_recorded_layout') and entry._recorded_layout.items]
        history_rows = [entry for entry in current_layout.items if isinstance(entry, FakeLayout)
                        and any(isinstance(child, FakeButton) and child.label == 'Version History…'
                                for child in entry.items)]
        check(result is None and len(frames) == 1 and len(history_rows) == 1,
              'App Page must construct one current card and one Version History entry')
        current_labels = [item.label for item in frame_layout_for(frames[0]).items if isinstance(item, FakeWidget)]
        check(any(label.startswith('0.2.0') for label in current_labels) and
              not any(label.startswith('0.2.1-exp1') for label in current_labels),
              'historical version card leaked back onto normal App Page')
        history_button = next(child for child in history_rows[0].items
                              if isinstance(child, FakeButton) and child.label == 'Version History…')
        history_button.clicked.callback(False)
        check(invoked[-1][0] == 'version_history' and invoked[-1][1] is component,
              'Version History button is not wired to the current component')
        component.versions = []
        component.active_version = None
        # Check developer-only Technical Details placement without duplicating Suite diagnostics.
        window.developer_config.enabled = True
        for kind in ('editor', 'reader', 'extension', 'hub'):
            component.component_kind = kind
            component.name = {'editor': 'Markopad', 'reader': 'Portapad',
                              'extension': 'Gitten', 'hub': 'Suite Pythoine'}[kind]
            layout = FakeLayout()
            window._populate_editor_details(layout, component)
            rows = _headings_and_rows(layout)
            buttons = [b.label for group in rows.values() for b in group]
            if kind == 'hub':
                check('Technical Details…' not in buttons, 'Suite technical details appears on App Page in Dev Mode')
            else:
                application = [b.label for b in rows.get('Application', [])]
                settings = [b.label for b in rows.get('Settings', [])]
                check(application[-1] == 'Technical Details…' and 'Technical Details…' not in settings,
                      f'{kind}: Developer details must finish Application and not appear in Settings')
                removal_labels = [b.label for b in rows.get('Removal', [])]
                check(settings[0] == 'Repair Desktop Integration' and settings[-1] == 'Preferences…' and
                      removal_labels == ['Prune…', 'Purge ' + kind.title() + '…'],
                      f'{kind}: Settings/Developer Prune/Purge order or labels changed')
    print('PASS: exact-version actions and 0.11 experimental current-version App Page regression'
          if not errors else 'CHECK: App Page/current-version layout regressions')


def frame_layout_for(frame):
    # FakeFrame stores the QVBoxLayout created with it (the real Qt frame owns it).
    return frame._recorded_layout
