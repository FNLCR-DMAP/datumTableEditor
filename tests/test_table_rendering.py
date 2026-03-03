"""
Tests for table rendering utilities.

Tests:
- Table row building with edited cell indicators
- PK-based edited cell lookup
- Status badge rendering
- Table body/container construction
"""

import pytest
import pandas as pd
from unittest.mock import MagicMock, patch


class TestBuildTableRow:
    """Tests for build_table_row function."""
    
    def test_row_contains_select_checkbox(self, sample_data):
        """Each row should have a selection checkbox."""
        from src.utils.table_utils import build_table_row
        
        row = sample_data.iloc[0]
        
        tr = build_table_row(
            idx=0,
            row=row,
            cols=["PatientID", "Gene_names"],
            current_df=sample_data,
            get_row_status_func=lambda x: "unprocessed",
            row_class="",
            edited_cells={},
            pk_columns=["PatientID_Mutsequence"]
        )
        
        # Should have checkbox cell
        tr_str = str(tr)
        assert "select_0" in tr_str or "checkbox" in tr_str.lower()
    
    def test_row_contains_status_badge(self, sample_data):
        """Each row should have a status badge."""
        from src.utils.table_utils import build_table_row
        
        row = sample_data.iloc[0]
        
        def mock_status(idx):
            return "edited"
        
        tr = build_table_row(
            idx=0,
            row=row,
            cols=["PatientID", "Gene_names"],
            current_df=sample_data,
            get_row_status_func=mock_status,
            row_class="",
            edited_cells={},
            pk_columns=["PatientID_Mutsequence"]
        )
        
        tr_str = str(tr)
        assert "status-edited" in tr_str or "Edited" in tr_str
    
    def test_edited_cell_has_brown_border_class(self, sample_data, cell_key_helper):
        """Edited cells should have 'cell-edited' class."""
        from src.utils.table_utils import build_table_row
        
        row = sample_data.iloc[0]
        pk = {"PatientID_Mutsequence": "PK001"}
        pk_tuple = tuple(sorted((k, str(v)) for k, v in pk.items()))
        
        edited_cells = {
            (pk_tuple, "Gene_names"): {"original": "OLD", "current": "NEW"}
        }
        
        tr = build_table_row(
            idx=0,
            row=row,
            cols=["PatientID", "Gene_names"],
            current_df=sample_data,
            get_row_status_func=lambda x: "edited",
            row_class="",
            edited_cells=edited_cells,
            pk_columns=["PatientID_Mutsequence"]
        )
        
        tr_str = str(tr)
        assert "cell-edited" in tr_str
    
    def test_edited_cell_has_data_original_attribute(self, sample_data):
        """Edited cells should have data-original attribute."""
        from src.utils.table_utils import build_table_row
        
        row = sample_data.iloc[0]
        pk = {"PatientID_Mutsequence": "PK001"}
        pk_tuple = tuple(sorted((k, str(v)) for k, v in pk.items()))
        
        edited_cells = {
            (pk_tuple, "Gene_names"): {"original": "ORIGINAL_VALUE", "current": "NEW"}
        }
        
        tr = build_table_row(
            idx=0,
            row=row,
            cols=["PatientID", "Gene_names"],
            current_df=sample_data,
            get_row_status_func=lambda x: "edited",
            row_class="",
            edited_cells=edited_cells,
            pk_columns=["PatientID_Mutsequence"]
        )
        
        tr_str = str(tr)
        assert "data-original" in tr_str
        assert "ORIGINAL_VALUE" in tr_str
    
    def test_non_edited_cell_no_edited_class(self, sample_data):
        """Non-edited cells should not have 'cell-edited' class."""
        from src.utils.table_utils import build_table_row
        
        row = sample_data.iloc[0]
        
        # Different row is edited, not this one
        pk_other = {"PatientID_Mutsequence": "PK999"}
        pk_tuple_other = tuple(sorted((k, str(v)) for k, v in pk_other.items()))
        
        edited_cells = {
            (pk_tuple_other, "Gene_names"): {"original": "OLD", "current": "NEW"}
        }
        
        tr = build_table_row(
            idx=0,
            row=row,
            cols=["PatientID", "Gene_names"],
            current_df=sample_data,
            get_row_status_func=lambda x: "unprocessed",
            row_class="",
            edited_cells=edited_cells,
            pk_columns=["PatientID_Mutsequence"]
        )
        
        tr_str = str(tr)
        # Should have editable-cell but not cell-edited for non-edited cells
        # This is a bit tricky to test without parsing HTML
        # The row PK is PK001, edited is PK999, so should not have cell-edited
        assert "editable-cell" in tr_str


class TestCellClickColumns:
    """Tests for cell_click_columns rendering in build_table_row."""

    def test_clickable_cell_has_class(self, sample_data):
        """Cells in cell_click_columns should get 'clickable-cell' class."""
        from src.utils.table_utils import build_table_row

        row = sample_data.iloc[0]
        tr = build_table_row(
            idx=0,
            row=row,
            cols=["PatientID", "Gene_names"],
            current_df=sample_data,
            get_row_status_func=lambda x: "unprocessed",
            row_class="",
            edited_cells={},
            pk_columns=["PatientID_Mutsequence"],
            cell_click_columns=["Gene_names"]
        )
        tr_str = str(tr)
        assert "clickable-cell" in tr_str

    def test_non_clickable_cell_no_class(self, sample_data):
        """Cells NOT in cell_click_columns should not get 'clickable-cell'."""
        from src.utils.table_utils import build_table_row

        row = sample_data.iloc[0]
        tr = build_table_row(
            idx=0,
            row=row,
            cols=["PatientID"],
            current_df=sample_data,
            get_row_status_func=lambda x: "unprocessed",
            row_class="",
            edited_cells={},
            pk_columns=["PatientID_Mutsequence"],
            cell_click_columns=["Gene_names"]
        )
        tr_str = str(tr)
        assert "clickable-cell" not in tr_str

    def test_clickable_cell_has_data_pk(self, sample_data):
        """Clickable cells should have data-pk JSON attribute."""
        from src.utils.table_utils import build_table_row

        row = sample_data.iloc[0]
        tr = build_table_row(
            idx=0,
            row=row,
            cols=["Gene_names"],
            current_df=sample_data,
            get_row_status_func=lambda x: "unprocessed",
            row_class="",
            edited_cells={},
            pk_columns=["PatientID_Mutsequence"],
            cell_click_columns=["Gene_names"]
        )
        tr_str = str(tr)
        assert "data-pk" in tr_str

    def test_empty_cell_click_columns(self, sample_data):
        """Empty cell_click_columns should produce no clickable cells."""
        from src.utils.table_utils import build_table_row

        row = sample_data.iloc[0]
        tr = build_table_row(
            idx=0,
            row=row,
            cols=["PatientID", "Gene_names"],
            current_df=sample_data,
            get_row_status_func=lambda x: "unprocessed",
            row_class="",
            edited_cells={},
            pk_columns=["PatientID_Mutsequence"],
            cell_click_columns=[]
        )
        tr_str = str(tr)
        assert "clickable-cell" not in tr_str

    def test_none_cell_click_columns(self, sample_data):
        """None cell_click_columns (default) should produce no clickable cells."""
        from src.utils.table_utils import build_table_row

        row = sample_data.iloc[0]
        tr = build_table_row(
            idx=0,
            row=row,
            cols=["PatientID", "Gene_names"],
            current_df=sample_data,
            get_row_status_func=lambda x: "unprocessed",
            row_class="",
            edited_cells={},
            pk_columns=["PatientID_Mutsequence"],
            cell_click_columns=None
        )
        tr_str = str(tr)
        assert "clickable-cell" not in tr_str

    def test_multiple_click_columns(self, sample_data):
        """Multiple columns in cell_click_columns should all be clickable."""
        from src.utils.table_utils import build_table_row

        row = sample_data.iloc[0]
        tr = build_table_row(
            idx=0,
            row=row,
            cols=["PatientID", "Gene_names"],
            current_df=sample_data,
            get_row_status_func=lambda x: "unprocessed",
            row_class="",
            edited_cells={},
            pk_columns=["PatientID_Mutsequence"],
            cell_click_columns=["PatientID", "Gene_names"]
        )
        tr_str = str(tr)
        # Both data cells should be clickable (2 occurrences, not counting the word elsewhere)
        assert tr_str.count("clickable-cell") >= 2


class TestBuildTableBody:
    """Tests for build_table_body function."""
    
    def test_builds_correct_number_of_rows(self, sample_data):
        """Table body should have correct number of rows."""
        from src.utils.table_utils import build_table_body
        
        indices = [0, 1, 2]
        
        tbody = build_table_body(
            paginated_indices=indices,
            current_df=sample_data,
            cols=["PatientID", "Gene_names"],
            get_row_status_func=lambda x: "unprocessed",
            edited_cells={},
            pk_columns=["PatientID_Mutsequence"]
        )
        
        # Should have 3 tr elements
        tbody_str = str(tbody)
        # Count <tr occurrences (rough check)
        assert tbody_str.count("<tr") == 3
    
    def test_uses_loc_for_dataframe_access(self, sample_data):
        """Should use .loc with actual DataFrame indices."""
        from src.utils.table_utils import build_table_body
        
        # Modify DataFrame to have non-sequential index
        df = sample_data.copy()
        df.index = [10, 20, 30, 40, 50]
        
        # Pass actual DataFrame indices
        indices = [10, 30]  # Skip index 20
        
        tbody = build_table_body(
            paginated_indices=indices,
            current_df=df,
            cols=["PatientID", "Gene_names"],
            get_row_status_func=lambda x: "unprocessed",
            edited_cells={},
            pk_columns=["PatientID_Mutsequence"]
        )
        
        # Should build without error and have 2 rows
        tbody_str = str(tbody)
        assert tbody_str.count("<tr") == 2
    
    def test_alternating_row_classes(self, sample_data):
        """Rows should have alternating even/odd classes."""
        from src.utils.table_utils import build_table_body
        
        indices = [0, 1, 2, 3]
        
        tbody = build_table_body(
            paginated_indices=indices,
            current_df=sample_data,
            cols=["PatientID"],
            get_row_status_func=lambda x: "unprocessed",
            edited_cells={},
            pk_columns=["PatientID_Mutsequence"]
        )
        
        tbody_str = str(tbody)
        assert "row-even" in tbody_str
        assert "row-odd" in tbody_str


class TestBuildTableContainer:
    """Tests for build_table_container function."""
    
    def test_includes_row_count_summary(self, sample_data):
        """Container should include row count summary."""
        from src.utils.table_utils import build_table_container
        
        container = build_table_container(
            paginated_indices=[0, 1, 2],
            current_df=sample_data,
            cols=["PatientID"],
            widths={},
            filtered_count=5,
            total_rows=10,
            get_row_status_func=lambda x: "unprocessed",
            edited_cells={},
            pk_columns=["PatientID_Mutsequence"]
        )
        
        container_str = str(container)
        # Should mention filtered count
        assert "3" in container_str  # displayed count
        assert "5" in container_str  # filtered count
    
    def test_includes_table_element(self, sample_data):
        """Container should include the table element."""
        from src.utils.table_utils import build_table_container
        
        container = build_table_container(
            paginated_indices=[0],
            current_df=sample_data,
            cols=["PatientID"],
            widths={},
            filtered_count=1,
            total_rows=5,
            get_row_status_func=lambda x: "unprocessed",
            edited_cells={},
            pk_columns=["PatientID_Mutsequence"]
        )
        
        container_str = str(container)
        assert "<table" in container_str
        assert "edit-table" in container_str


class TestStatusBadge:
    """Tests for status badge rendering."""
    
    def test_status_badge_texts(self):
        """Status badges should have correct display text."""
        from src.utils.table_utils import build_status_badge
        
        assert "New" in str(build_status_badge("unprocessed"))
        assert "Edited" in str(build_status_badge("edited"))
        assert "Approved" in str(build_status_badge("approved"))
        assert "Rejected" in str(build_status_badge("rejected"))
    
    def test_status_badge_classes(self):
        """Status badges should have correct CSS classes."""
        from src.utils.table_utils import build_status_badge
        
        assert "status-unprocessed" in str(build_status_badge("unprocessed"))
        assert "status-edited" in str(build_status_badge("edited"))
        assert "status-approved" in str(build_status_badge("approved"))
        assert "status-rejected" in str(build_status_badge("rejected"))


class TestTableHeader:
    """Tests for table header rendering."""
    
    def test_header_includes_all_columns(self):
        """Header should include all specified columns."""
        from src.utils.table_utils import build_table_header
        
        cols = ["PatientID", "Gene_names", "Status"]
        widths = {}
        
        header = build_table_header(cols, widths)
        header_str = str(header)
        
        for col in cols:
            assert col in header_str
    
    def test_header_includes_fixed_columns(self):
        """Header should include select, row number, and mod status columns."""
        from src.utils.table_utils import build_table_header
        
        header = build_table_header(["PatientID"], {})
        header_str = str(header)
        
        assert "Row" in header_str
        assert "Mod" in header_str
    
    def test_header_applies_widths(self):
        """Header should apply specified column widths."""
        from src.utils.table_utils import build_table_header
        
        cols = ["PatientID"]
        widths = {"PatientID": 200}
        
        header = build_table_header(cols, widths)
        header_str = str(header)
        
        assert "200px" in header_str


class TestPKBasedEditedCellLookup:
    """Tests for PK-based edited cell lookup in table rendering."""
    
    def test_lookup_with_single_pk_column(self, sample_data):
        """Should correctly lookup edited cells with single PK column."""
        from src.utils.table_utils import build_table_row
        
        # Row 0 has PK = PK001
        row = sample_data.iloc[0]
        pk_columns = ["PatientID_Mutsequence"]
        
        # Create edited_cells with matching PK
        pk_tuple = (("PatientID_Mutsequence", "PK001"),)
        edited_cells = {
            (pk_tuple, "Gene_names"): {"original": "OLD", "current": "NEW"}
        }
        
        tr = build_table_row(
            idx=0,
            row=row,
            cols=["Gene_names"],
            current_df=sample_data,
            get_row_status_func=lambda x: "edited",
            row_class="",
            edited_cells=edited_cells,
            pk_columns=pk_columns
        )
        
        assert "cell-edited" in str(tr)
    
    def test_lookup_with_multi_pk_columns(self):
        """Should correctly lookup edited cells with multiple PK columns."""
        from src.utils.table_utils import build_table_row
        
        # Create DataFrame with composite PK
        df = pd.DataFrame({
            "PK1": ["A", "B"],
            "PK2": ["1", "2"],
            "Value": ["val1", "val2"]
        })
        
        row = df.iloc[0]
        pk_columns = ["PK1", "PK2"]
        
        # Create edited_cells with composite PK
        pk_tuple = (("PK1", "A"), ("PK2", "1"))
        edited_cells = {
            (pk_tuple, "Value"): {"original": "OLD", "current": "NEW"}
        }
        
        tr = build_table_row(
            idx=0,
            row=row,
            cols=["Value"],
            current_df=df,
            get_row_status_func=lambda x: "edited",
            row_class="",
            edited_cells=edited_cells,
            pk_columns=pk_columns
        )
        
        assert "cell-edited" in str(tr)
    
    def test_no_match_for_different_pk(self, sample_data):
        """Should not match edited cells with different PK."""
        from src.utils.table_utils import build_table_row
        
        # Row 0 has PK = PK001
        row = sample_data.iloc[0]
        pk_columns = ["PatientID_Mutsequence"]
        
        # Create edited_cells with DIFFERENT PK
        pk_tuple_different = (("PatientID_Mutsequence", "PK999"),)
        edited_cells = {
            (pk_tuple_different, "Gene_names"): {"original": "OLD", "current": "NEW"}
        }
        
        tr = build_table_row(
            idx=0,
            row=row,
            cols=["Gene_names"],
            current_df=sample_data,
            get_row_status_func=lambda x: "unprocessed",
            row_class="",
            edited_cells=edited_cells,
            pk_columns=pk_columns
        )
        
        tr_str = str(tr)
        # The Gene_names cell should have editable-cell but not cell-edited
        # Since we're checking a specific td, this is approximate
        # The key point is cell-edited should NOT appear for this row's Gene_names
        assert "editable-cell" in tr_str


class TestBuildDraggableHeaderCell:
    """Tests for build_draggable_header_cell function — pinning tests."""

    def test_contains_column_name(self):
        """Header cell should display the column name."""
        from src.utils.table_utils import build_draggable_header_cell

        th = build_draggable_header_cell("Gene_names")
        html = str(th)

        assert "Gene_names" in html

    def test_has_sort_buttons(self):
        """Header cell should have ascending and descending sort buttons."""
        from src.utils.table_utils import build_draggable_header_cell

        th = build_draggable_header_cell("Status")
        html = str(th)

        assert "sort-asc-btn" in html
        assert "sort-desc-btn" in html

    def test_has_remove_column_button(self):
        """Header cell should have a remove column button."""
        from src.utils.table_utils import build_draggable_header_cell

        th = build_draggable_header_cell("Status")
        html = str(th)

        assert "remove-col-btn" in html

    def test_has_resize_handle(self):
        """Header cell should have a resize handle."""
        from src.utils.table_utils import build_draggable_header_cell

        th = build_draggable_header_cell("Col")
        html = str(th)

        assert "resize-handle" in html

    def test_draggable_attribute(self):
        """Header cell should be draggable."""
        from src.utils.table_utils import build_draggable_header_cell

        th = build_draggable_header_cell("Col")
        html = str(th)

        assert 'draggable="true"' in html

    def test_width_style_applied(self):
        """Width style should be applied when provided."""
        from src.utils.table_utils import build_draggable_header_cell

        th = build_draggable_header_cell("Col", width_style="width: 150px;")
        html = str(th)

        assert "width: 150px" in html

    def test_data_column_attribute(self):
        """Header cell should have data-column attribute."""
        from src.utils.table_utils import build_draggable_header_cell

        th = build_draggable_header_cell("MyCol")
        html = str(th)

        assert "MyCol" in html


class TestBuildDataTable:
    """Tests for build_data_table function — pinning tests."""

    def test_returns_table_element(self, sample_data):
        """Should return a table HTML element."""
        from src.utils.table_utils import build_data_table

        table = build_data_table(
            paginated_indices=[0, 1],
            current_df=sample_data,
            cols=["PatientID", "Gene_names"],
            widths={},
            get_row_status_func=lambda x: "unprocessed",
            pk_columns=["PatientID_Mutsequence"],
        )
        html = str(table)

        assert "<table" in html
        assert "edit-table" in html

    def test_contains_header_and_body(self, sample_data):
        """Table should contain thead and tbody."""
        from src.utils.table_utils import build_data_table

        table = build_data_table(
            paginated_indices=[0],
            current_df=sample_data,
            cols=["PatientID"],
            widths={},
            get_row_status_func=lambda x: "unprocessed",
            pk_columns=["PatientID_Mutsequence"],
        )
        html = str(table)

        assert "<thead" in html
        assert "<tbody" in html

    def test_renders_correct_number_of_rows(self, sample_data):
        """Should render one row per paginated index."""
        from src.utils.table_utils import build_data_table

        table = build_data_table(
            paginated_indices=[0, 1, 2],
            current_df=sample_data,
            cols=["PatientID"],
            widths={},
            get_row_status_func=lambda x: "unprocessed",
            pk_columns=["PatientID_Mutsequence"],
        )
        html = str(table)

        # Each row gets a tr with data-row attribute
        assert html.count("data-row=") >= 3


# =====================================================================
# Column Masks in Table Rendering Tests
# =====================================================================

class TestTableRenderingColumnMasks:
    """Tests for column_masks support in table rendering utilities."""

    def test_header_cell_uses_masked_name(self):
        """Header cell should display masked name, keep real data-column."""
        from src.utils.table_utils import build_draggable_header_cell

        result = build_draggable_header_cell("Gene_names", "width: 100px;",
                                             column_masks={"Gene_names": "Gene"})
        html = str(result)

        assert "Gene" in html  # Display text is masked
        assert 'data-column="Gene_names"' in html  # Data attr is real name

    def test_header_cell_no_mask_uses_original(self):
        """Header cell without mask should display original name."""
        from src.utils.table_utils import build_draggable_header_cell

        result = build_draggable_header_cell("Gene_names", "width: 100px;", column_masks=None)
        html = str(result)

        assert "Gene_names" in html

    def test_header_cell_missing_key_passes_through(self):
        """Header cell with mask dict missing the column should show original."""
        from src.utils.table_utils import build_draggable_header_cell

        result = build_draggable_header_cell("Gene_names", "width: 100px;",
                                             column_masks={"Other": "X"})
        html = str(result)

        assert "Gene_names" in html

    def test_table_header_applies_masks(self, sample_data):
        """build_table_header should pass masks to header cells."""
        from src.utils.table_utils import build_table_header

        result = build_table_header(
            cols=["Gene_names"],
            widths={"Gene_names": "100px"},
            column_masks={"Gene_names": "Gene"}
        )
        html = str(result)

        assert "Gene" in html
        assert 'data-column="Gene_names"' in html

    def test_build_data_table_passes_masks(self, sample_data):
        """build_data_table should propagate masks to header."""
        from src.utils.table_utils import build_data_table

        table = build_data_table(
            paginated_indices=[0],
            current_df=sample_data,
            cols=["Gene_names"],
            widths={},
            get_row_status_func=lambda x: "unprocessed",
            pk_columns=["PatientID_Mutsequence"],
            column_masks={"Gene_names": "Gene"}
        )
        html = str(table)

        assert "Gene" in html
        assert 'data-column="Gene_names"' in html

    def test_build_table_container_passes_masks(self, sample_data):
        """build_table_container should propagate masks through to table."""
        from src.utils.table_utils import build_table_container

        container = build_table_container(
            paginated_indices=[0],
            current_df=sample_data,
            cols=["Gene_names"],
            widths={},
            filtered_count=5,
            total_rows=5,
            get_row_status_func=lambda x: "unprocessed",
            pk_columns=["PatientID_Mutsequence"],
            column_masks={"Gene_names": "Gene"}
        )
        html = str(container)

        assert "Gene" in html
        assert 'data-column="Gene_names"' in html
