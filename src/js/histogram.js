// Sync histogram checkboxes with Shiny checkbox group
function initHistogramCheckboxes() {
    const histogramCheckboxes = document.querySelectorAll('.status-checkbox');
    histogramCheckboxes.forEach(function(checkbox) {
        checkbox.addEventListener('change', function() {
            // Get all checked statuses
            const checked = [];
            document.querySelectorAll('.status-checkbox:checked').forEach(function(cb) {
                checked.push(cb.value);
            });
            // Update the hidden Shiny checkbox group
            if (typeof Shiny !== 'undefined') {
                Shiny.setInputValue('status_filter_multi', checked);
            }
        });
    });
}

// Initialize histogram checkbox sync after Shiny renders
$(document).on('shiny:value', function(event) {
    if (event.name === 'stats_histogram') {
        setTimeout(initHistogramCheckboxes, 50);
    }
});
