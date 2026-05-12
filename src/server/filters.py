"""
Server filters — facet panels, dynamic filters, apply/reset.
"""
from shiny import render, ui, reactive
from shiny.types import SilentException, SilentCancelOutputException
import pandas as pd

from ..utils import (
    build_facet_panels,
    build_dynamic_filters_panel,
    build_filter_column_buttons,
    parse_filter_column,
    add_filter,
    remove_filter,
)
from ..utils import tracker
from .context import ServerContext


def register_filters(ctx: ServerContext):
    """Register all filter-related reactive effects and render outputs."""
    input = ctx.input
    config = ctx.config
    app_config = ctx.app_config
    data = ctx.data
    pending_filters = ctx.pending_filters
    active_filters = ctx.active_filters
    current_page = ctx.current_page
    column_masks = ctx.column_masks
    _filter_panel_trigger = ctx._filter_panel_trigger
    is_lazy_loading = ctx.is_lazy_loading

    _facet_columns = list(app_config.query.facet_columns)
    _facet_max = int(app_config.query.facet_max_values)

    # ── Facet panels ────────────────────────────────────────────────────

    @render.ui
    def facet_panels_ui():
        """Render sidebar facet panels (checkbox + value-count bars)."""
        if not _facet_columns:
            return ui.div()

        # Checkbox checked state comes from pending (reflects user clicks)
        pf = pending_filters.get()
        # Value counts come from active (only change after Apply)
        af = active_filters.get()

        with tracker.track_render("facet_panels_ui"):
            with reactive.isolate():
                df = data.get()

            vc_map = {}
            selected_map = {}
            for col in _facet_columns:
                # Build filters excluding the current facet column so counts
                # reflect the effect of OTHER active filters.
                other_filters = {k: v for k, v in af.items() if k != col}

                if is_lazy_loading() and hasattr(config, 'data_fetcher') and config.data_fetcher:
                    vc_map[col] = config.data_fetcher.get_value_counts(
                        col, limit=_facet_max * 10,
                        filters=other_filters if other_filters else None,
                    )
                elif col in df.columns:
                    from ..utils import apply_column_filters
                    filtered_df = apply_column_filters(df, other_filters) if other_filters else df
                    counts = filtered_df[col].fillna("No value").astype(str).value_counts()
                    vc_map[col] = [(str(v), int(c)) for v, c in counts.head(_facet_max * 10).items()]
                else:
                    vc_map[col] = []

                fv = pf.get(col)
                if fv and isinstance(fv, str) and fv.strip() and fv != "all":
                    selected_map[col] = [v.strip() for v in fv.split("\n") if v.strip()]
                elif isinstance(fv, dict) and fv.get("op") == "in":
                    selected_map[col] = [str(v) for v in fv.get("value", [])]

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
        """Update pending_filters with facet checkbox selection."""
        val = input.facet_filter_change()
        if not val:
            return
        col = val.get("column")
        fv = val.get("value")
        if not col:
            return
        filters = pending_filters.get().copy()
        if fv is None:
            filters.pop(col, None)
        else:
            filters[col] = fv
        pending_filters.set(filters)
        with reactive.isolate():
            _filter_panel_trigger.set(_filter_panel_trigger.get() + 1)

    # ── Dynamic filters UI ──────────────────────────────────────────────

    @render.ui
    def dynamic_filters():
        """Render active dynamic filters from pending state."""
        _filter_panel_trigger.get()

        with reactive.isolate():
            current_filters = pending_filters.get()
            _df = data.get()

        if is_lazy_loading() and hasattr(config, 'data_fetcher') and config.data_fetcher:
            _date_cols = config.data_fetcher.date_columns
        else:
            _date_cols = {col for col in _df.columns if pd.api.types.is_datetime64_any_dtype(_df[col])}

        if is_lazy_loading() and hasattr(config, 'data_fetcher') and config.data_fetcher:
            return build_dynamic_filters_panel(
                current_filters, _df,
                fix_filter=app_config.fix_filter,
                all_columns=config.all_columns,
                get_unique_values_func=config.data_fetcher.get_unique_values,
                column_masks=column_masks,
                date_columns=_date_cols,
            )
        return build_dynamic_filters_panel(
            current_filters, _df,
            fix_filter=app_config.fix_filter,
            column_masks=column_masks,
            date_columns=_date_cols,
        )

    @render.ui
    def add_filter_btn_ui():
        """Render the '+' add filter button when filters aren't fixed."""
        if app_config.fix_filter:
            return ui.div()
        return ui.tags.button(
            "+",
            class_="btn btn-sm btn-outline-primary add-filter-btn",
            onclick="openAddFilterModal(event)",
            style="margin-left: 10px; padding: 2px 8px; font-size: 12px;"
        )

    @render.ui
    def available_filter_columns():
        """Render list of columns that can be added as filters."""
        filters = pending_filters.get()
        if is_lazy_loading():
            all_cols = config.all_columns
        else:
            all_cols = list(data.get().columns)
        available_cols = [col for col in all_cols if col not in filters and not col.startswith('_')]
        return build_filter_column_buttons(available_cols, column_masks=column_masks)

    # ── Filter CRUD handlers ────────────────────────────────────────────

    @reactive.Effect
    @reactive.event(input.add_filter_column)
    def _add_filter():
        if app_config.fix_filter:
            ui.notification_show("Filters are locked by configuration.", type="warning", duration=3)
            return
        col_name = parse_filter_column(input.add_filter_column())
        if col_name:
            pending_filters.set(add_filter(pending_filters.get(), col_name))
            with reactive.isolate():
                _filter_panel_trigger.set(_filter_panel_trigger.get() + 1)

    @reactive.Effect
    @reactive.event(input.remove_filter_column)
    def _remove_filter():
        if app_config.fix_filter:
            return
        col_name = parse_filter_column(input.remove_filter_column())
        if col_name:
            pending_filters.set(remove_filter(pending_filters.get(), col_name))
            with reactive.isolate():
                _filter_panel_trigger.set(_filter_panel_trigger.get() + 1)

    @reactive.Effect
    @reactive.event(input.set_filter_operator)
    def _set_filter_operator():
        if app_config.fix_filter:
            return
        val = input.set_filter_operator()
        if not val:
            return
        col_name = val.get("column")
        op = val.get("op", "in")
        if not col_name:
            return
        filters = pending_filters.get().copy()
        old = filters.get(col_name)

        filter_id = f"filter_{col_name}"
        try:
            textarea_val = getattr(input, filter_id)()
            if textarea_val and str(textarea_val).strip():
                existing_values = [v.strip() for v in str(textarea_val).replace(',', '\n').split('\n') if v.strip()]
            else:
                existing_values = []
        except (SilentException, SilentCancelOutputException):
            raise
        except Exception:
            if isinstance(old, dict) and "op" in old:
                existing_values = old.get("value", [])
                if not isinstance(existing_values, list):
                    existing_values = [existing_values] if existing_values is not None else []
            elif old and str(old).strip() and old != "all":
                existing_values = [v.strip() for v in str(old).replace('\n', ',').replace('\r', ',').split(",") if v.strip()]
            else:
                existing_values = []

        if op == "in" and not existing_values:
            filters[col_name] = "all"
        elif op == "in":
            filters[col_name] = "\n".join(existing_values)
        else:
            filters[col_name] = {"op": op, "value": existing_values, "interactive": True}

        pending_filters.set(filters)
        with reactive.isolate():
            _filter_panel_trigger.set(_filter_panel_trigger.get() + 1)

    @reactive.Effect
    @reactive.event(input.apply_filter_value)
    def _apply_filter_value():
        if app_config.fix_filter:
            return
        val = input.apply_filter_value()
        if not val:
            return
        col_name = val.get("column")
        raw_value = val.get("value", "")
        if not col_name:
            return

        print(f"[_apply_filter_value] col={col_name}, raw_value={repr(raw_value)}")

        filters = pending_filters.get().copy()
        old = filters.get(col_name)

        is_between = isinstance(old, dict) and old.get("op") in ("between", "value_range")

        _is_date_col = False
        if is_lazy_loading() and hasattr(config, 'data_fetcher'):
            _is_date_col = col_name in config.data_fetcher.date_columns
        else:
            df = data.get()
            if col_name in df.columns:
                _is_date_col = pd.api.types.is_datetime64_any_dtype(df[col_name])

        if is_between or (_is_date_col and not isinstance(old, dict)):
            parts = str(raw_value).split('\n') if raw_value is not None else []
            values = [v.strip() for v in parts]
            values = [v if v else None for v in values]
            if _is_date_col and not is_between and len(values) == 2:
                is_between = True
        elif raw_value and str(raw_value).strip():
            values = [v.strip() for v in str(raw_value).replace(',', '\n').split('\n') if v.strip()]
        else:
            values = []

        if isinstance(old, dict) and "op" in old:
            op = old["op"]
            old_values = old.get("value", [])
            if not isinstance(old_values, list):
                old_values = [old_values] if old_values is not None else []
            if values != old_values:
                filters[col_name] = {"op": op, "value": values, "interactive": True}
                pending_filters.set(filters)
        elif is_between:
            filters[col_name] = {"op": "between", "value": values, "interactive": True}
            pending_filters.set(filters)
            with reactive.isolate():
                _filter_panel_trigger.set(_filter_panel_trigger.get() + 1)
        else:
            new_val = "\n".join(values) if values else "all"
            if new_val != old:
                filters[col_name] = new_val
                pending_filters.set(filters)

    # ── Apply / Reset ───────────────────────────────────────────────────

    @render.ui
    def apply_filters_ui():
        """Always show Apply/Reset buttons."""
        pending = pending_filters.get()
        active = active_filters.get()
        has_changes = pending != active
        return ui.div(
            ui.input_action_button(
                "apply_filters_btn",
                "Apply Filters",
                class_="apply-filters-btn" + (" btn-pending" if has_changes else ""),
                onclick="this.classList.add('btn-loading'); this.textContent='Loading…'; this.disabled=true;"
            ),
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
        with reactive.isolate():
            _filter_panel_trigger.set(_filter_panel_trigger.get() + 1)

    # ── Lazy-load filter values on dropdown open ────────────────────────

    @reactive.Effect
    @reactive.event(input.fetch_filter_values)
    def _fetch_filter_values():
        """Respond to JS request for filter unique values (lazy loading)."""
        val = input.fetch_filter_values()
        if not val:
            return
        col_name = val.get("column")
        if not col_name:
            return

        # Fetch unique values from DB
        if is_lazy_loading() and hasattr(config, 'data_fetcher') and config.data_fetcher:
            db_values = config.data_fetcher.get_unique_values(col_name)
        else:
            with reactive.isolate():
                df = data.get()
            if col_name in df.columns and len(df) > 0:
                db_values = sorted(df[col_name].dropna().astype(str).unique().tolist())
            else:
                db_values = []

        # Push values to JS via injected script
        import json
        values_json = json.dumps(db_values)
        js_code = f"(function(){{ if(typeof _receiveFilterValues === 'function') _receiveFilterValues({values_json}); }})()"
        ui.insert_ui(ui.tags.script(js_code), selector="body", where="beforeEnd")
