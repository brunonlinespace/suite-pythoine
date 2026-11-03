"""Suite Pythoine 0.9.1: independent, stdlib-only post-exit uninstall helper.

This file is copied to a private temporary directory BEFORE Hub exits. The
worker is intentionally executable without importing PyQt or installed Hub code.
There is no permanent installation registry and no use of elevated privileges.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone

ALLOWED_RUNTIME_NAMES = frozenset({'Portable', 'AppImage', 'Recovery'})


class UnsafePlan(ValueError):
    pass


def _stat_identity(path: Path) -> list[int]:
    stat = path.lstat()
    return [stat.st_dev, stat.st_ino]


def _no_link_path(path: Path) -> bool:
    """Disallow symlink traversal, including parent directories."""
    return all(not node.is_symlink() for node in (path, *path.parents) if node.exists() or node.is_symlink())


def _signature(path: Path, kind: str) -> dict:
    if not path.is_absolute() or not _no_link_path(path):
        raise UnsafePlan(f'Unsafe or linked path: {path}')
    if kind in ('version', 'component-preferences'):
        if not path.is_dir():
            raise UnsafePlan(f'Expected directory: {path}')
    elif not path.is_file():
        raise UnsafePlan(f'Expected regular file: {path}')
    out = {'kind': kind, 'path': str(path), 'identity': _stat_identity(path)}
    if kind in ('desktop', 'hub-preferences', 'bridge', 'mimeapps'):
        out['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def _same_signature(target: dict) -> Path:
    path = Path(target['path'])
    if not path.is_absolute() or not _no_link_path(path) or _stat_identity(path) != target['identity']:
        raise UnsafePlan(f'Changed or unsafe removal target: {path}')
    kind = target['kind']
    if kind in ('version', 'component-preferences'):
        if not path.is_dir():
            raise UnsafePlan(f'Directory no longer available: {path}')
    elif not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != target['sha256']:
        raise UnsafePlan(f'File changed after review: {path}')
    return path


def validate_plan(plan: dict) -> list[tuple[dict, Path]]:
    """Preflight the ENTIRE plan before renaming or removing one file."""
    if plan.get('schema') != 1 or plan.get('mode') not in ('hub', 'selective', 'full'):
        raise UnsafePlan('Unrecognised uninstall plan')
    root = Path(plan['root'])
    if not root.is_absolute() or root == Path.home() or not root.is_dir() or not _no_link_path(root):
        raise UnsafePlan('Invalid managed Applications folder')
    if _stat_identity(root) != plan['root_identity']:
        raise UnsafePlan('Managed Applications folder changed after review')
    if sorted(child.name for child in root.iterdir()) != plan.get('root_entries'):
        raise UnsafePlan('Managed Applications inventory changed after review; restart the wizard')
    if 'suite-pythoine' not in plan.get('selected_ids', ()):
        raise UnsafePlan('Hub must always be explicitly included')
    if len(plan['selected_ids']) != len(set(plan['selected_ids'])):
        raise UnsafePlan('Duplicate selected component')
    if plan['mode'] == 'hub' and plan['selected_ids'] != ['suite-pythoine']:
        raise UnsafePlan('Hub Only cannot delete other applications')
    if plan['mode'] == 'selective' and plan['selected_ids'][0] != 'suite-pythoine':
        raise UnsafePlan('Selective removal must include Hub')
    targets = plan.get('targets')
    if not isinstance(targets, list):
        raise UnsafePlan('Missing removal target list')
    selected = set(plan['selected_ids'])
    desktop_dir = Path(plan['desktop_dir'])
    config_dir = Path(plan['config_dir'])
    bridge_dir = Path(plan['bridge_dir'])
    component_config_base = Path(plan['component_config_base'])
    for parent in (desktop_dir, config_dir, component_config_base, bridge_dir):
        if not parent.is_absolute() or not _no_link_path(parent):
            raise UnsafePlan(f'Unsafe boundary: {parent}')
    seen: set[Path] = set()
    checked = []
    for target in targets:
        path = _same_signature(target)
        kind = target['kind']
        if path in seen:
            raise UnsafePlan(f'Duplicate removal target: {path}')
        seen.add(path)
        if kind == 'version':
            if (target.get('component_id') not in selected or path.parent.parent != root
                    or path.name != target.get('version') or not path.parent.is_dir()
                    or path.parent.is_symlink() or not path.name or path.name.startswith('.')):
                raise UnsafePlan(f'Unverified exact managed version: {path}')
            children = {part.name for part in path.iterdir()}
            if not children or not children <= ALLOWED_RUNTIME_NAMES or any(part.is_symlink() for part in path.iterdir()):
                raise UnsafePlan(f'Unexpected assets in version root (excluded, not guessed): {path}')
        elif kind == 'desktop':
            if (target.get('component_id') not in selected or path.parent != desktop_dir
                    or path.name != f'io.github.brunonlinespace.{target["component_id"]}.desktop'):
                raise UnsafePlan(f'Unrecognised desktop entry: {path}')
        elif kind == 'component-preferences':
            if (not plan.get('remove_component_preferences') or target.get('component_id') not in selected
                    or target.get('component_id') == 'suite-pythoine' or path.parent != component_config_base):
                raise UnsafePlan(f'Preferences are not selected or are outside boundary: {path}')
        elif kind == 'hub-preferences':
            if (not plan.get('remove_hub_preferences') or path.parent != config_dir
                    or path.name not in ('suite-pythoine.json','developer-intake.json','developer-components.json')):
                raise UnsafePlan(f'Unrecognised Hub preferences: {path}')
        elif kind == 'bridge':
            if path.parent != bridge_dir or path.name != 'suite-pythoine':
                raise UnsafePlan(f'Unrecognised Hub control bridge: {path}')
        else:
            raise UnsafePlan(f'Unknown target type: {kind}')
        checked.append((target, path))
    mime = plan.get('mimeapps')
    if mime is not None:
        if not isinstance(mime, dict) or mime.get('kind') != 'mimeapps':
            raise UnsafePlan('Unexpected MIME association update')
        mime_path = _same_signature(mime)
        if mime_path != component_config_base.parent / 'mimeapps.list':
            raise UnsafePlan('MIME associations are outside the XDG configuration boundary')
    if not any(t['kind'] == 'version' and t['component_id'] == 'suite-pythoine' for t,_ in checked):
        raise UnsafePlan('No validated managed Hub version was found; unmanaged copies need manual removal')
    # A newly created or unrecognised version must not make an alleged full
    # component purge silently partial. Never infer ownership from its name.
    for folder in {path.parent for t, path in checked if t['kind'] == 'version'}:
        planned = {path for t, path in checked if t['kind'] == 'version' and path.parent == folder}
        present = set(folder.iterdir())
        if present != planned:
            raise UnsafePlan(f'Unreviewed application-folder contents; inspect before uninstall: {folder}: {present - planned}')
    return checked


def _running_selected_processes(checked: list[tuple[dict, Path]]) -> list[str]:
    """Best-effort Linux process guard; never signal/kill a managed app."""
    if not sys.platform.startswith('linux'):
        return []
    proc = Path('/proc')
    if not proc.is_dir():
        raise UnsafePlan('Cannot check running applications: /proc is unavailable')
    folders = [path for target, path in checked if target['kind'] == 'version']
    blocked: list[str] = []
    for process in proc.iterdir():
        if not process.name.isdecimal() or int(process.name) == os.getpid():
            continue
        try:
            if process.stat().st_uid != os.getuid():
                continue
            command = (process / 'cmdline').read_bytes()[:4*1024*1024].split(b'\0')
            arguments = [os.fsdecode(arg) for arg in command if arg]
            # AppImage runtime paths are also published by the APPIMAGE env var.
            environment = (process / 'environ').read_bytes()[:4*1024*1024].split(b'\0')
            arguments += [os.fsdecode(arg[9:]) for arg in environment if arg.startswith(b'APPIMAGE=')]
            executable = (process / 'exe').resolve(strict=False)
            candidates = [executable] + [Path(value).resolve(strict=False) for value in arguments if Path(value).is_absolute()]
            if any(candidate == folder or folder in candidate.parents for candidate in candidates for folder in folders):
                blocked.append(process.name)
        except (OSError, PermissionError, ValueError):
            continue
    return blocked


def _atomic_save_preferences(path: Path, data: dict) -> None:
    tmp = path.with_name(f'.{path.name}.uninstall-{uuid.uuid4().hex}')
    try:
        with tmp.open('x', encoding='utf-8') as output:
            json.dump(data, output, indent=2, sort_keys=True)
            output.write('\n')
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _clear_removed_component_choices(plan: dict) -> None:
    """Retain Hub preferences by default, but discard choices for purged apps."""
    if plan.get('remove_hub_preferences') or not (set(plan['selected_ids']) - {'suite-pythoine'}):
        # Hub-only and zero-extra Selective must not even parse, let alone
        # rewrite, preferences the user elected to preserve.
        return
    config = Path(plan['config_file'])
    if not config.is_file() or config.is_symlink():
        return
    data = json.loads(config.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise UnsafePlan('Existing preferences are not a JSON object')
    gone = set(plan['selected_ids']) - {'suite-pythoine'}
    overrides = data.get('editor_overrides')
    if isinstance(overrides, dict):
        for name in gone:
            overrides.pop(name, None)
    associations = data.get('extension_preferences')
    if isinstance(associations, dict):
        for suffix, component in list(associations.items()):
            if component in gone:
                associations.pop(suffix, None)
    if data.get('last_selected_editor') in gone:
        data['last_selected_editor'] = None
    data['routing_index'] = {}
    data.pop('pending_self_cleanup', None)
    _atomic_save_preferences(config, data)



def _retire_mime_associations(plan: dict, result: list[str]) -> None:
    """Remove only reviewed Desktop IDs from existing XDG MIME association lists.

    Preserve unrelated IDs and all non-association sections; do not delete the
    user's mimeapps.list. Refuse overwrite if another process changed the file.
    """
    snapshot = plan.get('mimeapps')
    if snapshot is None:
        return
    path = _same_signature(snapshot)
    ids = {f'io.github.brunonlinespace.{name}.desktop' for name in plan['selected_ids']}
    original = path.read_text(encoding='utf-8')
    section = ''
    output: list[str] = []
    removed = False
    for line in original.splitlines(keepends=True):
        trimmed = line.strip()
        if trimmed.startswith('[') and trimmed.endswith(']'):
            section = trimmed[1:-1].strip()
        if section not in {'Default Applications', 'Added Associations', 'Removed Associations'} or '=' not in line or trimmed.startswith(('#', ';')):
            output.append(line)
            continue
        key, value = line.split('=', 1)
        ending = '\r\n' if value.endswith('\r\n') else '\n' if value.endswith('\n') else ''
        values = value.removesuffix(ending).split(';')
        keep = [item for item in values if item.strip() not in ids and item.strip()]
        if len(keep) == len([item for item in values if item.strip()]):
            output.append(line)
            continue
        removed = True
        if keep:
            output.append(key + '=' + ';'.join(keep) + ';' + ending)
        # If no alternate default/association remains, remove that key only.
    if not removed:
        return
    # Revalidate immediately before writing: no follow of a linked/replaced file.
    _same_signature(snapshot)
    target = path.with_name(f'.{path.name}.suite-uninstall-{uuid.uuid4().hex}')
    try:
        with target.open('x', encoding='utf-8', newline='') as stream:
            stream.write(''.join(output))
        target.chmod(path.stat().st_mode & 0o777)
        os.replace(target, path)
    finally:
        target.unlink(missing_ok=True)
    result.append('UPDATED: Selected Desktop IDs retired from ' + str(path))


def _refresh_desktop_cache(plan: dict, result: list[str]) -> None:
    if not any(target['kind'] == 'desktop' for target in plan['targets']):
        return
    executable = shutil.which('update-desktop-database')
    if not executable:
        result.append('NOTE: update-desktop-database unavailable; desktop files themselves were removed.')
        return
    try:
        operation = subprocess.run([executable, plan['desktop_dir']], stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8, check=False)
        if operation.returncode != 0:
            result.append('NOTE: Desktop cache refresh returned nonzero; desktop entries themselves were removed.')
    except (OSError, subprocess.TimeoutExpired) as error:
        result.append(f'NOTE: Desktop cache refresh unavailable: {error}')


def execute_plan(plan: dict) -> str:
    checked = validate_plan(plan)
    running = _running_selected_processes(checked)
    if running:
        raise UnsafePlan('Selected managed applications are still running (PIDs: ' + ', '.join(running) + '). Close them first; none will be killed.')
    stages: list[tuple[Path, Path, str]] = []
    deleting = False
    result = [f'Mode: {plan["mode"]}', f'Applications folder: {plan["root"]}',
              'Selected: ' + ', '.join(plan['selected_ids']),
              'Unexpected/unknown files are never removed by inference.']
    try:
        for target, original in checked:
            # Identical-boundary recheck just before staging prevents a changed target.
            _same_signature(target)
            stage = original.with_name(f'.{original.name}.suite-purge-{uuid.uuid4().hex}')
            if stage.exists() or stage.is_symlink():
                raise UnsafePlan(f'Staging target already occupied: {stage}')
            os.replace(original, stage)
            stages.append((original, stage, target['kind']))
        _clear_removed_component_choices(plan)
        deleting = True
        for original, stage, kind in stages:
            if kind in ('version', 'component-preferences'):
                shutil.rmtree(stage)
            else:
                stage.unlink()
            result.append(f'REMOVED: {original}')
        root = Path(plan['root'])
        for original, _, kind in stages:
            if kind != 'version':
                continue
            parent = original.parent
            if parent.is_dir() and not parent.is_symlink() and parent.parent == root and not any(parent.iterdir()):
                parent.rmdir()
        # Remove stale MIME preferences only for the exact selected Desktop IDs.
        # A failed unrelated update cannot widen deletion to another application.
        try:
            _retire_mime_associations(plan, result)
        except Exception as exc:
            result.append(f'NOTE: Could not safely update MIME associations: {exc}')
        _refresh_desktop_cache(plan, result)
        # Never rmtree the managed root, user config root, or parent data folders.
        result.append('SUCCESS: Every selected verified removal target was deleted.')
    except Exception as exc:
        result.append(f'INCOMPLETE: {type(exc).__name__}: {exc}')
        if not deleting:
            for original, stage, _kind in reversed(stages):
                try:
                    if original.exists() or original.is_symlink():
                        raise UnsafePlan(f'Cannot restore over existing path: {original}')
                    os.replace(stage, original)
                except OSError as rollback_error:
                    result.append(f'ROLLBACK FAILED: {stage}: {rollback_error}')
            result.append('Staged files restored where possible; no cleanup began.')
        else:
            for _, stage, _kind in stages:
                if stage.exists() or stage.is_symlink():
                    result.append(f'REMAINING STAGED ASSET (manual inspection): {stage}')
    return '\n'.join(result) + '\n'


def _notify(summary: str, body: str) -> None:
    executable = shutil.which('notify-send')
    if not executable:
        return
    try:
        subprocess.run([executable, summary, body], stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8, check=False)
    except (OSError, subprocess.TimeoutExpired):
        pass


def run_after_hub_exit(plan_path: Path, wait_fd: int) -> int:
    """Wait for the original process to exit; EOF works even across PID reuse."""
    with os.fdopen(wait_fd, 'rb', closefd=True) as pipe:
        while pipe.read(65536):
            pass
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    output = Path(plan['report_path'])
    try:
        report = execute_plan(plan)
    except Exception as exc:
        report = f'STOPPED BEFORE REMOVAL: {type(exc).__name__}: {exc}\n'
    try:
        output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        output.write_text(datetime.now(timezone.utc).isoformat() + '\n' + report, encoding='utf-8')
        output.chmod(0o600)
    except OSError:
        pass
    success = report.endswith('SUCCESS: Every selected verified removal target was deleted.\n')
    _notify(
        'Suite Pythoine uninstalled' if success else 'Suite Pythoine uninstall incomplete',
        ('The reviewed Suite removal completed successfully.' if success
         else f'The reviewed removal did not complete. Report: {output}'),
    )
    try:
        # Keep launch helper state in the private temp directory for postmortem
        # only when cleanup is incomplete; do not erase a failed plan/report.
        if success:
            plan_path.unlink(missing_ok=True)
            Path(__file__).unlink(missing_ok=True)
            plan_path.parent.rmdir()
    except OSError:
        pass
    return 0 if success else 1


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('Uninstall helper requires its reviewed plan and parent-exit pipe.')
    raise SystemExit(run_after_hub_exit(Path(sys.argv[1]), int(sys.argv[2])))
