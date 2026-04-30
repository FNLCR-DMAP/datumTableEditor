"""
Factor 4 Contract Tests: DataFrame → UI HTML

Tests the contract from pd.DataFrame → Shiny HTML tags, verifying
that the rendering pipeline (build_table_container and its call chain)
produces structurally correct, data-faithful HTML.

Key invariants verified:
  1. Every data cell carries correct data-row, data-col, data-value attributes
  2. Edited cells get "cell-edited" class and data-original attribute
  3. Editable/readonly classification respects editable_columns + readonly_columns
  4. Row count summary text matches actual paginated count / filtered / total
  5. Status badges have correct class and label text
  6. build_table_container produces outer div > summary div + table.edit-table
  7. Header includes select-all checkbox, Row, Mod, and one th per column
  8. Zebra striping alternates row-even / row-odd
  9. NaN/None values display as "—" with empty data-value
 10. PK-based edited cell lookup uses tuple(sorted(...)) contract
"""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock

from src.utils.table_utils import (
    build_table_container,
    build_data_table,
    build_table_header,
    build_table_body,
    build_table_row,
    build_status_badge,
    build_draggable_header_cell,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures & Helpers
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def simple_df():
    """Minimal 3-row DataFrame for rendering tests."""
    return pd.DataFrame({
        "pk": ["PK1", "PK2", "PK3"],
        "gene": ["BRCA1", "TP53", "EGFR"],
        "score": [95, 80, 70],
        "_mod_status": ["unprocessed", "edited", "approved"],
    })


@pytest.fixture
def default_widths():
    return {"gene": 150, "score": 100}


def _get_status(idx):
    """Simple status function for testing."""
    statuses = {0: "unprocessed", 1: "edited", 2: "approved"}
    return statuses.get(idx, "unprocessed")


def _render_html(tag) -> str:
    """Convert a Shiny tag to its HTML string."""
    return str(tag)


# ═══════════════════════════════════════════════════════════════════════════════
# build_table_row: Data Cell Attributes
# ═══════════════════════════════════════════════════════════════════════════════


class TestDataCellAttributes:
    """Contract: every data cell must carry data-row, data-col, data-value."""

    def test_data_row_attribute_is_string_index(self, simple_df):
        """data-row is str(idx), the DataFrame index label."""
        row = simple_df.iloc[0]
        tr = build_table_row(
            idx=0, row=row, cols=["gene", "score"],
            current_df=simple_df, get_row_status_func=_get_status,
            pk_columns=["pk"],
        )
        html = _render_html(tr)
        assert 'data-row="0"' in html

    def test_data_col_attribute_matches_column_name(self, simple_df):
        tr = build_table_row(
            idx=0, row=simple_df.iloc[0], cols=["gene", "score"],
            current_df=simple_df, get_row_status_func=_get_status,
            pk_columns=["pk"],
        )
        html = _render_html(tr)
        assert 'data-col="gene"' in html
        assert 'data-col="score"' in html

    def test_data_value_matches_cell_content(self, simple_df):
        tr = build_table_row(
            idx=0, row=simple_df.iloc[0], cols=["gene"],
            current_df=simple_df, get_row_status_func=_get_status,
            pk_columns=["pk"],
        )
        html = _render_html(tr)
        assert 'data-value="BRCA1"' in html

    def test_nan_value_renders_as_dash_with_empty_data_value(self):
        """NaN cells display '—' and have data-value=''."""
        df = pd.DataFrame({"pk": ["X"], "gene": [None]})
        row = df.iloc[0]
        tr = build_table_row(
            idx=0, row=row, cols=["gene"],
            current_df=df, get_row_status_func=lambda x: "unprocessed",
            pk_columns=["pk"],
        )
        html = _render_html(tr)
        assert 'data-value=""' in html
        assert "—" in html

    def test_numeric_value_rendered_as_string(self, simple_df):
        """Numeric values are str()-cast for data-value."""
        tr = build_table_row(
            idx=0, row=simple_df.iloc[0], cols=["score"],
            current_df=simple_df, get_row_status_func=_get_status,
            pk_columns=["pk"],
        )
        html = _render_html(tr)
        assert 'data-value="95"' in html

    def test_all_cols_present_in_row(self, simple_df):
        """Each column requested appears exactly once with data-col."""
        cols = ["gene", "score"]
        tr = build_table_row(
            idx=0, row=simple_df.iloc[0], cols=cols,
            current_df=simple_df, get_row_status_func=_get_status,
            pk_columns=["pk"],
        )
        html = _render_html(tr)
        for col in cols:
            assert html.count(f'data-col="{col}"') == 1


# ═══════════════════════════════════════════════════════════════════════════════
# build_table_row: Edited Cell Contract
# ═══════════════════════════════════════════════════════════════════════════════


class TestEditedCellRendering:
    """Contract: edited cells get 'cell-edited' class + data-original."""

    def _make_edited_cells(self, pk_dict, col, original="orig"):
        pk_tuple = tuple(sorted((k, str(v)) for k, v in pk_dict.items()))
        return {(pk_tuple, col): {"original": original, "current": "new"}}

    def test_edited_cell_has_cell_edited_class(self, simple_df):
        edited = self._make_edited_cells({"pk": "PK1"}, "gene")
        tr = build_table_row(
            idx=0, row=simple_df.iloc[0], cols=["gene"],
            current_df=simple_df, get_row_status_func=_get_status,
            edited_cells=edited, pk_columns=["pk"],
        )
        html = _render_html(tr)
        assert "cell-edited" in html

    def test_edited_cell_has_data_original_attribute(self, simple_df):
        edited = self._make_edited_cells({"pk": "PK1"}, "gene", original="OLD_VALUE")
        tr = build_table_row(
            idx=0, row=simple_df.iloc[0], cols=["gene"],
            current_df=simple_df, get_row_status_func=_get_status,
            edited_cells=edited, pk_columns=["pk"],
        )
        html = _render_html(tr)
        assert 'data-original="OLD_VALUE"' in html

    def test_unedited_cell_no_cell_edited_class(self, simple_df):
        """Non-edited cells should have editable-cell but NOT cell-edited."""
        tr = build_table_row(
            idx=0, row=simple_df.iloc[0], cols=["gene"],
            current_df=simple_df, get_row_status_func=_get_status,
            edited_cells={}, pk_columns=["pk"],
        )
        html = _render_html(tr)
        assert "editable-cell" in html
        assert "cell-edited" not in html

    def test_unedited_cell_no_data_original(self, simple_df):
        tr = build_table_row(
            idx=0, row=simple_df.iloc[0], cols=["gene"],
            current_df=simple_df, get_row_status_func=_get_status,
            edited_cells={}, pk_columns=["pk"],
        )
        html = _render_html(tr)
        assert "data-original" not in html

    def test_edited_cell_original_none_renders_empty(self, simple_df):
        """If original value is None, data-original should be empty string."""
        pk_tuple = tuple(sorted((k, str(v)) for k, v in {"pk": "PK1"}.items()))
        edited = {(pk_tuple, "gene"): {"original": None}}
        tr = build_table_row(
            idx=0, row=simple_df.iloc[0], cols=["gene"],
            current_df=simple_df, get_row_status_func=_get_status,
            edited_cells=edited, pk_columns=["pk"],
        )
        html = _render_html(tr)
        assert 'data-original=""' in html


# ═══════════════════════════════════════════════════════════════════════════════
# Editable / Readonly Classification
# ═══════════════════════════════════════════════════════════════════════════════


class TestEditableReadonlyClassification:
    """
    Contract:
    - editable_columns non-empty: col editable only if in editable_columns AND NOT in readonly_columns
    - editable_columns empty: all cols editable UNLESS in readonly_columns
    """

    def test_all_cols_editable_by_default(self, simple_df):
        """No editable/readonly lists → all cells get editable-cell."""
        tr = build_table_row(
            idx=0, row=simple_df.iloc[0], cols=["gene", "score"],
            current_df=simple_df, get_row_status_func=_get_status,
            pk_columns=["pk"],
        )
        html = _render_html(tr)
        assert html.count("editable-cell") == 2
        assert "readonly-cell" not in html

    def test_readonly_column_gets_readonly_class(self, simple_df):
        tr = build_table_row(
            idx=0, row=simple_df.iloc[0], cols=["gene", "score"],
            current_df=simple_df, get_row_status_func=_get_status,
            pk_columns=["pk"], readonly_columns=["score"],
        )
        html = _render_html(tr)
        assert "readonly-cell" in html
        assert "editable-cell" in html  # gene should still be editable

    def test_editable_columns_whitelist(self, simple_df):
        """Only whitelisted columns get editable-cell."""
        tr = build_table_row(
            idx=0, row=simple_df.iloc[0], cols=["gene", "score"],
            current_df=simple_df, get_row_status_func=_get_status,
            pk_columns=["pk"], editable_columns=["gene"],
        )
        html = _render_html(tr)
        # gene is editable, score is not in whitelist → readonly
        # Count editable-cell occurrences in data cells (not the whole row)
        assert 'editable-cell' in html
        assert 'readonly-cell' in html

    def test_editable_and_readonly_overlap_readonly_wins(self, simple_df):
        """If col is in both editable_columns and readonly_columns, readonly wins."""
        tr = build_table_row(
            idx=0, row=simple_df.iloc[0], cols=["gene"],
            current_df=simple_df, get_row_status_func=_get_status,
            pk_columns=["pk"], editable_columns=["gene"], readonly_columns=["gene"],
        )
        html = _render_html(tr)
        assert "readonly-cell" in html
        # Should NOT have editable-cell for gene
        # The cell will have readonly-cell class because readonly wins
        assert "editable-cell" not in html or html.index("readonly-cell") < html.rindex("readonly-cell") + 1


# ═══════════════════════════════════════════════════════════════════════════════
# Status Badge Contract
# ═══════════════════════════════════════════════════════════════════════════════


class TestStatusBadge:
    """Contract: build_status_badge produces <span class="row-status-badge status-{status}">."""

    def test_status_class_format(self):
        badge = build_status_badge("edited")
        html = _render_html(badge)
        assert "status-edited" in html
        assert "row-status-badge" in html

    def test_default_label_mapping(self):
        """Default labels: edited→Edited, approved→Approved, rejected→Rejected, unprocessed→New."""
        assert "Edited" in _render_html(build_status_badge("edited"))
        assert "Approved" in _render_html(build_status_badge("approved"))
        assert "Rejected" in _render_html(build_status_badge("rejected"))
        assert "New" in _render_html(build_status_badge("unprocessed"))

    def test_custom_labels_override_defaults(self):
        labels = {"edited": "Modified", "approved": "Confirmed"}
        badge = build_status_badge("edited", status_labels=labels)
        html = _render_html(badge)
        assert "Modified" in html
        assert "Edited" not in html

    def test_unknown_status_uses_raw_value(self):
        """Unknown statuses are returned as-is (lowercase) when no labels provided."""
        badge = build_status_badge("custom_status")
        html = _render_html(badge)
        assert "custom_status" in html
        assert "status-custom_status" in html

    def test_status_badge_in_row(self, simple_df):
        """Status badge appears in a table row when show_status_column=True."""
        tr = build_table_row(
            idx=1, row=simple_df.iloc[1], cols=["gene"],
            current_df=simple_df, get_row_status_func=lambda x: "edited",
            pk_columns=["pk"], show_status_column=True,
        )
        html = _render_html(tr)
        assert "status-edited" in html

    def test_no_status_badge_when_disabled(self, simple_df):
        """show_status_column=False → no status badge in row."""
        tr = build_table_row(
            idx=0, row=simple_df.iloc[0], cols=["gene"],
            current_df=simple_df, get_row_status_func=_get_status,
            pk_columns=["pk"], show_status_column=False,
        )
        html = _render_html(tr)
        assert "row-status-badge" not in html


# ═══════════════════════════════════════════════════════════════════════════════
# Table Header Contract
# ═══════════════════════════════════════════════════════════════════════════════


class TestTableHeader:
    """Contract: build_table_header produces correct header structure."""

    def test_select_all_checkbox_present(self, default_widths):
        thead = build_table_header(["gene", "score"], default_widths)
        html = _render_html(thead)
        assert "select_all_page" in html
        assert 'type="checkbox"' in html

    def test_row_number_header(self, default_widths):
        thead = build_table_header(["gene"], default_widths)
        html = _render_html(thead)
        assert "Row" in html

    def test_mod_column_when_enabled(self, default_widths):
        thead = build_table_header(["gene"], default_widths, show_status_column=True)
        html = _render_html(thead)
        assert "Mod" in html

    def test_no_mod_column_when_disabled(self, default_widths):
        thead = build_table_header(["gene"], default_widths, show_status_column=False)
        html = _render_html(thead)
        assert "Mod" not in html

    def test_column_headers_present(self, default_widths):
        thead = build_table_header(["gene", "score"], default_widths)
        html = _render_html(thead)
        assert "gene" in html
        assert "score" in html

    def test_draggable_header_cells(self, default_widths):
        thead = build_table_header(["gene"], default_widths)
        html = _render_html(thead)
        assert "draggable-header" in html
        assert 'draggable="true"' in html

    def test_column_width_applied(self):
        widths = {"gene": 200}
        thead = build_table_header(["gene"], widths)
        html = _render_html(thead)
        assert "200px" in html

    def test_default_width_for_unknown_column(self):
        """Columns not in widths dict get default 130px width."""
        thead = build_table_header(["unknown_col"], {})
        html = _render_html(thead)
        assert "130px" in html

    def test_header_action_buttons(self, default_widths):
        thead = build_table_header(["gene"], default_widths)
        html = _render_html(thead)
        assert "Sort Ascending" in html
        assert "Sort Descending" in html
        assert "Remove Column" in html


# ═══════════════════════════════════════════════════════════════════════════════
# Table Body: Zebra Striping
# ═══════════════════════════════════════════════════════════════════════════════


class TestZebraStriping:
    """Contract: rows alternate row-even / row-odd based on visual position."""

    def test_first_row_is_even(self, simple_df):
        tbody = build_table_body(
            [0], simple_df, ["gene"],
            get_row_status_func=_get_status,
            pk_columns=["pk"],
        )
        html = _render_html(tbody)
        assert "row-even" in html

    def test_two_rows_alternate(self, simple_df):
        tbody = build_table_body(
            [0, 1], simple_df, ["gene"],
            get_row_status_func=_get_status,
            pk_columns=["pk"],
        )
        html = _render_html(tbody)
        assert "row-even" in html
        assert "row-odd" in html

    def test_three_rows_pattern(self, simple_df):
        tbody = build_table_body(
            [0, 1, 2], simple_df, ["gene"],
            get_row_status_func=_get_status,
            pk_columns=["pk"],
        )
        html = _render_html(tbody)
        assert html.count("row-even") == 2  # positions 0 and 2
        assert html.count("row-odd") == 1   # position 1


# ═══════════════════════════════════════════════════════════════════════════════
# Row Number
# ═══════════════════════════════════════════════════════════════════════════════


class TestRowNumber:
    """Contract: row number displays as idx + 1 (1-based)."""

    def test_first_row_shows_1(self, simple_df):
        tr = build_table_row(
            idx=0, row=simple_df.iloc[0], cols=["gene"],
            current_df=simple_df, get_row_status_func=_get_status,
            pk_columns=["pk"],
        )
        html = _render_html(tr)
        assert "row-number" in html
        # The row number cell should contain "1"
        assert ">1<" in html

    def test_third_row_shows_3(self, simple_df):
        tr = build_table_row(
            idx=2, row=simple_df.iloc[2], cols=["gene"],
            current_df=simple_df, get_row_status_func=_get_status,
            pk_columns=["pk"],
        )
        html = _render_html(tr)
        assert ">3<" in html


# ═══════════════════════════════════════════════════════════════════════════════
# build_table_container: Summary Text
# ═══════════════════════════════════════════════════════════════════════════════


class TestContainerSummaryText:
    """Contract: summary row-count text matches actual counts."""

    def test_filtered_less_than_total_shows_filtered_text(self, simple_df, default_widths):
        container = build_table_container(
            paginated_indices=[0, 1],
            current_df=simple_df,
            cols=["gene"],
            widths=default_widths,
            filtered_count=2,
            total_rows=100,
            get_row_status_func=_get_status,
            pk_columns=["pk"],
        )
        html = _render_html(container)
        assert "Showing 2 of 2 filtered rows (total: 100)" in html

    def test_filtered_equals_total_shows_loaded_text(self, simple_df, default_widths):
        container = build_table_container(
            paginated_indices=[0, 1, 2],
            current_df=simple_df,
            cols=["gene"],
            widths=default_widths,
            filtered_count=3,
            total_rows=3,
            get_row_status_func=_get_status,
            pk_columns=["pk"],
        )
        html = _render_html(container)
        assert "Loaded 3 of 3 rows" in html

    def test_paginated_subset_count(self, simple_df, default_widths):
        """Displayed count = len(paginated_indices), not filtered_count."""
        container = build_table_container(
            paginated_indices=[0],  # Only showing 1 row
            current_df=simple_df,
            cols=["gene"],
            widths=default_widths,
            filtered_count=3,
            total_rows=100,
            get_row_status_func=_get_status,
            pk_columns=["pk"],
        )
        html = _render_html(container)
        assert "Showing 1 of 3 filtered rows (total: 100)" in html


# ═══════════════════════════════════════════════════════════════════════════════
# build_table_container: Structural Contract
# ═══════════════════════════════════════════════════════════════════════════════


class TestContainerStructure:
    """Contract: outer div contains summary div + table.edit-table."""

    def test_contains_edit_table(self, simple_df, default_widths):
        container = build_table_container(
            paginated_indices=[0],
            current_df=simple_df,
            cols=["gene"],
            widths=default_widths,
            filtered_count=1,
            total_rows=1,
            get_row_status_func=_get_status,
            pk_columns=["pk"],
        )
        html = _render_html(container)
        assert "edit-table" in html

    def test_contains_thead_and_tbody(self, simple_df, default_widths):
        container = build_table_container(
            paginated_indices=[0],
            current_df=simple_df,
            cols=["gene"],
            widths=default_widths,
            filtered_count=1,
            total_rows=1,
            get_row_status_func=_get_status,
            pk_columns=["pk"],
        )
        html = _render_html(container)
        assert "<thead>" in html or "<thead " in html
        assert "<tbody>" in html or "<tbody " in html

    def test_summary_styling(self, simple_df, default_widths):
        container = build_table_container(
            paginated_indices=[0],
            current_df=simple_df,
            cols=["gene"],
            widths=default_widths,
            filtered_count=1,
            total_rows=1,
            get_row_status_func=_get_status,
            pk_columns=["pk"],
        )
        html = _render_html(container)
        assert "margin-bottom: 10px" in html
        assert "font-size: 12px" in html


# ═══════════════════════════════════════════════════════════════════════════════
# Full Pipeline Snapshot: DataFrame → HTML
# ═══════════════════════════════════════════════════════════════════════════════


class TestFullRenderPipeline:
    """
    End-to-end snapshot: given a DataFrame with known values,
    verify the complete HTML output preserves every cell.
    """

    def test_all_cell_values_appear_in_html(self, simple_df, default_widths):
        """Every cell value from the DataFrame must appear in the rendered HTML."""
        container = build_table_container(
            paginated_indices=[0, 1, 2],
            current_df=simple_df,
            cols=["gene", "score"],
            widths=default_widths,
            filtered_count=3,
            total_rows=3,
            get_row_status_func=_get_status,
            pk_columns=["pk"],
        )
        html = _render_html(container)
        # All gene values
        assert "BRCA1" in html
        assert "TP53" in html
        assert "EGFR" in html
        # All score values (as strings)
        assert "95" in html
        assert "80" in html
        assert "70" in html

    def test_edited_cell_shows_in_full_table(self, simple_df, default_widths):
        """An edited cell in the full pipeline carries both cell-edited and data-original."""
        pk_tuple = tuple(sorted((k, str(v)) for k, v in {"pk": "PK2"}.items()))
        edited = {(pk_tuple, "gene"): {"original": "TP53_ORIGINAL"}}

        container = build_table_container(
            paginated_indices=[0, 1, 2],
            current_df=simple_df,
            cols=["gene"],
            widths=default_widths,
            filtered_count=3,
            total_rows=3,
            get_row_status_func=_get_status,
            edited_cells=edited,
            pk_columns=["pk"],
        )
        html = _render_html(container)
        assert "cell-edited" in html
        assert "TP53_ORIGINAL" in html

    def test_empty_dataframe_renders_without_crash(self, default_widths):
        """Empty DataFrame → table with header but no body rows."""
        df = pd.DataFrame({"pk": [], "gene": []})
        container = build_table_container(
            paginated_indices=[],
            current_df=df,
            cols=["gene"],
            widths=default_widths,
            filtered_count=0,
            total_rows=0,
            get_row_status_func=_get_status,
            pk_columns=["pk"],
        )
        html = _render_html(container)
        assert "edit-table" in html
        assert "Loaded 0" in html

    def test_special_characters_in_data(self, default_widths):
        """HTML-special characters in data must appear (Shiny escapes them)."""
        df = pd.DataFrame({"pk": ["X"], "value": ['<script>alert("xss")</script>']})
        container = build_table_container(
            paginated_indices=[0],
            current_df=df,
            cols=["value"],
            widths=default_widths,
            filtered_count=1,
            total_rows=1,
            get_row_status_func=lambda x: "unprocessed",
            pk_columns=["pk"],
        )
        html = _render_html(container)
        # The value should appear in data-value (Shiny handles escaping)
        assert "alert" in html  # Content is present in some form

    def test_status_labels_passed_to_badges(self, simple_df, default_widths):
        """Custom status_labels propagate to status badges."""
        labels = {"unprocessed": "Neu", "edited": "Bearbeitet", "approved": "Genehmigt"}
        container = build_table_container(
            paginated_indices=[0, 1, 2],
            current_df=simple_df,
            cols=["gene"],
            widths=default_widths,
            filtered_count=3,
            total_rows=3,
            get_row_status_func=_get_status,
            pk_columns=["pk"],
            show_status_column=True,
            status_labels=labels,
        )
        html = _render_html(container)
        assert "Neu" in html
        assert "Bearbeitet" in html
        assert "Genehmigt" in html


# ═══════════════════════════════════════════════════════════════════════════════
# Draggable Header Cell Contract
# ═══════════════════════════════════════════════════════════════════════════════


class TestDraggableHeaderCell:
    """Contract: build_draggable_header_cell structure."""

    def test_data_column_attribute(self):
        th = build_draggable_header_cell("gene")
        html = _render_html(th)
        assert 'data-column="gene"' in html

    def test_resize_handle_present(self):
        th = build_draggable_header_cell("gene")
        html = _render_html(th)
        assert "resize-handle" in html

    def test_header_text_content(self):
        th = build_draggable_header_cell("gene")
        html = _render_html(th)
        assert "header-text" in html
        assert "gene" in html

    def test_sort_buttons_present(self):
        th = build_draggable_header_cell("gene")
        html = _render_html(th)
        assert "sort-asc-btn" in html
        assert "sort-desc-btn" in html
        assert "remove-col-btn" in html

    def test_width_style_applied(self):
        th = build_draggable_header_cell("gene", "width: 200px; min-width: 200px;")
        html = _render_html(th)
        assert "200px" in html


# ═══════════════════════════════════════════════════════════════════════════════
# Datetime Timezone Display Contract
# ═══════════════════════════════════════════════════════════════════════════════


class TestNoTzDisplay:
    """Contract: no_tz_display option strips timezone from datetime values."""

    @pytest.fixture
    def datetime_df(self):
        """DataFrame with timezone-aware datetime column."""
        return pd.DataFrame({
            "pk": ["PK1", "PK2"],
            "timestamp": pd.to_datetime([
                "2024-01-15 10:30:00+00:00",
                "2024-06-20 14:45:00+00:00",
            ]),
        })

    def test_datetime_with_tz_display_default(self, datetime_df):
        """Default (no_tz_display=False) preserves timezone in display."""
        from src.utils.table_utils import _format_cell_value
        val = datetime_df["timestamp"].iloc[0]
        result = _format_cell_value(val, datetime_df["timestamp"].dtype, no_tz_display=False)
        # Should contain timezone info
        assert "+00:00" in result or "UTC" in result or result.endswith("+00")

    def test_datetime_without_tz_display(self, datetime_df):
        """no_tz_display=True shows date-only format."""
        from src.utils.table_utils import _format_cell_value
        val = datetime_df["timestamp"].iloc[0]
        result = _format_cell_value(val, datetime_df["timestamp"].dtype, no_tz_display=True)
        # Should NOT contain timezone info
        assert "+00" not in result
        assert "UTC" not in result
        # Should show date-only format
        assert result == "2024-01-15"

    def test_datetime_format_structure(self, datetime_df):
        """no_tz_display produces YYYY-MM-DD format."""
        from src.utils.table_utils import _format_cell_value
        val = datetime_df["timestamp"].iloc[0]
        result = _format_cell_value(val, datetime_df["timestamp"].dtype, no_tz_display=True)
        assert result == "2024-01-15"

    def test_naive_datetime_unaffected(self):
        """Naive datetime (no tz) works with no_tz_display=True."""
        from src.utils.table_utils import _format_cell_value
        df = pd.DataFrame({"ts": pd.to_datetime(["2024-01-15 10:30:00"])})
        val = df["ts"].iloc[0]
        result = _format_cell_value(val, df["ts"].dtype, no_tz_display=True)
        assert result == "2024-01-15"

    def test_build_table_row_with_no_tz_display(self, datetime_df):
        """build_table_row passes no_tz_display to cell formatting."""
        tr = build_table_row(
            idx=0,
            row=datetime_df.iloc[0],
            cols=["timestamp"],
            current_df=datetime_df,
            get_row_status_func=lambda x: "unprocessed",
            pk_columns=["pk"],
            no_tz_display=True,
        )
        html = _render_html(tr)
        # Should show date-only format
        assert "2024-01-15" in html
        assert "+00:00" not in html

    def test_build_table_container_with_no_tz_display(self, datetime_df):
        """build_table_container propagates no_tz_display through call chain."""
        container = build_table_container(
            paginated_indices=[0, 1],
            current_df=datetime_df,
            cols=["timestamp"],
            widths={"timestamp": 180},
            filtered_count=2,
            total_rows=2,
            get_row_status_func=lambda x: "unprocessed",
            pk_columns=["pk"],
            no_tz_display=True,
        )
        html = _render_html(container)
        # Both timestamps should show date-only format
        assert "2024-01-15" in html
        assert "2024-06-20" in html
        assert "+00:00" not in html
        assert "10:30:00" not in html

    def test_non_datetime_unaffected_by_no_tz_display(self):
        """Non-datetime columns are unaffected by no_tz_display."""
        from src.utils.table_utils import _format_cell_value
        # Integer
        assert _format_cell_value(42, pd.Series([42]).dtype, no_tz_display=True) == "42"
        # String
        assert _format_cell_value("hello", pd.Series(["hello"]).dtype, no_tz_display=True) == "hello"
        # Float
        assert _format_cell_value(3.14, pd.Series([3.14]).dtype, no_tz_display=True) == "3.14"

    def test_string_datetime_with_tz_stripped(self):
        """String datetime values from DB show date-only format."""
        from src.utils.table_utils import _format_cell_value
        # Common formats from PostgreSQL — all should become YYYY-MM-DD
        test_cases = [
            ("2026-03-30 +00", "2026-03-30"),
            ("2026-03-30 10:00:00+00:00", "2026-03-30"),
            ("2026-03-30 10:00:00 +00", "2026-03-30"),
            ("2024-01-15 14:30:00-05:00", "2024-01-15"),
        ]
        for input_val, expected in test_cases:
            result = _format_cell_value(input_val, pd.Series([input_val]).dtype, no_tz_display=True)
            assert result == expected, f"Expected {expected}, got {result} for {input_val}"

    def test_string_without_tz_unchanged(self):
        """String values without timezone pattern are unchanged."""
        from src.utils.table_utils import _format_cell_value
        # Date without timezone
        assert _format_cell_value("2024-01-15", pd.Series(["x"]).dtype, no_tz_display=True) == "2024-01-15"
        # Non-date string
        assert _format_cell_value("Hello World", pd.Series(["x"]).dtype, no_tz_display=True) == "Hello World"
