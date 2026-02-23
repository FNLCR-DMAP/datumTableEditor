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
        # Operator-dict filters without "interactive" flag are config-defined.
        # Skip them to avoid creating reactive dependencies on their textareas,
        # which would cause an infinite re-render loop (textareas get recreated
        # by dynamic_filters on every data.set(), and reading them here would
        # create a reactive dependency → effect re-fires → oscillation).
        is_op_dict = isinstance(filter_value, dict) and "op" in filter_value
        if is_op_dict and not filter_value.get("interactive"):
            continue
        
        filter_id = f"filter_{col_name}"
        try:
            current_val = getattr(input_obj, filter_id)()
            
            if is_op_dict:
                op = filter_value["op"]
                # Parse textarea content into a value list
                if current_val and str(current_val).strip():
                    values = [v.strip() for v in str(current_val).replace(',', '\n').split('\n') if v.strip()]
                else:
                    values = []
                
                old_values = filter_value.get("value", [])
                if not isinstance(old_values, list):
                    old_values = [old_values] if old_values is not None else []
                
                if values != old_values:
                    new_filters[col_name] = {"op": op, "value": values, "interactive": True}
                    updated = True
            else:
                # Simple string filter (original behavior)
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
