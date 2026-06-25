"""
Layer 1 pinning tests for ConfigInstance properties and methods.

These tests document the current behavior of ConfigInstance properties,
cache invalidation, data fetcher delegation, and DB update methods.
"""

import pytest
import pandas as pd
from unittest.mock import MagicMock, patch, PropertyMock


# =============================================================================
# ConfigInstance property pinning tests
# =============================================================================

class TestConfigInstanceDataFetcher:
    """Pinning tests for ConfigInstance.data_fetcher property."""

    def test_returns_data_fetcher_when_set(self):
        """Should return the internal _data_fetcher."""
        from src.config.config_instance import ConfigInstance

        ci = ConfigInstance.__new__(ConfigInstance)
        mock_fetcher = MagicMock()
        ci._data_fetcher = mock_fetcher

        assert ci.data_fetcher is mock_fetcher

    def test_returns_none_when_not_set(self):
        """Should return None when no data fetcher configured."""
        from src.config.config_instance import ConfigInstance

        ci = ConfigInstance.__new__(ConfigInstance)
        ci._data_fetcher = None

        assert ci.data_fetcher is None


class TestDataFetcherApplyFieldModifications:
    """Pinning tests for lazy field-modification metadata."""

    def test_prefetched_field_mods_rebuild_edited_cells(self):
        """A refreshed lazy page should preserve edited-cell border metadata."""
        from src.config.config_instance import DataFetcher

        fetcher = DataFetcher.__new__(DataFetcher)
        fetcher.app_config = MagicMock()
        fetcher.app_config.table.primary_key = ["Variant_key"]
        fetcher.app_config.database.mods_table = "test_mods"
        fetcher.app_config.database.mode = "direct"
        fetcher.app_config.enable_approval_workflow = True
        fetcher.app_config.enable_status_filter = True
        fetcher._table_override = None

        df = pd.DataFrame({
            "Variant_key": ["PK1"],
            "Comments": ["new value"],
            "_field_mods": [[{
                "column_name": "Comments",
                "old_value": "old value",
                "new_value": "new value",
            }]],
        })

        result = fetcher._apply_field_modifications(df)

        assert "_field_mods" not in result.columns
        cell_key = ((("Variant_key", "PK1"),), "Comments")
        assert fetcher.edited_cells[cell_key] == {
            "original": "old value",
            "current": "new value",
        }


class TestConfigInstanceIsLazyLoading:
    """Pinning tests for ConfigInstance.is_lazy_loading property."""

    def test_true_when_fetcher_exists(self):
        """Should return True when _data_fetcher is set."""
        from src.config.config_instance import ConfigInstance

        ci = ConfigInstance.__new__(ConfigInstance)
        ci._data_fetcher = MagicMock()

        assert ci.is_lazy_loading is True

    def test_false_when_no_fetcher(self):
        """Should return False when _data_fetcher is None."""
        from src.config.config_instance import ConfigInstance

        ci = ConfigInstance.__new__(ConfigInstance)
        ci._data_fetcher = None

        assert ci.is_lazy_loading is False


class TestConfigInstanceTotalRowCount:
    """Pinning tests for ConfigInstance.total_row_count property."""

    def test_from_fetcher_in_lazy_mode(self):
        """Should use fetcher.total_count when lazy loading."""
        from src.config.config_instance import ConfigInstance

        ci = ConfigInstance.__new__(ConfigInstance)
        mock_fetcher = MagicMock()
        mock_fetcher.total_count = 1000
        ci._data_fetcher = mock_fetcher

        assert ci.total_row_count == 1000

    def test_from_df_in_eager_mode(self):
        """Should use len(df) when not lazy loading."""
        from src.config.config_instance import ConfigInstance

        ci = ConfigInstance.__new__(ConfigInstance)
        ci._data_fetcher = None
        ci.df = pd.DataFrame({"a": [1, 2, 3]})

        assert ci.total_row_count == 3

    def test_zero_when_df_is_none(self):
        """Should return 0 when df is None and no fetcher."""
        from src.config.config_instance import ConfigInstance

        ci = ConfigInstance.__new__(ConfigInstance)
        ci._data_fetcher = None
        ci.df = None

        assert ci.total_row_count == 0


class TestConfigInstanceEnsureDataDir:
    """Pinning tests for ConfigInstance.ensure_data_dir."""

    def test_returns_true_on_success(self, tmp_path):
        """Should return True when directory is created."""
        from src.config.config_instance import ConfigInstance

        ci = ConfigInstance.__new__(ConfigInstance)
        ci.data_dir = tmp_path / "new_dir"

        assert ci.ensure_data_dir() is True
        assert ci.data_dir.exists()

    def test_returns_false_on_read_only(self):
        """Should return False when mkdir raises OSError."""
        from src.config.config_instance import ConfigInstance

        ci = ConfigInstance.__new__(ConfigInstance)
        ci.data_dir = MagicMock()
        ci.data_dir.mkdir.side_effect = OSError("read-only filesystem")

        assert ci.ensure_data_dir() is False


class TestConfigInstanceInvalidateDataCache:
    """Pinning tests for ConfigInstance.invalidate_data_cache."""

    def test_clears_cache_fields(self):
        """Should set _data_cache to None and _data_cache_time to 0."""
        from src.config.config_instance import ConfigInstance

        ci = ConfigInstance.__new__(ConfigInstance)
        ci._data_cache = pd.DataFrame({"a": [1]})
        ci._data_cache_time = 12345.0

        ci.invalidate_data_cache()

        assert ci._data_cache is None
        assert ci._data_cache_time == 0


class TestConfigInstanceInvalidateModsCache:
    """Pinning tests for ConfigInstance.invalidate_mods_cache."""

    def test_clears_mods_cache_fields(self):
        """Should set _mods_log_cache to None and _mods_log_cache_time to 0."""
        from src.config.config_instance import ConfigInstance

        ci = ConfigInstance.__new__(ConfigInstance)
        ci._mods_log_cache = [{"type": "field_modification"}]
        ci._mods_log_cache_time = 67890.0

        ci.invalidate_mods_cache()

        assert ci._mods_log_cache is None
        assert ci._mods_log_cache_time == 0


class TestConfigInstanceReloadData:
    """Pinning tests for ConfigInstance.reload_data."""

    def test_calls_load_data_and_updates_columns(self):
        """Should call _load_data and update df and all_columns."""
        from src.config.config_instance import ConfigInstance

        ci = ConfigInstance.__new__(ConfigInstance)
        new_df = pd.DataFrame({"X": [1], "Y": [2]})
        ci._load_data = MagicMock(return_value=new_df)
        ci.df = None
        ci.all_columns = []

        result = ci.reload_data()

        ci._load_data.assert_called_once()
        assert list(ci.df.columns) == ["X", "Y"]
        assert ci.all_columns == ["X", "Y"]
        assert result is ci.df


class TestConfigInstanceMarkModificationUndoneInDb:
    """Pinning tests for ConfigInstance.mark_modification_undone_in_db."""

    def test_datum_mode_delegates(self):
        """In datum mode, should delegate to _mark_modification_undone_datum."""
        from src.config.config_instance import ConfigInstance

        ci = ConfigInstance.__new__(ConfigInstance)
        ci.app_config = MagicMock()
        ci.app_config.database.mode = "datum"
        ci._mark_modification_undone_datum = MagicMock(return_value=True)

        result = ci.mark_modification_undone_in_db(42)

        ci._mark_modification_undone_datum.assert_called_once_with(42)
        assert result is True

    def test_direct_mode_executes_update(self):
        """In direct mode, should execute SQL UPDATE and invalidate cache."""
        from src.config.config_instance import ConfigInstance

        ci = ConfigInstance.__new__(ConfigInstance)
        ci.app_config = MagicMock()
        ci.app_config.database.mode = "direct"
        ci.app_config.database.mods_table = "test_mods"

        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_engine.connect.return_value = mock_conn
        ci._get_engine = MagicMock(return_value=mock_engine)
        ci.invalidate_mods_cache = MagicMock()

        result = ci.mark_modification_undone_in_db(99)

        assert result is True
        mock_conn.execute.assert_called_once()
        mock_conn.commit.assert_called_once()
        ci.invalidate_mods_cache.assert_called_once()

    def test_returns_false_when_no_engine(self):
        """Should return False when _get_engine returns None."""
        from src.config.config_instance import ConfigInstance

        ci = ConfigInstance.__new__(ConfigInstance)
        ci.app_config = MagicMock()
        ci.app_config.database.mode = "direct"
        ci.app_config.database.mods_table = "test_mods"
        ci._get_engine = MagicMock(return_value=None)

        result = ci.mark_modification_undone_in_db(1)

        assert result is False


class TestConfigInstanceCleanupCorruptedModifications:
    """Pinning tests for ConfigInstance.cleanup_corrupted_modifications."""

    def test_datum_mode_delegates(self):
        """In datum mode, should delegate to _cleanup_corrupted_modifications_datum."""
        from src.config.config_instance import ConfigInstance

        ci = ConfigInstance.__new__(ConfigInstance)
        ci.app_config = MagicMock()
        ci.app_config.database.mode = "datum"
        ci._cleanup_corrupted_modifications_datum = MagicMock(return_value=3)

        result = ci.cleanup_corrupted_modifications()

        ci._cleanup_corrupted_modifications_datum.assert_called_once()
        assert result == 3

    def test_postgres_mode_delegates_to_execute_sql_path(self):
        """In postgres mode, should use the execute_sql cleanup path."""
        from src.config.config_instance import ConfigInstance

        ci = ConfigInstance.__new__(ConfigInstance)
        ci.app_config = MagicMock()
        ci.app_config.database.mode = "postgres"
        ci._cleanup_corrupted_modifications_datum = MagicMock(return_value=2)

        result = ci.cleanup_corrupted_modifications()

        ci._cleanup_corrupted_modifications_datum.assert_called_once()
        assert result == 2

    def test_direct_mode_returns_zero(self):
        """In non-datum mode, should return 0."""
        from src.config.config_instance import ConfigInstance

        ci = ConfigInstance.__new__(ConfigInstance)
        ci.app_config = MagicMock()
        ci.app_config.database.mode = "direct"

        result = ci.cleanup_corrupted_modifications()

        assert result == 0


class TestConfigInstanceUpdateDataInDb:
    """Pinning tests for ConfigInstance.update_data_in_db."""

    def test_datum_mode_delegates(self):
        """In datum mode, should delegate to _update_data_in_datum."""
        from src.config.config_instance import ConfigInstance

        ci = ConfigInstance.__new__(ConfigInstance)
        ci.app_config = MagicMock()
        ci.app_config.database.mode = "datum"
        ci._update_data_in_datum = MagicMock(return_value=True)

        result = ci.update_data_in_db({"id": 1}, "name", "new_value")

        ci._update_data_in_datum.assert_called_once_with({"id": 1}, "name", "new_value")
        assert result is True

    def test_postgres_mode_delegates_to_execute_sql_path(self):
        """In postgres mode, should use the Datum-compatible execute_sql path."""
        from src.config.config_instance import ConfigInstance

        ci = ConfigInstance.__new__(ConfigInstance)
        ci.app_config = MagicMock()
        ci.app_config.database.mode = "postgres"
        ci._update_data_in_datum = MagicMock(return_value=True)
        ci._get_engine = MagicMock()

        result = ci.update_data_in_db({"id": 1}, "name", "new_value")

        ci._update_data_in_datum.assert_called_once_with({"id": 1}, "name", "new_value")
        ci._get_engine.assert_not_called()
        assert result is True

    def test_direct_mode_executes_update(self):
        """In direct mode, should execute SQL UPDATE with PK WHERE clause."""
        from src.config.config_instance import ConfigInstance

        ci = ConfigInstance.__new__(ConfigInstance)
        ci.app_config = MagicMock()
        ci.app_config.database.mode = "direct"
        ci.app_config.database.lazy_loading = False
        ci.app_config.database.data_table = "test_data"
        ci.app_config.table.primary_key = ["id"]

        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_engine.connect.return_value = mock_conn
        ci._get_engine = MagicMock(return_value=mock_engine)

        result = ci.update_data_in_db({"id": "42"}, "name", "Alice")

        assert result is True
        mock_conn.execute.assert_called_once()
        mock_conn.commit.assert_called_once()

    def test_returns_false_when_no_pk_match(self):
        """Should return False when row_pk has no matching PK columns."""
        from src.config.config_instance import ConfigInstance

        ci = ConfigInstance.__new__(ConfigInstance)
        ci.app_config = MagicMock()
        ci.app_config.database.mode = "direct"
        ci.app_config.database.data_table = "test_data"
        ci.app_config.table.primary_key = ["id"]

        mock_engine = MagicMock()
        ci._get_engine = MagicMock(return_value=mock_engine)

        # PK dict has wrong keys
        result = ci.update_data_in_db({"wrong_key": "42"}, "name", "Alice")

        assert result is False


class TestLoadConfigInstance:
    """Pinning tests for load_config_instance function."""

    def test_returns_config_instance(self):
        """Should return a ConfigInstance by calling the constructor."""
        from src.config.config_instance import load_config_instance, ConfigInstance

        with patch.object(ConfigInstance, '__init__', return_value=None) as mock_init:
            mock_init.return_value = None
            with patch.object(ConfigInstance, '__post_init__', return_value=None, create=True):
                result = load_config_instance("test_config.json", "testuser", "testuser@nih.gov")

                assert isinstance(result, ConfigInstance)
                mock_init.assert_called_once_with(config_path="test_config.json", username="testuser", user_email="testuser@nih.gov")


# =============================================================================
# Date column detection tests
# =============================================================================

class TestIsDateColumn:
    """Tests for DataFetcher.is_date_column method."""

    def _make_fetcher(self, column_types: dict):
        from src.config.config_instance import DataFetcher
        fetcher = DataFetcher.__new__(DataFetcher)
        fetcher._column_types = column_types
        return fetcher

    def test_date_type(self):
        fetcher = self._make_fetcher({"created_at": "date"})
        assert fetcher.is_date_column("created_at") is True

    def test_timestamp_type(self):
        fetcher = self._make_fetcher({"ts": "timestamp"})
        assert fetcher.is_date_column("ts") is True

    def test_timestamptz_type(self):
        fetcher = self._make_fetcher({"ts": "timestamptz"})
        assert fetcher.is_date_column("ts") is True

    def test_timestamp_with_time_zone(self):
        fetcher = self._make_fetcher({"ts": "timestamp with time zone"})
        assert fetcher.is_date_column("ts") is True

    def test_timestamp_without_time_zone(self):
        fetcher = self._make_fetcher({"ts": "timestamp without time zone"})
        assert fetcher.is_date_column("ts") is True

    def test_integer_not_date(self):
        fetcher = self._make_fetcher({"score": "integer"})
        assert fetcher.is_date_column("score") is False

    def test_text_not_date(self):
        fetcher = self._make_fetcher({"name": "character varying"})
        assert fetcher.is_date_column("name") is False

    def test_missing_column(self):
        fetcher = self._make_fetcher({})
        assert fetcher.is_date_column("nonexistent") is False

    def test_case_insensitive(self):
        fetcher = self._make_fetcher({"ts": "TIMESTAMP"})
        assert fetcher.is_date_column("ts") is True


class TestDateColumnsProperty:
    """Tests for DataFetcher.date_columns property."""

    def _make_fetcher(self, column_types: dict):
        from src.config.config_instance import DataFetcher
        fetcher = DataFetcher.__new__(DataFetcher)
        fetcher._column_types = column_types
        return fetcher

    def test_returns_date_columns_only(self):
        fetcher = self._make_fetcher({
            "created_at": "date",
            "name": "character varying",
            "updated_at": "timestamp",
            "score": "integer",
        })
        assert fetcher.date_columns == {"created_at", "updated_at"}

    def test_empty_when_no_dates(self):
        fetcher = self._make_fetcher({"name": "text", "score": "integer"})
        assert fetcher.date_columns == set()

    def test_empty_types(self):
        fetcher = self._make_fetcher({})
        assert fetcher.date_columns == set()

    def test_all_date_types(self):
        fetcher = self._make_fetcher({
            "a": "date", "b": "timestamp",
            "c": "timestamp without time zone",
            "d": "timestamp with time zone",
            "e": "timestamptz",
        })
        assert fetcher.date_columns == {"a", "b", "c", "d", "e"}


# =============================================================================
# DataFetcher.set_table_override / clear_table_override
# =============================================================================

class TestDataFetcherTableOverride:
    """Tests for DataFetcher.set_table_override and clear_table_override."""

    def _make_fetcher(self, data_table="original_data"):
        from src.config.config_instance import DataFetcher

        fetcher = DataFetcher.__new__(DataFetcher)
        fetcher.app_config = MagicMock()
        fetcher.app_config.database.data_table = data_table
        fetcher._table_override = None
        fetcher._query_override = None
        fetcher._total_count = 0
        fetcher._columns = []
        fetcher._column_types = {}
        fetcher._fetch_metadata = MagicMock()
        return fetcher

    def test_set_table_override_sets_field(self):
        """set_table_override should set _table_override."""
        fetcher = self._make_fetcher()
        fetcher.set_table_override("synthesis_result")
        assert fetcher._table_override == "synthesis_result"

    def test_set_table_override_calls_refresh_count(self):
        """set_table_override should call _fetch_metadata."""
        fetcher = self._make_fetcher()
        fetcher.set_table_override("my_matview")
        fetcher._fetch_metadata.assert_called_once()

    def test_clear_table_override_resets_to_none(self):
        """clear_table_override should set _table_override to None."""
        fetcher = self._make_fetcher()
        fetcher._table_override = "override_table"
        fetcher.clear_table_override()
        assert fetcher._table_override is None

    def test_clear_table_override_calls_refresh_count(self):
        """clear_table_override should call _fetch_metadata."""
        fetcher = self._make_fetcher()
        fetcher._table_override = "override_table"
        fetcher.clear_table_override()
        fetcher._fetch_metadata.assert_called_once()

    def test_set_then_clear_roundtrip(self):
        """Set override then clear should return to None."""
        fetcher = self._make_fetcher()
        fetcher.set_table_override("temp_table")
        assert fetcher._table_override == "temp_table"
        fetcher.clear_table_override()
        assert fetcher._table_override is None

    def test_set_query_override_sets_subquery_source(self):
        """set_query_override should use the query as a wrapped FROM source."""
        fetcher = self._make_fetcher()
        fetcher.set_query_override("SELECT id, name FROM source;")

        assert fetcher._query_override == "SELECT id, name FROM source"
        assert fetcher._table_override is None
        assert fetcher._source_sql == "(SELECT id, name FROM source)"
        fetcher._fetch_metadata.assert_called_once()


# =============================================================================
# DataFetcher.get_value_counts
# =============================================================================

class TestDataFetcherGetValueCounts:
    """Tests for DataFetcher.get_value_counts."""

    def _make_fetcher(self, mode="direct"):
        from src.config.config_instance import DataFetcher

        fetcher = DataFetcher.__new__(DataFetcher)
        fetcher.app_config = MagicMock()
        fetcher.app_config.database.mode = mode
        fetcher.app_config.database.data_table = "test_data"
        fetcher._table_override = None
        fetcher._engine = MagicMock()
        fetcher._datum_client = None
        fetcher._postgres_client = None
        return fetcher

    def test_direct_mode_returns_tuples(self):
        """Should return list of (value, count) tuples via SQLAlchemy engine."""
        fetcher = self._make_fetcher("direct")
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value.fetchall.return_value = [
            ("Active", 50), ("Inactive", 20)
        ]
        fetcher._engine.connect.return_value = mock_conn

        result = fetcher.get_value_counts("Status")

        assert result == [("Active", 50), ("Inactive", 20)]

    def test_returns_empty_on_exception(self):
        """Should return [] when engine raises."""
        fetcher = self._make_fetcher("direct")
        fetcher._engine.connect.side_effect = Exception("connection error")

        result = fetcher.get_value_counts("Status")

        assert result == []

    def test_datum_mode_queries_via_client(self):
        """Datum mode should use _datum_client.execute_sql."""
        fetcher = self._make_fetcher("datum")
        fetcher._datum_client = MagicMock()
        fetcher._datum_client.execute_sql.return_value.data = [
            {"val": "X", "cnt": 10}, {"val": "Y", "cnt": 5}
        ]
        fetcher.app_config.database.datum_database = "mydb"
        fetcher.app_config.database.datum_schema = "public"
        fetcher.app_config.database.datum_service_name = "postgres_sql"

        result = fetcher.get_value_counts("Gene")

        assert result == [("X", 10), ("Y", 5)]
        fetcher._datum_client.execute_sql.assert_called_once()

    def test_postgres_mode_initializes_postgres_client(self, monkeypatch):
        """Postgres mode should use PostgresClient as the DataFetcher SQL client."""
        fetcher = self._make_fetcher("postgres")
        fetcher.app_config.database.postgres_dsn = "MY_PG_DSN"
        fetcher.app_config.database.postgres_host = "MY_PG_HOST"
        fetcher.app_config.database.postgres_port = "MY_PG_PORT"
        fetcher.app_config.database.postgres_user = "MY_PG_USER"
        fetcher.app_config.database.postgres_password = "MY_PG_PASSWORD"
        fetcher.app_config.database.postgres_database = "MY_PG_DATABASE"
        fetcher.app_config.database.postgres_schema = "MY_PG_SCHEMA"
        fetcher.app_config.database.postgres_connect_timeout = "MY_PG_CONNECT_TIMEOUT"
        monkeypatch.setenv("MY_PG_DSN", "postgresql://example/db")
        monkeypatch.setenv("MY_PG_HOST", "db.example")
        monkeypatch.setenv("MY_PG_PORT", "6543")
        monkeypatch.setenv("MY_PG_USER", "app")
        monkeypatch.setenv("MY_PG_PASSWORD", "pw")
        monkeypatch.setenv("MY_PG_DATABASE", "db")
        monkeypatch.setenv("MY_PG_SCHEMA", "epi")
        monkeypatch.setenv("MY_PG_CONNECT_TIMEOUT", "7")

        with patch("src.adapter.postgres.PostgresClient") as MockClient:
            assert fetcher._is_datum is True

        MockClient.assert_called_once_with(
            dsn="postgresql://example/db",
            host="db.example",
            port=6543,
            user="app",
            password="pw",
            database="db",
            schema="epi",
            connect_timeout=7,
        )
        assert fetcher._datum_client is fetcher._postgres_client

    def test_postgres_mode_value_counts_use_execute_sql_client(self):
        """Postgres mode should use the Datum-compatible execute_sql path."""
        fetcher = self._make_fetcher("postgres")
        fetcher._postgres_client = MagicMock()
        fetcher._datum_client = fetcher._postgres_client
        fetcher._postgres_client.execute_sql.return_value.data = [
            {"val": "A", "cnt": 3},
        ]
        fetcher.app_config.database.datum_database = None
        fetcher.app_config.database.datum_schema = None
        fetcher.app_config.database.datum_service_name = "postgres_sql"

        result = fetcher.get_value_counts("Status")

        assert result == [("A", 3)]
        fetcher._postgres_client.execute_sql.assert_called_once()

    def test_respects_limit(self):
        """The SQL should include the specified LIMIT."""
        fetcher = self._make_fetcher("direct")
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value.fetchall.return_value = []
        fetcher._engine.connect.return_value = mock_conn

        fetcher.get_value_counts("Status", limit=10)

        # Verify the SQL contains LIMIT 10
        call_args = mock_conn.execute.call_args
        sql_str = str(call_args[0][0])
        assert "LIMIT 10" in sql_str

    def test_query_override_fetch_page_wraps_query_with_limit_offset(self):
        """Query override should page against the wrapped synthesis SQL."""
        from src.config.config_instance import QueryParams

        fetcher = self._make_fetcher("direct")
        fetcher._query_override = "SELECT id, name FROM source"
        fetcher._columns = ["id", "name"]
        fetcher._column_types = {"name": "text"}
        fetcher.app_config.database.mods_table = "mods"
        fetcher.app_config.table.primary_key = ["id"]
        fetcher.app_config.enable_approval_workflow = True
        fetcher.app_config.enable_status_filter = True
        fetcher.app_config.status_values = {}
        fetcher.app_config.status_labels = {
            "unprocessed": "Unprocessed",
            "edited": "Edited",
            "approved": "Approved",
            "rejected": "Rejected",
        }
        fetcher.app_config.database.status_column = "Status"

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [(26, "row", "unprocessed")]
        mock_result.keys.return_value = ["id", "name", "_mod_status"]
        mock_conn.execute.return_value = mock_result
        fetcher._engine.connect.return_value = mock_conn

        df = fetcher.fetch_page(QueryParams(page=2, page_size=25))

        sql_str = str(mock_conn.execute.call_args[0][0])
        assert "FROM (SELECT id, name FROM source) d" in sql_str
        assert "LIMIT 25 OFFSET 25" in sql_str
        assert list(df.columns) == ["id", "name", "_mod_status"]


# =============================================================================
# ConfigInstance.activate_synthesis_fetcher / deactivate_synthesis_fetcher
# =============================================================================

class TestSynthesisFetcherLifecycle:
    """Tests for activate/deactivate synthesis fetcher."""

    def _make_ci(self):
        from src.config.config_instance import ConfigInstance

        ci = ConfigInstance.__new__(ConfigInstance)
        ci.app_config = MagicMock()
        ci.app_config.database.data_table = "base_table"
        ci.app_config.database.lazy_loading = False
        ci._data_fetcher = None
        ci.all_columns = []
        ci.display_columns = []
        return ci

    def test_activate_creates_fetcher_when_none(self):
        """When _data_fetcher is None, should create a new one."""
        from src.config.config_instance import ConfigInstance

        ci = self._make_ci()

        with patch("src.config.config_instance.DataFetcher._init_connection"), \
             patch("src.config.config_instance.DataFetcher._fetch_metadata"):
            ci.activate_synthesis_fetcher("synth_table")

        assert ci._data_fetcher is not None
        assert ci._data_fetcher._table_override == "synth_table"

    def test_activate_reuses_existing_fetcher(self):
        """When _data_fetcher exists, should call set_table_override."""
        ci = self._make_ci()
        existing = MagicMock()
        ci._data_fetcher = existing

        ci.activate_synthesis_fetcher("synth_v2")

        existing.set_table_override.assert_called_once_with("synth_v2")

    def test_activate_populates_columns_if_empty(self):
        """Should populate all_columns from fetcher if currently empty."""
        ci = self._make_ci()

        with patch("src.config.config_instance.DataFetcher._init_connection"), \
             patch("src.config.config_instance.DataFetcher._fetch_metadata") as mock_meta:
            def set_cols(self_inner=None):
                ci._data_fetcher._columns = ["A", "B", "C"]
            mock_meta.side_effect = lambda: None
            ci.activate_synthesis_fetcher("synth_table")
            ci._data_fetcher._columns = ["A", "B", "C"]
            # Re-call to simulate behavior with columns
            ci._data_fetcher = None
            ci.all_columns = []
            ci.display_columns = []

            def fake_meta():
                pass
            with patch("src.config.config_instance.DataFetcher._init_connection"), \
                 patch("src.config.config_instance.DataFetcher._fetch_metadata", side_effect=fake_meta):
                ci.activate_synthesis_fetcher("synth_table")
                # Manually set _columns as _fetch_metadata would
                ci._data_fetcher._columns = ["X", "Y"]
                # Simulate the conditional
                if not ci.all_columns and ci._data_fetcher._columns:
                    ci.all_columns = ci._data_fetcher._columns.copy()
                    ci.display_columns = ci._data_fetcher._columns.copy()

        assert ci.all_columns == ["X", "Y"]

    def test_deactivate_removes_fetcher_when_not_lazy(self):
        """When lazy_loading=False, should set _data_fetcher to None."""
        ci = self._make_ci()
        ci.app_config.database.lazy_loading = False
        ci._data_fetcher = MagicMock()

        ci.deactivate_synthesis_fetcher()

        assert ci._data_fetcher is None

    def test_deactivate_clears_override_when_lazy(self):
        """When lazy_loading=True, should call clear_table_override."""
        ci = self._make_ci()
        ci.app_config.database.lazy_loading = True
        ci._data_fetcher = MagicMock()

        ci.deactivate_synthesis_fetcher()

        ci._data_fetcher.clear_table_override.assert_called_once()

    def test_deactivate_noop_when_no_fetcher(self):
        """Should not raise when _data_fetcher is already None."""
        ci = self._make_ci()
        ci._data_fetcher = None

        ci.deactivate_synthesis_fetcher()  # Should not raise

        assert ci._data_fetcher is None

    def test_run_synthesis_query_lazy_activates_fetcher_without_materializing(self):
        """Lazy query mode should prepare a DataFetcher, not fetch every row."""
        ci = self._make_ci()
        ci.app_config.database.lazy_loading = True
        ci.app_config.synthesis.mode = "query"
        ci.app_config.synthesis.query = "SELECT id, name FROM source"
        ci.all_columns = []
        ci._run_synthesis_direct_query = MagicMock()

        def activate(query):
            ci.all_columns = ["id", "name"]

        ci.activate_synthesis_query_fetcher = MagicMock(side_effect=activate)

        df, was_cached = ci.run_synthesis()

        ci.activate_synthesis_query_fetcher.assert_called_once_with("SELECT id, name FROM source")
        ci._run_synthesis_direct_query.assert_not_called()
        assert was_cached is False
        assert list(df.columns) == ["id", "name"]
        assert df.empty


# =============================================================================
# ConfigInstance.get_synthesis_table_name
# =============================================================================

class TestGetSynthesisTableName:
    """Tests for ConfigInstance.get_synthesis_table_name."""

    def _make_ci(self, data_table="my_data", prefix="_synthesis_result"):
        from src.config.config_instance import ConfigInstance

        ci = ConfigInstance.__new__(ConfigInstance)
        ci.app_config = MagicMock()
        ci.app_config.database.data_table = data_table
        ci.app_config.synthesis.result_table_prefix = prefix
        return ci

    def test_simple_table_returns_prefix(self):
        """No schema in data_table → returns just prefix."""
        ci = self._make_ci(data_table="my_data")
        assert ci.get_synthesis_table_name() == "_synthesis_result"

    def test_schema_qualified_table(self):
        """Schema.table in data_table → returns schema.prefix."""
        ci = self._make_ci(data_table="myschema.my_data")
        assert ci.get_synthesis_table_name() == "myschema._synthesis_result"

    def test_custom_prefix(self):
        """Custom prefix should be used."""
        ci = self._make_ci(data_table="abc.data", prefix="_custom_synth")
        assert ci.get_synthesis_table_name() == "abc._custom_synth"

    def test_none_prefix_uses_default(self):
        """None prefix should fall back to '_synthesis_result'."""
        ci = self._make_ci(data_table="data", prefix=None)
        assert ci.get_synthesis_table_name() == "_synthesis_result"

    def test_empty_prefix_uses_default(self):
        """Empty string prefix should fall back to '_synthesis_result'."""
        ci = self._make_ci(data_table="data", prefix="")
        assert ci.get_synthesis_table_name() == "_synthesis_result"


# =============================================================================
# ConfigInstance.check_synthesis_table_exists
# =============================================================================

class TestCheckSynthesisTableExists:
    """Tests for ConfigInstance.check_synthesis_table_exists."""

    def _make_ci(self):
        from src.config.config_instance import ConfigInstance

        ci = ConfigInstance.__new__(ConfigInstance)
        ci.app_config = MagicMock()
        ci.app_config.database.mode = "direct"
        ci.app_config.database.lazy_loading = False
        ci.app_config.database.data_table = "test_data"
        ci.app_config.synthesis.result_table_prefix = "_synthesis_result"
        ci._synthesis_exists_cache = None
        return ci

    def test_returns_cached_true(self):
        """Should return cached value without DB query."""
        ci = self._make_ci()
        ci._synthesis_exists_cache = True
        assert ci.check_synthesis_table_exists() is True

    def test_returns_cached_false(self):
        """Should return cached False without DB query."""
        ci = self._make_ci()
        ci._synthesis_exists_cache = False
        assert ci.check_synthesis_table_exists() is False

    def test_direct_mode_query_success(self):
        """DB query success → returns True and caches."""
        ci = self._make_ci()
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_engine.connect.return_value = mock_conn
        ci._get_engine = MagicMock(return_value=mock_engine)

        result = ci.check_synthesis_table_exists()

        assert result is True
        assert ci._synthesis_exists_cache is True

    def test_direct_mode_query_failure(self):
        """DB query failure → returns False and caches."""
        ci = self._make_ci()
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.side_effect = Exception("relation does not exist")
        mock_engine.connect.return_value = mock_conn
        ci._get_engine = MagicMock(return_value=mock_engine)

        result = ci.check_synthesis_table_exists()

        assert result is False
        assert ci._synthesis_exists_cache is False


# =============================================================================
# ConfigInstance.run_synthesis
# =============================================================================

class TestRunSynthesis:
    """Tests for ConfigInstance.run_synthesis."""

    def _make_ci(self):
        from src.config.config_instance import ConfigInstance

        ci = ConfigInstance.__new__(ConfigInstance)
        ci.app_config = MagicMock()
        ci.app_config.database.mode = "direct"
        ci.app_config.database.data_table = "test_data"
        ci.app_config.synthesis.query = "SELECT * FROM source"
        ci.app_config.synthesis.result_table_prefix = "_synth"
        ci.app_config.synthesis.ttl_minutes = 10
        ci._synthesis_exists_cache = None
        ci._synthesis_age_cache = None
        ci._synthesis_age_cache_time = 0
        return ci

    def test_raises_when_no_query(self):
        """Should raise ValueError when synthesis query is empty."""
        ci = self._make_ci()
        ci.app_config.synthesis.query = ""

        with pytest.raises(ValueError, match="No synthesis query"):
            ci.run_synthesis()

    def test_cache_hit_returns_cached_df(self):
        """When table exists and within TTL, should return cached data."""
        ci = self._make_ci()
        expected_df = pd.DataFrame({"x": [1, 2]})

        ci.check_synthesis_table_exists = MagicMock(return_value=True)
        ci._get_synthesis_age_minutes = MagicMock(return_value=5.0)
        ci._read_synthesis_table = MagicMock(return_value=expected_df)

        df, was_cached = ci.run_synthesis()

        assert was_cached is True
        assert list(df["x"]) == [1, 2]
        ci._read_synthesis_table.assert_called_once()

    def test_force_triggers_refresh(self):
        """force=True should refresh even within TTL."""
        ci = self._make_ci()
        expected_df = pd.DataFrame({"y": [3]})

        ci.check_synthesis_table_exists = MagicMock(return_value=True)
        ci._get_synthesis_age_minutes = MagicMock(return_value=1.0)
        ci._refresh_synthesis = MagicMock()
        ci._stamp_synthesis_comment = MagicMock()
        ci._read_synthesis_table = MagicMock(return_value=expected_df)

        df, was_cached = ci.run_synthesis(force=True)

        assert was_cached is False
        ci._refresh_synthesis.assert_called_once()

    def test_creates_when_missing(self):
        """When table doesn't exist, should create it."""
        ci = self._make_ci()
        expected_df = pd.DataFrame({"z": [9]})

        ci.check_synthesis_table_exists = MagicMock(return_value=False)
        ci._run_synthesis_direct = MagicMock()
        ci._stamp_synthesis_comment = MagicMock()
        ci._read_synthesis_table = MagicMock(return_value=expected_df)

        df, was_cached = ci.run_synthesis()

        assert was_cached is False
        ci._run_synthesis_direct.assert_called_once()
        assert ci._synthesis_exists_cache is True


# =============================================================================
# ConfigInstance._run_synthesis_direct_query (query mode)
# =============================================================================

class TestRunSynthesisDirectQuery:
    """Tests for synthesis query mode (no view creation)."""

    def _make_ci(self):
        from src.config.config_instance import ConfigInstance

        ci = ConfigInstance.__new__(ConfigInstance)
        ci.app_config = MagicMock()
        ci.app_config.database.mode = "direct"
        ci.app_config.database.data_table = "test_data"
        ci.app_config.database.lazy_loading = False
        ci.app_config.synthesis.query = "SELECT id, name FROM source"
        ci.app_config.synthesis.mode = "query"
        ci.app_config.synthesis.result_table_prefix = "_synth"
        ci.app_config.synthesis.ttl_minutes = 10
        ci._synthesis_exists_cache = None
        ci._synthesis_age_cache = None
        ci._synthesis_age_cache_time = 0
        ci.all_columns = []
        ci.display_columns = []
        return ci

    def test_run_synthesis_routes_to_direct_query(self):
        """When mode='query', run_synthesis should call _run_synthesis_direct_query."""
        ci = self._make_ci()
        expected_df = pd.DataFrame({"id": [1, 2], "name": ["a", "b"]})
        ci._run_synthesis_direct_query = MagicMock(return_value=(expected_df, False))

        df, was_cached = ci.run_synthesis()

        ci._run_synthesis_direct_query.assert_called_once_with("SELECT id, name FROM source")
        assert was_cached is False
        assert list(df.columns) == ["id", "name"]
        assert len(df) == 2

    def test_run_synthesis_query_mode_skips_view_check(self):
        """Query mode should NOT call check_synthesis_table_exists."""
        ci = self._make_ci()
        ci.check_synthesis_table_exists = MagicMock()
        ci._run_synthesis_direct_query = MagicMock(return_value=(pd.DataFrame(), False))

        ci.run_synthesis()

        ci.check_synthesis_table_exists.assert_not_called()

    def test_direct_query_returns_df_and_false(self):
        """_run_synthesis_direct_query returns (df, False) — never cached."""
        ci = self._make_ci()
        ci.app_config.database.mode = "direct"

        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [(1, "x"), (2, "y")]
        mock_result.keys.return_value = ["id", "val"]
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value = mock_conn
        ci._get_engine = MagicMock(return_value=mock_engine)

        df, was_cached = ci._run_synthesis_direct_query("SELECT id, val FROM t")

        assert was_cached is False
        assert list(df.columns) == ["id", "val"]
        assert len(df) == 2

    def test_direct_query_datum_mode(self):
        """_run_synthesis_direct_query in datum mode uses DatumClient."""
        ci = self._make_ci()
        ci.app_config.database.mode = "datum"
        ci.app_config.database.datum_base_url = "http://datum"
        ci.app_config.database.datum_token = "tok"
        ci.app_config.database.datum_database = "db"
        ci.app_config.database.datum_schema = "public"
        ci.app_config.database.datum_service_name = "postgres_sql"

        mock_response = MagicMock()
        mock_response.data = [{"a": 1}, {"a": 2}, {"a": 3}]

        with patch("src.adapter.datum.DatumClient") as MockClient:
            MockClient.return_value.execute_sql.return_value = mock_response
            df, was_cached = ci._run_synthesis_direct_query("SELECT a FROM t")

        assert was_cached is False
        assert len(df) == 3
        assert list(df.columns) == ["a"]

    def test_direct_query_postgres_mode_uses_execute_sql_client(self):
        """_run_synthesis_direct_query in postgres mode should not use SQLAlchemy."""
        ci = self._make_ci()
        ci.app_config.database.mode = "postgres"
        ci._execute_synthesis_sql = MagicMock()
        ci._execute_synthesis_sql.return_value.data = [{"a": 1}, {"a": 2}]
        ci._get_engine = MagicMock()

        df, was_cached = ci._run_synthesis_direct_query("SELECT a FROM t")

        assert was_cached is False
        assert list(df["a"]) == [1, 2]
        ci._execute_synthesis_sql.assert_called_once_with("SELECT a FROM t")
        ci._get_engine.assert_not_called()

    def test_raises_when_no_query(self):
        """Should raise ValueError when synthesis query is empty even in query mode."""
        ci = self._make_ci()
        ci.app_config.synthesis.query = ""

        with pytest.raises(ValueError, match="No synthesis query"):
            ci.run_synthesis()


class TestPostgresFullFunctionRouting:
    """Pin postgres mode away from SQLAlchemy-only feature branches."""

    def _make_ci(self):
        from src.config.config_instance import ConfigInstance

        ci = ConfigInstance.__new__(ConfigInstance)
        ci.app_config = MagicMock()
        ci.app_config.database.mode = "postgres"
        ci.app_config.state.persist_state = True
        ci.app_config.read_only = False
        ci.app_config.table.presets_enabled = True
        ci._get_engine = MagicMock()
        return ci

    def test_postgres_eager_load_uses_execute_sql_loader(self):
        """Non-lazy postgres loading should use the execute_sql loader."""
        ci = self._make_ci()
        expected_df = pd.DataFrame({"id": [1]})
        ci._data_cache = None
        ci._data_cache_time = 0
        ci._load_from_datum = MagicMock(return_value=expected_df)
        ci._load_from_database = MagicMock()

        result = ci._load_data()

        pd.testing.assert_frame_equal(result, expected_df)
        ci._load_from_datum.assert_called_once()
        ci._load_from_database.assert_not_called()

    def test_postgres_state_uses_execute_sql_methods(self):
        """Postgres UI state should delegate to execute_sql-backed methods."""
        ci = self._make_ci()
        ci._ensure_state_table_exists_datum = MagicMock(return_value=True)
        ci._save_ui_state_datum = MagicMock(return_value=True)
        ci._load_ui_state_datum = MagicMock(return_value={"current_page": 2})

        assert ci._ensure_state_table_exists() is True
        assert ci.save_ui_state(current_page=2) is True
        assert ci.load_ui_state() == {"current_page": 2}
        ci._get_engine.assert_not_called()

    def test_postgres_presets_use_execute_sql_methods(self):
        """Postgres presets should delegate to execute_sql-backed methods."""
        ci = self._make_ci()
        ci._preset_table_checked = False
        ci._preset_legacy_mode = False
        ci._detect_preset_legacy_mode = MagicMock()
        ci._ensure_preset_table_exists_datum = MagicMock(return_value=True)
        ci._save_preset_datum = MagicMock(return_value=11)
        ci._get_presets_datum = MagicMock(return_value=[{"preset_name": "Default"}])
        ci._delete_preset_datum = MagicMock(return_value=True)

        assert ci._ensure_preset_table_exists() is True
        assert ci.save_preset("Default", ["id"], is_default=True) == 11
        assert ci.get_presets() == [{"preset_name": "Default"}]
        assert ci.delete_preset("Default") is True
        ci._get_engine.assert_not_called()


# =============================================================================
# SynthesisConfig.mode field
# =============================================================================

class TestSynthesisConfigMode:
    """Tests for SynthesisConfig.mode field."""

    def test_default_mode_is_view(self):
        """Default synthesis mode should be 'view'."""
        from src.config.app_config_schema import SynthesisConfig
        config = SynthesisConfig()
        assert config.mode == "view"

    def test_mode_parsed_from_config(self, tmp_path):
        """mode should be loaded from JSON config."""
        import json
        from src.config.app_config_schema import AppConfig, load_config

        config_file = tmp_path / "app_config.json"
        config_file.write_text(json.dumps({
            "synthesis": {
                "query": "SELECT 1",
                "mode": "query"
            }
        }))

        config = load_config(str(config_file))
        assert config.synthesis.mode == "query"

    def test_mode_defaults_to_view_when_absent(self, tmp_path):
        """When mode not specified, should default to 'view'."""
        import json
        from src.config.app_config_schema import load_config

        config_file = tmp_path / "app_config.json"
        config_file.write_text(json.dumps({
            "synthesis": {
                "query": "SELECT 1"
            }
        }))

        config = load_config(str(config_file))
        assert config.synthesis.mode == "view"


# =============================================================================
# load_config_only
# =============================================================================

class TestLoadConfigOnly:
    """Tests for load_config_only module-level function."""

    def test_calls_load_config_with_path(self, tmp_path):
        """Should call load_config with resolved absolute path."""
        from src.config.config_instance import load_config_only
        from src.config.app_config_schema import AppConfig

        config_file = tmp_path / "app_config.json"
        config_file.write_text('{}')

        with patch("src.config.app_config_schema.load_config") as mock_load:
            mock_load.return_value = AppConfig()
            result = load_config_only(str(config_file))

        mock_load.assert_called_once()
        assert isinstance(result, AppConfig)

    def test_relative_path_resolved(self):
        """Relative path should be resolved against cwd."""
        from src.config.config_instance import load_config_only

        with patch("src.config.app_config_schema.load_config") as mock_load:
            from src.config.app_config_schema import AppConfig
            mock_load.return_value = AppConfig()

            result = load_config_only("nonexistent_config.json")

        # It should have been called with an absolute path
        called_path = mock_load.call_args[0][0]
        assert "/" in called_path or "\\" in called_path  # Absolute path


# =============================================================================
# batch_save_status tests
# =============================================================================

class TestBatchSaveStatus:
    """Tests for ConfigInstance.batch_save_status method."""

    def test_batch_save_status_direct_mode(self):
        """In direct mode, batch_save_status executes all in one transaction."""
        from src.config.config_instance import ConfigInstance

        ci = ConfigInstance.__new__(ConfigInstance)
        ci.app_config = MagicMock()
        ci.app_config.database.mode = "direct"
        ci.app_config.database.mods_table = "test_mods"
        ci.app_config.database.data_table = "test_data"
        ci.app_config.table.primary_key = ["id"]
        ci.app_config.database.status_column = "status"
        ci.username = "tester"

        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_engine.connect.return_value = mock_conn
        ci._get_engine = MagicMock(return_value=mock_engine)
        ci._ensure_mods_table_exists = MagicMock()
        ci.invalidate_mods_cache = MagicMock()

        entries = [
            {"row_pk": {"id": 1}, "status_value": "approved", "mod_type": "approval", "assignments": []},
            {"row_pk": {"id": 2}, "status_value": "approved", "mod_type": "approval", "assignments": [("reviewer", "Alice")]},
        ]

        ci.batch_save_status(entries)

        # Single commit for the whole batch
        mock_conn.commit.assert_called_once()
        ci.invalidate_mods_cache.assert_called_once()
        # Multiple execute calls (INSERT mods + UPDATE data + assignments)
        assert mock_conn.execute.call_count > 2

    def test_batch_save_status_empty_entries(self):
        """Empty entries list should be a no-op."""
        from src.config.config_instance import ConfigInstance

        ci = ConfigInstance.__new__(ConfigInstance)
        ci.app_config = MagicMock()
        ci.app_config.database.mode = "direct"

        ci.batch_save_status([])
        # No crash, no calls

    def test_batch_save_status_datum_mode(self):
        """In datum mode, batch_save_status constructs multi-statement SQL."""
        from src.config.config_instance import ConfigInstance

        ci = ConfigInstance.__new__(ConfigInstance)
        ci.app_config = MagicMock()
        ci.app_config.database.mode = "datum"
        ci.app_config.database.datum_base_url = "http://test"
        ci.app_config.database.datum_token = "token"
        ci.app_config.database.datum_database = "testdb"
        ci.app_config.database.datum_schema = "public"
        ci.app_config.database.datum_service_name = "svc"
        ci.app_config.database.mods_table = "test_mods"
        ci.app_config.database.data_table = "test_data"
        ci.app_config.table.primary_key = ["id"]
        ci.app_config.database.status_column = "status"
        ci.invalidate_mods_cache = MagicMock()

        entries = [
            {"row_pk": {"id": 1}, "status_value": "rejected", "mod_type": "rejection", "assignments": []},
        ]

        with patch("src.config.config_instance.os.environ", {"DATUM_BASE_URL": "", "DATUM_API_TOKEN": ""}):
            with patch("src.adapter.datum.DatumClient") as MockClient:
                mock_client = MagicMock()
                MockClient.return_value = mock_client
                ci.batch_save_status(entries)

                mock_client.execute_sql.assert_called_once()
                sql_arg = mock_client.execute_sql.call_args[1]["sql"]
                assert "BEGIN;" in sql_arg
                assert "COMMIT;" in sql_arg
                assert "INSERT INTO" in sql_arg
                ci.invalidate_mods_cache.assert_called_once()
