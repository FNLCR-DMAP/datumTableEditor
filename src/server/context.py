"""
ServerContext — shared state container passed to all server sub-modules.

Each register_*() function receives this context to access reactive values,
config, and helper functions without relying on closure capture.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, List


@dataclass
class ServerContext:
    """Shared state for all server sub-modules.

    All fields are set during create_server() setup and passed to register_*()
    functions. Reactive values are Shiny reactive.Value instances.
    """

    # ── Shiny session primitives ────────────────────────────────────────
    input: Any = None
    output: Any = None
    session: Any = None

    # ── Config ──────────────────────────────────────────────────────────
    config: Any = None                  # ConfigInstance
    app_config: Any = None              # AppConfig
    safe_username: str = ""
    user_email: str = ""
    is_viewer: bool = False
    display_columns: List[str] = field(default_factory=list)
    all_columns: List[str] = field(default_factory=list)
    column_masks: Any = None
    data_dir: Any = None                # Path
    modifications_log_path: Any = None  # Path

    # ── Reactive values ─────────────────────────────────────────────────
    data: Any = None                    # reactive.Value[DataFrame]
    total_rows: Any = None              # reactive.Value[int]
    filtered_row_count: Any = None      # reactive.Value[int]
    edited_cells: Any = None            # reactive.Value[dict]
    current_sort: Any = None            # reactive.Value[dict]
    mods_log: Any = None                # reactive.Value[list]
    approval_status: Any = None         # reactive.Value
    approval_timestamp: Any = None      # reactive.Value
    column_presets: Any = None          # reactive.Value[dict]
    active_preset: Any = None           # reactive.Value[str]
    active_columns: Any = None          # reactive.Value[list]
    column_widths: Any = None           # reactive.Value[dict]
    current_page: Any = None            # reactive.Value[int]
    rows_per_page_value: Any = None     # reactive.Value[str]
    active_filters: Any = None          # reactive.Value[dict]
    pending_filters: Any = None         # reactive.Value[dict]
    search_state: Any = None            # reactive.Value[dict]
    _filter_panel_trigger: Any = None   # reactive.Value[int]
    _columns_layout_trigger: Any = None # reactive.Value[int]
    _table_reload_trigger: Any = None   # reactive.Value[int]

    # Synthesis
    synthesis_active: Any = None
    synthesis_running: Any = None
    synthesis_data: Any = None
    synthesis_error: Any = None
    synthesis_cached: Any = None
    enable_synthesis: bool = False

    # Export
    export_state: Any = None
    export_csv_data: Any = None
    export_row_count: Any = None
    export_type: Any = None

    # ── Helper functions (closures from core) ───────────────────────────
    is_lazy_loading: Callable = None
    load_modifications_log: Callable = None
    load_data_from_source: Callable = None
    save_ui_state: Callable = None
    _require_editor: Callable = None
    _get_row_status: Callable = None
    _get_status_counts: Callable = None
    _get_modification_summary: Callable = None
    _get_filtered_rows: Callable = None
    _build_query_params: Callable = None
    _lazy_filtered_count: Callable = None
    _fetch_page_data: Callable = None
    _fetch_all_filtered_data: Callable = None
    _cached_page_data: Callable = None
    _get_page_selection: Callable = None
    _get_selected_pks: Callable = None
    _save_status_to_db: Callable = None
    _save_presets: Callable = None
    _save_active_preset: Callable = None
    _emit: Callable = None

    # ── Flags ───────────────────────────────────────────────────────────
    _initial_lazy_loading: bool = False
    _synthesis_needs_generate: bool = False
    _synthesis_autoloaded: bool = False
    _first_rows_per_page_sync: Any = None   # {"done": bool}
    _first_search_filter_sync: Any = None   # {"done": bool}

    def validate_ns(self, input_name: str) -> str:
        """Return the fully namespace-qualified input name and log a warning
        if the raw name doesn't match the session namespace.

        Usage in handlers where you receive a raw JS input name::

            qualified = ctx.validate_ns("fetch_filter_values")
        """
        if self.session is None:
            return input_name
        expected_prefix = self.session.ns("_x_").replace("_x_", "")
        if expected_prefix and not input_name.startswith(expected_prefix):
            print(f"[NS-WARNING] Input '{input_name}' missing namespace prefix '{expected_prefix}'")
        return expected_prefix + input_name if expected_prefix and not input_name.startswith(expected_prefix) else input_name
