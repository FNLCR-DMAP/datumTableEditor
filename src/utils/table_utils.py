"""
Table rendering utilities for the Epitopes Data Editor.
These functions help build the data table UI components.
"""

import pandas as pd
from shiny import ui
from typing import Callable, Any
from .data_utils import get_row_status


def _mask(col: str, column_masks: dict | None) -> str:
    """Return display name for a column, applying mask if available."""
    return column_masks.get(col, col) if column_masks else col


def build_draggable_header_cell(col: str, width_style: str = "", column_masks: dict | None = None) -> ui.tags.th:
    """Build a draggable table header cell with action dropdown."""
    display = _mask(col, column_masks)
    return ui.tags.th(
        ui.tags.span(display, class_="header-text"),
        ui.tags.div(
            ui.tags.button(
                "⋮",
                class_="header-action-btn",
                **{"data-column": col}
            ),
            ui.tags.div(
                ui.tags.button("↑ Sort Ascending", class_="dropdown-item sort-asc-btn", **{"data-column": col}),
                ui.tags.button("↓ Sort Descending", class_="dropdown-item sort-desc-btn", **{"data-column": col}),
                ui.tags.button("✕ Remove Column", class_="dropdown-item remove-col-btn", **{"data-column": col}),
                class_="header-dropdown"
            ),
            class_="header-action-container"
        ),
        ui.tags.span(class_="resize-handle"),
        class_="draggable-header",
        draggable="true",
        style=width_style,
        **{"data-column": col}
    )


def build_table_header(cols: list, widths: dict, default_width: int = 130, show_status_column: bool = True, column_masks: dict | None = None) -> ui.tags.thead:
    """Build the complete table header."""
    # Select-all checkbox for the header using HTML() since input_ is reserved
    select_all_checkbox = ui.HTML(
        '<input type="checkbox" id="select_all_page" '
        'title="Select/Deselect all rows on this page" '
        'onclick="toggleSelectAllPage(this)">'
    )
    
    header_cells = [
        ui.tags.th(select_all_checkbox, style="width: 40px; text-align: center;"),
        ui.tags.th("Row", style="width: 50px;"),
    ]
    
    if show_status_column:
        header_cells.append(ui.tags.th("Mod", style="width: 70px;", title="Modification Status"))
    
    for col in cols:
        col_width = widths.get(col, default_width)
        width_style = f"width: {col_width}px; min-width: {col_width}px;"
        header_cells.append(build_draggable_header_cell(col, width_style, column_masks=column_masks))
    
    return ui.tags.thead(ui.tags.tr(*header_cells))


def build_status_badge(status: str, status_labels: dict = None) -> ui.tags.span:
    """Build a status badge element."""
    if status_labels:
        status_text = status_labels.get(status, status.capitalize())
    else:
        status_text = {
            "edited": "Edited",
            "approved": "Approved",
            "rejected": "Rejected",
            "unprocessed": "New"
        }.get(status, status)
    return ui.tags.span(status_text, class_=f"row-status-badge status-{status}")


def build_table_row(idx: int, row: pd.Series, cols: list, current_df: pd.DataFrame, get_row_status_func: Callable[[int], str], row_class: str = "", edited_cells: dict = None, pk_columns: list = None, editable_columns: list = None, readonly_columns: list = None, show_status_column: bool = True, status_labels: dict = None, cell_click_columns: list = None) -> ui.tags.tr:
    """Build a single table row with all cells."""
    cells = []
    edited_cells = edited_cells or {}
    pk_columns = pk_columns or []
    editable_columns = editable_columns or []
    readonly_columns = readonly_columns or []
    cell_click_columns = cell_click_columns or []
    
    # Build PK tuple for this row (for looking up edited cells)
    row_pk = {pk: row[pk] for pk in pk_columns if pk in row.index}
    pk_tuple = tuple(sorted((k, str(v)) for k, v in row_pk.items()))
    
    # Select checkbox
    cells.append(
        ui.tags.td(
            ui.input_checkbox(f"select_{idx}", label="", value=False, width="30px"),
            style="text-align: center; width: 10px;",
        )
    )
    
    # Row number
    cells.append(ui.tags.td(str(idx + 1), class_="row-number"))
    
    # Status badge (only if approval workflow is enabled)
    if show_status_column:
        current_status = get_row_status_func(idx)
        cells.append(
            ui.tags.td(
                build_status_badge(current_status, status_labels),
                style="text-align: center; font-size: 12px;"
            )
        )
    
    # Data cells
    for col in cols:
        if col in current_df.columns:
            value = str(row[col]) if pd.notna(row[col]) else ""
        else:
            value = ""
        
        # Check if this cell has been edited (using PK-based key)
        cell_key = (pk_tuple, col)
        cell_info = edited_cells.get(cell_key)
        is_edited = cell_info is not None
        
        # Determine if column is editable
        # If editable_columns is specified, only those columns are editable
        # If readonly_columns is specified, those columns are NOT editable
        # Empty editable_columns means all columns are editable (unless in readonly_columns)
        if editable_columns:
            is_col_editable = col in editable_columns and col not in readonly_columns
        else:
            is_col_editable = col not in readonly_columns
        
        if is_col_editable:
            cell_class = "editable-cell cell-edited" if is_edited else "editable-cell"
        else:
            cell_class = "readonly-cell cell-edited" if is_edited else "readonly-cell"
        
        # Build cell attributes
        cell_attrs = {"data-row": str(idx), "data-col": col, "data-value": value}
        
        # Add original value attribute if cell was edited
        if is_edited and isinstance(cell_info, dict):
            original = cell_info.get("original", "")
            cell_attrs["data-original"] = str(original) if original is not None else ""
        
        # Clickable cell — emits cell_click event
        is_clickable = col in cell_click_columns
        if is_clickable:
            cell_class += " clickable-cell"
            # Embed PK values as JSON for the JS handler
            import json as _json
            cell_attrs["data-pk"] = _json.dumps({k: str(v) for k, v in row_pk.items()})
        
        cells.append(
            ui.tags.td(
                ui.span(value if value else "—", class_="cell-value"),
                class_=cell_class,
                **cell_attrs
            )
        )
    
    return ui.tags.tr(*cells, class_=row_class)


def build_table_body(paginated_indices: list, current_df: pd.DataFrame, cols: list, get_row_status_func: Callable[[int], str], edited_cells: dict = None, pk_columns: list = None, editable_columns: list = None, readonly_columns: list = None, show_status_column: bool = True, status_labels: dict = None, cell_click_columns: list = None) -> ui.tags.tbody:
    """Build the table body with all rows."""
    table_rows = []
    edited_cells = edited_cells or {}
    pk_columns = pk_columns or []
    for i, idx in enumerate(paginated_indices):
        # idx is the DataFrame index (label), use .loc to get the row
        row = current_df.loc[idx]
        # Add zebra striping class based on visual position
        row_class = "row-even" if i % 2 == 0 else "row-odd"
        table_rows.append(build_table_row(idx, row, cols, current_df, get_row_status_func, row_class, edited_cells, pk_columns, editable_columns, readonly_columns, show_status_column, status_labels, cell_click_columns=cell_click_columns))
    return ui.tags.tbody(*table_rows)


def build_data_table(paginated_indices: list, current_df: pd.DataFrame, cols: list, widths: dict, get_row_status_func: Callable[[int], str], edited_cells: dict = None, pk_columns: list = None, editable_columns: list = None, readonly_columns: list = None, show_status_column: bool = True, status_labels: dict = None, column_masks: dict | None = None, cell_click_columns: list = None) -> ui.tags.table:
    """Build the complete data table."""
    header = build_table_header(cols, widths, show_status_column=show_status_column, column_masks=column_masks)
    body = build_table_body(paginated_indices, current_df, cols, get_row_status_func, edited_cells, pk_columns, editable_columns, readonly_columns, show_status_column, status_labels, cell_click_columns=cell_click_columns)
    return ui.tags.table(header, body, class_="edit-table")


def build_table_container(
    paginated_indices: list,
    current_df: pd.DataFrame,
    cols: list,
    widths: dict,
    filtered_count: int,
    total_rows: int,
    get_row_status_func: Callable[[int], str],
    edited_cells: dict = None,
    pk_columns: list = None,
    editable_columns: list = None,
    readonly_columns: list = None,
    show_status_column: bool = True,
    status_labels: dict = None,
    column_masks: dict | None = None,
    cell_click_columns: list = None
) -> ui.div:
    """Build the complete table container with summary and table."""
    displayed_count = len(paginated_indices)
    
    if filtered_count < total_rows:
        rows_text = f"Loaded {displayed_count} rows (filtered {filtered_count} of {total_rows} total)"
    else:
        rows_text = f"Loaded {displayed_count} of {filtered_count} rows"
    
    table_html = build_data_table(paginated_indices, current_df, cols, widths, get_row_status_func, edited_cells, pk_columns, editable_columns, readonly_columns, show_status_column, status_labels, column_masks=column_masks, cell_click_columns=cell_click_columns)
    
    return ui.div(
        ui.div(rows_text, style="margin-bottom: 10px; color: #666; font-size: 12px;"),
        table_html,
    )
