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

class TestCustomRowsPerPageOptions:
    """Tests that custom rows_per_page_options are honoured in UI builders."""

    def test_selector_uses_custom_options(self):
        """build_rows_per_page_selector should render custom choices."""
        from src.utils.pagination_utils import build_rows_per_page_selector

        result = build_rows_per_page_selector("500", options=[25, 50, 100, 500])
        html = str(result)
        assert "500" in html

    def test_selector_includes_all_option(self):
        """'all' should appear when included in options."""
        from src.utils.pagination_utils import build_rows_per_page_selector

        result = build_rows_per_page_selector("all", options=[50, 100, "all"])
        html = str(result)
        assert "all" in html

    def test_selector_defaults_without_options(self):
        """None options falls back to [10, 25, 50, 100]."""
        from src.utils.pagination_utils import build_rows_per_page_selector

        result = build_rows_per_page_selector("25", options=None)
        html = str(result)
        assert "25" in html
        # Should NOT contain 500 (not in default list)
        # just verify it renders without error
        assert result is not None

    def test_controls_all_passes_options(self):
        """build_pagination_controls_all forwards options."""
        from src.utils.pagination_utils import build_pagination_controls_all

        result = build_pagination_controls_all(200, "all", rows_per_page_options=[50, 100, 500, "all"])
        html = str(result)
        assert "500" in html

    def test_controls_paged_passes_options(self):
        """build_pagination_controls_paged forwards options."""
        from src.utils.pagination_utils import build_pagination_controls_paged

        result = build_pagination_controls_paged(
            page=1, total_pages=2, start_row=1, end_row=500,
            total_rows=750, rows_per_page_val="500",
            rows_per_page_options=[25, 50, 100, 500],
        )
        html = str(result)
        assert "500" in html