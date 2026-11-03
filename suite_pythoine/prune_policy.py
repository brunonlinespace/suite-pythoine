"""Qt-free selection policy for Developer Mode Prune.

Prune is only a preset layer.  It selects exact records already discovered by
Suite Pythoine; actual deletion remains exclusively in ``asset_removal.py``.
"""
from __future__ import annotations


def select_prune_records(
    records: list[dict],
    *,
    current_component_id: str,
    active_version: str | None,
    prune_to_this_app: bool,
    keep_this_recovery: bool,
    prune_to_active_version: bool,
    keep_active_recovery: bool,
) -> list[dict]:
    """Return the additive exact-asset selection for the requested Prune scopes.

    ``Prune to This App`` always keeps the current application and Suite
    Pythoine. ``Prune to Active Version`` targets only other versions of the
    current application. Each scope independently preserves Recovery only when
    its nested ``Keep Recovery Files`` option is checked.
    """
    current_id = str(current_component_id or "")
    active = str(active_version or "")
    selected: dict[tuple[str, str, str, str], dict] = {}

    for record in records:
        component_id = str(record.get("component_id") or "")
        version = str(record.get("version") or "")
        asset = str(record.get("asset") or "")
        locations = record.get("locations") or []
        location = str(locations[0]) if locations else ""
        include = False

        if prune_to_this_app and component_id not in {current_id, "suite-pythoine"}:
            include = not (asset == "Recovery" and keep_this_recovery)

        if (prune_to_active_version and active and component_id == current_id
                and version != active):
            if not (asset == "Recovery" and keep_active_recovery):
                include = True

        if include:
            selected[(component_id, version, asset, location)] = record

    return list(selected.values())
