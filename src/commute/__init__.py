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

    from dmapTableEditor.widgets import table_editor_ui, table_editor_server

    app_ui = ui.page_fluid(
        table_editor_ui("editor1", config_path="app_config.json"),
    )

    def server(input, output, session):
        api = table_editor_server("editor1", config_path="app_config.json")

        @reactive.effect
        def _on_event():
            event = api.events.get()
            if event and event["action"] == "review_detail":
                print(event["pk"])
"""

from .emitter import EventEmitter, WidgetAPI

__all__ = ["EventEmitter", "WidgetAPI"]
