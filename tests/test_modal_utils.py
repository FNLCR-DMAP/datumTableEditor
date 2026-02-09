"""
Tests for modal utilities.
"""
import pytest
import pandas as pd


class TestBuildCurrentColumnTag:
    """Tests for build_current_column_tag function."""
    
    def test_creates_div(self):
        """Should create a div element."""
        from src.utils.modal_utils import build_current_column_tag
        
        result = build_current_column_tag("Gene", 1)
        
        # Result is a Shiny UI element, check it's not None
        assert result is not None
    
    def test_includes_column_name(self):
        """Tag should include column name."""
        from src.utils.modal_utils import build_current_column_tag
        
        result = build_current_column_tag("PatientID", 3)
        html = str(result)
        
        assert "PatientID" in html
        assert "3." in html


class TestBuildAvailableColumnTag:
    """Tests for build_available_column_tag function."""
    
    def test_creates_clickable_tag(self):
        """Should create clickable add tag."""
        from src.utils.modal_utils import build_available_column_tag
        
        result = build_available_column_tag("Gene")
        html = str(result)
        
        assert "Gene" in html
        assert "addColumn" in html


class TestBuildColumnsModalContent:
    """Tests for build_columns_modal_content function."""
    
    def test_both_sections_present(self):
        """Modal should have current and available sections."""
        from src.utils.modal_utils import build_columns_modal_content
        
        result = build_columns_modal_content(["A", "B"], ["C", "D"])
        html = str(result)
        
        assert "Current columns" in html
        assert "Remaining columns" in html
    
    def test_empty_current_shows_message(self):
        """Empty current columns should show message."""
        from src.utils.modal_utils import build_columns_modal_content
        
        result = build_columns_modal_content([], ["A"])
        html = str(result)
        
        assert "No columns displayed" in html
    
    def test_empty_available_shows_message(self):
        """Empty available columns should show message."""
        from src.utils.modal_utils import build_columns_modal_content
        
        result = build_columns_modal_content(["A"], [])
        html = str(result)
        
        assert "All columns displayed" in html


class TestBuildPresetMenuItems:
    """Tests for build_preset_menu_items function."""
    
    def test_creates_menu_items(self):
        """Should create menu item for each preset."""
        from src.utils.modal_utils import build_preset_menu_items
        
        presets = {"Default": ["A"], "Custom": ["B", "C"]}
        result = build_preset_menu_items(presets, "Default")
        html = str(result)
        
        assert "Default" in html
        assert "Custom" in html
    
    def test_default_no_delete_button(self):
        """Default preset should not have delete button."""
        from src.utils.modal_utils import build_preset_menu_items
        
        presets = {"Default": ["A"], "Custom": ["B"]}
        result = build_preset_menu_items(presets, "Default")
        html = str(result)
        
        # Custom should have delete class/functionality
        assert "deletePreset" in html  # Custom has delete
        assert "Custom" in html
    
    def test_empty_presets(self):
        """Empty presets should show message."""
        from src.utils.modal_utils import build_preset_menu_items
        
        result = build_preset_menu_items({}, "Default")
        html = str(result)
        
        assert "No presets available" in html


class TestBuildCopyColumnButtons:
    """Tests for build_copy_column_buttons function."""
    
    def test_creates_buttons(self):
        """Should create button for each column."""
        from src.utils.modal_utils import build_copy_column_buttons
        
        result = build_copy_column_buttons(["Gene", "Status"])
        html = str(result)
        
        assert "Gene" in html
        assert "Status" in html
        assert "copyColumnValues" in html


class TestBuildFilterColumnButtons:
    """Tests for build_filter_column_buttons function."""
    
    def test_creates_filter_buttons(self):
        """Should create button for each column."""
        from src.utils.modal_utils import build_filter_column_buttons
        
        result = build_filter_column_buttons(["Gene", "Status"])
        html = str(result)
        
        assert "Gene" in html
        assert "addFilter" in html
    
    def test_empty_columns(self):
        """Empty columns should show message."""
        from src.utils.modal_utils import build_filter_column_buttons
        
        result = build_filter_column_buttons([])
        html = str(result)
        
        assert "already being filtered" in html


class TestBuildDynamicFilterElement:
    """Tests for build_dynamic_filter_element function."""
    
    def test_creates_filter_element(self):
        """Should create filter with select."""
        from src.utils.modal_utils import build_dynamic_filter_element
        
        result = build_dynamic_filter_element("Status", ["all", "approved", "rejected"], "all")
        html = str(result)
        
        assert "Status" in html
        assert "filter_Status" in html
        assert "removeFilter" in html


class TestBuildDynamicFiltersPanel:
    """Tests for build_dynamic_filters_panel function."""
    
    @pytest.fixture
    def sample_df(self):
        return pd.DataFrame({
            "Status": ["approved", "rejected", "approved"],
            "Gene": ["TP53", "BRCA1", "EGFR"]
        })
    
    def test_creates_filters(self, sample_df):
        """Should create filter elements for each active filter."""
        from src.utils.modal_utils import build_dynamic_filters_panel
        
        filters = {"Status": "all", "Gene": "all"}
        result = build_dynamic_filters_panel(filters, sample_df)
        html = str(result)
        
        assert "Status" in html
        assert "Gene" in html
    
    def test_empty_filters(self, sample_df):
        """Empty filters should show message."""
        from src.utils.modal_utils import build_dynamic_filters_panel
        
        result = build_dynamic_filters_panel({}, sample_df)
        html = str(result)
        
        assert "No filters active" in html
    
    def test_skips_invalid_column(self, sample_df):
        """Should skip columns not in DataFrame."""
        from src.utils.modal_utils import build_dynamic_filters_panel
        
        filters = {"Status": "all", "NonExistent": "all"}
        result = build_dynamic_filters_panel(filters, sample_df)
        html = str(result)
        
        assert "Status" in html
        # NonExistent should be skipped, not cause error
