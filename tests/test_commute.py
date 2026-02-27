"""
Tests for the commute (event communication) layer.

The commute module provides ``EventEmitter`` and ``WidgetAPI`` for
decoupled event communication between the table-editor widget and
its host application.

Tests:
- EventEmitter initialisation, emit, clear, peek, property accessors
- Event message shape (action, source, timestamp, payload)
- Timestamp monotonicity (each emit has a unique timestamp)
- WidgetAPI dataclass construction and dict-style access
- WidgetAPI attribute access for events, data, active_columns
- Integration: emitter publishes, WidgetAPI consumer reads
"""

import time
import pytest
from unittest.mock import MagicMock

from src.commute.emitter import EventEmitter, WidgetAPI


# Helper: read a reactive.Value outside a reactive context
def _peek(rv):
    """Read reactive.Value._value directly (no reactive context needed)."""
    return rv._value


# =====================================================================
#  1. EventEmitter
# =====================================================================


class TestEventEmitterInit:
    """EventEmitter construction and property accessors."""

    def test_creates_with_widget_id(self):
        em = EventEmitter("editor1")
        assert em.widget_id == "editor1"

    def test_events_starts_none(self):
        em = EventEmitter("editor1")
        assert em.peek() is None

    def test_events_property_returns_reactive_value(self):
        em = EventEmitter("editor1")
        assert hasattr(em.events, "set")
        assert callable(em.events)

    def test_different_instances_independent(self):
        em1 = EventEmitter("a")
        em2 = EventEmitter("b")
        em1.emit("click")
        assert em1.peek()["action"] == "click"
        assert em2.peek() is None

    def test_widget_id_read_only(self):
        em = EventEmitter("fixed")
        with pytest.raises(AttributeError):
            em.widget_id = "changed"


class TestEventEmitterEmit:
    """EventEmitter.emit() message shape and payload."""

    def test_emit_sets_action(self):
        em = EventEmitter("w1")
        em.emit("review_detail")
        assert em.peek()["action"] == "review_detail"

    def test_emit_sets_source(self):
        em = EventEmitter("my_widget")
        em.emit("row_selected")
        assert em.peek()["source"] == "my_widget"

    def test_emit_sets_timestamp(self):
        before = time.time()
        em = EventEmitter("w")
        em.emit("ping")
        after = time.time()
        ts = em.peek()["timestamp"]
        assert before <= ts <= after

    def test_emit_includes_kwargs_payload(self):
        em = EventEmitter("w")
        em.emit("review_detail", pk={"id": 42}, table="patients")
        msg = em.peek()
        assert msg["pk"] == {"id": 42}
        assert msg["table"] == "patients"

    def test_emit_overwrites_previous(self):
        em = EventEmitter("w")
        em.emit("first")
        em.emit("second", val=99)
        msg = em.peek()
        assert msg["action"] == "second"
        assert msg["val"] == 99

    def test_emit_timestamps_are_monotonic(self):
        em = EventEmitter("w")
        em.emit("a")
        ts1 = em.peek()["timestamp"]
        time.sleep(0.002)
        em.emit("b")
        ts2 = em.peek()["timestamp"]
        assert ts2 > ts1

    def test_emit_with_no_payload(self):
        em = EventEmitter("w")
        em.emit("noop")
        msg = em.peek()
        assert set(msg.keys()) == {"action", "source", "timestamp"}

    def test_emit_with_complex_payload(self):
        em = EventEmitter("w")
        em.emit(
            "compare",
            pks=[{"id": 1}, {"id": 2}],
            columns=["a", "b"],
            metadata={"origin": "test"},
        )
        msg = em.peek()
        assert msg["pks"] == [{"id": 1}, {"id": 2}]
        assert msg["columns"] == ["a", "b"]
        assert msg["metadata"]["origin"] == "test"

    def test_emit_with_none_value_in_payload(self):
        em = EventEmitter("w")
        em.emit("action", key=None)
        assert em.peek()["key"] is None

    def test_emit_standard_message_shape(self):
        """Every emitted message has exactly action, source, timestamp + payload."""
        em = EventEmitter("widget_x")
        em.emit("test_action", data=123)
        msg = em.peek()
        assert "action" in msg
        assert "source" in msg
        assert "timestamp" in msg
        assert "data" in msg
        assert msg["data"] == 123

    def test_emit_source_matches_widget_id(self):
        """The source field always matches the widget_id passed at construction."""
        em = EventEmitter("specific_id")
        em.emit("a")
        em.emit("b", x=1)
        em.emit("c")
        assert em.peek()["source"] == "specific_id"


class TestEventEmitterClear:
    """EventEmitter.clear() resets to None."""

    def test_clear_sets_none(self):
        em = EventEmitter("w")
        em.emit("something")
        assert em.peek() is not None
        em.clear()
        assert em.peek() is None

    def test_clear_on_already_none(self):
        em = EventEmitter("w")
        em.clear()
        assert em.peek() is None

    def test_emit_after_clear(self):
        em = EventEmitter("w")
        em.emit("first")
        em.clear()
        em.emit("second")
        assert em.peek()["action"] == "second"


class TestEventEmitterPeek:
    """EventEmitter.peek() reads without reactive context."""

    def test_peek_returns_none_initially(self):
        em = EventEmitter("w")
        assert em.peek() is None

    def test_peek_returns_last_emitted(self):
        em = EventEmitter("w")
        em.emit("hello", val=42)
        msg = em.peek()
        assert msg["action"] == "hello"
        assert msg["val"] == 42

    def test_peek_after_clear(self):
        em = EventEmitter("w")
        em.emit("x")
        em.clear()
        assert em.peek() is None

    def test_peek_matches_reactive_value(self):
        em = EventEmitter("w")
        em.emit("y", num=7)
        assert em.peek() is _peek(em.events)


# =====================================================================
#  2. WidgetAPI
# =====================================================================


class TestWidgetAPI:
    """WidgetAPI dataclass construction and access patterns."""

    def _make_api(self, widget_id="test"):
        from shiny import reactive
        return WidgetAPI(
            events=reactive.Value(None),
            data=reactive.Value(None),
            active_columns=reactive.Value([]),
            widget_id=widget_id,
        )

    def test_construction(self):
        api = self._make_api("editor1")
        assert api.widget_id == "editor1"

    def test_events_attribute_access(self):
        api = self._make_api()
        assert _peek(api.events) is None

    def test_data_attribute_access(self):
        api = self._make_api()
        assert _peek(api.data) is None

    def test_active_columns_attribute_access(self):
        api = self._make_api()
        assert _peek(api.active_columns) == []

    def test_dict_style_access_events(self):
        api = self._make_api()
        assert _peek(api["events"]) is None

    def test_dict_style_access_widget_id(self):
        api = self._make_api("ed2")
        assert api["widget_id"] == "ed2"

    def test_dict_style_access_data(self):
        api = self._make_api()
        assert _peek(api["data"]) is None

    def test_dict_style_access_missing_key(self):
        api = self._make_api()
        with pytest.raises(KeyError):
            api["nonexistent"]

    def test_default_widget_id(self):
        from shiny import reactive
        api = WidgetAPI(
            events=reactive.Value(None),
            data=reactive.Value(None),
            active_columns=reactive.Value([]),
        )
        assert api.widget_id == ""

    def test_extra_dict(self):
        from shiny import reactive
        api = WidgetAPI(
            events=reactive.Value(None),
            data=reactive.Value(None),
            active_columns=reactive.Value([]),
            _extra={"custom": "value"},
        )
        assert api["custom"] == "value"

    def test_extra_dict_key_error(self):
        from shiny import reactive
        api = WidgetAPI(
            events=reactive.Value(None),
            data=reactive.Value(None),
            active_columns=reactive.Value([]),
            _extra={},
        )
        with pytest.raises(KeyError):
            api["missing"]


# =====================================================================
#  3. Integration: EventEmitter + WidgetAPI
# =====================================================================


class TestEmitterWithWidgetAPI:
    """End-to-end: emitter publishes, WidgetAPI consumer reads."""

    def test_host_receives_event_via_api(self):
        from shiny import reactive
        em = EventEmitter("editor1")
        api = WidgetAPI(
            events=em.events,
            data=reactive.Value(None),
            active_columns=reactive.Value([]),
            widget_id=em.widget_id,
        )
        em.emit("review_detail", pk={"id": 1})
        msg = _peek(api.events)
        assert msg["action"] == "review_detail"
        assert msg["source"] == "editor1"
        assert msg["pk"] == {"id": 1}

    def test_clear_visible_via_api(self):
        from shiny import reactive
        em = EventEmitter("w")
        api = WidgetAPI(
            events=em.events,
            data=reactive.Value(None),
            active_columns=reactive.Value([]),
        )
        em.emit("x")
        assert _peek(api.events) is not None
        em.clear()
        assert _peek(api.events) is None

    def test_multiple_emitters_isolated(self):
        from shiny import reactive
        em1 = EventEmitter("a")
        em2 = EventEmitter("b")
        api1 = WidgetAPI(events=em1.events, data=reactive.Value(None), active_columns=reactive.Value([]))
        api2 = WidgetAPI(events=em2.events, data=reactive.Value(None), active_columns=reactive.Value([]))

        em1.emit("click", row=1)
        em2.emit("select", row=2)

        msg1 = _peek(api1.events)
        msg2 = _peek(api2.events)
        assert msg1["action"] == "click"
        assert msg1["row"] == 1
        assert msg2["action"] == "select"
        assert msg2["row"] == 2

    def test_rapid_emit_preserves_last(self):
        em = EventEmitter("w")
        for i in range(100):
            em.emit("tick", count=i)
        assert em.peek()["count"] == 99
        assert em.peek()["action"] == "tick"

    def test_api_reflects_live_emitter_state(self):
        """WidgetAPI.events points to same reactive.Value, always current."""
        from shiny import reactive
        em = EventEmitter("live")
        api = WidgetAPI(events=em.events, data=reactive.Value(None), active_columns=reactive.Value([]))

        em.emit("step1")
        assert _peek(api.events)["action"] == "step1"

        em.emit("step2", detail="x")
        assert _peek(api.events)["action"] == "step2"
        assert _peek(api.events)["detail"] == "x"

        em.clear()
        assert _peek(api.events) is None

    def test_widget_id_propagates_to_api(self):
        em = EventEmitter("propagated_id")
        from shiny import reactive
        api = WidgetAPI(
            events=em.events,
            data=reactive.Value(None),
            active_columns=reactive.Value([]),
            widget_id=em.widget_id,
        )
        assert api.widget_id == "propagated_id"
