"""
Table Editor Shiny Module

Wrapper around src/ui.py and src/server/ package to enable module pattern.
This allows the table editor to be used as a reusable widget.

Usage:
    from dmapTableEditor.widgets import table_editor_ui, table_editor_server
    
    # In UI:
    table_editor_ui("editor1", config_path="config1.json")
    
    # In server:
    api = table_editor_server("editor1", config_path="config1.json")

    # Access the WidgetAPI:
    @reactive.Effect
    def watch():
        event = api.events.get()
        if event and event["action"] == "review_detail":
            print(event["pk"])
"""

from shiny import module

from ..ui import create_app_ui
from ..server import create_server


@module.ui
def table_editor_ui(config_path: str = "app_config.json"):
    """
    Module UI - wraps create_app_ui().
    
    Args:
        config_path: Path to the config JSON file for this widget instance
    
    Returns the complete table editor UI with:
    - Split panel layout (sidebar + main content)
    - Column customization
    - Search and filter controls
    - Modifications log
    - Cell edit modal
    """
    return create_app_ui(config_path=config_path)


@module.server
def table_editor_server(input, output, session, config_path: str = "app_config.json"):
    """
    Module server - wraps create_server().
    
    Args:
        config_path: Path to the config JSON file for this widget instance
    
    Returns:
        WidgetAPI with .events (reactive.Value), .data, .active_columns, .widget_id
    
    Provides all table editor functionality:
    - Data display and editing
    - Approval/rejection workflow
    - Undo support
    - Export capabilities
    - Pagination and sorting
    """
    return create_server(input, output, session, config_path=config_path)
