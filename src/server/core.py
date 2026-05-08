"""
Server core — create_server() setup, reactive values, and sub-module wiring.
"""
import time as _t
import os

from shiny import render, ui, reactive
from shiny.types import SilentException, SilentCancelOutputException
import pandas as pd
from datetime import datetime

from ..utils import (
    load_presets,
    load_active_preset,
    get_latest_approval_status,
    get_row_status,
    get_filtered_rows,
    build_status_histogram_bar,
    build_table_container,
    sort_dataframe,
    get_paginated_indices,
    get_selected_row_indices,
    get_preset_columns_and_widths,
)
from ..utils import tracker
from ..commute import EventEmitter, WidgetAPI
from .context import ServerContext
from .filters import register_filters
from .pagination import register_pagination
from .presets import register_presets
from .edits import register_edits
from .export import register_export
from .synthesis import register_synthesis


def create_server(input, output, session, config_path: str = "app_config.json"):  # noqa: ARG001
    """
    Server logic for the Shiny app.

    Args:
        config_path: Path to the config JSON file for this widget instance

    Returns:
        WidgetAPI: Public API object with .events, .data, .active_columns
    """
    # Get username
    posit_username = getattr(session, 'user', None) or os.environ.get('SHINY_USER') or 'default_user'
    safe_username = "".join(c if c.isalnum() else "_" for c in posit_username).lower()
    user_email = posit_username if '@' in posit_username else os.environ.get('LP_LIMS_USER', '')
    print(f"[Session] User: {posit_username} (safe: {safe_username}, email: {user_email})")

    # Load config instance
    _server_t0 = _t.time()
    from ..config.config_instance import load_config_instance, QueryParams
    print(f"[Config] Loading config from {config_path} for user: {safe_username}")
    config = load_config_instance(config_path, username=safe_username, user_email=user_email)
    _server_t1 = _t.time()
    print(f"[Timing] load_config_instance: {(_server_t1 - _server_t0)*1000:.0f}ms")

    # Initialise tracker mode
    tracker.init(config.app_config.tracker_mode)

    # Extract config values
    data_dir = config.data_dir
    modifications_log_path = config.modifications_log_path
    df_original = config.df
    display_columns = config.display_columns
    all_columns = config.all_columns
    app_config = config.app_config
    column_masks = app_config.table.column_masks or None

    # Resolve permission role
    _perm = app_config.permissions
    user_role = _perm.user_roles.get(safe_username, _perm.default_role)
    is_viewer = user_role == "viewer" or app_config.read_only
    print(f"[Permissions] User={safe_username} | role={user_role} | default_role={_perm.default_role} | user_roles={_perm.user_roles} | is_viewer={is_viewer} | read_only={app_config.read_only}")

    def _require_editor(action: str = "This action") -> bool:
        if is_viewer:
            print(f"[Permissions] BLOCKED: {action} denied for viewer {safe_username}")
            ui.notification_show(f"{action} requires editor permissions.", type="warning", duration=3)
            return False
        return True

    # ── Event emitter (commute layer) ──────────────────────────
    _emitter = EventEmitter(widget_id=config_path)

    def _emit(action: str, **payload) -> None:
        _emitter.emit(action, **payload)

    # Create local functions that use this config instance
    def load_modifications_log():
        return config.load_modifications_log()

    def load_data_from_source():
        return config.reload_data()

    def save_ui_state(**kwargs):
        if not app_config.state.persist_state:
            return False
        return config.save_ui_state(**kwargs)

    def load_ui_state():
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

    # Load UI state
    _t2 = _t.time()
    ui_state = load_ui_state()
    print(f"[Timing] load_ui_state: {(_t.time() - _t2)*1000:.0f}ms")

    # Lazy loading check
    _initial_lazy_loading = config.is_lazy_loading

    def is_lazy_loading():
        return config.is_lazy_loading

    # ----- Auto-synthesis: try cached synthesis table on startup -----
    _synthesis_autoloaded = False
    _synthesis_needs_generate = False
    if app_config.enable_synthesis and app_config.synthesis.query:
        if app_config.synthesis.mode == "query":
            # Direct query mode — no view caching, always generate on startup
            print("[Synthesis] Direct query mode — will auto-generate after startup")
            _synthesis_needs_generate = True
        else:
            try:
                if config.check_synthesis_table_exists():
                    result_table = config.get_synthesis_table_name()
                    if '.' in result_table:
                        config._schemas_verified.add(result_table.split('.', 1)[0])
                    age = config._get_synthesis_age_minutes()
                    if age is None:
                        from ..config.config_instance import SqlTableName
                        config._stamp_synthesis_comment(SqlTableName(result_table), _t.time())
                        age = 0.0
                    ttl = app_config.synthesis.ttl_minutes
                    if ttl > 0 and age > ttl:
                        print(f"[Synthesis] Matview expired ({age:.0f} min > {ttl} min TTL) — will refresh after startup")
                        _synthesis_needs_generate = True
                    else:
                        initial_df = config._read_synthesis_table(result_table)
                        total_row_count = len(initial_df)
                        _synthesis_autoloaded = True
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

    # Determine initial data
    if _synthesis_autoloaded:
        pass  # initial_df already set
    elif _synthesis_needs_generate:
        initial_df = pd.DataFrame()
        total_row_count = 0
        print("[Synthesis] Skipping main table load — will auto-generate")
    elif _initial_lazy_loading:
        initial_df = config.df
        total_row_count = config.total_row_count
        print(f"[Lazy Loading] Enabled. Total rows in DB: {total_row_count}")
    else:
        initial_df = config.df.copy() if app_config.database.enabled else df_original.copy()
        total_row_count = len(initial_df)

    # Apply initial sorting (non-lazy only)
    if not _initial_lazy_loading and ui_state.get("sort_column"):
        sort_col = ui_state["sort_column"]
        sort_asc = ui_state.get("sort_ascending", True)
        if isinstance(sort_col, list):
            if isinstance(sort_asc, list):
                direction = ["asc" if a else "desc" for a in sort_asc]
            else:
                direction = ["asc" if sort_asc else "desc"] * len(sort_col)
        else:
            direction = "asc" if sort_asc else "desc"
        initial_df = sort_dataframe(initial_df, sort_col, direction)

    # ── Reactive values ─────────────────────────────────────────────────
    data = reactive.Value(initial_df)
    total_rows = reactive.Value(total_row_count)
    filtered_row_count = reactive.Value(total_row_count)
    edited_cells = reactive.Value(config.get_edited_cells())
    current_sort = reactive.Value({
        "column": ui_state.get("sort_column"),
        "ascending": ui_state.get("sort_ascending", True)
    })
    _t3 = _t.time()
    mods_log = reactive.Value(load_modifications_log())
    print(f"[Timing] load_modifications_log: {(_t.time() - _t3)*1000:.0f}ms")

    initial_status, initial_timestamp = get_latest_approval_status(load_modifications_log())
    approval_status = reactive.Value(initial_status)
    approval_timestamp = reactive.Value(initial_timestamp)

    _t4 = _t.time()
    if app_config.table.presets_enabled:
        loaded_presets = load_presets(config, display_columns)
    else:
        loaded_presets = {"Default": {"columns": list(display_columns), "widths": {}}}
    column_presets = reactive.Value(loaded_presets)
    print(f"[Timing] load_presets: {(_t.time() - _t4)*1000:.0f}ms")

    if app_config.table.presets_enabled:
        initial_active_preset = load_active_preset(config)
        print(f"[Preset] Active preset for {safe_username}: {initial_active_preset}")
    else:
        initial_active_preset = "Default"
    if initial_active_preset not in loaded_presets:
        initial_active_preset = "Default"
    active_preset = reactive.Value(initial_active_preset)

    saved_preset = loaded_presets.get(initial_active_preset, loaded_presets.get("Default", {"columns": list(display_columns), "widths": {}}))
    initial_columns = saved_preset.get("columns", list(display_columns)) if isinstance(saved_preset, dict) else list(saved_preset)
    initial_widths = saved_preset.get("widths", {}) if isinstance(saved_preset, dict) else {}
    active_columns = reactive.Value(list(initial_columns))
    column_widths = reactive.Value(dict(initial_widths))
    _columns_layout_trigger = reactive.Value(0)

    initial_rows_per_page = str(ui_state.get("rows_per_page", 25))
    current_page = reactive.Value(1)
    rows_per_page_value = reactive.Value(initial_rows_per_page)
    print(f"[Timing] create_server total setup: {(_t.time() - _server_t0)*1000:.0f}ms")

    _first_rows_per_page_sync = {"done": False}
    _first_search_filter_sync = {"done": False}

    # ── Default filters ─────────────────────────────────────────────────
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
        result = {}
        for col, values in config_filters.items():
            if col.startswith("_"):
                continue
            if isinstance(values, dict) and "op" in values:
                raw_op = values.get("op", "in")
                normalised_op = _OP_LABEL_TO_KEY.get(raw_op.lower(), raw_op) if isinstance(raw_op, str) else raw_op
                result[col] = {**values, "op": normalised_op}
            elif isinstance(values, list):
                result[col] = "\n".join(str(v) for v in values)
            else:
                result[col] = str(values) if values else ""
        return result

    initial_filters = _convert_default_filters(app_config.query.default_filters) if hasattr(app_config, 'query') and app_config.query.default_filters else {}
    active_filters = reactive.Value(initial_filters)
    pending_filters = reactive.Value(initial_filters.copy())
    _filter_panel_trigger = reactive.Value(0)

    search_state = reactive.Value({"term": "", "column": "all"})

    # Synthesis state
    synthesis_active = reactive.Value(_synthesis_autoloaded)
    synthesis_running = reactive.Value(False)
    synthesis_data = reactive.Value(initial_df if _synthesis_autoloaded else pd.DataFrame())
    synthesis_error = reactive.Value("")
    synthesis_cached = reactive.Value(_synthesis_autoloaded)
    enable_synthesis = app_config.enable_synthesis
    _table_reload_trigger = reactive.Value(0)

    if _synthesis_autoloaded:
        config.activate_synthesis_fetcher(config.get_synthesis_table_name())

    # Export state
    export_state = reactive.Value("idle")
    export_csv_data = reactive.Value("")
    export_row_count = reactive.Value(0)
    export_type = reactive.Value("all")

    # ── Helper functions ────────────────────────────────────────────────

    def _get_row_status(row_idx):
        current_df = data.get()
        current_log = mods_log.get()
        if "_mod_status" in current_df.columns:
            try:
                db_status = str(current_df.loc[row_idx, "_mod_status"]).strip().lower()
                if db_status in ("edited", "approved", "rejected"):
                    return db_status
                if db_status == "approval":
                    return "approved"
                elif db_status == "rejection":
                    return "rejected"
                elif db_status == "field_modification":
                    return "edited"
                reverse = {v.lower(): k for k, v in app_config.status_values.items()}
                mapped = reverse.get(db_status, db_status)
                if mapped in ("edited", "approved", "rejected"):
                    return mapped
            except:
                pass
            return "unprocessed"
        try:
            pk_cols = app_config.table.primary_key
            row = current_df.loc[row_idx]
            row_pk = {pk: row[pk] for pk in pk_cols if pk in current_df.columns}
        except:
            row_pk = None
        return get_row_status(row_idx, current_log, row_pk)

    def _get_filtered_rows():
        current_df = data.get()
        search = search_state.get()
        try:
            status_filters = list(input.status_filter_multi())
        except (SilentException, SilentCancelOutputException):
            raise
        except:
            status_filters = list(app_config.status_labels.keys())
        return get_filtered_rows(
            df=current_df,
            active_columns=active_columns.get(),
            search_term=search.get("term", ""),
            status_filters=status_filters,
            column_filters=active_filters.get(),
            get_row_status_func=_get_row_status,
            search_column=search.get("column", "all")
        )

    def _build_query_params(page=None, page_size=None, for_export=False):
        search = search_state.get()
        sort_state = current_sort.get()
        try:
            status_filters = list(input.status_filter_multi())
        except (SilentException, SilentCancelOutputException):
            raise
        except:
            status_filters = list(app_config.status_labels.keys())
        filters_dict = {}
        for col, val in active_filters.get().items():
            if isinstance(val, dict) and "op" in val:
                filters_dict[col] = val
            elif val and str(val).strip() and val != "all":
                values = [v.strip() for v in str(val).split("\n") if v.strip()]
                if values:
                    filters_dict[col] = values if len(values) > 1 else values[0]
        if for_export:
            actual_page_size = 1000000
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
        if not is_lazy_loading():
            return 0
        fetcher = config.data_fetcher
        if fetcher is None:
            return 0
        params = _build_query_params()
        return fetcher.get_filtered_count(params)

    def _fetch_page_data():
        if is_lazy_loading():
            fetcher = config.data_fetcher
            if fetcher is None:
                return pd.DataFrame(), 0, 0
            params = _build_query_params()
            fetched_df = fetcher.fetch_page(params)
            return fetched_df, _lazy_filtered_count(), total_rows.get()
        else:
            current_df = data.get()
            filtered_indices = _get_filtered_rows()
            return current_df, len(filtered_indices), len(current_df)

    def _fetch_all_filtered_data():
        if is_lazy_loading():
            fetcher = config.data_fetcher
            if fetcher is None:
                return pd.DataFrame()
            params = _build_query_params(for_export=True)
            return fetcher.fetch_all_filtered(params)
        else:
            current_df = data.get()
            filtered_indices = _get_filtered_rows()
            return current_df.loc[filtered_indices] if filtered_indices else current_df

    @reactive.Calc
    def _cached_page_data():
        _ = _table_reload_trigger.get()
        if is_lazy_loading():
            current_df, filt_count, tot_count = _fetch_page_data()
            return current_df, list(current_df.index), filt_count, tot_count
        else:
            current_df = data.get()
            filtered_indices = _get_filtered_rows()
            paginated_indices = get_paginated_indices(filtered_indices, rows_per_page_value.get(), current_page.get())
            return current_df, paginated_indices, len(filtered_indices), len(current_df)

    def _get_page_selection():
        page_df, paginated_indices, _, _ = _cached_page_data()
        max_idx = max(paginated_indices) + 1 if paginated_indices else 0
        check_range = max(max_idx, len(data.get()) if not is_lazy_loading() else max_idx)
        selected = get_selected_row_indices(input, check_range)
        return page_df, selected

    def _get_selected_pks(row_indices, current_df):
        pk_cols = app_config.table.primary_key
        pks = []
        for row_idx in row_indices:
            try:
                row = current_df.loc[row_idx]
                row_pk = {pk: row[pk] for pk in pk_cols if pk in current_df.columns}
                if row_pk:
                    pks.append(row_pk)
            except Exception as e:
                print(f"Warning: Could not get PK for row {row_idx}: {e}")
        return pks

    def _save_status_to_db(selected_pks, mod_type: str, row_data_map: dict = None):
        internal_key = "approved" if mod_type == "approval" else "rejected"
        status_value = app_config.status_values.get(internal_key, internal_key)
        assignment = app_config.approval_assignment if mod_type == "approval" else {}
        entries = []
        for row_pk in selected_pks:
            entry = {"row_pk": row_pk, "status_value": status_value, "mod_type": mod_type, "assignments": []}
            if assignment and row_data_map:
                pk_key = tuple(sorted(row_pk.items()))
                row = row_data_map.get(pk_key)
                if row is not None:
                    for src_col, tgt_col in assignment.items():
                        src_val = row[src_col] if src_col in row.index else None
                        new_val = str(src_val) if src_val is not None else None
                        entry["assignments"].append((tgt_col, new_val))
            entries.append(entry)
        try:
            config.batch_save_status(entries)
            print(f"DEBUG: Batch {mod_type} saved {len(entries)} rows")
        except Exception as e:
            print(f"Warning: Batch {mod_type} save failed: {e}")

    def _get_status_counts():
        if is_lazy_loading():
            params = _build_query_params()
            from ..config.config_instance import QueryParams as QP
            count_params = QP(
                filters=params.filters,
                search_term=params.search_term,
                search_column=params.search_column,
                sort_column=params.sort_column,
                sort_ascending=params.sort_ascending,
                page=1, page_size=1,
                status_filters=list(app_config.status_labels.keys())
            )
            counts = config.data_fetcher.get_status_counts(count_params)
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
        current_df = data.get()
        _ = mods_log.get()
        all_statuses = list(app_config.status_labels.keys())
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
        from ..utils import get_modification_summary
        pk_cols = app_config.table.primary_key if hasattr(app_config.table, 'primary_key') else None
        return get_modification_summary(data.get(), mods_log.get(), pk_cols)

    # ── Build context and register sub-modules ──────────────────────────
    ctx = ServerContext(
        input=input,
        output=output,
        session=session,
        config=config,
        app_config=app_config,
        safe_username=safe_username,
        user_email=user_email,
        is_viewer=is_viewer,
        display_columns=display_columns,
        all_columns=all_columns,
        column_masks=column_masks,
        data_dir=data_dir,
        modifications_log_path=modifications_log_path,
        data=data,
        total_rows=total_rows,
        filtered_row_count=filtered_row_count,
        edited_cells=edited_cells,
        current_sort=current_sort,
        mods_log=mods_log,
        approval_status=approval_status,
        approval_timestamp=approval_timestamp,
        column_presets=column_presets,
        active_preset=active_preset,
        active_columns=active_columns,
        column_widths=column_widths,
        current_page=current_page,
        rows_per_page_value=rows_per_page_value,
        active_filters=active_filters,
        pending_filters=pending_filters,
        search_state=search_state,
        _filter_panel_trigger=_filter_panel_trigger,
        _columns_layout_trigger=_columns_layout_trigger,
        _table_reload_trigger=_table_reload_trigger,
        synthesis_active=synthesis_active,
        synthesis_running=synthesis_running,
        synthesis_data=synthesis_data,
        synthesis_error=synthesis_error,
        synthesis_cached=synthesis_cached,
        enable_synthesis=enable_synthesis,
        export_state=export_state,
        export_csv_data=export_csv_data,
        export_row_count=export_row_count,
        export_type=export_type,
        is_lazy_loading=is_lazy_loading,
        load_modifications_log=load_modifications_log,
        load_data_from_source=load_data_from_source,
        save_ui_state=save_ui_state,
        _require_editor=_require_editor,
        _get_row_status=_get_row_status,
        _get_status_counts=_get_status_counts,
        _get_modification_summary=_get_modification_summary,
        _get_filtered_rows=_get_filtered_rows,
        _build_query_params=_build_query_params,
        _lazy_filtered_count=_lazy_filtered_count,
        _fetch_page_data=_fetch_page_data,
        _fetch_all_filtered_data=_fetch_all_filtered_data,
        _cached_page_data=_cached_page_data,
        _get_page_selection=_get_page_selection,
        _get_selected_pks=_get_selected_pks,
        _save_status_to_db=_save_status_to_db,
        _save_presets=lambda presets_dict: None,  # set after register_presets
        _save_active_preset=lambda name: None,
        _emit=_emit,
        _initial_lazy_loading=_initial_lazy_loading,
        _synthesis_needs_generate=_synthesis_needs_generate,
        _synthesis_autoloaded=_synthesis_autoloaded,
        _first_rows_per_page_sync=_first_rows_per_page_sync,
        _first_search_filter_sync=_first_search_filter_sync,
    )

    # Register sub-modules (defines reactive effects/outputs in session scope)
    register_filters(ctx)
    register_pagination(ctx)
    register_presets(ctx)
    register_edits(ctx)
    register_export(ctx)
    register_synthesis(ctx)

    # ── Core outputs that remain here ───────────────────────────────────

    @render.ui
    def _namespace_holder():
        ns_prefix = session.ns("test").replace("test", "")
        selection_mode = "multiple" if app_config.review_detail_multi_select else "single"
        from shiny import ui as sui
        # Emit a validation script that checks all data-shiny-ns attributes
        # in the DOM match the expected namespace prefix for this module.
        validation_js = f"""
        (function() {{
            var expected = '{ns_prefix}';
            if (!expected) return;  // No namespace (single-module app)
            document.querySelectorAll('[data-shiny-ns]').forEach(function(el) {{
                var ns = el.getAttribute('data-shiny-ns');
                if (ns && ns !== expected) {{
                    // Multiple modules detected — validation is per-module, skip cross-module
                    return;
                }}
            }});
            // Register a Shiny message handler that validates incoming input names
            if (typeof Shiny !== 'undefined' && Shiny.addCustomMessageHandler) {{
                try {{
                    Shiny.addCustomMessageHandler('ns_validate_' + expected, function(msg) {{
                        console.log('[NS-Validate] Module "' + expected + '" received:', msg);
                    }});
                }} catch(e) {{}}
            }}
        }})();
        """
        return sui.div(
            style="display:none;",
            **{"data-shiny-ns": ns_prefix, "data-selection-mode": selection_mode,
               "data-ns-validated": "true"}
        )

    @render.ui
    def viewer_mode_ui():
        if not is_viewer:
            return ui.div()
        return ui.tags.style(
            """
            #save_btn, #approve_btn, #reject_btn { display: none !important; }
            #cell-edit-popup { display: none !important; }
            .editable-cell { cursor: default !important; pointer-events: auto; }
            .editable-cell:hover { background-color: inherit !important; }
            .undo-btn { display: none !important; }
            .viewer-banner { display: block !important; }
            """
        )

    @render.ui
    def selection_mode_ui():
        if app_config.review_detail_multi_select:
            return ui.div()
        return ui.tags.style(
            "#select_all_page { display: none !important; }"
        )

    @render.text
    def data_summary():
        if is_lazy_loading():
            total = total_rows.get()
            num_cols = len(config.all_columns)
        else:
            df = data.get()
            total = len(df)
            num_cols = len(df.columns)
        return f"{total} rows x {num_cols} columns"

    @render.ui
    def stats_histogram():
        _ = mods_log.get()
        with tracker.track_render("stats_histogram"):
            counts = _get_status_counts()
            total = sum(counts.values()) or 1
            try:
                selected = list(input.status_filter_multi())
            except (SilentException, SilentCancelOutputException):
                raise
            except:
                selected = list(app_config.status_labels.keys())
            labels = app_config.status_labels
            bars = []
            for status, count in counts.items():
                pct = (count / total) * 100
                is_checked = status in selected
                bars.append(build_status_histogram_bar(status, count, pct, is_checked, label=labels.get(status)))
        return ui.div(*bars)

    @render.ui
    def table_container():
        _ = _columns_layout_trigger.get()
        with tracker.track_render("table_container"):
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

    # ── Review Detail + Cell Click ──────────────────────────────────────

    @reactive.Effect
    @reactive.event(input.review_detail_btn)
    def _review_detail():
        current_df, indices = _get_page_selection()
        if not indices:
            ui.notification_show("Select a row first", type="warning", duration=3)
            return
        if app_config.review_detail_multi_select:
            pks = _get_selected_pks(indices, current_df)
            if not pks:
                ui.notification_show("Could not resolve primary keys", type="error", duration=3)
                return
            _emit("review_detail", pk=pks, source_table=app_config.database.data_table, row_indices=indices)
            ui.notification_show(f"Review Detail: {len(pks)} row(s)", type="message", duration=2)
        else:
            pks = _get_selected_pks([indices[0]], current_df)
            if not pks:
                ui.notification_show("Could not resolve primary key", type="error", duration=3)
                return
            _emit("review_detail", pk=pks[0], source_table=app_config.database.data_table, row_index=indices[0])
            ui.notification_show(f"Review Detail: {pks[0]}", type="message", duration=2)

    @reactive.Effect
    @reactive.event(input.cell_click)
    def _cell_click():
        payload = input.cell_click()
        if not payload or not app_config.table.cell_click_columns:
            return
        col = payload.get("col", "")
        value = payload.get("value", "")
        pk = payload.get("pk", {})
        _emit("cell_click", pk=pk, column=col, value=value, source_table=app_config.database.data_table)
        ui.notification_show(f"Cell click: {col} = {value}", type="message", duration=3)

    # ── Return public API ─────────────────────────────────────────────
    return WidgetAPI(
        events=_emitter.events,
        data=data,
        active_columns=active_columns,
        widget_id=_emitter.widget_id,
        config=config,
    )
