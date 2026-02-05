// Modal functions
window.openAddColumnModal = function() {
    // Trigger refresh when opening modal
    if (typeof Shiny !== 'undefined') {
        Shiny.setInputValue('refresh_preset', Date.now(), {priority: 'event'});
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
    
    console.log('Modal column order updated:', newOrder);
    if (newOrder.length > 0 && typeof Shiny !== 'undefined') {
        // Send with timestamp to ensure event fires
        Shiny.setInputValue('column_order', {order: newOrder, ts: Date.now()}, {priority: 'event'});
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
window.openCopyModal = function() {
    // Trigger refresh of column list
    if (typeof Shiny !== 'undefined') {
        Shiny.setInputValue('refresh_copy_columns', Date.now(), {priority: 'event'});
    }
    document.getElementById('copy-column-modal').classList.add('show');
};

window.closeCopyModal = function() {
    document.getElementById('copy-column-modal').classList.remove('show');
};

window.copyColumnValues = function(columnName) {
    // Get selected rows from checkboxes
    const checkboxes = document.querySelectorAll('input[type="checkbox"][id^="select_"]:checked');
    if (checkboxes.length === 0) {
        alert('Please select at least one row to copy values from.');
        return;
    }
    
    // Trigger server-side copy
    if (typeof Shiny !== 'undefined') {
        const selectedIndices = [];
        checkboxes.forEach(function(cb) {
            const match = cb.id.match(/select_(\d+)/);
            if (match) {
                selectedIndices.push(parseInt(match[1]));
            }
        });
        
        Shiny.setInputValue('copy_column_request', {
            column: columnName,
            indices: selectedIndices,
            ts: Date.now()
        }, {priority: 'event'});
    }
    
    closeCopyModal();
};

// Add Filter Modal functions
window.openAddFilterModal = function() {
    document.getElementById('add-filter-modal').classList.add('show');
};

window.closeAddFilterModal = function() {
    document.getElementById('add-filter-modal').classList.remove('show');
};

window.addFilter = function(columnName) {
    if (typeof Shiny !== 'undefined') {
        Shiny.setInputValue('add_filter_column', {
            column: columnName,
            ts: Date.now()
        }, {priority: 'event'});
    }
    closeAddFilterModal();
};

window.removeFilter = function(columnName) {
    if (typeof Shiny !== 'undefined') {
        Shiny.setInputValue('remove_filter_column', {
            column: columnName,
            ts: Date.now()
        }, {priority: 'event'});
    }
};

// Undo a modification from the log
window.undoModification = function(logIndex) {
    if (typeof Shiny !== 'undefined') {
        Shiny.setInputValue('undo_modification', {
            index: logIndex,
            ts: Date.now()
        }, {priority: 'event'});
    }
};