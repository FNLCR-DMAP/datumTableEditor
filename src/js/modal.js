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
        setTimeout(function() {
            initModalColumnDrag(currentModalContext);
            // Clear search box and selection basket on refresh
            _colSearchSelected = [];
            _colSearchHighlighted = null;
            var modal = findModalInContext(currentModalContext, 'add-column-modal');
            if (modal) {
                var searchInput = modal.querySelector('#col-search-input');
                if (searchInput) searchInput.value = '';
                var searchResults = modal.querySelector('#col-search-results');
                if (searchResults) { searchResults.innerHTML = ''; searchResults.style.display = 'none'; }
                var selectedWrap = modal.querySelector('#col-search-selected');
                if (selectedWrap) { selectedWrap.innerHTML = ''; selectedWrap.style.display = 'none'; }
            }
        }, 100);
    }
});

// ─── Column search / multi-select in Manage Layout modal ──────
// Staging basket: columns the user has selected from search results
let _colSearchSelected = [];   // [{col, display, section}]
let _colSearchHighlighted = null;

function _getSelectedCols() { return _colSearchSelected.map(function(s) { return s.col; }); }

// Render the staging tags underneath the search bar
function _renderSelectedTags(modal) {
    var wrap = modal.querySelector('#col-search-selected');
    if (!wrap) return;
    wrap.innerHTML = '';
    if (!_colSearchSelected.length) { wrap.style.display = 'none'; return; }
    wrap.style.display = 'flex';
    _colSearchSelected.forEach(function(item) {
        var tag = document.createElement('span');
        var borderColor = item.section === 'current' ? '#dc3545' : '#28a745';
        tag.style.cssText = 'display:inline-flex;align-items:center;padding:3px 8px;border:1px solid ' + borderColor + ';border-radius:4px;font-size:11px;color:#333;background:#fff;';
        var badge = item.section === 'current'
            ? '<span style="font-size:9px;background:#2c3e50;color:#fff;padding:0 4px;border-radius:2px;margin-right:4px;">C</span>'
            : '<span style="font-size:9px;background:#e9ecef;color:#333;padding:0 4px;border-radius:2px;margin-right:4px;">A</span>';
        tag.innerHTML = badge + item.display +
            ' <span style="margin-left:6px;cursor:pointer;color:#999;font-weight:bold" data-remove-col="' + item.col + '">&times;</span>';
        tag.querySelector('[data-remove-col]').addEventListener('click', function() {
            _colSearchSelected = _colSearchSelected.filter(function(s) { return s.col !== item.col; });
            _renderSelectedTags(modal);
            _refreshSearchHighlights(modal);
        });
        wrap.appendChild(tag);
    });
}

// Refresh checkmarks / highlights in the dropdown based on current selection
function _refreshSearchHighlights(modal) {
    var resultsDiv = modal.querySelector('#col-search-results');
    if (!resultsDiv) return;
    var selected = _getSelectedCols();
    resultsDiv.querySelectorAll('.col-search-row').forEach(function(row) {
        var col = row.getAttribute('data-column');
        var check = row.querySelector('.search-check');
        if (selected.indexOf(col) !== -1) {
            row.style.background = '#e8f0fe';
            if (check) check.textContent = '✓';
        } else {
            row.style.background = '';
            if (check) check.textContent = '';
        }
    });
}

window.filterModalColumns = function(query) {
    var modal = findModalInContext(currentModalContext, 'add-column-modal');
    if (!modal) return;
    var resultsDiv = modal.querySelector('#col-search-results');
    if (!resultsDiv) return;

    query = (query || '').trim().toLowerCase();
    if (!query) {
        resultsDiv.innerHTML = '';
        resultsDiv.style.display = 'none';
        _colSearchHighlighted = null;
        return;
    }

    // Gather all column names from both current and available sets
    var currentTags = modal.querySelectorAll('#modal-columns-container .modal-draggable-col');
    var availableTags = modal.querySelectorAll('#modal-available-container .add-col-tag');
    var matches = [];

    currentTags.forEach(function(tag) {
        var col = tag.getAttribute('data-column') || '';
        var display = (tag.querySelector('span:nth-child(2)') || {}).textContent || col;
        display = display.replace(/^\d+\.\s*/, '');
        if (col.toLowerCase().indexOf(query) !== -1 || display.toLowerCase().indexOf(query) !== -1) {
            matches.push({ col: col, display: display, section: 'current' });
        }
    });

    availableTags.forEach(function(tag) {
        var onclickAttr = tag.getAttribute('onclick') || '';
        var m = onclickAttr.match(/addColumn\('([^']+)'/);
        var col = m ? m[1].replace(/\\\\/g, '\\').replace(/\\'/g, "'") : tag.textContent.replace(/^\+\s*/, '').trim();
        var display = tag.textContent.replace(/^\+\s*/, '').trim();
        if (col.toLowerCase().indexOf(query) !== -1 || display.toLowerCase().indexOf(query) !== -1) {
            matches.push({ col: col, display: display, section: 'available' });
        }
    });

    matches.sort(function(a, b) { return a.display.toLowerCase().localeCompare(b.display.toLowerCase()); });

    if (!matches.length) {
        resultsDiv.innerHTML = '<div style="padding:8px 12px;color:#999;font-size:12px;">No matching columns</div>';
        resultsDiv.style.display = 'block';
        _colSearchHighlighted = null;
        return;
    }

    var selectedCols = _getSelectedCols();
    resultsDiv.innerHTML = '';
    matches.forEach(function(m) {
        var row = document.createElement('div');
        row.className = 'col-search-row';
        row.setAttribute('data-column', m.col);
        row.setAttribute('data-section', m.section);
        var isSelected = selectedCols.indexOf(m.col) !== -1;
        var badge = m.section === 'current'
            ? '<span style="font-size:10px;background:#2c3e50;color:#fff;padding:1px 6px;border-radius:3px;margin-left:8px;">current</span>'
            : '<span style="font-size:10px;background:#e9ecef;color:#333;padding:1px 6px;border-radius:3px;margin-left:8px;">available</span>';
        row.innerHTML = '<span class="search-check" style="width:16px;font-size:13px;color:#28a745;">' + (isSelected ? '✓' : '') + '</span>' +
            '<span style="flex:1">' + m.display + '</span>' + badge;
        row.style.cssText = 'padding:6px 12px;cursor:pointer;font-size:12px;display:flex;align-items:center;' + (isSelected ? 'background:#e8f0fe;' : '');
        row.addEventListener('mouseenter', function() { _colSearchHighlighted = this; });
        row.addEventListener('click', function() { _toggleSearchSelection(m, modal); });
        resultsDiv.appendChild(row);
    });

    _colSearchHighlighted = resultsDiv.querySelector('.col-search-row');
    resultsDiv.style.display = 'block';
};

function _toggleSearchSelection(item, modal) {
    var idx = _colSearchSelected.findIndex(function(s) { return s.col === item.col; });
    if (idx !== -1) {
        _colSearchSelected.splice(idx, 1);
    } else {
        _colSearchSelected.push(item);
    }
    _renderSelectedTags(modal);
    _refreshSearchHighlights(modal);
}

// Keyboard navigation in search results (arrow keys + Enter to toggle)
document.addEventListener('keydown', function(e) {
    var modal = findModalInContext(currentModalContext, 'add-column-modal');
    if (!modal || !modal.classList.contains('show')) return;
    var input = modal.querySelector('#col-search-input');
    if (!input || document.activeElement !== input) return;
    var resultsDiv = modal.querySelector('#col-search-results');
    if (!resultsDiv || resultsDiv.style.display === 'none') return;
    var rows = resultsDiv.querySelectorAll('.col-search-row');
    if (!rows.length) return;

    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        var idx = _colSearchHighlighted ? Array.from(rows).indexOf(_colSearchHighlighted) : -1;
        if (e.key === 'ArrowDown') idx = Math.min(idx + 1, rows.length - 1);
        else idx = Math.max(idx - 1, 0);
        _colSearchHighlighted = rows[idx];
        rows[idx].scrollIntoView({ block: 'nearest' });
    } else if (e.key === 'Enter') {
        e.preventDefault();
        if (_colSearchHighlighted) _colSearchHighlighted.click();
    }
});

// Bulk Add — add all selected available columns to Current
window.bulkAddSelected = function(event) {
    if (event) event.stopPropagation();
    var toAdd = _colSearchSelected.filter(function(s) { return s.section === 'available'; });
    if (!toAdd.length) return;
    // Add them one-by-one (each triggers a server round-trip; last one wins)
    // To avoid N round-trips, collect the desired full order and send once
    var modal = findModalInContext(currentModalContext, 'add-column-modal');
    if (!modal) return;
    var container = modal.querySelector('#modal-columns-container');
    if (!container) return;
    // Current order
    var order = [];
    container.querySelectorAll('.modal-draggable-col').forEach(function(el) {
        var c = el.getAttribute('data-column');
        if (c) order.push(c);
    });
    // Append new columns
    toAdd.forEach(function(item) {
        if (order.indexOf(item.col) === -1) order.push(item.col);
    });
    // Clear selection
    _colSearchSelected = [];
    _renderSelectedTags(modal);
    // Send single column_order update
    if (typeof setShinyInput !== 'undefined') {
        setShinyInput('column_order', {order: order, ts: Date.now()}, {priority: 'event'}, container);
    }
};

// Bulk Remove — remove all selected current columns from Current
window.bulkRemoveSelected = function(event) {
    if (event) event.stopPropagation();
    var toRemove = _colSearchSelected.filter(function(s) { return s.section === 'current'; }).map(function(s) { return s.col; });
    if (!toRemove.length) return;
    var modal = findModalInContext(currentModalContext, 'add-column-modal');
    if (!modal) return;
    var container = modal.querySelector('#modal-columns-container');
    if (!container) return;
    // Current order minus removed
    var order = [];
    container.querySelectorAll('.modal-draggable-col').forEach(function(el) {
        var c = el.getAttribute('data-column');
        if (c && toRemove.indexOf(c) === -1) order.push(c);
    });
    // Clear selection
    _colSearchSelected = [];
    _renderSelectedTags(modal);
    // Send single column_order update
    if (typeof setShinyInput !== 'undefined') {
        setShinyInput('column_order', {order: order, ts: Date.now()}, {priority: 'event'}, container);
    }
};

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
        } else if (e.target.id === 'export-confirm-modal') {
            closeExportConfirmModal();
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

window.setFilterOperator = function(columnName, operator, event) {
    if (typeof setShinyInput !== 'undefined') {
        var contextEl = event ? event.target : document.activeElement;
        setShinyInput('set_filter_operator', {
            column: columnName,
            op: operator,
            ts: Date.now()
        }, {priority: 'event'}, contextEl);
    }
};

// Toggle filter textarea between edit and confirm states
window.toggleFilterEdit = function(columnName, event) {
    var btn = event ? event.currentTarget : null;
    if (!btn) return;
    var filterGroup = btn.closest('.filter-group');
    if (!filterGroup) return;
    var textarea = filterGroup.querySelector('textarea');
    if (!textarea) return;

    if (textarea.readOnly) {
        // Enter edit mode
        textarea.readOnly = false;
        textarea.style.opacity = '1';
        textarea.style.cursor = 'text';
        textarea.focus();
        btn.textContent = '\u2713';  // checkmark
        btn.title = 'Confirm changes';
        btn.classList.remove('btn-outline-secondary');
        btn.classList.add('btn-outline-success');
    } else {
        // Confirm changes — send value to server
        textarea.readOnly = true;
        textarea.style.opacity = '0.85';
        textarea.style.cursor = 'default';
        btn.textContent = '\u270E';  // pencil
        btn.title = 'Edit filter values';
        btn.classList.remove('btn-outline-success');
        btn.classList.add('btn-outline-secondary');
        var value = textarea.value || '';
        if (typeof setShinyInput !== 'undefined') {
            setShinyInput('apply_filter_value', {
                column: columnName,
                value: value,
                ts: Date.now()
            }, {priority: 'event'}, textarea);
        }
    }
};

// Clear all content from a filter textarea and send empty value to server
window.clearFilterContent = function(columnName, event) {
    var btn = event ? event.currentTarget : null;
    if (!btn) return;
    var filterGroup = btn.closest('.filter-group');
    if (!filterGroup) return;
    var textarea = filterGroup.querySelector('textarea');
    if (!textarea) return;

    textarea.value = '';
    textarea.readOnly = true;
    textarea.style.opacity = '0.85';
    textarea.style.cursor = 'default';

    // Reset edit button if it was in edit mode
    var editBtn = filterGroup.querySelector('.filter-edit-btn');
    if (editBtn) {
        editBtn.textContent = '\u270E';
        editBtn.title = 'Edit filter values';
        editBtn.classList.remove('btn-outline-success');
        editBtn.classList.add('btn-outline-secondary');
    }

    if (typeof setShinyInput !== 'undefined') {
        setShinyInput('apply_filter_value', {
            column: columnName,
            value: '',
            ts: Date.now()
        }, {priority: 'event'}, textarea);
    }
};

// Apply date filter — reads date input(s) from the filter group and sends to server
window.applyDateFilter = function(columnName, event) {
    var btn = event ? event.currentTarget : null;
    if (!btn) return;
    var filterGroup = btn.closest('.filter-group');
    if (!filterGroup) return;
    
    var dateInputs = filterGroup.querySelectorAll('.filter-date-input');
    var values = [];
    dateInputs.forEach(function(inp) {
        // Always push the value (empty string if not set) to preserve position
        // so server knows which bound (from/to) was provided
        values.push(inp.value || '');
    });
    
    var value = values.join('\n');
    if (typeof setShinyInput !== 'undefined') {
        setShinyInput('apply_filter_value', {
            column: columnName,
            value: value,
            ts: Date.now()
        }, {priority: 'event'}, btn);
    }
};

// Initialize filter textareas as readonly after render (legacy — kept for backward compat)
window.initFilterReadonly = function(containerId) {
    // No-op: filters are now directly editable; blur triggers apply_filter_value
};

// Auto-attach change handlers to filter date inputs via MutationObserver
(function() {
    function attachDateChange(input) {
        if (input._dateChangeAttached) return;
        input._dateChangeAttached = true;
        input.addEventListener('change', function() {
            var columnName = this.getAttribute('data-column');
            if (!columnName) return;
            applyDateFilter(columnName, {currentTarget: this});
        });
    }

    function scanForDateInputs(root) {
        var inputs = root.querySelectorAll ? root.querySelectorAll('.filter-group .filter-date-input') : [];
        inputs.forEach(attachDateChange);
    }

    var dateObserver = new MutationObserver(function(mutations) {
        mutations.forEach(function(m) {
            m.addedNodes.forEach(function(node) {
                if (node.nodeType !== 1) return;
                scanForDateInputs(node);
                if (node.matches && node.matches('.filter-group .filter-date-input')) {
                    attachDateChange(node);
                }
            });
        });
    });

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            dateObserver.observe(document.body, {childList: true, subtree: true});
            scanForDateInputs(document);
        });
    } else {
        dateObserver.observe(document.body, {childList: true, subtree: true});
        scanForDateInputs(document);
    }
})();

// Auto-submit filter textarea value on blur (user clicked away)
(function() {
    function attachFilterBlur(textarea) {
        if (textarea._filterBlurAttached) return;
        textarea._filterBlurAttached = true;
        textarea.addEventListener('blur', function() {
            var colMatch = this.id.match(/filter_(.+)/);
            if (!colMatch) return;
            var columnName = colMatch[1];
            if (typeof setShinyInput !== 'undefined') {
                setShinyInput('apply_filter_value', {
                    column: columnName,
                    value: this.value || '',
                    ts: Date.now()
                }, {priority: 'event'}, this);
            }
        });
    }

    // Observe DOM for filter textareas appearing
    var observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(m) {
            m.addedNodes.forEach(function(node) {
                if (node.nodeType !== 1) return;
                var textareas = node.querySelectorAll ? node.querySelectorAll('.filter-group textarea') : [];
                textareas.forEach(attachFilterBlur);
                if (node.matches && node.matches('.filter-group textarea')) {
                    attachFilterBlur(node);
                }
            });
        });
    });

    // Start observing once DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            observer.observe(document.body, {childList: true, subtree: true});
            document.querySelectorAll('.filter-group textarea').forEach(attachFilterBlur);
        });
    } else {
        observer.observe(document.body, {childList: true, subtree: true});
        document.querySelectorAll('.filter-group textarea').forEach(attachFilterBlur);
    }
})();

// Filter Values Modal state
var currentFilterValuesColumn = null;
var currentFilterValuesContext = null;

window.openFilterValuesModal = function(columnName, event) {
    currentFilterValuesColumn = columnName;
    currentFilterValuesContext = event ? event.target : document.activeElement;
    
    // Find the modal in the correct namespace context
    var modal = findModalInContext(currentFilterValuesContext, 'filter-values-modal');
    if (!modal) return;
    
    // Get unique values from the hidden data element
    // The hidden div is NOT Shiny-namespaced, so find it relative to the filter group
    var filterGroup = currentFilterValuesContext.closest('.filter-group');
    var valuesEl = filterGroup ? filterGroup.querySelector('[data-values]') : null;
    // Fallback: try by raw ID (no namespace)
    if (!valuesEl) {
        valuesEl = document.getElementById('filter_values_' + columnName);
    }
    var values = valuesEl ? (valuesEl.getAttribute('data-values') || '').split(',').filter(function(v) { return v; }) : [];
    
    // Get current filter value from textarea inside the Shiny input container
    var filterContainer = findElementInContext(currentFilterValuesContext, 'filter_' + columnName);
    var filterInput = filterContainer ? (filterContainer.tagName === 'TEXTAREA' ? filterContainer : filterContainer.querySelector('textarea')) : null;
    var currentValues = [];
    if (filterInput && filterInput.value) {
        currentValues = filterInput.value.split('\n').map(function(v) { return v.trim(); }).filter(function(v) { return v; });
    }
    
    // Build checkboxes
    var checkboxContainer = modal.querySelector('#filter-values-checkboxes');
    if (checkboxContainer) {
        checkboxContainer.innerHTML = '';
        values.forEach(function(value) {
            var isChecked = currentValues.indexOf(value) !== -1;
            var div = document.createElement('div');
            div.className = 'filter-value-item';
            div.style.cssText = 'padding: 5px 0; border-bottom: 1px solid #eee;';
            div.innerHTML = '<label style="display: flex; align-items: center; cursor: pointer; margin: 0;">' +
                '<input type="checkbox" value="' + escapeHtml(value) + '" ' + (isChecked ? 'checked' : '') + ' style="margin-right: 8px;">' +
                '<span class="filter-value-text">' + escapeHtml(value) + '</span>' +
                '</label>';
            checkboxContainer.appendChild(div);
        });
        
        if (values.length === 0) {
            checkboxContainer.innerHTML = '<p style="color: #6c757d; margin: 0;">No values available</p>';
        }
    }
    
    // Clear search
    var searchInput = modal.querySelector('#filter_values_search');
    if (searchInput) {
        searchInput.value = '';
        searchInput.oninput = function() {
            filterValuesSearch(this.value);
        };
    }
    
    // Update modal title
    var title = modal.querySelector('.modal-header h3');
    if (title) {
        title.textContent = 'Select Values for: ' + columnName;
    }
    
    modal.classList.add('show');
};

window.closeFilterValuesModal = function() {
    var modal = findModalInContext(currentFilterValuesContext, 'filter-values-modal');
    if (modal) modal.classList.remove('show');
    currentFilterValuesColumn = null;
    currentFilterValuesContext = null;
};

window.selectAllFilterValues = function() {
    var modal = findModalInContext(currentFilterValuesContext, 'filter-values-modal');
    if (!modal) return;
    var checkboxes = modal.querySelectorAll('#filter-values-checkboxes input[type="checkbox"]');
    checkboxes.forEach(function(cb) {
        if (cb.closest('.filter-value-item').style.display !== 'none') {
            cb.checked = true;
        }
    });
};

window.clearAllFilterValues = function() {
    var modal = findModalInContext(currentFilterValuesContext, 'filter-values-modal');
    if (!modal) return;
    var checkboxes = modal.querySelectorAll('#filter-values-checkboxes input[type="checkbox"]');
    checkboxes.forEach(function(cb) { cb.checked = false; });
};

window.filterValuesSearch = function(searchTerm) {
    var modal = findModalInContext(currentFilterValuesContext, 'filter-values-modal');
    if (!modal) return;
    var items = modal.querySelectorAll('.filter-value-item');
    var term = searchTerm.toLowerCase();
    items.forEach(function(item) {
        var text = item.querySelector('.filter-value-text').textContent.toLowerCase();
        item.style.display = text.indexOf(term) !== -1 ? '' : 'none';
    });
};

window.applyFilterValues = function() {
    var modal = findModalInContext(currentFilterValuesContext, 'filter-values-modal');
    if (!modal || !currentFilterValuesColumn) return;
    
    // Get all checked values
    var checkboxes = modal.querySelectorAll('#filter-values-checkboxes input[type="checkbox"]:checked');
    var selectedValues = Array.from(checkboxes).map(function(cb) { return cb.value; });
    
    // Update the filter textarea visually
    var filterContainer = findElementInContext(currentFilterValuesContext, 'filter_' + currentFilterValuesColumn);
    var filterTextarea = filterContainer ? (filterContainer.tagName === 'TEXTAREA' ? filterContainer : filterContainer.querySelector('textarea')) : null;
    if (filterTextarea) {
        filterTextarea.value = selectedValues.join('\n');
    }
    
    // Send the value to the server explicitly (same path as blur)
    if (typeof setShinyInput !== 'undefined') {
        var contextEl = currentFilterValuesContext || document.activeElement;
        setShinyInput('apply_filter_value', {
            column: currentFilterValuesColumn,
            value: selectedValues.join('\n'),
            ts: Date.now()
        }, {priority: 'event'}, contextEl);
    }
    
    closeFilterValuesModal();
};

// Helper to escape HTML
function escapeHtml(text) {
    var div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Helper to find element by ID within context
function findElementInContext(contextEl, elementId) {
    if (!contextEl) return document.getElementById(elementId);
    var nsEl = contextEl.closest('[data-shiny-ns]');
    if (nsEl) {
        var ns = nsEl.getAttribute('data-shiny-ns');
        return document.getElementById(ns + elementId);
    }
    return document.getElementById(elementId);
}

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

// Export PHI/PII Confirmation Modal
let currentExportModalContext = null;
let pendingExportType = null;  // 'selected' or 'all'

window.openExportConfirmModal = function(event, exportType) {
    currentExportModalContext = event ? event.target : document.activeElement;
    pendingExportType = exportType;
    
    // Reset modal state: show the "I Understand" button, hide any previous download UI
    var modal = findModalInContext(currentExportModalContext, 'export-confirm-modal');
    if (modal) {
        var confirmBtn = modal.querySelector('#export-confirm-btn');
        if (confirmBtn) {
            confirmBtn.disabled = false;
            confirmBtn.textContent = 'I Understand';
            confirmBtn.classList.remove('btn-outline-success', 'btn-outline-secondary');
            confirmBtn.classList.add('btn-primary');
            confirmBtn.onclick = function(e) { confirmExportDownload(e); };
        }
        modal.classList.add('show');
    }
};

window.closeExportConfirmModal = function() {
    var modal = findModalInContext(currentExportModalContext, 'export-confirm-modal');
    if (modal) modal.classList.remove('show');
    currentExportModalContext = null;
    pendingExportType = null;
};

window.confirmExportDownload = function(event) {
    // Disable the button and show preparing state
    var contextEl = event ? event.target : currentExportModalContext;
    var modal = findModalInContext(currentExportModalContext, 'export-confirm-modal');
    if (modal) {
        var confirmBtn = modal.querySelector('#export-confirm-btn');
        if (confirmBtn) {
            confirmBtn.disabled = true;
            confirmBtn.textContent = 'Preparing...';
        }

        // Watch for the download button to appear, then transition to "Done"
        // Use attribute-ends-with selector to handle namespaced IDs (e.g. "editor1-export_download_ui")
        var outputContainer = modal.querySelector('[id$="export_download_ui"]');
        if (outputContainer) {
            var observer = new MutationObserver(function(mutations) {
                // Check if download button has been rendered (namespaced ID)
                var downloadBtn = outputContainer.querySelector('[id$="export_prepared_btn"]');
                if (downloadBtn && confirmBtn) {
                    confirmBtn.textContent = 'Done';
                    confirmBtn.disabled = false;
                    confirmBtn.classList.remove('btn-primary');
                    confirmBtn.classList.add('btn-outline-success');
                    // Click "Done" = close modal
                    confirmBtn.onclick = function() { closeExportConfirmModal(); };
                    observer.disconnect();
                }
                // Also handle error state
                var errorDiv = outputContainer.querySelector('[style*="fff0f0"]');
                if (errorDiv && confirmBtn) {
                    confirmBtn.textContent = 'Close';
                    confirmBtn.disabled = false;
                    confirmBtn.classList.remove('btn-primary');
                    confirmBtn.classList.add('btn-outline-secondary');
                    confirmBtn.onclick = function() { closeExportConfirmModal(); };
                    observer.disconnect();
                }
            });
            observer.observe(outputContainer, { childList: true, subtree: true });
        }
    }
    
    // Send signal to server to prepare the data
    if (typeof setShinyInput !== 'undefined') {
        setShinyInput('confirm_export', {
            type: pendingExportType || 'all',
            ts: Date.now()
        }, {priority: 'event'}, currentExportModalContext);
    }
};