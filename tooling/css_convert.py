"""Convert hardcoded CSS values to var() references - Pass 2."""
import os
import re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS_DIR = os.path.join(BASE, "src", "css")


def replace_in_file(filename, replacements):
    """Apply ordered replacements to a CSS file."""
    filepath = os.path.join(CSS_DIR, filename)
    with open(filepath, "r") as f:
        content = f.read()
    count = 0
    for old, new in replacements:
        if old in content:
            content = content.replace(old, new)
            count += 1
    with open(filepath, "w") as f:
        f.write(content)
    print(f"  {filename}: {count}/{len(replacements)} patterns matched")


# ─── layout.css ───────────────────────────────────────────────────────────────
replace_in_file("layout.css", [
    ("1px solid #ccc", "1px solid var(--toggle-btn-border)"),
])

# ─── sidebar.css ──────────────────────────────────────────────────────────────
replace_in_file("sidebar.css", [
    ("border-color: #2196F3", "border-color: var(--input-focus-border)"),
    ("color: #a71d2a !important", "color: var(--btn-danger-bg) !important"),
    ("background-color: #f8f9fa", "background-color: var(--toolbar-bg)"),
    ("color: #343a40", "color: var(--sidebar-color)"),
    ("background: #4a7dbd", "background: var(--btn-primary-bg)"),
    ("color: #fff", "color: var(--btn-primary-color)"),
    ("background: #218838", "background: var(--btn-success-bg)"),
    ("background: #fff", "background: var(--toggle-btn-bg)"),
])

# ─── table.css ────────────────────────────────────────────────────────────────
replace_in_file("table.css", [
    # Header borders
    ("border-right: 1px solid #6c757d", "border-right: 1px solid var(--table-header-bg)"),
    ("background-color: #343a40", "background-color: var(--table-header-border)"),
    ("box-shadow: inset 0 0 0 2px #3498db", "box-shadow: inset 0 0 0 2px var(--input-focus-border)"),
    ("background: #3498db", "background: var(--input-focus-border)"),
    # Dropdown
    ("color: #333", "color: var(--table-cell-color)"),
    ("background: #f0f0f0", "background: var(--filter-badge-bg)"),
    ("color: #dc3545", "color: var(--btn-danger-bg)"),
    ("1px solid #eee", "1px solid var(--filter-badge-bg)"),
    ("background: #fff5f5", "background: var(--table-cell-edited-bg)"),
    # Bootstrap overrides -- bs variables
    ("--bs-table-bg: #c4d4e3", "--bs-table-bg: var(--table-row-alt-bg)"),
    ("--bs-table-accent-bg: #c4d4e3", "--bs-table-accent-bg: var(--table-row-alt-bg)"),
    ("background: #c4d4e3 !important", "background: var(--table-row-alt-bg) !important"),
    ("--bs-table-bg: #f5f7f9", "--bs-table-bg: var(--table-row-bg)"),
    ("--bs-table-accent-bg: #f5f7f9", "--bs-table-accent-bg: var(--table-row-bg)"),
    ("background: #f5f7f9 !important", "background: var(--table-row-bg) !important"),
    ("--bs-table-bg: #d0e8f0", "--bs-table-bg: var(--table-row-hover-bg)"),
    ("--bs-table-accent-bg: #d0e8f0", "--bs-table-accent-bg: var(--table-row-hover-bg)"),
    # Selected row
    ("background-color: #cce5ff !important", "background-color: var(--table-row-hover-bg) !important"),
    ("background-color: #b8daff !important", "background-color: var(--table-row-hover-bg) !important"),
    # Status badges
    ("background-color: #e2e3e5; color: #383d41", "background-color: var(--filter-badge-bg); color: var(--filter-badge-color)"),
    ("color: #28a745; font-weight: 600", "color: var(--status-approved); font-weight: 600"),
    ("color: #dc3545; font-weight: 600", "color: var(--status-rejected); font-weight: 600"),
    (".status-label-unprocessed { color: #6c757d; }", ".status-label-unprocessed { color: var(--status-unprocessed); }"),
    # Banners
    ("background-color: #e8f5e9", "background-color: var(--status-approved-banner-bg)"),
    ("2px solid #4caf50", "2px solid var(--status-approved)"),
    ("color: #2e7d32", "color: var(--status-approved)"),
    ("background-color: #ffebee", "background-color: var(--status-rejected-banner-bg)"),
    ("2px solid #f44336", "2px solid var(--status-rejected)"),
    ("color: #c62828", "color: var(--status-rejected)"),
    # Editable/clickable cells
    ("background-color: #e3f2fd !important", "background-color: var(--table-row-hover-bg) !important"),
    ("color: #0d6efd", "color: var(--btn-primary-bg)"),
    ("background-color: #e8f0fe !important", "background-color: var(--table-row-hover-bg) !important"),
    ("background-color: #f0f0f0 !important", "background-color: var(--filter-badge-bg) !important"),
    ("background-color: #F5DEB3 !important", "background-color: var(--table-cell-edited-bg) !important"),
    # Cell edit popup
    ("border-bottom: 1px solid #eee", "border-bottom: 1px solid var(--filter-badge-bg)"),
    ("color: #495057", "color: var(--input-color)"),
    ("color: #6c757d", "color: var(--sidebar-subtext)"),
    ("color: #343a40", "color: var(--sidebar-color)"),
    ("color: #5D3A1A", "color: var(--table-cell-edited-border)"),
    ("border-color: #2196F3", "border-color: var(--input-focus-border)"),
    # Buttons
    ("background: #28a745", "background: var(--btn-success-bg)"),
    ("border-color: #28a745", "border-color: var(--btn-success-bg)"),
    ("border: 1px solid #28a745", "border: 1px solid var(--btn-success-bg)"),
    ("background: #218838", "background: var(--btn-success-bg)"),
    ("background: #dc3545", "background: var(--btn-danger-bg)"),
    ("border: 1px solid #dc3545", "border: 1px solid var(--btn-danger-bg)"),
    ("background: #c82333", "background: var(--btn-danger-bg)"),
])

# ─── toolbar.css ──────────────────────────────────────────────────────────────
replace_in_file("toolbar.css", [
    ("background: #e3f2fd", "background: var(--table-row-hover-bg)"),
    ("color: #dc3545", "color: var(--btn-danger-bg)"),
    ("border: 1px solid #28a745", "border: 1px solid var(--btn-success-bg)"),
    ("background: #218838", "background: var(--btn-success-bg)"),
    ("border: 1px solid #17a2b8", "border: 1px solid var(--btn-primary-bg)"),
    ("background: #17a2b8", "background: var(--btn-primary-bg)"),
    ("background: #138496", "background: var(--btn-primary-bg)"),
    ("border: 1px solid #6c757d", "border: 1px solid var(--status-unprocessed)"),
    ("background: #6c757d", "background: var(--status-unprocessed)"),
    ("background: #5a6268", "background: var(--status-unprocessed)"),
    ("color: white", "color: var(--btn-primary-color)"),
])

# ─── modal.css ────────────────────────────────────────────────────────────────
replace_in_file("modal.css", [
    ("box-shadow: 0 0 0 2px #007bff !important", "box-shadow: 0 0 0 2px var(--btn-primary-bg) !important"),
    ("background: #28a745", "background: var(--btn-success-bg)"),
    ("color: white", "color: var(--btn-primary-color)"),
    ("border: 1px dashed #ced4da", "border: 1px dashed var(--input-border)"),
    ("background: #2c3e50", "background: var(--sidebar-heading)"),
    ("color: #ff6b6b", "color: var(--btn-danger-bg)"),
])

# ─── pagination.css ───────────────────────────────────────────────────────────
# (Already fully converted in pass 1)

# ─── log.css ──────────────────────────────────────────────────────────────────
# (Already fully converted in pass 1)

# ─── synthesis.css ────────────────────────────────────────────────────────────
# (Already fully converted in pass 1)

print("\nPass 2 complete. Checking remaining hardcoded colors...")
import subprocess
result = subprocess.run(
    ["grep", "-rn", "--include=*.css", "-E", "#[0-9a-fA-F]{3,8}"],
    capture_output=True, text=True,
    cwd=os.path.join(BASE, "src", "css")
)
lines = [l for l in result.stdout.splitlines()
         if "var(" not in l and "/*" not in l and "themes/" not in l]
print(f"Remaining hardcoded hex colors: {len(lines)}")
for l in lines[:30]:
    print(f"  {l}")
