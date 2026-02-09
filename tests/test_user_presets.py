"""
Tests for UserPresetsService with mocked database connections.
"""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
import json


class TestUserPresetsServiceInit:
    """Tests for UserPresetsService initialization."""
    
    def test_init_with_engine(self):
        """Should accept existing engine."""
        with patch('src.db.user_presets.SQLALCHEMY_AVAILABLE', True):
            from src.db.user_presets import UserPresetsService
            
            mock_engine = MagicMock()
            service = UserPresetsService(engine=mock_engine, table_name="test")
            
            assert service._engine is mock_engine
    
    def test_get_preset_table_name(self):
        """Should generate correct table name."""
        with patch('src.db.user_presets.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.user_presets.create_engine'):
                from src.db.user_presets import UserPresetsService
                
                mock_engine = MagicMock()
                service = UserPresetsService(engine=mock_engine, table_name="epitopes")
                
                table_name = service._get_preset_table_name("john_doe")
                
                assert table_name == "epitopes_john_doe_column_presets"
    
    def test_get_preset_table_name_sanitizes(self):
        """Should sanitize username for table name."""
        with patch('src.db.user_presets.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.user_presets.create_engine'):
                from src.db.user_presets import UserPresetsService
                
                mock_engine = MagicMock()
                service = UserPresetsService(engine=mock_engine, table_name="epitopes")
                
                # Special characters should be replaced
                table_name = service._get_preset_table_name("john@company.com")
                
                assert "@" not in table_name
                assert "." not in table_name


class TestUserPresetsServiceSavePreset:
    """Tests for saving presets."""
    
    @pytest.fixture
    def mock_service(self):
        """Create service with mocked engine."""
        with patch('src.db.user_presets.SQLALCHEMY_AVAILABLE', True):
            from src.db.user_presets import UserPresetsService
            
            mock_engine = MagicMock()
            mock_conn = MagicMock()
            mock_result = MagicMock()
            mock_result.scalar.return_value = 1  # Return preset ID
            mock_conn.execute.return_value = mock_result
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_engine.connect.return_value = mock_conn
            
            service = UserPresetsService(engine=mock_engine, table_name="test")
            service._mock_conn = mock_conn  # Store for assertions
            return service
    
    def test_save_preset_returns_id(self, mock_service):
        """Saving preset should return preset ID."""
        # Mock _ensure_table_exists
        mock_service._ensure_table_exists = MagicMock(return_value="test_user_column_presets")
        
        preset_id = mock_service.save_preset(
            username="user1",
            preset_name="MyPreset",
            columns=["A", "B", "C"],
            is_default=False
        )
        
        assert preset_id == 1


class TestUserPresetsServiceEnsureTable:
    """Tests for ensuring table exists."""
    
    def test_ensure_table_creates_table(self):
        """Should create table if it doesn't exist."""
        with patch('src.db.user_presets.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.user_presets.inspect') as mock_inspect:
                from src.db.user_presets import UserPresetsService
                
                mock_engine = MagicMock()
                mock_conn = MagicMock()
                mock_conn.__enter__ = MagicMock(return_value=mock_conn)
                mock_conn.__exit__ = MagicMock(return_value=False)
                mock_engine.connect.return_value = mock_conn
                
                mock_inspector = MagicMock()
                mock_inspector.get_table_names.return_value = []  # Table doesn't exist
                mock_inspect.return_value = mock_inspector
                
                service = UserPresetsService(engine=mock_engine, table_name="test")
                table_name = service._ensure_table_exists("user1")
                
                # Should have executed CREATE TABLE
                assert mock_conn.execute.called
                assert table_name == "test_user1_column_presets"


class TestUserPresetsServiceGetPresets:
    """Tests for getting presets."""
    
    def test_get_presets_empty_when_no_table(self):
        """Should return empty list when table doesn't exist."""
        with patch('src.db.user_presets.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.user_presets.inspect') as mock_inspect:
                from src.db.user_presets import UserPresetsService
                
                mock_engine = MagicMock()
                mock_inspector = MagicMock()
                mock_inspector.get_table_names.return_value = []  # No tables
                mock_inspect.return_value = mock_inspector
                
                service = UserPresetsService(engine=mock_engine, table_name="test")
                presets = service.get_presets("newuser")
                
                assert presets == []


class TestUserPresetsServiceGetPresetByName:
    """Tests for getting a specific preset by name."""
    
    def test_get_preset_by_name_not_found(self):
        """Should return None if preset not found."""
        with patch('src.db.user_presets.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.user_presets.inspect') as mock_inspect:
                from src.db.user_presets import UserPresetsService
                
                mock_engine = MagicMock()
                mock_conn = MagicMock()
                mock_result = MagicMock()
                mock_result.fetchone.return_value = None
                mock_conn.execute.return_value = mock_result
                mock_conn.__enter__ = MagicMock(return_value=mock_conn)
                mock_conn.__exit__ = MagicMock(return_value=False)
                mock_engine.connect.return_value = mock_conn
                
                mock_inspector = MagicMock()
                mock_inspector.get_table_names.return_value = ["test_user_column_presets"]
                mock_inspect.return_value = mock_inspector
                
                service = UserPresetsService(engine=mock_engine, table_name="test")
                result = service.get_preset_by_name("user", "NonExistent")
                
                assert result is None


class TestUserPresetsServiceDeletePreset:
    """Tests for deleting presets."""
    
    def test_delete_preset_returns_true(self):
        """Should return True if preset deleted."""
        with patch('src.db.user_presets.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.user_presets.inspect') as mock_inspect:
                from src.db.user_presets import UserPresetsService
                
                mock_engine = MagicMock()
                mock_conn = MagicMock()
                mock_result = MagicMock()
                mock_result.rowcount = 1  # 1 row deleted
                mock_conn.execute.return_value = mock_result
                mock_conn.__enter__ = MagicMock(return_value=mock_conn)
                mock_conn.__exit__ = MagicMock(return_value=False)
                mock_engine.connect.return_value = mock_conn
                
                mock_inspector = MagicMock()
                mock_inspector.get_table_names.return_value = ["test_user_column_presets"]
                mock_inspect.return_value = mock_inspector
                
                service = UserPresetsService(engine=mock_engine, table_name="test")
                result = service.delete_preset("user", "MyPreset")
                
                assert result is True
    
    def test_delete_preset_returns_false_not_found(self):
        """Should return False if preset not found."""
        with patch('src.db.user_presets.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.user_presets.inspect') as mock_inspect:
                from src.db.user_presets import UserPresetsService
                
                mock_engine = MagicMock()
                mock_conn = MagicMock()
                mock_result = MagicMock()
                mock_result.rowcount = 0  # No rows deleted
                mock_conn.execute.return_value = mock_result
                mock_conn.__enter__ = MagicMock(return_value=mock_conn)
                mock_conn.__exit__ = MagicMock(return_value=False)
                mock_engine.connect.return_value = mock_conn
                
                mock_inspector = MagicMock()
                mock_inspector.get_table_names.return_value = ["test_user_column_presets"]
                mock_inspect.return_value = mock_inspector
                
                service = UserPresetsService(engine=mock_engine, table_name="test")
                result = service.delete_preset("user", "NonExistent")
                
                assert result is False
    
    def test_delete_preset_no_table(self):
        """Should return False if table doesn't exist."""
        with patch('src.db.user_presets.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.user_presets.inspect') as mock_inspect:
                from src.db.user_presets import UserPresetsService
                
                mock_engine = MagicMock()
                mock_inspector = MagicMock()
                mock_inspector.get_table_names.return_value = []  # No tables
                mock_inspect.return_value = mock_inspector
                
                service = UserPresetsService(engine=mock_engine, table_name="test")
                result = service.delete_preset("newuser", "MyPreset")
                
                assert result is False

class TestUserPresetsServiceGetDefaultPreset:
    """Tests for getting default preset."""
    
    def test_get_default_preset_no_table(self):
        """Should return None if table doesn't exist."""
        with patch('src.db.user_presets.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.user_presets.inspect') as mock_inspect:
                from src.db.user_presets import UserPresetsService
                
                mock_engine = MagicMock()
                mock_inspector = MagicMock()
                mock_inspector.get_table_names.return_value = []
                mock_inspect.return_value = mock_inspector
                
                service = UserPresetsService(engine=mock_engine, table_name="test")
                result = service.get_default_preset("newuser")
                
                assert result is None
    
    def test_get_default_preset_not_set(self):
        """Should return None if no default preset set."""
        with patch('src.db.user_presets.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.user_presets.inspect') as mock_inspect:
                from src.db.user_presets import UserPresetsService
                
                mock_engine = MagicMock()
                mock_conn = MagicMock()
                mock_result = MagicMock()
                mock_result.fetchone.return_value = None
                mock_conn.execute.return_value = mock_result
                mock_conn.__enter__ = MagicMock(return_value=mock_conn)
                mock_conn.__exit__ = MagicMock(return_value=False)
                mock_engine.connect.return_value = mock_conn
                
                mock_inspector = MagicMock()
                mock_inspector.get_table_names.return_value = ["test_user_column_presets"]
                mock_inspect.return_value = mock_inspector
                
                service = UserPresetsService(engine=mock_engine, table_name="test")
                result = service.get_default_preset("user")
                
                assert result is None


class TestUserPresetsServiceSetDefault:
    """Tests for setting default preset."""
    
    def test_set_default_no_table(self):
        """Should return False if table doesn't exist."""
        with patch('src.db.user_presets.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.user_presets.inspect') as mock_inspect:
                from src.db.user_presets import UserPresetsService
                
                mock_engine = MagicMock()
                mock_inspector = MagicMock()
                mock_inspector.get_table_names.return_value = []
                mock_inspect.return_value = mock_inspector
                
                service = UserPresetsService(engine=mock_engine, table_name="test")
                result = service.set_default("newuser", "SomePreset")
                
                assert result is False
    
    def test_set_default_success(self):
        """Should return True if preset was set as default."""
        with patch('src.db.user_presets.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.user_presets.inspect') as mock_inspect:
                from src.db.user_presets import UserPresetsService
                
                mock_engine = MagicMock()
                mock_conn = MagicMock()
                mock_result = MagicMock()
                mock_result.rowcount = 1
                mock_conn.execute.return_value = mock_result
                mock_conn.__enter__ = MagicMock(return_value=mock_conn)
                mock_conn.__exit__ = MagicMock(return_value=False)
                mock_engine.connect.return_value = mock_conn
                
                mock_inspector = MagicMock()
                mock_inspector.get_table_names.return_value = ["test_user_column_presets"]
                mock_inspect.return_value = mock_inspector
                
                service = UserPresetsService(engine=mock_engine, table_name="test")
                result = service.set_default("user", "MyPreset")
                
                assert result is True


class TestUserPresetsServiceListUsers:
    """Tests for listing users with presets."""
    
    def test_list_users_empty(self):
        """Should return empty list if no preset tables."""
        with patch('src.db.user_presets.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.user_presets.inspect') as mock_inspect:
                from src.db.user_presets import UserPresetsService
                
                mock_engine = MagicMock()
                mock_inspector = MagicMock()
                mock_inspector.get_table_names.return_value = []
                mock_inspect.return_value = mock_inspector
                
                service = UserPresetsService(engine=mock_engine, table_name="test")
                users = service.list_users()
                
                assert users == []
    
    def test_list_users_finds_users(self):
        """Should extract usernames from table names."""
        with patch('src.db.user_presets.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.user_presets.inspect') as mock_inspect:
                from src.db.user_presets import UserPresetsService
                
                mock_engine = MagicMock()
                mock_inspector = MagicMock()
                mock_inspector.get_table_names.return_value = [
                    "test_alice_column_presets",
                    "test_bob_column_presets",
                    "other_table"
                ]
                mock_inspect.return_value = mock_inspector
                
                service = UserPresetsService(engine=mock_engine, table_name="test")
                users = service.list_users()
                
                assert "alice" in users
                assert "bob" in users
                assert len(users) == 2


class TestUserPresetsServiceProperties:
    """Tests for service properties."""
    
    def test_engine_property(self):
        """Should return the engine."""
        with patch('src.db.user_presets.SQLALCHEMY_AVAILABLE', True):
            from src.db.user_presets import UserPresetsService
            
            mock_engine = MagicMock()
            service = UserPresetsService(engine=mock_engine, table_name="test")
            
            assert service.engine is mock_engine
    
    def test_table_name_property(self):
        """Should return the table name."""
        with patch('src.db.user_presets.SQLALCHEMY_AVAILABLE', True):
            from src.db.user_presets import UserPresetsService
            
            mock_engine = MagicMock()
            service = UserPresetsService(engine=mock_engine, table_name="my_table")
            
            assert service.table_name == "my_table"


class TestStandaloneFunctions:
    """Tests for standalone backward compatibility functions."""
    
    def test_get_user_preset_table_name(self):
        """Should generate correct table name."""
        with patch('src.db.user_presets.SQLALCHEMY_AVAILABLE', True):
            from src.db.user_presets import get_user_preset_table_name
            
            result = get_user_preset_table_name("epitopes", "john")
            
            assert result == "epitopes_john_column_presets"
    
    def test_get_user_preset_table_name_sanitizes(self):
        """Should sanitize special characters."""
        with patch('src.db.user_presets.SQLALCHEMY_AVAILABLE', True):
            from src.db.user_presets import get_user_preset_table_name
            
            result = get_user_preset_table_name("epitopes", "john@test.com")
            
            assert "@" not in result
            assert "." not in result
    
    def test_list_user_preset_tables(self):
        """Should list preset tables."""
        with patch('src.db.user_presets.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.user_presets.inspect') as mock_inspect:
                from src.db.user_presets import list_user_preset_tables
                
                mock_engine = MagicMock()
                mock_inspector = MagicMock()
                mock_inspector.get_table_names.return_value = [
                    "test_alice_column_presets",
                    "test_bob_column_presets",
                    "other_table"
                ]
                mock_inspect.return_value = mock_inspector
                
                result = list_user_preset_tables(mock_engine)
                
                assert "test_alice_column_presets" in result
                assert "test_bob_column_presets" in result
                assert "other_table" not in result
    
    def test_list_user_preset_tables_with_filter(self):
        """Should filter by table name prefix."""
        with patch('src.db.user_presets.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.user_presets.inspect') as mock_inspect:
                from src.db.user_presets import list_user_preset_tables
                
                mock_engine = MagicMock()
                mock_inspector = MagicMock()
                mock_inspector.get_table_names.return_value = [
                    "test_alice_column_presets",
                    "other_bob_column_presets"
                ]
                mock_inspect.return_value = mock_inspector
                
                result = list_user_preset_tables(mock_engine, table_name="test")
                
                assert "test_alice_column_presets" in result
                assert "other_bob_column_presets" not in result


class TestUserPresetsServiceLoadFromConfig:
    """Tests for loading configuration."""
    
    def test_load_from_config_file_exists(self):
        """Should load from app_config.json if it exists."""
        import tempfile
        import os
        from pathlib import Path as RealPath
        
        with patch('src.db.user_presets.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.user_presets.create_engine') as mock_create_engine:
                from src.db.user_presets import UserPresetsService
                
                # Create a temp config file
                config_content = {
                    "database": {"connection_string": "postgresql://test@localhost/testdb"},
                    "data_source": {"table_name": "my_table"}
                }
                
                with tempfile.TemporaryDirectory() as tmpdir:
                    # We need to patch PROJECT_ROOT as a Path object
                    with patch('src.db.user_presets.PROJECT_ROOT', RealPath(tmpdir)):
                        config_path = os.path.join(tmpdir, "app_config.json")
                        with open(config_path, 'w') as f:
                            json.dump(config_content, f)
                        
                        mock_engine = MagicMock()
                        mock_create_engine.return_value = mock_engine
                        
                        service = UserPresetsService()
                        
                        mock_create_engine.assert_called_with("postgresql://test@localhost/testdb")
                        assert service._table_name == "my_table"


class TestUserPresetsServiceGetPresetByNameWithData:
    """Tests for get_preset_by_name with actual data."""
    
    def test_get_preset_by_name_returns_dict(self):
        """Should return preset dict when found."""
        from datetime import datetime
        
        with patch('src.db.user_presets.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.user_presets.inspect') as mock_inspect:
                from src.db.user_presets import UserPresetsService
                
                mock_engine = MagicMock()
                mock_conn = MagicMock()
                
                # Mock row with datetime
                mock_row = (1, "MyPreset", ["col1", "col2"], True, datetime(2024, 1, 1), datetime(2024, 1, 2))
                mock_result = MagicMock()
                mock_result.fetchone.return_value = mock_row
                mock_conn.execute.return_value = mock_result
                mock_conn.__enter__ = MagicMock(return_value=mock_conn)
                mock_conn.__exit__ = MagicMock(return_value=False)
                mock_engine.connect.return_value = mock_conn
                
                mock_inspector = MagicMock()
                mock_inspector.get_table_names.return_value = ["test_user_column_presets"]
                mock_inspect.return_value = mock_inspector
                
                service = UserPresetsService(engine=mock_engine, table_name="test")
                result = service.get_preset_by_name("user", "MyPreset")
                
                assert result is not None
                assert result["id"] == 1
                assert result["preset_name"] == "MyPreset"
                assert result["columns"] == ["col1", "col2"]
                assert result["is_default"] is True

    def test_get_preset_by_name_no_table(self):
        """Should return None if table doesn't exist."""
        with patch('src.db.user_presets.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.user_presets.inspect') as mock_inspect:
                from src.db.user_presets import UserPresetsService
                
                mock_engine = MagicMock()
                mock_inspector = MagicMock()
                mock_inspector.get_table_names.return_value = []
                mock_inspect.return_value = mock_inspector
                
                service = UserPresetsService(engine=mock_engine, table_name="test")
                result = service.get_preset_by_name("newuser", "SomePreset")
                
                assert result is None


class TestUserPresetsServiceGetPresetsWithData:
    """Tests for get_presets returning data."""
    
    def test_get_presets_returns_list(self):
        """Should return list of presets."""
        from datetime import datetime
        
        with patch('src.db.user_presets.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.user_presets.inspect') as mock_inspect:
                from src.db.user_presets import UserPresetsService
                
                mock_engine = MagicMock()
                mock_conn = MagicMock()
                
                # Mock rows
                mock_rows = [
                    (1, "Preset1", ["col1"], False, datetime(2024, 1, 1), datetime(2024, 1, 2)),
                    (2, "Preset2", ["col2"], True, datetime(2024, 1, 3), datetime(2024, 1, 4)),
                ]
                mock_result = MagicMock()
                mock_result.__iter__ = MagicMock(return_value=iter(mock_rows))
                mock_conn.execute.return_value = mock_result
                mock_conn.__enter__ = MagicMock(return_value=mock_conn)
                mock_conn.__exit__ = MagicMock(return_value=False)
                mock_engine.connect.return_value = mock_conn
                
                mock_inspector = MagicMock()
                mock_inspector.get_table_names.return_value = ["test_user_column_presets"]
                mock_inspect.return_value = mock_inspector
                
                service = UserPresetsService(engine=mock_engine, table_name="test")
                presets = service.get_presets("user")
                
                assert len(presets) == 2
                assert presets[0]["preset_name"] == "Preset1"
                assert presets[1]["preset_name"] == "Preset2"
                assert presets[1]["is_default"] is True


class TestUserPresetsServiceGetDefaultPresetWithData:
    """Tests for get_default_preset returning data."""
    
    def test_get_default_preset_returns_dict(self):
        """Should return default preset when found."""
        from datetime import datetime
        
        with patch('src.db.user_presets.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.user_presets.inspect') as mock_inspect:
                from src.db.user_presets import UserPresetsService
                
                mock_engine = MagicMock()
                mock_conn = MagicMock()
                
                mock_row = (1, "Default", ["col1", "col2"], True, datetime(2024, 1, 1), datetime(2024, 1, 2))
                mock_result = MagicMock()
                mock_result.fetchone.return_value = mock_row
                mock_conn.execute.return_value = mock_result
                mock_conn.__enter__ = MagicMock(return_value=mock_conn)
                mock_conn.__exit__ = MagicMock(return_value=False)
                mock_engine.connect.return_value = mock_conn
                
                mock_inspector = MagicMock()
                mock_inspector.get_table_names.return_value = ["test_user_column_presets"]
                mock_inspect.return_value = mock_inspector
                
                service = UserPresetsService(engine=mock_engine, table_name="test")
                result = service.get_default_preset("user")
                
                assert result is not None
                assert result["preset_name"] == "Default"


class TestStandaloneFunctionsWithEngine:
    """Tests for standalone functions that take engine parameter."""
    
    def test_create_user_preset_table(self):
        """Should create user preset table via service."""
        with patch('src.db.user_presets.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.user_presets.UserPresetsService') as MockService:
                from src.db.user_presets import create_user_preset_table
                
                mock_engine = MagicMock()
                mock_service = MagicMock()
                mock_service._ensure_table_exists.return_value = "test_user1_column_presets"
                MockService.return_value = mock_service
                
                result = create_user_preset_table(mock_engine, "test", "user1")
                
                assert result == "test_user1_column_presets"
    
    def test_save_user_preset(self):
        """Should save preset via service."""
        with patch('src.db.user_presets.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.user_presets.UserPresetsService') as MockService:
                from src.db.user_presets import save_user_preset
                
                mock_engine = MagicMock()
                mock_service = MagicMock()
                mock_service.save_preset.return_value = 42
                MockService.return_value = mock_service
                
                result = save_user_preset(mock_engine, "test", "user1", "MyPreset", ["A", "B"])
                
                assert result == 42
                mock_service.save_preset.assert_called_with("user1", "MyPreset", ["A", "B"], False)
    
    def test_load_user_presets(self):
        """Should load presets via service."""
        with patch('src.db.user_presets.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.user_presets.UserPresetsService') as MockService:
                from src.db.user_presets import load_user_presets
                
                mock_engine = MagicMock()
                mock_service = MagicMock()
                mock_service.get_presets.return_value = [{"preset_name": "Default"}]
                MockService.return_value = mock_service
                
                result = load_user_presets(mock_engine, "test", "user1")
                
                assert len(result) == 1
    
    def test_get_default_preset_standalone(self):
        """Should get default preset via service."""
        with patch('src.db.user_presets.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.user_presets.UserPresetsService') as MockService:
                from src.db.user_presets import get_default_preset
                
                mock_engine = MagicMock()
                mock_service = MagicMock()
                mock_service.get_default_preset.return_value = {"preset_name": "MyDefault"}
                MockService.return_value = mock_service
                
                result = get_default_preset(mock_engine, "test", "user1")
                
                assert result["preset_name"] == "MyDefault"
    
    def test_delete_user_preset(self):
        """Should delete preset via service."""
        with patch('src.db.user_presets.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.user_presets.UserPresetsService') as MockService:
                from src.db.user_presets import delete_user_preset
                
                mock_engine = MagicMock()
                mock_service = MagicMock()
                mock_service.delete_preset.return_value = True
                MockService.return_value = mock_service
                
                result = delete_user_preset(mock_engine, "test", "user1", "OldPreset")
                
                assert result is True


class TestUserPresetsServiceSetDefaultSuccess:
    """Tests for set_default returning success."""
    
    def test_set_default_not_found(self):
        """Should return False if preset not found."""
        with patch('src.db.user_presets.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.user_presets.inspect') as mock_inspect:
                from src.db.user_presets import UserPresetsService
                
                mock_engine = MagicMock()
                mock_conn = MagicMock()
                mock_result = MagicMock()
                mock_result.rowcount = 0  # Not found
                mock_conn.execute.return_value = mock_result
                mock_conn.__enter__ = MagicMock(return_value=mock_conn)
                mock_conn.__exit__ = MagicMock(return_value=False)
                mock_engine.connect.return_value = mock_conn
                
                mock_inspector = MagicMock()
                mock_inspector.get_table_names.return_value = ["test_user_column_presets"]
                mock_inspect.return_value = mock_inspector
                
                service = UserPresetsService(engine=mock_engine, table_name="test")
                result = service.set_default("user", "NonExistent")
                
                assert result is False


class TestUserPresetsServiceSavePresetWithDefault:
    """Tests for save_preset with is_default=True."""
    
    def test_save_preset_clears_existing_default(self):
        """Saving as default should clear existing default."""
        with patch('src.db.user_presets.SQLALCHEMY_AVAILABLE', True):
            from src.db.user_presets import UserPresetsService
            
            mock_engine = MagicMock()
            mock_conn = MagicMock()
            mock_result = MagicMock()
            mock_result.scalar.return_value = 1
            mock_conn.execute.return_value = mock_result
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_engine.connect.return_value = mock_conn
            
            service = UserPresetsService(engine=mock_engine, table_name="test")
            service._ensure_table_exists = MagicMock(return_value="test_user_column_presets")
            
            result = service.save_preset("user", "NewDefault", ["A", "B"], is_default=True)
            
            # Should have called execute at least twice (clear default + insert)
            assert mock_conn.execute.call_count >= 2
            assert result == 1


class TestUserPresetsServiceGetPresetsNullDatetime:
    """Tests for get_presets handling null datetimes."""
    
    def test_get_presets_null_created_at(self):
        """Should handle null created_at field."""
        with patch('src.db.user_presets.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.user_presets.inspect') as mock_inspect:
                from src.db.user_presets import UserPresetsService
                
                mock_engine = MagicMock()
                mock_conn = MagicMock()
                
                # Row with None for timestamps
                mock_rows = [
                    (1, "Preset1", ["col1"], False, None, None),
                ]
                mock_result = MagicMock()
                mock_result.__iter__ = MagicMock(return_value=iter(mock_rows))
                mock_conn.execute.return_value = mock_result
                mock_conn.__enter__ = MagicMock(return_value=mock_conn)
                mock_conn.__exit__ = MagicMock(return_value=False)
                mock_engine.connect.return_value = mock_conn
                
                mock_inspector = MagicMock()
                mock_inspector.get_table_names.return_value = ["test_user_column_presets"]
                mock_inspect.return_value = mock_inspector
                
                service = UserPresetsService(engine=mock_engine, table_name="test")
                presets = service.get_presets("user")
                
                assert len(presets) == 1
                assert presets[0]["created_at"] is None
                assert presets[0]["updated_at"] is None