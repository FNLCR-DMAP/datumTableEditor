// Cell Edit Popup
let currentEditCell = null;

function createCellEditPopup() {
    if (document.getElementById('cell-edit-popup')) return;
    
    const popup = document.createElement('div');
    popup.id = 'cell-edit-popup';
    popup.className = 'cell-edit-popup';
    popup.innerHTML = `
        <div class="popup-header">
            <h4 id="popup-column-name">Edit Column</h4>
            <button class="popup-close" onclick="closeCellPopup()">&times;</button>
        </div>
        <div class="original-value-row" id="original-value-row" style="display: none;">
            <span class="original-value-label">Original:</span>
            <span class="original-value-text" id="popup-original-value"></span>
        </div>
        <div class="current-value-row">
            <span class="current-value-label">Current:</span>
            <span class="current-value-text" id="popup-current-value"></span>
            <button class="copy-btn" onclick="copyCurrentValue()">Copy</button>
        </div>
        <div class="new-value-section">
            <label>New Value:</label>
            <input type="text" id="popup-new-value" placeholder="Enter new value...">
        </div>
        <div class="popup-actions">
            <button class="btn-cancel" onclick="closeCellPopup()">Cancel</button>
            <button class="btn-save" onclick="saveCellValue()">Save</button>
        </div>
    `;
    document.body.appendChild(popup);
    
    // Handle Enter key in input
    document.getElementById('popup-new-value').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            saveCellValue();
        }
    });
    
    // Handle Escape key
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            closeCellPopup();
        }
    });
}

window.openCellPopup = function(cell) {
    createCellEditPopup();
    
    currentEditCell = cell;
    const row = cell.dataset.row;
    const col = cell.dataset.col;
    const value = cell.dataset.value || '';
    const originalValue = cell.dataset.original;  // Will be undefined if not edited
    
    document.getElementById('popup-column-name').textContent = 'Edit: ' + col;
    document.getElementById('popup-current-value').textContent = value || '(empty)';
    document.getElementById('popup-new-value').value = value;
    
    // Show/hide original value row
    const originalRow = document.getElementById('original-value-row');
    const originalValueEl = document.getElementById('popup-original-value');
    if (originalValue !== undefined) {
        // Cell has been edited - show original value
        originalValueEl.textContent = originalValue || '(empty)';
        originalRow.style.display = 'flex';
    } else {
        // Cell not edited - hide original row
        originalRow.style.display = 'none';
    }
    
    const popup = document.getElementById('cell-edit-popup');
    
    // Position popup near the cell
    const rect = cell.getBoundingClientRect();
    let left = rect.left;
    let top = rect.bottom + 5;
    
    // Adjust if popup would go off screen
    if (left + 320 > window.innerWidth) {
        left = window.innerWidth - 330;
    }
    if (top + 200 > window.innerHeight) {
        top = rect.top - 210;
    }
    
    popup.style.left = left + 'px';
    popup.style.top = top + 'px';
    popup.classList.add('show');
    
    // Focus the input
    setTimeout(() => {
        document.getElementById('popup-new-value').focus();
        document.getElementById('popup-new-value').select();
    }, 50);
};

window.closeCellPopup = function() {
    const popup = document.getElementById('cell-edit-popup');
    if (popup) {
        popup.classList.remove('show');
    }
    currentEditCell = null;
};

window.copyCurrentValue = function() {
    const value = document.getElementById('popup-current-value').textContent;
    if (value === '(empty)') {
        navigator.clipboard.writeText('');
    } else {
        navigator.clipboard.writeText(value);
    }
    const btn = document.querySelector('.copy-btn');
    btn.textContent = 'Copied!';
    btn.classList.add('copied');
    setTimeout(() => {
        btn.textContent = 'Copy';
        btn.classList.remove('copied');
    }, 1500);
};

window.saveCellValue = function() {
    if (!currentEditCell) return;
    
    const row = currentEditCell.dataset.row;
    const col = currentEditCell.dataset.col;
    const oldValue = currentEditCell.dataset.value || '';
    const newValue = document.getElementById('popup-new-value').value;
    
    if (newValue !== oldValue) {
        // Update the cell display
        currentEditCell.dataset.value = newValue;
        currentEditCell.querySelector('.cell-value').textContent = newValue || '—';
        
        // Send to Shiny (pass currentEditCell as context for namespace detection)
        if (typeof setShinyInput !== 'undefined') {
            setShinyInput('cell_edit', {
                row: parseInt(row),
                col: col,
                oldValue: oldValue,
                newValue: newValue,
                ts: Date.now()
            }, {priority: 'event'}, currentEditCell);
        }
    }
    
    closeCellPopup();
};

// Click handler for clickable cells (cell_click_columns) — fires before editable-cell handler
document.addEventListener('click', function(e) {
    const cell = e.target.closest('.clickable-cell');
    if (cell) {
        e.stopPropagation();
        const row = cell.getAttribute('data-row');
        const col = cell.getAttribute('data-col');
        const value = cell.getAttribute('data-value');
        const pkJson = cell.getAttribute('data-pk');
        let pk = {};
        try { pk = JSON.parse(pkJson || '{}'); } catch(_) {}
        console.log('[cell_click]', {row, col, value, pk});
        if (typeof setShinyInput !== 'undefined') {
            setShinyInput('cell_click', {
                row: parseInt(row),
                col: col,
                value: value,
                pk: pk,
                ts: Date.now()
            }, {priority: 'event'}, cell);
        }
        return;
    }
}, true);  // useCapture=true so this fires before the editable-cell handler

// Click handler for editable cells using event delegation
document.addEventListener('click', function(e) {
    const cell = e.target.closest('.editable-cell');
    if (cell) {
        openCellPopup(cell);
    }
});

// Close popup when clicking outside
document.addEventListener('mousedown', function(e) {
    const popup = document.getElementById('cell-edit-popup');
    if (popup && popup.classList.contains('show')) {
        if (!popup.contains(e.target) && !e.target.closest('.editable-cell')) {
            closeCellPopup();
        }
    }
});
