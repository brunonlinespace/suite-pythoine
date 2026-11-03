"""Historical Qt-free source view for x1.5-extracted presentation methods.

Previously written source/AST regression tests still inspect the original
SuiteWindow method bodies. This adapter resolves those bodies from the real
x1.5 production modules. It never copies a saved previous release: a change
in an extracted builder is visible immediately to every historical assertion.
The x1.4 and x1.5 extraction QA separately verify actual delegates and AST fidelity.
"""
from __future__ import annotations
import ast
from pathlib import Path
import textwrap

PACKAGE = Path(__file__).resolve().parents[1]
EXTRACTED = {
    "_add_details_identity_header": ("application.py", "add_details_identity_header"),
    "_current_version_frame": ("application.py", "build_current_version_frame"),
    "_populate_editor_details": ("application.py", "populate_editor_details"),
    "_editor_page": ("application.py", "build_application_page"),
    "_version_management_frame": ("version_history_page.py", "build_version_management_frame"),
    "_version_history_page": ("version_history_page.py", "build_version_history_page"),
    "_add_store_enrichment": ("store_catalogue.py", "add_store_enrichment"),
    "_catalogue_page": ("store_catalogue.py", "build_catalogue_page"),
    "_catalog_component_page": ("store_catalogue.py", "build_catalog_component_page"),
}


def read_app_with_presentations() -> str:
    """Read current app.py with extracted *live source* in historical AST positions."""
    source = (PACKAGE / "app.py").read_text(encoding="utf8")
    original = source.splitlines(keepends=True)
    tree = ast.parse(source)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SuiteWindow")
    replacements = []
    for method in cls.body:
        if not isinstance(method, ast.FunctionDef) or method.name not in EXTRACTED:
            continue
        filename, builder_name = EXTRACTED[method.name]
        page_source = (PACKAGE / "ui/pages" / filename).read_text(encoding="utf8")
        page_tree = ast.parse(page_source)
        builder = next(n for n in page_tree.body if isinstance(n, ast.FunctionDef) and n.name == builder_name)
        page_lines = page_source.splitlines(keepends=True)
        builder_body = "".join(page_lines[builder.body[0].lineno - 1: builder.end_lineno])
        start = min((d.lineno for d in method.decorator_list), default=method.lineno)
        header = "".join(original[start - 1: method.body[0].lineno - 1])
        restored = header + textwrap.indent(builder_body, "    ")
        replacements.append((start - 1, method.end_lineno, restored))
    for start, end, restored in sorted(replacements, reverse=True):
        original[start:end] = [restored]
    return "".join(original)
