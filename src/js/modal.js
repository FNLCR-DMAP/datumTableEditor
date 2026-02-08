// Modal functions
window.openAddColumnModal = function(event) {
    // Trigger refresh when opening modal (pass event target for namespace detection)
    if (typeof setShinyInput !== 'undefined') {
        var contextEl = event ? event.target : document.activeElement;
        setShinyInput('refresh_preset', Date.now(), {priority: 'event'}, contextEl);
    }
    document.getElementById('add-column-modal').classList.add('show');
    // Initialize modal drag after a short delay
    setTimeout(initModalColumnDrag, 100);
};

window.closeModal = function() {
    document.getElementById('add-column-modal').classList.remove('show');
};

// Log Modal functions
window.openLogModal = function() {
    document.getElementById('log-modal').classList.add('show');
};

window.closeLogModal = function() {
    document.getElementById('log-modal').classList.remove('show');
};

// Modal column drag and drop for reordering
let modalDraggedCol = null;

function initModalColumnDrag() {
    const container = document.getElementById('modal-columns-container');
    if (!container) return;
    
    const cols = container.querySelectorAll('.modal-draggable-col');
    cols.forEach(col => {
        col.addEventListener('dragstart', function(e) {
            modalDraggedCol = this;
            this.style.opacity = '0.5';
            e.dataTransfer.effectAllowed = 'move';
        });
        
        col.addEventListener('dragend', function(e) {
            this.style.opacity = '1';
            container.querySelectorAll('.modal-draggable-col').forEach(c => c.classList.remove('drag-over-modal'));
            if (modalDraggedCol) {
                updateModalColumnOrder();
            }
            modalDraggedCol = null;
        });
        
        col.addEventListener('dragover', function(e) {
            e.preventDefault();
            if (modalDraggedCol && modalDraggedCol !== this) {
                this.classList.add('drag-over-modal');
            }
        });
        
        col.addEventListener('dragleave', function(e) {
            this.classList.remove('drag-over-modal');
        });
        
        col.addEventListener('drop', function(e) {
            e.preventDefault();
            if (modalDraggedCol && modalDraggedCol !== this) {
                const container = this.parentNode;
                const allCols = Array.from(container.querySelectorAll('.modal-draggable-col'));
                const draggedIdx = allCols.indexOf(modalDraggedCol);
                const targetIdx = allCols.indexOf(this);
                
                if (draggedIdx < targetIdx) {
                    this.parentNode.insertBefore(modalDraggedCol, this.nextSibling);
                } else {
                    this.parentNode.insertBefore(modalDraggedCol, this);
                }
            }
            this.classList.remove('drag-over-modal');
        });
    });
}

function updateModalColumnOrder() {
    const container = document.getElementById('modal-columns-container');
    if (!container) return;
    
    const cols = container.querySelectorAll('.modal-draggable-col');
    const newOrder = [];
    cols.forEach(col => {
        const colName = col.dataset.column;
        if (colName) newOrder.push(colName);
    });
    
    if (newOrder.length > 0 && typeof setShinyInput !== 'undefined') {
        // Send with timestamp to ensure event fires (use container as context)
        setShinyInput('column_order', {order: newOrder, ts: Date.now()}, {priority: 'event'}, container);
    }
}

// Re-init modal drag when available_columns_modal updates
$(document).on('shiny:value', function(event) {
    if (event.name === 'available_columns_modal') {
        setTimeout(initModalColumnDrag, 100);
    }
});

// Close modal on overlay click (only if clicking directly on overlay, not content)
document.addEventListener('click', function(e) {
    if (e.target.id === 'add-column-modal') {
        closeModal();
    }
    if (e.target.id === 'copy-column-modal') {
        closeCopyModal();
    }
    if (e.target.id === 'add-filter-modal') {
        closeAddFilterModal();
    }
});

// Copy Column Modal functions
window.openCopyModal = function(event) {
    // Trigger refresh of column list (pass event target for namespace detection)
    if (typeof setShinyInput !== 'undefined') {
        var contextEl = event ? event.target : document.activeElement;
        setShinyInput('refresh_copy_columns', Date.now(), {priority: 'event'}, contextEl);
    }
    document.getElementById('copy-column-modal').classList.add('show');
};

window.closeCopyModal = function() {
    document.getElementById('copy-column-modal').classList.remove('show');
};

window.copyColumnValues = function(columnName, event) {
    // Get selected rows from checkboxes (handle namespaced IDs like editor1-select_0)
    const checkboxes = document.querySelectorAll('input[type="checkbox"][id*="select_"]:checked');
    if (checkboxes.length === 0) {
        alert('Please select at least one row to copy values from.');
        return;
    }
    
    // Trigger server-side copy
    if (typeof setShinyInput !== 'undefined') {
        const selectedIndices = [];
        checkboxes.forEach(function(cb) {
            const match = cb.id.match(/select_(\d+)/);
            if (match) {
                selectedIndices.push(parseInt(match[1]));
            }
        });
        
        var contextEl = event ? event.target : document.activeElement;
        setShinyInput('copy_column_request', {
            column: columnName,
            indices: selectedIndices,
            ts: Date.now()
        }, {priority: 'event'}, contextEl);
    }
    
    closeCopyModal();
};

// Add Filter Modal functions
window.openAddFilterModal = function(event) {
    document.getElementById('add-filter-modal').classList.add('show');
};

window.closeAddFilterModal = function() {
    document.getElementById('add-filter-modal').classList.remove('show');
};

window.addFilter = function(columnName, event) {
    if (typeof setShinyInput !== 'undefined') {
        var contextEl = event ? event.target : document.activeElement;
        setShinyInput('add_filter_column', {
            column: columnName,
            ts: Date.now()
        }, {priority: 'event'}, contextEl);
    }
    closeAddFilterModal();
};

window.removeFilter = function(columnName, event) {
    if (typeof setShinyInput !== 'undefined') {
        var contextEl = event ? event.target : document.activeElement;
        setShinyInput('remove_filter_column', {
            column: columnName,
            ts: Date.now()
        }, {priority: 'event'}, contextEl);
    }
};

// Undo a modification from the log
window.undoModification = function(logIndex, event) {
    if (typeof setShinyInput !== 'undefined') {
        var contextEl = event ? event.target : document.activeElement;
        setShinyInput('undo_modification', {
            index: logIndex,
            ts: Date.now()
        }, {priority: 'event'}, contextEl);
    }
};