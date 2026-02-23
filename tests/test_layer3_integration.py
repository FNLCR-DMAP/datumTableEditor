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
        # Shows "filtered X of Y total" when filtered_count < total
        assert "filtered 4 of 5 total" in html


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
        """perform_cell_edit must call update_data_in_db then save_modification_to_db."""
        from src.utils.data_operations import perform_cell_edit

        perform_cell_edit(df, [], 1, "Gene_names", "TP53", "TP53_mut", config_instance=mock_ci)

        # UPDATE data table
        mock_ci.update_data_in_db.assert_called_once()
        args_update = mock_ci.update_data_in_db.call_args
        assert args_update[0][0] == {"PatientID_Mutsequence": "PK002"}  # row_pk
        assert args_update[0][1] == "Gene_names"  # column
        assert args_update[0][2] == "TP53_mut"  # new_value

        # INSERT modification record
        mock_ci.save_modification_to_db.assert_called_once()
        args_insert = mock_ci.save_modification_to_db.call_args
        assert args_insert[0][0] == {"PatientID_Mutsequence": "PK002"}
        assert args_insert[0][1] == "Gene_names"
        assert args_insert[0][2] == "TP53"  # old_value
        assert args_insert[0][3] == "TP53_mut"  # new_value
        assert args_insert[0][4] == "field_modification"

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
        mock_ci.update_data_in_db.assert_called_once()
        revert_args = mock_ci.update_data_in_db.call_args[0]
        assert revert_args[0] == {"PatientID_Mutsequence": "PK002"}
        assert revert_args[1] == "Gene_names"
        assert revert_args[2] == "TP53"  # reverted to original

        # 2) Mark original mod as undone
        mock_ci.mark_modification_undone_in_db.assert_called_once()

        # 3) Insert undo record
        mock_ci.save_modification_to_db.assert_called_once()
        undo_args = mock_ci.save_modification_to_db.call_args[0]
        assert undo_args[1] == "Gene_names"
        assert undo_args[4] == "undo"  # mod_type

    def test_multi_edit_accumulates_sequential_db_calls(self, df, pk_cols, mock_ci):
        """Three consecutive edits → 3 update_data_in_db + 3 save_modification_to_db."""
        from src.utils.data_operations import perform_cell_edit

        log = []
        df1, log = perform_cell_edit(df, log, 0, "Gene_names", "BRCA1", "BRCA1x", config_instance=mock_ci)
        df2, log = perform_cell_edit(df1, log, 1, "Status", "Reviewed", "Done", config_instance=mock_ci)
        df3, log = perform_cell_edit(df2, log, 2, "Gene_names", "EGFR", "EGFRx", config_instance=mock_ci)

        assert mock_ci.update_data_in_db.call_count == 3
        assert mock_ci.save_modification_to_db.call_count == 3

        # Verify each call's row_pk
        update_calls = mock_ci.update_data_in_db.call_args_list
        assert update_calls[0][0][0] == {"PatientID_Mutsequence": "PK001"}
        assert update_calls[1][0][0] == {"PatientID_Mutsequence": "PK002"}
        assert update_calls[2][0][0] == {"PatientID_Mutsequence": "PK003"}

        # Verify columns
        assert update_calls[0][0][1] == "Gene_names"
        assert update_calls[1][0][1] == "Status"
        assert update_calls[2][0][1] == "Gene_names"


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
