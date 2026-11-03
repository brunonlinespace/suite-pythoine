"""Qt-free in-memory matching for the optional Suite applications launcher."""
from __future__ import annotations


def matches_application(entry: object, group: str, query: str) -> bool:
    """Search discovered metadata, without filesystem probes or page creation."""
    needle = str(query).strip().casefold()
    if not needle:
        return True
    haystack = " ".join((
        str(getattr(entry, "name", "")),
        str(getattr(entry, "editor_id", "")),
        str(getattr(entry, "description", "")),
        " ".join(getattr(entry, "extensions", ()) or ()),
        " ".join(getattr(entry, "capabilities", ()) or ()),
        group,
    )).casefold()
    return needle in haystack
