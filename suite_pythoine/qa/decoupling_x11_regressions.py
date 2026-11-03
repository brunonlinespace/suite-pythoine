"""1.0.0-x1.1 independent helper/widget extraction regressions (Qt-free)."""
from __future__ import annotations
from suite_pythoine.qa.wave2_x22_regressions import preserved_sha256

import ast
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "suite_pythoine"

EXPECTED_AST = {
    "SortableTableItem": "e08503eac11744aa4d32dcf4b1afb0cde410c606616ea406e3890c603d70ab59",
    "AssetSelectionHeader": "b2d695536b40cae069f27ced1d435adc8d0bd51f855a4ed9df99304e56506e5f",
    "PruneScopePage": "52adddc50582fb8326d1f9a918266a7bb36998dd553484c4cd44f977fda1de2d",
    "_human_size": "5a53bb721f9b3458bfa6caef34972680442726f0efe05dbb97e6d627aa0582a2",
    "_tree_size": "a44b3354596c557b1ba011e7acffdb2cb1f3ee25ada84cfe761d9dce81a5ee15",
    "_install_timestamp": "983dc203c4cea86b817f5876e09fd111f1fad8e82b63a429cd737cd0efdd2d8a",
    "_format_timestamp": "01d7f92177ebc6f26e92c46b81aec036986431c13ab004d4fe1ccac8a62c53cc",
}

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

SUITEWINDOW_METHODS_SHA256 = "f47d2b64f7ebf86d8b9f0be2644a5e66dc482acf937184fdcc6f394d9991ae7a"


def _definition_digest(path: Path, name: str) -> str:
    source = path.read_text(encoding="utf8")
    tree = ast.parse(source, filename=str(path))
    for node in tree.body:
        if getattr(node, "name", None) == name:
            payload = ast.dump(node, include_attributes=False)
            return hashlib.sha256(payload.encode("utf8")).hexdigest()
    return ""


def run_regressions(errors: list[str]) -> None:
    prefix = "1.0.0-x1.1 extraction: "

    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(prefix + message)

    app_path = PACKAGE / "app.py"
    app = app_path.read_text(encoding="utf8")
    inventory = PACKAGE / "ui" / "widgets" / "inventory.py"
    prune = PACKAGE / "ui" / "widgets" / "prune.py"
    helpers = PACKAGE / "ui" / "helpers.py"

    for path in (inventory, prune, helpers, PACKAGE / "ui" / "__init__.py", PACKAGE / "ui" / "widgets" / "__init__.py"):
        require(path.is_file(), f"missing extracted UI module: {path.relative_to(PACKAGE)}")

    require("from .ui.helpers import _install_timestamp, _tree_size" in app,
            "app.py no longer uses the remaining shell-owned inventory helpers")
    installed_page = (PACKAGE / "ui/pages/installed_applications.py").read_text(encoding="utf8")
    require("from ..helpers import _format_timestamp, _human_size" in installed_page,
            "Installed Applications no longer imports its extracted formatting helpers")
    require("from ..widgets.inventory import AssetSelectionHeader, SortableTableItem" in installed_page,
            "Installed Applications no longer imports its extracted inventory widgets")
    require("from .ui.widgets.prune import PruneScopePage" in app,
            "app.py does not import extracted Prune page")

    for declaration in (
        "class SortableTableItem(", "class AssetSelectionHeader(", "class PruneScopePage(",
        "def _human_size(", "def _tree_size(", "def _install_timestamp(", "def _format_timestamp(",
    ):
        require(declaration not in app, f"extracted definition still owned by app.py: {declaration}")

    locations = {
        "SortableTableItem": inventory,
        "AssetSelectionHeader": inventory,
        "PruneScopePage": prune,
        "_human_size": helpers,
        "_tree_size": helpers,
        "_install_timestamp": helpers,
        "_format_timestamp": helpers,
    }
    for name, expected in EXPECTED_AST.items():
        require(_definition_digest(locations[name], name) == expected,
                f"{name} changed while being extracted from the x1.0 baseline")

    tree = ast.parse(app, filename=str(app_path))
    suite_window = next((node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "SuiteWindow"), None)
    require(suite_window is not None, "SuiteWindow missing")
    if suite_window is not None:
        method_names = [node.name for node in suite_window.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
        require(len(method_names) == 212, "SuiteWindow method inventory changed during helper/widget extraction")
        require(hashlib.sha256("\n".join(method_names).encode("utf8")).hexdigest() == SUITEWINDOW_METHODS_SHA256,
                "SuiteWindow public/internal method inventory differs from x1.0")

    for relative, expected in FROZEN_RUNTIME_SHA256.items():
        path = PACKAGE / relative
        require(path.is_file(), f"frozen runtime module missing: {relative}")
        if path.is_file():
            require(preserved_sha256(path) == expected,
                    f"out-of-scope runtime module changed: {relative}")
