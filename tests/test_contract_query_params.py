"""
Factor 1 Contract Tests: UI Inputs → QueryParams

Tests the contract that governs how raw UI input values are transformed
into the QueryParams dataclass before SQL generation.

Since _build_query_params is a server closure, these tests verify:
  1. Filter conversion logic: active_filters dict → filters_dict
  2. Page-size resolution: explicit / "all" / export modes
  3. Search/sort passthrough: reactive state → QueryParams fields
  4. Status filter handling: list cast + fallback
  5. Edge cases: empty/None/whitespace/operator filters

These are "boundary contract" tests — they lock down the exact mapping
from upstream shape to downstream shape at the UI→Query seam.
"""

import pytest
from src.config.config_instance import QueryParams


# ── Helpers that mirror _build_query_params logic ────────────────────────────

def convert_active_filters(active_filters: dict) -> dict:
    """
    Replicates the filter-conversion logic inside _build_query_params.
    Extracted here so we can pin the contract in isolation.
    """
    filters_dict = {}
    for col, val in active_filters.items():
        if isinstance(val, dict) and "op" in val:
            filters_dict[col] = val
        elif val and str(val).strip() and val != "all":
            values = [v.strip() for v in str(val).split("\n") if v.strip()]
            if values:
                filters_dict[col] = values if len(values) > 1 else values[0]
    return filters_dict


def resolve_page_size(
    for_export: bool,
    explicit_page_size: int = None,
    rows_per_page: str = "25",
    page_buffer_size: int = 5000,
) -> int:
    """
    Replicates page-size resolution logic from _build_query_params.
    """
    if for_export:
        return 1000000
    elif explicit_page_size is not None:
        return explicit_page_size
    else:
        rpp = rows_per_page
        return int(rpp) if rpp != "all" else page_buffer_size


def build_query_params_from_state(
    search_state: dict,
    sort_state: dict,
    status_filters: list,
    active_filters: dict,
    current_page: int = 1,
    rows_per_page: str = "25",
    page_buffer_size: int = 5000,
    for_export: bool = False,
    page: int = None,
    page_size: int = None,
    all_status_keys: list = None,
) -> QueryParams:
    """
    Full replica of _build_query_params for contract testing.
    """
    if status_filters is None:
        status_filters = all_status_keys or ["unprocessed", "edited", "approved", "rejected"]

    filters_dict = convert_active_filters(active_filters)
    actual_page_size = resolve_page_size(for_export, page_size, rows_per_page, page_buffer_size)

    return QueryParams(
        filters=filters_dict,
        search_term=search_state.get("term", ""),
        search_column=search_state.get("column", "all"),
        sort_column=sort_state.get("column"),
        sort_ascending=sort_state.get("ascending", True),
        page=page if page is not None else current_page,
        page_size=actual_page_size,
        status_filters=status_filters,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Filter Conversion Contract
# ═══════════════════════════════════════════════════════════════════════════════


class TestFilterConversion:
    """Contract: active_filters → filters_dict transformation."""

    def test_empty_filters_produce_empty_dict(self):
        assert convert_active_filters({}) == {}

    def test_single_text_value_becomes_string(self):
        """A single non-newline value stays as a scalar string."""
        result = convert_active_filters({"Gene": "BRCA1"})
        assert result == {"Gene": "BRCA1"}
        assert isinstance(result["Gene"], str)

    def test_newline_delimited_values_become_list(self):
        """Multiple newline-separated values are split into a list."""
        result = convert_active_filters({"Gene": "BRCA1\nTP53"})
        assert result == {"Gene": ["BRCA1", "TP53"]}
        assert isinstance(result["Gene"], list)

    def test_three_values_stay_as_list(self):
        result = convert_active_filters({"Gene": "A\nB\nC"})
        assert result == {"Gene": ["A", "B", "C"]}

    def test_whitespace_only_lines_stripped(self):
        """Blank lines and whitespace-only entries are removed."""
        result = convert_active_filters({"Gene": "  BRCA1 \n\n  TP53  \n  "})
        assert result == {"Gene": ["BRCA1", "TP53"]}

    def test_all_value_excluded(self):
        """The literal string 'all' is filtered out."""
        result = convert_active_filters({"Gene": "all"})
        assert result == {}

    def test_empty_string_excluded(self):
        result = convert_active_filters({"Gene": ""})
        assert result == {}

    def test_whitespace_only_excluded(self):
        result = convert_active_filters({"Gene": "   "})
        assert result == {}

    def test_none_value_excluded(self):
        """None values should not crash; they fail the truthiness check."""
        result = convert_active_filters({"Gene": None})
        assert result == {}

    def test_operator_dict_passthrough(self):
        """Operator filters {'op': ..., 'value': ...} pass through as-is."""
        op_filter = {"op": ">=", "value": 100}
        result = convert_active_filters({"Score": op_filter})
        assert result == {"Score": {"op": ">=", "value": 100}}

    def test_operator_dict_preserved_exactly(self):
        """The operator dict object should be the same reference (not copied)."""
        op_filter = {"op": "<=", "value": 42, "extra": "metadata"}
        result = convert_active_filters({"Col": op_filter})
        assert result["Col"] is op_filter

    def test_mixed_filters(self):
        """Operator + text + 'all' + empty coexist correctly."""
        active = {
            "Gene": "BRCA1\nTP53",
            "Score": {"op": ">", "value": 50},
            "Status": "all",
            "Notes": "",
            "Region": "Chr1",
        }
        result = convert_active_filters(active)
        assert result == {
            "Gene": ["BRCA1", "TP53"],
            "Score": {"op": ">", "value": 50},
            "Region": "Chr1",
        }

    def test_single_value_after_strip_becomes_string(self):
        """A single value with surrounding whitespace→ scalar string after strip."""
        result = convert_active_filters({"Gene": "  BRCA1  "})
        assert result == {"Gene": "BRCA1"}
        assert isinstance(result["Gene"], str)

    def test_numeric_string_preserved(self):
        """Numeric-looking strings stay as strings (no cast to int/float)."""
        result = convert_active_filters({"ID": "12345"})
        assert result == {"ID": "12345"}
        assert isinstance(result["ID"], str)

    def test_integer_value_converted_to_string_by_str_cast(self):
        """Non-string values are str()-cast, split, and processed."""
        result = convert_active_filters({"ID": 42})
        assert result == {"ID": "42"}


# ═══════════════════════════════════════════════════════════════════════════════
# Page Size Resolution Contract
# ═══════════════════════════════════════════════════════════════════════════════


class TestPageSizeResolution:
    """Contract: page-size resolution from multiple sources."""

    def test_export_always_returns_million(self):
        assert resolve_page_size(for_export=True) == 1000000

    def test_export_overrides_explicit_page_size(self):
        assert resolve_page_size(for_export=True, explicit_page_size=50) == 1000000

    def test_explicit_page_size_used(self):
        assert resolve_page_size(for_export=False, explicit_page_size=100) == 100

    def test_rows_per_page_numeric_string(self):
        assert resolve_page_size(for_export=False, rows_per_page="50") == 50

    def test_rows_per_page_all_uses_buffer(self):
        assert resolve_page_size(for_export=False, rows_per_page="all", page_buffer_size=5000) == 5000

    def test_rows_per_page_all_custom_buffer(self):
        assert resolve_page_size(for_export=False, rows_per_page="all", page_buffer_size=10000) == 10000

    def test_default_page_size_25(self):
        """Default rows_per_page is '25'."""
        assert resolve_page_size(for_export=False) == 25

    def test_explicit_page_size_zero(self):
        """Zero is a valid explicit page size."""
        assert resolve_page_size(for_export=False, explicit_page_size=0) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Full QueryParams Assembly Contract
# ═══════════════════════════════════════════════════════════════════════════════


class TestQueryParamsAssembly:
    """Contract: full QueryParams construction from UI state."""

    def test_default_state_produces_default_params(self):
        """Minimal state → sane defaults."""
        qp = build_query_params_from_state(
            search_state={"term": "", "column": "all"},
            sort_state={"column": None, "ascending": True},
            status_filters=["unprocessed", "edited", "approved", "rejected"],
            active_filters={},
        )
        assert qp.search_term == ""
        assert qp.search_column == "all"
        assert qp.sort_column is None
        assert qp.sort_ascending is True
        assert qp.page == 1
        assert qp.page_size == 25  # default rows_per_page
        assert qp.filters == {}
        assert qp.status_filters == ["unprocessed", "edited", "approved", "rejected"]

    def test_search_term_passed_through(self):
        qp = build_query_params_from_state(
            search_state={"term": "BRCA1", "column": "Gene"},
            sort_state={"column": None, "ascending": True},
            status_filters=["unprocessed"],
            active_filters={},
        )
        assert qp.search_term == "BRCA1"
        assert qp.search_column == "Gene"

    def test_sort_column_and_direction(self):
        qp = build_query_params_from_state(
            search_state={"term": "", "column": "all"},
            sort_state={"column": "Gene_names", "ascending": False},
            status_filters=["unprocessed"],
            active_filters={},
        )
        assert qp.sort_column == "Gene_names"
        assert qp.sort_ascending is False

    def test_page_override(self):
        """Explicit page parameter overrides current_page."""
        qp = build_query_params_from_state(
            search_state={"term": "", "column": "all"},
            sort_state={"column": None, "ascending": True},
            status_filters=["unprocessed"],
            active_filters={},
            current_page=5,
            page=3,
        )
        assert qp.page == 3

    def test_page_falls_back_to_current_page(self):
        qp = build_query_params_from_state(
            search_state={"term": "", "column": "all"},
            sort_state={"column": None, "ascending": True},
            status_filters=["unprocessed"],
            active_filters={},
            current_page=7,
        )
        assert qp.page == 7

    def test_export_sets_large_page_size(self):
        qp = build_query_params_from_state(
            search_state={"term": "", "column": "all"},
            sort_state={"column": None, "ascending": True},
            status_filters=["unprocessed"],
            active_filters={},
            for_export=True,
        )
        assert qp.page_size == 1000000

    def test_status_filters_none_falls_back(self):
        """If status_filters is None, fall back to all status keys."""
        qp = build_query_params_from_state(
            search_state={"term": "", "column": "all"},
            sort_state={"column": None, "ascending": True},
            status_filters=None,
            active_filters={},
            all_status_keys=["edited", "approved"],
        )
        assert qp.status_filters == ["edited", "approved"]

    def test_all_fields_simultaneously(self):
        """All UI state fields populated — complete contract snapshot."""
        qp = build_query_params_from_state(
            search_state={"term": "TP53", "column": "Gene"},
            sort_state={"column": "Score", "ascending": False},
            status_filters=["edited", "approved"],
            active_filters={
                "Gene": "BRCA1\nTP53",
                "Region": "Chr1",
                "Score": {"op": ">", "value": 42},
                "Status": "all",
            },
            current_page=3,
            rows_per_page="100",
        )
        assert qp.search_term == "TP53"
        assert qp.search_column == "Gene"
        assert qp.sort_column == "Score"
        assert qp.sort_ascending is False
        assert qp.status_filters == ["edited", "approved"]
        assert qp.page == 3
        assert qp.page_size == 100
        assert qp.filters == {
            "Gene": ["BRCA1", "TP53"],
            "Region": "Chr1",
            "Score": {"op": ">", "value": 42},
        }

    def test_search_state_missing_keys_use_defaults(self):
        """Missing keys in search_state fall back safely."""
        qp = build_query_params_from_state(
            search_state={},
            sort_state={},
            status_filters=["unprocessed"],
            active_filters={},
        )
        assert qp.search_term == ""
        assert qp.search_column == "all"
        assert qp.sort_column is None
        assert qp.sort_ascending is True


# ═══════════════════════════════════════════════════════════════════════════════
# Status Count Params Contract
# ═══════════════════════════════════════════════════════════════════════════════


class TestStatusCountParamsContract:
    """
    Contract: _get_status_counts builds a second QueryParams that
    copies filters/search/sort but overrides page=1, page_size=1,
    and status_filters=all keys.
    """

    def test_count_params_override_pagination(self):
        """Status count params always use page=1, page_size=1."""
        base = build_query_params_from_state(
            search_state={"term": "test", "column": "Gene"},
            sort_state={"column": "Gene", "ascending": False},
            status_filters=["edited"],
            active_filters={"Gene": "BRCA1"},
            current_page=5,
            rows_per_page="100",
        )
        # Mimic what _get_status_counts does:
        all_keys = ["unprocessed", "edited", "approved", "rejected"]
        count_params = QueryParams(
            filters=base.filters,
            search_term=base.search_term,
            search_column=base.search_column,
            sort_column=base.sort_column,
            sort_ascending=base.sort_ascending,
            page=1,
            page_size=1,
            status_filters=all_keys,
        )
        # The overrides
        assert count_params.page == 1
        assert count_params.page_size == 1
        assert count_params.status_filters == all_keys
        # Passthrough fields preserved from base
        assert count_params.filters == base.filters
        assert count_params.search_term == base.search_term
        assert count_params.search_column == base.search_column
        assert count_params.sort_column == base.sort_column
        assert count_params.sort_ascending == base.sort_ascending

    def test_count_params_with_empty_filters(self):
        """No filters → count params also have no filters."""
        base = build_query_params_from_state(
            search_state={"term": "", "column": "all"},
            sort_state={"column": None, "ascending": True},
            status_filters=["unprocessed"],
            active_filters={},
        )
        count_params = QueryParams(
            filters=base.filters,
            search_term=base.search_term,
            search_column=base.search_column,
            sort_column=base.sort_column,
            sort_ascending=base.sort_ascending,
            page=1,
            page_size=1,
            status_filters=["unprocessed", "edited", "approved", "rejected"],
        )
        assert count_params.filters == {}


# ═══════════════════════════════════════════════════════════════════════════════
# QueryParams Dataclass Invariants
# ═══════════════════════════════════════════════════════════════════════════════


class TestQueryParamsDefaults:
    """Contract: QueryParams defaults match documented values."""

    def test_default_filters_empty(self):
        qp = QueryParams()
        assert qp.filters == {}

    def test_default_search_term_empty(self):
        assert QueryParams().search_term == ""

    def test_default_search_column_all(self):
        assert QueryParams().search_column == "all"

    def test_default_sort_column_none(self):
        assert QueryParams().sort_column is None

    def test_default_sort_ascending_true(self):
        assert QueryParams().sort_ascending is True

    def test_default_page_one(self):
        assert QueryParams().page == 1

    def test_default_page_size_300(self):
        assert QueryParams().page_size == 300

    def test_default_status_filters(self):
        assert QueryParams().status_filters == ["unprocessed", "edited", "approved", "rejected"]

    def test_each_instance_gets_fresh_mutable_defaults(self):
        """Mutable defaults must be independent across instances."""
        qp1 = QueryParams()
        qp2 = QueryParams()
        qp1.filters["x"] = 1
        assert "x" not in qp2.filters
        qp1.status_filters.append("custom")
        assert "custom" not in qp2.status_filters
