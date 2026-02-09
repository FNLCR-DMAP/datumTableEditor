"""
Tests for preset_utils with mocked database and file operations.
"""
import pytest
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path
import json
import tempfile


class TestIsDbEnabled:
    """Tests for database enabled check."""
    
    def test_database_enabled_true(self):
        """Should return True when database is enabled."""
        with patch('src.utils.preset_utils._load_app_config') as mock_load:
            with patch('src.utils.preset_utils.DB_SERVICE_AVAILABLE', True):
                # Clear the cache first
                import src.utils.preset_utils as preset_utils
                preset_utils._app_config_cache = None
                
                mock_load.return_value = {"database": {"enabled": True}}
                
                from src.utils.preset_utils import _is_database_enabled
                
                result = _is_database_enabled()
                
                assert result is True
    
    def test_database_enabled_false_when_disabled(self):
        """Should return False when database is disabled."""
        with patch('src.utils.preset_utils._load_app_config') as mock_load:
            import src.utils.preset_utils as preset_utils
            preset_utils._app_config_cache = None
            
            mock_load.return_value = {"database": {"enabled": False}}
            
            from src.utils.preset_utils import _is_database_enabled
            
            result = _is_database_enabled()
            
            assert result is False
    
    def test_database_enabled_false_when_service_unavailable(self):
        """Should return False when DB service not available."""
        with patch('src.utils.preset_utils._load_app_config') as mock_load:
            with patch('src.utils.preset_utils.DB_SERVICE_AVAILABLE', False):
                import src.utils.preset_utils as preset_utils
                preset_utils._app_config_cache = None
                
                mock_load.return_value = {"database": {"enabled": True}}
                
                from src.utils.preset_utils import _is_database_enabled
                
                result = _is_database_enabled()
                
                assert result is False


class TestLoadPresets:
    """Tests for load_presets function."""
    
    def test_load_presets_from_file(self):
        """Should load presets from JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('src.utils.preset_utils._is_database_enabled', return_value=False):
                from src.utils.preset_utils import load_presets
                
                presets_file = Path(tmpdir) / "presets.json"
                presets_data = {
                    "Default": {"columns": ["A", "B"], "widths": {}},
                    "Custom": {"columns": ["C", "D"], "widths": {"C": 150}}
                }
                with open(presets_file, 'w') as f:
                    json.dump(presets_data, f)
                
                result = load_presets(presets_file, ["A", "B", "C"])
                
                assert "Default" in result
                assert "Custom" in result
                assert result["Custom"]["columns"] == ["C", "D"]
    
    def test_load_presets_file_not_exists_returns_default(self):
        """Should return default preset when file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('src.utils.preset_utils._is_database_enabled', return_value=False):
                from src.utils.preset_utils import load_presets
                
                presets_file = Path(tmpdir) / "nonexistent.json"
                default_cols = ["X", "Y", "Z"]
                
                result = load_presets(presets_file, default_cols)
                
                assert "Default" in result
                assert result["Default"]["columns"] == ["X", "Y", "Z"]
    
    def test_load_presets_handles_old_list_format(self):
        """Should convert old list format to new dict format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('src.utils.preset_utils._is_database_enabled', return_value=False):
                from src.utils.preset_utils import load_presets
                
                presets_file = Path(tmpdir) / "presets.json"
                # Old format: values are lists, not dicts
                presets_data = {
                    "Default": ["A", "B"],
                    "Custom": ["C", "D"]
                }
                with open(presets_file, 'w') as f:
                    json.dump(presets_data, f)
                
                result = load_presets(presets_file, ["A", "B"])
                
                # Should be converted to new format
                assert isinstance(result["Default"], dict)
                assert result["Default"]["columns"] == ["A", "B"]
                assert "widths" in result["Default"]
    
    def test_load_presets_from_database(self):
        """Should load presets from database when enabled."""
        with patch('src.utils.preset_utils._is_database_enabled', return_value=True):
            with patch('src.utils.preset_utils._get_presets_service') as mock_service:
                from src.utils.preset_utils import load_presets
                
                mock_service.return_value.get_presets.return_value = [
                    {"preset_name": "Default", "columns": ["A", "B"], "is_default": True},
                    {"preset_name": "Custom", "columns": ["C"], "is_default": False}
                ]
                
                result = load_presets(Path("dummy.json"), ["A", "B"], username="testuser")
                
                assert "Default" in result
                assert "Custom" in result


class TestSavePresets:
    """Tests for save_presets function."""
    
    def test_save_presets_to_file(self):
        """Should save presets to JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('src.utils.preset_utils._is_database_enabled', return_value=False):
                from src.utils.preset_utils import save_presets
                
                presets_file = Path(tmpdir) / "presets.json"
                presets_dict = {
                    "Default": {"columns": ["A", "B"], "widths": {}},
                    "Custom": {"columns": ["C"], "widths": {"C": 200}}
                }
                
                save_presets(presets_file, presets_dict)
                
                assert presets_file.exists()
                with open(presets_file) as f:
                    saved = json.load(f)
                assert saved["Custom"]["widths"]["C"] == 200


class TestLoadActivePreset:
    """Tests for load_active_preset function."""
    
    def test_load_active_preset_from_file(self):
        """Should load active preset name from file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('src.utils.preset_utils._is_database_enabled', return_value=False):
                from src.utils.preset_utils import load_active_preset
                
                active_file = Path(tmpdir) / "active.json"
                with open(active_file, 'w') as f:
                    json.dump({"active_preset": "MyPreset"}, f)
                
                result = load_active_preset(active_file)
                
                assert result == "MyPreset"
    
    def test_load_active_preset_default_when_missing(self):
        """Should return 'Default' when file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('src.utils.preset_utils._is_database_enabled', return_value=False):
                from src.utils.preset_utils import load_active_preset
                
                active_file = Path(tmpdir) / "nonexistent.json"
                
                result = load_active_preset(active_file)
                
                assert result == "Default"
    
    def test_load_active_preset_from_database(self):
        """Should load active preset from database when enabled."""
        with patch('src.utils.preset_utils._is_database_enabled', return_value=True):
            with patch('src.utils.preset_utils._get_presets_service') as mock_service:
                from src.utils.preset_utils import load_active_preset
                
                mock_service.return_value.get_default_preset.return_value = {
                    "preset_name": "CustomDefault"
                }
                
                result = load_active_preset(Path("dummy.json"), username="testuser")
                
                assert result == "CustomDefault"
    
    def test_load_active_preset_from_database_no_default(self):
        """Should return 'Default' when no default in database."""
        with patch('src.utils.preset_utils._is_database_enabled', return_value=True):
            with patch('src.utils.preset_utils._get_presets_service') as mock_service:
                from src.utils.preset_utils import load_active_preset
                
                mock_service.return_value.get_default_preset.return_value = None
                
                result = load_active_preset(Path("dummy.json"))
                
                assert result == "Default"


class TestSaveActivePreset:
    """Tests for save_active_preset function."""
    
    def test_save_active_preset_to_file(self):
        """Should save active preset name to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('src.utils.preset_utils._is_database_enabled', return_value=False):
                from src.utils.preset_utils import save_active_preset
                
                active_file = Path(tmpdir) / "active.json"
                
                save_active_preset(active_file, "MyCustomPreset")
                
                assert active_file.exists()
                with open(active_file) as f:
                    data = json.load(f)
                assert data["active_preset"] == "MyCustomPreset"
    
    def test_save_active_preset_to_database(self):
        """Should save active preset to database when enabled."""
        with patch('src.utils.preset_utils._is_database_enabled', return_value=True):
            with patch('src.utils.preset_utils._get_presets_service') as mock_service:
                from src.utils.preset_utils import save_active_preset
                
                mock_service_instance = MagicMock()
                mock_service.return_value = mock_service_instance
                
                save_active_preset(Path("dummy.json"), "NewDefault", username="testuser")
                
                mock_service_instance.set_default.assert_called_once()


class TestGetUsername:
    """Tests for _get_username function."""
    
    def test_get_username_from_config(self):
        """Should get username from config."""
        with patch('src.utils.preset_utils._load_app_config') as mock_load:
            import src.utils.preset_utils as preset_utils
            preset_utils._app_config_cache = None
            
            mock_load.return_value = {"presets": {"default_user": "config_user"}}
            
            from src.utils.preset_utils import _get_username
            
            result = _get_username()
            
            assert result == "config_user"
    
    def test_get_username_default(self):
        """Should return default username when not in config."""
        with patch('src.utils.preset_utils._load_app_config') as mock_load:
            import src.utils.preset_utils as preset_utils
            preset_utils._app_config_cache = None
            
            mock_load.return_value = {}
            
            from src.utils.preset_utils import _get_username
            
            result = _get_username()
            
            assert result == "default_user"


class TestLoadAppConfig:
    """Tests for _load_app_config function."""
    
    def test_load_app_config_caches_result(self):
        """Should cache config after first load."""
        import src.utils.preset_utils as preset_utils
        preset_utils._app_config_cache = None  # Reset cache
        
        with patch('builtins.open', mock_open(read_data='{"test": "value"}')):
            with patch.object(Path, 'exists', return_value=True):
                from src.utils.preset_utils import _load_app_config
                
                result1 = _load_app_config()
                result2 = _load_app_config()
                
                assert result1 is result2  # Same object
    
    def test_load_app_config_returns_empty_when_missing(self):
        """Should return empty dict when config file missing."""
        import src.utils.preset_utils as preset_utils
        preset_utils._app_config_cache = None  # Reset cache
        
        with patch.object(Path, 'exists', return_value=False):
            from src.utils.preset_utils import _load_app_config
            
            result = _load_app_config()
            
            assert result == {}

class TestLoadPresetsDBFallback:
    """Tests for load_presets DB fallback behavior."""
    
    def test_load_presets_db_error_falls_back_to_file(self):
        """Should fall back to file when DB fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('src.utils.preset_utils._is_database_enabled', return_value=True):
                with patch('src.utils.preset_utils._get_presets_service') as mock_service:
                    from src.utils.preset_utils import load_presets
                    
                    mock_service.return_value.get_presets.side_effect = Exception("DB error")
                    
                    presets_file = Path(tmpdir) / "presets.json"
                    presets_data = {"Fallback": {"columns": ["F1", "F2"], "widths": {}}}
                    with open(presets_file, 'w') as f:
                        json.dump(presets_data, f)
                    
                    result = load_presets(presets_file, ["A", "B"])
                    
                    assert "Fallback" in result
    
    def test_load_presets_db_empty_returns_default(self):
        """Should return default preset when DB has no presets."""
        with patch('src.utils.preset_utils._is_database_enabled', return_value=True):
            with patch('src.utils.preset_utils._get_presets_service') as mock_service:
                from src.utils.preset_utils import load_presets
                
                mock_service.return_value.get_presets.return_value = []
                
                result = load_presets(Path("dummy.json"), ["X", "Y", "Z"])
                
                assert result == {"Default": {"columns": ["X", "Y", "Z"], "widths": {}}}
    
    def test_load_presets_db_with_nested_columns_format(self):
        """Should handle DB format with nested columns/widths."""
        with patch('src.utils.preset_utils._is_database_enabled', return_value=True):
            with patch('src.utils.preset_utils._get_presets_service') as mock_service:
                from src.utils.preset_utils import load_presets
                
                # Format where columns contains a dict with "columns" key
                mock_service.return_value.get_presets.return_value = [
                    {"preset_name": "Nested", "columns": {"columns": ["A", "B"], "widths": {"A": 100}}}
                ]
                
                result = load_presets(Path("dummy.json"), ["A", "B"])
                
                assert "Nested" in result
                assert result["Nested"]["columns"] == ["A", "B"]
    
    def test_load_presets_adds_default_if_missing_from_db(self):
        """Should add Default preset if not in DB results."""
        with patch('src.utils.preset_utils._is_database_enabled', return_value=True):
            with patch('src.utils.preset_utils._get_presets_service') as mock_service:
                from src.utils.preset_utils import load_presets
                
                mock_service.return_value.get_presets.return_value = [
                    {"preset_name": "Custom", "columns": ["C"]}
                ]
                
                result = load_presets(Path("dummy.json"), ["X", "Y"])
                
                assert "Default" in result
                assert "Custom" in result
    
    def test_load_presets_file_parse_error_returns_default(self):
        """Should return default when file has invalid JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('src.utils.preset_utils._is_database_enabled', return_value=False):
                from src.utils.preset_utils import load_presets
                
                presets_file = Path(tmpdir) / "invalid.json"
                with open(presets_file, 'w') as f:
                    f.write("not valid json {")
                
                result = load_presets(presets_file, ["A", "B"])
                
                assert "Default" in result


class TestSavePresetsDB:
    """Tests for save_presets database operations."""
    
    def test_save_presets_to_database(self):
        """Should save presets to database when enabled."""
        with patch('src.utils.preset_utils._is_database_enabled', return_value=True):
            with patch('src.utils.preset_utils._get_presets_service') as mock_service:
                from src.utils.preset_utils import save_presets
                
                mock_instance = MagicMock()
                mock_instance.get_presets.return_value = []
                mock_service.return_value = mock_instance
                
                presets_dict = {
                    "Default": {"columns": ["A", "B"], "widths": {}},
                    "Custom": {"columns": ["C"], "widths": {}}
                }
                
                save_presets(Path("dummy.json"), presets_dict, username="testuser")
                
                # Should have called save_preset for each preset
                assert mock_instance.save_preset.call_count == 2
    
    def test_save_presets_deletes_removed_presets(self):
        """Should delete presets removed from dict."""
        with patch('src.utils.preset_utils._is_database_enabled', return_value=True):
            with patch('src.utils.preset_utils._get_presets_service') as mock_service:
                from src.utils.preset_utils import save_presets
                
                mock_instance = MagicMock()
                # Existing presets in DB
                mock_instance.get_presets.return_value = [
                    {"preset_name": "Default", "is_default": True},
                    {"preset_name": "ToDelete", "is_default": False}
                ]
                mock_service.return_value = mock_instance
                
                # Only Default in new dict
                presets_dict = {"Default": {"columns": ["A"], "widths": {}}}
                
                save_presets(Path("dummy.json"), presets_dict, username="testuser")
                
                # Should have deleted ToDelete
                mock_instance.delete_preset.assert_called()
    
    def test_save_presets_db_error_falls_back_to_file(self):
        """Should fall back to file when DB save fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('src.utils.preset_utils._is_database_enabled', return_value=True):
                with patch('src.utils.preset_utils._get_presets_service') as mock_service:
                    from src.utils.preset_utils import save_presets
                    
                    mock_service.return_value.get_presets.side_effect = Exception("DB error")
                    
                    presets_file = Path(tmpdir) / "presets.json"
                    presets_dict = {"Default": {"columns": ["A"], "widths": {}}}
                    
                    save_presets(presets_file, presets_dict)
                    
                    # Should have saved to file
                    assert presets_file.exists()


class TestLoadActivePresetDBFallback:
    """Tests for load_active_preset DB fallback behavior."""
    
    def test_load_active_preset_db_error_falls_back_to_file(self):
        """Should fall back to file when DB fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('src.utils.preset_utils._is_database_enabled', return_value=True):
                with patch('src.utils.preset_utils._get_presets_service') as mock_service:
                    from src.utils.preset_utils import load_active_preset
                    
                    mock_service.return_value.get_default_preset.side_effect = Exception("DB error")
                    
                    active_file = Path(tmpdir) / "active.json"
                    with open(active_file, 'w') as f:
                        json.dump({"active_preset": "FileFallback"}, f)
                    
                    result = load_active_preset(active_file)
                    
                    assert result == "FileFallback"
    
    def test_load_active_preset_file_parse_error(self):
        """Should return Default when file has invalid JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('src.utils.preset_utils._is_database_enabled', return_value=False):
                from src.utils.preset_utils import load_active_preset
                
                active_file = Path(tmpdir) / "invalid.json"
                with open(active_file, 'w') as f:
                    f.write("not valid json")
                
                result = load_active_preset(active_file)
                
                assert result == "Default"


class TestSaveActivePresetDBFallback:
    """Tests for save_active_preset DB fallback behavior."""
    
    def test_save_active_preset_db_error_falls_back_to_file(self):
        """Should fall back to file when DB save fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('src.utils.preset_utils._is_database_enabled', return_value=True):
                with patch('src.utils.preset_utils._get_presets_service') as mock_service:
                    from src.utils.preset_utils import save_active_preset
                    
                    mock_service.return_value.set_default.side_effect = Exception("DB error")
                    
                    active_file = Path(tmpdir) / "active.json"
                    
                    save_active_preset(active_file, "TestPreset")
                    
                    # Should have saved to file
                    assert active_file.exists()


class TestGetPresetsService:
    """Tests for _get_presets_service function."""
    
    def test_get_presets_service_caches_by_table_name(self):
        """Should cache service instances by table name."""
        import src.utils.preset_utils as preset_utils
        preset_utils._presets_service_cache = {}  # Reset cache
        
        with patch('src.utils.preset_utils.UserPresetsService') as MockService:
            from src.utils.preset_utils import _get_presets_service
            
            mock_instance = MagicMock()
            MockService.return_value = mock_instance
            
            service1 = _get_presets_service("table1")
            service2 = _get_presets_service("table1")
            
            # Should return same cached instance
            assert service1 is service2
            # Should have only created once
            assert MockService.call_count == 1
    
    def test_get_presets_service_different_tables(self):
        """Should create separate service for different tables."""
        import src.utils.preset_utils as preset_utils
        preset_utils._presets_service_cache = {}  # Reset cache
        
        with patch('src.utils.preset_utils.UserPresetsService') as MockService:
            from src.utils.preset_utils import _get_presets_service
            
            _get_presets_service("table1")
            _get_presets_service("table2")
            
            # Should have created two instances
            assert MockService.call_count == 2
    
    def test_get_presets_service_none_table_uses_default(self):
        """Should use _default key for None table name."""
        import src.utils.preset_utils as preset_utils
        preset_utils._presets_service_cache = {}  # Reset cache
        
        with patch('src.utils.preset_utils.UserPresetsService') as MockService:
            from src.utils.preset_utils import _get_presets_service
            
            _get_presets_service(None)
            
            # Should be in cache with _default key
            assert "_default" in preset_utils._presets_service_cache