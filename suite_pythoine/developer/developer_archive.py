"""Developer Mode's explicit, non-installing managed source-ZIP retention path.

This is not Developer Intake's extracted-source workspace, nor the production
installer. It reuses the exact-version Recovery format so the existing inventory,
Restore Portable and Purge workflows can handle a retained-only asset unchanged.
No installation registry/active version, routing, desktop entry or runtime is written.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil

from ..install_inspection import ZipEditorInspection
from ..installer import InstallError, sha256_file
from ..recovery import retain_recovery_archive, validate_recovery_archive
from ..storage_layout import (
    application_folder_name, is_within, prune_empty_parents, recovery_root,
    version_folder_name,
)


@dataclass(frozen=True, slots=True)
class RetainedDeveloperArchive:
    archive: Path
    metadata: Path
    already_retained: bool


def exact_source_version(inspection: ZipEditorInspection) -> str:
    version = str(inspection.version or inspection.builder_version or "").strip()
    if not version or version.casefold() == "unknown":
        raise InstallError(
            "This source ZIP has no verifiable exact version. Declare a source "
            "version before retaining it in managed Recovery."
        )
    return version


def retain_developer_source_zip(
    inspection: ZipEditorInspection, editors_root: Path,
) -> RetainedDeveloperArchive:
    """Keep an inspected, catalogue-recognised ZIP, without installing anything.

    A complete pre-existing Recovery must match identity, version and checksum;
    identical requests are no-ops and different content is never overwritten.
    Retention itself rechecks the inspection hash before and after copying.
    """
    if not inspection.editor_id or not inspection.name:
        raise InstallError("Source ZIP has no recognised trusted application identity.")
    source = inspection.zip_path.expanduser().resolve(strict=False)
    version = exact_source_version(inspection)
    root_input = editors_root.expanduser()
    if root_input.is_symlink():
        raise InstallError("Managed Applications root must not be a symbolic link.")
    root = root_input.resolve(strict=False)
    application = root / application_folder_name(inspection.name)
    version_folder = application / version_folder_name(version)
    target = recovery_root(root, inspection.name, version)
    if not is_within(target, root) or target == root:
        raise InstallError("Managed Recovery destination escapes the Applications root.")
    if any(path.is_symlink() for path in (application, version_folder, target)):
        raise InstallError("Refusing a symbolic-link component/version/Recovery destination.")
    if any(path.exists() and not path.is_dir() for path in (application, version_folder)):
        raise InstallError("A component/version path is not a directory.")

    if target.exists():
        # Fail closed on incomplete, corrupt, mismatched, or altered metadata;
        # this operation must not silently replace a user's existing Recovery.
        info, _ = validate_recovery_archive(
            target, expected_editor_id=inspection.editor_id, expected_version=version,
        )
        if info.name != inspection.name:
            raise InstallError("Existing Recovery uses a different component display identity.")
        if info.sha256 != inspection.archive_sha256.casefold():
            raise InstallError(
                "A different ZIP is already retained for this exact version. "
                "No existing Recovery was replaced."
            )
        # The caller's source might have changed after inspection even for an
        # idempotent request. The actual copier handles the non-idempotent case.
        if sha256_file(source).casefold() != info.sha256:
            raise InstallError("The selected source ZIP changed after inspection.")
        return RetainedDeveloperArchive(info.archive_path, info.metadata_path, True)

    try:
        archive, metadata = retain_recovery_archive(
            source, target, expected_sha256=inspection.archive_sha256,
            editor_id=inspection.editor_id, name=inspection.name, version=version,
        )
        # Prove that the standard Restore workflow can still identify this ZIP
        # *after* it has been stored as original-source.zip. A filename-only
        # version inference can otherwise disappear on retention.
        try:
            validate_recovery_archive(
                target, expected_editor_id=inspection.editor_id, expected_version=version,
            )
        except Exception as exc:
            shutil.rmtree(target)
            raise InstallError(
                "The ZIP does not retain a verifiable exact version after storage. "
                "Declare the version in its source manifest or code. No archive was adopted."
            ) from exc
    except Exception:
        # Clean only newly created, EMPTY version/application containers. Never
        # remove an existing Portable, AppImage or other managed Recovery content.
        prune_empty_parents(version_folder, root)
        raise
    return RetainedDeveloperArchive(archive, metadata, False)
