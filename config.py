"""
Configuration and shared state for Epitopes Data Editor PyShiny App
"""

import json
import pandas as pd
from pathlib import Path


# Setup paths
app_dir = Path(__file__).parent
data_dir = app_dir / "data"
data_dir.mkdir(exist_ok=True)

# Load CSV data
csv_path = data_dir / "dummy_data_50rows.csv"
df_original = pd.read_csv(csv_path)

# Try to load saved data state if it exists
data_state_path = data_dir / "data_state.json"
if data_state_path.exists():
    try:
        df_saved = pd.read_json(data_state_path, orient="records")
        df_original = df_saved
    except:
        pass  # If loading fails, use original CSV

# Define columns to display (from tab_config.json structure)
display_columns = [
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

# Filter to available columns
display_columns = [col for col in display_columns if col in df_original.columns]

# All available columns from the dataframe
all_columns = list(df_original.columns)

# Modifications log file
modifications_log_path = data_dir / "modifications_log.json"


def load_modifications_log():
    """Load modifications log from file if it exists"""
    if modifications_log_path.exists():
        with open(modifications_log_path, "r") as f:
            return json.load(f)
    return []


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
