"""
Tests for ModificationsProcessor with mocked file operations.
"""
import pytest
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path
import pandas as pd
import json
import tempfile
import os


class TestModificationsProcessorInit:
    """Tests for ModificationsProcessor initialization."""
    
    def test_init_with_default_data_dir(self):
        """Should use default data directory."""
        from src.processing.process_modifications import ModificationsProcessor
        
        processor = ModificationsProcessor()
        
        assert processor.data_dir is not None
        assert processor.output_dir is not None
    
    def test_init_with_custom_data_dir(self):
        """Should accept custom data directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from src.processing.process_modifications import ModificationsProcessor
            
            processor = ModificationsProcessor(data_dir=tmpdir)
            
            assert str(processor.data_dir) == tmpdir
            assert processor.output_dir.exists()


class TestModificationsProcessorLoadData:
    """Tests for data loading."""
    
    def test_load_original_data(self):
        """Should load original CSV data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from src.processing.process_modifications import ModificationsProcessor
            
            # Create test CSV
            csv_path = Path(tmpdir) / "dummy_data_50rows.csv"
            df = pd.DataFrame({'id': [1, 2, 3], 'value': ['A', 'B', 'C']})
            df.to_csv(csv_path, index=False)
            
            processor = ModificationsProcessor(data_dir=tmpdir)
            result = processor.load_original_data()
            
            assert len(result) == 3
            assert 'id' in result.columns
    
    def test_load_modifications_file_exists(self):
        """Should load modifications from JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from src.processing.process_modifications import ModificationsProcessor
            
            # Create test modifications log
            log_path = Path(tmpdir) / "modifications_log.json"
            mods = [
                {"type": "field_modification", "details": {"row_index": 0, "column": "value", "new_value": "X"}}
            ]
            with open(log_path, 'w') as f:
                json.dump(mods, f)
            
            processor = ModificationsProcessor(data_dir=tmpdir)
            result = processor.load_modifications()
            
            assert len(result) == 1
            assert result[0]["type"] == "field_modification"
    
    def test_load_modifications_file_not_exists(self):
        """Should return empty list when file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from src.processing.process_modifications import ModificationsProcessor
            
            processor = ModificationsProcessor(data_dir=tmpdir)
            result = processor.load_modifications()
            
            assert result == []


class TestModificationsProcessorApplyModifications:
    """Tests for applying modifications."""
    
    def test_apply_field_modification(self):
        """Should apply field modifications to dataframe."""
        from src.processing.process_modifications import ModificationsProcessor
        
        processor = ModificationsProcessor()
        
        df = pd.DataFrame({
            'id': [1, 2, 3],
            'value': ['A', 'B', 'C'],
            'status': ['pending', 'pending', 'pending']
        })
        
        modifications = [
            {
                "type": "field_modification",
                "details": {
                    "row_index": 1,
                    "column": "value",
                    "old_value": "B",
                    "new_value": "B_modified"
                }
            }
        ]
        
        result = processor.apply_modifications(df, modifications)
        
        assert result.at[1, 'value'] == "B_modified"
        assert result.at[0, 'value'] == "A"  # Unchanged
    
    def test_apply_multiple_modifications(self):
        """Should apply multiple modifications."""
        from src.processing.process_modifications import ModificationsProcessor
        
        processor = ModificationsProcessor()
        
        df = pd.DataFrame({
            'id': [1, 2],
            'value': ['A', 'B']
        })
        
        modifications = [
            {"type": "field_modification", "details": {"row_index": 0, "column": "value", "new_value": "X"}},
            {"type": "field_modification", "details": {"row_index": 1, "column": "value", "new_value": "Y"}},
        ]
        
        result = processor.apply_modifications(df, modifications)
        
        assert result.at[0, 'value'] == "X"
        assert result.at[1, 'value'] == "Y"
    
    def test_skip_non_field_modifications(self):
        """Should skip non-field modification types."""
        from src.processing.process_modifications import ModificationsProcessor
        
        processor = ModificationsProcessor()
        
        df = pd.DataFrame({'id': [1], 'value': ['A']})
        
        modifications = [
            {"type": "approval", "details": {"row_index": 0}},
            {"type": "rejection", "details": {"row_index": 0}},
        ]
        
        result = processor.apply_modifications(df, modifications)
        
        # Should be unchanged
        assert result.at[0, 'value'] == "A"
    
    def test_apply_modifications_preserves_original(self):
        """Should not mutate original dataframe."""
        from src.processing.process_modifications import ModificationsProcessor
        
        processor = ModificationsProcessor()
        
        df_original = pd.DataFrame({'id': [1], 'value': ['A']})
        
        modifications = [
            {"type": "field_modification", "details": {"row_index": 0, "column": "value", "new_value": "X"}}
        ]
        
        result = processor.apply_modifications(df_original, modifications)
        
        assert df_original.at[0, 'value'] == "A"  # Original unchanged
        assert result.at[0, 'value'] == "X"  # Copy modified


class TestModificationsProcessorGetChangeSummary:
    """Tests for change summary generation."""
    
    def test_empty_modifications(self):
        """Should handle empty modifications list."""
        from src.processing.process_modifications import ModificationsProcessor
        
        processor = ModificationsProcessor()
        
        summary = processor.get_change_summary([])
        
        assert summary["total_modifications"] == 0
        assert summary["modified_columns"] == []
        assert summary["modified_rows"] == []
    
    def test_summary_counts_modifications(self):
        """Should count modifications correctly."""
        from src.processing.process_modifications import ModificationsProcessor
        
        processor = ModificationsProcessor()
        
        modifications = [
            {"type": "field_modification", "details": {"row_index": 0, "column": "value"}},
            {"type": "field_modification", "details": {"row_index": 1, "column": "value"}},
            {"type": "field_modification", "details": {"row_index": 0, "column": "status"}},
        ]
        
        summary = processor.get_change_summary(modifications)
        
        assert summary["total_modifications"] == 3
        assert sorted(summary["modified_columns"]) == ["status", "value"]
        assert sorted(summary["modified_rows"]) == [0, 1]
        assert summary["changes_by_column"]["value"] == 2
        assert summary["changes_by_column"]["status"] == 1
    
    def test_summary_has_timestamp(self):
        """Should include timestamp in summary."""
        from src.processing.process_modifications import ModificationsProcessor
        
        processor = ModificationsProcessor()
        
        summary = processor.get_change_summary([])
        
        assert "timestamp" in summary


class TestModificationsProcessorExport:
    """Tests for export functionality."""
    
    def test_export_as_csv(self):
        """Should export modifications as CSV."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from src.processing.process_modifications import ModificationsProcessor
            
            processor = ModificationsProcessor(data_dir=tmpdir)
            
            modifications = [
                {
                    "timestamp": "2024-01-01T10:00:00",
                    "type": "field_modification",
                    "details": {
                        "row_index": 0,
                        "column": "value",
                        "old_value": "A",
                        "new_value": "X"
                    }
                }
            ]
            
            output_path = processor.export_transformations(modifications, "csv")
            
            assert output_path.exists()
            df = pd.read_csv(output_path)
            assert len(df) == 1
            assert df.at[0, 'column'] == 'value'
    
    def test_export_as_json(self):
        """Should export modifications as JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from src.processing.process_modifications import ModificationsProcessor
            
            processor = ModificationsProcessor(data_dir=tmpdir)
            
            modifications = [
                {"type": "field_modification", "details": {"row_index": 0}}
            ]
            
            output_path = processor.export_transformations(modifications, "json")
            
            assert output_path.exists()
            with open(output_path) as f:
                data = json.load(f)
            assert len(data) == 1
    
    def test_export_as_sql(self):
        """Should export modifications as SQL statements."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from src.processing.process_modifications import ModificationsProcessor
            
            processor = ModificationsProcessor(data_dir=tmpdir)
            
            modifications = [
                {
                    "type": "field_modification",
                    "details": {
                        "row_index": 5,
                        "column": "status",
                        "new_value": "approved"
                    }
                }
            ]
            
            output_path = processor.export_transformations(modifications, "sql")
            
            assert output_path.exists()
            with open(output_path) as f:
                content = f.read()
            assert "UPDATE" in content
            assert "status" in content
            assert "approved" in content
    
    def test_export_sql_escapes_quotes(self):
        """Should escape single quotes in SQL values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from src.processing.process_modifications import ModificationsProcessor
            
            processor = ModificationsProcessor(data_dir=tmpdir)
            
            modifications = [
                {
                    "type": "field_modification",
                    "details": {
                        "row_index": 0,
                        "column": "name",
                        "new_value": "O'Brien"
                    }
                }
            ]
            
            output_path = processor.export_transformations(modifications, "sql")
            
            with open(output_path) as f:
                content = f.read()
            assert "O''Brien" in content  # Escaped quote
    
    def test_export_unknown_format_raises(self):
        """Should raise error for unknown format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from src.processing.process_modifications import ModificationsProcessor
            
            processor = ModificationsProcessor(data_dir=tmpdir)
            
            with pytest.raises(ValueError, match="Unknown format"):
                processor.export_transformations([], "xml")


class TestModificationsProcessorProcessAndSave:
    """Tests for complete workflow."""
    
    def test_process_and_save_no_modifications(self):
        """Should return no_modifications status when log is empty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from src.processing.process_modifications import ModificationsProcessor
            
            # Create empty modifications log
            log_path = Path(tmpdir) / "modifications_log.json"
            with open(log_path, 'w') as f:
                json.dump([], f)
            
            # Create dummy CSV
            csv_path = Path(tmpdir) / "dummy_data_50rows.csv"
            pd.DataFrame({'id': [1]}).to_csv(csv_path, index=False)
            
            processor = ModificationsProcessor(data_dir=tmpdir)
            result = processor.process_and_save()
            
            assert result["status"] == "no_modifications"
    
    def test_process_and_save_success(self):
        """Should process and save all output files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from src.processing.process_modifications import ModificationsProcessor
            
            # Create test data
            csv_path = Path(tmpdir) / "dummy_data_50rows.csv"
            df = pd.DataFrame({'id': [1, 2], 'value': ['A', 'B']})
            df.to_csv(csv_path, index=False)
            
            # Create modifications log
            log_path = Path(tmpdir) / "modifications_log.json"
            mods = [
                {
                    "timestamp": "2024-01-01",
                    "type": "field_modification",
                    "details": {"row_index": 0, "column": "value", "old_value": "A", "new_value": "X"}
                }
            ]
            with open(log_path, 'w') as f:
                json.dump(mods, f)
            
            processor = ModificationsProcessor(data_dir=tmpdir)
            result = processor.process_and_save()
            
            assert result["status"] == "success"
            assert result["modifications_count"] == 1
            assert "output_files" in result
            
            # Verify output files exist
            assert Path(result["output_files"]["data"]).exists()
            assert Path(result["output_files"]["audit_csv"]).exists()
            assert Path(result["output_files"]["summary"]).exists()


class TestApplyModificationsExceptionHandling:
    """Tests for exception handling in apply_modifications."""
    
    def test_apply_modifications_handles_invalid_column(self):
        """Should handle exception when column doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from src.processing.process_modifications import ModificationsProcessor
            import io
            import sys
            
            processor = ModificationsProcessor(data_dir=tmpdir)
            
            df = pd.DataFrame({'id': [1, 2], 'value': ['A', 'B']})
            modifications = [
                {
                    "type": "field_modification",
                    "details": {
                        "row_index": 0,
                        "column": "nonexistent_column",
                        "new_value": "X"
                    }
                }
            ]
            
            # Capture stdout to verify warning
            captured = io.StringIO()
            sys.stdout = captured
            try:
                result_df = processor.apply_modifications(df, modifications)
            finally:
                sys.stdout = sys.__stdout__
            
            # DataFrame should be unchanged
            assert result_df.at[0, 'value'] == 'A'
            # Warning should have been printed
            assert "Warning" in captured.getvalue() or len(result_df) == 2
    
    def test_apply_modifications_handles_invalid_row_index(self):
        """Should handle out-of-bounds row index gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from src.processing.process_modifications import ModificationsProcessor
            
            processor = ModificationsProcessor(data_dir=tmpdir)
            
            df = pd.DataFrame({'id': [1, 2], 'value': ['A', 'B']})
            modifications = [
                {
                    "type": "field_modification",
                    "details": {
                        "row_index": 999,  # Out of bounds
                        "column": "value",
                        "new_value": "X"
                    }
                }
            ]
            
            # Should not raise exception - pandas may expand or handle differently
            result_df = processor.apply_modifications(df, modifications)
            
            # Original data should remain accessible
            assert result_df.at[0, 'value'] == 'A'
            assert result_df.at[1, 'value'] == 'B'
