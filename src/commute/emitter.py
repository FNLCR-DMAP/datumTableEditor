"""
EventEmitter — a fire-and-forget message channel backed by ``reactive.Value``.

Each widget instance creates its own ``EventEmitter``.  The emit() call
sets the internal reactive value to a dict with a standard shape::

    {
        "action":    str,        # e.g. "review_detail", "row_selected"
        "source":    str,        # widget id that fired the event
        "timestamp": float,      # ensures identical payloads still trigger
        **payload                # action-specific key/value pairs
    }

The host app receives the ``reactive.Value`` via ``WidgetAPI.events`` and
subscribes to it using normal Shiny reactive effects.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

from shiny import reactive


class EventEmitter:
    """Scoped event emitter for a single widget instance.

    Parameters
    ----------
    widget_id : str
        The module / namespace id of the widget (e.g. ``"editor1"``).
    """

    def __init__(self, widget_id: str) -> None:
        self._widget_id = widget_id
        self._events: reactive.Value[Optional[dict]] = reactive.Value(None)

    # -- Public API ----------------------------------------------------------

    @property
    def events(self) -> reactive.Value:
        """The underlying reactive value.  Host app reads this."""
        return self._events

    @property
    def widget_id(self) -> str:
        return self._widget_id

    def emit(self, action: str, **payload: Any) -> None:
        """Publish an event.

        Parameters
        ----------
        action : str
            A short verb describing what happened.  By convention lowercase
            snake_case, e.g. ``"review_detail"``, ``"row_selected"``.
        **payload
            Arbitrary key/value pairs attached to the event.
        """
        self._events.set({
            "action": action,
            "source": self._widget_id,
            "timestamp": time.time(),
            **payload,
        })

    def clear(self) -> None:
        """Reset the event value to ``None``."""
        self._events.set(None)

    def peek(self) -> Optional[dict]:
        """Read the current event without requiring a reactive context.

        Useful in tests and non-reactive code.  In production code prefer
        ``emitter.events.get()`` inside a reactive context.
        """
        return self._events._value


@dataclass
class WidgetAPI:
    """Return value from ``table_editor_server()``.

    Host apps use this to subscribe to widget events and read widget state.

    Attributes
    ----------
    events : reactive.Value
        The event channel.  Read with ``.get()`` inside a reactive context.
    data : reactive.Value
        The widget's current DataFrame.
    active_columns : reactive.Value
        The list of currently visible column names.
    widget_id : str
        The namespace id of the widget instance.
    """

    events: reactive.Value
    data: reactive.Value
    active_columns: reactive.Value
    widget_id: str = ""
    _extra: dict = field(default_factory=dict)

    def __getitem__(self, key: str) -> Any:
        """Allow dict-style access: ``api["events"]``."""
        if hasattr(self, key):
            return getattr(self, key)
        return self._extra[key]
