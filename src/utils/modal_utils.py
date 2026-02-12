"""
Modal and dialog builders for the Epitopes Data Editor.
"""

import pandas as pd
from shiny import ui
from .filter_utils import _is_operator_filter, OPERATOR_LABELS


def build_current_column_tag(col: str, index: int) -> ui.div:
    """Build a draggable current column tag for the column modal."""
    return ui.div(
        ui.span("⠿", class_="drag-handle-modal", style="cursor: grab; margin-right: 6px; color: rgba(255,255,255,0.5);"),
        ui.span(f"{index}. {col}", style="margin-right: 8px;"),
        ui.tags.button("×", class_="remove-modal-col", onclick=f"removeColumnFromModal('{col}', event)", 
                       style="background: none; border: none; color: rgba(255,255,255,0.7); cursor: pointer; font-size: 14px;"),
        class_="current-col-tag modal-draggable-col",
        draggable="true",
        **{"data-column": col},
        style="display: inline-flex; align-items: center; padding: 6px 10px; background: #2c3e50; color: white; border-radius: 4px; font-size: 12px; margin: 3px; cursor: move;"
    )


def build_available_column_tag(col: str) -> ui.div:
    """Build an available column tag for the column modal."""
    return ui.div(
        f"+ {col}",
        class_="add-col-tag",
        onclick=f"addColumn('{col}', event)",
        style="display: inline-block; padding: 6px 12px; background: #e9ecef; border-radius: 4px; font-size: 12px; cursor: pointer; margin: 3px;"
    )


def build_columns_modal_content(current_cols: list, available_cols: list) -> ui.div:
    """Build the full columns modal content."""
    current_html = [build_current_column_tag(col, i) for i, col in enumerate(current_cols, 1)]
    available_html = [build_available_column_tag(col) for col in available_cols]
    
    return ui.div(
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
                style="display: flex; flex-wrap: wrap; min-height: 40px;"
            )
        )
    )


def build_preset_menu_items(presets: dict, current_preset: str) -> ui.div:
    """Build preset menu items list."""
    items = []
    for name in presets.keys():
        is_active = name == current_preset
        delete_btn = ui.tags.span(
            "×", 
            class_="delete-preset", 
            onclick=f"deletePreset('{name}', event)"
        ) if name != "Default" else ""
        
        items.append(
            ui.div(
                name,
                delete_btn,
                class_=f"preset-menu-item {'active' if is_active else ''}",
                onclick=f"loadPreset('{name}', event)"
            )
        )
    
    if not items:
        return ui.div("No presets available", style="color: #999; padding: 8px;")
    return ui.div(*items)


def build_copy_column_buttons(columns: list) -> ui.div:
    """Build copy column buttons list."""
    buttons = []
    for col in columns:
        safe_col = col.replace("'", "\\'")
        buttons.append(
            ui.tags.button(
                col,
                class_="btn copy-col-btn",
                onclick=f"copyColumnValues('{safe_col}')",
                style="width: 100%; margin-bottom: 4px; text-align: left; padding: 6px 10px; font-size: 12px; border: 1px solid #333; color: #333; background: white;"
            )
        )
    return ui.div(*buttons, style="max-height: 400px; overflow-y: auto;")


def build_filter_column_buttons(available_cols: list) -> ui.div:
    """Build filter column selection buttons."""
    if not available_cols:
        return ui.p("All columns are already being filtered.", style="color: #6c757d;")
    
    column_buttons = []
    for col in available_cols:
        column_buttons.append(
            ui.tags.button(
                col,
                class_="btn btn-outline-secondary btn-block",
                onclick=f"addFilter('{col}', event)",
                style="width: 100%; margin-bottom: 8px; text-align: left; padding: 8px 12px; font-size: 12px;"
            )
        )
    
    return ui.div(*column_buttons, style="max-height: 400px; overflow-y: auto;")


def build_operator_filter_element(col_name: str, filter_def: dict, fix_filter: bool = False) -> ui.div:
    """Build a read-only display element for an operator filter."""
    op = filter_def.get("op", "in")
    value = filter_def.get("value")
    op_label = OPERATOR_LABELS.get(op, op)
    
    # Format value display
    if isinstance(value, list):
        if op == "between" and len(value) == 2:
            value_display = f"{value[0]}  →  {value[1]}"
        else:
            value_display = ", ".join(str(v) for v in value)
    else:
        value_display = str(value) if value is not None else ""
    
    # Build remove button (hidden when filters are fixed)
    remove_btn = ui.tags.button("×", class_="remove-filter-btn", 
                       onclick=f"removeFilter('{col_name}', event)",
                       style="background: none; border: none; color: #dc3545; cursor: pointer; font-size: 14px; padding: 0 4px;") if not fix_filter else ui.span()
    
    return ui.div(
        ui.div(
            ui.tags.label(col_name, style="font-size: 12px; font-weight: 500;"),
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


def build_dynamic_filter_element(col_name: str, unique_values: list, current_value: str, fix_filter: bool = False) -> ui.div:
    """Build a single dynamic filter element with multi-select support."""
    # Format current value for display
    display_value = current_value if current_value and current_value != "all" else ""
    
    # Build the list of unique values for the modal (exclude 'all')
    value_options = [v for v in unique_values if v != "all"]
    
    # Build remove button (hidden when filters are fixed)
    remove_btn = ui.tags.button("×", class_="remove-filter-btn", 
                       onclick=f"removeFilter('{col_name}', event)",
                       style="background: none; border: none; color: #dc3545; cursor: pointer; font-size: 14px; padding: 0 4px;") if not fix_filter else ui.span()
    
    return ui.div(
        ui.div(
            ui.tags.label(col_name, style="font-size: 12px; font-weight: 500;"),
            remove_btn,
            style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;"
        ),
        ui.div(
            # Use textarea for multi-line paste support
            ui.input_text_area(
                f"filter_{col_name}",
                label=None,
                value=display_value,
                placeholder=f"Paste values (one per line) or click ⋮",
                rows=3
            ),
            ui.tags.button(
                "⋮",
                class_="btn btn-sm btn-outline-secondary filter-values-btn",
                onclick=f"openFilterValuesModal('{col_name}', event)",
                title="Select from available values",
                style="position: absolute; right: 5px; top: 50%; transform: translateY(-50%); padding: 2px 8px; font-size: 14px;"
            ),
            style="position: relative;"
        ),
        # Hidden data attribute with unique values for the modal
        ui.tags.div(
            id=f"filter_values_{col_name}",
            style="display: none;",
            **{"data-values": ",".join(value_options[:500])}  # Limit to 500 values
        ),
        class_="filter-group",
        style="margin-bottom: 10px;"
    )


def build_dynamic_filters_panel(filters: dict, df: pd.DataFrame, fix_filter: bool = False) -> ui.div:
    """Build the complete dynamic filters panel."""
    if not filters:
        if fix_filter:
            return ui.div(
                ui.p("No default filters configured.", style="font-size: 12px; color: #6c757d; margin: 5px 0;")
            )
        return ui.div(
            ui.p("No filters active. Click + to add a filter.", style="font-size: 12px; color: #6c757d; margin: 5px 0;")
        )
    
    filter_elements = []
    for col_name, filter_value in filters.items():
        # Operator dict → render as read-only label (no DataFrame dependency)
        if _is_operator_filter(filter_value):
            filter_elements.append(build_operator_filter_element(col_name, filter_value, fix_filter=fix_filter))
            continue
        
        # Simple string filter needs the column in the DataFrame for unique values
        if col_name not in df.columns:
            continue
        
        unique_values = ["all"] + sorted(df[col_name].dropna().astype(str).unique().tolist())
        current_value = filter_value if filter_value else "all"
        filter_elements.append(build_dynamic_filter_element(col_name, unique_values, current_value, fix_filter=fix_filter))
    
    return ui.div(*filter_elements)
