""" 
UI Definition for Epitopes Data Editor PyShiny App
Split panel layout with collapsible sidebar
"""

from shiny import ui
from pathlib import Path


def _load_css_files() -> str:
    """Load all CSS files from src/css directory"""
    css_dir = Path(__file__).parent / "css"
    css_files = [
        "layout.css",
        "sidebar.css",
        "toolbar.css",
        "modal.css",
        "table.css",
        "pagination.css",
        "log.css",
        "synthesis.css",
    ]
    
    combined_css = []
    for css_file in css_files:
        css_path = css_dir / css_file
        if css_path.exists():
            combined_css.append(f"/* === {css_file} === */")
            combined_css.append(css_path.read_text())
    
    return "\n".join(combined_css)


def _load_js_files() -> str:
    """Load all JS files from src/js directory"""
    js_dir = Path(__file__).parent / "js"
    js_files = [
        "panel-toggle.js",
        "table-drag.js",
        "modal.js",
        "preset.js",
        "histogram.js",
        "cell-edit.js",
        "row-selection.js",
        "synthesis.js",
    ]
    
    combined_js = []
    for js_file in js_files:
        js_path = js_dir / js_file
        if js_path.exists():
            combined_js.append(f"// === {js_file} ===")
            combined_js.append(js_path.read_text())
    
    return "\n".join(combined_js)


def create_app_ui(config_path: str = "app_config.json") -> ui.Tag:
    """
    Create and return the app UI definition with split panel layout
    
    Args:
        config_path: Path to the config JSON file
    """
    # Load config only (no DB queries) — the UI just needs feature flags and titles
    from .config.config_instance import load_config_only
    app_config = load_config_only(config_path)

    # Use default_columns from config for the initial search dropdown.
    # The server will have the real column list from the actual data.
    all_columns = app_config.table.default_columns or []
    column_masks = app_config.table.column_masks or {}
    
    # Get titles from config
    app_title = app_config.app_title or "Data Editor"
    table_title = app_config.table.title or app_title
    
    # Feature flags
    enable_approval_workflow = app_config.enable_approval_workflow
    enable_save_button = app_config.enable_save_button
    enable_export = app_config.enable_export
    enable_status_filter = app_config.enable_status_filter
    enable_synthesis = app_config.enable_synthesis
    synthesis_label = app_config.synthesis.label or "Synthesis"
    
    # Status labels from config
    status_labels = app_config.status_labels
    status_choices = {k: v for k, v in status_labels.items()}
    status_all_keys = list(status_labels.keys())
    
    return ui.page_fluid(
        # Hidden input to pass config path to server (completely hidden)
        ui.div(
            ui.input_text("_config_path", label=None, value=config_path),
            style="display: none; visibility: hidden; position: absolute; left: -9999px;"
        ),
        
        ui.head_content(
            ui.tags.title(app_title),
            ui.tags.style(_load_css_files()),
            ui.tags.script(_load_js_files()),
            # Namespace helper script - must be after the main JS files
            ui.tags.script("""
                // Helper function to set Shiny input with namespace support
                // contextEl: optional element to find the correct namespace from (for multi-tab support)
                window.setShinyInput = function(inputName, value, options, contextEl) {
                    // Find the namespace from the data-shiny-ns attribute
                    var ns = '';
                    var nsEl = null;
                    
                    if (contextEl) {
                        // Walk up DOM to find the namespace holder in the same module
                        var parent = contextEl;
                        while (parent && !nsEl) {
                            // Check if this element contains a namespace holder
                            nsEl = parent.querySelector('[data-shiny-ns]');
                            parent = parent.parentElement;
                        }
                    }
                    
                    // Fallback: find the namespace holder in the currently active/shown tab
                    if (!nsEl) {
                        // Try Bootstrap nav-panel active state (Shiny's navset_tab uses this)
                        var activePanel = document.querySelector('.tab-pane.active [data-shiny-ns]');
                        if (!activePanel) {
                            // Try bslib tab structure
                            activePanel = document.querySelector('[role="tabpanel"]:not([hidden]) [data-shiny-ns]');
                        }
                        if (!activePanel) {
                            // Try finding visible panel
                            var panels = document.querySelectorAll('[data-shiny-ns]');
                            for (var i = 0; i < panels.length; i++) {
                                var panel = panels[i];
                                var tabPane = panel.closest('.tab-pane, [role="tabpanel"]');
                                if (tabPane && (tabPane.classList.contains('active') || tabPane.classList.contains('show') || !tabPane.hasAttribute('hidden'))) {
                                    activePanel = panel;
                                    break;
                                }
                            }
                        }
                        if (activePanel) {
                            nsEl = activePanel;
                        }
                    }
                    
                    // Last resort: first namespace holder found
                    if (!nsEl) {
                        nsEl = document.querySelector('[data-shiny-ns]');
                    }
                    
                    if (nsEl) {
                        ns = nsEl.getAttribute('data-shiny-ns') || '';
                    }
                    var fullName = ns + inputName;
                    console.log('setShinyInput:', inputName, '-> fullName:', fullName, 'ns:', ns);
                    if (typeof Shiny !== 'undefined') {
                        Shiny.setInputValue(fullName, value, options || {priority: 'event'});
                    } else {
                        console.warn('Shiny not available');
                    }
                };
            """)
        ),
        
        # Main Container with Split Panels
        ui.div(
            # Hidden element to provide namespace to JavaScript
            ui.output_ui("_namespace_holder"),
            
            # Viewer mode CSS injection (hides edit controls for viewer role)
            ui.output_ui("viewer_mode_ui"),
            
            # Left Panel - Sidebar
            ui.div(
                ui.tags.button("◀", class_="toggle-btn", onclick="toggleLeftPanel(event)"),
                ui.div(
                    # Table Name Section
                    ui.div(
                        ui.h3(table_title, class_="table-name"),
                        ui.output_text("data_summary"),
                        class_="table-name-section"
                    ),
                    
                    # Stats Histogram Section (with filter checkboxes) - conditional
                    ui.div(
                        ui.h4("Status Distribution"),
                        ui.output_ui("stats_histogram"),
                        # Hidden input to store selected statuses
                        ui.input_checkbox_group(
                            "status_filter_multi",
                            label=None,
                            choices=status_choices,
                            selected=status_all_keys
                        ),
                        class_="stats-section",
                        style="" if enable_status_filter else "display: none;"
                    ) if enable_status_filter else ui.div(
                        # Hidden default filter when status filter is disabled
                        ui.input_checkbox_group(
                            "status_filter_multi",
                            label=None,
                            choices=status_choices,
                            selected=status_all_keys
                        ),
                        style="display: none;"
                    ),
                    
                    # Search Filter
                    ui.div(
                        ui.h4("Search"),
                        ui.div(
                            ui.input_select(
                                "search_column",
                                label=None,
                                choices={"all": "All Columns"} | {col: column_masks.get(col, col) for col in all_columns},
                                selected="all",
                                width="100%"
                            ),
                            ui.div(
                                ui.input_text("search_input", label=None, placeholder="Search..."),
                                ui.input_action_button("search_btn", "Search", class_="btn btn-primary btn-sm", style="margin-left: 5px;"),
                                style="display: flex; align-items: center; margin-top: 5px;"
                            ),
                            class_="filter-group"
                        ),
                        class_="filter-section"
                    ),
                    
                    # Column Filters (Dynamic)
                    ui.div(
                        ui.div(
                            ui.h4("Column Filters", style="display: inline-block; margin: 0;"),
                            ui.output_ui("add_filter_btn_ui"),
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
                    # Left side - Action Buttons (conditionally rendered based on config)
                    ui.div(
                        ui.input_action_button("save_btn", "Save", class_="btn btn-sm btn-success") if enable_save_button else None,
                        ui.tags.button("Export Selected", class_="btn btn-sm btn-info", onclick="openExportConfirmModal(event, 'selected')") if enable_export else None,
                        ui.tags.button("Export All", class_="btn btn-sm btn-outline-info", onclick="openExportConfirmModal(event, 'all')") if enable_export else None,
                        ui.input_action_button("approve_btn", "Approve", class_="btn btn-sm btn-success") if enable_approval_workflow else None,
                        ui.input_action_button("reject_btn", "Reject", class_="btn btn-sm btn-danger") if enable_approval_workflow else None,
                        ui.tags.button("Copy", class_="btn btn-sm btn-secondary", onclick="openCopyModal(event)"),
                        ui.tags.button("Clear Selection", class_="btn btn-sm btn-outline-secondary", onclick="deselectAllRows()"),
                        ui.tags.button(
                            synthesis_label,
                            class_="btn btn-sm btn-outline-warning synthesis-btn",
                            onclick="openSynthesisModal(event)"
                        ) if enable_synthesis else None,
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
                                    ui.tags.input(type="text", placeholder="New preset name...", class_="new-preset-name-input"),
                                    ui.tags.button("Save", class_="btn btn-sm btn-primary", onclick="saveNewPreset(this)"),
                                    class_="preset-save-row"
                                ),
                                ui.div(class_="preset-menu-divider"),
                                ui.div(
                                    "Reset to Default",
                                    class_="preset-menu-item",
                                    onclick="resetColumns(event)"
                                ),
                                class_="preset-menu"
                            ),
                            class_="preset-dropdown"
                        ),
                        # Save Layout Button
                        ui.tags.button("Save Layout", class_="save-layout-btn", onclick="saveLayoutPrompt(event)"),
                        # Manage Layout Button
                        ui.tags.button("Manage Layout", class_="add-col-btn", onclick="openAddColumnModal(event)"),
                        # Modifications Log Button
                        ui.tags.button("Mod Log", class_="mod-log-btn", onclick="openLogModal(event)"),
                        class_="toolbar-right"
                    ),
                    class_="top-toolbar"
                ),
                
                # Add Column Modal
                ui.div(
                    ui.div(
                        ui.div(
                            ui.h3("Manage Layout"),
                            ui.tags.button("Remove All", class_="btn btn-sm btn-outline-danger", onclick="removeAllColumns(event)", style="margin-left: auto; margin-right: 6px;"),
                            ui.tags.button("Add All", class_="btn btn-sm btn-outline-success", onclick="addAllColumns(event)", style="margin-right: 6px;"),
                            ui.tags.button("Update", class_="btn btn-sm btn-primary", onclick="updateCurrentPreset(event)", style="margin-right: 10px;"),
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
                
                # Filter Values Modal (for multi-select)
                ui.div(
                    ui.div(
                        ui.div(
                            ui.h3("Select Filter Values"),
                            ui.tags.button("×", class_="modal-close", onclick="closeFilterValuesModal()"),
                            class_="modal-header"
                        ),
                        ui.div(
                            ui.div(
                                ui.input_text("filter_values_search", label=None, placeholder="Search values..."),
                                style="margin-bottom: 10px;"
                            ),
                            ui.div(
                                ui.tags.button("Select All", class_="btn btn-sm btn-outline-primary", onclick="selectAllFilterValues()", style="margin-right: 5px;"),
                                ui.tags.button("Clear All", class_="btn btn-sm btn-outline-secondary", onclick="clearAllFilterValues()"),
                                style="margin-bottom: 10px;"
                            ),
                            ui.div(
                                id="filter-values-checkboxes",
                                style="max-height: 300px; overflow-y: auto; border: 1px solid #ddd; padding: 10px; border-radius: 4px;"
                            ),
                            ui.div(
                                ui.tags.button("Apply", class_="btn btn-primary", onclick="applyFilterValues()", style="margin-right: 10px;"),
                                ui.tags.button("Cancel", class_="btn btn-secondary", onclick="closeFilterValuesModal()"),
                                style="margin-top: 15px; text-align: right;"
                            ),
                            class_="modal-body"
                        ),
                        class_="modal-content",
                        style="max-width: 500px;"
                    ),
                    class_="modal-overlay",
                    id="filter-values-modal"
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
                
                # Export PHI/PII Confirmation Modal
                ui.div(
                    ui.div(
                        ui.div(
                            ui.h3("Sensitive Data Export Warning"),
                            ui.tags.button("×", class_="modal-close", onclick="closeExportConfirmModal()"),
                            class_="modal-header"
                        ),
                        ui.div(
                            ui.tags.p(
                                "The data you are about to download may contain ",
                                ui.tags.strong("Protected Health Information (PHI)"),
                                " and/or ",
                                ui.tags.strong("Personally Identifiable Information (PII)"),
                                ".",
                                style="margin-bottom: 12px; line-height: 1.6;"
                            ),
                            ui.tags.p(
                                "Please ensure you have the appropriate permissions and authorization "
                                "to download and store this data. You are responsible for handling "
                                "the exported file in compliance with all applicable data privacy "
                                "regulations and institutional policies.",
                                style="margin-bottom: 0; color: #555; line-height: 1.6;"
                            ),
                            # Dynamic area: shows preparing spinner → download button when ready
                            ui.output_ui("export_download_ui"),
                            class_="modal-body"
                        ),
                        ui.div(
                            ui.tags.button(
                                "Cancel",
                                class_="btn btn-secondary",
                                onclick="closeExportConfirmModal()",
                                style="margin-right: 10px;"
                            ),
                            ui.tags.button(
                                "I Understand",
                                class_="btn btn-primary",
                                id="export-confirm-btn",
                                onclick="confirmExportDownload(event)"
                            ),
                            style="display: flex; justify-content: flex-end; padding: 10px 20px; border-top: 1px solid #dee2e6;",
                            id="export-modal-footer"
                        ),
                        class_="modal-content",
                        style="max-width: 480px;"
                    ),
                    class_="modal-overlay",
                    id="export-confirm-modal"
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
                
                # Synthesis Modal (conditionally rendered)
                ui.div(
                    ui.div(
                        ui.div(
                            ui.h3(synthesis_label if enable_synthesis else "Synthesis"),
                            ui.tags.button("×", class_="modal-close", onclick="closeSynthesisModal()"),
                            class_="modal-header"
                        ),
                        ui.div(
                            # Synthesis mode banner (shown when viewing synthesized data)
                            ui.output_ui("synthesis_mode_banner"),
                            # Query preview
                            ui.div(
                                ui.h5("Transform Query", style="margin-bottom: 8px;"),
                                ui.output_ui("synthesis_query_preview"),
                                class_="synthesis-query-section"
                            ),
                            # Status/progress area
                            ui.output_ui("synthesis_status"),
                            class_="modal-body"
                        ),
                        ui.div(
                            ui.tags.button(
                                "Cancel",
                                class_="btn btn-secondary",
                                onclick="closeSynthesisModal()",
                                style="margin-right: 10px;"
                            ),
                            ui.input_action_button(
                                "synthesis_run_btn",
                                "Run Transform",
                                class_="btn btn-warning"
                            ),
                            ui.input_action_button(
                                "synthesis_regen_btn",
                                "Regenerate",
                                class_="btn btn-outline-warning",
                                style="display: none; margin-left: 8px;"
                            ),
                            ui.input_action_button(
                                "synthesis_exit_btn",
                                "Exit Synthesis Mode",
                                class_="btn btn-outline-secondary",
                                style="display: none;"
                            ),
                            style="display: flex; justify-content: flex-end; padding: 10px 20px; border-top: 1px solid #dee2e6;",
                            id="synthesis-modal-footer"
                        ),
                        class_="modal-content",
                        style="max-width: 700px;"
                    ),
                    class_="modal-overlay",
                    id="synthesis-modal"
                ) if enable_synthesis else None,
                
                class_="right-panel"
            ),
            
            class_="main-container"
        ),
    )


# Note: app_ui is created on-demand by calling create_app_ui(config_path)
# This supports the widget pattern where each instance can have its own config
