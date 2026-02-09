"""
Tests for filter handler utilities.
"""
import pytest
from typing import Dict, Any


class TestParseFilterColumn:
    """Tests for parse_filter_column function."""
    
    def test_parse_string_value(self):
        """String value should be returned as-is."""
        from src.utils.filter_handlers import parse_filter_column
        
        result = parse_filter_column("Gene_names")
        assert result == "Gene_names"
    
    def test_parse_dict_value(self):
        """Dict with 'column' key should extract column name."""
        from src.utils.filter_handlers import parse_filter_column
        
        result = parse_filter_column({"column": "Gene_names", "other": "data"})
        assert result == "Gene_names"
    
    def test_parse_none_value(self):
        """None should return None."""
        from src.utils.filter_handlers import parse_filter_column
        
        result = parse_filter_column(None)
        assert result is None
    
    def test_parse_empty_dict(self):
        """Empty dict should return None."""
        from src.utils.filter_handlers import parse_filter_column
        
        result = parse_filter_column({})
        assert result is None


class TestAddFilter:
    """Tests for add_filter function."""
    
    def test_add_new_filter(self):
        """Adding a new filter column should add with 'all' value."""
        from src.utils.filter_handlers import add_filter
        
        filters = {"Status": "approved"}
        result = add_filter(filters, "Gene_names")
        
        assert "Gene_names" in result
        assert result["Gene_names"] == "all"
    
    def test_add_existing_filter(self):
        """Adding existing filter should not change it."""
        from src.utils.filter_handlers import add_filter
        
        filters = {"Status": "approved"}
        result = add_filter(filters, "Status")
        
        assert result["Status"] == "approved"
    
    def test_does_not_mutate_original(self):
        """Should return a copy, not mutate original."""
        from src.utils.filter_handlers import add_filter
        
        original = {"Status": "approved"}
        result = add_filter(original, "Gene_names")
        
        assert "Gene_names" not in original
        assert "Gene_names" in result


class TestRemoveFilter:
    """Tests for remove_filter function."""
    
    def test_remove_existing_filter(self):
        """Removing existing filter should remove it."""
        from src.utils.filter_handlers import remove_filter
        
        filters = {"Status": "approved", "Gene_names": "TP53"}
        result = remove_filter(filters, "Gene_names")
        
        assert "Gene_names" not in result
        assert "Status" in result
    
    def test_remove_nonexistent_filter(self):
        """Removing non-existent filter should not error."""
        from src.utils.filter_handlers import remove_filter
        
        filters = {"Status": "approved"}
        result = remove_filter(filters, "NonExistent")
        
        assert result == {"Status": "approved"}
    
    def test_does_not_mutate_original(self):
        """Should return a copy, not mutate original."""
        from src.utils.filter_handlers import remove_filter
        
        original = {"Status": "approved", "Gene_names": "TP53"}
        result = remove_filter(original, "Gene_names")
        
        assert "Gene_names" in original
        assert "Gene_names" not in result


class TestUpdateFilterValues:
    """Tests for update_filter_values function."""
    
    def test_empty_filters_returns_unchanged(self):
        """Empty filters should return unchanged."""
        from src.utils.filter_handlers import update_filter_values
        
        filters = {}
        result, updated = update_filter_values(filters, None)
        
        assert result == {}
        assert updated is False
    
    def test_none_filters_returns_unchanged(self):
        """None filters should return unchanged."""
        from src.utils.filter_handlers import update_filter_values
        
        filters = None
        result, updated = update_filter_values(filters, None)
        
        assert result is None
        assert updated is False
    
    def test_with_mock_input_object(self):
        """Should update filters from input object attributes."""
        from src.utils.filter_handlers import update_filter_values
        from unittest.mock import MagicMock
        
        # Create mock input object with filter_Status method
        mock_input = MagicMock()
        mock_input.filter_Status = MagicMock(return_value="approved")
        
        filters = {"Status": "all"}
        result, updated = update_filter_values(filters, mock_input)
        
        assert result["Status"] == "approved"
        assert updated is True
    
    def test_no_update_when_same_value(self):
        """Should not mark as updated when value unchanged."""
        from src.utils.filter_handlers import update_filter_values
        from unittest.mock import MagicMock
        
        mock_input = MagicMock()
        mock_input.filter_Status = MagicMock(return_value="approved")
        
        filters = {"Status": "approved"}
        result, updated = update_filter_values(filters, mock_input)
        
        assert result["Status"] == "approved"
        assert updated is False
    
    def test_handles_missing_attribute(self):
        """Should handle missing filter attribute gracefully."""
        from src.utils.filter_handlers import update_filter_values
        from unittest.mock import MagicMock
        
        mock_input = MagicMock()
        # filter_NonExistent doesn't exist
        mock_input.filter_NonExistent = MagicMock(side_effect=AttributeError)
        
        filters = {"NonExistent": "all"}
        result, updated = update_filter_values(filters, mock_input)
        
        # Should not crash, filters unchanged
        assert result["NonExistent"] == "all"
