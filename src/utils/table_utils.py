"""
Table rendering utilities for the Epitopes Data Editor.
These functions help build the data table UI components.
"""

import pandas as pd
from shiny import ui
from typing import Callable, Any
from .data_utils import get_row_status


def build_draggable_header_cell(col: str, width_style: str = "") -> ui.tags.th:
    """Build a draggable table header cell with action dropdown."""
    return ui.tags.th(
        ui.tags.span(col, class_="header-text"),
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


def build_table_header(cols: list, widths: dict, default_width: int = 130) -> ui.tags.thead:
    """Build the complete table header."""
    header_cells = [
        ui.tags.th("", style="width: 40px; text-align: center;"),
        ui.tags.th("Row", style="width: 50px;"),
        ui.tags.th("Mod", style="width: 70px;", title="Modification Status"),
    ]
    
    for col in cols:
        col_width = widths.get(col, default_width)
        width_style = f"width: {col_width}px; min-width: {col_width}px;"
        header_cells.append(build_draggable_header_cell(col, width_style))
    
    return ui.tags.thead(ui.tags.tr(*header_cells))


def build_status_badge(status: str) -> ui.tags.span:
    """Build a status badge element."""
    status_text = {
        "edited": "Edited",
        "approved": "Approved",
        "rejected": "Rejected",
        "unprocessed": "New"
    }.get(status, status)
    return ui.tags.span(status_text, class_=f"row-status-badge status-{status}")


def build_table_row(idx: int, row: pd.Series, cols: list, current_df: pd.DataFrame, get_row_status_func: Callable[[int], str]) -> ui.tags.tr:
    """Build a single table row with all cells."""
    cells = []
    
    # Select checkbox
    cells.append(
        ui.tags.td(
            ui.input_checkbox(f"select_{idx}", label="", value=False, width="30px"),
            style="text-align: center; width: 10px;",
        )
    )
    
    # Row number
    cells.append(ui.tags.td(str(idx + 1), class_="row-number"))
    
    # Status badge
    current_status = get_row_status_func(idx)
    cells.append(
        ui.tags.td(
            build_status_badge(current_status),
            style="text-align: center; font-size: 12px;"
        )
    )
    
    # Data cells
    for col in cols:
        if col in current_df.columns:
            value = str(row[col]) if pd.notna(row[col]) else ""
        else:
            value = ""
        cells.append(
            ui.tags.td(
                ui.span(value if value else "—", class_="cell-value"),
                class_="editable-cell",
                **{"data-row": str(idx), "data-col": col, "data-value": value}
            )
        )
    
    return ui.tags.tr(*cells)


def build_table_body(paginated_indices: list, current_df: pd.DataFrame, cols: list, get_row_status_func: Callable[[int], str]) -> ui.tags.tbody:
    """Build the table body with all rows."""
    table_rows = []
    for idx in paginated_indices:
        row = current_df.iloc[idx]
        table_rows.append(build_table_row(idx, row, cols, current_df, get_row_status_func))
    return ui.tags.tbody(*table_rows)


def build_data_table(paginated_indices: list, current_df: pd.DataFrame, cols: list, widths: dict, get_row_status_func: Callable[[int], str]) -> ui.tags.table:
    """Build the complete data table."""
    header = build_table_header(cols, widths)
    body = build_table_body(paginated_indices, current_df, cols, get_row_status_func)
    return ui.tags.table(header, body, class_="edit-table")


def build_table_container(
    paginated_indices: list,
    current_df: pd.DataFrame,
    cols: list,
    widths: dict,
    filtered_count: int,
    total_rows: int,
    get_row_status_func: Callable[[int], str]
) -> ui.div:
    """Build the complete table container with summary and table."""
    displayed_count = len(paginated_indices)
    
    if filtered_count < total_rows:
        rows_text = f"Loaded {displayed_count} rows (filtered {filtered_count} of {total_rows} total)"
    else:
        rows_text = f"Loaded {displayed_count} of {filtered_count} rows"
    
    table_html = build_data_table(paginated_indices, current_df, cols, widths, get_row_status_func)
    
    return ui.div(
        ui.div(rows_text, style="margin-bottom: 10px; color: #666; font-size: 12px;"),
        table_html,
    )
