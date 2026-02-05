// Preset dropdown
window.togglePresetMenu = function(event) {
    event.stopPropagation();
    // Trigger refresh when opening dropdown
    if (typeof Shiny !== 'undefined') {
        Shiny.setInputValue('refresh_preset', Date.now(), {priority: 'event'});
    }
    const menu = document.getElementById('preset-menu');
    menu.classList.toggle('show');
};

// Refresh presets function
window.refreshPresets = function(event) {
    if (event) event.stopPropagation();
    if (typeof Shiny !== 'undefined') {
        Shiny.setInputValue('refresh_preset', Date.now(), {priority: 'event'});
    }
};

// Close dropdown when clicking outside
document.addEventListener('click', function(e) {
    const dropdown = document.querySelector('.preset-dropdown');
    if (dropdown && !dropdown.contains(e.target)) {
        document.getElementById('preset-menu').classList.remove('show');
    }
});

window.loadPreset = function(presetName) {
    if (typeof Shiny !== 'undefined') {
        Shiny.setInputValue('load_preset', presetName, {priority: 'event'});
    }
    document.getElementById('preset-menu').classList.remove('show');
};

window.deletePreset = function(presetName, event) {
    event.stopPropagation();
    if (confirm('Delete preset "' + presetName + '"?')) {
        if (typeof Shiny !== 'undefined') {
            Shiny.setInputValue('delete_preset', presetName, {priority: 'event'});
        }
    }
};

window.saveNewPreset = function() {
    const input = document.getElementById('new-preset-name');
    const name = input.value.trim();
    if (name) {
        if (typeof Shiny !== 'undefined') {
            Shiny.setInputValue('save_preset_name', name, {priority: 'event'});
        }
        input.value = '';
    }
};

// Save Layout - save to current preset (if not Default)
window.saveLayoutPrompt = function() {
    if (typeof Shiny !== 'undefined') {
        Shiny.setInputValue('save_current_layout', Date.now(), {priority: 'event'});
    }
};

// Update current preset from modal
window.updateCurrentPreset = function() {
    if (typeof Shiny !== 'undefined') {
        Shiny.setInputValue('save_current_layout', Date.now(), {priority: 'event'});
    }
};

// Reset columns
window.resetColumns = function() {
    if (typeof Shiny !== 'undefined') {
        Shiny.setInputValue('reset_columns', Date.now(), {priority: 'event'});
    }
    document.getElementById('preset-menu').classList.remove('show');
};
