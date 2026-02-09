"""
Tests for event handler utilities.
"""
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from typing import List, Dict


class TestProcessApprovalAction:
    """Tests for process_approval_action function."""
    
    @pytest.fixture
    def mock_get_selected(self):
        """Mock get_selected_func."""
        def get_selected(input_obj, df_length):
            return [0, 1]  # Return first two rows selected
        return get_selected
    
    @pytest.fixture
    def mock_create_entry(self):
        """Mock create_entry_func."""
        def create_entry(indices, total, log_count):
            return {"type": "approval", "details": {"indices": indices}}
        return create_entry
    
    @pytest.fixture
    def mock_save_log(self):
        """Mock save_log_func."""
        return MagicMock()
    
    def test_success_with_selected_rows(self, mock_get_selected, mock_create_entry, mock_save_log, tmp_path):
        """Should approve selected rows successfully."""
        from src.utils.event_handlers import process_approval_action
        
        log = []
        log_path = tmp_path / "log.json"
        
        updated_log, success_msg, error = process_approval_action(
            MagicMock(), 10, log, log_path,
            mock_get_selected, mock_create_entry, mock_save_log
        )
        
        assert updated_log is not None
        assert len(updated_log) == 1
        assert "APPROVED" in success_msg
        assert error is None
    
    def test_error_with_no_selection(self, mock_create_entry, mock_save_log, tmp_path):
        """Should return error when no rows selected."""
        from src.utils.event_handlers import process_approval_action
        
        def no_selection(input_obj, df_length):
            return []
        
        log = []
        log_path = tmp_path / "log.json"
        
        updated_log, success_msg, error = process_approval_action(
            MagicMock(), 10, log, log_path,
            no_selection, mock_create_entry, mock_save_log
        )
        
        assert updated_log is None
        assert success_msg is None
        assert "select rows" in error.lower()
    
    def test_calls_save_log(self, mock_get_selected, mock_create_entry, mock_save_log, tmp_path):
        """Should call save_log_func."""
        from src.utils.event_handlers import process_approval_action
        
        log = []
        log_path = tmp_path / "log.json"
        
        process_approval_action(
            MagicMock(), 10, log, log_path,
            mock_get_selected, mock_create_entry, mock_save_log
        )
        
        mock_save_log.assert_called_once()


class TestProcessRejectionAction:
    """Tests for process_rejection_action function."""
    
    @pytest.fixture
    def mock_get_selected(self):
        def get_selected(input_obj, df_length):
            return [0]
        return get_selected
    
    @pytest.fixture
    def mock_create_entry(self):
        def create_entry(indices, total, log_count):
            return {"type": "rejection", "details": {"indices": indices}}
        return create_entry
    
    @pytest.fixture
    def mock_save_log(self):
        return MagicMock()
    
    def test_success_with_selected_rows(self, mock_get_selected, mock_create_entry, mock_save_log, tmp_path):
        """Should reject selected rows successfully."""
        from src.utils.event_handlers import process_rejection_action
        
        log = []
        log_path = tmp_path / "log.json"
        
        updated_log, success_msg, error = process_rejection_action(
            MagicMock(), 10, log, log_path,
            mock_get_selected, mock_create_entry, mock_save_log
        )
        
        assert updated_log is not None
        assert "REJECTED" in success_msg
        assert error is None
    
    def test_error_with_no_selection(self, mock_create_entry, mock_save_log, tmp_path):
        """Should return error when no rows selected."""
        from src.utils.event_handlers import process_rejection_action
        
        def no_selection(input_obj, df_length):
            return []
        
        log = []
        log_path = tmp_path / "log.json"
        
        updated_log, success_msg, error = process_rejection_action(
            MagicMock(), 10, log, log_path,
            no_selection, mock_create_entry, mock_save_log
        )
        
        assert updated_log is None
        assert "select rows" in error.lower()


class TestProcessUndoAction:
    """Tests for process_undo_action function."""
    
    def test_extract_index_from_dict(self):
        """Should extract index from dict format."""
        from src.utils.event_handlers import process_undo_action
        
        result = process_undo_action({"index": 5})
        
        assert result == 5
    
    def test_extract_index_from_int(self):
        """Should return int as-is."""
        from src.utils.event_handlers import process_undo_action
        
        result = process_undo_action(3)
        
        assert result == 3
    
    def test_none_returns_none(self):
        """None input should return None."""
        from src.utils.event_handlers import process_undo_action
        
        result = process_undo_action(None)
        
        assert result is None


class TestProcessCellEditAction:
    """Tests for process_cell_edit_action function."""
    
    def test_extract_all_fields(self):
        """Should extract all edit fields."""
        from src.utils.event_handlers import process_cell_edit_action
        
        edit_data = {
            "row": 5,
            "col": "Gene",
            "oldValue": "TP53",
            "newValue": "BRCA1"
        }
        
        row, col, old_val, new_val = process_cell_edit_action(edit_data)
        
        assert row == 5
        assert col == "Gene"
        assert old_val == "TP53"
        assert new_val == "BRCA1"
    
    def test_missing_row_returns_none(self):
        """Missing row should return None for row and col."""
        from src.utils.event_handlers import process_cell_edit_action
        
        edit_data = {"col": "Gene", "oldValue": "X", "newValue": "Y"}
        
        row, col, old_val, new_val = process_cell_edit_action(edit_data)
        
        assert row is None
        assert col is None
    
    def test_missing_col_returns_none(self):
        """Missing col should return None for row and col."""
        from src.utils.event_handlers import process_cell_edit_action
        
        edit_data = {"row": 5, "oldValue": "X", "newValue": "Y"}
        
        row, col, old_val, new_val = process_cell_edit_action(edit_data)
        
        assert row is None
        assert col is None
    
    def test_none_input_returns_none(self):
        """None input should return Nones and empty strings."""
        from src.utils.event_handlers import process_cell_edit_action
        
        row, col, old_val, new_val = process_cell_edit_action(None)
        
        assert row is None
        assert col is None
        assert old_val == ''
        assert new_val == ''
    
    def test_empty_dict_returns_none(self):
        """Empty dict should return Nones."""
        from src.utils.event_handlers import process_cell_edit_action
        
        row, col, old_val, new_val = process_cell_edit_action({})
        
        assert row is None
        assert col is None
    
    def test_defaults_for_missing_values(self):
        """Missing oldValue/newValue should default to empty string."""
        from src.utils.event_handlers import process_cell_edit_action
        
        edit_data = {"row": 0, "col": "Gene"}
        
        row, col, old_val, new_val = process_cell_edit_action(edit_data)
        
        assert row == 0
        assert col == "Gene"
        assert old_val == ''
        assert new_val == ''
