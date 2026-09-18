from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Iterable

from .component_policy import document_candidates
from .config import apply_routing_compatibility_migrations, default_config_path
from .registry import discover_editors
from .routing_index import RoutingTarget, load_index, target_from_component
from .storage_layout import editors_root_default

ASK_EVERY_TIME = "__ask_every_time__"
INSPECTOR_FALLBACK_ASK = "__ask_every_time__"
INSPECTOR_FALLBACK_IDS = ("beespector", "beespector-lite")

_SANITIZED_VARIABLES = frozenset(
    {
        "APPDIR", "APPIMAGE", "ARGV0", "OWD", "LD_LIBRARY_PATH",
        "PYTHONHOME", "PYTHONPATH", "PYTHONEXECUTABLE", "QT_PLUGIN_PATH",
        "QT_QPA_PLATFORM_PLUGIN_PATH", "QML2_IMPORT_PATH", "QML_IMPORT_PATH",
    }
)


@dataclass(frozen=True, slots=True)
class ChoiceRequest:
    path: Path
    extension: str
    candidates: tuple[RoutingTarget, ...]


@dataclass(frozen=True, slots=True)
class InspectorFallbackRequest:
    path: Path
    candidates: tuple[RoutingTarget, ...]


@dataclass(frozen=True, slots=True)
class DispatchResult:
    launched: tuple[Path, ...]
    unresolved: tuple[Path, ...]
    choices: tuple[ChoiceRequest, ...]
    inspector_choices: tuple[InspectorFallbackRequest, ...]
    errors: tuple[str, ...]

    @property
    def fully_dispatched(self) -> bool:
        return bool(self.launched) and not self.unresolved and not self.choices and not self.inspector_choices and not self.errors

    @property
    def needs_chooser_only(self) -> bool:
        return bool(self.choices or self.inspector_choices) and not self.unresolved and not self.errors


def load_config() -> dict:
    try:
        data = json.loads(default_config_path().read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}
    apply_routing_compatibility_migrations(data)
    return data


def save_config(data: dict) -> bool:
    path = default_config_path()
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        import tempfile
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
            temporary = Path(handle.name)
        temporary.replace(path)
        return True
    except OSError:
        return False
    finally:
        if temporary is not None and temporary.exists():
            try:
                temporary.unlink()
            except OSError:
                pass


def _running_as_appimage() -> bool:
    return bool(os.environ.get("APPIMAGE"))


def _running_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def host_python() -> str | None:
    override = os.environ.get("SUITE_PYTHOINE_PYTHON", "").strip()
    if override:
        candidate = Path(override).expanduser()
        if candidate.is_absolute() and candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate.resolve())
        resolved = shutil.which(override)
        if resolved:
            return resolved
    if not _running_as_appimage() and not _running_frozen():
        return str(Path(sys.executable).resolve())
    return shutil.which("python3") or shutil.which("python")


def components_root(config: dict) -> Path:
    configured = config.get("editors_root")
    if isinstance(configured, str) and configured.strip():
        return Path(configured).expanduser().resolve(strict=False)
    override = (
        os.environ.get("SUITE_PYTHOINE_COMPONENTS_ROOT", "").strip()
        or os.environ.get("SUITE_PYTHOINE_EDITORS_ROOT", "").strip()
    )
    if override:
        return Path(override).expanduser().resolve(strict=False)
    return editors_root_default()


def process_environment() -> dict[str, str]:
    environment = dict(os.environ)
    if not _running_as_appimage() and not _running_frozen():
        return environment
    for name in _SANITIZED_VARIABLES:
        environment.pop(name, None)
    for name in ("LD_LIBRARY_PATH", "PYTHONHOME", "PYTHONPATH"):
        original_name = f"APPIMAGE_ORIGINAL_{name}"
        if original_name in os.environ:
            environment[name] = os.environ[original_name]
        environment.pop(original_name, None)
    return environment


def load_routing_targets(config: dict | None = None) -> tuple[list[RoutingTarget], Path, bool]:
    config = config if isinstance(config, dict) else load_config()
    root = components_root(config)
    cached = load_index(config, root)
    if cached is not None:
        return cached, root, True
    components = discover_editors(root, root, config, python_executable=host_python())
    return [target_from_component(component) for component in components], root, False


def _launch(target: RoutingTarget, path: Path | None = None) -> tuple[bool, str | None]:
    parts = target.command()
    if not parts:
        wanted = {"portable": "Portable/source", "installed": "AppImage"}.get(target.launch_mode, "launchable")
        return False, f"{target.name} has no {wanted} runtime available for its current launch preference."
    arguments = [*parts[1:]]
    if path is not None:
        arguments.append(str(path.resolve(strict=False)))
    working_directory = target.portable_root if target.portable_command and parts == target.portable_command else None
    if working_directory is None and target.installed_command and parts == target.installed_command:
        installed_program = Path(parts[0]).expanduser().resolve(strict=False)
        if installed_program.parent.is_dir():
            working_directory = installed_program.parent
    popen_kwargs = {
        "cwd": str(working_directory) if working_directory else None,
        "env": process_environment(),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": (os.name != "nt"),
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        popen_kwargs["start_new_session"] = True
    try:
        subprocess.Popen([parts[0], *arguments], **popen_kwargs)
    except (OSError, ValueError) as exc:
        return False, f"Could not launch {target.name}: {exc}"
    return True, None


def inspector_fallback_targets(targets: Iterable[RoutingTarget]) -> list[RoutingTarget]:
    """Return installed inspection Readers eligible only for zero-candidate fallback.

    This helper deliberately does *not* call document_candidates(): Beespector and
    Beespector Lite remain routing=false and therefore can never enter normal
    validated extension routing or MIME ownership.
    """
    by_id = {target.component_id: target for target in targets}
    return [
        by_id[component_id]
        for component_id in INSPECTOR_FALLBACK_IDS
        if component_id in by_id
        and by_id[component_id].available
        and "open" in by_id[component_id].capabilities
    ]


def launch_inspector_fallback(
    request: InspectorFallbackRequest,
    component_id: str,
    *,
    remember: bool,
) -> tuple[bool, str | None]:
    target = next((candidate for candidate in request.candidates if candidate.component_id == component_id), None)
    if target is None:
        return False, "The selected inspection application is no longer available."
    ok, error = _launch(target, request.path)
    if ok and remember:
        config = load_config()
        config["inspector_fallback_preference"] = target.component_id
        if not save_config(config):
            return True, "The file opened, but Suite Pythoine could not save the inspection fallback preference."
    return ok, error


def _dispatch_inspector_fallback(
    path: Path,
    targets: Iterable[RoutingTarget],
    config: dict,
) -> tuple[bool, InspectorFallbackRequest | None, str | None]:
    """Handle unsupported-file fallback after normal routing returned zero candidates.

    Returns (launched, chooser_request, error).  This stage is intentionally
    unreachable when a trusted Editor/Reader routing candidate exists.
    """
    candidates = inspector_fallback_targets(targets)
    if not candidates:
        return False, None, None
    preference = str(config.get("inspector_fallback_preference") or INSPECTOR_FALLBACK_ASK)
    preferred = next((candidate for candidate in candidates if candidate.component_id == preference), None)
    if preferred is not None:
        ok, error = _launch(preferred, path)
        return ok, None, error
    if len(candidates) == 1:
        ok, error = _launch(candidates[0], path)
        return ok, None, error
    return False, InspectorFallbackRequest(path, tuple(candidates)), None


def launch_choice(choice: ChoiceRequest, component_id: str, *, remember: bool) -> tuple[bool, str | None]:
    target = next((candidate for candidate in choice.candidates if candidate.component_id == component_id), None)
    if target is None:
        return False, "The selected application is no longer available."
    ok, error = _launch(target, choice.path)
    if ok and remember:
        config = load_config()
        preferences = config.get("extension_preferences")
        if not isinstance(preferences, dict):
            preferences = {}
            config["extension_preferences"] = preferences
        preferences[choice.extension] = target.component_id
        if not save_config(config):
            return True, "The application launched, but Suite Pythoine could not save the routing preference."
    return ok, error


def dispatch_paths_silently(paths: Iterable[str | Path], launcher_file: str | Path | None = None) -> DispatchResult:
    del launcher_file  # retained for compatibility with older callers
    config = load_config()
    targets, _root, _cached = load_routing_targets(config)
    preferences = config.get("extension_preferences", {})
    if not isinstance(preferences, dict):
        preferences = {}

    launched: list[Path] = []
    unresolved: list[Path] = []
    choices: list[ChoiceRequest] = []
    inspector_choices: list[InspectorFallbackRequest] = []
    errors: list[str] = []

    for raw in paths:
        path = Path(raw).expanduser().resolve(strict=False)
        if not path.is_file() or path.suffix.casefold() in {".zip", ".appimage"}:
            unresolved.append(path)
            continue
        extension = path.suffix.casefold()
        candidates = document_candidates(targets, extension)
        if not candidates:
            launched_fallback, fallback_choice, fallback_error = _dispatch_inspector_fallback(path, targets, config)
            if launched_fallback:
                launched.append(path)
            elif fallback_choice is not None:
                inspector_choices.append(fallback_choice)
            else:
                unresolved.append(path)
                if fallback_error:
                    errors.append(fallback_error)
            continue
        preference = preferences.get(extension)
        preferred = None if preference == ASK_EVERY_TIME else next(
            (candidate for candidate in candidates if candidate.component_id == preference), None
        )
        if preferred is not None:
            chosen = preferred
        elif len(candidates) == 1:
            chosen = candidates[0]
        else:
            choices.append(ChoiceRequest(path, extension, tuple(candidates)))
            continue
        ok, error = _launch(chosen, path)
        if ok:
            launched.append(path)
        else:
            unresolved.append(path)
            if error:
                errors.append(error)

    return DispatchResult(tuple(launched), tuple(unresolved), tuple(choices), tuple(inspector_choices), tuple(errors))


def diagnose_routing(path_value: str | Path) -> str:
    config = load_config()
    targets, root, cached = load_routing_targets(config)
    path = Path(path_value).expanduser().resolve(strict=False)
    extension = path.suffix.casefold()
    candidates = document_candidates(targets, extension)
    preferences = config.get("extension_preferences", {})
    preference = preferences.get(extension) if isinstance(preferences, dict) else None
    lines = [
        f"File: {path}",
        f"Extension: {extension or '<none>'}",
        f"Components root: {root}",
        f"Routing inventory: {'cached' if cached else 'discovered'}",
        "",
        "Known components:",
    ]
    for target in targets:
        lines.append(
            f"  - {target.component_id}: {target.name} [{target.kind}] "
            f"runtime={target.launch_mode} active={target.active_version or 'Unknown'}"
        )
    lines.extend(["", "Eligible document applications:"])
    if candidates:
        for target in candidates:
            available = []
            if target.portable_command:
                available.append("Portable")
            if target.installed_command:
                available.append("AppImage")
            lines.append(f"  - {target.component_id}: {target.name} ({' + '.join(available) or 'Unavailable'})")
    else:
        lines.append("  (none)")
    lines.extend(["", f"Stored routing preference: {preference or 'Automatic'}"])
    fallback_candidates = inspector_fallback_targets(targets) if not candidates else []
    fallback_preference = str(config.get("inspector_fallback_preference") or INSPECTOR_FALLBACK_ASK)
    if not candidates and fallback_candidates:
        lines.append("Inspection fallback candidates: " + ", ".join(item.name for item in fallback_candidates))
        lines.append(f"Stored inspection fallback: {fallback_preference}")
    if not candidates and fallback_candidates:
        preferred_fallback = next((item for item in fallback_candidates if item.component_id == fallback_preference), None)
        if preferred_fallback is not None or len(fallback_candidates) == 1:
            target = preferred_fallback or fallback_candidates[0]
            decision = f"INSPECTION FALLBACK → {target.component_id}"
        else:
            decision = "INSPECTION FALLBACK CHOOSER"
    elif not candidates:
        decision = "FULL HUB FALLBACK"
    elif preference not in {None, ASK_EVERY_TIME} and any(item.component_id == preference for item in candidates):
        decision = f"SILENT → {preference}"
    elif len(candidates) == 1:
        decision = f"SILENT → {candidates[0].component_id}"
    else:
        decision = "TINY CHOOSER"
    lines.append(f"Decision: {decision}")
    return "\n".join(lines)
