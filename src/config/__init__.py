"""
Configuration module for Epitopes Data Editor.
Contains app configuration schema and settings.
"""

from .app_config_schema import (
    AppConfig,
    DataSourceConfig,
    DatabaseConfig,
    TableConfig,
    StateConfig,
    load_config,
)

# Instance-based config (for widgets) - import first to avoid circular import
from .config_instance import ConfigInstance, load_config_instance

# Note: config.py has module-level loading which may cause issues
# For widget-based usage, prefer ConfigInstance
# These exports are for backward compatibility
def _lazy_import_config():
    from .config import (
        app_config,
        df_original,
        all_columns,
        display_columns,
        data_dir,
        ensure_data_dir,
        modifications_log_path,
        load_modifications_log,
        save_modification_to_db,
        mark_modification_undone_in_db,
        save_ui_state,
        load_ui_state,
        load_data_from_source,
    )
    return {
        "app_config": app_config,
        "df_original": df_original,
        "all_columns": all_columns,
        "display_columns": display_columns,
        "data_dir": data_dir,
        "ensure_data_dir": ensure_data_dir,
        "modifications_log_path": modifications_log_path,
        "load_modifications_log": load_modifications_log,
        "save_modification_to_db": save_modification_to_db,
        "mark_modification_undone_in_db": mark_modification_undone_in_db,
        "save_ui_state": save_ui_state,
        "load_ui_state": load_ui_state,
        "load_data_from_source": load_data_from_source,
    }

__all__ = [
    "AppConfig",
    "DataSourceConfig",
    "DatabaseConfig",
    "TableConfig",
    "StateConfig",
    "load_config",
    # Instance-based config (for widgets)
    "ConfigInstance",
    "load_config_instance",
    # Runtime config exports (global defaults, lazy-loaded)
    "app_config",
    "df_original",
    "all_columns",
    "display_columns",
    "data_dir",
    "ensure_data_dir",
    "modifications_log_path",
    "load_modifications_log",
    "save_modification_to_db",
    "mark_modification_undone_in_db",
    "save_ui_state",
    "load_ui_state",
    "load_data_from_source",
]

def __getattr__(name):
    """Lazy import for backward compatibility with config.py globals."""
    _lazy_config_names = {
        "app_config", "df_original", "all_columns", "display_columns",
        "data_dir", "ensure_data_dir", "modifications_log_path", "load_modifications_log",
        "save_modification_to_db", "mark_modification_undone_in_db",
        "save_ui_state", "load_ui_state", "load_data_from_source",
    }
    if name in _lazy_config_names:
        config_exports = _lazy_import_config()
        return config_exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
