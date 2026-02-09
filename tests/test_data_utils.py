"""
Tests for data utilities - row status, modifications, summaries.
"""
import pytest
import pandas as pd
from typing import List, Dict


class TestGetLatestApprovalStatus:
    """Tests for get_latest_approval_status function."""
    
    def test_empty_log(self):
        """Empty log should return None, None."""
        from src.utils.data_utils import get_latest_approval_status
        
        status, timestamp = get_latest_approval_status([])
        
        assert status is None
        assert timestamp is None
    
    def test_no_approval_entries(self):
        """Log with no approval entries should return None, None."""
        from src.utils.data_utils import get_latest_approval_status
        
        log = [
            {"type": "field_modification", "timestamp": "2024-01-01T10:00:00"}
        ]
        status, timestamp = get_latest_approval_status(log)
        
        assert status is None
        assert timestamp is None
    
    def test_global_approval(self):
        """Global approval (no row list) should return approved."""
        from src.utils.data_utils import get_latest_approval_status
        
        log = [
            {"type": "approval", "timestamp": "2024-01-01T10:00:00", "details": {}}
        ]
        status, timestamp = get_latest_approval_status(log)
        
        assert status == "approved"
        assert timestamp == "2024-01-01T10:00:00"
    
    def test_global_rejection(self):
        """Global rejection should return rejected."""
        from src.utils.data_utils import get_latest_approval_status
        
        log = [
            {"type": "rejection", "timestamp": "2024-01-01T10:00:00", "details": {}}
        ]
        status, timestamp = get_latest_approval_status(log)
        
        assert status == "rejected"
    
    def test_row_based_approval_ignored(self):
        """Row-based approval (with approved_rows) should return None."""
        from src.utils.data_utils import get_latest_approval_status
        
        log = [
            {"type": "approval", "timestamp": "2024-01-01T10:00:00", 
             "details": {"approved_rows": [{"id": 1}]}}
        ]
        status, timestamp = get_latest_approval_status(log)
        
        assert status is None
        assert timestamp is None
    
    def test_latest_entry_wins(self):
        """Latest entry should take precedence."""
        from src.utils.data_utils import get_latest_approval_status
        
        log = [
            {"type": "approval", "timestamp": "2024-01-01T10:00:00", "details": {}},
            {"type": "rejection", "timestamp": "2024-01-02T10:00:00", "details": {}},
        ]
        status, timestamp = get_latest_approval_status(log)
        
        assert status == "rejected"


class TestGetRowStatus:
    """Tests for get_row_status function."""
    
    def test_unprocessed_by_default(self):
        """Row with no modifications should be unprocessed."""
        from src.utils.data_utils import get_row_status
        
        status = get_row_status(0, [])
        
        assert status == "unprocessed"
    
    def test_edited_with_field_modification(self):
        """Row with field modification should be edited."""
        from src.utils.data_utils import get_row_status
        
        log = [
            {"type": "field_modification", "details": {"row_index": 0, "column": "A"}}
        ]
        status = get_row_status(0, log)
        
        assert status == "edited"
    
    def test_edited_not_applied_to_other_rows(self):
        """Modification on row 0 should not affect row 1."""
        from src.utils.data_utils import get_row_status
        
        log = [
            {"type": "field_modification", "details": {"row_index": 0, "column": "A"}}
        ]
        status = get_row_status(1, log)
        
        assert status == "unprocessed"
    
    def test_undone_modification_not_counted(self):
        """Undone modification should not mark row as edited."""
        from src.utils.data_utils import get_row_status
        
        log = [
            {"type": "field_modification", "details": {"row_index": 0, "column": "A"}, "undone": True}
        ]
        status = get_row_status(0, log)
        
        assert status == "unprocessed"
    
    def test_approved_row_list_format(self):
        """Row in approved_rows list should be approved."""
        from src.utils.data_utils import get_row_status
        
        row_pk = {"PatientID": "P001"}
        log = [
            {"type": "approval", "details": {"approved_rows": [{"PatientID": "P001"}]}}
        ]
        status = get_row_status(0, log, row_pk)
        
        assert status == "approved"
    
    def test_rejected_row_list_format(self):
        """Row in rejected_rows list should be rejected."""
        from src.utils.data_utils import get_row_status
        
        row_pk = {"PatientID": "P001"}
        log = [
            {"type": "rejection", "details": {"rejected_rows": [{"PatientID": "P001"}]}}
        ]
        status = get_row_status(0, log, row_pk)
        
        assert status == "rejected"
    
    def test_approved_direct_pk_format(self):
        """Row matching row_pk directly should be approved (DB format)."""
        from src.utils.data_utils import get_row_status
        
        row_pk = {"PatientID": "P001"}
        log = [
            {"type": "approval", "details": {"row_pk": {"PatientID": "P001"}}}
        ]
        status = get_row_status(0, log, row_pk)
        
        assert status == "approved"
    
    def test_approval_takes_precedence_over_edit(self):
        """Approval after edit should show approved status."""
        from src.utils.data_utils import get_row_status
        
        row_pk = {"PatientID": "P001"}
        log = [
            {"type": "field_modification", "details": {"row_pk": {"PatientID": "P001"}, "row_index": 0}},
            {"type": "approval", "details": {"approved_rows": [{"PatientID": "P001"}]}}
        ]
        status = get_row_status(0, log, row_pk)
        
        assert status == "approved"


class TestGetRowModifications:
    """Tests for get_row_modifications function."""
    
    def test_empty_log(self):
        """Empty log should return empty list."""
        from src.utils.data_utils import get_row_modifications
        
        result = get_row_modifications(0, [])
        
        assert result == []
    
    def test_returns_only_matching_row(self):
        """Should only return modifications for the specified row."""
        from src.utils.data_utils import get_row_modifications
        
        log = [
            {"type": "field_modification", "details": {"row_index": 0, "column": "A"}},
            {"type": "field_modification", "details": {"row_index": 1, "column": "B"}},
            {"type": "field_modification", "details": {"row_index": 0, "column": "C"}},
        ]
        result = get_row_modifications(0, log)
        
        assert len(result) == 2
        assert all(m["details"]["row_index"] == 0 for m in result)
    
    def test_excludes_non_field_modifications(self):
        """Should exclude approval/rejection entries."""
        from src.utils.data_utils import get_row_modifications
        
        log = [
            {"type": "field_modification", "details": {"row_index": 0, "column": "A"}},
            {"type": "approval", "details": {"row_index": 0}},
        ]
        result = get_row_modifications(0, log)
        
        assert len(result) == 1
        assert result[0]["type"] == "field_modification"


class TestGetStatusCounts:
    """Tests for get_status_counts function."""
    
    @pytest.fixture
    def sample_df(self):
        return pd.DataFrame({
            "PatientID": ["P001", "P002", "P003"],
            "Gene": ["TP53", "BRCA1", "EGFR"]
        })
    
    def test_all_unprocessed(self, sample_df):
        """Empty log should count all as unprocessed."""
        from src.utils.data_utils import get_status_counts
        
        counts = get_status_counts(sample_df, [])
        
        assert counts["unprocessed"] == 3
        assert counts["edited"] == 0
        assert counts["approved"] == 0
        assert counts["rejected"] == 0
    
    def test_counts_with_modifications(self, sample_df):
        """Should count edited rows correctly."""
        from src.utils.data_utils import get_status_counts
        
        log = [
            {"type": "field_modification", "details": {"row_index": 0, "column": "Gene"}}
        ]
        counts = get_status_counts(sample_df, log)
        
        assert counts["edited"] == 1
        assert counts["unprocessed"] == 2
    
    def test_counts_with_pk_cols(self, sample_df):
        """Should use PK for matching when provided."""
        from src.utils.data_utils import get_status_counts
        
        log = [
            {"type": "approval", "details": {"approved_rows": [{"PatientID": "P001"}]}}
        ]
        counts = get_status_counts(sample_df, log, pk_cols=["PatientID"])
        
        assert counts["approved"] == 1
        assert counts["unprocessed"] == 2


class TestGetModificationSummary:
    """Tests for get_modification_summary function."""
    
    @pytest.fixture
    def sample_df(self):
        return pd.DataFrame({
            "PatientID": ["P001", "P002"],
            "Variant_key": ["V1", "V2"],
            "Gene": ["TP53", "BRCA1"]
        })
    
    def test_returns_summary_and_counts(self, sample_df):
        """Should return both summary data and counts."""
        from src.utils.data_utils import get_modification_summary
        
        summary_data, status_counts = get_modification_summary(sample_df, [])
        
        assert len(summary_data) == 2
        assert status_counts["unprocessed"] == 2
    
    def test_summary_contains_expected_fields(self, sample_df):
        """Summary data should contain expected fields."""
        from src.utils.data_utils import get_modification_summary
        
        summary_data, _ = get_modification_summary(sample_df, [])
        
        first_row = summary_data[0]
        assert "row_index" in first_row
        assert "status" in first_row
        assert "modifications_count" in first_row
        assert "patient_id" in first_row
        assert "variant_key" in first_row
    
    def test_modifications_count_tracked(self, sample_df):
        """Should track modification count per row."""
        from src.utils.data_utils import get_modification_summary
        
        log = [
            {"type": "field_modification", "details": {"row_index": 0, "column": "Gene"}},
            {"type": "field_modification", "details": {"row_index": 0, "column": "PatientID"}},
        ]
        summary_data, _ = get_modification_summary(sample_df, log)
        
        assert summary_data[0]["modifications_count"] == 2
        assert summary_data[1]["modifications_count"] == 0


class TestGetStatusCountsWithExceptions:
    """Tests for exception handling in status counting."""
    
    def test_get_status_counts_with_invalid_pk_access(self):
        """Should handle exception when accessing invalid PK columns."""
        from src.utils.data_utils import get_status_counts
        
        df = pd.DataFrame({"id": [1, 2, 3]})
        log = []
        
        # Pass pk_cols that don't exist
        counts = get_status_counts(df, log, pk_cols=["nonexistent_col"])
        
        # Should still count rows as unprocessed
        assert counts["unprocessed"] == 3
    
    def test_get_modification_summary_with_invalid_pk(self):
        """Should handle exception when PK columns don't exist."""
        from src.utils.data_utils import get_modification_summary
        
        df = pd.DataFrame({"id": [1, 2]})
        log = []
        
        summary, counts = get_modification_summary(df, log, pk_cols=["missing_col"])
        
        # Should still produce summary
        assert len(summary) == 2
        assert counts["unprocessed"] == 2


class TestGetRowStatusEdgeCases:
    """Additional edge case tests for get_row_status."""
    
    def test_get_row_status_with_empty_row_pk_in_entry(self):
        """Should handle entries with empty row_pk."""
        from src.utils.data_utils import get_row_status
        
        log = [{
            "type": "field_modification",
            "undone": False,
            "details": {"row_pk": {}}  # Empty row_pk
        }]
        
        status = get_row_status(0, log, row_pk={"id": 1})
        
        # No match, should be unprocessed
        assert status == "unprocessed"
    
    def test_get_row_status_with_no_row_pk(self):
        """Should handle cases with no row_pk."""
        from src.utils.data_utils import get_row_status
        
        log = [{
            "type": "field_modification",
            "undone": False,
            "details": {"row_index": 5}
        }]
        
        # No row_pk provided
        status = get_row_status(5, log, row_pk=None)
        
        # Should match by row_index
        assert status == "edited"
