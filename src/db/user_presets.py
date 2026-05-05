#!/usr/bin/env python3
"""
User Presets Service for managing column presets per user.

Table naming convention: {table_name}_{username}_column_presets
Example: epitopes_john_column_presets

Usage (Server/UI):
    from dmapTableEditor.db import UserPresetsService
    
    # Initialize with app config (auto-detects connection string)
    presets_service = UserPresetsService()
    
    # Or with explicit connection
    presets_service = UserPresetsService(connection_string="postgresql://...")
    
    # Save a preset
    presets_service.save_preset("john", "My View", ["col1", "col2"], is_default=True)
    
    # Load presets
    presets = presets_service.get_presets("john")
    
    # Get default preset
    default = presets_service.get_default_preset("john")
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from sqlalchemy import create_engine, text, inspect
    from sqlalchemy.engine import Engine
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False


class UserPresetsService:
    """Service for managing user column presets in PostgreSQL.
    
    Provides methods for server-side and UI-side preset management.
    """
    
    def __init__(self, connection_string: str = None, table_name: str = None, engine: Engine = None):
        """Initialize the presets service.
        
        Args:
            connection_string: PostgreSQL connection string. If None, loads from app config.
            table_name: Base table name (e.g., 'epitopes'). If None, loads from app config.
            engine: Existing SQLAlchemy engine. If provided, connection_string is ignored.
        """
        if not SQLALCHEMY_AVAILABLE:
            raise ImportError("SQLAlchemy not installed. Run: pip install sqlalchemy psycopg2-binary")
        
        if engine:
            self._engine = engine
        else:
            if connection_string is None:
                # Load from app config
                connection_string, table_name = self._load_from_config(table_name)
            self._engine = create_engine(connection_string)
        
        self._table_name = table_name or "epitopes"
    
    def _load_from_config(self, table_name: str = None) -> tuple[str, str]:
        """Load connection string and table name from app_config.json."""
        config_path = PROJECT_ROOT / "app_config.json"
        if config_path.exists():
            with open(config_path) as f:
                config = json.load(f)
            conn_str = config.get("database", {}).get("connection_string", "postgresql://her2@localhost/epitopes_db")
            tbl_name = table_name or config.get("data_source", {}).get("table_name", "epitopes")
            return conn_str, tbl_name
        return "postgresql://her2@localhost/epitopes_db", table_name or "epitopes"
    
    @property
    def engine(self) -> Engine:
        """Get the SQLAlchemy engine."""
        return self._engine
    
    @property
    def table_name(self) -> str:
        """Get the base table name."""
        return self._table_name
    
    def _get_preset_table_name(self, username: str = None) -> str:
        """Generate the preset table name.
        
        Convention: {table_name}_column_presets (shared table with username column)
        """
        return f"{self._table_name}_column_presets"
    
    def _ensure_table_exists(self, username: str) -> str:
        """Create the preset table if it doesn't exist."""
        preset_table = self._get_preset_table_name()
        
        create_sql = f"""
        CREATE TABLE IF NOT EXISTS "{preset_table}" (
            id SERIAL PRIMARY KEY,
            username VARCHAR(255) NOT NULL,
            preset_name VARCHAR(255) NOT NULL,
            columns JSONB NOT NULL,
            is_default BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (username, preset_name)
        );
        CREATE INDEX IF NOT EXISTS idx_{preset_table}_user ON "{preset_table}" (username);
        """
        
        with self._engine.connect() as conn:
            conn.execute(text(create_sql))
            conn.commit()
        
        return preset_table
    
    def save_preset(self, username: str, preset_name: str, columns: list, 
                    is_default: bool = False) -> int:
        """Save a column preset for a user.
        
        Args:
            username: User identifier
            preset_name: Name for this preset
            columns: List of column names
            is_default: Whether this is the default preset
            
        Returns:
            The preset ID
        """
        preset_table = self._ensure_table_exists(username)
        
        with self._engine.connect() as conn:
            if is_default:
                conn.execute(text(f'UPDATE "{preset_table}" SET is_default = FALSE WHERE username = :username AND is_default = TRUE'),
                             {"username": username})
            
            upsert_sql = text(f"""
                INSERT INTO "{preset_table}" (username, preset_name, columns, is_default, updated_at)
                VALUES (:username, :preset_name, :columns, :is_default, CURRENT_TIMESTAMP)
                ON CONFLICT (username, preset_name) 
                DO UPDATE SET 
                    columns = EXCLUDED.columns,
                    is_default = EXCLUDED.is_default,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id
            """)
            
            result = conn.execute(upsert_sql, {
                "username": username,
                "preset_name": preset_name,
                "columns": json.dumps(columns),
                "is_default": is_default
            })
            preset_id = result.scalar()
            conn.commit()
            
        return preset_id
    
    def get_presets(self, username: str) -> list[dict]:
        """Load all presets for a user.
        
        Returns:
            List of preset dicts with keys: id, preset_name, columns, is_default, created_at, updated_at
        """
        preset_table = self._get_preset_table_name()
        
        inspector = inspect(self._engine)
        if preset_table not in inspector.get_table_names():
            return []
        
        with self._engine.connect() as conn:
            result = conn.execute(text(f"""
                SELECT id, preset_name, columns, is_default, created_at, updated_at
                FROM "{preset_table}"
                WHERE username = :username
                ORDER BY preset_name
            """), {"username": username})
            
            presets = []
            for row in result:
                presets.append({
                    "id": row[0],
                    "preset_name": row[1],
                    "columns": row[2],
                    "is_default": row[3],
                    "created_at": row[4].isoformat() if row[4] else None,
                    "updated_at": row[5].isoformat() if row[5] else None
                })
            
        return presets
    
    def get_preset_by_name(self, username: str, preset_name: str) -> Optional[dict]:
        """Get a specific preset by name.
        
        Returns:
            Preset dict or None if not found
        """
        preset_table = self._get_preset_table_name()
        
        inspector = inspect(self._engine)
        if preset_table not in inspector.get_table_names():
            return None
        
        with self._engine.connect() as conn:
            result = conn.execute(text(f"""
                SELECT id, preset_name, columns, is_default, created_at, updated_at
                FROM "{preset_table}"
                WHERE username = :username AND preset_name = :preset_name
                LIMIT 1
            """), {"username": username, "preset_name": preset_name})
            
            row = result.fetchone()
            if row:
                return {
                    "id": row[0],
                    "preset_name": row[1],
                    "columns": row[2],
                    "is_default": row[3],
                    "created_at": row[4].isoformat() if row[4] else None,
                    "updated_at": row[5].isoformat() if row[5] else None
                }
        
        return None
    
    def get_default_preset(self, username: str) -> Optional[dict]:
        """Get the default preset for a user.
        
        Returns:
            Preset dict or None if no default set
        """
        preset_table = self._get_preset_table_name()
        
        inspector = inspect(self._engine)
        if preset_table not in inspector.get_table_names():
            return None
        
        with self._engine.connect() as conn:
            result = conn.execute(text(f"""
                SELECT id, preset_name, columns, is_default, created_at, updated_at
                FROM "{preset_table}"
                WHERE username = :username AND is_default = TRUE
                LIMIT 1
            """), {"username": username})
            
            row = result.fetchone()
            if row:
                return {
                    "id": row[0],
                    "preset_name": row[1],
                    "columns": row[2],
                    "is_default": row[3],
                    "created_at": row[4].isoformat() if row[4] else None,
                    "updated_at": row[5].isoformat() if row[5] else None
                }
        
        return None
    
    def delete_preset(self, username: str, preset_name: str) -> bool:
        """Delete a preset by name.
        
        Returns:
            True if deleted, False if not found
        """
        preset_table = self._get_preset_table_name()
        
        inspector = inspect(self._engine)
        if preset_table not in inspector.get_table_names():
            return False
        
        with self._engine.connect() as conn:
            result = conn.execute(text(f"""
                DELETE FROM "{preset_table}"
                WHERE username = :username AND preset_name = :preset_name
            """), {"username": username, "preset_name": preset_name})
            conn.commit()
            
        return result.rowcount > 0
    
    def set_default(self, username: str, preset_name: str) -> bool:
        """Set a preset as the default.
        
        Returns:
            True if successful, False if preset not found
        """
        preset_table = self._get_preset_table_name()
        
        inspector = inspect(self._engine)
        if preset_table not in inspector.get_table_names():
            return False
        
        with self._engine.connect() as conn:
            # Unset current default for this user
            conn.execute(text(f'UPDATE "{preset_table}" SET is_default = FALSE WHERE username = :username AND is_default = TRUE'),
                         {"username": username})
            
            # Set new default
            result = conn.execute(text(f"""
                UPDATE "{preset_table}" 
                SET is_default = TRUE, updated_at = CURRENT_TIMESTAMP
                WHERE username = :username AND preset_name = :preset_name
            """), {"username": username, "preset_name": preset_name})
            conn.commit()
            
        return result.rowcount > 0
    
    def list_users(self) -> list[str]:
        """List all users with presets in this table.
        
        Returns:
            List of usernames
        """
        preset_table = self._get_preset_table_name()
        
        inspector = inspect(self._engine)
        if preset_table not in inspector.get_table_names():
            return []
        
        with self._engine.connect() as conn:
            result = conn.execute(text(f"""
                SELECT DISTINCT username FROM "{preset_table}" ORDER BY username
            """))
            return [row[0] for row in result]


# ============================================================================
# Standalone functions for backward compatibility
# ============================================================================

def get_user_preset_table_name(table_name: str, username: str) -> str:
    """Generate the preset table name (shared table, username is a column)."""
    return f"{table_name}_column_presets"


def create_user_preset_table(engine, table_name: str, username: str) -> str:
    """Create a user-specific column preset table."""
    service = UserPresetsService(engine=engine, table_name=table_name)
    return service._ensure_table_exists(username)


def save_user_preset(engine, table_name: str, username: str, 
                     preset_name: str, columns: list, is_default: bool = False) -> int:
    """Save a column preset for a user."""
    service = UserPresetsService(engine=engine, table_name=table_name)
    return service.save_preset(username, preset_name, columns, is_default)


def load_user_presets(engine, table_name: str, username: str) -> list:
    """Load all presets for a user."""
    service = UserPresetsService(engine=engine, table_name=table_name)
    return service.get_presets(username)


def get_default_preset(engine, table_name: str, username: str) -> Optional[dict]:
    """Get the default preset for a user."""
    service = UserPresetsService(engine=engine, table_name=table_name)
    return service.get_default_preset(username)


def delete_user_preset(engine, table_name: str, username: str, preset_name: str) -> bool:
    """Delete a preset by name."""
    service = UserPresetsService(engine=engine, table_name=table_name)
    return service.delete_preset(username, preset_name)


def list_user_preset_tables(engine, table_name: str = None) -> list:
    """List all user preset tables in the database."""
    inspector = inspect(engine)
    all_tables = inspector.get_table_names()
    
    preset_tables = [t for t in all_tables if t.endswith("_column_presets")]
    
    if table_name:
        preset_tables = [t for t in preset_tables if t.startswith(f"{table_name}_")]
    
    return preset_tables


# ============================================================================
# CLI (optional, for manual testing)
# ============================================================================

def main():
    """CLI for managing user presets."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Manage user column presets")
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Create table command
    create_parser = subparsers.add_parser("create", help="Create user preset table")
    create_parser.add_argument("--user", required=True, help="Username")
    
    # Save preset command
    save_parser = subparsers.add_parser("save", help="Save a preset")
    save_parser.add_argument("--user", required=True, help="Username")
    save_parser.add_argument("--name", required=True, help="Preset name")
    save_parser.add_argument("--columns", required=True, help="Comma-separated column names")
    save_parser.add_argument("--default", action="store_true", help="Set as default")
    
    # List presets command
    list_parser = subparsers.add_parser("list", help="List presets for a user")
    list_parser.add_argument("--user", required=True, help="Username")
    
    # List users command
    subparsers.add_parser("users", help="List all users with presets")
    
    # Delete preset command
    delete_parser = subparsers.add_parser("delete", help="Delete a preset")
    delete_parser.add_argument("--user", required=True, help="Username")
    delete_parser.add_argument("--name", required=True, help="Preset name to delete")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Initialize service (auto-loads from app config)
    service = UserPresetsService()
    
    if args.command == "create":
        table_name = service._ensure_table_exists(args.user)
        print(f"✓ Created table: {table_name}")
        
    elif args.command == "save":
        columns = [c.strip() for c in args.columns.split(",")]
        preset_id = service.save_preset(args.user, args.name, columns, args.default)
        print(f"✓ Saved preset '{args.name}' (id={preset_id})")
        print(f"  Columns: {columns}")
        if args.default:
            print("  Set as default")
        
    elif args.command == "list":
        presets = service.get_presets(args.user)
        if not presets:
            print(f"No presets found for {args.user}")
        else:
            print(f"Presets for {args.user}:")
            for p in presets:
                default_marker = " [DEFAULT]" if p["is_default"] else ""
                print(f"  - {p['preset_name']}{default_marker}")
                print(f"    Columns: {p['columns']}")
    
    elif args.command == "users":
        users = service.list_users()
        if not users:
            print("No users with presets found")
        else:
            print("Users with presets:")
            for u in users:
                print(f"  - {u}")
                
    elif args.command == "delete":
        if service.delete_preset(args.user, args.name):
            print(f"✓ Deleted preset '{args.name}'")
        else:
            print(f"✗ Preset '{args.name}' not found")


if __name__ == "__main__":
    main()
