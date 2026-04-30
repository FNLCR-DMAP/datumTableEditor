"""
Server Logic for Epitopes Data Editor PyShiny App
Updated for split panel layout with column customization
"""

from shiny import render, ui, reactive
import pandas as pd
from datetime import datetime

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
    build_facet_panels,
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
    # Clipboard utilities
    process_copy_request,
    # Event handlers
    process_approval_action,
    process_rejection_action,
    process_undo_action,
    process_cell_edit_action,
)
from .commute import EventEmitter, WidgetAPI


def create_server(input, output, session, config_path: str = "app_config.json"):  # noqa: ARG001
    """
    Server logic for the Shiny app
    
    Args:
        config_path: Path to the config JSON file for this widget instance
    
    Returns:
        WidgetAPI: Public API object with .events, .data, .active_columns
    """
    import os
    # Get username: Posit Connect session.user → SHINY_USER env var → 'default_user'
    posit_username = getattr(session, 'user', None) or os.environ.get('SHINY_USER') or 'default_user'
    # Sanitize username for use in table names
    safe_username = "".join(c if c.isalnum() else "_" for c in posit_username).lower()
    print(f"[Session] User: {posit_username} (safe: {safe_username})")
    
    # Load config instance for this widget, passing the username for user-scoped tables
    import time as _t
    _server_t0 = _t.time()
    from .config.config_instance import load_config_instance, QueryParams
    print(f"[Config] Loading config from {config_path} for user: {safe_username}")
    config = load_config_instance(config_path, username=safe_username)
    _server_t1 = _t.time()
    print(f"[Timing] load_config_instance: {(_server_t1 - _server_t0)*1000:.0f}ms")
    
    # Initialise tracker mode (force-flush SQL + render timings)
    from .utils import tracker
    tracker.init(config.app_config.tracker_mode)
    
    # Extract config values
    data_dir = config.data_dir
    modifications_log_path = config.modifications_log_path
    df_original = config.df
    display_columns = config.display_columns
    all_columns = config.all_columns
    app_config = config.app_config
    column_masks = app_config.table.column_masks or None
    
    # Resolve permission role for this user
    _perm = app_config.permissions
    user_role = _perm.user_roles.get(safe_username, _perm.default_role)
    is_viewer = user_role == "viewer" or app_config.read_only
    print(f"[Permissions] User={safe_username} | role={user_role} | default_role={_perm.default_role} | user_roles={_perm.user_roles} | is_viewer={is_viewer} | read_only={app_config.read_only}")
    
    def _require_editor(action: str = "This action") -> bool:
        """Return True if the user has editor permissions; show notification and return False for viewers."""
        if is_viewer:
            print(f"[Permissions] BLOCKED: {action} denied for viewer {safe_username}")
            ui.notification_show(f"{action} requires editor permissions.", type="warning", duration=3)
            return False
        return True
    
    # ── Event emitter (commute layer) ──────────────────────────
    _emitter = EventEmitter(widget_id=config_path)

    def _emit(action: str, **payload) -> None:
        """Fire an event to the host app via the commute layer."""
        _emitter.emit(action, **payload)

    # Create local functions that use this config instance
    def load_modifications_log():
        return config.load_modifications_log()
    
    def load_data_from_source():
        return config.reload_data()
    
    def save_ui_state(**kwargs):
        """Save UI state for this instance (no-op when persist_state is disabled)."""
        if not app_config.state.persist_state:
            return False
        return config.save_ui_state(**kwargs)
    
    def load_ui_state():
        """Load UI state for this instance (returns defaults when persist_state is disabled)."""
        if not app_config.state.persist_state:
            return {
                "sort_column": app_config.table.default_sort_column,
                "sort_ascending": app_config.table.default_sort_ascending,
                "current_page": 1,
                "rows_per_page": app_config.table.default_rows_per_page,
                "filters": {},
                "column_preset": None
            }
        return config.load_ui_state()
    
    # Presets use the server's ConfigInstance directly (handles datum & direct modes)
    
    # Load UI state (sort, filters, page) from database
    _t2 = _t.time()
    ui_state = load_ui_state()
    print(f"[Timing] load_ui_state: {(_t.time() - _t2)*1000:.0f}ms")
    
    # Check if lazy loading is enabled (at startup — may change when synthesis activates)
    _initial_lazy_loading = config.is_lazy_loading

    def is_lazy_loading():
        """Dynamic check: True when config has an active DataFetcher."""
        return config.is_lazy_loading
    
    # ----- Auto-synthesis: try cached synthesis table on startup -----
    _synthesis_autoloaded = False
    _synthesis_needs_generate = False
    if app_config.enable_synthesis and app_config.synthesis.query:
        try:
            if config.check_synthesis_table_exists():
                # Table exists — check TTL before serving stale data
                result_table = config.get_synthesis_table_name()
                # Mark schema as verified (table exists → schema exists)
                if '.' in result_table:
                    config._schemas_verified.add(result_table.split('.', 1)[0])
                age = config._get_synthesis_age_minutes()
                # Stamp comment if missing (pre-existing matview)
                if age is None:
                    import time as _time
                    from .config.config_instance import SqlTableName
                    config._stamp_synthesis_comment(SqlTableName(result_table), _time.time())
                    age = 0.0
                ttl = app_config.synthesis.ttl_minutes
                if ttl > 0 and age > ttl:
                    # Expired — trigger refresh via run_synthesis() (which does REFRESH MATERIALIZED VIEW)
                    print(f"[Synthesis] Matview expired ({age:.0f} min > {ttl} min TTL) — will refresh after startup")
                    _synthesis_needs_generate = True
                else:
                    # Within TTL — serve cached matview
                    initial_df = config._read_synthesis_table(result_table)
                    total_row_count = len(initial_df)
                    _synthesis_autoloaded = True
                    # Populate columns from synthesis result (base table was skipped)
                    if not all_columns and len(initial_df.columns) > 0:
                        all_columns = list(initial_df.columns)
                        display_columns = list(initial_df.columns)
                        config.all_columns = all_columns
                        config.display_columns = display_columns
                    print(f"[Synthesis] Auto-loaded cached matview ({age:.0f} min old, TTL {ttl} min) — {total_row_count} rows")
            else:
                print(f"[Synthesis] Matview missing — will auto-generate after startup")
                _synthesis_needs_generate = True
        except Exception as e:
            print(f"[Synthesis] Auto-load failed: {e} — falling back to main table")

    # Use data already loaded by ConfigInstance.__post_init__ (respects shared cache).
    # reload_data() is reserved for explicit user-triggered reloads (Reload button).
    if _synthesis_autoloaded:
        pass  # Already loaded the synthesis table above
    elif _synthesis_needs_generate:
        # Synthesis enabled but cache missing/expired — start with empty frame;
        # the reactive effect will auto-generate and swap in the result.
        initial_df = pd.DataFrame()
        total_row_count = 0
        print("[Synthesis] Skipping main table load — will auto-generate")
    elif _initial_lazy_loading:
        # In lazy loading mode, start with empty dataframe - data fetched on demand
        initial_df = config.df  # Empty dataframe with correct columns
        total_row_count = config.total_row_count
        print(f"[Lazy Loading] Enabled. Total rows in DB: {total_row_count}")
    else:
        # Traditional mode: data already loaded by __post_init__ → _load_data()
        # which checks shared_cache_key first (no redundant DB round-trip)
        initial_df = config.df.copy() if app_config.database.enabled else df_original.copy()
        total_row_count = len(initial_df)
    
    # Apply initial sorting if saved (only in non-lazy mode)
    if not _initial_lazy_loading and ui_state.get("sort_column"):
        sort_col = ui_state["sort_column"]
        sort_asc = ui_state.get("sort_ascending", True)
        # Normalise ascending to list of direction strings matching columns
        if isinstance(sort_col, list):
            if isinstance(sort_asc, list):
                direction = ["asc" if a else "desc" for a in sort_asc]
            else:
                direction = ["asc" if sort_asc else "desc"] * len(sort_col)
        else:
            direction = "asc" if sort_asc else "desc"
        initial_df = sort_dataframe(initial_df, sort_col, direction)
    
    # Reactive values
    data = reactive.Value(initial_df)
    total_rows = reactive.Value(total_row_count)  # Total rows for pagination UI
    filtered_row_count = reactive.Value(total_row_count)  # Filtered count (updated on filter change)
    
    # Track edited cells from config - {(row_idx, col_name): new_value}
    edited_cells = reactive.Value(config.get_edited_cells())
    
    current_sort = reactive.Value({
        "column": ui_state.get("sort_column"),
        "ascending": ui_state.get("sort_ascending", True)
    })
    _t3 = _t.time()
    mods_log = reactive.Value(load_modifications_log())
    print(f"[Timing] load_modifications_log: {(_t.time() - _t3)*1000:.0f}ms")
    
    # Load initial approval status from log
    initial_status, initial_timestamp = get_latest_approval_status(load_modifications_log())
    approval_status = reactive.Value(initial_status)
    approval_timestamp = reactive.Value(initial_timestamp)
    
    # Load presets via ConfigInstance (scoped by data_table + username)
    _t4 = _t.time()
    if app_config.table.presets_enabled:
        loaded_presets = load_presets(config, display_columns)
    else:
        loaded_presets = {"Default": {"columns": list(display_columns), "widths": {}}}
    column_presets = reactive.Value(loaded_presets)
    print(f"[Timing] load_presets: {(_t.time() - _t4)*1000:.0f}ms")
    
    # Load last active preset (persists across refreshes)
    if app_config.table.presets_enabled:
        initial_active_preset = load_active_preset(config)
        print(f"[Preset] Active preset for {safe_username}: {initial_active_preset}")
    else:
        initial_active_preset = "Default"
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
    
    # Trigger for column layout changes that need a table re-render.
    # Header drag-reorder and resize update state silently (JS already shows it);
    # add/remove/preset/synthesis bump this to force a server-side re-render.
    _columns_layout_trigger = reactive.Value(0)
    
    # Pagination state - always start on page 1; restore rows-per-page preference
    initial_rows_per_page = str(ui_state.get("rows_per_page", 25))
    current_page = reactive.Value(1)
    rows_per_page_value = reactive.Value(initial_rows_per_page)
    print(f"[Timing] create_server total setup: {(_t.time() - _server_t0)*1000:.0f}ms")
    
    # Track first sync to avoid resetting page on initial load
    _first_rows_per_page_sync = {"done": False}
    _first_search_filter_sync = {"done": False}
    
    # Initialize default filters from config
    # Config format: {column: [values]} or {column: "value"} or {column: {"op": "...", "value": ...}}
    # Internal format: {column: "value1\nvalue2\n..."} or {column: {"op": "...", "value": ...}}
    # Map user-friendly operator labels (used in config) to internal keys
    _OP_LABEL_TO_KEY = {
        "is": "in", "is not": "not_in",
        "contains": "contains", "does not contain": "not_contains",
        "between": "between",
        ">": "gt", "≥": "gte", ">=": "gte",
        "<": "lt", "≤": "lte", "<=": "lte",
        "matches regex": "regex", "matches": "regex",
        "is not empty": "not_empty",
        "is null": "is_null",
        "within last n days": "last_n_days",
    }

    def _convert_default_filters(config_filters: dict) -> dict:
        """Convert config default_filters to internal format.
        
        Operator dicts ({"op": "...", "value": ...}) are normalised so that
        user-friendly labels (e.g. "is") are mapped to internal keys ("in").
        Simple values are converted to newline-delimited strings.
        """
        result = {}
        for col, values in config_filters.items():
            if col.startswith("_"):  # skip _comment, _example keys
                continue
            if isinstance(values, dict) and "op" in values:
                # Normalise operator name (e.g. "is" → "in")
                raw_op = values.get("op", "in")
                normalised_op = _OP_LABEL_TO_KEY.get(raw_op.lower(), raw_op) if isinstance(raw_op, str) else raw_op
                result[col] = {**values, "op": normalised_op}
            elif isinstance(values, list):
                # List of values -> newline-delimited string
                result[col] = "\n".join(str(v) for v in values)
            else:
                # Single value -> string
                result[col] = str(values) if values else ""
        return result
    
    initial_filters = _convert_default_filters(app_config.query.default_filters) if hasattr(app_config, 'query') and app_config.query.default_filters else {}
    
    # Dynamic column filters - stores active filters as {column_name: "value1\nvalue2\n..."}
    active_filters = reactive.Value(initial_filters)
    # Pending filters — edited in the sidebar without triggering table reload.
    # Copied to active_filters when the user clicks "Apply Filters".
    pending_filters = reactive.Value(initial_filters.copy())
    # Trigger for filter panel re-render (bumped on structural changes: add/remove filter, change operator)
    _filter_panel_trigger = reactive.Value(0)
    
    # Search state - updated only when search button is clicked
    search_state = reactive.Value({"term": "", "column": "all"})
    
    # ----- Synthesis state -----
    synthesis_active = reactive.Value(_synthesis_autoloaded)   # True if auto-loaded from cache
    synthesis_running = reactive.Value(False)        # True while transform is executing
    synthesis_data = reactive.Value(initial_df if _synthesis_autoloaded else pd.DataFrame())
    synthesis_error = reactive.Value("")             # Error message if transform failed
    synthesis_cached = reactive.Value(_synthesis_autoloaded)   # True if last result was from cache
    enable_synthesis = app_config.enable_synthesis

    # Monotonic counter bumped after every synthesis completion (auto-gen / run / regen).
    # table_container reads it to guarantee a re-render even when the lazy-loading
    # path drops the dependency on the ``data`` reactive value.
    _table_reload_trigger = reactive.Value(0)

    # Activate DataFetcher for synthesis matview when auto-loaded
    if _synthesis_autoloaded:
        config.activate_synthesis_fetcher(config.get_synthesis_table_name())

    # Auto-generate synthesis if cache was expired/missing on startup
    _synthesis_auto_triggered = {"done": False}

    @reactive.Effect
    async def _auto_generate_synthesis():
        """Trigger synthesis generation automatically when cache is stale."""
        import asyncio
        if _synthesis_auto_triggered["done"] or not _synthesis_needs_generate:
            return
        _synthesis_auto_triggered["done"] = True
        synthesis_running.set(True)
        synthesis_error.set("")
        try:
            result_df, was_cached = await asyncio.to_thread(config.run_synthesis)
            synthesis_data.set(result_df)
            synthesis_cached.set(was_cached)
            synthesis_active.set(True)
            data.set(result_df)
            total_rows.set(len(result_df))
            filtered_row_count.set(len(result_df))
            current_page.set(1)
            # Activate DataFetcher for SQL-level filtering on matview
            config.activate_synthesis_fetcher(config.get_synthesis_table_name())
            # Always sync active_columns from the fetcher (synthesis may have
            # different columns than the base table, and on first boot
            # active_columns starts as [] because base table load was skipped).
            if config.all_columns:
                active_columns.set(list(config.all_columns))
            cache_msg = " (cached)" if was_cached else ""
            print(f"[Synthesis] Auto-generated{cache_msg} — {len(result_df):,} rows")
            # Bump reload trigger to force table_container re-render
            _table_reload_trigger.set(_table_reload_trigger.get() + 1)
            ui.notification_show(
                f"Synthesis ready{cache_msg} — {len(result_df):,} rows",
                type="message", duration=4
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            synthesis_error.set(str(e))
            ui.notification_show(
                f"Synthesis auto-generation failed: {e}",
                type="error", duration=6
            )
        finally:
            synthesis_running.set(False)
    
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
    def _save_status_to_db(selected_pks, mod_type: str, row_data_map: dict = None):
        """Save approval/rejection entries to database with PKs using batch transaction.
        
        Uses app_config.status_values to determine what value is written to the
        status column.  mod_type is the internal log type ("approval"/"rejection").
        
        When mod_type is "approval" and approval_assignment is configured,
        also copies source column values to target columns for each row.
        
        All DB operations are batched into a single transaction for performance.
        
        Args:
            selected_pks: List of PK dicts for the selected rows.
            mod_type: "approval" or "rejection".
            row_data_map: Optional dict mapping PK tuple -> row Series for
                          column value lookups (needed for approval_assignment).
        """
        internal_key = "approved" if mod_type == "approval" else "rejected"
        status_value = app_config.status_values.get(internal_key, internal_key)
        assignment = app_config.approval_assignment if mod_type == "approval" else {}

        # Build batch entries
        entries = []
        for row_pk in selected_pks:
            entry = {
                "row_pk": row_pk,
                "status_value": status_value,
                "mod_type": mod_type,
                "assignments": []
            }
            # Approval assignment: copy source col → target col
            if assignment and row_data_map:
                pk_key = tuple(sorted(row_pk.items()))
                row = row_data_map.get(pk_key)
                if row is not None:
                    for src_col, tgt_col in assignment.items():
                        src_val = row[src_col] if src_col in row.index else None
                        new_val = str(src_val) if src_val is not None else None
                        entry["assignments"].append((tgt_col, new_val))
            entries.append(entry)

        # Execute all in one transaction
        try:
            config.batch_save_status(entries)
            print(f"DEBUG: Batch {mod_type} saved {len(entries)} rows")
        except Exception as e:
            print(f"Warning: Batch {mod_type} save failed: {e}")
    
    # Helper functions that wrap utilities with reactive values
    def _get_row_status(row_idx):
        """Determine row status.
        
        The status_column in the data table is the source of truth.
        The _mod_status column (SQL-computed) normalises it to an internal key.
        For in-memory mode (no _mod_status column), the mods log is checked.
        """
        current_df = data.get()
        current_log = mods_log.get()
        
        # Prefer _mod_status column (already normalised from status_column by SQL)
        if "_mod_status" in current_df.columns:
            try:
                db_status = str(current_df.loc[row_idx, "_mod_status"]).strip().lower()
                if db_status in ("edited", "approved", "rejected"):
                    return db_status
                # Normalize raw mod_type values to internal keys
                if db_status == "approval":
                    return "approved"
                elif db_status == "rejection":
                    return "rejected"
                elif db_status == "field_modification":
                    return "edited"
                # Also check custom status_values (reverse lookup)
                reverse = {v.lower(): k for k, v in app_config.status_values.items()}
                mapped = reverse.get(db_status, db_status)
                if mapped in ("edited", "approved", "rejected"):
                    return mapped
            except:
                pass
            return "unprocessed"
        
        # Fallback: in-memory mods log (non-lazy / non-DB mode)
        try:
            pk_cols = app_config.table.primary_key
            row = current_df.loc[row_idx]
            row_pk = {pk: row[pk] for pk in pk_cols if pk in current_df.columns}
        except:
            row_pk = None
        return get_row_status(row_idx, current_log, row_pk)
    
    def _get_status_counts():
        """Wrapper for get_status_counts that uses reactive values.
        In lazy loading mode, queries DB for overall counts instead of page-only."""
        if is_lazy_loading():
            # Use DB query for filtered status distribution
            params = _build_query_params()
            # Build params without status filters to get counts for all statuses
            from .config.config_instance import QueryParams as QP
            count_params = QP(
                filters=params.filters,
                search_term=params.search_term,
                search_column=params.search_column,
                sort_column=params.sort_column,
                sort_ascending=params.sort_ascending,
                page=1,
                page_size=1,
                status_filters=list(app_config.status_labels.keys())
            )
            counts = config.data_fetcher.get_status_counts(count_params)
            # Overlay uncommitted mods_log changes on top of DB counts
            current_log = mods_log.get()
            if current_log:
                current_df = data.get()
                pk_cols = app_config.table.primary_key
                for idx in current_df.index:
                    try:
                        row = current_df.loc[idx]
                        row_pk = {pk: row[pk] for pk in pk_cols if pk in current_df.columns}
                        log_status = get_row_status(idx, current_log, row_pk)
                        db_status = str(row.get("_mod_status", "unprocessed")).strip().lower()
                        if log_status != "unprocessed" and log_status != db_status:
                            if db_status in counts:
                                counts[db_status] = max(0, counts[db_status] - 1)
                            if log_status in counts:
                                counts[log_status] += 1
                    except:
                        pass
            return counts
        # Non-lazy mode: count statuses from filtered rows (respecting column/search filters)
        current_df = data.get()
        _ = mods_log.get()  # reactive dependency on mods_log
        all_statuses = list(app_config.status_labels.keys())
        # Get rows filtered by column filters and search (include ALL statuses for counting)
        search = search_state.get()
        filtered_indices = get_filtered_rows(
            df=current_df,
            active_columns=active_columns.get(),
            search_term=search.get("term", ""),
            status_filters=all_statuses,
            column_filters=active_filters.get(),
            get_row_status_func=_get_row_status,
            search_column=search.get("column", "all")
        )
        counts = {k: 0 for k in all_statuses}
        for idx in filtered_indices:
            status = _get_row_status(idx)
            if status in counts:
                counts[status] += 1
            else:
                counts["unprocessed"] = counts.get("unprocessed", 0) + 1
        return counts
    
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
            status_filters = list(app_config.status_labels.keys())
        
        return get_filtered_rows(
            df=current_df,
            active_columns=active_columns.get(),
            search_term=search_term,
            status_filters=status_filters,
            column_filters=active_filters.get(),
            get_row_status_func=_get_row_status,
            search_column=search_column
        )

    def _build_query_params(page: int = None, page_size: int = None, for_export: bool = False) -> QueryParams:
        """Build QueryParams from current UI state for lazy loading."""
        search = search_state.get()
        sort_state = current_sort.get()
        
        # Get status filters
        try:
            status_filters = list(input.status_filter_multi())
        except:
            status_filters = list(app_config.status_labels.keys())
        
        # Convert active_filters to dict format expected by QueryParams
        # active_filters: {column: "value1\nvalue2\n..."} -> {column: [values]}
        # Operator dicts ({"op": "...", "value": ...}) pass through as-is
        filters_dict = {}
        for col, val in active_filters.get().items():
            if isinstance(val, dict) and "op" in val:
                # Operator filter — pass through directly
                filters_dict[col] = val
            elif val and str(val).strip() and val != "all":
                values = [v.strip() for v in str(val).split("\n") if v.strip()]
                if values:
                    filters_dict[col] = values if len(values) > 1 else values[0]
        
        # Determine page size
        if for_export:
            actual_page_size = 1000000  # Large number for export (no limit)
        elif page_size is not None:
            actual_page_size = page_size
        else:
            rpp = rows_per_page_value.get()
            actual_page_size = int(rpp) if rpp != "all" else app_config.database.page_buffer_size
        
        return QueryParams(
            filters=filters_dict,
            search_term=search.get("term", ""),
            search_column=search.get("column", "all"),
            sort_column=sort_state.get("column"),
            sort_ascending=sort_state.get("ascending", True),
            page=page if page is not None else current_page.get(),
            page_size=actual_page_size,
            status_filters=status_filters
        )
    
    @reactive.Calc
    def _lazy_filtered_count():
        """Cached filtered count for lazy-loading mode.
        Reacts to the same inputs as _build_query_params so it invalidates
        when filters/search/sort change, but is computed only once per cycle."""
        if not is_lazy_loading():
            return 0
        params = _build_query_params()
        return config.data_fetcher.get_filtered_count(params)
    
    def _fetch_page_data() -> tuple:
        """
        Fetch current page data. Returns (df, filtered_count, total_count).
        
        In lazy loading mode: queries database
        In traditional mode: slices in-memory data
        
        NOTE: This is a pure function with no side effects (no .set() calls).
        The caller is responsible for using the returned counts as needed.
        """
        if is_lazy_loading():
            # Build query params and fetch from DB
            params = _build_query_params()
            fetched_df = config.data_fetcher.fetch_page(params)
            
            # Use cached filtered count
            new_filtered_count = _lazy_filtered_count()
            
            return fetched_df, new_filtered_count, total_rows.get()
        else:
            # Traditional mode: use in-memory data
            current_df = data.get()
            filtered_indices = _get_filtered_rows()
            return current_df, len(filtered_indices), len(current_df)
    
    def _fetch_all_filtered_data():
        """Fetch all data matching current filters (for export)."""
        if is_lazy_loading():
            params = _build_query_params(for_export=True)
            return config.data_fetcher.fetch_all_filtered(params)
        else:
            # Traditional mode: return filtered data
            current_df = data.get()
            filtered_indices = _get_filtered_rows()
            return current_df.loc[filtered_indices] if filtered_indices else current_df

    # Wrapper functions for preset utilities (using file paths and username from this scope)
    def _save_presets(presets_dict):
        save_presets(config, presets_dict)
    
    def _save_active_preset(preset_name):
        save_active_preset(config, preset_name)

    # Output: Namespace holder for JavaScript
    @render.ui
    def _namespace_holder():
        # Get namespace by calling session.ns with a test ID and extracting the prefix
        # session.ns("test") returns "editor1-test", so we remove "test" to get "editor1-"
        ns_prefix = session.ns("test").replace("test", "")
        selection_mode = "multiple" if app_config.review_detail_multi_select else "single"
        from shiny import ui as sui
        return sui.div(
            style="display:none;",
            **{"data-shiny-ns": ns_prefix, "data-selection-mode": selection_mode}
        )

    # Output: Viewer mode — inject CSS that hides edit controls for viewers
    @render.ui
    def viewer_mode_ui():
        if not is_viewer:
            return ui.div()
        return ui.tags.style(
            """
            /* === Viewer mode: hide all edit-related controls === */
            /* Toolbar buttons: Save, Approve, Reject */
            #save_btn, #approve_btn, #reject_btn { display: none !important; }
            /* Cell edit popup */
            #cell-edit-popup { display: none !important; }
            /* Disable editable-cell click cursor */
            .editable-cell { cursor: default !important; pointer-events: auto; }
            .editable-cell:hover { background-color: inherit !important; }
            /* Undo buttons in mod log */
            .undo-btn { display: none !important; }
            /* Viewer banner */
            .viewer-banner { display: block !important; }
            """
        )

    # Output: Single-select mode — hide Select All header checkbox
    @render.ui
    def selection_mode_ui():
        if app_config.review_detail_multi_select:
            return ui.div()
        return ui.tags.style(
            """
            /* === Single-select mode: hide select-all checkbox === */
            #select_all_page { display: none !important; }
            """
        )

    # Output: Data summary text
    @render.text
    def data_summary():
        if is_lazy_loading():
            # Use the full dataset count and all known columns
            total = total_rows.get()
            num_cols = len(config.all_columns)
        else:
            df = data.get()
            total = len(df)
            num_cols = len(df.columns)
        return f"{total} rows x {num_cols} columns"
    
    # Output: Stats histogram
    @render.ui
    def stats_histogram():
        # Explicit dependency on mods_log for reactivity
        _ = mods_log.get()
        with tracker.track_render("stats_histogram"):
            counts = _get_status_counts()
            total = sum(counts.values()) or 1
            
            # Get current filter selections
            try:
                selected = list(input.status_filter_multi())
            except:
                selected = list(app_config.status_labels.keys())
            
            # Get configured labels
            labels = app_config.status_labels
            
            bars = []
            for status, count in counts.items():
                pct = (count / total) * 100
                is_checked = status in selected
                bars.append(build_status_histogram_bar(status, count, pct, is_checked, label=labels.get(status)))
        return ui.div(*bars)
    
    # Output: Current preset name
    @render.text
    def current_preset_name():
        return active_preset.get()
    
    # Event: Refresh presets - reload from file and update reactive values
    @reactive.Effect
    @reactive.event(input.refresh_preset)
    def _refresh_presets():
        """Reload presets from file when triggered (no-op when presets disabled)"""
        if not app_config.table.presets_enabled:
            return
        fresh_presets = load_presets(config, display_columns)
        column_presets.set(fresh_presets)
        
        # Also refresh active_columns based on current preset
        current = active_preset.get()
        if current in fresh_presets:
            preset_data = fresh_presets[current]
            if isinstance(preset_data, dict):
                active_columns.set(list(preset_data.get("columns", display_columns)))
                column_widths.set(dict(preset_data.get("widths", {})))
                _columns_layout_trigger.set(_columns_layout_trigger.get() + 1)
    
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
        current = active_columns.get()
        cols = list(current) if current is not None else list(display_columns)
        available = [c for c in all_columns if c not in cols]
        return build_columns_modal_content(cols, available, column_masks=column_masks)
    
    # Handle column order changes from JS
    @reactive.Effect
    @reactive.event(input.column_order)
    def _update_column_order():
        val = input.column_order()
        if isinstance(val, dict):
            # Modal drag — user expects to see result, bump trigger
            new_order = val.get('order')
            if new_order is not None:
                active_columns.set(list(new_order))
                _columns_layout_trigger.set(_columns_layout_trigger.get() + 1)
                return
        # Header drag — update state and re-render body to match new order
        new_order = parse_column_order(val)
        if new_order:
            active_columns.set(list(new_order))
            _columns_layout_trigger.set(_columns_layout_trigger.get() + 1)
    
    # Handle adding a column
    @reactive.Effect
    @reactive.event(input.add_column)
    def _add_column():
        col = parse_column_value(input.add_column())
        if col:
            active_columns.set(add_column_to_list(active_columns.get(), col))
            _columns_layout_trigger.set(_columns_layout_trigger.get() + 1)
    
    # Handle removing a column
    @reactive.Effect
    @reactive.event(input.remove_column)
    def _remove_column():
        col = parse_column_value(input.remove_column())
        if col:
            active_columns.set(remove_column_from_list(active_columns.get(), col))
            _columns_layout_trigger.set(_columns_layout_trigger.get() + 1)
    
    # Handle removing all columns
    @reactive.Effect
    @reactive.event(input.clear_all_columns)
    def _clear_all_columns():
        active_columns.set([])
        _columns_layout_trigger.set(_columns_layout_trigger.get() + 1)
    
    # Handle adding all remaining columns
    @reactive.Effect
    @reactive.event(input.add_all_columns)
    def _add_all_columns():
        active_columns.set(list(all_columns))
        _columns_layout_trigger.set(_columns_layout_trigger.get() + 1)
    
    # Handle sorting a column
    @reactive.Effect
    @reactive.event(input.sort_column)
    def _sort_column():
        val = input.sort_column()
        if val and val.get('col'):
            col = val.get('col')
            direction = val.get('direction', 'asc')
            ascending = (direction == 'asc')
            # In lazy mode the DB handles sorting — skip in-memory sort
            if not is_lazy_loading():
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
        _columns_layout_trigger.set(_columns_layout_trigger.get() + 1)
    
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
            _columns_layout_trigger.set(_columns_layout_trigger.get() + 1)
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
                    _columns_layout_trigger.set(_columns_layout_trigger.get() + 1)
                ui.notification_show(f"Preset '{name}' deleted!", type="message", duration=2)
    
    # Output: Copy column list for copy modal
    @render.ui
    def copy_column_list():
        """Render list of columns available to copy"""
        preset_cols = list(active_columns.get()) or list(display_columns)
        ordered_cols = get_ordered_columns(preset_cols, list(data.get().columns))
        return build_copy_column_buttons(ordered_cols, column_masks=column_masks)

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
    
    # ── Facet filter panels ─────────────────────────────────────────────
    _facet_columns = list(app_config.query.facet_columns)
    _facet_max = int(app_config.query.facet_max_values)

    @render.ui
    def facet_panels_ui():
        """Render sidebar facet panels (checkbox + value‑count bars)."""
        if not _facet_columns:
            return ui.div()

        # Depend on pending_filters so the UI refreshes when selections change
        filters = pending_filters.get()

        with tracker.track_render("facet_panels_ui"):
            # Build value counts map — lazy loading uses DB, traditional uses in‑memory
            vc_map = {}
            selected_map = {}
            for col in _facet_columns:
                if is_lazy_loading() and hasattr(config, 'data_fetcher') and config.data_fetcher:
                    vc_map[col] = config.data_fetcher.get_value_counts(col, limit=_facet_max * 10)
                else:
                    df = data.get()
                    if col in df.columns:
                        counts = df[col].fillna("No value").astype(str).value_counts()
                        vc_map[col] = [(str(v), int(c)) for v, c in counts.head(_facet_max * 10).items()]
                    else:
                        vc_map[col] = []

                # Derive selected from active_filters
                fv = filters.get(col)
                if fv and isinstance(fv, str) and fv.strip() and fv != "all":
                    selected_map[col] = [v.strip() for v in fv.split("\n") if v.strip()]
                elif isinstance(fv, dict) and fv.get("op") == "in":
                    selected_map[col] = [str(v) for v in fv.get("value", [])]
                # else: None → all checked

            result = build_facet_panels(
                _facet_columns, vc_map,
                selected_map=selected_map if selected_map else None,
                max_visible=_facet_max,
                column_masks=column_masks,
            )
        return result

    @reactive.Effect
    @reactive.event(input.facet_filter_change)
    def _handle_facet_filter():
        """Apply facet checkbox selection to pending_filters."""
        val = input.facet_filter_change()
        if not val:
            return
        col = val.get("column")
        fv = val.get("value")  # newline‑delimited string or None
        if not col:
            return
        filters = pending_filters.get().copy()
        if fv is None:
            filters.pop(col, None)
        else:
            filters[col] = fv
        pending_filters.set(filters)
        _filter_panel_trigger.set(_filter_panel_trigger.get() + 1)

    # Output: Dynamic filters UI
    @render.ui
    def dynamic_filters():
        """Render active dynamic filters from pending state"""
        # Only re-render on structural changes (add/remove filter, operator change)
        _filter_panel_trigger.get()
        
        # Detect date columns from schema types (lazy loading) or DataFrame dtypes
        _date_cols = set()
        if is_lazy_loading() and hasattr(config, 'data_fetcher'):
            _date_cols = config.data_fetcher.date_columns
        else:
            df = data.get()
            for col in df.columns:
                if pd.api.types.is_datetime64_any_dtype(df[col]):
                    _date_cols.add(col)
        
        # Read pending_filters without creating a reactive dependency
        with reactive.isolate():
            current_filters = pending_filters.get()
        
        if is_lazy_loading():
            # In lazy mode, data.get() may be empty; pass all known columns
            # and a callback to fetch unique values from DB
            return build_dynamic_filters_panel(
                current_filters, data.get(),
                fix_filter=app_config.fix_filter,
                all_columns=config.all_columns,
                get_unique_values_func=config.data_fetcher.get_unique_values,
                column_masks=column_masks,
                date_columns=_date_cols
            )
        return build_dynamic_filters_panel(current_filters, data.get(), fix_filter=app_config.fix_filter, column_masks=column_masks, date_columns=_date_cols)
    
    # Output: Add filter button (hidden for Default preset)
    @render.ui
    def add_filter_btn_ui():
        """Render the '+' add filter button when filters aren't fixed."""
        if app_config.fix_filter:
            return ui.div()  # Filters are locked by config
        return ui.tags.button(
            "+",
            class_="btn btn-sm btn-outline-primary add-filter-btn",
            onclick="openAddFilterModal(event)",
            style="margin-left: 10px; padding: 2px 8px; font-size: 12px;"
        )
    
    # Output: Available columns for filter modal
    @render.ui
    def available_filter_columns():
        """Render list of columns that can be added as filters"""
        filters = pending_filters.get()
        # In lazy mode, data.get() may have no columns; use config.all_columns
        if is_lazy_loading():
            all_cols = config.all_columns
        else:
            all_cols = list(data.get().columns)
        available_cols = [col for col in all_cols if col not in filters and not col.startswith('_')]
        return build_filter_column_buttons(available_cols, column_masks=column_masks)
    
    # Handle adding a filter
    @reactive.Effect
    @reactive.event(input.add_filter_column)
    def _add_filter():
        if app_config.fix_filter:
            ui.notification_show("Filters are locked by configuration.", type="warning", duration=3)
            return
        col_name = parse_filter_column(input.add_filter_column())
        if col_name:
            pending_filters.set(add_filter(pending_filters.get(), col_name))
            _filter_panel_trigger.set(_filter_panel_trigger.get() + 1)
    
    # Handle removing a filter
    @reactive.Effect
    @reactive.event(input.remove_filter_column)
    def _remove_filter():
        if app_config.fix_filter:
            return  # Filters are locked by config
        col_name = parse_filter_column(input.remove_filter_column())
        if col_name:
            pending_filters.set(remove_filter(pending_filters.get(), col_name))
            _filter_panel_trigger.set(_filter_panel_trigger.get() + 1)
    
    # Handle changing a filter's operator
    @reactive.Effect
    @reactive.event(input.set_filter_operator)
    def _set_filter_operator():
        if app_config.fix_filter:
            return  # Filters are locked by config
        val = input.set_filter_operator()
        if not val:
            return
        col_name = val.get("column")
        op = val.get("op", "in")
        if not col_name:
            return
        filters = pending_filters.get().copy()
        old = filters.get(col_name)
        
        # Read live textarea value first — the user may have edited values
        # before changing the operator (especially for config-defined filters
        # which are now rendered with editable textareas + dropdowns).
        filter_id = f"filter_{col_name}"
        try:
            textarea_val = getattr(input, filter_id)()
            if textarea_val and str(textarea_val).strip():
                existing_values = [v.strip() for v in str(textarea_val).replace(',', '\n').split('\n') if v.strip()]
            else:
                existing_values = []
        except Exception:
            # Textarea not available — fall back to stored filter values
            if isinstance(old, dict) and "op" in old:
                existing_values = old.get("value", [])
                if not isinstance(existing_values, list):
                    existing_values = [existing_values] if existing_values is not None else []
            elif old and str(old).strip() and old != "all":
                existing_values = [v.strip() for v in str(old).replace('\n', ',').replace('\r', ',').split(",") if v.strip()]
            else:
                existing_values = []
        
        if op == "in" and not existing_values:
            # Switch back to simple string filter
            filters[col_name] = "all"
        elif op == "in":
            # Convert back to simple newline-separated string
            filters[col_name] = "\n".join(existing_values)
        else:
            # Store as interactive operator dict
            filters[col_name] = {"op": op, "value": existing_values, "interactive": True}
        
        pending_filters.set(filters)
        _filter_panel_trigger.set(_filter_panel_trigger.get() + 1)
    
    # Apply filter value on blur (user clicked away from textarea)
    @reactive.Effect
    @reactive.event(input.apply_filter_value)
    def _apply_filter_value():
        if app_config.fix_filter:
            return  # Filters are locked by config
        val = input.apply_filter_value()
        if not val:
            return
        col_name = val.get("column")
        raw_value = val.get("value", "")
        if not col_name:
            return
        
        filters = pending_filters.get().copy()
        old = filters.get(col_name)
        
        # Determine if this is a between-type operator filter
        is_between = isinstance(old, dict) and old.get("op") == "between"
        
        # Parse textarea content into values list
        if is_between:
            # For between, preserve positional empty strings (from/to)
            parts = str(raw_value).split('\n') if raw_value is not None else []
            values = [v.strip() for v in parts]
            # Normalize: convert empty strings to None for null-bound semantics
            values = [v if v else None for v in values]
        elif raw_value and str(raw_value).strip():
            values = [v.strip() for v in str(raw_value).replace(',', '\n').split('\n') if v.strip()]
        else:
            values = []
        
        if isinstance(old, dict) and "op" in old:
            # Operator dict filter — preserve op, update value
            op = old["op"]
            old_values = old.get("value", [])
            if not isinstance(old_values, list):
                old_values = [old_values] if old_values is not None else []
            if values != old_values:
                filters[col_name] = {"op": op, "value": values, "interactive": True}
                pending_filters.set(filters)
        else:
            # Simple string filter
            new_val = "\n".join(values) if values else "all"
            if new_val != old:
                filters[col_name] = new_val
                pending_filters.set(filters)
    
    # ---- Apply / Reset Filters (unified action) ----
    @render.ui
    def apply_filters_ui():
        """Always show Apply/Reset buttons."""
        pending = pending_filters.get()
        active = active_filters.get()
        has_changes = pending != active
        return ui.div(
            ui.input_action_button("apply_filters_btn", "Apply Filters", class_="apply-filters-btn" + (" btn-pending" if has_changes else "")),
            ui.input_action_button("reset_filters_btn", "Reset", class_="reset-filters-btn"),
            class_="apply-filters-bar"
        )

    @reactive.Effect
    @reactive.event(input.apply_filters_btn)
    def _apply_filters():
        """Copy pending filters to active filters and reload the table."""
        active_filters.set(pending_filters.get().copy())
        current_page.set(1)

    @reactive.Effect
    @reactive.event(input.reset_filters_btn)
    def _reset_pending_filters():
        """Revert pending filters back to current active filters."""
        pending_filters.set(active_filters.get().copy())
        _filter_panel_trigger.set(_filter_panel_trigger.get() + 1)

    # Output: Pagination controls
    @render.ui
    def pagination_controls():
        """Render pagination controls with rows per page selector"""
        with tracker.track_render("pagination_controls"):
            if is_lazy_loading():
                # In lazy loading mode, use cached filtered count
                total_filtered = _lazy_filtered_count()
            else:
                # Traditional mode: count filtered indices
                filtered_indices = _get_filtered_rows()
                total_filtered = len(filtered_indices)
            
            rows_per_page_val = rows_per_page_value.get()
            rpp_options = app_config.table.rows_per_page_options
            
            if rows_per_page_val == "all":
                result = build_pagination_controls_all(total_filtered, rows_per_page_val, rpp_options)
            else:
                page, total_pages, start_row, end_row = calculate_pagination(total_filtered, rows_per_page_val, current_page.get())
                result = build_pagination_controls_paged(page, total_pages, start_row, end_row, total_filtered, rows_per_page_val, rpp_options)
        return result
    
    # Sync rows_per_page input with reactive value
    @reactive.Effect
    def _sync_rows_per_page():
        try:
            val = input.rows_per_page()
            with reactive.isolate():
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
        # Get filtered count based on mode
        if is_lazy_loading():
            total_filtered = _lazy_filtered_count()
        else:
            filtered_indices = _get_filtered_rows()
            total_filtered = len(filtered_indices)
        
        rows_per_page_val = rows_per_page_value.get()
        if rows_per_page_val != "all":
            rows_per_page = int(rows_per_page_val)
            total_pages = max(1, (total_filtered + rows_per_page - 1) // rows_per_page)
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
        # Get filtered count based on mode
        if is_lazy_loading():
            total_filtered = _lazy_filtered_count()
        else:
            filtered_indices = _get_filtered_rows()
            total_filtered = len(filtered_indices)
        
        rows_per_page_val = rows_per_page_value.get()
        if rows_per_page_val != "all":
            rows_per_page = int(rows_per_page_val)
            total_pages = max(1, (total_filtered + rows_per_page - 1) // rows_per_page)
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
        # Get filtered count based on mode
        if is_lazy_loading():
            total_filtered = _lazy_filtered_count()
        else:
            filtered_indices = _get_filtered_rows()
            total_filtered = len(filtered_indices)
        
        rows_per_page_val = rows_per_page_value.get()
        if rows_per_page_val != "all":
            rows_per_page = int(rows_per_page_val)
            total_pages = max(1, (total_filtered + rows_per_page - 1) // rows_per_page)
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
    
    # Handle clear search button click
    @reactive.Effect
    @reactive.event(input.clear_search_btn)
    def _handle_clear_search():
        ui.update_text("search_input", value="")
        ui.update_select("search_column", selected="all")
        search_state.set({"term": "", "column": "all"})
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

    # Cached page data — only re-fetches when data actually changes
    # (reload trigger, page, filters, sort), NOT on column layout changes.
    @reactive.Calc
    def _cached_page_data():
        """Fetch and cache current page data. Reacts to data-changing triggers only."""
        _ = _table_reload_trigger.get()
        if is_lazy_loading():
            current_df, filt_count, tot_count = _fetch_page_data()
            paginated_indices = list(current_df.index)
            return current_df, paginated_indices, filt_count, tot_count
        else:
            current_df = data.get()
            filtered_indices = _get_filtered_rows()
            paginated_indices = get_paginated_indices(filtered_indices, rows_per_page_value.get(), current_page.get())
            return current_df, paginated_indices, len(filtered_indices), len(current_df)

    # Output: Data table
    @render.ui
    def table_container():
        """Render the editable data table with pagination"""
        # Depend on layout trigger for column reorder/add/remove/preset
        _ = _columns_layout_trigger.get()
        
        with tracker.track_render("table_container"):
            # Use cached page data (no re-fetch on layout-only changes)
            current_df, paginated_indices, filtered_count, total_count = _cached_page_data()
            
            with reactive.isolate():
                _cols = active_columns.get()
                _widths = column_widths.get()
                _edited = edited_cells.get()
            result = build_table_container(
                paginated_indices=paginated_indices,
                current_df=current_df,
                cols=_cols,
                widths=_widths,
                filtered_count=filtered_count,
                total_rows=total_count,
                get_row_status_func=_get_row_status,
                edited_cells=_edited,
                pk_columns=app_config.table.primary_key,
                editable_columns=[] if is_viewer else app_config.table.editable_columns,
                readonly_columns=list(all_columns) if is_viewer else app_config.table.readonly_columns,
                show_status_column=app_config.enable_approval_workflow,
                status_labels=app_config.status_labels,
                column_masks=column_masks,
                cell_click_columns=app_config.table.cell_click_columns,
                status_col_name=getattr(app_config.database, "status_column", None),
                no_tz_display=app_config.table.no_tz_display,
                show_select=app_config.enable_row_select
            )
        return result
    
    # Output: Approval status
    @render.ui
    def approval_status_ui():
        with tracker.track_render("approval_status_ui"):
            result = build_approval_status_banner(approval_status.get(), approval_timestamp.get())
        return result
    
    # Output: Modifications log
    @render.ui
    def modifications_log_ui():
        with tracker.track_render("modifications_log_ui"):
            result = build_modifications_log(mods_log.get())
        return result
    
    # Event: Handle undo modification
    @reactive.Effect
    @reactive.event(input.undo_modification)
    def _handle_undo():
        if not _require_editor("Undo"):
            return
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
        if not _require_editor("Editing"):
            return
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
            # Resolve edit_assignment redirect for tracking
            target_col = col
            for mapping in (app_config.edit_assignment or []):
                if isinstance(mapping, dict) and mapping.get('source') == col:
                    target_col = mapping['target']
                    break
            try:
                row_data = current_df.iloc[row]
                row_pk = {pk: row_data[pk] for pk in pk_cols if pk in current_df.columns}
                pk_tuple = tuple(sorted((k, str(v)) for k, v in row_pk.items()))
                
                # Keep original value from first edit, update current value
                current_edited = edited_cells.get().copy()
                cell_key = (pk_tuple, target_col)
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
            _table_reload_trigger.set(_table_reload_trigger.get() + 1)
            col_label = f"{col} → {target_col}" if target_col != col else col
            ui.notification_show(f"Updated Row {row + 1}, {col_label}", type="message", duration=2)
    
    # Event: Reset cell to original value
    @reactive.Effect
    @reactive.event(input.cell_reset)
    def _handle_cell_reset():
        if not _require_editor("Reset"):
            return
        reset_data = input.cell_reset()
        print(f"DEBUG: cell_reset received: {reset_data}")
        if not reset_data:
            return
        row = reset_data.get("row")
        col = reset_data.get("col")
        original_value = reset_data.get("originalValue", "")
        current_value = reset_data.get("oldValue", "")
        if row is None or not col:
            return

        current_df = data.get()
        current_log = mods_log.get()

        # Resolve edit_assignment
        target_col = col
        for mapping in (app_config.edit_assignment or []):
            if isinstance(mapping, dict) and mapping.get('source') == col:
                target_col = mapping['target']
                break

        # Use perform_cell_edit to write original value back (handles DB + mods table)
        updated_df, updated_log = perform_cell_edit(
            current_df, current_log, row, target_col,
            current_value, original_value, config_instance=config
        )
        data.set(updated_df)
        mods_log.set(updated_log)

        # Remove from edited_cells tracking
        pk_cols = app_config.table.primary_key
        try:
            row_data = current_df.iloc[row]
            row_pk = {pk: row_data[pk] for pk in pk_cols if pk in current_df.columns}
            pk_tuple = tuple(sorted((k, str(v)) for k, v in row_pk.items()))
            current_edited = edited_cells.get().copy()
            cell_key = (pk_tuple, target_col)
            if cell_key in current_edited:
                del current_edited[cell_key]
            edited_cells.set(current_edited)
        except Exception as e:
            print(f"Warning: Could not clear edited cell tracking: {e}")

        save_log_to_file(updated_log, modifications_log_path)
        updated_df.to_json(data_dir / "data_state.json", orient="records", indent=2, default_handler=str)
        ui.notification_show(f"Reset Row {row + 1}, {col} to original value", type="message", duration=2)
    
    # Event: Save modifications to file
    @reactive.Effect
    @reactive.event(input.save_btn)
    def _save_modifications():
        if not _require_editor("Saving"):
            return
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
    
    # === Export Flow: confirm → prepare → download ===
    # Reactive values for export state
    export_state = reactive.Value("idle")  # "idle" | "preparing" | "ready" | "error"
    export_csv_data = reactive.Value("")   # Prepared CSV content
    export_row_count = reactive.Value(0)   # Number of rows in export
    export_type = reactive.Value("all")    # "selected" | "all"
    
    # Step 1: User clicks "I Understand" → triggers data preparation
    @reactive.Effect
    @reactive.event(input.confirm_export)
    def _prepare_export():
        """Prepare export data after user confirms PHI/PII warning."""
        import io
        
        req = input.confirm_export()
        etype = req.get("type", "all") if isinstance(req, dict) else "all"
        export_type.set(etype)
        export_state.set("preparing")
        
        try:
            if etype == "selected":
                # Export selected rows
                current_df = data.get()
                selected_indices = get_selected_row_indices(input, len(current_df))
                
                if not selected_indices:
                    ui.notification_show("Please select rows to export", type="warning", duration=3)
                    export_state.set("idle")
                    return
                
                result_df = current_df.iloc[selected_indices]
            else:
                # Export all filtered/sorted rows
                if is_lazy_loading():
                    result_df = _fetch_all_filtered_data()
                else:
                    current_df = data.get()
                    if current_df.empty:
                        ui.notification_show("No data to export", type="warning", duration=3)
                        export_state.set("idle")
                        return
                    
                    filtered_indices = _get_filtered_rows()
                    if not filtered_indices:
                        ui.notification_show("No rows match current filters", type="warning", duration=3)
                        export_state.set("idle")
                        return
                    
                    result_df = current_df.iloc[filtered_indices].copy()
                    sort_state = current_sort.get()
                    if sort_state.get("column") and sort_state.get("column") in result_df.columns:
                        result_df = sort_dataframe(
                            result_df,
                            sort_state.get("column"),
                            "asc" if sort_state.get("ascending", True) else "desc"
                        )
            
            if result_df.empty:
                ui.notification_show("No data to export", type="warning", duration=3)
                export_state.set("idle")
                return
            
            # Mirror UI display: filter to active columns and preserve their order
            ui_cols = [c for c in active_columns.get() if c in result_df.columns]
            if ui_cols:
                result_df = result_df[ui_cols]
            
            # Apply column masks (display names) to CSV headers
            if column_masks:
                result_df = result_df.rename(columns=column_masks)
            
            output = io.StringIO()
            result_df.to_csv(output, index=False)
            export_csv_data.set(output.getvalue())
            export_row_count.set(len(result_df))
            export_state.set("ready")
        except Exception as e:
            ui.notification_show(f"Export failed: {str(e)}", type="error", duration=5)
            export_state.set("error")
    
    # Step 2: Dynamic UI in modal shows status + download button when ready
    @render.ui
    def export_download_ui():
        """Render export status indicator and download button in the modal."""
        state = export_state.get()
        
        if state == "idle":
            return ui.div()
        
        if state == "preparing":
            return ui.div(
                ui.div(
                    ui.tags.span(
                        class_="spinner-border spinner-border-sm",
                        role="status",
                        style="margin-right: 8px;"
                    ),
                    "Preparing data for download...",
                    style="display: flex; align-items: center; color: #0d6efd; font-weight: 500;"
                ),
                style="margin-top: 16px; padding: 12px; background: #f0f7ff; border-radius: 6px;"
            )
        
        if state == "ready":
            row_count = export_row_count.get()
            etype = export_type.get()
            label = f"selected" if etype == "selected" else "filtered"
            ready_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return ui.div(
                ui.div(
                    ui.tags.span("✅ ", style="font-size: 18px; margin-right: 6px;"),
                    f"Data ready — {row_count} {label} row(s)",
                    ui.tags.span(
                        f" (prepared at {ready_ts})",
                        style="font-weight: 400; font-size: 0.85em; color: #6c757d; margin-left: 4px;"
                    ),
                    style="font-weight: 500; color: #198754; margin-bottom: 10px;"
                ),
                ui.download_button(
                    "export_prepared_btn",
                    "⬇ Download CSV",
                    class_="btn btn-success",
                    style="width: 100%;"
                ),
                style="margin-top: 16px; padding: 12px; background: #f0fff4; border-radius: 6px;"
            )
        
        if state == "error":
            return ui.div(
                "❌ Export failed. Please close and try again.",
                style="margin-top: 16px; padding: 12px; background: #fff0f0; border-radius: 6px; color: #dc3545; font-weight: 500;"
            )
        
        return ui.div()
    
    # Step 3: Actual download handler — serves the prepared CSV
    def _get_export_filename():
        """Generate dynamic filename based on app title and export type."""
        import re
        title = app_config.app_title or "data"
        safe_title = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_')
        etype = export_type.get()
        suffix = "selected" if etype == "selected" else "filtered"
        return f"{safe_title}_data_{suffix}.csv"
    
    @render.download(filename=_get_export_filename)
    async def export_prepared_btn():
        """Serve the prepared CSV data."""
        csv_content = export_csv_data.get()
        if not csv_content:
            return
        row_count = export_row_count.get()
        ui.notification_show(f"Exported {row_count} row(s)", type="message", duration=2)
        # Reset export state after download
        export_state.set("idle")
        export_csv_data.set("")
        yield csv_content
    
    # Event: Reload data
    @reactive.Effect
    @reactive.event(input.reload_btn)
    def _reload_data():
        if is_lazy_loading():
            # In lazy loading mode, only refresh row count (schema doesn't change mid-session)
            config._data_fetcher._refresh_count()
            total_rows.set(config.data_fetcher.total_count)
            # Data will be re-fetched on next table render
        else:
            # Traditional mode: reload all data
            fresh_data = load_data_from_source()
            data.set(fresh_data)
        mods_log.set(load_modifications_log())
        ui.notification_show("Data reloaded from database.", type="message", duration=3)
    
    # Event: Approve rows
    @reactive.Effect
    @reactive.event(input.approve_btn)
    def _approve_data():
        if not _require_editor("Approval"):
            return
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
            # Build row data map for approval_assignment column copies
            row_data_map = {}
            if app_config.approval_assignment:
                pk_cols = app_config.table.primary_key
                for idx in selected_indices:
                    try:
                        row = current_df.loc[idx]
                        pk = {pk: row[pk] for pk in pk_cols if pk in current_df.columns}
                        pk_key = tuple(sorted(pk.items()))
                        row_data_map[pk_key] = row
                    except Exception:
                        pass
            _save_status_to_db(selected_pks, "approval", row_data_map)
        
        # Force-sync in-memory DataFrame so the status column reflects the change immediately
        internal_key = "approved"
        status_value = app_config.status_values.get(internal_key, internal_key)
        updated_df = current_df.copy()
        status_col = getattr(app_config.database, "status_column", None)
        for idx in selected_indices:
            if status_col and status_col in updated_df.columns:
                updated_df.at[updated_df.index[idx], status_col] = status_value
            if "_mod_status" in updated_df.columns:
                updated_df.at[updated_df.index[idx], "_mod_status"] = internal_key
        data.set(updated_df)
        
        mods_log.set(log)
        _table_reload_trigger.set(_table_reload_trigger.get() + 1)
        ui.notification_show(f"{len(selected_pks)} row(s) APPROVED!", type="message", duration=2)
    
    # Event: Reject rows
    @reactive.Effect
    @reactive.event(input.reject_btn)
    def _reject_data():
        if not _require_editor("Rejection"):
            return
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
        
        # Force-sync in-memory DataFrame so the status column reflects the change immediately
        internal_key = "rejected"
        status_value = app_config.status_values.get(internal_key, internal_key)
        updated_df = current_df.copy()
        status_col = getattr(app_config.database, "status_column", None)
        for idx in selected_indices:
            if status_col and status_col in updated_df.columns:
                updated_df.at[updated_df.index[idx], status_col] = status_value
            if "_mod_status" in updated_df.columns:
                updated_df.at[updated_df.index[idx], "_mod_status"] = internal_key
        data.set(updated_df)
        
        mods_log.set(log)
        _table_reload_trigger.set(_table_reload_trigger.get() + 1)
        ui.notification_show(f"{len(selected_pks)} row(s) REJECTED!", type="message", duration=2)
    
    # Event: Clear approval
    @reactive.Effect
    @reactive.event(input.clear_approval_btn)
    def _clear_approval():
        approval_status.set(None)
        approval_timestamp.set(None)

    # ------------------------------------------------------------------
    # Synthesis handlers
    # ------------------------------------------------------------------

    @render.ui
    def synthesis_query_preview():
        """Render the synthesis SQL query as a read-only code block."""
        if not enable_synthesis:
            return ui.div()
        query_text = app_config.synthesis.query or "(no query configured)"
        return ui.tags.pre(
            ui.tags.code(query_text),
            class_="synthesis-query-code"
        )

    @render.ui
    def synthesis_mode_banner():
        """Show a banner when the user is viewing synthesized data."""
        if not synthesis_active.get():
            return ui.div()
        label = app_config.synthesis.label or "Synthesis"
        return ui.div(
            ui.tags.i(class_="fa fa-flask", style="margin-right: 6px;"),
            f"You are viewing the {label} result table. ",
            "Filters and search operate on the synthesized data. ",
            "Click \"Exit Synthesis Mode\" to return to the original table.",
            class_="synthesis-mode-banner"
        )

    @render.ui
    def synthesis_status():
        """Show progress / error / success status inside the modal."""
        if synthesis_running.get():
            return ui.div(
                ui.div(class_="synthesis-spinner"),
                ui.p("Synthesizing report, please wait…",
                     style="margin-top: 10px; font-weight: 500;"),
                ui.p("This may take 3–5 minutes.",
                     style="color: #666; font-size: 13px;"),
                class_="synthesis-status-area"
            )
        err = synthesis_error.get()
        if err:
            return ui.div(
                ui.p("Transform failed:", style="color: #dc3545; font-weight: 600;"),
                ui.tags.pre(err, style="color: #dc3545; font-size: 12px; white-space: pre-wrap;"),
                class_="synthesis-status-area"
            )
        if synthesis_active.get():
            synth_df = synthesis_data.get()
            was_cached = synthesis_cached.get()
            cache_note = " (served from cache)" if was_cached else " (freshly generated)"
            ttl = app_config.synthesis.ttl_minutes
            # Build a live countdown driven by inline JS (guaranteed to run on Shiny render)
            countdown_html = ""
            try:
                import time as _srv_time
                cache_epoch = config._synthesis_age_cache_time
                if cache_epoch <= 0:
                    age_min = config._get_synthesis_age_minutes()
                    if age_min is not None:
                        cache_epoch = _srv_time.time() - age_min * 60
                    else:
                        cache_epoch = _srv_time.time()
                countdown_html = f"""
                <p style="color: #555; font-size: 13px; margin-top: 4px;">
                  <i class="fa fa-clock-o" style="margin-right: 5px;"></i>
                  <span id="synthesis-countdown"></span>
                </p>
                <script>
                (function() {{
                  var created = {cache_epoch:.3f};
                  var ttl = {ttl};
                  var el = document.getElementById('synthesis-countdown');
                  if (!el) return;
                  function fmt(sec) {{
                    sec = Math.max(0, Math.round(sec));
                    if (sec < 60) return sec + 's';
                    var m = Math.floor(sec / 60), s = sec % 60;
                    return m + 'm ' + (s < 10 ? '0' : '') + s + 's';
                  }}
                  function tick() {{
                    var age = Date.now() / 1000 - created;
                    var parts = ['Cache age: ' + fmt(age)];
                    if (ttl > 0) {{
                      var rem = ttl * 60 - age;
                      parts.push(rem > 0 ? 'expires in ' + fmt(rem) : 'expired');
                    }}
                    el.textContent = parts.join(' \\u00b7 ');
                  }}
                  tick();
                  var iv = setInterval(tick, 1000);
                  var obs = new MutationObserver(function() {{
                    if (!document.getElementById('synthesis-countdown')) {{
                      clearInterval(iv); obs.disconnect();
                    }}
                  }});
                  obs.observe(el.parentNode.parentNode, {{ childList: true, subtree: true }});
                }})();
                </script>
                """
            except Exception as _ce:
                print(f"[Synthesis] Countdown error: {_ce}")
            status_children = [
                ui.p("Transform complete", ui.tags.br(),
                     f"{len(synth_df):,} rows returned{cache_note}.",
                     style="color: #28a745; font-weight: 500;"),
            ]
            if countdown_html:
                status_children.append(ui.HTML(countdown_html))
            status_children.append(
                ui.p("Close this modal to interact with the synthesized table.",
                     style="color: #666; font-size: 13px;")
            )
            # Toggle footer buttons: hide Run, show Regen + Exit
            status_children.append(ui.HTML("""<script>
              (function(){
                var r=document.querySelector('[id$="synthesis_run_btn"]');
                var g=document.querySelector('[id$="synthesis_regen_btn"]');
                if(r) r.style.display='none';
                if(g) g.style.display='';
              })();
            </script>"""))
            return ui.div(*status_children, class_="synthesis-status-area")
        # Not active — show cache info and what "Run Transform" will do
        # Reset footer buttons: show Run, hide Regen + Exit
        _btn_reset = ui.HTML("""<script>
          (function(){
            var r=document.querySelector('[id$="synthesis_run_btn"]');
            var g=document.querySelector('[id$="synthesis_regen_btn"]');
            if(r) r.style.display='';
            if(g) g.style.display='none';
          })();
        </script>""")
        if enable_synthesis:
            try:
                table_exists = config.check_synthesis_table_exists()
                ttl = app_config.synthesis.ttl_minutes
                if table_exists:
                    age = config._get_synthesis_age_minutes()
                    if age is not None:
                        age_text = f"{age:.0f} min" if age >= 1 else f"{age * 60:.0f}s"
                        ttl_text = f"TTL: {ttl} min." if ttl > 0 else ""
                        return ui.div(
                            _btn_reset,
                            ui.p(
                                ui.tags.i(class_="fa fa-database", style="margin-right: 6px; color: #28a745;"),
                                f"Cached result available — {age_text} old. {ttl_text}",
                                style="color: #28a745; font-size: 13px; font-weight: 500;"
                            ),
                            ui.p(
                                'Click "Run Transform" to load the cached table instantly.',
                                style="color: #666; font-size: 13px;"
                            ),
                            class_="synthesis-status-area"
                        )
                    else:
                        return ui.div(
                            _btn_reset,
                            ui.p(
                                ui.tags.i(class_="fa fa-database", style="margin-right: 6px; color: #17a2b8;"),
                                "Cached result table exists.",
                                style="color: #17a2b8; font-size: 13px; font-weight: 500;"
                            ),
                            ui.p(
                                'Click "Run Transform" to load it.',
                                style="color: #666; font-size: 13px;"
                            ),
                            class_="synthesis-status-area"
                        )
                else:
                    ttl_note = f" Result will be cached for {ttl} min." if ttl > 0 else ""
                    return ui.div(
                        _btn_reset,
                        ui.p(
                            ui.tags.i(class_="fa fa-info-circle", style="margin-right: 6px; color: #6c757d;"),
                            "No cached result.",
                            style="color: #6c757d; font-size: 13px; font-weight: 500;"
                        ),
                        ui.p(
                            f'Click "Run Transform" to execute the synthesis query and create the matview.{ttl_note}',
                            style="color: #666; font-size: 13px;"
                        ),
                        class_="synthesis-status-area"
                    )
            except Exception:
                pass
        return ui.div()

    @reactive.Effect
    @reactive.event(input.synthesis_run_btn)
    async def _run_synthesis():
        """Execute the synthesis transform (async to keep UI responsive)."""
        import asyncio
        if not enable_synthesis:
            return
        synthesis_running.set(True)
        synthesis_error.set("")
        try:
            # run_synthesis returns (df, was_cached)
            result_df, was_cached = await asyncio.to_thread(config.run_synthesis)
            synthesis_data.set(result_df)
            synthesis_cached.set(was_cached)
            synthesis_active.set(True)
            # Switch the main table to show synthesis data
            data.set(result_df)
            total_rows.set(len(result_df))
            filtered_row_count.set(len(result_df))
            current_page.set(1)
            # Activate DataFetcher for SQL-level filtering on matview
            config.activate_synthesis_fetcher(config.get_synthesis_table_name())
            # Sync active_columns from the fetcher
            if config.all_columns:
                active_columns.set(list(config.all_columns))
            cache_msg = " (cached)" if was_cached else ""
            # Bump reload trigger to force table_container re-render
            _table_reload_trigger.set(_table_reload_trigger.get() + 1)
            ui.notification_show(
                f"Synthesis complete{cache_msg} — {len(result_df):,} rows",
                type="message", duration=4
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            synthesis_error.set(str(e))
        finally:
            synthesis_running.set(False)

    @reactive.Effect
    @reactive.event(input.synthesis_regen_btn)
    async def _regen_synthesis():
        """Force-recreate the synthesis view (CREATE OR REPLACE VIEW)."""
        import asyncio
        if not enable_synthesis:
            return
        synthesis_running.set(True)
        synthesis_error.set("")
        try:
            result_df, _ = await asyncio.to_thread(config.run_synthesis, force=True)
            synthesis_data.set(result_df)
            synthesis_cached.set(False)
            synthesis_active.set(True)
            data.set(result_df)
            total_rows.set(len(result_df))
            filtered_row_count.set(len(result_df))
            current_page.set(1)
            # Activate DataFetcher for SQL-level filtering on matview
            config.activate_synthesis_fetcher(config.get_synthesis_table_name())
            # Sync active_columns from the fetcher
            if config.all_columns:
                active_columns.set(list(config.all_columns))
            # Bump reload trigger to force table_container re-render
            _table_reload_trigger.set(_table_reload_trigger.get() + 1)
            ui.notification_show(
                f"Synthesis regenerated — {len(result_df):,} rows",
                type="message", duration=4
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            synthesis_error.set(str(e))
        finally:
            synthesis_running.set(False)

    @reactive.Effect
    @reactive.event(input.synthesis_exit_btn)
    def _exit_synthesis():
        """Exit synthesis mode and restore the original data table."""
        synthesis_active.set(False)
        synthesis_data.set(pd.DataFrame())
        synthesis_error.set("")
        # Deactivate synthesis DataFetcher (restores original table or removes fetcher)
        config.deactivate_synthesis_fetcher()
        # Reload original data
        if _initial_lazy_loading:
            data.set(config.df)
            total_rows.set(config.total_row_count)
            filtered_row_count.set(config.total_row_count)
        else:
            fresh = load_data_from_source() if app_config.database.enabled else df_original.copy()
            data.set(fresh)
            total_rows.set(len(fresh))
            filtered_row_count.set(len(fresh))
        current_page.set(1)
        ui.notification_show("Returned to original table", type="message", duration=3)

    # ── Review Detail action ──────────────────────────────────
    @reactive.Effect
    @reactive.event(input.review_detail_btn)
    def _review_detail():
        """Emit review_detail event with selected row PK(s)."""
        current_df = data.get()
        indices = get_selected_row_indices(input, len(current_df))
        if not indices:
            ui.notification_show("Select a row first", type="warning", duration=3)
            return
        if app_config.review_detail_multi_select:
            # Multi-select: emit all selected rows
            pks = _get_selected_pks(indices, current_df)
            if not pks:
                ui.notification_show("Could not resolve primary keys", type="error", duration=3)
                return
            _emit(
                "review_detail",
                pk=pks,
                source_table=app_config.database.data_table,
                row_indices=indices,
            )
            ui.notification_show(f"Review Detail: {len(pks)} row(s)", type="message", duration=2)
        else:
            # Single-select: emit first selected row only
            pks = _get_selected_pks([indices[0]], current_df)
            if not pks:
                ui.notification_show("Could not resolve primary key", type="error", duration=3)
                return
            _emit(
                "review_detail",
                pk=pks[0],
                source_table=app_config.database.data_table,
                row_index=indices[0],
            )
            ui.notification_show(f"Review Detail: {pks[0]}", type="message", duration=2)

    # ── Cell click event ──────────────────────────────────────
    @reactive.Effect
    @reactive.event(input.cell_click)
    def _cell_click():
        """Emit cell_click event when a clickable-cell is clicked."""
        payload = input.cell_click()
        if not payload or not app_config.table.cell_click_columns:
            return
        col = payload.get("col", "")
        value = payload.get("value", "")
        pk = payload.get("pk", {})
        _emit(
            "cell_click",
            pk=pk,
            column=col,
            value=value,
            source_table=app_config.database.data_table,
        )
        ui.notification_show(f"Cell click: {col} = {value}", type="message", duration=3)

    # ── Return public API ─────────────────────────────────────
    return WidgetAPI(
        events=_emitter.events,
        data=data,
        active_columns=active_columns,
        widget_id=_emitter.widget_id,
        config=config,
    )