from __future__ import annotations

from dataclasses import dataclass

from .versioning import compare_versions, version_sort_key


@dataclass(frozen=True, slots=True)
class InstallDecision:
    kind: str
    default_mode: str
    incoming_version: str
    active_version: str | None
    exact_present: bool


def classify_install(incoming_version: str, active_version: str | None, existing_versions: list[str] | tuple[str, ...]) -> InstallDecision:
    existing = [str(value) for value in existing_versions if str(value)]
    exact = any(value.casefold() == incoming_version.casefold() for value in existing)
    if not existing:
        return InstallDecision("install", "install", incoming_version, active_version, False)
    if exact:
        return InstallDecision("reinstall", "reinstall", incoming_version, active_version, True)
    relation = compare_versions(incoming_version, active_version)
    if relation is not None and relation > 0:
        return InstallDecision("upgrade", "upgrade_remove", incoming_version, active_version, False)
    if relation is not None and relation < 0:
        return InstallDecision("downgrade", "downgrade_alongside", incoming_version, active_version, False)
    return InstallDecision("parallel", "alongside", incoming_version, active_version, False)


def versions_to_remove(existing_versions: list[str] | tuple[str, ...], incoming_version: str, mode: str) -> tuple[str, ...]:
    selected: list[str] = []
    for version in existing_versions:
        version = str(version)
        if not version or version.casefold() == incoming_version.casefold():
            continue
        relation = compare_versions(version, incoming_version)
        if mode == "upgrade_remove" and relation is not None and relation < 0:
            selected.append(version)
        elif mode == "downgrade_remove" and relation is not None and relation > 0:
            selected.append(version)
    return tuple(sorted(set(selected), key=version_sort_key))
