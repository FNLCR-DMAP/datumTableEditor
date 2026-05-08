"""
Server pagination — page navigation, rows-per-page sync, search handlers.
"""
from shiny import render, ui, reactive
from shiny.types import SilentException, SilentCancelOutputException

from ..utils import (
    build_pagination_controls_all,
    build_pagination_controls_paged,
    calculate_pagination,
)
from ..utils import tracker
from .context import ServerContext


def register_pagination(ctx: ServerContext):
    """Register pagination reactive effects and render outputs."""
    input = ctx.input
    app_config = ctx.app_config
    current_page = ctx.current_page
    rows_per_page_value = ctx.rows_per_page_value
    active_preset = ctx.active_preset
    current_sort = ctx.current_sort
    search_state = ctx.search_state
    is_lazy_loading = ctx.is_lazy_loading
    save_ui_state = ctx.save_ui_state
    _lazy_filtered_count = ctx._lazy_filtered_count
    _get_filtered_rows = ctx._get_filtered_rows
    _first_rows_per_page_sync = ctx._first_rows_per_page_sync
    _first_search_filter_sync = ctx._first_search_filter_sync

    def _persist_page(page_num):
        """Persist page state to database."""
        sort_state = current_sort.get()
        rpp = rows_per_page_value.get()
        save_ui_state(
            sort_column=sort_state.get("column"),
            sort_ascending=sort_state.get("ascending", True),
            current_page=page_num,
            rows_per_page=int(rpp) if rpp != "all" else 25,
            column_preset=active_preset.get()
        )

    def _total_filtered():
        """Get current filtered count based on mode."""
        if is_lazy_loading():
            return _lazy_filtered_count()
        return len(_get_filtered_rows())

    @render.ui
    def pagination_controls():
        """Render pagination controls with rows per page selector."""
        with tracker.track_render("pagination_controls"):
            total_filtered = _total_filtered()
            rows_per_page_val = rows_per_page_value.get()
            rpp_options = app_config.table.rows_per_page_options

            if rows_per_page_val == "all":
                result = build_pagination_controls_all(total_filtered, rows_per_page_val, rpp_options)
            else:
                page, total_pages, start_row, end_row = calculate_pagination(total_filtered, rows_per_page_val, current_page.get())
                result = build_pagination_controls_paged(page, total_pages, start_row, end_row, total_filtered, rows_per_page_val, rpp_options)
        return result

    @reactive.Effect
    def _sync_rows_per_page():
        try:
            val = input.rows_per_page()
            with reactive.isolate():
                if val and val != rows_per_page_value.get():
                    rows_per_page_value.set(val)
                    if _first_rows_per_page_sync["done"]:
                        current_page.set(1)
            if not _first_rows_per_page_sync["done"]:
                _first_rows_per_page_sync["done"] = True
        except (SilentException, SilentCancelOutputException):
            raise
        except:
            pass

    @reactive.Effect
    @reactive.event(input.first_page_btn)
    def _first_page():
        current_page.set(1)
        _persist_page(1)

    @reactive.Effect
    @reactive.event(input.prev_page_btn)
    def _prev_page():
        page = current_page.get()
        if page > 1:
            new_page = page - 1
            current_page.set(new_page)
            _persist_page(new_page)

    @reactive.Effect
    @reactive.event(input.next_page_btn)
    def _next_page():
        total_filtered = _total_filtered()
        rows_per_page_val = rows_per_page_value.get()
        if rows_per_page_val != "all":
            rpp = int(rows_per_page_val)
            total_pages = max(1, (total_filtered + rpp - 1) // rpp)
            page = current_page.get()
            if page < total_pages:
                new_page = page + 1
                current_page.set(new_page)
                _persist_page(new_page)

    @reactive.Effect
    @reactive.event(input.last_page_btn)
    def _last_page():
        total_filtered = _total_filtered()
        rows_per_page_val = rows_per_page_value.get()
        if rows_per_page_val != "all":
            rpp = int(rows_per_page_val)
            total_pages = max(1, (total_filtered + rpp - 1) // rpp)
            current_page.set(total_pages)
            _persist_page(total_pages)

    @reactive.Effect
    @reactive.event(input.page_jump_btn)
    def _page_jump():
        total_filtered = _total_filtered()
        rows_per_page_val = rows_per_page_value.get()
        if rows_per_page_val != "all":
            rpp = int(rows_per_page_val)
            total_pages = max(1, (total_filtered + rpp - 1) // rpp)
            try:
                target_page = int(input.page_jump_input())
                target_page = max(1, min(target_page, total_pages))
                current_page.set(target_page)
                _persist_page(target_page)
            except (SilentException, SilentCancelOutputException):
                raise
            except:
                pass

    # ── Search ──────────────────────────────────────────────────────────

    @reactive.Effect
    @reactive.event(input.search_btn)
    def _handle_search():
        search_term = input.search_input() if hasattr(input, 'search_input') else ""
        search_column = input.search_column() if hasattr(input, 'search_column') else "all"
        search_state.set({"term": search_term, "column": search_column})
        current_page.set(1)

    @reactive.Effect
    @reactive.event(input.clear_search_btn)
    def _handle_clear_search():
        ui.update_text("search_input", value="")
        ui.update_select("search_column", selected="all")
        search_state.set({"term": "", "column": "all"})
        current_page.set(1)

    @reactive.Effect
    @reactive.event(input.status_filter_multi)
    def _reset_page_on_filter_change():
        if not _first_search_filter_sync["done"]:
            _first_search_filter_sync["done"] = True
            return
        current_page.set(1)
        _persist_page(1)
