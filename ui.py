"""
UI Definition for Epitopes Data Editor PyShiny App
Split panel layout with collapsible sidebar
"""

from shiny import ui
from pathlib import Path


def _load_css_files():
    """Load all CSS files from src/css directory"""
    css_dir = Path(__file__).parent / "src" / "css"
    css_files = [
        "layout.css",
        "sidebar.css",
        "toolbar.css",
        "modal.css",
        "table.css",
        "pagination.css",
        "log.css",
    ]
    
    combined_css = []
    for css_file in css_files:
        css_path = css_dir / css_file
        if css_path.exists():
            combined_css.append(f"/* === {css_file} === */")
            combined_css.append(css_path.read_text())
    
    return "\n".join(combined_css)


def _load_js_files():
    """Load all JS files from src/js directory"""
    js_dir = Path(__file__).parent / "src" / "js"
    js_files = [
        "panel-toggle.js",
        "table-drag.js",
        "modal.js",
        "preset.js",
        "histogram.js",
        "cell-edit.js",
        "row-selection.js",
    ]
    
    combined_js = []
    for js_file in js_files:
        js_path = js_dir / js_file
        if js_path.exists():
            combined_js.append(f"// === {js_file} ===")
            combined_js.append(js_path.read_text())
    
    return "\n".join(combined_js)


def create_app_ui():
    """Create and return the app UI definition with split panel layout"""
    return ui.page_fluid(
        ui.head_content(
            ui.tags.style(_load_css_files()),
            ui.tags.script(_load_js_files())
        ),
        
        # Main Container with Split Panels
        ui.div(
            # Left Panel - Sidebar
            ui.div(
                ui.tags.button("◀", class_="toggle-btn", onclick="toggleLeftPanel()"),
                ui.div(
                    # Table Name Section
                    ui.div(
                        ui.h3("Epitopes Table", class_="table-name"),
                        ui.p("dummy_data_50rows.csv", class_="table-subtitle"),
                        ui.output_text("data_summary"),
                        class_="table-name-section"
                    ),
                    
                    # Stats Histogram Section (with filter checkboxes)
                    ui.div(
                        ui.h4("Status Distribution"),
                        ui.output_ui("stats_histogram"),
                        # Hidden input to store selected statuses
                        ui.input_checkbox_group(
                            "status_filter_multi",
                            label=None,
                            choices={
                                "unprocessed": "Unprocessed",
                                "edited": "Edited",
                                "approved": "Approved",
                                "rejected": "Rejected"
                            },
                            selected=["unprocessed", "edited", "approved", "rejected"]
                        ),
                        class_="stats-section"
                    ),
                    
                    # Search Filter
                    ui.div(
                        ui.h4("Search"),
                        ui.div(
                            ui.input_text("search_input", label=None, placeholder="Search all fields..."),
                            class_="filter-group"
                        ),
                        class_="filter-section"
                    ),
                    
                    # Column Filters (Dynamic)
                    ui.div(
                        ui.div(
                            ui.h4("Column Filters", style="display: inline-block; margin: 0;"),
                            ui.tags.button("+", class_="btn btn-sm btn-outline-primary add-filter-btn", onclick="openAddFilterModal()", style="margin-left: 10px; padding: 2px 8px; font-size: 12px;"),
                            class_="filter-header"
                        ),
                        ui.output_ui("dynamic_filters"),
                        class_="column-filter-section"
                    ),
                    
                    class_="panel-content"
                ),
                class_="left-panel"
            ),
            
            # Right Panel - Main Content
            ui.div(
                # Top Toolbar - Actions + Preset + Add Column
                ui.div(
                    # Left side - Action Buttons
                    ui.div(
                        ui.input_action_button("save_btn", "Save", class_="btn btn-sm btn-success"),
                        ui.input_action_button("export_btn", "Export CSV", class_="btn btn-sm btn-info"),
                        ui.input_action_button("reload_btn", "Reload", class_="btn btn-sm btn-warning"),
                        ui.input_action_button("clear_log_btn", "Clear Log", class_="btn btn-sm btn-danger"),
                        ui.input_action_button("approve_btn", "Approve", class_="btn btn-sm btn-success"),
                        ui.input_action_button("reject_btn", "Reject", class_="btn btn-sm btn-danger"),
                        ui.tags.button("Copy", class_="btn btn-sm btn-secondary", onclick="openCopyModal()"),
                        ui.tags.button("Clear Selection", class_="btn btn-sm btn-outline-secondary", onclick="deselectAllRows()"),
                        class_="toolbar-left"
                    ),
                    # Right side - Preset dropdown + Add Column button
                    ui.div(
                        # Preset Dropdown
                        ui.div(
                            ui.tags.button(
                                "Preset: ",
                                ui.output_text("current_preset_name", inline=True),
                                " ▼",
                                class_="preset-btn",
                                onclick="togglePresetMenu(event)"
                            ),
                            ui.div(
                                ui.output_ui("preset_menu_items"),
                                ui.div(class_="preset-menu-divider"),
                                ui.div(
                                    "⟳ Refresh",
                                    class_="preset-menu-item",
                                    onclick="refreshPresets(event)",
                                    style="color: #007bff;"
                                ),
                                ui.div(class_="preset-menu-divider"),
                                ui.div(
                                    ui.tags.input(type="text", placeholder="New preset name...", id="new-preset-name"),
                                    ui.tags.button("Save", class_="btn btn-sm btn-primary", onclick="saveNewPreset()"),
                                    class_="preset-save-row"
                                ),
                                ui.div(class_="preset-menu-divider"),
                                ui.div(
                                    "Reset to Default",
                                    class_="preset-menu-item",
                                    onclick="resetColumns()"
                                ),
                                class_="preset-menu",
                                id="preset-menu"
                            ),
                            class_="preset-dropdown"
                        ),
                        # Save Layout Button
                        ui.tags.button("Save Layout", class_="save-layout-btn", onclick="saveLayoutPrompt()"),
                        # Manage Layout Button
                        ui.tags.button("Manage Layout", class_="add-col-btn", onclick="openAddColumnModal()"),
                        # Modifications Log Button
                        ui.tags.button("Mod Log", class_="mod-log-btn", onclick="openLogModal()"),
                        class_="toolbar-right"
                    ),
                    class_="top-toolbar"
                ),
                
                # Add Column Modal
                ui.div(
                    ui.div(
                        ui.div(
                            ui.h3("Manage Layout"),
                            ui.tags.button("Update", class_="btn btn-sm btn-primary", onclick="updateCurrentPreset()", style="margin-left: auto; margin-right: 10px;"),
                            ui.tags.button("×", class_="modal-close", onclick="closeModal()"),
                            class_="modal-header"
                        ),
                        ui.div(
                            ui.output_ui("available_columns_modal"),
                            class_="modal-body"
                        ),
                        class_="modal-content"
                    ),
                    class_="modal-overlay",
                    id="add-column-modal"
                ),
                
                # Approval Status Display
                ui.output_ui("approval_status_ui"),
                
                # Copy Column Modal
                ui.div(
                    ui.div(
                        ui.div(
                            ui.h3("Copy Column Values"),
                            ui.tags.button("×", class_="modal-close", onclick="closeCopyModal()"),
                            class_="modal-header"
                        ),
                        ui.div(
                            ui.p("Select a column to copy values from selected rows:", style="margin-bottom: 10px; font-size: 13px;"),
                            ui.output_ui("copy_column_list"),
                            class_="modal-body"
                        ),
                        class_="modal-content"
                    ),
                    class_="modal-overlay",
                    id="copy-column-modal"
                ),
                
                # Add Filter Modal
                ui.div(
                    ui.div(
                        ui.div(
                            ui.h3("Add Column Filter"),
                            ui.tags.button("×", class_="modal-close", onclick="closeAddFilterModal()"),
                            class_="modal-header"
                        ),
                        ui.div(
                            ui.p("Select a column to filter by:", style="margin-bottom: 15px;"),
                            ui.output_ui("available_filter_columns"),
                            class_="modal-body"
                        ),
                        class_="modal-content"
                    ),
                    class_="modal-overlay",
                    id="add-filter-modal"
                ),
                
                # Data Table
                ui.div(
                    ui.div(
                        ui.output_ui("table_container"),
                        class_="table-scroll-wrapper"
                    ),
                    class_="table-container-frame"
                ),
                
                # Pagination Controls (at bottom)
                ui.div(
                    ui.output_ui("pagination_controls"),
                    class_="pagination-controls-section"
                ),
                
                # Modifications Log Modal
                ui.div(
                    ui.div(
                        ui.div(
                            ui.h3("Modifications Log"),
                            ui.tags.button("×", class_="modal-close", onclick="closeLogModal()"),
                            class_="modal-header"
                        ),
                        ui.div(
                            ui.div(
                                ui.output_ui("modifications_log_ui"),
                                class_="log-container"
                            ),
                            class_="modal-body"
                        ),
                        ui.div(
                            ui.tags.button("Cancel", class_="btn btn-secondary", onclick="closeLogModal()"),
                            style="display: flex; justify-content: flex-end; padding: 10px 20px; border-top: 1px solid #dee2e6;"
                        ),
                        class_="modal-content"
                    ),
                    class_="modal-overlay",
                    id="log-modal"
                ),
                
                class_="right-panel"
            ),
            
            class_="main-container"
        ),
    )


# Create the UI instance
app_ui = create_app_ui()
