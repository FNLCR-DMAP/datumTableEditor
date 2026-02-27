"""
Database Operations for Epitopes Data Editor

High-level database operations that integrate:
- Query building
- Session book management
- Modification tracking
- State persistence
"""

import json
import logging
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Generator, Optional

import pandas as pd

try:
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import Engine
    from sqlalchemy.pool import QueuePool
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False

from .db_schema import DatabaseSchemaManager, TableSchema
from .query_builder import (
    FilterCondition,
    QueryBuilder,
    QueryContext,
    SortConfig,
    parse_filters_from_list,
)
from .session_book import SessionBook, SessionBookManager


logger = logging.getLogger(__name__)


@dataclass
class DatabaseConfig:
    """Database configuration."""
    connection_string: str
    data_table: str
    mods_table: str = "epitopes_modifications"
    state_table: str = "epitopes_ui_state"
    status_column: str = "Status"
    auto_detect_pk: bool = True
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30
    max_rows_per_page: int = 100
    default_rows_per_page: int = 25


@dataclass
class FetchResult:
    """Result from a fetch operation."""
    df: pd.DataFrame
    total_count: int
    page: int
    rows_per_page: int
    has_more: bool
    context_changed: bool
    new_rows_added: int


@dataclass
class ModificationRecord:
    """A modification record."""
    id: int
    row_pk: dict[str, Any]
    column_name: str
    old_value: Any
    new_value: Any
    mod_type: str
    created_by: Optional[str]
    created_at: datetime
    undone: bool = False


class DatabaseOperations:
    """
    High-level database operations with session book integration.
    
    This class provides the main interface for:
    - Fetching paginated data with session book
    - Saving modifications
    - Undoing modifications
    - Managing UI state
    """
    
    def __init__(self, config: DatabaseConfig):
        """
        Initialize database operations.
        
        Args:
            config: Database configuration
        """
        if not SQLALCHEMY_AVAILABLE:
            raise ImportError("SQLAlchemy is required for database operations")
        
        self.config = config
        self._engine: Optional[Engine] = None
        self._schema_manager: Optional[DatabaseSchemaManager] = None
        self._table_schema: Optional[TableSchema] = None
        self._query_builder: Optional[QueryBuilder] = None
        self._session_book_manager: Optional[SessionBookManager] = None
    
    def initialize(self) -> None:
        """Initialize database connection and schema."""
        # Create engine with connection pooling
        self._engine = create_engine(
            self.config.connection_string,
            poolclass=QueuePool,
            pool_size=self.config.pool_size,
            max_overflow=self.config.max_overflow,
            pool_timeout=self.config.pool_timeout,
            pool_pre_ping=True
        )
        
        # Initialize schema manager
        self._schema_manager = DatabaseSchemaManager(self._engine)
        
        # Get table schema
        self._table_schema = self._schema_manager.get_table_schema(
            self.config.data_table
        )
        
        if self._table_schema is None:
            raise ValueError(f"Table '{self.config.data_table}' not found")
        
        # Ensure mods and state tables exist
        self._schema_manager.ensure_tables_exist(
            self.config.data_table,
            self.config.mods_table,
            self.config.state_table
        )
        
        # Initialize query builder
        self._query_builder = QueryBuilder(
            data_table=self.config.data_table,
            mods_table=self.config.mods_table,
            primary_key=self._table_schema.primary_key,
            status_column=self.config.status_column,
            max_rows_per_page=self.config.max_rows_per_page,
        )
        
        # Initialize session book manager
        self._session_book_manager = SessionBookManager(
            self._table_schema.primary_key
        )
        
        logger.info(
            f"Database initialized: table={self.config.data_table}, "
            f"pk={self._table_schema.primary_key}"
        )
    
    @contextmanager
    def _connection(self) -> Generator:
        """Get a database connection from the pool."""
        if self._engine is None:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        
        with self._engine.connect() as conn:
            yield conn
    
    @property
    def primary_key(self) -> list[str]:
        """Get the primary key columns."""
        if self._table_schema is None:
            raise RuntimeError("Database not initialized")
        return self._table_schema.primary_key
    
    @property
    def columns(self) -> list[str]:
        """Get all column names."""
        if self._table_schema is None:
            raise RuntimeError("Database not initialized")
        return self._table_schema.get_column_names()
    
    def get_session_book(self, session_id: str) -> SessionBook:
        """Get session book for a session."""
        if self._session_book_manager is None:
            raise RuntimeError("Database not initialized")
        return self._session_book_manager.get_book(session_id)
    
    def fetch_page(
        self,
        session_id: str,
        filters: Optional[list[dict]] = None,
        sort_column: Optional[str] = None,
        sort_ascending: bool = True,
        page: int = 1,
        rows_per_page: int = 25,
        force_refresh: bool = False
    ) -> FetchResult:
        """
        Fetch a page of data, using session book for consistency.
        
        Args:
            session_id: Session identifier
            filters: List of filter dicts
            sort_column: Column to sort by
            sort_ascending: Sort direction
            page: Page number (1-indexed)
            rows_per_page: Rows per page
            force_refresh: Force reload even if data is cached
            
        Returns:
            FetchResult with data and metadata
        """
        if self._query_builder is None:
            raise RuntimeError("Database not initialized")
        
        # Build query context
        filter_conditions = parse_filters_from_list(filters) if filters else []
        sort_config = SortConfig(sort_column, sort_ascending) if sort_column else None
        context = QueryContext(filters=filter_conditions, sort=sort_config)
        
        # Get session book
        book = self.get_session_book(session_id)
        
        # Check if context changed
        context_changed = book.set_context(context.get_hash())
        
        if context_changed:
            logger.info(f"Context changed for session {session_id}, clearing book")
        
        # If we have cached data and don't need this page yet, return from cache
        if not force_refresh and not context_changed:
            if book.row_count >= page * rows_per_page:
                # We have enough cached data
                df = book.to_dataframe()
                start_idx = (page - 1) * rows_per_page
                end_idx = start_idx + rows_per_page
                page_df = df.iloc[start_idx:end_idx]
                
                return FetchResult(
                    df=page_df,
                    total_count=book.row_count,
                    page=page,
                    rows_per_page=rows_per_page,
                    has_more=book.has_more_pages() or end_idx < book.row_count,
                    context_changed=False,
                    new_rows_added=0
                )
        
        # Fetch from database
        sql, params = self._query_builder.build_select_query(
            filters=filter_conditions,
            sort=sort_config,
            page=page,
            limit=rows_per_page,
            include_mods_status=True
        )
        
        with self._connection() as conn:
            result = conn.execute(text(sql), params)
            rows = result.fetchall()
            columns = result.keys()
        
        # Convert to DataFrame
        df = pd.DataFrame(rows, columns=columns)
        
        # Get total count
        count_sql, count_params = self._query_builder.build_count_query(filter_conditions)
        with self._connection() as conn:
            result = conn.execute(text(count_sql), count_params)
            total_count = result.scalar()
        
        # Determine if there are more pages
        has_more = (page * rows_per_page) < total_count
        
        # Append to session book
        new_rows = book.append_page(df, page, has_more)
        
        return FetchResult(
            df=df,
            total_count=total_count,
            page=page,
            rows_per_page=rows_per_page,
            has_more=has_more,
            context_changed=context_changed,
            new_rows_added=new_rows
        )
    
    def get_all_session_data(self, session_id: str) -> pd.DataFrame:
        """
        Get all data currently in the session book.
        
        Args:
            session_id: Session identifier
            
        Returns:
            DataFrame with all session data in local order
        """
        book = self.get_session_book(session_id)
        return book.to_dataframe()
    
    def save_modification(
        self,
        session_id: str,
        pk_values: dict[str, Any],
        column_name: str,
        old_value: Any,
        new_value: Any,
        mod_type: str = "field_modification",
        created_by: Optional[str] = None
    ) -> int:
        """
        Save a modification to the database.
        
        Args:
            session_id: Session identifier
            pk_values: Primary key values for the row
            column_name: Column that was modified
            old_value: Previous value
            new_value: New value
            mod_type: Type of modification
            created_by: User identifier
            
        Returns:
            Modification ID
        """
        if self._query_builder is None:
            raise RuntimeError("Database not initialized")
        
        sql = self._query_builder.build_insert_modification()
        
        with self._connection() as conn:
            result = conn.execute(
                text(sql),
                {
                    "row_pk": json.dumps(pk_values, sort_keys=True),
                    "column_name": column_name,
                    "old_value": json.dumps(old_value) if old_value is not None else None,
                    "new_value": json.dumps(new_value) if new_value is not None else None,
                    "mod_type": mod_type,
                    "created_by": created_by
                }
            )
            mod_id = result.scalar()
            conn.commit()
        
        # Update session book
        book = self.get_session_book(session_id)
        book.update_row(pk_values, {column_name: new_value})
        
        logger.info(
            f"Saved modification {mod_id}: {pk_values}.{column_name} = {new_value}"
        )
        
        return mod_id
    
    def undo_modification(
        self,
        session_id: str,
        mod_id: int,
        pk_values: dict[str, Any],
        column_name: str,
        old_value: Any
    ) -> bool:
        """
        Undo a modification.
        
        Args:
            session_id: Session identifier
            mod_id: Modification ID to undo
            pk_values: Primary key values for the row
            column_name: Column that was modified
            old_value: Value to restore
            
        Returns:
            True if undo succeeded
        """
        if self._query_builder is None:
            raise RuntimeError("Database not initialized")
        
        sql = self._query_builder.build_undo_modification()
        
        with self._connection() as conn:
            result = conn.execute(text(sql), {"mod_id": mod_id})
            success = result.rowcount > 0
            conn.commit()
        
        if success:
            # Update session book
            book = self.get_session_book(session_id)
            book.update_row(pk_values, {column_name: old_value})
            
            logger.info(f"Undone modification {mod_id}")
        
        return success
    
    def get_modifications_for_row(
        self,
        pk_values: dict[str, Any]
    ) -> list[ModificationRecord]:
        """
        Get all modifications for a specific row.
        
        Args:
            pk_values: Primary key values for the row
            
        Returns:
            List of modification records
        """
        if self._query_builder is None:
            raise RuntimeError("Database not initialized")
        
        sql = self._query_builder.build_get_modifications_for_row()
        
        with self._connection() as conn:
            result = conn.execute(
                text(sql),
                {"row_pk": json.dumps(pk_values, sort_keys=True)}
            )
            rows = result.fetchall()
        
        return [
            ModificationRecord(
                id=row.id,
                row_pk=json.loads(row.row_pk),
                column_name=row.column_name,
                old_value=json.loads(row.old_value) if row.old_value else None,
                new_value=json.loads(row.new_value) if row.new_value else None,
                mod_type=row.mod_type,
                created_by=row.created_by,
                created_at=row.created_at,
                undone=row.undone
            )
            for row in rows
        ]
    
    def save_ui_state(
        self,
        user_id: str,
        session_id: str,
        filters: Optional[list[dict]] = None,
        sort_column: Optional[str] = None,
        sort_ascending: bool = True,
        current_page: int = 1,
        rows_per_page: int = 25,
        column_preset: Optional[str] = None
    ) -> None:
        """
        Save UI state to database.
        
        Args:
            user_id: User identifier
            session_id: Session identifier
            filters: Current filters
            sort_column: Current sort column
            sort_ascending: Sort direction
            current_page: Current page number
            rows_per_page: Rows per page setting
            column_preset: Active column preset name
        """
        if self._query_builder is None:
            raise RuntimeError("Database not initialized")
        
        sql = self._query_builder.build_upsert_state(self.config.state_table)
        
        with self._connection() as conn:
            conn.execute(
                text(sql),
                {
                    "user_id": user_id,
                    "session_id": session_id,
                    "filters": json.dumps(filters) if filters else None,
                    "sort_column": sort_column,
                    "sort_ascending": sort_ascending,
                    "current_page": current_page,
                    "rows_per_page": rows_per_page,
                    "column_preset": column_preset
                }
            )
            conn.commit()
        
        logger.debug(f"Saved UI state for {user_id}/{session_id}")
    
    def load_ui_state(
        self,
        user_id: str,
        session_id: str
    ) -> Optional[dict]:
        """
        Load UI state from database.
        
        Args:
            user_id: User identifier
            session_id: Session identifier
            
        Returns:
            State dict or None if not found
        """
        if self._query_builder is None:
            raise RuntimeError("Database not initialized")
        
        sql = self._query_builder.build_get_state(self.config.state_table)
        
        with self._connection() as conn:
            result = conn.execute(
                text(sql),
                {"user_id": user_id, "session_id": session_id}
            )
            row = result.fetchone()
        
        if row is None:
            return None
        
        return {
            "filters": json.loads(row.filters) if row.filters else None,
            "sort_column": row.sort_column,
            "sort_ascending": row.sort_ascending,
            "current_page": row.current_page,
            "rows_per_page": row.rows_per_page,
            "column_preset": row.column_preset,
            "updated_at": row.updated_at
        }
    
    def clear_session(self, session_id: str) -> None:
        """Clear a session's data from memory."""
        if self._session_book_manager:
            self._session_book_manager.remove_book(session_id)
    
    def close(self) -> None:
        """Close database connections."""
        if self._engine:
            self._engine.dispose()
            self._engine = None
        
        if self._session_book_manager:
            self._session_book_manager.clear_all()
        
        logger.info("Database connections closed")


# Module-level instance for singleton pattern
_db_ops: Optional[DatabaseOperations] = None


def get_database_operations(config: Optional[DatabaseConfig] = None) -> DatabaseOperations:
    """
    Get the singleton DatabaseOperations instance.
    
    Args:
        config: Database configuration (required on first call)
        
    Returns:
        DatabaseOperations instance
    """
    global _db_ops
    
    if _db_ops is None:
        if config is None:
            raise ValueError("Config required on first call to get_database_operations")
        _db_ops = DatabaseOperations(config)
        _db_ops.initialize()
    
    return _db_ops


def reset_database_operations() -> None:
    """Reset the singleton instance (for testing)."""
    global _db_ops
    if _db_ops:
        _db_ops.close()
    _db_ops = None
