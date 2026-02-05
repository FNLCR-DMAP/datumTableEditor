// Panel toggle functionality
document.addEventListener('DOMContentLoaded', function() {
    window.toggleLeftPanel = function() {
        const panel = document.querySelector('.left-panel');
        const btn = document.querySelector('.toggle-btn');
        if (panel.classList.contains('collapsed')) {
            panel.classList.remove('collapsed');
            btn.innerHTML = '◀';
        } else {
            panel.classList.add('collapsed');
            btn.innerHTML = '▶';
        }
    };
});
