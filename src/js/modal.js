// Modal functions
// Store reference to the current context for finding the right modal
let currentModalContext = null;

// Helper to find modal within the same tab/widget as the context element
function findModalInContext(contextEl, modalId) {
    if (!contextEl) {
        return document.getElementById(modalId);
    }
    // Walk up to find the tab-pane or widget container
    let container = contextEl.closest('.tab-pane, [role="tabpanel"], .main-container');
    if (container) {
        let modal = container.querySelector('#' + modalId);
        if (modal) return modal;
    }
    // Fallback: find the active tab's modal
    let activeTab = document.querySelector('.tab-pane.active #' + modalId);
    if (activeTab) return activeTab;
    // Last resort: first modal found
    return document.getElementById(modalId);
}

window.openAddColumnModal = function(event) {
    // Store context for later use
    currentModalContext = event ? event.target : document.activeElement;
    
    // Trigger refresh when opening modal (pass event target for namespace detection)
    if (typeof setShinyInput !== 'undefined') {
        setShinyInput('refresh_preset', Date.now(), {priority: 'event'}, currentModalContext);
    }
    var modal = findModalInContext(currentModalContext, 'add-column-modal');
    if (modal) modal.classList.add('show');
    // Initialize modal drag after a short delay
    setTimeout(function() { initModalColumnDrag(currentModalContext); }, 100);
};

window.closeModal = function() {
    var modal = findModalInContext(currentModalContext, 'add-column-modal');
    if (modal) modal.classList.remove('show');
    currentModalContext = null;
};

// Log Modal functions
let currentLogModalContext = null;

window.openLogModal = function(event) {
    currentLogModalContext = event ? event.target : document.activeElement;
    var modal = findModalInContext(currentLogModalContext, 'log-modal');
    if (modal) modal.classList.add('show');
};

window.closeLogModal = function() {
    var modal = findModalInContext(currentLogModalContext, 'log-modal');
    if (modal) modal.classList.remove('show');
    currentLogModalContext = null;
};

// Modal column drag and drop for reordering
let modalDraggedCol = null;
let modalDragContext = null;

function initModalColumnDrag(contextEl) {
    // Store context for use in updateModalColumnOrder
    modalDragContext = contextEl || currentModalContext;
    
    // Find the modal container relative to context
    var modal = findModalInContext(modalDragContext, 'add-column-modal');
    var container = modal ? modal.querySelector('#modal-columns-container, .modal-columns-container') : null;
    if (!container) {
        // Try finding any visible modal-columns-container
        container = document.querySelector('.modal-overlay.show #modal-columns-container');
    }
    if (!container) return;
    
    const cols = container.querySelectorAll('.modal-draggable-col');
    cols.forEach(col => {
        // Remove existing listeners to avoid duplicates
        col.replaceWith(col.cloneNode(true));
    });
    
    // Re-query after cloning
    const freshCols = container.querySelectorAll('.modal-draggable-col');
    freshCols.forEach(col => {
        col.addEventListener('dragstart', function(e) {
            modalDraggedCol = this;
            this.style.opacity = '0.5';
            e.dataTransfer.effectAllowed = 'move';
        });
        
        col.addEventListener('dragend', function(e) {
            this.style.opacity = '1';
            container.querySelectorAll('.modal-draggable-col').forEach(c => c.classList.remove('drag-over-modal'));
            if (modalDraggedCol) {
                updateModalColumnOrder(container);
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
                const parentContainer = this.parentNode;
                const allCols = Array.from(parentContainer.querySelectorAll('.modal-draggable-col'));
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

function updateModalColumnOrder(container) {
    if (!container) {
        // Try to find the visible modal's container
        var modal = findModalInContext(modalDragContext, 'add-column-modal');
        container = modal ? modal.querySelector('#modal-columns-container, .modal-columns-container') : null;
    }
    if (!container) return;
    
    const cols = container.querySelectorAll('.modal-draggable-col');
    const newOrder = [];
    cols.forEach(col => {
        const colName = col.dataset.column;
        if (colName) newOrder.push(colName);
    });
    
    if (newOrder.length > 0 && typeof setShinyInput !== 'undefined') {
        // Send with timestamp to ensure event fires (use container as context for namespace)
        setShinyInput('column_order', {order: newOrder, ts: Date.now()}, {priority: 'event'}, container);
    }
}

// Re-init modal drag when available_columns_modal updates
$(document).on('shiny:value', function(event) {
    // Check if the event name ends with available_columns_modal (namespaced)
    if (event.name && event.name.endsWith('available_columns_modal')) {
        setTimeout(function() { initModalColumnDrag(currentModalContext); }, 100);
    }
});

// Close modal on overlay click (only if clicking directly on overlay, not content)
document.addEventListener('click', function(e) {
    if (e.target.classList.contains('modal-overlay')) {
        // Check which modal was clicked
        if (e.target.id === 'add-column-modal' || e.target.querySelector('.modal-header h3')?.textContent === 'Manage Layout') {
            closeModal();
        } else if (e.target.id === 'copy-column-modal' || e.target.querySelector('.modal-header h3')?.textContent === 'Copy Column Values') {
            closeCopyModal();
        } else if (e.target.id === 'add-filter-modal' || e.target.querySelector('.modal-header h3')?.textContent === 'Add Column Filter') {
            closeAddFilterModal();
        } else if (e.target.id === 'log-modal' || e.target.querySelector('.modal-header h3')?.textContent?.includes('Modification')) {
            closeLogModal();
        }
    }
});

// Copy Column Modal functions
let currentCopyModalContext = null;

window.openCopyModal = function(event) {
    currentCopyModalContext = event ? event.target : document.activeElement;
    // Trigger refresh of column list (pass event target for namespace detection)
    if (typeof setShinyInput !== 'undefined') {
        setShinyInput('refresh_copy_columns', Date.now(), {priority: 'event'}, currentCopyModalContext);
    }
    var modal = findModalInContext(currentCopyModalContext, 'copy-column-modal');
    if (modal) modal.classList.add('show');
};

window.closeCopyModal = function() {
    var modal = findModalInContext(currentCopyModalContext, 'copy-column-modal');
    if (modal) modal.classList.remove('show');
    currentCopyModalContext = null;
};

window.copyColumnValues = function(columnName, event) {
    // Get selected rows from checkboxes in the active tab
    var contextEl = event ? event.target : currentCopyModalContext;
    var tabPane = contextEl ? contextEl.closest('.tab-pane, [role="tabpanel"]') : null;
    var checkboxSelector = 'input[type="checkbox"][id*="select_"]:checked';
    var checkboxes = tabPane ? tabPane.querySelectorAll(checkboxSelector) : document.querySelectorAll(checkboxSelector);
    
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
        
        setShinyInput('copy_column_request', {
            column: columnName,
            indices: selectedIndices,
            ts: Date.now()
        }, {priority: 'event'}, contextEl);
    }
    
    closeCopyModal();
};

// Add Filter Modal functions
let currentFilterModalContext = null;

window.openAddFilterModal = function(event) {
    currentFilterModalContext = event ? event.target : document.activeElement;
    var modal = findModalInContext(currentFilterModalContext, 'add-filter-modal');
    if (modal) modal.classList.add('show');
};

window.closeAddFilterModal = function() {
    var modal = findModalInContext(currentFilterModalContext, 'add-filter-modal');
    if (modal) modal.classList.remove('show');
    currentFilterModalContext = null;
};

window.addFilter = function(columnName, event) {
    if (typeof setShinyInput !== 'undefined') {
        var contextEl = event ? event.target : currentFilterModalContext;
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
        var contextEl = event ? event.target : currentLogModalContext;
        setShinyInput('undo_modification', {
            index: logIndex,
            ts: Date.now()
        }, {priority: 'event'}, contextEl);
    }
};