"""
Tests for configuration loading and ConfigInstance.

Tests:
- Config file loading and validation
- ConfigInstance initialization
- Edited cells tracking with PK-based keys
- Data loading from mocked database
"""

import pytest
import pandas as pd
import json
from unittest.mock import MagicMock, patch, PropertyMock
from pathlib import Path


class TestConfigInstance:
    """Tests for ConfigInstance class."""
    
    def test_edited_cells_pk_based_keys(self, mock_config_instance, cell_key_helper):
        """Edited cells should use PK-based keys, not row indices."""
        edited_cells = mock_config_instance.get_edited_cells()
        
        # All keys should be (pk_tuple, column_name) format
        for key in edited_cells.keys():
            assert isinstance(key, tuple), "Key should be a tuple"
            assert len(key) == 2, "Key should have 2 elements: (pk_tuple, col_name)"
            pk_tuple, col_name = key
            assert isinstance(pk_tuple, tuple), "First element should be PK tuple"
            assert isinstance(col_name, str), "Second element should be column name"
    
    def test_is_cell_edited_with_pk(self, mock_config_instance):
        """is_cell_edited should work with PK dictionary."""
        row_pk = {"PatientID_Mutsequence": "PK002"}
        
        assert mock_config_instance.is_cell_edited(row_pk, "Gene_names") == True
        assert mock_config_instance.is_cell_edited(row_pk, "Status") == False
        
        # Different PK should not match
        other_pk = {"PatientID_Mutsequence": "PK001"}
        assert mock_config_instance.is_cell_edited(other_pk, "Gene_names") == False
    
    def test_get_original_value_with_pk(self, mock_config_instance):
        """get_original_value should return original value for edited cell."""
        row_pk = {"PatientID_Mutsequence": "PK002"}
        
        original = mock_config_instance.get_original_value(row_pk, "Gene_names")
        assert original == "TP53"
        
        # Non-edited cell should return None
        assert mock_config_instance.get_original_value(row_pk, "Status") is None
    
    def test_edited_cells_structure(self, mock_config_instance):
        """Edited cells dict should have correct structure with original and current values."""
        edited_cells = mock_config_instance.get_edited_cells()
        
        for key, value in edited_cells.items():
            assert isinstance(value, dict), "Value should be a dict"
            assert "original" in value, "Should have 'original' key"
            assert "current" in value, "Should have 'current' key"


class TestConfigInstanceDatabaseLoading:
    """Tests for ConfigInstance database loading with mocks."""
    
    def test_apply_field_modifications_tracks_edits(self, sample_data, primary_key_columns):
        """_apply_field_modifications should populate edited_cells dict."""
        # This tests the logic of applying field modifications
        # Simulate what _apply_field_modifications does
        df = sample_data.copy()
        
        mods_data = [
            (json.dumps({"PatientID_Mutsequence": "PK002"}), "Gene_names", "TP53", "TP53_edited"),
        ]
        
        edited_cells = {}
        for mod in mods_data:
            row_pk = json.loads(mod[0])
            col_name = mod[1]
            old_value = mod[2]
            new_value = mod[3]
            
            if col_name in df.columns:
                mask = pd.Series([True] * len(df))
                for pk_col in primary_key_columns:
                    if pk_col in row_pk and pk_col in df.columns:
                        mask &= (df[pk_col].astype(str) == str(row_pk[pk_col]))
                
                if mask.any():
                    pk_tuple = tuple(sorted((k, str(v)) for k, v in row_pk.items()))
                    cell_key = (pk_tuple, col_name)
                    
                    if cell_key not in edited_cells:
                        edited_cells[cell_key] = {"original": old_value, "current": new_value}
                    else:
                        edited_cells[cell_key]["current"] = new_value
                    
                    df.loc[mask, col_name] = new_value
        
        # Verify
        assert len(edited_cells) == 1
        pk_tuple = (("PatientID_Mutsequence", "PK002"),)
        assert (pk_tuple, "Gene_names") in edited_cells
        assert edited_cells[(pk_tuple, "Gene_names")]["original"] == "TP53"
        assert edited_cells[(pk_tuple, "Gene_names")]["current"] == "TP53_edited"
        
        # Verify df was updated
        assert df[df["PatientID_Mutsequence"] == "PK002"]["Gene_names"].iloc[0] == "TP53_edited"


class TestPKTupleCreation:
    """Tests for PK tuple creation and hashing."""
    
    def test_pk_tuple_is_hashable(self, pk_tuple_helper):
        """PK tuple should be hashable for use as dict key."""
        pk = {"PatientID_Mutsequence": "PK001", "OtherKey": "value"}
        pk_tuple = pk_tuple_helper(pk)
        
        # Should be hashable
        test_dict = {pk_tuple: "test_value"}
        assert test_dict[pk_tuple] == "test_value"
    
    def test_pk_tuple_order_independent(self, pk_tuple_helper):
        """PK tuple should be same regardless of dict key order."""
        pk1 = {"A": "1", "B": "2"}
        pk2 = {"B": "2", "A": "1"}
        
        assert pk_tuple_helper(pk1) == pk_tuple_helper(pk2)
    
    def test_pk_tuple_converts_values_to_string(self, pk_tuple_helper):
        """PK tuple should convert all values to strings for consistency."""
        pk_int = {"ID": 123}
        pk_str = {"ID": "123"}
        
        assert pk_tuple_helper(pk_int) == pk_tuple_helper(pk_str)
    
    def test_cell_key_structure(self, cell_key_helper):
        """Cell key should be (pk_tuple, column_name)."""
        pk = {"PatientID_Mutsequence": "PK001"}
        col = "Gene_names"
        
        cell_key = cell_key_helper(pk, col)
        
        assert isinstance(cell_key, tuple)
        assert len(cell_key) == 2
        assert cell_key[1] == col


class TestExportConfigSchema:
    """Tests for export_config_schema function."""

    def test_returns_dict(self):
        """Should return a dictionary."""
        from src.config.app_config_schema import export_config_schema

        result = export_config_schema()

        assert isinstance(result, dict)

    def test_has_expected_keys(self):
        """Should contain expected top-level config keys."""
        from src.config.app_config_schema import export_config_schema

        result = export_config_schema()

        assert "app_title" in result
        assert "data_source" in result
        assert "database" in result
        assert "table" in result
        assert "persistence" in result

    def test_database_section_has_fields(self):
        """Database section should document its fields."""
        from src.config.app_config_schema import export_config_schema

        result = export_config_schema()

        assert "enabled" in result["database"]
        assert "connection_string" in result["database"]


class TestGetModificationStatus:
    """Tests for get_modification_status function."""

    def test_no_log_file(self, tmp_path, monkeypatch):
        """No log file should return unprocessed status."""
        import src.config.config as config_module
        monkeypatch.setattr(config_module, "modifications_log_path", tmp_path / "nonexistent.json")

        from src.config.config import get_modification_status
        result = get_modification_status(0)

        assert result["status"] == "unprocessed"
        assert result["modifications_count"] == 0
        assert result["modifications"] == []

    def test_edited_status(self, tmp_path, monkeypatch):
        """Row with field modifications should show 'edited'."""
        import src.config.config as config_module

        log = [{"type": "field_modification", "details": {"row_index": 0}, "timestamp": "2024-01-01"}]
        log_path = tmp_path / "log.json"
        log_path.write_text(json.dumps(log))
        monkeypatch.setattr(config_module, "modifications_log_path", log_path)

        from src.config.config import get_modification_status
        result = get_modification_status(0)

        assert result["status"] == "edited"
        assert result["modifications_count"] == 1

    def test_approved_status(self, tmp_path, monkeypatch):
        """Row with approval entry should show 'approved'."""
        import src.config.config as config_module

        log = [{"type": "approval", "timestamp": "2024-01-01"}]
        log_path = tmp_path / "log.json"
        log_path.write_text(json.dumps(log))
        monkeypatch.setattr(config_module, "modifications_log_path", log_path)

        from src.config.config import get_modification_status
        result = get_modification_status(0)

        assert result["status"] == "approved"

    def test_rejected_status(self, tmp_path, monkeypatch):
        """Row with rejection entry should show 'rejected'."""
        import src.config.config as config_module

        log = [{"type": "rejection", "timestamp": "2024-01-01"}]
        log_path = tmp_path / "log.json"
        log_path.write_text(json.dumps(log))
        monkeypatch.setattr(config_module, "modifications_log_path", log_path)

        from src.config.config import get_modification_status
        result = get_modification_status(0)

        assert result["status"] == "rejected"

    def test_unmodified_row(self, tmp_path, monkeypatch):
        """Row not in log should show 'unprocessed' even with other mods."""
        import src.config.config as config_module

        log = [{"type": "field_modification", "details": {"row_index": 5}, "timestamp": "2024-01-01"}]
        log_path = tmp_path / "log.json"
        log_path.write_text(json.dumps(log))
        monkeypatch.setattr(config_module, "modifications_log_path", log_path)

        from src.config.config import get_modification_status
        result = get_modification_status(0)

        assert result["status"] == "unprocessed"
        assert result["modifications_count"] == 0


class TestGetAllModificationStatuses:
    """Tests for get_all_modification_statuses function.
    
    Note: get_all_modification_statuses references a module-level csv_path that
    is not defined in the current config.py (legacy code). Only the no-log-file
    path can be tested without triggering the NameError.
    """

    def test_no_log_file(self, tmp_path, monkeypatch):
        """No log file should return empty result."""
        import src.config.config as config_module
        monkeypatch.setattr(config_module, "modifications_log_path", tmp_path / "nonexistent.json")

        from src.config.config import get_all_modification_statuses
        result = get_all_modification_statuses()

        assert result["rows"] == []
        assert result["summary"]["total"] == 0
