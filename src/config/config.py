"""
Configuration and shared state for Epitopes Data Editor PyShiny App

This module provides backward-compatible access to configuration.
Database-only mode - no CSV/JSON fallback.
"""

import json
import os
import pandas as pd
from pathlib import Path

# Import new configuration system (same package)
from .app_config_schema import AppConfig, load_config


def _format_table_name(table_name: str) -> str:
    """
    Format table name for SQL queries.
    
    If table_name contains a dot (schema.table), don't quote the whole thing.
    Otherwise, quote it to handle special characters.
    """
    if '.' in table_name:
        # Schema-qualified: schema.table -> schema.table (no quotes)
        parts = table_name.split('.', 1)
        return f'{parts[0]}.{parts[1]}'
    else:
        # Simple table name - quote it
        return f'"{table_name}"'


# Load application configuration
app_config = load_config()

# Setup paths (backward compatible - project root is 2 levels up from src/config/)
project_root = Path(__file__).parent.parent.parent
data_dir = project_root / "data"
data_dir.mkdir(exist_ok=True)


# Load data based on source type (database only)
def _load_initial_data() -> pd.DataFrame:
    """Load initial data from database."""
    if app_config.database.mode == "datum":
        return _load_from_datum()
    return _load_from_database()


def load_data_from_source() -> pd.DataFrame:
    """
    Public function to load fresh data from the database.
    Call this on each session to get the latest data.
    """
    return _load_initial_data()


def _get_datum_client():
    """Get a configured DatumClient instance."""
    from src.adapter.datum import DatumClient
    
    # Check config first, then environment variables (for RS Connect deployment)
    base_url = app_config.database.datum_base_url or os.environ.get("DATUM_BASE_URL", "")
    token = app_config.database.datum_token or os.environ.get("DATUM_API_TOKEN", "")
    
    if not base_url or not token:
        raise ValueError("Datum mode requires datum_base_url and datum_token (or DATUM_BASE_URL/DATUM_API_TOKEN env vars)")
    
    return DatumClient(base_url=base_url, token=token)


def _execute_sql_via_datum(sql: str) -> list[dict]:
    """Execute SQL via Datum proxy and return list of row dicts."""
    client = _get_datum_client()
    response = client.execute_sql(
        sql=sql,
        database=app_config.database.datum_database,
        schema=app_config.database.datum_schema,
        service_name=app_config.database.datum_service_name,
    )
    return response.data


def _load_from_datum() -> pd.DataFrame:
    """Load data from PostgreSQL via Datum proxy service."""
    try:
        data_table = app_config.database.data_table
        mods_table = app_config.database.mods_table
        pk_columns = app_config.table.primary_key
        
        # Format table names for SQL
        data_table_sql = _format_table_name(data_table)
        mods_table_sql = _format_table_name(mods_table)
        
        # Build query that gets base data with modification status
        pk_conditions = " AND ".join(
            f"m.row_pk->>'{pk}' = d.\"{pk}\"::text"
            for pk in pk_columns
        )
        
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
        
        data = _execute_sql_via_datum(query)
        df = pd.DataFrame(data)
        
        # Apply field modifications
        mods_query = f"""
        SELECT row_pk, column_name, new_value 
        FROM {mods_table_sql} 
        WHERE mod_type = 'field_modification' 
          AND undone = FALSE
        ORDER BY created_at ASC
        """
        
        try:
            mods_data = _execute_sql_via_datum(mods_query)
            if mods_data:
                for mod in mods_data:
                    row_pk = mod['row_pk']
                    col_name = mod['column_name']
                    new_value = mod['new_value']
                    
                    if col_name in df.columns:
                        mask = pd.Series([True] * len(df))
                        for pk_col in pk_columns:
                            if pk_col in row_pk and pk_col in df.columns:
                                mask &= (df[pk_col].astype(str) == str(row_pk[pk_col]))
                        if mask.any():
                            df.loc[mask, col_name] = new_value
                
                print(f"✓ Applied {len(mods_data)} modifications via Datum")
        except Exception as e:
            print(f"⚠ Could not load modifications via Datum: {e}")
        
        print(f"✓ Loaded {len(df)} rows via Datum: {data_table}")
        return df
    except Exception as e:
        print(f"✗ Datum error: {e}. Falling back to CSV.")
        return pd.read_csv(csv_path)


def _load_from_database() -> pd.DataFrame:
    """Load data from PostgreSQL database with modifications applied."""
    try:
        from sqlalchemy import create_engine, text
        
        conn_string = app_config.database.connection_string
        data_table = app_config.database.data_table
        mods_table = app_config.database.mods_table
        pk_columns = app_config.table.primary_key
        
        engine = create_engine(conn_string)
        
        # Format table names for SQL
        data_table_sql = _format_table_name(data_table)
        mods_table_sql = _format_table_name(mods_table)
        
        # Build query that applies latest modifications to each row
        # This query gets the base data and overlays any field modifications
        pk_conditions = " AND ".join(
            f'm.row_pk->>\'{pk}\' = d."{pk}"::text'
            for pk in pk_columns
        )
        
        # Query that gets base data with modification status
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
        
        df = pd.read_sql(query, engine)
        
        # Now apply any field modifications to update the actual cell values
        # Get all non-undone field modifications
        mods_query = f"""
        SELECT row_pk, column_name, new_value 
        FROM {mods_table_sql} 
        WHERE mod_type = 'field_modification' 
          AND undone = FALSE
        ORDER BY created_at ASC
        """
        
        try:
            mods_df = pd.read_sql(mods_query, engine)
            
            if len(mods_df) > 0:
                # Apply modifications to the dataframe
                for _, mod in mods_df.iterrows():
                    row_pk = mod['row_pk']  # This is a JSON dict
                    col_name = mod['column_name']
                    new_value = mod['new_value']
                    
                    if col_name in df.columns:
                        # Find the row(s) matching the PK
                        mask = pd.Series([True] * len(df))
                        for pk_col in pk_columns:
                            if pk_col in row_pk and pk_col in df.columns:
                                mask &= (df[pk_col].astype(str) == str(row_pk[pk_col]))
                        
                        if mask.any():
                            df.loc[mask, col_name] = new_value
                
                print(f"✓ Applied {len(mods_df)} modifications to data")
        except Exception as e:
            print(f"⚠ Could not load modifications: {e}")
        
        return df
    except ImportError as e:
        print(f"✗ SQLAlchemy not installed: {e}")
        return pd.DataFrame()
    except Exception as e:
        print(f"✗ Database error: {e}")
        return pd.DataFrame()

df_original = _load_initial_data()

# Define columns to display from config or fallback
def _get_display_columns() -> list[str]:
    """Get default display columns from configuration."""
    if app_config.table.default_columns:
        return [col for col in app_config.table.default_columns if col in df_original.columns]
    return [
        "PatientID",
        "Variant_key",
        "Gene_names",
        "Wt_nmer",
        "Mut_nmer",
        "Status",
        "Comments",
        "aa_changes",
        "cDNA_changes",
        "WtNMerReviewed",
        "MutNMerReviewed",
        "Max_Read2Count",
    ]

display_columns = _get_display_columns()

# Filter to available columns
display_columns = [col for col in display_columns if col in df_original.columns]

# All available columns from the dataframe
all_columns = list(df_original.columns)

# Modifications log file path from config
def _get_modifications_log_path() -> Path:
    """Get modifications log path from configuration."""
    if app_config.persistence.modifications_log_path:
        p = Path(app_config.persistence.modifications_log_path)
        if not p.is_absolute():
            p = project_root / p
        return p
    return data_dir / "modifications_log.json"

modifications_log_path = _get_modifications_log_path()


def load_modifications_log():
    """Load modifications log from database."""
    if app_config.database.mode == "datum":
        return _load_modifications_from_datum()
    return _load_modifications_from_db()


def _aggregate_approval_rejection_entries(log: list) -> list:
    """
    Group individual approval/rejection DB rows into batch entries for UI display.
    
    DB stores one row per approved/rejected row, but UI expects grouped entries like:
    {type: "approval", details: {approved_rows: [...], approved_row_count: N}}
    """
    from collections import defaultdict
    
    result = []
    # Group by (timestamp truncated to second, type) to batch entries made at same time
    approval_groups = defaultdict(list)
    rejection_groups = defaultdict(list)
    
    for entry in log:
        mod_type = entry.get("type")
        if mod_type == "approval":
            # Use timestamp (truncated to second) as grouping key
            ts = entry.get("timestamp", "")[:19]  # "2026-02-08T01:06:46"
            row_pk = entry.get("details", {}).get("row_pk", {})
            if row_pk:
                approval_groups[ts].append({"entry": entry, "row_pk": row_pk})
        elif mod_type == "rejection":
            ts = entry.get("timestamp", "")[:19]
            row_pk = entry.get("details", {}).get("row_pk", {})
            if row_pk:
                rejection_groups[ts].append({"entry": entry, "row_pk": row_pk})
        else:
            # Keep field modifications as-is
            result.append(entry)
    
    # Create grouped approval entries
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
    
    # Create grouped rejection entries
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
    
    # Sort by timestamp
    result.sort(key=lambda x: x.get("timestamp", ""))
    return result


def _load_modifications_from_datum():
    """Load modifications from the database via Datum proxy."""
    try:
        mods_table = app_config.database.mods_table
        mods_table_sql = _format_table_name(mods_table)
        
        query = f'''
            SELECT id, row_pk, column_name, old_value, new_value, 
                   mod_type, created_by, created_at, undone
            FROM {mods_table_sql}
            ORDER BY created_at ASC
        '''
        
        rows = _execute_sql_via_datum(query)
        
        # Convert to log format
        log = []
        for row in rows:
            row_pk = row.get('row_pk', {})
            if isinstance(row_pk, str):
                row_pk = json.loads(row_pk)
            elif row_pk is None:
                row_pk = {}
            
            timestamp = row.get('created_at')
            if timestamp and not isinstance(timestamp, str):
                timestamp = str(timestamp)
            
            log.append({
                "db_id": row.get('id'),
                "timestamp": timestamp,
                "type": row.get('mod_type'),
                "undone": row.get('undone', False),
                "details": {
                    "row_pk": row_pk,
                    "column": row.get('column_name'),
                    "old_value": row.get('old_value'),
                    "new_value": row.get('new_value'),
                    "created_by": row.get('created_by')
                }
            })
        
        # Aggregate approval/rejection entries for UI display
        return _aggregate_approval_rejection_entries(log)
    except Exception as e:
        print(f"✗ Error loading modifications from Datum: {e}")
        return []


def _load_modifications_from_db():
    """Load modifications from the database."""
    try:
        from sqlalchemy import create_engine, text
        
        conn_string = app_config.database.connection_string
        mods_table = app_config.database.mods_table
        mods_table_sql = _format_table_name(mods_table)
        
        engine = create_engine(conn_string)
        
        with engine.connect() as conn:
            result = conn.execute(text(f'''
                SELECT id, row_pk, column_name, old_value, new_value, 
                       mod_type, created_by, created_at, undone
                FROM {mods_table_sql}
                ORDER BY created_at ASC
            '''))
            rows = result.fetchall()
        
        # Convert to log format
        log = []
        for row in rows:
            # row_pk is JSONB - may already be dict or may need parsing
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
        
        # Aggregate approval/rejection entries for UI display
        return _aggregate_approval_rejection_entries(log)
    except Exception as e:
        print(f"✗ Error loading modifications from DB: {e}")
        return []


def save_modification_to_db(row_pk: dict, column: str, old_value, new_value, mod_type: str = "field_modification"):
    """Save a single modification to the database."""
    if not app_config.database.enabled:
        return None
    
    if app_config.database.mode == "datum":
        return _save_modification_to_datum(row_pk, column, old_value, new_value, mod_type)
    
    try:
        from sqlalchemy import create_engine, text
        
        conn_string = app_config.database.connection_string
        mods_table = app_config.database.mods_table
        mods_table_sql = _format_table_name(mods_table)
        
        engine = create_engine(conn_string)
        
        with engine.connect() as conn:
            result = conn.execute(
                text(f'''
                    INSERT INTO {mods_table_sql} 
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


def _save_modification_to_datum(row_pk: dict, column: str, old_value, new_value, mod_type: str = "field_modification"):
    """Save a single modification via Datum proxy."""
    try:
        mods_table = app_config.database.mods_table
        mods_table_sql = _format_table_name(mods_table)
        
        # Escape values for SQL
        row_pk_json = json.dumps(row_pk).replace("'", "''")
        old_val_sql = f"'{str(old_value).replace(chr(39), chr(39)+chr(39))}'" if old_value is not None else "NULL"
        new_val_sql = f"'{str(new_value).replace(chr(39), chr(39)+chr(39))}'" if new_value is not None else "NULL"
        column_sql = column.replace("'", "''")
        mod_type_sql = mod_type.replace("'", "''")
        
        query = f"""
            INSERT INTO {mods_table_sql} 
                (row_pk, column_name, old_value, new_value, mod_type)
            VALUES 
                ('{row_pk_json}'::jsonb, '{column_sql}', {old_val_sql}, {new_val_sql}, '{mod_type_sql}')
            RETURNING id
        """
        
        result = _execute_sql_via_datum(query)
        if result and len(result) > 0:
            return result[0].get('id')
        return None
    except Exception as e:
        print(f"✗ Error saving modification via Datum: {e}")
        return None


def mark_modification_undone_in_db(mod_id: int):
    """Mark a modification as undone in the database."""
    if not app_config.database.enabled:
        return False
    
    if app_config.database.mode == "datum":
        return _mark_modification_undone_in_datum(mod_id)
    
    try:
        from sqlalchemy import create_engine, text
        
        conn_string = app_config.database.connection_string
        mods_table = app_config.database.mods_table
        mods_table_sql = _format_table_name(mods_table)
        
        engine = create_engine(conn_string)
        
        with engine.connect() as conn:
            conn.execute(
                text(f'UPDATE {mods_table_sql} SET undone = TRUE WHERE id = :mod_id'),
                {"mod_id": mod_id}
            )
            conn.commit()
            return True
    except Exception as e:
        print(f"✗ Error marking modification undone: {e}")
        return False


def _mark_modification_undone_in_datum(mod_id: int):
    """Mark a modification as undone via Datum proxy."""
    try:
        mods_table = app_config.database.mods_table
        mods_table_sql = _format_table_name(mods_table)
        query = f'UPDATE {mods_table_sql} SET undone = TRUE WHERE id = {mod_id}'
        _execute_sql_via_datum(query)
        return True
    except Exception as e:
        print(f"✗ Error marking modification undone via Datum: {e}")
        return False


def update_data_in_db(row_pk: dict, column: str, new_value):
    """Update a cell value directly in the database."""
    if not app_config.database.enabled:
        return False
    
    if app_config.database.mode == "datum":
        return _update_data_via_datum(row_pk, column, new_value)
    
    try:
        from sqlalchemy import create_engine, text
        
        conn_string = app_config.database.connection_string
        data_table = app_config.database.data_table
        data_table_sql = _format_table_name(data_table)
        
        engine = create_engine(conn_string)
        
        # Build WHERE clause from primary key
        pk_cols = app_config.table.primary_key
        where_parts = [f'"{pk}" = :pk_{pk}' for pk in pk_cols]
        where_clause = " AND ".join(where_parts)
        
        params = {f"pk_{pk}": row_pk.get(pk) for pk in pk_cols}
        params["new_value"] = new_value
        
        with engine.connect() as conn:
            conn.execute(
                text(f'UPDATE {data_table_sql} SET "{column}" = :new_value WHERE {where_clause}'),
                params
            )
            conn.commit()
            return True
    except Exception as e:
        print(f"✗ Error updating data in DB: {e}")
        return False


def _update_data_via_datum(row_pk: dict, column: str, new_value):
    """Update a cell value via Datum proxy."""
    try:
        data_table = app_config.database.data_table
        data_table_sql = _format_table_name(data_table)
        pk_cols = app_config.table.primary_key
        
        # Build WHERE clause from primary key
        where_parts = []
        for pk in pk_cols:
            pk_val = row_pk.get(pk)
            if pk_val is not None:
                escaped_val = str(pk_val).replace("'", "''")
                where_parts.append(f'"{pk}" = \'{escaped_val}\'')
        
        where_clause = " AND ".join(where_parts)
        
        # Escape the new value
        if new_value is None:
            new_val_sql = "NULL"
        else:
            escaped_new = str(new_value).replace("'", "''")
            new_val_sql = f"'{escaped_new}'"
        
        sql = f'UPDATE {data_table_sql} SET "{column}" = {new_val_sql} WHERE {where_clause}'
        
        _execute_sql_via_datum(sql)
        return True
    except Exception as e:
        print(f"✗ Error updating data via Datum: {e}")
        return False


def get_modification_status(row_index):
    """
    Public function to retrieve modification status for a specific row.
    Can be called from external scripts or Python interpreter.
    
    Args:
        row_index (int): Row index (0-based)
    
    Returns:
        dict: Status info {row_index, status, modifications_count, last_modified, modifications}
    """
    if not modifications_log_path.exists():
        return {
            "row_index": row_index, 
            "status": "unprocessed", 
            "modifications_count": 0, 
            "last_modified": None, 
            "modifications": []
        }
    
    with open(modifications_log_path, "r") as f:
        log = json.load(f)
    
    row_mods = [
        m for m in log 
        if m.get("details", {}).get("row_index") == row_index 
        and m.get("type") == "field_modification"
    ]
    
    # Determine status
    approval_entries = [m for m in log if m.get("type") in ["approval", "rejection"]]
    status = "unprocessed"
    if approval_entries:
        last_approval = approval_entries[-1]
        if last_approval.get("type") == "approval":
            status = "approved"
        elif last_approval.get("type") == "rejection":
            status = "rejected"
    elif row_mods:
        status = "edited"
    
    return {
        "row_index": row_index,
        "status": status,
        "modifications_count": len(row_mods),
        "last_modified": row_mods[-1].get("timestamp") if row_mods else None,
        "modifications": row_mods,
    }


def get_all_modification_statuses():
    """
    Public function to retrieve modification status for all rows.
    Can be called from external scripts or Python interpreter.
    
    Returns:
        dict: {rows: [list of status dicts], summary: {counts}}
    """
    if not modifications_log_path.exists():
        return {
            "rows": [], 
            "summary": {"total": 0, "unprocessed": 0, "edited": 0, "approved": 0, "rejected": 0}
        }
    
    with open(modifications_log_path, "r") as f:
        log = json.load(f)
    
    # Determine overall approval status
    approval_entries = [m for m in log if m.get("type") in ["approval", "rejection"]]
    overall_status = None
    if approval_entries:
        last_approval = approval_entries[-1]
        overall_status = "approved" if last_approval.get("type") == "approval" else "rejected"
    
    # Load data to get row count
    if not csv_path.exists():
        return {
            "rows": [], 
            "summary": {"total": 0, "unprocessed": 0, "edited": 0, "approved": 0, "rejected": 0}
        }
    
    df = pd.read_csv(csv_path)
    statuses = []
    counts = {"total": len(df), "unprocessed": 0, "edited": 0, "approved": 0, "rejected": 0}
    
    for idx in range(len(df)):
        row_mods = [
            m for m in log 
            if m.get("details", {}).get("row_index") == idx 
            and m.get("type") == "field_modification"
        ]
        
        status = overall_status if overall_status else ("edited" if row_mods else "unprocessed")
        if not overall_status and row_mods:
            status = "edited"
        elif not overall_status:
            status = "unprocessed"
        
        counts[status] += 1
        
        statuses.append({
            "row_index": idx,
            "status": status,
            "modifications_count": len(row_mods),
            "last_modified": row_mods[-1].get("timestamp") if row_mods else None,
        })
    
    return {"rows": statuses, "summary": counts}


# ============================================================================
# UI State Persistence (sort, filters, page, etc.) - Database storage
# ============================================================================

# Default user/session for single-user mode
_DEFAULT_USER_ID = "default_user"
_DEFAULT_SESSION_ID = "default_session"


def save_ui_state(
    sort_column: str = None,
    sort_ascending: bool = True,
    current_page: int = 1,
    rows_per_page: int = 25,
    filters: dict = None,
    column_preset: str = None,
    **kwargs  # Ignore extra args for compatibility
) -> bool:
    """Save UI state to database."""
    try:
        from src.db.db_operations import get_database_operations
        from src.db import DatabaseConfig
        
        db_config = DatabaseConfig(
            connection_string=app_config.database.connection_string,
            data_table=app_config.database.data_table,
            mods_table=app_config.database.mods_table,
            state_table=app_config.database.state_table
        )
        db_ops = get_database_operations(db_config)
        
        db_ops.save_ui_state(
            user_id=_DEFAULT_USER_ID,
            session_id=_DEFAULT_SESSION_ID,
            sort_column=sort_column,
            sort_ascending=sort_ascending,
            current_page=current_page,
            rows_per_page=rows_per_page,
            filters=list(filters.items()) if filters else None,
            column_preset=column_preset
        )
        return True
    except Exception as e:
        print(f"Warning: Could not save UI state: {e}")
        return False


def load_ui_state(**kwargs) -> dict:
    """Load UI state from database."""
    default_state = {
        "sort_column": app_config.table.default_sort_column,
        "sort_ascending": app_config.table.default_sort_ascending,
        "current_page": 1,
        "rows_per_page": app_config.table.default_rows_per_page,
        "filters": {},
        "column_preset": None
    }
    try:
        from src.db.db_operations import get_database_operations
        from src.db import DatabaseConfig
        
        db_config = DatabaseConfig(
            connection_string=app_config.database.connection_string,
            data_table=app_config.database.data_table,
            mods_table=app_config.database.mods_table,
            state_table=app_config.database.state_table
        )
        db_ops = get_database_operations(db_config)
        
        saved_state = db_ops.load_ui_state(
            user_id=_DEFAULT_USER_ID,
            session_id=_DEFAULT_SESSION_ID
        )
        if saved_state:
            # Convert filters from list back to dict if present
            if saved_state.get("filters"):
                saved_state["filters"] = dict(saved_state["filters"])
            else:
                saved_state["filters"] = {}
            return {**default_state, **saved_state}
    except Exception as e:
        print(f"Warning: Could not load UI state: {e}")
    return default_state
