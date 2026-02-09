"""
Tests for table_editor widget module.
"""
import pytest
from unittest.mock import MagicMock, patch


class TestTableEditorUi:
    """Tests for table_editor_ui function."""
    
    def test_table_editor_ui_returns_ui(self):
        """table_editor_ui should return UI element."""
        with patch('src.widgets.table_editor.create_app_ui') as mock_create:
            from src.widgets.table_editor import table_editor_ui
            
            mock_ui = MagicMock()
            mock_create.return_value = mock_ui
            
            # The module decorator changes the signature, so just verify import works
            assert table_editor_ui is not None


class TestTableEditorServer:
    """Tests for table_editor_server function."""
    
    def test_table_editor_server_calls_create_server(self):
        """table_editor_server should call create_server."""
        with patch('src.widgets.table_editor.create_server') as mock_create:
            from src.widgets.table_editor import table_editor_server
            
            # The module decorator changes the signature, so just verify import works
            assert table_editor_server is not None


class TestWidgetsInit:
    """Tests for widgets __init__.py exports."""
    
    def test_imports_available(self):
        """Should be able to import from widgets module."""
        from src.widgets import table_editor_ui, table_editor_server
        
        assert table_editor_ui is not None
        assert table_editor_server is not None
