"""
Tracker Mode — performance instrumentation for SQL queries and UI renders.

When ``tracker_mode`` is enabled in app_config, every SQL query and every
UI render call is logged with its elapsed time.  Output is force-flushed
to stdout so it appears immediately in the console / log collector.
"""

import sys
import time
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Optional


# Module-level flag — toggled once at startup from AppConfig.tracker_mode
_enabled: bool = False


def init(enabled: bool) -> None:
    """Initialise the tracker.  Call once at server startup."""
    global _enabled
    _enabled = enabled
    if _enabled:
        _log("Tracker mode ENABLED — SQL and render timings will be logged")


def is_enabled() -> bool:
    return _enabled


# ── helpers ────────────────────────────────────────────────────

def _log(msg: str) -> None:
    """Print a tracker message and force-flush stdout."""
    print(f"[Tracker] {msg}", flush=True)


# ── SQL tracking ──────────────────────────────────────────────

@contextmanager
def track_sql(label: str, sql: str = ""):
    """Context manager that logs SQL elapsed time when tracker is on.

    Usage::

        with tracker.track_sql("fetch_page", query):
            result = conn.execute(text(query), params)
    """
    if not _enabled:
        yield
        return

    preview = sql.replace("\n", " ").strip()[:120] if sql else ""
    _log(f"SQL  START  {label} | {preview}")
    t0 = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        _log(f"SQL  END    {label} | {elapsed_ms:.1f}ms")


def log_sql(label: str, sql: str, elapsed_ms: float) -> None:
    """One-shot log for SQL that was already timed externally."""
    if not _enabled:
        return
    preview = sql.replace("\n", " ").strip()[:120] if sql else ""
    _log(f"SQL  {label} | {elapsed_ms:.1f}ms | {preview}")


# ── Render tracking ───────────────────────────────────────────

@contextmanager
def track_render(label: str):
    """Context manager that logs render elapsed time when tracker is on.

    Usage::

        with tracker.track_render("table_container"):
            html = build_table_container(...)
    """
    if not _enabled:
        yield
        return

    _log(f"RENDER START  {label}")
    t0 = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        _log(f"RENDER END    {label} | {elapsed_ms:.1f}ms")


def render_timer(label: str):
    """Decorator that wraps a function with render timing.

    Usage::

        @tracker.render_timer("table_container")
        def table_container():
            ...
    """
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not _enabled:
                return fn(*args, **kwargs)
            _log(f"RENDER START  {label}")
            t0 = time.perf_counter()
            try:
                result = fn(*args, **kwargs)
            finally:
                elapsed_ms = (time.perf_counter() - t0) * 1000
                _log(f"RENDER END    {label} | {elapsed_ms:.1f}ms")
            return result
        return wrapper
    return decorator
