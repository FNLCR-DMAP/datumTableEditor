"""
Configuration Instance Loader

Provides on-demand config loading for widget instances.
Each widget can load its own config file independently.
"""

import json
import os
import pandas as pd
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

from .app_config_schema import AppConfig, load_config


def _format_table_name(table_name: str) -> str:
    """
    Format table name for SQL queries.
    
    If table_name contains a dot (schema.table), don't quote the whole thing.
    Otherwise, quote it to handle special characters.
    """
    if '.' in table_name:
        # Schema-qualified: schema.table -> schema.table (no quotes)
        # Or optionally: "schema"."table"
        parts = table_name.split('.', 1)
        return f'{parts[0]}.{parts[1]}'
    else:
        # Simple table name - quote it
        return f'"{table_name}"'


@dataclass
class ConfigInstance:
    """
    Holds all configuration and data for a single widget instance.
    
    This allows multiple widgets to have independent configs and data.
    """
    config_path: str
    username: str = "default_user"  # User identifier for user-scoped state
    app_config: AppConfig = field(default=None)
    df: pd.DataFrame = field(default=None)
    all_columns: List[str] = field(default_factory=list)
    display_columns: List[str] = field(default_factory=list)
    data_dir: Path = field(default=None)
    modifications_log_path: Path = field(default=None)
    _state_table_checked: bool = field(default=False, repr=False)
    _engine: Any = field(default=None, repr=False)
    
    def __post_init__(self):
        """Load config and data after initialization."""
        self._load_all()
    
    def _get_engine(self):
        """Get or create a cached SQLAlchemy engine."""
        if self._engine is None:
            from sqlalchemy import create_engine
            conn_string = self.app_config.database.connection_string
            if conn_string:
                self._engine = create_engine(conn_string)
        return self._engine
    
    def _load_all(self):
        """Load configuration and data."""
        # Determine project root from config path
        config_file = Path(self.config_path)
        if not config_file.is_absolute():
            config_file = Path.cwd() / config_file
        
        project_root = config_file.parent
        
        # Load app config
        self.app_config = load_config(
            str(config_file).strip(),
            username=self.username
        )
        
        # Setup paths (don't create at init - filesystem may be read-only)
        self.data_dir = project_root / "data"
        # Note: Directory created lazily when needed for exports
        
        # Load data from database
        self.df = self._load_data()
        
        # Set columns
        self.all_columns = list(self.df.columns)
        self.display_columns = self._get_display_columns()
        
        # Modifications log path (for reference only)
        self.modifications_log_path = self.data_dir / "modifications_log.json"
    
    def ensure_data_dir(self) -> bool:
        """
        Ensure data directory exists for file exports.
        Returns True if directory exists/created, False if filesystem is read-only.
        """
        try:
            self.data_dir.mkdir(exist_ok=True)
            return True
        except OSError:
            # Read-only filesystem (e.g., RStudio Connect)
            return False

    def _load_data(self) -> pd.DataFrame:
        """Load data from database."""
        if self.app_config.database.mode == "datum":
            return self._load_from_datum()
        return self._load_from_database()
    
    def _load_from_database(self) -> pd.DataFrame:
        """Load data from PostgreSQL database with modification status."""
        try:
            from sqlalchemy import text
            
            data_table = self.app_config.database.data_table
            mods_table = self.app_config.database.mods_table
            pk_columns = self.app_config.table.primary_key
            
            engine = self._get_engine()
            if engine is None:
                raise ValueError(
                    f"Database connection_string is None. "
                    f"Config path: {self.config_path}, "
                    f"Mode: {self.app_config.database.mode}, "
                    f"Enabled: {self.app_config.database.enabled}"
                )
            
            data_table_sql = _format_table_name(data_table)
            mods_table_sql = _format_table_name(mods_table)
            
            # Build PK match condition for subquery
            pk_conditions = " AND ".join(
                f"m.row_pk->>'{pk}' = d.\"{pk}\"::text"
                for pk in pk_columns
            )
            
            # Query with modification status via subquery
            query = f"""
            SELECT d.*,
                COALESCE(
                    (SELECT m.mod_type 
                     FROM {mods_table_sql} m 
                     WHERE {pk_conditions}
                       AND m.undone = FALSE
                     ORDER BY m.created_at DESC 
                     LIMIT 1),
                    'unprocessed'
                ) AS _mod_status
            FROM {data_table_sql} d
            ORDER BY d."{pk_columns[0]}"
            """
            
            with engine.connect() as conn:
                result = conn.execute(text(query))
                rows = result.fetchall()
                columns = result.keys()
            
            df = pd.DataFrame(rows, columns=columns)
            
            # Apply field modifications to the data
            df = self._apply_field_modifications(df, engine)
            
            return df
        except Exception as e:
            print(f"✗ Error loading from database: {e}")
            return pd.DataFrame()
    
    def _apply_field_modifications(self, df: pd.DataFrame, engine) -> pd.DataFrame:
        """
        Apply field modifications to the dataframe AND track which cells were edited.
        Tracks the FIRST old_value as the original value for each cell.
        """
        try:
            from sqlalchemy import text
            
            mods_table = self.app_config.database.mods_table
            pk_columns = self.app_config.table.primary_key
            mods_table_sql = _format_table_name(mods_table)
            
            # Query field modifications - include old_value for original tracking
            # Order by created_at ASC so first edit contains the original value
            mods_query = f"""
            SELECT row_pk, column_name, old_value, new_value 
            FROM {mods_table_sql}
            WHERE mod_type = 'field_modification' 
              AND undone = FALSE
            ORDER BY created_at ASC
            """
            
            with engine.connect() as conn:
                result = conn.execute(text(mods_query))
                mods_data = result.fetchall()
            
            # Store edited cells info: {(pk_tuple, col_name): {"original": first_old_value, "current": latest_new_value}}
            # PK is stored as a tuple of (pk_col, pk_val) pairs for hashability
            self.edited_cells = {}
            
            if mods_data:
                for mod in mods_data:
                    row_pk = mod[0]
                    if isinstance(row_pk, str):
                        row_pk = json.loads(row_pk)
                    col_name = mod[1]
                    old_value = mod[2]
                    new_value = mod[3]
                    
                    if col_name in df.columns:
                        # Build mask to find the row
                        mask = pd.Series([True] * len(df))
                        for pk_col in pk_columns:
                            if pk_col in row_pk and pk_col in df.columns:
                                mask &= (df[pk_col].astype(str) == str(row_pk[pk_col]))
                        if mask.any():
                            # Create PK tuple for stable cell key (hashable)
                            pk_tuple = tuple(sorted((k, str(v)) for k, v in row_pk.items()))
                            cell_key = (pk_tuple, col_name)
                            
                            # Track edited cell - keep FIRST old_value as original
                            if cell_key not in self.edited_cells:
                                # First edit for this cell - old_value is the original
                                self.edited_cells[cell_key] = {
                                    "original": old_value,
                                    "current": new_value
                                }
                            else:
                                # Subsequent edit - update current, keep original
                                self.edited_cells[cell_key]["current"] = new_value
                            
                            # Apply modification to df (show current edited value)
                            df.loc[mask, col_name] = new_value
            
            return df
        except Exception as e:
            print(f"⚠ Could not apply field modifications: {e}")
            self.edited_cells = {}
            return df
    
    def get_edited_cells(self) -> dict:
        """Return dict of edited cells: {(pk_tuple, col_name): {"original": val, "current": val}}"""
        return getattr(self, 'edited_cells', {})
    
    def is_cell_edited(self, row_pk: dict, col_name: str) -> bool:
        """Check if a specific cell has been edited using its PK."""
        pk_tuple = tuple(sorted((k, str(v)) for k, v in row_pk.items()))
        return (pk_tuple, col_name) in getattr(self, 'edited_cells', {})
    
    def get_original_value(self, row_pk: dict, col_name: str) -> str:
        """Get the original value for an edited cell, or None if not edited."""
        pk_tuple = tuple(sorted((k, str(v)) for k, v in row_pk.items()))
        cell_info = getattr(self, 'edited_cells', {}).get((pk_tuple, col_name))
        if cell_info:
            return cell_info.get("original")
        return None
    
    def _load_from_datum(self) -> pd.DataFrame:
        """Load data via Datum proxy."""
        try:
            from ..adapter.datum import DatumClient
            
            base_url = self.app_config.database.datum_base_url or os.environ.get("DATUM_BASE_URL", "")
            token = self.app_config.database.datum_token or os.environ.get("DATUM_API_TOKEN", "")
            
            if not base_url or not token:
                raise ValueError("Datum mode requires datum_base_url and datum_token")
            
            client = DatumClient(base_url=base_url, token=token)
            data_table = self.app_config.database.data_table
            
            response = client.execute_sql(
                sql=f'SELECT * FROM "{data_table}"',
                database=self.app_config.database.datum_database,
                schema=self.app_config.database.datum_schema,
                service_name=self.app_config.database.datum_service_name,
            )
            
            df = pd.DataFrame(response.data)
            return df
        except Exception as e:
            print(f"✗ Error loading from Datum: {e}")
            return pd.DataFrame()
    
    def _get_display_columns(self) -> List[str]:
        """Get default display columns from configuration."""
        if self.app_config.table.default_columns:
            return [col for col in self.app_config.table.default_columns if col in self.df.columns]
        return self.all_columns[:12]  # Default to first 12 columns
    
    def load_modifications_log(self) -> List[Dict]:
        """Load modifications log from database."""
        if self.app_config.database.mode == "datum":
            return self._load_modifications_from_datum()
        return self._load_modifications_from_db()
    
    def _load_modifications_from_datum(self) -> List[Dict]:
        """Load modifications via Datum proxy."""
        try:
            from ..adapter.datum import DatumClient
            
            base_url = self.app_config.database.datum_base_url or os.environ.get("DATUM_BASE_URL", "")
            token = self.app_config.database.datum_token or os.environ.get("DATUM_API_TOKEN", "")
            
            if not base_url or not token:
                print("⚠ Datum credentials not configured for modifications")
                return []
            
            client = DatumClient(base_url=base_url, token=token)
            mods_table = self.app_config.database.mods_table
            
            response = client.execute_sql(
                sql=f'''SELECT id, row_pk, column_name, old_value, new_value, 
                       mod_type, created_by, created_at, undone
                       FROM "{mods_table}" ORDER BY created_at ASC''',
                database=self.app_config.database.datum_database,
                schema=self.app_config.database.datum_schema,
                service_name=self.app_config.database.datum_service_name,
            )
            
            log = []
            for row in response.data:
                row_pk = row.get("row_pk", {})
                if isinstance(row_pk, str):
                    row_pk = json.loads(row_pk)
                
                log.append({
                    "db_id": row.get("id"),
                    "timestamp": row.get("created_at"),
                    "type": row.get("mod_type"),
                    "undone": row.get("undone", False),
                    "details": {
                        "row_pk": row_pk,
                        "column": row.get("column_name"),
                        "old_value": row.get("old_value"),
                        "new_value": row.get("new_value"),
                        "created_by": row.get("created_by")
                    }
                })
            
            return self._aggregate_approval_rejection_entries(log)
        except Exception as e:
            print(f"✗ Error loading modifications from Datum: {e}")
            return []

    def _load_modifications_from_db(self) -> List[Dict]:
        """Load modifications from database."""
        try:
            from sqlalchemy import text
            
            mods_table = self.app_config.database.mods_table
            
            engine = self._get_engine()
            if engine is None:
                return []
            
            table_sql = _format_table_name(mods_table)
            with engine.connect() as conn:
                result = conn.execute(text(f'''
                    SELECT id, row_pk, column_name, old_value, new_value, 
                           mod_type, created_by, created_at, undone
                    FROM {table_sql}
                    ORDER BY created_at ASC
                '''))
                rows = result.fetchall()
            
            log = []
            for row in rows:
                row_pk = row[1]
                if isinstance(row_pk, str):
                    row_pk = json.loads(row_pk)
                elif row_pk is None:
                    row_pk = {}
                
                log.append({
                    "db_id": row[0],
                    "timestamp": row[7].isoformat() if row[7] else None,
                    "type": row[5],
                    "undone": row[8],
                    "details": {
                        "row_pk": row_pk,
                        "column": row[2],
                        "old_value": row[3],
                        "new_value": row[4],
                        "created_by": row[6]
                    }
                })
            
            return self._aggregate_approval_rejection_entries(log)
        except Exception as e:
            print(f"✗ Error loading modifications: {e}")
            return []
    
    def _aggregate_approval_rejection_entries(self, log: list) -> list:
        """Group approval/rejection entries by timestamp."""
        from collections import defaultdict
        
        result = []
        approval_groups = defaultdict(list)
        rejection_groups = defaultdict(list)
        
        for entry in log:
            mod_type = entry.get("type")
            if mod_type == "approval":
                ts = entry.get("timestamp", "")[:19]
                row_pk = entry.get("details", {}).get("row_pk", {})
                if row_pk:
                    approval_groups[ts].append({"entry": entry, "row_pk": row_pk})
            elif mod_type == "rejection":
                ts = entry.get("timestamp", "")[:19]
                row_pk = entry.get("details", {}).get("row_pk", {})
                if row_pk:
                    rejection_groups[ts].append({"entry": entry, "row_pk": row_pk})
            else:
                result.append(entry)
        
        for ts, items in approval_groups.items():
            result.append({
                "timestamp": ts,
                "type": "approval",
                "details": {
                    "action": "approved",
                    "approved_rows": [item["row_pk"] for item in items],
                    "approved_row_count": len(items),
                }
            })
        
        for ts, items in rejection_groups.items():
            result.append({
                "timestamp": ts,
                "type": "rejection",
                "details": {
                    "action": "rejected",
                    "rejected_rows": [item["row_pk"] for item in items],
                    "rejected_row_count": len(items),
                }
            })
        
        result.sort(key=lambda x: x.get("timestamp", ""))
        return result
    
    def reload_data(self) -> pd.DataFrame:
        """Reload data from database."""
        self.df = self._load_data()
        self.all_columns = list(self.df.columns)
        return self.df
    
    def save_modification_to_db(self, row_pk: dict, column: str, old_value, new_value, mod_type: str = "field_modification"):
        """Save a single modification to the database using this config instance."""
        if self.app_config.database.mode == "datum":
            return self._save_modification_to_datum(row_pk, column, old_value, new_value, mod_type)
        
        try:
            from sqlalchemy import text
            
            mods_table = self.app_config.database.mods_table
            
            engine = self._get_engine()
            if engine is None:
                return None
            
            table_sql = _format_table_name(mods_table)
            
            with engine.connect() as conn:
                result = conn.execute(
                    text(f'''
                        INSERT INTO {table_sql} 
                            (row_pk, column_name, old_value, new_value, mod_type)
                        VALUES 
                            (:row_pk, :column_name, :old_value, :new_value, :mod_type)
                        RETURNING id
                    '''),
                    {
                        "row_pk": json.dumps(row_pk),
                        "column_name": column,
                        "old_value": str(old_value) if old_value is not None else None,
                        "new_value": str(new_value) if new_value is not None else None,
                        "mod_type": mod_type
                    }
                )
                mod_id = result.scalar()
                conn.commit()
                return mod_id
        except Exception as e:
            print(f"✗ Error saving modification to DB: {e}")
            return None
    
    def _save_modification_to_datum(self, row_pk: dict, column: str, old_value, new_value, mod_type: str):
        """Save modification via Datum proxy."""
        try:
            from ..adapter.datum import DatumClient
            
            base_url = self.app_config.database.datum_base_url or os.environ.get("DATUM_BASE_URL", "")
            token = self.app_config.database.datum_token or os.environ.get("DATUM_API_TOKEN", "")
            
            if not base_url or not token:
                print("⚠ Datum credentials not configured")
                return None
            
            client = DatumClient(base_url=base_url, token=token)
            mods_table = self.app_config.database.mods_table
            
            old_val_str = str(old_value) if old_value is not None else None
            new_val_str = str(new_value) if new_value is not None else None
            row_pk_json = json.dumps(row_pk).replace("'", "''")
            
            sql = f'''
                INSERT INTO "{mods_table}" 
                    (row_pk, column_name, old_value, new_value, mod_type)
                VALUES 
                    ('{row_pk_json}'::jsonb, '{column}', 
                     {f"'{old_val_str}'" if old_val_str else 'NULL'}, 
                     {f"'{new_val_str}'" if new_val_str else 'NULL'}, 
                     '{mod_type}')
                RETURNING id
            '''
            
            response = client.execute_sql(
                sql=sql,
                database=self.app_config.database.datum_database,
                schema=self.app_config.database.datum_schema,
                service_name=self.app_config.database.datum_service_name,
            )
            
            if response.data:
                return response.data[0].get("id")
            return None
        except Exception as e:
            print(f"✗ Error saving modification to Datum: {e}")
            return None

    def mark_modification_undone_in_db(self, mod_id: int):
        """Mark a modification as undone in the database."""
        if self.app_config.database.mode == "datum":
            return self._mark_modification_undone_datum(mod_id)
        
        try:
            from sqlalchemy import text
            
            mods_table = self.app_config.database.mods_table
            
            engine = self._get_engine()
            if engine is None:
                return False
            
            table_sql = _format_table_name(mods_table)
            
            with engine.connect() as conn:
                conn.execute(
                    text(f'UPDATE {table_sql} SET undone = TRUE WHERE id = :mod_id'),
                    {"mod_id": mod_id}
                )
                conn.commit()
                return True
        except Exception as e:
            print(f"✗ Error marking modification undone: {e}")
            return False
    
    def _mark_modification_undone_datum(self, mod_id: int):
        """Mark modification undone via Datum proxy."""
        try:
            from ..adapter.datum import DatumClient
            
            base_url = self.app_config.database.datum_base_url or os.environ.get("DATUM_BASE_URL", "")
            token = self.app_config.database.datum_token or os.environ.get("DATUM_API_TOKEN", "")
            
            if not base_url or not token:
                return False
            
            client = DatumClient(base_url=base_url, token=token)
            mods_table = self.app_config.database.mods_table
            
            client.execute_sql(
                sql=f'UPDATE "{mods_table}" SET undone = TRUE WHERE id = {mod_id}',
                database=self.app_config.database.datum_database,
                schema=self.app_config.database.datum_schema,
                service_name=self.app_config.database.datum_service_name,
            )
            return True
        except Exception as e:
            print(f"✗ Error marking modification undone via Datum: {e}")
            return False

    def update_data_in_db(self, row_pk: dict, column: str, new_value):
        """Update the actual data in the database."""
        if self.app_config.database.mode == "datum":
            return self._update_data_in_datum(row_pk, column, new_value)
        
        try:
            from sqlalchemy import text
            
            data_table = self.app_config.database.data_table
            pk_columns = self.app_config.table.primary_key
            
            engine = self._get_engine()
            if engine is None:
                return False
            
            # Build WHERE clause from PK
            where_parts = []
            params = {"new_value": new_value}
            for i, pk_col in enumerate(pk_columns):
                if pk_col in row_pk:
                    where_parts.append(f'"{pk_col}" = :pk_{i}')
                    params[f"pk_{i}"] = row_pk[pk_col]
            
            if not where_parts:
                return False
            
            where_clause = " AND ".join(where_parts)
            table_sql = _format_table_name(data_table)
            
            with engine.connect() as conn:
                conn.execute(
                    text(f'UPDATE {table_sql} SET "{column}" = :new_value WHERE {where_clause}'),
                    params
                )
                conn.commit()
                return True
        except Exception as e:
            print(f"✗ Error updating data in DB: {e}")
            return False
    
    def _update_data_in_datum(self, row_pk: dict, column: str, new_value):
        """Update data via Datum proxy."""
        try:
            from ..adapter.datum import DatumClient
            
            base_url = self.app_config.database.datum_base_url or os.environ.get("DATUM_BASE_URL", "")
            token = self.app_config.database.datum_token or os.environ.get("DATUM_API_TOKEN", "")
            
            if not base_url or not token:
                return False
            
            client = DatumClient(base_url=base_url, token=token)
            data_table = self.app_config.database.data_table
            pk_columns = self.app_config.table.primary_key
            
            # Build WHERE clause from PK
            where_parts = []
            for pk_col in pk_columns:
                if pk_col in row_pk:
                    pk_val = row_pk[pk_col]
                    if isinstance(pk_val, str):
                        where_parts.append(f'"{pk_col}" = \'{pk_val}\'')
                    else:
                        where_parts.append(f'"{pk_col}" = {pk_val}')
            
            if not where_parts:
                return False
            
            where_clause = " AND ".join(where_parts)
            new_val_sql = f"'{new_value}'" if new_value is not None else "NULL"
            
            client.execute_sql(
                sql=f'UPDATE "{data_table}" SET "{column}" = {new_val_sql} WHERE {where_clause}',
                database=self.app_config.database.datum_database,
                schema=self.app_config.database.datum_schema,
                service_name=self.app_config.database.datum_service_name,
            )
            return True
        except Exception as e:
            print(f"✗ Error updating data via Datum: {e}")
            return False

    def _ensure_state_table_exists(self) -> bool:
        """Create the UI state table if it doesn't exist. Only runs once per instance."""
        # Skip if already checked this session
        if self._state_table_checked:
            return True
        
        # Skip for datum mode - state operations not supported via proxy
        if self.app_config.database.mode == "datum":
            self._state_table_checked = True
            return False
        
        try:
            from sqlalchemy import text
            
            state_table = self.app_config.database.state_table
            
            # Parse schema.table format
            if '.' in state_table:
                schema, table_name = state_table.split('.', 1)
                schema_sql = schema
                table_sql = f'{schema}."{table_name}"'
            else:
                schema_sql = None
                table_sql = f'"{state_table}"'
            
            engine = self._get_engine()
            if engine is None:
                return False
            
            with engine.connect() as conn:
                # Create schema if needed
                if schema_sql:
                    conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS {schema_sql}'))
                
                # Create table if not exists
                conn.execute(text(f'''
                    CREATE TABLE IF NOT EXISTS {table_sql} (
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
                    )
                '''))
                conn.commit()
            self._state_table_checked = True
            return True
        except Exception as e:
            print(f"⚠ Could not create state table: {e}")
            return False

    def save_ui_state(
        self,
        sort_column: str = None,
        sort_ascending: bool = True,
        current_page: int = 1,
        rows_per_page: int = 25,
        filters: dict = None,
        column_preset: str = None,
        **kwargs  # Ignore extra args for compatibility
    ) -> bool:
        """Save UI state to database for this config instance."""
        # Skip for datum mode - state operations not supported via proxy
        if self.app_config.database.mode == "datum":
            return False
        
        try:
            from sqlalchemy import text
            
            state_table = self.app_config.database.state_table
            state_table_sql = _format_table_name(state_table)
            
            engine = self._get_engine()
            if engine is None:
                return False
            
            # Serialize filters as JSON
            filters_json = json.dumps(filters) if filters else None
            
            with engine.connect() as conn:
                # Use upsert pattern
                conn.execute(
                    text(f'''
                        INSERT INTO {state_table_sql} 
                            (user_id, session_id, sort_column, sort_ascending, 
                             current_page, rows_per_page, filters, column_preset, updated_at)
                        VALUES 
                            (:user_id, :session_id, :sort_column, :sort_ascending,
                             :current_page, :rows_per_page, :filters, :column_preset, NOW())
                        ON CONFLICT (user_id, session_id) 
                        DO UPDATE SET
                            sort_column = :sort_column,
                            sort_ascending = :sort_ascending,
                            current_page = :current_page,
                            rows_per_page = :rows_per_page,
                            filters = :filters,
                            column_preset = :column_preset,
                            updated_at = NOW()
                    '''),
                    {
                        "user_id": self.username,
                        "session_id": "default_session",
                        "sort_column": sort_column,
                        "sort_ascending": sort_ascending,
                        "current_page": current_page,
                        "rows_per_page": rows_per_page,
                        "filters": filters_json,
                        "column_preset": column_preset
                    }
                )
                conn.commit()
                return True
        except Exception as e:
            print(f"⚠ Could not save UI state: {e}")
            return False
    
    def load_ui_state(self) -> Dict:
        """Load UI state from database for this config instance."""
        default_state = {
            "sort_column": self.app_config.table.default_sort_column,
            "sort_ascending": self.app_config.table.default_sort_ascending,
            "current_page": 1,
            "rows_per_page": self.app_config.table.default_rows_per_page,
            "filters": {},
            "column_preset": None
        }
        
        # Skip for datum mode - state operations not supported via proxy
        if self.app_config.database.mode == "datum":
            return default_state
        
        # Ensure state table exists first
        self._ensure_state_table_exists()
        
        try:
            from sqlalchemy import text
            
            state_table = self.app_config.database.state_table
            state_table_sql = _format_table_name(state_table)
            
            engine = self._get_engine()
            if engine is None:
                return default_state
            
            with engine.connect() as conn:
                result = conn.execute(
                    text(f'''
                        SELECT sort_column, sort_ascending, current_page, 
                               rows_per_page, filters, column_preset
                        FROM {state_table_sql}
                        WHERE user_id = :user_id AND session_id = :session_id
                    '''),
                    {"user_id": self.username, "session_id": "default_session"}
                )
                row = result.fetchone()
            
            if row:
                filters = row[4]
                if isinstance(filters, str):
                    filters = json.loads(filters)
                elif filters is None:
                    filters = {}
                
                return {
                    "sort_column": row[0] or default_state["sort_column"],
                    "sort_ascending": row[1] if row[1] is not None else default_state["sort_ascending"],
                    "current_page": row[2] or default_state["current_page"],
                    "rows_per_page": row[3] or default_state["rows_per_page"],
                    "filters": filters,
                    "column_preset": row[5]
                }
        except Exception as e:
            print(f"⚠ Could not load UI state: {e}")
        
        return default_state


def load_config_instance(config_path: str = "app_config.json", username: str = "default_user") -> ConfigInstance:
    """
    Load a configuration instance for a widget.
    
    Args:
        config_path: Path to the config JSON file
        username: Username for user-scoped state (from Posit Connect session.user)
        
    Returns:
        ConfigInstance with loaded config and data
    """
    return ConfigInstance(config_path=config_path, username=username)
