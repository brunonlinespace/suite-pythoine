"""Independent stdlib-only post-exit worker for active Hub Portable Recovery."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid


class UnsafeRestore(ValueError):
    pass


def _identity(path: Path) -> list[int]:
    st = path.lstat()
    return [st.st_dev, st.st_ino]


def _no_links(path: Path) -> bool:
    return all(not node.is_symlink() for node in (path, *path.parents) if node.exists() or node.is_symlink())


def _validate(plan: dict) -> tuple[Path, Path]:
    if plan.get("schema") != 1:
        raise UnsafeRestore("Unrecognised self-restore plan")
    target = Path(plan["target"])
    staged = Path(plan["staged"])
    if not target.is_absolute() or not staged.is_absolute() or target.parent != staged.parent:
        raise UnsafeRestore("Restore paths are outside the reviewed exact-version folder")
    if target.name != "Portable" or not staged.name.startswith(".Portable.self-restore-staging-"):
        raise UnsafeRestore("Unexpected Portable restore path")
    if not staged.is_dir() or not _no_links(staged) or _identity(staged) != plan["staged_identity"]:
        raise UnsafeRestore("Prepared recovered Portable changed before handoff")
    target_expected = bool(plan.get("target_exists"))
    if target_expected:
        if not target.is_dir() or not _no_links(target) or _identity(target) != plan["target_identity"]:
            raise UnsafeRestore("Running Portable changed after review")
    elif target.exists() or target.is_symlink():
        raise UnsafeRestore("Portable target appeared after review")
    return target, staged


def _notify(summary: str, body: str) -> None:
    executable = shutil.which("notify-send")
    if not executable:
        return
    try:
        subprocess.run([executable, summary, body], stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=8, check=False)
    except (OSError, subprocess.TimeoutExpired):
        pass


def execute(plan: dict) -> str:
    target, staged = _validate(plan)
    backup = target.parent / f".Portable.self-restore-backup-{uuid.uuid4().hex[:10]}"
    moved_old = False
    try:
        if target.exists():
            os.replace(target, backup)
            moved_old = True
        os.replace(staged, target)
        main = target / "main.py"
        python = str(plan.get("python") or "")
        if not main.is_file() or not python or not Path(python).is_file():
            raise UnsafeRestore("Restored Hub cannot be relaunched with the reviewed Python runtime")
        if backup.exists():
            shutil.rmtree(backup)
        subprocess.Popen([python, str(main), "--show"], cwd=str(target),
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True)
        return f"SUCCESS: Suite Pythoine Portable restored to {target} and relaunch requested.\n"
    except Exception:
        try:
            if target.exists() and moved_old:
                shutil.rmtree(target, ignore_errors=True)
            if moved_old and backup.exists() and not target.exists():
                os.replace(backup, target)
        except OSError:
            pass
        raise


def run_after_hub_exit(plan_path: Path, wait_fd: int) -> int:
    with os.fdopen(wait_fd, "rb", closefd=True) as pipe:
        while pipe.read(65536):
            pass
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    report_path = Path(plan["report_path"])
    try:
        report = execute(plan)
        ok = report.startswith("SUCCESS:")
    except Exception as exc:
        report = f"FAILED: {type(exc).__name__}: {exc}\n"
        ok = False
    try:
        report_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        report_path.write_text(datetime.now(timezone.utc).isoformat() + "\n" + report, encoding="utf-8")
        report_path.chmod(0o600)
    except OSError:
        pass
    _notify("Suite Pythoine restored" if ok else "Suite Pythoine restore failed",
            ("Portable Recovery completed and Suite is reopening." if ok else
             f"Recovery did not complete. Report: {report_path}"))
    try:
        if ok:
            plan_path.unlink(missing_ok=True)
            Path(__file__).unlink(missing_ok=True)
            plan_path.parent.rmdir()
    except OSError:
        pass
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Self-restore worker requires its reviewed plan and parent-exit pipe.")
    raise SystemExit(run_after_hub_exit(Path(sys.argv[1]), int(sys.argv[2])))
