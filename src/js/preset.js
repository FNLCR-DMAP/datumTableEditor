// Preset dropdown
window.togglePresetMenu = function(event) {
    event.stopPropagation();
    // Trigger refresh when opening dropdown (pass event.target for namespace detection)
    if (typeof setShinyInput !== 'undefined') {
        setShinyInput('refresh_preset', Date.now(), {priority: 'event'}, event.target);
    }
    // Find the preset-menu within the same widget container
    const btn = event.target.closest('.preset-btn') || event.target;
    const dropdown = btn.closest('.preset-dropdown');
    const menu = dropdown ? dropdown.querySelector('.preset-menu') : null;
    if (menu) {
        menu.classList.toggle('show');
    }
};

// Refresh presets function
window.refreshPresets = function(event) {
    if (event) event.stopPropagation();
    if (typeof setShinyInput !== 'undefined') {
        setShinyInput('refresh_preset', Date.now(), {priority: 'event'}, event ? event.target : null);
    }
};

// Close dropdown when clicking outside
document.addEventListener('click', function(e) {
    // Close all preset menus that aren't being clicked on
    document.querySelectorAll('.preset-dropdown').forEach(function(dropdown) {
        if (!dropdown.contains(e.target)) {
            const menu = dropdown.querySelector('.preset-menu');
            if (menu) menu.classList.remove('show');
        }
    });
});

window.loadPreset = function(presetName, event) {
    if (typeof setShinyInput !== 'undefined') {
        // Use event target or find the clicked element for namespace detection
        var contextEl = event ? event.target : document.activeElement;
        setShinyInput('load_preset', presetName, {priority: 'event'}, contextEl);
    }
    // Close all preset menus
    document.querySelectorAll('.preset-menu').forEach(function(menu) {
        menu.classList.remove('show');
    });
};

window.deletePreset = function(presetName, event) {
    event.stopPropagation();
    if (confirm('Delete preset "' + presetName + '"?')) {
        if (typeof setShinyInput !== 'undefined') {
            setShinyInput('delete_preset', presetName, {priority: 'event'}, event.target);
        }
    }
};

window.saveNewPreset = function(btn) {
    // Find the input within the same preset-save-row
    const row = btn ? btn.closest('.preset-save-row') : null;
    const input = row ? row.querySelector('.new-preset-name-input') : document.querySelector('.new-preset-name-input');
    const name = input ? input.value.trim() : '';
    if (name) {
        if (typeof setShinyInput !== 'undefined') {
            // Use btn as context element for namespace detection
            setShinyInput('save_preset_name', name, {priority: 'event'}, btn);
        }
        if (input) input.value = '';
    }
};

// Save Layout - save to current preset (if not Default)
window.saveLayoutPrompt = function(event) {
    if (typeof setShinyInput !== 'undefined') {
        var contextEl = event ? event.target : document.activeElement;
        setShinyInput('save_current_layout', Date.now(), {priority: 'event'}, contextEl);
    }
};

// Update current preset from modal
window.updateCurrentPreset = function(event) {
    if (typeof setShinyInput !== 'undefined') {
        var contextEl = event ? event.target : document.activeElement;
        setShinyInput('save_current_layout', Date.now(), {priority: 'event'}, contextEl);
    }
};

// Reset columns
window.resetColumns = function(event) {
    if (typeof setShinyInput !== 'undefined') {
        var contextEl = event ? event.target : document.activeElement;
        setShinyInput('reset_columns', Date.now(), {priority: 'event'}, contextEl);
    }
    // Close all preset menus
    document.querySelectorAll('.preset-menu').forEach(function(menu) {
        menu.classList.remove('show');
    });
};
