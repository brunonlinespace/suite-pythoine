"""1.0.0-x1.3 Installed Applications presentation extraction contract (Qt-free).

The page construction AST is preserved from x1.2 without modifying callbacks.
Operational ownership stays with SuiteWindow; only the rendering body moved.
"""
from __future__ import annotations
from suite_pythoine.qa.wave2_x22_regressions import preserved_sha256
from .extracted_page_sources import read_app_with_presentations

import ast
import hashlib
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
PAGE_PATH = PACKAGE / "ui/pages/installed_applications.py"
EXPECTED_PAGE_BODY_SHA256 = "f80a943c16eb4cb99c738c2f8aae2378fc3c64639fd501776bb317df37704efa"
EXPECTED_GUIDANCE_AST_SHA256 = "48a87370771ee55c2a7f110e320cbe2e94669a7f1d1809df99f3b163ccd074c1"
SUITEWINDOW_METHODS_SHA256 = "f47d2b64f7ebf86d8b9f0be2644a5e66dc482acf937184fdcc6f394d9991ae7a"
UNCHANGED_SHELL_METHODS_SHA256 = "b73b79b189e531a1505e1c08b48aa591b616bea3d4fbb7c13f3edfbf6f685fb5"
FROZEN_RUNTIME_SHA256 = {
    "installer.py": "ac7b9e29f62c52ea41b9577c8bdc22cc4404a6e2182c1fe481d9d32ac304a0c0",
    "install_wizard.py": "45d1e0f5d7212a927d118b81f1830ce83b5ba2189e2cc378357b25e407f04dad",
    "appimage_wizard.py": "37ee6df031bbbd381b89498a307deb31edff15a689b01e5f5d1144dfa9c33784",
    "appimage_inspection.py": "80060dfd202ddbf9a7366175859ae5c8c2c2f52e808c352b4107e6199792d727",
    "registry.py": "79ff12bc8601bf1ec153d12ee070e30d3fb1779d5de0acd7eb0e52b39035215d",
    "installation_state.py": "f43ca48b3230cab03f9036c90ea119c3d90d597674541cb4f1fd10835562dd33",
    "recovery.py": "ef6022441d845a8c489f1c798fedb2cca1787e17514bf59ce12a9da2f9cb7c5b",
    "purge_wizard.py": "f50e6204cbdaec6227e1d764dc33467c37e8526068afa1d45f78be883b571ce2",
    "asset_removal.py": "c09283c8c6171057e0b2cdcda963829fae848784745748c0bd995e17dc107329",
    "prune_policy.py": "91b0c15cbc9f456923aac99aa19bdca08457b7bc9088204d34ba0bd05597e8d2",
    "version_history.py": "f758e7928bcd6a8aefed610f54d5c7014c1eff8eab0bf24a2af51039db39850b",
    "catalogue/component_catalog.py": "25e866f18f775229dd142e5b7444f845a5e5c34854d62235c4a7864faa571398",
    "store/store_content.py": "0a5ae87deb49d05fa1216fa9eb695b460ebac058fa71ae99dcfdec421dd141ef",
    "ui/shell/suite_theme.py": "880f77b11d4e8d02cc46400d4f95b7ba136f3009be80bf95b45b43c583b65e15",
    "ui/shell/sidebar_launcher.py": "19efdd2fde4073ac1646571455b8ac966b52bc8416aa6a0c426169e08b230d25",
    "runtime/runtime_launcher.py": "1d360644dd088f138ce2ebbeabc2735c22e026991d9e8a089f3a8464f36b2ffd",
    "routing/routing_index.py": "14f0543cf9707afbf6ecdfcd2593db7d5efbb3e1205e10cd4a9a96def5c8a542",
    "registry_retirement.py": "08f5d66eb7ab05f186939d1f18959a5de930736da183f7f21557e05c1d490a6f",
}


def _digest(node: ast.AST) -> str:
    return hashlib.sha256(ast.dump(node, include_attributes=False).encode("utf8")).hexdigest()


def run_regressions(errors: list[str]) -> None:
    prefix = "1.0.0-x1.3 presentation extraction: "

    def check(condition: bool, reason: str) -> None:
        if not condition:
            errors.append(prefix + reason)

    app_path = PACKAGE / "app.py"
    app = read_app_with_presentations()
    page = PAGE_PATH.read_text(encoding="utf8") if PAGE_PATH.is_file() else ""
    check(PAGE_PATH.is_file(), "missing Installed Applications page")
    check((PACKAGE / "ui/pages/__init__.py").is_file(), "missing pages package")
    check("from .ui.pages.installed_applications import build_installed_applications_page" in app,
          "SuiteWindow must import the extracted page")
    app_tree = ast.parse(app)
    window = next((node for node in app_tree.body if isinstance(node, ast.ClassDef)
                   and node.name == "SuiteWindow"), None)
    check(window is not None, "SuiteWindow missing")
    if window is not None:
        methods = [node.name for node in window.body
                   if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
        check(len(methods) == 212 and hashlib.sha256("\n".join(methods).encode()).hexdigest()
              == SUITEWINDOW_METHODS_SHA256, "SuiteWindow method inventory changed")
        other_methods = [node for node in window.body
                         if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                         and node.name != "_installed_applications_page"]
        check(_digest(ast.Module(body=other_methods, type_ignores=[]))
              == UNCHANGED_SHELL_METHODS_SHA256,
              "one of 211 out-of-scope SuiteWindow methods changed")
        entry = next((node for node in window.body if isinstance(node, ast.FunctionDef)
                      and node.name == "_installed_applications_page"), None)
        check(entry is not None, "SuiteWindow page entry point missing")
        if entry is not None:
            check(len(entry.body) == 1 and isinstance(entry.body[0], ast.Return),
                  "page entry point must remain a thin delegate")
            check('@traced_operation("page_installed_applications")' in app,
                  "page tracing decorator lost")
            check("APP_ICON_PATH=APP_ICON_PATH" in ast.get_source_segment(app, entry)
                  and "_style_destructive_button=_style_destructive_button" in ast.get_source_segment(app, entry),
                  "shell resources are not forwarded")
        guidance = next((node for node in window.body if isinstance(node, ast.FunctionDef)
                         and node.name == "_show_installed_applications_guidance"), None)
        check(guidance is not None and _digest(guidance) == EXPECTED_GUIDANCE_AST_SHA256,
              "Installed Applications guidance changed")
        for owner in ("_inventory_records", "_asset_inventory_records", "_remove_asset_records",
                      "_inventory_launch_runtime", "_inventory_open_component",
                      "_save_inventory_table_layout", "_restore_inventory_table_layout"):
            check(owner in methods, f"operational/layout owner moved out of SuiteWindow: {owner}")

    if page:
        tree = ast.parse(page)
        builder = next((node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == "build_installed_applications_page"), None)
        check(builder is not None, "page builder missing")
        if builder is not None:
            # Drop only the new top-level function docstring, not production code.
            check(len(builder.body) > 1 and isinstance(builder.body[0], ast.Expr)
                  and isinstance(builder.body[0].value, ast.Constant)
                  and _digest(ast.Module(body=builder.body[1:], type_ignores=[]))
                  == EXPECTED_PAGE_BODY_SHA256,
                  "extracted page construction/callback AST differs from x1.2")
            check([arg.arg for arg in builder.args.kwonlyargs]
                  == ["APP_ICON_PATH", "_style_destructive_button"],
                  "page must receive only the two shell-owned resources")
        check("from ...app import SuiteWindow" in page and "if TYPE_CHECKING:" in page,
              "type-only SuiteWindow import guard missing")
        check("from ...app import SuiteWindow\n" in page,
              "type-only SuiteWindow reference missing")
        check("from ...installer import" not in page and "from ...asset_removal import" not in page,
              "extracted UI now directly owns operational services")

    for relative, digest in FROZEN_RUNTIME_SHA256.items():
        path = PACKAGE / relative
        check(path.is_file() and preserved_sha256(path) == digest,
              f"frozen operational module changed: {relative}")

    # Historical regressions must follow the relocated implementation rather
    # than drop their original page behavior assertions.
    for name in ("polish089", "polish105", "polish106", "polish107", "polish108",
                 "removal104", "corrections087", "corrections092", "corrections091",
                 "store_backend011exp60", "convergence0120"):
        path = PACKAGE / "qa" / f"{name}_regressions.py"
        check(path.is_file() and "ui/pages/installed_applications.py" in path.read_text(encoding="utf8"),
              f"historical behavior regression no longer targets the extracted UI: {name}")
