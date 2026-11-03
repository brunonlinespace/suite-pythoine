from __future__ import annotations

from . import APP_NAME


def app_dialog_title(subject: object) -> str:
    """Return the canonical ``Window — Suite Pythoine`` title format.

    Callers may accidentally include the application name before or after the
    window subject. Normalize both forms so auxiliary windows never duplicate
    Suite Pythoine in their title bar.
    """
    text = str(subject).strip()
    if not text or text.casefold() == APP_NAME.casefold():
        return APP_NAME

    suffix = f" — {APP_NAME}"
    if text.casefold().endswith(suffix.casefold()):
        text = text[: -len(suffix)].rstrip(" —-")

    if text.casefold().startswith(APP_NAME.casefold()):
        text = text[len(APP_NAME) :].lstrip(" —-:")
    if text.casefold().endswith(APP_NAME.casefold()):
        text = text[: -len(APP_NAME)].rstrip(" —-:")

    return f"{text or APP_NAME}{suffix}" if text else APP_NAME
