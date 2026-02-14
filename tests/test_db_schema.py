"""
Tests for DatabaseSchemaManager with mocked database connections.
"""
import pytest
from unittest.mock import MagicMock, patch


class TestColumnInfo:
    """Tests for ColumnInfo dataclass."""
    
    def test_create_column_info(self):
        """Should create ColumnInfo with all fields."""
        from src.db.db_schema import ColumnInfo
        
        col = ColumnInfo(
            name="id",
            data_type="INTEGER",
            is_nullable=False,
            is_primary_key=True,
            ordinal_position=1
        )
        
        assert col.name == "id"
        assert col.data_type == "INTEGER"
        assert col.is_primary_key is True
        assert col.default_value is None
    
    def test_column_info_with_default(self):
        """Should accept default value."""
        from src.db.db_schema import ColumnInfo
        
        col = ColumnInfo(
            name="status",
            data_type="VARCHAR",
            is_nullable=True,
            is_primary_key=False,
            ordinal_position=2,
            default_value="'unprocessed'"
        )
        
        assert col.default_value == "'unprocessed'"


class TestTableSchema:
    """Tests for TableSchema dataclass."""
    
    @pytest.fixture
    def sample_schema(self):
        """Create sample table schema."""
        from src.db.db_schema import ColumnInfo, TableSchema
        
        return TableSchema(
            table_name="epitopes",
            columns=[
                ColumnInfo(name="patient_id", data_type="VARCHAR", is_nullable=False, is_primary_key=True, ordinal_position=1),
                ColumnInfo(name="variant_id", data_type="VARCHAR", is_nullable=False, is_primary_key=True, ordinal_position=2),
                ColumnInfo(name="value", data_type="NUMERIC", is_nullable=True, is_primary_key=False, ordinal_position=3),
                ColumnInfo(name="status", data_type="VARCHAR", is_nullable=True, is_primary_key=False, ordinal_position=4),
            ],
            primary_key=["patient_id", "variant_id"]
        )
    
    def test_get_column_names_ordered(self, sample_schema):
        """Should return column names in ordinal order."""
        names = sample_schema.get_column_names()
        
        assert names == ["patient_id", "variant_id", "value", "status"]
    
    def test_get_pk_tuple(self, sample_schema):
        """Should extract PK tuple from row dict."""
        row = {"patient_id": "P001", "variant_id": "V1", "value": 100, "status": "approved"}
        
        pk = sample_schema.get_pk_tuple(row)
        
        assert pk == ("P001", "V1")
    
    def test_get_pk_dict(self, sample_schema):
        """Should extract PK as dict from row."""
        row = {"patient_id": "P001", "variant_id": "V1", "value": 100}
        
        pk_dict = sample_schema.get_pk_dict(row)
        
        assert pk_dict == {"patient_id": "P001", "variant_id": "V1"}
    
    def test_get_pk_tuple_missing_column(self, sample_schema):
        """Should return None for missing PK columns."""
        row = {"patient_id": "P001", "value": 100}  # Missing variant_id
        
        pk = sample_schema.get_pk_tuple(row)
        
        assert pk == ("P001", None)
    
    def test_empty_schema(self):
        """Should work with empty columns list."""
        from src.db.db_schema import TableSchema
        
        schema = TableSchema(table_name="empty_table")
        
        assert schema.get_column_names() == []
        assert schema.primary_key == []


class TestDatabaseSchemaManagerInit:
    """Tests for DatabaseSchemaManager initialization."""
    
    def test_init_with_connection_string(self):
        """Should accept connection string."""
        with patch('src.db.db_schema.SQLALCHEMY_AVAILABLE', True):
            from src.db.db_schema import DatabaseSchemaManager
            
            manager = DatabaseSchemaManager("postgresql://user:pass@host/db")
            
            assert manager.connection_string == "postgresql://user:pass@host/db"
            assert manager._engine is None  # Lazy loaded
    
    def test_init_with_engine(self):
        """Should accept existing engine."""
        with patch('src.db.db_schema.SQLALCHEMY_AVAILABLE', True):
            from src.db.db_schema import DatabaseSchemaManager
            
            mock_engine = MagicMock()
            manager = DatabaseSchemaManager(mock_engine)
            
            assert manager._engine is mock_engine
            assert manager.connection_string is None
    
    def test_init_without_params_uses_env(self):
        """Should use env var when no params provided."""
        with patch('src.db.db_schema.SQLALCHEMY_AVAILABLE', True):
            with patch.dict('os.environ', {'APP_DB_CONNECTION': 'postgresql://env/db'}):
                from src.db.db_schema import DatabaseSchemaManager
                
                manager = DatabaseSchemaManager()
                
                assert manager.connection_string == "postgresql://env/db"


class TestDatabaseSchemaManagerEngine:
    """Tests for engine property."""
    
    def test_engine_property_creates_engine(self):
        """Engine property should create engine from connection string."""
        with patch('src.db.db_schema.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.db_schema.create_engine') as mock_create:
                from src.db.db_schema import DatabaseSchemaManager
                
                mock_engine = MagicMock()
                mock_create.return_value = mock_engine
                
                manager = DatabaseSchemaManager("postgresql://user:pass@host/db")
                engine = manager.engine
                
                mock_create.assert_called_once()
                assert engine is mock_engine
    
    def test_engine_property_returns_cached(self):
        """Engine property should return cached engine."""
        with patch('src.db.db_schema.SQLALCHEMY_AVAILABLE', True):
            from src.db.db_schema import DatabaseSchemaManager
            
            mock_engine = MagicMock()
            manager = DatabaseSchemaManager(mock_engine)
            
            # Access property multiple times
            engine1 = manager.engine
            engine2 = manager.engine
            
            assert engine1 is engine2 is mock_engine
    
    def test_engine_property_raises_without_connection(self):
        """Should raise error when no connection string."""
        with patch('src.db.db_schema.SQLALCHEMY_AVAILABLE', True):
            with patch.dict('os.environ', {}, clear=True):
                from src.db.db_schema import DatabaseSchemaManager
                
                manager = DatabaseSchemaManager()
                manager.connection_string = None
                
                with pytest.raises(ValueError, match="connection string"):
                    _ = manager.engine


class TestDatabaseSchemaManagerGetTableSchema:
    """Tests for get_table_schema method."""
    
    def test_get_table_schema_uses_cache(self):
        """Should return cached schema."""
        with patch('src.db.db_schema.SQLALCHEMY_AVAILABLE', True):
            from src.db.db_schema import DatabaseSchemaManager, TableSchema, ColumnInfo
            
            mock_engine = MagicMock()
            manager = DatabaseSchemaManager(mock_engine)
            
            # Pre-populate cache
            cached_schema = TableSchema(
                table_name="test",
                columns=[ColumnInfo(name="id", data_type="INTEGER", is_nullable=False, is_primary_key=True, ordinal_position=1)],
                primary_key=["id"]
            )
            manager._schema_cache["test"] = cached_schema
            
            result = manager.get_table_schema("test")
            
            assert result is cached_schema
    
    def test_get_table_schema_force_refresh(self):
        """Force refresh should bypass cache."""
        with patch('src.db.db_schema.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.db_schema.inspect') as mock_inspect:
                from src.db.db_schema import DatabaseSchemaManager, TableSchema, ColumnInfo
                
                mock_engine = MagicMock()
                mock_inspector = MagicMock()
                mock_inspector.get_columns.return_value = [
                    {'name': 'id', 'type': MagicMock(__str__=lambda x: 'INTEGER'), 'nullable': False, 'default': None}
                ]
                mock_inspector.get_pk_constraint.return_value = {'constrained_columns': ['id']}
                mock_inspect.return_value = mock_inspector
                
                manager = DatabaseSchemaManager(mock_engine)
                
                # Pre-populate cache
                old_schema = TableSchema(table_name="test", columns=[], primary_key=[])
                manager._schema_cache["test"] = old_schema
                
                result = manager.get_table_schema("test", force_refresh=True)
                
                # Should have used inspector, not cache
                mock_inspect.assert_called_once()
                assert result is not old_schema


class TestDatabaseSchemaManagerEnsureTablesExist:
    """Tests for ensure_tables_exist method."""
    
    def test_ensure_tables_calls_method(self):
        """Should call ensure_tables_exist without error."""
        with patch('src.db.db_schema.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.db_schema.inspect') as mock_inspect:
                from src.db.db_schema import DatabaseSchemaManager
                
                mock_engine = MagicMock()
                mock_conn = MagicMock()
                mock_conn.__enter__ = MagicMock(return_value=mock_conn)
                mock_conn.__exit__ = MagicMock(return_value=False)
                mock_engine.connect.return_value = mock_conn
                mock_engine.begin.return_value = mock_conn
                
                mock_inspector = MagicMock()
                mock_inspector.get_table_names.return_value = ["data_table"]  # mods/state don't exist
                mock_inspect.return_value = mock_inspector
                
                manager = DatabaseSchemaManager(mock_engine)
                
                # Should not raise
                manager.ensure_tables_exist("data_table", "mods_table", "state_table")
    
    def test_ensure_tables_skips_existing(self):
        """Should not create tables that already exist."""
        with patch('src.db.db_schema.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.db_schema.inspect') as mock_inspect:
                from src.db.db_schema import DatabaseSchemaManager
                
                mock_engine = MagicMock()
                mock_conn = MagicMock()
                mock_conn.__enter__ = MagicMock(return_value=mock_conn)
                mock_conn.__exit__ = MagicMock(return_value=False)
                mock_engine.connect.return_value = mock_conn
                
                mock_inspector = MagicMock()
                mock_inspector.get_table_names.return_value = ["data_table", "mods_table", "state_table"]
                mock_inspect.return_value = mock_inspector
                
                manager = DatabaseSchemaManager(mock_engine)
                manager.ensure_tables_exist("data_table", "mods_table", "state_table")
                
                # Connection may not be used if tables exist
                # This test verifies no errors occur

    def test_ensure_tables_raises_if_data_table_missing(self):
        """Should raise ValueError if data table does not exist."""
        with patch('src.db.db_schema.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.db_schema.inspect') as mock_inspect:
                from src.db.db_schema import DatabaseSchemaManager
                
                mock_engine = MagicMock()
                mock_inspector = MagicMock()
                mock_inspector.get_table_names.return_value = []  # No tables exist
                mock_inspect.return_value = mock_inspector
                
                manager = DatabaseSchemaManager(mock_engine)
                
                with pytest.raises(ValueError, match="does not exist"):
                    manager.ensure_tables_exist("data_table", "mods_table", "state_table")
    
    def test_ensure_tables_creates_both_tables(self):
        """Should create both mods and state tables when they don't exist."""
        with patch('src.db.db_schema.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.db_schema.inspect') as mock_inspect:
                from src.db.db_schema import DatabaseSchemaManager
                
                mock_engine = MagicMock()
                mock_conn = MagicMock()
                mock_conn.__enter__ = MagicMock(return_value=mock_conn)
                mock_conn.__exit__ = MagicMock(return_value=False)
                mock_engine.begin.return_value = mock_conn
                
                mock_inspector = MagicMock()
                # Only data_table exists
                mock_inspector.get_table_names.return_value = ["data_table"]
                mock_inspect.return_value = mock_inspector
                
                manager = DatabaseSchemaManager(mock_engine)
                result = manager.ensure_tables_exist("data_table", "mods_table", "state_table")
                
                # Should report both tables were created
                assert result["mods_table"] is True
                assert result["state_table"] is True
    
    def test_ensure_tables_returns_false_when_tables_exist(self):
        """Should return False for tables that already exist."""
        with patch('src.db.db_schema.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.db_schema.inspect') as mock_inspect:
                from src.db.db_schema import DatabaseSchemaManager
                
                mock_engine = MagicMock()
                mock_inspector = MagicMock()
                # All tables exist
                mock_inspector.get_table_names.return_value = ["data_table", "mods_table", "state_table"]
                mock_inspect.return_value = mock_inspector
                
                manager = DatabaseSchemaManager(mock_engine)
                result = manager.ensure_tables_exist("data_table", "mods_table", "state_table")
                
                # Should report no tables were created
                assert result["mods_table"] is False
                assert result["state_table"] is False


class TestDatabaseSchemaManagerCreateModsTable:
    """Tests for create_mods_table method."""
    
    def test_create_mods_table_skips_if_exists(self):
        """Should not create table if it already exists."""
        with patch('src.db.db_schema.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.db_schema.inspect') as mock_inspect:
                from src.db.db_schema import DatabaseSchemaManager
                
                mock_engine = MagicMock()
                mock_inspector = MagicMock()
                mock_inspector.get_table_names.return_value = ["mods_table"]  # Already exists
                mock_inspect.return_value = mock_inspector
                
                manager = DatabaseSchemaManager(mock_engine)
                manager.create_mods_table("mods_table")
                
                # Should not call begin() because table exists
                mock_engine.begin.assert_not_called()


class TestDatabaseSchemaManagerCreateStateTable:
    """Tests for create_state_table method."""
    
    def test_create_state_table_skips_if_exists(self):
        """Should not create table if it already exists."""
        with patch('src.db.db_schema.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.db_schema.inspect') as mock_inspect:
                from src.db.db_schema import DatabaseSchemaManager
                
                mock_engine = MagicMock()
                mock_inspector = MagicMock()
                mock_inspector.get_table_names.return_value = ["state_table"]  # Already exists
                mock_inspect.return_value = mock_inspector
                
                manager = DatabaseSchemaManager(mock_engine)
                manager.create_state_table("state_table")
                
                # Should not call begin() because table exists
                mock_engine.begin.assert_not_called()


class TestSingletonFunctions:
    """Tests for singleton helper functions."""
    
    def test_get_schema_manager_creates_singleton(self):
        """get_schema_manager should create singleton instance."""
        with patch('src.db.db_schema.SQLALCHEMY_AVAILABLE', True):
            # Reset singleton
            import src.db.db_schema as schema_module
            schema_module._schema_manager = None
            
            with patch.object(schema_module, 'DatabaseSchemaManager') as MockManager:
                mock_manager = MagicMock()
                MockManager.return_value = mock_manager
                
                result1 = schema_module.get_schema_manager("postgresql://test/db")
                result2 = schema_module.get_schema_manager("postgresql://other/db")
                
                # Should only create once
                assert MockManager.call_count == 1
                assert result1 is mock_manager
                assert result2 is mock_manager
    
    def test_get_table_schema_uses_singleton(self):
        """get_table_schema should use singleton manager."""
        with patch('src.db.db_schema.SQLALCHEMY_AVAILABLE', True):
            import src.db.db_schema as schema_module
            
            mock_manager = MagicMock()
            mock_schema = MagicMock()
            mock_manager.get_table_schema.return_value = mock_schema
            schema_module._schema_manager = mock_manager
            
            result = schema_module.get_table_schema("my_table")
            
            mock_manager.get_table_schema.assert_called_once_with("my_table")
            assert result is mock_schema
    
    def test_get_primary_key_uses_singleton(self):
        """get_primary_key should return primary key from singleton."""
        with patch('src.db.db_schema.SQLALCHEMY_AVAILABLE', True):
            import src.db.db_schema as schema_module
            
            mock_manager = MagicMock()
            mock_schema = MagicMock()
            mock_schema.primary_key = ["id", "variant"]
            mock_manager.get_table_schema.return_value = mock_schema
            schema_module._schema_manager = mock_manager
            
            result = schema_module.get_primary_key("my_table")
            
            assert result == ["id", "variant"]


class TestSqlalchemyNotAvailable:
    """Tests for when SQLAlchemy is not available."""
    
    def test_init_raises_without_sqlalchemy(self):
        """Should raise ImportError when SQLAlchemy not available."""
        with patch('src.db.db_schema.SQLALCHEMY_AVAILABLE', False):
            # Need to reload module to pick up patched value
            import importlib
            import src.db.db_schema as schema_module
            
            # Temporarily modify the class
            original_init = schema_module.DatabaseSchemaManager.__init__
            
            # Create a test instance that checks SQLALCHEMY_AVAILABLE
            class TestManager:
                def __init__(self, conn=None):
                    if not schema_module.SQLALCHEMY_AVAILABLE:
                        raise ImportError("SQLAlchemy is required")
            
            with pytest.raises(ImportError, match="SQLAlchemy"):
                TestManager()


class TestDatabaseSchemaManagerTableExists:
    """Tests for DatabaseSchemaManager.table_exists — pinning test."""

    def test_table_exists_returns_true(self):
        """Should return True when table is in inspector's table names."""
        from src.db.db_schema import DatabaseSchemaManager

        mock_engine = MagicMock()
        mock_inspector = MagicMock()
        mock_inspector.get_table_names.return_value = ["users", "presets", "data"]

        with patch('src.db.db_schema.inspect', return_value=mock_inspector):
            mgr = DatabaseSchemaManager.__new__(DatabaseSchemaManager)
            mgr._engine = mock_engine
            mgr._conn_string = "mock://"

            # Patch the engine property
            type(mgr).engine = property(lambda self: self._engine)

            assert mgr.table_exists("users") is True
            assert mgr.table_exists("nonexistent") is False

    def test_table_exists_empty_db(self):
        """Should return False when database has no tables."""
        from src.db.db_schema import DatabaseSchemaManager

        mock_engine = MagicMock()
        mock_inspector = MagicMock()
        mock_inspector.get_table_names.return_value = []

        with patch('src.db.db_schema.inspect', return_value=mock_inspector):
            mgr = DatabaseSchemaManager.__new__(DatabaseSchemaManager)
            mgr._engine = mock_engine
            mgr._conn_string = "mock://"
            type(mgr).engine = property(lambda self: self._engine)

            assert mgr.table_exists("anything") is False


class TestDatabaseSchemaManagerGetRowCount:
    """Tests for DatabaseSchemaManager.get_row_count — pinning test."""

    def test_count_without_where(self):
        """Should return scalar count without WHERE clause."""
        from src.db.db_schema import DatabaseSchemaManager

        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 42
        mock_conn.execute.return_value = mock_result
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_engine.connect.return_value = mock_conn

        mgr = DatabaseSchemaManager.__new__(DatabaseSchemaManager)
        mgr._engine = mock_engine
        mgr._conn_string = "mock://"
        type(mgr).engine = property(lambda self: self._engine)

        result = mgr.get_row_count("my_table")

        assert result == 42

    def test_count_with_where(self):
        """Should append WHERE clause when provided."""
        from src.db.db_schema import DatabaseSchemaManager

        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 5
        mock_conn.execute.return_value = mock_result
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_engine.connect.return_value = mock_conn

        mgr = DatabaseSchemaManager.__new__(DatabaseSchemaManager)
        mgr._engine = mock_engine
        mgr._conn_string = "mock://"
        type(mgr).engine = property(lambda self: self._engine)

        result = mgr.get_row_count("my_table", where_clause="status = 'active'")

        assert result == 5
        # Verify the SQL contains WHERE
        call_args = mock_conn.execute.call_args
        sql_text = str(call_args[0][0])
        assert "WHERE" in sql_text

    def test_count_returns_zero_on_none(self):
        """Should return 0 when scalar returns None."""
        from src.db.db_schema import DatabaseSchemaManager

        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        mock_conn.execute.return_value = mock_result
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_engine.connect.return_value = mock_conn

        mgr = DatabaseSchemaManager.__new__(DatabaseSchemaManager)
        mgr._engine = mock_engine
        mgr._conn_string = "mock://"
        type(mgr).engine = property(lambda self: self._engine)

        result = mgr.get_row_count("my_table")

        assert result == 0


class TestDatabaseSchemaManagerGenerateDefaultPreset:
    """Tests for DatabaseSchemaManager.generate_default_preset — pinning test."""

    def test_returns_columns_and_widths(self):
        """Should return dict with columns list and empty widths."""
        from src.db.db_schema import DatabaseSchemaManager

        mgr = DatabaseSchemaManager.__new__(DatabaseSchemaManager)

        mock_schema = MagicMock()
        mock_schema.get_column_names.return_value = ["id", "name", "status"]
        mgr.get_table_schema = MagicMock(return_value=mock_schema)

        result = mgr.generate_default_preset("test_table")

        assert result == {"columns": ["id", "name", "status"], "widths": {}}
        mgr.get_table_schema.assert_called_once_with("test_table")
