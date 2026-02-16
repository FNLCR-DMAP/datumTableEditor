"""
Tests for filtering and pagination utilities.

Tests:
- Row filtering by status, search, column filters
- Pagination logic
- Search in specific columns vs all columns
"""

import pytest
import pandas as pd
from unittest.mock import MagicMock


class TestGetFilteredRows:
    """Tests for get_filtered_rows function."""
    
    def test_filter_by_status_unprocessed(self, sample_data):
        """Filter should return only unprocessed rows."""
        from src.utils.filter_utils import get_filtered_rows
        
        def mock_get_row_status(idx):
            return sample_data.loc[idx, "_mod_status"]
        
        filtered = get_filtered_rows(
            df=sample_data,
            active_columns=["PatientID", "Gene_names"],
            search_term="",
            status_filters=["unprocessed"],
            column_filters={},
            get_row_status_func=mock_get_row_status,
        )
        
        # Should return indices of unprocessed rows
        for idx in filtered:
            assert sample_data.loc[idx, "_mod_status"] == "unprocessed"
    
    def test_filter_by_multiple_statuses(self, sample_data):
        """Filter should return rows matching any of the status filters."""
        from src.utils.filter_utils import get_filtered_rows
        
        def mock_get_row_status(idx):
            return sample_data.loc[idx, "_mod_status"]
        
        filtered = get_filtered_rows(
            df=sample_data,
            active_columns=["PatientID", "Gene_names"],
            search_term="",
            status_filters=["unprocessed", "edited"],
            column_filters={},
            get_row_status_func=mock_get_row_status,
        )
        
        for idx in filtered:
            assert sample_data.loc[idx, "_mod_status"] in ["unprocessed", "edited"]
    
    def test_filter_by_search_term_all_columns(self, sample_data):
        """Search should find matches in any active column."""
        from src.utils.filter_utils import get_filtered_rows
        
        def mock_get_row_status(idx):
            return "unprocessed"  # Allow all statuses
        
        filtered = get_filtered_rows(
            df=sample_data,
            active_columns=["PatientID", "Gene_names", "Variant_key"],
            search_term="BRCA",  # Should match Gene_names
            status_filters=["unprocessed", "edited", "approved", "rejected"],
            column_filters={},
            get_row_status_func=mock_get_row_status,
        )
        
        # Should find row with BRCA1
        assert len(filtered) >= 1
        found_brca = False
        for idx in filtered:
            if "BRCA" in str(sample_data.loc[idx, "Gene_names"]):
                found_brca = True
        assert found_brca
    
    def test_filter_by_search_term_specific_column(self, sample_data):
        """Search in specific column should only match that column."""
        from src.utils.filter_utils import get_filtered_rows
        
        def mock_get_row_status(idx):
            return "unprocessed"
        
        # Search for "PAT001" in PatientID column specifically
        filtered = get_filtered_rows(
            df=sample_data,
            active_columns=["PatientID", "Gene_names"],
            search_term="PAT001",
            status_filters=["unprocessed", "edited", "approved", "rejected"],
            column_filters={},
            get_row_status_func=mock_get_row_status,
            search_column="PatientID"
        )
        
        # Should find exactly one match
        assert len(filtered) >= 1
        for idx in filtered:
            assert "PAT001" in str(sample_data.loc[idx, "PatientID"])
    
    def test_filter_by_column_filter(self, sample_data):
        """Column filter should filter exact matches."""
        from src.utils.filter_utils import get_filtered_rows
        
        def mock_get_row_status(idx):
            return "unprocessed"
        
        filtered = get_filtered_rows(
            df=sample_data,
            active_columns=["PatientID", "Gene_names", "Status"],
            search_term="",
            status_filters=["unprocessed", "edited", "approved", "rejected"],
            column_filters={"Status": "Pending"},
            get_row_status_func=mock_get_row_status,
        )
        
        # All returned rows should have Status == "Pending"
        for idx in filtered:
            assert sample_data.loc[idx, "Status"] == "Pending"
    
    def test_filter_combination(self, sample_data):
        """Multiple filters should be combined (AND logic)."""
        from src.utils.filter_utils import get_filtered_rows
        
        def mock_get_row_status(idx):
            return sample_data.loc[idx, "_mod_status"]
        
        filtered = get_filtered_rows(
            df=sample_data,
            active_columns=["PatientID", "Gene_names", "Status"],
            search_term="PAT",  # All patients have PAT in ID
            status_filters=["unprocessed"],  # Only unprocessed
            column_filters={"Status": "Pending"},  # Only Pending status
            get_row_status_func=mock_get_row_status,
        )
        
        # All filters should be satisfied
        for idx in filtered:
            row = sample_data.loc[idx]
            assert "PAT" in str(row["PatientID"])
            assert row["_mod_status"] == "unprocessed"
            assert row["Status"] == "Pending"
    
    def test_filter_returns_dataframe_indices(self, sample_data):
        """Filtered indices should be actual DataFrame indices, not positions."""
        from src.utils.filter_utils import get_filtered_rows
        
        # Create a DataFrame with non-sequential index
        df = sample_data.copy()
        df.index = [10, 20, 30, 40, 50]  # Non-sequential indices
        
        def mock_get_row_status(idx):
            return "unprocessed"
        
        filtered = get_filtered_rows(
            df=df,
            active_columns=["PatientID", "Gene_names"],
            search_term="",
            status_filters=["unprocessed", "edited", "approved", "rejected"],
            column_filters={},
            get_row_status_func=mock_get_row_status,
        )
        
        # Should return actual DataFrame indices
        for idx in filtered:
            assert idx in df.index
            # Should be able to use .loc with these indices
            row = df.loc[idx]
            assert row is not None
    
    def test_case_insensitive_search(self, sample_data):
        """Search should be case-insensitive."""
        from src.utils.filter_utils import get_filtered_rows
        
        def mock_get_row_status(idx):
            return "unprocessed"
        
        # Search with lowercase
        filtered_lower = get_filtered_rows(
            df=sample_data,
            active_columns=["PatientID", "Gene_names"],
            search_term="brca",  # lowercase
            status_filters=["unprocessed", "edited", "approved", "rejected"],
            column_filters={},
            get_row_status_func=mock_get_row_status,
        )
        
        # Search with uppercase
        filtered_upper = get_filtered_rows(
            df=sample_data,
            active_columns=["PatientID", "Gene_names"],
            search_term="BRCA",  # uppercase
            status_filters=["unprocessed", "edited", "approved", "rejected"],
            column_filters={},
            get_row_status_func=mock_get_row_status,
        )
        
        # Should get same results
        assert filtered_lower == filtered_upper


class TestPagination:
    """Tests for pagination utilities."""
    
    def test_get_paginated_indices_first_page(self):
        """First page should return first N indices."""
        from src.utils.data_operations import get_paginated_indices
        
        all_indices = list(range(100))
        
        paginated = get_paginated_indices(
            filtered_indices=all_indices,
            rows_per_page_val="25",
            current_page=1
        )
        
        assert len(paginated) == 25
        assert paginated == list(range(25))
    
    def test_get_paginated_indices_middle_page(self):
        """Middle page should return correct slice."""
        from src.utils.data_operations import get_paginated_indices
        
        all_indices = list(range(100))
        
        paginated = get_paginated_indices(
            filtered_indices=all_indices,
            rows_per_page_val="25",
            current_page=2
        )
        
        assert len(paginated) == 25
        assert paginated == list(range(25, 50))
    
    def test_get_paginated_indices_last_page_partial(self):
        """Last page may have fewer items."""
        from src.utils.data_operations import get_paginated_indices
        
        all_indices = list(range(90))  # 90 items, last page has 15
        
        paginated = get_paginated_indices(
            filtered_indices=all_indices,
            rows_per_page_val="25",
            current_page=4  # 4th page (76-90)
        )
        
        assert len(paginated) == 15
        assert paginated == list(range(75, 90))
    
    def test_get_paginated_indices_empty_list(self):
        """Empty filtered list should return empty."""
        from src.utils.data_operations import get_paginated_indices
        
        paginated = get_paginated_indices(
            filtered_indices=[],
            rows_per_page_val="25",
            current_page=1
        )
        
        assert paginated == []
    
    def test_get_paginated_indices_preserves_actual_indices(self):
        """Pagination should preserve actual DataFrame indices."""
        from src.utils.data_operations import get_paginated_indices
        
        # Non-sequential indices (as would come from DataFrame)
        all_indices = [5, 10, 15, 20, 25, 100, 200, 300]
        
        paginated = get_paginated_indices(
            filtered_indices=all_indices,
            rows_per_page_val="3",
            current_page=1
        )
        
        assert paginated == [5, 10, 15]
        
        paginated_p2 = get_paginated_indices(
            filtered_indices=all_indices,
            rows_per_page_val="3",
            current_page=2
        )
        
        assert paginated_p2 == [20, 25, 100]
    
    def test_get_paginated_indices_all_rows(self):
        """When rows_per_page is 'all', return all indices."""
        from src.utils.data_operations import get_paginated_indices
        
        all_indices = list(range(100))
        
        paginated = get_paginated_indices(
            filtered_indices=all_indices,
            rows_per_page_val="all",
            current_page=1
        )
        
        assert paginated == all_indices
    
    def test_page_out_of_bounds(self):
        """Page beyond available should return empty."""
        from src.utils.data_operations import get_paginated_indices
        
        all_indices = list(range(50))
        
        paginated = get_paginated_indices(
            filtered_indices=all_indices,
            rows_per_page_val="25",
            current_page=10  # Way beyond available
        )
        
        # Should return empty list for out-of-bounds page
        assert paginated == []


class TestStatusCounts:
    """Tests for status count aggregation."""
    
    def test_count_by_status(self, sample_data):
        """Should correctly count rows by status."""
        from src.utils.data_utils import get_modification_summary
        
        pk_cols = ["PatientID_Mutsequence"]
        
        # get_modification_summary returns (summary_data, status_counts)
        _, counts = get_modification_summary(
            df=sample_data,
            log=[],
            pk_cols=pk_cols
        )
        
        # Total should equal row count
        total = counts["unprocessed"] + counts["edited"] + counts["approved"] + counts["rejected"]
        assert total == len(sample_data)


class TestBetweenFilterNumeric:
    """Tests for between filter numeric comparison (Finding #31)."""

    def test_between_numeric_correct_ordering(self):
        """Between should use numeric comparison when values are numbers."""
        from src.utils.filter_utils import _row_matches_operator

        # "9" > "15" lexicographically, but 9 < 15 numerically
        assert _row_matches_operator("9", {"op": "between", "value": ["5", "15"]}) is True
        assert _row_matches_operator("15", {"op": "between", "value": ["5", "15"]}) is True
        assert _row_matches_operator("20", {"op": "between", "value": ["5", "15"]}) is False

    def test_between_string_fallback(self):
        """Between should fall back to string comparison for non-numeric values."""
        from src.utils.filter_utils import _row_matches_operator

        assert _row_matches_operator("banana", {"op": "between", "value": ["apple", "cherry"]}) is True
        assert _row_matches_operator("date", {"op": "between", "value": ["apple", "cherry"]}) is False

    def test_between_malformed_value(self):
        """Malformed between value should not filter (return True)."""
        from src.utils.filter_utils import _row_matches_operator

        assert _row_matches_operator("5", {"op": "between", "value": ["only_one"]}) is True
        assert _row_matches_operator("5", {"op": "between", "value": []}) is True
