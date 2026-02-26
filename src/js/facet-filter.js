// Facet filter checkboxes → Shiny active_filters sync
function initFacetCheckboxes(contextEl) {
    var container = _findWidgetContainer(contextEl);
    var checkboxes = container.querySelectorAll('.facet-checkbox');
    checkboxes.forEach(function(cb) {
        // Guard against double-binding
        if (cb._facetBound) return;
        cb._facetBound = true;

        cb.addEventListener('change', function() {
            var column = cb.getAttribute('data-column');
            if (!column) return;
            var widgetContainer = _findWidgetContainer(cb);
            // Collect ALL checkboxes for this column (visible + overflow)
            var allCbs = widgetContainer.querySelectorAll('.facet-checkbox[data-column="' + column + '"]');
            var total = allCbs.length;
            var checked = [];
            allCbs.forEach(function(c) {
                if (c.checked) checked.push(c.value);
            });

            // If all checked (or none checked) → clear the filter for that column
            var filterValue;
            if (checked.length === 0 || checked.length === total) {
                filterValue = null;  // clear
            } else {
                filterValue = checked.join('\n');
            }
            if (typeof setShinyInput !== 'undefined') {
                setShinyInput('facet_filter_change',
                    { column: column, value: filterValue, ts: Date.now() },
                    { priority: 'event' },
                    cb
                );
            }
        });
    });
}

// Re-initialize whenever Shiny re-renders the facet panels output
$(document).on('shiny:value', function(event) {
    if (event.name && event.name.endsWith('facet_panels_ui')) {
        var target = event.target;
        setTimeout(function() { initFacetCheckboxes(target); }, 50);
    }
});
