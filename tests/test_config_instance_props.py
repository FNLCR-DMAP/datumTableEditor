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

    def test_direct_mode_executes_update(self):
        """In direct mode, should execute SQL UPDATE with PK WHERE clause."""
        from src.config.config_instance import ConfigInstance

        ci = ConfigInstance.__new__(ConfigInstance)
        ci.app_config = MagicMock()
        ci.app_config.database.mode = "direct"
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
                result = load_config_instance("test_config.json", "testuser")

                assert isinstance(result, ConfigInstance)
                mock_init.assert_called_once_with(config_path="test_config.json", username="testuser")
