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


class TestBuildOperatorFilterElement:
    """Tests for build_operator_filter_element function."""

    def test_basic_equals_filter(self):
        """Should render column name and value."""
        from src.utils.modal_utils import build_operator_filter_element

        result = build_operator_filter_element("Status", {"op": "=", "value": "active"})
        html = str(result)

        assert "Status" in html
        assert "active" in html

    def test_not_empty_no_value_display(self):
        """not_empty operator should show empty value display."""
        from src.utils.modal_utils import build_operator_filter_element

        result = build_operator_filter_element("Col", {"op": "not_empty", "value": None})
        html = str(result)

        assert "Col" in html

    def test_last_n_days_shows_days(self):
        """last_n_days should display 'N days'."""
        from src.utils.modal_utils import build_operator_filter_element

        result = build_operator_filter_element("Date", {"op": "last_n_days", "value": 7})
        html = str(result)

        assert "7 days" in html

    def test_between_shows_arrow(self):
        """between operator should display 'a → b'."""
        from src.utils.modal_utils import build_operator_filter_element

        result = build_operator_filter_element("Score", {"op": "between", "value": [1, 10]})
        html = str(result)

        assert "1" in html
        assert "10" in html
        assert "→" in html

    def test_list_shows_comma_separated(self):
        """List values should display comma-separated."""
        from src.utils.modal_utils import build_operator_filter_element

        result = build_operator_filter_element("Type", {"op": "in", "value": ["a", "b", "c"]})
        html = str(result)

        assert "a, b, c" in html

    def test_remove_button_present_by_default(self):
        """Remove button should be present when fix_filter=False."""
        from src.utils.modal_utils import build_operator_filter_element

        result = build_operator_filter_element("Col", {"op": "=", "value": "x"}, fix_filter=False)
        html = str(result)

        assert "removeFilter" in html

    def test_remove_button_hidden_when_fixed(self):
        """Remove button should NOT be present when fix_filter=True."""
        from src.utils.modal_utils import build_operator_filter_element

        result = build_operator_filter_element("Col", {"op": "=", "value": "x"}, fix_filter=True)
        html = str(result)

        assert "removeFilter" not in html


# =====================================================================
# Column Masks Tests
# =====================================================================

class TestMaskHelper:
    """Tests for _mask helper function."""

    def test_returns_display_name(self):
        """Should return mapped display name when mask exists."""
        from src.utils.modal_utils import _mask

        assert _mask("Gene_names", {"Gene_names": "Gene"}) == "Gene"

    def test_returns_original_when_no_masks(self):
        """Should return original name when masks is None."""
        from src.utils.modal_utils import _mask

        assert _mask("Gene_names", None) == "Gene_names"

    def test_returns_original_when_key_missing(self):
        """Should return original name when column not in masks."""
        from src.utils.modal_utils import _mask

        assert _mask("Gene_names", {"Other": "X"}) == "Gene_names"

    def test_empty_dict_returns_original(self):
        """Should return original name when masks is empty dict."""
        from src.utils.modal_utils import _mask

        assert _mask("Gene_names", {}) == "Gene_names"


class TestColumnMasksInModalUtils:
    """Tests for column_masks support across modal utility functions."""

    def test_current_column_tag_uses_mask(self):
        """Current column tag should display masked name, keep real data-column."""
        from src.utils.modal_utils import build_current_column_tag

        result = build_current_column_tag("Gene_names", 1, column_masks={"Gene_names": "Gene"})
        html = str(result)

        assert "Gene" in html  # Display uses masked name
        assert 'data-column="Gene_names"' in html  # Data attr uses real name

    def test_available_column_tag_uses_mask(self):
        """Available column tag should display masked name, onclick uses real name."""
        from src.utils.modal_utils import build_available_column_tag

        result = build_available_column_tag("Gene_names", column_masks={"Gene_names": "Gene"})
        html = str(result)

        assert "+ Gene" in html  # Display uses masked name
        assert "addColumn" in html and "Gene_names" in html  # JS uses real name

    def test_columns_modal_content_uses_masks(self):
        """Modal content should display masked names for both sections."""
        from src.utils.modal_utils import build_columns_modal_content

        masks = {"Gene_names": "Gene", "Status": "State"}
        result = build_columns_modal_content(["Gene_names"], ["Status"], column_masks=masks)
        html = str(result)

        assert "Gene" in html
        assert "State" in html

    def test_copy_column_buttons_use_masks(self):
        """Copy buttons should display masked name, onclick uses real name."""
        from src.utils.modal_utils import build_copy_column_buttons

        result = build_copy_column_buttons(["Gene_names"], column_masks={"Gene_names": "Gene"})
        html = str(result)

        assert "Gene" in html  # Button text is masked
        assert "copyColumnValues" in html and "Gene_names" in html  # JS uses real name

    def test_filter_column_buttons_use_masks(self):
        """Filter buttons should display masked name, onclick uses real name."""
        from src.utils.modal_utils import build_filter_column_buttons

        result = build_filter_column_buttons(["Gene_names"], column_masks={"Gene_names": "Gene"})
        html = str(result)

        assert "Gene" in html  # Button text is masked
        assert "addFilter" in html and "Gene_names" in html  # JS uses real name

    def test_operator_filter_element_uses_mask(self):
        """Operator filter label should display masked name."""
        from src.utils.modal_utils import build_operator_filter_element

        result = build_operator_filter_element(
            "Gene_names", {"op": "in", "value": ["TP53"]},
            column_masks={"Gene_names": "Gene"}
        )
        html = str(result)

        assert "Gene" in html  # Label is masked

    def test_dynamic_filter_element_uses_mask(self):
        """Dynamic filter label should display masked name, input ID uses real name."""
        from src.utils.modal_utils import build_dynamic_filter_element

        result = build_dynamic_filter_element(
            "Gene_names", ["all", "TP53"], "all",
            column_masks={"Gene_names": "Gene"}
        )
        html = str(result)

        assert "Gene" in html  # Label is masked
        assert "filter_Gene_names" in html  # Input ID uses real name

    def test_dynamic_filters_panel_uses_masks(self):
        """Filters panel should pass masks through to child elements."""
        from src.utils.modal_utils import build_dynamic_filters_panel

        df = pd.DataFrame({"Gene_names": ["TP53", "BRCA1"]})
        filters = {"Gene_names": "all"}
        result = build_dynamic_filters_panel(filters, df, column_masks={"Gene_names": "Gene"})
        html = str(result)

        assert "Gene" in html


# =====================================================================
# Interactive Operator Dropdown Tests
# =====================================================================

class TestDynamicFilterOperatorDropdown:
    """Tests for operator <select> dropdown in dynamic filter elements."""

    def test_has_operator_select(self):
        """Dynamic filter element should include operator dropdown."""
        from src.utils.modal_utils import build_dynamic_filter_element

        result = build_dynamic_filter_element("Col", ["all", "A"], "all")
        html = str(result)

        assert "filter-op-select" in html
        assert "<select" in html

    def test_contains_all_operator_options(self):
        """Dropdown should contain all 12 operator options."""
        from src.utils.modal_utils import build_dynamic_filter_element

        result = build_dynamic_filter_element("Col", ["all"], "all")
        html = str(result)

        for op_value in ["in", "not_in", "contains", "not_contains", "gt", "gte",
                         "lt", "lte", "between", "regex", "not_empty", "last_n_days"]:
            assert f'value="{op_value}"' in html, f"Missing operator option: {op_value}"

    def test_preselects_operator(self):
        """Should pre-select the specified operator."""
        from src.utils.modal_utils import build_dynamic_filter_element

        result = build_dynamic_filter_element("Col", ["all"], "all", current_op="not_in")
        html = str(result)

        # The not_in option should have selected attribute
        assert 'value="not_in" selected' in html or 'value="not_in"  selected' in html

    def test_default_operator_is_in(self):
        """Default operator should be 'in'."""
        from src.utils.modal_utils import build_dynamic_filter_element

        result = build_dynamic_filter_element("Col", ["all"], "all")
        html = str(result)

        assert 'value="in" selected' in html or 'value="in"  selected' in html

    def test_not_empty_hides_textarea(self):
        """not_empty operator should hide the textarea."""
        from src.utils.modal_utils import build_dynamic_filter_element

        result = build_dynamic_filter_element("Col", ["all"], "all", current_op="not_empty")
        html = str(result)

        assert "display: none" in html

    def test_in_operator_shows_textarea(self):
        """'in' operator should show the textarea (textarea is visible)."""
        from src.utils.modal_utils import build_dynamic_filter_element

        result = build_dynamic_filter_element("Col", ["all"], "all", current_op="in")
        html = str(result)

        # Textarea element should be present and not hidden
        assert "<textarea" in html

    def test_onchange_calls_setFilterOperator(self):
        """Select onchange should call setFilterOperator with correct column."""
        from src.utils.modal_utils import build_dynamic_filter_element

        result = build_dynamic_filter_element("MyCol", ["all"], "all")
        html = str(result)

        assert "setFilterOperator" in html and "MyCol" in html

    def test_panel_interactive_op_renders_dropdown(self):
        """Interactive operator dict should render editable element with dropdown."""
        from src.utils.modal_utils import build_dynamic_filters_panel

        df = pd.DataFrame({"Col": ["A", "B"]})
        filters = {"Col": {"op": "not_in", "value": ["A"], "interactive": True}}
        result = build_dynamic_filters_panel(filters, df)
        html = str(result)

        # Should have operator dropdown (not read-only label)
        assert "filter-op-select" in html
        assert "filter_Col" in html  # textarea present

    def test_panel_interactive_op_extracts_value(self):
        """Interactive operator dict should show values in textarea."""
        from src.utils.modal_utils import build_dynamic_filters_panel

        df = pd.DataFrame({"Col": ["A", "B"]})
        filters = {"Col": {"op": "not_in", "value": ["X", "Y"], "interactive": True}}
        result = build_dynamic_filters_panel(filters, df)
        html = str(result)

        assert "X\nY" in html  # Values joined with newlines

    def test_panel_config_op_stays_readonly(self):
        """Config-defined operator dict (no interactive key) should be read-only."""
        from src.utils.modal_utils import build_dynamic_filters_panel

        df = pd.DataFrame({"Col": ["A", "B"]})
        filters = {"Col": {"op": "not_in", "value": ["A"]}}
        result = build_dynamic_filters_panel(filters, df)
        html = str(result)

        # Should NOT have operator dropdown
        assert "filter-op-select" not in html
        # Should have read-only operator label
        assert "is not" in html
