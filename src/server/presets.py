"""
Server presets — preset CRUD, column management, copy modal.
"""
from shiny import render, ui, reactive

from ..utils import (
    load_presets,
    save_presets,
    load_active_preset,
    save_active_preset,
    build_preset_menu_items,
    build_columns_modal_content,
    build_copy_column_buttons,
    parse_column_value,
    parse_column_order,
    add_column_to_list,
    remove_column_from_list,
    sort_dataframe,
    get_preset_columns_and_widths,
    create_preset_data,
    get_ordered_columns,
    get_copy_column_values,
    get_paginated_indices,
    process_copy_request,
)
from .context import ServerContext


def register_presets(ctx: ServerContext):
    """Register preset/column-management reactive effects and render outputs."""
    input = ctx.input
    config = ctx.config
    app_config = ctx.app_config
    data = ctx.data
    display_columns = ctx.display_columns
    all_columns = ctx.all_columns
    column_masks = ctx.column_masks
    active_columns = ctx.active_columns
    column_widths = ctx.column_widths
    column_presets = ctx.column_presets
    active_preset = ctx.active_preset
    current_page = ctx.current_page
    current_sort = ctx.current_sort
    rows_per_page_value = ctx.rows_per_page_value
    _columns_layout_trigger = ctx._columns_layout_trigger
    is_lazy_loading = ctx.is_lazy_loading
    save_ui_state = ctx.save_ui_state
    _get_filtered_rows = ctx._get_filtered_rows
    _get_page_selection = ctx._get_page_selection

    def _save_presets_fn(presets_dict):
        save_presets(config, presets_dict)

    def _save_active_preset_fn(preset_name):
        save_active_preset(config, preset_name)

    @render.text
    def current_preset_name():
        return active_preset.get()

    @reactive.Effect
    @reactive.event(input.refresh_preset)
    def _refresh_presets():
        """Reload presets from file when triggered."""
        if not app_config.table.presets_enabled:
            return
        fresh_presets = load_presets(config, display_columns)
        column_presets.set(fresh_presets)
        current = active_preset.get()
        if current in fresh_presets:
            preset_data = fresh_presets[current]
            if isinstance(preset_data, dict):
                active_columns.set(list(preset_data.get("columns", display_columns)))
                column_widths.set(dict(preset_data.get("widths", {})))
                _columns_layout_trigger.set(_columns_layout_trigger.get() + 1)

    @render.ui
    def preset_menu_items():
        presets = column_presets.get()
        current = active_preset.get()
        if not presets:
            presets = {"Default": {"columns": list(display_columns), "widths": {}}}
        return build_preset_menu_items(presets, current)

    @render.ui
    def available_columns_modal():
        current = active_columns.get()
        cols = list(current) if current is not None else list(display_columns)
        available = [c for c in all_columns if c not in cols]
        return build_columns_modal_content(cols, available, column_masks=column_masks)

    @reactive.Effect
    @reactive.event(input.column_order)
    def _update_column_order():
        val = input.column_order()
        if isinstance(val, dict):
            new_order = val.get('order')
            if new_order is not None:
                active_columns.set(list(new_order))
                _columns_layout_trigger.set(_columns_layout_trigger.get() + 1)
                return
        new_order = parse_column_order(val)
        if new_order:
            active_columns.set(list(new_order))
            _columns_layout_trigger.set(_columns_layout_trigger.get() + 1)

    @reactive.Effect
    @reactive.event(input.add_column)
    def _add_column():
        col = parse_column_value(input.add_column())
        if col:
            active_columns.set(add_column_to_list(active_columns.get(), col))
            _columns_layout_trigger.set(_columns_layout_trigger.get() + 1)

    @reactive.Effect
    @reactive.event(input.remove_column)
    def _remove_column():
        col = parse_column_value(input.remove_column())
        if col:
            active_columns.set(remove_column_from_list(active_columns.get(), col))
            _columns_layout_trigger.set(_columns_layout_trigger.get() + 1)

    @reactive.Effect
    @reactive.event(input.clear_all_columns)
    def _clear_all_columns():
        active_columns.set([])
        _columns_layout_trigger.set(_columns_layout_trigger.get() + 1)

    @reactive.Effect
    @reactive.event(input.add_all_columns)
    def _add_all_columns():
        active_columns.set(list(all_columns))
        _columns_layout_trigger.set(_columns_layout_trigger.get() + 1)

    @reactive.Effect
    @reactive.event(input.sort_column)
    def _sort_column():
        val = input.sort_column()
        if val and val.get('col'):
            col = val.get('col')
            direction = val.get('direction', 'asc')
            ascending = (direction == 'asc')
            if not is_lazy_loading():
                data.set(sort_dataframe(data.get(), col, direction))
            current_sort.set({"column": col, "ascending": ascending})
            current_page.set(1)
            save_ui_state(
                sort_column=col,
                sort_ascending=ascending,
                current_page=1,
                rows_per_page=int(rows_per_page_value.get()),
                column_preset=active_preset.get()
            )

    @reactive.Effect
    @reactive.event(input.reset_columns)
    def _reset_columns():
        active_columns.set(list(display_columns))
        column_widths.set({})
        active_preset.set("Default")
        _save_active_preset_fn("Default")
        _columns_layout_trigger.set(_columns_layout_trigger.get() + 1)

    @reactive.Effect
    @reactive.event(input.column_widths)
    def _update_column_widths():
        widths = input.column_widths()
        if widths and isinstance(widths, dict):
            column_widths.set(widths)

    @reactive.Effect
    @reactive.event(input.load_preset)
    def _load_preset():
        preset_name = input.load_preset()
        if preset_name and preset_name in column_presets.get():
            cols, widths = get_preset_columns_and_widths(column_presets.get()[preset_name], display_columns)
            active_columns.set(cols)
            column_widths.set(widths)
            active_preset.set(preset_name)
            _save_active_preset_fn(preset_name)
            _columns_layout_trigger.set(_columns_layout_trigger.get() + 1)
            sort_state = current_sort.get()
            save_ui_state(
                sort_column=sort_state.get("column"),
                sort_ascending=sort_state.get("ascending", True),
                current_page=current_page.get(),
                rows_per_page=int(rows_per_page_value.get()),
                column_preset=preset_name
            )

    @reactive.Effect
    @reactive.event(input.save_preset_name)
    def _save_preset():
        name = input.save_preset_name()
        if name and name.strip():
            name = name.strip()
            presets = column_presets.get().copy()
            presets[name] = create_preset_data(active_columns.get(), column_widths.get())
            column_presets.set(presets)
            _save_presets_fn(presets)
            active_preset.set(name)
            _save_active_preset_fn(name)
            ui.notification_show(f"Preset '{name}' saved!", type="message", duration=2)

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
        _save_presets_fn(presets)
        ui.notification_show(f"Layout saved to '{current}'!", type="message", duration=2)

    @reactive.Effect
    @reactive.event(input.delete_preset)
    def _delete_preset():
        name = input.delete_preset()
        if name and name != "Default":
            presets = column_presets.get().copy()
            if name in presets:
                del presets[name]
                column_presets.set(presets)
                _save_presets_fn(presets)
                if active_preset.get() == name:
                    active_preset.set("Default")
                    _save_active_preset_fn("Default")
                    cols, widths = get_preset_columns_and_widths(
                        presets.get("Default", {"columns": list(display_columns), "widths": {}}),
                        display_columns
                    )
                    active_columns.set(cols)
                    column_widths.set(widths)
                    _columns_layout_trigger.set(_columns_layout_trigger.get() + 1)
                ui.notification_show(f"Preset '{name}' deleted!", type="message", duration=2)

    # ── Copy column ─────────────────────────────────────────────────────

    @render.ui
    def copy_column_list():
        """Render list of columns available to copy."""
        preset_cols = list(active_columns.get()) or list(display_columns)
        ordered_cols = get_ordered_columns(preset_cols, list(data.get().columns))
        return build_copy_column_buttons(ordered_cols, column_masks=column_masks)

    @reactive.Effect
    @reactive.event(input.copy_column_request)
    def _handle_copy_request():
        req = input.copy_column_request()
        if not req:
            return
        column_name = req.get('column')
        if not column_name:
            ui.notification_show("No column specified.", type="warning", duration=2)
            return

        # Get selected rows from server-side state (same as Export)
        page_df, selected_indices = _get_page_selection()
        if not selected_indices:
            ui.notification_show("No rows selected.", type="warning", duration=2)
            return

        if column_name not in page_df.columns:
            ui.notification_show(f"Column '{column_name}' not found.", type="error", duration=2)
            return

        result_df = page_df.loc[page_df.index.isin(selected_indices)]
        values = result_df[column_name].astype(str).tolist()
        if not values:
            ui.notification_show("No valid rows selected.", type="warning", duration=2)
            return

        from ..utils.clipboard_utils import generate_clipboard_js
        copy_text = "\n".join(values)
        js_code = generate_clipboard_js(copy_text)
        ui.insert_ui(ui.tags.script(js_code), selector="body", where="beforeEnd")
        ui.notification_show(f"Copied {len(values)} values from '{column_name}' to clipboard!", type="message", duration=2)
