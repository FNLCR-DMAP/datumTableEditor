"""
Server edits — cell edit, cell reset, undo, approve/reject, reload, save.
"""
from shiny import render, ui, reactive
from shiny.types import SilentException, SilentCancelOutputException

from ..utils import (
    build_approval_status_banner,
    build_modifications_log,
    perform_undo,
    perform_cell_edit,
    save_modifications_to_file,
    save_log_to_file,
    export_status_report,
    create_approval_entry,
    create_rejection_entry,
    get_row_status,
    process_undo_action,
    process_cell_edit_action,
)
from ..utils import tracker
from .context import ServerContext


def register_edits(ctx: ServerContext):
    """Register cell-edit, undo, approve/reject reactive effects."""
    input = ctx.input
    config = ctx.config
    app_config = ctx.app_config
    data = ctx.data
    total_rows = ctx.total_rows
    filtered_row_count = ctx.filtered_row_count
    mods_log = ctx.mods_log
    edited_cells = ctx.edited_cells
    approval_status = ctx.approval_status
    approval_timestamp = ctx.approval_timestamp
    current_page = ctx.current_page
    _table_reload_trigger = ctx._table_reload_trigger
    data_dir = ctx.data_dir
    modifications_log_path = ctx.modifications_log_path
    is_lazy_loading = ctx.is_lazy_loading
    _require_editor = ctx._require_editor
    _get_page_selection = ctx._get_page_selection
    _get_selected_pks = ctx._get_selected_pks
    _get_modification_summary = ctx._get_modification_summary
    _save_status_to_db = ctx._save_status_to_db
    load_modifications_log = ctx.load_modifications_log
    load_data_from_source = ctx.load_data_from_source
    _cached_page_data = ctx._cached_page_data

    @render.ui
    def approval_status_ui():
        with tracker.track_render("approval_status_ui"):
            result = build_approval_status_banner(approval_status.get(), approval_timestamp.get())
        return result

    @render.ui
    def modifications_log_ui():
        with tracker.track_render("modifications_log_ui"):
            # Get PKs for currently displayed rows to filter the log
            displayed_pks = None
            if _cached_page_data and not is_lazy_loading():
                try:
                    page_df, _, _, _ = _cached_page_data()
                    pk_cols = app_config.table.primary_key
                    displayed_pks = []
                    for _, row in page_df.iterrows():
                        row_pk = {pk: row[pk] for pk in pk_cols if pk in page_df.columns}
                        if row_pk:
                            displayed_pks.append(row_pk)
                except Exception:
                    pass
            result = build_modifications_log(mods_log.get(), displayed_pks)
        return result

    @reactive.Effect
    @reactive.event(input.undo_modification)
    def _handle_undo():
        if not _require_editor("Undo"):
            return
        log_idx = process_undo_action(input.undo_modification())
        if log_idx is None:
            return
        updated_df, updated_log, message, error = perform_undo(data.get(), mods_log.get(), log_idx, config_instance=config)
        if error:
            ui.notification_show(error, type="warning", duration=2)
        else:
            data.set(updated_df)
            mods_log.set(updated_log)
            save_log_to_file(updated_log, modifications_log_path)
            updated_df.to_json(data_dir / "data_state.json", orient="records", indent=2, default_handler=str)
            ui.notification_show(message, type="message", duration=2)

    @reactive.Effect
    @reactive.event(input.cell_edit)
    def _handle_cell_edit():
        if not _require_editor("Editing"):
            return
        edit_data = input.cell_edit()
        print(f"DEBUG: cell_edit received: {edit_data}")
        row, col, old_val, new_val = process_cell_edit_action(edit_data)
        print(f"DEBUG: processed edit - row={row}, col={col}, old={old_val}, new={new_val}")
        if row is not None and col:
            if is_lazy_loading() and _cached_page_data:
                current_df, _, _, _ = _cached_page_data()
            else:
                current_df = data.get()
            current_log = mods_log.get()
            print(f"DEBUG: config type={type(config)}, db_mode={config.app_config.database.mode if hasattr(config, 'app_config') else 'N/A'}")
            updated_df, updated_log = perform_cell_edit(current_df, current_log, row, col, old_val, new_val, config_instance=config)
            print(f"DEBUG: perform_cell_edit returned, log entries: {len(updated_log)}")
            if not is_lazy_loading():
                data.set(updated_df)
            mods_log.set(updated_log)

            pk_cols = app_config.table.primary_key
            target_col = col
            for mapping in (app_config.edit_assignment or []):
                if isinstance(mapping, dict) and mapping.get('source') == col:
                    target_col = mapping['target']
                    break
            try:
                row_data = current_df.iloc[row]
                row_pk = {pk: row_data[pk] for pk in pk_cols if pk in current_df.columns}
                pk_tuple = tuple(sorted((k, str(v)) for k, v in row_pk.items()))
                current_edited = edited_cells.get().copy()
                cell_key = (pk_tuple, target_col)
                if cell_key not in current_edited:
                    current_edited[cell_key] = {"original": old_val, "current": new_val}
                else:
                    current_edited[cell_key]["current"] = new_val
                edited_cells.set(current_edited)
            except (SilentException, SilentCancelOutputException):
                raise
            except Exception as e:
                print(f"Warning: Could not track edited cell: {e}")

            save_log_to_file(updated_log, modifications_log_path)
            if not is_lazy_loading():
                updated_df.to_json(data_dir / "data_state.json", orient="records", indent=2, default_handler=str)
            else:
                _table_reload_trigger.set(_table_reload_trigger.get() + 1)
            col_label = f"{col} → {target_col}" if target_col != col else col
            ui.notification_show(f"Updated Row {row + 1}, {col_label}", type="message", duration=2)

    @reactive.Effect
    @reactive.event(input.cell_reset)
    def _handle_cell_reset():
        if not _require_editor("Reset"):
            return
        reset_data = input.cell_reset()
        print(f"DEBUG: cell_reset received: {reset_data}")
        if not reset_data:
            return
        row = reset_data.get("row")
        col = reset_data.get("col")
        original_value = reset_data.get("originalValue", "")
        current_value = reset_data.get("oldValue", "")
        if row is None or not col:
            return

        current_df = data.get()
        current_log = mods_log.get()

        target_col = col
        for mapping in (app_config.edit_assignment or []):
            if isinstance(mapping, dict) and mapping.get('source') == col:
                target_col = mapping['target']
                break

        updated_df, updated_log = perform_cell_edit(
            current_df, current_log, row, target_col,
            current_value, original_value, config_instance=config
        )
        data.set(updated_df)
        mods_log.set(updated_log)

        pk_cols = app_config.table.primary_key
        try:
            row_data = current_df.iloc[row]
            row_pk = {pk: row_data[pk] for pk in pk_cols if pk in current_df.columns}
            pk_tuple = tuple(sorted((k, str(v)) for k, v in row_pk.items()))
            current_edited = edited_cells.get().copy()
            cell_key = (pk_tuple, target_col)
            if cell_key in current_edited:
                del current_edited[cell_key]
            edited_cells.set(current_edited)
        except (SilentException, SilentCancelOutputException):
            raise
        except Exception as e:
            print(f"Warning: Could not clear edited cell tracking: {e}")

        save_log_to_file(updated_log, modifications_log_path)
        updated_df.to_json(data_dir / "data_state.json", orient="records", indent=2, default_handler=str)
        ui.notification_show(f"Reset Row {row + 1}, {col} to original value", type="message", duration=2)

    @reactive.Effect
    @reactive.event(input.save_btn)
    def _save_modifications():
        if not _require_editor("Saving"):
            return
        message = save_modifications_to_file(
            data.get(), mods_log.get(),
            modifications_log_path, data_dir / "data_state.json"
        )
        ui.notification_show(message, type="message", duration=3)

    @reactive.Effect
    @reactive.event(input.export_status_btn)
    def _export_status_report():
        summary_data, status_counts = _get_modification_summary()
        message = export_status_report(summary_data, status_counts, data_dir / "modification_status_report.csv")
        ui.notification_show(message, type="message", duration=5)

    @reactive.Effect
    @reactive.event(input.reload_btn)
    def _reload_data():
        if is_lazy_loading():
            config.data_fetcher.refresh_count()
            total_rows.set(config.data_fetcher.total_count)
        else:
            fresh_data = load_data_from_source()
            data.set(fresh_data)
        mods_log.set(load_modifications_log())
        ui.notification_show("Data reloaded from database.", type="message", duration=3)

    # ── Approve / Reject ────────────────────────────────────────────────

    @reactive.Effect
    @reactive.event(input.approve_btn)
    def _approve_data():
        if not _require_editor("Approval"):
            return
        current_df, selected_indices = _get_page_selection()
        if not selected_indices:
            ui.notification_show("Please select rows to approve", type="warning", duration=3)
            return

        selected_pks = _get_selected_pks(selected_indices, current_df)
        print(f"DEBUG: Approve - selected indices: {selected_indices}, PKs: {selected_pks}")

        log = mods_log.get().copy()
        log.append(create_approval_entry(selected_pks, len(current_df), len(log)))
        save_log_to_file(log, modifications_log_path)

        if app_config.database.enabled:
            row_data_map = {}
            if app_config.approval_assignment:
                pk_cols = app_config.table.primary_key
                for idx in selected_indices:
                    try:
                        row = current_df.loc[idx]
                        pk = {pk_col: row[pk_col] for pk_col in pk_cols if pk_col in current_df.columns}
                        pk_key = tuple(sorted(pk.items()))
                        row_data_map[pk_key] = row
                    except (SilentException, SilentCancelOutputException):
                        raise
                    except Exception:
                        pass
            _save_status_to_db(selected_pks, "approval", row_data_map)

        internal_key = "approved"
        status_value = app_config.status_values.get(internal_key, internal_key)
        if not is_lazy_loading():
            full_df = data.get().copy()
            status_col = getattr(app_config.database, "status_column", None)
            for idx in selected_indices:
                if status_col and status_col in full_df.columns:
                    full_df.at[idx, status_col] = status_value
                if "_mod_status" in full_df.columns:
                    full_df.at[idx, "_mod_status"] = internal_key
            data.set(full_df)

        mods_log.set(log)
        with reactive.isolate():
            _table_reload_trigger.set(_table_reload_trigger.get() + 1)
        ui.notification_show(f"{len(selected_pks)} row(s) APPROVED!", type="message", duration=2)

    @reactive.Effect
    @reactive.event(input.reject_btn)
    def _reject_data():
        if not _require_editor("Rejection"):
            return
        current_df, selected_indices = _get_page_selection()
        if not selected_indices:
            ui.notification_show("Please select rows to reject", type="warning", duration=3)
            return

        selected_pks = _get_selected_pks(selected_indices, current_df)
        print(f"DEBUG: Reject - selected indices: {selected_indices}, PKs: {selected_pks}")

        log = mods_log.get().copy()
        log.append(create_rejection_entry(selected_pks, len(current_df), len(log)))
        save_log_to_file(log, modifications_log_path)

        if app_config.database.enabled:
            _save_status_to_db(selected_pks, "rejection")

        internal_key = "rejected"
        status_value = app_config.status_values.get(internal_key, internal_key)
        if not is_lazy_loading():
            full_df = data.get().copy()
            status_col = getattr(app_config.database, "status_column", None)
            for idx in selected_indices:
                if status_col and status_col in full_df.columns:
                    full_df.at[idx, status_col] = status_value
                if "_mod_status" in full_df.columns:
                    full_df.at[idx, "_mod_status"] = internal_key
            data.set(full_df)

        mods_log.set(log)
        with reactive.isolate():
            _table_reload_trigger.set(_table_reload_trigger.get() + 1)
        ui.notification_show(f"{len(selected_pks)} row(s) REJECTED!", type="message", duration=2)

    @reactive.Effect
    @reactive.event(input.clear_approval_btn)
    def _clear_approval():
        approval_status.set(None)
        approval_timestamp.set(None)
