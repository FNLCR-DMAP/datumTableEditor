#!/usr/bin/env python3
"""
Extract all deterministic SQL strings from QueryBuilder and DataFetcher.

Produces a golden reference JSON at qcmetric/sql_golden.json containing every
SQL string the system can produce, organized by generator (QueryBuilder vs
DataFetcher) and scenario.  The test suite test_sql_golden.py pins these
exact strings — if anything drifts, the snapshot tests will catch it.

Usage:
    python tooling/src/sql/extract_golden_sql.py          # writes qcmetric/sql_golden.json
    python tooling/src/sql/extract_golden_sql.py --print   # also dumps to stdout
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.db.query_builder import QueryBuilder, FilterCondition, SortConfig
from src.config.config_instance import DataFetcher, QueryParams


# =====================================================================
# Helpers
# =====================================================================

def _make_fetcher(searchable=None, columns=None):
    """Build a DataFetcher stub without a real DB connection."""
    f = DataFetcher.__new__(DataFetcher)
    f.app_config = MagicMock()
    f.app_config.query.searchable_columns = searchable or ["Gene_names", "Status"]
    f.app_config.database.status_column = None
    f._columns = columns or [
        "PatientID_Mutsequence", "PatientID", "Gene_names", "Status",
    ]
    f._engine = None
    f._datum_client = None
    f._total_count = 0
    return f


# =====================================================================
# QueryBuilder scenarios
# =====================================================================

def extract_query_builder() -> dict[str, Any]:
    """Return every QueryBuilder scenario as {name: {sql, params}}."""
    book: dict[str, Any] = {}

    # QB1 — no filters, clean SELECT
    qb = QueryBuilder("epitopes.epitopes_data", "epitopes.modifications", ["PatientID_Mutsequence"])
    sql, p = qb.build_select_query(filters=[], sort=None, page=1, limit=25, include_mods_status=False)
    book["no_filters_clean_select"] = {"sql": sql, "params": p}

    # QB2 — single = filter
    qb = QueryBuilder("data_table", "mods_table", ["id"])
    sql, p = qb.build_select_query(
        filters=[FilterCondition("Status", "=", "Pending")],
        include_mods_status=False,
    )
    book["single_equals_filter"] = {"sql": sql, "params": p}

    # QB3 — stacked AND chain
    qb = QueryBuilder("data", "mods", ["id"])
    sql, p = qb.build_select_query(
        filters=[
            FilterCondition("Status", "=", "Pending"),
            FilterCondition("Gene_names", "IN", ["BRCA1", "TP53"]),
            FilterCondition("Comments", "IS NOT NULL"),
        ],
        include_mods_status=False,
    )
    book["stacked_and_chain"] = {"sql": sql, "params": p}

    # QB4 — sort ASC / DESC
    qb = QueryBuilder("data", "mods", ["id"])
    sql_asc, p_asc = qb.build_select_query(sort=SortConfig("PatientID", True), include_mods_status=False)
    sql_desc, p_desc = qb.build_select_query(sort=SortConfig("PatientID", False), include_mods_status=False)
    book["sort_asc"] = {"sql": sql_asc, "params": p_asc}
    book["sort_desc"] = {"sql": sql_desc, "params": p_desc}

    # QB5 — page offsets
    qb = QueryBuilder("data", "mods", ["id"])
    _, p1 = qb.build_select_query(page=1, limit=25, include_mods_status=False)
    _, p2 = qb.build_select_query(page=2, limit=25, include_mods_status=False)
    _, p3 = qb.build_select_query(page=3, limit=10, include_mods_status=False)
    book["page_1"] = {"params": p1}
    book["page_2"] = {"params": p2}
    book["page_3"] = {"params": p3}

    # QB6 — SELECT + COUNT with same filter
    qb = QueryBuilder("data", "mods", ["id"])
    flt = [FilterCondition("Status", "=", "Pending")]
    sql_sel, p_sel = qb.build_select_query(filters=flt, include_mods_status=False)
    sql_cnt, p_cnt = qb.build_count_query(filters=flt)
    book["select_with_filter"] = {"sql": sql_sel, "params": p_sel}
    book["count_with_filter"] = {"sql": sql_cnt, "params": p_cnt}

    # QB7 — INSERT modification
    qb = QueryBuilder("schema.data", "schema.mods", ["PatientID_Mutsequence"])
    book["insert_modification"] = {"sql": qb.build_insert_modification()}

    # QB8 — UNDO modification
    qb = QueryBuilder("data", "schema.mods", ["id"])
    book["undo_modification"] = {"sql": qb.build_undo_modification()}

    # QB9 — include_mods_status=True (LATERAL subquery)
    qb = QueryBuilder("schema.data", "schema.mods", ["PatientID_Mutsequence"])
    sql, p = qb.build_select_query(include_mods_status=True)
    book["lateral_join_mods_status"] = {"sql": sql, "params": p}

    # QB10 — include_mods_status=False
    sql, p = qb.build_select_query(include_mods_status=False)
    book["no_mods_status"] = {"sql": sql, "params": p}

    # UPSERT state
    qb = QueryBuilder("data", "mods", ["id"])
    book["upsert_state"] = {"sql": qb.build_upsert_state("public.ui_state")}

    # GET state
    book["get_state"] = {"sql": qb.build_get_state("public.ui_state")}

    # GET modifications for row
    qb = QueryBuilder("schema.data", "schema.mods", ["PatientID_Mutsequence"])
    book["get_modifications_for_row"] = {"sql": qb.build_get_modifications_for_row()}

    # Full composition: filter + sort + paginate + mods
    qb = QueryBuilder("epi.epitopes_data", "epi.modifications", ["PatientID_Mutsequence"])
    filters = [
        FilterCondition("Gene_names", "IN", ["BRCA1", "TP53"]),
        FilterCondition("Status", "ILIKE", "Pend"),
    ]
    sort = SortConfig("PatientID", ascending=False)
    sql, p = qb.build_select_query(filters=filters, sort=sort, page=3, limit=25, include_mods_status=True)
    book["full_filter_sort_paginate_mods"] = {"sql": sql, "params": p}
    sql_c, p_c = qb.build_count_query(filters=filters)
    book["full_filter_count"] = {"sql": sql_c, "params": p_c}

    # INSERT for public schema
    qb = QueryBuilder("public.data", "public.mods", ["PatientID_Mutsequence"])
    book["insert_modification_public"] = {"sql": qb.build_insert_modification()}

    return book


# =====================================================================
# DataFetcher WHERE clause scenarios
# =====================================================================

def extract_data_fetcher_where() -> dict[str, Any]:
    """Return every DataFetcher WHERE clause scenario."""
    book: dict[str, Any] = {}
    f = _make_fetcher()

    # DF1 — empty
    w, p = f._build_where_clause(QueryParams())
    book["empty_params"] = {"where": w, "params": p}

    # DF2 — simple equals
    w, p = f._build_where_clause(QueryParams(filters={"Status": "Pending"}), use_params=True)
    book["simple_equals"] = {"where": w, "params": p}

    # DF3 — list IN
    w, p = f._build_where_clause(QueryParams(filters={"Gene_names": ["BRCA1", "TP53"]}), use_params=True)
    book["list_in"] = {"where": w, "params": p}

    # DF4 — not_contains
    w, p = f._build_where_clause(
        QueryParams(filters={"Gene_names": {"op": "not_contains", "value": "BRCA"}}), use_params=True)
    book["not_contains"] = {"where": w, "params": p}

    # DF5 — between
    w, p = f._build_where_clause(
        QueryParams(filters={"Gene_names": {"op": "between", "value": ["A", "M"]}}), use_params=True)
    book["between"] = {"where": w, "params": p}

    # DF6 — regex
    w, p = f._build_where_clause(
        QueryParams(filters={"Gene_names": {"op": "regex", "value": "^TP"}}), use_params=True)
    book["regex"] = {"where": w, "params": p}

    # DF7 — search all columns
    w, p = f._build_where_clause(QueryParams(search_term="PAT"), use_params=True)
    book["search_all_columns"] = {"where": w, "params": p}

    # DF8 — search specific column
    w, p = f._build_where_clause(
        QueryParams(search_term="TP53", search_column="Gene_names"), use_params=True)
    book["search_specific_column"] = {"where": w, "params": p}

    # DF9 — filter + search
    w, p = f._build_where_clause(
        QueryParams(filters={"Status": "Pending"}, search_term="BRCA"), use_params=True)
    book["filter_plus_search"] = {"where": w, "params": p}

    # DF10 — interpolated (Datum mode)
    w, p = f._build_where_clause(
        QueryParams(filters={"Gene_names": ["BRCA1", "TP53"]}, search_term="PAT"), use_params=False)
    book["interpolated_mode"] = {"where": w, "params": p}

    # DF11 — gt
    w, p = f._build_where_clause(
        QueryParams(filters={"Score": {"op": "gt", "value": "50"}}), use_params=True)
    book["gt_operator"] = {"where": w, "params": p}

    # DF12 — not_empty
    w, p = f._build_where_clause(
        QueryParams(filters={"Comments": {"op": "not_empty"}}), use_params=True)
    book["not_empty"] = {"where": w, "params": p}

    # DF13 — contains (both modes)
    qp = QueryParams(filters={"Gene_names": {"op": "contains", "value": "BRC"}})
    w_p, p_p = f._build_where_clause(qp, use_params=True)
    w_i, p_i = f._build_where_clause(qp, use_params=False)
    book["contains_parameterized"] = {"where": w_p, "params": p_p}
    book["contains_interpolated"] = {"where": w_i, "params": p_i}

    # DF14 — complex multi-filter (3 searchable cols)
    f2 = _make_fetcher(
        searchable=["Gene_names", "Status", "PatientID"],
        columns=["PatientID_Mutsequence", "PatientID", "Gene_names", "Status", "Comments"],
    )
    w, p = f2._build_where_clause(
        QueryParams(
            filters={
                "Gene_names": {"op": "not_contains", "value": "BRCA"},
                "Status": ["Pending", "Reviewed"],
                "Comments": {"op": "not_empty"},
            },
            search_term="PAT",
            search_column="PatientID",
        ),
        use_params=True,
    )
    book["complex_multi_filter"] = {"where": w, "params": p}

    # DF15 — status filter
    clause_all = f._build_status_filter_clause(
        QueryParams(status_filters=["unprocessed", "edited", "approved", "rejected"]))
    clause_sub = f._build_status_filter_clause(
        QueryParams(status_filters=["unprocessed", "edited"]))
    book["status_filter_all"] = {"clause": clause_all}
    book["status_filter_subset"] = {"clause": clause_sub}

    # DF16 — progression: filter then search
    w1, p1 = f._build_where_clause(QueryParams(filters={"Gene_names": ["BRCA1", "TP53"]}))
    w2, p2 = f._build_where_clause(
        QueryParams(filters={"Gene_names": ["BRCA1", "TP53"]}, search_term="PAT001"))
    book["progression_step1_filter_only"] = {"where": w1, "params": p1}
    book["progression_step2_filter_plus_search"] = {"where": w2, "params": p2}

    return book


# =====================================================================
# Main
# =====================================================================

def extract_all() -> dict[str, Any]:
    """Run all extractions and return the full golden book."""
    return {
        "_meta": {
            "description": "Golden SQL strings extracted from QueryBuilder and DataFetcher. "
                           "Any change here means a potential SQL regression.",
            "generator": "tooling/src/sql/extract_golden_sql.py",
        },
        "query_builder": extract_query_builder(),
        "data_fetcher_where": extract_data_fetcher_where(),
    }


def main():
    parser = argparse.ArgumentParser(description="Extract golden SQL strings")
    parser.add_argument("--print", action="store_true", help="Print to stdout as well")
    parser.add_argument("--output", default=None, help="Output JSON path (default: qcmetric/sql_golden.json)")
    args = parser.parse_args()

    golden = extract_all()

    output_path = Path(args.output) if args.output else PROJECT_ROOT / "qcmetric" / "sql_golden.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as fh:
        json.dump(golden, fh, indent=2)

    qb_count = len(golden["query_builder"])
    df_count = len(golden["data_fetcher_where"])
    print(f"Extracted {qb_count} QueryBuilder + {df_count} DataFetcher scenarios → {output_path}")

    if getattr(args, "print"):
        print(json.dumps(golden, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
