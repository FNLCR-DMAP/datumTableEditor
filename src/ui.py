""" 
UI Definition for Epitopes Data Editor PyShiny App
Split panel layout with collapsible sidebar
"""

from shiny import ui
from pathlib import Path


def _load_css_files() -> str:
    """Load component CSS files (no theme variables — those go inline on theme-provider div)"""
    css_dir = Path(__file__).parent / "css"
    
    css_files = [
        "layout.css",
        "sidebar.css",
        "toolbar.css",
        "modal.css",
        "table.css",
        "pagination.css",
        "log.css",
        "synthesis.css",
    ]
    
    combined_css = []
    for css_file in css_files:
        css_path = css_dir / css_file
        if css_path.exists():
            combined_css.append(f"/* === {css_file} === */")
            combined_css.append(css_path.read_text())
    
    # Also load dark-mode specific overrides (non-variable rules)
    dark_extra = css_dir / "themes" / "dark" / "theme.css"
    if dark_extra.exists():
        content = dark_extra.read_text()
        # Extract only the non-variable rules (after the closing } of the variable block)
        parts = content.split("/* Dark mode specific overrides")
        if len(parts) > 1:
            combined_css.append("/* === dark mode overrides === */")
            combined_css.append("/* Dark mode specific overrides" + parts[1])
    
    return "\n".join(combined_css)


def _build_theme_styles() -> dict:
    """Build inline style strings for each theme (all CSS variables as inline properties)."""
    # Classic theme — the base/default
    classic = (
        "--font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; "
        "--font-size-xs: 11px; --font-size-sm: 12px; --font-size-md: 13px; --font-size-lg: 16px; --font-size-xl: 17px; "
        "--page-bg: white; "
        "--sidebar-bg: #c5ccd3; --sidebar-color: #343a40; --sidebar-border: #adb5bd; --sidebar-shadow: none; "
        "--sidebar-heading: #2c3e50; --sidebar-subtext: #6c757d; --sidebar-text: #495057; "
        "--toolbar-bg: #f8f9fa; --toolbar-border: #dee2e6; --toolbar-shadow: none; "
        "--toolbar-btn-bg: #ffffff; --toolbar-btn-border: #ced4da; --toolbar-btn-color: #495057; --toolbar-btn-hover-bg: #e9ecef; "
        "--table-bg: white; --table-border: #ddd; --table-radius: 5px; --table-shadow: none; "
        "--table-header-bg: #495057; --table-header-color: #ffffff; --table-header-border: #343a40; "
        "--table-row-bg: #f5f7f9; --table-row-alt-bg: #c4d4e3; --table-row-hover-bg: #d0e8f0; "
        "--table-cell-border: #ddd; --table-cell-color: #212529; "
        "--table-cell-edited-bg: #FFF8DC; --table-cell-edited-border: #8B4513; "
        "--status-unprocessed: #6c757d; --status-edited: #8B4513; --status-approved: #28a745; --status-rejected: #dc3545; "
        "--pagination-bg: #f8f9fa; --pagination-border: #dee2e6; --pagination-btn-bg: #ffffff; "
        "--pagination-btn-border: #dee2e6; --pagination-btn-color: #495057; --pagination-btn-hover-bg: #e9ecef; "
        "--pagination-btn-active-bg: #495057; --pagination-btn-active-color: #ffffff; --pagination-info-color: #495057; "
        "--modal-overlay-bg: #000000; --modal-bg: #ffffff; --modal-radius: 8px; "
        "--modal-shadow: 0 4px 20px rgba(0,0,0,0.4); --modal-header-border: #dee2e6; --modal-header-color: #212529; "
        "--input-bg: #ffffff; --input-border: #ced4da; --input-color: #495057; "
        "--input-focus-border: #80bdff; --input-placeholder: #6c757d; "
        "--btn-primary-bg: #007bff; --btn-primary-color: #ffffff; --btn-primary-hover-bg: #0069d9; "
        "--btn-success-bg: #28a745; --btn-success-color: #ffffff; "
        "--btn-danger-bg: #dc3545; --btn-danger-color: #ffffff; "
        "--toggle-btn-bg: #ffffff; --toggle-btn-border: #ced4da; --toggle-btn-color: #495057; --toggle-btn-hover-bg: #e9ecef; "
        "--scrollbar-track: #f1f1f1; --scrollbar-thumb: #adb5bd; --scrollbar-thumb-hover: #6c757d; "
        "--histogram-track: #d0d5db; "
        "--filter-badge-bg: #e9ecef; --filter-badge-color: #495057; "
        "--log-bg: #ffffff; --log-border: #dee2e6; --log-item-border: #f1f1f1; --log-text: #212529; "
        "--synthesis-bg: #ffc107; --synthesis-border: #e0a800; --synthesis-color: #856404; --synthesis-banner-bg: #fff3cd; "
        "--status-approved-banner-bg: #e8f5e9; --status-rejected-banner-bg: #ffebee;"
    )
    
    # Modern — override only what differs from classic
    modern = classic.replace("--page-bg: white", "--page-bg: #f0f2f5")
    modern = modern.replace("--sidebar-bg: #c5ccd3", "--sidebar-bg: #ffffff")
    modern = modern.replace("--table-header-bg: #495057", "--table-header-bg: #1e293b")
    modern = modern.replace("--table-header-color: #ffffff", "--table-header-color: #f1f5f9")
    modern = modern.replace("--table-header-border: #343a40", "--table-header-border: #334155")
    modern = modern.replace("--btn-primary-bg: #007bff", "--btn-primary-bg: #6366f1")
    modern = modern.replace("--table-radius: 5px", "--table-radius: 12px")
    modern = modern.replace("--modal-radius: 8px", "--modal-radius: 16px")
    
    # Eye Protection — full override
    eye_protection = (
        "--font-family: Georgia, Cambria, 'Times New Roman', serif; "
        "--font-size-xs: 11px; --font-size-sm: 12px; --font-size-md: 13px; --font-size-lg: 16px; --font-size-xl: 17px; "
        "--page-bg: #f5f0e8; "
        "--sidebar-bg: #faf7f2; --sidebar-color: #3d3328; --sidebar-border: #e8e0d4; "
        "--sidebar-shadow: 1px 0 6px rgba(80,60,30,0.05); "
        "--sidebar-heading: #3d3328; --sidebar-subtext: #8c7b68; --sidebar-text: #5c4e3e; "
        "--toolbar-bg: #faf7f2; --toolbar-border: #e8e0d4; --toolbar-shadow: 0 1px 3px rgba(80,60,30,0.04); "
        "--toolbar-btn-bg: #faf7f2; --toolbar-btn-border: #e0d8cc; --toolbar-btn-color: #5c4e3e; --toolbar-btn-hover-bg: #f0ebe3; "
        "--table-bg: #fefcf8; --table-border: #e8e0d4; --table-radius: 10px; --table-shadow: 0 1px 3px rgba(80,60,30,0.05); "
        "--table-header-bg: #5c4e3e; --table-header-color: #faf7f2; --table-header-border: #4a3f33; "
        "--table-row-bg: #fefcf8; --table-row-alt-bg: #f9f5ee; --table-row-hover-bg: #f4ede3; "
        "--table-cell-border: #f0ebe3; --table-cell-color: #3d3328; "
        "--table-cell-edited-bg: #fef9e7; --table-cell-edited-border: #a08050; "
        "--status-unprocessed: #a89880; --status-edited: #c49030; --status-approved: #5a9060; --status-rejected: #b85040; "
        "--pagination-bg: #faf7f2; --pagination-border: #e8e0d4; --pagination-btn-bg: #faf7f2; "
        "--pagination-btn-border: #e0d8cc; --pagination-btn-color: #5c4e3e; --pagination-btn-hover-bg: #f0ebe3; "
        "--pagination-btn-active-bg: #7a6b58; --pagination-btn-active-color: #faf7f2; --pagination-info-color: #8c7b68; "
        "--modal-overlay-bg: rgba(60,48,30,0.35); --modal-bg: #faf7f2; --modal-radius: 14px; "
        "--modal-shadow: 0 16px 48px rgba(60,48,30,0.12); --modal-header-border: #e8e0d4; --modal-header-color: #3d3328; "
        "--input-bg: #fefcf8; --input-border: #e0d8cc; --input-color: #3d3328; "
        "--input-focus-border: #7a6b58; --input-placeholder: #b0a090; "
        "--btn-primary-bg: #7a6b58; --btn-primary-color: #faf7f2; --btn-primary-hover-bg: #655840; "
        "--btn-success-bg: #5a9060; --btn-success-color: #faf7f2; "
        "--btn-danger-bg: #b85040; --btn-danger-color: #faf7f2; "
        "--toggle-btn-bg: #faf7f2; --toggle-btn-border: #e0d8cc; --toggle-btn-color: #8c7b68; --toggle-btn-hover-bg: #f0ebe3; "
        "--scrollbar-track: #f0ebe3; --scrollbar-thumb: #d0c4b4; --scrollbar-thumb-hover: #a89880; "
        "--histogram-track: #f0ebe3; "
        "--filter-badge-bg: #f0ebe3; --filter-badge-color: #5c4e3e; "
        "--log-bg: #faf7f2; --log-border: #e8e0d4; --log-item-border: #f0ebe3; --log-text: #5c4e3e; "
        "--synthesis-bg: #d4a030; --synthesis-border: #b08820; --synthesis-color: #5c4e3e; --synthesis-banner-bg: #fef9e7; "
        "--status-approved-banner-bg: #e8f0e0; --status-rejected-banner-bg: #f5e8e5;"
    )
    
    # Dark — full override
    dark = (
        "--font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; "
        "--font-size-xs: 11px; --font-size-sm: 12px; --font-size-md: 13px; --font-size-lg: 16px; --font-size-xl: 17px; "
        "--page-bg: #0f1419; "
        "--sidebar-bg: #1a1f2e; --sidebar-color: #e2e8f0; --sidebar-border: #2d3748; "
        "--sidebar-shadow: 1px 0 8px rgba(0,0,0,0.3); "
        "--sidebar-heading: #f1f5f9; --sidebar-subtext: #8892a4; --sidebar-text: #c4cdd8; "
        "--toolbar-bg: #1a1f2e; --toolbar-border: #2d3748; --toolbar-shadow: 0 1px 3px rgba(0,0,0,0.3); "
        "--toolbar-btn-bg: #242b3d; --toolbar-btn-border: #3d4760; --toolbar-btn-color: #c4cdd8; --toolbar-btn-hover-bg: #2d3548; "
        "--table-bg: #1a1f2e; --table-border: #2d3748; --table-radius: 12px; --table-shadow: 0 2px 8px rgba(0,0,0,0.3); "
        "--table-header-bg: #111827; --table-header-color: #e2e8f0; --table-header-border: #374151; "
        "--table-row-bg: #1a1f2e; --table-row-alt-bg: #1f2537; --table-row-hover-bg: #252d40; "
        "--table-cell-border: #2d3748; --table-cell-color: #d1d5db; "
        "--table-cell-edited-bg: #3b2f1a; --table-cell-edited-border: #d97706; "
        "--status-unprocessed: #6b7280; --status-edited: #f59e0b; --status-approved: #34d399; --status-rejected: #f87171; "
        "--pagination-bg: #1a1f2e; --pagination-border: #2d3748; --pagination-btn-bg: #242b3d; "
        "--pagination-btn-border: #3d4760; --pagination-btn-color: #c4cdd8; --pagination-btn-hover-bg: #2d3548; "
        "--pagination-btn-active-bg: #6366f1; --pagination-btn-active-color: #ffffff; --pagination-info-color: #8892a4; "
        "--modal-overlay-bg: rgba(0,0,0,0.7); --modal-bg: #1a1f2e; --modal-radius: 16px; "
        "--modal-shadow: 0 20px 60px rgba(0,0,0,0.5); --modal-header-border: #2d3748; --modal-header-color: #f1f5f9; "
        "--input-bg: #242b3d; --input-border: #3d4760; --input-color: #e2e8f0; "
        "--input-focus-border: #818cf8; --input-placeholder: #6b7280; "
        "--btn-primary-bg: #6366f1; --btn-primary-color: #ffffff; --btn-primary-hover-bg: #818cf8; "
        "--btn-success-bg: #059669; --btn-success-color: #ffffff; "
        "--btn-danger-bg: #dc2626; --btn-danger-color: #ffffff; "
        "--toggle-btn-bg: #242b3d; --toggle-btn-border: #3d4760; --toggle-btn-color: #8892a4; --toggle-btn-hover-bg: #2d3548; "
        "--scrollbar-track: #1f2537; --scrollbar-thumb: #3d4760; --scrollbar-thumb-hover: #4b5a78; "
        "--histogram-track: #242b3d; "
        "--filter-badge-bg: #242b3d; --filter-badge-color: #c4cdd8; "
        "--log-bg: #1f2537; --log-border: #2d3748; --log-item-border: #2d3748; --log-text: #c4cdd8; "
        "--synthesis-bg: #ffc107; --synthesis-border: #e0a800; --synthesis-color: #856404; --synthesis-banner-bg: #3b2f1a; "
        "--status-approved-banner-bg: #1a2e1a; --status-rejected-banner-bg: #2e1a1a;"
    )
    
    return {
        "classic": classic,
        "modern": modern,
        "eye-protection": eye_protection,
        "dark": dark,
    }


def _load_js_files() -> str:
    """Load all JS files from src/js directory"""
    js_dir = Path(__file__).parent / "js"
    js_files = [
        "panel-toggle.js",
        "table-drag.js",
        "modal.js",
        "preset.js",
        "histogram.js",
        "facet-filter.js",
        "cell-edit.js",
        "row-selection.js",
        "synthesis.js",
    ]
    
    combined_js = []
    for js_file in js_files:
        js_path = js_dir / js_file
        if js_path.exists():
            combined_js.append(f"// === {js_file} ===")
            combined_js.append(js_path.read_text())
    
    return "\n".join(combined_js)


def create_app_ui(config_path: str = "app_config.json") -> ui.Tag:
    """
    Create and return the app UI definition with split panel layout
    
    Args:
        config_path: Path to the config JSON file
    """
    # Load config only (no DB queries) — the UI just needs feature flags and titles
    from .config.config_instance import load_config_only
    app_config = load_config_only(config_path)

    # Use default_columns from config for the initial search dropdown.
    # The server will have the real column list from the actual data.
    all_columns = app_config.table.default_columns or []
    column_masks = app_config.table.column_masks or {}
    
    # Get titles from config
    app_title = app_config.app_title or "Data Editor"
    table_title = app_config.table.title or app_title
    
    # Feature flags
    enable_approval_workflow = app_config.enable_approval_workflow
    enable_save_button = app_config.enable_save_button
    enable_export = app_config.enable_export
    enable_status_filter = app_config.enable_status_filter
    enable_synthesis = app_config.enable_synthesis
    enable_search = app_config.query.enable_search
    enable_review_detail = app_config.enable_review_detail
    review_detail_label = app_config.review_detail_label or "Review Detail"
    synthesis_label = app_config.synthesis.label or "Synthesis"
    presets_enabled = app_config.table.presets_enabled
    theme = app_config.theme or "classic"
    clean_slate = app_config.clean_slate
    
    # Build theme variable maps
    theme_styles = _build_theme_styles()
    active_theme_style = theme_styles.get(theme, theme_styles["classic"])
    
    # Status labels from config
    status_labels = app_config.status_labels
    status_choices = {k: v for k, v in status_labels.items()}
    status_all_keys = list(status_labels.keys())
    
    return ui.page_fluid(
        # Hidden input to pass config path to server (completely hidden)
        ui.div(
            ui.input_text("_config_path", label=None, value=config_path),
            style="display: none; visibility: hidden; position: absolute; left: -9999px;"
        ),
        
        # Custom CSS injected in body to override Shiny/Bootstrap defaults
        ui.tags.style(_load_css_files()),
        
        ui.head_content(
            ui.tags.title(app_title),
            ui.tags.script(_load_js_files()),
            # Theme engine: stores all theme variable strings in JS, swaps inline style on #theme-provider
            ui.tags.script(f"""
                window._themeStyles = {repr(theme_styles)};
                window._currentTheme = '{theme}';
                window._configTheme = '{theme}';
                window.setTheme = function(name) {{
                    var provider = document.getElementById('theme-provider');
                    if (provider && window._themeStyles[name]) {{
                        provider.style.cssText = window._themeStyles[name];
                    }}
                    window._currentTheme = name;
                    localStorage.setItem('dmap-theme', name);
                    var sel = document.getElementById('theme-selector');
                    if (sel) sel.value = name;
                }};
                document.addEventListener('DOMContentLoaded', function() {{
                    var saved = localStorage.getItem('dmap-theme');
                    var configTheme = '{theme}';
                    var lastConfig = localStorage.getItem('dmap-theme-config');
                    var activeTheme = configTheme;
                    if (saved && lastConfig === configTheme) {{
                        activeTheme = saved;
                    }} else {{
                        localStorage.removeItem('dmap-theme');
                        localStorage.setItem('dmap-theme-config', configTheme);
                    }}
                    window.setTheme(activeTheme);
                    var sel = document.getElementById('theme-selector');
                    if (sel) {{
                        sel.value = activeTheme;
                        sel.addEventListener('change', function() {{
                            setTheme(this.value);
                        }});
                    }}
                }});
            """),
            # Namespace helper script - must be after the main JS files
            ui.tags.script("""
                // ── Centralized namespace extraction ───────────────────────────
                // Returns the Shiny namespace prefix string for a given DOM element.
                // Uses closest() first (fast), then walks up, then falls back to
                // active-tab / first-in-document.  Never returns undefined.
                window.getShinyNs = function(contextEl) {
                    var nsEl = null;

                    if (contextEl) {
                        // Fast path: closest ancestor with namespace attribute
                        nsEl = contextEl.closest ? contextEl.closest('[data-shiny-ns]') : null;

                        // Walk-up fallback (covers shadow DOM / detached subtrees)
                        if (!nsEl) {
                            var parent = contextEl;
                            while (parent && !nsEl) {
                                nsEl = parent.querySelector ? parent.querySelector('[data-shiny-ns]') : null;
                                parent = parent.parentElement;
                            }
                        }
                    }

                    // Fallback: active tab panel
                    if (!nsEl) {
                        nsEl = document.querySelector('.tab-pane.active [data-shiny-ns]')
                            || document.querySelector('[role="tabpanel"]:not([hidden]) [data-shiny-ns]');
                    }
                    if (!nsEl) {
                        // Visible panel scan
                        var panels = document.querySelectorAll('[data-shiny-ns]');
                        for (var i = 0; i < panels.length; i++) {
                            var tabPane = panels[i].closest('.tab-pane, [role="tabpanel"]');
                            if (tabPane && (tabPane.classList.contains('active') || tabPane.classList.contains('show') || !tabPane.hasAttribute('hidden'))) {
                                nsEl = panels[i];
                                break;
                            }
                        }
                    }

                    // Last resort: first namespace holder in document
                    if (!nsEl) {
                        nsEl = document.querySelector('[data-shiny-ns]');
                    }

                    return nsEl ? (nsEl.getAttribute('data-shiny-ns') || '') : '';
                };

                // ── Namespace validation helper ────────────────────────────────
                // Call from browser console: validateNamespaces()
                // Checks all [data-shiny-ns] elements and reports inconsistencies.
                window.validateNamespaces = function() {
                    var holders = document.querySelectorAll('[data-shiny-ns]');
                    if (holders.length === 0) {
                        console.warn('[NS-Validate] No [data-shiny-ns] elements found in DOM');
                        return;
                    }
                    var nsMap = {};
                    holders.forEach(function(el) {
                        var ns = el.getAttribute('data-shiny-ns');
                        var tab = el.closest('.tab-pane, [role="tabpanel"]');
                        var tabId = tab ? (tab.id || tab.getAttribute('data-value') || 'unknown') : 'root';
                        if (!nsMap[ns]) nsMap[ns] = [];
                        nsMap[ns].push({element: el, tab: tabId, validated: el.hasAttribute('data-ns-validated')});
                    });
                    var nsKeys = Object.keys(nsMap);
                    console.log('[NS-Validate] Found ' + holders.length + ' namespace holder(s), ' + nsKeys.length + ' unique namespace(s):');
                    nsKeys.forEach(function(ns) {
                        var entries = nsMap[ns];
                        console.log('  NS="' + ns + '" (' + entries.length + ' holder(s)):');
                        entries.forEach(function(e) {
                            console.log('    tab=' + e.tab + ', validated=' + e.validated);
                        });
                    });
                    // Check for orphan inputs (Shiny inputs without matching namespace)
                    if (typeof Shiny !== 'undefined' && Shiny.inputBindings) {
                        console.log('[NS-Validate] ✓ Shiny bindings available. Use Shiny.shinyapp.$inputValues to inspect live inputs.');
                    }
                    return nsMap;
                };

                // ── setShinyInput (uses getShinyNs) ────────────────────────────
                // contextEl: optional element to find the correct namespace from (for multi-tab support)
                window.setShinyInput = function(inputName, value, options, contextEl) {
                    var ns = getShinyNs(contextEl || null);
                    var fullName = ns + inputName;
                    if (ns === '' && document.querySelectorAll('[data-shiny-ns]').length > 0) {
                        console.warn('setShinyInput: resolved empty namespace for "' + inputName + '" despite namespace holders existing — possible global leakage. Pass a contextEl.');
                    }
                    console.log('setShinyInput:', inputName, '-> fullName:', fullName, 'ns:', ns);
                    if (typeof Shiny !== 'undefined') {
                        Shiny.setInputValue(fullName, value, options || {priority: 'event'});
                    } else {
                        console.warn('Shiny not available');
                    }
                };
            """)
        ),
        
        # Main Container with Split Panels — also the theme-provider (inline CSS vars)
        ui.div(
          ui.div(
            # Hidden element to provide namespace to JavaScript
            ui.output_ui("_namespace_holder"),
            
            # Viewer mode CSS injection (hides edit controls for viewer role)
            ui.output_ui("viewer_mode_ui"),
            
            # Selection mode CSS injection (hides select-all for single-select)
            ui.output_ui("selection_mode_ui"),
            
            # Clean slate mode is applied via .clean-slate class on main-container
            # (scoped so it doesn't leak into other tabs)
            
            # Left Panel - Sidebar
            ui.div(
                ui.tags.button("◀", class_="toggle-btn", onclick="toggleLeftPanel(event)"),
                ui.div(
                    # Table Name Section
                    ui.div(
                        ui.h3(table_title, class_="table-name"),
                        ui.output_text("data_summary"),
                        class_="table-name-section"
                    ),
                    
                    # Stats Histogram Section (with filter checkboxes) - conditional
                    ui.div(
                        ui.h4("Status Distribution"),
                        ui.output_ui("stats_histogram"),
                        # Hidden input to store selected statuses
                        ui.input_checkbox_group(
                            "status_filter_multi",
                            label=None,
                            choices=status_choices,
                            selected=status_all_keys
                        ),
                        class_="stats-section",
                        style="" if enable_status_filter else "display: none;"
                    ) if enable_status_filter else ui.div(
                        # Hidden default filter when status filter is disabled
                        ui.input_checkbox_group(
                            "status_filter_multi",
                            label=None,
                            choices=status_choices,
                            selected=status_all_keys
                        ),
                        style="display: none;"
                    ),
                    
                    # Search Filter
                    ui.div(
                        ui.h4("Search"),
                        ui.div(
                            ui.input_select(
                                "search_column",
                                label=None,
                                choices={"all": "All Columns"} | {col: column_masks.get(col, col) for col in all_columns},
                                selected="all",
                                width="100%"
                            ),
                            ui.input_text("search_input", label=None, placeholder="Search...", width="100%"),
                            ui.div(
                                ui.input_action_button("search_btn", "Search", class_="btn btn-primary btn-sm"),
                                ui.input_action_button("clear_search_btn", "Clear", class_="btn btn-outline-secondary btn-sm", style="margin-left: 5px;"),
                                style="display: flex; align-items: center; margin-top: 5px;"
                            ),
                            class_="filter-group"
                        ),
                        class_="filter-section"
                    ) if enable_search else ui.div(),
                    
                    # Facet Filter Panels (checkbox + value counts)
                    ui.output_ui("facet_panels_ui"),
                    
                    # Column Filters (Dynamic)
                    ui.div(
                        ui.div(
                            ui.h4("Column Filters", style="display: inline-block; margin: 0;"),
                            ui.output_ui("add_filter_btn_ui"),
                            ui.output_ui("apply_filters_ui"),
                            class_="filter-header"
                        ),
                        ui.output_ui("dynamic_filters"),
                        class_="column-filter-section"
                    ),
                    
                    class_="panel-content"
                ),
                class_="left-panel"
            ),
            
            # Right Panel - Main Content
            ui.div(
                # Top Toolbar - Actions + Preset + Add Column
                ui.div(
                    # Left side - Action Buttons (conditionally rendered based on config)
                    ui.div(
                        ui.input_action_button("save_btn", "Save", class_="btn btn-sm btn-success") if enable_save_button else None,
                        ui.tags.button("Export Selected", class_="btn btn-sm btn-info", onclick="openExportConfirmModal(event, 'selected')") if enable_export else None,
                        ui.tags.button("Export All", class_="btn btn-sm export-all-btn", onclick="openExportConfirmModal(event, 'all')") if enable_export else None,
                        ui.input_action_button("approve_btn", "Approve", class_="btn btn-sm btn-success") if enable_approval_workflow else None,
                        ui.input_action_button("reject_btn", "Reject", class_="btn btn-sm btn-danger") if enable_approval_workflow else None,
                        ui.tags.button("Copy", class_="btn btn-sm btn-secondary", onclick="openCopyModal(event)"),
                        ui.tags.button("Clear Selection", class_="btn btn-sm btn-outline-secondary", onclick="deselectAllRows(event)"),
                        ui.input_action_button("reload_btn", "↻ Refresh", class_="btn btn-sm btn-outline-secondary"),
                        ui.input_action_button("review_detail_btn", review_detail_label, class_="btn btn-sm btn-outline-primary") if enable_review_detail else None,
                        ui.tags.button(
                            synthesis_label,
                            class_="btn btn-sm btn-outline-warning synthesis-btn",
                            onclick="openSynthesisModal(event)"
                        ) if enable_synthesis else None,
                        class_="toolbar-left"
                    ),
                    # Right side - Preset dropdown + Add Column button
                    ui.div(
                        # Preset Dropdown (hidden when presets disabled)
                        ui.div(
                            ui.tags.button(
                                "Preset: ",
                                ui.output_text("current_preset_name", inline=True),
                                " ▼",
                                class_="preset-btn",
                                onclick="togglePresetMenu(event)"
                            ),
                            ui.div(
                                ui.output_ui("preset_menu_items"),
                                ui.div(class_="preset-menu-divider"),
                                ui.div(
                                    "⟳ Refresh",
                                    class_="preset-menu-item",
                                    onclick="refreshPresets(event)",
                                    style="color: #007bff;"
                                ),
                                ui.div(class_="preset-menu-divider"),
                                ui.div(
                                    ui.tags.input(type="text", placeholder="New preset name...", class_="new-preset-name-input"),
                                    ui.tags.button("Save", class_="btn btn-sm btn-primary", onclick="saveNewPreset(this)"),
                                    class_="preset-save-row"
                                ),
                                ui.div(class_="preset-menu-divider"),
                                ui.div(
                                    "Reset to Default",
                                    class_="preset-menu-item",
                                    onclick="resetColumns(event)"
                                ),
                                class_="preset-menu"
                            ),
                            class_="preset-dropdown"
                        ) if presets_enabled else None,
                        # Save Layout Button
                        ui.tags.button("Save Layout", class_="save-layout-btn", onclick="saveLayoutPrompt(event)") if presets_enabled else None,
                        # Manage Layout Button
                        ui.tags.button("Manage Layout", class_="add-col-btn", onclick="openAddColumnModal(event)"),
                        # Modifications Log Button
                        ui.tags.button("Mod Log", class_="mod-log-btn", onclick="openLogModal(event)"),
                        # Theme selector
                        ui.tags.select(
                            ui.tags.option("Modern", value="modern", selected="selected" if theme == "modern" else None),
                            ui.tags.option("Classic", value="classic", selected="selected" if theme == "classic" else None),
                            ui.tags.option("Eye Protection", value="eye-protection", selected="selected" if theme == "eye-protection" else None),
                            ui.tags.option("Dark", value="dark", selected="selected" if theme == "dark" else None),
                            id="theme-selector",
                            onchange="setTheme(this.value)",
                            class_="theme-selector",
                            title="Color Theme"
                        ),
                        class_="toolbar-right"
                    ),
                    class_="top-toolbar"
                ),
                
                # Add Column Modal
                ui.div(
                    ui.div(
                        ui.div(
                            ui.h3("Manage Layout"),
                            ui.tags.button("Remove All", class_="btn btn-sm btn-outline-danger", onclick="removeAllColumns(event)", style="margin-left: auto; margin-right: 6px;"),
                            ui.tags.button("Add All", class_="btn btn-sm btn-outline-success", onclick="addAllColumns(event)", style="margin-right: 6px;"),
                            ui.tags.button("Update", class_="btn btn-sm btn-primary", onclick="updateCurrentPreset(event)", style="margin-right: 10px;"),
                            ui.tags.button("×", class_="modal-close", onclick="closeModal()"),
                            class_="modal-header"
                        ),
                        ui.div(
                            ui.output_ui("available_columns_modal"),
                            class_="modal-body"
                        ),
                        class_="modal-content"
                    ),
                    class_="modal-overlay",
                    id="add-column-modal"
                ),
                
                # Copy Column Modal
                ui.div(
                    ui.div(
                        ui.div(
                            ui.h3("Copy Column Values"),
                            ui.tags.button("×", class_="modal-close", onclick="closeCopyModal()"),
                            class_="modal-header"
                        ),
                        ui.div(
                            ui.p("Select a column to copy values from selected rows:", style="margin-bottom: 10px; font-size: 13px;"),
                            ui.output_ui("copy_column_list"),
                            class_="modal-body"
                        ),
                        class_="modal-content"
                    ),
                    class_="modal-overlay",
                    id="copy-column-modal"
                ),
                
                # Add Filter Modal
                ui.div(
                    ui.div(
                        ui.div(
                            ui.h3("Add Column Filter"),
                            ui.tags.button("×", class_="modal-close", onclick="closeAddFilterModal()"),
                            class_="modal-header"
                        ),
                        ui.div(
                            ui.tags.input(
                                type="text",
                                placeholder="Search columns...",
                                class_="form-control form-control-sm filter-col-search",
                                oninput="_filterColumnList(this.value)",
                                style="margin-bottom: 10px; font-size: 12px;"
                            ),
                            ui.output_ui("available_filter_columns"),
                            class_="modal-body"
                        ),
                        class_="modal-content"
                    ),
                    class_="modal-overlay",
                    id="add-filter-modal"
                ),
                
                # Filter Values Modal (for multi-select)
                ui.div(
                    ui.div(
                        ui.div(
                            ui.h3("Select Filter Values"),
                            ui.tags.button("×", class_="modal-close", onclick="closeFilterValuesModal()"),
                            class_="modal-header"
                        ),
                        ui.div(
                            ui.div(
                                ui.input_text("filter_values_search", label=None, placeholder="Search values..."),
                                style="margin-bottom: 10px;"
                            ),
                            ui.div(
                                ui.tags.button("Select All", class_="btn btn-sm btn-outline-primary", onclick="selectAllFilterValues()", style="margin-right: 5px;"),
                                ui.tags.button("Clear All", class_="btn btn-sm btn-outline-secondary", onclick="clearAllFilterValues()"),
                                style="margin-bottom: 10px;"
                            ),
                            ui.div(
                                id="filter-values-checkboxes",
                                style="max-height: 300px; overflow-y: auto; border: 1px solid #ddd; padding: 10px; border-radius: 4px;"
                            ),
                            ui.div(
                                ui.tags.button("Apply", class_="btn btn-primary", onclick="applyFilterValues()", style="margin-right: 10px;"),
                                ui.tags.button("Cancel", class_="btn btn-secondary", onclick="closeFilterValuesModal()"),
                                style="margin-top: 15px; text-align: right;"
                            ),
                            class_="modal-body"
                        ),
                        class_="modal-content",
                        style="max-width: 500px;"
                    ),
                    class_="modal-overlay",
                    id="filter-values-modal"
                ),
                
                # Data Table
                ui.div(
                    ui.div(
                        ui.output_ui("table_container"),
                        class_="table-scroll-wrapper"
                    ),
                    class_="table-container-frame"
                ),
                
                # Pagination Controls (at bottom)
                ui.div(
                    ui.output_ui("pagination_controls"),
                    class_="pagination-controls-section"
                ),
                
                # Export PHI/PII Confirmation Modal
                ui.div(
                    ui.div(
                        ui.div(
                            ui.h3("Sensitive Data Export Warning"),
                            ui.tags.button("×", class_="modal-close", onclick="closeExportConfirmModal()"),
                            class_="modal-header"
                        ),
                        ui.div(
                            ui.tags.p(
                                "The data you are about to download may contain ",
                                ui.tags.strong("Protected Health Information (PHI)"),
                                " and/or ",
                                ui.tags.strong("Personally Identifiable Information (PII)"),
                                ".",
                                style="margin-bottom: 12px; line-height: 1.6;"
                            ),
                            ui.tags.p(
                                "Please ensure you have the appropriate permissions and authorization "
                                "to download and store this data. You are responsible for handling "
                                "the exported file in compliance with all applicable data privacy "
                                "regulations and institutional policies.",
                                style="margin-bottom: 0; color: #555; line-height: 1.6;"
                            ),
                            # Dynamic area: shows preparing spinner → download button when ready
                            ui.output_ui("export_download_ui"),
                            class_="modal-body"
                        ),
                        ui.div(
                            ui.tags.button(
                                "Cancel",
                                class_="btn btn-secondary",
                                onclick="closeExportConfirmModal()",
                                style="margin-right: 10px;"
                            ),
                            ui.tags.button(
                                "I Understand",
                                class_="btn btn-primary",
                                id="export-confirm-btn",
                                onclick="confirmExportDownload(event)"
                            ),
                            style="display: flex; justify-content: flex-end; padding: 10px 20px; border-top: 1px solid #dee2e6;",
                            id="export-modal-footer"
                        ),
                        class_="modal-content",
                        style="max-width: 480px;"
                    ),
                    class_="modal-overlay",
                    id="export-confirm-modal"
                ),
                
                # Modifications Log Modal
                ui.div(
                    ui.div(
                        ui.div(
                            ui.h3("Modifications Log"),
                            ui.tags.button("×", class_="modal-close", onclick="closeLogModal()"),
                            class_="modal-header"
                        ),
                        ui.div(
                            ui.div(
                                ui.output_ui("modifications_log_ui"),
                                class_="log-container"
                            ),
                            class_="modal-body"
                        ),
                        ui.div(
                            ui.tags.button("Cancel", class_="btn btn-secondary", onclick="closeLogModal()"),
                            style="display: flex; justify-content: flex-end; padding: 10px 20px; border-top: 1px solid #dee2e6;"
                        ),
                        class_="modal-content"
                    ),
                    class_="modal-overlay",
                    id="log-modal"
                ),
                
                # Synthesis Modal (conditionally rendered)
                ui.div(
                    ui.div(
                        ui.div(
                            ui.h3(synthesis_label if enable_synthesis else "Synthesis"),
                            ui.tags.button("×", class_="modal-close", onclick="closeSynthesisModal()"),
                            class_="modal-header"
                        ),
                        ui.div(
                            # Synthesis mode banner (shown when viewing synthesized data)
                            ui.output_ui("synthesis_mode_banner"),
                            # Query preview
                            ui.div(
                                ui.h5("Transform Query", style="margin-bottom: 8px;"),
                                ui.output_ui("synthesis_query_preview"),
                                class_="synthesis-query-section"
                            ),
                            # Status/progress area
                            ui.output_ui("synthesis_status"),
                            class_="modal-body"
                        ),
                        ui.div(
                            ui.tags.button(
                                "Cancel",
                                class_="btn btn-secondary",
                                onclick="closeSynthesisModal()",
                                style="margin-right: 10px;"
                            ),
                            ui.input_action_button(
                                "synthesis_run_btn",
                                "Run Transform",
                                class_="btn btn-warning"
                            ),
                            ui.input_action_button(
                                "synthesis_regen_btn",
                                "Regenerate",
                                class_="btn btn-outline-warning",
                                style="display: none; margin-left: 8px;"
                            ),
                            style="display: flex; justify-content: flex-end; padding: 10px 20px; border-top: 1px solid #dee2e6;",
                            id="synthesis-modal-footer"
                        ),
                        class_="modal-content",
                        style="max-width: 700px;"
                    ),
                    class_="modal-overlay",
                    id="synthesis-modal"
                ) if enable_synthesis else None,
                
                class_="right-panel"
            ),
            
            class_="main-container clean-slate" if clean_slate else "main-container"
          ),
          id="theme-provider",
          style=active_theme_style
        ),
    )


# Note: app_ui is created on-demand by calling create_app_ui(config_path)
# This supports the widget pattern where each instance can have its own config
