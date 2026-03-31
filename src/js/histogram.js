// Sync histogram checkboxes with Shiny checkbox group via event delegation.
// The output container (event.target) is stable across re-renders — only its
// innerHTML changes.  A single delegated listener avoids the race condition
// where individual listeners registered after a timeout could miss clicks.
$(document).on('shiny:value', function(event) {
    if (event.name && event.name.endsWith('stats_histogram')) {
        var outputEl = event.target;
        if (outputEl._histDelegated) return;  // already wired
        outputEl._histDelegated = true;
        outputEl.addEventListener('change', function(e) {
            if (!e.target.classList.contains('status-checkbox')) return;
            var container = _findWidgetContainer(e.target);
            var checked = [];
            container.querySelectorAll('.status-checkbox:checked').forEach(function(cb) {
                checked.push(cb.value);
            });
            if (typeof setShinyInput !== 'undefined') {
                setShinyInput('status_filter_multi', checked, {priority: 'event'}, e.target);
            }
        });
    }
});
