"""Dormant low-overhead performance tracing for Suite Pythoine.

The tracer is deliberately standard-library-only so timing can begin before Qt
is imported. Production behavior is unchanged unless the developer explicitly
enables tracing with ``SUITE_PYTHOINE_PERF=1``. One compact JSON object is
appended per operation to a private XDG cache log. The tracer itself never
records document contents or traversed filenames, and any diagnostic I/O error
is ignored so tracing cannot make Suite fail.
"""
from __future__ import annotations

from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
import json
import os
from pathlib import Path
from time import perf_counter
import uuid

from . import __version__

TRACE_SCHEMA = 1
# Fixed at process import. Developer opt-in must be set before launching Suite;
# changing the environment mid-session cannot attach new decorators safely.
_ENABLED = os.environ.get("SUITE_PYTHOINE_PERF", "0").strip().casefold() in {
    "1", "true", "yes", "on", "enabled",
}
_SESSION_ID = uuid.uuid4().hex[:12] if _ENABLED else ""
_PROCESS_START = perf_counter() if _ENABLED else 0.0
_CURRENT: ContextVar["TraceOperation | None"] = ContextVar("suite_pythoine_perf_operation", default=None)


def enabled() -> bool:
    """Return True only when tracing was explicitly enabled by the developer."""
    return _ENABLED


def process_start_perf() -> float:
    return _PROCESS_START


def log_path() -> Path:
    configured = os.environ.get("XDG_CACHE_HOME", "").strip()
    cache_root = Path(configured).expanduser() if configured and Path(configured).is_absolute() else Path.home() / ".cache"
    return cache_root / "suite-pythoine" / "performance.jsonl"


def _write(record: dict) -> None:
    if not enabled():
        return
    path = log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            path.parent.chmod(0o700)
        except OSError:
            pass
        payload = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
        with path.open("a", encoding="utf-8") as stream:
            stream.write(payload)
        try:
            path.chmod(0o600)
        except OSError:
            pass
    except OSError:
        # Diagnostics are observational only and must never alter Suite workflow.
        pass


class TraceOperation:
    def __init__(self, name: str, *, start_perf: float | None = None, **fields) -> None:
        self.name = str(name)
        self.started = float(start_perf if start_perf is not None else perf_counter())
        self.fields = dict(fields)
        self.counters: dict[str, int | float] = {}
        self.duration_totals_ms: dict[str, float] = {}
        self.spans: list[dict] = []
        self.finished = False
        self._token = None

    def activate(self) -> "TraceOperation":
        if enabled() and self._token is None:
            self._token = _CURRENT.set(self)
        return self

    def count(self, key: str, amount: int | float = 1) -> None:
        if not enabled():
            return
        self.counters[key] = self.counters.get(key, 0) + amount

    def add_duration(self, key: str, milliseconds: float) -> None:
        if enabled():
            self.duration_totals_ms[key] = self.duration_totals_ms.get(key, 0.0) + float(milliseconds)

    def set(self, key: str, value) -> None:
        if enabled():
            self.fields[str(key)] = value

    @contextmanager
    def span(self, name: str, **fields):
        if not enabled():
            yield
            return
        started = perf_counter()
        try:
            yield
        finally:
            self.spans.append({
                "name": str(name),
                "ms": round((perf_counter() - started) * 1000.0, 3),
                **fields,
            })

    def finish(self, **fields) -> None:
        if self.finished:
            return
        self.finished = True
        self.fields.update(fields)
        record = {
            "schema": TRACE_SCHEMA,
            "suite_version": __version__,
            "session": _SESSION_ID,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "pid": os.getpid(),
            "operation": self.name,
            "total_ms": round((perf_counter() - self.started) * 1000.0, 3),
            "fields": self.fields,
            "counters": self.counters,
            "duration_totals_ms": {key: round(value, 3) for key, value in self.duration_totals_ms.items()},
            "spans": self.spans,
        }
        _write(record)
        if self._token is not None:
            try:
                _CURRENT.reset(self._token)
            except (LookupError, RuntimeError, ValueError):
                pass
            self._token = None

    def __enter__(self) -> "TraceOperation":
        return self.activate()

    def __exit__(self, exc_type, exc, _tb) -> bool:
        self.finish(error=(f"{exc_type.__name__}: {exc}" if exc_type is not None else ""))
        return False


class _NoopOperation:
    """Inert startup handle: never allocates counters, timers or output."""

    def set(self, key: str, value) -> None:
        pass

    def finish(self, **fields) -> None:
        pass


_NOOP_OPERATION = _NoopOperation()
_NOOP_CONTEXT = nullcontext()


def begin_operation(name: str, *, start_perf: float | None = None, **fields) -> TraceOperation | _NoopOperation:
    if not _ENABLED:
        return _NOOP_OPERATION
    return TraceOperation(name, start_perf=start_perf, **fields).activate()


@contextmanager
def trace_operation(name: str, **fields):
    operation = begin_operation(name, **fields)
    try:
        yield operation
    except Exception as exc:
        operation.finish(error=f"{type(exc).__name__}: {exc}")
        raise
    else:
        operation.finish()


@contextmanager
def _enabled_trace_span(name: str, **fields):
    operation = _CURRENT.get()
    if operation is None:
        yield
        return
    with operation.span(name, **fields):
        yield


def trace_span(name: str, **fields):
    # In normal runs this is a reusable, inert context manager: no generator,
    # context lookup, TraceOperation, clock read, JSON serialization or disk I/O.
    if not _ENABLED:
        return _NOOP_CONTEXT
    return _enabled_trace_span(name, **fields)


def trace_counter(key: str, amount: int | float = 1) -> None:
    if _ENABLED:
        operation = _CURRENT.get()
        if operation is not None:
            operation.count(key, amount)


def trace_set(key: str, value) -> None:
    if _ENABLED:
        operation = _CURRENT.get()
        if operation is not None:
            operation.set(key, value)


def traced_duration(label: str):
    """Aggregate call count and duration into the currently active operation."""
    def decorate(function):
        if not _ENABLED:
            return function  # No wrapper or per-call dispatch on the default path.

        @wraps(function)
        def wrapper(*args, **kwargs):
            operation = _CURRENT.get()
            if operation is None:
                return function(*args, **kwargs)
            started = perf_counter()
            operation.count(f"{label}_calls")
            try:
                return function(*args, **kwargs)
            finally:
                operation.add_duration(label, (perf_counter() - started) * 1000.0)
        return wrapper
    return decorate


def traced_operation(name: str):
    """Make each function invocation its own top-level trace operation when enabled."""
    def decorate(function):
        if not _ENABLED:
            return function  # Original callable identity survives; no wrapper.

        @wraps(function)
        def wrapper(*args, **kwargs):
            with trace_operation(name) as operation:
                result = function(*args, **kwargs)
                try:
                    operation.set("result_count", len(result))
                except (TypeError, AttributeError):
                    pass
                return result
        return wrapper
    return decorate
