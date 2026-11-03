"""1.0.0-x1.5 Store/catalogue presentation-only extraction contract (Qt-free).

Checks original x1.4 construction-body ASTs, all remaining SuiteWindow methods,
unchanged operational code and new delegates without a GUI runtime dependency.
"""
from __future__ import annotations
from suite_pythoine.qa.wave2_x22_regressions import preserved_sha256
import ast
import hashlib
from pathlib import Path
from .extracted_page_sources import read_app_with_presentations, EXTRACTED

PACKAGE = Path(__file__).resolve().parents[1]
TARGETS = {'_add_store_enrichment': 'add_store_enrichment', '_catalogue_page': 'build_catalogue_page', '_catalog_component_page': 'build_catalog_component_page'}
EXPECTED_BODIES = {'_add_store_enrichment': 'c42825482896f4879ad85660356e707b9c7bdc32dab0c3e78cc848d302ed97ec', '_catalogue_page': '3518e03c6b7edcf000710e693eb053b29bd0f3c7306045a8a3e45960e39128ee', '_catalog_component_page': '495df4e16abb450dafea154bf3db863af65a08105d3bcc63f5a8102bdc0aeaf3'}
UNCHANGED_SHELL_SHA256 = '1d9154708d92bb975f69ddea9347a7debc3e6f70b490de34ee76a6c0a4383923'
FROZEN_FILES = {'installer.py': 'ac7b9e29f62c52ea41b9577c8bdc22cc4404a6e2182c1fe481d9d32ac304a0c0', 'install_wizard.py': '45d1e0f5d7212a927d118b81f1830ce83b5ba2189e2cc378357b25e407f04dad', 'appimage_wizard.py': '37ee6df031bbbd381b89498a307deb31edff15a689b01e5f5d1144dfa9c33784', 'appimage_inspection.py': '80060dfd202ddbf9a7366175859ae5c8c2c2f52e808c352b4107e6199792d727', 'registry.py': '79ff12bc8601bf1ec153d12ee070e30d3fb1779d5de0acd7eb0e52b39035215d', 'installation_state.py': 'f43ca48b3230cab03f9036c90ea119c3d90d597674541cb4f1fd10835562dd33', 'recovery.py': 'ef6022441d845a8c489f1c798fedb2cca1787e17514bf59ce12a9da2f9cb7c5b', 'purge_wizard.py': 'f50e6204cbdaec6227e1d764dc33467c37e8526068afa1d45f78be883b571ce2', 'asset_removal.py': 'c09283c8c6171057e0b2cdcda963829fae848784745748c0bd995e17dc107329', 'prune_policy.py': '91b0c15cbc9f456923aac99aa19bdca08457b7bc9088204d34ba0bd05597e8d2', 'version_history.py': 'f758e7928bcd6a8aefed610f54d5c7014c1eff8eab0bf24a2af51039db39850b', 'catalogue/component_catalog.py': '25e866f18f775229dd142e5b7444f845a5e5c34854d62235c4a7864faa571398', 'store/store_content.py': '0a5ae87deb49d05fa1216fa9eb695b460ebac058fa71ae99dcfdec421dd141ef', 'ui/shell/suite_theme.py': '880f77b11d4e8d02cc46400d4f95b7ba136f3009be80bf95b45b43c583b65e15', 'ui/shell/sidebar_launcher.py': '19efdd2fde4073ac1646571455b8ac966b52bc8416aa6a0c426169e08b230d25', 'runtime/runtime_launcher.py': '1d360644dd088f138ce2ebbeabc2735c22e026991d9e8a089f3a8464f36b2ffd', 'routing/routing_index.py': '14f0543cf9707afbf6ecdfcd2593db7d5efbb3e1205e10cd4a9a96def5c8a542', 'registry_retirement.py': '08f5d66eb7ab05f186939d1f18959a5de930736da183f7f21557e05c1d490a6f', 'store/store_bridge.py': 'f829866279d626620eff8d3b3fe5380ec9a6a53cc49fb7cd1fd5a1b953da0249', 'self_restore.py': '1a873f9d8516f35c07bfa1c3836d7bd2286f61404166ce070183006bbd0cd382', 'developer/developer_intake.py': 'd6dd878ccf49a618876145c191d807941c3158d65f5fe8c8ab211e973320c761', 'config.py': '2b992d3a18d00837daf2e47b43731da19da075f450d519b83ce20ee303850ceb'}


def _digest(node: ast.AST) -> str:
    return hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()


def run_regressions(errors: list[str]) -> None:
    prefix = "1.0.0-x1.5 extraction: "
    def check(condition: bool, reason: str) -> None:
        if not condition:
            errors.append(prefix + reason)

    app = (PACKAGE / "app.py").read_text(encoding="utf8")
    cls = next(n for n in ast.parse(app).body if isinstance(n, ast.ClassDef) and n.name == "SuiteWindow")
    funcs = {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}
    others = [n for n in cls.body if isinstance(n, (ast.FunctionDef,ast.AsyncFunctionDef)) and n.name not in TARGETS]
    check(len(funcs) == 212 and set(TARGETS).issubset(funcs), "SuiteWindow entry points changed")
    check(_digest(ast.Module(body=others,type_ignores=[])) == UNCHANGED_SHELL_SHA256,
          "one of 209 out-of-scope SuiteWindow methods changed")
    check("from .ui.pages.store_catalogue import (" in app, "Store presentation import missing")
    store = PACKAGE / "ui/pages/store_catalogue.py"
    check(store.is_file(), "missing store_catalogue.py")
    if not store.is_file(): return
    source = store.read_text(encoding="utf8")
    body = ast.parse(source)
    builders = {n.name:n for n in body.body if isinstance(n,ast.FunctionDef)}
    for method, builder_name in TARGETS.items():
        wrapper = funcs.get(method)
        builder = builders.get(builder_name)
        check(builder is not None, f"missing {builder_name}")
        if builder is not None:
            check(_digest(ast.Module(body=builder.body,type_ignores=[])) == EXPECTED_BODIES[method],
                  f"{builder_name} AST differs from x1.4")
            check([a.arg for a in builder.args.args][:1] == ["self"], f"{builder_name} must receive SuiteWindow")
        if wrapper is not None:
            check(len(wrapper.body)==1 and isinstance(wrapper.body[0],ast.Return)
                  and isinstance(wrapper.body[0].value,ast.Call)
                  and isinstance(wrapper.body[0].value.func,ast.Name)
                  and wrapper.body[0].value.func.id==builder_name,
                  f"SuiteWindow.{method} is not a one-call delegate")
            if method in ("_catalogue_page", "_catalog_component_page"):
                expected = "page_catalogue" if method=="_catalogue_page" else "page_catalog_component"
                check(len(wrapper.decorator_list)==1 and isinstance(wrapper.decorator_list[0],ast.Call)
                      and isinstance(wrapper.decorator_list[0].func,ast.Name)
                      and wrapper.decorator_list[0].func.id=="traced_operation"
                      and len(wrapper.decorator_list[0].args)==1
                      and isinstance(wrapper.decorator_list[0].args[0],ast.Constant)
                      and wrapper.decorator_list[0].args[0].value==expected,
                      f"SuiteWindow.{method} lost original performance tracing")
    check('if TYPE_CHECKING:' in source and 'from ...app import SuiteWindow' in source,
          "unexpected circular runtime SuiteWindow import")
    check('from ...installer import' not in source
          and 'from ...installation_state import' not in source
          and 'from ...store_bridge import' not in source
          and 'from ...asset_removal import' not in source,
          "Store presentation imported an operational service")
    check(all(EXTRACTED.get(k)==("store_catalogue.py",v) for k,v in TARGETS.items()),
          "historical source view lacks Store methods")
    restored = next(n for n in ast.parse(read_app_with_presentations()).body
                    if isinstance(n,ast.ClassDef) and n.name=="SuiteWindow")
    restored_methods={n.name:n for n in restored.body if isinstance(n,ast.FunctionDef)}
    for method in TARGETS:
        check(_digest(ast.Module(body=restored_methods[method].body,type_ignores=[]))==EXPECTED_BODIES[method],
              f"historical source view did not restore live {method}")
    # Store backend & navigation orchestration must stay on SuiteWindow.
    for method in ('_reload_store_content','_store_catalog_profiles','_store_enrichment',
                   '_store_update_available','_publish_installed_store_content',
                   '_start_store_backend_operation','_refresh_store_online',
                   '_acquire_store_component','_install_acquired_store_package',
                   '_uninstalled_catalog_profiles','install_catalog_component',
                   'show_store','show_catalog_component'):
        check(method in funcs and method not in TARGETS, f"Store backend/owner moved: {method}")
    check("self._add_store_enrichment(layout, editor.editor_id)" in
          (PACKAGE/'ui/pages/application.py').read_text(encoding='utf8'),
          "canonical installed Application Page lost Store enrichment")
    for relative, digest in FROZEN_FILES.items():
        f = PACKAGE / relative
        check(f.is_file() and preserved_sha256(f) == digest,
              f"frozen operational module changed: {relative}")
