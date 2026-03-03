"""
SQL Golden Snapshot Tests
=========================

Each test pins the EXACT SQL string produced by QueryBuilder and DataFetcher.
If the ground-truth dataset schema does not change and business logic does not
change, these strings must never vary.  Any drift means a regression.

Golden rule: ``assert sql == GOLDEN`` — no fragment matching.
"""

import pytest
from unittest.mock import MagicMock


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  GOLDEN BOOK — QueryBuilder                                              ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

# --- QB1: No filters, clean SELECT ---
GOLDEN_QB1_SQL = (
    'SELECT * FROM "epitopes"."epitopes_data"'
    ' ORDER BY "PatientID_Mutsequence" ASC'
    ' LIMIT :limit OFFSET :offset'
)
GOLDEN_QB1_PARAMS = {"limit": 25, "offset": 0}

# --- QB2: Single = filter ---
GOLDEN_QB2_SQL = (
    'SELECT * FROM "data_table"'
    ' WHERE "Status" = :f0_Status'
    ' ORDER BY "id" ASC'
    ' LIMIT :limit OFFSET :offset'
)
GOLDEN_QB2_PARAMS = {"f0_Status": "Pending", "limit": 25, "offset": 0}

# --- QB3: Stacked filters (=, IN, IS NOT NULL) ---
GOLDEN_QB3_SQL = (
    'SELECT * FROM "data"'
    ' WHERE "Status" = :f0_Status'
    ' AND "Gene_names" IN (:f1_Gene_names_0, :f1_Gene_names_1)'
    ' AND "Comments" IS NOT NULL'
    ' ORDER BY "id" ASC'
    ' LIMIT :limit OFFSET :offset'
)
GOLDEN_QB3_PARAMS = {
    "f0_Status": "Pending",
    "f1_Gene_names_0": "BRCA1",
    "f1_Gene_names_1": "TP53",
    "limit": 25,
    "offset": 0,
}

# --- QB4: Sort ASC / DESC ---
GOLDEN_QB4A_SQL = (
    'SELECT * FROM "data"'
    ' ORDER BY "PatientID" ASC'
    ' LIMIT :limit OFFSET :offset'
)
GOLDEN_QB4B_SQL = (
    'SELECT * FROM "data"'
    ' ORDER BY "PatientID" DESC'
    ' LIMIT :limit OFFSET :offset'
)

# --- QB5: Page offsets ---
GOLDEN_QB5A_PARAMS = {"limit": 25, "offset": 0}
GOLDEN_QB5B_PARAMS = {"limit": 25, "offset": 25}
GOLDEN_QB5C_PARAMS = {"limit": 10, "offset": 20}

# --- QB6: SELECT + COUNT with same filter ---
GOLDEN_QB6_SELECT_SQL = (
    'SELECT * FROM "data"'
    ' WHERE "Status" = :f0_Status'
    ' ORDER BY "id" ASC'
    ' LIMIT :limit OFFSET :offset'
)
GOLDEN_QB6_COUNT_SQL = (
    'SELECT COUNT(*) FROM "data"'
    ' WHERE "Status" = :f0_Status'
)
GOLDEN_QB6_COUNT_PARAMS = {"f0_Status": "Pending"}

# --- QB7: INSERT modification ---
GOLDEN_QB7_SQL = (
    '\n        INSERT INTO "schema"."mods" \n'
    '            (row_pk, column_name, old_value, new_value, mod_type, created_by)\n'
    '        VALUES \n'
    '            (:row_pk, :column_name, :old_value, :new_value, :mod_type, :created_by)\n'
    '        RETURNING id\n'
    '        '
)

# --- QB8: UNDO modification ---
GOLDEN_QB8_SQL = (
    '\n        UPDATE "schema"."mods"\n'
    '        SET undone = TRUE\n'
    '        WHERE id = :mod_id\n'
    '        RETURNING id\n'
    '        '
)

# --- QB9: include_mods_status=True (LATERAL subquery) ---
GOLDEN_QB9_SQL = (
    "\n        SELECT d.*,\n"
    "            COALESCE(\n"
    "                (SELECT m.mod_type \n"
    '                 FROM "schema"."mods" m \n'
    "                 WHERE m.row_pk->>'PatientID_Mutsequence'"
    ' = d."PatientID_Mutsequence"::text\n'
    "                   AND m.undone = FALSE\n"
    "                 ORDER BY m.created_at DESC \n"
    "                 LIMIT 1),\n"
    "                'unprocessed'\n"
    "            ) AS _mod_status,\n"
    "            (SELECT COUNT(*) \n"
    '             FROM "schema"."mods" m \n'
    "             WHERE m.row_pk->>'PatientID_Mutsequence'"
    ' = d."PatientID_Mutsequence"::text\n'
    "               AND m.undone = FALSE\n"
    "               AND m.mod_type = 'field_modification'\n"
    "            ) AS _mod_count\n"
    '        FROM "schema"."data" d\n'
    '         ORDER BY "PatientID_Mutsequence" ASC'
    " LIMIT :limit OFFSET :offset"
)
GOLDEN_QB9_PARAMS = {"limit": 25, "offset": 0}

# --- QB10: include_mods_status=False ---
GOLDEN_QB10_SQL = (
    'SELECT * FROM "schema"."data"'
    ' ORDER BY "PatientID_Mutsequence" ASC'
    ' LIMIT :limit OFFSET :offset'
)
GOLDEN_QB10_PARAMS = {"limit": 25, "offset": 0}

# --- QB_UPSERT: UI state persistence ---
GOLDEN_QB_UPSERT_SQL = (
    "\n        INSERT INTO \"public\".\"ui_state\" \n"
    "            (user_id, session_id, filters, sort_column, sort_ascending, \n"
    "             current_page, rows_per_page, column_preset, updated_at)\n"
    "        VALUES \n"
    "            (:user_id, :session_id, :filters, :sort_column, :sort_ascending,\n"
    "             :current_page, :rows_per_page, :column_preset, NOW())\n"
    "        ON CONFLICT (user_id, session_id) \n"
    "        DO UPDATE SET\n"
    "            filters = EXCLUDED.filters,\n"
    "            sort_column = EXCLUDED.sort_column,\n"
    "            sort_ascending = EXCLUDED.sort_ascending,\n"
    "            current_page = EXCLUDED.current_page,\n"
    "            rows_per_page = EXCLUDED.rows_per_page,\n"
    "            column_preset = EXCLUDED.column_preset,\n"
    "            updated_at = NOW()\n"
    "        "
)

# --- QB_GET_STATE ---
GOLDEN_QB_GET_STATE_SQL = (
    "\n        SELECT * FROM \"public\".\"ui_state\"\n"
    "        WHERE user_id = :user_id AND session_id = :session_id\n"
    "        "
)

# --- QB_GET_MODS ---
GOLDEN_QB_GET_MODS_SQL = (
    '\n        SELECT * FROM "schema"."mods"\n'
    "        WHERE row_pk = :row_pk\n"
    "          AND undone = FALSE\n"
    "        ORDER BY created_at DESC\n"
    "        "
)

# --- QB_L3_INSERT ---
GOLDEN_QB_L3_INSERT_SQL = (
    '\n        INSERT INTO "public"."mods" \n'
    '            (row_pk, column_name, old_value, new_value, mod_type, created_by)\n'
    '        VALUES \n'
    '            (:row_pk, :column_name, :old_value, :new_value, :mod_type, :created_by)\n'
    '        RETURNING id\n'
    '        '
)

# --- QB_L3_FULL: filter + sort + paginate + mods ---
GOLDEN_QB_L3_FULL_SQL = (
    "\n        SELECT d.*,\n"
    "            COALESCE(\n"
    "                (SELECT m.mod_type \n"
    '                 FROM "epi"."modifications" m \n'
    "                 WHERE m.row_pk->>'PatientID_Mutsequence'"
    ' = d."PatientID_Mutsequence"::text\n'
    "                   AND m.undone = FALSE\n"
    "                 ORDER BY m.created_at DESC \n"
    "                 LIMIT 1),\n"
    "                'unprocessed'\n"
    "            ) AS _mod_status,\n"
    "            (SELECT COUNT(*) \n"
    '             FROM "epi"."modifications" m \n'
    "             WHERE m.row_pk->>'PatientID_Mutsequence'"
    ' = d."PatientID_Mutsequence"::text\n'
    "               AND m.undone = FALSE\n"
    "               AND m.mod_type = 'field_modification'\n"
    "            ) AS _mod_count\n"
    '        FROM "epi"."epitopes_data" d\n'
    '         WHERE "Gene_names" IN (:f0_Gene_names_0, :f0_Gene_names_1)'
    ' AND "Status" ILIKE :f1_Status'
    ' ORDER BY "PatientID" DESC'
    " LIMIT :limit OFFSET :offset"
)
GOLDEN_QB_L3_FULL_PARAMS = {
    "f0_Gene_names_0": "BRCA1",
    "f0_Gene_names_1": "TP53",
    "f1_Status": "%Pend%",
    "limit": 25,
    "offset": 50,
}
GOLDEN_QB_L3_FULL_COUNT_SQL = (
    'SELECT COUNT(*) FROM "epi"."epitopes_data"'
    ' WHERE "Gene_names" IN (:f0_Gene_names_0, :f0_Gene_names_1)'
    ' AND "Status" ILIKE :f1_Status'
)
GOLDEN_QB_L3_FULL_COUNT_PARAMS = {
    "f0_Gene_names_0": "BRCA1",
    "f0_Gene_names_1": "TP53",
    "f1_Status": "%Pend%",
}


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  GOLDEN BOOK — DataFetcher WHERE clauses                                 ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

GOLDEN_DF1_WHERE = ""
GOLDEN_DF1_PARAMS = {}

GOLDEN_DF2_WHERE = ' WHERE CAST("Status" AS TEXT) = :p0'
GOLDEN_DF2_PARAMS = {"p0": "Pending"}

GOLDEN_DF3_WHERE = ' WHERE CAST("Gene_names" AS TEXT) IN (:p0, :p1)'
GOLDEN_DF3_PARAMS = {"p0": "BRCA1", "p1": "TP53"}

GOLDEN_DF4_WHERE = ' WHERE CAST("Gene_names" AS TEXT) NOT ILIKE :p0'
GOLDEN_DF4_PARAMS = {"p0": "%BRCA%"}

GOLDEN_DF5_WHERE = ' WHERE CAST("Gene_names" AS TEXT) BETWEEN :p0 AND :p1'
GOLDEN_DF5_PARAMS = {"p0": "A", "p1": "M"}

GOLDEN_DF6_WHERE = ' WHERE CAST("Gene_names" AS TEXT) ~* :p0'
GOLDEN_DF6_PARAMS = {"p0": "^TP"}

GOLDEN_DF7_WHERE = (
    ' WHERE (CAST("Gene_names" AS TEXT) ILIKE :search_term'
    ' OR CAST("Status" AS TEXT) ILIKE :search_term)'
)
GOLDEN_DF7_PARAMS = {"search_term": "%PAT%"}

GOLDEN_DF8_WHERE = ' WHERE (CAST("Gene_names" AS TEXT) ILIKE :search_term)'
GOLDEN_DF8_PARAMS = {"search_term": "%TP53%"}

GOLDEN_DF9_WHERE = (
    ' WHERE CAST("Status" AS TEXT) = :p0'
    ' AND (CAST("Gene_names" AS TEXT) ILIKE :search_term'
    ' OR CAST("Status" AS TEXT) ILIKE :search_term)'
)
GOLDEN_DF9_PARAMS = {"p0": "Pending", "search_term": "%BRCA%"}

GOLDEN_DF10_WHERE = (
    " WHERE CAST(\"Gene_names\" AS TEXT) IN ('BRCA1', 'TP53')"
    " AND (CAST(\"Gene_names\" AS TEXT) ILIKE '%PAT%'"
    " OR CAST(\"Status\" AS TEXT) ILIKE '%PAT%')"
)
GOLDEN_DF10_PARAMS = {}

GOLDEN_DF11_WHERE = ' WHERE CAST("Score" AS TEXT) > :p0'
GOLDEN_DF11_PARAMS = {"p0": "50"}

GOLDEN_DF12_WHERE = ' WHERE ("Comments" IS NOT NULL AND CAST("Comments" AS TEXT) != :p0)'
GOLDEN_DF12_PARAMS = {"p0": ""}

GOLDEN_DF13_WHERE_PARAM = ' WHERE CAST("Gene_names" AS TEXT) ILIKE :p0'
GOLDEN_DF13_PARAMS = {"p0": "%BRC%"}
GOLDEN_DF13_WHERE_INTERP = " WHERE CAST(\"Gene_names\" AS TEXT) ILIKE '%BRC%'"
GOLDEN_DF13_PARAMS_INTERP = {}

GOLDEN_DF14_WHERE = (
    ' WHERE CAST("Gene_names" AS TEXT) NOT ILIKE :p0'
    ' AND CAST("Status" AS TEXT) IN (:p1, :p2)'
    ' AND ("Comments" IS NOT NULL AND CAST("Comments" AS TEXT) != :p3)'
    ' AND (CAST("PatientID" AS TEXT) ILIKE :search_term)'
)
GOLDEN_DF14_PARAMS = {
    "p0": "%BRCA%",
    "p1": "Pending",
    "p2": "Reviewed",
    "p3": "",
    "search_term": "%PAT%",
}

GOLDEN_DF15_STATUS_ALL = ""
GOLDEN_DF15_STATUS_SUB = " AND _mod_status IN ('unprocessed', 'edited')"

GOLDEN_DF16_STEP1_WHERE = ' WHERE CAST("Gene_names" AS TEXT) IN (:p0, :p1)'
GOLDEN_DF16_STEP1_PARAMS = {"p0": "BRCA1", "p1": "TP53"}
GOLDEN_DF16_STEP2_WHERE = (
    ' WHERE CAST("Gene_names" AS TEXT) IN (:p0, :p1)'
    ' AND (CAST("Gene_names" AS TEXT) ILIKE :search_term'
    ' OR CAST("Status" AS TEXT) ILIKE :search_term)'
)
GOLDEN_DF16_STEP2_PARAMS = {"p0": "BRCA1", "p1": "TP53", "search_term": "%PAT001%"}


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  GOLDEN BOOK — Edit/Undo DB call arguments                               ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

# perform_cell_edit(row=1, Gene_names, TP53 -> TP53_mut)
GOLDEN_EDIT_UPDATE_ARGS = ({"PatientID_Mutsequence": "PK002"}, "Gene_names", "TP53_mut")
GOLDEN_EDIT_INSERT_ARGS = (
    {"PatientID_Mutsequence": "PK002"},
    "Gene_names",
    "TP53",       # old_value
    "TP53_mut",   # new_value
    "field_modification",
)

# perform_undo for above edit
GOLDEN_UNDO_REVERT_ARGS = ({"PatientID_Mutsequence": "PK002"}, "Gene_names", "TP53")
GOLDEN_UNDO_INSERT_ARGS_MOD_TYPE = "undo"


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def fetcher():
    """Standard DataFetcher stub with 2 searchable columns."""
    from src.config.config_instance import DataFetcher

    f = DataFetcher.__new__(DataFetcher)
    f.app_config = MagicMock()
    f.app_config.query.searchable_columns = ["Gene_names", "Status"]
    f._columns = ["PatientID_Mutsequence", "PatientID", "Gene_names", "Status"]
    f._column_types = {}
    f._engine = None
    f._datum_client = None
    f._total_count = 0
    return f


@pytest.fixture
def fetcher_3col():
    """DataFetcher stub with 3 searchable columns and Comments."""
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


@pytest.fixture
def edit_df():
    """5-row DataFrame for edit lifecycle tests."""
    import pandas as pd
    return pd.DataFrame({
        "PatientID_Mutsequence": ["PK001", "PK002", "PK003", "PK004", "PK005"],
        "PatientID": ["PAT001", "PAT002", "PAT003", "PAT004", "PAT005"],
        "Gene_names": ["BRCA1", "TP53", "EGFR", "PTEN", "RB1"],
        "Variant_key": ["VAR_001", "VAR_002", "VAR_003", "VAR_004", "VAR_005"],
        "Status": ["Pending", "Reviewed", "Pending", "Approved", "Pending"],
        "Comments": ["", "Needs review", "", "Good", ""],
    })


@pytest.fixture
def mock_ci():
    """Mock ConfigInstance for edit/undo pipeline tests."""
    ci = MagicMock()
    ci.app_config.table.primary_key = ["PatientID_Mutsequence"]
    ci.update_data_in_db.return_value = True
    ci.save_modification_to_db.return_value = 999
    ci.mark_modification_undone_in_db.return_value = True
    return ci


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║   TEST CLASS: QueryBuilder Snapshots                                      ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

class TestQueryBuilderGoldenSnapshots:
    """Every assertion is ``== GOLDEN`` — exact string, no fragments."""

    def test_qb1_no_filters_clean_select(self):
        from src.db.query_builder import QueryBuilder
        qb = QueryBuilder("epitopes.epitopes_data", "epitopes.modifications", ["PatientID_Mutsequence"])
        sql, params = qb.build_select_query(filters=[], sort=None, page=1, limit=25, include_mods_status=False)
        assert sql == GOLDEN_QB1_SQL
        assert params == GOLDEN_QB1_PARAMS

    def test_qb2_single_equals_filter(self):
        from src.db.query_builder import QueryBuilder, FilterCondition
        qb = QueryBuilder("data_table", "mods_table", ["id"])
        sql, params = qb.build_select_query(
            filters=[FilterCondition("Status", "=", "Pending")],
            include_mods_status=False,
        )
        assert sql == GOLDEN_QB2_SQL
        assert params == GOLDEN_QB2_PARAMS

    def test_qb3_stacked_filters_and_chain(self):
        from src.db.query_builder import QueryBuilder, FilterCondition
        qb = QueryBuilder("data", "mods", ["id"])
        filters = [
            FilterCondition("Status", "=", "Pending"),
            FilterCondition("Gene_names", "IN", ["BRCA1", "TP53"]),
            FilterCondition("Comments", "IS NOT NULL"),
        ]
        sql, params = qb.build_select_query(filters=filters, include_mods_status=False)
        assert sql == GOLDEN_QB3_SQL
        assert params == GOLDEN_QB3_PARAMS

    def test_qb4_sort_asc_vs_desc(self):
        from src.db.query_builder import QueryBuilder, SortConfig
        qb = QueryBuilder("data", "mods", ["id"])
        sql_asc, _ = qb.build_select_query(sort=SortConfig("PatientID", True), include_mods_status=False)
        sql_desc, _ = qb.build_select_query(sort=SortConfig("PatientID", False), include_mods_status=False)
        assert sql_asc == GOLDEN_QB4A_SQL
        assert sql_desc == GOLDEN_QB4B_SQL

    def test_qb5_page_offset_progression(self):
        from src.db.query_builder import QueryBuilder
        qb = QueryBuilder("data", "mods", ["id"])
        _, p1 = qb.build_select_query(page=1, limit=25, include_mods_status=False)
        _, p2 = qb.build_select_query(page=2, limit=25, include_mods_status=False)
        _, p3 = qb.build_select_query(page=3, limit=10, include_mods_status=False)
        assert p1 == GOLDEN_QB5A_PARAMS
        assert p2 == GOLDEN_QB5B_PARAMS
        assert p3 == GOLDEN_QB5C_PARAMS

    def test_qb6_count_mirrors_select_filter(self):
        from src.db.query_builder import QueryBuilder, FilterCondition
        qb = QueryBuilder("data", "mods", ["id"])
        filters = [FilterCondition("Status", "=", "Pending")]
        sql_sel, _ = qb.build_select_query(filters=filters, include_mods_status=False)
        sql_cnt, p_cnt = qb.build_count_query(filters=filters)
        assert sql_sel == GOLDEN_QB6_SELECT_SQL
        assert sql_cnt == GOLDEN_QB6_COUNT_SQL
        assert p_cnt == GOLDEN_QB6_COUNT_PARAMS

    def test_qb7_insert_modification(self):
        from src.db.query_builder import QueryBuilder
        qb = QueryBuilder("schema.data", "schema.mods", ["PatientID_Mutsequence"])
        sql = qb.build_insert_modification()
        assert sql == GOLDEN_QB7_SQL

    def test_qb8_undo_modification(self):
        from src.db.query_builder import QueryBuilder
        qb = QueryBuilder("data", "schema.mods", ["id"])
        sql = qb.build_undo_modification()
        assert sql == GOLDEN_QB8_SQL

    def test_qb9_include_mods_status_lateral_join(self):
        from src.db.query_builder import QueryBuilder
        qb = QueryBuilder("schema.data", "schema.mods", ["PatientID_Mutsequence"])
        sql, params = qb.build_select_query(include_mods_status=True)
        assert sql == GOLDEN_QB9_SQL
        assert params == GOLDEN_QB9_PARAMS

    def test_qb10_no_mods_status(self):
        from src.db.query_builder import QueryBuilder
        qb = QueryBuilder("schema.data", "schema.mods", ["PatientID_Mutsequence"])
        sql, params = qb.build_select_query(include_mods_status=False)
        assert sql == GOLDEN_QB10_SQL
        assert params == GOLDEN_QB10_PARAMS

    def test_qb_upsert_state(self):
        from src.db.query_builder import QueryBuilder
        qb = QueryBuilder("data", "mods", ["id"])
        sql = qb.build_upsert_state("public.ui_state")
        assert sql == GOLDEN_QB_UPSERT_SQL

    def test_qb_get_state(self):
        from src.db.query_builder import QueryBuilder
        qb = QueryBuilder("data", "mods", ["id"])
        sql = qb.build_get_state("public.ui_state")
        assert sql == GOLDEN_QB_GET_STATE_SQL

    def test_qb_get_modifications_for_row(self):
        from src.db.query_builder import QueryBuilder
        qb = QueryBuilder("schema.data", "schema.mods", ["PatientID_Mutsequence"])
        sql = qb.build_get_modifications_for_row()
        assert sql == GOLDEN_QB_GET_MODS_SQL

    def test_qb_l3_insert_modification(self):
        from src.db.query_builder import QueryBuilder
        qb = QueryBuilder("public.data", "public.mods", ["PatientID_Mutsequence"])
        sql = qb.build_insert_modification()
        assert sql == GOLDEN_QB_L3_INSERT_SQL

    def test_qb_l3_full_filter_sort_paginate_mods(self):
        from src.db.query_builder import QueryBuilder, FilterCondition, SortConfig
        qb = QueryBuilder("epi.epitopes_data", "epi.modifications", ["PatientID_Mutsequence"])
        filters = [
            FilterCondition("Gene_names", "IN", ["BRCA1", "TP53"]),
            FilterCondition("Status", "ILIKE", "Pend"),
        ]
        sort = SortConfig("PatientID", ascending=False)
        sql, params = qb.build_select_query(
            filters=filters, sort=sort, page=3, limit=25, include_mods_status=True,
        )
        assert sql == GOLDEN_QB_L3_FULL_SQL
        assert params == GOLDEN_QB_L3_FULL_PARAMS

    def test_qb_l3_full_count_query(self):
        from src.db.query_builder import QueryBuilder, FilterCondition
        qb = QueryBuilder("epi.epitopes_data", "epi.modifications", ["PatientID_Mutsequence"])
        filters = [
            FilterCondition("Gene_names", "IN", ["BRCA1", "TP53"]),
            FilterCondition("Status", "ILIKE", "Pend"),
        ]
        sql, params = qb.build_count_query(filters=filters)
        assert sql == GOLDEN_QB_L3_FULL_COUNT_SQL
        assert params == GOLDEN_QB_L3_FULL_COUNT_PARAMS


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║   TEST CLASS: DataFetcher WHERE Clause Snapshots                          ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

class TestDataFetcherWhereClauseGoldenSnapshots:
    """Pin every WHERE clause string — exact match, no fragments."""

    def test_df1_empty_params_no_where(self, fetcher):
        from src.config.config_instance import QueryParams
        where, params = fetcher._build_where_clause(QueryParams())
        assert where == GOLDEN_DF1_WHERE
        assert params == GOLDEN_DF1_PARAMS

    def test_df2_simple_equals(self, fetcher):
        from src.config.config_instance import QueryParams
        where, params = fetcher._build_where_clause(
            QueryParams(filters={"Status": "Pending"}), use_params=True)
        assert where == GOLDEN_DF2_WHERE
        assert params == GOLDEN_DF2_PARAMS

    def test_df3_list_in_clause(self, fetcher):
        from src.config.config_instance import QueryParams
        where, params = fetcher._build_where_clause(
            QueryParams(filters={"Gene_names": ["BRCA1", "TP53"]}), use_params=True)
        assert where == GOLDEN_DF3_WHERE
        assert params == GOLDEN_DF3_PARAMS

    def test_df4_not_contains(self, fetcher):
        from src.config.config_instance import QueryParams
        where, params = fetcher._build_where_clause(
            QueryParams(filters={"Gene_names": {"op": "not_contains", "value": "BRCA"}}),
            use_params=True)
        assert where == GOLDEN_DF4_WHERE
        assert params == GOLDEN_DF4_PARAMS

    def test_df5_between(self, fetcher):
        from src.config.config_instance import QueryParams
        where, params = fetcher._build_where_clause(
            QueryParams(filters={"Gene_names": {"op": "between", "value": ["A", "M"]}}),
            use_params=True)
        assert where == GOLDEN_DF5_WHERE
        assert params == GOLDEN_DF5_PARAMS

    def test_df5_between_both_null(self, fetcher):
        """Both bounds None → no WHERE clause at all."""
        from src.config.config_instance import QueryParams
        where, params = fetcher._build_where_clause(
            QueryParams(filters={"Gene_names": {"op": "between", "value": [None, None]}}),
            use_params=True)
        assert where == ""
        assert params == {}

    def test_df5_between_lower_only(self, fetcher):
        """Only lower bound → >= clause."""
        from src.config.config_instance import QueryParams
        where, params = fetcher._build_where_clause(
            QueryParams(filters={"Gene_names": {"op": "between", "value": ["A", None]}}),
            use_params=True)
        assert where == ' WHERE CAST("Gene_names" AS TEXT) >= :p0'
        assert params == {"p0": "A"}

    def test_df5_between_upper_only(self, fetcher):
        """Only upper bound → <= clause."""
        from src.config.config_instance import QueryParams
        where, params = fetcher._build_where_clause(
            QueryParams(filters={"Gene_names": {"op": "between", "value": [None, "M"]}}),
            use_params=True)
        assert where == ' WHERE CAST("Gene_names" AS TEXT) <= :p0'
        assert params == {"p0": "M"}

    def test_df5_between_empty_strings(self, fetcher):
        """Empty strings treated as null bounds."""
        from src.config.config_instance import QueryParams
        where, params = fetcher._build_where_clause(
            QueryParams(filters={"Gene_names": {"op": "between", "value": ["", ""]}}),
            use_params=True)
        assert where == ""
        assert params == {}

    def test_df6_regex(self, fetcher):
        from src.config.config_instance import QueryParams
        where, params = fetcher._build_where_clause(
            QueryParams(filters={"Gene_names": {"op": "regex", "value": "^TP"}}),
            use_params=True)
        assert where == GOLDEN_DF6_WHERE
        assert params == GOLDEN_DF6_PARAMS

    def test_df7_search_all_columns(self, fetcher):
        from src.config.config_instance import QueryParams
        where, params = fetcher._build_where_clause(
            QueryParams(search_term="PAT"), use_params=True)
        assert where == GOLDEN_DF7_WHERE
        assert params == GOLDEN_DF7_PARAMS

    def test_df8_search_specific_column(self, fetcher):
        from src.config.config_instance import QueryParams
        where, params = fetcher._build_where_clause(
            QueryParams(search_term="TP53", search_column="Gene_names"), use_params=True)
        assert where == GOLDEN_DF8_WHERE
        assert params == GOLDEN_DF8_PARAMS

    def test_df9_filter_plus_search(self, fetcher):
        from src.config.config_instance import QueryParams
        where, params = fetcher._build_where_clause(
            QueryParams(filters={"Status": "Pending"}, search_term="BRCA"),
            use_params=True)
        assert where == GOLDEN_DF9_WHERE
        assert params == GOLDEN_DF9_PARAMS

    def test_df10_interpolated_mode(self, fetcher):
        from src.config.config_instance import QueryParams
        where, params = fetcher._build_where_clause(
            QueryParams(filters={"Gene_names": ["BRCA1", "TP53"]}, search_term="PAT"),
            use_params=False)
        assert where == GOLDEN_DF10_WHERE
        assert params == GOLDEN_DF10_PARAMS

    def test_df11_gt_operator(self, fetcher):
        from src.config.config_instance import QueryParams
        where, params = fetcher._build_where_clause(
            QueryParams(filters={"Score": {"op": "gt", "value": "50"}}), use_params=True)
        assert where == GOLDEN_DF11_WHERE
        assert params == GOLDEN_DF11_PARAMS

    def test_df12_not_empty(self, fetcher):
        from src.config.config_instance import QueryParams
        where, params = fetcher._build_where_clause(
            QueryParams(filters={"Comments": {"op": "not_empty"}}), use_params=True)
        assert where == GOLDEN_DF12_WHERE
        assert params == GOLDEN_DF12_PARAMS

    def test_df13_contains_param_vs_interpolated(self, fetcher):
        from src.config.config_instance import QueryParams
        qp = QueryParams(filters={"Gene_names": {"op": "contains", "value": "BRC"}})
        w_p, p_p = fetcher._build_where_clause(qp, use_params=True)
        assert w_p == GOLDEN_DF13_WHERE_PARAM
        assert p_p == GOLDEN_DF13_PARAMS
        w_i, p_i = fetcher._build_where_clause(qp, use_params=False)
        assert w_i == GOLDEN_DF13_WHERE_INTERP
        assert p_i == GOLDEN_DF13_PARAMS_INTERP

    def test_df14_complex_multi_filter(self, fetcher_3col):
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
        where, params = fetcher_3col._build_where_clause(qp, use_params=True)
        assert where == GOLDEN_DF14_WHERE
        assert params == GOLDEN_DF14_PARAMS

    def test_df15_status_filter_all_vs_subset(self, fetcher):
        from src.config.config_instance import QueryParams
        clause_all = fetcher._build_status_filter_clause(
            QueryParams(status_filters=["unprocessed", "edited", "approved", "rejected"]))
        assert clause_all == GOLDEN_DF15_STATUS_ALL

        clause_sub = fetcher._build_status_filter_clause(
            QueryParams(status_filters=["unprocessed", "edited"]))
        assert clause_sub == GOLDEN_DF15_STATUS_SUB

    def test_df16_column_filter_then_search_progression(self, fetcher):
        from src.config.config_instance import QueryParams
        # Step 1: column filter only
        w1, p1 = fetcher._build_where_clause(
            QueryParams(filters={"Gene_names": ["BRCA1", "TP53"]}))
        assert w1 == GOLDEN_DF16_STEP1_WHERE
        assert p1 == GOLDEN_DF16_STEP1_PARAMS
        # Step 2: add search
        w2, p2 = fetcher._build_where_clause(
            QueryParams(filters={"Gene_names": ["BRCA1", "TP53"]}, search_term="PAT001"))
        assert w2 == GOLDEN_DF16_STEP2_WHERE
        assert p2 == GOLDEN_DF16_STEP2_PARAMS


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║   TEST CLASS: Edit/Undo Pipeline DB Call Arg Snapshots                    ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

class TestEditUndoPipelineGoldenSnapshots:
    """Pin the exact arguments passed to config_instance DB methods."""

    def test_cell_edit_update_args(self, edit_df, mock_ci):
        from src.utils.data_operations import perform_cell_edit
        perform_cell_edit(
            edit_df, [], 1, "Gene_names", "TP53", "TP53_mut",
            config_instance=mock_ci)
        args = mock_ci.update_data_in_db.call_args[0]
        assert args == GOLDEN_EDIT_UPDATE_ARGS

    def test_cell_edit_save_modification_args(self, edit_df, mock_ci):
        from src.utils.data_operations import perform_cell_edit
        perform_cell_edit(
            edit_df, [], 1, "Gene_names", "TP53", "TP53_mut",
            config_instance=mock_ci)
        args = mock_ci.save_modification_to_db.call_args[0]
        assert args == GOLDEN_EDIT_INSERT_ARGS

    def test_undo_revert_args(self, edit_df, mock_ci):
        from src.utils.data_operations import perform_cell_edit, perform_undo
        _, log = perform_cell_edit(
            edit_df, [], 1, "Gene_names", "TP53", "TP53_mut",
            config_instance=mock_ci)
        mock_ci.reset_mock()
        df_copy = edit_df.copy()
        df_copy.iloc[1, df_copy.columns.get_loc("Gene_names")] = "TP53_mut"
        perform_undo(df_copy, log, 0, config_instance=mock_ci)
        args = mock_ci.update_data_in_db.call_args[0]
        assert args == GOLDEN_UNDO_REVERT_ARGS

    def test_undo_insert_record_type(self, edit_df, mock_ci):
        from src.utils.data_operations import perform_cell_edit, perform_undo
        _, log = perform_cell_edit(
            edit_df, [], 1, "Gene_names", "TP53", "TP53_mut",
            config_instance=mock_ci)
        mock_ci.reset_mock()
        df_copy = edit_df.copy()
        df_copy.iloc[1, df_copy.columns.get_loc("Gene_names")] = "TP53_mut"
        perform_undo(df_copy, log, 0, config_instance=mock_ci)
        mod_type = mock_ci.save_modification_to_db.call_args[0][4]
        assert mod_type == GOLDEN_UNDO_INSERT_ARGS_MOD_TYPE

    def test_multi_edit_sequential_pks(self, edit_df, mock_ci):
        """Three edits → exact PK sequence in update_data_in_db calls."""
        from src.utils.data_operations import perform_cell_edit
        log = []
        df, log = perform_cell_edit(edit_df, log, 0, "Gene_names", "BRCA1", "BRCA1x", config_instance=mock_ci)
        df, log = perform_cell_edit(df, log, 1, "Status", "Reviewed", "Done", config_instance=mock_ci)
        df, log = perform_cell_edit(df, log, 2, "Gene_names", "EGFR", "EGFRx", config_instance=mock_ci)

        calls = mock_ci.update_data_in_db.call_args_list
        assert calls[0][0] == ({"PatientID_Mutsequence": "PK001"}, "Gene_names", "BRCA1x")
        assert calls[1][0] == ({"PatientID_Mutsequence": "PK002"}, "Status", "Done")
        assert calls[2][0] == ({"PatientID_Mutsequence": "PK003"}, "Gene_names", "EGFRx")
