"""
Utility modules for Epitopes Data Editor PyShiny App
"""

from .preset_utils import load_presets, save_presets, load_active_preset, save_active_preset
from .data_utils import (
    get_latest_approval_status,
    get_row_status,
    get_row_modifications,
    get_status_counts,
    get_modification_summary,
)
from .filter_utils import get_filtered_rows
from .ui_components import (
    build_log_entry_undo,
    build_log_entry_approval,
    build_log_entry_rejection,
    build_log_entry_undone,
    build_log_entry_field_modification,
    build_status_histogram_bar,
    build_empty_log_message,
    build_approval_status_banner,
    build_modifications_log,
    build_facet_panels,
)
from .table_utils import (
    build_table_container,
    build_table_header,
    build_table_body,
    build_data_table,
)
from .modal_utils import (
    build_columns_modal_content,
    build_preset_menu_items,
    build_copy_column_buttons,
    build_filter_column_buttons,
    build_dynamic_filters_panel,
)
from .pagination_utils import (
    build_pagination_controls_all,
    build_pagination_controls_paged,
)
from .column_utils import (
    parse_column_value,
    parse_column_order,
    add_column_to_list,
    remove_column_from_list,
    sort_dataframe,
    get_preset_columns_and_widths,
    create_preset_data,
    get_ordered_columns,
)
from .data_operations import (
    perform_undo,
    perform_cell_edit,
    save_modifications_to_file,
    save_log_to_file,
    export_csv,
    export_status_report,
    create_approval_entry,
    create_rejection_entry,
    get_selected_row_indices,
    get_copy_column_values,
    get_paginated_indices,
    calculate_pagination,
)
from .filter_handlers import (
    parse_filter_column,
    add_filter,
    remove_filter,
    update_filter_values,
)
from .clipboard_utils import (
    generate_clipboard_js,
    process_copy_request,
)
from .event_handlers import (
    process_approval_action,
    process_rejection_action,
    process_undo_action,
    process_cell_edit_action,
)
from . import tracker

__all__ = [
    # Preset utilities
    "load_presets",
    "save_presets",
    "load_active_preset",
    "save_active_preset",
    # Data utilities
    "get_latest_approval_status",
    "get_row_status",
    "get_row_modifications",
    "get_status_counts",
    "get_modification_summary",
    # Filter utilities
    "get_filtered_rows",
    # UI components
    "build_log_entry_undo",
    "build_log_entry_approval",
    "build_log_entry_rejection",
    "build_log_entry_undone",
    "build_log_entry_field_modification",
    "build_status_histogram_bar",
    "build_empty_log_message",
    "build_approval_status_banner",
    "build_modifications_log",
    "build_facet_panels",
    # Table utilities
    "build_table_container",
    "build_table_header",
    "build_table_body",
    "build_data_table",
    # Modal utilities
    "build_columns_modal_content",
    "build_preset_menu_items",
    "build_copy_column_buttons",
    "build_filter_column_buttons",
    "build_dynamic_filters_panel",
    # Pagination utilities
    "build_pagination_controls_all",
    "build_pagination_controls_paged",
    # Column utilities
    "parse_column_value",
    "parse_column_order",
    "add_column_to_list",
    "remove_column_from_list",
    "sort_dataframe",
    "get_preset_columns_and_widths",
    "create_preset_data",
    "get_ordered_columns",
    # Data operations
    "perform_undo",
    "perform_cell_edit",
    "save_modifications_to_file",
    "save_log_to_file",
    "export_csv",
    "export_status_report",
    "create_approval_entry",
    "create_rejection_entry",
    "get_selected_row_indices",
    "get_copy_column_values",
    "get_paginated_indices",
    "calculate_pagination",
    # Filter handlers
    "parse_filter_column",
    "add_filter",
    "remove_filter",
    "update_filter_values",
    # Clipboard utilities
    "generate_clipboard_js",
    "process_copy_request",
    # Event handlers
    "process_approval_action",
    "process_rejection_action",
    "process_undo_action",
    "process_cell_edit_action",
]
