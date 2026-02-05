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
            .histogram-fill.edited { background: #8B4513; }
            .histogram-fill.approved { background: #28a745; }
            .histogram-fill.rejected { background: #dc3545; }
            .histogram-count {
                width: 35px;
                font-size: 12px;
                font-weight: 600;
                text-align: right;
            }
            
            /* Histogram checkbox styling */
            .histogram-checkbox-label {
                display: flex;
                align-items: center;
                gap: 6px;
                width: 110px;
                cursor: pointer;
            }
            .histogram-checkbox-label input[type="checkbox"] {
                cursor: pointer;
                width: 14px;
                height: 14px;
            }
            .histogram-checkbox-label .histogram-label {
                width: auto;
            }
            
            /* Hide the actual shiny checkbox group - we use custom checkboxes */
            .stats-section > .shiny-input-checkboxgroup {
                display: none;
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
            }
            .action-buttons button {
                padding: 8px 14px;
                font-size: 13px;
            }
            
            /* Top Toolbar Row */
            .top-toolbar {
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: 15px;
                margin-bottom: 15px;
                padding: 12px;
                background: #f8f9fa;
                border-radius: 8px;
                border: 1px solid #dee2e6;
            }
            .toolbar-left {
                display: flex;
                gap: 8px;
                flex-wrap: wrap;
                align-items: center;
            }
            .toolbar-right {
                display: flex;
                gap: 10px;
                align-items: center;
            }
            
            /* Preset Dropdown */
            .preset-dropdown {
                position: relative;
                display: inline-block;
            }
            .preset-btn {
                padding: 8px 14px;
                font-size: 13px;
                border: 1px solid #ced4da;
                background: white;
                border-radius: 4px;
                cursor: pointer;
                display: flex;
                align-items: center;
                gap: 6px;
            }
            .preset-btn:hover {
                background: #f8f9fa;
            }
            .preset-menu {
                display: none;
                position: absolute;
                top: 100%;
                right: 0;
                min-width: 200px;
                background: white;
                border: 1px solid #dee2e6;
                border-radius: 6px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                z-index: 1000;
                margin-top: 4px;
            }
            .preset-menu.show {
                display: block;
            }
            .preset-menu-item {
                padding: 10px 14px;
                cursor: pointer;
                display: flex;
                justify-content: space-between;
                align-items: center;
                font-size: 13px;
            }
            .preset-menu-item:hover {
                background: #f8f9fa;
            }
            .preset-menu-item.active {
                background: #e3f2fd;
                font-weight: 600;
            }
            .preset-menu-item .delete-preset {
                color: #dc3545;
                opacity: 0.7;
                cursor: pointer;
            }
            .preset-menu-item .delete-preset:hover {
                opacity: 1;
            }
            .preset-menu-divider {
                border-top: 1px solid #dee2e6;
                margin: 4px 0;
            }
            .preset-save-row {
                padding: 10px 14px;
                display: flex;
                gap: 6px;
            }
            .preset-save-row input {
                flex: 1;
                padding: 6px 10px;
                border: 1px solid #ced4da;
                border-radius: 4px;
                font-size: 12px;
            }
            
            /* Add Column Button */
            .add-col-btn {
                padding: 8px 14px;
                font-size: 13px;
                border: 1px solid #28a745;
                background: #28a745;
                color: white;
                border-radius: 4px;
                cursor: pointer;
            }
            .add-col-btn:hover {
                background: #218838;
            }
            
            /* Modal Styles */
            .modal-overlay {
                display: none;
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0,0,0,0.5);
                z-index: 2000;
                justify-content: center;
                align-items: center;
            }
            .modal-overlay.show {
                display: flex;
            }
            .modal-content {
                background: white;
                border-radius: 8px;
                padding: 20px;
                max-width: 500px;
                width: 90%;
                max-height: 80vh;
                overflow-y: auto;
                box-shadow: 0 4px 20px rgba(0,0,0,0.3);
            }
            .modal-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 15px;
                padding-bottom: 10px;
                border-bottom: 1px solid #dee2e6;
            }
            .modal-header h3 {
                margin: 0;
                font-size: 16px;
            }
            .modal-close {
                background: none;
                border: none;
                font-size: 20px;
                cursor: pointer;
                color: #6c757d;
            }
            .modal-close:hover {
                color: #343a40;
            }
            .modal-body {
                margin-bottom: 15px;
            }
            .available-cols-grid {
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
            }
            .add-col-tag {
                padding: 6px 12px;
                background: #e9ecef;
                border-radius: 4px;
                font-size: 12px;
                cursor: pointer;
            }
            .add-col-tag:hover {
                background: #28a745;
                color: white;
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
                background: white;
                position: relative;
            }
            .table-scroll-wrapper {
                height: 100%;
                overflow: auto;
                position: relative;
            }
            .edit-table {
                width: 100%;
                font-size: 13px;
                border-collapse: separate;
                border-spacing: 0;
            }
            .edit-table thead {
                position: sticky;
                top: 0;
                z-index: 10;
            }
            .edit-table th {
                background-color: #495057;
                color: white;
                padding: 10px 8px;
                text-align: left;
                font-weight: 600;
                white-space: nowrap;
                user-select: none;
                border-bottom: 2px solid #343a40;
                border-right: 1px solid #6c757d;
                position: relative;
            }
            .edit-table th.draggable-header {
                cursor: grab;
                padding-right: 35px;
                min-width: 100px;
                width: 100px;
            }
            .edit-table th.draggable-header:active {
                cursor: grabbing;
            }
            .edit-table th.draggable-header.drag-over {
                background-color: #343a40;
                box-shadow: inset 0 0 0 2px #3498db;
            }
            /* Column resize handle */
            .resize-handle {
                position: absolute;
                right: 0;
                top: 0;
                bottom: 0;
                width: 5px;
                cursor: col-resize;
                background: transparent;
            }
            .resize-handle:hover {
                background: #3498db;
            }
            .remove-header-btn {
                position: absolute;
                right: 12px;
                top: 50%;
                transform: translateY(-50%);
                background: transparent;
                border: none;
                color: rgba(255,255,255,0.6);
                cursor: pointer;
                font-size: 16px;
                font-weight: bold;
                padding: 0 4px;
                line-height: 1;
            }
            .remove-header-btn:hover {
                color: #ff6b6b;
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
                padding: 3px 8px;
                border-radius: 3px;
                font-size: 11px;
                font-weight: bold;
            }
            .status-edited { background-color: #8B4513; color: white; }
            .status-approved { background-color: #28a745; color: white; }
            .status-rejected { background-color: #dc3545; color: white; }
            .status-unprocessed { background-color: #e2e3e5; color: #383d41; }
            
            /* Histogram label colors */
            .status-label-edited { color: #8B4513; font-weight: 600; }
            .status-label-approved { color: #28a745; font-weight: 600; }
            .status-label-rejected { color: #dc3545; font-weight: 600; }
            .status-label-unprocessed { color: #6c757d; }
            
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
            
            /* Pagination Controls */
            .pagination-controls-section {
                margin-bottom: 10px;
            }
            .pagination-bar {
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: 10px 15px;
                background: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 6px;
            }
            .pagination-info {
                font-size: 13px;
                color: #495057;
            }
            .pagination-buttons {
                display: flex;
                gap: 5px;
                align-items: center;
            }
            .pagination-buttons button {
                padding: 6px 12px;
                font-size: 13px;
                border: 1px solid #dee2e6;
                background: white;
                border-radius: 4px;
                cursor: pointer;
            }
            .pagination-buttons button:hover:not(:disabled) {
                background: #e9ecef;
            }
            .pagination-buttons button:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }
            .pagination-buttons .page-indicator {
                padding: 6px 12px;
                font-size: 13px;
                font-weight: 600;
                color: #495057;
            }
            .page-jump {
                display: flex;
                align-items: center;
                gap: 5px;
            }
            .page-jump input {
                width: 60px;
                padding: 5px;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                text-align: center;
                font-size: 13px;
            }
            .page-jump button {
                padding: 5px 10px;
                font-size: 12px;
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
            # JavaScript for panel toggle, header drag-drop, modal, preset management
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
            
            // Header drag and drop for column reordering
            let draggedHeader = null;
            
            window.initHeaderDrag = function() {
                document.querySelectorAll('.draggable-header').forEach(header => {
                    header.addEventListener('dragstart', function(e) {
                        draggedHeader = this;
                        this.style.opacity = '0.5';
                        e.dataTransfer.effectAllowed = 'move';
                    });
                    
                    header.addEventListener('dragend', function(e) {
                        this.style.opacity = '1';
                        document.querySelectorAll('.draggable-header').forEach(h => h.classList.remove('drag-over'));
                        if (draggedHeader) {
                            updateHeaderOrder();
                        }
                        draggedHeader = null;
                    });
                    
                    header.addEventListener('dragover', function(e) {
                        e.preventDefault();
                        if (draggedHeader && draggedHeader !== this) {
                            this.classList.add('drag-over');
                        }
                    });
                    
                    header.addEventListener('dragleave', function(e) {
                        this.classList.remove('drag-over');
                    });
                    
                    header.addEventListener('drop', function(e) {
                        e.preventDefault();
                        this.classList.remove('drag-over');
                        if (draggedHeader && draggedHeader !== this) {
                            const headerRow = this.parentNode;
                            const allHeaders = [...headerRow.querySelectorAll('.draggable-header')];
                            const draggedIdx = allHeaders.indexOf(draggedHeader);
                            const dropIdx = allHeaders.indexOf(this);
                            
                            if (draggedIdx < dropIdx) {
                                headerRow.insertBefore(draggedHeader, this.nextSibling);
                            } else {
                                headerRow.insertBefore(draggedHeader, this);
                            }
                        }
                    });
                });
            };
            
            function updateHeaderOrder() {
                const headers = document.querySelectorAll('.draggable-header');
                const columns = [...headers].map(h => h.dataset.column);
                if (typeof Shiny !== 'undefined') {
                    Shiny.setInputValue('column_order', columns, {priority: 'event'});
                }
            }
            
            // Column resizing
            let resizing = null;
            let startX = 0;
            let startWidth = 0;
            
            window.initColumnResize = function() {
                document.querySelectorAll('.resize-handle').forEach(handle => {
                    handle.addEventListener('mousedown', function(e) {
                        e.stopPropagation();
                        e.preventDefault();
                        const th = this.parentElement;
                        resizing = th;
                        startX = e.pageX;
                        startWidth = th.offsetWidth;
                        document.body.style.cursor = 'col-resize';
                        document.body.style.userSelect = 'none';
                    });
                });
            };
            
            document.addEventListener('mousemove', function(e) {
                if (resizing) {
                    const diff = e.pageX - startX;
                    const newWidth = Math.max(80, startWidth + diff);
                    resizing.style.width = newWidth + 'px';
                    resizing.style.minWidth = newWidth + 'px';
                }
            });
            
            document.addEventListener('mouseup', function(e) {
                if (resizing) {
                    // Save column widths
                    saveColumnWidths();
                    resizing = null;
                    document.body.style.cursor = '';
                    document.body.style.userSelect = '';
                }
            });
            
            function saveColumnWidths() {
                const headers = document.querySelectorAll('.draggable-header');
                const widths = {};
                headers.forEach(h => {
                    const col = h.dataset.column;
                    const width = h.offsetWidth;
                    if (col && width) {
                        widths[col] = width;
                    }
                });
                if (typeof Shiny !== 'undefined') {
                    Shiny.setInputValue('column_widths', widths, {priority: 'event'});
                }
            }
            
            // Remove column from header - use event delegation
            document.addEventListener('click', function(e) {
                if (e.target.classList.contains('remove-header-btn')) {
                    e.stopPropagation();
                    e.preventDefault();
                    const col = e.target.dataset.column;
                    console.log('Remove button clicked for column:', col);
                    if (col && typeof Shiny !== 'undefined') {
                        // Send unique value each time to ensure event fires
                        Shiny.setInputValue('remove_column', {col: col, ts: Date.now()}, {priority: 'event'});
                    }
                }
            });
            
            // Legacy function for compatibility
            window.removeColumn = function(col, event) {
                if (event) {
                    event.stopPropagation();
                    event.preventDefault();
                }
                console.log('removeColumn called for:', col);
                if (typeof Shiny !== 'undefined') {
                    Shiny.setInputValue('remove_column', {col: col, ts: Date.now()}, {priority: 'event'});
                }
            };
            
            // Add column
            window.addColumn = function(col) {
                if (typeof Shiny !== 'undefined') {
                    Shiny.setInputValue('add_column', col, {priority: 'event'});
                }
                closeModal();
            };
            
            // Modal functions
            window.openAddColumnModal = function() {
                document.getElementById('add-column-modal').classList.add('show');
            };
            
            window.closeModal = function() {
                document.getElementById('add-column-modal').classList.remove('show');
            };
            
            // Close modal on overlay click
            document.addEventListener('click', function(e) {
                if (e.target.classList.contains('modal-overlay')) {
                    closeModal();
                }
            });
            
            // Preset dropdown
            window.togglePresetMenu = function(event) {
                event.stopPropagation();
                const menu = document.getElementById('preset-menu');
                menu.classList.toggle('show');
            };
            
            // Close dropdown when clicking outside
            document.addEventListener('click', function(e) {
                const dropdown = document.querySelector('.preset-dropdown');
                if (dropdown && !dropdown.contains(e.target)) {
                    document.getElementById('preset-menu').classList.remove('show');
                }
            });
            
            window.loadPreset = function(presetName) {
                if (typeof Shiny !== 'undefined') {
                    Shiny.setInputValue('load_preset', presetName, {priority: 'event'});
                }
                document.getElementById('preset-menu').classList.remove('show');
            };
            
            window.deletePreset = function(presetName, event) {
                event.stopPropagation();
                if (confirm('Delete preset "' + presetName + '"?')) {
                    if (typeof Shiny !== 'undefined') {
                        Shiny.setInputValue('delete_preset', presetName, {priority: 'event'});
                    }
                }
            };
            
            window.saveNewPreset = function() {
                const input = document.getElementById('new-preset-name');
                const name = input.value.trim();
                if (name) {
                    if (typeof Shiny !== 'undefined') {
                        Shiny.setInputValue('save_preset_name', name, {priority: 'event'});
                    }
                    input.value = '';
                }
            };
            
            // Reset columns
            window.resetColumns = function() {
                if (typeof Shiny !== 'undefined') {
                    Shiny.setInputValue('reset_columns', Date.now(), {priority: 'event'});
                }
                document.getElementById('preset-menu').classList.remove('show');
            };
            
            // Initialize header drag after Shiny renders
            $(document).on('shiny:value', function(event) {
                if (event.name === 'table_container') {
                    setTimeout(function() {
                        initHeaderDrag();
                        initColumnResize();
                    }, 100);
                }
                // Initialize histogram checkbox sync
                if (event.name === 'stats_histogram') {
                    setTimeout(initHistogramCheckboxes, 50);
                }
            });
            
            // Sync histogram checkboxes with Shiny checkbox group
            function initHistogramCheckboxes() {
                const histogramCheckboxes = document.querySelectorAll('.status-checkbox');
                histogramCheckboxes.forEach(function(checkbox) {
                    checkbox.addEventListener('change', function() {
                        // Get all checked statuses
                        const checked = [];
                        document.querySelectorAll('.status-checkbox:checked').forEach(function(cb) {
                            checked.push(cb.value);
                        });
                        // Update the hidden Shiny checkbox group
                        if (typeof Shiny !== 'undefined') {
                            Shiny.setInputValue('status_filter_multi', checked);
                        }
                    });
                });
            }
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
                    
                    # Pagination Controls
                    ui.div(
                        ui.h4("Pagination"),
                        ui.div(
                            ui.tags.label("Rows per page"),
                            ui.input_select(
                                "rows_per_page",
                                label=None,
                                choices={
                                    "10": "10 rows",
                                    "25": "25 rows",
                                    "50": "50 rows",
                                    "100": "100 rows",
                                    "all": "All rows"
                                },
                                selected="25"
                            ),
                            class_="filter-group"
                        ),
                        class_="filter-section"
                    ),
                    
                    # Column Filters
                    ui.div(
                        ui.h4("Column Filters"),
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
                # Top Toolbar - Actions + Preset + Add Column
                ui.div(
                    # Left side - Action Buttons
                    ui.div(
                        ui.input_action_button("save_btn", "Save", class_="btn btn-success"),
                        ui.input_action_button("export_btn", "Export CSV", class_="btn btn-info"),
                        ui.input_action_button("reload_btn", "Reload", class_="btn btn-warning"),
                        ui.input_action_button("clear_log_btn", "Clear Log", class_="btn btn-danger"),
                        ui.input_action_button("approve_btn", "Approve", class_="btn btn-success"),
                        ui.input_action_button("reject_btn", "Reject", class_="btn btn-danger"),
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
                        # Add Column Button
                        ui.tags.button("+ Add Column", class_="add-col-btn", onclick="openAddColumnModal()"),
                        class_="toolbar-right"
                    ),
                    class_="top-toolbar"
                ),
                
                # Add Column Modal
                ui.div(
                    ui.div(
                        ui.div(
                            ui.h3("Add Columns"),
                            ui.tags.button("×", class_="modal-close", onclick="closeModal()"),
                            class_="modal-header"
                        ),
                        ui.div(
                            ui.p("Click a column to add it to the table:", style="margin-bottom: 10px; color: #666;"),
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
                
                # Pagination Controls
                ui.div(
                    ui.output_ui("pagination_controls"),
                    class_="pagination-controls-section"
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
                    ui.h3("Modifications Log"),
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
