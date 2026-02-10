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
    Format table name for SQL queries with proper PostgreSQL quoting.
    
    Properly quotes schema-qualified names by quoting each part separately:
    - "users" -> '"users"'
    - "epitopes.epitopes_data" -> '"epitopes"."epitopes_data"'
    - "public.my_table" -> '"public"."my_table"'
    """
    parts = table_name.split('.')
    return ".".join(f'"{part}"' for part in parts)


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
    _mods_log_cache: List[Dict] = field(default=None, repr=False)  # Cache for modifications log
    _mods_log_cache_time: float = field(default=0, repr=False)  # Cache timestamp
    _data_cache: pd.DataFrame = field(default=None, repr=False)  # Cache for data
    _data_cache_time: float = field(default=0, repr=False)  # Data cache timestamp
    
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
        """Load data from database with caching."""
        import time
        cache_ttl = 30  # Cache data for 30 seconds
        
        # Check if we have valid cached data
        if self._data_cache is not None and (time.time() - self._data_cache_time) < cache_ttl:
            return self._data_cache.copy()
        
        if self.app_config.database.mode == "datum":
            df = self._load_from_datum()
        else:
            df = self._load_from_database()
        
        # Update cache
        self._data_cache = df.copy()
        self._data_cache_time = time.time()
        
        return df
    
    def invalidate_data_cache(self):
        """Invalidate the data cache to force reload on next access."""
        self._data_cache = None
        self._data_cache_time = 0
    
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
            
            # OPTIMIZED: Use a single JOIN with DISTINCT ON instead of correlated subquery
            # This is much faster as the database can use indexes on mods_table
            pk_json_build = ", ".join(f"'{pk}', d.\"{pk}\"::text" for pk in pk_columns)
            
            query = f"""
            SELECT d.*, 
                   COALESCE(ms.mod_type, 'unprocessed') AS _mod_status
            FROM {data_table_sql} d
            LEFT JOIN LATERAL (
                SELECT mod_type 
                FROM {mods_table_sql} m
                WHERE m.row_pk = jsonb_build_object({pk_json_build})
                  AND m.undone = FALSE
                ORDER BY m.created_at DESC
                LIMIT 1
            ) ms ON TRUE
            ORDER BY d."{pk_columns[0]}"
            """
            
            with engine.connect() as conn:
                result = conn.execute(text(query))
                rows = result.fetchall()
                columns = result.keys()
            
            df = pd.DataFrame(rows, columns=columns)
            
            # Apply field modifications to the data (also optimized)
            df = self._apply_field_modifications(df, engine)
            
            return df
        except Exception as e:
            print(f"✗ Error loading from database: {e}")
            return pd.DataFrame()
    
    def _apply_field_modifications(self, df: pd.DataFrame, engine) -> pd.DataFrame:
        """
        Apply field modifications to the dataframe AND track which cells were edited.
        Tracks the FIRST old_value as the original value for each cell.
        
        OPTIMIZED: Only queries mods for PKs present in the current dataframe,
        avoiding full table scan when mods table is large.
        """
        try:
            from sqlalchemy import text
            
            if df.empty:
                self.edited_cells = {}
                return df
            
            mods_table = self.app_config.database.mods_table
            pk_columns = self.app_config.table.primary_key
            mods_table_sql = _format_table_name(mods_table)
            
            # OPTIMIZED: Build list of PKs from current dataframe
            # Create JSONB array of all PKs in the current view
            pk_values = []
            pk_index = {}  # Map pk_json -> row indices for fast lookup
            for idx, row in df.iterrows():
                pk_dict = {pk: row[pk] for pk in pk_columns if pk in df.columns}
                # Convert to JSON-compatible types
                serializable_pk = {}
                for k, v in pk_dict.items():
                    if hasattr(v, 'item'):  # numpy scalar
                        serializable_pk[k] = v.item()
                    elif pd.isna(v):
                        serializable_pk[k] = None
                    else:
                        serializable_pk[k] = v
                pk_json = json.dumps(serializable_pk, sort_keys=True)
                pk_values.append(pk_json)
                if pk_json not in pk_index:
                    pk_index[pk_json] = []
                pk_index[pk_json].append(idx)
            
            if not pk_values:
                self.edited_cells = {}
                return df
            
            # OPTIMIZED: Query only modifications for PKs in current view
            # Use ANY with jsonb array for efficient filtering
            pk_array = "ARRAY[" + ",".join(f"'{pv}'::jsonb" for pv in pk_values) + "]"
            
            mods_query = f"""
            SELECT row_pk, column_name, old_value, new_value 
            FROM {mods_table_sql}
            WHERE mod_type = 'field_modification' 
              AND undone = FALSE
              AND row_pk = ANY({pk_array})
            ORDER BY created_at ASC
            """
            
            with engine.connect() as conn:
                result = conn.execute(text(mods_query))
                mods_data = result.fetchall()
            
            # Store edited cells info: {(pk_tuple, col_name): {"original": first_old_value, "current": latest_new_value}}
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
                        # OPTIMIZED: Use pre-built index instead of building mask each time
                        pk_json = json.dumps(row_pk, sort_keys=True)
                        row_indices = pk_index.get(pk_json, [])
                        
                        if row_indices:
                            # Create PK tuple for stable cell key (hashable)
                            pk_tuple = tuple(sorted((k, str(v)) for k, v in row_pk.items()))
                            cell_key = (pk_tuple, col_name)
                            
                            # Track edited cell - keep FIRST old_value as original
                            if cell_key not in self.edited_cells:
                                self.edited_cells[cell_key] = {
                                    "original": old_value,
                                    "current": new_value
                                }
                            else:
                                self.edited_cells[cell_key]["current"] = new_value
                            
                            # Apply modification to df using direct index access
                            for idx in row_indices:
                                df.at[idx, col_name] = new_value
            
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
            mods_table = self.app_config.database.mods_table
            pk_columns = self.app_config.table.primary_key
            data_table_sql = _format_table_name(data_table)
            mods_table_sql = _format_table_name(mods_table)
            
            # OPTIMIZED: Use LATERAL JOIN instead of correlated subquery
            pk_json_build = ", ".join(f"'{pk}', d.\"{pk}\"::text" for pk in pk_columns)
            
            query = f"""
            SELECT d.*, 
                   COALESCE(ms.mod_type, 'unprocessed') AS _mod_status
            FROM {data_table_sql} d
            LEFT JOIN LATERAL (
                SELECT mod_type 
                FROM {mods_table_sql} m
                WHERE m.row_pk = jsonb_build_object({pk_json_build})
                  AND m.undone = FALSE
                ORDER BY m.created_at DESC
                LIMIT 1
            ) ms ON TRUE
            ORDER BY d."{pk_columns[0]}"
            """
            
            response = client.execute_sql(
                sql=query,
                database=self.app_config.database.datum_database,
                schema=self.app_config.database.datum_schema,
                service_name=self.app_config.database.datum_service_name,
            )
            
            df = pd.DataFrame(response.data)
            
            # Clean up any corrupted modifications before applying
            self._cleanup_corrupted_modifications_datum()
            
            # Apply field modifications to the data (also optimized)
            df = self._apply_field_modifications_datum(df, client)
            
            return df
        except Exception as e:
            print(f"✗ Error loading from Datum: {e}")
            return pd.DataFrame()
    
    def _apply_field_modifications_datum(self, df: pd.DataFrame, client) -> pd.DataFrame:
        """
        Apply field modifications to the dataframe via Datum proxy.
        Tracks the FIRST old_value as the original value for each cell.
        
        OPTIMIZED: Only queries mods for PKs present in the current dataframe.
        """
        try:
            if df.empty:
                self.edited_cells = {}
                return df
            
            mods_table = self.app_config.database.mods_table
            pk_columns = self.app_config.table.primary_key
            mods_table_sql = _format_table_name(mods_table)
            
            # OPTIMIZED: Build list of PKs from current dataframe
            pk_values = []
            pk_index = {}  # Map pk_json -> row indices for fast lookup
            for idx, row in df.iterrows():
                pk_dict = {pk: row[pk] for pk in pk_columns if pk in df.columns}
                serializable_pk = {}
                for k, v in pk_dict.items():
                    if hasattr(v, 'item'):
                        serializable_pk[k] = v.item()
                    elif pd.isna(v):
                        serializable_pk[k] = None
                    else:
                        serializable_pk[k] = v
                pk_json = json.dumps(serializable_pk, sort_keys=True)
                pk_values.append(pk_json)
                if pk_json not in pk_index:
                    pk_index[pk_json] = []
                pk_index[pk_json].append(idx)
            
            if not pk_values:
                self.edited_cells = {}
                return df
            
            # OPTIMIZED: Query only modifications for PKs in current view
            pk_array = "ARRAY[" + ",".join(f"'{pv}'::jsonb" for pv in pk_values) + "]"
            
            mods_query = f"""
            SELECT row_pk, column_name, old_value, new_value 
            FROM {mods_table_sql}
            WHERE mod_type = 'field_modification' 
              AND undone = FALSE
              AND row_pk = ANY({pk_array})
            ORDER BY created_at ASC
            """
            
            print(f"[Datum DEBUG] Applying field modifications, query: {mods_query[:200]}...")
            
            response = client.execute_sql(
                sql=mods_query,
                database=self.app_config.database.datum_database,
                schema=self.app_config.database.datum_schema,
                service_name=self.app_config.database.datum_service_name,
            )
            
            print(f"[Datum DEBUG] Found {len(response.data)} field modifications to apply")
            
            # Store edited cells info
            self.edited_cells = {}
            
            if response.data:
                for idx, mod in enumerate(response.data):
                    row_pk_raw = mod.get("row_pk", {})
                    row_pk = row_pk_raw
                    if isinstance(row_pk, str):
                        row_pk = json.loads(row_pk)
                    col_name = mod.get("column_name")
                    old_value = mod.get("old_value")
                    new_value = mod.get("new_value")
                    
                    print(f"[Datum DEBUG] Mod {idx}: pk={row_pk}, col={col_name}, old={old_value[:30] if old_value else None}..., new={new_value[:30] if new_value else None}...")
                    
                    # Skip modifications with empty row_pk
                    if not row_pk:
                        print(f"[Datum DEBUG] Skipping mod {idx}: empty row_pk")
                        continue
                    
                    if col_name in df.columns:
                        # OPTIMIZED: Use pre-built index instead of building mask
                        pk_json = json.dumps(row_pk, sort_keys=True)
                        row_indices = pk_index.get(pk_json, [])
                        
                        if row_indices:
                            pk_tuple = tuple(sorted((k, str(v)) for k, v in row_pk.items()))
                            cell_key = (pk_tuple, col_name)
                            
                            if cell_key not in self.edited_cells:
                                self.edited_cells[cell_key] = {
                                    "original": old_value,
                                    "current": new_value
                                }
                            else:
                                self.edited_cells[cell_key]["current"] = new_value
                            
                            # Apply modification using direct index access
                            for row_idx in row_indices:
                                df.at[row_idx, col_name] = new_value
                        else:
                            print(f"[Datum DEBUG] No matching row found for pk_json={pk_json}")
                    else:
                        print(f"[Datum DEBUG] Column {col_name} not in dataframe")
            
            mod_count = len(self.edited_cells)
            if mod_count > 0:
                print(f"✓ Applied {mod_count} modifications to data")
            
            return df
        except Exception as e:
            print(f"⚠ Could not apply field modifications via Datum: {e}")
            self.edited_cells = {}
            return df

    def _get_display_columns(self) -> List[str]:
        """Get default display columns from configuration."""
        if self.app_config.table.default_columns:
            return [col for col in self.app_config.table.default_columns if col in self.df.columns]
        return self.all_columns[:12]  # Default to first 12 columns
    
    def load_modifications_log(self, force_refresh: bool = False) -> List[Dict]:
        """
        Load modifications log from database with caching.
        
        Args:
            force_refresh: If True, bypass cache and reload from DB
        """
        import time
        
        # Use cached data if available and not expired (cache for 5 seconds)
        cache_ttl = 5.0
        if not force_refresh and self._mods_log_cache is not None:
            if time.time() - self._mods_log_cache_time < cache_ttl:
                return self._mods_log_cache
        
        # Load from database
        if self.app_config.database.mode == "datum":
            result = self._load_modifications_from_datum()
        else:
            result = self._load_modifications_from_db()
        
        # Update cache
        self._mods_log_cache = result
        self._mods_log_cache_time = time.time()
        
        return result
    
    def invalidate_mods_cache(self):
        """Invalidate the modifications log cache (call after making changes)."""
        self._mods_log_cache = None
        self._mods_log_cache_time = 0
    
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
            mods_table_sql = _format_table_name(mods_table)
            
            query = f'''SELECT id, row_pk, column_name, old_value, new_value, 
                       mod_type, created_by, created_at, undone
                       FROM {mods_table_sql} ORDER BY created_at ASC'''
            
            print(f"[Datum DEBUG] Loading modifications from {mods_table_sql}, database={self.app_config.database.datum_database}, schema={self.app_config.database.datum_schema}")
            
            response = client.execute_sql(
                sql=query,
                database=self.app_config.database.datum_database,
                schema=self.app_config.database.datum_schema,
                service_name=self.app_config.database.datum_service_name,
            )
            
            print(f"[Datum DEBUG] Loaded {len(response.data)} raw modifications")
            # Show latest few IDs to verify new entries
            if response.data:
                latest_ids = [r.get("id") for r in response.data[-5:]]
                print(f"[Datum DEBUG] Latest 5 modification IDs: {latest_ids}")
            
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
            
            result = self._aggregate_approval_rejection_entries(log)
            print(f"[Datum DEBUG] After aggregation: {len(result)} modifications")
            return result
        except Exception as e:
            print(f"✗ Error loading modifications from Datum: {e}")
            import traceback
            traceback.print_exc()
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
        db_mode = self.app_config.database.mode
        print(f"[Datum DEBUG] save_modification_to_db called: mode={db_mode}, pk={row_pk}, col={column}")
        
        if db_mode == "datum":
            return self._save_modification_to_datum(row_pk, column, old_value, new_value, mod_type)
        
        print(f"[Datum DEBUG] Using direct SQLAlchemy mode (not datum)")
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
                            (row_pk, column_name, old_value, new_value, mod_type, created_by)
                        VALUES 
                            (:row_pk, :column_name, :old_value, :new_value, :mod_type, :created_by)
                        RETURNING id
                    '''),
                    {
                        "row_pk": json.dumps(row_pk),
                        "column_name": column,
                        "old_value": str(old_value) if old_value is not None else None,
                        "new_value": str(new_value) if new_value is not None else None,
                        "mod_type": mod_type,
                        "created_by": self.username
                    }
                )
                mod_id = result.scalar()
                conn.commit()
                
                # Invalidate cache after successful insert
                self.invalidate_mods_cache()
                
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
            mods_table_sql = _format_table_name(mods_table)
            
            old_val_str = str(old_value) if old_value is not None else None
            new_val_str = str(new_value) if new_value is not None else None
            
            # Convert numpy/pandas types to native Python types for JSON serialization
            serializable_pk = {}
            for k, v in row_pk.items():
                if hasattr(v, 'item'):  # numpy scalar
                    serializable_pk[k] = v.item()
                elif pd.isna(v):
                    serializable_pk[k] = None
                else:
                    serializable_pk[k] = v
            
            # Use sort_keys=True for consistent JSON representation
            row_pk_json = json.dumps(serializable_pk, sort_keys=True).replace("'", "''")
            
            # Escape username for SQL
            safe_username = self.username.replace("'", "''") if self.username else 'unknown'
            
            # Escape old/new values for SQL (handle single quotes)
            old_val_escaped = old_val_str.replace("'", "''") if old_val_str else None
            new_val_escaped = new_val_str.replace("'", "''") if new_val_str else None
            
            # Escape column name for SQL
            column_escaped = column.replace("'", "''")
            
            # INSERT without created_by (column may not exist in all databases)
            sql = f'''
                INSERT INTO {mods_table_sql} 
                    (row_pk, column_name, old_value, new_value, mod_type)
                VALUES 
                    ('{row_pk_json}'::jsonb, '{column_escaped}', 
                     {f"'{old_val_escaped}'" if old_val_escaped else 'NULL'}, 
                     {f"'{new_val_escaped}'" if new_val_escaped else 'NULL'}, 
                     '{mod_type}')
                RETURNING id
            '''
            
            print(f"[Datum DEBUG] Saving modification: pk={row_pk_json}, col={column}, old={old_val_str[:50] if old_val_str else None}..., new={new_val_str[:50] if new_val_str else None}...")
            print(f"[Datum DEBUG] INSERT SQL table: {mods_table_sql}, database: {self.app_config.database.datum_database}, schema: {self.app_config.database.datum_schema}")
            print(f"[Datum DEBUG] Full SQL: {sql}")
            
            response = client.execute_sql(
                sql=sql,
                database=self.app_config.database.datum_database,
                schema=self.app_config.database.datum_schema,
                service_name=self.app_config.database.datum_service_name,
            )
            
            print(f"[Datum DEBUG] Response data: {response.data}")
            
            if response.data:
                mod_id = response.data[0].get("id")
                print(f"[Datum DEBUG] ✓ Saved modification with id={mod_id}")
                
                # Verify the row actually exists by querying it back
                verify_sql = f"SELECT id, row_pk, column_name, mod_type FROM {mods_table_sql} WHERE id = {mod_id}"
                try:
                    verify_response = client.execute_sql(
                        sql=verify_sql,
                        database=self.app_config.database.datum_database,
                        schema=self.app_config.database.datum_schema,
                        service_name=self.app_config.database.datum_service_name,
                    )
                    print(f"[Datum DEBUG] Verification query result: {verify_response.data}")
                    
                    # Also count total modifications
                    count_sql = f"SELECT COUNT(*) as total FROM {mods_table_sql}"
                    count_response = client.execute_sql(
                        sql=count_sql,
                        database=self.app_config.database.datum_database,
                        schema=self.app_config.database.datum_schema,
                        service_name=self.app_config.database.datum_service_name,
                    )
                    print(f"[Datum DEBUG] Total modifications in table: {count_response.data}")
                except Exception as ve:
                    print(f"[Datum DEBUG] Verification query failed: {ve}")
                
                # Invalidate cache after successful insert
                self.invalidate_mods_cache()
                
                return mod_id
            print(f"[Datum DEBUG] ⚠ No id returned from INSERT")
            return None
        except Exception as e:
            print(f"✗ Error saving modification to Datum: {e}")
            import traceback
            traceback.print_exc()
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
                
                # Invalidate cache after successful update
                self.invalidate_mods_cache()
                
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
            mods_table_sql = _format_table_name(mods_table)
            
            client.execute_sql(
                sql=f'UPDATE {mods_table_sql} SET undone = TRUE WHERE id = {mod_id}',
                database=self.app_config.database.datum_database,
                schema=self.app_config.database.datum_schema,
                service_name=self.app_config.database.datum_service_name,
            )
            
            # Invalidate cache after successful update
            self.invalidate_mods_cache()
            
            return True
        except Exception as e:
            print(f"✗ Error marking modification undone via Datum: {e}")
            return False

    def cleanup_corrupted_modifications(self):
        """
        Delete modifications with empty row_pk from database.
        These records are corrupted and will cause all rows to be updated.
        """
        if self.app_config.database.mode == "datum":
            return self._cleanup_corrupted_modifications_datum()
        return 0
    
    def _cleanup_corrupted_modifications_datum(self):
        """Clean up corrupted modifications via Datum."""
        try:
            from ..adapter.datum import DatumClient
            
            base_url = self.app_config.database.datum_base_url or os.environ.get("DATUM_BASE_URL", "")
            token = self.app_config.database.datum_token or os.environ.get("DATUM_API_TOKEN", "")
            
            if not base_url or not token:
                print("⚠ Datum credentials not configured for cleanup")
                return 0
            
            client = DatumClient(base_url=base_url, token=token)
            mods_table = self.app_config.database.mods_table
            mods_table_sql = _format_table_name(mods_table)
            
            # First count how many will be deleted
            count_sql = f"""
                SELECT COUNT(*) as cnt FROM {mods_table_sql}
                WHERE mod_type = 'field_modification'
                  AND (row_pk IS NULL OR row_pk = '{{}}'::jsonb)
            """
            count_response = client.execute_sql(
                sql=count_sql,
                database=self.app_config.database.datum_database,
                schema=self.app_config.database.datum_schema,
                service_name=self.app_config.database.datum_service_name,
            )
            count = count_response.data[0].get("cnt", 0) if count_response.data else 0
            
            if count > 0:
                # Delete corrupted records
                delete_sql = f"""
                    DELETE FROM {mods_table_sql}
                    WHERE mod_type = 'field_modification'
                      AND (row_pk IS NULL OR row_pk = '{{}}'::jsonb)
                """
                client.execute_sql(
                    sql=delete_sql,
                    database=self.app_config.database.datum_database,
                    schema=self.app_config.database.datum_schema,
                    service_name=self.app_config.database.datum_service_name,
                )
                print(f"✓ Cleaned up {count} corrupted field_modification records with empty row_pk")
            
            return count
        except Exception as e:
            print(f"✗ Error cleaning up corrupted modifications: {e}")
            return 0

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
            data_table_sql = _format_table_name(data_table)
            
            client.execute_sql(
                sql=f'UPDATE {data_table_sql} SET "{column}" = {new_val_sql} WHERE {where_clause}',
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
        
        if self.app_config.database.mode == "datum":
            return self._ensure_state_table_exists_datum()
        
        try:
            from sqlalchemy import text
            
            state_table = self.app_config.database.state_table
            
            # Parse schema.table format
            if '.' in state_table:
                schema, table_name = state_table.split('.', 1)
                schema_sql = schema
                table_sql = _format_table_name(state_table)
            else:
                schema_sql = None
                table_sql = _format_table_name(state_table)
            
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

    def _ensure_state_table_exists_datum(self) -> bool:
        """Create UI state table via Datum proxy if it doesn't exist."""
        try:
            from ..adapter.datum import DatumClient
            
            base_url = self.app_config.database.datum_base_url or os.environ.get("DATUM_BASE_URL", "")
            token = self.app_config.database.datum_token or os.environ.get("DATUM_API_TOKEN", "")
            
            if not base_url or not token:
                return False
            
            client = DatumClient(base_url=base_url, token=token)
            state_table = self.app_config.database.state_table
            state_table_sql = _format_table_name(state_table)
            
            # Parse schema for CREATE SCHEMA
            schema_sql = None
            if '.' in state_table:
                schema = state_table.split('.', 1)[0]
                schema_sql = f'"{schema}"'
            
            # Create schema if needed
            if schema_sql:
                try:
                    client.execute_sql(
                        sql=f'CREATE SCHEMA IF NOT EXISTS {schema_sql}',
                        database=self.app_config.database.datum_database,
                        schema=self.app_config.database.datum_schema,
                        service_name=self.app_config.database.datum_service_name,
                    )
                except Exception:
                    pass  # Schema may already exist
            
            # Create table if not exists - DDL auto-commits
            client.execute_sql(
                sql=f'''
                    CREATE TABLE IF NOT EXISTS {state_table_sql} (
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
                ''',
                database=self.app_config.database.datum_database,
                schema=self.app_config.database.datum_schema,
                service_name=self.app_config.database.datum_service_name,
            )
            
            self._state_table_checked = True
            return True
        except Exception as e:
            print(f"⚠ Could not create state table via Datum: {e}")
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
        if self.app_config.database.mode == "datum":
            return self._save_ui_state_datum(
                sort_column, sort_ascending, current_page, 
                rows_per_page, filters, column_preset
            )
        
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

    def _save_ui_state_datum(
        self,
        sort_column: str,
        sort_ascending: bool,
        current_page: int,
        rows_per_page: int,
        filters: dict,
        column_preset: str
    ) -> bool:
        """Save UI state via Datum proxy."""
        # Ensure state table exists first
        self._ensure_state_table_exists()
        
        try:
            from ..adapter.datum import DatumClient
            
            base_url = self.app_config.database.datum_base_url or os.environ.get("DATUM_BASE_URL", "")
            token = self.app_config.database.datum_token or os.environ.get("DATUM_API_TOKEN", "")
            
            if not base_url or not token:
                print("⚠ Datum credentials not configured for state")
                return False
            
            client = DatumClient(base_url=base_url, token=token)
            state_table = self.app_config.database.state_table
            state_table_sql = _format_table_name(state_table)
            
            # Escape values for SQL
            filters_json = json.dumps(filters).replace("'", "''") if filters else 'null'
            sort_col_sql = f"'{sort_column}'" if sort_column else 'NULL'
            preset_sql = f"'{column_preset}'" if column_preset else 'NULL'
            user_sql = self.username.replace("'", "''")
            
            sql = f'''
                INSERT INTO {state_table_sql} 
                    (user_id, session_id, sort_column, sort_ascending, 
                     current_page, rows_per_page, filters, column_preset, updated_at)
                VALUES 
                    ('{user_sql}', 'default_session', {sort_col_sql}, {str(sort_ascending).upper()},
                     {current_page}, {rows_per_page}, '{filters_json}'::jsonb, {preset_sql}, NOW())
                ON CONFLICT (user_id, session_id) 
                DO UPDATE SET
                    sort_column = {sort_col_sql},
                    sort_ascending = {str(sort_ascending).upper()},
                    current_page = {current_page},
                    rows_per_page = {rows_per_page},
                    filters = '{filters_json}'::jsonb,
                    column_preset = {preset_sql},
                    updated_at = NOW()
            '''
            
            client.execute_sql(
                sql=sql,
                database=self.app_config.database.datum_database,
                schema=self.app_config.database.datum_schema,
                service_name=self.app_config.database.datum_service_name,
            )
            return True
        except Exception as e:
            print(f"⚠ Could not save UI state via Datum: {e}")
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
        
        if self.app_config.database.mode == "datum":
            return self._load_ui_state_datum(default_state)
        
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

    def _load_ui_state_datum(self, default_state: Dict) -> Dict:
        """Load UI state via Datum proxy."""
        # Ensure state table exists first
        self._ensure_state_table_exists()
        
        try:
            from ..adapter.datum import DatumClient
            
            base_url = self.app_config.database.datum_base_url or os.environ.get("DATUM_BASE_URL", "")
            token = self.app_config.database.datum_token or os.environ.get("DATUM_API_TOKEN", "")
            
            if not base_url or not token:
                return default_state
            
            client = DatumClient(base_url=base_url, token=token)
            state_table = self.app_config.database.state_table
            state_table_sql = _format_table_name(state_table)
            user_sql = self.username.replace("'", "''")
            
            response = client.execute_sql(
                sql=f'''
                    SELECT sort_column, sort_ascending, current_page, 
                           rows_per_page, filters, column_preset
                    FROM {state_table_sql}
                    WHERE user_id = '{user_sql}' AND session_id = 'default_session'
                ''',
                database=self.app_config.database.datum_database,
                schema=self.app_config.database.datum_schema,
                service_name=self.app_config.database.datum_service_name,
            )
            
            if response.data and len(response.data) > 0:
                row = response.data[0]
                filters = row.get("filters", {})
                if isinstance(filters, str):
                    filters = json.loads(filters)
                elif filters is None:
                    filters = {}
                
                return {
                    "sort_column": row.get("sort_column") or default_state["sort_column"],
                    "sort_ascending": row.get("sort_ascending") if row.get("sort_ascending") is not None else default_state["sort_ascending"],
                    "current_page": row.get("current_page") or default_state["current_page"],
                    "rows_per_page": row.get("rows_per_page") or default_state["rows_per_page"],
                    "filters": filters,
                    "column_preset": row.get("column_preset")
                }
        except Exception as e:
            print(f"⚠ Could not load UI state via Datum: {e}")
        
        return default_state

    # =========================================================================
    # Preset Management (Datum-aware)
    # =========================================================================
    
    def _get_preset_table_name(self) -> str:
        """Generate the user preset table name: {data_table_base}_{username}_column_presets"""
        # Extract base table name (without schema)
        data_table = self.app_config.database.data_table
        if '.' in data_table:
            base_name = data_table.split('.')[-1]
        else:
            base_name = data_table
        safe_username = "".join(c if c.isalnum() else "_" for c in self.username).lower()
        
        # Include schema if present
        if '.' in data_table:
            schema = data_table.split('.')[0]
            return f"{schema}.{base_name}_{safe_username}_column_presets"
        return f"{base_name}_{safe_username}_column_presets"
    
    def _ensure_preset_table_exists(self) -> bool:
        """Create the preset table if it doesn't exist."""
        if self.app_config.database.mode == "datum":
            return self._ensure_preset_table_exists_datum()
        
        try:
            from sqlalchemy import text
            
            preset_table = self._get_preset_table_name()
            preset_table_sql = _format_table_name(preset_table)
            
            engine = self._get_engine()
            if engine is None:
                return False
            
            with engine.connect() as conn:
                conn.execute(text(f'''
                    CREATE TABLE IF NOT EXISTS {preset_table_sql} (
                        id SERIAL PRIMARY KEY,
                        preset_name VARCHAR(255) NOT NULL UNIQUE,
                        columns JSONB NOT NULL,
                        is_default BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                '''))
                conn.commit()
            return True
        except Exception as e:
            print(f"⚠ Could not create preset table: {e}")
            return False
    
    def _ensure_preset_table_exists_datum(self) -> bool:
        """Create preset table via Datum proxy."""
        try:
            from ..adapter.datum import DatumClient
            
            base_url = self.app_config.database.datum_base_url or os.environ.get("DATUM_BASE_URL", "")
            token = self.app_config.database.datum_token or os.environ.get("DATUM_API_TOKEN", "")
            
            if not base_url or not token:
                return False
            
            client = DatumClient(base_url=base_url, token=token)
            preset_table = self._get_preset_table_name()
            preset_table_sql = _format_table_name(preset_table)
            
            client.execute_sql(
                sql=f'''
                    CREATE TABLE IF NOT EXISTS {preset_table_sql} (
                        id SERIAL PRIMARY KEY,
                        preset_name VARCHAR(255) NOT NULL UNIQUE,
                        columns JSONB NOT NULL,
                        is_default BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''',
                database=self.app_config.database.datum_database,
                schema=self.app_config.database.datum_schema,
                service_name=self.app_config.database.datum_service_name,
            )
            return True
        except Exception as e:
            print(f"⚠ Could not create preset table via Datum: {e}")
            return False
    
    def save_preset(self, preset_name: str, columns: Any, is_default: bool = False) -> Optional[int]:
        """Save a column preset."""
        self._ensure_preset_table_exists()
        
        if self.app_config.database.mode == "datum":
            return self._save_preset_datum(preset_name, columns, is_default)
        
        try:
            from sqlalchemy import text
            
            preset_table = self._get_preset_table_name()
            preset_table_sql = _format_table_name(preset_table)
            
            engine = self._get_engine()
            if engine is None:
                return None
            
            with engine.connect() as conn:
                if is_default:
                    conn.execute(text(f'UPDATE {preset_table_sql} SET is_default = FALSE WHERE is_default = TRUE'))
                
                result = conn.execute(
                    text(f'''
                        INSERT INTO {preset_table_sql} (preset_name, columns, is_default, updated_at)
                        VALUES (:preset_name, :columns, :is_default, CURRENT_TIMESTAMP)
                        ON CONFLICT (preset_name) 
                        DO UPDATE SET 
                            columns = EXCLUDED.columns,
                            is_default = EXCLUDED.is_default,
                            updated_at = CURRENT_TIMESTAMP
                        RETURNING id
                    '''),
                    {
                        "preset_name": preset_name,
                        "columns": json.dumps(columns),
                        "is_default": is_default
                    }
                )
                preset_id = result.scalar()
                conn.commit()
                return preset_id
        except Exception as e:
            print(f"⚠ Could not save preset: {e}")
            return None
    
    def _save_preset_datum(self, preset_name: str, columns: Any, is_default: bool) -> Optional[int]:
        """Save preset via Datum proxy."""
        try:
            from ..adapter.datum import DatumClient
            
            base_url = self.app_config.database.datum_base_url or os.environ.get("DATUM_BASE_URL", "")
            token = self.app_config.database.datum_token or os.environ.get("DATUM_API_TOKEN", "")
            
            if not base_url or not token:
                return None
            
            client = DatumClient(base_url=base_url, token=token)
            preset_table = self._get_preset_table_name()
            preset_table_sql = _format_table_name(preset_table)
            
            # Clear existing default if setting new default
            if is_default:
                client.execute_sql(
                    sql=f'UPDATE {preset_table_sql} SET is_default = FALSE WHERE is_default = TRUE',
                    database=self.app_config.database.datum_database,
                    schema=self.app_config.database.datum_schema,
                    service_name=self.app_config.database.datum_service_name,
                )
            
            columns_json = json.dumps(columns).replace("'", "''")
            preset_name_sql = preset_name.replace("'", "''")
            
            # Single UPSERT auto-commits
            sql = f'''
                    INSERT INTO {preset_table_sql} (preset_name, columns, is_default, updated_at)
                    VALUES ('{preset_name_sql}', '{columns_json}'::jsonb, {str(is_default).upper()}, CURRENT_TIMESTAMP)
                    ON CONFLICT (preset_name) 
                    DO UPDATE SET 
                        columns = EXCLUDED.columns,
                        is_default = EXCLUDED.is_default,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id
                '''
            
            print(f"[Datum DEBUG] Saving preset: name={preset_name}, is_default={is_default}")
            print(f"[Datum DEBUG] Preset table: {preset_table_sql}, database: {self.app_config.database.datum_database}, schema: {self.app_config.database.datum_schema}")
            print(f"[Datum DEBUG] Preset SQL: {sql}")
            
            response = client.execute_sql(
                sql=sql,
                database=self.app_config.database.datum_database,
                schema=self.app_config.database.datum_schema,
                service_name=self.app_config.database.datum_service_name,
            )
            
            print(f"[Datum DEBUG] Preset save response: {response.data}")
            
            if response.data:
                preset_id = response.data[0].get("id")
                print(f"[Datum DEBUG] Preset saved with ID: {preset_id}")
                return preset_id
            print("[Datum DEBUG] No data returned from preset save")
            return None
        except Exception as e:
            print(f"⚠ Could not save preset via Datum: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_presets(self) -> List[Dict]:
        """Load all presets for the current user."""
        self._ensure_preset_table_exists()
        
        if self.app_config.database.mode == "datum":
            return self._get_presets_datum()
        
        try:
            from sqlalchemy import text
            
            preset_table = self._get_preset_table_name()
            preset_table_sql = _format_table_name(preset_table)
            
            engine = self._get_engine()
            if engine is None:
                return []
            
            with engine.connect() as conn:
                result = conn.execute(text(f'''
                    SELECT id, preset_name, columns, is_default, created_at, updated_at
                    FROM {preset_table_sql}
                    ORDER BY preset_name
                '''))
                
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
        except Exception as e:
            print(f"⚠ Could not load presets: {e}")
            return []
    
    def _get_presets_datum(self) -> List[Dict]:
        """Load presets via Datum proxy."""
        try:
            from ..adapter.datum import DatumClient
            
            base_url = self.app_config.database.datum_base_url or os.environ.get("DATUM_BASE_URL", "")
            token = self.app_config.database.datum_token or os.environ.get("DATUM_API_TOKEN", "")
            
            if not base_url or not token:
                return []
            
            client = DatumClient(base_url=base_url, token=token)
            preset_table = self._get_preset_table_name()
            preset_table_sql = _format_table_name(preset_table)
            
            query = f'''
                    SELECT id, preset_name, columns, is_default, created_at, updated_at
                    FROM {preset_table_sql}
                    ORDER BY preset_name
                '''
            
            response = client.execute_sql(
                sql=query,
                database=self.app_config.database.datum_database,
                schema=self.app_config.database.datum_schema,
                service_name=self.app_config.database.datum_service_name,
            )
            
            presets = []
            for row in response.data:
                columns = row.get("columns", {})
                if isinstance(columns, str):
                    columns = json.loads(columns)
                presets.append({
                    "id": row.get("id"),
                    "preset_name": row.get("preset_name"),
                    "columns": columns,
                    "is_default": row.get("is_default", False),
                    "created_at": row.get("created_at"),
                    "updated_at": row.get("updated_at")
                })
            return presets
        except Exception as e:
            print(f"⚠ Could not load presets via Datum: {e}")
            return []
    
    def delete_preset(self, preset_name: str) -> bool:
        """Delete a preset by name."""
        if self.app_config.database.mode == "datum":
            return self._delete_preset_datum(preset_name)
        
        try:
            from sqlalchemy import text
            
            preset_table = self._get_preset_table_name()
            preset_table_sql = _format_table_name(preset_table)
            
            engine = self._get_engine()
            if engine is None:
                return False
            
            with engine.connect() as conn:
                result = conn.execute(
                    text(f'DELETE FROM {preset_table_sql} WHERE preset_name = :preset_name'),
                    {"preset_name": preset_name}
                )
                conn.commit()
                return result.rowcount > 0
        except Exception as e:
            print(f"⚠ Could not delete preset: {e}")
            return False
    
    def _delete_preset_datum(self, preset_name: str) -> bool:
        """Delete preset via Datum proxy."""
        try:
            from ..adapter.datum import DatumClient
            
            base_url = self.app_config.database.datum_base_url or os.environ.get("DATUM_BASE_URL", "")
            token = self.app_config.database.datum_token or os.environ.get("DATUM_API_TOKEN", "")
            
            if not base_url or not token:
                return False
            
            client = DatumClient(base_url=base_url, token=token)
            preset_table = self._get_preset_table_name()
            preset_table_sql = _format_table_name(preset_table)
            preset_name_sql = preset_name.replace("'", "''")
            
            client.execute_sql(
                sql=f"DELETE FROM {preset_table_sql} WHERE preset_name = '{preset_name_sql}'",
                database=self.app_config.database.datum_database,
                schema=self.app_config.database.datum_schema,
                service_name=self.app_config.database.datum_service_name,
            )
            return True
        except Exception as e:
            print(f"⚠ Could not delete preset via Datum: {e}")
            return False
    
    def get_default_preset(self) -> Optional[Dict]:
        """Get the default preset for current user."""
        presets = self.get_presets()
        for p in presets:
            if p.get("is_default"):
                return p
        return None


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
