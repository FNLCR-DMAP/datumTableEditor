"""
Database module for Epitopes Data Editor

Provides PostgreSQL-driven data access with:
- Auto-detect primary key and schema
- Modifications stored in separate mods_table
- Session book for in-memory UI consistency
- Parameterized queries with pagination
"""

from .db_schema import (
    ColumnInfo,
    DatabaseSchemaManager,
    TableSchema,
    get_schema_manager,
)
from .query_builder import (
    FilterCondition,
    QueryBuilder,
    QueryContext,
    SortConfig,
    build_search_filter,
    parse_filter_from_dict,
    parse_filters_from_list,
)
from .session_book import (
    PageInfo,
    RowEntry,
    SessionBook,
    SessionBookManager,
)
from .db_operations import (
    DatabaseConfig,
    DatabaseOperations,
    FetchResult,
    ModificationRecord,
    get_database_operations,
    reset_database_operations,
)
from .user_presets import (
    UserPresetsService,
    get_user_preset_table_name,
    create_user_preset_table,
    save_user_preset,
    load_user_presets,
    get_default_preset,
    delete_user_preset,
    list_user_preset_tables,
)

__all__ = [
    # Schema
    "ColumnInfo",
    "DatabaseSchemaManager",
    "TableSchema",
    "get_schema_manager",
    # Query Builder
    "FilterCondition",
    "QueryBuilder",
    "QueryContext",
    "SortConfig",
    "build_search_filter",
    "parse_filter_from_dict",
    "parse_filters_from_list",
    # Session Book
    "PageInfo",
    "RowEntry",
    "SessionBook",
    "SessionBookManager",
    # Operations
    "DatabaseConfig",
    "DatabaseOperations",
    "FetchResult",
    "ModificationRecord",
    "get_database_operations",
    "reset_database_operations",
    # User Presets
    "UserPresetsService",
    "get_user_preset_table_name",
    "create_user_preset_table",
    "save_user_preset",
    "load_user_presets",
    "get_default_preset",
    "delete_user_preset",
    "list_user_preset_tables",
]
