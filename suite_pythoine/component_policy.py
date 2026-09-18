from __future__ import annotations

from typing import Iterable, TypeVar

T = TypeVar("T")

_CAPABILITY_DEFAULTS = {
    "hub": frozenset(),
    "editor": frozenset({"routing", "open", "create"}),
    "reader": frozenset({"routing", "open"}),
    "extension": frozenset(),
}


def component_kind(component: object) -> str:
    value = getattr(component, "component_kind", None)
    if value is None:
        value = getattr(component, "kind", None)
    return str(value or "editor").strip().casefold()


def component_capabilities(component: object) -> frozenset[str]:
    raw = getattr(component, "capabilities", None)
    if isinstance(raw, dict):
        return frozenset(str(name).strip().casefold() for name, enabled in raw.items() if enabled and str(name).strip())
    if isinstance(raw, (tuple, list, set, frozenset)) and raw:
        return frozenset(str(name).strip().casefold() for name in raw if str(name).strip())
    return _CAPABILITY_DEFAULTS.get(component_kind(component), frozenset())


def has_capability(component: object, capability: str) -> bool:
    return str(capability or "").strip().casefold() in component_capabilities(component)


def is_document_editor(component: object) -> bool:
    return component_kind(component) == "editor"


def is_reader(component: object) -> bool:
    return component_kind(component) == "reader"


def is_hub(component: object) -> bool:
    return component_kind(component) == "hub"


def is_extension(component: object) -> bool:
    return component_kind(component) == "extension"


def can_route_document(component: object) -> bool:
    return has_capability(component, "routing")


def can_open_document(component: object) -> bool:
    return has_capability(component, "open")


def can_create_document(component: object) -> bool:
    return has_capability(component, "create")


def document_editors(components: Iterable[T]) -> list[T]:
    return [component for component in components if is_document_editor(component)]


def document_readers(components: Iterable[T]) -> list[T]:
    return [component for component in components if is_reader(component)]


def routable_components(components: Iterable[T]) -> list[T]:
    return [component for component in components if can_route_document(component) and can_open_document(component)]


def document_candidates(components: Iterable[T], extension: str) -> list[T]:
    wanted = str(extension or "").strip().casefold()
    if wanted and not wanted.startswith("."):
        wanted = f".{wanted}"
    return [
        component
        for component in components
        if can_route_document(component)
        and can_open_document(component)
        and bool(getattr(component, "available", False))
        and wanted in tuple(getattr(component, "extensions", ()))
    ]
