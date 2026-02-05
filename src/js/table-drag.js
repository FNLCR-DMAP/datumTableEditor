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
        const newWidth = Math.max(10, startWidth + diff);
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

// Header action dropdown - use event delegation
document.addEventListener('click', function(e) {
    // Toggle dropdown when clicking action button
    if (e.target.classList.contains('header-action-btn')) {
        e.stopPropagation();
        e.preventDefault();
        
        const dropdown = e.target.nextElementSibling;
        const isOpen = dropdown.classList.contains('show');
        
        // Close all other dropdowns first
        document.querySelectorAll('.header-dropdown.show').forEach(d => d.classList.remove('show'));
        
        // Toggle this dropdown
        if (!isOpen) {
            dropdown.classList.add('show');
        }
        return;
    }
    
    // Handle sort ascending
    if (e.target.classList.contains('sort-asc-btn')) {
        e.stopPropagation();
        e.preventDefault();
        const col = e.target.dataset.column;
        if (col && typeof Shiny !== 'undefined') {
            Shiny.setInputValue('sort_column', {col: col, direction: 'asc', ts: Date.now()}, {priority: 'event'});
        }
        document.querySelectorAll('.header-dropdown.show').forEach(d => d.classList.remove('show'));
        return;
    }
    
    // Handle sort descending
    if (e.target.classList.contains('sort-desc-btn')) {
        e.stopPropagation();
        e.preventDefault();
        const col = e.target.dataset.column;
        if (col && typeof Shiny !== 'undefined') {
            Shiny.setInputValue('sort_column', {col: col, direction: 'desc', ts: Date.now()}, {priority: 'event'});
        }
        document.querySelectorAll('.header-dropdown.show').forEach(d => d.classList.remove('show'));
        return;
    }
    
    // Handle remove column
    if (e.target.classList.contains('remove-col-btn')) {
        e.stopPropagation();
        e.preventDefault();
        const col = e.target.dataset.column;
        if (col && typeof Shiny !== 'undefined') {
            Shiny.setInputValue('remove_column', {col: col, ts: Date.now()}, {priority: 'event'});
        }
        document.querySelectorAll('.header-dropdown.show').forEach(d => d.classList.remove('show'));
        return;
    }
    
    // Close dropdowns when clicking elsewhere
    document.querySelectorAll('.header-dropdown.show').forEach(d => d.classList.remove('show'));
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
window.addColumn = function(col, event) {
    if (event) event.stopPropagation();
    if (typeof Shiny !== 'undefined') {
        Shiny.setInputValue('add_column', {col: col, ts: Date.now()}, {priority: 'event'});
    }
};

// Remove column from modal
window.removeColumnFromModal = function(col, event) {
    if (event) event.stopPropagation();
    if (typeof Shiny !== 'undefined') {
        Shiny.setInputValue('remove_column', {col: col, ts: Date.now()}, {priority: 'event'});
    }
};

// Initialize header drag after Shiny renders
$(document).on('shiny:value', function(event) {
    if (event.name === 'table_container') {
        setTimeout(function() {
            initHeaderDrag();
            initColumnResize();
        }, 100);
    }
});
