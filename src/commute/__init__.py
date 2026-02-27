"""
commute — Widget event communication layer.

Provides a lightweight event-emitter built on ``shiny.reactive.Value``
so that a table-editor widget can publish actions (e.g. "review_detail")
and the host application can subscribe to them without tight coupling.

Usage inside the widget (server.py)::

    from .commute import EventEmitter
    emitter = EventEmitter(widget_id="editor1")
    emitter.emit("review_detail", pk={"PatientID": "ABC"})

Usage in the host app::

    editor1 = table_editor_server("editor1", ...)
    # editor1["events"] is the reactive.Value

    @reactive.effect
    def _on_event():
        msg = editor1["events"].get()
        if msg and msg["action"] == "review_detail":
            open_detail_tab(msg["pk"])
"""

from .emitter import EventEmitter, WidgetAPI

__all__ = ["EventEmitter", "WidgetAPI"]
