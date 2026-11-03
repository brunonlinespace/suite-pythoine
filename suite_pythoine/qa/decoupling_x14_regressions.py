"""1.0.0-x1.4 App Page and Version History presentation-only extraction (Qt-free).

The executable bodies match their x1.3 predecessors AST-for-AST, all other
SuiteWindow methods remain unchanged, and frozen operational modules remain
byte-identical. Historical assertions use live extracted source, never snapshots.
"""
from __future__ import annotations
from suite_pythoine.qa.wave2_x22_regressions import preserved_sha256
import ast
import hashlib
from pathlib import Path
from .extracted_page_sources import read_app_with_presentations, EXTRACTED

PACKAGE = Path(__file__).resolve().parents[1]
TARGETS = {'_add_details_identity_header': ('application.py', 'add_details_identity_header'), '_current_version_frame': ('application.py', 'build_current_version_frame'), '_populate_editor_details': ('application.py', 'populate_editor_details'), '_editor_page': ('application.py', 'build_application_page'), '_version_management_frame': ('version_history_page.py', 'build_version_management_frame'), '_version_history_page': ('version_history_page.py', 'build_version_history_page')}
EXPECTED_BODIES = {'_add_details_identity_header': 'f868977accb73448e203af23677596cbb85d4b9b297b6b461134cf1f3775fde8', '_current_version_frame': '5f5f6e0293d88718cd6faa4b05911084d86c30fd2256329f3219d8d1d1b5f9ed', '_populate_editor_details': '606c55ba0e7254358d8b9b7a45ec1c4e151abfd56081be655c944903cee2c0dd', '_editor_page': 'c54d6465875f5a70820c1f83119f9fdce8481562e782fee136565c62d9b5aaa2', '_version_management_frame': 'e5f54241414224d2d27150ce668bd651a784f8bc97b8682300b918a2e7793094', '_version_history_page': 'a4f310ad3166a951614fca0a85cd2df378cc529f21fae50f8c37602df3386e64'}
UNCHANGED_SHELL_SHA256 = '1670c7b771489e8fe7b2963a65ed776206b36aea79494cde7c843f515ef31d20'
FROZEN_FILES = {'installer.py': 'ac7b9e29f62c52ea41b9577c8bdc22cc4404a6e2182c1fe481d9d32ac304a0c0', 'install_wizard.py': '45d1e0f5d7212a927d118b81f1830ce83b5ba2189e2cc378357b25e407f04dad', 'appimage_wizard.py': '37ee6df031bbbd381b89498a307deb31edff15a689b01e5f5d1144dfa9c33784', 'appimage_inspection.py': '80060dfd202ddbf9a7366175859ae5c8c2c2f52e808c352b4107e6199792d727', 'registry.py': '79ff12bc8601bf1ec153d12ee070e30d3fb1779d5de0acd7eb0e52b39035215d', 'installation_state.py': 'f43ca48b3230cab03f9036c90ea119c3d90d597674541cb4f1fd10835562dd33', 'recovery.py': 'ef6022441d845a8c489f1c798fedb2cca1787e17514bf59ce12a9da2f9cb7c5b', 'purge_wizard.py': 'f50e6204cbdaec6227e1d764dc33467c37e8526068afa1d45f78be883b571ce2', 'asset_removal.py': 'c09283c8c6171057e0b2cdcda963829fae848784745748c0bd995e17dc107329', 'prune_policy.py': '91b0c15cbc9f456923aac99aa19bdca08457b7bc9088204d34ba0bd05597e8d2', 'version_history.py': 'f758e7928bcd6a8aefed610f54d5c7014c1eff8eab0bf24a2af51039db39850b', 'catalogue/component_catalog.py': '25e866f18f775229dd142e5b7444f845a5e5c34854d62235c4a7864faa571398', 'store/store_content.py': '0a5ae87deb49d05fa1216fa9eb695b460ebac058fa71ae99dcfdec421dd141ef', 'ui/shell/suite_theme.py': '880f77b11d4e8d02cc46400d4f95b7ba136f3009be80bf95b45b43c583b65e15', 'ui/shell/sidebar_launcher.py': '19efdd2fde4073ac1646571455b8ac966b52bc8416aa6a0c426169e08b230d25', 'runtime/runtime_launcher.py': '1d360644dd088f138ce2ebbeabc2735c22e026991d9e8a089f3a8464f36b2ffd', 'routing/routing_index.py': '14f0543cf9707afbf6ecdfcd2593db7d5efbb3e1205e10cd4a9a96def5c8a542', 'registry_retirement.py': '08f5d66eb7ab05f186939d1f18959a5de930736da183f7f21557e05c1d490a6f', 'store/store_bridge.py': 'f829866279d626620eff8d3b3fe5380ec9a6a53cc49fb7cd1fd5a1b953da0249', 'self_restore.py': '1a873f9d8516f35c07bfa1c3836d7bd2286f61404166ce070183006bbd0cd382', 'developer/developer_intake.py': 'd6dd878ccf49a618876145c191d807941c3158d65f5fe8c8ab211e973320c761', 'config.py': '2b992d3a18d00837daf2e47b43731da19da075f450d519b83ce20ee303850ceb'}


def _digest(node: ast.AST) -> str:
    return hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()


def run_regressions(errors: list[str]) -> None:
    prefix = "1.0.0-x1.4 extraction: "
    def check(condition: bool, reason: str) -> None:
        if not condition:
            errors.append(prefix + reason)

    app = (PACKAGE / "app.py").read_text(encoding="utf8")
    cls = next(n for n in ast.parse(app).body if isinstance(n, ast.ClassDef) and n.name == "SuiteWindow")
    funcs = {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}
    # Preserve the x1.4 historical out-of-scope AST contract even after x1.5
    # moved three more builders. The adapter loads the current live builders.
    prior_view_cls = next(n for n in ast.parse(read_app_with_presentations()).body
                          if isinstance(n, ast.ClassDef) and n.name == "SuiteWindow")
    others = [n for n in prior_view_cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name not in TARGETS]
    check(_digest(ast.Module(body=others, type_ignores=[])) == UNCHANGED_SHELL_SHA256,
          "out-of-scope SuiteWindow method body changed")
    check(len(funcs) == 212 and all(n in funcs for n in TARGETS),
          "existing SuiteWindow method inventory/entry points changed")
    check('from .ui.pages.application import (' in app and 'from .ui.pages.version_history_page import (' in app,
          "presentation builders missing from SuiteWindow imports")

    expected_delegates = {
        "_add_details_identity_header": "add_details_identity_header",
        "_current_version_frame": "build_current_version_frame",
        "_populate_editor_details": "populate_editor_details",
        "_editor_page": "build_application_page",
        "_version_management_frame": "build_version_management_frame",
        "_version_history_page": "build_version_history_page",
    }
    for name, (filename, builder_name) in TARGETS.items():
        wrapper = funcs.get(name)
        if wrapper:
            check(len(wrapper.body) == 1 and isinstance(wrapper.body[0], ast.Return)
                  and isinstance(wrapper.body[0].value, ast.Call)
                  and isinstance(wrapper.body[0].value.func, ast.Name)
                  and wrapper.body[0].value.func.id == expected_delegates[name],
                  f"SuiteWindow.{name} must remain a one-call delegate")
            if name == "_add_details_identity_header":
                check(len(wrapper.decorator_list) == 1 and isinstance(wrapper.decorator_list[0], ast.Name)
                      and wrapper.decorator_list[0].id == "staticmethod", "identity header lost staticmethod")
            if name in {"_editor_page", "_version_history_page"}:
                check(len(wrapper.decorator_list) == 1 and isinstance(wrapper.decorator_list[0], ast.Call)
                      and isinstance(wrapper.decorator_list[0].func, ast.Name)
                      and wrapper.decorator_list[0].func.id == 'traced_operation',
                      f"{name} no longer traced on SuiteWindow")
        page = PACKAGE / 'ui/pages' / filename
        check(page.is_file(), f"missing {filename}")
        if not page.is_file():
            continue
        content = page.read_text(encoding='utf8')
        tree = ast.parse(content)
        builder = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == builder_name), None)
        check(builder is not None, f"missing {builder_name}")
        if builder:
            body_hash = _digest(ast.Module(body=builder.body, type_ignores=[]))
            check(body_hash == EXPECTED_BODIES[name], f"{builder_name} construction AST differs from x1.3")
        check('if TYPE_CHECKING:' in content and 'from ...app import SuiteWindow' in content,
              f"missing type-only import boundary: {filename}")
        check('from ...asset_removal import' not in content and 'from ...installation_state import' not in content,
              f"{filename} imports ownership/removal logic")

    check(all(EXTRACTED.get(name) == mapping for name, mapping in TARGETS.items()),
          "historical view does not cover x1.4 extracted methods")
    virtual = read_app_with_presentations()
    restored_cls = next(n for n in ast.parse(virtual).body if isinstance(n, ast.ClassDef) and n.name == "SuiteWindow")
    restored = {n.name: n for n in restored_cls.body if isinstance(n, ast.FunctionDef)}
    for name in TARGETS:
        # x1.3's AST fidelity is reflected in the restored live-source view, including decorators.
        check(_digest(ast.Module(body=restored[name].body, type_ignores=[])) == EXPECTED_BODIES[name],
              f"historical source adapter doesn't expose live {name} body")
    for name, digest in FROZEN_FILES.items():
        f = PACKAGE / name
        check(f.is_file() and preserved_sha256(f) == digest,
              f"frozen non-presentation source changed: {name}")
    check('APP_ICON_PATH=APP_ICON_PATH' in app and '_style_destructive_button=_style_destructive_button' in app,
          "shell-owned icon/style resources are not passed through")
    check('APP_ICON_PATH=APP_ICON_PATH' in ast.get_source_segment(app, funcs['_add_details_identity_header'])
          and '_style_destructive_button=_style_destructive_button' in ast.get_source_segment(app, funcs['_populate_editor_details']),
          "details icon/destructive styling callbacks missing")
    check('preferred_version=preferred_version' in ast.get_source_segment(app, funcs['_version_history_page']),
          "preferred-version selection lost in delegate")
    check('self._version_filters[page] = version_filter' in (PACKAGE/'ui/pages/version_history_page.py').read_text(),
          "version-filter focus lifecycle not retained")
