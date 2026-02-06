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

__all__ = [
    "AppConfig",
    "DataSourceConfig",
    "DatabaseConfig",
    "TableConfig",
    "StateConfig",
    "load_config",
]
