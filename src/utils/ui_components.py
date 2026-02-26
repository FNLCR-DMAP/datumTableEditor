"""
UI component builders for the Epitopes Data Editor.
These functions generate Shiny UI components for various parts of the application.
"""

from shiny import ui


def build_log_entry_undo(timestamp: str, details: dict) -> ui.div:
    """Build UI for an undo log entry."""
    pk = details.get('primary_key', details.get('row_index', '?'))
    return ui.div(
        ui.div(
            ui.tags.span(f"[{timestamp[:19]}]", class_="timestamp"),
            ui.tags.span("UNDO", style="color: #ffc107; font-size: 10px; font-weight: bold;"),
            style="display: flex; justify-content: space-between; align-items: center;"
        ),
        ui.tags.span(
            f"[{pk}] {details.get('column', '?')}: "
            f"reverted to '{details.get('reverted_to', '')}'",
            class_="change-detail",
            style="font-size: 11px; display: block; margin-top: 4px; color: #888;"
        ),
        class_="log-entry",
        style="padding: 8px; border-bottom: 1px solid #eee; background: #fffdf0;"
    )


def build_log_entry_approval(timestamp: str, details: dict) -> ui.div:
    """Build UI for an approval log entry."""
    row_count = details.get('approved_row_count', 0)
    rows = details.get('approved_rows', [])
    
    # Handle both PK dicts and legacy row indices
    def format_row(r):
        if isinstance(r, dict):
            # PK dict - get first value
            pk_val = list(r.values())[0] if r else "?"
            return f"[{pk_val}]"
        else:
            # Legacy row index
            return str(r + 1)
    
    rows_str = ', '.join(format_row(r) for r in rows[:5])
    if len(rows) > 5:
        rows_str += f"... (+{len(rows) - 5} more)"
    
    return ui.div(
        ui.div(
            ui.tags.span(f"[{timestamp[:19]}]", class_="timestamp"),
            ui.tags.span("APPROVED", style="color: #28a745; font-size: 10px; font-weight: bold;"),
            style="display: flex; justify-content: space-between; align-items: center;"
        ),
        ui.tags.span(
            f"{row_count} row(s): {rows_str}",
            class_="change-detail",
            style="font-size: 11px; display: block; margin-top: 4px; color: #28a745;"
        ),
        class_="log-entry",
        style="padding: 8px; border-bottom: 1px solid #eee; background: #f0fff0;"
    )


def build_log_entry_rejection(timestamp: str, details: dict) -> ui.div:
    """Build UI for a rejection log entry."""
    row_count = details.get('rejected_row_count', 0)
    rows = details.get('rejected_rows', [])
    
    # Handle both PK dicts and legacy row indices
    def format_row(r):
        if isinstance(r, dict):
            # PK dict - get first value
            pk_val = list(r.values())[0] if r else "?"
            return f"[{pk_val}]"
        else:
            # Legacy row index
            return str(r + 1)
    
    rows_str = ', '.join(format_row(r) for r in rows[:5])
    if len(rows) > 5:
        rows_str += f"... (+{len(rows) - 5} more)"
    
    return ui.div(
        ui.div(
            ui.tags.span(f"[{timestamp[:19]}]", class_="timestamp"),
            ui.tags.span("REJECTED", style="color: #dc3545; font-size: 10px; font-weight: bold;"),
            style="display: flex; justify-content: space-between; align-items: center;"
        ),
        ui.tags.span(
            f"{row_count} row(s): {rows_str}",
            class_="change-detail",
            style="font-size: 11px; display: block; margin-top: 4px; color: #dc3545;"
        ),
        class_="log-entry",
        style="padding: 8px; border-bottom: 1px solid #eee; background: #fff0f0;"
    )


def build_log_entry_undone(timestamp: str, details: dict) -> ui.div:
    """Build UI for an undone field modification log entry."""
    # Handle different PK formats: primary_key (in-memory), row_pk (from DB), row_index (legacy)
    pk = details.get('primary_key') or details.get('row_pk') or details.get('row_index', '?')
    # If pk is a dict, format it nicely
    if isinstance(pk, dict):
        pk = ', '.join(f"{v}" for v in pk.values()) if pk else '?'
    return ui.div(
        ui.div(
            ui.tags.span(f"[{timestamp[:19]}]", class_="timestamp", style="text-decoration: line-through; color: #999;"),
            ui.tags.span("UN-DONE", style="color: #dc3545; font-size: 10px; font-weight: bold;"),
            style="display: flex; justify-content: space-between; align-items: center;"
        ),
        ui.tags.span(
            f"[{pk}] {details.get('column', '?')}: "
            f"'{details.get('old_value', '')}' → '{details.get('new_value', '')}'",
            class_="change-detail",
            style="font-size: 11px; display: block; margin-top: 4px; text-decoration: line-through; color: #999;"
        ),
        class_="log-entry",
        style="padding: 8px; border-bottom: 1px solid #eee; background: #fff5f5;"
    )


def build_log_entry_field_modification(timestamp: str, details: dict, log_idx: int) -> ui.div:
    """Build UI for a field modification log entry with undo button."""
    # Handle different PK formats: primary_key (in-memory), row_pk (from DB), row_index (legacy)
    pk = details.get('primary_key') or details.get('row_pk') or details.get('row_index', '?')
    # If pk is a dict, format it nicely
    if isinstance(pk, dict):
        pk = ', '.join(f"{v}" for v in pk.values()) if pk else '?'
    return ui.div(
        ui.div(
            ui.tags.span(f"[{timestamp[:19]}]", class_="timestamp"),
            ui.tags.button(
                "Undo",
                class_="btn btn-xs btn-outline-warning undo-btn",
                onclick=f"undoModification({log_idx}, event)",
                style="float: right; padding: 2px 8px; font-size: 10px;"
            ),
            style="display: flex; justify-content: space-between; align-items: center;"
        ),
        ui.tags.span(
            f"[{pk}] {details.get('column', '?')}: "
            f"'{details.get('old_value', '')}' → '{details.get('new_value', '')}'",
            class_="change-detail",
            style="font-size: 11px; display: block; margin-top: 4px;"
        ),
        class_="log-entry",
        style="padding: 8px; border-bottom: 1px solid #eee;"
    )


def build_status_histogram_bar(status: str, count: int, pct: float, is_checked: bool, label: str = None) -> ui.div:
    """Build a single bar for the status histogram."""
    display_label = label or status.capitalize()
    return ui.div(
        ui.tags.label(
            ui.tags.input(
                type="checkbox",
                checked="checked" if is_checked else None,
                value=status,
                class_="status-checkbox",
                **{"data-status": status}
            ),
            ui.span(display_label, class_=f"histogram-label status-label-{status}"),
            class_="histogram-checkbox-label"
        ),
        ui.div(
            ui.div(style=f"width: {pct}%;", class_=f"histogram-fill {status}"),
            class_="histogram-track"
        ),
        ui.span(str(count), class_="histogram-count"),
        class_="histogram-bar"
    )


def build_empty_log_message() -> ui.div:
    """Build the empty log placeholder message."""
    return ui.div(
        "No modifications yet. Edit cells in the table above to get started.",
        style="color: #999; padding: 20px; text-align: center;",
    )


# ── Facet Filter Panels ──────────────────────────────────────────────────

def build_facet_bar(col_name: str, value: str, count: int, max_count: int, is_checked: bool) -> ui.div:
    """Build a single facet value row: checkbox + label + count + bar."""
    pct = (count / max_count * 100) if max_count > 0 else 0
    return ui.div(
        ui.tags.label(
            ui.tags.input(
                type="checkbox",
                checked="checked" if is_checked else None,
                value=value,
                class_="facet-checkbox",
                **{"data-column": col_name}
            ),
            ui.span(
                value if len(value) <= 25 else value[:22] + "…",
                class_="facet-label",
                title=value
            ),
            class_="facet-checkbox-label"
        ),
        ui.span(f"{count:,}", class_="facet-count"),
        ui.div(
            ui.div(style=f"width: {pct}%;", class_="facet-fill"),
            class_="facet-track"
        ),
        class_="facet-bar"
    )


def build_facet_panel(
    col_name: str,
    value_counts: list,
    selected_values: list | None,
    max_visible: int = 5,
    column_masks: dict | None = None,
) -> ui.div:
    """Build a complete facet panel for one column.

    Args:
        col_name: Column name.
        value_counts: List of (value, count) tuples, sorted by count desc.
        selected_values: Currently checked values (None = all checked).
        max_visible: How many rows to show before "Show more" toggle.
        column_masks: Optional display-name overrides.
    """
    display_name = (column_masks or {}).get(col_name, col_name).upper()
    max_count = value_counts[0][1] if value_counts else 1

    # Generate bars
    bars = []
    for val, cnt in value_counts:
        is_checked = selected_values is None or val in selected_values
        bars.append(build_facet_bar(col_name, val, cnt, max_count, is_checked))

    # Split into visible + overflow
    visible = bars[:max_visible]
    overflow = bars[max_visible:]

    children = [ui.h4(display_name, class_="facet-title")]
    children.extend(visible)

    if overflow:
        # Overflow bucket in a collapsible wrapper
        collapse_id = f"facet-more-{col_name.replace(' ', '_')}"
        children.append(
            ui.div(*overflow, class_="facet-overflow", id=collapse_id, style="display: none;")
        )
        children.append(
            ui.tags.button(
                "Show more",
                class_="facet-toggle-btn",
                onclick=(
                    f"(function(btn){{"
                    f"  var el=document.getElementById('{collapse_id}');"
                    f"  if(el.style.display==='none'){{el.style.display='';btn.textContent='Show less';}}"
                    f"  else{{el.style.display='none';btn.textContent='Show more';}}"
                    f"}})(this)"
                )
            )
        )

    return ui.div(*children, class_="facet-section", **{"data-facet-column": col_name})


def build_facet_panels(
    facet_columns: list,
    value_counts_map: dict,
    selected_map: dict | None = None,
    max_visible: int = 5,
    column_masks: dict | None = None,
) -> ui.div:
    """Build all facet panels for the sidebar.

    Args:
        facet_columns: Ordered list of column names to show.
        value_counts_map: ``{col: [(value, count), ...]}``
        selected_map: ``{col: [selected_values]}`` or None (all selected).
        max_visible: Rows before "Show more".
        column_masks: Display-name overrides.
    """
    panels = []
    for col in facet_columns:
        vc = value_counts_map.get(col, [])
        selected = (selected_map or {}).get(col)
        panels.append(build_facet_panel(col, vc, selected, max_visible, column_masks))
    return ui.div(*panels, class_="facet-panels") if panels else ui.div()


def build_approval_status_banner(status: str, timestamp: str) -> ui.div:
    """Build the approval/rejection status banner UI."""
    if status is None:
        return ui.div()
    
    if status == "approved":
        return ui.div(
            ui.div(f"APPROVED on {timestamp}", class_="status-approved-banner"),
            ui.div(
                ui.input_action_button("clear_approval_btn", "Clear", class_="btn btn-sm btn-secondary"),
                style="text-align: center; margin-top: 10px;"
            )
        )
    elif status == "rejected":
        return ui.div(
            ui.div(f"REJECTED on {timestamp}", class_="status-rejected-banner"),
            ui.div(
                ui.input_action_button("clear_approval_btn", "Clear", class_="btn btn-sm btn-secondary"),
                style="text-align: center; margin-top: 10px;"
            )
        )
    return ui.div()


def build_modifications_log(log: list) -> ui.div:
    """Build the modifications log UI from log entries."""
    if not log:
        return build_empty_log_message()
    
    log_items = []
    # Show all entries (field modifications, approvals, rejections)
    for actual_idx, mod in reversed(list(enumerate(log))):
        timestamp = mod.get("timestamp", "Unknown")
        details = mod.get("details", {})
        mod_type = mod.get("type")
        undone = mod.get("undone", False)
        
        if mod_type == "approval":
            log_items.append(build_log_entry_approval(timestamp, details))
        elif mod_type == "rejection":
            log_items.append(build_log_entry_rejection(timestamp, details))
        elif mod_type == "field_modification":
            if undone:
                log_items.append(build_log_entry_undone(timestamp, details))
            else:
                log_items.append(build_log_entry_field_modification(timestamp, details, actual_idx))
    
    if not log_items:
        return build_empty_log_message()
    
    return ui.div(*log_items)
