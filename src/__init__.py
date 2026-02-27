"""
dmapTableEditor - A reusable PyShiny table editor widget

Usage:
    from dmapTableEditor import table_editor_ui, table_editor_server
    
    # In your app UI
    table_editor_ui("my_editor")
    
    # In your app server
    table_editor_server("my_editor", config_path="app_config.json")
"""

from .ui import create_app_ui as table_editor_ui
from .server import create_server as table_editor_server
from .config.config_instance import load_config_instance, ConfigInstance
from .config.app_config_schema import AppConfig, load_config
from .commute import EventEmitter, WidgetAPI

__version__ = "0.1.0"

__all__ = [
    "table_editor_ui",
    "table_editor_server",
    "load_config_instance",
    "ConfigInstance",
    "AppConfig",
    "load_config",
    "EventEmitter",
    "WidgetAPI",
    "__version__",
]
