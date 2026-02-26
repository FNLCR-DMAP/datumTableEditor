// Row selection with Shift+Click support
let lastSelectedRow = null;

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
        const checkbox = e.target.closest('input[type="checkbox"][id*="select_"]');
        if (!checkbox) return;
        
        // Skip the header "select all" checkbox - it has its own handler
        if (checkbox.id === 'select_all_page') return;
        
        // Extract row index from checkbox id (select_0, select_1, etc.)
        const match = checkbox.id.match(/select_(\d+)/);
        if (!match) return;
        
        const currentRow = parseInt(match[1]);
        
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
        const checkbox = e.target.closest('input[type="checkbox"][id*="select_"]');
        if (checkbox) {
            updateRowHighlight(checkbox);
            updateSelectAllCheckbox(table);
        }
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
    const checkboxes = container.querySelectorAll('input[type="checkbox"][id*="select_"]');
    checkboxes.forEach(function(checkbox) {
        if (checkbox.checked) {
            checkbox.checked = false;
            updateRowHighlight(checkbox);
            if (typeof setShinyInput !== 'undefined') {
                // Extract just the input name part (select_N) from the full namespaced id
                const inputName = checkbox.id.includes('-') ? checkbox.id.split('-').pop() : checkbox.id;
                setShinyInput(inputName, false, {priority: 'event'}, checkbox);
            }
        }
    });
    lastSelectedRow = null;
    // Also uncheck the header checkbox
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

// Initialize row selection after table renders
$(document).on('shiny:value', function(event) {
    if (event.name && event.name.endsWith('table_container')) {
        // Reset last selected row on table re-render (e.g., page change)
        lastSelectedRow = null;
        var target = event.target;
        setTimeout(function() { initRowSelection(target); }, 100);
    }
});
