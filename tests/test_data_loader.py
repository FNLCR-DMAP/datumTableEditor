"""
Tests for DataLoader with mocked data sources.
"""
import pytest
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path
import pandas as pd
import json


class TestDataLoaderInit:
    """Tests for DataLoader initialization."""
    
    def test_init_with_config(self):
        """Should accept config object."""
        from src.data.data_loader import DataLoader
        
        mock_config = MagicMock()
        mock_config.data_source.source_type = "csv"
        
        loader = DataLoader(config=mock_config)
        
        assert loader.config is mock_config
        assert loader._df is None
    
    def test_init_without_config_loads_default(self):
        """Should load default config when none provided."""
        with patch('src.data.data_loader.load_config') as mock_load:
            from src.data.data_loader import DataLoader
            
            mock_config = MagicMock()
            mock_config.data_source.source_type = "csv"
            mock_load.return_value = mock_config
            
            loader = DataLoader()
            
            mock_load.assert_called_once()


class TestDataLoaderLoadCSV:
    """Tests for CSV loading."""
    
    def test_load_csv_success(self):
        """Should load CSV file successfully."""
        with patch('src.data.data_loader.load_config') as mock_load:
            with patch('pandas.read_csv') as mock_read_csv:
                with patch.object(Path, 'exists', return_value=True):
                    from src.data.data_loader import DataLoader
                    
                    mock_config = MagicMock()
                    mock_config.data_source.source_type = "csv"
                    mock_config.data_source.file_path = "data/test.csv"
                    mock_config.data_source.date_columns = []
                    mock_config.data_source.numeric_columns = []
                    mock_load.return_value = mock_config
                    
                    mock_df = pd.DataFrame({'a': [1, 2], 'b': [3, 4]})
                    mock_read_csv.return_value = mock_df
                    
                    loader = DataLoader()
                    result = loader.load()
                    
                    assert len(result) == 2
    
    def test_load_csv_file_not_found(self):
        """Should raise error when CSV file doesn't exist."""
        with patch('src.data.data_loader.load_config') as mock_load:
            with patch.object(Path, 'exists', return_value=False):
                from src.data.data_loader import DataLoader
                
                mock_config = MagicMock()
                mock_config.data_source.source_type = "csv"
                mock_config.data_source.file_path = "nonexistent.csv"
                mock_load.return_value = mock_config
                
                loader = DataLoader()
                
                with pytest.raises(FileNotFoundError):
                    loader.load()


class TestDataLoaderLoadJSON:
    """Tests for JSON loading."""
    
    def test_load_json_success(self):
        """Should load JSON file successfully."""
        with patch('src.data.data_loader.load_config') as mock_load:
            with patch('pandas.read_json') as mock_read_json:
                with patch.object(Path, 'exists', return_value=True):
                    from src.data.data_loader import DataLoader
                    
                    mock_config = MagicMock()
                    mock_config.data_source.source_type = "json"
                    mock_config.data_source.file_path = "data/test.json"
                    mock_config.data_source.date_columns = []
                    mock_config.data_source.numeric_columns = []
                    mock_load.return_value = mock_config
                    
                    mock_df = pd.DataFrame({'x': [1, 2]})
                    mock_read_json.return_value = mock_df
                    
                    loader = DataLoader()
                    result = loader.load()
                    
                    assert len(result) == 2


class TestDataLoaderLoadAPI:
    """Tests for API loading."""
    
    def test_load_api_success(self):
        """Should load from API successfully."""
        with patch('src.data.data_loader.load_config') as mock_load:
            with patch('requests.request') as mock_request:
                from src.data.data_loader import DataLoader
                
                mock_config = MagicMock()
                mock_config.data_source.source_type = "api"
                mock_config.data_source.api_url = "https://api.example.com/data"
                mock_config.data_source.api_method = "GET"
                mock_config.data_source.api_headers = {}
                mock_config.data_source.date_columns = []
                mock_config.data_source.numeric_columns = []
                mock_load.return_value = mock_config
                
                mock_response = MagicMock()
                mock_response.json.return_value = [{"id": 1}, {"id": 2}]
                mock_request.return_value = mock_response
                
                loader = DataLoader()
                result = loader.load()
                
                assert len(result) == 2
    
    def test_load_api_with_nested_data(self):
        """Should handle nested API response with 'data' key."""
        with patch('src.data.data_loader.load_config') as mock_load:
            with patch('requests.request') as mock_request:
                from src.data.data_loader import DataLoader
                
                mock_config = MagicMock()
                mock_config.data_source.source_type = "api"
                mock_config.data_source.api_url = "https://api.example.com/data"
                mock_config.data_source.api_method = "GET"
                mock_config.data_source.api_headers = {"Authorization": "Bearer token"}
                mock_config.data_source.date_columns = []
                mock_config.data_source.numeric_columns = []
                mock_load.return_value = mock_config
                
                mock_response = MagicMock()
                mock_response.json.return_value = {
                    "data": [{"id": 1}, {"id": 2}, {"id": 3}],
                    "meta": {"total": 3}
                }
                mock_request.return_value = mock_response
                
                loader = DataLoader()
                result = loader.load()
                
                assert len(result) == 3


class TestDataLoaderLoadDatabase:
    """Tests for database loading."""
    
    def test_load_database_with_table(self):
        """Should load from database table."""
        with patch('src.data.data_loader.load_config') as mock_load:
            with patch('sqlalchemy.create_engine') as mock_create_engine:
                with patch('pandas.read_sql') as mock_read_sql:
                    from src.data.data_loader import DataLoader
                    
                    mock_config = MagicMock()
                    mock_config.data_source.source_type = "database"
                    mock_config.data_source.db_connection_string = "postgresql://user:pass@host/db"
                    mock_config.data_source.db_query = None
                    mock_config.data_source.db_table = "epitopes"
                    mock_config.data_source.date_columns = []
                    mock_config.data_source.numeric_columns = []
                    mock_load.return_value = mock_config
                    
                    mock_df = pd.DataFrame({'id': [1, 2]})
                    mock_read_sql.return_value = mock_df
                    
                    loader = DataLoader()
                    result = loader.load()
                    
                    assert len(result) == 2
                    mock_read_sql.assert_called()
    
    def test_load_database_with_query(self):
        """Should execute custom query."""
        with patch('src.data.data_loader.load_config') as mock_load:
            with patch('sqlalchemy.create_engine') as mock_create_engine:
                with patch('pandas.read_sql') as mock_read_sql:
                    from src.data.data_loader import DataLoader
                    
                    mock_config = MagicMock()
                    mock_config.data_source.source_type = "database"
                    mock_config.data_source.db_connection_string = "postgresql://user:pass@host/db"
                    mock_config.data_source.db_query = "SELECT * FROM epitopes WHERE status = 'approved'"
                    mock_config.data_source.db_table = None
                    mock_config.data_source.date_columns = []
                    mock_config.data_source.numeric_columns = []
                    mock_load.return_value = mock_config
                    
                    mock_df = pd.DataFrame({'id': [1]})
                    mock_read_sql.return_value = mock_df
                    
                    loader = DataLoader()
                    result = loader.load()
                    
                    # Verify custom query was used
                    call_args = mock_read_sql.call_args
                    assert "approved" in str(call_args)
    
    def test_load_database_no_table_or_query_raises(self):
        """Should raise error when neither table nor query specified."""
        with patch('src.data.data_loader.load_config') as mock_load:
            with patch('sqlalchemy.create_engine') as mock_create_engine:
                from src.data.data_loader import DataLoader
                
                mock_config = MagicMock()
                mock_config.data_source.source_type = "database"
                mock_config.data_source.db_connection_string = "postgresql://user:pass@host/db"
                mock_config.data_source.db_query = None
                mock_config.data_source.db_table = None
                mock_load.return_value = mock_config
                
                loader = DataLoader()
                
                with pytest.raises(ValueError, match="db_query or db_table"):
                    loader.load()


class TestDataLoaderTypeConversions:
    """Tests for type conversion application."""
    
    def test_convert_date_columns(self):
        """Should convert date columns to datetime."""
        with patch('src.data.data_loader.load_config') as mock_load:
            with patch('pandas.read_csv') as mock_read_csv:
                with patch.object(Path, 'exists', return_value=True):
                    from src.data.data_loader import DataLoader
                    
                    mock_config = MagicMock()
                    mock_config.data_source.source_type = "csv"
                    mock_config.data_source.file_path = "data/test.csv"
                    mock_config.data_source.date_columns = ["created_at"]
                    mock_config.data_source.numeric_columns = []
                    mock_load.return_value = mock_config
                    
                    mock_df = pd.DataFrame({
                        'id': [1, 2],
                        'created_at': ['2024-01-01', '2024-01-02']
                    })
                    mock_read_csv.return_value = mock_df
                    
                    loader = DataLoader()
                    result = loader.load()
                    
                    assert pd.api.types.is_datetime64_any_dtype(result['created_at'])
    
    def test_convert_numeric_columns(self):
        """Should convert numeric columns."""
        with patch('src.data.data_loader.load_config') as mock_load:
            with patch('pandas.read_csv') as mock_read_csv:
                with patch.object(Path, 'exists', return_value=True):
                    from src.data.data_loader import DataLoader
                    
                    mock_config = MagicMock()
                    mock_config.data_source.source_type = "csv"
                    mock_config.data_source.file_path = "data/test.csv"
                    mock_config.data_source.date_columns = []
                    mock_config.data_source.numeric_columns = ["value"]
                    mock_load.return_value = mock_config
                    
                    mock_df = pd.DataFrame({
                        'id': [1, 2],
                        'value': ['100', '200']
                    })
                    mock_read_csv.return_value = mock_df
                    
                    loader = DataLoader()
                    result = loader.load()
                    
                    assert pd.api.types.is_numeric_dtype(result['value'])


class TestDataLoaderUnknownSourceType:
    """Tests for unknown source type handling."""
    
    def test_unknown_source_type_raises(self):
        """Should raise error for unknown source type."""
        with patch('src.data.data_loader.load_config') as mock_load:
            from src.data.data_loader import DataLoader
            
            mock_config = MagicMock()
            mock_config.data_source.source_type = "unknown_type"
            mock_load.return_value = mock_config
            
            loader = DataLoader()
            
            with pytest.raises(ValueError, match="Unknown source type"):
                loader.load()


class TestDataLoaderEnvVarResolution:
    """Tests for environment variable resolution."""
    
    def test_resolve_env_vars_in_api_url(self):
        """Should resolve environment variables in API URL."""
        with patch('src.data.data_loader.load_config') as mock_load:
            with patch('requests.request') as mock_request:
                with patch.dict('os.environ', {'API_BASE_URL': 'https://api.example.com'}):
                    from src.data.data_loader import DataLoader
                    
                    mock_config = MagicMock()
                    mock_config.data_source.source_type = "api"
                    mock_config.data_source.api_url = "${API_BASE_URL}/data"
                    mock_config.data_source.api_method = "GET"
                    mock_config.data_source.api_headers = {}
                    mock_config.data_source.date_columns = []
                    mock_config.data_source.numeric_columns = []
                    mock_load.return_value = mock_config
                    
                    mock_response = MagicMock()
                    mock_response.json.return_value = []
                    mock_request.return_value = mock_response
                    
                    loader = DataLoader()
                    loader.load()
                    
                    # Verify URL was called with resolved env var
                    call_args = mock_request.call_args
                    assert 'api.example.com' in str(call_args)

class TestDataLoaderDataframeProperty:
    """Tests for dataframe property."""
    
    def test_dataframe_property_none_before_load(self):
        """Property should be None before load is called."""
        with patch('src.data.data_loader.load_config') as mock_load:
            from src.data.data_loader import DataLoader
            
            mock_config = MagicMock()
            mock_config.data_source.source_type = "csv"
            mock_load.return_value = mock_config
            
            loader = DataLoader()
            
            assert loader.dataframe is None
    
    def test_dataframe_property_after_load(self):
        """Property should return df after load."""
        with patch('src.data.data_loader.load_config') as mock_load:
            with patch('pandas.read_csv') as mock_read_csv:
                with patch.object(Path, 'exists', return_value=True):
                    from src.data.data_loader import DataLoader
                    
                    mock_config = MagicMock()
                    mock_config.data_source.source_type = "csv"
                    mock_config.data_source.file_path = "data/test.csv"
                    mock_config.data_source.date_columns = []
                    mock_config.data_source.numeric_columns = []
                    mock_load.return_value = mock_config
                    
                    mock_df = pd.DataFrame({'a': [1, 2]})
                    mock_read_csv.return_value = mock_df
                    
                    loader = DataLoader()
                    loader.load()
                    
                    assert loader.dataframe is not None
                    assert len(loader.dataframe) == 2


class TestDataLoaderResolvePathNone:
    """Tests for _resolve_path with None."""
    
    def test_resolve_path_none_raises(self):
        """Should raise ValueError when path is None."""
        with patch('src.data.data_loader.load_config') as mock_load:
            from src.data.data_loader import DataLoader
            
            mock_config = MagicMock()
            mock_config.data_source.source_type = "csv"
            mock_config.data_source.file_path = None
            mock_load.return_value = mock_config
            
            loader = DataLoader()
            
            with pytest.raises(ValueError, match="not configured"):
                loader._resolve_path(None)


class TestPersistenceManager:
    """Tests for PersistenceManager class."""
    
    def test_init_with_config(self):
        """Should accept config object."""
        with patch('src.data.data_loader.load_config') as mock_load:
            from src.data.data_loader import PersistenceManager
            
            mock_config = MagicMock()
            mock_load.return_value = mock_config
            
            pm = PersistenceManager(config=mock_config)
            
            assert pm.config is mock_config


class TestPersistenceManagerLocalJSON:
    """Tests for local JSON persistence."""
    
    def test_save_modifications_log_local(self):
        """Should save modifications to local JSON."""
        import tempfile
        import os
        
        with patch('src.data.data_loader.load_config') as mock_load:
            from src.data.data_loader import PersistenceManager
            
            mock_config = MagicMock()
            mock_config.persistence.persistence_type = "local"
            mock_load.return_value = mock_config
            
            with tempfile.TemporaryDirectory() as tmpdir:
                log_path = os.path.join(tmpdir, "mods.json")
                mock_config.persistence.modifications_log_path = log_path
                
                pm = PersistenceManager(config=mock_config)
                pm._project_root = Path(tmpdir)
                
                test_log = [{"id": 1, "action": "edit"}]
                pm.save_modifications_log(test_log)
                
                # Verify file was created
                assert Path(log_path).exists()
    
    def test_load_modifications_log_local(self):
        """Should load modifications from local JSON."""
        import tempfile
        import os
        
        with patch('src.data.data_loader.load_config') as mock_load:
            from src.data.data_loader import PersistenceManager
            
            mock_config = MagicMock()
            mock_config.persistence.persistence_type = "local"
            mock_load.return_value = mock_config
            
            with tempfile.TemporaryDirectory() as tmpdir:
                log_path = os.path.join(tmpdir, "mods.json")
                mock_config.persistence.modifications_log_path = log_path
                
                # Create test file
                test_log = [{"id": 1, "action": "edit"}]
                with open(log_path, 'w') as f:
                    json.dump(test_log, f)
                
                pm = PersistenceManager(config=mock_config)
                pm._project_root = Path(tmpdir)
                
                result = pm.load_modifications_log()
                
                assert result == test_log
    
    def test_load_modifications_log_file_not_exists(self):
        """Should return default when file doesn't exist."""
        with patch('src.data.data_loader.load_config') as mock_load:
            from src.data.data_loader import PersistenceManager
            
            mock_config = MagicMock()
            mock_config.persistence.persistence_type = "local"
            mock_config.persistence.modifications_log_path = "nonexistent.json"
            mock_load.return_value = mock_config
            
            pm = PersistenceManager(config=mock_config)
            
            result = pm.load_modifications_log()
            
            assert result == []


class TestPersistenceManagerDataState:
    """Tests for data state persistence."""
    
    def test_save_data_state_local(self):
        """Should save DataFrame to local JSON."""
        import tempfile
        import os
        
        with patch('src.data.data_loader.load_config') as mock_load:
            from src.data.data_loader import PersistenceManager
            
            mock_config = MagicMock()
            mock_config.persistence.persistence_type = "local"
            mock_load.return_value = mock_config
            
            with tempfile.TemporaryDirectory() as tmpdir:
                state_path = os.path.join(tmpdir, "state.json")
                mock_config.persistence.data_state_path = state_path
                
                pm = PersistenceManager(config=mock_config)
                pm._project_root = Path(tmpdir)
                
                test_df = pd.DataFrame({'a': [1, 2], 'b': [3, 4]})
                pm.save_data_state(test_df)
                
                # Verify file was created
                assert Path(state_path).exists()
    
    def test_load_data_state_local(self):
        """Should load DataFrame from local JSON."""
        import tempfile
        import os
        
        with patch('src.data.data_loader.load_config') as mock_load:
            from src.data.data_loader import PersistenceManager
            
            mock_config = MagicMock()
            mock_config.persistence.persistence_type = "local"
            mock_load.return_value = mock_config
            
            with tempfile.TemporaryDirectory() as tmpdir:
                state_path = os.path.join(tmpdir, "state.json")
                mock_config.persistence.data_state_path = state_path
                
                # Create test file
                test_data = [{"a": 1, "b": 3}, {"a": 2, "b": 4}]
                with open(state_path, 'w') as f:
                    json.dump(test_data, f)
                
                pm = PersistenceManager(config=mock_config)
                pm._project_root = Path(tmpdir)
                
                result = pm.load_data_state()
                
                assert result is not None
                assert len(result) == 2
    
    def test_load_data_state_not_exists(self):
        """Should return None when state file doesn't exist."""
        with patch('src.data.data_loader.load_config') as mock_load:
            from src.data.data_loader import PersistenceManager
            
            mock_config = MagicMock()
            mock_config.persistence.persistence_type = "local"
            mock_config.persistence.data_state_path = "nonexistent.json"
            mock_load.return_value = mock_config
            
            pm = PersistenceManager(config=mock_config)
            
            result = pm.load_data_state()
            
            assert result is None


class TestPersistenceManagerAPI:
    """Tests for API persistence."""
    
    def test_save_api(self):
        """Should save data via API."""
        with patch('src.data.data_loader.load_config') as mock_load:
            with patch('requests.post') as mock_post:
                from src.data.data_loader import PersistenceManager
                
                mock_config = MagicMock()
                mock_config.persistence.persistence_type = "api"
                mock_config.persistence.api_save_url = "https://api.example.com/save"
                mock_config.persistence.api_headers = {}
                mock_load.return_value = mock_config
                
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_post.return_value = mock_response
                
                pm = PersistenceManager(config=mock_config)
                test_log = [{"id": 1}]
                pm.save_modifications_log(test_log)
                
                mock_post.assert_called_once()
    
    def test_load_api(self):
        """Should load data via API."""
        with patch('src.data.data_loader.load_config') as mock_load:
            with patch('requests.get') as mock_get:
                from src.data.data_loader import PersistenceManager
                
                mock_config = MagicMock()
                mock_config.persistence.persistence_type = "api"
                mock_config.persistence.api_save_url = "https://api.example.com/save"
                mock_config.persistence.api_headers = {}
                mock_load.return_value = mock_config
                
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = [{"id": 1}]
                mock_get.return_value = mock_response
                
                pm = PersistenceManager(config=mock_config)
                result = pm.load_modifications_log()
                
                assert result == [{"id": 1}]
    
    def test_load_api_404_returns_empty(self):
        """Should return empty list on 404."""
        with patch('src.data.data_loader.load_config') as mock_load:
            with patch('requests.get') as mock_get:
                from src.data.data_loader import PersistenceManager
                
                mock_config = MagicMock()
                mock_config.persistence.persistence_type = "api"
                mock_config.persistence.api_save_url = "https://api.example.com/save"
                mock_config.persistence.api_headers = {}
                mock_load.return_value = mock_config
                
                mock_response = MagicMock()
                mock_response.status_code = 404
                mock_get.return_value = mock_response
                
                pm = PersistenceManager(config=mock_config)
                result = pm.load_modifications_log()
                
                assert result == []


class TestPersistenceManagerDatabase:
    """Tests for database persistence."""
    
    def test_save_database(self):
        """Should save data to database."""
        with patch('src.data.data_loader.load_config') as mock_load:
            with patch('sqlalchemy.create_engine') as mock_create:
                with patch('pandas.DataFrame.to_sql') as mock_to_sql:
                    from src.data.data_loader import PersistenceManager
                    
                    mock_config = MagicMock()
                    mock_config.persistence.persistence_type = "database"
                    mock_config.persistence.db_connection_string = "postgresql://user:pass@host/db"
                    mock_load.return_value = mock_config
                    
                    pm = PersistenceManager(config=mock_config)
                    test_log = [{"id": 1}]
                    pm.save_modifications_log(test_log)
                    
                    mock_to_sql.assert_called_once()
    
    def test_load_database(self):
        """Should load data from database."""
        with patch('src.data.data_loader.load_config') as mock_load:
            with patch('sqlalchemy.create_engine') as mock_create:
                with patch('pandas.read_sql') as mock_read_sql:
                    from src.data.data_loader import PersistenceManager
                    
                    mock_config = MagicMock()
                    mock_config.persistence.persistence_type = "database"
                    mock_config.persistence.db_connection_string = "postgresql://user:pass@host/db"
                    mock_load.return_value = mock_config
                    
                    mock_df = pd.DataFrame({'id': [1, 2]})
                    mock_read_sql.return_value = mock_df
                    
                    pm = PersistenceManager(config=mock_config)
                    result = pm.load_modifications_log()
                    
                    assert len(result) == 2
    
    def test_load_database_error_returns_empty(self):
        """Should return empty list on database error."""
        with patch('src.data.data_loader.load_config') as mock_load:
            with patch('sqlalchemy.create_engine') as mock_create:
                with patch('pandas.read_sql') as mock_read_sql:
                    from src.data.data_loader import PersistenceManager
                    
                    mock_config = MagicMock()
                    mock_config.persistence.persistence_type = "database"
                    mock_config.persistence.db_connection_string = "postgresql://user:pass@host/db"
                    mock_load.return_value = mock_config
                    
                    mock_read_sql.side_effect = Exception("Table not found")
                    
                    pm = PersistenceManager(config=mock_config)
                    result = pm.load_modifications_log()
                    
                    assert result == []


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""
    
    def test_get_data_loader(self):
        """Should return singleton DataLoader."""
        with patch('src.data.data_loader.load_config') as mock_load:
            mock_config = MagicMock()
            mock_config.data_source.source_type = "csv"
            mock_load.return_value = mock_config
            
            # Reset singleton
            import src.data.data_loader as mod
            mod._loader = None
            
            from src.data.data_loader import get_data_loader
            
            loader1 = get_data_loader()
            loader2 = get_data_loader()
            
            assert loader1 is loader2
    
    def test_get_persistence_manager(self):
        """Should return singleton PersistenceManager."""
        with patch('src.data.data_loader.load_config') as mock_load:
            mock_config = MagicMock()
            mock_load.return_value = mock_config
            
            # Reset singleton
            import src.data.data_loader as mod
            mod._persistence = None
            
            from src.data.data_loader import get_persistence_manager
            
            pm1 = get_persistence_manager()
            pm2 = get_persistence_manager()
            
            assert pm1 is pm2


class TestPersistenceManagerResolvePathNone:
    """Tests for _resolve_path with None."""
    
    def test_resolve_path_none_returns_none(self):
        """Should return None when path is None."""
        with patch('src.data.data_loader.load_config') as mock_load:
            from src.data.data_loader import PersistenceManager
            
            mock_config = MagicMock()
            mock_load.return_value = mock_config
            
            pm = PersistenceManager(config=mock_config)
            
            result = pm._resolve_path(None)
            
            assert result is None


class TestPersistenceManagerSaveLocalNonePath:
    """Tests for _save_local_json with None path."""
    
    def test_save_local_none_path_no_op(self):
        """Should do nothing when path is None."""
        with patch('src.data.data_loader.load_config') as mock_load:
            from src.data.data_loader import PersistenceManager
            
            mock_config = MagicMock()
            mock_load.return_value = mock_config
            
            pm = PersistenceManager(config=mock_config)
            
            # Should not raise
            pm._save_local_json({"data": 1}, None)


class TestPersistenceManagerSaveAPIUrlNone:
    """Tests for _save_api with None URL."""
    
    def test_save_api_none_url_no_op(self):
        """Should do nothing when URL is None."""
        with patch('src.data.data_loader.load_config') as mock_load:
            from src.data.data_loader import PersistenceManager
            
            mock_config = MagicMock()
            mock_config.persistence.api_headers = {}
            mock_load.return_value = mock_config
            
            pm = PersistenceManager(config=mock_config)
            
            # Should not raise
            pm._save_api({"data": 1}, None, "endpoint")


class TestPersistenceManagerLoadAPIUrlNone:
    """Tests for _load_api with None URL."""
    
    def test_load_api_none_url_returns_empty(self):
        """Should return empty list when URL is None."""
        with patch('src.data.data_loader.load_config') as mock_load:
            from src.data.data_loader import PersistenceManager
            
            mock_config = MagicMock()
            mock_config.persistence.api_headers = {}
            mock_load.return_value = mock_config
            
            pm = PersistenceManager(config=mock_config)
            
            result = pm._load_api(None, "endpoint")
            
            assert result == []


class TestPersistenceManagerResolveEnvVarsNone:
    """Tests for _resolve_env_vars with None."""
    
    def test_resolve_env_vars_none(self):
        """Should return None for None input."""
        with patch('src.data.data_loader.load_config') as mock_load:
            from src.data.data_loader import PersistenceManager
            
            mock_config = MagicMock()
            mock_load.return_value = mock_config
            
            pm = PersistenceManager(config=mock_config)
            
            result = pm._resolve_env_vars(None)
            
            assert result is None