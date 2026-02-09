"""
Tests for column utilities.
"""
import pytest
import pandas as pd
from typing import List, Dict, Any


class TestParseColumnValue:
    """Tests for parse_column_value function."""
    
    def test_parse_string_value(self):
        """String value should be returned as-is."""
        from src.utils.column_utils import parse_column_value
        
        result = parse_column_value("Gene_names")
        assert result == "Gene_names"
    
    def test_parse_dict_value(self):
        """Dict with 'col' key should extract column name."""
        from src.utils.column_utils import parse_column_value
        
        result = parse_column_value({"col": "Gene_names", "other": "data"})
        assert result == "Gene_names"
    
    def test_parse_none_value(self):
        """None should return None."""
        from src.utils.column_utils import parse_column_value
        
        result = parse_column_value(None)
        assert result is None
    
    def test_parse_empty_string(self):
        """Empty string should return None (falsy)."""
        from src.utils.column_utils import parse_column_value
        
        result = parse_column_value("")
        assert result is None


class TestParseColumnOrder:
    """Tests for parse_column_order function."""
    
    def test_parse_list_value(self):
        """List value should be returned as-is."""
        from src.utils.column_utils import parse_column_order
        
        order = ["A", "B", "C"]
        result = parse_column_order(order)
        assert result == order
    
    def test_parse_dict_value(self):
        """Dict with 'order' key should extract order list."""
        from src.utils.column_utils import parse_column_order
        
        result = parse_column_order({"order": ["A", "B", "C"], "extra": "data"})
        assert result == ["A", "B", "C"]
    
    def test_parse_none_value(self):
        """None should return None."""
        from src.utils.column_utils import parse_column_order
        
        result = parse_column_order(None)
        assert result is None


class TestAddColumnToList:
    """Tests for add_column_to_list function."""
    
    def test_add_new_column(self):
        """Adding a new column should append it."""
        from src.utils.column_utils import add_column_to_list
        
        columns = ["A", "B"]
        result = add_column_to_list(columns, "C")
        
        assert "C" in result
        assert len(result) == 3
    
    def test_add_existing_column(self):
        """Adding existing column should not duplicate."""
        from src.utils.column_utils import add_column_to_list
        
        columns = ["A", "B", "C"]
        result = add_column_to_list(columns, "B")
        
        assert result.count("B") == 1
        assert len(result) == 3
    
    def test_does_not_mutate_original(self):
        """Should return a copy, not mutate original."""
        from src.utils.column_utils import add_column_to_list
        
        original = ["A", "B"]
        result = add_column_to_list(original, "C")
        
        assert len(original) == 2
        assert len(result) == 3


class TestRemoveColumnFromList:
    """Tests for remove_column_from_list function."""
    
    def test_remove_existing_column(self):
        """Removing existing column should remove it."""
        from src.utils.column_utils import remove_column_from_list
        
        columns = ["A", "B", "C"]
        result = remove_column_from_list(columns, "B")
        
        assert "B" not in result
        assert len(result) == 2
    
    def test_remove_nonexistent_column(self):
        """Removing non-existent column should return same list."""
        from src.utils.column_utils import remove_column_from_list
        
        columns = ["A", "B", "C"]
        result = remove_column_from_list(columns, "D")
        
        assert result == ["A", "B", "C"]
    
    def test_does_not_mutate_original(self):
        """Should return a copy, not mutate original."""
        from src.utils.column_utils import remove_column_from_list
        
        original = ["A", "B", "C"]
        result = remove_column_from_list(original, "B")
        
        assert len(original) == 3
        assert len(result) == 2


class TestSortDataframe:
    """Tests for sort_dataframe function."""
    
    def test_sort_ascending(self):
        """Sorting ascending should work."""
        from src.utils.column_utils import sort_dataframe
        
        df = pd.DataFrame({"A": [3, 1, 2], "B": ["c", "a", "b"]})
        result = sort_dataframe(df, "A", "asc")
        
        assert list(result["A"]) == [1, 2, 3]
    
    def test_sort_descending(self):
        """Sorting descending should work."""
        from src.utils.column_utils import sort_dataframe
        
        df = pd.DataFrame({"A": [3, 1, 2], "B": ["c", "a", "b"]})
        result = sort_dataframe(df, "A", "desc")
        
        assert list(result["A"]) == [3, 2, 1]
    
    def test_sort_nonexistent_column(self):
        """Sorting by non-existent column should return original."""
        from src.utils.column_utils import sort_dataframe
        
        df = pd.DataFrame({"A": [3, 1, 2]})
        result = sort_dataframe(df, "NonExistent", "asc")
        
        assert list(result["A"]) == [3, 1, 2]


class TestGetPresetColumnsAndWidths:
    """Tests for get_preset_columns_and_widths function."""
    
    def test_list_format(self):
        """Old list format should return columns with empty widths."""
        from src.utils.column_utils import get_preset_columns_and_widths
        
        preset = ["A", "B", "C"]
        columns, widths = get_preset_columns_and_widths(preset, ["Default"])
        
        assert columns == ["A", "B", "C"]
        assert widths == {}
    
    def test_dict_format(self):
        """New dict format should extract columns and widths."""
        from src.utils.column_utils import get_preset_columns_and_widths
        
        preset = {"columns": ["A", "B"], "widths": {"A": "100px"}}
        columns, widths = get_preset_columns_and_widths(preset, ["Default"])
        
        assert columns == ["A", "B"]
        assert widths == {"A": "100px"}
    
    def test_invalid_format(self):
        """Invalid format should return defaults."""
        from src.utils.column_utils import get_preset_columns_and_widths
        
        columns, widths = get_preset_columns_and_widths(None, ["Default"])
        
        assert columns == ["Default"]
        assert widths == {}


class TestCreatePresetData:
    """Tests for create_preset_data function."""
    
    def test_create_with_widths(self):
        """Should create preset data with columns and widths."""
        from src.utils.column_utils import create_preset_data
        
        result = create_preset_data(["A", "B"], {"A": "100px"})
        
        assert result["columns"] == ["A", "B"]
        assert result["widths"] == {"A": "100px"}
    
    def test_create_without_widths(self):
        """Should create preset data with empty widths dict."""
        from src.utils.column_utils import create_preset_data
        
        result = create_preset_data(["A", "B"], None)
        
        assert result["columns"] == ["A", "B"]
        assert result["widths"] == {}


class TestGetOrderedColumns:
    """Tests for get_ordered_columns function."""
    
    def test_preset_columns_first(self):
        """Preset columns should come first in order."""
        from src.utils.column_utils import get_ordered_columns
        
        preset_cols = ["C", "A"]
        all_cols = ["A", "B", "C", "D"]
        
        result = get_ordered_columns(preset_cols, all_cols)
        
        assert result[:2] == ["C", "A"]
        assert set(result) == set(all_cols)
    
    def test_filters_missing_columns(self):
        """Should filter out preset columns not in all_cols."""
        from src.utils.column_utils import get_ordered_columns
        
        preset_cols = ["X", "A"]  # X doesn't exist
        all_cols = ["A", "B", "C"]
        
        result = get_ordered_columns(preset_cols, all_cols)
        
        assert result[0] == "A"
        assert "X" not in result
