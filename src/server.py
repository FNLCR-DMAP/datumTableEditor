"""
Server Logic for Epitopes Data Editor PyShiny App
Updated for split panel layout with column customization
"""

from shiny import render, ui, reactive

from .utils import (
    load_presets,
    save_presets,
    load_active_preset,
    save_active_preset,
    get_latest_approval_status,
    get_row_status,
    get_status_counts,
    get_modification_summary,
    get_filtered_rows,
    # UI components
    build_status_histogram_bar,
    build_approval_status_banner,
    build_modifications_log,
    # Table utilities
    build_table_container,
    # Modal utilities
    build_columns_modal_content,
    build_preset_menu_items,
    build_copy_column_buttons,
    build_filter_column_buttons,
    build_dynamic_filters_panel,
    # Pagination utilities
    build_pagination_controls_all,
    build_pagination_controls_paged,
    # Column utilities
    parse_column_value,
    parse_column_order,
    add_column_to_list,
    remove_column_from_list,
    sort_dataframe,
    get_preset_columns_and_widths,
    create_preset_data,
    get_ordered_columns,
    # Data operations
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
    # Filter handlers
    parse_filter_column,
    add_filter,
    remove_filter,
    update_filter_values,
    # Clipboard utilities
    process_copy_request,
    # Event handlers
    process_approval_action,
    process_rejection_action,
    process_undo_action,
    process_cell_edit_action,
)


def create_server(input, output, session, config_path: str = "app_config.json"):  # noqa: ARG001
    """
    Server logic for the Shiny app
    
    Args:
        config_path: Path to the config JSON file for this widget instance
    """
    import os
    # Get username: Posit Connect session.user → SHINY_USER env var → 'default_user'
    posit_username = getattr(session, 'user', None) or os.environ.get('SHINY_USER') or 'default_user'
    # Sanitize username for use in table names
    safe_username = "".join(c if c.isalnum() else "_" for c in posit_username).lower()
    print(f"[Session] User: {posit_username} (safe: {safe_username})")
    
    # Load config instance for this widget, passing the username for user-scoped tables
    from .config.config_instance import load_config_instance
    print(f"[Config] Loading config from {config_path} for user: {safe_username}")
    config = load_config_instance(config_path, username=safe_username)
    
    # Extract config values
    data_dir = config.data_dir
    modifications_log_path = config.modifications_log_path
    df_original = config.df
    display_columns = config.display_columns
    all_columns = config.all_columns
    app_config = config.app_config
    
    # Create local functions that use this config instance
    def load_modifications_log():
        return config.load_modifications_log()
    
    def load_data_from_source():
        return config.reload_data()
    
    def save_ui_state(**kwargs):
        """Save UI state for this instance."""
        return config.save_ui_state(**kwargs)
    
    def load_ui_state():
        """Load UI state for this instance."""
        return config.load_ui_state()
    
    # File paths for presets
    presets_file = data_dir / "column_presets.json"
    active_preset_file = data_dir / "active_preset.json"
    
    # Get table name for scoping presets (for multi-widget support)
    # Use mods_table as it's unique per widget instance (e.g., epitopes.modifications vs epitopes.modifications_clone)
    preset_table_name = app_config.database.mods_table.replace('.', '_').replace('-', '_')
    
    # Load UI state (sort, filters, page) from database
    ui_state = load_ui_state()
    
    # Load fresh data from source (database) on each session
    # This ensures browser refresh gets the latest data
    initial_df = load_data_from_source() if app_config.database.enabled else df_original.copy()
    
    # Apply initial sorting if saved
    if ui_state.get("sort_column"):
        initial_df = sort_dataframe(
            initial_df, 
            ui_state["sort_column"], 
            "asc" if ui_state.get("sort_ascending", True) else "desc"
        )
    
    # Reactive values
    data = reactive.Value(initial_df)
    
    # Track edited cells from config - {(row_idx, col_name): new_value}
    edited_cells = reactive.Value(config.get_edited_cells())
    
    current_sort = reactive.Value({
        "column": ui_state.get("sort_column"),
        "ascending": ui_state.get("sort_ascending", True)
    })
    mods_log = reactive.Value(load_modifications_log())
    
    # Load initial approval status from log
    initial_status, initial_timestamp = get_latest_approval_status(load_modifications_log())
    approval_status = reactive.Value(initial_status)
    approval_timestamp = reactive.Value(initial_timestamp)
    
    # Load presets (scoped by preset_table_name and username)
    print(f"[Preset] Loading presets for scope: {preset_table_name}, user: {safe_username}")
    loaded_presets = load_presets(presets_file, display_columns, preset_table_name, safe_username)
    column_presets = reactive.Value(loaded_presets)
    
    # Load last active preset (persists across refreshes)
    initial_active_preset = load_active_preset(active_preset_file, preset_table_name, safe_username)
    print(f"[Preset] Active preset for {preset_table_name}/{safe_username}: {initial_active_preset}")
    # Ensure the preset exists, fallback to Default if not
    if initial_active_preset not in loaded_presets:
        initial_active_preset = "Default"
    active_preset = reactive.Value(initial_active_preset)
    
    # Initialize active_columns from the saved active preset (not just Default)
    saved_preset = loaded_presets.get(initial_active_preset, loaded_presets.get("Default", {"columns": list(display_columns), "widths": {}}))
    initial_columns = saved_preset.get("columns", list(display_columns)) if isinstance(saved_preset, dict) else list(saved_preset)
    initial_widths = saved_preset.get("widths", {}) if isinstance(saved_preset, dict) else {}
    
    # Column customization - track which columns to display and their order
    active_columns = reactive.Value(list(initial_columns))
    
    # Column widths storage
    column_widths = reactive.Value(dict(initial_widths))
    
    # Pagination state - load from saved UI state
    initial_page = ui_state.get("current_page", 1)
    initial_rows_per_page = str(ui_state.get("rows_per_page", 25))
    current_page = reactive.Value(initial_page)
    rows_per_page_value = reactive.Value(initial_rows_per_page)
    
    # Track first sync to avoid resetting page on initial load
    _first_rows_per_page_sync = {"done": False}
    _first_filter_sync = {"done": False}
    _first_search_filter_sync = {"done": False}
    
    # Initialize default filters from config
    # Config format: {column: [values]} or {column: "value"}
    # Internal format: {column: "value1\nvalue2\n..."} (newline-delimited string)
    def _convert_default_filters(config_filters: dict) -> dict:
        """Convert config default_filters to internal format."""
        result = {}
        for col, values in config_filters.items():
            if isinstance(values, list):
                # List of values -> newline-delimited string
                result[col] = "\n".join(str(v) for v in values)
            else:
                # Single value -> string
                result[col] = str(values) if values else ""
        return result
    
    initial_filters = _convert_default_filters(app_config.query.default_filters) if hasattr(app_config, 'query') and app_config.query.default_filters else {}
    
    # Dynamic column filters - stores active filters as {column_name: "value1\nvalue2\n..."}
    active_filters = reactive.Value(initial_filters)
    
    # Search state - updated only when search button is clicked
    search_state = reactive.Value({"term": "", "column": "all"})
    
    # Helper function to get PKs for selected row indices
    def _get_selected_pks(row_indices, current_df):
        """Convert row indices (DataFrame labels) to list of PK dicts"""
        pk_cols = app_config.table.primary_key
        pks = []
        for row_idx in row_indices:
            try:
                row = current_df.loc[row_idx]  # Use .loc for label-based indexing
                row_pk = {pk: row[pk] for pk in pk_cols if pk in current_df.columns}
                if row_pk:
                    pks.append(row_pk)
            except Exception as e:
                print(f"Warning: Could not get PK for row {row_idx}: {e}")
        return pks
    
    # Helper function to save approval/rejection status to database
    def _save_status_to_db(selected_pks, mod_type: str):
        """Save approval/rejection entries to database with PKs using config instance"""
        for row_pk in selected_pks:
            try:
                result = config.save_modification_to_db(
                    row_pk=row_pk,
                    column="_status",
                    old_value=None,
                    new_value=mod_type,
                    mod_type=mod_type
                )
                print(f"DEBUG: Saved {mod_type} for PK {row_pk}, result: {result}")
            except Exception as e:
                print(f"Warning: Could not save {mod_type} for PK {row_pk}: {e}")
    
    # Helper functions that wrap utilities with reactive values
    def _get_row_status(row_idx):
        """Wrapper for get_row_status that uses reactive log and PK for accurate matching"""
        current_df = data.get()
        current_log = mods_log.get()
        # Get the primary key for this row (using DataFrame index label, not position)
        try:
            pk_cols = app_config.table.primary_key
            row = current_df.loc[row_idx]  # Use .loc for label-based indexing
            row_pk = {pk: row[pk] for pk in pk_cols if pk in current_df.columns}
        except:
            row_pk = None
        return get_row_status(row_idx, current_log, row_pk)
    
    def _get_status_counts():
        """Wrapper for get_status_counts that uses reactive values"""
        pk_cols = app_config.table.primary_key if hasattr(app_config.table, 'primary_key') else None
        return get_status_counts(data.get(), mods_log.get(), pk_cols)
    
    def _get_modification_summary():
        """Wrapper for get_modification_summary that uses reactive values"""
        pk_cols = app_config.table.primary_key if hasattr(app_config.table, 'primary_key') else None
        return get_modification_summary(data.get(), mods_log.get(), pk_cols)
    
    def _get_filtered_rows():
        """Get filtered rows based on search, status filter, and dynamic column filters"""
        current_df = data.get()
        search = search_state.get()
        search_term = search.get("term", "")
        search_column = search.get("column", "all")
        
        # Get multi-select status filter
        try:
            status_filters = list(input.status_filter_multi())
        except:
            status_filters = ["unprocessed", "edited", "approved", "rejected"]
        
        return get_filtered_rows(
            df=current_df,
            active_columns=active_columns.get(),
            search_term=search_term,
            status_filters=status_filters,
            column_filters=active_filters.get(),
            get_row_status_func=_get_row_status,
            search_column=search_column
        )

    # Wrapper functions for preset utilities (using file paths and username from this scope)
    def _save_presets(presets_dict):
        save_presets(presets_file, presets_dict, preset_table_name, safe_username)
    
    def _save_active_preset(preset_name):
        save_active_preset(active_preset_file, preset_name, preset_table_name, safe_username)

    # Output: Namespace holder for JavaScript
    @render.ui
    def _namespace_holder():
        # Get namespace by calling session.ns with a test ID and extracting the prefix
        # session.ns("test") returns "editor1-test", so we remove "test" to get "editor1-"
        ns_prefix = session.ns("test").replace("test", "")
        from shiny import ui as sui
        return sui.div(
            style="display:none;",
            **{"data-shiny-ns": ns_prefix}
        )

    # Output: Data summary text
    @render.text
    def data_summary():
        df = data.get()
        return f"{len(df)} rows x {len(df.columns)} columns"
    
    # Output: Stats histogram
    @render.ui
    def stats_histogram():
        # Explicit dependency on mods_log for reactivity
        _ = mods_log.get()
        counts = _get_status_counts()
        total = sum(counts.values()) or 1
        
        # Get current filter selections
        try:
            selected = list(input.status_filter_multi())
        except:
            selected = ["unprocessed", "edited", "approved", "rejected"]
        
        bars = []
        for status, count in counts.items():
            pct = (count / total) * 100
            is_checked = status in selected
            bars.append(build_status_histogram_bar(status, count, pct, is_checked))
        return ui.div(*bars)
    
    # Output: Current preset name
    @render.text
    def current_preset_name():
        return active_preset.get()
    
    # Event: Refresh presets - reload from file and update reactive values
    @reactive.Effect
    @reactive.event(input.refresh_preset)
    def _refresh_presets():
        """Reload presets from file when triggered"""
        fresh_presets = load_presets(presets_file, display_columns, preset_table_name, safe_username)
        column_presets.set(fresh_presets)
        
        # Also refresh active_columns based on current preset
        current = active_preset.get()
        if current in fresh_presets:
            preset_data = fresh_presets[current]
            if isinstance(preset_data, dict):
                active_columns.set(list(preset_data.get("columns", display_columns)))
                column_widths.set(dict(preset_data.get("widths", {})))
    
    # Output: Preset menu items
    @render.ui
    def preset_menu_items():
        presets = column_presets.get()
        current = active_preset.get()
        
        if not presets:
            presets = {"Default": {"columns": list(display_columns), "widths": {}}}
        
        return build_preset_menu_items(presets, current)
    
    # Output: Available columns for modal
    @render.ui
    def available_columns_modal():
        cols = list(active_columns.get()) or list(display_columns)
        available = [c for c in all_columns if c not in cols]
        return build_columns_modal_content(cols, available)
    
    # Handle column order changes from JS
    @reactive.Effect
    @reactive.event(input.column_order)
    def _update_column_order():
        new_order = parse_column_order(input.column_order())
        if new_order:
            active_columns.set(list(new_order))
    
    # Handle adding a column
    @reactive.Effect
    @reactive.event(input.add_column)
    def _add_column():
        col = parse_column_value(input.add_column())
        if col:
            active_columns.set(add_column_to_list(active_columns.get(), col))
    
    # Handle removing a column
    @reactive.Effect
    @reactive.event(input.remove_column)
    def _remove_column():
        col = parse_column_value(input.remove_column())
        if col:
            active_columns.set(remove_column_from_list(active_columns.get(), col))
    
    # Handle sorting a column
    @reactive.Effect
    @reactive.event(input.sort_column)
    def _sort_column():
        val = input.sort_column()
        if val and val.get('col'):
            col = val.get('col')
            direction = val.get('direction', 'asc')
            ascending = (direction == 'asc')
            data.set(sort_dataframe(data.get(), col, direction))
            current_sort.set({"column": col, "ascending": ascending})
            # Reset to first page when sorting
            current_page.set(1)
            # Persist sort state to database
            save_ui_state(
                sort_column=col,
                sort_ascending=ascending,
                current_page=1,
                rows_per_page=int(rows_per_page_value.get()),
                column_preset=active_preset.get()
            )
    
    # Reset columns (from JS)
    @reactive.Effect
    @reactive.event(input.reset_columns)
    def _reset_columns():
        active_columns.set(list(display_columns))
        column_widths.set({})
        active_preset.set("Default")
        _save_active_preset("Default")
    
    # Handle column widths from JS
    @reactive.Effect
    @reactive.event(input.column_widths)
    def _update_column_widths():
        widths = input.column_widths()
        if widths and isinstance(widths, dict):
            column_widths.set(widths)
    
    # Handle loading a preset
    @reactive.Effect
    @reactive.event(input.load_preset)
    def _load_preset():
        preset_name = input.load_preset()
        if preset_name and preset_name in column_presets.get():
            cols, widths = get_preset_columns_and_widths(column_presets.get()[preset_name], display_columns)
            active_columns.set(cols)
            column_widths.set(widths)
            active_preset.set(preset_name)
            _save_active_preset(preset_name)
            # Also save preset to UI state
            sort_state = current_sort.get()
            save_ui_state(
                sort_column=sort_state.get("column"),
                sort_ascending=sort_state.get("ascending", True),
                current_page=current_page.get(),
                rows_per_page=int(rows_per_page_value.get()),
                column_preset=preset_name
            )
    
    # Handle saving a new preset (from JS)
    @reactive.Effect
    @reactive.event(input.save_preset_name)
    def _save_preset():
        name = input.save_preset_name()
        if name and name.strip():
            name = name.strip()
            presets = column_presets.get().copy()
            presets[name] = create_preset_data(active_columns.get(), column_widths.get())
            column_presets.set(presets)
            _save_presets(presets)
            active_preset.set(name)
            _save_active_preset(name)
            ui.notification_show(f"Preset '{name}' saved!", type="message", duration=2)
    
    # Handle saving current layout to current preset (not Default)
    @reactive.Effect
    @reactive.event(input.save_current_layout)
    def _save_current_layout():
        current = active_preset.get()
        if current == "Default":
            ui.notification_show("Cannot overwrite Default preset. Use 'Save' in preset menu to create a new one.", type="warning", duration=3)
            return
        presets = column_presets.get().copy()
        presets[current] = create_preset_data(active_columns.get(), column_widths.get())
        column_presets.set(presets)
        _save_presets(presets)
        ui.notification_show(f"Layout saved to '{current}'!", type="message", duration=2)
    
    # Handle deleting a preset
    @reactive.Effect
    @reactive.event(input.delete_preset)
    def _delete_preset():
        name = input.delete_preset()
        if name and name != "Default":
            presets = column_presets.get().copy()
            if name in presets:
                del presets[name]
                column_presets.set(presets)
                _save_presets(presets)
                if active_preset.get() == name:
                    active_preset.set("Default")
                    _save_active_preset("Default")
                    cols, widths = get_preset_columns_and_widths(
                        presets.get("Default", {"columns": list(display_columns), "widths": {}}),
                        display_columns
                    )
                    active_columns.set(cols)
                    column_widths.set(widths)
                ui.notification_show(f"Preset '{name}' deleted!", type="message", duration=2)
    
    # Output: Copy column list for copy modal
    @render.ui
    def copy_column_list():
        """Render list of columns available to copy"""
        preset_cols = list(active_columns.get()) or list(display_columns)
        ordered_cols = get_ordered_columns(preset_cols, list(data.get().columns))
        return build_copy_column_buttons(ordered_cols)

    # Handle copy column request from JS
    @reactive.Effect
    @reactive.event(input.copy_column_request)
    def _handle_copy_request():
        js_code, col_name, count, error = process_copy_request(
            input.copy_column_request(),
            data.get(),
            _get_filtered_rows(),
            rows_per_page_value.get(),
            current_page.get(),
            get_paginated_indices,
            get_copy_column_values
        )
        if error:
            ui.notification_show(error, type="warning" if "select" in error else "error", duration=2)
        elif js_code:
            ui.insert_ui(ui.tags.script(js_code), selector="body", where="beforeEnd")
            ui.notification_show(f"Copied {count} values from '{col_name}' to clipboard!", type="message", duration=2)
    
    # Output: Dynamic filters UI
    @render.ui
    def dynamic_filters():
        """Render active dynamic filters"""
        return build_dynamic_filters_panel(active_filters.get(), data.get())
    
    # Output: Available columns for filter modal
    @render.ui
    def available_filter_columns():
        """Render list of columns that can be added as filters"""
        df = data.get()
        filters = active_filters.get()
        available_cols = [col for col in df.columns if col not in filters]
        return build_filter_column_buttons(available_cols)
    
    # Handle adding a filter
    @reactive.Effect
    @reactive.event(input.add_filter_column)
    def _add_filter():
        col_name = parse_filter_column(input.add_filter_column())
        if col_name:
            active_filters.set(add_filter(active_filters.get(), col_name))
    
    # Handle removing a filter
    @reactive.Effect
    @reactive.event(input.remove_filter_column)
    def _remove_filter():
        col_name = parse_filter_column(input.remove_filter_column())
        if col_name:
            active_filters.set(remove_filter(active_filters.get(), col_name))
    
    # Watch for filter dropdown changes - dynamically observe filter inputs
    @reactive.Effect
    def _watch_filter_changes():
        new_filters, updated = update_filter_values(active_filters.get(), input)
        if updated:
            active_filters.set(new_filters)
            # Skip page reset on first sync (initial load)
            if _first_filter_sync["done"]:
                current_page.set(1)
            else:
                _first_filter_sync["done"] = True
    
    # Output: Pagination controls
    @render.ui
    def pagination_controls():
        """Render pagination controls with rows per page selector"""
        filtered_indices = _get_filtered_rows()
        total_rows = len(filtered_indices)
        rows_per_page_val = rows_per_page_value.get()
        
        if rows_per_page_val == "all":
            return build_pagination_controls_all(total_rows, rows_per_page_val)
        
        page, total_pages, start_row, end_row = calculate_pagination(total_rows, rows_per_page_val, current_page.get())
        return build_pagination_controls_paged(page, total_pages, start_row, end_row, total_rows, rows_per_page_val)
    
    # Sync rows_per_page input with reactive value
    @reactive.Effect
    def _sync_rows_per_page():
        try:
            val = input.rows_per_page()
            if val and val != rows_per_page_value.get():
                rows_per_page_value.set(val)
                # Skip page reset on first sync (initial load)
                if _first_rows_per_page_sync["done"]:
                    current_page.set(1)  # Reset to first page when changing rows per page
            # Mark first sync as done
            if not _first_rows_per_page_sync["done"]:
                _first_rows_per_page_sync["done"] = True
        except:
            pass
    
    # Pagination event handlers
    @reactive.Effect
    @reactive.event(input.first_page_btn)
    def _first_page():
        current_page.set(1)
        # Persist page state (consistent with sort handler pattern)
        sort_state = current_sort.get()
        save_ui_state(
            sort_column=sort_state.get("column"),
            sort_ascending=sort_state.get("ascending", True),
            current_page=1,
            rows_per_page=int(rows_per_page_value.get()) if rows_per_page_value.get() != "all" else 25,
            column_preset=active_preset.get()
        )
    
    @reactive.Effect
    @reactive.event(input.prev_page_btn)
    def _prev_page():
        page = current_page.get()
        if page > 1:
            new_page = page - 1
            current_page.set(new_page)
            # Persist page state
            sort_state = current_sort.get()
            save_ui_state(
                sort_column=sort_state.get("column"),
                sort_ascending=sort_state.get("ascending", True),
                current_page=new_page,
                rows_per_page=int(rows_per_page_value.get()) if rows_per_page_value.get() != "all" else 25,
                column_preset=active_preset.get()
            )
    
    @reactive.Effect
    @reactive.event(input.next_page_btn)
    def _next_page():
        filtered_indices = _get_filtered_rows()
        rows_per_page_val = rows_per_page_value.get()
        if rows_per_page_val != "all":
            rows_per_page = int(rows_per_page_val)
            total_pages = max(1, (len(filtered_indices) + rows_per_page - 1) // rows_per_page)
            page = current_page.get()
            if page < total_pages:
                new_page = page + 1
                current_page.set(new_page)
                # Persist page state
                sort_state = current_sort.get()
                save_ui_state(
                    sort_column=sort_state.get("column"),
                    sort_ascending=sort_state.get("ascending", True),
                    current_page=new_page,
                    rows_per_page=rows_per_page,
                    column_preset=active_preset.get()
                )
    
    @reactive.Effect
    @reactive.event(input.last_page_btn)
    def _last_page():
        filtered_indices = _get_filtered_rows()
        rows_per_page_val = rows_per_page_value.get()
        if rows_per_page_val != "all":
            rows_per_page = int(rows_per_page_val)
            total_pages = max(1, (len(filtered_indices) + rows_per_page - 1) // rows_per_page)
            current_page.set(total_pages)
            # Persist page state
            sort_state = current_sort.get()
            save_ui_state(
                sort_column=sort_state.get("column"),
                sort_ascending=sort_state.get("ascending", True),
                current_page=total_pages,
                rows_per_page=rows_per_page,
                column_preset=active_preset.get()
            )
    
    @reactive.Effect
    @reactive.event(input.page_jump_btn)
    def _page_jump():
        filtered_indices = _get_filtered_rows()
        rows_per_page_val = rows_per_page_value.get()
        if rows_per_page_val != "all":
            rows_per_page = int(rows_per_page_val)
            total_pages = max(1, (len(filtered_indices) + rows_per_page - 1) // rows_per_page)
            try:
                target_page = int(input.page_jump_input())
                target_page = max(1, min(target_page, total_pages))
                current_page.set(target_page)
                # Persist page state
                sort_state = current_sort.get()
                save_ui_state(
                    sort_column=sort_state.get("column"),
                    sort_ascending=sort_state.get("ascending", True),
                    current_page=target_page,
                    rows_per_page=rows_per_page,
                    column_preset=active_preset.get()
                )
            except:
                pass
    
    # Handle search button click
    @reactive.Effect
    @reactive.event(input.search_btn)
    def _handle_search():
        search_term = input.search_input() if hasattr(input, 'search_input') else ""
        search_column = input.search_column() if hasattr(input, 'search_column') else "all"
        search_state.set({"term": search_term, "column": search_column})
        current_page.set(1)
    
    # Reset to page 1 when status filters change
    @reactive.Effect
    @reactive.event(input.status_filter_multi)
    def _reset_page_on_filter_change():
        # Skip first invocation (initial load)
        if not _first_search_filter_sync["done"]:
            _first_search_filter_sync["done"] = True
            return
        current_page.set(1)
        # Persist page state
        sort_state = current_sort.get()
        save_ui_state(
            sort_column=sort_state.get("column"),
            sort_ascending=sort_state.get("ascending", True),
            current_page=1,
            rows_per_page=int(rows_per_page_value.get()) if rows_per_page_value.get() != "all" else 25,
            column_preset=active_preset.get()
        )

    # Output: Data table
    @render.ui
    def table_container():
        """Render the editable data table with pagination"""
        _ = mods_log.get()
        _ = approval_status.get()
        
        current_df = data.get()
        filtered_indices = _get_filtered_rows()
        paginated_indices = get_paginated_indices(filtered_indices, rows_per_page_value.get(), current_page.get())
        
        return build_table_container(
            paginated_indices=paginated_indices,
            current_df=current_df,
            cols=active_columns.get(),
            widths=column_widths.get(),
            filtered_count=len(filtered_indices),
            total_rows=len(current_df),
            get_row_status_func=_get_row_status,
            edited_cells=edited_cells.get(),
            pk_columns=app_config.table.primary_key,
            editable_columns=app_config.table.editable_columns,
            readonly_columns=app_config.table.readonly_columns
        )
    
    # Output: Approval status
    @render.ui
    def approval_status_ui():
        return build_approval_status_banner(approval_status.get(), approval_timestamp.get())
    
    # Output: Modifications log
    @render.ui
    def modifications_log_ui():
        return build_modifications_log(mods_log.get())
    
    # Event: Handle undo modification
    @reactive.Effect
    @reactive.event(input.undo_modification)
    def _handle_undo():
        log_idx = process_undo_action(input.undo_modification())
        if log_idx is None:
            return
        updated_df, updated_log, message, error = perform_undo(data.get(), mods_log.get(), log_idx, config_instance=config)
        if error:
            ui.notification_show(error, type="warning", duration=2)
        else:
            data.set(updated_df)
            mods_log.set(updated_log)
            # Auto-save log and data state to file
            save_log_to_file(updated_log, modifications_log_path)
            updated_df.to_json(data_dir / "data_state.json", orient="records", indent=2, default_handler=str)
            ui.notification_show(message, type="message", duration=2)
    
    # Event: Handle cell edit from popup
    @reactive.Effect
    @reactive.event(input.cell_edit)
    def _handle_cell_edit():
        edit_data = input.cell_edit()
        print(f"DEBUG: cell_edit received: {edit_data}")
        row, col, old_val, new_val = process_cell_edit_action(edit_data)
        print(f"DEBUG: processed edit - row={row}, col={col}, old={old_val}, new={new_val}")
        if row is not None and col:
            current_df = data.get()
            current_log = mods_log.get()
            # Debug: verify config instance is correct
            print(f"DEBUG: config type={type(config)}, db_mode={config.app_config.database.mode if hasattr(config, 'app_config') else 'N/A'}")
            updated_df, updated_log = perform_cell_edit(current_df, current_log, row, col, old_val, new_val, config_instance=config)
            print(f"DEBUG: perform_cell_edit returned, log entries: {len(updated_log)}")
            data.set(updated_df)
            mods_log.set(updated_log)
            
            # Track edited cell for brown border display using PK-based key
            # Get the row's PK values
            pk_cols = app_config.table.primary_key
            try:
                row_data = current_df.iloc[row]
                row_pk = {pk: row_data[pk] for pk in pk_cols if pk in current_df.columns}
                pk_tuple = tuple(sorted((k, str(v)) for k, v in row_pk.items()))
                
                # Keep original value from first edit, update current value
                current_edited = edited_cells.get().copy()
                cell_key = (pk_tuple, col)
                if cell_key not in current_edited:
                    # First edit - old_val is the original
                    current_edited[cell_key] = {"original": old_val, "current": new_val}
                else:
                    # Subsequent edit - keep original, update current
                    current_edited[cell_key]["current"] = new_val
                edited_cells.set(current_edited)
            except Exception as e:
                print(f"Warning: Could not track edited cell: {e}")
            
            # Auto-save log and data state to file
            save_log_to_file(updated_log, modifications_log_path)
            updated_df.to_json(data_dir / "data_state.json", orient="records", indent=2, default_handler=str)
            ui.notification_show(f"Updated Row {row + 1}, {col}", type="message", duration=2)
    
    # Event: Save modifications to file
    @reactive.Effect
    @reactive.event(input.save_btn)
    def _save_modifications():
        message = save_modifications_to_file(
            data.get(), mods_log.get(),
            modifications_log_path, data_dir / "data_state.json"
        )
        ui.notification_show(message, type="message", duration=3)
    
    # Event: Export status report
    @reactive.Effect
    @reactive.event(input.export_status_btn)
    def _export_status_report():
        summary_data, status_counts = _get_modification_summary()
        message = export_status_report(summary_data, status_counts, data_dir / "modification_status_report.csv")
        ui.notification_show(message, type="message", duration=5)
    
    # Event: Export CSV - Download handler (selected rows only)
    @render.download(filename="data_selected.csv")
    def export_btn():
        """Generate CSV file for download with selected rows only."""
        import io
        current_df = data.get()
        selected_indices = get_selected_row_indices(input, len(current_df))
        
        if not selected_indices:
            ui.notification_show("Please select rows to export", type="warning", duration=3)
            return  # Return nothing - no download
        
        # Filter to selected rows only
        selected_df = current_df.iloc[selected_indices]
        
        output = io.StringIO()
        selected_df.to_csv(output, index=False)
        ui.notification_show(f"Exported {len(selected_indices)} row(s)", type="message", duration=2)
        yield output.getvalue()
    
    # Event: Export All CSV - Download handler (all filtered/sorted rows)
    def _get_export_filename():
        """Generate dynamic filename based on app title."""
        # Sanitize app title for filename (remove special chars, replace spaces with underscores)
        import re
        title = app_config.app_title or "data"
        safe_title = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_')
        return f"{safe_title}_data_filtered.csv"
    
    @render.download(filename=_get_export_filename)
    def export_all_btn():
        """Generate CSV file for download with all rows matching current filter/sort criteria."""
        import io
        current_df = data.get()
        
        if current_df.empty:
            ui.notification_show("No data to export", type="warning", duration=3)
            return  # Return nothing - no download
        
        # Get filtered row indices (respects search, status filter, column filters)
        filtered_indices = _get_filtered_rows()
        
        if not filtered_indices:
            ui.notification_show("No rows match current filters", type="warning", duration=3)
            return
        
        # Filter to matching rows
        filtered_df = current_df.iloc[filtered_indices].copy()
        
        # Apply current sort
        sort_state = current_sort.get()
        if sort_state.get("column") and sort_state.get("column") in filtered_df.columns:
            filtered_df = sort_dataframe(
                filtered_df,
                sort_state.get("column"),
                "asc" if sort_state.get("ascending", True) else "desc"
            )
        
        output = io.StringIO()
        filtered_df.to_csv(output, index=False)
        ui.notification_show(f"Exported {len(filtered_df)} filtered row(s)", type="message", duration=2)
        yield output.getvalue()
    
    # Event: Reload data
    @reactive.Effect
    @reactive.event(input.reload_btn)
    def _reload_data():
        # Reload fresh data from database
        fresh_data = load_data_from_source()
        data.set(fresh_data)
        mods_log.set(load_modifications_log())
        ui.notification_show("Data reloaded from database.", type="message", duration=3)
    
    # Event: Approve rows
    @reactive.Effect
    @reactive.event(input.approve_btn)
    def _approve_data():
        # Debug: Check what rows are selected
        current_df = data.get()
        selected_indices = get_selected_row_indices(input, len(current_df))
        
        if not selected_indices:
            ui.notification_show("Please select rows to approve", type="warning", duration=3)
            return
        
        # Convert indices to PKs
        selected_pks = _get_selected_pks(selected_indices, current_df)
        print(f"DEBUG: Approve - selected indices: {selected_indices}, PKs: {selected_pks}")
        
        # Create log entry with PKs
        log = mods_log.get().copy()
        log.append(create_approval_entry(selected_pks, len(current_df), len(log)))
        
        # Save to file (for non-DB mode)
        save_log_to_file(log, modifications_log_path)
        
        # Save to database if enabled
        if app_config.database.enabled:
            _save_status_to_db(selected_pks, "approval")
        
        mods_log.set(log)
        ui.notification_show(f"{len(selected_pks)} row(s) APPROVED!", type="message", duration=2)
    
    # Event: Reject rows
    @reactive.Effect
    @reactive.event(input.reject_btn)
    def _reject_data():
        current_df = data.get()
        selected_indices = get_selected_row_indices(input, len(current_df))
        
        if not selected_indices:
            ui.notification_show("Please select rows to reject", type="warning", duration=3)
            return
        
        # Convert indices to PKs
        selected_pks = _get_selected_pks(selected_indices, current_df)
        print(f"DEBUG: Reject - selected indices: {selected_indices}, PKs: {selected_pks}")
        
        # Create log entry with PKs
        log = mods_log.get().copy()
        log.append(create_rejection_entry(selected_pks, len(current_df), len(log)))
        
        # Save to file (for non-DB mode)
        save_log_to_file(log, modifications_log_path)
        
        # Save to database if enabled
        if app_config.database.enabled:
            _save_status_to_db(selected_pks, "rejection")
        
        mods_log.set(log)
        ui.notification_show(f"{len(selected_pks)} row(s) REJECTED!", type="message", duration=2)
    
    # Event: Clear approval
    @reactive.Effect
    @reactive.event(input.clear_approval_btn)
    def _clear_approval():
        approval_status.set(None)
        approval_timestamp.set(None)
