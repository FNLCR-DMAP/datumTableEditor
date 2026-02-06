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
    rows_str = ', '.join(str(r + 1) for r in rows[:5])
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
    rows_str = ', '.join(str(r + 1) for r in rows[:5])
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
    pk = details.get('primary_key', details.get('row_index', '?'))
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
    pk = details.get('primary_key', details.get('row_index', '?'))
    return ui.div(
        ui.div(
            ui.tags.span(f"[{timestamp[:19]}]", class_="timestamp"),
            ui.tags.button(
                "Undo",
                class_="btn btn-xs btn-outline-warning undo-btn",
                onclick=f"undoModification({log_idx})",
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


def build_status_histogram_bar(status: str, count: int, pct: float, is_checked: bool) -> ui.div:
    """Build a single bar for the status histogram."""
    return ui.div(
        ui.tags.label(
            ui.tags.input(
                type="checkbox",
                checked="checked" if is_checked else None,
                value=status,
                class_="status-checkbox",
                **{"data-status": status}
            ),
            ui.span(f"{status.capitalize()}", class_=f"histogram-label status-label-{status}"),
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
    displayable = [(i, m) for i, m in enumerate(log)]
    
    for actual_idx, mod in reversed(displayable):
        timestamp = mod.get("timestamp", "Unknown")
        details = mod.get("details", {})
        mod_type = mod.get("type")
        is_undone = mod.get("undone", False)
        
        if mod_type == "undo":
            log_items.append(build_log_entry_undo(timestamp, details))
        elif mod_type == "approval":
            log_items.append(build_log_entry_approval(timestamp, details))
        elif mod_type == "rejection":
            log_items.append(build_log_entry_rejection(timestamp, details))
        elif is_undone:
            log_items.append(build_log_entry_undone(timestamp, details))
        elif mod_type == "field_modification":
            log_items.append(build_log_entry_field_modification(timestamp, details, actual_idx))
    
    if not log_items:
        return build_empty_log_message()
    
    return ui.div(*log_items)
