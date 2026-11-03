"""1.0.0-x1.2 Preferences-dialog extraction regressions (Qt-free)."""
from __future__ import annotations
from suite_pythoine.qa.wave2_x22_regressions import preserved_sha256

import ast
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "suite_pythoine"

EXPECTED_AST = {
    "EditorPreferencesDialog": "7d8ab858db05bcbbae46c3a8d407180034db2e2091e1ddc2b364c231262474de",
    "GeneralPreferencesDialog": "0dca7baaf353bfdeb9ba83c023d6bab001f973b4c1ca9c9b97c1aca69fb3f6f7",
}
SUITEWINDOW_METHODS_SHA256 = "f47d2b64f7ebf86d8b9f0be2644a5e66dc482acf937184fdcc6f394d9991ae7a"

FROZEN_RUNTIME_SHA256 = {
    "install_wizard.py": "45d1e0f5d7212a927d118b81f1830ce83b5ba2189e2cc378357b25e407f04dad",
    "installer.py": "ac7b9e29f62c52ea41b9577c8bdc22cc4404a6e2182c1fe481d9d32ac304a0c0",
    "recovery.py": "ef6022441d845a8c489f1c798fedb2cca1787e17514bf59ce12a9da2f9cb7c5b",
    "purge_wizard.py": "f50e6204cbdaec6227e1d764dc33467c37e8526068afa1d45f78be883b571ce2",
    "asset_removal.py": "c09283c8c6171057e0b2cdcda963829fae848784745748c0bd995e17dc107329",
    "prune_policy.py": "91b0c15cbc9f456923aac99aa19bdca08457b7bc9088204d34ba0bd05597e8d2",
    "installation_state.py": "f43ca48b3230cab03f9036c90ea119c3d90d597674541cb4f1fd10835562dd33",
    "registry.py": "79ff12bc8601bf1ec153d12ee070e30d3fb1779d5de0acd7eb0e52b39035215d",
    "store/store_content.py": "0a5ae87deb49d05fa1216fa9eb695b460ebac058fa71ae99dcfdec421dd141ef",
    "catalogue/component_catalog.py": "25e866f18f775229dd142e5b7444f845a5e5c34854d62235c4a7864faa571398",
    "ui/shell/suite_theme.py": "880f77b11d4e8d02cc46400d4f95b7ba136f3009be80bf95b45b43c583b65e15",
    "ui/shell/sidebar_launcher.py": "19efdd2fde4073ac1646571455b8ac966b52bc8416aa6a0c426169e08b230d25",
}


def _definition_digest(path: Path, name: str) -> str:
    source = path.read_text(encoding="utf8")
    tree = ast.parse(source, filename=str(path))
    for node in tree.body:
        if getattr(node, "name", None) == name:
            return hashlib.sha256(ast.dump(node, include_attributes=False).encode("utf8")).hexdigest()
    return ""


def run_regressions(errors: list[str]) -> None:
    prefix = "1.0.0-x1.2 extraction: "

    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(prefix + message)

    app_path = PACKAGE / "app.py"
    app = app_path.read_text(encoding="utf8")
    preferences = PACKAGE / "ui" / "dialogs" / "preferences.py"
    init = PACKAGE / "ui" / "dialogs" / "__init__.py"
    require(preferences.is_file(), "missing extracted Preferences dialog module")
    require(init.is_file(), "missing ui.dialogs package initializer")
    require("from .ui.dialogs.preferences import EditorPreferencesDialog, GeneralPreferencesDialog" in app,
            "app.py does not import the extracted Preferences dialogs")
    require("class EditorPreferencesDialog(" not in app and "class GeneralPreferencesDialog(" not in app,
            "Preferences dialog class still owned by app.py")

    for name, expected in EXPECTED_AST.items():
        require(_definition_digest(preferences, name) == expected,
                f"{name} changed while being extracted from x1.1")

    tree = ast.parse(app, filename=str(app_path))
    suite_window = next((node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "SuiteWindow"), None)
    require(suite_window is not None, "SuiteWindow missing")
    if suite_window is not None:
        methods = [node.name for node in suite_window.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
        require(len(methods) == 212, "SuiteWindow method inventory changed during Preferences extraction")
        require(hashlib.sha256("\n".join(methods).encode("utf8")).hexdigest() == SUITEWINDOW_METHODS_SHA256,
                "SuiteWindow method inventory differs from x1.1")

    for relative, expected in FROZEN_RUNTIME_SHA256.items():
        path = PACKAGE / relative
        require(path.is_file(), f"frozen runtime module missing: {relative}")
        if path.is_file():
            require(preserved_sha256(path) == expected,
                    f"out-of-scope runtime module changed: {relative}")
