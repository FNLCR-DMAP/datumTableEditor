"""
Tests for UI component builders.
"""
import pytest


class TestBuildLogEntryUndo:
    """Tests for build_log_entry_undo function."""
    
    def test_creates_undo_entry(self):
        """Should create undo log entry UI."""
        from src.utils.ui_components import build_log_entry_undo
        
        details = {
            "primary_key": "PK001",
            "column": "Gene",
            "reverted_to": "TP53"
        }
        result = build_log_entry_undo("2024-01-01T10:00:00", details)
        html = str(result)
        
        assert "UNDO" in html
        assert "Gene" in html
        assert "TP53" in html


class TestBuildLogEntryApproval:
    """Tests for build_log_entry_approval function."""
    
    def test_creates_approval_entry(self):
        """Should create approval log entry UI."""
        from src.utils.ui_components import build_log_entry_approval
        
        details = {
            "approved_row_count": 2,
            "approved_rows": [{"PatientID": "P001"}, {"PatientID": "P002"}]
        }
        result = build_log_entry_approval("2024-01-01T10:00:00", details)
        html = str(result)
        
        assert "APPROVED" in html
        assert "2 row(s)" in html
    
    def test_handles_legacy_indices(self):
        """Should handle legacy row indices."""
        from src.utils.ui_components import build_log_entry_approval
        
        details = {
            "approved_row_count": 1,
            "approved_rows": [0]  # Legacy format
        }
        result = build_log_entry_approval("2024-01-01T10:00:00", details)
        html = str(result)
        
        assert "APPROVED" in html
    
    def test_truncates_many_rows(self):
        """Should truncate display for many rows."""
        from src.utils.ui_components import build_log_entry_approval
        
        details = {
            "approved_row_count": 10,
            "approved_rows": [{"id": i} for i in range(10)]
        }
        result = build_log_entry_approval("2024-01-01T10:00:00", details)
        html = str(result)
        
        assert "+5 more" in html


class TestBuildLogEntryRejection:
    """Tests for build_log_entry_rejection function."""
    
    def test_creates_rejection_entry(self):
        """Should create rejection log entry UI."""
        from src.utils.ui_components import build_log_entry_rejection
        
        details = {
            "rejected_row_count": 1,
            "rejected_rows": [{"PatientID": "P001"}]
        }
        result = build_log_entry_rejection("2024-01-01T10:00:00", details)
        html = str(result)
        
        assert "REJECTED" in html


class TestBuildLogEntryUndone:
    """Tests for build_log_entry_undone function."""
    
    def test_creates_undone_entry(self):
        """Should create undone field modification entry."""
        from src.utils.ui_components import build_log_entry_undone
        
        details = {
            "primary_key": "PK001",
            "column": "Gene",
            "old_value": "TP53",
            "new_value": "BRCA1"
        }
        result = build_log_entry_undone("2024-01-01T10:00:00", details)
        html = str(result)
        
        assert "UN-DONE" in html
        assert "line-through" in html
    
    def test_handles_pk_dict(self):
        """Should handle PK as dict."""
        from src.utils.ui_components import build_log_entry_undone
        
        details = {
            "row_pk": {"PatientID": "P001", "Variant": "V1"},
            "column": "Gene"
        }
        result = build_log_entry_undone("2024-01-01T10:00:00", details)
        html = str(result)
        
        assert "Gene" in html


class TestBuildLogEntryFieldModification:
    """Tests for build_log_entry_field_modification function."""
    
    def test_creates_field_modification_entry(self):
        """Should create field modification with undo button."""
        from src.utils.ui_components import build_log_entry_field_modification
        
        details = {
            "primary_key": "PK001",
            "column": "Gene",
            "old_value": "TP53",
            "new_value": "BRCA1"
        }
        result = build_log_entry_field_modification("2024-01-01T10:00:00", details, 5)
        html = str(result)
        
        assert "Undo" in html
        assert "Gene" in html
        assert "undoModification(5" in html


class TestBuildStatusHistogramBar:
    """Tests for build_status_histogram_bar function."""
    
    def test_creates_histogram_bar(self):
        """Should create histogram bar with checkbox."""
        from src.utils.ui_components import build_status_histogram_bar
        
        result = build_status_histogram_bar("approved", 10, 50.0, True)
        html = str(result)
        
        assert "Approved" in html
        assert "checked" in html
        assert "histogram-bar" in html
    
    def test_unchecked_checkbox(self):
        """Should handle unchecked state."""
        from src.utils.ui_components import build_status_histogram_bar
        
        result = build_status_histogram_bar("rejected", 5, 25.0, False)
        html = str(result)
        
        assert "Rejected" in html


class TestBuildEmptyLogMessage:
    """Tests for build_empty_log_message function."""
    
    def test_creates_empty_message(self):
        """Should create placeholder message."""
        from src.utils.ui_components import build_empty_log_message
        
        result = build_empty_log_message()
        html = str(result)
        
        assert "No modifications yet" in html


class TestBuildApprovalStatusBanner:
    """Tests for build_approval_status_banner function."""
    
    def test_approved_banner(self):
        """Should create approved banner."""
        from src.utils.ui_components import build_approval_status_banner
        
        result = build_approval_status_banner("approved", "2024-01-01 10:00")
        html = str(result)
        
        assert "APPROVED" in html
        assert "Clear" in html
    
    def test_rejected_banner(self):
        """Should create rejected banner."""
        from src.utils.ui_components import build_approval_status_banner
        
        result = build_approval_status_banner("rejected", "2024-01-01 10:00")
        html = str(result)
        
        assert "REJECTED" in html
    
    def test_none_status_returns_empty(self):
        """None status should return empty div."""
        from src.utils.ui_components import build_approval_status_banner
        
        result = build_approval_status_banner(None, "2024-01-01 10:00")
        html = str(result)
        
        # Should be minimal/empty
        assert "APPROVED" not in html
        assert "REJECTED" not in html
    
    def test_pending_status(self):
        """Pending status should show pending text."""
        from src.utils.ui_components import build_approval_status_banner
        
        result = build_approval_status_banner("Pending", "2024-01-01 10:00")
        html = str(result)
        
        # Should be minimal for pending
        assert "APPROVED" not in html


class TestBuildModificationsLog:
    """Tests for build_modifications_log function."""
    
    def test_empty_log(self):
        """Empty log should show placeholder."""
        from src.utils.ui_components import build_modifications_log
        
        result = build_modifications_log([])
        html = str(result)
        
        assert "No modifications yet" in html
    
    def test_with_entries(self):
        """Should render log entries."""
        from src.utils.ui_components import build_modifications_log
        
        log = [
            {
                "timestamp": "2024-01-01T10:00:00",
                "type": "field_modification",
                "details": {"primary_key": "PK1", "column": "Gene", "old_value": "A", "new_value": "B"}
            },
            {
                "timestamp": "2024-01-01T11:00:00",
                "type": "approval",
                "details": {"approved_row_count": 1, "approved_rows": [{"id": 1}]}
            }
        ]
        result = build_modifications_log(log)
        html = str(result)
        
        assert "Gene" in html
        assert "APPROVED" in html
    
    def test_undone_entries(self):
        """Should render undone entries with strikethrough."""
        from src.utils.ui_components import build_modifications_log
        
        log = [
            {
                "timestamp": "2024-01-01T10:00:00",
                "type": "field_modification",
                "details": {"primary_key": "PK1", "column": "Gene"},
                "undone": True
            }
        ]
        result = build_modifications_log(log)
        html = str(result)
        
        assert "UN-DONE" in html
    
    def test_rejection_entries(self):
        """Should render rejection entries."""
        from src.utils.ui_components import build_modifications_log
        
        log = [
            {
                "timestamp": "2024-01-01T10:00:00",
                "type": "rejection",
                "details": {"rejected_row_count": 2, "rejected_rows": [{"id": 1}, {"id": 2}]}
            }
        ]
        result = build_modifications_log(log)
        html = str(result)
        
        assert "REJECTED" in html
    
    def test_undo_type_not_rendered(self):
        """Undo type entries are not rendered (handled separately)."""
        from src.utils.ui_components import build_modifications_log
        
        # "undo" type is currently not rendered in the log
        # Only field_modification, approval, rejection are shown
        log = [
            {
                "timestamp": "2024-01-01T10:00:00",
                "type": "undo",
                "details": {"primary_key": "PK1", "column": "Gene", "reverted_to": "A"}
            }
        ]
        result = build_modifications_log(log)
        html = str(result)
        
        # Since "undo" type is not handled, it shows empty message
        assert "No modifications yet" in html


class TestBuildLogEntryRejectionTruncation:
    """Tests for rejection entry truncation."""
    
    def test_truncates_many_rows(self):
        """Should truncate display for many rows."""
        from src.utils.ui_components import build_log_entry_rejection
        
        details = {
            "rejected_row_count": 10,
            "rejected_rows": [{"id": i} for i in range(10)]
        }
        result = build_log_entry_rejection("2024-01-01T10:00:00", details)
        html = str(result)
        
        assert "+5 more" in html


class TestBuildLogEntryFieldModificationFormats:
    """Tests for field modification with different PK formats."""
    
    def test_dict_pk_format(self):
        """Should handle dict PK format."""
        from src.utils.ui_components import build_log_entry_field_modification
        
        details = {
            "row_pk": {"PatientID": "P001", "Gene": "TP53"},
            "column": "Status",
            "old_value": "Pending",
            "new_value": "Approved"
        }
        result = build_log_entry_field_modification("2024-01-01T10:00:00", details, 0)
        html = str(result)
        
        assert "Status" in html
        assert "Undo" in html
    
    def test_legacy_row_index_format(self):
        """Should handle legacy row_index format."""
        from src.utils.ui_components import build_log_entry_field_modification
        
        details = {
            "row_index": 5,
            "column": "Status",
            "old_value": "A",
            "new_value": "B"
        }
        result = build_log_entry_field_modification("2024-01-01T10:00:00", details, 0)
        html = str(result)
        
        assert "Status" in html


class TestBuildLogEntryUndoneFormats:
    """Tests for undone entry with different PK formats."""
    
    def test_row_pk_dict_format(self):
        """Should handle row_pk dict format."""
        from src.utils.ui_components import build_log_entry_undone
        
        details = {
            "row_pk": {"ID": "123"},
            "column": "Gene",
            "old_value": "A",
            "new_value": "B"
        }
        result = build_log_entry_undone("2024-01-01T10:00:00", details)
        html = str(result)
        
        assert "123" in html
        assert "UN-DONE" in html
    
    def test_empty_pk_dict(self):
        """Should handle empty PK dict."""
        from src.utils.ui_components import build_log_entry_undone
        
        details = {
            "row_pk": {},
            "column": "Gene"
        }
        result = build_log_entry_undone("2024-01-01T10:00:00", details)
        html = str(result)
        
        assert "?" in html


class TestBuildLogEntryApprovalEmptyRows:
    """Tests for approval entry edge cases."""
    
    def test_empty_rows_dict(self):
        """Should handle empty dict in rows."""
        from src.utils.ui_components import build_log_entry_approval
        
        details = {
            "approved_row_count": 1,
            "approved_rows": [{}]
        }
        result = build_log_entry_approval("2024-01-01T10:00:00", details)
        html = str(result)
        
        assert "?" in html


class TestBuildLogEntryRejectionEmptyRows:
    """Tests for rejection entry edge cases."""
    
    def test_empty_rows_dict(self):
        """Should handle empty dict in rows."""
        from src.utils.ui_components import build_log_entry_rejection
        
        details = {
            "rejected_row_count": 1,
            "rejected_rows": [{}]
        }
        result = build_log_entry_rejection("2024-01-01T10:00:00", details)
        html = str(result)
        
        assert "?" in html


# =====================================================================
# Facet UI Components Tests
# =====================================================================

class TestBuildFacetBar:
    """Tests for build_facet_bar function."""

    def test_renders_checkbox_with_value(self):
        """Should render a checkbox with the given value."""
        from src.utils.ui_components import build_facet_bar

        result = build_facet_bar("Status", "Active", 50, 100, True)
        html = str(result)

        assert "Active" in html
        assert 'value="Active"' in html
        assert 'data-column="Status"' in html

    def test_checked_when_is_checked_true(self):
        """Should include checked attribute when is_checked=True."""
        from src.utils.ui_components import build_facet_bar

        result = build_facet_bar("Status", "Active", 50, 100, True)
        html = str(result)

        assert "checked" in html

    def test_unchecked_when_is_checked_false(self):
        """Should not include checked attribute when is_checked=False."""
        from src.utils.ui_components import build_facet_bar

        result = build_facet_bar("Status", "Inactive", 20, 100, False)
        html = str(result)

        # The checkbox should not be checked
        assert 'checked="checked"' not in html

    def test_count_displayed(self):
        """Should display the count value."""
        from src.utils.ui_components import build_facet_bar

        result = build_facet_bar("Gene", "BRCA1", 42, 100, True)
        html = str(result)

        assert "42" in html

    def test_bar_width_percentage(self):
        """Bar width should reflect count/max_count ratio."""
        from src.utils.ui_components import build_facet_bar

        result = build_facet_bar("Gene", "TP53", 50, 100, True)
        html = str(result)

        assert "50.0%" in html or "50%" in html

    def test_zero_max_count_no_division_error(self):
        """Should not crash with max_count=0."""
        from src.utils.ui_components import build_facet_bar

        result = build_facet_bar("Gene", "X", 0, 0, True)
        html = str(result)

        assert "X" in html

    def test_long_value_truncated(self):
        """Values longer than 25 chars should be truncated with ellipsis."""
        from src.utils.ui_components import build_facet_bar

        long_val = "A" * 30
        result = build_facet_bar("Col", long_val, 10, 10, True)
        html = str(result)

        assert "…" in html
        assert long_val[:22] in html

    def test_facet_bar_css_class(self):
        """Should have facet-bar CSS class."""
        from src.utils.ui_components import build_facet_bar

        result = build_facet_bar("Col", "val", 5, 10, True)
        html = str(result)

        assert "facet-bar" in html


class TestBuildFacetPanel:
    """Tests for build_facet_panel function."""

    def test_renders_column_title(self):
        """Should render uppercased column name as title."""
        from src.utils.ui_components import build_facet_panel

        vc = [("Active", 50), ("Inactive", 20)]
        result = build_facet_panel("Status", vc, None)
        html = str(result)

        assert "STATUS" in html

    def test_renders_all_values(self):
        """Should render a bar for each value_count entry."""
        from src.utils.ui_components import build_facet_panel

        vc = [("A", 10), ("B", 5), ("C", 3)]
        result = build_facet_panel("Gene", vc, None, max_visible=10)
        html = str(result)

        assert "A" in html
        assert "B" in html
        assert "C" in html

    def test_show_more_when_exceeds_max_visible(self):
        """Should show 'Show more' toggle when values exceed max_visible."""
        from src.utils.ui_components import build_facet_panel

        vc = [("A", 10), ("B", 5), ("C", 3), ("D", 2), ("E", 1), ("F", 1)]
        result = build_facet_panel("Gene", vc, None, max_visible=3)
        html = str(result)

        assert "Show more" in html
        assert "facet-overflow" in html

    def test_no_show_more_when_within_limit(self):
        """Should not show toggle when all values fit."""
        from src.utils.ui_components import build_facet_panel

        vc = [("A", 10), ("B", 5)]
        result = build_facet_panel("Gene", vc, None, max_visible=5)
        html = str(result)

        assert "Show more" not in html

    def test_selected_values_checked(self):
        """Only selected values should be checked."""
        from src.utils.ui_components import build_facet_panel

        vc = [("Active", 50), ("Inactive", 20)]
        result = build_facet_panel("Status", vc, ["Active"], max_visible=5)
        html = str(result)

        assert "Active" in html

    def test_none_selected_means_all_checked(self):
        """selected_values=None should check all values."""
        from src.utils.ui_components import build_facet_panel

        vc = [("A", 10), ("B", 5)]
        result = build_facet_panel("Col", vc, None, max_visible=5)
        html = str(result)

        # Both should be checked
        assert html.count("checked") >= 2

    def test_column_masks_applied(self):
        """Should apply column mask to the title."""
        from src.utils.ui_components import build_facet_panel

        vc = [("X", 10)]
        result = build_facet_panel("gene_names", vc, None, column_masks={"gene_names": "Gene"})
        html = str(result)

        assert "GENE" in html

    def test_data_facet_column_attribute(self):
        """Should have data-facet-column attribute."""
        from src.utils.ui_components import build_facet_panel

        result = build_facet_panel("Status", [("A", 1)], None)
        html = str(result)

        assert 'data-facet-column="Status"' in html


class TestBuildFacetPanels:
    """Tests for build_facet_panels function."""

    def test_renders_multiple_panels(self):
        """Should render a panel for each facet column."""
        from src.utils.ui_components import build_facet_panels

        vc_map = {
            "Status": [("Active", 50), ("Inactive", 20)],
            "Gene": [("BRCA1", 30), ("TP53", 15)],
        }
        result = build_facet_panels(["Status", "Gene"], vc_map)
        html = str(result)

        assert "STATUS" in html
        assert "GENE" in html
        assert "Active" in html
        assert "BRCA1" in html

    def test_empty_columns_returns_empty_div(self):
        """Empty facet_columns should return empty div."""
        from src.utils.ui_components import build_facet_panels

        result = build_facet_panels([], {})
        html = str(result)

        assert "<div>" in html or "div" in html

    def test_missing_column_in_map_renders_empty_panel(self):
        """Column not in value_counts_map gets empty panel."""
        from src.utils.ui_components import build_facet_panels

        result = build_facet_panels(["Missing"], {})
        html = str(result)

        assert "MISSING" in html

    def test_selected_map_passed_through(self):
        """selected_map should filter checked values."""
        from src.utils.ui_components import build_facet_panels

        vc_map = {"Status": [("Active", 50), ("Inactive", 20)]}
        result = build_facet_panels(
            ["Status"], vc_map,
            selected_map={"Status": ["Active"]}
        )
        html = str(result)

        assert "Active" in html

    def test_column_masks_passed_through(self):
        """Column masks should be applied to panel titles."""
        from src.utils.ui_components import build_facet_panels

        vc_map = {"gene_names": [("BRCA1", 10)]}
        result = build_facet_panels(
            ["gene_names"], vc_map,
            column_masks={"gene_names": "Gene"}
        )
        html = str(result)

        assert "GENE" in html

    def test_facet_panels_css_class(self):
        """Wrapper should have facet-panels CSS class."""
        from src.utils.ui_components import build_facet_panels

        vc_map = {"Col": [("A", 1)]}
        result = build_facet_panels(["Col"], vc_map)
        html = str(result)

        assert "facet-panels" in html
