"""Stage only SHA-256-verified release files for an isolated AppImage build.

Builder output (build/, dist/, venvs, Python caches) must never become input to
release QA, its recursive compilation, or PyInstaller. This is distinct from
weakening the strict SOURCE_MANIFEST release check.
"""
from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
import shutil
import sys


def stage_verified_source(source_root: Path, destination: Path) -> int:
    source_root = source_root.absolute()
    destination = destination.absolute()
    if destination == source_root or source_root in destination.parents:
        raise ValueError('Verified source snapshot must be outside the source tree')
    if destination.is_symlink() or (destination.exists() and (
            not destination.is_dir() or any(destination.iterdir()))):
        raise ValueError(f'Snapshot destination must be an empty directory: {destination}')
    manifest = source_root / 'suite_pythoine' / 'SOURCE_MANIFEST.sha256'
    if not manifest.is_file() or manifest.is_symlink():
        raise ValueError('Missing or unsafe source release manifest')
    entries: list[tuple[Path, Path]] = []
    seen: set[str] = set()
    for line in manifest.read_text(encoding='ascii').splitlines():
        if not line.strip():
            continue
        digest, separator, relative = line.partition('  ')
        rel = PurePosixPath(relative)
        if (not separator or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest)
                or rel.is_absolute() or any(part in ('', '.', '..') for part in rel.parts)
                or relative in seen or relative == 'suite_pythoine/SOURCE_MANIFEST.sha256'):
            raise ValueError(f'Invalid SOURCE_MANIFEST entry: {line[:100]}')
        seen.add(relative)
        source = source_root.joinpath(*rel.parts)
        if not source.is_file() or any(part.is_symlink() for part in (source, *source.parents) if part != source_root and source_root in part.parents):
            raise ValueError(f'Missing or symlinked release file: {relative}')
        if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
            raise ValueError(f'Source SHA-256 mismatch: {relative}')
        entries.append((source, destination.joinpath(*rel.parts)))
    if not entries or 'main.py' not in seen:
        raise ValueError('Source release manifest is empty or lacks main.py')
    destination.mkdir(parents=True, exist_ok=True)
    for source, target in entries:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    target_manifest = destination / 'suite_pythoine' / 'SOURCE_MANIFEST.sha256'
    shutil.copy2(manifest, target_manifest)
    return len(entries)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print('Usage: python -m suite_pythoine.tools.build_source SOURCE_ROOT DESTINATION', file=sys.stderr)
        return 2
    try:
        count = stage_verified_source(Path(args[0]), Path(args[1]))
    except (ValueError, OSError) as exc:
        print(f'Verified source staging failed: {exc}', file=sys.stderr)
        return 1
    print(f'Verified source snapshot staged ({count} authored files).')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
