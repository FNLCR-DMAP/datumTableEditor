"""
Configuration and shared state for Epitopes Data Editor PyShiny App

This module provides backward-compatible access to configuration.
New code should use src/app_config_schema.py and src/data_loader.py directly.
"""

import json
import pandas as pd
from pathlib import Path

# Import new configuration system from src
from src.config import AppConfig, load_config

# Load application configuration
app_config = load_config()

# Setup paths (backward compatible)
app_dir = Path(__file__).parent
data_dir = app_dir / "data"
data_dir.mkdir(exist_ok=True)

# Resolve data source from config
def _get_data_path() -> Path:
    """Get data file path from configuration."""
    if app_config.data_source.file_path:
        p = Path(app_config.data_source.file_path)
        if not p.is_absolute():
            p = app_dir / p
        return p
    return data_dir / "dummy_data_50rows.csv"

csv_path = _get_data_path()

# Load data based on source type
def _load_initial_data() -> pd.DataFrame:
    """Load initial data from configured source."""
    # Check if database mode is enabled
    if app_config.database.enabled:
        return _load_from_database()
    
    if app_config.data_source.source_type == "csv":
        if csv_path.exists():
            return pd.read_csv(csv_path)
    elif app_config.data_source.source_type == "json":
        if csv_path.exists():
            return pd.read_json(csv_path, orient="records")
    # Fallback to CSV
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
                 FROM "{mods_table}" m 
                 WHERE {pk_conditions}
                   AND m.undone = FALSE
                 ORDER BY m.created_at DESC 
                 LIMIT 1),
                'unprocessed'
            ) AS _mod_status
        FROM "{data_table}" d
        ORDER BY d."{pk_columns[0]}"
        """
        
        df = pd.read_sql(query, engine)
        
        # Now apply any field modifications to update the actual cell values
        # Get all non-undone field modifications
        mods_query = f"""
        SELECT row_pk, column_name, new_value 
        FROM "{mods_table}" 
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
        
        print(f"✓ Loaded {len(df)} rows from database: {data_table}")
        return df
    except ImportError:
        print("✗ SQLAlchemy not installed. Falling back to CSV.")
        return pd.read_csv(csv_path)
    except Exception as e:
        print(f"✗ Database error: {e}. Falling back to CSV.")
        return pd.read_csv(csv_path)

df_original = _load_initial_data()

# Data state path (only used when database is disabled)
def _get_data_state_path() -> Path:
    """Get data state path from configuration (file-based mode only)."""
    if app_config.persistence.data_state_path:
        p = Path(app_config.persistence.data_state_path)
        if not p.is_absolute():
            p = app_dir / p
        return p
    return data_dir / "data_state.json"

data_state_path = _get_data_state_path()

# Only load from file if database mode is disabled
if not app_config.database.enabled and data_state_path.exists():
    try:
        df_saved = pd.read_json(data_state_path, orient="records")
        df_original = df_saved
    except:
        pass  # If loading fails, use original data

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
            p = app_dir / p
        return p
    return data_dir / "modifications_log.json"

modifications_log_path = _get_modifications_log_path()


def load_modifications_log():
    """Load modifications log from database or file."""
    # Use database if enabled
    if app_config.database.enabled:
        return _load_modifications_from_db()
    
    # Fallback to file
    if modifications_log_path.exists():
        with open(modifications_log_path, "r") as f:
            return json.load(f)
    return []


def _load_modifications_from_db():
    """Load modifications from the database."""
    try:
        from sqlalchemy import create_engine, text
        
        conn_string = app_config.database.connection_string
        mods_table = app_config.database.mods_table
        
        engine = create_engine(conn_string)
        
        with engine.connect() as conn:
            result = conn.execute(text(f'''
                SELECT id, row_pk, column_name, old_value, new_value, 
                       mod_type, created_by, created_at, undone
                FROM "{mods_table}"
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
        
        return log
    except Exception as e:
        print(f"✗ Error loading modifications from DB: {e}")
        return []


def save_modification_to_db(row_pk: dict, column: str, old_value, new_value, mod_type: str = "field_modification"):
    """Save a single modification to the database."""
    if not app_config.database.enabled:
        return None
    
    try:
        from sqlalchemy import create_engine, text
        
        conn_string = app_config.database.connection_string
        mods_table = app_config.database.mods_table
        
        engine = create_engine(conn_string)
        
        with engine.connect() as conn:
            result = conn.execute(
                text(f'''
                    INSERT INTO "{mods_table}" 
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


def mark_modification_undone_in_db(mod_id: int):
    """Mark a modification as undone in the database."""
    if not app_config.database.enabled:
        return False
    
    try:
        from sqlalchemy import create_engine, text
        
        conn_string = app_config.database.connection_string
        mods_table = app_config.database.mods_table
        
        engine = create_engine(conn_string)
        
        with engine.connect() as conn:
            conn.execute(
                text(f'UPDATE "{mods_table}" SET undone = TRUE WHERE id = :mod_id'),
                {"mod_id": mod_id}
            )
            conn.commit()
            return True
    except Exception as e:
        print(f"✗ Error marking modification undone: {e}")
        return False


def update_data_in_db(row_pk: dict, column: str, new_value):
    """Update a cell value directly in the database."""
    if not app_config.database.enabled:
        return False
    
    try:
        from sqlalchemy import create_engine, text
        
        conn_string = app_config.database.connection_string
        data_table = app_config.database.data_table
        
        engine = create_engine(conn_string)
        
        # Build WHERE clause from primary key
        pk_cols = app_config.table.primary_key
        where_parts = [f'"{pk}" = :pk_{pk}' for pk in pk_cols]
        where_clause = " AND ".join(where_parts)
        
        params = {f"pk_{pk}": row_pk.get(pk) for pk in pk_cols}
        params["new_value"] = new_value
        
        with engine.connect() as conn:
            conn.execute(
                text(f'UPDATE "{data_table}" SET "{column}" = :new_value WHERE {where_clause}'),
                params
            )
            conn.commit()
            return True
    except Exception as e:
        print(f"✗ Error updating data in DB: {e}")
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
# UI State Persistence (sort, filters, page, etc.) - In-memory storage
# ============================================================================

_ui_state = {}


def save_ui_state(
    sort_column: str = None,
    sort_ascending: bool = True,
    current_page: int = 1,
    rows_per_page: int = 25,
    filters: dict = None,
    column_preset: str = None,
    **kwargs  # Ignore extra args for compatibility
) -> bool:
    """Save UI state to memory."""
    global _ui_state
    _ui_state = {
        "sort_column": sort_column,
        "sort_ascending": sort_ascending,
        "current_page": current_page,
        "rows_per_page": rows_per_page,
        "filters": filters or {},
        "column_preset": column_preset
    }
    return True


def load_ui_state(**kwargs) -> dict:
    """Load UI state from memory."""
    default_state = {
        "sort_column": app_config.table.default_sort_column,
        "sort_ascending": app_config.table.default_sort_ascending,
        "current_page": 1,
        "rows_per_page": app_config.table.default_rows_per_page,
        "filters": {},
        "column_preset": None
    }
    return {**default_state, **_ui_state}
