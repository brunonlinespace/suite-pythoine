"""Ephemeral exact-archive retention for Developer Intake.

This private vault exists only to keep a byte-identical validated source ZIP
available for the rest of one Developer Intake session when the user chooses to
delete the visible development ZIP.  It is not Recovery storage and is never
discovered as an installed or managed asset.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import time

VAULT_SCHEMA = 1
VAULT_MARKER = ".suite-pythoine-developer-intake-vault.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def vault_base() -> Path:
    """Return Suite's private runtime-temp root for Developer Intake vaults."""
    runtime = os.environ.get("XDG_RUNTIME_DIR", "").strip()
    if runtime:
        base = Path(runtime).expanduser().resolve(strict=False) / "suite-pythoine" / "developer-intake"
    else:
        uid = str(os.getuid()) if hasattr(os, "getuid") else "user"
        base = Path(tempfile.gettempdir()).resolve(strict=False) / f"suite-pythoine-{uid}" / "developer-intake"
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        base.chmod(0o700)
    except OSError:
        pass
    return base


def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def cleanup_stale_intake_vaults(base: Path | None = None) -> int:
    """Remove only marked abandoned Suite vaults; never touch live sessions."""
    root = (base or vault_base()).expanduser().resolve(strict=False)
    if not root.is_dir():
        return 0
    removed = 0
    for candidate in root.iterdir():
        if not candidate.is_dir():
            continue
        marker = candidate / VAULT_MARKER
        if not marker.is_file():
            continue
        try:
            payload = json.loads(marker.read_text(encoding="utf-8"))
            pid = int(payload.get("pid", 0))
            schema = int(payload.get("schema", 0))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
        if schema != VAULT_SCHEMA or _process_alive(pid):
            continue
        try:
            shutil.rmtree(candidate)
            removed += 1
        except OSError:
            pass
    return removed


class DeveloperIntakeSessionVault:
    """Own one private exact ZIP copy for the lifetime of one Intake dialog."""

    def __init__(self, *, base: Path | None = None) -> None:
        self._base = base.expanduser().resolve(strict=False) if base is not None else None
        self._directory: Path | None = None
        self._archive: Path | None = None
        self._sha256: str | None = None

    @property
    def archive_path(self) -> Path | None:
        path = self._archive
        return path if path is not None and path.is_file() else None

    @property
    def digest(self) -> str | None:
        return self._sha256

    def stage_exact_copy(self, source: Path) -> Path:
        """Create and SHA-256 verify a private byte-identical copy of source."""
        source = source.expanduser().resolve(strict=True)
        if not source.is_file():
            raise OSError(f"Developer Intake session source is not a file: {source}")
        self.cleanup()
        base = self._base or vault_base()
        base.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory = Path(tempfile.mkdtemp(prefix=f"{os.getpid()}-", dir=base))
        try:
            directory.chmod(0o700)
        except OSError:
            pass
        self._directory = directory
        marker = directory / VAULT_MARKER
        source_digest = _sha256(source)
        marker.write_text(json.dumps({
            "schema": VAULT_SCHEMA,
            "pid": os.getpid(),
            "created_at": time.time(),
            "source_name": source.name,
            "sha256": source_digest,
            "complete": False,
        }, sort_keys=True), encoding="utf-8")
        target = directory / source.name
        try:
            shutil.copy2(source, target)
            copied_digest = _sha256(target)
            if copied_digest != source_digest:
                raise OSError("Developer Intake temporary ZIP verification failed after copy.")
            marker.write_text(json.dumps({
                "schema": VAULT_SCHEMA,
                "pid": os.getpid(),
                "created_at": time.time(),
                "source_name": source.name,
                "sha256": copied_digest,
                "complete": True,
            }, sort_keys=True), encoding="utf-8")
            self._archive = target
            self._sha256 = copied_digest
            return target
        except Exception:
            self.cleanup()
            raise

    def cleanup(self) -> None:
        directory = self._directory
        self._archive = None
        self._sha256 = None
        self._directory = None
        if directory is not None and directory.exists():
            shutil.rmtree(directory, ignore_errors=True)
