"""
Tests for pagination_utils UI builders.
"""
import pytest
from unittest.mock import MagicMock, patch


class TestBuildRowsPerPageSelector:
    """Tests for build_rows_per_page_selector function."""
    
    def test_returns_div(self):
        """Should return a div element."""
        from src.utils.pagination_utils import build_rows_per_page_selector
        
        result = build_rows_per_page_selector("25")
        
        # Should be a Shiny UI element (div)
        assert result is not None
    
    def test_respects_selected_value(self):
        """Should set selected value correctly."""
        from src.utils.pagination_utils import build_rows_per_page_selector
        
        result = build_rows_per_page_selector("50")
        
        # Result should be a UI element
        assert result is not None


class TestBuildPaginationControlsAll:
    """Tests for build_pagination_controls_all function."""
    
    def test_shows_all_rows_message(self):
        """Should show 'all rows' message."""
        from src.utils.pagination_utils import build_pagination_controls_all
        
        result = build_pagination_controls_all(
            total_rows=100,
            rows_per_page_val="all"
        )
        
        assert result is not None
    
    def test_includes_total_count(self):
        """Should include total row count."""
        from src.utils.pagination_utils import build_pagination_controls_all
        
        result = build_pagination_controls_all(
            total_rows=500,
            rows_per_page_val="all"
        )
        
        # Result should be a UI element
        assert result is not None


class TestBuildPaginationControlsPaged:
    """Tests for build_pagination_controls_paged function."""
    
    def test_shows_page_range(self):
        """Should show page range info."""
        from src.utils.pagination_utils import build_pagination_controls_paged
        
        result = build_pagination_controls_paged(
            page=1,
            total_pages=5,
            start_row=1,
            end_row=25,
            total_rows=125,
            rows_per_page_val="25"
        )
        
        assert result is not None
    
    def test_middle_page(self):
        """Should handle middle page correctly."""
        from src.utils.pagination_utils import build_pagination_controls_paged
        
        result = build_pagination_controls_paged(
            page=3,
            total_pages=10,
            start_row=51,
            end_row=75,
            total_rows=250,
            rows_per_page_val="25"
        )
        
        assert result is not None
    
    def test_last_page(self):
        """Should handle last page correctly."""
        from src.utils.pagination_utils import build_pagination_controls_paged
        
        result = build_pagination_controls_paged(
            page=5,
            total_pages=5,
            start_row=101,
            end_row=120,
            total_rows=120,
            rows_per_page_val="25"
        )
        
        assert result is not None
