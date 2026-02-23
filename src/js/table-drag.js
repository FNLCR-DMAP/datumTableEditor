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
    if (typeof setShinyInput !== 'undefined') {
        // Use first header as context for namespace detection
        setShinyInput('column_order', columns, {priority: 'event'}, headers[0]);
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
        const newWidth = Math.max(50, startWidth + diff);
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
    if (typeof setShinyInput !== 'undefined') {
        // Use first header as context for namespace detection
        setShinyInput('column_widths', widths, {priority: 'event'}, headers[0]);
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
        if (col && typeof setShinyInput !== 'undefined') {
            setShinyInput('sort_column', {col: col, direction: 'asc', ts: Date.now()}, {priority: 'event'}, e.target);
        }
        document.querySelectorAll('.header-dropdown.show').forEach(d => d.classList.remove('show'));
        return;
    }
    
    // Handle sort descending
    if (e.target.classList.contains('sort-desc-btn')) {
        e.stopPropagation();
        e.preventDefault();
        const col = e.target.dataset.column;
        if (col && typeof setShinyInput !== 'undefined') {
            setShinyInput('sort_column', {col: col, direction: 'desc', ts: Date.now()}, {priority: 'event'}, e.target);
        }
        document.querySelectorAll('.header-dropdown.show').forEach(d => d.classList.remove('show'));
        return;
    }
    
    // Handle remove column
    if (e.target.classList.contains('remove-col-btn')) {
        e.stopPropagation();
        e.preventDefault();
        const col = e.target.dataset.column;
        if (col && typeof setShinyInput !== 'undefined') {
            setShinyInput('remove_column', {col: col, ts: Date.now()}, {priority: 'event'}, e.target);
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
    if (typeof setShinyInput !== 'undefined') {
        setShinyInput('remove_column', {col: col, ts: Date.now()}, {priority: 'event'});
    }
};

// Add column
window.addColumn = function(col, event) {
    if (event) event.stopPropagation();
    if (typeof setShinyInput !== 'undefined') {
        setShinyInput('add_column', {col: col, ts: Date.now()}, {priority: 'event'});
    }
};

// Remove all columns from modal (DOM manipulation + batch server update)
window.removeAllColumns = function(event) {
    if (event) event.stopPropagation();
    var container = document.getElementById('modal-columns-container');
    if (!container) return;
    
    // Move all current columns to available section
    var currentTags = container.querySelectorAll('.modal-draggable-col');
    var availableSection = container.closest('.modal-body')
        ?.querySelectorAll('div > div')[1]; // Second section = "Remaining columns"
    if (!availableSection) {
        // Fallback: find the div after the current columns container's parent
        var sections = container.closest('.modal-body')?.children;
        if (sections && sections.length > 1) {
            availableSection = sections[1].querySelector('div');
        }
    }
    
    currentTags.forEach(function(tag) {
        var col = tag.getAttribute('data-column');
        if (col && availableSection) {
            // Create an available tag
            var addTag = document.createElement('div');
            addTag.className = 'add-col-tag';
            addTag.textContent = '+ ' + col;
            addTag.style.cssText = 'display: inline-block; padding: 6px 12px; background: #e9ecef; border-radius: 4px; font-size: 12px; cursor: pointer; margin: 3px;';
            var safeCol = col.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
            addTag.setAttribute('onclick', "addColumn('" + safeCol + "', event)");
            availableSection.appendChild(addTag);
        }
        tag.remove();
    });
    
    // Send empty column list to server
    if (typeof setShinyInput !== 'undefined') {
        setShinyInput('column_order', {order: [], ts: Date.now()}, {priority: 'event'});
    }
};

// Add all remaining columns to current columns (DOM manipulation + batch server update)
window.addAllColumns = function(event) {
    if (event) event.stopPropagation();
    var container = document.getElementById('modal-columns-container');
    if (!container) return;
    
    // Find available column tags
    var modalBody = container.closest('.modal-body');
    if (!modalBody) return;
    var availableTags = modalBody.querySelectorAll('.add-col-tag');
    
    // Get current column count for numbering
    var currentCount = container.querySelectorAll('.modal-draggable-col').length;
    
    availableTags.forEach(function(tag) {
        var text = tag.textContent.replace(/^\+\s*/, '').trim();
        // Find the real column name from onclick attribute
        var onclickAttr = tag.getAttribute('onclick') || '';
        var match = onclickAttr.match(/addColumn\('([^']+)'/);
        var col = match ? match[1].replace(/\\\\/g, '\\').replace(/\\'/g, "'") : text;
        currentCount++;
        
        // Create a current column tag
        var currentTag = document.createElement('div');
        currentTag.className = 'current-col-tag modal-draggable-col';
        currentTag.setAttribute('draggable', 'true');
        currentTag.setAttribute('data-column', col);
        currentTag.style.cssText = 'display: inline-flex; align-items: center; padding: 6px 10px; background: #2c3e50; color: white; border-radius: 4px; font-size: 12px; margin: 3px; cursor: move;';
        
        var safeCol = col.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
        currentTag.innerHTML = '<span class="drag-handle-modal" style="cursor: grab; margin-right: 6px; color: rgba(255,255,255,0.5);">⠃</span>' +
            '<span style="margin-right: 8px;">' + currentCount + '. ' + col + '</span>' +
            '<button class="remove-modal-col" onclick="removeColumnFromModal(\'' + safeCol + '\', event)" style="background: none; border: none; color: rgba(255,255,255,0.7); cursor: pointer; font-size: 14px;">×</button>';
        
        container.appendChild(currentTag);
        tag.remove();
    });
    
    // Collect all column names and send to server
    var allCols = [];
    container.querySelectorAll('.modal-draggable-col').forEach(function(el) {
        var c = el.getAttribute('data-column');
        if (c) allCols.push(c);
    });
    if (typeof setShinyInput !== 'undefined') {
        setShinyInput('column_order', {order: allCols, ts: Date.now()}, {priority: 'event'});
    }
};

// Remove column from modal
window.removeColumnFromModal = function(col, event) {
    if (event) event.stopPropagation();
    var contextEl = event ? event.target : document.activeElement;
    if (typeof setShinyInput !== 'undefined') {
        setShinyInput('remove_column', {col: col, ts: Date.now()}, {priority: 'event'}, contextEl);
    }
};

// Initialize header drag after Shiny renders
$(document).on('shiny:value', function(event) {
    // Check if the event name ends with table_container (namespaced)
    if (event.name && event.name.endsWith('table_container')) {
        setTimeout(function() {
            initHeaderDrag();
            initColumnResize();
        }, 100);
    }
});
