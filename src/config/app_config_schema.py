"""
App Configuration Schema for Epitopes Data Editor

This module provides a centralized, configurable schema for all external 
dependencies: data sources, persistence, queries, state management, and table defaults.

Configuration can be loaded from:
1. app_config.json (file-based)
2. Environment variables (for sensitive data)
3. URL parameters (for iframe embedding)
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal, Optional


# =============================================================================
# Configuration Data Classes
# =============================================================================

@dataclass
class DataSourceConfig:
    """Configuration for data source."""
    
    # Source type: 'csv', 'json', 'api', 'database'
    source_type: Literal["csv", "json", "api", "database"] = "csv"
    
    # Table/dataset name (identifier for the data being worked with)
    table_name: str = "data"
    
    # File path (for csv/json)
    file_path: Optional[str] = None
    
    # API endpoint (for api source)
    api_url: Optional[str] = None
    api_headers: dict[str, str] = field(default_factory=dict)
    api_method: str = "GET"
    
    # Database connection (for database source)
    db_connection_string: Optional[str] = None
    db_query: Optional[str] = None
    db_table: Optional[str] = None
    
    # Data transformation
    date_columns: list[str] = field(default_factory=list)
    numeric_columns: list[str] = field(default_factory=list)


@dataclass
class PersistenceConfig:
    """Configuration for data persistence (saves/modifications)."""
    
    # Persistence type: 'local', 'api', 'database'
    persistence_type: Literal["local", "api", "database"] = "local"
    
    # Local file paths
    modifications_log_path: Optional[str] = None
    data_state_path: Optional[str] = None
    export_path: Optional[str] = None
    
    # API persistence
    api_save_url: Optional[str] = None
    api_headers: dict[str, str] = field(default_factory=dict)
    
    # Database persistence
    db_connection_string: Optional[str] = None
    db_modifications_table: Optional[str] = None
    
    # Auto-save settings
    auto_save: bool = True
    auto_save_interval_ms: int = 0  # 0 = immediate


@dataclass
class QueryConfig:
    """Configuration for search/filter queries."""
    
    # Searchable columns (empty = all text columns)
    searchable_columns: list[str] = field(default_factory=list)
    
    # Filterable columns with filter types
    filter_columns: dict[str, Literal["text", "numeric", "date", "select"]] = field(default_factory=dict)
    
    # Default filters applied on load
    default_filters: dict[str, Any] = field(default_factory=dict)
    
    # Search settings
    search_case_sensitive: bool = False
    search_regex_enabled: bool = False
    
    # Status filter options
    status_filter_enabled: bool = True
    status_column: str = "Status"


@dataclass
class StateConfig:
    """Configuration for state management."""
    
    # State persistence
    persist_state: bool = True
    state_storage: Literal["local", "session", "url"] = "local"
    state_file_path: Optional[str] = None
    
    # What to persist
    persist_filters: bool = True
    persist_sort: bool = True
    persist_page: bool = True
    persist_column_selection: bool = True
    persist_column_widths: bool = True
    
    # Session settings
    session_timeout_minutes: int = 30


@dataclass
class TableConfig:
    """Configuration for table display defaults."""
    
    # Table display title
    title: str = "Data Table"
    
    # Primary key column(s) for row identification
    primary_key: list[str] = field(default_factory=lambda: ["id"])
    
    # Default visible columns (empty = all columns)
    default_columns: list[str] = field(default_factory=list)
    
    # Column widths (column_name: width_px)
    default_column_widths: dict[str, int] = field(default_factory=dict)
    
    # Default sort
    default_sort_column: Optional[str] = None
    default_sort_ascending: bool = True
    
    # Pagination
    default_rows_per_page: int = 25
    rows_per_page_options: list[int | str] = field(default_factory=lambda: [10, 25, 50, 100, "all"])
    
    # Editable columns (empty = all columns editable)
    editable_columns: list[str] = field(default_factory=list)
    readonly_columns: list[str] = field(default_factory=list)
    
    # Column presets
    presets_enabled: bool = True
    presets_file_path: Optional[str] = None
    default_preset: str = "Default"


@dataclass
class DatabaseConfig:
    """Configuration for PostgreSQL database connection."""
    
    # Enable database mode (if False, uses local CSV mode)
    enabled: bool = False
    
    # Mode: "direct" for SQLAlchemy, "datum" for Datum proxy service
    mode: str = "direct"
    
    # Direct mode: SQLAlchemy connection settings
    connection_string: Optional[str] = None
    
    # Datum mode: Proxy service settings
    datum_base_url: Optional[str] = None
    datum_token: Optional[str] = None
    datum_service_name: str = "postgres_sql"
    datum_database: Optional[str] = None
    datum_schema: Optional[str] = None
    
    # Table names
    data_table: str = "epitopes_data"
    mods_table: str = "epitopes_modifications"
    state_table: str = "epitopes_ui_state"
    
    # Column settings
    status_column: str = "Status"
    auto_detect_pk: bool = True
    
    # Connection pool settings (direct mode only)
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30
    
    # Pagination settings
    max_rows_per_page: int = 100
    default_rows_per_page: int = 25


@dataclass
class AppConfig:
    """Master configuration combining all sections."""
    
    # App metadata
    app_title: str = "Epitopes Data Editor"
    app_version: str = "1.0.0"
    
    # Sub-configurations
    data_source: DataSourceConfig = field(default_factory=DataSourceConfig)
    persistence: PersistenceConfig = field(default_factory=PersistenceConfig)
    query: QueryConfig = field(default_factory=QueryConfig)
    state: StateConfig = field(default_factory=StateConfig)
    table: TableConfig = field(default_factory=TableConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    
    # Feature flags
    enable_approval_workflow: bool = True
    enable_export: bool = True
    enable_undo: bool = True
    enable_copy_column: bool = True


# =============================================================================
# Configuration Loader
# =============================================================================

def load_config(config_path: Optional[Path] = None, username: Optional[str] = None) -> AppConfig:
    """
    Load configuration from file, environment variables, and defaults.
    
    Priority (highest to lowest):
    1. Environment variables (APP_CONFIG_*)
    2. Config file (app_config.json)
    3. Default values
    """
    config = AppConfig()
    
    # Determine config file path (look in project root - 3 levels up from this file)
    # src/config/app_config_schema.py -> src/config -> src -> project_root
    if config_path is None:
        config_path = Path(__file__).parent.parent.parent / "app_config.json"
    elif isinstance(config_path, str):
        config_path = Path(config_path)
    
    # Load from file if exists
    if config_path.exists():
        with open(config_path, "r") as f:
            file_config = json.load(f)
        config = _merge_config(config, file_config, username=username)
    
    # Override with environment variables
    config = _apply_env_overrides(config, username=username)
    
    return config


def _merge_config(config: AppConfig, file_config: dict, username: Optional[str] = None) -> AppConfig:
    """Merge file configuration into AppConfig."""
    
    if "app_title" in file_config:
        config.app_title = file_config["app_title"]
    if "app_version" in file_config:
        config.app_version = file_config["app_version"]
    
    # Data source
    if "data_source" in file_config:
        ds = file_config["data_source"]
        config.data_source.source_type = ds.get("source_type", config.data_source.source_type)
        config.data_source.table_name = ds.get("table_name", config.data_source.table_name)
        config.data_source.file_path = ds.get("file_path", config.data_source.file_path)
        config.data_source.api_url = ds.get("api_url", config.data_source.api_url)
        config.data_source.api_headers = ds.get("api_headers", config.data_source.api_headers)
        config.data_source.db_connection_string = ds.get("db_connection_string")
        config.data_source.db_query = ds.get("db_query")
        config.data_source.db_table = ds.get("db_table")
    
    # Persistence
    if "persistence" in file_config:
        ps = file_config["persistence"]
        config.persistence.persistence_type = ps.get("persistence_type", config.persistence.persistence_type)
        config.persistence.modifications_log_path = ps.get("modifications_log_path")
        config.persistence.data_state_path = ps.get("data_state_path")
        config.persistence.export_path = ps.get("export_path")
        config.persistence.api_save_url = ps.get("api_save_url")
        config.persistence.auto_save = ps.get("auto_save", config.persistence.auto_save)
    
    # Query
    if "query" in file_config:
        qs = file_config["query"]
        config.query.searchable_columns = qs.get("searchable_columns", config.query.searchable_columns)
        config.query.filter_columns = qs.get("filter_columns", config.query.filter_columns)
        config.query.default_filters = qs.get("default_filters", config.query.default_filters)
        config.query.status_column = qs.get("status_column", config.query.status_column)
    
    # State
    if "state" in file_config:
        st = file_config["state"]
        config.state.persist_state = st.get("persist_state", config.state.persist_state)
        config.state.state_storage = st.get("state_storage", config.state.state_storage)
        config.state.state_file_path = st.get("state_file_path")
    
    # Table
    if "table" in file_config:
        tb = file_config["table"]
        config.table.title = tb.get("title", config.table.title)
        config.table.primary_key = tb.get("primary_key", config.table.primary_key)
        config.table.default_columns = tb.get("default_columns", config.table.default_columns)
        config.table.default_column_widths = tb.get("default_column_widths", config.table.default_column_widths)
        config.table.default_sort_column = tb.get("default_sort_column")
        config.table.default_sort_ascending = tb.get("default_sort_ascending", config.table.default_sort_ascending)
        config.table.default_rows_per_page = tb.get("default_rows_per_page", config.table.default_rows_per_page)
        config.table.editable_columns = tb.get("editable_columns", config.table.editable_columns)
        config.table.readonly_columns = tb.get("readonly_columns", config.table.readonly_columns)
        config.table.presets_file_path = tb.get("presets_file_path")
        config.table.default_preset = tb.get("default_preset", config.table.default_preset)
    
    # Database
    if "database" in file_config:
        db = file_config["database"]
        config.database.enabled = db.get("enabled", config.database.enabled)
        config.database.mode = db.get("mode", config.database.mode)
        config.database.connection_string = db.get("connection_string")
        config.database.datum_base_url = db.get("datum_base_url")
        config.database.datum_token = db.get("datum_token")
        config.database.datum_service_name = db.get("datum_service_name", config.database.datum_service_name)
        config.database.datum_database = db.get("datum_database")
        config.database.datum_schema = db.get("datum_schema")
        config.database.data_table = db.get("data_table", config.database.data_table)
        config.database.mods_table = db.get("mods_table", config.database.mods_table)
        config.database.state_table = db.get("state_table", config.database.state_table)
        if username:
            # Personalize state table per user (use underscore to avoid cross-database reference)
            config.database.state_table = f"{config.database.state_table}_{username}"
        config.database.status_column = db.get("status_column", config.database.status_column)
        config.database.auto_detect_pk = db.get("auto_detect_pk", config.database.auto_detect_pk)
        config.database.pool_size = db.get("pool_size", config.database.pool_size)
        config.database.max_overflow = db.get("max_overflow", config.database.max_overflow)
        config.database.pool_timeout = db.get("pool_timeout", config.database.pool_timeout)
        config.database.max_rows_per_page = db.get("max_rows_per_page", config.database.max_rows_per_page)
        config.database.default_rows_per_page = db.get("default_rows_per_page", config.database.default_rows_per_page)
    
    # Feature flags
    config.enable_approval_workflow = file_config.get("enable_approval_workflow", config.enable_approval_workflow)
    config.enable_export = file_config.get("enable_export", config.enable_export)
    config.enable_undo = file_config.get("enable_undo", config.enable_undo)
    
    return config


def _apply_env_overrides(config: AppConfig, username: Optional[str] = None) -> AppConfig:
    """Apply environment variable overrides."""
    
    # Data source overrides
    if os.environ.get("APP_DATA_SOURCE_TYPE"):
        config.data_source.source_type = os.environ["APP_DATA_SOURCE_TYPE"]
    if os.environ.get("APP_DATA_FILE_PATH"):
        config.data_source.file_path = os.environ["APP_DATA_FILE_PATH"]
    if os.environ.get("APP_DATA_API_URL"):
        config.data_source.api_url = os.environ["APP_DATA_API_URL"]
    if os.environ.get("APP_DB_CONNECTION_STRING"):
        config.data_source.db_connection_string = os.environ["APP_DB_CONNECTION_STRING"]
    
    # Persistence overrides
    if os.environ.get("APP_PERSISTENCE_TYPE"):
        config.persistence.persistence_type = os.environ["APP_PERSISTENCE_TYPE"]
    if os.environ.get("APP_MODIFICATIONS_LOG_PATH"):
        config.persistence.modifications_log_path = os.environ["APP_MODIFICATIONS_LOG_PATH"]
    if os.environ.get("APP_SAVE_API_URL"):
        config.persistence.api_save_url = os.environ["APP_SAVE_API_URL"]
    
    # Database overrides
    if os.environ.get("APP_DATABASE_ENABLED"):
        config.database.enabled = os.environ["APP_DATABASE_ENABLED"].lower() in ("true", "1", "yes")
    if os.environ.get("APP_DB_CONNECTION_STRING"):
        config.database.connection_string = os.environ["APP_DB_CONNECTION_STRING"]
    if os.environ.get("APP_DB_DATA_TABLE"):
        config.database.data_table = os.environ["APP_DB_DATA_TABLE"]
    if os.environ.get("APP_DB_MODS_TABLE"):
        config.database.mods_table = os.environ["APP_DB_MODS_TABLE"]
    if os.environ.get("APP_DB_STATE_TABLE"):
        config.database.state_table = os.environ["APP_DB_STATE_TABLE"]
        if username:
            # Personalize state table per user
            config.database.state_table = f"{config.database.state_table}_{username}"
    
    return config


# =============================================================================
# Configuration Export (for documentation/validation)
# =============================================================================

def export_config_schema() -> dict:
    """Export configuration schema as JSON for documentation."""
    return {
        "app_title": "string",
        "app_version": "string",
        "data_source": {
            "source_type": "csv | json | api | database",
            "table_name": "string (identifier for the table/dataset)",
            "file_path": "string (path to data file)",
            "api_url": "string (API endpoint for data fetch)",
            "api_headers": "object (HTTP headers)",
            "db_connection_string": "string (database connection)",
            "db_query": "string (SQL query)",
            "db_table": "string (table name)",
        },
        "persistence": {
            "persistence_type": "local | api | database",
            "modifications_log_path": "string (path to log file)",
            "data_state_path": "string (path to state file)",
            "api_save_url": "string (API endpoint for saving)",
            "auto_save": "boolean",
        },
        "query": {
            "searchable_columns": "array of column names",
            "filter_columns": "object {column: filter_type}",
            "default_filters": "object {column: value}",
            "status_column": "string",
        },
        "state": {
            "persist_state": "boolean",
            "state_storage": "local | session | url",
            "state_file_path": "string",
        },
        "table": {
            "primary_key": "array of column names",
            "default_columns": "array of column names",
            "default_column_widths": "object {column: width_px}",
            "default_sort_column": "string",
            "default_sort_ascending": "boolean",
            "default_rows_per_page": "number",
            "editable_columns": "array of column names",
            "readonly_columns": "array of column names",
            "presets_file_path": "string",
            "default_preset": "string",
        },
        "database": {
            "enabled": "boolean (enable PostgreSQL mode)",
            "connection_string": "string (PostgreSQL connection string)",
            "data_table": "string (main data table name)",
            "mods_table": "string (modifications tracking table)",
            "state_table": "string (UI state persistence table)",
            "status_column": "string (column for modification status)",
            "auto_detect_pk": "boolean (auto-detect primary key from DB)",
            "pool_size": "number (connection pool size)",
            "max_overflow": "number (max pool overflow connections)",
            "pool_timeout": "number (seconds to wait for connection)",
            "max_rows_per_page": "number (max rows per page, hard limit 100)",
            "default_rows_per_page": "number (default rows per page)",
        },
        "enable_approval_workflow": "boolean",
        "enable_export": "boolean",
        "enable_undo": "boolean",
    }
