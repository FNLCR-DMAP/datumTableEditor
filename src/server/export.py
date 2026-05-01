"""
Server export — confirm → prepare → download flow.
"""
import io
import re
from datetime import datetime

from shiny import render, ui, reactive

from ..utils import sort_dataframe
from .context import ServerContext


def register_export(ctx: ServerContext):
    """Register export reactive effects and render outputs."""
    input = ctx.input
    app_config = ctx.app_config
    data = ctx.data
    active_columns = ctx.active_columns
    column_masks = ctx.column_masks
    current_sort = ctx.current_sort
    is_lazy_loading = ctx.is_lazy_loading
    _get_page_selection = ctx._get_page_selection
    _get_filtered_rows = ctx._get_filtered_rows
    _fetch_all_filtered_data = ctx._fetch_all_filtered_data

    # Reactive values for export state
    export_state = ctx.export_state
    export_csv_data = ctx.export_csv_data
    export_row_count = ctx.export_row_count
    export_type = ctx.export_type

    @reactive.Effect
    @reactive.event(input.confirm_export)
    def _prepare_export():
        """Prepare export data after user confirms PHI/PII warning."""
        req = input.confirm_export()
        etype = req.get("type", "all") if isinstance(req, dict) else "all"
        export_type.set(etype)
        export_state.set("preparing")

        try:
            if etype == "selected":
                page_df, selected_indices = _get_page_selection()
                if not selected_indices:
                    ui.notification_show("Please select rows to export", type="warning", duration=3)
                    export_state.set("idle")
                    return
                result_df = page_df.loc[page_df.index.isin(selected_indices)]
            else:
                if is_lazy_loading():
                    result_df = _fetch_all_filtered_data()
                else:
                    current_df = data.get()
                    if current_df.empty:
                        ui.notification_show("No data to export", type="warning", duration=3)
                        export_state.set("idle")
                        return
                    filtered_indices = _get_filtered_rows()
                    if not filtered_indices:
                        ui.notification_show("No rows match current filters", type="warning", duration=3)
                        export_state.set("idle")
                        return
                    result_df = current_df.iloc[filtered_indices].copy()
                    sort_state = current_sort.get()
                    if sort_state.get("column") and sort_state.get("column") in result_df.columns:
                        result_df = sort_dataframe(
                            result_df,
                            sort_state.get("column"),
                            "asc" if sort_state.get("ascending", True) else "desc"
                        )

            if result_df.empty:
                ui.notification_show("No data to export", type="warning", duration=3)
                export_state.set("idle")
                return

            ui_cols = [c for c in active_columns.get() if c in result_df.columns]
            if ui_cols:
                result_df = result_df[ui_cols]

            if column_masks:
                result_df = result_df.rename(columns=column_masks)

            output = io.StringIO()
            result_df.to_csv(output, index=False)
            export_csv_data.set(output.getvalue())
            export_row_count.set(len(result_df))
            export_state.set("ready")
        except Exception as e:
            ui.notification_show(f"Export failed: {str(e)}", type="error", duration=5)
            export_state.set("error")

    @render.ui
    def export_download_ui():
        """Render export status indicator and download button in the modal."""
        state = export_state.get()

        if state == "idle":
            return ui.div()

        if state == "preparing":
            return ui.div(
                ui.div(
                    ui.tags.span(
                        class_="spinner-border spinner-border-sm",
                        role="status",
                        style="margin-right: 8px;"
                    ),
                    "Preparing data for download...",
                    style="display: flex; align-items: center; color: #0d6efd; font-weight: 500;"
                ),
                style="margin-top: 16px; padding: 12px; background: #f0f7ff; border-radius: 6px;"
            )

        if state == "ready":
            row_count = export_row_count.get()
            etype = export_type.get()
            label = "selected" if etype == "selected" else "filtered"
            ready_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return ui.div(
                ui.div(
                    ui.tags.span("✅ ", style="font-size: 18px; margin-right: 6px;"),
                    f"Data ready — {row_count} {label} row(s)",
                    ui.tags.span(
                        f" (prepared at {ready_ts})",
                        style="font-weight: 400; font-size: 0.85em; color: #6c757d; margin-left: 4px;"
                    ),
                    style="font-weight: 500; color: #198754; margin-bottom: 10px;"
                ),
                ui.download_button(
                    "export_prepared_btn",
                    "⬇ Download CSV",
                    class_="btn btn-success",
                    style="width: 100%;"
                ),
                style="margin-top: 16px; padding: 12px; background: #f0fff4; border-radius: 6px;"
            )

        if state == "error":
            return ui.div(
                "❌ Export failed. Please close and try again.",
                style="margin-top: 16px; padding: 12px; background: #fff0f0; border-radius: 6px; color: #dc3545; font-weight: 500;"
            )

        return ui.div()

    def _get_export_filename():
        """Generate dynamic filename based on app title and export type."""
        title = app_config.app_title or "data"
        safe_title = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_')
        etype = export_type.get()
        suffix = "selected" if etype == "selected" else "filtered"
        return f"{safe_title}_data_{suffix}.csv"

    @render.download(filename=_get_export_filename)
    async def export_prepared_btn():
        """Serve the prepared CSV data."""
        csv_content = export_csv_data.get()
        if not csv_content:
            return
        row_count = export_row_count.get()
        ui.notification_show(f"Exported {row_count} row(s)", type="message", duration=2)
        export_state.set("idle")
        export_csv_data.set("")
        yield csv_content
