// Row selection with Shift+Click support
let lastSelectedRow = null;

// Check if this widget is in single-select mode
function _isSingleSelectMode(contextEl) {
    var container = _findWidgetContainer(contextEl);
    var nsHolder = container.querySelector('[data-selection-mode]');
    if (nsHolder && nsHolder.getAttribute('data-selection-mode') === 'single') {
        return true;
    }
    return false;
}

// Deselect all rows except the one at `keepIndex`
function _deselectOtherRows(table, keepIndex, keepCheckbox) {
    var container = _findWidgetContainer(table);
    const checkboxes = container.querySelectorAll('input[type="checkbox"][id*="select_"]:not(#select_all_page)');
    checkboxes.forEach(function(cb) {
        if (cb !== keepCheckbox && cb.checked) {
            cb.checked = false;
            updateRowHighlight(cb);
            if (typeof setShinyInput !== 'undefined') {
                const inputName = cb.id.includes('-') ? cb.id.split('-').pop() : cb.id;
                setShinyInput(inputName, false, {priority: 'event'}, cb);
            }
        }
    });
}

function updateRowHighlight(checkbox) {
    const row = checkbox.closest('tr');
    if (row) {
        if (checkbox.checked) {
            row.classList.add('row-selected');
        } else {
            row.classList.remove('row-selected');
        }
    }
}

function initRowSelection(contextEl) {
    var widgetContainer = _findWidgetContainer(contextEl);
    const table = widgetContainer.querySelector('.edit-table');
    if (!table) return;
    
    // Apply initial highlighting for any pre-checked checkboxes (handle namespaced IDs)
    const checkboxes = table.querySelectorAll('input[type="checkbox"][id*="select_"]:not(#select_all_page)');
    checkboxes.forEach(function(checkbox) {
        updateRowHighlight(checkbox);
    });
    
    // Update header checkbox state based on current selections
    updateSelectAllCheckbox(table);
    
    // Use event delegation for checkbox clicks (handle namespaced IDs)
    table.addEventListener('click', function(e) {
        // Find the checkbox - either clicked directly or via label/wrapper
        var checkbox = e.target.closest('input[type="checkbox"][id*="select_"]');
        if (!checkbox) {
            // User might have clicked the label or form-check wrapper
            var td = e.target.closest('td');
            if (td) {
                checkbox = td.querySelector('input[type="checkbox"][id*="select_"]');
            }
        }
        if (!checkbox) return;
        
        // Skip the header "select all" checkbox - it has its own handler
        if (checkbox.id === 'select_all_page' || checkbox.id.endsWith('select_all_page')) return;
        
        // Extract row index from checkbox id (select_0, select_1, etc.)
        const match = checkbox.id.match(/select_(\d+)/);
        if (!match) return;
        
        const currentRow = parseInt(match[1]);
        
        // Single-select mode: deselect all others when checking a row
        if (_isSingleSelectMode(table) && checkbox.checked) {
            _deselectOtherRows(table, currentRow, checkbox);
            updateRowHighlight(checkbox);
            lastSelectedRow = currentRow;
            updateSelectAllCheckbox(table);
            return;  // skip shift-click range logic
        }

        if (e.shiftKey && lastSelectedRow !== null) {
            e.preventDefault();
            
            // Get range of rows to select
            const start = Math.min(lastSelectedRow, currentRow);
            const end = Math.max(lastSelectedRow, currentRow);
            
            // Determine if we're selecting or deselecting based on last clicked checkbox state
            const shouldCheck = checkbox.checked;
            
            // Extract namespace prefix from the clicked checkbox (e.g., "module-" from "module-select_0")
            const namespaceMatch = checkbox.id.match(/^(.+-)?select_\d+$/);
            const prefix = namespaceMatch && namespaceMatch[1] ? namespaceMatch[1] : '';
            
            // Select/deselect all rows in range
            for (let i = start; i <= end; i++) {
                // Try with namespace prefix first, then without
                let rowCheckbox = table.querySelector(`input[type="checkbox"][id="${prefix}select_${i}"]`);
                if (!rowCheckbox) {
                    rowCheckbox = table.querySelector(`input[type="checkbox"][id$="select_${i}"]`);
                }
                if (rowCheckbox && rowCheckbox.checked !== shouldCheck) {
                    rowCheckbox.checked = shouldCheck;
                    updateRowHighlight(rowCheckbox);
                    // Trigger Shiny input change (pass checkbox as context)
                    if (typeof setShinyInput !== 'undefined') {
                        setShinyInput(`select_${i}`, shouldCheck, {priority: 'event'}, rowCheckbox);
                    }
                }
            }
        }
        
        // Update highlight for the clicked checkbox
        updateRowHighlight(checkbox);
        
        // Update last selected row
        lastSelectedRow = currentRow;
        
        // Update header checkbox state
        updateSelectAllCheckbox(table);
    });
    
    // Also listen for programmatic checkbox changes (from Shiny)
    table.addEventListener('change', function(e) {
        var checkbox = e.target.closest('input[type="checkbox"][id*="select_"]');
        if (!checkbox) {
            // For Shiny bindings that might fire change on wrapper elements
            var td = e.target.closest('td');
            if (td) checkbox = td.querySelector('input[type="checkbox"][id*="select_"]');
        }
        if (checkbox) {
            updateRowHighlight(checkbox);
            updateSelectAllCheckbox(table);
        }
    });

    // Periodic sync: ensure row-selected class stays in sync with checked state
    // This catches cases where Shiny bindings update checkboxes without firing events we can capture
    table.addEventListener('mouseup', function() {
        setTimeout(function() {
            var inputs = table.querySelectorAll('tbody input[type="checkbox"][id*="select_"]:not([id*="select_all"])');
            inputs.forEach(function(cb) { updateRowHighlight(cb); });
        }, 50);
    });
}

// Select all / deselect all functionality
window.selectAllRows = function(event) {
    var container = _findWidgetContainer(event ? event.target : document.activeElement);
    const checkboxes = container.querySelectorAll('input[type="checkbox"][id*="select_"]');
    checkboxes.forEach(function(checkbox) {
        if (!checkbox.checked) {
            checkbox.checked = true;
            updateRowHighlight(checkbox);
            if (typeof setShinyInput !== 'undefined') {
                // Extract just the input name part (select_N) from the full namespaced id
                const inputName = checkbox.id.includes('-') ? checkbox.id.split('-').pop() : checkbox.id;
                setShinyInput(inputName, true, {priority: 'event'}, checkbox);
            }
        }
    });
};

window.deselectAllRows = function(event) {
    var container = _findWidgetContainer(event ? event.target : document.activeElement);
    // Deselect checkboxes
    const checkboxes = container.querySelectorAll('input[type="checkbox"][id*="select_"]');
    checkboxes.forEach(function(checkbox) {
        if (checkbox.checked) {
            checkbox.checked = false;
            updateRowHighlight(checkbox);
            if (typeof setShinyInput !== 'undefined') {
                const inputName = checkbox.id.includes('-') ? checkbox.id.split('-').pop() : checkbox.id;
                setShinyInput(inputName, false, {priority: 'event'}, checkbox);
            }
        }
    });
    // Deselect radio buttons and clear highlights
    const radios = container.querySelectorAll('input[type="radio"][name="row_select"]');
    radios.forEach(function(radio) {
        if (radio.checked) {
            radio.checked = false;
            var row = radio.closest('tr');
            if (row) row.classList.remove('row-selected');
        }
    });
    if (radios.length > 0 && typeof setShinyInput !== 'undefined') {
        setShinyInput('selected_radio_row', null, {priority: 'event'}, radios[0]);
    }
    lastSelectedRow = null;
    const selectAllCheckbox = container.querySelector('#select_all_page, input[id$="select_all_page"]');
    if (selectAllCheckbox) selectAllCheckbox.checked = false;
};

// Toggle select all for current page (called from header checkbox)
window.toggleSelectAllPage = function(headerCheckbox) {
    const shouldCheck = headerCheckbox.checked;
    var container = _findWidgetContainer(headerCheckbox);
    const checkboxes = container.querySelectorAll('input[type="checkbox"][id*="select_"]:not(#select_all_page)');
    
    checkboxes.forEach(function(checkbox) {
        if (checkbox.checked !== shouldCheck) {
            checkbox.checked = shouldCheck;
            updateRowHighlight(checkbox);
            if (typeof setShinyInput !== 'undefined') {
                const inputName = checkbox.id.includes('-') ? checkbox.id.split('-').pop() : checkbox.id;
                setShinyInput(inputName, shouldCheck, {priority: 'event'}, checkbox);
            }
        }
    });
    
    if (!shouldCheck) {
        lastSelectedRow = null;
    }
};

// Update header checkbox state based on row selections
function updateSelectAllCheckbox(tableEl) {
    var container = tableEl ? _findWidgetContainer(tableEl) : document;
    const selectAllCheckbox = container.querySelector('#select_all_page, input[id$="select_all_page"]');
    if (!selectAllCheckbox) return;
    
    const rowCheckboxes = container.querySelectorAll('input[type="checkbox"][id*="select_"]:not(#select_all_page)');
    if (rowCheckboxes.length === 0) {
        selectAllCheckbox.checked = false;
        selectAllCheckbox.indeterminate = false;
        return;
    }
    
    const checkedCount = Array.from(rowCheckboxes).filter(cb => cb.checked).length;
    
    if (checkedCount === 0) {
        selectAllCheckbox.checked = false;
        selectAllCheckbox.indeterminate = false;
    } else if (checkedCount === rowCheckboxes.length) {
        selectAllCheckbox.checked = true;
        selectAllCheckbox.indeterminate = false;
    } else {
        selectAllCheckbox.checked = false;
        selectAllCheckbox.indeterminate = true;
    }
}

// Reset last selected row when page changes
window.resetRowSelection = function() {
    lastSelectedRow = null;
};

// Handle radio button selection (single-select mode)
window.handleRadioSelect = function(radio, rowIdx) {
    var container = _findWidgetContainer(radio);
    // Clear all row highlights (visual only — browser handles radio mutual exclusion)
    var allRows = container.querySelectorAll('.edit-table tbody tr.row-selected');
    allRows.forEach(function(tr) {
        tr.classList.remove('row-selected');
    });
    // Highlight selected row
    var row = radio.closest('tr');
    if (row) row.classList.add('row-selected');
    // Send single selected index to Shiny
    if (typeof setShinyInput !== 'undefined') {
        setShinyInput('selected_radio_row', rowIdx, {priority: 'event'}, radio);
    }
    lastSelectedRow = rowIdx;
};

// Initialize row selection after table renders
$(document).on('shiny:value', function(event) {
    if (event.name && event.name.endsWith('table_container')) {
        // Reset last selected row on table re-render (e.g., page change)
        lastSelectedRow = null;
        var target = event.target;
        setTimeout(function() { initRowSelection(target); }, 100);
    }
});
