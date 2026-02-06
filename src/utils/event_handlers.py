"""
Event handler utilities for the Epitopes Data Editor.
Process event logic and return results for reactive handlers.
"""

from typing import Tuple, Optional, List, Dict, Any, Callable
from pathlib import Path


def process_approval_action(
    input_obj: Any,
    df_length: int,
    log: List[Dict],
    log_path: Path,
    get_selected_func: Callable[[Any, int], List[int]],
    create_entry_func: Callable[[List[int], int, int], Dict],
    save_log_func: Callable[[List[Dict], Path], None]
) -> Tuple[Optional[List[Dict]], Optional[str], Optional[str]]:
    """
    Process approval action.
    
    Returns:
        (updated_log, success_message, error_message)
    """
    selected_indices = get_selected_func(input_obj, df_length)
    
    if not selected_indices:
        return None, None, "Please select rows to approve"
    
    updated_log = log.copy()
    updated_log.append(create_entry_func(selected_indices, df_length, len(log)))
    save_log_func(updated_log, log_path)
    
    return updated_log, f"{len(selected_indices)} row(s) APPROVED!", None


def process_rejection_action(
    input_obj: Any,
    df_length: int,
    log: List[Dict],
    log_path: Path,
    get_selected_func: Callable[[Any, int], List[int]],
    create_entry_func: Callable[[List[int], int, int], Dict],
    save_log_func: Callable[[List[Dict], Path], None]
) -> Tuple[Optional[List[Dict]], Optional[str], Optional[str]]:
    """
    Process rejection action.
    
    Returns:
        (updated_log, success_message, error_message)
    """
    selected_indices = get_selected_func(input_obj, df_length)
    
    if not selected_indices:
        return None, None, "Please select rows to reject"
    
    updated_log = log.copy()
    updated_log.append(create_entry_func(selected_indices, df_length, len(log)))
    save_log_func(updated_log, log_path)
    
    return updated_log, f"{len(selected_indices)} row(s) REJECTED!", None


def process_undo_action(undo_data: Any) -> Optional[int]:
    """
    Extract log index from undo data.
    
    Returns:
        log_idx or None if invalid
    """
    if undo_data is None:
        return None
    return undo_data.get('index') if isinstance(undo_data, dict) else undo_data


def process_cell_edit_action(edit_data: Any) -> Tuple[Optional[int], Optional[str], str, str]:
    """
    Extract cell edit parameters from edit data.
    
    Returns:
        (row, col, old_value, new_value) - row/col are None if invalid
    """
    if not edit_data:
        return None, None, '', ''
    
    row = edit_data.get('row')
    col = edit_data.get('col')
    
    if row is None or not col:
        return None, None, '', ''
    
    return row, col, edit_data.get('oldValue', ''), edit_data.get('newValue', '')
