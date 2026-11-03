"""Read-only, Qt-free Wave-2 Python dependency and location-sensitivity inventory.

The graph describes statically resolvable imports only; runtime imports, C/C++
plugins and resource paths formed dynamically require manual review. This tool
never imports the analysed modules or modifies a source tree.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

EXCLUDED_PARTS = frozenset({'qa', 'tools', 'packaging', 'portable', 'docs', 'assets'})


def production_files(root: Path) -> list[Path]:
    root = root.resolve()
    package = root / 'suite_pythoine'
    if not (root / 'main.py').is_file() or not (package / '__init__.py').is_file():
        raise ValueError('Expected the Suite Pythoine source root (main.py and suite_pythoine/__init__.py)')
    return [root / 'main.py'] + sorted(
        file for file in package.rglob('*.py')
        if not EXCLUDED_PARTS.intersection(file.relative_to(package).parts)
    )


def _module_name(path: Path, root: Path) -> str:
    rel = path.relative_to(root).with_suffix('')
    return '.'.join(rel.parts[:-1] if rel.name == '__init__' else rel.parts)


def _static_imports(tree: ast.AST, module: str, modules: set[str]) -> list[str]:
    package = module if module in ('suite_pythoine',) else module.rpartition('.')[0]
    resolved: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            candidates = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                try:
                    base = importlib.util.resolve_name('.' * node.level + (node.module or ''), package)
                except ImportError:
                    continue
            else:
                base = node.module or ''
            candidates = [base] + [base + '.' + alias.name for alias in node.names]
        else:
            continue
        for candidate in candidates:
            if candidate in modules and candidate != module:
                resolved.add(candidate)
    return sorted(resolved)


def build_inventory(root: Path) -> dict:
    """Return a deterministic snapshot of authored, executable Python modules."""
    root = root.resolve()
    files = production_files(root)
    modules_by_path = {_module_name(path, root): path for path in files}
    available = set(modules_by_path)
    nodes: list[dict] = []
    importers: dict[str, list[str]] = {module: [] for module in available}
    for module, path in sorted(modules_by_path.items()):
        source = path.read_text(encoding='utf-8')
        tree = ast.parse(source, filename=str(path))
        dependencies = _static_imports(tree, module, available)
        for dependency in dependencies:
            importers[dependency].append(module)
        # These are *review cues*, not proof that a move will break the module.
        location_sensitive = any(isinstance(n, ast.Name) and n.id == '__file__'
                                 for n in ast.walk(tree))
        dynamic_import = any(isinstance(n, ast.Call) and (
            isinstance(n.func, ast.Name) and n.func.id == '__import__' or
            isinstance(n.func, ast.Attribute) and n.func.attr == 'import_module'
        ) for n in ast.walk(tree))
        nodes.append({
            'module': module,
            'path': path.relative_to(root).as_posix(),
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'imports': dependencies,
            'uses___file__': location_sensitive,
            'has_dynamic_import_call': dynamic_import,
        })
    for node in nodes:
        node['imported_by'] = sorted(importers[node['module']])
    return {
        'schema': 1,
        'basis': 'static Python AST, no module execution; dynamic/resource paths are not fully resolved',
        'modules': nodes,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2],
                        help='source root with main.py (default: current Suite source)')
    parser.add_argument('--output', type=Path, help='optional output path; otherwise print JSON')
    args = parser.parse_args(argv)
    try:
        payload = json.dumps(build_inventory(args.root), indent=2, ensure_ascii=False) + '\n'
        if args.output:
            args.output.write_text(payload, encoding='utf-8')
        else:
            sys.stdout.write(payload)
    except (OSError, SyntaxError, ValueError) as exc:
        print(f'Wave-2 dependency inventory failed: {exc}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
