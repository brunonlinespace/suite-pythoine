from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import uuid

from .install_inspection import ZipEditorInspection, inspect_editor_zip
from .installer import (
    InstallError,
    archive_editor_root_parts,
    extract_editor_zip_to_staging,
    sha256_file,
    validate_zip,
)
from .registry import EditorEntry, inspect_editor_root
from .storage_layout import is_within

RECOVERY_ARCHIVE_NAME = "original-source.zip"
RECOVERY_METADATA_NAME = "recovery.json"
RECOVERY_SCHEMA = 1


@dataclass(frozen=True, slots=True)
class RecoveryInfo:
    recovery_dir: Path
    archive_path: Path
    metadata_path: Path
    editor_id: str
    name: str
    version: str
    original_filename: str
    sha256: str
    retained_at: str


def recovery_available(recovery_dir: Path) -> bool:
    """Return structural Recovery availability without continuously re-hashing it."""
    candidate = recovery_dir.expanduser()
    if candidate.is_symlink() or not candidate.is_dir():
        return False
    return (candidate / RECOVERY_ARCHIVE_NAME).is_file() and (candidate / RECOVERY_METADATA_NAME).is_file()


def _load_recovery_info(recovery_dir: Path) -> RecoveryInfo:
    candidate = recovery_dir.expanduser()
    if candidate.is_symlink() or not candidate.is_dir():
        raise InstallError("No managed Recovery archive is available for this version.")
    recovery = candidate.resolve(strict=False)
    archive = recovery / RECOVERY_ARCHIVE_NAME
    metadata_path = recovery / RECOVERY_METADATA_NAME
    if not archive.is_file() or archive.is_symlink() or not metadata_path.is_file() or metadata_path.is_symlink():
        raise InstallError("The managed Recovery archive is incomplete or unsafe.")
    try:
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, TypeError) as exc:
        raise InstallError(f"Could not read Recovery metadata: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema") != RECOVERY_SCHEMA:
        raise InstallError("The Recovery metadata schema is unsupported or invalid.")
    editor_id = str(data.get("editor_id") or "").strip()
    name = str(data.get("name") or "").strip()
    version = str(data.get("version") or "").strip()
    original_filename = str(data.get("original_filename") or "").strip()
    sha256 = str(data.get("sha256") or "").strip().casefold()
    retained_at = str(data.get("retained_at") or "").strip()
    if not editor_id or not version or not original_filename:
        raise InstallError("Recovery metadata is missing component identity information.")
    if len(sha256) != 64 or any(ch not in "0123456789abcdef" for ch in sha256):
        raise InstallError("Recovery metadata contains an invalid SHA-256 value.")
    return RecoveryInfo(
        recovery_dir=recovery,
        archive_path=archive,
        metadata_path=metadata_path,
        editor_id=editor_id,
        name=name,
        version=version,
        original_filename=original_filename,
        sha256=sha256,
        retained_at=retained_at,
    )


def validate_recovery_archive(
    recovery_dir: Path,
    *,
    expected_editor_id: str,
    expected_version: str,
    python_executable: str | None = None,
    allow_checksum_mismatch: bool = False,
) -> tuple[RecoveryInfo, ZipEditorInspection]:
    """Validate one retained archive only when the user requests a restore."""
    info = _load_recovery_info(recovery_dir)
    if info.editor_id.casefold() != str(expected_editor_id).strip().casefold():
        raise InstallError(
            f"Recovery identity mismatch: expected {expected_editor_id}, metadata records {info.editor_id}."
        )
    if info.version.casefold() != str(expected_version).strip().casefold():
        raise InstallError(
            f"Recovery version mismatch: expected {expected_version}, metadata records {info.version}."
        )
    actual_sha = sha256_file(info.archive_path).casefold()
    if actual_sha != info.sha256 and not allow_checksum_mismatch:
        raise InstallError("The retained Recovery ZIP no longer matches its recorded SHA-256.")
    inspection = inspect_editor_zip(info.archive_path, python_executable=python_executable)
    inspected_version = inspection.version or inspection.builder_version or ""
    if inspection.editor_id.casefold() != info.editor_id.casefold():
        raise InstallError(
            f"Recovery archive identity mismatch: metadata records {info.editor_id}, archive identifies {inspection.editor_id}."
        )
    if inspected_version.casefold() != info.version.casefold():
        raise InstallError(
            f"Recovery archive version mismatch: metadata records {info.version}, archive identifies {inspected_version or 'Unknown'}."
        )
    if inspection.archive_sha256.casefold() != actual_sha:
        raise InstallError("Recovery archive changed DURING inspection; restoration was refused.")
    return info, inspection


def prepare_portable_restore_staging(
    recovery_dir: Path,
    portable_dir: Path,
    *,
    editors_root: Path,
    expected_editor_id: str,
    expected_version: str,
    config: dict | None = None,
    installed_dir: Path | None = None,
    python_executable: str | None = None,
    allow_checksum_mismatch: bool = False,
) -> tuple[Path, EditorEntry]:
    """Extract and verify a Recovery Portable without replacing its live target.

    Used by Hub self-restore so the currently executing Portable is never
    mutated in-process. The returned sibling staging directory is ready for a
    post-exit atomic handoff.
    """
    info, _inspection = validate_recovery_archive(
        recovery_dir,
        expected_editor_id=expected_editor_id,
        expected_version=expected_version,
        python_executable=python_executable,
        allow_checksum_mismatch=allow_checksum_mismatch,
    )
    root = editors_root.expanduser().resolve(strict=False)
    target_input = portable_dir.expanduser()
    if target_input.is_symlink():
        raise InstallError(f"Refusing to restore over a symbolic-link Portable folder: {target_input}")
    target = target_input.resolve(strict=False)
    if not is_within(target, root):
        raise InstallError("Refusing to restore Portable outside Suite Pythoine's managed Applications folder.")
    if target.exists() and not target.is_dir():
        raise InstallError(f"The Portable restore target is not a directory: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    staged = target.parent / f".{target.name}.self-restore-staging-{uuid.uuid4().hex[:10]}"
    try:
        members = validate_zip(info.archive_path)
        root_parts = archive_editor_root_parts(members)
        extract_editor_zip_to_staging(info.archive_path, staged, members=members, root_parts=root_parts)
        restored = inspect_editor_root(
            staged, config=config, installed_dir=installed_dir, python_executable=python_executable,
        )
        if restored.editor_id.casefold() != expected_editor_id.casefold():
            raise InstallError(
                f"Recovered Portable identity mismatch: expected {expected_editor_id}, got {restored.editor_id}."
            )
        restored_version = str(restored.source_version or "").strip()
        if restored_version.casefold() != expected_version.casefold():
            raise InstallError(
                f"Recovered Portable version mismatch: expected {expected_version}, got {restored_version or 'Unknown'}."
            )
        if not restored.portable_command:
            raise InstallError("The recovered source does not expose a launchable Portable command.")
        return staged, restored
    except Exception:
        if staged.exists():
            shutil.rmtree(staged, ignore_errors=True)
        raise


def restore_portable_from_recovery(
    recovery_dir: Path,
    portable_dir: Path,
    *,
    editors_root: Path,
    expected_editor_id: str,
    expected_version: str,
    config: dict | None = None,
    installed_dir: Path | None = None,
    python_executable: str | None = None,
    progress_callback=None,
    allow_checksum_mismatch: bool = False,
) -> tuple[Path, EditorEntry]:
    """Transactionally recreate/replace one exact Portable from managed Recovery."""
    def progress(stage: str, detail: str = "") -> None:
        if progress_callback is not None:
            progress_callback(stage, detail)

    progress("validate", "validating retained archive")
    info, _inspection = validate_recovery_archive(
        recovery_dir,
        expected_editor_id=expected_editor_id,
        expected_version=expected_version,
        python_executable=python_executable,
        allow_checksum_mismatch=allow_checksum_mismatch,
    )

    root = editors_root.expanduser().resolve(strict=False)
    target_input = portable_dir.expanduser()
    if target_input.is_symlink():
        raise InstallError(f"Refusing to restore over a symbolic-link Portable folder: {target_input}")
    target = target_input.resolve(strict=False)
    if not is_within(target, root):
        raise InstallError("Refusing to restore Portable outside Suite Pythoine's managed Applications folder.")
    if target.exists() and not target.is_dir():
        raise InstallError(f"The Portable restore target is not a directory: {target}")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise InstallError(f"Could not prepare the Portable version folder: {exc}") from exc

    token = uuid.uuid4().hex[:10]
    staged = target.parent / f".{target.name}.recovery-staging-{token}"
    backup = target.parent / f".{target.name}.recovery-backup-{token}"
    try:
        progress("extract", str(staged))
        members = validate_zip(info.archive_path)
        root_parts = archive_editor_root_parts(members)
        extract_editor_zip_to_staging(info.archive_path, staged, members=members, root_parts=root_parts)

        progress("verify", "verifying recovered Portable identity")
        restored = inspect_editor_root(
            staged,
            config=config,
            installed_dir=installed_dir,
            python_executable=python_executable,
        )
        if restored.editor_id.casefold() != expected_editor_id.casefold():
            raise InstallError(
                f"Recovered Portable identity mismatch: expected {expected_editor_id}, got {restored.editor_id}."
            )
        restored_version = str(restored.source_version or "").strip()
        if restored_version.casefold() != expected_version.casefold():
            raise InstallError(
                f"Recovered Portable version mismatch: expected {expected_version}, got {restored_version or 'Unknown'}."
            )
        if not restored.portable_command:
            raise InstallError("The recovered source does not expose a launchable Portable command.")

        progress("replace", str(target))
        if target.exists():
            os.replace(target, backup)
        os.replace(staged, target)
    except Exception:
        try:
            if target.exists() and backup.exists():
                shutil.rmtree(target, ignore_errors=True)
            if backup.exists() and not target.exists():
                os.replace(backup, target)
        finally:
            if staged.exists():
                shutil.rmtree(staged, ignore_errors=True)
        raise
    else:
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)

    progress("done", str(target))
    final = inspect_editor_root(
        target,
        config=config,
        installed_dir=installed_dir,
        python_executable=python_executable,
    )
    return target, final


def retain_recovery_archive(
    source_zip: Path,
    recovery_dir: Path,
    *,
    expected_sha256: str,
    editor_id: str,
    name: str,
    version: str,
) -> tuple[Path, Path]:
    """Atomically retain the exact validated source ZIP for one managed version.

    The archive payload is copied byte-for-byte and verified against the SHA-256
    calculated during pre-install inspection. Existing recovery data is replaced
    only after the complete new Recovery directory has been staged successfully.
    """
    source = source_zip.expanduser().resolve(strict=False)
    recovery_input = recovery_dir.expanduser()
    if recovery_input.is_symlink():
        raise InstallError(f"Refusing to use a symbolic-link Recovery folder: {recovery_input}")
    recovery = recovery_input.resolve(strict=False)
    if not source.is_file():
        raise InstallError(f"Recovery source archive is missing: {source}")

    expected = str(expected_sha256 or "").strip().casefold()
    if len(expected) != 64 or any(ch not in "0123456789abcdef" for ch in expected):
        raise InstallError("The validated source archive has no usable SHA-256 for Recovery retention.")
    source_hash = sha256_file(source).casefold()
    if source_hash != expected:
        raise InstallError("The source ZIP changed after inspection; Recovery retention was refused.")

    try:
        recovery.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise InstallError(f"Could not prepare the Recovery folder: {exc}") from exc

    token = uuid.uuid4().hex[:10]
    staged = recovery.parent / f".{recovery.name}.staging-{token}"
    backup = recovery.parent / f".{recovery.name}.backup-{token}"
    try:
        staged.mkdir(parents=False, exist_ok=False)
        staged_archive = staged / RECOVERY_ARCHIVE_NAME
        shutil.copyfile(source, staged_archive)
        copied_hash = sha256_file(staged_archive).casefold()
        if copied_hash != expected:
            raise InstallError("The retained Recovery archive failed SHA-256 verification.")

        metadata = {
            "schema": RECOVERY_SCHEMA,
            "editor_id": str(editor_id),
            "name": str(name),
            "version": str(version),
            "original_filename": source.name,
            "sha256": copied_hash,
            "retained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        (staged / RECOVERY_METADATA_NAME).write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        if recovery.exists():
            if not recovery.is_dir() or recovery.is_symlink():
                raise InstallError(f"Existing Recovery path is unsafe: {recovery}")
            os.replace(recovery, backup)
        os.replace(staged, recovery)
    except Exception:
        try:
            if recovery.exists() and backup.exists():
                shutil.rmtree(recovery, ignore_errors=True)
            if backup.exists() and not recovery.exists():
                os.replace(backup, recovery)
        finally:
            if staged.exists():
                shutil.rmtree(staged, ignore_errors=True)
        raise
    else:
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)

    return recovery / RECOVERY_ARCHIVE_NAME, recovery / RECOVERY_METADATA_NAME


def install_portable_with_recovery(
    source_zip: Path, portable_dir: Path, *, editors_root: Path,
    editor_id: str, name: str, version: str, expected_sha256: str,
    config: dict | None = None, installed_dir: Path | None = None,
    python_executable: str | None = None,
) -> tuple[Path, EditorEntry, Path, Path]:
    """Replace Portable AND original Recovery archive as one recoverable step.

    Both old assets are moved to private sibling backups. The validated ZIP is
    then imported, verified and retained. A failure in either half reinstates
    BOTH former assets; AppImage is never touched.
    """
    from .installer import import_zip
    from .storage_layout import validate_version_boundary
    base = editors_root.expanduser().resolve(strict=False)
    target = portable_dir.expanduser()
    if target.is_symlink() or target.name != 'Portable':
        raise InstallError('Unsafe Portable target for ZIP installation')
    target = target.resolve(strict=False)
    folder = target.parent
    if (not folder.is_relative_to(base) or folder.name != version
            or not folder.parent.parent.resolve(strict=False) == base):
        raise InstallError('Portable/Recovery target does not match the managed exact-version layout')
    validate_version_boundary(folder, base)
    rec = folder / 'Recovery'
    if target.exists() and not target.is_dir():
        raise InstallError('Portable path is not a directory')
    if rec.is_symlink() or (rec.exists() and not rec.is_dir()):
        raise InstallError('Recovery path is unsafe')
    source = source_zip.expanduser().resolve(strict=False)
    if sha256_file(source).casefold() != expected_sha256.casefold():
        raise InstallError('Source ZIP changed after validation')
    token = uuid.uuid4().hex[:12]
    old_p = folder / ('.Portable.reinstall-backup-' + token)
    old_r = folder / ('.Recovery.reinstall-backup-' + token)
    old_p_moved = old_r_moved = installed = retained = False
    folder.mkdir(parents=True, exist_ok=True)
    try:
        if target.exists():
            os.replace(target, old_p); old_p_moved = True
        if rec.exists():
            os.replace(rec, old_r); old_r_moved = True
        imported = import_zip(source, base, replace_existing=False, destination=target)
        installed = True
        checked = inspect_editor_root(imported, config=config, installed_dir=installed_dir,
                                      python_executable=python_executable)
        if (checked.editor_id != editor_id or str(checked.source_version or '').casefold() != version.casefold()
                or not checked.portable_command):
            raise InstallError('Installed Portable identity/version/entry point does not match the inspected archive')
        archive, metadata = retain_recovery_archive(source, rec,
            expected_sha256=expected_sha256, editor_id=editor_id, name=name, version=version)
        retained = True
    except Exception as original:
        recovery_failures: list[str] = []
        try:
            if installed and target.exists():
                shutil.rmtree(target)
            if retained and rec.exists():
                shutil.rmtree(rec)
            if old_p_moved and old_p.exists():
                os.replace(old_p, target)
            if old_r_moved and old_r.exists():
                os.replace(old_r, rec)
        except OSError as exc:
            recovery_failures.append(f'Rollback incomplete; inspect staged backups in {folder}: {exc}')
        if recovery_failures:
            raise InstallError(str(original) + '\n' + '\n'.join(recovery_failures)) from original
        raise
    else:
        # Failed backup cleanup does not invalidate an already completed install.
        for old in (old_p, old_r):
            if old.exists():
                shutil.rmtree(old, ignore_errors=True)
        return imported, checked, archive, metadata
