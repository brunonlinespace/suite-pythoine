from __future__ import annotations

from collections.abc import Iterable

from .registry import EditorEntry


def editor_search_text(editor: EditorEntry) -> str:
    """Return the searchable, user-visible editor metadata as one casefolded string."""
    return " ".join(
        (
            editor.name,
            editor.editor_id,
            editor.source_kind,
            editor.component_kind,
            " ".join(editor.extensions),
            editor.description,
        )
    ).casefold()


def filter_and_sort_editors(
    editors: Iterable[EditorEntry],
    query: str = "",
    sort_mode: str = "title_az",
) -> list[EditorEntry]:
    """Pure dashboard model used by Qt UI and non-GUI release checks.

    Search terms are ANDed. This makes searches such as ``pad html`` predictable,
    while a blank query returns every editor. Sort always includes deterministic
    tie-breakers so refreshes do not visually reshuffle equal values.
    """
    terms = tuple(part for part in query.casefold().split() if part)
    matched = [
        editor
        for editor in editors
        if not terms or all(term in editor_search_text(editor) for term in terms)
    ]

    if sort_mode == "title_za":
        return sorted(
            matched,
            key=lambda editor: (editor.name.casefold(), editor.editor_id.casefold(), str(editor.root).casefold()),
            reverse=True,
        )
    if sort_mode == "modified":
        return sorted(
            matched,
            key=lambda editor: (-float(editor.modified), editor.name.casefold(), editor.editor_id.casefold(), str(editor.root).casefold()),
        )
    return sorted(
        matched,
        key=lambda editor: (editor.name.casefold(), editor.editor_id.casefold(), str(editor.root).casefold()),
    )
