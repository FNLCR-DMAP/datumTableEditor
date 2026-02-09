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
