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


def get_row_status(row_idx: int, log: list) -> str:
    """
    Determine row status based on modifications log.
    
    Args:
        row_idx: Index of the row
        log: List of modification log entries
        
    Returns:
        Status string: "approved", "rejected", "edited", or "unprocessed"
    """
    # Check for active (non-undone) modifications on this row
    has_active_modifications = any(
        m.get("details", {}).get("row_index") == row_idx 
        and not m.get("undone", False)
        for m in log if m.get("type") == "field_modification"
    )
    
    row_approval_entries = [
        m for m in log 
        if m.get("type") in ["approval", "rejection"] 
        and row_idx in m.get("details", {}).get("approved_rows", []) + m.get("details", {}).get("rejected_rows", [])
    ]
    
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


def get_status_counts(df: pd.DataFrame, log: list) -> dict:
    """
    Get counts of each status.
    
    Args:
        df: DataFrame containing the data
        log: List of modification log entries
        
    Returns:
        Dictionary with counts for each status
    """
    counts = {"unprocessed": 0, "edited": 0, "approved": 0, "rejected": 0}
    for idx in range(len(df)):
        status = get_row_status(idx, log)
        counts[status] += 1
    return counts


def get_modification_summary(df: pd.DataFrame, log: list) -> Tuple[list, dict]:
    """
    Get summary of modification status for all rows.
    
    Args:
        df: DataFrame containing the data
        log: List of modification log entries
        
    Returns:
        Tuple of (summary_data list, status_counts dict)
    """
    status_counts = {"unprocessed": 0, "edited": 0, "approved": 0, "rejected": 0}
    
    summary_data = []
    for idx in range(len(df)):
        status = get_row_status(idx, log)
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
