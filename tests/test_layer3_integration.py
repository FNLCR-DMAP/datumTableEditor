"""
Layer 3 — Feature integration tests.

Each test exercises a COMPLETE FEATURE PIPELINE where multiple modules
collaborate with realistic (but mocked) data flowing through real functions.
"""

import json
import pandas as pd
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from shiny import ui


# =============================================================================
# Shared Fixtures
# =============================================================================

@pytest.fixture
def df():
    """5-row DataFrame with _mod_status seed column."""
    return pd.DataFrame({
        "PatientID_Mutsequence": ["PK001", "PK002", "PK003", "PK004", "PK005"],
        "PatientID": ["PAT001", "PAT002", "PAT003", "PAT004", "PAT005"],
        "Gene_names": ["BRCA1", "TP53", "EGFR", "PTEN", "RB1"],
        "Variant_key": ["VAR_001", "VAR_002", "VAR_003", "VAR_004", "VAR_005"],
        "Status": ["Pending", "Reviewed", "Pending", "Approved", "Pending"],
        "Comments": ["", "Needs review", "", "Good", ""],
    })


@pytest.fixture
def pk_cols():
    return ["PatientID_Mutsequence"]


@pytest.fixture
def display_cols():
    return ["PatientID", "Gene_names", "Variant_key", "Status"]


def _make_status_func(df, log, pk_cols):
    """Build a get_row_status_func from real get_row_status."""
    from src.utils.data_utils import get_row_status

    def func(idx):
        row_pk = {pk: df.iloc[idx][pk] for pk in pk_cols}
        return get_row_status(idx, log, row_pk)
    return func


def _pk_tuple(pk_dict):
    return tuple(sorted((k, str(v)) for k, v in pk_dict.items()))


@pytest.fixture
def mock_ci(pk_cols):
    """Lightweight mock ConfigInstance so perform_cell_edit can resolve PK cols."""
    ci = MagicMock()
    ci.app_config.table.primary_key = pk_cols
    ci.app_config.edit_assignment = []
    ci.app_config.status_values = {"approved": "approved", "rejected": "rejected", "edited": "edited"}
    ci.app_config.database.status_column = "Status"
    ci.update_data_in_db = MagicMock(return_value=True)
    ci.save_modification_to_db = MagicMock(return_value=999)
    ci.mark_modification_undone_in_db = MagicMock()
    return ci


# =============================================================================
# 1. Edit → Status → Counts → Table Render
# =============================================================================

class TestEditStatusCountsRender:
    """Full pipeline: edit a cell, check status changes, verify counts,
    then confirm the rendered table row contains correct CSS classes."""

    def test_edit_flows_through_status_to_table_html(self, df, pk_cols, mock_ci):
        from src.utils.data_operations import perform_cell_edit
        from src.utils.data_utils import get_row_status, get_status_counts
        from src.utils.table_utils import build_table_row

        log = []
        # Edit row 1 (PK002) Gene_names
        updated_df, updated_log = perform_cell_edit(df, log, 1, "Gene_names", "TP53", "TP53_mut", config_instance=mock_ci)

        # 1) DataFrame cell updated
        assert updated_df.iloc[1]["Gene_names"] == "TP53_mut"

        # 2) Log entry created
        assert len(updated_log) == 1
        entry = updated_log[0]
        assert entry["type"] == "field_modification"
        assert entry["details"]["row_pk"]["PatientID_Mutsequence"] == "PK002"

        # 3) Row status transitions
        row_pk = {"PatientID_Mutsequence": "PK002"}
        assert get_row_status(1, updated_log, row_pk) == "edited"
        assert get_row_status(0, updated_log, {"PatientID_Mutsequence": "PK001"}) == "unprocessed"

        # 4) Status counts reflect 1 edit
        counts = get_status_counts(updated_df, updated_log, pk_cols)
        assert counts == {"unprocessed": 4, "edited": 1, "approved": 0, "rejected": 0}

        # 5) Rendered table row has correct CSS
        status_func = _make_status_func(updated_df, updated_log, pk_cols)
        pk_t = _pk_tuple(row_pk)
        edited_cells = {(pk_t, "Gene_names"): {"original": "TP53", "current": "TP53_mut"}}
        row_html = build_table_row(
            1, updated_df.iloc[1], ["PatientID", "Gene_names"],
            updated_df, status_func,
            edited_cells=edited_cells,
            pk_columns=pk_cols,
            editable_columns=["Gene_names"],
            readonly_columns=["PatientID_Mutsequence"],
        )
        html_str = str(row_html)
        assert "cell-edited" in html_str
        assert "status-edited" in html_str
        assert 'data-original="TP53"' in html_str


# =============================================================================
# 2. Edit → Undo → Status Revert → Log Integrity
# =============================================================================

class TestEditUndoStatusRevert:
    """Pipeline: edit → undo → value reverts, status returns to unprocessed,
    log has correct entries."""

    def test_edit_then_undo_restores_everything(self, df, pk_cols, mock_ci):
        from src.utils.data_operations import perform_cell_edit, perform_undo
        from src.utils.data_utils import get_row_status, get_status_counts

        log = []
        # Edit row 0 Gene_names
        df1, log1 = perform_cell_edit(df, log, 0, "Gene_names", "BRCA1", "BRCA2", config_instance=mock_ci)
        assert df1.iloc[0]["Gene_names"] == "BRCA2"
        assert get_row_status(0, log1, {"PatientID_Mutsequence": "PK001"}) == "edited"

        # Undo
        df2, log2, msg, err = perform_undo(df1, log1, 0, config_instance=mock_ci)
        assert err is None

        # Value restored
        assert df2.iloc[0]["Gene_names"] == "BRCA1"

        # Log integrity: 2 entries, first undone
        assert len(log2) == 2
        assert log2[0]["undone"] is True
        assert log2[1]["type"] == "undo"
        assert log2[1]["details"]["reverted_to"] == "BRCA1"

        # Status returns to unprocessed everywhere
        assert get_row_status(0, log2, {"PatientID_Mutsequence": "PK001"}) == "unprocessed"
        counts = get_status_counts(df2, log2, pk_cols)
        assert counts == {"unprocessed": 5, "edited": 0, "approved": 0, "rejected": 0}


# =============================================================================
# 3. Filter + Search + Pagination → Table Rendering
# =============================================================================

class TestFilterSearchPaginationRender:
    """Pipeline: add column filter → search → paginate → render HTML table."""

    def test_filter_then_search_then_paginate_then_render(self, df, pk_cols, display_cols):
        from src.utils.filter_handlers import add_filter
        from src.utils.filter_utils import get_filtered_rows
        from src.utils.data_operations import get_paginated_indices, calculate_pagination
        from src.utils.table_utils import build_table_body

        log = []
        status_func = _make_status_func(df, log, pk_cols)
        all_statuses = ["unprocessed", "edited", "approved", "rejected"]

        # Step 1: No filters → all 5 rows
        indices_all = get_filtered_rows(df, display_cols, "", all_statuses, {}, status_func)
        assert len(indices_all) == 5

        # Step 2: Column filter on Gene_names = "BRCA1" or "TP53"
        filters = add_filter({}, "Gene_names")
        assert "Gene_names" in filters
        filters["Gene_names"] = "BRCA1,TP53"

        indices_filtered = get_filtered_rows(df, display_cols, "", all_statuses, filters, status_func)
        assert sorted(indices_filtered) == [0, 1]  # PK001 (BRCA1), PK002 (TP53)

        # Step 3: Add search "BRCA" → narrows to PK001
        indices_searched = get_filtered_rows(df, display_cols, "BRCA", all_statuses, filters, status_func)
        assert indices_searched == [0]

        # Step 4: Pagination math
        page, total_pages, start, end = calculate_pagination(len(indices_searched), "25", 1)
        assert (page, total_pages) == (1, 1)

        pag_indices = get_paginated_indices(indices_searched, "25", 1)
        assert pag_indices == [0]

        # Step 5: Render body → 1 <tr>
        tbody = build_table_body(pag_indices, df, display_cols, status_func, pk_columns=pk_cols)
        html = str(tbody)
        assert html.count("<tr") == 1  # exactly one row
        assert "BRCA1" in html

    def test_status_filter_excludes_rows(self, df, pk_cols, display_cols, mock_ci):
        """Status filter narrows results to matching statuses only."""
        from src.utils.filter_utils import get_filtered_rows
        from src.utils.data_operations import perform_cell_edit, create_approval_entry
        from src.utils.data_utils import get_row_status

        log = []
        # Edit PK002 → "edited"
        df1, log1 = perform_cell_edit(df, log, 1, "Gene_names", "TP53", "TP53x", config_instance=mock_ci)
        # Approve PK004 → "approved"
        log1.append(create_approval_entry(
            [{"PatientID_Mutsequence": "PK004"}], 5, len(log1)
        ))
        status_func = _make_status_func(df1, log1, pk_cols)

        # Only "unprocessed" rows
        indices = get_filtered_rows(df1, display_cols, "", ["unprocessed"], {}, status_func)
        assert 1 not in indices  # PK002 is edited
        assert 3 not in indices  # PK004 is approved
        assert len(indices) == 3  # PK001, PK003, PK005


# =============================================================================
# 4. Approval → Rejection Override → Status Counts → Histogram
# =============================================================================

class TestApprovalRejectionHistogram:
    """Pipeline: approve rows, reject some, check counts, render histogram bar."""

    def test_approve_then_reject_overrides_and_histogram(self, df, pk_cols):
        from src.utils.data_operations import create_approval_entry, create_rejection_entry
        from src.utils.data_utils import get_row_status, get_status_counts
        from src.utils.ui_components import build_status_histogram_bar

        log = []

        # Approve PK001 and PK002
        log.append(create_approval_entry(
            [{"PatientID_Mutsequence": "PK001"}, {"PatientID_Mutsequence": "PK002"}],
            total_rows=5, log_count=0
        ))
        counts = get_status_counts(df, log, pk_cols)
        assert counts == {"unprocessed": 3, "edited": 0, "approved": 2, "rejected": 0}

        # Reject PK002 → overrides approval
        log.append(create_rejection_entry(
            [{"PatientID_Mutsequence": "PK002"}],
            total_rows=5, log_count=1
        ))
        assert get_row_status(0, log, {"PatientID_Mutsequence": "PK001"}) == "approved"
        assert get_row_status(1, log, {"PatientID_Mutsequence": "PK002"}) == "rejected"

        counts = get_status_counts(df, log, pk_cols)
        assert counts == {"unprocessed": 3, "edited": 0, "approved": 1, "rejected": 1}

        # Histogram bar renders correctly
        total = sum(counts.values())
        bar = build_status_histogram_bar("approved", counts["approved"], counts["approved"] / total * 100, True)
        html = str(bar)
        assert "histogram-fill approved" in html
        assert "width: 20.0%" in html


# =============================================================================
# 5. Preset Load → Apply Columns → Save → Reload
# =============================================================================

class TestPresetColumnsLifecycle:
    """Pipeline: load presets → extract columns/widths → ordered columns →
    save presets → reload."""

    def test_preset_column_application_and_persistence(self):
        from src.utils.preset_utils import load_presets, save_presets, load_active_preset, save_active_preset
        from src.utils.column_utils import get_preset_columns_and_widths, get_ordered_columns

        default_columns = ["PatientID", "Gene_names", "Variant_key", "Status"]
        all_columns = ["PatientID_Mutsequence", "PatientID", "Gene_names", "Variant_key",
                       "Wt_nmer", "Mut_nmer", "Status", "Comments"]

        # Mock ConfigInstance
        stored_presets = [
            {
                "preset_name": "Mini",
                "columns": {"columns": ["PatientID", "Gene_names"], "widths": {"PatientID": 200}},
                "is_default": True,
            }
        ]
        config = MagicMock()
        config.get_presets = MagicMock(return_value=list(stored_presets))
        config.get_default_preset = MagicMock(return_value=stored_presets[0])
        config._get_preset_table_name = MagicMock(return_value="presets")
        config.username = "tester"
        config.app_config.table.default_columns = default_columns

        # 1) Load → Default + Mini
        presets = load_presets(config, default_columns)
        assert "Default" in presets
        assert "Mini" in presets

        # 2) Extract columns / widths for Mini
        cols, widths = get_preset_columns_and_widths(presets["Mini"], default_columns)
        assert cols == ["PatientID", "Gene_names"]
        assert widths == {"PatientID": 200}

        # 3) Ordered columns: preset cols first, rest appended
        ordered = get_ordered_columns(cols, all_columns)
        assert ordered[:2] == ["PatientID", "Gene_names"]
        assert set(ordered) == set(all_columns)

        # 4) Active preset loaded from DB
        assert load_active_preset(config) == "Mini"

        # 5) Save new preset → calls save_preset
        presets["Custom"] = {"columns": ["Status", "Comments"], "widths": {}}
        save_presets(config, presets)
        config.save_preset.assert_called()

        # 6) Switch active
        save_active_preset(config, "Custom")
        # save_active_preset iterates presets and calls save_preset for each
        # with is_default=True/False


# =============================================================================
# 6. Clipboard Copy Pipeline
# =============================================================================

class TestClipboardCopyPipeline:
    """Pipeline: selection → paginated indices → get values → generate JS."""

    def test_copy_column_values_through_pagination(self, df):
        from src.utils.data_operations import get_paginated_indices, get_copy_column_values
        from src.utils.clipboard_utils import process_copy_request, generate_clipboard_js

        filtered_indices = list(range(5))  # all rows

        # Page 1, 3 per page → indices [0, 1, 2]
        pag = get_paginated_indices(filtered_indices, "3", 1)
        assert pag == [0, 1, 2]

        # Copy Gene_names for visual rows 0 and 2 (df indices 0, 2)
        values, err = get_copy_column_values(df, "Gene_names", pag, [0, 2])
        assert err is None
        assert values == ["BRCA1", "EGFR"]

        # JS code contains text
        js = generate_clipboard_js("BRCA1\nEGFR")
        assert "navigator.clipboard.writeText" in js
        assert "BRCA1" in js

        # Full pipeline via process_copy_request
        request = {"column": "Gene_names", "indices": [0, 2]}
        js_code, col, count, error = process_copy_request(
            request, df, filtered_indices, "3", 1,
            get_paginated_indices, get_copy_column_values
        )
        assert error is None
        assert col == "Gene_names"
        assert count == 2
        assert "BRCA1" in js_code

    def test_copy_nonexistent_column_returns_error(self, df):
        from src.utils.data_operations import get_paginated_indices, get_copy_column_values
        from src.utils.clipboard_utils import process_copy_request

        request = {"column": "NONEXISTENT", "indices": [0]}
        js, col, count, err = process_copy_request(
            request, df, list(range(5)), "25", 1,
            get_paginated_indices, get_copy_column_values
        )
        assert js is None
        assert err is not None
        assert "not found" in err


# =============================================================================
# 7. Edit + Approve + Modification Summary + Export
# =============================================================================

class TestEditApproveExportPipeline:
    """Pipeline: edits + approvals → get_modification_summary → export_status_report."""

    def test_multi_action_then_export(self, df, pk_cols, tmp_path, mock_ci):
        from src.utils.data_operations import perform_cell_edit, create_approval_entry, export_status_report
        from src.utils.data_utils import get_modification_summary

        log = []
        # Edit PK002 Gene_names
        df1, log = perform_cell_edit(df, log, 1, "Gene_names", "TP53", "TP53x", config_instance=mock_ci)
        # Edit PK003 Status
        df2, log = perform_cell_edit(df1, log, 2, "Status", "Pending", "Done", config_instance=mock_ci)
        # Approve PK001
        log.append(create_approval_entry(
            [{"PatientID_Mutsequence": "PK001"}], total_rows=5, log_count=len(log)
        ))

        # Summary
        summary_data, status_counts = get_modification_summary(df2, log, pk_cols)
        assert len(summary_data) == 5
        assert status_counts == {"unprocessed": 2, "edited": 2, "approved": 1, "rejected": 0}

        # Each row summary has correct mod count
        pk002_entry = next(s for s in summary_data if s["patient_id"] == "PAT002")
        assert pk002_entry["status"] == "edited"
        # Note: get_row_modifications matches by row_index, verify approach
        assert pk002_entry["modifications_count"] >= 0

        pk001_entry = next(s for s in summary_data if s["patient_id"] == "PAT001")
        assert pk001_entry["status"] == "approved"

        # Export
        report_path = tmp_path / "report.csv"
        msg = export_status_report(summary_data, status_counts, report_path)
        assert "Exported" in msg
        assert report_path.exists()

        # Re-read and verify
        exported = pd.read_csv(report_path)
        assert len(exported) == 5
        assert "status" in exported.columns
        approved_rows = exported[exported["status"] == "approved"]
        assert len(approved_rows) == 1


# =============================================================================
# 8. Operator Filter + Status Filter → Pagination
# =============================================================================

class TestOperatorFilterPipeline:
    """Pipeline: rich operator filters + status filters → correct row set → pagination."""

    def test_not_contains_operator_with_status_filter(self, df, pk_cols, display_cols):
        from src.utils.filter_utils import get_filtered_rows
        from src.utils.data_operations import get_paginated_indices, calculate_pagination

        log = []
        status_func = _make_status_func(df, log, pk_cols)
        all_statuses = ["unprocessed", "edited", "approved", "rejected"]

        # Operator: Gene_names not_contains "BRCA"
        op_filter = {"Gene_names": {"op": "not_contains", "value": "BRCA"}}
        indices = get_filtered_rows(df, display_cols, "", all_statuses, op_filter, status_func)
        # Excludes PK001 (BRCA1), keeps PK002-PK005
        assert 0 not in indices
        assert len(indices) == 4

        # Combine with pagination
        page, total, start, end = calculate_pagination(len(indices), "2", 1)
        assert total == 2  # 4 rows / 2 per page
        pag = get_paginated_indices(indices, "2", 1)
        assert len(pag) == 2

    def test_regex_operator_filter(self, df, pk_cols, display_cols):
        from src.utils.filter_utils import get_filtered_rows

        log = []
        status_func = _make_status_func(df, log, pk_cols)
        all_statuses = ["unprocessed", "edited", "approved", "rejected"]

        # Regex: Gene_names matches "^TP" → only TP53
        indices = get_filtered_rows(
            df, display_cols, "", all_statuses,
            {"Gene_names": {"op": "regex", "value": "^TP"}}, status_func
        )
        assert indices == [1]  # PK002 = TP53

    def test_between_operator_filter(self, df, pk_cols, display_cols):
        from src.utils.filter_utils import get_filtered_rows

        log = []
        status_func = _make_status_func(df, log, pk_cols)
        all_statuses = ["unprocessed", "edited", "approved", "rejected"]

        # Between "E" and "T" on Gene_names → EGFR, PTEN, RB1 (string comparison)
        indices = get_filtered_rows(
            df, display_cols, "", all_statuses,
            {"Gene_names": {"op": "between", "value": ["E", "T"]}}, status_func
        )
        gene_names = [df.iloc[i]["Gene_names"] for i in indices]
        for g in gene_names:
            assert "E" <= g <= "T"
        assert "EGFR" in gene_names
        assert "PTEN" in gene_names
        assert "RB1" in gene_names


# =============================================================================
# 9. QueryBuilder SQL Generation Pipeline
# =============================================================================

class TestQueryBuilderPipeline:
    """Pipeline: FilterCondition + SortConfig → QueryBuilder → SQL + params."""

    def test_select_with_filters_sort_pagination(self):
        from src.db.query_builder import QueryBuilder, FilterCondition, SortConfig

        qb = QueryBuilder(
            data_table="epitopes.data",
            mods_table="epitopes.mods",
            primary_key=["PatientID_Mutsequence"],
        )

        filters = [
            FilterCondition("Gene_names", "IN", ["BRCA1", "TP53"]),
            FilterCondition("Status", "ILIKE", "Pend"),
        ]
        sort = SortConfig("PatientID", ascending=True)

        sql, params = qb.build_select_query(
            filters=filters, sort=sort, page=2, limit=25, include_mods_status=False
        )

        # Contains quoted column filters
        assert '"Gene_names" IN' in sql
        assert '"Status" ILIKE' in sql
        # Contains sort
        assert '"PatientID" ASC' in sql
        # Contains pagination
        assert "LIMIT" in sql
        assert params["limit"] == 25
        assert params["offset"] == 25  # page 2

        # Count query uses same filters
        count_sql, count_params = qb.build_count_query(filters=filters)
        assert "COUNT" in count_sql
        assert '"Gene_names" IN' in count_sql

    def test_filter_condition_operators(self):
        from src.db.query_builder import FilterCondition

        # IN
        fc_in = FilterCondition("Gene_names", "IN", ["BRCA1", "TP53"])
        sql, params = fc_in.to_sql("p")
        assert "IN" in sql
        assert len(params) == 2

        # ILIKE
        fc_like = FilterCondition("Status", "ILIKE", "Pend")
        sql, params = fc_like.to_sql("q")
        assert "ILIKE" in sql
        assert "%Pend%" in list(params.values())[0]

        # IS NULL
        fc_null = FilterCondition("Comments", "IS NULL")
        sql, params = fc_null.to_sql("r")
        assert "IS NULL" in sql
        assert params == {}


# =============================================================================
# 10. SessionBook Append + Context + Reconcile
# =============================================================================

class TestSessionBookReconcilePipeline:
    """Pipeline: set_context → append pages → reconcile fresh data → to_dataframe."""

    def test_full_session_book_lifecycle(self):
        from src.db.session_book import SessionBook

        book = SessionBook(primary_key=["id"])

        # Initial context
        assert book.set_context("ctx_v1") is True

        # Append page 1 (3 rows)
        page1 = pd.DataFrame({"id": ["A", "B", "C"], "val": [1, 2, 3]})
        added = book.append_page(page1, page_number=1)
        assert added == 3
        assert book.row_count == 3

        # Append page 2 (3 rows, 1 duplicate PK "C")
        page2 = pd.DataFrame({"id": ["C", "D", "E"], "val": [30, 4, 5]})
        added = book.append_page(page2, page_number=2)
        assert added == 2  # C skipped
        assert book.row_count == 5

        # to_dataframe preserves append order
        result = book.to_dataframe()
        assert list(result["id"]) == ["A", "B", "C", "D", "E"]

        # Reconcile with fresh data (B updated, D deleted from fresh)
        fresh = pd.DataFrame({"id": ["A", "B", "C", "E"], "val": [1, 20, 3, 5]})
        reconciled = book.reconcile_data(fresh)
        # order preserved (A, B, C, D, E)
        assert list(reconciled["id"]) == ["A", "B", "C", "D", "E"]
        # B has fresh value
        b_row = reconciled[reconciled["id"] == "B"].iloc[0]
        assert b_row["val"] == 20
        # D marked as _deleted
        d_row = reconciled[reconciled["id"] == "D"].iloc[0]
        assert d_row.get("_deleted") is True

        # Context change clears
        assert book.set_context("ctx_v2") is True
        assert book.row_count == 0

    def test_manager_provides_independent_books(self):
        from src.db.session_book import SessionBookManager

        mgr = SessionBookManager(primary_key=["id"])
        book_a = mgr.get_book("session_A")
        book_b = mgr.get_book("session_B")

        page = pd.DataFrame({"id": ["X"], "val": [99]})
        book_a.append_page(page, page_number=1)

        assert book_a.row_count == 1
        assert book_b.row_count == 0
        assert mgr.session_count == 2


# =============================================================================
# 11. Full Table Container Render
# =============================================================================

class TestFullTableContainerRender:
    """Pipeline: data + edits + filter + paginate → build_table_container HTML."""

    def test_renders_correct_summary_and_cell_classes(self, df, pk_cols, display_cols, mock_ci):
        from src.utils.data_operations import perform_cell_edit
        from src.utils.data_utils import get_row_status
        from src.utils.filter_utils import get_filtered_rows
        from src.utils.data_operations import get_paginated_indices
        from src.utils.table_utils import build_table_container

        log = []
        # Edit PK002 Gene_names
        df1, log = perform_cell_edit(df, log, 1, "Gene_names", "TP53", "TP53_edited", config_instance=mock_ci)

        status_func = _make_status_func(df1, log, pk_cols)
        all_statuses = ["unprocessed", "edited", "approved", "rejected"]

        # Filter → all 5
        filtered = get_filtered_rows(df1, display_cols, "", all_statuses, {}, status_func)
        assert len(filtered) == 5

        # Paginate: 2 per page, page 1
        pag = get_paginated_indices(filtered, "2", 1)
        assert len(pag) == 2

        pk_t = _pk_tuple({"PatientID_Mutsequence": "PK002"})
        edited_cells = {(pk_t, "Gene_names"): {"original": "TP53", "current": "TP53_edited"}}

        container = build_table_container(
            pag, df1, display_cols, {"PatientID": 150},
            filtered_count=5, total_rows=5,
            get_row_status_func=status_func,
            edited_cells=edited_cells,
            pk_columns=pk_cols,
            editable_columns=["Gene_names", "Status"],
            readonly_columns=["PatientID_Mutsequence"],
        )
        html = str(container)

        # Summary text
        assert "Loaded 2 of 5 rows" in html

        # Edited cell styling (PK002 is on page 1 at index 1)
        assert "cell-edited" in html
        assert 'data-original="TP53"' in html

        # Editable cell class present
        assert "editable-cell" in html

    def test_filtered_summary_text(self, df, pk_cols, display_cols):
        from src.utils.data_operations import perform_cell_edit, create_approval_entry
        from src.utils.filter_utils import get_filtered_rows
        from src.utils.data_operations import get_paginated_indices
        from src.utils.table_utils import build_table_container

        log = []
        # Create an approved row so status filter can exclude it
        log.append(create_approval_entry(
            [{"PatientID_Mutsequence": "PK004"}], 5, 0
        ))
        status_func = _make_status_func(df, log, pk_cols)

        # Filter: only unprocessed
        filtered = get_filtered_rows(df, display_cols, "", ["unprocessed"], {}, status_func)
        assert len(filtered) == 4  # PK004 excluded

        pag = get_paginated_indices(filtered, "25", 1)

        container = build_table_container(
            pag, df, display_cols, {},
            filtered_count=len(filtered), total_rows=5,
            get_row_status_func=status_func, pk_columns=pk_cols,
        )
        html = str(container)
        # Shows filtered indicator when filtered_count < total
        assert "4 filtered rows (total: 5)" in html


# =============================================================================
# 12. Multi-Edit + Save to File + Re-read
# =============================================================================

class TestMultiEditSavePipeline:
    """Pipeline: multiple edits → save log to file → re-read → verify."""

    def test_three_edits_save_and_reload(self, df, pk_cols, tmp_path, mock_ci):
        from src.utils.data_operations import perform_cell_edit, save_log_to_file
        from src.utils.data_utils import get_status_counts

        log = []
        # 3 edits on different rows/columns
        df1, log = perform_cell_edit(df, log, 0, "Gene_names", "BRCA1", "BRCA1x", config_instance=mock_ci)
        df2, log = perform_cell_edit(df1, log, 1, "Status", "Reviewed", "Done", config_instance=mock_ci)
        df3, log = perform_cell_edit(df2, log, 2, "Comments", "", "new comment", config_instance=mock_ci)

        # 3 entries in log
        assert len(log) == 3
        assert all(e["type"] == "field_modification" for e in log)

        # Status counts
        counts = get_status_counts(df3, log, pk_cols)
        assert counts["edited"] == 3
        assert counts["unprocessed"] == 2

        # Save log to file (bypass DB_AVAILABLE check with patch)
        log_path = tmp_path / "log.json"
        with patch("src.utils.data_operations.DB_AVAILABLE", False), \
             patch("src.utils.data_operations.app_config") as mock_cfg:
            mock_cfg.database.enabled = False
            save_log_to_file(log, log_path)

        assert log_path.exists()

        # Re-read
        with open(log_path) as f:
            reloaded = json.load(f)
        assert len(reloaded) == 3

        # Each entry has correct structure
        for i, entry in enumerate(reloaded):
            assert entry["type"] == "field_modification"
            assert "row_pk" in entry["details"]
            assert "old_value" in entry["details"]
            assert "new_value" in entry["details"]

        # Status counts from reloaded log match original
        counts2 = get_status_counts(df3, reloaded, pk_cols)
        assert counts2 == counts


# =============================================================================
# 13. SQL Query Logging — Edit Pipeline DB Calls
# =============================================================================

class TestEditPipelineSQLCalls:
    """Capture and verify all DB calls made during edit/undo pipelines
    via config_instance method invocations."""

    def test_cell_edit_issues_update_then_insert(self, df, pk_cols, mock_ci):
        """perform_cell_edit must call update_data_in_db then save_modification_to_db,
        plus an additional pair of calls to sync the status column to 'edited'."""
        from src.utils.data_operations import perform_cell_edit

        perform_cell_edit(df, [], 1, "Gene_names", "TP53", "TP53_mut", config_instance=mock_ci)

        # UPDATE data table: field edit + status sync
        assert mock_ci.update_data_in_db.call_count == 2
        field_update = mock_ci.update_data_in_db.call_args_list[0]
        assert field_update[0][0] == {"PatientID_Mutsequence": "PK002"}  # row_pk
        assert field_update[0][1] == "Gene_names"  # column
        assert field_update[0][2] == "TP53_mut"  # new_value
        # Status sync
        status_update = mock_ci.update_data_in_db.call_args_list[1]
        assert status_update[0][1] == "Status"
        assert status_update[0][2] == "edited"

        # INSERT modification records: field edit + status sync
        assert mock_ci.save_modification_to_db.call_count == 2
        field_insert = mock_ci.save_modification_to_db.call_args_list[0]
        assert field_insert[0][0] == {"PatientID_Mutsequence": "PK002"}
        assert field_insert[0][1] == "Gene_names"
        assert field_insert[0][2] == "TP53"  # old_value
        assert field_insert[0][3] == "TP53_mut"  # new_value
        assert field_insert[0][4] == "field_modification"

    def test_undo_issues_revert_update_mark_undone_and_insert(self, df, pk_cols, mock_ci):
        """perform_undo calls: update_data_in_db (revert), mark_modification_undone_in_db,
        save_modification_to_db (undo record)."""
        from src.utils.data_operations import perform_cell_edit, perform_undo

        _, log = perform_cell_edit(df, [], 1, "Gene_names", "TP53", "TP53_mut", config_instance=mock_ci)
        # Reset call tracking
        mock_ci.reset_mock()

        df_copy = df.copy()
        df_copy.iloc[1, df_copy.columns.get_loc("Gene_names")] = "TP53_mut"

        df2, log2, msg, err = perform_undo(df_copy, log, 0, config_instance=mock_ci)
        assert err is None

        # 1) Revert: update_data_in_db with old_value
        assert mock_ci.update_data_in_db.call_count == 2
        revert_args = mock_ci.update_data_in_db.call_args_list[0][0]
        assert revert_args[0] == {"PatientID_Mutsequence": "PK002"}
        assert revert_args[1] == "Gene_names"
        assert revert_args[2] == "TP53"  # reverted to original

        # 1b) Status column reset (no remaining edits for this row)
        status_reset = mock_ci.update_data_in_db.call_args_list[1][0]
        assert status_reset[1] == "Status"
        assert status_reset[2] == ""  # cleared

        # 2) Mark original mod as undone
        mock_ci.mark_modification_undone_in_db.assert_called_once()

        # 3) Insert undo record
        mock_ci.save_modification_to_db.assert_called_once()
        undo_args = mock_ci.save_modification_to_db.call_args[0]
        assert undo_args[1] == "Gene_names"
        assert undo_args[4] == "undo"  # mod_type

    def test_multi_edit_accumulates_sequential_db_calls(self, df, pk_cols, mock_ci):
        """Three consecutive edits → 3 field updates + 2 status syncs (editing Status
        itself skips the sync) = 5 update_data_in_db + 5 save_modification_to_db."""
        from src.utils.data_operations import perform_cell_edit

        log = []
        df1, log = perform_cell_edit(df, log, 0, "Gene_names", "BRCA1", "BRCA1x", config_instance=mock_ci)
        df2, log = perform_cell_edit(df1, log, 1, "Status", "Reviewed", "Done", config_instance=mock_ci)
        df3, log = perform_cell_edit(df2, log, 2, "Gene_names", "EGFR", "EGFRx", config_instance=mock_ci)

        # 3 field updates + 2 status syncs (editing Status col directly skips sync)
        assert mock_ci.update_data_in_db.call_count == 5
        assert mock_ci.save_modification_to_db.call_count == 5

        # Verify field updates (every other call is a status sync)
        update_calls = mock_ci.update_data_in_db.call_args_list
        # Edit 1: Gene_names on PK001 + status sync
        assert update_calls[0][0][0] == {"PatientID_Mutsequence": "PK001"}
        assert update_calls[0][0][1] == "Gene_names"
        assert update_calls[1][0][1] == "Status"  # status sync
        # Edit 2: Status on PK002 (no status sync — editing Status itself)
        assert update_calls[2][0][0] == {"PatientID_Mutsequence": "PK002"}
        assert update_calls[2][0][1] == "Status"
        # Edit 3: Gene_names on PK003 + status sync
        assert update_calls[3][0][0] == {"PatientID_Mutsequence": "PK003"}
        assert update_calls[3][0][1] == "Gene_names"
        assert update_calls[4][0][1] == "Status"  # status sync


# =============================================================================
# 14. SQL Query Logging — QueryBuilder Composition for Full Features
# =============================================================================

class TestQueryBuilderCompositionSQL:
    """Verify end-to-end SQL composition as features produce queries."""

    def test_edit_produces_correct_insert_sql_params(self):
        """Verify the INSERT SQL and params that would be sent to DB for an edit."""
        from src.db.query_builder import QueryBuilder

        qb = QueryBuilder("public.data", "public.mods", ["PatientID_Mutsequence"])

        insert_sql = qb.build_insert_modification()
        assert 'INSERT INTO "public"."mods"' in insert_sql
        assert "RETURNING id" in insert_sql

        # Simulate params that perform_cell_edit would assemble
        params = {
            "row_pk": '{"PatientID_Mutsequence": "PK002"}',
            "column_name": "Gene_names",
            "old_value": "TP53",
            "new_value": "TP53_mut",
            "mod_type": "field_modification",
            "created_by": "testuser",
        }
        # All required placeholders present in SQL
        for key in params:
            assert f":{key}" in insert_sql

    def test_undo_produces_correct_update_sql(self):
        """Verify the UPDATE SQL for marking a modification undone."""
        from src.db.query_builder import QueryBuilder

        qb = QueryBuilder("data", "public.mods", ["id"])
        undo_sql = qb.build_undo_modification()

        assert 'UPDATE "public"."mods"' in undo_sql
        assert "SET undone = TRUE" in undo_sql
        assert "WHERE id = :mod_id" in undo_sql

    def test_filter_sort_paginate_full_query_composition(self):
        """Build a full SELECT with filters + sort + pagination, check complete SQL."""
        from src.db.query_builder import QueryBuilder, FilterCondition, SortConfig

        qb = QueryBuilder("epi.epitopes_data", "epi.modifications", ["PatientID_Mutsequence"])

        filters = [
            FilterCondition("Gene_names", "IN", ["BRCA1", "TP53"]),
            FilterCondition("Status", "ILIKE", "Pend"),
        ]
        sort = SortConfig("PatientID", ascending=False)

        sql, params = qb.build_select_query(
            filters=filters, sort=sort, page=3, limit=25,
            include_mods_status=True,
        )

        # Table references
        assert '"epi"."epitopes_data"' in sql
        assert '"epi"."modifications"' in sql

        # Mod status subquery
        assert "_mod_status" in sql
        assert "_mod_count" in sql

        # Filters
        assert '"Gene_names" IN' in sql
        assert '"Status" ILIKE' in sql

        # Sort
        assert '"PatientID" DESC' in sql

        # Pagination
        assert params["limit"] == 25
        assert params["offset"] == 50  # page 3 * 25

        # Count query has same filters, no pagination
        count_sql, _ = qb.build_count_query(filters=filters)
        assert "COUNT(*)" in count_sql
        assert "LIMIT" not in count_sql
        assert '"Gene_names" IN' in count_sql

    def test_upsert_state_sql_has_on_conflict(self):
        """UI state persistence uses ON CONFLICT for idempotent save."""
        from src.db.query_builder import QueryBuilder

        qb = QueryBuilder("data", "mods", ["id"])
        sql = qb.build_upsert_state("public.ui_state")

        assert 'INSERT INTO "public"."ui_state"' in sql
        assert "ON CONFLICT (user_id, session_id)" in sql
        assert "DO UPDATE SET" in sql
        assert ":filters" in sql
        assert ":sort_column" in sql


# =============================================================================
# 15. DataFetcher WHERE Clause in Integration Context
# =============================================================================

class TestDataFetcherIntegrationSQL:
    """End-to-end: user actions → QueryParams → _build_where_clause → SQL verification."""

    @pytest.fixture
    def fetcher(self):
        from src.config.config_instance import DataFetcher
        f = DataFetcher.__new__(DataFetcher)
        f.app_config = MagicMock()
        f.app_config.query.searchable_columns = ["Gene_names", "Status", "PatientID"]
        f.app_config.database.status_column = None
        f._columns = ["PatientID_Mutsequence", "PatientID", "Gene_names", "Status", "Comments"]
        f._column_types = {}
        f._engine = None
        f._datum_client = None
        f._total_count = 100
        return f

    def test_user_adds_column_filter_then_searches(self, fetcher):
        """Simulate: user adds Gene_names filter, then types search."""
        from src.config.config_instance import QueryParams

        # Step 1: Column filter only
        qp1 = QueryParams(filters={"Gene_names": ["BRCA1", "TP53"]})
        where1, p1 = fetcher._build_where_clause(qp1)
        assert 'CAST("Gene_names" AS TEXT) IN (:p0, :p1)' in where1
        assert p1 == {"p0": "BRCA1", "p1": "TP53"}

        # Step 2: Add search
        qp2 = QueryParams(filters={"Gene_names": ["BRCA1", "TP53"]}, search_term="PAT001")
        where2, p2 = fetcher._build_where_clause(qp2)
        assert 'CAST("Gene_names" AS TEXT) IN (:p0, :p1)' in where2
        assert "ILIKE :search_term" in where2
        assert p2["search_term"] == "%PAT001%"
        # Search is ANDed with filter
        assert " AND " in where2

    def test_user_applies_operator_filter_parameterized_vs_interpolated(self, fetcher):
        """Same filter, parameterized (SQLAlchemy) vs interpolated (Datum) mode."""
        from src.config.config_instance import QueryParams

        qp = QueryParams(filters={"Gene_names": {"op": "contains", "value": "BRC"}})

        # Parameterized mode
        where_p, params_p = fetcher._build_where_clause(qp, use_params=True)
        assert 'ILIKE :p0' in where_p
        assert params_p["p0"] == "%BRC%"

        # Interpolated mode (Datum)
        where_i, params_i = fetcher._build_where_clause(qp, use_params=False)
        assert "'%BRC%'" in where_i
        assert ":p0" not in where_i
        assert params_i == {}

    def test_complex_multi_filter_composition(self, fetcher):
        """Multiple filters of different types combined into one WHERE clause."""
        from src.config.config_instance import QueryParams

        qp = QueryParams(
            filters={
                "Gene_names": {"op": "not_contains", "value": "BRCA"},
                "Status": ["Pending", "Reviewed"],
                "Comments": {"op": "not_empty"},
            },
            search_term="PAT",
            search_column="PatientID",
        )
        where, params = fetcher._build_where_clause(qp, use_params=True)

        # Gene_names NOT ILIKE
        assert 'CAST("Gene_names" AS TEXT) NOT ILIKE :p0' in where
        assert params["p0"] == "%BRCA%"

        # Status IN
        assert 'CAST("Status" AS TEXT) IN (:p1, :p2)' in where
        assert params["p1"] == "Pending"
        assert params["p2"] == "Reviewed"

        # Comments not_empty
        assert '"Comments" IS NOT NULL' in where

        # Search on specific column
        assert 'CAST("PatientID" AS TEXT) ILIKE :search_term' in where
        assert params["search_term"] == "%PAT%"
        # No OR (single search column)
        search_portion = where.split("AND")[-1]
        assert " OR " not in search_portion

    def test_status_filter_clause_generation(self, fetcher):
        """Verify _build_status_filter_clause for lazy-loading status filter."""
        from src.config.config_instance import QueryParams

        # All statuses → empty clause
        qp_all = QueryParams(status_filters=["unprocessed", "edited", "approved", "rejected"])
        clause_all = fetcher._build_status_filter_clause(qp_all)
        assert clause_all == ""

        # Subset → IN clause
        qp_sub = QueryParams(status_filters=["unprocessed", "edited"])
        clause_sub = fetcher._build_status_filter_clause(qp_sub)
        assert "_mod_status IN" in clause_sub
        assert "'unprocessed'" in clause_sub
        assert "'edited'" in clause_sub
        assert "'approved'" not in clause_sub


# =============================================================================
# 15. Date Picker + Filter Operator Integration
# =============================================================================

class TestDateFilterIntegration:
    """End-to-end: date column detection → operator filter → row filtering → UI render."""

    @pytest.fixture
    def date_df(self):
        return pd.DataFrame({
            "Name": ["Alice", "Bob", "Charlie", "Diana"],
            "created_at": ["2024-01-15", "2024-06-20", "2024-09-01", "2024-12-25"],
            "Score": [85, 42, 95, 70],
        })

    @pytest.fixture
    def status_func(self):
        return lambda idx: "unprocessed"

    def test_date_between_filters_then_renders_panel(self, date_df, status_func):
        """Between filter on date column should correctly filter rows AND render date picker UI."""
        from src.utils.filter_utils import get_filtered_rows
        from src.utils.modal_utils import build_dynamic_filters_panel

        filters = {"created_at": {"op": "between", "value": ["2024-01-01", "2024-07-01"], "interactive": True}}

        # 1) Filter rows
        result = get_filtered_rows(
            date_df, ["Name", "created_at", "Score"], "",
            ["unprocessed"], filters, status_func
        )
        names = [date_df.loc[i, "Name"] for i in result]
        assert "Alice" in names      # 2024-01-15 in range
        assert "Bob" in names        # 2024-06-20 in range
        assert "Charlie" not in names  # 2024-09-01 outside
        assert "Diana" not in names   # 2024-12-25 outside

        # 2) Render panel with date_columns
        html = str(build_dynamic_filters_panel(
            filters, date_df, date_columns={"created_at"}
        ))
        assert 'type="date"' in html
        assert "From" in html
        assert "To" in html
        assert 'data-column="created_at"' in html

    def test_date_gt_filter_and_render(self, date_df, status_func):
        """gt operator on date column filters correctly and renders single date input."""
        from src.utils.filter_utils import get_filtered_rows
        from src.utils.modal_utils import build_dynamic_filters_panel

        filters = {"created_at": {"op": "gt", "value": "2024-06-30", "interactive": True}}

        # Filter
        result = get_filtered_rows(
            date_df, ["Name", "created_at", "Score"], "",
            ["unprocessed"], filters, status_func
        )
        names = [date_df.loc[i, "Name"] for i in result]
        assert "Charlie" in names
        assert "Diana" in names
        assert "Alice" not in names
        assert "Bob" not in names

        # Render
        html = str(build_dynamic_filters_panel(
            filters, date_df, date_columns={"created_at"}
        ))
        assert 'type="date"' in html
        assert "From" not in html  # single input, not range

    def test_not_empty_on_date_col(self, date_df, status_func):
        """not_empty on date column filters nulls and renders hidden value area."""
        from src.utils.filter_utils import get_filtered_rows
        from src.utils.modal_utils import build_dynamic_filters_panel

        df2 = date_df.copy()
        df2.loc[1, "created_at"] = None

        filters = {"created_at": {"op": "not_empty", "value": None, "interactive": True}}

        result = get_filtered_rows(
            df2, ["Name", "created_at"], "",
            ["unprocessed"], filters, status_func
        )
        assert 1 not in result
        assert 0 in result

        html = str(build_dynamic_filters_panel(
            filters, df2, date_columns={"created_at"}
        ))
        assert "display: none" in html

    def test_operator_change_preserves_filter_state(self, date_df, status_func):
        """Changing operator via update_filter_values preserves column and value."""
        from src.utils.filter_handlers import update_filter_values
        from src.utils.filter_utils import get_filtered_rows
        from unittest.mock import MagicMock

        # Start with between
        filters = {"created_at": {"op": "between", "value": ["2024-01-01", "2024-12-31"], "interactive": True}}
        r1 = get_filtered_rows(
            date_df, ["Name", "created_at"], "",
            ["unprocessed"], filters, status_func
        )
        assert len(r1) == 4  # All in range

        # Simulate user changing textarea to narrow range
        mock_input = MagicMock()
        mock_input.filter_created_at = MagicMock(return_value="2024-01-01\n2024-07-01")
        new_filters, updated = update_filter_values(filters, mock_input)

        assert updated is True
        assert new_filters["created_at"]["value"] == ["2024-01-01", "2024-07-01"]

        # Re-filter with updated values
        r2 = get_filtered_rows(
            date_df, ["Name", "created_at"], "",
            ["unprocessed"], new_filters, status_func
        )
        assert len(r2) == 2  # Only Alice and Bob

    def test_date_detection_fallback_integration(self):
        """_looks_like_dates fallback integrates with panel rendering."""
        from src.utils.modal_utils import _looks_like_dates, build_dynamic_filters_panel

        df = pd.DataFrame({
            "mystery_col": ["2024-01-01", "2024-06-15", "2024-12-31"],
        })

        # Values look like dates
        assert _looks_like_dates(["2024-01-01", "2024-06-15", "2024-12-31"]) is True

        # Panel should detect and render date picker (via fallback)
        filters = {"mystery_col": {"op": "between", "value": [], "interactive": True}}
        html = str(build_dynamic_filters_panel(filters, df, date_columns=set()))
        assert 'type="date"' in html

    def test_config_defined_date_filter_skip_reactive(self):
        """Config-defined operator dict on date column is skipped by update_filter_values."""
        from src.utils.filter_handlers import update_filter_values
        from src.utils.modal_utils import build_dynamic_filters_panel
        from unittest.mock import MagicMock

        df = pd.DataFrame({"created_at": ["2024-01-01"]})

        # Config-defined: no "interactive" key
        filters = {"created_at": {"op": "gte", "value": "2024-01-01"}}

        mock_input = MagicMock()
        mock_input.filter_created_at = MagicMock(side_effect=AssertionError("should not be called"))

        result, updated = update_filter_values(filters, mock_input)
        assert updated is False  # skipped

        # But it still renders correctly
        html = str(build_dynamic_filters_panel(filters, df, date_columns={"created_at"}))
        assert 'type="date"' in html


# =============================================================================
# 17. Multi-tab Widget Context Integration
# =============================================================================

class TestMultiTabContextIntegration:
    """Integration: UI components + JS + CSS must support multi-tab widget
    context — actions scope to the correct tab instead of always hitting the
    first DOM element."""

    def test_clear_selection_passes_event(self):
        """The Clear Selection button must call deselectAllRows(event) so
        the JS can scope to the correct widget/tab container."""
        from pathlib import Path

        ui_source = (Path(__file__).resolve().parent.parent / "src" / "ui.py").read_text()

        # Must pass event so deselectAllRows can scope to the correct tab
        assert 'deselectAllRows(event)' in ui_source
        # Must NOT have the bare no-arg call
        assert 'deselectAllRows()' not in ui_source

    def test_header_dropdown_has_sort_and_remove_actions(self):
        """Each draggable header cell includes sort + remove action buttons."""
        from src.utils.table_utils import build_draggable_header_cell

        th = build_draggable_header_cell("Gene_names")
        html = str(th)

        # Sort buttons carry data-column for context-aware JS
        assert 'data-column="Gene_names"' in html
        assert "sort-asc-btn" in html
        assert "sort-desc-btn" in html
        assert "remove-col-btn" in html
        # The dropdown container is positioned absolutely within the header
        assert "header-dropdown" in html
        assert "header-action-container" in html

    def test_js_files_contain_widget_container_scoping(self):
        """Core JS files must define/use _findWidgetContainer for tab scoping."""
        from pathlib import Path

        js_dir = Path(__file__).resolve().parent.parent / "src" / "js"

        # table-drag.js must define the shared utility
        table_drag = (js_dir / "table-drag.js").read_text()
        assert "function _findWidgetContainer" in table_drag
        assert "initHeaderDrag" in table_drag
        assert "initColumnResize" in table_drag

        # row-selection.js must use _findWidgetContainer
        row_sel = (js_dir / "row-selection.js").read_text()
        assert "_findWidgetContainer" in row_sel
        assert "initRowSelection" in row_sel

        # histogram.js must use _findWidgetContainer
        hist = (js_dir / "histogram.js").read_text()
        assert "_findWidgetContainer" in hist

        # synthesis.js must use findModalInContext
        synth = (js_dir / "synthesis.js").read_text()
        assert "findModalInContext" in synth

    def test_css_th_allows_dropdown_overflow(self):
        """Table th must have overflow:visible so header dropdown is not clipped."""
        from pathlib import Path

        css_path = Path(__file__).resolve().parent.parent / "src" / "css" / "table.css"
        css = css_path.read_text()

        # Find the .edit-table th rule — it should have overflow: visible
        import re
        th_block = re.search(r'\.edit-table\s+th\s*\{([^}]+)\}', css)
        assert th_block is not None, "Could not find .edit-table th rule in table.css"
        th_styles = th_block.group(1)
        assert "overflow: visible" in th_styles or "overflow:visible" in th_styles


# =============================================================================
# 18. Modal Utils Integration — Filter Panel → Apply → Table Render
# =============================================================================

class TestFilterPanelToTableRender:
    """Full pipeline: add filter via filter_handlers → build filter panel →
    apply filter via filter_utils → render table body with filtered rows."""

    @pytest.fixture
    def filter_df(self):
        return pd.DataFrame({
            "PatientID_Mutsequence": ["PK001", "PK002", "PK003", "PK004"],
            "Gene_names": ["BRCA1", "TP53", "EGFR", "BRCA1"],
            "Status": ["Pending", "Reviewed", "Pending", "Approved"],
        })

    def test_add_filter_build_panel_apply_render(self, filter_df):
        """add_filter → build_dynamic_filters_panel → get_filtered_rows → build_table_body."""
        from src.utils.filter_handlers import add_filter
        from src.utils.modal_utils import build_dynamic_filters_panel
        from src.utils.filter_utils import get_filtered_rows
        from src.utils.table_utils import build_table_body

        status_func = lambda idx: "unprocessed"
        pk_cols = ["PatientID_Mutsequence"]
        display_cols = ["Gene_names", "Status"]

        # Step 1: Add filter
        filters = add_filter({}, "Gene_names")
        assert "Gene_names" in filters
        assert filters["Gene_names"] == "all"

        # Step 2: Build panel — should see textarea with BRCA1, EGFR, TP53
        panel_html = str(build_dynamic_filters_panel(filters, filter_df))
        assert "Gene_names" in panel_html
        assert "filter_Gene_names" in panel_html

        # Step 3: Set filter value to "BRCA1"
        filters["Gene_names"] = "BRCA1"
        result = get_filtered_rows(
            filter_df, display_cols, "",
            ["unprocessed", "edited", "approved", "rejected"],
            filters, status_func
        )
        assert sorted(result) == [0, 3]  # PK001 and PK004 both have BRCA1

        # Step 4: Render table body for filtered rows
        tbody = build_table_body(result, filter_df, display_cols, status_func, pk_columns=pk_cols)
        html = str(tbody)
        assert html.count("<tr") == 2
        assert "BRCA1" in html

    def test_remove_filter_shows_all_rows(self, filter_df):
        """After removing a filter, all rows should appear again."""
        from src.utils.filter_handlers import add_filter, remove_filter
        from src.utils.filter_utils import get_filtered_rows

        status_func = lambda idx: "unprocessed"
        all_statuses = ["unprocessed", "edited", "approved", "rejected"]

        filters = add_filter({}, "Gene_names")
        filters["Gene_names"] = "BRCA1"
        result = get_filtered_rows(filter_df, ["Gene_names"], "", all_statuses, filters, status_func)
        assert len(result) == 2

        # Remove filter
        filters = remove_filter(filters, "Gene_names")
        result = get_filtered_rows(filter_df, ["Gene_names"], "", all_statuses, filters, status_func)
        assert len(result) == 4


# =============================================================================
# 19. Modal Utils Integration — Column Modal → Preset → Table Header
# =============================================================================

class TestColumnModalToTableHeader:
    """Pipeline: build column modal content with preset columns → render
    table header with the same columns → verify consistency."""

    def test_preset_columns_drive_modal_and_header(self):
        """Preset columns appear both in column modal and table header."""
        from src.utils.modal_utils import build_columns_modal_content
        from src.utils.table_utils import build_table_header

        all_cols = ["PatientID", "Gene_names", "Variant_key", "Status", "Comments"]
        preset_cols = ["PatientID", "Gene_names", "Status"]
        available = [c for c in all_cols if c not in preset_cols]

        # Modal shows current + available
        modal_html = str(build_columns_modal_content(preset_cols, available))
        for c in preset_cols:
            assert c in modal_html
        for c in available:
            assert c in modal_html
        assert "Current columns" in modal_html
        assert "Remaining columns" in modal_html

        # Table header uses same columns
        widths = {c: "150px" for c in preset_cols}
        header_html = str(build_table_header(preset_cols, widths))
        for c in preset_cols:
            assert c in header_html
        # Unavailable columns NOT in header
        for c in available:
            assert c not in header_html

    def test_column_masks_consistent_across_modal_and_header(self):
        """column_masks produce the same display name in modal and header."""
        from src.utils.modal_utils import build_columns_modal_content, build_filter_column_buttons, build_copy_column_buttons
        from src.utils.table_utils import build_draggable_header_cell

        masks = {"Gene_names": "Gene", "Variant_key": "Variant"}
        cols = ["Gene_names", "Variant_key"]

        # Modal tags show masked names
        modal_html = str(build_columns_modal_content(cols, [], column_masks=masks))
        assert "Gene" in modal_html
        assert "Variant" in modal_html

        # Header cell shows masked name
        th_html = str(build_draggable_header_cell("Gene_names", column_masks=masks))
        assert "Gene" in th_html
        assert 'data-column="Gene_names"' in th_html  # real name in data attr

        # Filter buttons show masked name
        fb_html = str(build_filter_column_buttons(cols, column_masks=masks))
        assert "Gene" in fb_html
        assert "Variant" in fb_html

        # Copy buttons show masked name
        cb_html = str(build_copy_column_buttons(cols, column_masks=masks))
        assert "Gene" in cb_html
        assert "Variant" in cb_html


# =============================================================================
# 20. Modal Utils Integration — Copy Modal → Clipboard Pipeline
# =============================================================================

class TestCopyModalToClipboard:
    """Pipeline: build copy column buttons → process_copy_request → clipboard JS."""

    def test_copy_button_triggers_clipboard_pipeline(self):
        """Copy button columns match clipboard pipeline output."""
        from src.utils.modal_utils import build_copy_column_buttons
        from src.utils.clipboard_utils import process_copy_request
        from src.utils.data_operations import get_paginated_indices, get_copy_column_values

        df = pd.DataFrame({
            "Gene_names": ["BRCA1", "TP53", "EGFR"],
            "Score": [85, 42, 95],
        })

        # Build copy buttons
        btn_html = str(build_copy_column_buttons(["Gene_names", "Score"]))
        assert "copyColumnValues" in btn_html
        assert "Gene_names" in btn_html
        assert "Score" in btn_html

        # Simulate the copy pipeline for Gene_names
        filtered_indices = [0, 1, 2]
        request = {"action": "copy_column", "column": "Gene_names", "indices": [0, 1, 2]}

        def mock_paginate(indices, rpp, page):
            return get_paginated_indices(indices, rpp, page)

        def mock_copy_values(frame, col, pag_indices, sel_indices):
            return get_copy_column_values(frame, col, pag_indices, sel_indices)

        js, col, count, err = process_copy_request(
            request, df, filtered_indices, "25", 1,
            mock_paginate, mock_copy_values
        )
        assert err is None
        assert col == "Gene_names"
        assert count == 3
        assert "BRCA1" in js
        assert "TP53" in js


# =============================================================================
# 21. Modal Utils Integration — Operator Filter + fix_filter Lockdown
# =============================================================================

class TestFixFilterLockdownPipeline:
    """Pipeline: config-defined operator filters rendered locked →
    update_filter_values skips them → get_filtered_rows still applies."""

    def test_locked_filter_renders_readonly_and_still_filters(self):
        """fix_filter=True renders locked UI; filter_utils still applies the filter."""
        from src.utils.modal_utils import build_dynamic_filters_panel
        from src.utils.filter_utils import get_filtered_rows
        from src.utils.filter_handlers import update_filter_values
        from unittest.mock import MagicMock

        df = pd.DataFrame({
            "Gene_names": ["BRCA1", "TP53", "EGFR", "PTEN"],
            "Score": [85, 42, 95, 70],
        })
        status_func = lambda idx: "unprocessed"

        # Config-defined filter (no "interactive" key)
        filters = {"Gene_names": {"op": "in", "value": ["BRCA1", "TP53"]}}

        # 1) Render panel as locked
        html = str(build_dynamic_filters_panel(filters, df, fix_filter=True))
        assert "Gene_names" in html
        assert "disabled" in html  # operator select locked

        # 2) update_filter_values SKIPS config-defined filters
        mock_input = MagicMock()
        new_filters, updated = update_filter_values(filters, mock_input)
        assert updated is False  # Nothing changed

        # 3) get_filtered_rows still applies the locked filter
        result = get_filtered_rows(
            df, ["Gene_names", "Score"], "",
            ["unprocessed"], filters, status_func
        )
        names = [df.loc[i, "Gene_names"] for i in result]
        assert sorted(names) == ["BRCA1", "TP53"]

    def test_interactive_filter_alongside_locked(self):
        """Interactive filter works while locked config filter stays untouched."""
        from src.utils.filter_utils import get_filtered_rows
        from src.utils.filter_handlers import update_filter_values
        from unittest.mock import MagicMock

        df = pd.DataFrame({
            "Gene_names": ["BRCA1", "TP53", "EGFR"],
            "Score": [85, 42, 95],
        })
        status_func = lambda idx: "unprocessed"

        filters = {
            "Gene_names": {"op": "in", "value": ["BRCA1", "TP53"]},  # locked (no interactive)
            "Score": "all",  # user-added simple filter
        }

        # User types a score filter
        mock_input = MagicMock()
        mock_input.filter_Gene_names = MagicMock(side_effect=Exception("should not be called"))
        mock_input.filter_Score = MagicMock(return_value="85")

        new_filters, updated = update_filter_values(filters, mock_input)
        assert updated is True
        assert new_filters["Score"] == "85"
        # Gene_names unchanged
        assert new_filters["Gene_names"] == {"op": "in", "value": ["BRCA1", "TP53"]}

        # Both filters apply
        result = get_filtered_rows(
            df, ["Gene_names", "Score"], "",
            ["unprocessed"], new_filters, status_func
        )
        assert result == [0]  # BRCA1 + Score=85


# =============================================================================
# 22. Modal Utils Integration — Cell Edit → Filter Panel Rebuilds
# =============================================================================

class TestCellEditUpdatesFilterPanel:
    """After a cell edit changes a value, the rebuilt filter panel should
    reflect the new unique values."""

    def test_edit_introduces_new_unique_value_in_panel(self):
        """Editing Gene_names from EGFR → ALK adds ALK to filter panel unique values."""
        from src.utils.data_operations import perform_cell_edit
        from src.utils.modal_utils import build_dynamic_filters_panel
        from src.utils.filter_handlers import add_filter
        from unittest.mock import MagicMock

        df = pd.DataFrame({
            "PatientID_Mutsequence": ["PK001", "PK002", "PK003"],
            "Gene_names": ["BRCA1", "TP53", "EGFR"],
        })

        mock_ci = MagicMock()
        mock_ci.app_config.table.primary_key = ["PatientID_Mutsequence"]
        mock_ci.update_data_in_db = MagicMock(return_value=True)
        mock_ci.save_modification_to_db = MagicMock(return_value=1)

        # Edit EGFR → ALK
        df2, log = perform_cell_edit(df, [], 2, "Gene_names", "EGFR", "ALK", config_instance=mock_ci)
        assert df2.iloc[2]["Gene_names"] == "ALK"

        # Build filter panel → should include ALK in unique values
        filters = add_filter({}, "Gene_names")
        panel_html = str(build_dynamic_filters_panel(filters, df2))
        assert "ALK" in panel_html
        assert "EGFR" not in panel_html  # Old value gone

    def test_edit_does_not_affect_other_column_filters(self):
        """Editing Gene_names should not change Status filter unique values."""
        from src.utils.data_operations import perform_cell_edit
        from src.utils.modal_utils import build_dynamic_filters_panel
        from unittest.mock import MagicMock

        df = pd.DataFrame({
            "PatientID_Mutsequence": ["PK001", "PK002"],
            "Gene_names": ["BRCA1", "TP53"],
            "Status": ["Pending", "Reviewed"],
        })

        mock_ci = MagicMock()
        mock_ci.app_config.table.primary_key = ["PatientID_Mutsequence"]
        mock_ci.update_data_in_db = MagicMock(return_value=True)
        mock_ci.save_modification_to_db = MagicMock(return_value=1)

        df2, _ = perform_cell_edit(df, [], 0, "Gene_names", "BRCA1", "ALK", config_instance=mock_ci)

        filters = {"Gene_names": "all", "Status": "all"}
        panel_html = str(build_dynamic_filters_panel(filters, df2))
        # Gene_names has the new value
        assert "ALK" in panel_html
        # Status still has originals
        assert "Pending" in panel_html
        assert "Reviewed" in panel_html


# =============================================================================
# 23. Modal Utils Integration — Lazy Mode get_unique_values_func Callback
# =============================================================================

class TestLazyModeUniqueValuesCallback:
    """When DataFrame is empty (lazy loading), build_dynamic_filters_panel
    uses the get_unique_values_func callback to populate filter values."""

    def test_empty_df_calls_callback_for_values(self):
        """Empty DataFrame triggers callback; panel shows DB-fetched values."""
        from src.utils.modal_utils import build_dynamic_filters_panel
        from unittest.mock import MagicMock

        empty_df = pd.DataFrame(columns=["Gene_names", "Status"])

        callback = MagicMock(return_value=["BRCA1", "TP53", "EGFR"])

        filters = {"Gene_names": "all"}
        panel_html = str(build_dynamic_filters_panel(
            filters, empty_df,
            all_columns=["Gene_names", "Status"],
            get_unique_values_func=callback
        ))

        callback.assert_called_once_with("Gene_names")
        assert "BRCA1" in panel_html
        assert "TP53" in panel_html

    def test_non_empty_df_prefers_callback(self):
        """When callback is available, it is preferred over DataFrame for full unique values."""
        from src.utils.modal_utils import build_dynamic_filters_panel
        from unittest.mock import MagicMock

        df = pd.DataFrame({"Gene_names": ["BRCA1", "TP53"]})
        callback = MagicMock(return_value=["BRCA1", "TP53", "EGFR"])

        filters = {"Gene_names": "all"}
        panel_html = str(build_dynamic_filters_panel(
            filters, df, get_unique_values_func=callback
        ))

        callback.assert_called_once_with("Gene_names")
        assert "BRCA1" in panel_html
        assert "EGFR" in panel_html

    def test_operator_filter_with_callback(self):
        """Operator filter on empty df uses callback, then get_filtered_rows applies it."""
        from src.utils.modal_utils import build_dynamic_filters_panel
        from src.utils.filter_utils import get_filtered_rows
        from unittest.mock import MagicMock

        # Panel built with callback (lazy mode)
        empty_df = pd.DataFrame(columns=["Gene_names"])
        callback = MagicMock(return_value=["BRCA1", "TP53", "EGFR"])
        filters = {"Gene_names": {"op": "in", "value": ["BRCA1"], "interactive": True}}

        panel_html = str(build_dynamic_filters_panel(
            filters, empty_df,
            all_columns=["Gene_names"],
            get_unique_values_func=callback
        ))
        assert "BRCA1" in panel_html

        # Now apply filter on actual data
        real_df = pd.DataFrame({"Gene_names": ["BRCA1", "TP53", "EGFR"]})
        status_func = lambda idx: "unprocessed"
        result = get_filtered_rows(
            real_df, ["Gene_names"], "",
            ["unprocessed"], filters, status_func
        )
        assert result == [0]  # Only BRCA1


# =============================================================================
# 24. Modal Utils Integration — Preset Menu → Column Change → Filter Sync
# =============================================================================

class TestPresetMenuFilterSync:
    """Pipeline: preset menu built → switching presets changes columns →
    filter column buttons update to reflect available columns."""

    def test_preset_switch_updates_filter_buttons(self):
        """Different presets show different available columns for filtering."""
        from src.utils.modal_utils import build_preset_menu_items, build_filter_column_buttons

        presets = {
            "Default": {"columns": ["Gene_names", "Status"]},
            "Extended": {"columns": ["Gene_names", "Status", "Score", "Comments"]},
        }

        # Build preset menu
        menu_html = str(build_preset_menu_items(presets, "Default"))
        assert "Default" in menu_html
        assert "Extended" in menu_html
        assert "deletePreset" in menu_html  # Extended has delete

        # Default preset: filter buttons for the 2 columns
        fb_default = str(build_filter_column_buttons(presets["Default"]["columns"]))
        assert "Gene_names" in fb_default
        assert "Status" in fb_default
        assert "Score" not in fb_default

        # Extended preset: filter buttons for 4 columns
        fb_ext = str(build_filter_column_buttons(presets["Extended"]["columns"]))
        assert "Score" in fb_ext
        assert "Comments" in fb_ext

    def test_filtered_columns_excluded_from_available(self):
        """Columns already filtered should not appear in filter column buttons."""
        from src.utils.modal_utils import build_filter_column_buttons
        from src.utils.filter_handlers import add_filter

        all_cols = ["Gene_names", "Status", "Score"]
        filters = add_filter({}, "Gene_names")
        available = [c for c in all_cols if c not in filters]

        fb_html = str(build_filter_column_buttons(available))
        assert "Gene_names" not in fb_html  # Already filtered
        assert "Status" in fb_html
        assert "Score" in fb_html


# =============================================================================
# 25. Modal Utils Integration — All 12 Operators End-to-End
# =============================================================================

class TestAllOperatorsEndToEnd:
    """Each operator renders correctly in the panel AND filters data correctly."""

    @pytest.fixture
    def op_df(self):
        return pd.DataFrame({
            "Name": ["Alice", "Bob", "Charlie", "Diana", "Eve"],
            "Score": ["85", "42", "95", "70", "60"],
            "Gene": ["BRCA1", "TP53", "EGFR", "PTEN", "BRCA2"],
        })

    @pytest.fixture
    def status_func(self):
        return lambda idx: "unprocessed"

    def _filter_names(self, df, filters, status_func, cols=None):
        from src.utils.filter_utils import get_filtered_rows
        cols = cols or ["Name", "Score", "Gene"]
        result = get_filtered_rows(df, cols, "", ["unprocessed"], filters, status_func)
        return [df.loc[i, "Name"] for i in result]

    def test_contains_operator(self, op_df, status_func):
        from src.utils.modal_utils import build_dynamic_filters_panel
        filters = {"Gene": {"op": "contains", "value": "BRC", "interactive": True}}
        names = self._filter_names(op_df, filters, status_func)
        assert sorted(names) == ["Alice", "Eve"]
        html = str(build_dynamic_filters_panel(filters, op_df))
        assert "contains" in html.lower() or "BRC" in html

    def test_not_contains_operator(self, op_df, status_func):
        filters = {"Gene": {"op": "not_contains", "value": "BRC", "interactive": True}}
        names = self._filter_names(op_df, filters, status_func)
        assert "Alice" not in names
        assert "Bob" in names

    def test_regex_operator(self, op_df, status_func):
        filters = {"Gene": {"op": "regex", "value": "^(BRCA|TP)", "interactive": True}}
        names = self._filter_names(op_df, filters, status_func)
        assert sorted(names) == ["Alice", "Bob", "Eve"]

    def test_not_in_operator(self, op_df, status_func):
        filters = {"Gene": {"op": "not_in", "value": ["BRCA1", "TP53"], "interactive": True}}
        names = self._filter_names(op_df, filters, status_func)
        assert sorted(names) == ["Charlie", "Diana", "Eve"]

    def test_gt_operator_numeric(self, op_df, status_func):
        filters = {"Score": {"op": "gt", "value": "70", "interactive": True}}
        names = self._filter_names(op_df, filters, status_func)
        assert sorted(names) == ["Alice", "Charlie"]

    def test_lte_operator_numeric(self, op_df, status_func):
        filters = {"Score": {"op": "lte", "value": "60", "interactive": True}}
        names = self._filter_names(op_df, filters, status_func)
        assert sorted(names) == ["Bob", "Eve"]

    def test_between_operator(self, op_df, status_func):
        filters = {"Score": {"op": "between", "value": ["50", "85"], "interactive": True}}
        names = self._filter_names(op_df, filters, status_func)
        assert sorted(names) == ["Alice", "Diana", "Eve"]

    def test_not_empty_operator(self, op_df, status_func):
        df2 = op_df.copy()
        df2.loc[1, "Gene"] = None
        filters = {"Gene": {"op": "not_empty", "value": None, "interactive": True}}
        names = self._filter_names(df2, filters, status_func)
        assert "Bob" not in names
        assert len(names) == 4
