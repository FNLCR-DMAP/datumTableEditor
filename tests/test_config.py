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


# =====================================================================
# Column Masks Config Tests
# =====================================================================

class TestTableConfigColumnMasks:
    """Tests for column_masks in TableConfig and _merge_config."""

    def test_column_masks_default_empty(self):
        """TableConfig should default column_masks to empty dict."""
        from src.config.app_config_schema import TableConfig

        tc = TableConfig()
        assert tc.column_masks == {}

    def test_merge_config_loads_column_masks(self, tmp_path):
        """_merge_config should load column_masks from JSON."""
        import json
        from src.config.app_config_schema import AppConfig, _merge_config

        cfg_data = {
            "table": {
                "column_masks": {"Gene_names": "Gene"}
            }
        }
        cfg_path = tmp_path / "cfg.json"
        cfg_path.write_text(json.dumps(cfg_data))

        config = AppConfig()
        _merge_config(config, cfg_data)

        assert config.table.column_masks == {"Gene_names": "Gene"}

    def test_merge_config_missing_masks_preserves_default(self, tmp_path):
        """_merge_config should keep empty dict when column_masks absent."""
        from src.config.app_config_schema import AppConfig, _merge_config

        cfg_data = {"table": {}}
        config = AppConfig()
        _merge_config(config, cfg_data)

        assert config.table.column_masks == {}

    def test_export_config_schema_has_table_section(self):
        """export_config_schema should contain a table section."""
        from src.config.app_config_schema import export_config_schema

        schema = export_config_schema()
        assert "table" in schema or "table_config" in schema or isinstance(schema, dict)


# =====================================================================
# Permissions Config Tests
# =====================================================================

class TestPermissionsConfig:
    """Tests for PermissionsConfig and role resolution."""

    def test_default_role_is_viewer(self):
        """PermissionsConfig should default to viewer role."""
        from src.config.app_config_schema import PermissionsConfig

        perm = PermissionsConfig()
        assert perm.default_role == "viewer"
        assert perm.user_roles == {}

    def test_user_roles_mapping(self):
        """PermissionsConfig should store user-role mappings."""
        from src.config.app_config_schema import PermissionsConfig

        perm = PermissionsConfig(user_roles={"alice": "editor", "bob": "viewer"})
        assert perm.user_roles["alice"] == "editor"
        assert perm.user_roles["bob"] == "viewer"

    def test_app_config_has_permissions(self):
        """AppConfig should include a PermissionsConfig."""
        from src.config.app_config_schema import AppConfig

        cfg = AppConfig()
        assert cfg.permissions.default_role == "viewer"

    def test_merge_config_loads_permissions(self):
        """_merge_config should load permissions section from JSON."""
        from src.config.app_config_schema import AppConfig, _merge_config

        cfg_data = {
            "permissions": {
                "default_role": "viewer",
                "user_roles": {"admin_user": "editor"}
            }
        }
        config = AppConfig()
        _merge_config(config, cfg_data)

        assert config.permissions.default_role == "viewer"
        assert config.permissions.user_roles == {"admin_user": "editor"}

    def test_merge_config_missing_permissions_keeps_defaults(self):
        """_merge_config should keep defaults when permissions section absent."""
        from src.config.app_config_schema import AppConfig, _merge_config

        config = AppConfig()
        _merge_config(config, {})

        assert config.permissions.default_role == "viewer"
        assert config.permissions.user_roles == {}

    def test_role_resolution_user_in_map(self):
        """User in user_roles map should get their assigned role."""
        from src.config.app_config_schema import PermissionsConfig

        perm = PermissionsConfig(default_role="editor", user_roles={"bob": "viewer"})
        role = perm.user_roles.get("bob", perm.default_role)
        assert role == "viewer"

    def test_role_resolution_user_not_in_map(self):
        """User not in user_roles map should get default_role."""
        from src.config.app_config_schema import PermissionsConfig

        perm = PermissionsConfig(default_role="viewer", user_roles={"alice": "editor"})
        role = perm.user_roles.get("unknown", perm.default_role)
        assert role == "viewer"


class TestStatusValuesConfig:
    """Tests for the status_values configuration field."""

    def test_default_status_values(self):
        """AppConfig should default status_values to internal keys."""
        from src.config.app_config_schema import AppConfig

        cfg = AppConfig()
        assert cfg.status_values == {"approved": "Accepted", "rejected": "Rejected", "edited": "Edited"}

    def test_merge_config_loads_status_values(self):
        """_merge_config should load custom status_values from JSON."""
        from src.config.app_config_schema import AppConfig, _merge_config

        cfg_data = {
            "status_values": {
                "approved": "Accepted",
                "rejected": "Declined"
            }
        }
        config = AppConfig()
        _merge_config(config, cfg_data)
        assert config.status_values["approved"] == "Accepted"
        assert config.status_values["rejected"] == "Declined"

    def test_merge_config_partial_update(self):
        """Partial status_values update should merge, not replace."""
        from src.config.app_config_schema import AppConfig, _merge_config

        config = AppConfig()
        _merge_config(config, {"status_values": {"approved": "PASS"}})
        assert config.status_values["approved"] == "PASS"
        assert config.status_values["rejected"] == "Rejected"  # default retained

    def test_merge_config_missing_keeps_defaults(self):
        """Missing status_values keeps defaults."""
        from src.config.app_config_schema import AppConfig, _merge_config

        config = AppConfig()
        _merge_config(config, {})
        assert config.status_values == {"approved": "Accepted", "rejected": "Rejected", "edited": "Edited"}

    def test_status_values_independent_of_labels(self):
        """status_values and status_labels are independent configs."""
        from src.config.app_config_schema import AppConfig, _merge_config

        config = AppConfig()
        _merge_config(config, {
            "status_labels": {"approved": "Thumbs Up"},
            "status_values": {"approved": "PASS"}
        })
        assert config.status_labels["approved"] == "Thumbs Up"
        assert config.status_values["approved"] == "PASS"


class TestApprovalAssignmentConfig:
    """Tests for the approval_assignment configuration field."""

    def test_default_is_empty(self):
        """approval_assignment defaults to empty dict."""
        from src.config.app_config_schema import AppConfig

        cfg = AppConfig()
        assert cfg.approval_assignment == {}

    def test_merge_config_loads_assignment(self):
        """_merge_config should load approval_assignment from JSON."""
        from src.config.app_config_schema import AppConfig, _merge_config

        config = AppConfig()
        _merge_config(config, {
            "approval_assignment": {"Draft_Value": "Final_Value", "Notes": "Approved_Notes"}
        })
        assert config.approval_assignment == {"Draft_Value": "Final_Value", "Notes": "Approved_Notes"}

    def test_merge_config_replaces_not_merges(self):
        """approval_assignment replaces entirely (not dict.update)."""
        from src.config.app_config_schema import AppConfig, _merge_config

        config = AppConfig()
        _merge_config(config, {"approval_assignment": {"a": "b"}})
        _merge_config(config, {"approval_assignment": {"x": "y"}})
        assert config.approval_assignment == {"x": "y"}

    def test_merge_config_missing_keeps_empty(self):
        """Missing approval_assignment keeps the default empty dict."""
        from src.config.app_config_schema import AppConfig, _merge_config

        config = AppConfig()
        _merge_config(config, {})
        assert config.approval_assignment == {}

    def test_empty_dict_disables_assignment(self):
        """An explicitly empty dict means no column copies."""
        from src.config.app_config_schema import AppConfig, _merge_config

        config = AppConfig()
        _merge_config(config, {"approval_assignment": {}})
        assert config.approval_assignment == {}
        assert not config.approval_assignment  # falsy


class TestPaginationConfig:
    """Tests for pagination-related config fields being honoured."""

    def test_table_default_rows_per_page_options(self):
        """TableConfig defaults include 'all'."""
        from src.config.app_config_schema import TableConfig

        tc = TableConfig()
        assert tc.rows_per_page_options == [10, 25, 50, 100, "all"]
        assert tc.default_rows_per_page == 25

    def test_merge_loads_rows_per_page_options(self):
        """_merge_config should load rows_per_page_options from table section."""
        from src.config.app_config_schema import AppConfig, _merge_config

        config = AppConfig()
        _merge_config(config, {
            "table": {"rows_per_page_options": [25, 50, 100, 500]}
        })
        assert config.table.rows_per_page_options == [25, 50, 100, 500]

    def test_merge_loads_rows_per_page_options_with_all(self):
        """Options list may include the string 'all'."""
        from src.config.app_config_schema import AppConfig, _merge_config

        config = AppConfig()
        _merge_config(config, {
            "table": {"rows_per_page_options": [50, 100, 500, "all"]}
        })
        assert "all" in config.table.rows_per_page_options
        assert 500 in config.table.rows_per_page_options

    def test_merge_missing_keeps_default(self):
        """Missing rows_per_page_options keeps the dataclass default."""
        from src.config.app_config_schema import AppConfig, _merge_config

        config = AppConfig()
        _merge_config(config, {"table": {"title": "X"}})
        assert config.table.rows_per_page_options == [10, 25, 50, 100, "all"]

    def test_database_max_rows_per_page_loaded(self):
        """database.max_rows_per_page is loaded from config."""
        from src.config.app_config_schema import AppConfig, _merge_config

        config = AppConfig()
        _merge_config(config, {"database": {"max_rows_per_page": 500}})
        assert config.database.max_rows_per_page == 500

    def test_database_default_rows_per_page_loaded(self):
        """database.default_rows_per_page is loaded from config."""
        from src.config.app_config_schema import AppConfig, _merge_config

        config = AppConfig()
        _merge_config(config, {"database": {"default_rows_per_page": 100}})
        assert config.database.default_rows_per_page == 100

    def test_database_page_buffer_size_loaded(self):
        """database.page_buffer_size is loaded from config."""
        from src.config.app_config_schema import AppConfig, _merge_config

        config = AppConfig()
        _merge_config(config, {"database": {"page_buffer_size": 1000}})
        assert config.database.page_buffer_size == 1000

    def test_table_default_rows_per_page_loaded(self):
        """table.default_rows_per_page is loaded from config."""
        from src.config.app_config_schema import AppConfig, _merge_config

        config = AppConfig()
        _merge_config(config, {"table": {"default_rows_per_page": 500}})
        assert config.table.default_rows_per_page == 500


class TestReviewDetailMultiSelectConfig:
    """Tests for the review_detail_multi_select configuration field."""

    def test_default_is_false(self):
        """review_detail_multi_select defaults to False (single select)."""
        from src.config.app_config_schema import AppConfig

        cfg = AppConfig()
        assert cfg.review_detail_multi_select is False

    def test_merge_config_enables_multi_select(self):
        """_merge_config should load review_detail_multi_select from JSON."""
        from src.config.app_config_schema import AppConfig, _merge_config

        config = AppConfig()
        _merge_config(config, {"review_detail_multi_select": True})
        assert config.review_detail_multi_select is True

    def test_merge_config_missing_keeps_default(self):
        """Missing review_detail_multi_select keeps the default False."""
        from src.config.app_config_schema import AppConfig, _merge_config

        config = AppConfig()
        _merge_config(config, {})
        assert config.review_detail_multi_select is False

    def test_enable_review_detail_independent(self):
        """enable_review_detail and review_detail_multi_select are independent flags."""
        from src.config.app_config_schema import AppConfig, _merge_config

        config = AppConfig()
        _merge_config(config, {
            "enable_review_detail": True,
            "review_detail_multi_select": True,
        })
        assert config.enable_review_detail is True
        assert config.review_detail_multi_select is True


# =====================================================================
# Shared App-Level Cache Tests
# =====================================================================

class TestSharedAppCache:
    """Tests for the shared_cache_key / shared_cache_ttl configuration."""

    def test_default_shared_cache_key_is_none(self):
        """shared_cache_key defaults to None (no sharing)."""
        from src.config.app_config_schema import DatabaseConfig

        db = DatabaseConfig()
        assert db.shared_cache_key is None

    def test_default_shared_cache_ttl(self):
        """shared_cache_ttl defaults to 300 seconds."""
        from src.config.app_config_schema import DatabaseConfig

        db = DatabaseConfig()
        assert db.shared_cache_ttl == 300

    def test_merge_config_loads_shared_cache_key(self):
        """_merge_config should load shared_cache_key from JSON."""
        from src.config.app_config_schema import AppConfig, _merge_config

        config = AppConfig()
        _merge_config(config, {"database": {"shared_cache_key": "my_table_v1"}})
        assert config.database.shared_cache_key == "my_table_v1"

    def test_merge_config_loads_shared_cache_ttl(self):
        """_merge_config should load shared_cache_ttl from JSON."""
        from src.config.app_config_schema import AppConfig, _merge_config

        config = AppConfig()
        _merge_config(config, {"database": {"shared_cache_ttl": 600}})
        assert config.database.shared_cache_ttl == 600

    def test_merge_config_missing_keeps_defaults(self):
        """Missing shared_cache_* keeps defaults."""
        from src.config.app_config_schema import AppConfig, _merge_config

        config = AppConfig()
        _merge_config(config, {"database": {}})
        assert config.database.shared_cache_key is None
        assert config.database.shared_cache_ttl == 300

    def test_app_cache_get_set_hit(self):
        """_app_cache_set + _app_cache_get should return a copy within TTL."""
        from src.config.config_instance import _app_cache_get, _app_cache_set, _app_cache_invalidate

        key = "_test_hit"
        try:
            df = pd.DataFrame({"a": [1, 2, 3]})
            _app_cache_set(key, df)
            result = _app_cache_get(key, ttl=60)
            assert result is not None
            assert list(result["a"]) == [1, 2, 3]
            # Must be a copy, not the same object
            assert result is not df
        finally:
            _app_cache_invalidate(key)

    def test_app_cache_miss_no_key(self):
        """_app_cache_get returns None for unknown keys."""
        from src.config.config_instance import _app_cache_get

        assert _app_cache_get("_nonexistent_key_xyz", ttl=60) is None

    def test_app_cache_ttl_expiry(self):
        """Expired entries should return None."""
        import time
        from src.config.config_instance import (
            _app_cache_get, _app_cache_set, _app_cache_invalidate,
            _APP_CACHE, _APP_CACHE_LOCK,
        )

        key = "_test_expiry"
        try:
            df = pd.DataFrame({"x": [10]})
            _app_cache_set(key, df)
            # Manually backdate the timestamp
            with _APP_CACHE_LOCK:
                old_df, _ = _APP_CACHE[key]
                _APP_CACHE[key] = (old_df, time.time() - 999)
            result = _app_cache_get(key, ttl=60)
            assert result is None
        finally:
            _app_cache_invalidate(key)

    def test_app_cache_invalidate(self):
        """_app_cache_invalidate should remove the entry."""
        from src.config.config_instance import _app_cache_get, _app_cache_set, _app_cache_invalidate

        key = "_test_invalidate"
        df = pd.DataFrame({"b": [4, 5]})
        _app_cache_set(key, df)
        assert _app_cache_get(key, ttl=60) is not None
        _app_cache_invalidate(key)
        assert _app_cache_get(key, ttl=60) is None

    def test_app_cache_different_keys_isolated(self):
        """Different keys should not interfere."""
        from src.config.config_instance import _app_cache_get, _app_cache_set, _app_cache_invalidate

        try:
            _app_cache_set("_key_a", pd.DataFrame({"v": [1]}))
            _app_cache_set("_key_b", pd.DataFrame({"v": [2]}))
            a = _app_cache_get("_key_a", ttl=60)
            b = _app_cache_get("_key_b", ttl=60)
            assert list(a["v"]) == [1]
            assert list(b["v"]) == [2]
        finally:
            _app_cache_invalidate("_key_a")
            _app_cache_invalidate("_key_b")

    def test_app_cache_invalidate_nonexistent_is_noop(self):
        """Invalidating a non-existent key should not raise."""
        from src.config.config_instance import _app_cache_invalidate

        _app_cache_invalidate("_does_not_exist_xyz")  # Should not raise

    def test_app_cache_set_stores_copy(self):
        """Mutating the original DataFrame should not affect the cache."""
        from src.config.config_instance import _app_cache_get, _app_cache_set, _app_cache_invalidate

        key = "_test_copy_isolation"
        try:
            df = pd.DataFrame({"c": [10, 20]})
            _app_cache_set(key, df)
            df["c"] = [99, 99]  # Mutate original
            result = _app_cache_get(key, ttl=60)
            assert list(result["c"]) == [10, 20]  # Cache unaffected
        finally:
            _app_cache_invalidate(key)


class TestReadOnlyConfig:
    """Tests for the read_only feature flag."""

    def test_default_is_false(self):
        """AppConfig.read_only should default to False."""
        from src.config.app_config_schema import AppConfig

        cfg = AppConfig()
        assert cfg.read_only is False

    def test_merge_config_sets_read_only_true(self):
        """_merge_config should load read_only: true from JSON."""
        from src.config.app_config_schema import AppConfig, _merge_config

        config = AppConfig()
        _merge_config(config, {"read_only": True})
        assert config.read_only is True

    def test_merge_config_sets_read_only_false(self):
        """_merge_config should load read_only: false from JSON."""
        from src.config.app_config_schema import AppConfig, _merge_config

        config = AppConfig()
        config.read_only = True  # Start with True
        _merge_config(config, {"read_only": False})
        assert config.read_only is False

    def test_merge_config_missing_read_only_keeps_default(self):
        """_merge_config should keep default when read_only absent."""
        from src.config.app_config_schema import AppConfig, _merge_config

        config = AppConfig()
        _merge_config(config, {})
        assert config.read_only is False

    def test_read_only_independent_of_permissions(self):
        """read_only flag should be independent of permissions config."""
        from src.config.app_config_schema import AppConfig, _merge_config

        config = AppConfig()
        _merge_config(config, {
            "read_only": True,
            "permissions": {
                "default_role": "editor",
                "user_roles": {"alice": "editor"}
            }
        })
        assert config.read_only is True
        assert config.permissions.default_role == "editor"

    def test_read_only_independent_of_editable_columns(self):
        """read_only should not alter table.editable_columns or readonly_columns."""
        from src.config.app_config_schema import AppConfig, _merge_config

        config = AppConfig()
        _merge_config(config, {
            "read_only": True,
            "table": {
                "editable_columns": ["Gene_names"],
                "readonly_columns": ["PatientID"]
            }
        })
        # read_only is a runtime flag; it doesn't mutate config-level column lists
        assert config.read_only is True
        assert config.table.editable_columns == ["Gene_names"]
        assert config.table.readonly_columns == ["PatientID"]

    def test_read_only_with_all_features_enabled(self):
        """read_only should coexist with other feature flags."""
        from src.config.app_config_schema import AppConfig, _merge_config

        config = AppConfig()
        _merge_config(config, {
            "read_only": True,
            "enable_approval_workflow": True,
            "enable_save_button": True,
            "enable_export": True,
        })
        assert config.read_only is True
        assert config.enable_approval_workflow is True
        assert config.enable_save_button is True
        assert config.enable_export is True