"""
Tests for DatabaseOperations with mocked database connections.
"""
import pytest
from unittest.mock import MagicMock, patch, call
import json


class TestDatabaseConfig:
    """Tests for DatabaseConfig dataclass."""
    
    def test_create_config(self):
        """Should create config with required fields."""
        from src.db.db_operations import DatabaseConfig
        
        config = DatabaseConfig(
            connection_string="postgresql://user:pass@host/db",
            data_table="test_table"
        )
        
        assert config.connection_string == "postgresql://user:pass@host/db"
        assert config.data_table == "test_table"
    
    def test_config_defaults(self):
        """Should have default values for optional fields."""
        from src.db.db_operations import DatabaseConfig
        
        config = DatabaseConfig(
            connection_string="postgresql://user:pass@host/db",
            data_table="test_table"
        )
        
        assert config.mods_table == "epitopes_modifications"
        assert config.status_column == "Status"
        assert config.pool_size == 5
        assert config.default_rows_per_page == 25


class TestFetchResult:
    """Tests for FetchResult dataclass."""
    
    def test_create_fetch_result(self):
        """Should create FetchResult with all fields."""
        import pandas as pd
        from src.db.db_operations import FetchResult
        
        df = pd.DataFrame({'a': [1, 2]})
        result = FetchResult(
            df=df,
            total_count=100,
            page=1,
            rows_per_page=25,
            has_more=True,
            context_changed=False,
            new_rows_added=2
        )
        
        assert len(result.df) == 2
        assert result.total_count == 100
        assert result.has_more is True


class TestModificationRecord:
    """Tests for ModificationRecord dataclass."""
    
    def test_create_modification_record(self):
        """Should create ModificationRecord."""
        from datetime import datetime
        from src.db.db_operations import ModificationRecord
        
        record = ModificationRecord(
            id=1,
            row_pk={"id": 123},
            column_name="status",
            old_value="pending",
            new_value="approved",
            mod_type="edit",
            created_by="user1",
            created_at=datetime.now()
        )
        
        assert record.id == 1
        assert record.row_pk == {"id": 123}
        assert record.undone is False


class TestDatabaseOperationsInit:
    """Tests for DatabaseOperations initialization."""
    
    def test_init_with_config(self):
        """Should accept DatabaseConfig object."""
        with patch('src.db.db_operations.SQLALCHEMY_AVAILABLE', True):
            from src.db.db_operations import DatabaseOperations, DatabaseConfig
            
            config = DatabaseConfig(
                connection_string="postgresql://user:pass@host/db",
                data_table="test_table"
            )
            
            db_ops = DatabaseOperations(config=config)
            
            assert db_ops.config is config
            assert db_ops._engine is None  # Not initialized until .initialize()


class TestDatabaseOperationsInitialize:
    """Tests for DatabaseOperations.initialize() method."""
    
    @pytest.fixture
    def mock_db_ops(self):
        """Create DatabaseOperations with mocked dependencies."""
        with patch('src.db.db_operations.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.db_operations.create_engine') as mock_create_engine:
                with patch('src.db.db_operations.DatabaseSchemaManager') as mock_schema:
                    with patch('src.db.db_operations.QueryBuilder') as mock_qb:
                        with patch('src.db.db_operations.SessionBookManager') as mock_sbm:
                            from src.db.db_operations import DatabaseOperations, DatabaseConfig
                            
                            # Mock engine
                            mock_engine = MagicMock()
                            mock_create_engine.return_value = mock_engine
                            
                            # Mock schema manager
                            mock_schema_instance = MagicMock()
                            mock_table_schema = MagicMock()
                            mock_table_schema.primary_key = ["id"]
                            mock_schema_instance.get_table_schema.return_value = mock_table_schema
                            mock_schema.return_value = mock_schema_instance
                            
                            config = DatabaseConfig(
                                connection_string="postgresql://user:pass@host/db",
                                data_table="test_table"
                            )
                            
                            db_ops = DatabaseOperations(config=config)
                            db_ops._mock_engine = mock_engine
                            db_ops._mock_schema = mock_schema_instance
                            return db_ops
    
    def test_initialize_creates_engine(self, mock_db_ops):
        """Initialize should create database engine."""
        with patch('src.db.db_operations.create_engine') as mock_create_engine:
            with patch('src.db.db_operations.DatabaseSchemaManager') as mock_schema:
                mock_engine = MagicMock()
                mock_create_engine.return_value = mock_engine
                
                mock_schema_instance = MagicMock()
                mock_table_schema = MagicMock()
                mock_table_schema.primary_key = ["id"]
                mock_schema_instance.get_table_schema.return_value = mock_table_schema
                mock_schema.return_value = mock_schema_instance
                
                mock_db_ops.initialize()
                
                assert mock_create_engine.called


class TestDatabaseOperationsConnection:
    """Tests for database connection context manager."""
    
    def test_connection_context_manager(self):
        """Should properly manage connection lifecycle."""
        with patch('src.db.db_operations.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.db_operations.create_engine') as mock_create_engine:
                from src.db.db_operations import DatabaseOperations, DatabaseConfig
                
                mock_engine = MagicMock()
                mock_conn = MagicMock()
                mock_conn.__enter__ = MagicMock(return_value=mock_conn)
                mock_conn.__exit__ = MagicMock(return_value=False)
                mock_engine.connect.return_value = mock_conn
                mock_create_engine.return_value = mock_engine
                
                config = DatabaseConfig(
                    connection_string="postgresql://user:pass@host/db",
                    data_table="test_table"
                )
                
                db_ops = DatabaseOperations(config=config)
                db_ops._engine = mock_engine
                
                # Use the connection context manager
                with db_ops._connection() as conn:
                    assert conn is mock_conn
                
                mock_conn.__exit__.assert_called()


class TestQueryBuilder:
    """Tests for query building functionality."""
    
    def test_query_builder_created_on_initialize(self):
        """QueryBuilder should be created during initialization."""
        with patch('src.db.db_operations.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.db_operations.create_engine') as mock_create_engine:
                with patch('src.db.db_operations.DatabaseSchemaManager') as mock_schema:
                    with patch('src.db.db_operations.QueryBuilder') as MockQueryBuilder:
                        from src.db.db_operations import DatabaseOperations, DatabaseConfig
                        
                        mock_engine = MagicMock()
                        mock_create_engine.return_value = mock_engine
                        
                        mock_schema_instance = MagicMock()
                        mock_table_schema = MagicMock()
                        mock_table_schema.primary_key = ["id"]
                        mock_schema_instance.get_table_schema.return_value = mock_table_schema
                        mock_schema.return_value = mock_schema_instance
                        
                        config = DatabaseConfig(
                            connection_string="postgresql://user:pass@host/db",
                            data_table="test_table"
                        )
                        
                        db_ops = DatabaseOperations(config=config)
                        db_ops.initialize()
                        
                        MockQueryBuilder.assert_called_once()


class TestSessionBookIntegration:
    """Tests for session book management."""
    
    def test_session_book_manager_created_on_initialize(self):
        """SessionBookManager should be created during initialization."""
        with patch('src.db.db_operations.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.db_operations.create_engine') as mock_create_engine:
                with patch('src.db.db_operations.DatabaseSchemaManager') as mock_schema:
                    with patch('src.db.db_operations.SessionBookManager') as MockSessionBookManager:
                        from src.db.db_operations import DatabaseOperations, DatabaseConfig
                        
                        mock_engine = MagicMock()
                        mock_create_engine.return_value = mock_engine
                        
                        mock_schema_instance = MagicMock()
                        mock_table_schema = MagicMock()
                        mock_table_schema.primary_key = ["id"]
                        mock_schema_instance.get_table_schema.return_value = mock_table_schema
                        mock_schema.return_value = mock_schema_instance
                        
                        config = DatabaseConfig(
                            connection_string="postgresql://user:pass@host/db",
                            data_table="test_table"
                        )
                        
                        db_ops = DatabaseOperations(config=config)
                        db_ops.initialize()
                        
                        MockSessionBookManager.assert_called_once_with(["id"])

class TestDatabaseOperationsProperties:
    """Tests for properties after initialization."""
    
    def test_primary_key_property(self):
        """Should return primary key columns."""
        with patch('src.db.db_operations.SQLALCHEMY_AVAILABLE', True):
            from src.db.db_operations import DatabaseOperations, DatabaseConfig
            
            config = DatabaseConfig(
                connection_string="postgresql://user:pass@host/db",
                data_table="test_table"
            )
            
            db_ops = DatabaseOperations(config=config)
            
            mock_schema = MagicMock()
            mock_schema.primary_key = ["id", "name"]
            db_ops._table_schema = mock_schema
            
            assert db_ops.primary_key == ["id", "name"]
    
    def test_columns_property(self):
        """Should return all column names."""
        with patch('src.db.db_operations.SQLALCHEMY_AVAILABLE', True):
            from src.db.db_operations import DatabaseOperations, DatabaseConfig
            
            config = DatabaseConfig(
                connection_string="postgresql://user:pass@host/db",
                data_table="test_table"
            )
            
            db_ops = DatabaseOperations(config=config)
            
            mock_schema = MagicMock()
            mock_schema.column_names = ["id", "name", "status"]
            db_ops._table_schema = mock_schema
            
            assert db_ops.columns == ["id", "name", "status"]
    
    def test_primary_key_raises_if_not_initialized(self):
        """Should raise if not initialized."""
        with patch('src.db.db_operations.SQLALCHEMY_AVAILABLE', True):
            from src.db.db_operations import DatabaseOperations, DatabaseConfig
            
            config = DatabaseConfig(
                connection_string="postgresql://user:pass@host/db",
                data_table="test_table"
            )
            
            db_ops = DatabaseOperations(config=config)
            
            with pytest.raises(RuntimeError, match="not initialized"):
                _ = db_ops.primary_key


class TestFetchPage:
    """Tests for fetch_page method."""
    
    def test_fetch_page_raises_if_not_initialized(self):
        """Should raise if not initialized."""
        with patch('src.db.db_operations.SQLALCHEMY_AVAILABLE', True):
            from src.db.db_operations import DatabaseOperations, DatabaseConfig
            
            config = DatabaseConfig(
                connection_string="postgresql://user:pass@host/db",
                data_table="test_table"
            )
            
            db_ops = DatabaseOperations(config=config)
            
            with pytest.raises(RuntimeError, match="not initialized"):
                db_ops.fetch_page("session1")


class TestSaveModification:
    """Tests for save_modification method."""
    
    def test_save_modification_raises_if_not_initialized(self):
        """Should raise if not initialized."""
        with patch('src.db.db_operations.SQLALCHEMY_AVAILABLE', True):
            from src.db.db_operations import DatabaseOperations, DatabaseConfig
            
            config = DatabaseConfig(
                connection_string="postgresql://user:pass@host/db",
                data_table="test_table"
            )
            
            db_ops = DatabaseOperations(config=config)
            
            with pytest.raises(RuntimeError, match="not initialized"):
                db_ops.save_modification(
                    session_id="s1",
                    pk_values={"id": 1},
                    column_name="status",
                    old_value="old",
                    new_value="new"
                )


class TestUndoModification:
    """Tests for undo_modification method."""
    
    def test_undo_modification_raises_if_not_initialized(self):
        """Should raise if not initialized."""
        with patch('src.db.db_operations.SQLALCHEMY_AVAILABLE', True):
            from src.db.db_operations import DatabaseOperations, DatabaseConfig
            
            config = DatabaseConfig(
                connection_string="postgresql://user:pass@host/db",
                data_table="test_table"
            )
            
            db_ops = DatabaseOperations(config=config)
            
            with pytest.raises(RuntimeError, match="not initialized"):
                db_ops.undo_modification(
                    session_id="s1",
                    mod_id=1,
                    pk_values={"id": 1},
                    column_name="status",
                    old_value="old"
                )


class TestGetModificationsForRow:
    """Tests for get_modifications_for_row method."""
    
    def test_get_modifications_raises_if_not_initialized(self):
        """Should raise if not initialized."""
        with patch('src.db.db_operations.SQLALCHEMY_AVAILABLE', True):
            from src.db.db_operations import DatabaseOperations, DatabaseConfig
            
            config = DatabaseConfig(
                connection_string="postgresql://user:pass@host/db",
                data_table="test_table"
            )
            
            db_ops = DatabaseOperations(config=config)
            
            with pytest.raises(RuntimeError, match="not initialized"):
                db_ops.get_modifications_for_row({"id": 1})


class TestSaveUIState:
    """Tests for save_ui_state method."""
    
    def test_save_ui_state_raises_if_not_initialized(self):
        """Should raise if not initialized."""
        with patch('src.db.db_operations.SQLALCHEMY_AVAILABLE', True):
            from src.db.db_operations import DatabaseOperations, DatabaseConfig
            
            config = DatabaseConfig(
                connection_string="postgresql://user:pass@host/db",
                data_table="test_table"
            )
            
            db_ops = DatabaseOperations(config=config)
            
            with pytest.raises(RuntimeError, match="not initialized"):
                db_ops.save_ui_state(user_id="user1", session_id="s1")


class TestLoadUIState:
    """Tests for load_ui_state method."""
    
    def test_load_ui_state_raises_if_not_initialized(self):
        """Should raise if not initialized."""
        with patch('src.db.db_operations.SQLALCHEMY_AVAILABLE', True):
            from src.db.db_operations import DatabaseOperations, DatabaseConfig
            
            config = DatabaseConfig(
                connection_string="postgresql://user:pass@host/db",
                data_table="test_table"
            )
            
            db_ops = DatabaseOperations(config=config)
            
            with pytest.raises(RuntimeError, match="not initialized"):
                db_ops.load_ui_state(user_id="user1", session_id="s1")


class TestClearSession:
    """Tests for clear_session method."""
    
    def test_clear_session_calls_remove_book(self):
        """Should call remove_book on session book manager."""
        with patch('src.db.db_operations.SQLALCHEMY_AVAILABLE', True):
            from src.db.db_operations import DatabaseOperations, DatabaseConfig
            
            config = DatabaseConfig(
                connection_string="postgresql://user:pass@host/db",
                data_table="test_table"
            )
            
            db_ops = DatabaseOperations(config=config)
            
            mock_sbm = MagicMock()
            db_ops._session_book_manager = mock_sbm
            
            db_ops.clear_session("session1")
            
            mock_sbm.remove_book.assert_called_once_with("session1")
    
    def test_clear_session_no_op_if_no_manager(self):
        """Should not fail if no session book manager."""
        with patch('src.db.db_operations.SQLALCHEMY_AVAILABLE', True):
            from src.db.db_operations import DatabaseOperations, DatabaseConfig
            
            config = DatabaseConfig(
                connection_string="postgresql://user:pass@host/db",
                data_table="test_table"
            )
            
            db_ops = DatabaseOperations(config=config)
            
            # Should not raise
            db_ops.clear_session("session1")


class TestClose:
    """Tests for close method."""
    
    def test_close_disposes_engine(self):
        """Should dispose the engine."""
        with patch('src.db.db_operations.SQLALCHEMY_AVAILABLE', True):
            from src.db.db_operations import DatabaseOperations, DatabaseConfig
            
            config = DatabaseConfig(
                connection_string="postgresql://user:pass@host/db",
                data_table="test_table"
            )
            
            db_ops = DatabaseOperations(config=config)
            
            mock_engine = MagicMock()
            db_ops._engine = mock_engine
            
            db_ops.close()
            
            mock_engine.dispose.assert_called_once()
            assert db_ops._engine is None
    
    def test_close_clears_session_books(self):
        """Should clear all session books."""
        with patch('src.db.db_operations.SQLALCHEMY_AVAILABLE', True):
            from src.db.db_operations import DatabaseOperations, DatabaseConfig
            
            config = DatabaseConfig(
                connection_string="postgresql://user:pass@host/db",
                data_table="test_table"
            )
            
            db_ops = DatabaseOperations(config=config)
            
            mock_sbm = MagicMock()
            db_ops._session_book_manager = mock_sbm
            
            db_ops.close()
            
            mock_sbm.clear_all.assert_called_once()


class TestGetDatabaseOperations:
    """Tests for get_database_operations singleton function."""
    
    def test_get_database_operations_requires_config_first_call(self):
        """Should raise if no config on first call."""
        with patch('src.db.db_operations.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.db_operations._db_ops', None):
                from src.db.db_operations import get_database_operations
                
                with pytest.raises(ValueError, match="Config required"):
                    get_database_operations()
    
    def test_reset_database_operations(self):
        """Should reset the singleton."""
        with patch('src.db.db_operations.SQLALCHEMY_AVAILABLE', True):
            from src.db.db_operations import reset_database_operations
            import src.db.db_operations as mod
            
            mock_db_ops = MagicMock()
            mod._db_ops = mock_db_ops
            
            reset_database_operations()
            
            mock_db_ops.close.assert_called_once()
            assert mod._db_ops is None


class TestGetSessionBook:
    """Tests for get_session_book method."""
    
    def test_get_session_book_raises_if_not_initialized(self):
        """Should raise if not initialized."""
        with patch('src.db.db_operations.SQLALCHEMY_AVAILABLE', True):
            from src.db.db_operations import DatabaseOperations, DatabaseConfig
            
            config = DatabaseConfig(
                connection_string="postgresql://user:pass@host/db",
                data_table="test_table"
            )
            
            db_ops = DatabaseOperations(config=config)
            
            with pytest.raises(RuntimeError, match="not initialized"):
                db_ops.get_session_book("session1")
    
    def test_get_session_book_calls_manager(self):
        """Should call session book manager."""
        with patch('src.db.db_operations.SQLALCHEMY_AVAILABLE', True):
            from src.db.db_operations import DatabaseOperations, DatabaseConfig
            
            config = DatabaseConfig(
                connection_string="postgresql://user:pass@host/db",
                data_table="test_table"
            )
            
            db_ops = DatabaseOperations(config=config)
            
            mock_sbm = MagicMock()
            mock_book = MagicMock()
            mock_sbm.get_book.return_value = mock_book
            db_ops._session_book_manager = mock_sbm
            
            result = db_ops.get_session_book("session1")
            
            mock_sbm.get_book.assert_called_once_with("session1")
            assert result is mock_book


class TestInitializeTableNotFound:
    """Tests for initialize when table not found."""
    
    def test_initialize_raises_if_table_not_found(self):
        """Should raise ValueError if table doesn't exist."""
        with patch('src.db.db_operations.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.db_operations.create_engine') as mock_create_engine:
                with patch('src.db.db_operations.DatabaseSchemaManager') as mock_schema:
                    from src.db.db_operations import DatabaseOperations, DatabaseConfig
                    
                    mock_engine = MagicMock()
                    mock_create_engine.return_value = mock_engine
                    
                    mock_schema_instance = MagicMock()
                    mock_schema_instance.get_table_schema.return_value = None
                    mock_schema.return_value = mock_schema_instance
                    
                    config = DatabaseConfig(
                        connection_string="postgresql://user:pass@host/db",
                        data_table="nonexistent_table"
                    )
                    
                    db_ops = DatabaseOperations(config=config)
                    
                    with pytest.raises(ValueError, match="not found"):
                        db_ops.initialize()


class TestConnectionRaisesIfNotInitialized:
    """Tests for _connection when not initialized."""
    
    def test_connection_raises_if_no_engine(self):
        """Should raise RuntimeError if engine is None."""
        with patch('src.db.db_operations.SQLALCHEMY_AVAILABLE', True):
            from src.db.db_operations import DatabaseOperations, DatabaseConfig
            
            config = DatabaseConfig(
                connection_string="postgresql://user:pass@host/db",
                data_table="test_table"
            )
            
            db_ops = DatabaseOperations(config=config)
            
            with pytest.raises(RuntimeError, match="not initialized"):
                with db_ops._connection():
                    pass


class TestGetAllSessionData:
    """Tests for get_all_session_data method."""
    
    def test_get_all_session_data_returns_dataframe(self):
        """Should return DataFrame from session book."""
        import pandas as pd
        
        with patch('src.db.db_operations.SQLALCHEMY_AVAILABLE', True):
            from src.db.db_operations import DatabaseOperations, DatabaseConfig
            
            config = DatabaseConfig(
                connection_string="postgresql://user:pass@host/db",
                data_table="test_table"
            )
            
            db_ops = DatabaseOperations(config=config)
            
            mock_sbm = MagicMock()
            mock_book = MagicMock()
            expected_df = pd.DataFrame({'col1': [1, 2, 3]})
            mock_book.to_dataframe.return_value = expected_df
            mock_sbm.get_book.return_value = mock_book
            db_ops._session_book_manager = mock_sbm
            
            result = db_ops.get_all_session_data("session1")
            
            assert result is expected_df


class TestFetchPageWithCache:
    """Tests for fetch_page using cached data."""
    
    def test_fetch_page_from_cache(self):
        """Should return from cache when data available."""
        import pandas as pd
        
        with patch('src.db.db_operations.SQLALCHEMY_AVAILABLE', True):
            from src.db.db_operations import DatabaseOperations, DatabaseConfig
            
            config = DatabaseConfig(
                connection_string="postgresql://user:pass@host/db",
                data_table="test_table"
            )
            
            db_ops = DatabaseOperations(config=config)
            
            # Mock query builder
            mock_qb = MagicMock()
            db_ops._query_builder = mock_qb
            
            # Mock session book with cached data
            mock_sbm = MagicMock()
            mock_book = MagicMock()
            mock_book.row_count = 50  # Enough rows for page 1 and 2
            cached_df = pd.DataFrame({'id': list(range(50)), 'value': ['v'] * 50})
            mock_book.to_dataframe.return_value = cached_df
            mock_book.set_context.return_value = False  # Context unchanged
            mock_book.has_more_pages.return_value = True
            mock_sbm.get_book.return_value = mock_book
            db_ops._session_book_manager = mock_sbm
            
            result = db_ops.fetch_page(
                session_id="session1",
                page=1,
                rows_per_page=25,
                force_refresh=False
            )
            
            # Should return cached data without DB call
            assert result.page == 1
            assert result.rows_per_page == 25
            assert result.context_changed is False
            assert result.new_rows_added == 0
    
    def test_fetch_page_from_database(self):
        """Should fetch from database when cache insufficient."""
        import pandas as pd
        
        with patch('src.db.db_operations.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.db_operations.text') as mock_text:
                from src.db.db_operations import DatabaseOperations, DatabaseConfig
                
                config = DatabaseConfig(
                    connection_string="postgresql://user:pass@host/db",
                    data_table="test_table"
                )
                
                db_ops = DatabaseOperations(config=config)
                
                # Mock query builder
                mock_qb = MagicMock()
                mock_qb.build_select_query.return_value = ("SELECT SQL", {"param": 1})
                mock_qb.build_count_query.return_value = ("SELECT COUNT SQL", {})
                db_ops._query_builder = mock_qb
                
                # Mock session book - need to fetch from DB
                mock_sbm = MagicMock()
                mock_book = MagicMock()
                mock_book.row_count = 0  # No cached data
                mock_book.set_context.return_value = True  # Context changed (filter change)
                mock_book.append_page.return_value = 10
                mock_book.has_more_pages.return_value = False
                mock_sbm.get_book.return_value = mock_book
                db_ops._session_book_manager = mock_sbm
                
                # Mock engine and connection
                mock_engine = MagicMock()
                mock_conn = MagicMock()
                
                # Mock result rows
                mock_row1 = MagicMock()
                mock_row2 = MagicMock()
                mock_result = MagicMock()
                mock_result.fetchall.return_value = [
                    (1, 'value1'),
                    (2, 'value2')
                ]
                mock_result.keys.return_value = ['id', 'name']
                
                # Mock count result
                mock_count_result = MagicMock()
                mock_count_result.scalar.return_value = 100
                
                # Return different results for select vs count queries
                mock_conn.execute.side_effect = [mock_result, mock_count_result]
                mock_conn.__enter__ = MagicMock(return_value=mock_conn)
                mock_conn.__exit__ = MagicMock(return_value=False)
                mock_engine.connect.return_value = mock_conn
                db_ops._engine = mock_engine
                
                result = db_ops.fetch_page(
                    session_id="session1",
                    page=1,
                    rows_per_page=25,
                    filters=[],
                    force_refresh=True
                )
                
                # Should have called database
                mock_qb.build_select_query.assert_called_once()
                mock_qb.build_count_query.assert_called_once()
                assert result.total_count == 100
                assert result.context_changed is True
                assert result.has_more is True  # 100 total, showing 25 per page
    
    def test_fetch_page_no_more_pages(self):
        """Should correctly report no more pages when at end."""
        import pandas as pd
        
        with patch('src.db.db_operations.SQLALCHEMY_AVAILABLE', True):
            with patch('src.db.db_operations.text') as mock_text:
                from src.db.db_operations import DatabaseOperations, DatabaseConfig
                
                config = DatabaseConfig(
                    connection_string="postgresql://user:pass@host/db",
                    data_table="test_table"
                )
                
                db_ops = DatabaseOperations(config=config)
                
                # Mock query builder
                mock_qb = MagicMock()
                mock_qb.build_select_query.return_value = ("SELECT SQL", {})
                mock_qb.build_count_query.return_value = ("SELECT COUNT SQL", {})
                db_ops._query_builder = mock_qb
                
                # Mock session book
                mock_sbm = MagicMock()
                mock_book = MagicMock()
                mock_book.row_count = 0
                mock_book.set_context.return_value = False
                mock_book.append_page.return_value = 5
                mock_book.has_more_pages.return_value = False
                mock_sbm.get_book.return_value = mock_book
                db_ops._session_book_manager = mock_sbm
                
                # Mock engine and connection
                mock_engine = MagicMock()
                mock_conn = MagicMock()
                
                mock_result = MagicMock()
                mock_result.fetchall.return_value = [
                    (1, 'value1'),
                    (2, 'value2'),
                    (3, 'value3'),
                    (4, 'value4'),
                    (5, 'value5')
                ]
                mock_result.keys.return_value = ['id', 'name']
                
                mock_count_result = MagicMock()
                mock_count_result.scalar.return_value = 5  # Only 5 total rows
                
                mock_conn.execute.side_effect = [mock_result, mock_count_result]
                mock_conn.__enter__ = MagicMock(return_value=mock_conn)
                mock_conn.__exit__ = MagicMock(return_value=False)
                mock_engine.connect.return_value = mock_conn
                db_ops._engine = mock_engine
                
                result = db_ops.fetch_page(
                    session_id="session1",
                    page=1,
                    rows_per_page=25
                )
                
                # Should report no more pages - only 5 rows, showing all on page 1
                assert result.total_count == 5
                assert result.has_more is False


class TestSaveModificationWithDB:
    """Tests for save_modification with database."""
    
    def test_save_modification_success(self):
        """Should save modification and return ID."""
        with patch('src.db.db_operations.SQLALCHEMY_AVAILABLE', True):
            from src.db.db_operations import DatabaseOperations, DatabaseConfig
            
            config = DatabaseConfig(
                connection_string="postgresql://user:pass@host/db",
                data_table="test_table"
            )
            
            db_ops = DatabaseOperations(config=config)
            
            # Mock query builder
            mock_qb = MagicMock()
            mock_qb.build_insert_modification.return_value = "INSERT SQL"
            db_ops._query_builder = mock_qb
            
            # Mock engine and connection
            mock_engine = MagicMock()
            mock_conn = MagicMock()
            mock_result = MagicMock()
            mock_result.scalar.return_value = 123  # Modification ID
            mock_conn.execute.return_value = mock_result
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_engine.connect.return_value = mock_conn
            db_ops._engine = mock_engine
            
            # Mock session book manager
            mock_sbm = MagicMock()
            mock_book = MagicMock()
            mock_sbm.get_book.return_value = mock_book
            db_ops._session_book_manager = mock_sbm
            
            result = db_ops.save_modification(
                session_id="s1",
                pk_values={"id": 1},
                column_name="status",
                old_value="pending",
                new_value="approved"
            )
            
            assert result == 123
            mock_book.update_row.assert_called_once()


class TestUndoModificationWithDB:
    """Tests for undo_modification with database."""
    
    def test_undo_modification_success(self):
        """Should undo modification and return True."""
        with patch('src.db.db_operations.SQLALCHEMY_AVAILABLE', True):
            from src.db.db_operations import DatabaseOperations, DatabaseConfig
            
            config = DatabaseConfig(
                connection_string="postgresql://user:pass@host/db",
                data_table="test_table"
            )
            
            db_ops = DatabaseOperations(config=config)
            
            # Mock query builder
            mock_qb = MagicMock()
            mock_qb.build_undo_modification.return_value = "UPDATE SQL"
            db_ops._query_builder = mock_qb
            
            # Mock engine and connection
            mock_engine = MagicMock()
            mock_conn = MagicMock()
            mock_result = MagicMock()
            mock_result.rowcount = 1  # Success
            mock_conn.execute.return_value = mock_result
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_engine.connect.return_value = mock_conn
            db_ops._engine = mock_engine
            
            # Mock session book manager
            mock_sbm = MagicMock()
            mock_book = MagicMock()
            mock_sbm.get_book.return_value = mock_book
            db_ops._session_book_manager = mock_sbm
            
            result = db_ops.undo_modification(
                session_id="s1",
                mod_id=123,
                pk_values={"id": 1},
                column_name="status",
                old_value="pending"
            )
            
            assert result is True
            mock_book.update_row.assert_called_once()
    
    def test_undo_modification_not_found(self):
        """Should return False if modification not found."""
        with patch('src.db.db_operations.SQLALCHEMY_AVAILABLE', True):
            from src.db.db_operations import DatabaseOperations, DatabaseConfig
            
            config = DatabaseConfig(
                connection_string="postgresql://user:pass@host/db",
                data_table="test_table"
            )
            
            db_ops = DatabaseOperations(config=config)
            
            # Mock query builder
            mock_qb = MagicMock()
            mock_qb.build_undo_modification.return_value = "UPDATE SQL"
            db_ops._query_builder = mock_qb
            
            # Mock engine and connection
            mock_engine = MagicMock()
            mock_conn = MagicMock()
            mock_result = MagicMock()
            mock_result.rowcount = 0  # Not found
            mock_conn.execute.return_value = mock_result
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_engine.connect.return_value = mock_conn
            db_ops._engine = mock_engine
            
            # Mock session book manager
            mock_sbm = MagicMock()
            db_ops._session_book_manager = mock_sbm
            
            result = db_ops.undo_modification(
                session_id="s1",
                mod_id=999,
                pk_values={"id": 1},
                column_name="status",
                old_value="pending"
            )
            
            assert result is False


class TestSaveUIStateWithDB:
    """Tests for save_ui_state with database."""
    
    def test_save_ui_state_success(self):
        """Should save UI state to database."""
        with patch('src.db.db_operations.SQLALCHEMY_AVAILABLE', True):
            from src.db.db_operations import DatabaseOperations, DatabaseConfig
            
            config = DatabaseConfig(
                connection_string="postgresql://user:pass@host/db",
                data_table="test_table"
            )
            
            db_ops = DatabaseOperations(config=config)
            
            # Mock query builder
            mock_qb = MagicMock()
            mock_qb.build_upsert_state.return_value = "INSERT SQL"
            db_ops._query_builder = mock_qb
            
            # Mock engine and connection
            mock_engine = MagicMock()
            mock_conn = MagicMock()
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_engine.connect.return_value = mock_conn
            db_ops._engine = mock_engine
            
            # Should not raise
            db_ops.save_ui_state(
                user_id="user1",
                session_id="s1",
                filters=[{"col": "status", "op": "eq", "val": "pending"}],
                sort_column="name",
                sort_ascending=True,
                current_page=1,
                rows_per_page=25
            )
            
            mock_conn.execute.assert_called_once()


class TestLoadUIStateWithDB:
    """Tests for load_ui_state with database."""
    
    def test_load_ui_state_found(self):
        """Should return state when found."""
        from datetime import datetime
        
        with patch('src.db.db_operations.SQLALCHEMY_AVAILABLE', True):
            from src.db.db_operations import DatabaseOperations, DatabaseConfig
            
            config = DatabaseConfig(
                connection_string="postgresql://user:pass@host/db",
                data_table="test_table"
            )
            
            db_ops = DatabaseOperations(config=config)
            
            # Mock query builder
            mock_qb = MagicMock()
            mock_qb.build_get_state.return_value = "SELECT SQL"
            db_ops._query_builder = mock_qb
            
            # Mock engine and connection
            mock_engine = MagicMock()
            mock_conn = MagicMock()
            mock_row = MagicMock()
            mock_row.filters = '{"col": "status"}'
            mock_row.sort_column = "name"
            mock_row.sort_ascending = True
            mock_row.current_page = 2
            mock_row.rows_per_page = 50
            mock_row.column_preset = "Default"
            mock_row.updated_at = datetime.now()
            
            mock_result = MagicMock()
            mock_result.fetchone.return_value = mock_row
            mock_conn.execute.return_value = mock_result
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_engine.connect.return_value = mock_conn
            db_ops._engine = mock_engine
            
            result = db_ops.load_ui_state(user_id="user1", session_id="s1")
            
            assert result is not None
            assert result["sort_column"] == "name"
            assert result["current_page"] == 2
    
    def test_load_ui_state_not_found(self):
        """Should return None when not found."""
        with patch('src.db.db_operations.SQLALCHEMY_AVAILABLE', True):
            from src.db.db_operations import DatabaseOperations, DatabaseConfig
            
            config = DatabaseConfig(
                connection_string="postgresql://user:pass@host/db",
                data_table="test_table"
            )
            
            db_ops = DatabaseOperations(config=config)
            
            # Mock query builder
            mock_qb = MagicMock()
            mock_qb.build_get_state.return_value = "SELECT SQL"
            db_ops._query_builder = mock_qb
            
            # Mock engine and connection
            mock_engine = MagicMock()
            mock_conn = MagicMock()
            mock_result = MagicMock()
            mock_result.fetchone.return_value = None
            mock_conn.execute.return_value = mock_result
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_engine.connect.return_value = mock_conn
            db_ops._engine = mock_engine
            
            result = db_ops.load_ui_state(user_id="user1", session_id="s1")
            
            assert result is None
    
    def test_load_ui_state_null_filters(self):
        """Should handle null filters."""
        from datetime import datetime
        
        with patch('src.db.db_operations.SQLALCHEMY_AVAILABLE', True):
            from src.db.db_operations import DatabaseOperations, DatabaseConfig
            
            config = DatabaseConfig(
                connection_string="postgresql://user:pass@host/db",
                data_table="test_table"
            )
            
            db_ops = DatabaseOperations(config=config)
            
            # Mock query builder
            mock_qb = MagicMock()
            mock_qb.build_get_state.return_value = "SELECT SQL"
            db_ops._query_builder = mock_qb
            
            # Mock engine and connection
            mock_engine = MagicMock()
            mock_conn = MagicMock()
            mock_row = MagicMock()
            mock_row.filters = None  # Null filters
            mock_row.sort_column = None
            mock_row.sort_ascending = True
            mock_row.current_page = 1
            mock_row.rows_per_page = 25
            mock_row.column_preset = None
            mock_row.updated_at = datetime.now()
            
            mock_result = MagicMock()
            mock_result.fetchone.return_value = mock_row
            mock_conn.execute.return_value = mock_result
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_engine.connect.return_value = mock_conn
            db_ops._engine = mock_engine
            
            result = db_ops.load_ui_state(user_id="user1", session_id="s1")
            
            assert result is not None
            assert result["filters"] is None


class TestGetModificationsForRowWithDB:
    """Tests for get_modifications_for_row with database."""
    
    def test_get_modifications_for_row(self):
        """Should return list of modifications."""
        from datetime import datetime
        
        with patch('src.db.db_operations.SQLALCHEMY_AVAILABLE', True):
            from src.db.db_operations import DatabaseOperations, DatabaseConfig
            
            config = DatabaseConfig(
                connection_string="postgresql://user:pass@host/db",
                data_table="test_table"
            )
            
            db_ops = DatabaseOperations(config=config)
            
            # Mock query builder
            mock_qb = MagicMock()
            mock_qb.build_get_modifications_for_row.return_value = "SELECT SQL"
            db_ops._query_builder = mock_qb
            
            # Mock engine and connection
            mock_engine = MagicMock()
            mock_conn = MagicMock()
            
            # Mock row data
            mock_row = MagicMock()
            mock_row.id = 1
            mock_row.row_pk = '{"id": 1}'
            mock_row.column_name = "status"
            mock_row.old_value = '"pending"'
            mock_row.new_value = '"approved"'
            mock_row.mod_type = "edit"
            mock_row.created_by = "user1"
            mock_row.created_at = datetime.now()
            mock_row.undone = False
            
            mock_result = MagicMock()
            mock_result.fetchall.return_value = [mock_row]
            mock_conn.execute.return_value = mock_result
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_engine.connect.return_value = mock_conn
            db_ops._engine = mock_engine
            
            result = db_ops.get_modifications_for_row({"id": 1})
            
            assert len(result) == 1
            assert result[0].id == 1
            assert result[0].column_name == "status"
    
    def test_get_modifications_for_row_null_values(self):
        """Should handle null old/new values."""
        from datetime import datetime
        
        with patch('src.db.db_operations.SQLALCHEMY_AVAILABLE', True):
            from src.db.db_operations import DatabaseOperations, DatabaseConfig
            
            config = DatabaseConfig(
                connection_string="postgresql://user:pass@host/db",
                data_table="test_table"
            )
            
            db_ops = DatabaseOperations(config=config)
            
            # Mock query builder
            mock_qb = MagicMock()
            mock_qb.build_get_modifications_for_row.return_value = "SELECT SQL"
            db_ops._query_builder = mock_qb
            
            # Mock engine and connection
            mock_engine = MagicMock()
            mock_conn = MagicMock()
            
            # Mock row with null values
            mock_row = MagicMock()
            mock_row.id = 1
            mock_row.row_pk = '{"id": 1}'
            mock_row.column_name = "status"
            mock_row.old_value = None  # Null
            mock_row.new_value = '"new"'
            mock_row.mod_type = "insert"
            mock_row.created_by = None
            mock_row.created_at = datetime.now()
            mock_row.undone = False
            
            mock_result = MagicMock()
            mock_result.fetchall.return_value = [mock_row]
            mock_conn.execute.return_value = mock_result
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_engine.connect.return_value = mock_conn
            db_ops._engine = mock_engine
            
            result = db_ops.get_modifications_for_row({"id": 1})
            
            assert len(result) == 1
            assert result[0].old_value is None


class TestSingletonFunctions:
    """Tests for singleton functions in db_operations."""
    
    def test_get_database_operations_raises_without_config_first_call(self):
        """Should raise error if no config on first call."""
        with patch('src.db.db_operations.SQLALCHEMY_AVAILABLE', True):
            import src.db.db_operations as db_ops_module
            
            # Reset singleton
            db_ops_module._db_ops = None
            
            with pytest.raises(ValueError, match="Config required"):
                db_ops_module.get_database_operations(None)
    
    def test_get_database_operations_returns_singleton(self):
        """Should return same instance on repeated calls."""
        with patch('src.db.db_operations.SQLALCHEMY_AVAILABLE', True):
            import src.db.db_operations as db_ops_module
            from src.db.db_operations import DatabaseConfig, DatabaseOperations
            
            # Reset singleton
            db_ops_module._db_ops = None
            
            config = DatabaseConfig(
                connection_string="postgresql://user:pass@host/db",
                data_table="test_table"
            )
            
            # Mock the initialize method
            with patch.object(DatabaseOperations, 'initialize'):
                result1 = db_ops_module.get_database_operations(config)
                result2 = db_ops_module.get_database_operations()  # No config second time
                
                assert result1 is result2
                
                # Cleanup
                db_ops_module._db_ops = None
    
    def test_reset_database_operations_clears_singleton(self):
        """reset_database_operations should clear the singleton."""
        with patch('src.db.db_operations.SQLALCHEMY_AVAILABLE', True):
            import src.db.db_operations as db_ops_module
            
            # Set up a mock singleton
            mock_ops = MagicMock()
            db_ops_module._db_ops = mock_ops
            
            db_ops_module.reset_database_operations()
            
            mock_ops.close.assert_called_once()
            assert db_ops_module._db_ops is None
    
    def test_reset_database_operations_handles_none(self):
        """reset_database_operations should handle None gracefully."""
        with patch('src.db.db_operations.SQLALCHEMY_AVAILABLE', True):
            import src.db.db_operations as db_ops_module
            
            db_ops_module._db_ops = None
            
            # Should not raise
            db_ops_module.reset_database_operations()
            
            assert db_ops_module._db_ops is None
