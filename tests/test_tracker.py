"""Tests for src/utils/tracker — performance instrumentation helpers."""

import time

import pytest

from src.utils import tracker


@pytest.fixture(autouse=True)
def _reset_tracker():
    """Ensure tracker state is reset between tests."""
    tracker._enabled = False
    yield
    tracker._enabled = False


# ── is_enabled ────────────────────────────────────────────────

class TestIsEnabled:
    def test_disabled_by_default(self):
        assert tracker.is_enabled() is False

    def test_enabled_after_init(self):
        tracker.init(True)
        assert tracker.is_enabled() is True

    def test_disabled_after_init_false(self):
        tracker.init(True)
        tracker.init(False)
        assert tracker.is_enabled() is False


# ── track_sql ─────────────────────────────────────────────────

class TestTrackSql:
    def test_context_manager_runs_body_when_disabled(self):
        executed = False
        with tracker.track_sql("test_label", "SELECT 1"):
            executed = True
        assert executed

    def test_context_manager_runs_body_when_enabled(self):
        tracker.init(True)
        executed = False
        with tracker.track_sql("test_label", "SELECT 1"):
            executed = True
        assert executed

    def test_logs_start_and_end_when_enabled(self, capsys):
        tracker.init(True)
        with tracker.track_sql("fetch", "SELECT * FROM t"):
            pass
        out = capsys.readouterr().out
        assert "SQL  START  fetch" in out
        assert "SQL  END    fetch" in out
        assert "ms" in out

    def test_no_output_when_disabled(self, capsys):
        with tracker.track_sql("fetch", "SELECT 1"):
            pass
        out = capsys.readouterr().out
        # Only init message should be absent; no SQL lines
        assert "SQL" not in out

    def test_truncates_long_sql(self, capsys):
        tracker.init(True)
        long_sql = "SELECT " + "x" * 200
        with tracker.track_sql("long", long_sql):
            pass
        out = capsys.readouterr().out
        # Preview is capped at 120 chars
        assert "SQL  START  long" in out

    def test_handles_empty_sql(self, capsys):
        tracker.init(True)
        with tracker.track_sql("empty", ""):
            pass
        out = capsys.readouterr().out
        assert "SQL  START  empty" in out


# ── log_sql ───────────────────────────────────────────────────

class TestLogSql:
    def test_logs_when_enabled(self, capsys):
        tracker.init(True)
        tracker.log_sql("manual", "SELECT 1", 42.5)
        out = capsys.readouterr().out
        assert "SQL  manual" in out
        assert "42.5ms" in out

    def test_silent_when_disabled(self, capsys):
        tracker.log_sql("manual", "SELECT 1", 42.5)
        out = capsys.readouterr().out
        assert out == "" or "SQL" not in out

    def test_handles_empty_sql(self, capsys):
        tracker.init(True)
        tracker.log_sql("empty", "", 0.0)
        out = capsys.readouterr().out
        assert "SQL  empty" in out


# ── track_render ──────────────────────────────────────────────

class TestTrackRender:
    def test_context_manager_runs_body_when_disabled(self):
        executed = False
        with tracker.track_render("widget"):
            executed = True
        assert executed

    def test_context_manager_runs_body_when_enabled(self):
        tracker.init(True)
        executed = False
        with tracker.track_render("widget"):
            executed = True
        assert executed

    def test_logs_start_and_end_when_enabled(self, capsys):
        tracker.init(True)
        with tracker.track_render("table"):
            pass
        out = capsys.readouterr().out
        assert "RENDER START  table" in out
        assert "RENDER END    table" in out
        assert "ms" in out

    def test_no_output_when_disabled(self, capsys):
        with tracker.track_render("table"):
            pass
        out = capsys.readouterr().out
        assert "RENDER" not in out


# ── render_timer ──────────────────────────────────────────────

class TestRenderTimer:
    def test_decorator_returns_value_when_disabled(self):
        @tracker.render_timer("fn")
        def add(a, b):
            return a + b

        assert add(2, 3) == 5

    def test_decorator_returns_value_when_enabled(self):
        tracker.init(True)

        @tracker.render_timer("fn")
        def add(a, b):
            return a + b

        assert add(2, 3) == 5

    def test_decorator_logs_when_enabled(self, capsys):
        tracker.init(True)

        @tracker.render_timer("my_render")
        def noop():
            pass

        noop()
        out = capsys.readouterr().out
        assert "RENDER START  my_render" in out
        assert "RENDER END    my_render" in out

    def test_decorator_silent_when_disabled(self, capsys):
        @tracker.render_timer("my_render")
        def noop():
            pass

        noop()
        out = capsys.readouterr().out
        assert "RENDER" not in out

    def test_preserves_function_name(self):
        @tracker.render_timer("x")
        def my_function():
            """My docstring."""
            pass

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "My docstring."
