"""
PyShiny App for Epitopes Data Editing with Modification Tracking
Renders a table based on tab_config.json and allows editing with JSON logging
"""

import json
import pandas as pd
from datetime import datetime
from pathlib import Path
from shiny import App, render, ui, reactive
from shiny.types import FileInfo
import shinywidgets
from htmltools import HTMLDocument

# Setup paths
app_dir = Path(__file__).parent
data_dir = app_dir / "data"
data_dir.mkdir(exist_ok=True)

# Load CSV data
csv_path = data_dir / "dummy_data_50rows.csv"
df_original = pd.read_csv(csv_path)

# Try to load saved data state if it exists
data_state_path = data_dir / "data_state.json"
if data_state_path.exists():
    try:
        df_saved = pd.read_json(data_state_path, orient="records")
        df_original = df_saved
    except:
        pass  # If loading fails, use original CSV

# Define columns to display (from tab_config.json structure)
display_columns = [
    "PatientID",
    "Variant_key",
    "Gene_names",
    "Wt_nmer",
    "Mut_nmer",
    "Status",
    "Comments",
    "aa_changes",
    "cDNA_changes",
    "WtNMerReviewed",
    "MutNMerReviewed",
    "Max_Read2Count",
]

# Filter to available columns
display_columns = [col for col in display_columns if col in df_original.columns]

# Modifications log file
modifications_log_path = data_dir / "modifications_log.json"


# UI Definition
app_ui = ui.page_fluid(
    ui.head_content(
        ui.tags.style("""
        .edit-table {
            width: 100%;
            font-size: 14px;
        }
        .edit-table tbody tr:nth-child(even) {
            background-color: #f9f9f9;
        }
        .edit-table tbody tr:hover {
            background-color: #e8f4f8;
        }
        .edit-table th {
            background-color: #2c3e50;
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: 600;
            position: sticky;
            top: 0;
        }
        .edit-table td {
            padding: 10px;
            border: 1px solid #ddd;
        }
        .edit-table input {
            width: 95%;
            padding: 6px;
            border: 1px solid #ccc;
            border-radius: 3px;
            font-size: 13px;
        }
        .edit-table input:focus {
            outline: none;
            border-color: #2196F3;
            box-shadow: 0 0 5px rgba(33, 150, 243, 0.5);
        }
        .row-selector {
            width: 30px !important;
            text-align: center;
        }
        .row-number {
            width: 50px;
            background-color: #f0f0f0;
            font-weight: bold;
            text-align: center;
        }
        .action-buttons {
            margin-bottom: 20px;
            padding: 15px;
            background-color: #f5f5f5;
            border-radius: 5px;
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }
        .action-buttons button {
            padding: 8px 16px;
            font-size: 14px;
        }
        .section-title {
            margin-top: 30px;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #2c3e50;
        }
        .log-container {
            max-height: 400px;
            overflow-y: auto;
            border: 1px solid #ddd;
            border-radius: 5px;
            padding: 10px;
        }
        .log-entry {
            padding: 10px;
            margin-bottom: 10px;
            border-left: 4px solid #2196F3;
            background-color: #f0f7ff;
            border-radius: 3px;
            font-size: 13px;
        }
        .log-entry .timestamp {
            font-weight: bold;
            color: #1565c0;
        }
        .log-entry .change-detail {
            color: #666;
            margin-top: 5px;
            font-family: monospace;
        }
        .stats {
            display: flex;
            gap: 20px;
            margin-bottom: 20px;
        }
        .stat-box {
            padding: 15px;
            background-color: #f0f0f0;
            border-radius: 5px;
            text-align: center;
            flex: 1;
            max-width: 200px;
        }
        .stat-box .number {
            font-size: 24px;
            font-weight: bold;
            color: #2196F3;
        }
        .stat-box .label {
            color: #666;
            font-size: 12px;
            margin-top: 5px;
        }
        .table-container-frame {
            height: 600px;
            border: 2px solid #ddd;
            border-radius: 5px;
            overflow: hidden;
            background: white;
            display: flex;
            flex-direction: column;
        }
        .table-scroll-wrapper {
            flex: 1;
            overflow-y: auto;
            overflow-x: auto;
        }
        .approval-buttons {
            display: flex;
            gap: 10px;
            margin: 15px 0;
            flex-wrap: wrap;
        }
        .approval-buttons button {
            padding: 10px 20px;
            font-size: 14px;
            min-width: 120px;
        }
        .status-approved {
            background-color: #e8f5e9;
            border: 2px solid #4caf50;
            color: #2e7d32;
            font-weight: bold;
            padding: 10px;
            border-radius: 5px;
            text-align: center;
            margin: 10px 0;
        }
        .status-rejected {
            background-color: #ffebee;
            border: 2px solid #f44336;
            color: #c62828;
            font-weight: bold;
            padding: 10px;
            border-radius: 5px;
            text-align: center;
            margin: 10px 0;
        }
        .filter-controls {
            display: flex;
            gap: 15px;
            margin: 15px 0;
            padding: 15px;
            background: #f5f5f5;
            border-radius: 5px;
            flex-wrap: wrap;
            align-items: flex-end;
        }
        .filter-controls > div {
            flex: 1;
            min-width: 200px;
        }
        .filter-controls input,
        .filter-controls select {
            width: 100%;
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 14px;
        }
        .filter-controls label {
            display: block;
            margin-bottom: 5px;
            font-weight: 500;
            color: #333;
            font-size: 13px;
        }
        .row-status-badge {
            display: inline-block;
            padding: 3px 8px;
            border-radius: 3px;
            font-size: 11px;
            font-weight: bold;
            margin-left: 5px;
        }
        .status-edited {
            background-color: #fff3cd;
            color: #856404;
        }
        .status-approved-badge {
            background-color: #d4edda;
            color: #155724;
        }
        .status-rejected-badge {
            background-color: #f8d7da;
            color: #721c24;
        }
        .status-unprocessed {
            background-color: #e2e3e5;
            color: #383d41;
        }
        """)
    ),
    ui.h1("Epitopes Data Editor"),
    ui.p("Edit table fields directly and track all modifications"),
    
    # Stats
    ui.div(
        ui.div(
            ui.div(
                ui.div(ui.output_text("stat_rows"), class_="number"),
                ui.div("Total Rows", class_="label"),
                class_="stat-box"
            ),
            ui.div(
                ui.div(ui.output_text("stat_mods"), class_="number"),
                ui.div("Modifications", class_="label"),
                class_="stat-box"
            ),
            ui.div(
                ui.div(ui.output_text("stat_cols"), class_="number"),
                ui.div("Editable Columns", class_="label"),
                class_="stat-box"
            ),
            class_="stats"
        )
    ),
    
    # Action buttons
    ui.div(
        ui.input_action_button("save_btn", "Save Modifications", class_="btn btn-success btn-lg"),
        ui.input_action_button("export_btn", "Export to CSV", class_="btn btn-info btn-lg"),
        ui.input_action_button("export_status_btn", "📊 Export Status Report", class_="btn btn-primary btn-lg"),
        ui.input_action_button("reload_btn", "Reload Data", class_="btn btn-warning btn-lg"),
        ui.input_action_button("clear_log_btn", "Clear Log", class_="btn btn-danger btn-lg"),
        class_="action-buttons"
    ),
    
    # Approval buttons
    ui.div(
        ui.input_action_button("approve_btn", "✅ Approve", class_="btn btn-success"),
        ui.input_action_button("reject_btn", "❌ Reject", class_="btn btn-danger"),
        class_="approval-buttons"
    ),
    
    # Approval status display
    ui.output_ui("approval_status_ui"),
    
    # Search and filter controls
    ui.div(
        ui.div(
            ui.tags.label("Search Samples"),
            ui.input_text("search_input", label=None, placeholder="Search by sample name or field..."),
        ),
        ui.div(
            ui.tags.label("Filter by Status"),
            ui.input_select(
                "status_filter",
                label=None,
                choices={
                    "all": "All Rows",
                    "edited": "Edited",
                    "approved": "Approved",
                    "rejected": "Rejected",
                    "unprocessed": "Unprocessed"
                },
                selected="all"
            ),
        ),
        class_="filter-controls"
    ),
    
    # Data table section - self-contained with scrolling
    ui.h2("Data Table", class_="section-title"),
    ui.div(
        ui.div(
            ui.output_ui("table_container"),
            class_="table-scroll-wrapper"
        ),
        class_="table-container-frame"
    ),
    
    # Modifications log section
    ui.h2("Modifications Log", class_="section-title"),
    ui.div(
        ui.output_ui("modifications_log_ui"),
        class_="log-container"
    ),
)


def server(input, output, session):
    """Server logic for the Shiny app"""
    
    def _get_latest_approval_status():
        """Load the latest approval/rejection status from the modifications log"""
        log = _load_modifications_log()
        
        # Find the latest approval or rejection entry
        approval_entries = [m for m in log if m.get("type") in ["approval", "rejection"]]
        
        if approval_entries:
            latest = approval_entries[-1]
            status = "approved" if latest.get("type") == "approval" else "rejected"
            timestamp = latest.get("timestamp", None)
            return status, timestamp[:19] if timestamp else None
        
        return None, None
    
    # Reactive values
    data = reactive.Value(df_original.copy())
    mods_log = reactive.Value(_load_modifications_log())
    selected_rows = reactive.Value(set())
    
    # Load initial approval status from log
    initial_status, initial_timestamp = _get_latest_approval_status()
    approval_status = reactive.Value(initial_status)  # None, "approved", or "rejected"
    approval_timestamp = reactive.Value(initial_timestamp)
    row_status = reactive.Value({})  # Track status of each row: {row_idx: "edited"|"approved"|"rejected"|"unprocessed"}
    
    def _get_row_status(row_idx):
        """Determine row status based on modifications log"""
        log = mods_log.get()
        has_modifications = any(m.get("details", {}).get("row_index") == row_idx for m in log if m.get("type") == "field_modification")
        
        # Check if this specific row was approved or rejected
        row_approval_entries = [m for m in log if m.get("type") in ["approval", "rejection"] and row_idx in m.get("details", {}).get("approved_rows", []) + m.get("details", {}).get("rejected_rows", [])]
        
        if row_approval_entries:
            latest_approval = row_approval_entries[-1]
            if latest_approval.get("type") == "approval":
                return "approved"
            elif latest_approval.get("type") == "rejection":
                return "rejected"
        
        # If not explicitly approved/rejected, check if it has modifications
        if has_modifications:
            return "edited"
        else:
            return "unprocessed"
    
    def _get_row_modifications(row_idx):
        """Get all modifications for a specific row"""
        log = mods_log.get()
        row_mods = [m for m in log if m.get("details", {}).get("row_index") == row_idx and m.get("type") == "field_modification"]
        return row_mods
    
    def _get_modification_summary():
        """Get summary of modification status for all rows"""
        current_df = data.get()
        log = mods_log.get()
        status_counts = {"unprocessed": 0, "edited": 0, "approved": 0, "rejected": 0}
        
        summary_data = []
        for idx in range(len(current_df)):
            status = _get_row_status(idx)
            status_counts[status] += 1
            mods = _get_row_modifications(idx)
            mod_count = len(mods)
            
            row_entry = {
                "row_index": idx + 1,
                "status": status,
                "modifications_count": mod_count,
                "patient_id": current_df.iloc[idx].get("PatientID", "N/A"),
                "variant_key": current_df.iloc[idx].get("Variant_key", "N/A"),
            }
            summary_data.append(row_entry)
        
        return summary_data, status_counts
    
    def _get_row_modifications(row_idx):
        """Get all modifications for a specific row"""
        log = mods_log.get()
        row_mods = [m for m in log if m.get("details", {}).get("row_index") == row_idx and m.get("type") == "field_modification"]
        return row_mods
    
    def _get_modification_summary():
        """Get summary of modification status for all rows"""
        current_df = data.get()
        log = mods_log.get()
        status_counts = {"unprocessed": 0, "edited": 0, "approved": 0, "rejected": 0}
        
        summary_data = []
        for idx in range(len(current_df)):
            status = _get_row_status(idx)
            status_counts[status] += 1
            mods = _get_row_modifications(idx)
            mod_count = len(mods)
            
            row_entry = {
                "row_index": idx + 1,
                "status": status,
                "modifications_count": mod_count,
                "patient_id": current_df.iloc[idx].get("PatientID", "N/A"),
                "variant_key": current_df.iloc[idx].get("Variant_key", "N/A"),
            }
            summary_data.append(row_entry)
        
        return summary_data, status_counts
    
    def _get_filtered_rows():
        """Get filtered rows based on search and status filter"""
        current_df = data.get()
        search_term = input.search_input() if hasattr(input, 'search_input') else ""
        status_filter = input.status_filter() if hasattr(input, 'status_filter') else "all"
        
        filtered_indices = []
        
        for idx, (_, row) in enumerate(current_df.iterrows()):
            # Check status filter
            if status_filter != "all":
                current_status = _get_row_status(idx)
                if current_status != status_filter:
                    continue
            
            # Check search filter
            if search_term.strip():
                search_lower = search_term.lower().strip()
                row_matches = False
                for col in display_columns:
                    if search_lower in str(row[col]).lower():
                        row_matches = True
                        break
                if not row_matches:
                    continue
            
            filtered_indices.append(idx)
        
        return filtered_indices
    
    @output
    @render.text
    def stat_rows():
        return str(len(data.get()))
    
    @output
    @render.text
    def stat_cols():
        return str(len(display_columns))
    
    @output
    @render.text
    def stat_mods():
        return str(len(mods_log.get()))
    
    @output
    @render.ui
    def table_container():
        """Render the editable data table with search and filter"""
        # Trigger re-render when mods_log or approval_status changes
        _ = mods_log.get()  # Reactive dependency
        _ = approval_status.get()  # Reactive dependency
        
        current_df = data.get()
        filtered_indices = _get_filtered_rows()
        
        # Create header
        header_cells = [
            ui.tags.th("", style="width: 40px; text-align: center;"),  # Select
            ui.tags.th("Row", style="width: 50px;"),  # Row number
            ui.tags.th("Status", style="width: 80px;"),  # Status badge
        ]
        for col in display_columns:
            header_cells.append(ui.tags.th(col))
        
        header = ui.tags.thead(ui.tags.tr(*header_cells))
        
        # Create rows
        table_rows = []
        for idx in filtered_indices:
            _, row = list(current_df.iterrows())[idx]
            cells = []
            
            
            # Select checkbox
            cells.append(
                ui.tags.td(
                    ui.input_checkbox(
                        f"select_{idx}",
                        label="",
                        value=False,
                        width="30px",
                    ),
                    style="text-align: center; width: 10px;",
                )
            )
            
            # Row number
            cells.append(
                ui.tags.td(str(idx + 1), class_="row-number")
            )
            
            # Status badge
            current_status = _get_row_status(idx)
            status_text = {
                "edited": "✏️ Edited",
                "approved": "✅ Approved",
                "rejected": "❌ Rejected",
                "unprocessed": "⭕ New"
            }.get(current_status, current_status)
            status_class = f"row-status-badge status-{current_status}"
            cells.append(
                ui.tags.td(
                    ui.tags.span(status_text, class_=status_class),
                    style="text-align: center; font-size: 12px;"
                )
            )
            
            # Data cells
            for col in display_columns:
                value = str(row[col]) if pd.notna(row[col]) else ""
                cell_id = f"cell_{idx}_{col}"
                
                cells.append(
                    ui.tags.td(
                        ui.input_text(
                            cell_id,
                            label=None,
                            value=value,
                            placeholder=f"Edit {col}",
                        ),
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
        rows_text = f"Displaying {filtered_count} of {total_rows} rows" if filtered_count < total_rows else f"Displaying {filtered_count} rows"
        
        return ui.div(
            ui.div(
                rows_text,
                style="margin-bottom: 10px; color: #666;",
            ),
            table_html,
        )
    
    @output
    @render.ui
    def approval_status_ui():
        """Display approval status"""
        status = approval_status.get()
        timestamp = approval_timestamp.get()
        
        if status is None:
            return ui.div()  # Empty placeholder
        
        if status == "approved":
            return ui.div(
                ui.div(
                    f"✅ APPROVED on {timestamp}",
                    class_="status-approved"
                ),
                ui.div(
                    ui.input_action_button("clear_approval_btn", "✕ Clear", class_="btn btn-sm btn-secondary"),
                    style="text-align: center; margin-top: 10px;"
                )
            )
        elif status == "rejected":
            return ui.div(
                ui.div(
                    f"❌ REJECTED on {timestamp}",
                    class_="status-rejected"
                ),
                ui.div(
                    ui.input_action_button("clear_approval_btn", "✕ Clear", class_="btn btn-sm btn-secondary"),
                    style="text-align: center; margin-top: 10px;"
                )
            )
        return ui.div()
    
    @output
    @render.ui
    def modifications_log_ui():
        """Display the modifications log"""
        log = mods_log.get()
        
        if not log:
            return ui.div(
                "No modifications yet. Edit cells in the table above to get started.",
                style="color: #999; padding: 20px; text-align: center;",
            )
        
        log_items = []
        for mod in reversed(log[-20:]):  # Show last 20
            timestamp = mod.get("timestamp", "Unknown")
            details = mod.get("details", {})
            
            log_items.append(
                ui.div(
                    ui.tags.span(
                        f"[{timestamp}]",
                        class_="timestamp"
                    ),
                    ui.tags.br(),
                    ui.tags.span(
                        f"Row {details.get('row_index', '?')} → {details.get('column', '?')}: "
                        f"'{details.get('old_value', '')}' → '{details.get('new_value', '')}'",
                        class_="change-detail"
                    ),
                    class_="log-entry"
                )
            )
        
        return ui.div(*log_items)
    
    @reactive.Effect
    @reactive.event(input.save_btn)
    def _save_modifications():
        """Save modifications to JSON and detect any pending cell changes"""
        # First, detect and log any cell changes that haven't been logged yet
        current_df = data.get()
        log = mods_log.get()
        
        for idx in range(len(current_df)):
            for col in display_columns:
                cell_id = f"cell_{idx}_{col}"
                try:
                    new_value = input[cell_id]()
                    old_value = str(current_df.at[idx, col]) if pd.notna(current_df.at[idx, col]) else ""
                    
                    # Detect change
                    if new_value != old_value and new_value:
                        # Update dataframe
                        current_df.at[idx, col] = new_value
                        
                        # Check if this change was already logged
                        existing_entry = any(
                            m.get("details", {}).get("row_index") == idx and 
                            m.get("details", {}).get("column") == col and
                            m.get("details", {}).get("new_value") == new_value
                            for m in log if m.get("type") == "field_modification"
                        )
                        
                        # Only log if not already logged
                        if not existing_entry:
                            mod_entry = {
                                "timestamp": datetime.now().isoformat(),
                                "type": "field_modification",
                                "details": {
                                    "row_index": idx,
                                    "column": col,
                                    "old_value": old_value,
                                    "new_value": new_value,
                                }
                            }
                            log.append(mod_entry)
                except:
                    pass
        
        # Update reactive values
        data.set(current_df.copy())
        mods_log.set(log.copy())
        
        # Save modifications log
        with open(modifications_log_path, "w") as f:
            json.dump(log, f, indent=2)
        
        # Save current data state
        data_state_path = data_dir / "data_state.json"
        current_df.to_json(data_state_path, orient="records", indent=2, default_handler=str)
        
        ui.notification_show(
            f"✅ Saved {len(log)} modifications!",
            type="message",
            duration=3,
        )
    
    @reactive.Effect
    @reactive.event(input.export_status_btn)
    def _export_status_report():
        """Export modification status report to CSV"""
        summary_data, status_counts = _get_modification_summary()
        
        # Create DataFrame from summary
        status_df = pd.DataFrame(summary_data)
        
        # Save to CSV
        status_report_path = data_dir / "modification_status_report.csv"
        status_df.to_csv(status_report_path, index=False)
        
        # Create summary text
        summary_text = f"Total: {len(status_df)} rows | Unprocessed: {status_counts['unprocessed']} | Edited: {status_counts['edited']} | Approved: {status_counts['approved']} | Rejected: {status_counts['rejected']}"
        
        ui.notification_show(
            f"📊 Status Report Exported! {summary_text}",
            type="message",
            duration=5,
        )
    
    @reactive.Effect
    @reactive.event(input.export_btn)
    def _export_csv():
        """Export current data to CSV"""
        current_df = data.get()
        export_path = data_dir / "data_modified.csv"
        current_df.to_csv(export_path, index=False)
        
        ui.notification_show(
            f"📥 Exported to {export_path.name}",
            type="message",
            duration=3,
        )
    
    @reactive.Effect
    @reactive.event(input.reload_btn)
    def _reload_data():
        """Reload original data and clear modifications"""
        data.set(df_original.copy())
        mods_log.set([])
        
        ui.notification_show(
            "🔄 Data reloaded. Modifications cleared.",
            type="message",
            duration=3,
        )
    
    @reactive.Effect
    @reactive.event(input.clear_log_btn)
    def _clear_log():
        """Clear modifications log"""
        mods_log.set([])
        modifications_log_path.write_text(json.dumps([], indent=2))
        
        ui.notification_show(
            "🗑️ Modifications log cleared!",
            type="message",
            duration=3,
        )
    
    @reactive.Effect
    @reactive.event(input.approve_btn)
    def _approve_data():
        """Approve selected rows"""
        # Get selected row indices
        current_df = data.get()
        selected_indices = []
        
        for idx in range(len(current_df)):
            try:
                if input[f"select_{idx}"]():
                    selected_indices.append(idx)
            except:
                pass
        
        if not selected_indices:
            ui.notification_show(
                "⚠️ Please select rows to approve",
                type="warning",
                duration=3,
            )
            return
        
        log = mods_log.get()
        timestamp = datetime.now().isoformat()
        
        # Log approval action for selected rows
        approval_entry = {
            "timestamp": timestamp,
            "type": "approval",
            "details": {
                "action": "approved",
                "approved_row_count": len(selected_indices),
                "approved_rows": selected_indices,
                "total_rows": len(current_df),
                "modification_count": len(log)
            }
        }
        log.append(approval_entry)
        mods_log.set(log.copy())
        
        # Save to log file
        with open(modifications_log_path, "w") as f:
            json.dump(log, f, indent=2)
        
        ui.notification_show(
            f"✅ {len(selected_indices)} row(s) APPROVED and logged!",
            type="message",
            duration=3,
        )
    
    @reactive.Effect
    @reactive.event(input.reject_btn)
    def _reject_data():
        """Reject selected rows"""
        # Get selected row indices
        current_df = data.get()
        selected_indices = []
        
        for idx in range(len(current_df)):
            try:
                if input[f"select_{idx}"]():
                    selected_indices.append(idx)
            except:
                pass
        
        if not selected_indices:
            ui.notification_show(
                "⚠️ Please select rows to reject",
                type="warning",
                duration=3,
            )
            return
        
        log = mods_log.get()
        timestamp = datetime.now().isoformat()
        
        # Log rejection action for selected rows
        rejection_entry = {
            "timestamp": timestamp,
            "type": "rejection",
            "details": {
                "action": "rejected",
                "rejected_row_count": len(selected_indices),
                "rejected_rows": selected_indices,
                "total_rows": len(current_df),
                "modification_count": len(log)
            }
        }
        log.append(rejection_entry)
        mods_log.set(log.copy())
        
        # Save to log file
        with open(modifications_log_path, "w") as f:
            json.dump(log, f, indent=2)
        
        ui.notification_show(
            f"❌ {len(selected_indices)} row(s) REJECTED and logged!",
            type="message",
            duration=3,
        )
    
    @reactive.Effect
    @reactive.event(input.clear_approval_btn)
    def _clear_approval():
        """Clear the approval/rejection banner"""
        approval_status.set(None)
        approval_timestamp.set(None)
    
    # Monitor cell changes
    def get_all_cell_values():
        """Get all current cell values from inputs"""
        current_df = data.get()
        log = mods_log.get()
        
        for idx in range(len(current_df)):
            for col in display_columns:
                cell_id = f"cell_{idx}_{col}"
                try:
                    new_value = input[cell_id]()
                    old_value = str(current_df.at[idx, col]) if pd.notna(current_df.at[idx, col]) else ""
                    
                    # Detect change
                    if new_value != old_value and new_value:
                        # Update dataframe
                        current_df.at[idx, col] = new_value
                        
                        # Log modification
                        mod_entry = {
                            "timestamp": datetime.now().isoformat(),
                            "type": "field_modification",
                            "details": {
                                "row_index": idx,
                                "column": col,
                                "old_value": old_value,
                                "new_value": new_value,
                            }
                        }
                        log.append(mod_entry)
                        
                        # Update reactive values
                        data.set(current_df.copy())
                        mods_log.set(log.copy())
                except:
                    pass


def get_modification_status(row_index):
    """
    Public function to retrieve modification status for a specific row.
    Can be called from external scripts.
    
    Args:
        row_index (int): Row index (0-based)
    
    Returns:
        dict: Status info {status, modifications_count, timestamp, details}
    """
    if not modifications_log_path.exists():
        return {"status": "unprocessed", "modifications_count": 0, "timestamp": None, "details": []}
    
    with open(modifications_log_path, "r") as f:
        log = json.load(f)
    
    row_mods = [m for m in log if m.get("details", {}).get("row_index") == row_index and m.get("type") == "field_modification"]
    
    # Determine status
    approval_entries = [m for m in log if m.get("type") in ["approval", "rejection"]]
    status = "unprocessed"
    if approval_entries:
        last_approval = approval_entries[-1]
        if last_approval.get("type") == "approval":
            status = "approved"
        elif last_approval.get("type") == "rejection":
            status = "rejected"
    elif row_mods:
        status = "edited"
    
    return {
        "row_index": row_index,
        "status": status,
        "modifications_count": len(row_mods),
        "last_modified": row_mods[-1].get("timestamp") if row_mods else None,
        "modifications": row_mods,
    }


def get_all_modification_statuses():
    """
    Public function to retrieve modification status for all rows.
    
    Returns:
        list: List of status dicts for each row
    """
    if not modifications_log_path.exists():
        return []
    
    with open(modifications_log_path, "r") as f:
        log = json.load(f)
    
    # Determine overall approval status
    approval_entries = [m for m in log if m.get("type") in ["approval", "rejection"]]
    overall_status = None
    if approval_entries:
        last_approval = approval_entries[-1]
        overall_status = "approved" if last_approval.get("type") == "approval" else "rejected"
    
    # Load data to get row count
    csv_path = data_dir / "dummy_data_50rows.csv"
    if not csv_path.exists():
        return []
    
    df = pd.read_csv(csv_path)
    statuses = []
    
    for idx in range(len(df)):
        row_mods = [m for m in log if m.get("details", {}).get("row_index") == idx and m.get("type") == "field_modification"]
        
        status = overall_status if overall_status else ("edited" if row_mods else "unprocessed")
        if not overall_status and row_mods:
            status = "edited"
        elif not overall_status:
            status = "unprocessed"
        
        statuses.append({
            "row_index": idx,
            "status": status,
            "modifications_count": len(row_mods),
            "last_modified": row_mods[-1].get("timestamp") if row_mods else None,
        })
    
    return statuses


def _load_modifications_log():
    """Load modifications log from file if it exists"""
    if modifications_log_path.exists():
        with open(modifications_log_path, "r") as f:
            return json.load(f)
    return []


def get_modification_status(row_index):
    """
    Public function to retrieve modification status for a specific row.
    Can be called from external scripts or Python interpreter.
    
    Args:
        row_index (int): Row index (0-based)
    
    Returns:
        dict: Status info {row_index, status, modifications_count, last_modified, modifications}
    """
    if not modifications_log_path.exists():
        return {"row_index": row_index, "status": "unprocessed", "modifications_count": 0, "last_modified": None, "modifications": []}
    
    with open(modifications_log_path, "r") as f:
        log = json.load(f)
    
    row_mods = [m for m in log if m.get("details", {}).get("row_index") == row_index and m.get("type") == "field_modification"]
    
    # Determine status
    approval_entries = [m for m in log if m.get("type") in ["approval", "rejection"]]
    status = "unprocessed"
    if approval_entries:
        last_approval = approval_entries[-1]
        if last_approval.get("type") == "approval":
            status = "approved"
        elif last_approval.get("type") == "rejection":
            status = "rejected"
    elif row_mods:
        status = "edited"
    
    return {
        "row_index": row_index,
        "status": status,
        "modifications_count": len(row_mods),
        "last_modified": row_mods[-1].get("timestamp") if row_mods else None,
        "modifications": row_mods,
    }


def get_all_modification_statuses():
    """
    Public function to retrieve modification status for all rows.
    Can be called from external scripts or Python interpreter.
    
    Returns:
        dict: {rows: [list of status dicts], summary: {counts}}
    """
    if not modifications_log_path.exists():
        return {"rows": [], "summary": {"total": 0, "unprocessed": 0, "edited": 0, "approved": 0, "rejected": 0}}
    
    with open(modifications_log_path, "r") as f:
        log = json.load(f)
    
    # Determine overall approval status
    approval_entries = [m for m in log if m.get("type") in ["approval", "rejection"]]
    overall_status = None
    if approval_entries:
        last_approval = approval_entries[-1]
        overall_status = "approved" if last_approval.get("type") == "approval" else "rejected"
    
    # Load data to get row count
    csv_path = data_dir / "dummy_data_50rows.csv"
    if not csv_path.exists():
        return {"rows": [], "summary": {"total": 0, "unprocessed": 0, "edited": 0, "approved": 0, "rejected": 0}}
    
    df = pd.read_csv(csv_path)
    statuses = []
    counts = {"total": len(df), "unprocessed": 0, "edited": 0, "approved": 0, "rejected": 0}
    
    for idx in range(len(df)):
        row_mods = [m for m in log if m.get("details", {}).get("row_index") == idx and m.get("type") == "field_modification"]
        
        status = overall_status if overall_status else ("edited" if row_mods else "unprocessed")
        if not overall_status and row_mods:
            status = "edited"
        elif not overall_status:
            status = "unprocessed"
        
        counts[status] += 1
        
        statuses.append({
            "row_index": idx,
            "status": status,
            "modifications_count": len(row_mods),
            "last_modified": row_mods[-1].get("timestamp") if row_mods else None,
        })
    
    return {"rows": statuses, "summary": counts}


# Create the app (module level for Shiny)
app = App(app_ui, server)
