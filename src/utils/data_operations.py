"""
Data operations utilities for the Epitopes Data Editor.
Handle undo, cell edits, save, export operations.
"""

import json
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional

# Import config for database operations
try:
    from src.config.config import (
        app_config,
        save_modification_to_db,
        mark_modification_undone_in_db,
        update_data_in_db
    )
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False


def _get_row_pk(df: pd.DataFrame, row_idx: int) -> dict:
    """Extract primary key values for a row using positional index (iloc)."""
    try:
        from src.config.config import app_config
        pk_cols = app_config.table.primary_key
        row = df.iloc[row_idx]
        return {pk: row[pk] for pk in pk_cols if pk in df.columns}
    except:
        return {"row_index": row_idx}


def _pk_to_string(row_pk: dict) -> str:
    """Convert primary key dict to display string."""
    if not row_pk:
        return "?"
    # Primary key is PatientID_Mutsequence
    if "PatientID_Mutsequence" in row_pk:
        return str(row_pk["PatientID_Mutsequence"])
    # Fallback: return first non-row_index value
    for k, v in row_pk.items():
        if k != "row_index":
            return str(v)
    return str(row_pk.get("row_index", "?"))


def perform_undo(
    df: pd.DataFrame,
    log: List[Dict],
    log_idx: int,
    config_instance = None
) -> Tuple[Optional[pd.DataFrame], Optional[List[Dict]], Optional[str], Optional[str]]:
    """
    Perform an undo operation on a field modification.
    
    Args:
        df: DataFrame to update
        log: Modifications log
        log_idx: Index of the modification to undo
        config_instance: Optional ConfigInstance for database operations
    
    Returns:
        (updated_df, updated_log, success_message, error_message)
        If error, df and log are None, error_message is set.
        If success, error_message is None.
    """
    if log_idx < 0 or log_idx >= len(log):
        return None, None, None, "Invalid log index"
    
    mod = log[log_idx]
    if mod.get("type") != "field_modification":
        return None, None, None, "Can only undo field modifications."
    
    details = mod.get("details", {})
    col = details.get("column")
    old_value = details.get("old_value")
    new_value = details.get("new_value")
    row_pk = details.get("row_pk", {})
    db_id = mod.get("db_id")
    
    # Must have column name
    if not col:
        return None, None, None, "Invalid modification data: missing column"
    
    # Must have row_pk to find the row
    if not row_pk:
        return None, None, None, "Invalid modification data: missing row primary key"
    
    if col not in df.columns:
        return None, None, None, f"Column '{col}' not found"
    
    # Create copies to avoid mutating originals
    updated_df = df.copy()
    
    # Get config for PK columns
    if config_instance:
        pk_cols = config_instance.app_config.table.primary_key
    else:
        from src.config.config import app_config
        pk_cols = app_config.table.primary_key
    
    if not pk_cols:
        return None, None, None, "No primary key configured"
    
    # Find row using primary key
    mask = pd.Series([True] * len(updated_df))
    for pk_col in pk_cols:
        if pk_col in row_pk and pk_col in updated_df.columns:
            mask &= (updated_df[pk_col].astype(str) == str(row_pk[pk_col]))
    
    if not mask.any():
        return None, None, None, f"Could not find row with PK: {row_pk}"
    
    col_idx = updated_df.columns.get_loc(col)
    updated_df.iloc[mask.values, col_idx] = old_value
    
    # Update database if enabled (use config_instance if provided)
    if config_instance:
        # Revert the data in database
        config_instance.update_data_in_db(row_pk, col, old_value)
        # Mark modification as undone
        if db_id:
            config_instance.mark_modification_undone_in_db(db_id)
        # Save undo record
        config_instance.save_modification_to_db(row_pk, col, new_value, old_value, "undo")
    elif DB_AVAILABLE and app_config.database.enabled:
        # Revert the data in database
        update_data_in_db(row_pk, col, old_value)
        # Mark modification as undone
        if db_id:
            mark_modification_undone_in_db(db_id)
        # Save undo record
        save_modification_to_db(row_pk, col, new_value, old_value, "undo")
    
    # Mark the original modification as undone
    updated_log = log.copy()
    updated_log[log_idx] = updated_log[log_idx].copy()
    updated_log[log_idx]["undone"] = True
    
    # Add undo entry to the log
    updated_log.append({
        "timestamp": datetime.now().isoformat(),
        "type": "undo",
        "details": {
            "row_pk": row_pk,
            "primary_key": _pk_to_string(row_pk),
            "column": col,
            "reverted_from": new_value,
            "reverted_to": old_value,
            "original_mod_index": log_idx
        }
    })
    
    message = f"Undone: [{_pk_to_string(row_pk)}], {col}"
    return updated_df, updated_log, message, None


def perform_cell_edit(
    df: pd.DataFrame,
    log: List[Dict],
    row: int,
    col: str,
    old_value: str,
    new_value: str,
    config_instance = None
) -> Tuple[pd.DataFrame, List[Dict]]:
    """
    Perform a cell edit operation.
    
    Args:
        df: DataFrame to update
        log: Modifications log
        row: Row position (iloc index)
        col: Column name
        old_value: Previous value
        new_value: New value
        config_instance: Optional ConfigInstance for database operations
    
    Returns:
        (updated_df, updated_log)
    """
    if col not in df.columns:
        return df, log
    
    updated_df = df.copy()
    # Use iloc for positional indexing (row is a position, not a label)
    updated_df.iloc[row, updated_df.columns.get_loc(col)] = new_value
    
    # Get row primary key for database operations
    row_pk = _get_row_pk(df, row)
    
    # Save to database if enabled (use config_instance if provided)
    db_id = None
    if config_instance:
        # Update the data table
        config_instance.update_data_in_db(row_pk, col, new_value)
        # Save modification record
        db_id = config_instance.save_modification_to_db(row_pk, col, old_value, new_value, "field_modification")
    elif DB_AVAILABLE and app_config.database.enabled:
        # Update the data table
        update_data_in_db(row_pk, col, new_value)
        # Save modification record
        db_id = save_modification_to_db(row_pk, col, old_value, new_value, "field_modification")
    
    updated_log = log.copy()
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "type": "field_modification",
        "details": {
            "row_index": row,
            "row_pk": row_pk,
            "primary_key": _pk_to_string(row_pk),
            "column": col,
            "old_value": old_value,
            "new_value": new_value,
        }
    }
    if db_id:
        log_entry["db_id"] = db_id
    
    updated_log.append(log_entry)
    
    return updated_df, updated_log


def save_modifications_to_file(
    df: pd.DataFrame,
    log: List[Dict],
    log_path: Path,
    data_state_path: Path
) -> str:
    """
    Save modifications log and data state to files (or database if enabled).
    
    Returns:
        Success message
    """
    # In database mode, data is already saved on each edit
    if DB_AVAILABLE and app_config.database.enabled:
        return f"Changes saved to database ({len(log)} modifications tracked)"
    
    # File-based persistence
    save_log_to_file(log, log_path)
    df.to_json(data_state_path, orient="records", indent=2, default_handler=str)
    
    return f"Saved {len(log)} modifications!"


def save_log_to_file(log: List[Dict], log_path: Path) -> None:
    """Save modifications log to file (skipped if database mode)."""
    # In database mode, skip file saves (handled by server.py)
    if DB_AVAILABLE and app_config.database.enabled:
        return
    
    with open(log_path, "w") as f:
        json.dump(log, f, indent=2)


def export_csv(df: pd.DataFrame, export_path: Path) -> str:
    """
    Export dataframe to CSV.
    
    Returns:
        Success message
    """
    df.to_csv(export_path, index=False)
    return f"Exported to {export_path.name}"


def export_status_report(
    summary_data: List[Dict],
    status_counts: Dict[str, int],
    export_path: Path
) -> str:
    """
    Export status report to CSV.
    
    Returns:
        Success message with summary
    """
    status_df = pd.DataFrame(summary_data)
    status_df.to_csv(export_path, index=False)
    
    summary_text = (
        f"Total: {len(status_df)} rows | "
        f"Unprocessed: {status_counts['unprocessed']} | "
        f"Edited: {status_counts['edited']} | "
        f"Approved: {status_counts['approved']} | "
        f"Rejected: {status_counts['rejected']}"
    )
    return f"Status Report Exported! {summary_text}"


def create_approval_entry(
    selected_pks: List[Dict[str, Any]],
    total_rows: int,
    log_count: int
) -> Dict[str, Any]:
    """Create log entry for approval action with PKs."""
    return {
        "timestamp": datetime.now().isoformat(),
        "type": "approval",
        "details": {
            "action": "approved",
            "approved_row_count": len(selected_pks),
            "approved_rows": selected_pks,  # List of PK dicts
            "total_rows": total_rows,
            "modification_count": log_count
        }
    }


def create_rejection_entry(
    selected_pks: List[Dict[str, Any]],
    total_rows: int,
    log_count: int
) -> Dict[str, Any]:
    """Create log entry for rejection action with PKs."""
    return {
        "timestamp": datetime.now().isoformat(),
        "type": "rejection",
        "details": {
            "action": "rejected",
            "rejected_row_count": len(selected_pks),
            "rejected_rows": selected_pks,  # List of PK dicts
            "total_rows": total_rows,
            "modification_count": log_count
        }
    }


def get_selected_row_indices(input_obj: Any, df_length: int) -> List[int]:
    """Get list of selected row indices from checkboxes."""
    selected = []
    for idx in range(df_length):
        try:
            if input_obj[f"select_{idx}"]():
                selected.append(idx)
        except:
            pass
    return selected


def get_copy_column_values(
    df: pd.DataFrame,
    column_name: str,
    paginated_indices: List[int],
    selected_indices: List[int]
) -> Tuple[Optional[List[str]], Optional[str]]:
    """
    Get column values for selected rows to copy.
    
    Returns:
        (values_list, error_message)
        If error, values_list is None.
    """
    if column_name not in df.columns:
        return None, f"Column '{column_name}' not found."
    
    actual_indices = [paginated_indices[i] for i in selected_indices if i < len(paginated_indices)]
    if not actual_indices:
        return None, "No valid rows selected."
    
    values = df.loc[actual_indices, column_name].astype(str).tolist()
    return values, None


def get_paginated_indices(
    filtered_indices: List[int],
    rows_per_page_val: str,
    current_page: int
) -> List[int]:
    """Calculate paginated indices from filtered indices."""
    if rows_per_page_val == "all":
        return filtered_indices
    
    rows_per_page = int(rows_per_page_val)
    start = (current_page - 1) * rows_per_page
    end = start + rows_per_page
    return filtered_indices[start:end]


def calculate_pagination(
    total_rows: int,
    rows_per_page_val: str,
    current_page: int
) -> Tuple[int, int, int, int]:
    """
    Calculate pagination values.
    
    Returns:
        (page, total_pages, start_row, end_row)
    """
    if rows_per_page_val == "all":
        return 1, 1, 1, total_rows
    
    rows_per_page = int(rows_per_page_val)
    total_pages = max(1, (total_rows + rows_per_page - 1) // rows_per_page)
    page = min(current_page, total_pages)
    start_row = (page - 1) * rows_per_page + 1
    end_row = min(page * rows_per_page, total_rows)
    
    return page, total_pages, start_row, end_row
