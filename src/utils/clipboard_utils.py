"""
Clipboard utilities for the Epitopes Data Editor.
Handle copy-to-clipboard operations.
"""

import json
import pandas as pd
from typing import List, Tuple, Optional, Any, Callable


def generate_clipboard_js(text: str) -> str:
    """Generate JavaScript code to copy text to clipboard."""
    # Escape </script> to prevent tag breakout in inline scripts
    safe_text = json.dumps(text).replace("</", "<\\/")
    return f"""
        navigator.clipboard.writeText({safe_text}).then(function() {{
            console.log('Copied to clipboard');
        }}).catch(function(err) {{
            console.error('Could not copy: ', err);
        }});
    """


def process_copy_request(
    request: dict,
    df: pd.DataFrame,
    filtered_indices: List[int],
    rows_per_page_val: str,
    current_page: int,
    get_paginated_indices_func: Callable[[List[int], str, int], List[int]],
    get_copy_values_func: Callable[[pd.DataFrame, str, List[int], List[int]], Tuple[Optional[List[str]], Optional[str]]]
) -> Tuple[Optional[str], Optional[str], Optional[int], Optional[str]]:
    """
    Process a copy column request.
    
    Returns:
        (js_code, column_name, values_count, error_message)
        If error, js_code is None and error_message is set.
    """
    if not request:
        return None, None, None, None  # No request, silently return
    
    column_name = request.get('column')
    indices = request.get('indices', [])
    
    if not column_name or not indices:
        return None, None, None, "No column or rows selected."
    
    paginated_indices = get_paginated_indices_func(filtered_indices, rows_per_page_val, current_page)
    values, error = get_copy_values_func(df, column_name, paginated_indices, indices)
    
    if error:
        return None, column_name, None, error
    
    if values is None:
        return None, column_name, None, "Failed to get values"
    
    copy_text = "\n".join(values)
    js_code = generate_clipboard_js(copy_text)
    
    return js_code, column_name, len(values), None
