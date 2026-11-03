"""0.12.3 Store backend installation completion hotfix regressions (Qt-free)."""
from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent


class _DummyQtObject:
    def __init__(self, *args, **kwargs):
        pass

    def __call__(self, *args, **kwargs):
        return _DummyQtObject()

    def __getattr__(self, name):
        return _DummyQtObject()

    def __iter__(self):
        return iter(())

    def __bool__(self):
        return False

    def __or__(self, other):
        return 0

    def __ror__(self, other):
        return 0


class _DummyQtModule(types.ModuleType):
    def __getattr__(self, name):
        if name == "pyqtSignal":
            return lambda *args, **kwargs: _DummyQtObject()
        return _DummyQtObject


def _import_install_wizard_without_qt():
    existing = {name: sys.modules.get(name) for name in ("PyQt6", "PyQt6.QtCore", "PyQt6.QtGui", "PyQt6.QtWidgets")}
    package = types.ModuleType("PyQt6")
    package.__path__ = []
    sys.modules["PyQt6"] = package
    for suffix in ("QtCore", "QtGui", "QtWidgets"):
        module = _DummyQtModule(f"PyQt6.{suffix}")
        sys.modules[f"PyQt6.{suffix}"] = module
        setattr(package, suffix, module)
    try:
        sys.modules.pop("suite_pythoine.install_wizard", None)
        module = importlib.import_module("suite_pythoine.install_wizard")
    finally:
        for name, previous in existing.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous
    return module


class _Config:
    def __init__(self):
        self.data = {}

    def as_dict(self):
        return self.data


class _Options:
    backend_only = True
    make_active_after_install = True
    incoming_version = "0.0.4"


class _Editor:
    editor_id = "store-pythoine"
    source_version = "0.0.4"


def run_regressions(errors: list[str]) -> None:
    prefix = "0.12.3 Store backend install hotfix: "

    def check(condition: bool, message: str) -> None:
        if not condition:
            errors.append(prefix + message)

    source = (PACKAGE / "install_wizard.py").read_text(encoding="utf-8")
    check("set_active_version, set_desktop_version" in source,
          "ZIP installer still does not import set_active_version")
    check("except Exception as exc:" in source and "INTERNAL INSTALLER ERROR" in source
          and "traceback.format_exception" in source,
          "unexpected ZIP-installer exceptions are not surfaced in Technical details")

    try:
        wizard = _import_install_wizard_without_qt()
        progress = object.__new__(wizard.ProgressPage)
        progress.editor = _Editor()
        progress.options = _Options()
        progress.config = _Config()
        steps: list[tuple[str, str, str | None]] = []
        progress._set_step = lambda key, state, detail=None: steps.append((key, state, detail))

        # Execute the exact backend-only activation path that previously raised
        # NameError, then execute it again to cover a retry after a partial install.
        first = wizard.ProgressPage._synchronize_active_desktop(progress)
        second = wizard.ProgressPage._synchronize_active_desktop(progress)
        active = progress.config.data.get("editor_overrides", {}).get("store-pythoine", {}).get("active_version")
        check(first is None and second is None, "backend-only desktop synchronization unexpectedly returned a launcher")
        check(active == "0.0.4", "Store active version was not recorded by the real backend-only installer path")
        check(steps == [
            ("desktop", "skip", "Suite-integrated backend; no standalone launcher"),
            ("desktop", "skip", "Suite-integrated backend; no standalone launcher"),
        ], "backend-only Store retry changed desktop-step behavior")
    except Exception as exc:
        errors.append(prefix + f"real backend-only installer path raised {type(exc).__name__}: {exc}")

    print("PASS: 0.12.3 Store backend installation completion regressions"
          if not any(error.startswith(prefix) for error in errors)
          else "CHECK: 0.12.3 Store backend installation completion regressions")


if __name__ == "__main__":
    failures: list[str] = []
    run_regressions(failures)
    if failures:
        for failure in failures:
            print("FAIL:", failure)
        raise SystemExit(1)
    print("PASS: 0.12.3 Store backend installation completion regressions")
