"""1.0.0-x1.6 Wave-1 convergence guard (Qt-free, based on issued x1.5).

Prove source-only import clean-up and single page ownership, validate the
performance comparison reporter and keep all existing production code frozen.
"""
from __future__ import annotations
from suite_pythoine.qa.wave2_x22_regressions import preserved_sha256
import ast
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import json
from suite_pythoine.tools.performance_compare import compare_records, read_traces
from .extracted_page_sources import EXTRACTED

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "suite_pythoine"
BASELINE_PRODUCTION_SHA256 = {'main.py': 'fb9773d61a63cb1a4bb54172cfa708e0ffa4c3743e23b35206a155fabb9dfe95', 'suite_pythoine/self_restore.py': '1a873f9d8516f35c07bfa1c3836d7bd2286f61404166ce070183006bbd0cd382', 'suite_pythoine/suite_self_restore_worker.py': 'f70892f10457706b6ecb4870875a88cb41c0e4c333b68b918167cfa4cfc56e96', 'suite_pythoine/storage_migration.py': '3648d0f4941cc7262b9661008e4a6a64d767f2ce831a177928e19d3a8a57c2a6', 'suite_pythoine/ui/dialogs/shortcuts_dialog.py': 'e4330c5aeca3593a6b7373088a714c2cc1d8a1ff1b713efcfb8d30905f24a474', 'suite_pythoine/version_management.py': 'a1aca2487a0f1762db02c00c11d278d1abf6f50da9c38058b20eb1f8a6f3e5ce', 'suite_pythoine/ui/dialogs/quick_tour.py': 'f4248a55b8adf0edee010a323dc1d4628a1cfd0a68dcfdb419b89c7027acf2a3', 'suite_pythoine/catalogue/component_catalog.py': '25e866f18f775229dd142e5b7444f845a5e5c34854d62235c4a7864faa571398', 'suite_pythoine/routing/routing_index.py': '14f0543cf9707afbf6ecdfcd2593db7d5efbb3e1205e10cd4a9a96def5c8a542', 'suite_pythoine/developer/developer_archive.py': 'f76cbdd4a4bead31d89ebcff6f9c80fceb015e246629c5bfff0d0e1f4e6ed2e4', 'suite_pythoine/self_update.py': 'd8d3a19c0ceee21e3d59496aa4f38cea1d5fc0d5ee8866b565349af4c5069f4f', 'suite_pythoine/ui/shell/sidebar_search.py': '291d3301c95c0815f310650e240e7fd0f5a5d72eed50b5b382e3e3408759e295', 'suite_pythoine/developer/developer_intake_vault.py': '9b3af996dd900485e3ac890be461986c89fdeb5a2362aeeba86ae408b780e75c', 'suite_pythoine/ui_titles.py': '23fbf126cdec44ac5ddf08c897c4a25ff0b54871e98c52a28fa12ae40281b705', 'suite_pythoine/installer.py': 'ac7b9e29f62c52ea41b9577c8bdc22cc4404a6e2182c1fe481d9d32ac304a0c0', 'suite_pythoine/appimage_wizard.py': '37ee6df031bbbd381b89498a307deb31edff15a689b01e5f5d1144dfa9c33784', 'suite_pythoine/routing/routing_chooser.py': 'f6b339e3b789225bbda263d89b17a0663d25e3950139bfad26285f12e9633c4b', 'suite_pythoine/registry_retirement.py': '08f5d66eb7ab05f186939d1f18959a5de930736da183f7f21557e05c1d490a6f', 'suite_pythoine/versioning.py': '3f8b48a2957556b618bafdcb939a8210a15574ecdb6e4d72defad7da49b1a915', 'suite_pythoine/recovery.py': 'ef6022441d845a8c489f1c798fedb2cca1787e17514bf59ce12a9da2f9cb7c5b', 'suite_pythoine/gui_errors.py': 'bb0640c8f8bce19722055177fbf7188b6fcfcfb416269535f9cbc1026018abca', 'suite_pythoine/catalogue/component_policy.py': '91aeb7d848beeea4af4ab9f370dd303cfbfd7fac9a5920ffbb7b423c030ab8d1', 'suite_pythoine/migration_wizard.py': 'ac0e798f07f39c0ea1cc08f91be5cb9fc79227494347ec8723c7154d9d234b5e', 'suite_pythoine/config.py': '2b992d3a18d00837daf2e47b43731da19da075f450d519b83ce20ee303850ceb', 'suite_pythoine/operation_ui.py': 'de924e66ed6b487d1737dc6efd092a351c00d39bdf2b4e666e62887d5e00fb19', 'suite_pythoine/version_history.py': 'f758e7928bcd6a8aefed610f54d5c7014c1eff8eab0bf24a2af51039db39850b', 'suite_pythoine/install_inspection.py': '5e02028c4f93ef8d810e81efec68d3b5f441b9f3360f6ac527dcd59ae22a4f06', 'suite_pythoine/runtime/runtime_launcher.py': '1d360644dd088f138ce2ebbeabc2735c22e026991d9e8a089f3a8464f36b2ffd', 'suite_pythoine/editor_watcher.py': '46d12fb7dcb35bf4752653f57d0056d163e8ae0f08aa48188031d3d080460e42', 'suite_pythoine/ui/shell/dashboard_model.py': '6671f6a2116727da5e4b5bd76ef9fecfd938e63ecb63fce4d373ecec3bea4d48', 'suite_pythoine/registry.py': '79ff12bc8601bf1ec153d12ee070e30d3fb1779d5de0acd7eb0e52b39035215d', 'suite_pythoine/self_bootstrap.py': '72a689f3278ff1b7e62b658a714599183c8aaaabdcc6be1113c31285149814fb', 'suite_pythoine/ui/shell/sidebar_launcher.py': '19efdd2fde4073ac1646571455b8ac966b52bc8416aa6a0c426169e08b230d25', 'suite_pythoine/prune_policy.py': '91b0c15cbc9f456923aac99aa19bdca08457b7bc9088204d34ba0bd05597e8d2', 'suite_pythoine/routing/silent_dispatch.py': '8d88653955d1895a9fb000d28ebe8275ec243173ad5e0200a40b9671dd956153', 'suite_pythoine/ui/shell/dashboard.py': '75193ca82aaf5dc5a080b12baa66828dc787c35d8b381ac9747d38c11b4272db', 'suite_pythoine/storage_layout.py': '5310804ae5cc817ae0df358168e1cebd93df4b67a081e74c97dcf5299fd169e4', 'suite_pythoine/recovery_restore_wizard.py': 'd4e2af86e68556d5116e1b77183284e77a7ba63561f41168e7971aadd5e0eada', 'suite_pythoine/store/store_bridge.py': 'f829866279d626620eff8d3b3fe5380ec9a6a53cc49fb7cd1fd5a1b953da0249', 'suite_pythoine/suite_uninstall.py': '8eb09f7157bbae4d42d4eff2a11718db8a06137255f228cd19576700af245711', 'suite_pythoine/root_transition.py': '04088ce4be6c8c1fd087e28ba9f749bf3c94d58e71680d09eacec015efa9b0f5', 'suite_pythoine/purge_wizard.py': 'f50e6204cbdaec6227e1d764dc33467c37e8526068afa1d45f78be883b571ce2', 'suite_pythoine/appimage_build_wizard.py': '8e635800be51a572e5f423a5b12c4c34a1dc1ac9111da3b21155e47efbdd7219', 'suite_pythoine/ui/shell/suite_theme.py': '880f77b11d4e8d02cc46400d4f95b7ba136f3009be80bf95b45b43c583b65e15', 'suite_pythoine/store/store_content.py': '0a5ae87deb49d05fa1216fa9eb695b460ebac058fa71ae99dcfdec421dd141ef', 'suite_pythoine/install_wizard.py': '45d1e0f5d7212a927d118b81f1830ce83b5ba2189e2cc378357b25e407f04dad', 'suite_pythoine/runtime/runtime_paths.py': 'a53ee3056fb7f2367000db6db793d15d01149820a010cb32cf2752bc3dd724b5', 'suite_pythoine/purge_assets.py': '1d2f19b2c43bf2510f892851e76b8e2ca0f23c14883bf01ec88c0c016e1370ad', 'suite_pythoine/appimage_inspection.py': '80060dfd202ddbf9a7366175859ae5c8c2c2f52e808c352b4107e6199792d727', 'suite_pythoine/installation_state.py': 'f43ca48b3230cab03f9036c90ea119c3d90d597674541cb4f1fd10835562dd33', 'suite_pythoine/developer/developer_policy.py': '316f74a639d0d0300201338d028bd12251152b928280f64e617215b29e30283e', 'suite_pythoine/asset_removal.py': 'c09283c8c6171057e0b2cdcda963829fae848784745748c0bd995e17dc107329', 'suite_pythoine/suite_uninstall_worker.py': '11349c8dbefd6c02e3ca25dd09fd8ab791abd669b6a38908cf8f4a5e61a04488', 'suite_pythoine/developer/developer_intake.py': 'd6dd878ccf49a618876145c191d807941c3158d65f5fe8c8ab211e973320c761', 'suite_pythoine/ui/helpers.py': '8c319f7195d7ab7cb00af6435f60534261f0f2febf209d24efa9fdb13ed6a1b7', 'suite_pythoine/ui/widgets/inventory.py': 'fe17f8e1473e9cef2b4503958e55d64856f1464381aab0ecf1b1c4ca83403501', 'suite_pythoine/ui/widgets/prune.py': 'ac5c95c945fc48a49c471a82d1b1427f3f6623cf1040c425341b67fcffd39a5e', 'suite_pythoine/ui/pages/application.py': 'c80bbddc468aca97ee503ef91a9f20d1353f94460993337ef76c54b0aca0e270', 'suite_pythoine/ui/pages/version_history_page.py': 'b94aaa83552f9befc5aeed3582d2d5331cd802ba74a2ad37464af1ddef9da494', 'suite_pythoine/ui/pages/store_catalogue.py': 'd5e5eff8a5be795d2c24faff704482fda517336eb6faf0d420e805398fedb528', 'suite_pythoine/ui/pages/installed_applications.py': '1db383d0b033f30184d3a564ced97c018d9c818bf2088512424a8960aea41fb2'}

# Every extracted page builder has one owner and one legacy SuiteWindow entry point.
PAGES = {
    "_add_details_identity_header": ("application.py", "add_details_identity_header"),
    "_current_version_frame": ("application.py", "build_current_version_frame"),
    "_populate_editor_details": ("application.py", "populate_editor_details"),
    "_editor_page": ("application.py", "build_application_page"),
    "_version_management_frame": ("version_history_page.py", "build_version_management_frame"),
    "_version_history_page": ("version_history_page.py", "build_version_history_page"),
    "_add_store_enrichment": ("store_catalogue.py", "add_store_enrichment"),
    "_catalogue_page": ("store_catalogue.py", "build_catalogue_page"),
    "_catalog_component_page": ("store_catalogue.py", "build_catalog_component_page"),
    "_installed_applications_page": ("installed_applications.py", "build_installed_applications_page"),
}


def run_regressions(errors: list[str]) -> None:
    def check(condition: bool, label: str) -> None:
        if not condition:
            errors.append("1.0.0-x1.6 convergence: " + label)

    app_source = (PACKAGE / "app.py").read_text(encoding="utf8")
    app_tree = ast.parse(app_source)
    window = next(x for x in app_tree.body if isinstance(x, ast.ClassDef) and x.name == "SuiteWindow")
    methods = {x.name: x for x in window.body if isinstance(x, ast.FunctionDef)}
    check(len(methods) == 212, "SuiteWindow method count changed")
    check(len(PAGES) == 10, "extraction inventory incomplete")
    shared_implementations: list[str] = []
    for name, (filename, builder_name) in PAGES.items():
        path = PACKAGE / "ui/pages" / filename
        contents = ast.parse(path.read_text(encoding="utf8"))
        builders = [x for x in contents.body if isinstance(x, ast.FunctionDef) and x.name == builder_name]
        check(len(builders) == 1, f"{name}: missing or duplicate implementation in {filename}")
        shared_implementations.extend(x.name for x in contents.body if isinstance(x, ast.FunctionDef) and x.name == builder_name)
        check(name in methods, f"SuiteWindow.{name} is absent")
        if name in methods:
            wrapper = methods[name]
            check(len(wrapper.body) == 1 and isinstance(wrapper.body[0], ast.Return)
                  and isinstance(wrapper.body[0].value, ast.Call)
                  and isinstance(wrapper.body[0].value.func, ast.Name)
                  and wrapper.body[0].value.func.id == builder_name,
                  f"SuiteWindow.{name} no longer delegates once to its canonical builder")
        if name != "_installed_applications_page":
            check(EXTRACTED.get(name) == (filename, builder_name),
                  f"{name} historical source mapping has drifted")
    check(len(shared_implementations) == len(set(shared_implementations)),
          "duplicate builder names across application/Store/history/inventory pages")
    check("self._add_details_identity_header(" in
          (PACKAGE/'ui/pages/installed_applications.py').read_text(encoding='utf8'),
          "Installed Applications no longer uses the canonical identity header")
    check("self._add_store_enrichment(layout, editor.editor_id)" in
          (PACKAGE/'ui/pages/application.py').read_text(encoding='utf8'),
          "Application Page Store enrichment no longer reuses canonical owner")

    # Imports already moved to the actual page: no stale shell-only duplicates.
    app_imports = set()
    for node in app_tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            app_imports.update(alias.asname or alias.name.split('.')[0] for alias in node.names)
    old_names = {'QDesktopServices', 'QAbstractItemView', 'QButtonGroup', 'QFormLayout',
                 'QGroupBox', 'QHeaderView', 'QTabWidget', 'QTableWidgetItem',
                 'traced_duration', 'installed_icon_candidates', 'normalize_extension',
                 'published_manifest_path', 'resolve_store_screenshot',
                 'DeveloperSettingsDialog', 'read_appimage_metadata',
                 'build_version_history_rows', '_format_timestamp', '_human_size',
                 'AssetSelectionHeader', 'SortableTableItem'}
    check(not old_names.intersection(app_imports),
          "obsolete x1.1–x1.5 import still present in app.py")
    check('from ..helpers import _format_timestamp, _human_size' in
          (PACKAGE/'ui/pages/installed_applications.py').read_text(encoding='utf8'),
          "extracted inventory helper imports missing")
    check('from ..widgets.inventory import AssetSelectionHeader, SortableTableItem' in
          (PACKAGE/'ui/pages/installed_applications.py').read_text(encoding='utf8'),
          "extracted inventory widget imports missing")

    for relative, digest in BASELINE_PRODUCTION_SHA256.items():
        file = ROOT / relative
        check(file.is_file() and preserved_sha256(file) == digest,
              f"x1.5 production code unexpectedly changed: {relative}")

    # Synthetic records test only the comparator's numerical/reporting logic.
    # They are never presented as real GUI benchmarks.
    records = ([{'suite_version': '1.0.0-x1.0', 'operation': 'page_application',
                 'total_ms': value} for value in (8.,9.,10.,11.,12.)]
               + [{'suite_version': '1.0.0-x1.6', 'operation': 'page_application',
                   'total_ms': value} for value in (9.,10.,11.,12.,13.)])
    result, incomplete = compare_records(records, '1.0.0-x1.0', '1.0.0-x1.6',
                                          operations=('page_application',), min_samples=5)
    check(not incomplete and len(result) == 1 and result[0]['median_ratio'] == 1.1
          and result[0]['baseline_p95_ms'] == 12.0
          and result[0]['candidate_p95_ms'] == 13.0,
          "performance comparator median/p95 arithmetic inaccurate")
    result, incomplete = compare_records(records[:4], '1.0.0-x1.0', '1.0.0-x1.6',
                                          operations=('page_application',), min_samples=5)
    check(not result and len(incomplete) == 1,
          "insufficient samples were silently treated as evidence of parity")
    with TemporaryDirectory(prefix='suite-x16-perf-qa-') as directory:
        log = Path(directory)/'traces.jsonl'
        log.write_text(''.join(json.dumps(row)+'\n' for row in records), encoding='utf8')
        check(len(read_traces([log])) == 10, "performance JSONL reader missed records")
