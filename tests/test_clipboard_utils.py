"""
Tests for clipboard utilities.
"""
import pytest
import pandas as pd
from typing import List, Tuple, Optional
from unittest.mock import MagicMock


class TestGenerateClipboardJs:
    """Tests for generate_clipboard_js function."""
    
    def test_generates_js_code(self):
        """Should generate valid JavaScript code."""
        from src.utils.clipboard_utils import generate_clipboard_js
        
        result = generate_clipboard_js("test text")
        
        assert "navigator.clipboard.writeText" in result
        assert "test text" in result
    
    def test_escapes_special_characters(self):
        """Should properly escape special characters."""
        from src.utils.clipboard_utils import generate_clipboard_js
        
        result = generate_clipboard_js('text with "quotes" and newlines\n')
        
        assert "navigator.clipboard.writeText" in result
        # JSON.dumps handles escaping
        assert '\\"' in result or '"quotes"' in result


class TestProcessCopyRequest:
    """Tests for process_copy_request function."""
    
    @pytest.fixture
    def sample_df(self):
        return pd.DataFrame({
            "PatientID": ["P001", "P002", "P003"],
            "Gene": ["TP53", "BRCA1", "EGFR"]
        })
    
    @pytest.fixture
    def mock_paginate_func(self):
        """Returns indices as-is."""
        def paginate(filtered_indices, rows_per_page, page):
            return filtered_indices
        return paginate
    
    @pytest.fixture
    def mock_get_values_func(self, sample_df):
        """Returns column values for given indices."""
        def get_values(df, column, paginated_indices, row_indices):
            if column not in df.columns:
                return None, f"Column {column} not found"
            # row_indices are positions within paginated view
            actual_indices = [paginated_indices[i] for i in row_indices if i < len(paginated_indices)]
            values = [str(df.iloc[idx][column]) for idx in actual_indices]
            return values, None
        return get_values
    
    def test_none_request_returns_none(self, sample_df, mock_paginate_func, mock_get_values_func):
        """None request should return all None."""
        from src.utils.clipboard_utils import process_copy_request
        
        js, col, count, error = process_copy_request(
            None, sample_df, [0, 1, 2], "25", 1,
            mock_paginate_func, mock_get_values_func
        )
        
        assert js is None
        assert col is None
        assert error is None
    
    def test_empty_request_returns_none(self, sample_df, mock_paginate_func, mock_get_values_func):
        """Empty request should return all None."""
        from src.utils.clipboard_utils import process_copy_request
        
        js, col, count, error = process_copy_request(
            {}, sample_df, [0, 1, 2], "25", 1,
            mock_paginate_func, mock_get_values_func
        )
        
        assert js is None
        assert error is None
    
    def test_missing_column_returns_error(self, sample_df, mock_paginate_func, mock_get_values_func):
        """Request without column should return error."""
        from src.utils.clipboard_utils import process_copy_request
        
        js, col, count, error = process_copy_request(
            {"indices": [0]}, sample_df, [0, 1, 2], "25", 1,
            mock_paginate_func, mock_get_values_func
        )
        
        assert js is None
        assert "No column or rows selected" in error
    
    def test_missing_indices_returns_error(self, sample_df, mock_paginate_func, mock_get_values_func):
        """Request without indices should return error."""
        from src.utils.clipboard_utils import process_copy_request
        
        js, col, count, error = process_copy_request(
            {"column": "Gene"}, sample_df, [0, 1, 2], "25", 1,
            mock_paginate_func, mock_get_values_func
        )
        
        assert js is None
        assert "No column or rows selected" in error
    
    def test_successful_copy(self, sample_df, mock_paginate_func, mock_get_values_func):
        """Successful copy should return JS code and count."""
        from src.utils.clipboard_utils import process_copy_request
        
        js, col, count, error = process_copy_request(
            {"column": "Gene", "indices": [0, 1]},
            sample_df, [0, 1, 2], "25", 1,
            mock_paginate_func, mock_get_values_func
        )
        
        assert js is not None
        assert col == "Gene"
        assert count == 2
        assert error is None
    
    def test_invalid_column_returns_error(self, sample_df, mock_paginate_func, mock_get_values_func):
        """Invalid column should return error from get_values func."""
        from src.utils.clipboard_utils import process_copy_request
        
        js, col, count, error = process_copy_request(
            {"column": "NonExistent", "indices": [0]},
            sample_df, [0, 1, 2], "25", 1,
            mock_paginate_func, mock_get_values_func
        )
        
        assert js is None
        assert "not found" in error
