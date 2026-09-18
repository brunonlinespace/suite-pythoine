from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PyQt6.QtCore import QObject, QProcess, QProcessEnvironment, pyqtSignal

from .runtime_paths import RuntimePaths

PYTHON_OVERRIDE_VARIABLE = "SUITE_PYTHOINE_PYTHON"

_SANITIZED_VARIABLES = frozenset(
    {
        "APPDIR",
        "APPIMAGE",
        "ARGV0",
        "OWD",
        "LD_LIBRARY_PATH",
        "PYTHONHOME",
        "PYTHONPATH",
        "PYTHONEXECUTABLE",
        "QT_PLUGIN_PATH",
        "QT_QPA_PLATFORM_PLUGIN_PATH",
        "QML2_IMPORT_PATH",
        "QML_IMPORT_PATH",
    }
)


@dataclass(frozen=True, slots=True)
class LaunchCommand:
    program: str
    arguments: tuple[str, ...] = ()
    working_directory: Path | None = None


class RuntimeLauncher(QObject):
    """Launch loaded editors and host desktop tools outside Suite's bundle."""

    status_message = pyqtSignal(str)
    launch_error = pyqtSignal(str)

    def __init__(self, runtime_paths: RuntimePaths, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.runtime_paths = runtime_paths

    def python_executable(self) -> str | None:
        override = os.environ.get(PYTHON_OVERRIDE_VARIABLE, "").strip()
        if override:
            resolved = self._resolve_executable(override)
            if resolved:
                return resolved

        if not self.runtime_paths.running_as_appimage and not self.runtime_paths.running_frozen:
            return str(Path(sys.executable).resolve())

        for candidate in ("python3", "python"):
            resolved = self._resolve_executable(candidate)
            if resolved:
                return resolved
        return None

    def process_environment(self) -> QProcessEnvironment:
        environment = QProcessEnvironment.systemEnvironment()
        if not self.runtime_paths.running_as_appimage and not self.runtime_paths.running_frozen:
            return environment

        for name in _SANITIZED_VARIABLES:
            environment.remove(name)
        for name in ("LD_LIBRARY_PATH", "PYTHONHOME", "PYTHONPATH"):
            original_name = f"APPIMAGE_ORIGINAL_{name}"
            original_value = os.environ.get(original_name)
            if original_value is not None:
                environment.insert(name, original_value)
            environment.remove(original_name)
        return environment

    def configure_process(self, process: QProcess, command: LaunchCommand) -> None:
        process.setProgram(command.program)
        process.setArguments(list(command.arguments))
        if command.working_directory is not None:
            process.setWorkingDirectory(str(command.working_directory))
        process.setProcessEnvironment(self.process_environment())

    def start_detached(self, command: LaunchCommand) -> bool:
        process = QProcess(self)
        self.configure_process(process, command)
        try:
            result = process.startDetached()
        except TypeError:
            result = QProcess.startDetached(
                command.program,
                list(command.arguments),
                str(command.working_directory) if command.working_directory else "",
            )
        return bool(result[0] if isinstance(result, tuple) else result)

    def open_path(self, path: str | Path) -> bool:
        target = Path(path).expanduser().resolve(strict=False)
        command = self._desktop_open_command(str(target))
        if command is None:
            return self._fail("No host desktop opener was found (xdg-open or gio).")
        if not self.start_detached(command):
            return self._fail(f"Could not open '{target}'.")
        return True

    def open_url(self, url: str) -> bool:
        target = str(url).strip()
        if not (target.startswith("https://") or target.startswith("http://")):
            return self._fail("Only HTTP and HTTPS links can be opened externally.")
        command = self._desktop_open_command(target)
        if command is None:
            return self._fail("No host desktop opener was found (xdg-open or gio).")
        if not self.start_detached(command):
            return self._fail(f"Could not open '{target}'.")
        return True

    def command_for_parts(self, parts: Iterable[str], *, working_directory: str | Path | None = None) -> LaunchCommand | None:
        values = tuple(str(part) for part in parts)
        if not values:
            return None
        resolved = self._resolve_executable(values[0])
        if resolved is None:
            candidate = Path(values[0]).expanduser()
            if candidate.is_file() and os.access(candidate, os.X_OK):
                resolved = str(candidate.resolve())
            else:
                return None
        cwd = Path(working_directory).expanduser().resolve(strict=False) if working_directory else None
        return LaunchCommand(resolved, values[1:], cwd)

    def _desktop_open_command(self, target: str) -> LaunchCommand | None:
        xdg_open = self._resolve_executable("xdg-open")
        if xdg_open:
            return LaunchCommand(xdg_open, (target,))
        gio = self._resolve_executable("gio")
        if gio:
            return LaunchCommand(gio, ("open", target))
        if os.name == "nt":
            # Explorer is the least surprising Windows fallback for folders.
            explorer = self._resolve_executable("explorer.exe")
            if explorer:
                return LaunchCommand(explorer, (target,))
        return None

    def _resolve_executable(self, executable: str) -> str | None:
        path = Path(executable).expanduser()
        if path.is_absolute():
            return str(path) if path.is_file() and os.access(path, os.X_OK) else None
        return shutil.which(executable, path=os.environ.get("PATH"))

    def _fail(self, message: str) -> bool:
        self.launch_error.emit(message)
        self.status_message.emit(message)
        return False
