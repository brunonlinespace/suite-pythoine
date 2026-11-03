from __future__ import annotations

import os
from pathlib import Path


def _human_size(value: int) -> str:
    size = float(max(0, value))
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024.0 or unit == "TiB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{int(value)} B"


def _tree_size(path: Path | None) -> int:
    if path is None:
        return 0
    target = path.expanduser().resolve(strict=False)
    try:
        if target.is_file() and not target.is_symlink():
            return target.stat().st_size
    except OSError:
        return 0
    total = 0
    if not target.is_dir():
        return 0
    for root, dirs, files in os.walk(target, followlinks=False):
        root_path = Path(root)
        dirs[:] = [name for name in dirs if not (root_path / name).is_symlink()]
        for name in files:
            candidate = root_path / name
            try:
                if not candidate.is_symlink():
                    total += candidate.stat().st_size
            except OSError:
                continue
    return total


def _install_timestamp(paths: list[Path]) -> float:
    stamps: list[float] = []
    for path in paths:
        try:
            # Version/runtime container mtime best approximates when Suite created
            # the managed installation. Linux does not expose a portable birthtime.
            target = path.parent if path.is_file() else path
            stamps.append(target.stat().st_mtime)
        except OSError:
            continue
    return min(stamps) if stamps else 0.0


def _format_timestamp(value: float) -> str:
    if not value:
        return "Unknown"
    try:
        from datetime import datetime
        return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M")
    except (OSError, OverflowError, ValueError):
        return "Unknown"
