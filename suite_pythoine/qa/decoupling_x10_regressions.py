"""1.0.0-x1.0 decoupling-baseline diagnostic regressions (Qt-free)."""
from __future__ import annotations

import ast
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "suite_pythoine"


def run_regressions(errors: list[str]) -> None:
    prefix = "1.0.0-x1.0 diagnostics baseline: "

    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(prefix + message)

    perf = PACKAGE / "perf_trace.py"
    require(perf.is_file(), "perf_trace.py missing")
    if perf.is_file():
        source = perf.read_text(encoding="utf-8")
        try:
            ast.parse(source)
        except SyntaxError as exc:
            errors.append(prefix + f"perf_trace syntax: {exc}")
        for token in (
            'SUITE_PYTHOINE_PERF', 'performance.jsonl',
            'def trace_operation(', 'def traced_duration(', 'def traced_operation(',
            'suite_version', 'except OSError:',
        ):
            require(token in source, f"missing tracer contract: {token}")
        require('os.environ.get("SUITE_PYTHOINE_PERF", "0")' in source,
                "tracing is not disabled by default")
        require('stream.write(payload)' in source, "trace append missing")

    app = (PACKAGE / "app.py").read_text(encoding="utf-8")
    registry = (PACKAGE / "registry.py").read_text(encoding="utf-8")
    dashboard = (PACKAGE / "ui/shell/dashboard.py").read_text(encoding="utf-8")
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    for token in (
        '@traced_operation("refresh_editors")',
        '@traced_operation("page_installed_applications")',
        '@traced_operation("page_application")',
        '@traced_operation("page_version_history")',
        '@traced_operation("page_catalogue")',
        '@traced_operation("zip_install_handoff")',
        '@traced_operation("appimage_install_handoff")',
        '@traced_operation("developer_mode_toggle")',
        'begin_operation("startup", start_perf=process_start_perf()',
    ):
        require(token in app, f"missing app diagnostic probe: {token}")
    require('@traced_operation("inventory_discovery")' in registry, "inventory operation probe missing")
    for token in ('bounded_files_visited', 'installed_command_candidates_examined', 'result_components', 'result_versions'):
        require(token in registry, f"missing inventory counter: {token}")
    require('dashboard_list_cards' in dashboard and 'dashboard_grid_cards' in dashboard,
            "Dashboard construction probes missing")
    require('from suite_pythoine.perf_trace import process_start_perf' in main,
            "process timer is not started before full app import")

    # Disabled tracing must perform no file I/O and report disabled even when imported.
    previous = os.environ.pop("SUITE_PYTHOINE_PERF", None)
    try:
        from suite_pythoine import perf_trace
        require(not perf_trace.enabled(), "tracing unexpectedly enabled by default")
    finally:
        if previous is not None:
            os.environ["SUITE_PYTHOINE_PERF"] = previous
