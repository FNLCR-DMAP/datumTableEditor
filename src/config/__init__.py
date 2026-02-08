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

from .config import (
    app_config,
    df_original,
    all_columns,
    display_columns,
    data_dir,
    modifications_log_path,
    load_modifications_log,
    save_modification_to_db,
    mark_modification_undone_in_db,
    save_ui_state,
    load_ui_state,
    load_data_from_source,
)

__all__ = [
    "AppConfig",
    "DataSourceConfig",
    "DatabaseConfig",
    "TableConfig",
    "StateConfig",
    "load_config",
    # Runtime config exports
    "app_config",
    "df_original",
    "all_columns",
    "display_columns",
    "data_dir",
    "modifications_log_path",
    "load_modifications_log",
    "save_modification_to_db",
    "mark_modification_undone_in_db",
    "save_ui_state",
    "load_ui_state",
    "load_data_from_source",
]
