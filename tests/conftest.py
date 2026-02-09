"""
Pytest configuration and shared fixtures for dmapTableEditor tests.

Provides mock database connections, sample data, and common test utilities.
"""

import pytest
import pandas as pd
import json
from unittest.mock import MagicMock, patch, PropertyMock
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Any


# =============================================================================
# Sample Test Data
# =============================================================================

@pytest.fixture
def sample_data():
    """Sample DataFrame mimicking epitopes data."""
    return pd.DataFrame({
        "PatientID_Mutsequence": ["PK001", "PK002", "PK003", "PK004", "PK005"],
        "PatientID": ["PAT001", "PAT002", "PAT003", "PAT004", "PAT005"],
        "Gene_names": ["BRCA1", "TP53", "EGFR", "PTEN", "RB1"],
        "Variant_key": ["VAR_001", "VAR_002", "VAR_003", "VAR_004", "VAR_005"],
        "Wt_nmer": ["ABCDEFGH", "IJKLMNOP", "QRSTUVWX", "YZABCDEF", "GHIJKLMN"],
        "Mut_nmer": ["ABXDEFGH", "IJXLMNOP", "QRXTUVWX", "YZXBCDEF", "GHXJKLMN"],
        "Status": ["Pending", "Reviewed", "Pending", "Approved", "Pending"],
        "Comments": ["", "Needs review", "", "Good", ""],
        "_mod_status": ["unprocessed", "edited", "unprocessed", "approved", "rejected"],
    })


@pytest.fixture
def sample_modifications():
    """Sample modifications log entries."""
    return [
        {
            "db_id": 1,
            "timestamp": "2026-02-08T10:00:00",
            "type": "field_modification",
            "undone": False,
            "details": {
                "row_pk": {"PatientID_Mutsequence": "PK002"},
                "column": "Gene_names",
                "old_value": "TP53",
                "new_value": "TP53_edited",
                "created_by": "testuser"
            }
        },
        {
            "db_id": 2,
            "timestamp": "2026-02-08T10:05:00",
            "type": "approval",
            "undone": False,
            "details": {
                "action": "approved",
                "approved_rows": [{"PatientID_Mutsequence": "PK004"}],
                "approved_row_count": 1,
            }
        },
        {
            "db_id": 3,
            "timestamp": "2026-02-08T10:10:00",
            "type": "rejection",
            "undone": False,
            "details": {
                "action": "rejected",
                "rejected_rows": [{"PatientID_Mutsequence": "PK005"}],
                "rejected_row_count": 1,
            }
        },
    ]


@pytest.fixture
def sample_field_modifications_db():
    """Sample field modifications as returned from database query."""
    return [
        # (row_pk, column_name, old_value, new_value)
        ({"PatientID_Mutsequence": "PK002"}, "Gene_names", "TP53", "TP53_edited"),
        ({"PatientID_Mutsequence": "PK003"}, "Status", "Pending", "Reviewed"),
    ]


@pytest.fixture
def primary_key_columns():
    """Primary key column names."""
    return ["PatientID_Mutsequence"]


# =============================================================================
# Mock App Configuration
# =============================================================================

@dataclass
class MockTableConfig:
    primary_key: List[str]
    default_columns: List[str]
    default_sort_column: str = "PatientID"
    default_sort_ascending: bool = True
    default_rows_per_page: int = 25
    title: str = "Test Table"


@dataclass
class MockDatabaseConfig:
    enabled: bool = True
    mode: str = "direct"
    connection_string: str = "postgresql://test:test@localhost/testdb"
    data_table: str = "test_data"
    mods_table: str = "test_modifications"
    state_table: str = "test_ui_state"
    datum_base_url: str = ""
    datum_token: str = ""
    datum_database: str = ""
    datum_schema: str = ""
    datum_service_name: str = ""


@dataclass
class MockPersistenceConfig:
    modifications_log_path: str = "data/modifications_log.json"


@dataclass
class MockAppConfig:
    table: MockTableConfig
    database: MockDatabaseConfig
    persistence: MockPersistenceConfig


@pytest.fixture
def mock_app_config(primary_key_columns):
    """Mock application configuration."""
    return MockAppConfig(
        table=MockTableConfig(
            primary_key=primary_key_columns,
            default_columns=["PatientID", "Gene_names", "Variant_key", "Status"],
        ),
        database=MockDatabaseConfig(),
        persistence=MockPersistenceConfig(),
    )


# =============================================================================
# Database Mocks
# =============================================================================

@pytest.fixture
def mock_db_engine():
    """Mock SQLAlchemy engine."""
    engine = MagicMock()
    return engine


@pytest.fixture
def mock_db_connection(sample_data, sample_field_modifications_db):
    """Mock database connection with execute capabilities."""
    conn = MagicMock()
    
    def mock_execute(query, params=None):
        result = MagicMock()
        query_str = str(query) if hasattr(query, 'text') else str(query)
        
        # Return different results based on query content
        if "SELECT d.*" in query_str or "FROM test_data" in query_str:
            # Main data query
            result.fetchall.return_value = [tuple(row) for _, row in sample_data.iterrows()]
            result.keys.return_value = sample_data.columns.tolist()
        elif "mod_type = 'field_modification'" in query_str:
            # Field modifications query
            result.fetchall.return_value = sample_field_modifications_db
        elif "INSERT INTO" in query_str:
            # Insert modification
            result.scalar.return_value = 999  # New modification ID
        elif "UPDATE" in query_str:
            # Update query
            pass
        else:
            result.fetchall.return_value = []
            result.keys.return_value = []
        
        return result
    
    conn.execute = mock_execute
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    
    return conn


@pytest.fixture
def mock_engine_with_connection(mock_db_engine, mock_db_connection):
    """Mock engine that returns mock connection."""
    mock_db_engine.connect.return_value = mock_db_connection
    return mock_db_engine


# =============================================================================
# Config Instance Mocks
# =============================================================================

@pytest.fixture
def mock_config_instance(sample_data, mock_app_config, primary_key_columns):
    """Mock ConfigInstance for testing."""
    from unittest.mock import MagicMock
    
    config = MagicMock()
    config.app_config = mock_app_config
    config.df = sample_data.copy()
    config.all_columns = sample_data.columns.tolist()
    config.display_columns = ["PatientID", "Gene_names", "Variant_key", "Status"]
    config.username = "testuser"
    
    # Set up edited_cells with PK-based keys
    pk_tuple_1 = (("PatientID_Mutsequence", "PK002"),)
    config.edited_cells = {
        (pk_tuple_1, "Gene_names"): {"original": "TP53", "current": "TP53_edited"}
    }
    
    config.get_edited_cells.return_value = config.edited_cells
    
    def is_cell_edited(row_pk, col_name):
        pk_tuple = tuple(sorted((k, str(v)) for k, v in row_pk.items()))
        return (pk_tuple, col_name) in config.edited_cells
    
    def get_original_value(row_pk, col_name):
        pk_tuple = tuple(sorted((k, str(v)) for k, v in row_pk.items()))
        cell_info = config.edited_cells.get((pk_tuple, col_name))
        return cell_info.get("original") if cell_info else None
    
    config.is_cell_edited = is_cell_edited
    config.get_original_value = get_original_value
    
    # Mock save_modification_to_db
    config.save_modification_to_db.return_value = 999
    
    return config


# =============================================================================
# Shiny Test Utilities
# =============================================================================

@pytest.fixture
def mock_shiny_session():
    """Mock Shiny session object."""
    session = MagicMock()
    session.user = "testuser"
    session.send_input_message = MagicMock()
    return session


@pytest.fixture
def mock_reactive_value():
    """Factory for mock reactive values."""
    def create_reactive(initial_value):
        rv = MagicMock()
        rv._value = initial_value
        rv.get = MagicMock(return_value=initial_value)
        
        def set_value(new_val):
            rv._value = new_val
            rv.get.return_value = new_val
        
        rv.set = set_value
        return rv
    
    return create_reactive


# =============================================================================
# File System Mocks
# =============================================================================

@pytest.fixture
def mock_file_system(tmp_path):
    """Create temporary file system structure for tests."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    
    # Create empty state files
    (data_dir / "ui_state.json").write_text("{}")
    (data_dir / "data_state.json").write_text("[]")
    (data_dir / "modifications_log.json").write_text("[]")
    
    return tmp_path


@pytest.fixture
def mock_presets_file(tmp_path):
    """Create mock presets file."""
    presets = {
        "test_table": {
            "testuser": {
                "Default": ["PatientID", "Gene_names", "Variant_key", "Status"],
                "Minimal": ["PatientID", "Status"],
            }
        }
    }
    presets_path = tmp_path / "presets.json"
    presets_path.write_text(json.dumps(presets))
    return presets_path


# =============================================================================
# Helper Functions
# =============================================================================

def create_pk_tuple(pk_dict: dict) -> tuple:
    """Create a hashable PK tuple from a PK dictionary."""
    return tuple(sorted((k, str(v)) for k, v in pk_dict.items()))


def create_cell_key(pk_dict: dict, col_name: str) -> tuple:
    """Create an edited_cells key from PK dict and column name."""
    return (create_pk_tuple(pk_dict), col_name)


# Make helper functions available as fixtures
@pytest.fixture
def pk_tuple_helper():
    return create_pk_tuple


@pytest.fixture
def cell_key_helper():
    return create_cell_key
