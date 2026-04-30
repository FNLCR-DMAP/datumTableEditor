"""
Modal and dialog builders for the Epitopes Data Editor.
"""

import re
import pandas as pd
from shiny import ui
from .filter_utils import _is_operator_filter, OPERATOR_LABELS


# Date pattern: YYYY-MM-DD (with optional time)
_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}')


def _mask(col: str, column_masks: dict | None) -> str:
    """Return display name for a column, applying mask if available."""
    return column_masks.get(col, col) if column_masks else col


def build_current_column_tag(col: str, index: int, column_masks: dict | None = None) -> ui.div:
    """Build a draggable current column tag for the column modal."""
    display = _mask(col, column_masks)
    safe_col = col.replace("\\", "\\\\").replace("'", "\\'")
    return ui.div(
        ui.span("⠃", class_="drag-handle-modal", style="cursor: grab; margin-right: 6px; color: rgba(255,255,255,0.5);"),
        ui.span(f"{index}. {display}", style="margin-right: 8px;"),
        ui.tags.button("×", class_="remove-modal-col", onclick=f"removeColumnFromModal('{safe_col}', event)", 
                       style="background: none; border: none; color: rgba(255,255,255,0.7); cursor: pointer; font-size: 14px;"),
        class_="current-col-tag modal-draggable-col",
        draggable="true",
        **{"data-column": col},
        style="display: inline-flex; align-items: center; padding: 6px 10px; background: #2c3e50; color: white; border-radius: 4px; font-size: 12px; margin: 3px; cursor: move;"
    )


def build_available_column_tag(col: str, column_masks: dict | None = None) -> ui.div:
    """Build an available column tag for the column modal."""
    display = _mask(col, column_masks)
    safe_col = col.replace("\\", "\\\\").replace("'", "\\'")
    return ui.div(
        f"+ {display}",
        class_="add-col-tag",
        onclick=f"addColumn('{safe_col}', event)",
        style="display: inline-block; padding: 6px 12px; background: #e9ecef; border-radius: 4px; font-size: 12px; cursor: pointer; margin: 3px;"
    )


def build_columns_modal_content(current_cols: list, available_cols: list, column_masks: dict | None = None) -> ui.div:
    """Build the full columns modal content."""
    current_html = [build_current_column_tag(col, i, column_masks=column_masks) for i, col in enumerate(current_cols, 1)]
    # Sort available columns alphabetically (by display name)
    sorted_available = sorted(available_cols, key=lambda c: _mask(c, column_masks).lower())
    available_html = [build_available_column_tag(col, column_masks=column_masks) for col in sorted_available]
    
    return ui.div(
        # Search box with Add / Remove buttons
        ui.div(
            ui.div(
                ui.tags.input(
                    type="text",
                    id="col-search-input",
                    placeholder="Search columns…",
                    autocomplete="off",
                    style="flex: 1; padding: 6px 10px; border: 1px solid #ced4da; border-radius: 4px; font-size: 12px; outline: none;",
                    oninput="filterModalColumns(this.value)"
                ),
                ui.tags.button(
                    "▼ Add selected",
                    class_="btn btn-sm btn-outline-success",
                    style="margin-left: 6px; font-size: 11px; padding: 5px 10px;",
                    onclick="bulkAddSelected(event)",
                    title="Add all selected columns to Current columns"
                ),
                ui.tags.button(
                    "▲ Remove selected",
                    class_="btn btn-sm btn-outline-danger",
                    style="margin-left: 4px; font-size: 11px; padding: 5px 10px;",
                    onclick="bulkRemoveSelected(event)",
                    title="Remove all selected columns from Current columns"
                ),
                style="display: flex; align-items: center;"
            ),
            # Search results dropdown (hidden by default, shown when typing)
            ui.div(
                id="col-search-results",
                style="display: none; max-height: 160px; overflow-y: auto; border: 1px solid #ced4da; border-radius: 4px; background: #fff; margin-top: 4px; margin-bottom: 4px;"
            ),
            # Selected columns staging area
            ui.div(
                id="col-search-selected",
                style="display: none; flex-wrap: wrap; gap: 4px; padding: 6px 0; margin-bottom: 10px;"
            ),
        ),
        # Current columns section
        ui.div(
            ui.tags.strong("Current columns (drag to reorder):", style="display: block; margin-bottom: 10px; color: #2c3e50;"),
            ui.div(
                *current_html if current_html else [ui.span("No columns displayed.", style="color: #999;")],
                id="modal-columns-container",
                style="display: flex; flex-wrap: wrap; padding: 10px; background: #f8f9fa; border-radius: 4px; border: 1px dashed #ced4da; min-height: 40px;"
            ),
            style="margin-bottom: 20px;"
        ),
        # Available columns section
        ui.div(
            ui.tags.strong("Remaining columns:", style="display: block; margin-bottom: 10px; color: #2c3e50;"),
            ui.div(
                *available_html if available_html else [ui.span("All columns displayed.", style="color: #999;")],
                id="modal-available-container",
                style="display: flex; flex-wrap: wrap; min-height: 40px;"
            )
        )
    )


def build_preset_menu_items(presets: dict, current_preset: str) -> ui.div:
    """Build preset menu items list."""
    items = []
    for name in presets.keys():
        is_active = name == current_preset
        safe_name = name.replace("\\", "\\\\").replace("'", "\\'")
        delete_btn = ui.tags.span(
            "×", 
            class_="delete-preset", 
            onclick=f"deletePreset('{safe_name}', event)"
        ) if name != "Default" else ""
        
        items.append(
            ui.div(
                name,
                delete_btn,
                class_=f"preset-menu-item {'active' if is_active else ''}",
                onclick=f"loadPreset('{safe_name}', event)"
            )
        )
    
    if not items:
        return ui.div("No presets available", style="color: #999; padding: 8px;")
    return ui.div(*items)


def build_copy_column_buttons(columns: list, column_masks: dict | None = None) -> ui.div:
    """Build copy column buttons list."""
    buttons = []
    for col in columns:
        display = _mask(col, column_masks)
        safe_col = col.replace("'", "\\'")
        buttons.append(
            ui.tags.button(
                display,
                class_="btn copy-col-btn",
                onclick=f"copyColumnValues('{safe_col}')",
                style="width: 100%; margin-bottom: 4px; text-align: left; padding: 6px 10px; font-size: 12px; border: 1px solid #333; color: #333; background: white;"
            )
        )
    return ui.div(*buttons, style="max-height: 400px; overflow-y: auto;")


def build_filter_column_buttons(available_cols: list, column_masks: dict | None = None) -> ui.div:
    """Build filter column selection buttons."""
    if not available_cols:
        return ui.p("All columns are already being filtered.", style="color: #6c757d;")
    
    column_buttons = []
    for col in available_cols:
        display = _mask(col, column_masks)
        safe_col = col.replace("\\", "\\\\").replace("'", "\\'")
        column_buttons.append(
            ui.tags.button(
                display,
                class_="btn btn-outline-secondary btn-block",
                onclick=f"addFilter('{safe_col}', event)",
                style="width: 100%; margin-bottom: 8px; text-align: left; padding: 8px 12px; font-size: 12px;"
            )
        )
    
    return ui.div(*column_buttons, style="max-height: 400px; overflow-y: auto;")


def build_operator_filter_element(col_name: str, filter_def: dict, fix_filter: bool = False, column_masks: dict | None = None) -> ui.div:
    """Build a read-only display element for an operator filter."""
    display = _mask(col_name, column_masks)
    op = filter_def.get("op", "in")
    value = filter_def.get("value")
    op_label = OPERATOR_LABELS.get(op, op)
    
    # Format value display
    if op in ("not_empty", "is_null"):
        value_display = ""  # no-value operator
    elif op == "last_n_days":
        value_display = f"{value} days"  # show "7 days"
    elif isinstance(value, list):
        if op == "between" and len(value) == 2:
            value_display = f"{value[0]}  →  {value[1]}"
        else:
            value_display = ", ".join(str(v) for v in value)
    else:
        value_display = str(value) if value is not None else ""
    
    # Build remove button (hidden when filters are fixed)
    safe_col_name = col_name.replace("\\", "\\\\").replace("'", "\\'")
    remove_btn = ui.tags.button("×", class_="remove-filter-btn", 
                       onclick=f"removeFilter('{safe_col_name}', event)",
                       style="background: none; border: none; color: #dc3545; cursor: pointer; font-size: 14px; padding: 0 4px;") if not fix_filter else ui.span()
    
    return ui.div(
        ui.div(
            ui.tags.label(display, style="font-size: 12px; font-weight: 500;"),
            remove_btn,
            style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;"
        ),
        ui.div(
            ui.tags.span(op_label, style="font-size: 11px; color: #fff; background: #6c757d; padding: 2px 6px; border-radius: 3px; margin-right: 6px;"),
            ui.tags.span(value_display, style="font-size: 12px; color: #333; word-break: break-word;"),
            style="padding: 6px 8px; background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px;"
        ),
        class_="filter-group",
        style="margin-bottom: 10px;"
    )


def _looks_like_dates(values: list) -> bool:
    """Return True if at least half of the non-empty sample values look like dates."""
    if not values:
        return False
    sample = [v for v in values[:20] if v and str(v).strip()]
    if not sample:
        return False
    date_count = sum(1 for v in sample if _DATE_RE.match(str(v).strip()))
    return date_count >= len(sample) * 0.5


def build_dynamic_filter_element(col_name: str, unique_values: list, current_value: str, fix_filter: bool = False, column_masks: dict | None = None, current_op: str = "in", is_date: bool = False) -> ui.div:
    """Build a single dynamic filter element with multi-select support and operator dropdown."""
    display = _mask(col_name, column_masks)
    # Format current value for display
    display_value = current_value if current_value and current_value != "all" else ""
    
    # Build the list of unique values for the modal (exclude 'all')
    value_options = [v for v in unique_values if v != "all"]
    
    # Build remove button (hidden when filters are fixed)
    safe_col_name = col_name.replace("\\", "\\\\").replace("'", "\\'")
    remove_btn = ui.tags.button("×", class_="remove-filter-btn", 
                       onclick=f"removeFilter('{safe_col_name}', event)",
                       style="background: none; border: none; color: #dc3545; cursor: pointer; font-size: 14px; padding: 0 4px;") if not fix_filter else ui.span()
    
    # Operator options available for interactive filters
    op_options = [
        ("in", "is"),
        ("not_in", "is not"),
        ("contains", "contains"),
        ("not_contains", "does not contain"),
        ("gt", ">"),
        ("gte", "≥"),
        ("lt", "<"),
        ("lte", "≤"),
        ("between", "between"),
        ("regex", "matches regex"),
        ("not_empty", "is not empty"),
        ("is_null", "is null"),
        ("last_n_days", "within last N days"),
    ]
    
    option_tags = [
        ui.tags.option(label, value=val, selected="selected" if val == current_op else None)
        for val, label in op_options
    ]
    
    op_select_attrs = {
        "class_": "form-select form-select-sm filter-op-select",
        "onchange": f"setFilterOperator('{safe_col_name}', this.value, event)",
        "style": "font-size: 11px; padding: 2px 6px; height: auto; max-width: 160px; margin-left: 6px;",
    }
    if fix_filter:
        op_select_attrs["disabled"] = "disabled"
    op_select = ui.tags.select(
        *option_tags,
        **op_select_attrs
    )
    
    # For 'not_empty' / 'is_null' operators, hide the value area (no value needed)
    textarea_style = "position: relative;" if current_op not in ("not_empty", "is_null") else "position: relative; display: none;"
    
    # Shared attributes for date inputs when locked
    _date_disabled = {"disabled": "disabled"} if fix_filter else {}

    if is_date and current_op not in ("not_empty", "is_null"):
        # Parse existing date values
        date_vals = [v.strip()[:10] for v in display_value.split('\n') if v.strip()] if display_value else []
        
        if current_op == "between":
            # Two date pickers for range
            date_from = date_vals[0] if len(date_vals) > 0 else ""
            date_to = date_vals[1] if len(date_vals) > 1 else ""
            value_area = ui.div(
                ui.div(
                    ui.tags.label("From", style="font-size: 11px; color: #6c757d; margin-right: 4px;"),
                    ui.tags.input(
                        type="date", value=date_from,
                        class_="form-control form-control-sm filter-date-input",
                        style="font-size: 12px;",
                        onchange=f"applyDateFilter('{safe_col_name}', event)",
                        **{"data-column": col_name, "data-role": "from", **_date_disabled}
                    ),
                    style="display: flex; align-items: center; margin-bottom: 4px;"
                ),
                ui.div(
                    ui.tags.label("To", style="font-size: 11px; color: #6c757d; margin-right: 16px;"),
                    ui.tags.input(
                        type="date", value=date_to,
                        class_="form-control form-control-sm filter-date-input",
                        style="font-size: 12px;",
                        onchange=f"applyDateFilter('{safe_col_name}', event)",
                        **{"data-column": col_name, "data-role": "to", **_date_disabled}
                    ),
                    style="display: flex; align-items: center;"
                ),
                style="padding: 4px 0;"
            )
        elif current_op == "last_n_days":
            # Number input for "within last N days"
            n_val = ""
            if date_vals:
                # Value should be a number (days), not a date
                try:
                    n_val = str(int(date_vals[0]))
                except (ValueError, TypeError):
                    n_val = "7"
            value_area = ui.div(
                ui.div(
                    ui.tags.input(
                        type="number", value=n_val, min="1", step="1",
                        placeholder="e.g. 7",
                        class_="form-control form-control-sm filter-date-input",
                        style="font-size: 12px; width: 80px; display: inline-block;",
                        id=f"filter_{col_name}",
                        onchange=f"applyDateFilter('{safe_col_name}', event)",
                        **_date_disabled
                    ),
                    ui.tags.span(" days", style="font-size: 12px; color: #6c757d; margin-left: 4px;"),
                    style="display: flex; align-items: center; margin-bottom: 4px;"
                ),
                style="padding: 4px 0;"
            )
        elif current_op in ("gt", "gte", "lt", "lte"):
            # Single date picker
            date_val = date_vals[0] if date_vals else ""
            value_area = ui.div(
                ui.tags.input(
                    type="date", value=date_val,
                    class_="form-control form-control-sm filter-date-input",
                    style="font-size: 12px;",
                    onchange=f"applyDateFilter('{safe_col_name}', event)",
                    **{"data-column": col_name, "data-role": "single", **_date_disabled}
                ),
                style="padding: 4px 0;"
            )
        else:
            # in / not_in / contains / etc → fall through to textarea
            is_date = False
    
    if not is_date or current_op in ("not_empty", "is_null"):
        # Standard textarea with edit/confirm and ⋮ buttons
        if fix_filter:
            # Locked mode: read-only textarea, no edit/values buttons
            value_area = ui.div(
                ui.input_text_area(
                    f"filter_{col_name}",
                    label=None,
                    value=display_value,
                    placeholder="",
                    rows=3
                ),
                # Force textarea readonly via inline script
                ui.tags.script(
                    f"(function(){{ var ta = document.getElementById('filter_{col_name}'); if(ta){{ ta.readOnly=true; ta.style.background='#f0f0f0'; ta.style.cursor='default'; }} }})()"
                ),
                style=textarea_style
            )
        else:
            value_area = ui.div(
                ui.input_text_area(
                    f"filter_{col_name}",
                    label=None,
                    value=display_value,
                    placeholder=f"Paste values (one per line) or click ⋮",
                    rows=3
                ),
                ui.tags.button(
                    "\u22ee",
                    class_="btn btn-sm btn-outline-secondary filter-values-btn",
                    onclick=f"openFilterValuesModal('{safe_col_name}', event)",
                    title="Select from available values",
                    style="position: absolute; right: 5px; top: 35%; transform: translateY(-50%); padding: 2px 8px; font-size: 14px; z-index: 2;"
                ),
                ui.tags.button(
                    "\u2715",
                    class_="btn btn-sm btn-outline-danger filter-clear-btn",
                    onclick=f"clearFilterContent('{col_name}', event)",
                    title="Clear filter content",
                    style="position: absolute; right: 5px; top: 70%; transform: translateY(-50%); padding: 2px 6px; font-size: 12px; z-index: 2;"
                ),
                style=textarea_style
            )
    
    return ui.div(
        ui.div(
            ui.tags.label(display, style="font-size: 12px; font-weight: 500;"),
            op_select,
            remove_btn,
            style="display: flex; align-items: center; margin-bottom: 4px; gap: 4px;"
        ),
        value_area,
        # Hidden data attribute with unique values for the modal
        ui.tags.div(
            id=f"filter_values_{col_name}",
            style="display: none;",
            **{"data-values": ",".join(value_options)}
        ),
        class_="filter-group",
        style="margin-bottom: 10px;"
    )


def build_dynamic_filters_panel(
    filters: dict,
    df: pd.DataFrame,
    fix_filter: bool = False,
    all_columns: list = None,
    get_unique_values_func=None,
    column_masks: dict | None = None,
    date_columns: set | None = None
) -> ui.div:
    """Build the complete dynamic filters panel.
    
    Args:
        filters: Active filters dict
        df: Current DataFrame (may be empty in lazy loading mode)
        fix_filter: Whether filters are locked
        all_columns: All known column names (for lazy loading when df has no columns)
        get_unique_values_func: Callback to fetch unique values from DB (lazy mode)
        column_masks: Optional column display name overrides
        date_columns: Set of column names known to be date/timestamp type
    """
    if date_columns is None:
        date_columns = set()
    if not filters:
        if fix_filter:
            return ui.div(
                ui.p("No default filters configured.", style="font-size: 12px; color: #6c757d; margin: 5px 0;")
            )
        return ui.div(
            ui.p("No filters active. Click + to add a filter.", style="font-size: 12px; color: #6c757d; margin: 5px 0;")
        )
    
    known_columns = set(df.columns)
    if all_columns:
        known_columns.update(all_columns)
    
    filter_elements = []
    for col_name, filter_value in filters.items():
        # Operator dict filters — both config-defined and interactive
        if _is_operator_filter(filter_value):
            op = filter_value.get("op", "in")
            # Extract display value from the operator dict
            raw_val = filter_value.get("value")
            if isinstance(raw_val, list):
                display_val = "\n".join(str(v) if v is not None else "" for v in raw_val)
            elif raw_val is not None:
                display_val = str(raw_val)
            else:
                display_val = ""
            
            # Get unique values for the values picker
            # Prefer DB callback (full table) over DataFrame (may be paginated)
            if get_unique_values_func:
                db_values = get_unique_values_func(col_name)
                unique_values = ["all"] + db_values
            elif col_name in df.columns and len(df) > 0:
                unique_values = ["all"] + sorted(df[col_name].dropna().astype(str).unique().tolist())
            else:
                unique_values = ["all"]
            
            filter_elements.append(build_dynamic_filter_element(
                col_name, unique_values, display_val,
                fix_filter=fix_filter, column_masks=column_masks, current_op=op,
                is_date=(col_name in date_columns or _looks_like_dates(unique_values[1:]))
            ))
            continue
        
        # Skip columns that aren't known at all
        if col_name not in known_columns:
            continue
        
        # Get unique values: prefer DB query (full table), fall back to DataFrame
        if get_unique_values_func:
            db_values = get_unique_values_func(col_name)
            unique_values = ["all"] + db_values
        elif col_name in df.columns and len(df) > 0:
            unique_values = ["all"] + sorted(df[col_name].dropna().astype(str).unique().tolist())
        else:
            unique_values = ["all"]
        
        current_value = filter_value if filter_value else "all"
        col_is_date = col_name in date_columns or _looks_like_dates(unique_values[1:])
        filter_elements.append(build_dynamic_filter_element(col_name, unique_values, current_value, fix_filter=fix_filter, column_masks=column_masks, is_date=col_is_date))
    
    return ui.div(*filter_elements)
