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
        """Load the latest approval/rejection status from the modifications log"""
        log = load_modifications_log()
        approval_entries = [m for m in log if m.get("type") in ["approval", "rejection"]]
        
        if approval_entries:
            latest = approval_entries[-1]
            status = "approved" if latest.get("type") == "approval" else "rejected"
            timestamp = latest.get("timestamp", None)
            return status, timestamp[:19] if timestamp else None
        
        return None, None
    
    # Reactive values
    data = reactive.Value(df_original.copy())
    mods_log = reactive.Value(load_modifications_log())
    selected_rows = reactive.Value(set())
    
    # Column customization - track which columns to display and their order
    active_columns = reactive.Value(list(display_columns))
    
    # Pagination state
    current_page = reactive.Value(1)
    
    # Presets storage - load from file if exists
    presets_file = data_dir / "column_presets.json"
    def _load_presets():
        if presets_file.exists():
            try:
                with open(presets_file) as f:
                    return json.load(f)
            except:
                pass
        return {"Default": list(display_columns)}
    
    def _save_presets(presets_dict):
        with open(presets_file, "w") as f:
            json.dump(presets_dict, f, indent=2)
    
    column_presets = reactive.Value(_load_presets())
    active_preset = reactive.Value("Default")
    
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
        """Get filtered rows based on search, status filter, and column filters"""
        current_df = data.get()
        search_term = input.search_input() if hasattr(input, 'search_input') else ""
        
        # Get multi-select status filter
        try:
            status_filters = list(input.status_filter_multi())
        except:
            status_filters = ["unprocessed", "edited", "approved", "rejected"]
        
        # Get column filters
        try:
            gene_filter = input.gene_filter()
        except:
            gene_filter = "all"
        
        try:
            status_value_filter = input.status_value_filter()
        except:
            status_value_filter = "all"
        
        try:
            exonic_filter = input.exonic_filter()
        except:
            exonic_filter = "all"
        
        cols = active_columns.get()
        filtered_indices = []
        
        for idx, (_, row) in enumerate(current_df.iterrows()):
            # Check status filter
            current_status = _get_row_status(idx)
            if current_status not in status_filters:
                continue
            
            # Check column filters
            if gene_filter != "all" and "Gene_names" in current_df.columns:
                if str(row.get("Gene_names", "")) != gene_filter:
                    continue
            
            if status_value_filter != "all" and "Status" in current_df.columns:
                if str(row.get("Status", "")) != status_value_filter:
                    continue
            
            if exonic_filter != "all" and "Exonic_Functions" in current_df.columns:
                if str(row.get("Exonic_Functions", "")) != exonic_filter:
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
    @output
    @render.text
    def data_summary():
        df = data.get()
        return f"{len(df)} rows x {len(df.columns)} columns"
    
    # Output: Stats histogram
    @output
    @render.ui
    def stats_histogram():
        counts = _get_status_counts()
        total = sum(counts.values())
        if total == 0:
            total = 1
        
        bars = []
        for status, count in counts.items():
            pct = (count / total) * 100
            bars.append(
                ui.div(
                    ui.span(f"{status.capitalize()}", class_=f"histogram-label status-label-{status}"),
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
    @output
    @render.text
    def current_preset_name():
        return active_preset.get()
    
    # Output: Preset menu items
    @output
    @render.ui
    def preset_menu_items():
        presets = column_presets.get()
        current = active_preset.get()
        
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
        return ui.div(*items)
    
    # Output: Available columns for modal
    @output
    @render.ui
    def available_columns_modal():
        cols = active_columns.get()
        available = [c for c in all_columns if c not in cols]
        
        if not available:
            return ui.div("All columns are already displayed.", style="color: #666; font-style: italic;")
        
        tags = []
        for col in available:
            tags.append(
                ui.tags.span(
                    f"+ {col}",
                    class_="add-col-tag",
                    onclick=f"addColumn('{col}')"
                )
            )
        return ui.div(*tags, class_="available-cols-grid")
    
    # Handle column order changes from JS
    @reactive.Effect
    @reactive.event(input.column_order)
    def _update_column_order():
        new_order = input.column_order()
        if new_order:
            active_columns.set(list(new_order))
    
    # Handle adding a column
    @reactive.Effect
    @reactive.event(input.add_column)
    def _add_column():
        col = input.add_column()
        if col:
            cols = active_columns.get()
            if col not in cols:
                cols.append(col)
                active_columns.set(cols)
    
    # Handle removing a column
    @reactive.Effect
    @reactive.event(input.remove_column)
    def _remove_column():
        col = input.remove_column()
        if col:
            cols = active_columns.get()
            if col in cols:
                cols.remove(col)
                active_columns.set(cols)
    
    # Reset columns (from JS)
    @reactive.Effect
    @reactive.event(input.reset_columns)
    def _reset_columns():
        active_columns.set(list(display_columns))
        active_preset.set("Default")
    
    # Handle loading a preset
    @reactive.Effect
    @reactive.event(input.load_preset)
    def _load_preset():
        preset_name = input.load_preset()
        if preset_name:
            presets = column_presets.get()
            if preset_name in presets:
                active_columns.set(list(presets[preset_name]))
                active_preset.set(preset_name)
    
    # Handle saving a new preset (from JS)
    @reactive.Effect
    @reactive.event(input.save_preset_name)
    def _save_preset():
        name = input.save_preset_name()
        if name and name.strip():
            name = name.strip()
            presets = column_presets.get().copy()
            presets[name] = list(active_columns.get())
            column_presets.set(presets)
            _save_presets(presets)
            active_preset.set(name)
            ui.notification_show(f"Preset '{name}' saved!", type="message", duration=2)
    
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
                    active_columns.set(list(presets.get("Default", display_columns)))
                ui.notification_show(f"Preset '{name}' deleted!", type="message", duration=2)
    
    # Update filter dropdowns based on data
    @reactive.Effect
    def _update_filters():
        df = data.get()
        
        # Gene filter
        if "Gene_names" in df.columns:
            genes = ["all"] + sorted(df["Gene_names"].dropna().unique().tolist())
            ui.update_select("gene_filter", choices={g: g if g != "all" else "All Genes" for g in genes})
        
        # Status value filter
        if "Status" in df.columns:
            statuses = ["all"] + sorted(df["Status"].dropna().unique().tolist())
            ui.update_select("status_value_filter", choices={s: s if s != "all" else "All Status Values" for s in statuses})
        
        # Exonic function filter
        if "Exonic_Functions" in df.columns:
            funcs = ["all"] + sorted(df["Exonic_Functions"].dropna().unique().tolist())
            ui.update_select("exonic_filter", choices={f: f if f != "all" else "All Functions" for f in funcs})
    
    # Output: Pagination controls
    @output
    @render.ui
    def pagination_controls():
        """Render pagination controls"""
        filtered_indices = _get_filtered_rows()
        total_rows = len(filtered_indices)
        
        rows_per_page_val = input.rows_per_page()
        if rows_per_page_val == "all":
            return ui.div(
                ui.span(f"Showing all {total_rows} rows", class_="pagination-info"),
                class_="pagination-bar"
            )
        
        rows_per_page = int(rows_per_page_val)
        total_pages = max(1, (total_rows + rows_per_page - 1) // rows_per_page)
        page = min(current_page.get(), total_pages)
        
        start_row = (page - 1) * rows_per_page + 1
        end_row = min(page * rows_per_page, total_rows)
        
        return ui.div(
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
        rows_per_page_val = input.rows_per_page()
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
        rows_per_page_val = input.rows_per_page()
        if rows_per_page_val != "all":
            rows_per_page = int(rows_per_page_val)
            total_pages = max(1, (len(filtered_indices) + rows_per_page - 1) // rows_per_page)
            current_page.set(total_pages)
    
    @reactive.Effect
    @reactive.event(input.page_jump_btn)
    def _page_jump():
        filtered_indices = _get_filtered_rows()
        rows_per_page_val = input.rows_per_page()
        if rows_per_page_val != "all":
            rows_per_page = int(rows_per_page_val)
            total_pages = max(1, (len(filtered_indices) + rows_per_page - 1) // rows_per_page)
            try:
                target_page = int(input.page_jump_input())
                target_page = max(1, min(target_page, total_pages))
                current_page.set(target_page)
            except:
                pass
    
    # Reset to page 1 when filters change
    @reactive.Effect
    @reactive.event(input.rows_per_page)
    def _reset_page_on_rows_change():
        current_page.set(1)
    
    @reactive.Effect
    @reactive.event(input.search_input, input.status_filter_multi, input.gene_filter, input.status_value_filter, input.exonic_filter)
    def _reset_page_on_filter_change():
        current_page.set(1)

    # Output: Data table
    @output
    @render.ui
    def table_container():
        """Render the editable data table with pagination"""
        _ = mods_log.get()
        _ = approval_status.get()
        
        current_df = data.get()
        filtered_indices = _get_filtered_rows()
        cols = active_columns.get()
        
        # Apply pagination
        rows_per_page_val = input.rows_per_page()
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
            header_cells.append(
                ui.tags.th(
                    col,
                    ui.tags.button(
                        "×",
                        class_="remove-header-btn",
                        onclick=f"removeColumn('{col}', event)"
                    ),
                    class_="draggable-header",
                    draggable="true",
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
            
            # Data cells
            for col in cols:
                if col in current_df.columns:
                    value = str(row[col]) if pd.notna(row[col]) else ""
                else:
                    value = ""
                cell_id = f"cell_{idx}_{col}"
                cells.append(
                    ui.tags.td(
                        ui.input_text(cell_id, label=None, value=value, placeholder=f"Edit {col}"),
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
    @output
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
    @output
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
    
    # Event: Save modifications
    @reactive.Effect
    @reactive.event(input.save_btn)
    def _save_modifications():
        current_df = data.get()
        log = mods_log.get()
        cols = active_columns.get()
        
        for idx in range(len(current_df)):
            for col in cols:
                if col not in current_df.columns:
                    continue
                cell_id = f"cell_{idx}_{col}"
                try:
                    new_value = input[cell_id]()
                    old_value = str(current_df.at[idx, col]) if pd.notna(current_df.at[idx, col]) else ""
                    
                    if new_value != old_value and new_value:
                        current_df.at[idx, col] = new_value
                        
                        existing_entry = any(
                            m.get("details", {}).get("row_index") == idx and 
                            m.get("details", {}).get("column") == col and
                            m.get("details", {}).get("new_value") == new_value
                            for m in log if m.get("type") == "field_modification"
                        )
                        
                        if not existing_entry:
                            log.append({
                                "timestamp": datetime.now().isoformat(),
                                "type": "field_modification",
                                "details": {
                                    "row_index": idx,
                                    "column": col,
                                    "old_value": old_value,
                                    "new_value": new_value,
                                }
                            })
                except:
                    pass
        
        data.set(current_df.copy())
        mods_log.set(log.copy())
        
        with open(modifications_log_path, "w") as f:
            json.dump(log, f, indent=2)
        
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
