"""
Tests for filter_utils — operator matching and filtered row retrieval.

Covers: _is_operator_filter, _row_matches_operator (all operators),
        get_filtered_rows with operator dicts.
"""
import math
import re
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.utils.filter_utils import (
    OPERATOR_LABELS,
    _is_operator_filter,
    _row_matches_operator,
    get_filtered_rows,
)


# =====================================================================
# _is_operator_filter
# =====================================================================

class TestIsOperatorFilter:
    def test_dict_with_op(self):
        assert _is_operator_filter({"op": "in", "value": ["A"]}) is True

    def test_dict_without_op(self):
        assert _is_operator_filter({"value": "A"}) is False

    def test_plain_string(self):
        assert _is_operator_filter("hello") is False

    def test_none(self):
        assert _is_operator_filter(None) is False

    def test_empty_dict(self):
        assert _is_operator_filter({}) is False


class TestGetFilteredRowsFastPath:
    def test_no_filters_all_statuses_skips_status_callback(self):
        df = pd.DataFrame({"Name": ["A", "B", "C"]}, index=[10, 11, 12])
        status_func = MagicMock(side_effect=AssertionError("status callback should not run"))

        result = get_filtered_rows(
            df=df,
            active_columns=["Name"],
            search_term="",
            status_filters=["unprocessed", "edited", "approved", "rejected"],
            column_filters={},
            get_row_status_func=status_func,
        )

        assert result == [10, 11, 12]
        status_func.assert_not_called()


# =====================================================================
# _row_matches_operator — IN / NOT_IN
# =====================================================================

class TestOperatorIn:
    def test_in_match(self):
        assert _row_matches_operator("A", {"op": "in", "value": ["A", "B"]}) is True

    def test_in_no_match(self):
        assert _row_matches_operator("C", {"op": "in", "value": ["A", "B"]}) is False

    def test_in_single_value(self):
        assert _row_matches_operator("X", {"op": "in", "value": "X"}) is True

    def test_not_in_match(self):
        assert _row_matches_operator("C", {"op": "not_in", "value": ["A", "B"]}) is True

    def test_not_in_no_match(self):
        assert _row_matches_operator("A", {"op": "not_in", "value": ["A", "B"]}) is False


# =====================================================================
# _row_matches_operator — CONTAINS / NOT_CONTAINS
# =====================================================================

class TestOperatorContains:

    def test_contains_match(self):
        assert _row_matches_operator("Hello World", {"op": "contains", "value": "world"}) is True

    def test_contains_no_match(self):
        assert _row_matches_operator("Hello", {"op": "contains", "value": "xyz"}) is False

    def test_contains_multiple_any_match(self):
        # Should match if any value is present
        assert _row_matches_operator("Hello World", {"op": "contains", "value": ["foo", "world"]}) is True
        assert _row_matches_operator("Hello World", {"op": "contains", "value": ["world", "foo"]}) is True
        assert _row_matches_operator("Hello World", {"op": "contains", "value": ["foo", "bar"]}) is False

    def test_not_contains_match(self):
        assert _row_matches_operator("Hello", {"op": "not_contains", "value": "xyz"}) is True

    def test_not_contains_no_match(self):
        assert _row_matches_operator("Hello World", {"op": "not_contains", "value": "world"}) is False

    def test_not_contains_multiple_all_must_absent(self):
        # Should only match if all values are absent
        assert _row_matches_operator("Hello World", {"op": "not_contains", "value": ["foo", "bar"]}) is True
        assert _row_matches_operator("Hello World", {"op": "not_contains", "value": ["foo", "world"]}) is False
        assert _row_matches_operator("Hello World", {"op": "not_contains", "value": ["world", "foo"]}) is False


# =====================================================================
# _row_matches_operator — BETWEEN
# =====================================================================

class TestOperatorBetween:
    def test_numeric_in_range(self):
        assert _row_matches_operator("5", {"op": "between", "value": [1, 10]}) is True

    def test_numeric_out_of_range(self):
        assert _row_matches_operator("15", {"op": "between", "value": [1, 10]}) is False

    def test_numeric_boundary_low(self):
        assert _row_matches_operator("1", {"op": "between", "value": [1, 10]}) is True

    def test_numeric_boundary_high(self):
        assert _row_matches_operator("10", {"op": "between", "value": [1, 10]}) is True

    def test_string_fallback(self):
        """Non-numeric values fall back to lexicographic comparison."""
        assert _row_matches_operator("B", {"op": "between", "value": ["A", "C"]}) is True

    def test_string_fallback_out_of_range(self):
        assert _row_matches_operator("D", {"op": "between", "value": ["A", "C"]}) is False

    def test_malformed_single_value(self):
        """Malformed (not 2-element list) → don't filter (returns True)."""
        assert _row_matches_operator("5", {"op": "between", "value": [1]}) is True

    def test_malformed_not_list(self):
        assert _row_matches_operator("5", {"op": "between", "value": "1-10"}) is True

    def test_date_string_between(self):
        """Date strings compared lexicographically."""
        assert _row_matches_operator("2024-06-15", {"op": "between", "value": ["2024-01-01", "2024-12-31"]}) is True

    def test_date_string_outside(self):
        assert _row_matches_operator("2023-06-15", {"op": "between", "value": ["2024-01-01", "2024-12-31"]}) is False


# =====================================================================
# _row_matches_operator — BETWEEN (null / empty bounds)
# =====================================================================

class TestOperatorBetweenNullBounds:
    """Tests for between operator with None or empty-string bounds."""

    def test_both_none_passes(self):
        """[None, None] → no filtering, always pass."""
        assert _row_matches_operator("5", {"op": "between", "value": [None, None]}) is True

    def test_both_empty_string_passes(self):
        """['', ''] → treated as null bounds, always pass."""
        assert _row_matches_operator("5", {"op": "between", "value": ["", ""]}) is True

    def test_lower_only_numeric_pass(self):
        """[5, None] → gte 5."""
        assert _row_matches_operator("10", {"op": "between", "value": [5, None]}) is True

    def test_lower_only_numeric_fail(self):
        assert _row_matches_operator("3", {"op": "between", "value": [5, None]}) is False

    def test_lower_only_boundary(self):
        assert _row_matches_operator("5", {"op": "between", "value": [5, None]}) is True

    def test_upper_only_numeric_pass(self):
        """[None, 10] → lte 10."""
        assert _row_matches_operator("5", {"op": "between", "value": [None, 10]}) is True

    def test_upper_only_numeric_fail(self):
        assert _row_matches_operator("15", {"op": "between", "value": [None, 10]}) is False

    def test_upper_only_boundary(self):
        assert _row_matches_operator("10", {"op": "between", "value": [None, 10]}) is True

    def test_lower_only_empty_string_upper(self):
        """['5', ''] → lower bound only."""
        assert _row_matches_operator("10", {"op": "between", "value": ["5", ""]}) is True
        assert _row_matches_operator("3", {"op": "between", "value": ["5", ""]}) is False

    def test_upper_only_empty_string_lower(self):
        """['', '10'] → upper bound only."""
        assert _row_matches_operator("5", {"op": "between", "value": ["", "10"]}) is True
        assert _row_matches_operator("15", {"op": "between", "value": ["", "10"]}) is False

    def test_date_lower_only(self):
        """Date string with only lower bound."""
        assert _row_matches_operator("2024-06-15", {"op": "between", "value": ["2024-01-01", None]}) is True
        assert _row_matches_operator("2023-06-15", {"op": "between", "value": ["2024-01-01", None]}) is False

    def test_date_upper_only(self):
        """Date string with only upper bound."""
        assert _row_matches_operator("2024-06-15", {"op": "between", "value": [None, "2024-12-31"]}) is True
        assert _row_matches_operator("2025-06-15", {"op": "between", "value": [None, "2024-12-31"]}) is False

    def test_whitespace_only_treated_as_null(self):
        """'   ' is treated as empty → null bound."""
        assert _row_matches_operator("5", {"op": "between", "value": ["  ", "  "]}) is True


# =====================================================================
# _row_matches_operator — GT / GTE / LT / LTE
# =====================================================================

class TestOperatorComparisons:
    # GT
    def test_gt_numeric_true(self):
        assert _row_matches_operator("10", {"op": "gt", "value": "5"}) is True

    def test_gt_numeric_false(self):
        assert _row_matches_operator("3", {"op": "gt", "value": "5"}) is False

    def test_gt_numeric_equal(self):
        assert _row_matches_operator("5", {"op": "gt", "value": "5"}) is False

    def test_gt_string_fallback(self):
        assert _row_matches_operator("B", {"op": "gt", "value": "A"}) is True

    # GTE
    def test_gte_numeric_equal(self):
        assert _row_matches_operator("5", {"op": "gte", "value": "5"}) is True

    def test_gte_numeric_greater(self):
        assert _row_matches_operator("10", {"op": "gte", "value": "5"}) is True

    def test_gte_numeric_less(self):
        assert _row_matches_operator("3", {"op": "gte", "value": "5"}) is False

    def test_gte_string_fallback(self):
        assert _row_matches_operator("A", {"op": "gte", "value": "A"}) is True

    # LT
    def test_lt_numeric_true(self):
        assert _row_matches_operator("3", {"op": "lt", "value": "5"}) is True

    def test_lt_numeric_false(self):
        assert _row_matches_operator("10", {"op": "lt", "value": "5"}) is False

    def test_lt_numeric_equal(self):
        assert _row_matches_operator("5", {"op": "lt", "value": "5"}) is False

    def test_lt_string_fallback(self):
        assert _row_matches_operator("A", {"op": "lt", "value": "B"}) is True

    # LTE
    def test_lte_numeric_equal(self):
        assert _row_matches_operator("5", {"op": "lte", "value": "5"}) is True

    def test_lte_numeric_less(self):
        assert _row_matches_operator("3", {"op": "lte", "value": "5"}) is True

    def test_lte_numeric_greater(self):
        assert _row_matches_operator("10", {"op": "lte", "value": "5"}) is False

    def test_lte_string_fallback(self):
        assert _row_matches_operator("B", {"op": "lte", "value": "B"}) is True


# =====================================================================
# _row_matches_operator — LAST_N_DAYS
# =====================================================================

class TestOperatorLastNDays:
    def test_recent_date_passes(self):
        """Date within last 7 days should pass."""
        recent = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
        assert _row_matches_operator(recent, {"op": "last_n_days", "value": "7"}) is True

    def test_old_date_fails(self):
        """Date older than N days should fail."""
        old = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        assert _row_matches_operator(old, {"op": "last_n_days", "value": "7"}) is False

    def test_unparseable_date_fails(self):
        """Non-date string should fail (parsed as NaT)."""
        assert _row_matches_operator("not-a-date", {"op": "last_n_days", "value": "7"}) is False

    def test_malformed_n_passes(self):
        """Non-numeric N → malformed, don't filter (True)."""
        assert _row_matches_operator("2024-01-01", {"op": "last_n_days", "value": "abc"}) is True

    def test_none_value_fails(self):
        """None value → unparseable date → fail."""
        assert _row_matches_operator(None, {"op": "last_n_days", "value": "7"}) is False


# =====================================================================
# _row_matches_operator — NOT_EMPTY
# =====================================================================

class TestOperatorNotEmpty:
    def test_none_value(self):
        assert _row_matches_operator(None, {"op": "not_empty", "value": None}) is False

    def test_nan_value(self):
        assert _row_matches_operator(float("nan"), {"op": "not_empty", "value": None}) is False

    def test_empty_string(self):
        assert _row_matches_operator("", {"op": "not_empty", "value": None}) is False

    def test_whitespace_only(self):
        assert _row_matches_operator("   ", {"op": "not_empty", "value": None}) is False

    def test_valid_value(self):
        assert _row_matches_operator("hello", {"op": "not_empty", "value": None}) is True

    def test_zero_is_not_empty(self):
        assert _row_matches_operator(0, {"op": "not_empty", "value": None}) is True

    def test_pd_nat(self):
        assert _row_matches_operator(pd.NaT, {"op": "not_empty", "value": None}) is False


# =====================================================================
# _row_matches_operator — REGEX
# =====================================================================

class TestOperatorRegex:
    def test_matching_pattern(self):
        assert _row_matches_operator("abc123", {"op": "regex", "value": r"\d+"}) is True

    def test_non_matching_pattern(self):
        assert _row_matches_operator("abc", {"op": "regex", "value": r"^\d+$"}) is False

    def test_invalid_regex_passes(self):
        """Invalid regex → don't filter (True)."""
        assert _row_matches_operator("abc", {"op": "regex", "value": "[invalid"}) is True

    def test_none_row_value(self):
        assert _row_matches_operator(None, {"op": "regex", "value": r".*"}) is True


# =====================================================================
# _row_matches_operator — UNKNOWN OP
# =====================================================================

class TestOperatorUnknown:
    def test_unknown_op_passes(self):
        """Unknown operator → don't filter (True)."""
        assert _row_matches_operator("anything", {"op": "does_not_exist", "value": "x"}) is True


# =====================================================================
# OPERATOR_LABELS constant
# =====================================================================

class TestOperatorLabels:
    def test_all_operators_have_labels(self):
        expected = {"in", "not_in", "contains", "not_contains", "between",
                    "value_range",
                    "gt", "gte", "lt", "lte", "regex", "not_empty", "is_null", "last_n_days"}
        assert expected == set(OPERATOR_LABELS.keys())


# =====================================================================
# get_filtered_rows — operator dict integration
# =====================================================================

class TestGetFilteredRowsOperator:
    @pytest.fixture
    def df(self):
        return pd.DataFrame({
            "Name": ["Alice", "Bob", "Charlie", "Diana", "Eve"],
            "Score": [85, 42, 95, 70, 60],
            "Status": ["active", "inactive", "active", "active", "inactive"],
        })

    @pytest.fixture
    def status_func(self):
        """All rows have status 'unprocessed'."""
        return lambda idx: "unprocessed"

    def test_contains_operator(self, df, status_func):
        filters = {"Name": {"op": "contains", "value": "li"}}
        result = get_filtered_rows(df, ["Name", "Score", "Status"], "", ["unprocessed"], filters, status_func)
        names = [df.loc[i, "Name"] for i in result]
        assert "Alice" in names
        assert "Charlie" in names
        assert "Bob" not in names

    def test_not_in_operator(self, df, status_func):
        filters = {"Status": {"op": "not_in", "value": ["inactive"]}}
        result = get_filtered_rows(df, ["Name", "Score", "Status"], "", ["unprocessed"], filters, status_func)
        statuses = [df.loc[i, "Status"] for i in result]
        assert all(s == "active" for s in statuses)

    def test_gt_operator(self, df, status_func):
        filters = {"Score": {"op": "gt", "value": "70"}}
        result = get_filtered_rows(df, ["Name", "Score", "Status"], "", ["unprocessed"], filters, status_func)
        scores = [df.loc[i, "Score"] for i in result]
        assert all(s > 70 for s in scores)

    def test_between_operator(self, df, status_func):
        filters = {"Score": {"op": "between", "value": [60, 85]}}
        result = get_filtered_rows(df, ["Name", "Score", "Status"], "", ["unprocessed"], filters, status_func)
        scores = [df.loc[i, "Score"] for i in result]
        assert all(60 <= s <= 85 for s in scores)
        assert len(result) == 3  # Alice(85), Diana(70), Eve(60)

    def test_between_both_null_passes_all(self, df, status_func):
        """[None, None] between should not filter anything."""
        filters = {"Score": {"op": "between", "value": [None, None]}}
        result = get_filtered_rows(df, ["Name", "Score", "Status"], "", ["unprocessed"], filters, status_func)
        assert len(result) == 5

    def test_between_lower_only(self, df, status_func):
        """[70, None] → rows with score >= 70."""
        filters = {"Score": {"op": "between", "value": [70, None]}}
        result = get_filtered_rows(df, ["Name", "Score", "Status"], "", ["unprocessed"], filters, status_func)
        scores = [df.loc[i, "Score"] for i in result]
        assert all(s >= 70 for s in scores)
        assert len(result) == 3  # Alice(85), Charlie(95), Diana(70)

    def test_between_upper_only(self, df, status_func):
        """[None, 70] → rows with score <= 70."""
        filters = {"Score": {"op": "between", "value": [None, 70]}}
        result = get_filtered_rows(df, ["Name", "Score", "Status"], "", ["unprocessed"], filters, status_func)
        scores = [df.loc[i, "Score"] for i in result]
        assert all(s <= 70 for s in scores)
        assert len(result) == 3  # Bob(42), Diana(70), Eve(60)

    def test_not_empty_operator(self, df, status_func):
        df2 = df.copy()
        df2.loc[1, "Name"] = ""
        df2.loc[3, "Name"] = None
        filters = {"Name": {"op": "not_empty", "value": None}}
        result = get_filtered_rows(df2, ["Name", "Score", "Status"], "", ["unprocessed"], filters, status_func)
        assert 1 not in result
        assert 3 not in result
        assert 0 in result

    def test_regex_operator(self, df, status_func):
        filters = {"Name": {"op": "regex", "value": r"^[A-D]"}}
        result = get_filtered_rows(df, ["Name", "Score", "Status"], "", ["unprocessed"], filters, status_func)
        names = [df.loc[i, "Name"] for i in result]
        assert "Alice" in names
        assert "Bob" in names
        assert "Charlie" in names
        assert "Diana" in names
        assert "Eve" not in names

    def test_combined_operator_and_search(self, df, status_func):
        """Operator filter + search term should both apply."""
        filters = {"Status": {"op": "in", "value": ["active"]}}
        result = get_filtered_rows(df, ["Name", "Score", "Status"], "ali", ["unprocessed"], filters, status_func)
        names = [df.loc[i, "Name"] for i in result]
        assert names == ["Alice"]

    def test_simple_string_filter(self, df, status_func):
        """Original simple string filter still works."""
        filters = {"Status": "active"}
        result = get_filtered_rows(df, ["Name", "Score", "Status"], "", ["unprocessed"], filters, status_func)
        statuses = [df.loc[i, "Status"] for i in result]
        assert all(s == "active" for s in statuses)

    def test_all_filter_passes_all(self, df, status_func):
        filters = {"Status": "all"}
        result = get_filtered_rows(df, ["Name"], "", ["unprocessed"], filters, status_func)
        assert len(result) == 5

    def test_column_not_in_df(self, df, status_func):
        """Filter on non-existent column should be silently skipped."""
        filters = {"NonExistent": {"op": "in", "value": ["X"]}}
        result = get_filtered_rows(df, ["Name"], "", ["unprocessed"], filters, status_func)
        assert len(result) == 5

    def test_search_specific_column(self, df, status_func):
        """search_column parameter targets a specific column."""
        result = get_filtered_rows(df, ["Name", "Score", "Status"], "alice", ["unprocessed"], {}, status_func, search_column="Name")
        assert len(result) == 1  # Only Alice matches

    def test_search_no_match(self, df, status_func):
        result = get_filtered_rows(df, ["Name", "Score", "Status"], "zzzzz", ["unprocessed"], {}, status_func)
        assert len(result) == 0

    def test_lte_operator(self, df, status_func):
        filters = {"Score": {"op": "lte", "value": "60"}}
        result = get_filtered_rows(df, ["Name", "Score", "Status"], "", ["unprocessed"], filters, status_func)
        scores = [df.loc[i, "Score"] for i in result]
        assert all(s <= 60 for s in scores)
