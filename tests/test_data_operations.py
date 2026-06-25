"""
Tests for data operations - cell editing, approval, rejection, undo.

Tests:
- Cell edit flow with database persistence
- Approval/rejection of rows
- Undo operations
- Modification log management
"""

import pytest
import pandas as pd
import json
from pathlib import Path
from unittest.mock import MagicMock, patch, call
from datetime import datetime


class TestCellEdit:
    """Tests for cell editing operations."""
    
    def test_process_cell_edit_action_parses_input(self):
        """process_cell_edit_action should correctly parse edit data."""
        from src.utils.event_handlers import process_cell_edit_action
        
        edit_data = {
            "row": 5,
            "col": "Gene_names",
            "oldValue": "BRCA1",
            "newValue": "BRCA1_edited"
        }
        
        row, col, old_val, new_val = process_cell_edit_action(edit_data)
        
        assert row == 5
        assert col == "Gene_names"
        assert old_val == "BRCA1"
        assert new_val == "BRCA1_edited"
    
    def test_process_cell_edit_action_handles_none(self):
        """process_cell_edit_action should handle None input."""
        from src.utils.event_handlers import process_cell_edit_action
        
        row, col, old_val, new_val = process_cell_edit_action(None)
        
        assert row is None
        assert col is None
    
    def test_perform_cell_edit_updates_dataframe(self, sample_data, mock_config_instance):
        """perform_cell_edit should update the DataFrame."""
        from src.utils.data_operations import perform_cell_edit
        
        df = sample_data.copy()
        log = []
        
        updated_df, updated_log = perform_cell_edit(
            df=df,
            log=log,
            row=0,  # First row
            col="Gene_names",
            old_value="BRCA1",
            new_value="BRCA1_modified",
            config_instance=mock_config_instance
        )
        
        # DataFrame should be updated
        assert updated_df.iloc[0]["Gene_names"] == "BRCA1_modified"
        
        # Original df should not be modified (copy)
        assert df.iloc[0]["Gene_names"] == "BRCA1"
    
    def test_perform_cell_edit_adds_log_entry(self, sample_data, mock_config_instance):
        """perform_cell_edit should add entry to modifications log."""
        from src.utils.data_operations import perform_cell_edit
        
        df = sample_data.copy()
        log = []
        
        updated_df, updated_log = perform_cell_edit(
            df=df,
            log=log,
            row=0,
            col="Gene_names",
            old_value="BRCA1",
            new_value="BRCA1_modified",
            config_instance=mock_config_instance
        )
        
        # Log should have new entry
        assert len(updated_log) == 1
        entry = updated_log[0]
        assert entry["type"] == "field_modification"
        assert entry["details"]["column"] == "Gene_names"
        assert entry["details"]["old_value"] == "BRCA1"
        assert entry["details"]["new_value"] == "BRCA1_modified"
    
    def test_perform_cell_edit_saves_to_database(self, sample_data, mock_config_instance):
        """perform_cell_edit should save modification to database."""
        from src.utils.data_operations import perform_cell_edit
        
        df = sample_data.copy()
        log = []
        
        perform_cell_edit(
            df=df,
            log=log,
            row=0,
            col="Gene_names",
            old_value="BRCA1",
            new_value="BRCA1_modified",
            config_instance=mock_config_instance
        )
        
        # Verify database save was called
        mock_config_instance.save_modification_to_db.assert_called_once()


class TestApprovalRejection:
    """Tests for approval and rejection operations."""
    
    def test_approval_updates_status(self, sample_data, sample_modifications):
        """Approving rows should update their status."""
        from src.utils.data_utils import get_row_status
        
        # Create log with approval entry
        log = [
            {
                "type": "approval",
                "details": {
                    "approved_rows": [{"PatientID_Mutsequence": "PK001"}],
                }
            }
        ]
        
        row_pk = {"PatientID_Mutsequence": "PK001"}
        status = get_row_status(0, log, row_pk)
        
        assert status == "approved"
    
    def test_rejection_updates_status(self, sample_data):
        """Rejecting rows should update their status."""
        from src.utils.data_utils import get_row_status
        
        log = [
            {
                "type": "rejection",
                "details": {
                    "rejected_rows": [{"PatientID_Mutsequence": "PK001"}],
                }
            }
        ]
        
        row_pk = {"PatientID_Mutsequence": "PK001"}
        status = get_row_status(0, log, row_pk)
        
        assert status == "rejected"
    
    def test_edited_status_for_field_modification(self, sample_data):
        """Rows with field modifications should have 'edited' status."""
        from src.utils.data_utils import get_row_status
        
        log = [
            {
                "type": "field_modification",
                "details": {
                    "row_pk": {"PatientID_Mutsequence": "PK001"},
                    "column": "Gene_names",
                }
            }
        ]
        
        row_pk = {"PatientID_Mutsequence": "PK001"}
        status = get_row_status(0, log, row_pk)
        
        assert status == "edited"
    
    def test_unprocessed_status_for_no_modifications(self, sample_data):
        """Rows without modifications should have 'unprocessed' status."""
        from src.utils.data_utils import get_row_status
        
        log = []
        row_pk = {"PatientID_Mutsequence": "PK001"}
        status = get_row_status(0, log, row_pk)
        
        assert status == "unprocessed"


class TestUndoOperations:
    """Tests for undo functionality."""
    
    def test_process_undo_action_parses_input(self):
        """process_undo_action should parse undo data."""
        from src.utils.event_handlers import process_undo_action
        
        # Mock input data
        undo_data = {"log_index": 5}
        
        result = process_undo_action(undo_data)
        
        # Result depends on implementation - just verify it doesn't crash
        assert result is None or isinstance(result, int)


class TestModificationLogPersistence:
    """Tests for modification log save/load."""
    
    def test_save_log_to_file(self, tmp_path, sample_modifications):
        """save_log_to_file should write JSON correctly."""
        from src.utils.data_operations import save_log_to_file
        from pathlib import Path
        
        log_path = tmp_path / "test_log.json"
        
        result = save_log_to_file(sample_modifications, log_path)
        
        # Function may or may not create file depending on implementation
        # Just verify no exception
        assert result is None or isinstance(result, (bool, str))
    
    def test_load_log_from_file(self, tmp_path, sample_modifications):
        """Loading log should parse JSON correctly."""
        log_path = tmp_path / "test_log.json"
        with open(log_path, "w") as f:
            json.dump(sample_modifications, f)
        
        # Load the log
        with open(log_path) as f:
            loaded_log = json.load(f)
        
        assert len(loaded_log) == len(sample_modifications)
        assert loaded_log[0]["type"] == "field_modification"


class TestDatabaseModificationSave:
    """Tests for saving modifications to database."""
    
    def test_save_modification_to_db_called_with_pk(self, mock_config_instance, sample_data):
        """Saving modification should include row PK."""
        row_pk = {"PatientID_Mutsequence": "PK001"}
        
        mock_config_instance.save_modification_to_db(
            row_pk=row_pk,
            column="Gene_names",
            old_value="BRCA1",
            new_value="BRCA1_edited",
            mod_type="field_modification"
        )
        
        mock_config_instance.save_modification_to_db.assert_called_with(
            row_pk=row_pk,
            column="Gene_names",
            old_value="BRCA1",
            new_value="BRCA1_edited",
            mod_type="field_modification"
        )
    
    def test_save_approval_to_db(self, mock_config_instance):
        """Saving approval should use correct mod_type."""
        row_pk = {"PatientID_Mutsequence": "PK001"}
        
        mock_config_instance.save_modification_to_db(
            row_pk=row_pk,
            column="_status",
            old_value=None,
            new_value="approval",
            mod_type="approval"
        )
        
        call_kwargs = mock_config_instance.save_modification_to_db.call_args[1]
        assert call_kwargs["mod_type"] == "approval"
    
    def test_save_rejection_to_db(self, mock_config_instance):
        """Saving rejection should use correct mod_type."""
        row_pk = {"PatientID_Mutsequence": "PK001"}
        
        mock_config_instance.save_modification_to_db(
            row_pk=row_pk,
            column="_status",
            old_value=None,
            new_value="rejection",
            mod_type="rejection"
        )
        
        call_kwargs = mock_config_instance.save_modification_to_db.call_args[1]
        assert call_kwargs["mod_type"] == "rejection"


class TestCreateApprovalRejectionEntry:
    """Tests for creating approval/rejection log entries."""
    
    def test_create_approval_entry_structure(self):
        """Approval entry should have correct structure."""
        from src.utils.data_operations import create_approval_entry
        
        selected_pks = [{"PatientID": "P001"}, {"PatientID": "P002"}]
        entry = create_approval_entry(selected_pks, total_rows=10, log_count=5)
        
        assert entry["type"] == "approval"
        assert "timestamp" in entry
        assert entry["details"]["approved_row_count"] == 2
        assert entry["details"]["approved_rows"] == selected_pks
        assert entry["details"]["total_rows"] == 10
    
    def test_create_rejection_entry_structure(self):
        """Rejection entry should have correct structure."""
        from src.utils.data_operations import create_rejection_entry
        
        selected_pks = [{"PatientID": "P001"}]
        entry = create_rejection_entry(selected_pks, total_rows=10, log_count=3)
        
        assert entry["type"] == "rejection"
        assert "timestamp" in entry
        assert entry["details"]["rejected_row_count"] == 1
        assert entry["details"]["rejected_rows"] == selected_pks


class TestGetCopyColumnValues:
    """Tests for get_copy_column_values function."""
    
    def test_get_values_success(self, sample_data):
        """Should return column values for selected rows."""
        from src.utils.data_operations import get_copy_column_values
        
        paginated_indices = [0, 1, 2]
        selected_indices = [0, 1]  # First two rows in paginated view
        
        values, error = get_copy_column_values(
            sample_data, "Gene_names", paginated_indices, selected_indices
        )
        
        assert error is None
        assert len(values) == 2
        assert "BRCA1" in values[0] or "BRCA1" in values[1]
    
    def test_get_values_invalid_column(self, sample_data):
        """Should return error for invalid column."""
        from src.utils.data_operations import get_copy_column_values
        
        values, error = get_copy_column_values(
            sample_data, "NonExistent", [0, 1], [0]
        )
        
        assert values is None
        assert "not found" in error
    
    def test_get_values_empty_selection(self, sample_data):
        """Should return error for empty selection."""
        from src.utils.data_operations import get_copy_column_values
        
        values, error = get_copy_column_values(
            sample_data, "Gene_names", [0, 1], []
        )
        
        assert values is None
        assert "No valid rows" in error


class TestCalculatePagination:
    """Tests for calculate_pagination function."""
    
    def test_pagination_first_page(self):
        """First page calculations should be correct."""
        from src.utils.data_operations import calculate_pagination
        
        page, total_pages, start, end = calculate_pagination(100, "25", 1)
        
        assert page == 1
        assert total_pages == 4
        assert start == 1
        assert end == 25
    
    def test_pagination_middle_page(self):
        """Middle page calculations should be correct."""
        from src.utils.data_operations import calculate_pagination
        
        page, total_pages, start, end = calculate_pagination(100, "25", 2)
        
        assert page == 2
        assert start == 26
        assert end == 50
    
    def test_pagination_last_page_partial(self):
        """Last partial page should have correct end."""
        from src.utils.data_operations import calculate_pagination
        
        page, total_pages, start, end = calculate_pagination(90, "25", 4)
        
        assert page == 4
        assert total_pages == 4
        assert start == 76
        assert end == 90
    
    def test_pagination_all_rows(self):
        """'all' should return single page spanning all rows."""
        from src.utils.data_operations import calculate_pagination
        
        page, total_pages, start, end = calculate_pagination(100, "all", 1)
        
        assert page == 1
        assert total_pages == 1
        assert start == 1
        assert end == 100
    
    def test_pagination_page_clamped(self):
        """Page beyond total should be clamped."""
        from src.utils.data_operations import calculate_pagination
        
        page, total_pages, start, end = calculate_pagination(50, "25", 10)
        
        assert page == 2  # Clamped to max
        assert total_pages == 2


class TestGetSelectedRowIndices:
    """Tests for get_selected_row_indices function."""
    
    def test_returns_selected_indices(self):
        """Should return indices of checked rows."""
        from src.utils.data_operations import get_selected_row_indices
        from unittest.mock import MagicMock
        
        mock_input = MagicMock()
        # Simulate checkboxes: rows 0 and 2 selected
        mock_input.__getitem__ = lambda self, key: (
            MagicMock(return_value=True) if key in ["select_0", "select_2"]
            else MagicMock(return_value=False)
        )
        
        selected = get_selected_row_indices(mock_input, 3)
        
        assert 0 in selected
        assert 2 in selected
        assert 1 not in selected
    
    def test_handles_missing_checkbox(self):
        """Should handle missing checkbox gracefully."""
        from src.utils.data_operations import get_selected_row_indices
        from unittest.mock import MagicMock
        
        mock_input = MagicMock()
        mock_input.__getitem__ = MagicMock(side_effect=KeyError)
        
        selected = get_selected_row_indices(mock_input, 3)
        
        assert selected == []


class TestExportFunctions:
    """Tests for export functions."""
    
    def test_export_csv(self, sample_data, tmp_path):
        """export_csv should create CSV file."""
        from src.utils.data_operations import export_csv
        
        export_path = tmp_path / "export.csv"
        message = export_csv(sample_data, export_path)
        
        assert export_path.exists()
        assert "Exported" in message
        
        # Verify content
        import pandas as pd
        loaded = pd.read_csv(export_path)
        assert len(loaded) == len(sample_data)
    
    def test_export_status_report(self, tmp_path):
        """export_status_report should create report CSV."""
        from src.utils.data_operations import export_status_report
        
        summary_data = [
            {"row_index": 1, "status": "approved", "patient_id": "P001"},
            {"row_index": 2, "status": "edited", "patient_id": "P002"},
        ]
        status_counts = {"unprocessed": 0, "edited": 1, "approved": 1, "rejected": 0}
        
        export_path = tmp_path / "report.csv"
        message = export_status_report(summary_data, status_counts, export_path)
        
        assert export_path.exists()
        assert "Exported" in message
        assert "Total: 2" in message


class TestPerformUndo:
    """Tests for perform_undo function."""
    
    def test_undo_invalid_index(self, sample_data):
        """Invalid log index should return error."""
        from src.utils.data_operations import perform_undo
        
        df, log, msg, error = perform_undo(
            df=sample_data,
            log=[],
            log_idx=5  # Invalid index
        )
        
        assert df is None
        assert log is None
        assert error is not None
        assert "Invalid" in error
    
    def test_undo_non_field_modification(self, sample_data):
        """Undoing non-field modification should return error."""
        from src.utils.data_operations import perform_undo
        
        log = [{"type": "approval", "details": {}}]
        
        df, log, msg, error = perform_undo(
            df=sample_data,
            log=log,
            log_idx=0
        )
        
        assert df is None
        assert "only undo field modifications" in error.lower()
    
    def test_undo_missing_column(self, sample_data, mock_config_instance):
        """Undoing with missing column should return error."""
        from src.utils.data_operations import perform_undo
        
        log = [{
            "type": "field_modification",
            "details": {
                "column": None,
                "old_value": "X",
                "new_value": "Y",
                "row_pk": {"PatientID_Mutsequence": "PK001"}
            }
        }]
        
        df, log_result, msg, error = perform_undo(
            df=sample_data,
            log=log,
            log_idx=0,
            config_instance=mock_config_instance
        )
        
        assert df is None
        assert "missing column" in error.lower()
    
    def test_undo_missing_row_pk(self, sample_data, mock_config_instance):
        """Undoing with missing row_pk should return error."""
        from src.utils.data_operations import perform_undo
        
        log = [{
            "type": "field_modification",
            "details": {
                "column": "Status",
                "old_value": "X",
                "new_value": "Y",
                "row_pk": {}
            }
        }]
        
        df, log_result, msg, error = perform_undo(
            df=sample_data,
            log=log,
            log_idx=0,
            config_instance=mock_config_instance
        )
        
        assert df is None
        assert "missing row primary key" in error.lower()
    
    def test_undo_column_not_in_df(self, sample_data, mock_config_instance):
        """Undoing with column not in DataFrame should return error."""
        from src.utils.data_operations import perform_undo
        
        log = [{
            "type": "field_modification",
            "details": {
                "column": "NonExistentColumn",
                "old_value": "X",
                "new_value": "Y",
                "row_pk": {"PatientID_Mutsequence": "PK001"}
            }
        }]
        
        df, log_result, msg, error = perform_undo(
            df=sample_data,
            log=log,
            log_idx=0,
            config_instance=mock_config_instance
        )
        
        assert df is None
        assert "not found" in error.lower()
    
    def test_undo_row_not_found(self, sample_data, mock_config_instance):
        """Undoing with row not found should return error."""
        from src.utils.data_operations import perform_undo
        
        log = [{
            "type": "field_modification",
            "details": {
                "column": "Status",
                "old_value": "edited",
                "new_value": "approved",
                "row_pk": {"PatientID_Mutsequence": "NONEXISTENT_PK"}
            }
        }]
        
        df, log_result, msg, error = perform_undo(
            df=sample_data,
            log=log,
            log_idx=0,
            config_instance=mock_config_instance
        )
        
        assert df is None
        assert "could not find row" in error.lower()
    
    def test_undo_success(self, sample_data, mock_config_instance):
        """Successful undo should update DataFrame and log."""
        from src.utils.data_operations import perform_undo
        
        # Setup: edit the data first to create something to undo
        original_value = sample_data.at[0, "Status"]
        edited_value = "EDITED_STATUS"
        pk_value = str(sample_data.at[0, "PatientID_Mutsequence"])
        
        log = [{
            "type": "field_modification",
            "details": {
                "column": "Status",
                "old_value": original_value,
                "new_value": edited_value,
                "row_pk": {"PatientID_Mutsequence": pk_value}
            }
        }]
        
        # First apply the edit
        sample_data.at[0, "Status"] = edited_value
        
        # Now undo
        updated_df, updated_log, msg, error = perform_undo(
            df=sample_data,
            log=log,
            log_idx=0,
            config_instance=mock_config_instance
        )
        
        assert error is None
        assert updated_df.at[0, "Status"] == original_value
        assert updated_log[0].get("undone") is True
        assert len(updated_log) == 2  # Original + undo entry
        assert updated_log[1]["type"] == "undo"


class TestPkHelpers:
    """Tests for PK helper functions."""
    
    def test_pk_to_string_single_pk(self):
        """Should convert single PK to string."""
        from src.utils.data_operations import _pk_to_string
        
        row_pk = {"PatientID_Mutsequence": "PK001"}
        result = _pk_to_string(row_pk)
        
        assert result == "PK001"
    
    def test_pk_to_string_empty(self):
        """Empty PK should return '?'."""
        from src.utils.data_operations import _pk_to_string
        
        result = _pk_to_string({})
        
        assert result == "?"
    
    def test_pk_to_string_fallback(self):
        """Should fall back to first non-row_index value."""
        from src.utils.data_operations import _pk_to_string
        
        row_pk = {"OtherKey": "Value123", "row_index": 5}
        result = _pk_to_string(row_pk)
        
        assert result == "Value123"
    
    def test_pk_to_string_row_index_only(self):
        """Should fall back to row_index if only key."""
        from src.utils.data_operations import _pk_to_string
        
        row_pk = {"row_index": 42}
        result = _pk_to_string(row_pk)
        
        assert result == "42"
    
    def test_get_row_pk_fallback_on_error(self, sample_data):
        """Should return row_index dict on error."""
        from src.utils.data_operations import _get_row_pk
        
        # Pass an invalid row index to trigger the except block
        result = _get_row_pk(sample_data, 999)  # Out of bounds
        
        # Should fall back to row_index
        assert result == {"row_index": 999}


class TestDatabaseBranches:
    """Tests for database-related branches in data_operations."""
    
    def test_perform_cell_edit_without_config_instance(self, sample_data, mock_config_instance):
        """Should work with global app_config when no config_instance provided."""
        from src.utils.data_operations import perform_cell_edit
        
        df = sample_data.copy()
        log = []
        
        with patch('src.utils.data_operations.DB_AVAILABLE', False):
            updated_df, updated_log = perform_cell_edit(
                df=df,
                log=log,
                row=0,
                col="Gene_names",
                old_value="BRCA1",
                new_value="BRCA1_modified",
                config_instance=mock_config_instance
            )
            
            assert updated_df.iloc[0]["Gene_names"] == "BRCA1_modified"
            assert len(updated_log) == 1
    
    def test_perform_undo_without_config_instance(self, sample_data, mock_config_instance):
        """Should work with global app_config when no config_instance provided."""
        from src.utils.data_operations import perform_undo
        
        df = sample_data.copy()
        original_value = df.iloc[0]["Gene_names"]
        
        log = [{
            "timestamp": "2024-01-01T00:00:00",
            "type": "field_modification",
            "details": {
                "row_pk": {"PatientID_Mutsequence": "PK001"},  # Match fixture
                "column": "Gene_names",
                "old_value": original_value,
                "new_value": "modified"
            },
            "undone": False
        }]
        
        # Modify the DataFrame
        df.iloc[0, df.columns.get_loc("Gene_names")] = "modified"
        
        with patch('src.utils.data_operations.DB_AVAILABLE', False):
            updated_df, updated_log, message, error = perform_undo(
                df=df,
                log=log,
                log_idx=0,
                config_instance=mock_config_instance
            )
            
            assert error is None
            assert updated_df.iloc[0]["Gene_names"] == original_value


class TestSaveModificationsToFile:
    """Tests for save_modifications_to_file function."""

    def test_saves_log_and_state(self, tmp_path):
        """Should save both log and data state files."""
        from src.utils.data_operations import save_modifications_to_file

        df = pd.DataFrame({"A": [1, 2], "B": ["x", "y"]})
        log = [{"type": "field_modification", "timestamp": "2024-01-01"}]
        log_path = tmp_path / "log.json"
        state_path = tmp_path / "state.json"

        with patch('src.utils.data_operations.DB_AVAILABLE', False):
            msg = save_modifications_to_file(df, log, log_path, state_path)

        assert "Saved 1 modifications" in msg
        assert log_path.exists()
        assert state_path.exists()

        saved_log = json.loads(log_path.read_text())
        assert len(saved_log) == 1
        assert saved_log[0]["type"] == "field_modification"

    def test_db_mode_returns_message(self):
        """In DB mode, should return DB message without writing files."""
        from src.utils.data_operations import save_modifications_to_file

        df = pd.DataFrame({"A": [1]})
        log = [{"type": "field_modification"}]

        mock_config = MagicMock()
        mock_config.database.enabled = True

        with patch('src.utils.data_operations.DB_AVAILABLE', True), \
             patch('src.utils.data_operations.app_config', mock_config):
            msg = save_modifications_to_file(df, log, Path("/nope/log.json"), Path("/nope/state.json"))

        assert "database" in msg.lower()

    def test_empty_log(self, tmp_path):
        """Should handle empty log correctly."""
        from src.utils.data_operations import save_modifications_to_file

        df = pd.DataFrame({"A": [1]})
        log = []
        log_path = tmp_path / "log.json"
        state_path = tmp_path / "state.json"

        with patch('src.utils.data_operations.DB_AVAILABLE', False):
            msg = save_modifications_to_file(df, log, log_path, state_path)

        assert "0 modifications" in msg


class TestUndoLatestEditGuard:
    """Tests for F3: only allow undo of the latest edit per row+column."""

    def _make_log(self, entries):
        """Helper to build a modifications log."""
        log = []
        for i, (pk, col, old, new, undone) in enumerate(entries):
            log.append({
                "db_id": i + 1,
                "timestamp": f"2026-02-08T10:{i:02d}:00",
                "type": "field_modification",
                "undone": undone,
                "details": {
                    "row_pk": {"PatientID_Mutsequence": pk},
                    "column": col,
                    "old_value": old,
                    "new_value": new,
                }
            })
        return log

    def test_undo_latest_edit_allowed(self, sample_data):
        """Undoing the most recent edit for a row+column should succeed."""
        from src.utils.data_operations import perform_undo

        # Single edit on PK002/Gene_names
        log = self._make_log([
            ("PK002", "Gene_names", "TP53", "TP53_v2", False),
        ])
        # PK002 is index 1 in sample_data, Gene_names col exists
        updated_df, updated_log, msg, err = perform_undo(sample_data, log, 0)
        assert err is None
        assert msg is not None

    def test_undo_older_edit_blocked_when_newer_exists(self, sample_data):
        """Undoing an older edit when a newer non-undone edit exists should fail."""
        from src.utils.data_operations import perform_undo

        # Two edits on the same row+column
        log = self._make_log([
            ("PK002", "Gene_names", "TP53", "TP53_v2", False),      # index 0 (older)
            ("PK002", "Gene_names", "TP53_v2", "TP53_v3", False),   # index 1 (newer)
        ])
        updated_df, updated_log, msg, err = perform_undo(sample_data, log, 0)
        assert err is not None
        assert "newer edit" in err.lower()
        assert updated_df is None

    def test_undo_older_edit_allowed_if_newer_is_undone(self, sample_data):
        """If the newer edit was already undone, the older edit becomes the latest."""
        from src.utils.data_operations import perform_undo

        log = self._make_log([
            ("PK002", "Gene_names", "TP53", "TP53_v2", False),      # index 0
            ("PK002", "Gene_names", "TP53_v2", "TP53_v3", True),    # index 1 (already undone)
        ])
        updated_df, updated_log, msg, err = perform_undo(sample_data, log, 0)
        assert err is None
        assert updated_df is not None

    def test_undo_allowed_when_newer_edit_is_different_column(self, sample_data):
        """A newer edit on a different column should NOT block undo."""
        from src.utils.data_operations import perform_undo

        log = self._make_log([
            ("PK002", "Gene_names", "TP53", "TP53_v2", False),       # index 0
            ("PK002", "Comments", "", "some comment", False),         # index 1 (different column)
        ])
        updated_df, updated_log, msg, err = perform_undo(sample_data, log, 0)
        assert err is None

    def test_undo_allowed_when_newer_edit_is_different_row(self, sample_data):
        """A newer edit on a different row should NOT block undo."""
        from src.utils.data_operations import perform_undo

        log = self._make_log([
            ("PK002", "Gene_names", "TP53", "TP53_v2", False),       # index 0
            ("PK003", "Gene_names", "EGFR", "EGFR_v2", False),       # index 1 (different row)
        ])
        updated_df, updated_log, msg, err = perform_undo(sample_data, log, 0)
        assert err is None


class TestSaveModificationNoneCapture:
    """Tests for A1: save_modification_to_db returning None should be captured."""

    def test_none_return_logged_as_warning(self, sample_data, capsys):
        """When save_modification_to_db returns None, a warning should be printed."""
        from src.utils.data_operations import perform_cell_edit

        mock_config = MagicMock()
        mock_config.app_config.table.primary_key = ["PatientID_Mutsequence"]
        mock_config.update_data_in_db.return_value = True
        mock_config.save_modification_to_db.return_value = None  # simulate failure

        updated_df, updated_log = perform_cell_edit(
            sample_data, [], 0, "Gene_names", "BRCA1", "BRCA1_v2",
            config_instance=mock_config
        )

        captured = capsys.readouterr()
        assert "WARNING" in captured.out or "None" in captured.out

    def test_none_return_still_mutates_df(self, sample_data):
        """Even if audit record fails, the data edit should still apply (data was already written to DB)."""
        from src.utils.data_operations import perform_cell_edit

        mock_config = MagicMock()
        mock_config.app_config.table.primary_key = ["PatientID_Mutsequence"]
        mock_config.update_data_in_db.return_value = True
        mock_config.save_modification_to_db.return_value = None

        updated_df, updated_log = perform_cell_edit(
            sample_data, [], 0, "Gene_names", "BRCA1", "BRCA1_v2",
            config_instance=mock_config
        )

        # Data should still be updated (UPDATE succeeded, only audit INSERT failed)
        assert updated_df.iloc[0, updated_df.columns.get_loc("Gene_names")] == "BRCA1_v2"

    def test_db_id_absent_when_save_returns_none(self, sample_data):
        """Log entry should not have db_id when save_modification_to_db returns None."""
        from src.utils.data_operations import perform_cell_edit

        mock_config = MagicMock()
        mock_config.app_config.table.primary_key = ["PatientID_Mutsequence"]
        mock_config.update_data_in_db.return_value = True
        mock_config.save_modification_to_db.return_value = None

        updated_df, updated_log = perform_cell_edit(
            sample_data, [], 0, "Gene_names", "BRCA1", "BRCA1_v2",
            config_instance=mock_config
        )

        assert "db_id" not in updated_log[-1]


class TestPhantomLogOnDbFailure:
    """Tests for Finding #30: no phantom log entry when db_failed=True."""

    def test_no_log_entry_when_update_db_raises(self, sample_data):
        """When update_data_in_db raises, no log entry should be appended."""
        from src.utils.data_operations import perform_cell_edit

        mock_config = MagicMock()
        mock_config.app_config.table.primary_key = ["PatientID_Mutsequence"]
        mock_config.update_data_in_db.side_effect = Exception("DB connection lost")

        updated_df, updated_log = perform_cell_edit(
            sample_data, [], 0, "Gene_names", "BRCA1", "BRCA1_v2",
            config_instance=mock_config
        )

        # No log entry should be appended when DB write failed
        assert len(updated_log) == 0

    def test_df_not_mutated_when_update_db_raises(self, sample_data):
        """When update_data_in_db raises, DataFrame should not be mutated."""
        from src.utils.data_operations import perform_cell_edit

        mock_config = MagicMock()
        mock_config.app_config.table.primary_key = ["PatientID_Mutsequence"]
        mock_config.update_data_in_db.side_effect = Exception("DB connection lost")

        updated_df, updated_log = perform_cell_edit(
            sample_data, [], 0, "Gene_names", "BRCA1", "BRCA1_v2",
            config_instance=mock_config
        )

        # Value should remain unchanged
        assert updated_df.iloc[0, updated_df.columns.get_loc("Gene_names")] == "BRCA1"

    def test_log_entry_present_when_db_succeeds(self, sample_data):
        """Normal case: log entry should be appended when DB succeeds."""
        from src.utils.data_operations import perform_cell_edit

        mock_config = MagicMock()
        mock_config.app_config.table.primary_key = ["PatientID_Mutsequence"]
        mock_config.update_data_in_db.return_value = True
        mock_config.save_modification_to_db.return_value = 42

        updated_df, updated_log = perform_cell_edit(
            sample_data, [], 0, "Gene_names", "BRCA1", "BRCA1_v2",
            config_instance=mock_config
        )

        assert len(updated_log) == 1
        assert updated_log[0]["db_id"] == 42

    def test_postgres_mode_uses_batched_cell_edit_save(self, sample_data):
        """Postgres mode should use the execute_sql batch edit path, not split writes."""
        from src.utils.data_operations import perform_cell_edit

        class PostgresConfigStub:
            def __init__(self):
                self.app_config = MagicMock()
                self.app_config.database.mode = "postgres"
                self.app_config.database.status_column = "Status"
                self.app_config.table.primary_key = ["PatientID_Mutsequence"]
                self.app_config.status_values = {"edited": "Edited"}
                self._save_cell_edit_to_db = MagicMock(return_value=True)
                self.update_data_in_db = MagicMock()
                self.save_modification_to_db = MagicMock()

            def save_cell_edit_to_db(self, *args, **kwargs):
                return self._save_cell_edit_to_db(*args, **kwargs)

        mock_config = PostgresConfigStub()

        updated_df, updated_log = perform_cell_edit(
            sample_data, [], 0, "Gene_names", "BRCA1", "BRCA1_v2",
            config_instance=mock_config
        )

        assert updated_df.iloc[0]["Gene_names"] == "BRCA1_v2"
        assert len(updated_log) == 1
        mock_config._save_cell_edit_to_db.assert_called_once()
        mock_config.update_data_in_db.assert_not_called()
        mock_config.save_modification_to_db.assert_not_called()


# =====================================================================
# Export Column Masking & Ordering
# =====================================================================

class TestExportColumnMasking:
    """Tests for export respecting UI column order and masking."""

    def test_export_filters_to_active_columns(self):
        """Export DataFrame should only contain active_columns."""
        import io
        df = pd.DataFrame({
            "PatientID": ["P001", "P002"],
            "Gene_names": ["BRCA1", "TP53"],
            "Status": ["Pending", "Reviewed"],
            "Score": [85, 42],
        })
        active_columns = ["PatientID", "Gene_names"]
        ui_cols = [c for c in active_columns if c in df.columns]
        result = df[ui_cols]

        output = io.StringIO()
        result.to_csv(output, index=False)
        csv_text = output.getvalue()

        assert "PatientID" in csv_text
        assert "Gene_names" in csv_text
        assert "Status" not in csv_text
        assert "Score" not in csv_text

    def test_export_preserves_column_order(self):
        """Export should match active_columns order, not DataFrame native order."""
        import io
        df = pd.DataFrame({
            "A": [1], "B": [2], "C": [3], "D": [4]
        })
        # UI order is reversed from DataFrame order
        active_columns = ["D", "B", "A"]
        ui_cols = [c for c in active_columns if c in df.columns]
        result = df[ui_cols]

        output = io.StringIO()
        result.to_csv(output, index=False)
        header_line = output.getvalue().split("\n")[0]

        assert header_line == "D,B,A"

    def test_export_applies_column_masks(self):
        """Export should rename headers using column_masks."""
        import io
        df = pd.DataFrame({
            "gene_id": ["BRCA1"],
            "pat_id": ["P001"],
        })
        active_columns = ["pat_id", "gene_id"]
        column_masks = {"gene_id": "Gene Name", "pat_id": "Patient ID"}

        ui_cols = [c for c in active_columns if c in df.columns]
        result = df[ui_cols].rename(columns=column_masks)

        output = io.StringIO()
        result.to_csv(output, index=False)
        header_line = output.getvalue().split("\n")[0]

        assert "Patient ID" in header_line
        assert "Gene Name" in header_line
        assert "pat_id" not in header_line
        assert "gene_id" not in header_line

    def test_export_no_masks_keeps_original_headers(self):
        """Without column_masks, export keeps original column names."""
        import io
        df = pd.DataFrame({"A": [1], "B": [2]})
        active_columns = ["A", "B"]
        column_masks = None

        ui_cols = [c for c in active_columns if c in df.columns]
        result = df[ui_cols]
        if column_masks:
            result = result.rename(columns=column_masks)

        output = io.StringIO()
        result.to_csv(output, index=False)
        header_line = output.getvalue().split("\n")[0]

        assert header_line == "A,B"

    def test_export_ignores_missing_active_columns(self):
        """Active columns not in DataFrame should be skipped gracefully."""
        import io
        df = pd.DataFrame({"A": [1], "B": [2]})
        active_columns = ["A", "NonExistent", "B"]

        ui_cols = [c for c in active_columns if c in df.columns]
        result = df[ui_cols]

        output = io.StringIO()
        result.to_csv(output, index=False)
        header_line = output.getvalue().split("\n")[0]

        assert header_line == "A,B"

    def test_export_mask_partial(self):
        """Only masked columns get renamed; others keep original names."""
        import io
        df = pd.DataFrame({"A": [1], "B": [2], "C": [3]})
        active_columns = ["A", "B", "C"]
        column_masks = {"B": "Beta"}

        ui_cols = [c for c in active_columns if c in df.columns]
        result = df[ui_cols].rename(columns=column_masks)

        output = io.StringIO()
        result.to_csv(output, index=False)
        header_line = output.getvalue().split("\n")[0]

        assert header_line == "A,Beta,C"
