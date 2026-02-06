"""
Column management utilities for the Epitopes Data Editor.
Handle column operations like add, remove, reorder, sort.
"""

import pandas as pd
from typing import List, Dict, Any, Optional, Tuple


def parse_column_value(val: Any) -> Optional[str]:
    """Extract column name from input value (handles both string and dict format)."""
    if not val:
        return None
    return val.get('col') if isinstance(val, dict) else val


def parse_column_order(val: Any) -> Optional[List[str]]:
    """Extract column order from input value."""
    if not val:
        return None
    return val.get('order') if isinstance(val, dict) else val


def add_column_to_list(columns: List[str], column: str) -> List[str]:
    """Add a column to the list if not already present."""
    cols = columns.copy()
    if column not in cols:
        cols.append(column)
    return cols


def remove_column_from_list(columns: List[str], column: str) -> List[str]:
    """Remove a column from the list if present."""
    cols = columns.copy()
    if column in cols:
        cols.remove(column)
    return cols


def sort_dataframe(df: pd.DataFrame, column: str, direction: str = 'asc') -> pd.DataFrame:
    """Sort a dataframe by column. Returns new sorted dataframe."""
    if column not in df.columns:
        return df
    ascending = direction == 'asc'
    return df.sort_values(by=column, ascending=ascending, ignore_index=True)


def get_preset_columns_and_widths(preset_data: Any, default_columns: List[str]) -> Tuple[List[str], Dict[str, Any]]:
    """Extract columns and widths from preset data (handles both old list format and new dict format)."""
    if isinstance(preset_data, list):
        return list(preset_data), {}
    elif isinstance(preset_data, dict):
        columns = list(preset_data.get("columns", default_columns))
        widths = preset_data.get("widths", {})
        return columns, widths
    return list(default_columns), {}


def create_preset_data(columns: List[str], widths: Dict[str, Any]) -> Dict[str, Any]:
    """Create preset data dict from columns and widths."""
    return {
        "columns": list(columns),
        "widths": widths.copy() if widths else {}
    }


def get_ordered_columns(preset_cols: List[str], all_cols: List[str]) -> List[str]:
    """Build ordered column list: preset columns first, then remaining columns."""
    ordered = [col for col in preset_cols if col in all_cols]
    ordered.extend([col for col in all_cols if col not in ordered])
    return ordered
