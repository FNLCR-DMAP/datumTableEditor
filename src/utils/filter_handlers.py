"""
Filter handling utilities for the Epitopes Data Editor.
Handle dynamic filter operations.
"""

from typing import Dict, Any, Optional, Tuple


def parse_filter_column(val: Any) -> Optional[str]:
    """Extract column name from filter input value."""
    if not val:
        return None
    return val.get('column') if isinstance(val, dict) else val


def add_filter(filters: Dict[str, str], column: str) -> Dict[str, str]:
    """Add a new filter column with default value 'all'."""
    updated = filters.copy()
    if column not in updated:
        updated[column] = "all"
    return updated


def remove_filter(filters: Dict[str, str], column: str) -> Dict[str, str]:
    """Remove a filter column."""
    updated = filters.copy()
    if column in updated:
        del updated[column]
    return updated


def update_filter_values(filters: Dict[str, str], input_obj: Any) -> Tuple[Dict[str, str], bool]:
    """
    Update filter values from input objects.
    
    Returns:
        (updated_filters, was_updated)
    """
    if not filters:
        return filters, False
    
    updated = False
    new_filters = filters.copy()
    
    for col_name, filter_value in list(filters.items()):
        # Operator-dict filters (e.g. {"op": "not_contains", ...}) are rendered
        # as read-only labels — they have no input_text_area to read.
        if isinstance(filter_value, dict) and "op" in filter_value:
            continue
        filter_id = f"filter_{col_name}"
        try:
            current_val = getattr(input_obj, filter_id)()
            prev_val = new_filters.get(col_name)
            if current_val and prev_val != current_val:
                # User typed or selected filter values
                new_filters[col_name] = current_val
                updated = True
            elif not current_val and prev_val and prev_val != "all":
                # User cleared the filter → reset to "all" (no filter)
                new_filters[col_name] = "all"
                updated = True
        except Exception:
            # Only catch Exception; let SilentException/SilentCancelOutputException
            # (BaseException subclasses) propagate so Shiny's reactive graph stays intact
            pass
    
    return new_filters, updated
