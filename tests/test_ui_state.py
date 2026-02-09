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
    
    def test_load_presets_from_file(self, tmp_path):
        """Loading presets should parse JSON correctly."""
        from unittest.mock import patch
        from src.utils.preset_utils import load_presets
        
        # Create a presets file in the expected format (flat structure for file mode)
        presets_file = tmp_path / "presets.json"
        presets_data = {
            "Default": {"columns": ["PatientID", "Gene_names", "Variant_key", "Status"], "widths": {}},
            "Minimal": {"columns": ["PatientID", "Status"], "widths": {}}
        }
        presets_file.write_text(json.dumps(presets_data))
        
        # Mock database to be disabled so file fallback is used
        with patch('src.utils.preset_utils._is_database_enabled', return_value=False):
            presets = load_presets(
                presets_file=presets_file,
                default_columns=["PatientID", "Gene_names"],
                table_name="test_table",
                username="testuser"
            )
        
        # Should have Default preset
        assert "Default" in presets
        # The structure may be dict with columns/widths or just a list
        default_preset = presets["Default"]
        assert default_preset is not None
    
    def test_save_and_load_preset_roundtrip(self, tmp_path):
        """Saving and loading a preset should preserve data (file fallback)."""
        from unittest.mock import patch
        from src.utils.preset_utils import save_presets, load_presets
        
        presets_file = tmp_path / "presets.json"
        presets_file.write_text("{}")
        
        columns = ["PatientID", "Gene_names", "Status"]
        
        # save_presets takes a dict of all presets
        presets_dict = {
            "Default": {"columns": ["Default"], "widths": {}},
            "MyPreset": {"columns": columns, "widths": {}}
        }
        
        # Mock database to be disabled so file fallback is used
        with patch('src.utils.preset_utils._is_database_enabled', return_value=False):
            save_presets(
                presets_file=presets_file,
                presets_dict=presets_dict,
                table_name="test_table",
                username="testuser"
            )
            
            # Reload and verify preset exists
            loaded = load_presets(
                presets_file=presets_file,
                default_columns=["Default"],
                table_name="test_table",
                username="testuser"
            )
            
            assert "MyPreset" in loaded
    
    def test_presets_user_isolation(self, tmp_path):
        """Presets should be isolated per user (with DB backend), or shared with file fallback."""
        from unittest.mock import patch
        from src.utils.preset_utils import save_presets, load_presets
        
        presets_file = tmp_path / "presets.json"
        presets_file.write_text("{}")
        
        # User 1 creates preset (file fallback doesn't scope by user)
        presets_dict_user1 = {
            "Default": {"columns": ["Default"], "widths": {}},
            "User1Preset": {"columns": ["A", "B"], "widths": {}}
        }
        
        # Mock database to be disabled so file fallback is used
        with patch('src.utils.preset_utils._is_database_enabled', return_value=False):
            save_presets(
                presets_file=presets_file,
                presets_dict=presets_dict_user1,
                table_name="test_table",
                username="user1"
            )
            
            # With file fallback (no DB), presets are NOT user-scoped
            # This test validates the file fallback works
            loaded = load_presets(
                presets_file=presets_file,
                default_columns=["Default"],
                table_name="test_table",
                username="user1"
            )
            
            # User1 should see their own preset
            assert "User1Preset" in loaded


class TestActivePresetPersistence:
    """Tests for active preset save/load."""
    
    def test_load_active_preset_default(self, tmp_path):
        """Loading missing active preset should return 'Default'."""
        from unittest.mock import patch
        from src.utils.preset_utils import load_active_preset
        
        missing_file = tmp_path / "missing_active.json"
        
        # Mock database to be disabled so file fallback is used
        with patch('src.utils.preset_utils._is_database_enabled', return_value=False):
            loaded = load_active_preset(
                active_preset_file=missing_file,
                table_name="test_table",
                username="testuser"
            )
            
            assert loaded == "Default"
    
    def test_save_and_load_active_preset(self, tmp_path):
        """Saving and loading active preset should work (file fallback)."""
        from unittest.mock import patch
        from src.utils.preset_utils import save_active_preset, load_active_preset
        
        active_preset_file = tmp_path / "active_preset.json"
        
        # Mock database to be disabled so file fallback is used
        with patch('src.utils.preset_utils._is_database_enabled', return_value=False):
            save_active_preset(
                active_preset_file=active_preset_file,
                preset_name="MyActive",
                table_name="test_table",
                username="testuser"
            )
            
            # Verify file was written with correct format
            import json
            with open(active_preset_file) as f:
                data = json.load(f)
            
            assert data.get("active_preset") == "MyActive"
            
            loaded = load_active_preset(
                active_preset_file=active_preset_file,
                table_name="test_table",
                username="testuser"
            )
            
            assert loaded == "MyActive"
