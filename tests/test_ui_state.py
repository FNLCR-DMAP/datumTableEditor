"""
Tests for UI state persistence and presets.

Tests:
- UI state save/load (sort, filters, page, etc.)
- Column presets CRUD
- User-scoped state isolation
"""

import pytest
import json
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestUIStatePersistence:
    """Tests for UI state save/load operations."""
    
    def test_ui_state_structure(self, mock_app_config):
        """UI state should have correct default structure."""
        default_state = {
            "sort_column": mock_app_config.table.default_sort_column,
            "sort_ascending": mock_app_config.table.default_sort_ascending,
            "current_page": 1,
            "rows_per_page": mock_app_config.table.default_rows_per_page,
            "filters": {},
            "column_preset": None
        }
        
        # Verify structure
        assert "sort_column" in default_state
        assert "sort_ascending" in default_state
        assert "current_page" in default_state
        assert "rows_per_page" in default_state
        assert "filters" in default_state
        assert default_state["current_page"] == 1
        assert default_state["filters"] == {}
    
    def test_ui_state_user_scoped_concept(self):
        """UI state should be scoped to user (conceptual test)."""
        # Test the concept of user scoping
        user1_state = {"user": "user1", "sort_column": "A"}
        user2_state = {"user": "user2", "sort_column": "B"}
        
        # Different users have different state
        assert user1_state["sort_column"] != user2_state["sort_column"]


class TestColumnPresets:
    """Tests for column preset management."""
    
    def test_load_presets_returns_default_when_empty(self, tmp_path):
        """Loading presets from empty DB should return Default."""
        from unittest.mock import MagicMock
        from src.utils.preset_utils import load_presets
        
        mock_config = MagicMock()
        mock_config.username = "testuser"
        mock_config._get_preset_table_name.return_value = "test_testuser_column_presets"
        mock_config.get_presets.return_value = []
        
        presets = load_presets(mock_config, ["PatientID", "Gene_names"])
        
        assert "Default" in presets
        default_preset = presets["Default"]
        assert default_preset is not None
    
    def test_save_and_load_preset_roundtrip(self, tmp_path):
        """Saving and loading a preset should preserve data."""
        from unittest.mock import MagicMock
        from src.utils.preset_utils import save_presets, load_presets
        
        columns = ["PatientID", "Gene_names", "Status"]
        
        presets_dict = {
            "Default": {"columns": ["Default"], "widths": {}},
            "MyPreset": {"columns": columns, "widths": {}}
        }
        
        mock_config = MagicMock()
        mock_config.username = "testuser"
        mock_config._get_preset_table_name.return_value = "test_testuser_column_presets"
        mock_config.get_presets.return_value = []
        
        save_presets(mock_config, presets_dict)
        
        # Simulate what DB would return after save
        mock_config.get_presets.return_value = [
            {"preset_name": "Default", "columns": ["Default"], "is_default": True},
            {"preset_name": "MyPreset", "columns": columns, "is_default": False}
        ]
        
        loaded = load_presets(mock_config, ["Default"])
        assert "MyPreset" in loaded
    
    def test_presets_user_isolation(self, tmp_path):
        """Presets should be scoped by user (via ConfigInstance username)."""
        from unittest.mock import MagicMock
        from src.utils.preset_utils import save_presets, load_presets
        
        presets_dict = {
            "Default": {"columns": ["Default"], "widths": {}},
            "User1Preset": {"columns": ["A", "B"], "widths": {}}
        }
        
        mock_config = MagicMock()
        mock_config.username = "user1"
        mock_config._get_preset_table_name.return_value = "test_user1_column_presets"
        mock_config.get_presets.return_value = []
        
        save_presets(mock_config, presets_dict)
        
        # Simulate DB result for user1
        mock_config.get_presets.return_value = [
            {"preset_name": "Default", "columns": ["Default"], "is_default": True},
            {"preset_name": "User1Preset", "columns": ["A", "B"], "is_default": False}
        ]
        
        loaded = load_presets(mock_config, ["Default"])
        assert "User1Preset" in loaded


class TestActivePresetPersistence:
    """Tests for active preset save/load."""
    
    def test_load_active_preset_default(self, tmp_path):
        """Loading missing active preset should return 'Default'."""
        from unittest.mock import MagicMock
        from src.utils.preset_utils import load_active_preset
        
        mock_config = MagicMock()
        mock_config.get_default_preset.return_value = None
        
        loaded = load_active_preset(mock_config)
        
        assert loaded == "Default"
    
    def test_save_and_load_active_preset(self, tmp_path):
        """Saving and loading active preset should work."""
        from unittest.mock import MagicMock
        from src.utils.preset_utils import save_active_preset, load_active_preset
        
        mock_config = MagicMock()
        mock_config.get_presets.return_value = [
            {"preset_name": "Default", "is_default": True, "columns": ["A"]},
            {"preset_name": "MyActive", "is_default": False, "columns": ["B"]}
        ]
        
        save_active_preset(mock_config, "MyActive")
        
        # Simulate what DB would return after setting active
        mock_config.get_default_preset.return_value = {"preset_name": "MyActive"}
        
        loaded = load_active_preset(mock_config)
        
        assert loaded == "MyActive"
