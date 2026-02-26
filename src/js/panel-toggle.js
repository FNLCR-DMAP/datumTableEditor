// Panel toggle functionality
document.addEventListener('DOMContentLoaded', function() {
    window.toggleLeftPanel = function(event) {
        // Scope to the widget that contains the clicked button
        var btn = event ? event.currentTarget : document.querySelector('.toggle-btn');
        var container = btn.closest('.main-container');
        if (!container) return;
        var panel = container.querySelector('.left-panel');
        if (!panel) return;
        if (panel.classList.contains('collapsed')) {
            panel.classList.remove('collapsed');
            btn.innerHTML = '◀';
        } else {
            panel.classList.add('collapsed');
            btn.innerHTML = '▶';
        }
    };
});
