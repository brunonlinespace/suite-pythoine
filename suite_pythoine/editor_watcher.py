from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QFileSystemWatcher, QObject, QTimer, pyqtSignal


class EditorDirectoryWatcher(QObject):
    """Debounced watching for the versioned Editors hierarchy."""

    refresh_requested = pyqtSignal()

    def __init__(self, *, debounce_ms: int = 500, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self._schedule)
        self._watcher.fileChanged.connect(self._schedule)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(max(100, debounce_ms))
        self._timer.timeout.connect(self.refresh_requested)
        self._stopping = False

    def watch(self, roots: list[str | Path]) -> None:
        desired: list[str] = []
        for raw in roots:
            root = Path(raw).expanduser().resolve(strict=False)
            if not root.is_dir():
                continue
            desired.append(str(root))
            # New layout is Editors/Application/Version/{Portable,AppImage}.
            # Watch to depth three without following symlinks.
            frontier = [(root, 0)]
            while frontier and len(desired) < 512:
                parent, depth = frontier.pop(0)
                if depth >= 3:
                    continue
                try:
                    children = [child for child in parent.iterdir() if child.is_dir() and not child.is_symlink()]
                except OSError:
                    continue
                for child in children:
                    desired.append(str(child.resolve(strict=False)))
                    frontier.append((child, depth + 1))
                    if len(desired) >= 512:
                        break
        desired = list(dict.fromkeys(desired))[:512]
        active = set(self._watcher.directories())
        target = set(desired)
        remove = sorted(active - target)
        add = sorted(target - active)
        if remove:
            self._watcher.removePaths(remove)
        if add:
            self._watcher.addPaths(add)

    def stop(self) -> None:
        self._stopping = True
        self._timer.stop()
        self._watcher.blockSignals(True)

    def _schedule(self, *_args: object) -> None:
        if not self._stopping:
            self._timer.start()
