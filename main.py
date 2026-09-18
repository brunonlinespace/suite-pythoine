#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from suite_pythoine import APP_NAME, __version__
from suite_pythoine.store_bridge import ensure_control_bridge, handle_store_protocol_cli
from suite_pythoine.developer_policy import handle_developer_cli


def _existing_startup_paths(arguments: list[str]) -> list[Path]:
    return [
        Path(arg).expanduser().resolve(strict=False)
        for arg in arguments
        if not arg.startswith("-") and Path(arg).expanduser().exists()
    ]


def _diagnose_argument(arguments: list[str]) -> str | None:
    if "--diagnose-routing" not in arguments:
        return None
    index = arguments.index("--diagnose-routing")
    return arguments[index + 1] if index + 1 < len(arguments) else ""


if __name__ == "__main__":
    if "--version" in sys.argv:
        print(f"{APP_NAME} {__version__}")
        raise SystemExit(0)

    diagnose_target = _diagnose_argument(sys.argv[1:])
    if diagnose_target is not None:
        if not diagnose_target:
            print("Usage: main.py --diagnose-routing <file>", file=sys.stderr)
            raise SystemExit(2)
        from suite_pythoine.silent_dispatch import diagnose_routing
        print(diagnose_routing(diagnose_target))
        raise SystemExit(0)

    # Finish a deferred self-update only after the newly installed managed
    # Suite copy has successfully reached startup. This remains dependency-free
    # and executes before any PyQt import.
    from suite_pythoine.self_update import complete_pending_self_cleanup
    complete_pending_self_cleanup(__version__, __file__)

    developer_result = handle_developer_cli(sys.argv[1:])
    if developer_result is not None:
        raise SystemExit(developer_result)

    # Store Pythoine talks to Suite through a small, on-demand control protocol.
    # No Store daemon or background Suite process is involved. On Linux the
    # stable ~/.local/bin/suite-pythoine bridge follows Suite's direct active-
    # runtime desktop entry, so callers do not need to know Portable/AppImage.
    ensure_control_bridge()
    store_result = handle_store_protocol_cli(sys.argv[1:], launcher_file=__file__)
    if store_result is not None:
        raise SystemExit(store_result)

    force_show = "--show" in sys.argv
    if force_show:
        sys.argv = [arg for arg in sys.argv if arg != "--show"]

    smoke_test = "--suite-pythoine-smoke-test" in sys.argv
    startup_paths = _existing_startup_paths(sys.argv[1:])
    if startup_paths and not force_show and not smoke_test:
        from suite_pythoine.silent_dispatch import dispatch_paths_silently

        result = dispatch_paths_silently(startup_paths, __file__)
        for message in result.errors:
            print(message, file=sys.stderr)

        chooser_failed_paths: set[str] = set()
        if result.choices:
            # Ambiguity must stay pseudo-silent: import only the tiny chooser,
            # never the full Suite window, unless a requested launch genuinely
            # fails and needs the hub as a recovery surface.
            from suite_pythoine.routing_chooser import run_routing_choices
            if not run_routing_choices(result.choices):
                chooser_failed_paths.update(str(choice.path) for choice in result.choices)

        if result.inspector_choices:
            # Unsupported-file inspection is deliberately a post-routing stage:
            # normal trusted Editor/Reader candidates have already been proven
            # absent before this compact Beespector chooser can be reached.
            from suite_pythoine.routing_chooser import run_inspector_fallback_choices
            if not run_inspector_fallback_choices(result.inspector_choices):
                chooser_failed_paths.update(str(choice.path) for choice in result.inspector_choices)

        if not result.unresolved and not result.errors and not chooser_failed_paths:
            # All paths were launched, intentionally cancelled in the compact
            # chooser, or already handled. The full hub is not constructed.
            raise SystemExit(0)

        unresolved = {str(path) for path in result.unresolved} | chooser_failed_paths
        sys.argv = [
            sys.argv[0],
            *[
                arg for arg in sys.argv[1:]
                if not arg.startswith("-")
                and str(Path(arg).expanduser().resolve(strict=False)) in unresolved
            ],
        ]

    # Since 0.3.2-exp9-r2 the desktop entry follows the active Suite runtime directly.
    # A particular AppImage/Portable copy therefore remains authoritative when
    # it is launched explicitly; it must never redirect through shared state.

    from suite_pythoine.app import main
    raise SystemExit(main(__file__))
