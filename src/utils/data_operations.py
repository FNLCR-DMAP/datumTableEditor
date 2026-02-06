"""
Data operations utilities for the Epitopes Data Editor.
Handle undo, cell edits, save, export operations.
"""

import json
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional


def perform_undo(
    df: pd.DataFrame,
    log: List[Dict],
    log_idx: int
) -> Tuple[Optional[pd.DataFrame], Optional[List[Dict]], Optional[str], Optional[str]]:
    """
    Perform an undo operation on a field modification.
    
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
    row_idx = details.get("row_index")
    col = details.get("column")
    old_value = details.get("old_value")
    new_value = details.get("new_value")
    
    if row_idx is None or not col:
        return None, None, None, "Invalid modification data"
    
    if col not in df.columns:
        return None, None, None, f"Column '{col}' not found"
    
    # Create copies to avoid mutating originals
    updated_df = df.copy()
    updated_df.at[row_idx, col] = old_value
    
    # Mark the original modification as undone
    updated_log = log.copy()
    updated_log[log_idx] = updated_log[log_idx].copy()
    updated_log[log_idx]["undone"] = True
    
    # Add undo entry to the log
    updated_log.append({
        "timestamp": datetime.now().isoformat(),
        "type": "undo",
        "details": {
            "row_index": row_idx,
            "column": col,
            "reverted_from": new_value,
            "reverted_to": old_value,
            "original_mod_index": log_idx
        }
    })
    
    message = f"Undone: Row {row_idx + 1}, {col}"
    return updated_df, updated_log, message, None


def perform_cell_edit(
    df: pd.DataFrame,
    log: List[Dict],
    row: int,
    col: str,
    old_value: str,
    new_value: str
) -> Tuple[pd.DataFrame, List[Dict]]:
    """
    Perform a cell edit operation.
    
    Returns:
        (updated_df, updated_log)
    """
    if col not in df.columns:
        return df, log
    
    updated_df = df.copy()
    updated_df.at[row, col] = new_value
    
    updated_log = log.copy()
    updated_log.append({
        "timestamp": datetime.now().isoformat(),
        "type": "field_modification",
        "details": {
            "row_index": row,
            "column": col,
            "old_value": old_value,
            "new_value": new_value,
        }
    })
    
    return updated_df, updated_log


def save_modifications_to_file(
    df: pd.DataFrame,
    log: List[Dict],
    log_path: Path,
    data_state_path: Path
) -> str:
    """
    Save modifications log and data state to files.
    
    Returns:
        Success message
    """
    save_log_to_file(log, log_path)
    df.to_json(data_state_path, orient="records", indent=2, default_handler=str)
    
    return f"Saved {len(log)} modifications!"


def save_log_to_file(log: List[Dict], log_path: Path) -> None:
    """Save modifications log to file."""
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
    selected_indices: List[int],
    total_rows: int,
    log_count: int
) -> Dict[str, Any]:
    """Create log entry for approval action."""
    return {
        "timestamp": datetime.now().isoformat(),
        "type": "approval",
        "details": {
            "action": "approved",
            "approved_row_count": len(selected_indices),
            "approved_rows": selected_indices,
            "total_rows": total_rows,
            "modification_count": log_count
        }
    }


def create_rejection_entry(
    selected_indices: List[int],
    total_rows: int,
    log_count: int
) -> Dict[str, Any]:
    """Create log entry for rejection action."""
    return {
        "timestamp": datetime.now().isoformat(),
        "type": "rejection",
        "details": {
            "action": "rejected",
            "rejected_row_count": len(selected_indices),
            "rejected_rows": selected_indices,
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
