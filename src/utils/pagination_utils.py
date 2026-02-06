"""
Pagination UI builders for the Epitopes Data Editor.
"""

from shiny import ui


def build_rows_per_page_selector(selected_value: str) -> ui.div:
    """Build the rows per page selector control."""
    return ui.div(
        ui.tags.label("Rows: ", style="font-size: 11px; margin-right: 4px;"),
        ui.input_select(
            "rows_per_page",
            label=None,
            choices={
                "10": "10",
                "25": "25",
                "50": "50",
                "100": "100",
                "all": "All"
            },
            selected=selected_value,
            width="70px"
        ),
        class_="rows-per-page-control"
    )


def build_pagination_controls_all(total_rows: int, rows_per_page_val: str) -> ui.div:
    """Build pagination controls when showing all rows."""
    return ui.div(
        build_rows_per_page_selector(rows_per_page_val),
        ui.span(f"Showing all {total_rows} rows", class_="pagination-info"),
        class_="pagination-bar"
    )


def build_pagination_controls_paged(
    page: int,
    total_pages: int,
    start_row: int,
    end_row: int,
    total_rows: int,
    rows_per_page_val: str
) -> ui.div:
    """Build pagination controls with page navigation."""
    return ui.div(
        build_rows_per_page_selector(rows_per_page_val),
        ui.span(f"Showing {start_row}-{end_row} of {total_rows} rows", class_="pagination-info"),
        ui.div(
            ui.input_action_button("first_page_btn", "« First", class_="btn btn-sm btn-outline-secondary", disabled=(page <= 1)),
            ui.input_action_button("prev_page_btn", "‹ Prev", class_="btn btn-sm btn-outline-secondary", disabled=(page <= 1)),
            ui.span(f"Page {page} of {total_pages}", class_="page-indicator"),
            ui.input_action_button("next_page_btn", "Next ›", class_="btn btn-sm btn-outline-secondary", disabled=(page >= total_pages)),
            ui.input_action_button("last_page_btn", "Last »", class_="btn btn-sm btn-outline-secondary", disabled=(page >= total_pages)),
            class_="pagination-buttons"
        ),
        ui.div(
            ui.span("Go to: "),
            ui.input_numeric("page_jump_input", label=None, value=page, min=1, max=total_pages, width="60px"),
            ui.input_action_button("page_jump_btn", "Go", class_="btn btn-sm btn-primary"),
            class_="page-jump"
        ),
        class_="pagination-bar"
    )
