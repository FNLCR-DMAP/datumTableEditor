"""
Tests for preset_utils with mocked ConfigInstance.
"""
import pytest
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path
import json
import tempfile


def _make_mock_config(presets=None, default_preset_name=None):
    """Create a mock ConfigInstance with preset methods."""
    mock = MagicMock()
    mock.username = "testuser"
    mock._get_preset_table_name.return_value = "test_table_testuser_column_presets"

    if presets is None:
        presets = []
    mock.get_presets.return_value = presets

    if default_preset_name:
        mock.get_default_preset.return_value = {"preset_name": default_preset_name}
    else:
        mock.get_default_preset.return_value = None

    return mock


class TestLoadPresets:
    """Tests for load_presets function."""

    def test_load_presets_returns_default_when_empty(self):
        """Should return default preset when DB has no presets."""
        from src.utils.preset_utils import load_presets

        mock_config = _make_mock_config(presets=[])
        result = load_presets(mock_config, ["X", "Y", "Z"])

        assert result == {"Default": {"columns": ["X", "Y", "Z"], "widths": {}}}

    def test_load_presets_from_database(self):
        """Should load user presets from DB, Default from config."""
        from src.utils.preset_utils import load_presets

        mock_config = _make_mock_config(presets=[
            {"preset_name": "Custom", "columns": ["C"], "is_default": False}
        ])

        result = load_presets(mock_config, ["A", "B"])

        assert "Default" in result
        # Default comes from config, not DB
        assert result["Default"]["columns"] == ["A", "B"]
        assert "Custom" in result
        mock_config.get_presets.assert_called_once()

    def test_load_presets_ignores_default_in_db(self):
        """Should ignore Default row if it exists in DB and use config instead."""
        from src.utils.preset_utils import load_presets

        mock_config = _make_mock_config(presets=[
            {"preset_name": "Default", "columns": ["OLD"], "is_default": True},
            {"preset_name": "Custom", "columns": ["C"], "is_default": False}
        ])

        result = load_presets(mock_config, ["CONFIG_COL"])

        # Default must come from config, not the DB row
        assert result["Default"]["columns"] == ["CONFIG_COL"]
        assert "Custom" in result

    def test_load_presets_handles_nested_columns_format(self):
        """Should handle DB format with nested columns/widths."""
        from src.utils.preset_utils import load_presets

        mock_config = _make_mock_config(presets=[
            {"preset_name": "Nested", "columns": {"columns": ["A", "B"], "widths": {"A": 100}}}
        ])

        result = load_presets(mock_config, ["A", "B"])

        assert "Nested" in result
        assert result["Nested"]["columns"] == ["A", "B"]
        assert result["Nested"]["widths"] == {"A": 100}

    def test_load_presets_adds_default_if_missing(self):
        """Should add Default preset if not in DB results."""
        from src.utils.preset_utils import load_presets

        mock_config = _make_mock_config(presets=[
            {"preset_name": "Custom", "columns": ["C"]}
        ])

        result = load_presets(mock_config, ["X", "Y"])

        assert "Default" in result
        assert "Custom" in result

    def test_load_presets_error_returns_default(self):
        """Should return default preset on error."""
        from src.utils.preset_utils import load_presets

        mock_config = _make_mock_config()
        mock_config.get_presets.side_effect = Exception("DB error")

        result = load_presets(mock_config, ["A", "B"])

        assert result == {"Default": {"columns": ["A", "B"], "widths": {}}}


class TestSavePresets:
    """Tests for save_presets function."""

    def test_save_presets_skips_default(self):
        """Should only save non-Default presets to DB."""
        from src.utils.preset_utils import save_presets

        mock_config = _make_mock_config(presets=[])

        presets_dict = {
            "Default": {"columns": ["A", "B"], "widths": {}},
            "Custom": {"columns": ["C"], "widths": {}}
        }

        save_presets(mock_config, presets_dict)

        # Only Custom should be saved, Default is config-driven
        assert mock_config.save_preset.call_count == 1
        mock_config.save_preset.assert_called_once()
        call_args = mock_config.save_preset.call_args
        assert call_args[0][0] == "Custom"

    def test_save_presets_deletes_removed_user_presets(self):
        """Should delete user presets removed from dict."""
        from src.utils.preset_utils import save_presets

        mock_config = _make_mock_config(presets=[
            {"preset_name": "ToDelete", "is_default": False, "columns": ["B"]}
        ])

        presets_dict = {"Default": {"columns": ["A"], "widths": {}}}

        save_presets(mock_config, presets_dict)

        mock_config.delete_preset.assert_called_once_with("ToDelete")

    def test_save_presets_error_does_not_raise(self):
        """Should catch errors gracefully."""
        from src.utils.preset_utils import save_presets

        mock_config = _make_mock_config()
        mock_config.get_presets.side_effect = Exception("DB error")

        # Should not raise
        save_presets(mock_config, {"Default": {"columns": ["A"], "widths": {}}})


class TestLoadActivePreset:
    """Tests for load_active_preset function."""

    def test_load_active_preset_returns_name(self):
        """Should return preset name from ConfigInstance."""
        from src.utils.preset_utils import load_active_preset

        mock_config = _make_mock_config(default_preset_name="CustomDefault")

        result = load_active_preset(mock_config)

        assert result == "CustomDefault"

    def test_load_active_preset_default_when_none(self):
        """Should return 'Default' when no default in database."""
        from src.utils.preset_utils import load_active_preset

        mock_config = _make_mock_config(default_preset_name=None)

        result = load_active_preset(mock_config)

        assert result == "Default"

    def test_load_active_preset_error_returns_default(self):
        """Should return 'Default' on error."""
        from src.utils.preset_utils import load_active_preset

        mock_config = _make_mock_config()
        mock_config.get_default_preset.side_effect = Exception("DB error")

        result = load_active_preset(mock_config)

        assert result == "Default"


class TestSaveActivePreset:
    """Tests for save_active_preset function."""

    def test_save_active_preset_updates_defaults(self):
        """Should update is_default flag on user presets only."""
        from src.utils.preset_utils import save_active_preset

        mock_config = _make_mock_config(presets=[
            {"preset_name": "Preset1", "is_default": True, "columns": ["A"]},
            {"preset_name": "Custom", "is_default": False, "columns": ["B"]}
        ])

        save_active_preset(mock_config, "Custom")

        # Should have called save_preset to update is_default flags on user presets
        assert mock_config.save_preset.call_count == 2

    def test_save_active_preset_to_default_clears_flags(self):
        """Setting active to Default should clear all is_default flags."""
        from src.utils.preset_utils import save_active_preset

        mock_config = _make_mock_config(presets=[
            {"preset_name": "Custom", "is_default": True, "columns": ["A"]}
        ])

        save_active_preset(mock_config, "Default")

        # Custom should have is_default cleared
        mock_config.save_preset.assert_called_once_with("Custom", ["A"], is_default=False)

    def test_save_active_preset_error_does_not_raise(self):
        """Should catch errors gracefully."""
        from src.utils.preset_utils import save_active_preset

        mock_config = _make_mock_config()
        mock_config.get_presets.side_effect = Exception("DB error")

        # Should not raise
        save_active_preset(mock_config, "TestPreset")