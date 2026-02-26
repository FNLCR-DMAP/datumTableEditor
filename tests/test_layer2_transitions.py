"""
Layer 2: State transition and function interaction tests.

These tests verify multi-step state transitions — how functions compose
and how state flows through edit→undo→approve→filter→paginate chains.
"""

import pytest
import pandas as pd
from unittest.mock import MagicMock, patch
from copy import deepcopy


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def edit_df():
    """5-row DataFrame for edit lifecycle tests."""
    return pd.DataFrame({
        "PatientID_Mutsequence": ["PK001", "PK002", "PK003", "PK004", "PK005"],
        "Gene_names": ["BRCA1", "TP53", "EGFR", "PTEN", "RB1"],
        "Status": ["Pending", "Pending", "Pending", "Pending", "Pending"],
    })


@pytest.fixture
def pk_cols():
    return ["PatientID_Mutsequence"]


@pytest.fixture
def mock_config():
    """Mock ConfigInstance for edit operations."""
    config = MagicMock()
    config.app_config.database.enabled = False
    config.app_config.table.primary_key = ["PatientID_Mutsequence"]
    config.save_modification_to_db.return_value = None
    config.mark_modification_undone_in_db.return_value = True
    config.update_data_in_db.return_value = True
    return config


# =============================================================================
# 1. Edit Lifecycle: edit → log → status → undo → revert
# =============================================================================

class TestEditToStatusTransition:
    """Scenario 1: Cell edit → log entry → status changes to 'edited'."""

    def test_edit_creates_log_entry_and_changes_status(self, edit_df, pk_cols, mock_config):
        from src.utils.data_operations import perform_cell_edit
        from src.utils.data_utils import get_row_status, get_status_counts

        with patch('src.utils.data_operations.DB_AVAILABLE', False):
            updated_df, updated_log = perform_cell_edit(
                df=edit_df.copy(), log=[], row=0, col="Gene_names",
                old_value="BRCA1", new_value="BRCA1_edited",
                config_instance=mock_config
            )

        # Cell updated
        assert updated_df.iloc[0]["Gene_names"] == "BRCA1_edited"
        # Log entry created
        assert len(updated_log) == 1
        assert updated_log[0]["type"] == "field_modification"
        assert updated_log[0]["details"]["row_pk"] == {"PatientID_Mutsequence": "PK001"}
        # Status changed
        row_pk = {"PatientID_Mutsequence": "PK001"}
        assert get_row_status(0, updated_log, row_pk) == "edited"
        # Status counts updated
        counts = get_status_counts(updated_df, updated_log, pk_cols)
        assert counts["edited"] == 1
        assert counts["unprocessed"] == 4


class TestEditUndoReverts:
    """Scenario 2: edit → undo → status reverts to 'unprocessed'."""

    def test_undo_reverts_cell_and_status(self, edit_df, pk_cols, mock_config):
        from src.utils.data_operations import perform_cell_edit, perform_undo
        from src.utils.data_utils import get_row_status

        with patch('src.utils.data_operations.DB_AVAILABLE', False):
            df1, log1 = perform_cell_edit(
                df=edit_df.copy(), log=[], row=0, col="Gene_names",
                old_value="BRCA1", new_value="EDITED",
                config_instance=mock_config
            )

        assert get_row_status(0, log1, {"PatientID_Mutsequence": "PK001"}) == "edited"

        with patch('src.utils.data_operations.DB_AVAILABLE', False):
            df2, log2, msg, err = perform_undo(
                df=df1, log=log1, log_idx=0, config_instance=mock_config
            )

        # Cell reverted
        assert df2.iloc[0]["Gene_names"] == "BRCA1"
        # Log entry marked undone
        assert log2[0]["undone"] is True
        # Undo entry appended
        assert log2[-1]["type"] == "undo"
        # Status reverts
        assert get_row_status(0, log2, {"PatientID_Mutsequence": "PK001"}) == "unprocessed"


class TestMultiEditUndoLast:
    """Scenario 3: Multiple edits → undo last → intermediate state preserved."""

    def test_undo_last_restores_intermediate(self, edit_df, pk_cols, mock_config):
        from src.utils.data_operations import perform_cell_edit, perform_undo
        from src.utils.data_utils import get_row_status

        with patch('src.utils.data_operations.DB_AVAILABLE', False):
            df1, log1 = perform_cell_edit(
                df=edit_df.copy(), log=[], row=0, col="Gene_names",
                old_value="BRCA1", new_value="V1",
                config_instance=mock_config
            )
            df2, log2 = perform_cell_edit(
                df=df1, log=log1, row=0, col="Gene_names",
                old_value="V1", new_value="V2",
                config_instance=mock_config
            )

        assert df2.iloc[0]["Gene_names"] == "V2"
        assert len(log2) == 2

        with patch('src.utils.data_operations.DB_AVAILABLE', False):
            df3, log3, msg, err = perform_undo(
                df=df2, log=log2, log_idx=1, config_instance=mock_config
            )

        # Reverts to intermediate "V1", not original "BRCA1"
        assert df3.iloc[0]["Gene_names"] == "V1"
        # First edit still active → still "edited"
        assert get_row_status(0, log3, {"PatientID_Mutsequence": "PK001"}) == "edited"


# =============================================================================
# 2. Approval/Rejection: edit → approve → reject → status precedence
# =============================================================================

class TestApprovalChangesStatus:
    """Scenario 4: Select rows → approve → status distribution changes."""

    def test_approval_updates_status_counts(self, edit_df, pk_cols):
        from src.utils.data_operations import create_approval_entry
        from src.utils.data_utils import get_row_status, get_status_counts

        pks = [{"PatientID_Mutsequence": "PK001"}, {"PatientID_Mutsequence": "PK003"}]
        entry = create_approval_entry(pks, total_rows=5, log_count=0)

        log = [entry]

        assert get_row_status(0, log, {"PatientID_Mutsequence": "PK001"}) == "approved"
        assert get_row_status(2, log, {"PatientID_Mutsequence": "PK003"}) == "approved"
        assert get_row_status(1, log, {"PatientID_Mutsequence": "PK002"}) == "unprocessed"

        counts = get_status_counts(edit_df, log, pk_cols)
        assert counts["approved"] == 2
        assert counts["unprocessed"] == 3


class TestApprovalOverridesEdit:
    """Scenario 5: Edit row → approve → approval takes precedence."""

    def test_approval_overrides_edited_status(self, edit_df, pk_cols, mock_config):
        from src.utils.data_operations import perform_cell_edit, create_approval_entry
        from src.utils.data_utils import get_row_status

        with patch('src.utils.data_operations.DB_AVAILABLE', False):
            df1, log1 = perform_cell_edit(
                df=edit_df.copy(), log=[], row=0, col="Gene_names",
                old_value="BRCA1", new_value="EDITED",
                config_instance=mock_config
            )

        assert get_row_status(0, log1, {"PatientID_Mutsequence": "PK001"}) == "edited"

        # Approve the same row
        approval = create_approval_entry(
            [{"PatientID_Mutsequence": "PK001"}], total_rows=5, log_count=1
        )
        log2 = log1 + [approval]

        # Approval wins over edit
        assert get_row_status(0, log2, {"PatientID_Mutsequence": "PK001"}) == "approved"
        # But the data change persists
        assert df1.iloc[0]["Gene_names"] == "EDITED"


class TestRejectionOverridesApproval:
    """Scenario 6: Approve → reject → last entry wins."""

    def test_reject_after_approve_flips_status(self, edit_df, pk_cols):
        from src.utils.data_operations import create_approval_entry, create_rejection_entry
        from src.utils.data_utils import get_row_status, get_status_counts

        pk = {"PatientID_Mutsequence": "PK001"}

        approval = create_approval_entry([pk], total_rows=5, log_count=0)
        rejection = create_rejection_entry([pk], total_rows=5, log_count=1)
        log = [approval, rejection]

        assert get_row_status(0, log, pk) == "rejected"

        counts = get_status_counts(edit_df, log, pk_cols)
        assert counts["rejected"] == 1
        assert counts["approved"] == 0


# =============================================================================
# 3. Filter + Search Composition
# =============================================================================

class TestFilterSearchComposition:
    """Scenario 7: Column filter + search → intersection → clear → wider."""

    def test_filter_then_search_narrows_then_clear_widens(self, edit_df, pk_cols):
        from src.utils.filter_utils import get_filtered_rows
        from src.utils.filter_handlers import add_filter, remove_filter

        status_func = lambda idx: "unprocessed"
        all_statuses = ["unprocessed", "edited", "approved", "rejected"]
        cols = ["Gene_names", "Status"]

        # No filter: all 5 rows
        all_rows = get_filtered_rows(edit_df, cols, "", all_statuses, {}, status_func)
        assert len(all_rows) == 5

        # Add column filter: only BRCA1
        filters = add_filter({}, "Gene_names")
        assert filters == {"Gene_names": "all"}

        filter_only = get_filtered_rows(
            edit_df, cols, "", all_statuses,
            {"Gene_names": "BRCA1"}, status_func
        )
        assert len(filter_only) == 1
        assert edit_df.iloc[filter_only[0]]["Gene_names"] == "BRCA1"

        # Add search on top: filter + search = intersection
        filter_and_search = get_filtered_rows(
            edit_df, cols, "PK001", all_statuses,
            {"Gene_names": "BRCA1"}, status_func
        )
        assert len(filter_and_search) <= len(filter_only)

        # Remove filter: search-only is broader
        filters = remove_filter(filters, "Gene_names")
        assert filters == {}

        search_only = get_filtered_rows(
            edit_df, cols, "PK001", all_statuses, {}, status_func
        )
        assert len(search_only) >= len(filter_and_search)


class TestOperatorFilterWithStatusFilter:
    """Scenario 8: Operator filter + status filter composition."""

    def test_operator_and_status_both_applied(self, edit_df, pk_cols):
        from src.utils.filter_utils import get_filtered_rows, _is_operator_filter, _row_matches_operator

        # Verify operator detection
        assert _is_operator_filter({"op": "not_contains", "value": "TP"}) is True
        assert _is_operator_filter("BRCA1") is False

        # Verify operator logic
        assert _row_matches_operator("TP53", {"op": "not_contains", "value": "TP"}) is False
        assert _row_matches_operator("BRCA1", {"op": "not_contains", "value": "TP"}) is True

        # Combined: only "unprocessed" rows where Gene_names does NOT contain "TP"
        status_func = lambda idx: "unprocessed"
        result = get_filtered_rows(
            edit_df,
            ["Gene_names"],
            "",
            ["unprocessed"],
            {"Gene_names": {"op": "not_contains", "value": "TP"}},
            status_func,
        )

        # TP53 excluded → 4 rows remain
        for idx in result:
            assert "TP" not in edit_df.iloc[idx]["Gene_names"]


# =============================================================================
# 4. Preset Lifecycle
# =============================================================================

class TestPresetSaveActivateDeleteFallback:
    """Scenario 9: save → activate → reload → delete → fallback to Default."""

    def test_full_preset_lifecycle(self):
        from src.utils.preset_utils import load_presets, save_presets, load_active_preset, save_active_preset

        default_columns = ["PatientID", "Gene_names", "Status"]

        # Mock ConfigInstance
        config = MagicMock()
        stored_presets = []
        stored_defaults = [None]

        def mock_get_presets():
            return list(stored_presets)

        def mock_save_preset(name, data, is_default=False):
            # Remove existing with same name
            stored_presets[:] = [p for p in stored_presets if p["preset_name"] != name]
            # data may be a dict (from save_presets) or a list (from save_active_preset)
            if isinstance(data, dict):
                columns = data.get("columns", [])
                widths = data.get("widths", {})
            else:
                columns = data
                widths = {}
            stored_presets.append({
                "preset_name": name,
                "columns": columns,
                "column_widths": widths,
                "is_default": is_default,
            })
            if is_default:
                stored_defaults[0] = name
            return len(stored_presets)

        def mock_delete_preset(name):
            before = len(stored_presets)
            stored_presets[:] = [p for p in stored_presets if p["preset_name"] != name]
            if stored_defaults[0] == name:
                stored_defaults[0] = None
            return len(stored_presets) < before

        def mock_get_default():
            for p in stored_presets:
                if p.get("is_default"):
                    return p
            return None

        config.get_presets = mock_get_presets
        config.save_preset = mock_save_preset
        config.delete_preset = mock_delete_preset
        config.get_default_preset = mock_get_default
        config.app_config.table.default_columns = default_columns

        # Step 1: Load initial — only Default exists
        presets = load_presets(config, default_columns)
        assert "Default" in presets

        # Step 2: Save a custom preset
        presets["MyPreset"] = {"columns": ["Gene_names"], "widths": {}}
        save_presets(config, presets)
        assert any(p["preset_name"] == "MyPreset" for p in stored_presets)

        # Step 3: Activate MyPreset
        save_active_preset(config, "MyPreset")
        assert load_active_preset(config) == "MyPreset"

        # Step 4: Delete MyPreset (simulate: save without it)
        presets_after = load_presets(config, default_columns)
        del presets_after["MyPreset"]
        save_presets(config, presets_after)

        # Step 5: Fallback to Default
        assert load_active_preset(config) == "Default"


# =============================================================================
# 5. Pagination State
# =============================================================================

class TestPaginationStateTransitions:
    """Scenario 11-12: Page changes, RPP changes, clamping."""

    def test_page_change_produces_disjoint_indices(self):
        from src.utils.data_operations import get_paginated_indices, calculate_pagination

        filtered = list(range(10))

        page1 = get_paginated_indices(filtered, "5", 1)
        page2 = get_paginated_indices(filtered, "5", 2)

        assert len(page1) == 5
        assert len(page2) == 5
        assert set(page1).isdisjoint(set(page2))
        assert set(page1) | set(page2) == set(filtered)

    def test_rpp_change_resets_page_size(self):
        from src.utils.data_operations import get_paginated_indices, calculate_pagination

        filtered = list(range(10))

        # RPP=5, page 1
        page = get_paginated_indices(filtered, "5", 1)
        assert len(page) == 5

        # Change RPP to 3, page 1
        page = get_paginated_indices(filtered, "3", 1)
        assert len(page) == 3

        # Pagination metadata
        current, total_pages, start, end = calculate_pagination(10, "3", 1)
        assert total_pages == 4
        assert current == 1

    def test_page_clamped_when_filter_reduces_rows(self):
        from src.utils.data_operations import calculate_pagination

        # Was on page 3 with 10 rows, RPP=3 (4 pages)
        current, total, start, end = calculate_pagination(10, "3", 3)
        assert current == 3
        assert total == 4

        # Filter reduces to 5 rows → page 3 exceeds 2 pages → clamped
        current, total, start, end = calculate_pagination(5, "3", 3)
        assert current <= total
        assert total == 2

    def test_rpp_all_returns_everything(self):
        from src.utils.data_operations import get_paginated_indices, calculate_pagination

        filtered = list(range(100))

        page = get_paginated_indices(filtered, "all", 1)
        assert page == filtered

        current, total, start, end = calculate_pagination(100, "all", 1)
        assert total == 1


# =============================================================================
# 6. SessionBook State Transitions
# =============================================================================

class TestSessionBookContextChange:
    """Scenario 14: Context change clears data, append deduplicates."""

    def test_context_change_clears_data(self):
        from src.db.session_book import SessionBook

        book = SessionBook(primary_key=["id"])
        df = pd.DataFrame({"id": ["A", "B"], "val": [1, 2]})

        # Set initial context, then load data
        book.set_context("filter_a")
        book.append_page(df, page_number=1)
        assert book.row_count == 2

        # Same context → no clear
        changed = book.set_context("filter_a")
        assert changed is False
        assert book.row_count == 2

        # Different context → clears
        changed = book.set_context("filter_b")
        assert changed is True
        assert book.row_count == 0

    def test_append_page_deduplicates(self):
        from src.db.session_book import SessionBook

        book = SessionBook(primary_key=["id"])
        df = pd.DataFrame({"id": ["A", "B"], "val": [1, 2]})

        n1 = book.append_page(df, page_number=1)
        assert n1 == 2

        # Same page again → 0 new rows
        n2 = book.append_page(df, page_number=1)
        assert n2 == 0
        assert book.row_count == 2  # Not doubled


class TestSessionBookUpdateAndReconcile:
    """Scenario 15: update_row + reconcile preserves order."""

    def test_update_row_changes_value(self):
        from src.db.session_book import SessionBook

        book = SessionBook(primary_key=["id"])
        df = pd.DataFrame({"id": ["A", "B", "C"], "name": ["Alice", "Bob", "Carol"]})
        book.append_page(df, page_number=1)

        result = book.update_row({"id": "B"}, {"name": "Bob_edited"})
        assert result is True

        row = book.get_row_by_pk({"id": "B"})
        assert row["name"] == "Bob_edited"

    def test_update_row_unknown_pk_returns_false(self):
        from src.db.session_book import SessionBook

        book = SessionBook(primary_key=["id"])
        df = pd.DataFrame({"id": ["A"], "name": ["Alice"]})
        book.append_page(df, page_number=1)

        result = book.update_row({"id": "NONEXISTENT"}, {"name": "nobody"})
        assert result is False


# =============================================================================
# 7. SQL Query Generation Transitions
# =============================================================================

class TestQueryBuilderSQLTransitions:
    """Verify that filter/sort state transitions produce correct SQL strings."""

    def test_no_filters_produces_clean_select(self):
        from src.db.query_builder import QueryBuilder

        qb = QueryBuilder("schema.data", "schema.mods", ["PatientID_Mutsequence"])
        sql, params = qb.build_select_query(filters=[], sort=None, page=1, limit=25, include_mods_status=False)

        assert sql.startswith('SELECT * FROM "schema"."data"')
        assert "WHERE" not in sql.split("ORDER")[0]  # no filters before ORDER BY
        assert 'ORDER BY "PatientID_Mutsequence" ASC' in sql
        assert "LIMIT :limit OFFSET :offset" in sql
        assert params["limit"] == 25
        assert params["offset"] == 0

    def test_adding_filter_adds_where_clause(self):
        from src.db.query_builder import QueryBuilder, FilterCondition

        qb = QueryBuilder("data_table", "mods_table", ["id"])
        sql_empty, _ = qb.build_select_query(filters=[], include_mods_status=False)
        assert "WHERE" not in sql_empty.split("ORDER")[0]

        sql_with, params = qb.build_select_query(
            filters=[FilterCondition("Status", "=", "Pending")],
            include_mods_status=False,
        )
        assert 'WHERE "Status" = :f0_Status' in sql_with
        assert params["f0_Status"] == "Pending"

    def test_stacking_filters_produces_and_chain(self):
        from src.db.query_builder import QueryBuilder, FilterCondition

        qb = QueryBuilder("data", "mods", ["id"])
        filters = [
            FilterCondition("Status", "=", "Pending"),
            FilterCondition("Gene_names", "IN", ["BRCA1", "TP53"]),
            FilterCondition("Comments", "IS NOT NULL"),
        ]
        sql, params = qb.build_select_query(filters=filters, include_mods_status=False)

        # All filters connected by AND
        where_segment = sql.split("ORDER")[0]
        assert '"Status" =' in where_segment
        assert '"Gene_names" IN' in where_segment
        assert '"Comments" IS NOT NULL' in where_segment
        assert where_segment.count(" AND ") == 2  # 3 conditions → 2 ANDs

    def test_sort_direction_flip_changes_sql(self):
        from src.db.query_builder import QueryBuilder, SortConfig

        qb = QueryBuilder("data", "mods", ["id"])
        sql_asc, _ = qb.build_select_query(sort=SortConfig("PatientID", True), include_mods_status=False)
        sql_desc, _ = qb.build_select_query(sort=SortConfig("PatientID", False), include_mods_status=False)

        assert '"PatientID" ASC' in sql_asc
        assert '"PatientID" DESC' in sql_desc

    def test_page_progression_changes_offset(self):
        from src.db.query_builder import QueryBuilder

        qb = QueryBuilder("data", "mods", ["id"])
        _, p1 = qb.build_select_query(page=1, limit=25, include_mods_status=False)
        _, p2 = qb.build_select_query(page=2, limit=25, include_mods_status=False)
        _, p3 = qb.build_select_query(page=3, limit=10, include_mods_status=False)

        assert p1["offset"] == 0
        assert p2["offset"] == 25
        assert p3["offset"] == 20

    def test_count_query_mirrors_select_filters(self):
        from src.db.query_builder import QueryBuilder, FilterCondition

        qb = QueryBuilder("data", "mods", ["id"])
        filters = [FilterCondition("Status", "=", "Pending")]

        select_sql, select_params = qb.build_select_query(filters=filters, include_mods_status=False)
        count_sql, count_params = qb.build_count_query(filters=filters)

        # Both use same filter but different projections
        assert "COUNT(*)" in count_sql
        assert "COUNT(*)" not in select_sql
        # Filter present in both
        assert '"Status" =' in select_sql
        assert '"Status" =' in count_sql

    def test_insert_modification_sql_structure(self):
        from src.db.query_builder import QueryBuilder

        qb = QueryBuilder("schema.data", "schema.mods", ["PatientID_Mutsequence"])
        sql = qb.build_insert_modification()

        assert 'INSERT INTO "schema"."mods"' in sql
        assert ":row_pk" in sql
        assert ":column_name" in sql
        assert ":old_value" in sql
        assert ":new_value" in sql
        assert ":mod_type" in sql
        assert ":created_by" in sql
        assert "RETURNING id" in sql

    def test_undo_modification_sql_structure(self):
        from src.db.query_builder import QueryBuilder

        qb = QueryBuilder("data", "schema.mods", ["id"])
        sql = qb.build_undo_modification()

        assert 'UPDATE "schema"."mods"' in sql
        assert "SET undone = TRUE" in sql
        assert "WHERE id = :mod_id" in sql
        assert "RETURNING id" in sql

    def test_include_mods_status_adds_lateral_join(self):
        from src.db.query_builder import QueryBuilder

        qb = QueryBuilder("schema.data", "schema.mods", ["PatientID_Mutsequence"])
        sql_with, _ = qb.build_select_query(include_mods_status=True)
        sql_without, _ = qb.build_select_query(include_mods_status=False)

        assert "_mod_status" in sql_with
        assert "_mod_count" in sql_with
        assert "schema" in sql_with
        assert "_mod_status" not in sql_without


class TestDataFetcherWhereClauseTransitions:
    """Verify DataFetcher._build_where_clause SQL for different filter combos."""

    @pytest.fixture
    def fetcher(self):
        """Build a DataFetcher with mocked internals (skip DB connection)."""
        from src.config.config_instance import DataFetcher

        f = DataFetcher.__new__(DataFetcher)
        # Minimal config stub
        f.app_config = MagicMock()
        f.app_config.query.searchable_columns = ["Gene_names", "Status"]
        f._columns = ["PatientID_Mutsequence", "PatientID", "Gene_names", "Status"]
        f._column_types = {}
        f._engine = None
        f._datum_client = None
        f._total_count = 0
        return f

    def test_empty_params_no_where(self, fetcher):
        from src.config.config_instance import QueryParams
        qp = QueryParams()
        where, params = fetcher._build_where_clause(qp)
        assert where == ""
        assert params == {}

    def test_simple_value_filter_produces_equals(self, fetcher):
        from src.config.config_instance import QueryParams
        qp = QueryParams(filters={"Status": "Pending"})
        where, params = fetcher._build_where_clause(qp, use_params=True)

        assert 'CAST("Status" AS TEXT) = :p0' in where
        assert params["p0"] == "Pending"

    def test_list_filter_produces_in_clause(self, fetcher):
        from src.config.config_instance import QueryParams
        qp = QueryParams(filters={"Gene_names": ["BRCA1", "TP53"]})
        where, params = fetcher._build_where_clause(qp, use_params=True)

        assert 'CAST("Gene_names" AS TEXT) IN (:p0, :p1)' in where
        assert params["p0"] == "BRCA1"
        assert params["p1"] == "TP53"

    def test_operator_not_contains_produces_not_ilike(self, fetcher):
        from src.config.config_instance import QueryParams
        qp = QueryParams(filters={"Gene_names": {"op": "not_contains", "value": "BRCA"}})
        where, params = fetcher._build_where_clause(qp, use_params=True)

        assert 'NOT ILIKE' in where
        assert params["p0"] == "%BRCA%"

    def test_operator_between_produces_between_clause(self, fetcher):
        from src.config.config_instance import QueryParams
        qp = QueryParams(filters={"Gene_names": {"op": "between", "value": ["A", "M"]}})
        where, params = fetcher._build_where_clause(qp, use_params=True)

        assert 'BETWEEN :p0 AND :p1' in where
        assert params["p0"] == "A"
        assert params["p1"] == "M"

    def test_operator_regex_produces_tilde_star(self, fetcher):
        from src.config.config_instance import QueryParams
        qp = QueryParams(filters={"Gene_names": {"op": "regex", "value": "^TP"}})
        where, params = fetcher._build_where_clause(qp, use_params=True)

        assert '~*' in where
        assert params["p0"] == "^TP"

    def test_search_term_adds_ilike_or_clause(self, fetcher):
        from src.config.config_instance import QueryParams
        qp = QueryParams(search_term="PAT")
        where, params = fetcher._build_where_clause(qp, use_params=True)

        assert "ILIKE :search_term" in where
        assert params["search_term"] == "%PAT%"
        # searchable_columns has 2 cols → OR
        assert " OR " in where

    def test_search_specific_column_single_ilike(self, fetcher):
        from src.config.config_instance import QueryParams
        qp = QueryParams(search_term="TP53", search_column="Gene_names")
        where, params = fetcher._build_where_clause(qp, use_params=True)

        assert 'CAST("Gene_names" AS TEXT) ILIKE :search_term' in where
        assert " OR " not in where  # only one column

    def test_filter_plus_search_produces_and(self, fetcher):
        from src.config.config_instance import QueryParams
        qp = QueryParams(
            filters={"Status": "Pending"},
            search_term="BRCA",
        )
        where, params = fetcher._build_where_clause(qp, use_params=True)

        # Both filter and search present
        assert 'CAST("Status" AS TEXT) = :p0' in where
        assert "ILIKE :search_term" in where
        assert params["p0"] == "Pending"
        assert params["search_term"] == "%BRCA%"
        # They are ANDed together
        assert " AND " in where

    def test_interpolated_mode_no_param_placeholders(self, fetcher):
        """Datum mode: use_params=False → values inlined, no :param markers."""
        from src.config.config_instance import QueryParams
        qp = QueryParams(filters={"Gene_names": ["BRCA1", "TP53"]}, search_term="PAT")
        where, params = fetcher._build_where_clause(qp, use_params=False)

        # No :param placeholders
        assert ":p0" not in where
        assert ":search_term" not in where
        # Values inlined
        assert "'BRCA1'" in where
        assert "'TP53'" in where
        assert "'%PAT%'" in where
        # params dict should be empty for interpolated mode
        assert params == {}

    def test_operator_gt_produces_greater_than(self, fetcher):
        from src.config.config_instance import QueryParams
        qp = QueryParams(filters={"Score": {"op": "gt", "value": "50"}})
        where, params = fetcher._build_where_clause(qp, use_params=True)

        assert '>' in where
        assert params["p0"] == "50"

    def test_not_empty_operator(self, fetcher):
        from src.config.config_instance import QueryParams
        qp = QueryParams(filters={"Comments": {"op": "not_empty"}})
        where, params = fetcher._build_where_clause(qp, use_params=True)

        assert 'IS NOT NULL' in where
        assert '!= :p0' in where
        assert params["p0"] == ""


# =============================================================================
# 15. JS Context-Scoping Transitions
# =============================================================================

class TestJSContextScopingTransitions:
    """Layer 2: Verify that JS initialization functions receive context from
    shiny:value event handlers, enabling multi-tab isolation.

    These tests read the JS source and verify the wiring patterns that ensure
    initHeaderDrag/initColumnResize/initRowSelection get context from the
    shiny:value event target (not bare document queries).
    """

    @pytest.fixture
    def js_dir(self):
        from pathlib import Path
        return Path(__file__).resolve().parent.parent / "src" / "js"

    def test_table_drag_passes_event_target(self, js_dir):
        """shiny:value handler for table_container must capture event.target
        and pass it to initHeaderDrag/initColumnResize."""
        js = (js_dir / "table-drag.js").read_text()

        # Must capture event.target before setTimeout
        assert "var target = event.target" in js
        # Must pass target to init functions
        assert "initHeaderDrag(target)" in js
        assert "initColumnResize(target)" in js

    def test_row_selection_passes_event_target(self, js_dir):
        """shiny:value handler must pass event.target to initRowSelection."""
        js = (js_dir / "row-selection.js").read_text()

        assert "var target = event.target" in js
        assert "initRowSelection(target)" in js

    def test_histogram_passes_event_target(self, js_dir):
        """shiny:value handler must pass event.target to initHistogramCheckboxes."""
        js = (js_dir / "histogram.js").read_text()

        assert "var target = event.target" in js
        assert "initHistogramCheckboxes(target)" in js

    def test_synthesis_uses_context_modal_lookup(self, js_dir):
        """synthesis.js must use findModalInContext, not bare getElementById."""
        js = (js_dir / "synthesis.js").read_text()

        assert "findModalInContext" in js
        # Should NOT have bare getElementById for synthesis-modal
        # (The regex-counted paren inside strings is expected)
        assert 'document.getElementById("synthesis-modal")' not in js

    def test_find_widget_container_scopes_to_tab(self, js_dir):
        """_findWidgetContainer must scope to .tab-pane or .main-container."""
        js = (js_dir / "table-drag.js").read_text()

        assert ".tab-pane" in js
        assert ".main-container" in js
        assert 'el.closest(' in js
