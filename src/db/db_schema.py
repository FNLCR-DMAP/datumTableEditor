"""
Database Schema Manager for Epitopes Data Editor

Auto-detects schema from PostgreSQL:
- Primary key columns
- Column names, types, and order
- Creates mods_table and state_table if not exist
"""

import json
import os
from dataclasses import dataclass, field
from typing import Any, Optional

try:
    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.engine import Engine
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False


@dataclass
class ColumnInfo:
    """Information about a database column."""
    name: str
    data_type: str
    is_nullable: bool
    is_primary_key: bool
    ordinal_position: int
    default_value: Optional[str] = None


@dataclass
class TableSchema:
    """Schema information for a database table."""
    table_name: str
    columns: list[ColumnInfo] = field(default_factory=list)
    primary_key: list[str] = field(default_factory=list)
    
    def get_column_names(self) -> list[str]:
        """Get column names in ordinal order."""
        sorted_cols = sorted(self.columns, key=lambda c: c.ordinal_position)
        return [c.name for c in sorted_cols]
    
    def get_pk_tuple(self, row: dict) -> tuple:
        """Extract primary key tuple from a row."""
        return tuple(row.get(pk) for pk in self.primary_key)
    
    def get_pk_dict(self, row: dict) -> dict:
        """Extract primary key as dict from a row."""
        return {pk: row.get(pk) for pk in self.primary_key}


class DatabaseSchemaManager:
    """Manages database schema introspection and table creation."""
    
    def __init__(self, connection_string: Optional[str] = None):
        if not SQLALCHEMY_AVAILABLE:
            raise ImportError("SQLAlchemy is required for database operations. Install with: pip install sqlalchemy psycopg2-binary")
        
        self.connection_string = connection_string or os.environ.get("APP_DB_CONNECTION")
        self._engine: Optional[Engine] = None
        self._schema_cache: dict[str, TableSchema] = {}
    
    @property
    def engine(self) -> Engine:
        """Lazy-load database engine."""
        if self._engine is None:
            if not self.connection_string:
                raise ValueError("Database connection string not configured")
            self._engine = create_engine(self.connection_string, pool_pre_ping=True)
        return self._engine
    
    def get_table_schema(self, table_name: str, force_refresh: bool = False) -> TableSchema:
        """
        Get schema for a table, auto-detecting from information_schema.
        
        Args:
            table_name: Name of the table to introspect
            force_refresh: If True, bypass cache and re-query
            
        Returns:
            TableSchema with columns and primary key info
        """
        if not force_refresh and table_name in self._schema_cache:
            return self._schema_cache[table_name]
        
        inspector = inspect(self.engine)
        
        # Get columns
        columns = []
        for idx, col in enumerate(inspector.get_columns(table_name), start=1):
            columns.append(ColumnInfo(
                name=col["name"],
                data_type=str(col["type"]),
                is_nullable=col.get("nullable", True),
                is_primary_key=False,  # Will be updated below
                ordinal_position=idx,
                default_value=str(col.get("default")) if col.get("default") else None
            ))
        
        # Get primary key
        pk_constraint = inspector.get_pk_constraint(table_name)
        pk_columns = pk_constraint.get("constrained_columns", []) if pk_constraint else []
        
        # Update is_primary_key flag
        for col in columns:
            col.is_primary_key = col.name in pk_columns
        
        schema = TableSchema(
            table_name=table_name,
            columns=columns,
            primary_key=pk_columns
        )
        
        self._schema_cache[table_name] = schema
        return schema
    
    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists in the database."""
        inspector = inspect(self.engine)
        return table_name in inspector.get_table_names()
    
    def create_mods_table(self, table_name: str) -> None:
        """
        Create the modifications table if it doesn't exist.
        
        Schema:
        - id: SERIAL PRIMARY KEY
        - row_pk: JSONB NOT NULL (composite PK of data row)
        - column_name: VARCHAR(255)
        - old_value: TEXT
        - new_value: TEXT
        - mod_type: VARCHAR(50)
        - undone: BOOLEAN DEFAULT FALSE
        - created_at: TIMESTAMP
        - created_by: VARCHAR(255)
        """
        if self.table_exists(table_name):
            return
        
        sql = f"""
        CREATE TABLE {table_name} (
            id SERIAL PRIMARY KEY,
            row_pk JSONB NOT NULL,
            column_name VARCHAR(255) NOT NULL,
            old_value TEXT,
            new_value TEXT,
            mod_type VARCHAR(50) NOT NULL,
            undone BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW(),
            created_by VARCHAR(255)
        );
        CREATE INDEX idx_{table_name}_row_pk ON {table_name} USING GIN (row_pk);
        CREATE INDEX idx_{table_name}_created_at ON {table_name} (created_at DESC);
        """
        
        with self.engine.begin() as conn:
            for statement in sql.strip().split(";"):
                if statement.strip():
                    conn.execute(text(statement))
    
    def create_state_table(self, table_name: str) -> None:
        """
        Create the UI state table if it doesn't exist.
        
        Schema:
        - id: SERIAL PRIMARY KEY
        - user_id: VARCHAR(255)
        - session_id: VARCHAR(255)
        - filters: JSONB
        - sort_column: VARCHAR(255)
        - sort_ascending: BOOLEAN
        - current_page: INT
        - rows_per_page: INT
        - column_preset: VARCHAR(255)
        - updated_at: TIMESTAMP
        """
        if self.table_exists(table_name):
            return
        
        sql = f"""
        CREATE TABLE {table_name} (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(255),
            session_id VARCHAR(255),
            filters JSONB,
            sort_column VARCHAR(255),
            sort_ascending BOOLEAN DEFAULT TRUE,
            current_page INT DEFAULT 1,
            rows_per_page INT DEFAULT 25,
            column_preset VARCHAR(255),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(user_id, session_id)
        );
        CREATE INDEX idx_{table_name}_user_session ON {table_name} (user_id, session_id);
        """
        
        with self.engine.begin() as conn:
            for statement in sql.strip().split(";"):
                if statement.strip():
                    conn.execute(text(statement))
    
    def generate_default_preset(self, table_name: str) -> dict:
        """
        Generate a default column preset from table schema.
        
        Returns:
            Dict with columns in ordinal order and empty widths
        """
        schema = self.get_table_schema(table_name)
        return {
            "columns": schema.get_column_names(),
            "widths": {}
        }
    
    def get_row_count(self, table_name: str, where_clause: Optional[str] = None) -> int:
        """Get total row count for a table, optionally with WHERE clause."""
        sql = f"SELECT COUNT(*) FROM {table_name}"
        if where_clause:
            sql += f" WHERE {where_clause}"
        
        with self.engine.connect() as conn:
            result = conn.execute(text(sql))
            return result.scalar() or 0
    
    def ensure_tables_exist(
        self, 
        data_table: str, 
        mods_table: str, 
        state_table: str
    ) -> dict[str, bool]:
        """
        Ensure all required tables exist, creating mods and state tables if needed.
        
        Returns:
            Dict indicating which tables were created
        """
        created = {"mods_table": False, "state_table": False}
        
        # Check data table exists
        if not self.table_exists(data_table):
            raise ValueError(f"Data table '{data_table}' does not exist")
        
        # Create mods table if needed
        if not self.table_exists(mods_table):
            self.create_mods_table(mods_table)
            created["mods_table"] = True
        
        # Create state table if needed
        if not self.table_exists(state_table):
            self.create_state_table(state_table)
            created["state_table"] = True
        
        return created


# =============================================================================
# Singleton instance
# =============================================================================

_schema_manager: Optional[DatabaseSchemaManager] = None


def get_schema_manager(connection_string: Optional[str] = None) -> DatabaseSchemaManager:
    """Get singleton schema manager instance."""
    global _schema_manager
    if _schema_manager is None:
        _schema_manager = DatabaseSchemaManager(connection_string)
    return _schema_manager


def get_table_schema(table_name: str) -> TableSchema:
    """Convenience function to get table schema."""
    return get_schema_manager().get_table_schema(table_name)


def get_primary_key(table_name: str) -> list[str]:
    """Convenience function to get primary key columns."""
    return get_schema_manager().get_table_schema(table_name).primary_key
