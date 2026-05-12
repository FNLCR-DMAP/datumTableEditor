"""
Filtering utilities for search and column filters.

Supports two filter value formats:
  - Simple string: "val1\\nval2" → exact match (IN)
  - Operator dict: {"op": "not_contains", "value": "RT"} → rich operator

Supported operators:
  in, not_in, contains, not_contains, between, value_range, gt, gte, lt, lte, last_n_days, not_empty, is_null, regex
"""

import re
from datetime import datetime, timedelta

import pandas as pd
from typing import Any, Callable


# ── Operator helpers ──────────────────────────────────────────────

OPERATOR_LABELS = {
    "in": "is",
    "not_in": "is not",
    "contains": "contains",
    "not_contains": "does not contain",
    "between": "between",
    "value_range": "value range",
    "gt": ">",
    "gte": "≥",
    "lt": "<",
    "lte": "≤",
    "regex": "matches",
    "not_empty": "is not empty",
    "is_null": "is null",
    "last_n_days": "within last N days",
}


def _is_operator_filter(filter_value) -> bool:
    """Check if a filter value is an operator dict."""
    return isinstance(filter_value, dict) and "op" in filter_value


def _row_matches_operator(row_value_raw: Any, filter_def: dict) -> bool:
    """
    Evaluate a single row value against an operator filter definition.
    
    Args:
        row_value_raw: The raw cell value from the DataFrame row
        filter_def: {"op": "...", "value": ...}
    """
    op = filter_def.get("op", "in")
    fval = filter_def.get("value")
    row_str = str(row_value_raw) if row_value_raw is not None else ""
    
    # Empty / blank value → no constraint (pass through) for value-based ops
    if op not in ("not_empty", "is_null"):
        if fval is None or fval == "" or fval == []:
            return True
        if isinstance(fval, list) and all(
            v is None or (isinstance(v, str) and v.strip() == "") for v in fval
        ):
            return True
    
    if op == "in" or op == "is":
        targets = fval if isinstance(fval, list) else [fval]
        return row_str in [str(t) for t in targets]
    
    elif op == "not_in" or op == "is not":
        targets = fval if isinstance(fval, list) else [fval]
        return row_str not in [str(t) for t in targets]
    
    elif op == "contains":
        targets = fval if isinstance(fval, list) else [fval]
        return any(str(t).lower() in row_str.lower() for t in targets if t)
    
    elif op == "not_contains":
        targets = fval if isinstance(fval, list) else [fval]
        return all(str(t).lower() not in row_str.lower() for t in targets if t)
    
    elif op in ("between", "value_range"):
        if isinstance(fval, list) and len(fval) == 2:
            lo_raw, hi_raw = fval
            lo_none = lo_raw is None or str(lo_raw).strip() == ""
            hi_none = hi_raw is None or str(hi_raw).strip() == ""
            # Both bounds absent — pass through (no filtering)
            if lo_none and hi_none:
                return True
            # Half-open: only lower bound → gte
            if hi_none:
                try:
                    return float(row_str) >= float(lo_raw)
                except (ValueError, TypeError):
                    return row_str >= str(lo_raw)
            # Half-open: only upper bound → lte
            if lo_none:
                try:
                    return float(row_str) <= float(hi_raw)
                except (ValueError, TypeError):
                    return row_str <= str(hi_raw)
            # Both bounds present — closed range
            try:
                return float(lo_raw) <= float(row_str) <= float(hi_raw)
            except (ValueError, TypeError):
                return str(lo_raw) <= row_str <= str(hi_raw)
        return True  # malformed — don't filter
    
    elif op == "gt":
        try: return float(row_str) > float(fval)
        except (ValueError, TypeError): return row_str > str(fval)
    
    elif op == "gte":
        try: return float(row_str) >= float(fval)
        except (ValueError, TypeError): return row_str >= str(fval)
    
    elif op == "lt":
        try: return float(row_str) < float(fval)
        except (ValueError, TypeError): return row_str < str(fval)
    
    elif op == "lte":
        try: return float(row_str) <= float(fval)
        except (ValueError, TypeError): return row_str <= str(fval)
    
    elif op == "last_n_days":
        try:
            raw = fval[0] if isinstance(fval, list) else fval
            n = int(raw)
            cutoff = datetime.now() - timedelta(days=n)
            parsed = pd.to_datetime(row_str, errors="coerce")
            if pd.isna(parsed):
                return False
            return parsed >= cutoff
        except (ValueError, TypeError):
            return True  # malformed — don't filter
    
    elif op == "not_empty":
        if row_value_raw is None or pd.isna(row_value_raw):
            return False
        return row_str.strip() != ""
    
    elif op == "is_null":
        return row_value_raw is None or pd.isna(row_value_raw) or row_str.strip() == ""
    
    elif op == "regex":
        try:
            return bool(re.search(str(fval), row_str))
        except re.error:
            return True  # invalid regex — don't filter
    
    return True  # unknown op — don't filter


def get_filtered_rows(
    df: pd.DataFrame,
    active_columns: list,
    search_term: str,
    status_filters: list,
    column_filters: dict,
    get_row_status_func: Callable[[int], str],
    search_column: str = "all"
) -> list:
    """
    Get filtered row indices based on search, status filter, and dynamic column filters.
    
    Filter values can be:
      - A string ("val1\\nval2"): exact match, row value must be one of the values
      - An operator dict ({"op": "not_contains", "value": "RT"}): rich operator
    
    Args:
        df: DataFrame containing the data
        active_columns: List of currently active/visible columns
        search_term: Search string to filter by
        status_filters: List of status values to include
        column_filters: Dictionary of {column_name: filter_value_or_operator_dict}
        get_row_status_func: Function that returns status for a given row index
        search_column: Column to search in, or "all" for all active columns
        
    Returns:
        List of row indices (DataFrame index values) that match all filters
    """
    filtered_indices = []
    
    for idx, row in df.iterrows():
        # Check status filter
        current_status = get_row_status_func(idx)
        if current_status not in status_filters:
            continue
        
        # Check dynamic column filters
        filter_pass = True
        for col_name, filter_value in column_filters.items():
            if col_name not in df.columns:
                continue
            
            # Operator dict filter
            if _is_operator_filter(filter_value):
                if not _row_matches_operator(row.get(col_name), filter_value):
                    filter_pass = False
                    break
                continue
            
            # Simple string filter (original behavior)
            if not filter_value or not str(filter_value).strip() or filter_value == "all":
                continue
            
            normalized = str(filter_value).replace('\n', ',').replace('\r', ',')
            filter_values = [v.strip() for v in normalized.split(",") if v.strip()]
            if filter_values:
                row_value = str(row.get(col_name, ""))
                if row_value not in filter_values:
                    filter_pass = False
                    break
        
        if not filter_pass:
            continue
        
        # Check search filter (case-insensitive contains)
        if search_term.strip():
            search_lower = search_term.lower().strip()
            row_matches = False
            
            if search_column and search_column != "all" and search_column in df.columns:
                if search_lower in str(row[search_column]).lower():
                    row_matches = True
            else:
                for col in active_columns:
                    if col in df.columns and search_lower in str(row[col]).lower():
                        row_matches = True
                        break
            
            if not row_matches:
                continue
        
        filtered_indices.append(idx)
    
    return filtered_indices


def apply_column_filters(df: pd.DataFrame, column_filters: dict) -> pd.DataFrame:
    """Apply column filters to a DataFrame and return the filtered subset.

    This is a lightweight filter intended for computing facet value counts
    on the already-loaded DataFrame.  It supports the same filter formats as
    ``get_filtered_rows`` (newline-delimited strings and operator dicts) but
    skips status/search filtering.
    """
    if not column_filters:
        return df

    mask = pd.Series(True, index=df.index)

    for col_name, filter_value in column_filters.items():
        if col_name not in df.columns:
            continue

        if _is_operator_filter(filter_value):
            col_mask = df.apply(
                lambda row, _col=col_name, _fv=filter_value: _row_matches_operator(row.get(_col), _fv),
                axis=1,
            )
            mask &= col_mask
            continue

        if not filter_value or not str(filter_value).strip() or filter_value == "all":
            continue

        normalized = str(filter_value).replace("\n", ",").replace("\r", ",")
        filter_values = [v.strip() for v in normalized.split(",") if v.strip()]
        if filter_values:
            col_series = df[col_name].fillna("No value").astype(str)
            mask &= col_series.isin(filter_values)

    return df.loc[mask]
