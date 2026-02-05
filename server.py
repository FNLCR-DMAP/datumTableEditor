"""
Server Logic for Epitopes Data Editor PyShiny App
Updated for split panel layout with column customization
"""

import json
import pandas as pd
from datetime import datetime
from shiny import render, ui, reactive

from config import (
    data_dir,
    modifications_log_path,
    df_original,
    display_columns,
    load_modifications_log,
    all_columns,
)


def create_server(input, output, session):
    """Server logic for the Shiny app"""
    
    def _get_latest_approval_status():
        """Load the latest approval/rejection status from the modifications log.
        Only returns status for global approval (not row-based approval).
        """
        log = load_modifications_log()
        approval_entries = [m for m in log if m.get("type") in ["approval", "rejection"]]
        
        if approval_entries:
            latest = approval_entries[-1]
            details = latest.get("details", {})
            # Only show global banner if it's NOT a row-based approval
            # Row-based approvals have "approved_rows" or "rejected_rows" in details
            if "approved_rows" in details or "rejected_rows" in details:
                # This is a row-based approval, don't show global banner
                return None, None
            status = "approved" if latest.get("type") == "approval" else "rejected"
            timestamp = latest.get("timestamp", None)
            return status, timestamp[:19] if timestamp else None
        
        return None, None
    
    # Reactive values
    data = reactive.Value(df_original.copy())
    mods_log = reactive.Value(load_modifications_log())
    selected_rows = reactive.Value(set())
    
    # Presets storage - load from file if exists
    # Preset format: {"name": {"columns": [...], "widths": {...}}}
    presets_file = data_dir / "column_presets.json"
    active_preset_file = data_dir / "active_preset.json"
    
    def _load_presets():
        if presets_file.exists():
            try:
                with open(presets_file) as f:
                    preset_data = json.load(f)
                    # Handle old format (list) and new format (dict with columns/widths)
                    result = {}
                    for name, value in preset_data.items():
                        if isinstance(value, list):
                            result[name] = {"columns": value, "widths": {}}
                        else:
                            result[name] = value
                    return result
            except:
                pass
        return {"Default": {"columns": list(display_columns), "widths": {}}}
    
    def _save_presets(presets_dict):
        with open(presets_file, "w") as f:
            json.dump(presets_dict, f, indent=2)
    
    def _load_active_preset():
        """Load the last active preset name from file"""
        if active_preset_file.exists():
            try:
                with open(active_preset_file) as f:
                    data = json.load(f)
                    return data.get("active_preset", "Default")
            except:
                pass
        return "Default"
    
    def _save_active_preset(preset_name):
        """Save the active preset name to file"""
        with open(active_preset_file, "w") as f:
            json.dump({"active_preset": preset_name}, f)
    
    # Load presets first
    loaded_presets = _load_presets()
    column_presets = reactive.Value(loaded_presets)
    
    # Load last active preset (persists across refreshes)
    initial_active_preset = _load_active_preset()
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
    
    # Pagination state
    current_page = reactive.Value(1)
    rows_per_page_value = reactive.Value("25")  # Default rows per page
    
    # Dynamic column filters - stores active filters as {column_name: selected_value}
    active_filters = reactive.Value({})
    
    # Load initial approval status from log
    initial_status, initial_timestamp = _get_latest_approval_status()
    approval_status = reactive.Value(initial_status)
    approval_timestamp = reactive.Value(initial_timestamp)
    
    def _get_row_status(row_idx):
        """Determine row status based on modifications log"""
        log = mods_log.get()
        has_modifications = any(
            m.get("details", {}).get("row_index") == row_idx 
            for m in log if m.get("type") == "field_modification"
        )
        
        row_approval_entries = [
            m for m in log 
            if m.get("type") in ["approval", "rejection"] 
            and row_idx in m.get("details", {}).get("approved_rows", []) + m.get("details", {}).get("rejected_rows", [])
        ]
        
        if row_approval_entries:
            latest_approval = row_approval_entries[-1]
            if latest_approval.get("type") == "approval":
                return "approved"
            elif latest_approval.get("type") == "rejection":
                return "rejected"
        
        if has_modifications:
            return "edited"
        else:
            return "unprocessed"
    
    def _get_row_modifications(row_idx):
        """Get all modifications for a specific row"""
        log = mods_log.get()
        return [
            m for m in log 
            if m.get("details", {}).get("row_index") == row_idx 
            and m.get("type") == "field_modification"
        ]
    
    def _get_status_counts():
        """Get counts of each status"""
        current_df = data.get()
        counts = {"unprocessed": 0, "edited": 0, "approved": 0, "rejected": 0}
        for idx in range(len(current_df)):
            status = _get_row_status(idx)
            counts[status] += 1
        return counts
    
    def _get_modification_summary():
        """Get summary of modification status for all rows"""
        current_df = data.get()
        status_counts = {"unprocessed": 0, "edited": 0, "approved": 0, "rejected": 0}
        
        summary_data = []
        for idx in range(len(current_df)):
            status = _get_row_status(idx)
            status_counts[status] += 1
            mods = _get_row_modifications(idx)
            
            summary_data.append({
                "row_index": idx + 1,
                "status": status,
                "modifications_count": len(mods),
                "patient_id": current_df.iloc[idx].get("PatientID", "N/A"),
                "variant_key": current_df.iloc[idx].get("Variant_key", "N/A"),
            })
        
        return summary_data, status_counts
    
    def _get_filtered_rows():
        """Get filtered rows based on search, status filter, and dynamic column filters"""
        current_df = data.get()
        search_term = input.search_input() if hasattr(input, 'search_input') else ""
        
        # Get multi-select status filter
        try:
            status_filters = list(input.status_filter_multi())
        except:
            status_filters = ["unprocessed", "edited", "approved", "rejected"]
        
        # Get dynamic column filters
        filters = active_filters.get()
        
        cols = active_columns.get()
        filtered_indices = []
        
        for idx, (_, row) in enumerate(current_df.iterrows()):
            # Check status filter
            current_status = _get_row_status(idx)
            if current_status not in status_filters:
                continue
            
            # Check dynamic column filters
            filter_pass = True
            for col_name, filter_value in filters.items():
                if filter_value and filter_value != "all" and col_name in current_df.columns:
                    if str(row.get(col_name, "")) != filter_value:
                        filter_pass = False
                        break
            
            if not filter_pass:
                continue
            
            # Check search filter
            if search_term.strip():
                search_lower = search_term.lower().strip()
                row_matches = False
                for col in cols:
                    if col in current_df.columns and search_lower in str(row[col]).lower():
                        row_matches = True
                        break
                if not row_matches:
                    continue
            
            filtered_indices.append(idx)
        
        return filtered_indices
    
    # Output: Data summary text
    @render.text
    def data_summary():
        df = data.get()
        return f"{len(df)} rows x {len(df.columns)} columns"
    
    # Output: Stats histogram
    @render.ui
    def stats_histogram():
        counts = _get_status_counts()
        total = sum(counts.values())
        if total == 0:
            total = 1
        
        # Get current filter selections
        try:
            selected = list(input.status_filter_multi())
        except:
            selected = ["unprocessed", "edited", "approved", "rejected"]
        
        bars = []
        for status, count in counts.items():
            pct = (count / total) * 100
            is_checked = status in selected
            bars.append(
                ui.div(
                    ui.tags.label(
                        ui.tags.input(
                            type="checkbox",
                            checked="checked" if is_checked else None,
                            value=status,
                            class_="status-checkbox",
                            **{"data-status": status}
                        ),
                        ui.span(f"{status.capitalize()}", class_=f"histogram-label status-label-{status}"),
                        class_="histogram-checkbox-label"
                    ),
                    ui.div(
                        ui.div(style=f"width: {pct}%;", class_=f"histogram-fill {status}"),
                        class_="histogram-track"
                    ),
                    ui.span(str(count), class_="histogram-count"),
                    class_="histogram-bar"
                )
            )
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
        fresh_presets = _load_presets()
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
        
        # Ensure we have at least a Default preset
        if not presets:
            presets = {"Default": {"columns": list(display_columns), "widths": {}}}
        
        items = []
        for name in presets.keys():
            is_active = name == current
            delete_btn = ui.tags.span(
                "×", 
                class_="delete-preset", 
                onclick=f"deletePreset('{name}', event)"
            ) if name != "Default" else ""
            
            items.append(
                ui.div(
                    name,
                    delete_btn,
                    class_=f"preset-menu-item {'active' if is_active else ''}",
                    onclick=f"loadPreset('{name}')"
                )
            )
        
        if not items:
            return ui.div("No presets available", style="color: #999; padding: 8px;")
        return ui.div(*items)
    
    # Output: Available columns for modal
    @render.ui
    def available_columns_modal():
        cols = list(active_columns.get())
        
        # Ensure we have columns to work with
        if not cols:
            cols = list(display_columns)
        
        available = [c for c in all_columns if c not in cols]
        
        # Build current columns HTML with drag support
        current_html = []
        for i, col in enumerate(cols, 1):
            current_html.append(
                ui.div(
                    ui.span("⠿", class_="drag-handle-modal", style="cursor: grab; margin-right: 6px; color: rgba(255,255,255,0.5);"),
                    ui.span(f"{i}. {col}", style="margin-right: 8px;"),
                    ui.tags.button("×", class_="remove-modal-col", onclick=f"removeColumnFromModal('{col}', event)", style="background: none; border: none; color: rgba(255,255,255,0.7); cursor: pointer; font-size: 14px;"),
                    class_="current-col-tag modal-draggable-col",
                    draggable="true",
                    **{"data-column": col},
                    style="display: inline-flex; align-items: center; padding: 6px 10px; background: #2c3e50; color: white; border-radius: 4px; font-size: 12px; margin: 3px; cursor: move;"
                )
            )
        
        # Build available columns HTML
        available_html = []
        for col in available:
            available_html.append(
                ui.div(
                    f"+ {col}",
                    class_="add-col-tag",
                    onclick=f"addColumn('{col}', event)",
                    style="display: inline-block; padding: 6px 12px; background: #e9ecef; border-radius: 4px; font-size: 12px; cursor: pointer; margin: 3px;"
                )
            )
        
        return ui.div(
            # Current columns section
            ui.div(
                ui.tags.strong("Current columns (drag to reorder):", style="display: block; margin-bottom: 10px; color: #2c3e50;"),
                ui.div(
                    *current_html if current_html else [ui.span("No columns displayed.", style="color: #999;")],
                    id="modal-columns-container",
                    style="display: flex; flex-wrap: wrap; padding: 10px; background: #f8f9fa; border-radius: 4px; border: 1px dashed #ced4da; min-height: 40px;"
                ),
                style="margin-bottom: 20px;"
            ),
            # Available columns section
            ui.div(
                ui.tags.strong("Remaining columns:", style="display: block; margin-bottom: 10px; color: #2c3e50;"),
                ui.div(
                    *available_html if available_html else [ui.span("All columns displayed.", style="color: #999;")],
                    style="display: flex; flex-wrap: wrap; min-height: 40px;"
                )
            )
        )
    
    # Handle column order changes from JS
    @reactive.Effect
    @reactive.event(input.column_order)
    def _update_column_order():
        val = input.column_order()
        if val:
            # Handle both direct array and object with order property
            new_order = val.get('order') if isinstance(val, dict) else val
            if new_order:
                active_columns.set(list(new_order))
    
    # Handle adding a column
    @reactive.Effect
    @reactive.event(input.add_column)
    def _add_column():
        val = input.add_column()
        if val:
            # Handle both string and dict format
            col = val.get('col') if isinstance(val, dict) else val
            if col:
                cols = active_columns.get().copy()
                if col not in cols:
                    cols.append(col)
                    active_columns.set(cols)
    
    # Handle removing a column
    @reactive.Effect
    @reactive.event(input.remove_column)
    def _remove_column():
        val = input.remove_column()
        if val:
            # Handle both string and dict format
            col = val.get('col') if isinstance(val, dict) else val
            if col:
                cols = active_columns.get().copy()
                if col in cols:
                    cols.remove(col)
                    active_columns.set(cols)
    
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
        if preset_name:
            presets = column_presets.get()
            if preset_name in presets:
                preset_data = presets[preset_name]
                # Handle both old format (list) and new format (dict)
                if isinstance(preset_data, list):
                    active_columns.set(list(preset_data))
                    column_widths.set({})
                else:
                    active_columns.set(list(preset_data.get("columns", [])))
                    column_widths.set(preset_data.get("widths", {}))
                active_preset.set(preset_name)
                _save_active_preset(preset_name)
    
    # Handle saving a new preset (from JS)
    @reactive.Effect
    @reactive.event(input.save_preset_name)
    def _save_preset():
        name = input.save_preset_name()
        if name and name.strip():
            name = name.strip()
            presets = column_presets.get().copy()
            presets[name] = {
                "columns": list(active_columns.get()),
                "widths": column_widths.get().copy()
            }
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
        presets[current] = {
            "columns": list(active_columns.get()),
            "widths": column_widths.get().copy()
        }
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
                    default_preset = presets.get("Default", {"columns": list(display_columns), "widths": {}})
                    if isinstance(default_preset, list):
                        active_columns.set(list(default_preset))
                        column_widths.set({})
                    else:
                        active_columns.set(list(default_preset.get("columns", display_columns)))
                        column_widths.set(default_preset.get("widths", {}))
                ui.notification_show(f"Preset '{name}' deleted!", type="message", duration=2)
    
    # Output: Copy column list for copy modal
    @render.ui
    def copy_column_list():
        """Render list of columns available to copy"""
        # Access reactive values to trigger render
        df = data.get()
        preset_cols = list(active_columns.get()) or list(display_columns)
        all_cols = list(df.columns)
        
        # Build ordered list: preset columns first, then remaining columns
        ordered_cols = []
        for col in preset_cols:
            if col in all_cols:
                ordered_cols.append(col)
        for col in all_cols:
            if col not in ordered_cols:
                ordered_cols.append(col)
        
        buttons = []
        for col in ordered_cols:
            safe_col = col.replace("'", "\\'")
            buttons.append(
                ui.tags.button(
                    col,
                    class_="btn copy-col-btn",
                    onclick=f"copyColumnValues('{safe_col}')",
                    style="width: 100%; margin-bottom: 4px; text-align: left; padding: 6px 10px; font-size: 12px; border: 1px solid #333; color: #333; background: white;"
                )
            )
        
        return ui.div(*buttons, style="max-height: 400px; overflow-y: auto;")

    # Handle copy column request from JS
    @reactive.Effect
    @reactive.event(input.copy_column_request)
    def _handle_copy_request():
        req = input.copy_column_request()
        if not req:
            return
        
        column_name = req.get('column')
        indices = req.get('indices', [])
        
        if not column_name or not indices:
            ui.notification_show("No column or rows selected.", type="warning", duration=2)
            return
        
        df = data.get()
        filtered_indices = _get_filtered_rows()
        
        # Get the actual row indices from paginated indices
        rows_per_page_val = rows_per_page_value.get()
        if rows_per_page_val == "all":
            paginated_indices = filtered_indices
        else:
            rows_per_page = int(rows_per_page_val)
            page = current_page.get()
            start = (page - 1) * rows_per_page
            end = start + rows_per_page
            paginated_indices = filtered_indices[start:end]
        
        # Get actual DataFrame indices
        actual_indices = [paginated_indices[i] for i in indices if i < len(paginated_indices)]
        
        if column_name in df.columns:
            values = df.loc[actual_indices, column_name].astype(str).tolist()
            copy_text = "\n".join(values)
            
            # Send to JS to copy to clipboard
            from shiny import session
            import json
            js_code = f"""
                navigator.clipboard.writeText({json.dumps(copy_text)}).then(function() {{
                    console.log('Copied to clipboard');
                }}).catch(function(err) {{
                    console.error('Could not copy: ', err);
                }});
            """
            ui.insert_ui(
                ui.tags.script(js_code),
                selector="body",
                where="beforeEnd"
            )
            ui.notification_show(f"Copied {len(values)} values from '{column_name}' to clipboard!", type="message", duration=2)
        else:
            ui.notification_show(f"Column '{column_name}' not found.", type="error", duration=2)
    
    # Output: Dynamic filters UI
    @render.ui
    def dynamic_filters():
        """Render active dynamic filters"""
        filters = active_filters.get()
        df = data.get()
        
        if not filters:
            return ui.div(
                ui.p("No filters active. Click + to add a filter.", style="font-size: 12px; color: #6c757d; margin: 5px 0;")
            )
        
        filter_elements = []
        for col_name in filters:
            if col_name not in df.columns:
                continue
            
            # Get unique values for this column
            unique_values = ["all"] + sorted(df[col_name].dropna().astype(str).unique().tolist())
            current_value = filters.get(col_name, "all")
            
            filter_elements.append(
                ui.div(
                    ui.div(
                        ui.tags.label(col_name, style="font-size: 12px; font-weight: 500;"),
                        ui.tags.button("×", class_="remove-filter-btn", 
                                       onclick=f"removeFilter('{col_name}')",
                                       style="background: none; border: none; color: #dc3545; cursor: pointer; font-size: 14px; padding: 0 4px;"),
                        style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;"
                    ),
                    ui.input_select(
                        f"filter_{col_name}",
                        label=None,
                        choices={v: v if v != "all" else f"All {col_name}" for v in unique_values},
                        selected=current_value
                    ),
                    class_="filter-group",
                    style="margin-bottom: 10px;"
                )
            )
        
        return ui.div(*filter_elements)
    
    # Output: Available columns for filter modal
    @render.ui
    def available_filter_columns():
        """Render list of columns that can be added as filters"""
        df = data.get()
        filters = active_filters.get()
        
        # Get columns that aren't already active filters
        available_cols = [col for col in df.columns if col not in filters]
        
        if not available_cols:
            return ui.p("All columns are already being filtered.", style="color: #6c757d;")
        
        column_buttons = []
        for col in available_cols:
            column_buttons.append(
                ui.tags.button(
                    col,
                    class_="btn btn-outline-secondary btn-block",
                    onclick=f"addFilter('{col}')",
                    style="width: 100%; margin-bottom: 8px; text-align: left; padding: 8px 12px; font-size: 12px;"
                )
            )
        
        return ui.div(
            *column_buttons,
            style="max-height: 400px; overflow-y: auto;"
        )
    
    # Handle adding a filter
    @reactive.Effect
    @reactive.event(input.add_filter_column)
    def _add_filter():
        val = input.add_filter_column()
        if val:
            col_name = val.get('column') if isinstance(val, dict) else val
            if col_name:
                filters = active_filters.get().copy()
                if col_name not in filters:
                    filters[col_name] = "all"
                    active_filters.set(filters)
    
    # Handle removing a filter
    @reactive.Effect
    @reactive.event(input.remove_filter_column)
    def _remove_filter():
        val = input.remove_filter_column()
        if val:
            col_name = val.get('column') if isinstance(val, dict) else val
            if col_name:
                filters = active_filters.get().copy()
                if col_name in filters:
                    del filters[col_name]
                    active_filters.set(filters)
    
    # Watch for filter dropdown changes - dynamically observe filter inputs
    @reactive.Effect
    def _watch_filter_changes():
        filters = active_filters.get()
        
        if not filters:
            return
        
        updated = False
        new_filters = filters.copy()
        
        for col_name in list(filters.keys()):
            filter_id = f"filter_{col_name}"
            try:
                current_val = getattr(input, filter_id)()
                if current_val and new_filters.get(col_name) != current_val:
                    new_filters[col_name] = current_val
                    updated = True
            except:
                pass
        
        if updated:
            active_filters.set(new_filters)
            current_page.set(1)  # Reset to first page when filter changes
    
    # Output: Pagination controls
    @render.ui
    def pagination_controls():
        """Render pagination controls with rows per page selector"""
        filtered_indices = _get_filtered_rows()
        total_rows = len(filtered_indices)
        
        rows_per_page_val = rows_per_page_value.get()
        
        if rows_per_page_val == "all":
            return ui.div(
                ui.div(
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
                        selected=rows_per_page_val,
                        width="70px"
                    ),
                    class_="rows-per-page-control"
                ),
                ui.span(f"Showing all {total_rows} rows", class_="pagination-info"),
                class_="pagination-bar"
            )
        
        rows_per_page = int(rows_per_page_val)
        total_pages = max(1, (total_rows + rows_per_page - 1) // rows_per_page)
        page = min(current_page.get(), total_pages)
        
        start_row = (page - 1) * rows_per_page + 1
        end_row = min(page * rows_per_page, total_rows)
        
        return ui.div(
            ui.div(
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
                    selected=rows_per_page_val,
                    width="70px"
                ),
                class_="rows-per-page-control"
            ),
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
    
    # Sync rows_per_page input with reactive value
    @reactive.Effect
    def _sync_rows_per_page():
        try:
            val = input.rows_per_page()
            if val and val != rows_per_page_value.get():
                rows_per_page_value.set(val)
                current_page.set(1)  # Reset to first page when changing rows per page
        except:
            pass
    
    # Pagination event handlers
    @reactive.Effect
    @reactive.event(input.first_page_btn)
    def _first_page():
        current_page.set(1)
    
    @reactive.Effect
    @reactive.event(input.prev_page_btn)
    def _prev_page():
        page = current_page.get()
        if page > 1:
            current_page.set(page - 1)
    
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
                current_page.set(page + 1)
    
    @reactive.Effect
    @reactive.event(input.last_page_btn)
    def _last_page():
        filtered_indices = _get_filtered_rows()
        rows_per_page_val = rows_per_page_value.get()
        if rows_per_page_val != "all":
            rows_per_page = int(rows_per_page_val)
            total_pages = max(1, (len(filtered_indices) + rows_per_page - 1) // rows_per_page)
            current_page.set(total_pages)
    
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
            except:
                pass
    
    # Reset to page 1 when search or status filters change
    @reactive.Effect
    @reactive.event(input.search_input, input.status_filter_multi)
    def _reset_page_on_filter_change():
        current_page.set(1)

    # Output: Data table
    @render.ui
    def table_container():
        """Render the editable data table with pagination"""
        _ = mods_log.get()
        _ = approval_status.get()
        
        current_df = data.get()
        filtered_indices = _get_filtered_rows()
        cols = active_columns.get()
        widths = column_widths.get()
        
        # Apply pagination
        rows_per_page_val = rows_per_page_value.get()
        if rows_per_page_val == "all":
            paginated_indices = filtered_indices
        else:
            rows_per_page = int(rows_per_page_val)
            total_pages = max(1, (len(filtered_indices) + rows_per_page - 1) // rows_per_page)
            page = min(current_page.get(), total_pages)
            start_idx = (page - 1) * rows_per_page
            end_idx = start_idx + rows_per_page
            paginated_indices = filtered_indices[start_idx:end_idx]
        
        # Create header with draggable columns (except fixed columns)
        header_cells = [
            ui.tags.th("", style="width: 40px; text-align: center;"),
            ui.tags.th("Row", style="width: 50px;"),
            ui.tags.th("Status", style="width: 80px;"),
        ]
        for col in cols:
            # Apply saved width if available
            width_style = f"width: {widths[col]}px; min-width: {widths[col]}px;" if col in widths else ""
            header_cells.append(
                ui.tags.th(
                    col,
                    ui.tags.span(
                        "×",
                        class_="remove-header-btn",
                        **{"data-column": col}
                    ),
                    ui.tags.span(class_="resize-handle"),
                    class_="draggable-header",
                    draggable="true",
                    style=width_style,
                    **{"data-column": col}
                )
            )
        
        header = ui.tags.thead(ui.tags.tr(*header_cells))
        
        # Create rows - only for current page
        table_rows = []
        for idx in paginated_indices:
            row = current_df.iloc[idx]
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
            current_status = _get_row_status(idx)
            status_text = {
                "edited": "Edited",
                "approved": "Approved",
                "rejected": "Rejected",
                "unprocessed": "New"
            }.get(current_status, current_status)
            cells.append(
                ui.tags.td(
                    ui.tags.span(status_text, class_=f"row-status-badge status-{current_status}"),
                    style="text-align: center; font-size: 12px;"
                )
            )
            
            # Data cells - clickable text cells
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
            
            table_rows.append(ui.tags.tr(*cells))
        
        table_html = ui.tags.table(
            header,
            ui.tags.tbody(*table_rows),
            class_="edit-table"
        )
        
        total_rows = len(current_df)
        filtered_count = len(filtered_indices)
        displayed_count = len(paginated_indices)
        
        if filtered_count < total_rows:
            rows_text = f"Loaded {displayed_count} rows (filtered {filtered_count} of {total_rows} total)"
        else:
            rows_text = f"Loaded {displayed_count} of {filtered_count} rows"
        
        return ui.div(
            ui.div(rows_text, style="margin-bottom: 10px; color: #666; font-size: 12px;"),
            table_html,
        )
    
    # Output: Approval status
    @render.ui
    def approval_status_ui():
        status = approval_status.get()
        timestamp = approval_timestamp.get()
        
        if status is None:
            return ui.div()
        
        if status == "approved":
            return ui.div(
                ui.div(f"APPROVED on {timestamp}", class_="status-approved-banner"),
                ui.div(
                    ui.input_action_button("clear_approval_btn", "Clear", class_="btn btn-sm btn-secondary"),
                    style="text-align: center; margin-top: 10px;"
                )
            )
        elif status == "rejected":
            return ui.div(
                ui.div(f"REJECTED on {timestamp}", class_="status-rejected-banner"),
                ui.div(
                    ui.input_action_button("clear_approval_btn", "Clear", class_="btn btn-sm btn-secondary"),
                    style="text-align: center; margin-top: 10px;"
                )
            )
        return ui.div()
    
    # Output: Modifications log
    @render.ui
    def modifications_log_ui():
        log = mods_log.get()
        
        if not log:
            return ui.div(
                "No modifications yet. Edit cells in the table above to get started.",
                style="color: #999; padding: 20px; text-align: center;",
            )
        
        log_items = []
        for mod in reversed(log[-20:]):
            timestamp = mod.get("timestamp", "Unknown")
            details = mod.get("details", {})
            
            log_items.append(
                ui.div(
                    ui.tags.span(f"[{timestamp}]", class_="timestamp"),
                    ui.tags.br(),
                    ui.tags.span(
                        f"Row {details.get('row_index', '?')} -> {details.get('column', '?')}: "
                        f"'{details.get('old_value', '')}' -> '{details.get('new_value', '')}'",
                        class_="change-detail"
                    ),
                    class_="log-entry"
                )
            )
        
        return ui.div(*log_items)
    
    # Event: Handle cell edit from popup
    @reactive.Effect
    @reactive.event(input.cell_edit)
    def _handle_cell_edit():
        edit_data = input.cell_edit()
        if not edit_data:
            return
        
        row = edit_data.get('row')
        col = edit_data.get('col')
        old_value = edit_data.get('oldValue', '')
        new_value = edit_data.get('newValue', '')
        
        if row is None or not col:
            return
        
        current_df = data.get()
        log = mods_log.get()
        
        # Update the dataframe
        if col in current_df.columns:
            current_df.at[row, col] = new_value
            
            # Add to log
            log.append({
                "timestamp": datetime.now().isoformat(),
                "type": "field_modification",
                "details": {
                    "row_index": row,
                    "column": col,
                    "old_value": old_value,
                    "new_value": new_value,
                }
            })
            
            data.set(current_df.copy())
            mods_log.set(log.copy())
    
    # Event: Save modifications to file
    @reactive.Effect
    @reactive.event(input.save_btn)
    def _save_modifications():
        current_df = data.get()
        log = mods_log.get()
        
        # Save modifications log
        with open(modifications_log_path, "w") as f:
            json.dump(log, f, indent=2)
        
        # Save data state
        data_state_path = data_dir / "data_state.json"
        current_df.to_json(data_state_path, orient="records", indent=2, default_handler=str)
        
        ui.notification_show(f"Saved {len(log)} modifications!", type="message", duration=3)
    
    # Event: Export status report
    @reactive.Effect
    @reactive.event(input.export_status_btn)
    def _export_status_report():
        summary_data, status_counts = _get_modification_summary()
        status_df = pd.DataFrame(summary_data)
        status_report_path = data_dir / "modification_status_report.csv"
        status_df.to_csv(status_report_path, index=False)
        
        summary_text = f"Total: {len(status_df)} rows | Unprocessed: {status_counts['unprocessed']} | Edited: {status_counts['edited']} | Approved: {status_counts['approved']} | Rejected: {status_counts['rejected']}"
        ui.notification_show(f"Status Report Exported! {summary_text}", type="message", duration=5)
    
    # Event: Export CSV
    @reactive.Effect
    @reactive.event(input.export_btn)
    def _export_csv():
        current_df = data.get()
        export_path = data_dir / "data_modified.csv"
        current_df.to_csv(export_path, index=False)
        ui.notification_show(f"Exported to {export_path.name}", type="message", duration=3)
    
    # Event: Reload data
    @reactive.Effect
    @reactive.event(input.reload_btn)
    def _reload_data():
        data.set(df_original.copy())
        mods_log.set([])
        ui.notification_show("Data reloaded. Modifications cleared.", type="message", duration=3)
    
    # Event: Clear log
    @reactive.Effect
    @reactive.event(input.clear_log_btn)
    def _clear_log():
        mods_log.set([])
        modifications_log_path.write_text(json.dumps([], indent=2))
        ui.notification_show("Modifications log cleared!", type="message", duration=3)
    
    # Event: Approve rows
    @reactive.Effect
    @reactive.event(input.approve_btn)
    def _approve_data():
        current_df = data.get()
        selected_indices = []
        
        for idx in range(len(current_df)):
            try:
                if input[f"select_{idx}"]():
                    selected_indices.append(idx)
            except:
                pass
        
        if not selected_indices:
            ui.notification_show("Please select rows to approve", type="warning", duration=3)
            return
        
        log = mods_log.get()
        timestamp = datetime.now().isoformat()
        
        log.append({
            "timestamp": timestamp,
            "type": "approval",
            "details": {
                "action": "approved",
                "approved_row_count": len(selected_indices),
                "approved_rows": selected_indices,
                "total_rows": len(current_df),
                "modification_count": len(log)
            }
        })
        mods_log.set(log.copy())
        
        with open(modifications_log_path, "w") as f:
            json.dump(log, f, indent=2)
        
        ui.notification_show(f"{len(selected_indices)} row(s) APPROVED!", type="message", duration=3)
    
    # Event: Reject rows
    @reactive.Effect
    @reactive.event(input.reject_btn)
    def _reject_data():
        current_df = data.get()
        selected_indices = []
        
        for idx in range(len(current_df)):
            try:
                if input[f"select_{idx}"]():
                    selected_indices.append(idx)
            except:
                pass
        
        if not selected_indices:
            ui.notification_show("Please select rows to reject", type="warning", duration=3)
            return
        
        log = mods_log.get()
        timestamp = datetime.now().isoformat()
        
        log.append({
            "timestamp": timestamp,
            "type": "rejection",
            "details": {
                "action": "rejected",
                "rejected_row_count": len(selected_indices),
                "rejected_rows": selected_indices,
                "total_rows": len(current_df),
                "modification_count": len(log)
            }
        })
        mods_log.set(log.copy())
        
        with open(modifications_log_path, "w") as f:
            json.dump(log, f, indent=2)
        
        ui.notification_show(f"{len(selected_indices)} row(s) REJECTED!", type="message", duration=3)
    
    # Event: Clear approval
    @reactive.Effect
    @reactive.event(input.clear_approval_btn)
    def _clear_approval():
        approval_status.set(None)
        approval_timestamp.set(None)
