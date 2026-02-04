"""
UI Definition for Epitopes Data Editor PyShiny App
Split panel layout with collapsible sidebar
"""

from shiny import ui


def create_app_ui():
    """Create and return the app UI definition with split panel layout"""
    return ui.page_fluid(
        ui.head_content(
            ui.tags.style("""
            /* Main Layout */
            .main-container {
                display: flex;
                height: calc(100vh - 60px);
                gap: 0;
            }
            
            /* Left Panel - Sidebar */
            .left-panel {
                width: 25%;
                min-width: 280px;
                max-width: 400px;
                background: #f8f9fa;
                border-right: 2px solid #dee2e6;
                padding: 15px;
                overflow-y: auto;
                transition: all 0.3s ease;
                position: relative;
            }
            .left-panel.collapsed {
                width: 40px;
                min-width: 40px;
                padding: 10px 5px;
                overflow: hidden;
            }
            .left-panel.collapsed .panel-content {
                display: none;
            }
            .toggle-btn {
                position: absolute;
                top: 10px;
                right: 10px;
                width: 28px;
                height: 28px;
                border-radius: 4px;
                border: 1px solid #ccc;
                background: white;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 14px;
                z-index: 100;
            }
            .left-panel.collapsed .toggle-btn {
                right: 6px;
            }
            
            /* Right Panel - Main Content */
            .right-panel {
                flex: 1;
                padding: 15px;
                overflow-y: auto;
                background: white;
            }
            
            /* Table Name Section */
            .table-name-section {
                margin-bottom: 20px;
                padding-bottom: 15px;
                border-bottom: 1px solid #dee2e6;
            }
            .table-name {
                font-size: 18px;
                font-weight: 600;
                color: #2c3e50;
                margin: 0;
            }
            .table-subtitle {
                font-size: 12px;
                color: #6c757d;
                margin-top: 5px;
            }
            
            /* Stats Histogram */
            .stats-section {
                margin-bottom: 20px;
            }
            .stats-section h4 {
                font-size: 14px;
                font-weight: 600;
                color: #495057;
                margin-bottom: 10px;
            }
            .histogram-bar {
                display: flex;
                align-items: center;
                margin-bottom: 8px;
            }
            .histogram-label {
                width: 90px;
                font-size: 12px;
                color: #495057;
            }
            .histogram-track {
                flex: 1;
                height: 20px;
                background: #e9ecef;
                border-radius: 4px;
                overflow: hidden;
                margin-right: 8px;
            }
            .histogram-fill {
                height: 100%;
                border-radius: 4px;
                transition: width 0.3s ease;
            }
            .histogram-fill.unprocessed { background: #6c757d; }
            .histogram-fill.edited { background: #ffc107; }
            .histogram-fill.approved { background: #28a745; }
            .histogram-fill.rejected { background: #dc3545; }
            .histogram-count {
                width: 35px;
                font-size: 12px;
                font-weight: 600;
                text-align: right;
            }
            
            /* Filter Section */
            .filter-section {
                margin-bottom: 20px;
            }
            .filter-section h4 {
                font-size: 14px;
                font-weight: 600;
                color: #495057;
                margin-bottom: 10px;
            }
            .filter-group {
                margin-bottom: 15px;
            }
            .filter-group label {
                display: block;
                font-size: 12px;
                font-weight: 500;
                color: #495057;
                margin-bottom: 5px;
            }
            .filter-group input,
            .filter-group select {
                width: 100%;
                padding: 8px;
                border: 1px solid #ced4da;
                border-radius: 4px;
                font-size: 13px;
            }
            .filter-group input:focus,
            .filter-group select:focus {
                border-color: #2196F3;
                outline: none;
                box-shadow: 0 0 0 2px rgba(33, 150, 243, 0.2);
            }
            
            /* Column Filter Section */
            .column-filter-section {
                margin-bottom: 20px;
            }
            
            /* Action Buttons */
            .action-buttons {
                display: flex;
                gap: 8px;
                flex-wrap: wrap;
                margin-bottom: 15px;
            }
            .action-buttons button {
                padding: 8px 14px;
                font-size: 13px;
            }
            
            /* Column Customization */
            .column-config-section {
                margin-bottom: 15px;
                padding: 12px;
                background: #f8f9fa;
                border-radius: 8px;
                border: 1px solid #dee2e6;
            }
            .column-config-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 10px;
            }
            .column-config-header h4 {
                margin: 0;
                font-size: 14px;
                font-weight: 600;
            }
            .column-list {
                display: flex;
                flex-wrap: wrap;
                gap: 6px;
                min-height: 40px;
                padding: 8px;
                background: white;
                border: 1px dashed #ced4da;
                border-radius: 4px;
            }
            .column-tag {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                padding: 5px 10px;
                background: #2c3e50;
                color: white;
                border-radius: 4px;
                font-size: 12px;
                cursor: grab;
                user-select: none;
            }
            .column-tag:active {
                cursor: grabbing;
            }
            .column-tag .remove-col {
                cursor: pointer;
                opacity: 0.7;
                margin-left: 4px;
            }
            .column-tag .remove-col:hover {
                opacity: 1;
            }
            .column-tag.dragging {
                opacity: 0.5;
            }
            .available-columns {
                margin-top: 10px;
            }
            .available-columns-label {
                font-size: 12px;
                color: #6c757d;
                margin-bottom: 5px;
            }
            .available-column-tag {
                display: inline-flex;
                align-items: center;
                padding: 4px 8px;
                background: #e9ecef;
                color: #495057;
                border-radius: 4px;
                font-size: 11px;
                cursor: pointer;
                margin: 2px;
            }
            .available-column-tag:hover {
                background: #dee2e6;
            }
            
            /* Table Styles */
            .table-container-frame {
                height: calc(100vh - 380px);
                min-height: 300px;
                border: 2px solid #ddd;
                border-radius: 5px;
                overflow: hidden;
                background: white;
            }
            .table-scroll-wrapper {
                height: 100%;
                overflow: auto;
            }
            .edit-table {
                width: 100%;
                font-size: 13px;
                border-collapse: collapse;
            }
            .edit-table th {
                background-color: #2c3e50;
                color: white;
                padding: 10px 8px;
                text-align: left;
                font-weight: 600;
                position: sticky;
                top: 0;
                z-index: 10;
                white-space: nowrap;
            }
            .edit-table tbody tr:nth-child(even) {
                background-color: #f9f9f9;
            }
            .edit-table tbody tr:hover {
                background-color: #e8f4f8;
            }
            .edit-table td {
                padding: 6px 8px;
                border: 1px solid #ddd;
            }
            .edit-table input[type="text"] {
                width: 100%;
                padding: 5px;
                border: 1px solid #ccc;
                border-radius: 3px;
                font-size: 12px;
                box-sizing: border-box;
            }
            .edit-table input[type="text"]:focus {
                outline: none;
                border-color: #2196F3;
                box-shadow: 0 0 3px rgba(33, 150, 243, 0.5);
            }
            .row-number {
                background-color: #f0f0f0;
                font-weight: bold;
                text-align: center;
                width: 50px;
            }
            
            /* Status Badges */
            .row-status-badge {
                display: inline-block;
                padding: 2px 6px;
                border-radius: 3px;
                font-size: 10px;
                font-weight: bold;
            }
            .status-edited { background-color: #fff3cd; color: #856404; }
            .status-approved { background-color: #d4edda; color: #155724; }
            .status-rejected { background-color: #f8d7da; color: #721c24; }
            .status-unprocessed { background-color: #e2e3e5; color: #383d41; }
            
            /* Approval Status Banners */
            .status-approved-banner {
                background-color: #e8f5e9;
                border: 2px solid #4caf50;
                color: #2e7d32;
                font-weight: bold;
                padding: 10px;
                border-radius: 5px;
                text-align: center;
                margin: 10px 0;
            }
            .status-rejected-banner {
                background-color: #ffebee;
                border: 2px solid #f44336;
                color: #c62828;
                font-weight: bold;
                padding: 10px;
                border-radius: 5px;
                text-align: center;
                margin: 10px 0;
            }
            
            /* Log Container */
            .log-section {
                margin-top: 15px;
            }
            .log-section h3 {
                font-size: 16px;
                margin-bottom: 10px;
            }
            .log-container {
                max-height: 200px;
                overflow-y: auto;
                border: 1px solid #ddd;
                border-radius: 5px;
                padding: 10px;
                background: #fafafa;
            }
            .log-entry {
                padding: 8px;
                margin-bottom: 8px;
                border-left: 3px solid #2196F3;
                background-color: #f0f7ff;
                border-radius: 3px;
                font-size: 12px;
            }
            .log-entry .timestamp {
                font-weight: bold;
                color: #1565c0;
            }
            .log-entry .change-detail {
                color: #666;
                margin-top: 4px;
                font-family: monospace;
                font-size: 11px;
            }
            """),
            # JavaScript for panel toggle and column management
            ui.tags.script("""
            document.addEventListener('DOMContentLoaded', function() {
                window.toggleLeftPanel = function() {
                    const panel = document.querySelector('.left-panel');
                    const btn = document.querySelector('.toggle-btn');
                    if (panel.classList.contains('collapsed')) {
                        panel.classList.remove('collapsed');
                        btn.innerHTML = '◀';
                    } else {
                        panel.classList.add('collapsed');
                        btn.innerHTML = '▶';
                    }
                };
            });
            
            // Drag and drop for column reordering
            let draggedItem = null;
            
            document.addEventListener('dragstart', function(e) {
                if (e.target.classList.contains('column-tag')) {
                    draggedItem = e.target;
                    e.target.classList.add('dragging');
                    e.dataTransfer.effectAllowed = 'move';
                }
            });
            
            document.addEventListener('dragend', function(e) {
                if (e.target.classList.contains('column-tag')) {
                    e.target.classList.remove('dragging');
                    // Update column order after drag
                    updateColumnOrder();
                    draggedItem = null;
                }
            });
            
            document.addEventListener('dragover', function(e) {
                e.preventDefault();
                const columnList = document.querySelector('.column-list');
                if (!columnList || !draggedItem) return;
                
                const afterElement = getDragAfterElement(columnList, e.clientX);
                if (afterElement == null) {
                    columnList.appendChild(draggedItem);
                } else {
                    columnList.insertBefore(draggedItem, afterElement);
                }
            });
            
            function getDragAfterElement(container, x) {
                const draggableElements = [...container.querySelectorAll('.column-tag:not(.dragging)')];
                return draggableElements.reduce((closest, child) => {
                    const box = child.getBoundingClientRect();
                    const offset = x - box.left - box.width / 2;
                    if (offset < 0 && offset > closest.offset) {
                        return { offset: offset, element: child };
                    } else {
                        return closest;
                    }
                }, { offset: Number.NEGATIVE_INFINITY }).element;
            }
            
            function updateColumnOrder() {
                const columnList = document.querySelector('.column-list');
                if (!columnList) return;
                const columns = [...columnList.querySelectorAll('.column-tag')].map(el => el.dataset.column);
                if (typeof Shiny !== 'undefined') {
                    Shiny.setInputValue('column_order', columns, {priority: 'event'});
                }
            }
            
            window.addColumn = function(col) {
                if (typeof Shiny !== 'undefined') {
                    Shiny.setInputValue('add_column', col, {priority: 'event'});
                }
            };
            
            window.removeColumn = function(col) {
                if (typeof Shiny !== 'undefined') {
                    Shiny.setInputValue('remove_column', col, {priority: 'event'});
                }
            };
            """)
        ),
        
        # App Title Header
        ui.div(
            ui.h1("Epitopes Data Editor", style="margin: 10px 0; font-size: 20px;"),
            style="padding: 10px 15px; background: #2c3e50; color: white;"
        ),
        
        # Main Container with Split Panels
        ui.div(
            # Left Panel - Sidebar
            ui.div(
                ui.tags.button("◀", class_="toggle-btn", onclick="toggleLeftPanel()"),
                ui.div(
                    # Table Name Section
                    ui.div(
                        ui.h3("📊 Epitopes Table", class_="table-name"),
                        ui.p("dummy_data_50rows.csv", class_="table-subtitle"),
                        ui.output_text("data_summary"),
                        class_="table-name-section"
                    ),
                    
                    # Stats Histogram Section
                    ui.div(
                        ui.h4("Status Distribution"),
                        ui.output_ui("stats_histogram"),
                        class_="stats-section"
                    ),
                    
                    # Status Filter (Multi-select)
                    ui.div(
                        ui.h4("🔍 Filters"),
                        ui.div(
                            ui.tags.label("Filter by Status"),
                            ui.input_checkbox_group(
                                "status_filter_multi",
                                label=None,
                                choices={
                                    "unprocessed": "⭕ Unprocessed",
                                    "edited": "✏️ Edited",
                                    "approved": "✅ Approved",
                                    "rejected": "❌ Rejected"
                                },
                                selected=["unprocessed", "edited", "approved", "rejected"]
                            ),
                            class_="filter-group"
                        ),
                        ui.div(
                            ui.tags.label("Search"),
                            ui.input_text("search_input", label=None, placeholder="Search all fields..."),
                            class_="filter-group"
                        ),
                        class_="filter-section"
                    ),
                    
                    # Column Filters
                    ui.div(
                        ui.h4("📋 Column Filters"),
                        ui.div(
                            ui.tags.label("Gene Name"),
                            ui.input_select(
                                "gene_filter",
                                label=None,
                                choices={"all": "All Genes"},
                                selected="all"
                            ),
                            class_="filter-group"
                        ),
                        ui.div(
                            ui.tags.label("Status Value"),
                            ui.input_select(
                                "status_value_filter",
                                label=None,
                                choices={"all": "All Status Values"},
                                selected="all"
                            ),
                            class_="filter-group"
                        ),
                        ui.div(
                            ui.tags.label("Exonic Function"),
                            ui.input_select(
                                "exonic_filter",
                                label=None,
                                choices={"all": "All Functions"},
                                selected="all"
                            ),
                            class_="filter-group"
                        ),
                        class_="column-filter-section"
                    ),
                    
                    class_="panel-content"
                ),
                class_="left-panel"
            ),
            
            # Right Panel - Main Content
            ui.div(
                # Action Buttons Row
                ui.div(
                    ui.input_action_button("save_btn", "💾 Save", class_="btn btn-success"),
                    ui.input_action_button("export_btn", "📥 Export CSV", class_="btn btn-info"),
                    ui.input_action_button("export_status_btn", "📊 Status Report", class_="btn btn-primary"),
                    ui.input_action_button("reload_btn", "🔄 Reload", class_="btn btn-warning"),
                    ui.input_action_button("clear_log_btn", "🗑️ Clear Log", class_="btn btn-danger"),
                    ui.input_action_button("approve_btn", "✅ Approve", class_="btn btn-success"),
                    ui.input_action_button("reject_btn", "❌ Reject", class_="btn btn-danger"),
                    class_="action-buttons"
                ),
                
                # Approval Status Display
                ui.output_ui("approval_status_ui"),
                
                # Column Customization Section
                ui.div(
                    ui.div(
                        ui.h4("🔧 Display Columns (drag to reorder)"),
                        ui.input_action_button("reset_columns_btn", "Reset", class_="btn btn-sm btn-secondary"),
                        class_="column-config-header"
                    ),
                    ui.output_ui("column_selector"),
                    class_="column-config-section"
                ),
                
                # Data Table
                ui.div(
                    ui.div(
                        ui.output_ui("table_container"),
                        class_="table-scroll-wrapper"
                    ),
                    class_="table-container-frame"
                ),
                
                # Modifications Log
                ui.div(
                    ui.h3("📝 Modifications Log"),
                    ui.div(
                        ui.output_ui("modifications_log_ui"),
                        class_="log-container"
                    ),
                    class_="log-section"
                ),
                
                class_="right-panel"
            ),
            
            class_="main-container"
        ),
    )


# Create the UI instance
app_ui = create_app_ui()
