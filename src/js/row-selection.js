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

function initRowSelection() {
    const table = document.querySelector('.edit-table');
    if (!table) return;
    
    // Apply initial highlighting for any pre-checked checkboxes (handle namespaced IDs)
    const checkboxes = table.querySelectorAll('input[type="checkbox"][id*="select_"]');
    checkboxes.forEach(function(checkbox) {
        updateRowHighlight(checkbox);
    });
    
    // Use event delegation for checkbox clicks (handle namespaced IDs)
    table.addEventListener('click', function(e) {
        const checkbox = e.target.closest('input[type="checkbox"][id*="select_"]');
        if (!checkbox) return;
        
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
            
            // Select/deselect all rows in range
            for (let i = start; i <= end; i++) {
                const rowCheckbox = document.getElementById(`select_${i}`);
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
    });
    
    // Also listen for programmatic checkbox changes (from Shiny)
    table.addEventListener('change', function(e) {
        const checkbox = e.target.closest('input[type="checkbox"][id*="select_"]');
        if (checkbox) {
            updateRowHighlight(checkbox);
        }
    });
}

// Select all / deselect all functionality
window.selectAllRows = function() {
    const checkboxes = document.querySelectorAll('input[type="checkbox"][id*="select_"]');
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

window.deselectAllRows = function() {
    const checkboxes = document.querySelectorAll('input[type="checkbox"][id^="select_"]');
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
};

// Reset last selected row when page changes
window.resetRowSelection = function() {
    lastSelectedRow = null;
};

// Initialize row selection after table renders
$(document).on('shiny:value', function(event) {
    if (event.name === 'table_container') {
        // Reset last selected row on table re-render (e.g., page change)
        lastSelectedRow = null;
        setTimeout(initRowSelection, 100);
    }
});
