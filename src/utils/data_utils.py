"""
Data processing utilities for row status, modifications, and data summaries.
"""

import pandas as pd
from typing import Optional, Tuple


def get_latest_approval_status(log: list) -> Tuple[Optional[str], Optional[str]]:
    """
    Get the latest global approval/rejection status from the modifications log.
    Only returns status for global approval (not row-based approval).
    
    Args:
        log: List of modification log entries
        
    Returns:
        Tuple of (status, timestamp) where status is "approved", "rejected", or None
    """
    approval_entries = [m for m in log if m.get("type") in ["approval", "rejection"]]
    
    if approval_entries:
        latest = approval_entries[-1]
        details = latest.get("details", {})
        # Only show global banner if it's NOT a row-based approval
        # Row-based approvals have "approved_rows" or "rejected_rows" in details
        if "approved_rows" in details or "rejected_rows" in details:
            # This is a row-based approval, don't show global banner
            return None, None
        status = "approved" if latest.get("type") == "approval" else "rejected"
        timestamp = latest.get("timestamp", None)
        return status, timestamp[:19] if timestamp else None
    
    return None, None


def get_row_status(row_idx: int, log: list, row_pk: dict = None) -> str:
    """
    Determine row status based on modifications log.
    
    Args:
        row_idx: Index of the row (positional)
        log: List of modification log entries
        row_pk: Optional primary key dict for more accurate matching
        
    Returns:
        Status string: "approved", "rejected", "edited", or "unprocessed"
    """
    # Helper to check if a log entry matches this row by PK
    def matches_row_pk(entry_details):
        if not row_pk:
            return False
        entry_pk = entry_details.get("row_pk", {})
        if not entry_pk:
            return False
        # Match if all PK values match
        return all(str(row_pk.get(k)) == str(v) for k, v in entry_pk.items())
    
    # Helper to check if a log entry matches this row (for field modifications)
    def matches_row(entry_details):
        # First try to match by primary key if both are available
        if row_pk and "row_pk" in entry_details:
            return matches_row_pk(entry_details)
        # Fallback to row_index matching
        return entry_details.get("row_index") == row_idx
    
    # Check for active (non-undone) modifications on this row
    has_active_modifications = any(
        matches_row(m.get("details", {}))
        and not m.get("undone", False)
        for m in log if m.get("type") == "field_modification"
    )
    
    # Helper to check if row_pk matches any PK in a list of PK dicts
    def pk_in_list(pk_list):
        if not row_pk or not pk_list:
            return False
        for entry_pk in pk_list:
            if isinstance(entry_pk, dict):
                # Match if all PK values match
                if all(str(row_pk.get(k)) == str(v) for k, v in entry_pk.items()):
                    return True
        return False
    
    # Check for approval/rejection entries - two formats:
    # 1. File/in-memory format: type=approval/rejection with details.approved_rows/rejected_rows as list
    # 2. DB format: type=approval/rejection with details.row_pk matching this row directly
    
    row_approval_entries = []
    for m in log:
        if m.get("type") not in ["approval", "rejection"]:
            continue
        if m.get("undone", False):
            continue
        details = m.get("details", {})
        
        # Check format 1: list-based (in-memory log from create_approval_entry)
        if pk_in_list(details.get("approved_rows", [])) or pk_in_list(details.get("rejected_rows", [])):
            row_approval_entries.append(m)
        # Check format 2: direct row_pk match (DB loaded entries)
        elif matches_row_pk(details):
            row_approval_entries.append(m)
    
    if row_approval_entries:
        latest_approval = row_approval_entries[-1]
        if latest_approval.get("type") == "approval":
            return "approved"
        elif latest_approval.get("type") == "rejection":
            return "rejected"
    
    if has_active_modifications:
        return "edited"
    else:
        return "unprocessed"


def get_row_modifications(row_idx: int, log: list) -> list:
    """
    Get all modifications for a specific row.
    
    Args:
        row_idx: Index of the row
        log: List of modification log entries
        
    Returns:
        List of modification entries for the specified row
    """
    return [
        m for m in log 
        if m.get("details", {}).get("row_index") == row_idx 
        and m.get("type") == "field_modification"
    ]


def get_status_counts(df: pd.DataFrame, log: list, pk_cols: list = None) -> dict:
    """
    Get counts of each status.
    
    Args:
        df: DataFrame containing the data
        log: List of modification log entries
        pk_cols: Optional list of primary key column names
        
    Returns:
        Dictionary with counts for each status
    """
    counts = {"unprocessed": 0, "edited": 0, "approved": 0, "rejected": 0}
    for idx in range(len(df)):
        row_pk = None
        if pk_cols:
            try:
                row = df.iloc[idx]
                row_pk = {pk: row[pk] for pk in pk_cols if pk in df.columns}
            except:
                pass
        status = get_row_status(idx, log, row_pk)
        counts[status] += 1
    return counts


def get_modification_summary(df: pd.DataFrame, log: list, pk_cols: list = None) -> Tuple[list, dict]:
    """
    Get summary of modification status for all rows.
    
    Args:
        df: DataFrame containing the data
        log: List of modification log entries
        pk_cols: Optional list of primary key column names
        
    Returns:
        Tuple of (summary_data list, status_counts dict)
    """
    status_counts = {"unprocessed": 0, "edited": 0, "approved": 0, "rejected": 0}
    
    summary_data = []
    for idx in range(len(df)):
        row_pk = None
        if pk_cols:
            try:
                row = df.iloc[idx]
                row_pk = {pk: row[pk] for pk in pk_cols if pk in df.columns}
            except:
                pass
        status = get_row_status(idx, log, row_pk)
        status_counts[status] += 1
        mods = get_row_modifications(idx, log)
        
        summary_data.append({
            "row_index": idx + 1,
            "status": status,
            "modifications_count": len(mods),
            "patient_id": df.iloc[idx].get("PatientID", "N/A"),
            "variant_key": df.iloc[idx].get("Variant_key", "N/A"),
        })
    
    return summary_data, status_counts
