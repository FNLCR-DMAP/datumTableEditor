"""
Filtering utilities for search and column filters.
"""

import pandas as pd
from typing import Callable


def get_filtered_rows(
    df: pd.DataFrame,
    active_columns: list,
    search_term: str,
    status_filters: list,
    column_filters: dict,
    get_row_status_func: Callable[[int], str]
) -> list:
    """
    Get filtered row indices based on search, status filter, and dynamic column filters.
    
    Args:
        df: DataFrame containing the data
        active_columns: List of currently active/visible columns
        search_term: Search string to filter by
        status_filters: List of status values to include (e.g., ["unprocessed", "edited"])
        column_filters: Dictionary of {column_name: filter_value}
        get_row_status_func: Function that returns status for a given row index
        
    Returns:
        List of row indices that match all filters
    """
    filtered_indices = []
    
    for idx, (_, row) in enumerate(df.iterrows()):
        # Check status filter
        current_status = get_row_status_func(idx)
        if current_status not in status_filters:
            continue
        
        # Check dynamic column filters
        filter_pass = True
        for col_name, filter_value in column_filters.items():
            if filter_value and filter_value != "all" and col_name in df.columns:
                if str(row.get(col_name, "")) != filter_value:
                    filter_pass = False
                    break
        
        if not filter_pass:
            continue
        
        # Check search filter
        if search_term.strip():
            search_lower = search_term.lower().strip()
            row_matches = False
            for col in active_columns:
                if col in df.columns and search_lower in str(row[col]).lower():
                    row_matches = True
                    break
            if not row_matches:
                continue
        
        filtered_indices.append(idx)
    
    return filtered_indices
