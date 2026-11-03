"""Restore x2.4 source views for pre-x2.5 historical byte comparisons."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT/'suite_pythoine/docs/WAVE2_X25_TRANSFER.json'

def old_relative(relative: str) -> str:
    moves = json.loads(LEDGER.read_text(encoding='utf-8'))['moves']
    return {value: key for key, value in moves.items()}.get(relative,relative)

def current_path(relative: str) -> Path:
    moves = json.loads(LEDGER.read_text(encoding='utf-8'))['moves']
    return ROOT/moves.get(relative,relative)

def source_x24(path: Path) -> str:
    data = json.loads(LEDGER.read_text(encoding='utf-8'))
    relative = path.relative_to(ROOT).as_posix()
    prior = old_relative(relative)
    text = path.read_text(encoding='utf-8')
    # x2.6 changes only the release identity; compare historical transfer against x2.5.
    if prior == 'suite_pythoine/__init__.py':
        text = text.replace('1.0.0-x2.6', '1.0.0-x2.5')
    for before, after in data['edits'].get(prior, []):
        assert text.count(after) >= 1, (relative,after)
        text = text.replace(after,before)
    return text
