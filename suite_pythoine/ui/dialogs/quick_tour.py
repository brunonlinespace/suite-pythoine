"""Offline, reusable native Quick Tour for Suite Pythoine (Shift+F1)."""
from __future__ import annotations

import html

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel, QListWidget,
                             QPushButton, QTextBrowser, QVBoxLayout)

from ... import APP_NAME

CHAPTERS: tuple[tuple[str,str], ...] = (
    ('Welcome to Suite Pythoine', '''
Suite Pythoine is the management and file-opening Hub for separately usable applications. Its slogan is Friendly. Fast. Focused. Editors create and modify documents; Readers inspect documents; Extensions add capabilities without becoming normal document-routing candidates. The Hub is not required for every standalone program to run.

Hub Details (Ctrl+S) describes Suite itself. Installed Applications (Ctrl+I) shows discovered managed runtime installations; Hub Preferences (Ctrl+/) controls Hub behaviour. Removing Hub does not have to remove its applications.'''),
    ('Your Dashboard', '''
The Dashboard provides the application catalogue, entry points and search. Open the sidebar with F9, return to Dashboard with Ctrl+W, and refresh discovery with F5. Choose List or Grid from Dashboard Settings. Icons and the Drop Bar have independent visibility options.

Ctrl+F focuses the search belonging to your current page; Esc clears that page's search without changing your selected application. The Drop Bar supplies a convenient place to open supported files or supported URL payloads.'''),
    ('Installed Applications', '''
Ctrl+I shows the real installations found under your managed Applications folder. Portable and AppImage runtimes are shown separately, with their version and current state. Use Refresh Inventory only when you want a new filesystem discovery; typing in Search installed applications never rescans or modifies a runtime.

The four header actions are Hub Details, Refresh Inventory, Open Applications Folder and Install Application. A filter hides nonmatching table rows, not installed files.'''),
    ('Understanding Versions', '''
Each application can have several versions installed at the same time. A version may hold Portable, AppImage, and Recovery assets. Active identifies the version chosen for normal operation and desktop integration; merely launching another version does not activate it.

Use the version card to Launch Portable/AppImage explicitly, Make Active when appropriate, open its exact version folder, or uninstall one version. The Versions filter in an App Page only controls visibility: it never changes the active version.'''),
    ('Portable and AppImage', '''
Portable means an installed source tree launched with Python; AppImage is a bundled Linux executable. Both runtimes can coexist for the same exact application version under one managed Applications root. A runtime preference selects how normal launch requests are handled.

An explicitly chosen runtime is strict: if it is unavailable, Suite does not silently substitute another. Repair Desktop Integration uses the saved runtime preference and validates the selected target rather than treating a filename alone as proof. If discovery has no active selection, Repair asks you to establish the version/runtime explicitly instead of guessing.'''),
    ('Installing and Building', '''
Install Application accepts a supported source ZIP or a direct AppImage. Validated ZIP installations retain the exact original source archive in Recovery. Installations may coexist alongside older versions and need not automatically become active.

For installed Portable versions, Build/Rebuild AppImage is available on the version card where the source permits it. Developer Mode (F12) adds development-specific tools; it does not change ordinary routing. Get More Applications opens the separate application discovery path.'''),
    ('Desktop Integration', '''
A managed desktop entry makes a particular application/version/runtime accessible from the Linux application menu. Make Active changes the chosen target; Repair Desktop Integration checks the exact launcher and restores it against the selected runtime when you ask.

Portable and AppImage installations should never be removed on the assumption that a similarly named external desktop file belongs to Suite. A broken, ambiguous or external launcher must be inspected or repaired explicitly.'''),
    ('File Routing', '''
Supported file formats come from trusted component metadata, not editable per-user extension overrides. File Routing in Hub Preferences chooses a preferred eligible application for a format. It cannot invent a capability an application does not declare.

When no normal candidate is available, an explicitly configured inspector fallback can offer inspection; it does not add that inspector to normal MIME routing. Opening a document and creating a new document are separate actions owned by the application.'''),
    ('Recovery and Maintenance', '''
Recovery retains the validated original source ZIP beside the corresponding version. Restore Portable can use it when a managed Portable installation needs rebuilding. The running Hub Portable prepares and verifies its replacement first, then completes the swap only after Hub exits. Recovery is not a backup of your personal documents.

Remove Portable removes one runtime; Remove AppImage removes another. Uninstall Version removes one complete managed version and its retained Recovery assets. Purge Application concerns one whole application. The Suite-wide uninstaller is distinct and is accessed from Hub Details or Hub Preferences → Hub Versions.'''),
    ('Storage and Hub Preferences', '''
The managed Applications folder defaults to $XDG_DATA_HOME/suite-pythoine/ (or ~/.local/share/suite-pythoine/ when XDG_DATA_HOME is not a valid absolute path). Your explicitly configured Applications folder takes precedence. Portable, AppImage and Recovery share that root.

Ordinary Hub preferences are saved separately from installations. There is no central persisted managed-installation registry: inventory is reconstructed from validated filesystem metadata and desktop integration. The Hub Preferences General tab also controls automatic Quick Tour display.'''),
    ('Uninstalling Suite Pythoine', '''
Uninstall Hub Only removes validated managed Hub versions and verified Hub launcher; other applications and their Recovery archives remain untouched. Selective Suite Purge removes Hub plus only the whole components you explicitly tick; zero selected extras is allowed. Full Suite Purge includes every validated managed application.

All modes have a review listing exact paths. Optional Hub-preferences removal and selected-app-preferences removal start unchecked. Full Suite Purge requires an additional confirmation. After Hub exits, an independent helper performs verified staged cleanup and writes a report under your user state folder. Unknown or changed paths stop removal rather than being guessed.'''),
    ('Shortcuts and Useful Features', '''
F1: Documentation · Shift+F1: Quick Tour · Ctrl+Shift+/: Keyboard Shortcuts.
Ctrl+S: Hub Details · Ctrl+/: Hub Preferences · Ctrl+I: Installed Applications.
Ctrl+W: Dashboard · Ctrl+F: search on current page · Esc: clear contextual search · F5: Refresh Applications · F9: Sidebar · F12: Developer Mode.

Use Keyboard Shortcuts in Help to search the full live list. Tick “Don’t show this tutorial on startup again” below if you prefer to open it only when needed. You can reverse that choice in Hub Preferences → General.'''),
)


class QuickTourDialog(QDialog):
    def __init__(self, config, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.setWindowTitle(f'{APP_NAME} — Quick Tour')
        self.setMinimumSize(760, 540)
        self.resize(940, 680)
        layout = QVBoxLayout(self)
        heading = QLabel('Suite Pythoine — Quick Tour')
        font = heading.font(); font.setPointSize(max(font.pointSize() + 5, 16)); font.setBold(True)
        heading.setFont(font)
        layout.addWidget(heading)
        subheading = QLabel('Friendly. Fast. Focused.  ·  An offline guide to Hub, installations and safe maintenance.')
        subheading.setWordWrap(True)
        layout.addWidget(subheading)
        middle = QHBoxLayout()
        self.chapter_list = QListWidget()
        self.chapter_list.setMinimumWidth(225)
        self.chapter_list.setMaximumWidth(285)
        for index, (title, _) in enumerate(CHAPTERS, 1):
            self.chapter_list.addItem(f'{index:02d}   {title}')
        self.chapter_list.currentRowChanged.connect(self._show_chapter)
        middle.addWidget(self.chapter_list)
        self.article = QTextBrowser()
        self.article.setOpenExternalLinks(False)
        self.article.setReadOnly(True)
        middle.addWidget(self.article, 1)
        layout.addLayout(middle, 1)
        self.disable_startup = QCheckBox("Don't show this tutorial on startup again")
        self.disable_startup.setChecked(not bool(config.get('show_quick_tour_on_startup', True)))
        layout.addWidget(self.disable_startup)
        buttons = QHBoxLayout()
        self.position = QLabel()
        buttons.addWidget(self.position)
        buttons.addStretch(1)
        self.previous = QPushButton('Previous')
        self.previous.clicked.connect(lambda: self.chapter_list.setCurrentRow(max(0, self.chapter_list.currentRow()-1)))
        buttons.addWidget(self.previous)
        self.next = QPushButton('Next')
        self.next.clicked.connect(lambda: self.chapter_list.setCurrentRow(min(len(CHAPTERS)-1, self.chapter_list.currentRow()+1)))
        buttons.addWidget(self.next)
        close = QPushButton('Close')
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self.chapter_list.setCurrentRow(0)

    def _show_chapter(self, index: int) -> None:
        if not 0 <= index < len(CHAPTERS):
            return
        title, description = CHAPTERS[index]
        blocks = '\n'.join(f'<p>{html.escape(paragraph).replace(chr(10), '<br>')}</p>' for paragraph in description.strip().split('\n\n'))
        self.article.setHtml(f'<h2>{index+1:02d}. {html.escape(title)}</h2>{blocks}')
        self.position.setText(f'Chapter {index+1} of {len(CHAPTERS)}')
        self.previous.setEnabled(index > 0)
        self.next.setEnabled(index < len(CHAPTERS)-1)

    def done(self, result: int) -> None:
        self.config.set('show_quick_tour_on_startup', not self.disable_startup.isChecked(), save=True)
        super().done(result)
