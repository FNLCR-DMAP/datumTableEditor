// Sync histogram checkboxes with Shiny checkbox group
function initHistogramCheckboxes(contextEl) {
    var container = _findWidgetContainer(contextEl);
    const histogramCheckboxes = container.querySelectorAll('.status-checkbox');
    histogramCheckboxes.forEach(function(checkbox) {
        checkbox.addEventListener('change', function() {
            // Get all checked statuses within this widget
            var widgetContainer = _findWidgetContainer(checkbox);
            const checked = [];
            widgetContainer.querySelectorAll('.status-checkbox:checked').forEach(function(cb) {
                checked.push(cb.value);
            });
            // Update the hidden Shiny checkbox group (pass checkbox as context)
            if (typeof setShinyInput !== 'undefined') {
                setShinyInput('status_filter_multi', checked, {priority: 'event'}, checkbox);
            }
        });
    });
}

// Initialize histogram checkbox sync after Shiny renders
$(document).on('shiny:value', function(event) {
    if (event.name && event.name.endsWith('stats_histogram')) {
        var target = event.target;
        setTimeout(function() { initHistogramCheckboxes(target); }, 50);
    }
});
