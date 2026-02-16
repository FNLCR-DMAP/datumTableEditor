"""
Utility script to process modifications log and apply transformations.
This shows how to ingest the JSON modification log for data transformation pipelines.
"""

import json
import pandas as pd
from pathlib import Path
from datetime import datetime


class ModificationsProcessor:
    """Process and apply modifications from the log file."""
    
    def __init__(self, data_dir=None):
        if data_dir is None:
            # Default to data dir in parent directory
            data_dir = Path(__file__).parent.parent / "data"
        self.data_dir = Path(data_dir)
        self.original_csv = self.data_dir / "dummy_data_50rows.csv"
        self.modifications_log = self.data_dir / "modifications_log.json"
        self.output_dir = self.data_dir / "processed"
        self.output_dir.mkdir(exist_ok=True)
    
    def load_original_data(self):
        """Load original CSV data."""
        return pd.read_csv(self.original_csv)
    
    def load_modifications(self):
        """Load modifications log."""
        if self.modifications_log.exists():
            with open(self.modifications_log, "r") as f:
                return json.load(f)
        return []
    
    def apply_modifications(self, df, modifications):
        """
        Apply all modifications from the log to the dataframe.
        
        Args:
            df: Original pandas DataFrame
            modifications: List of modification records from JSON
            
        Returns:
            DataFrame with modifications applied
        """
        df_modified = df.copy()
        
        for mod in modifications:
            if mod.get("type") != "field_modification":
                continue
            
            details = mod.get("details", {})
            row_idx = details.get("row_index")
            column = details.get("column")
            new_value = details.get("new_value")
            
            if row_idx is not None and column and new_value is not None:
                try:
                    df_modified.at[row_idx, column] = new_value
                except Exception as e:
                    print(f"Warning: Could not apply modification at row {row_idx}, col {column}: {e}")
        
        return df_modified
    
    def get_change_summary(self, modifications):
        """
        Generate a summary of all changes.
        
        Returns:
            Dictionary with change statistics
        """
        summary = {
            "total_modifications": len(modifications),
            "modified_columns": set(),
            "modified_rows": set(),
            "changes_by_column": {},
            "timestamp": datetime.now().isoformat(),
        }
        
        for mod in modifications:
            details = mod.get("details", {})
            col = details.get("column")
            row = details.get("row_index")
            
            if col:
                summary["modified_columns"].add(col)
                if col not in summary["changes_by_column"]:
                    summary["changes_by_column"][col] = 0
                summary["changes_by_column"][col] += 1
            
            if row is not None:
                summary["modified_rows"].add(row)
        
        # Convert sets to lists for JSON serialization
        summary["modified_columns"] = sorted(list(summary["modified_columns"]))
        summary["modified_rows"] = sorted(list(summary["modified_rows"]))
        
        return summary
    
    def export_transformations(self, modifications, output_format="csv"):
        """
        Export transformations in various formats.
        
        Args:
            modifications: List of modification records
            output_format: 'csv', 'json', or 'sql'
            
        Returns:
            Path to exported file
        """
        if output_format == "csv":
            return self._export_as_csv(modifications)
        elif output_format == "json":
            return self._export_as_json(modifications)
        elif output_format == "sql":
            return self._export_as_sql(modifications)
        else:
            raise ValueError(f"Unknown format: {output_format}")
    
    def _export_as_csv(self, modifications):
        """Export modifications as CSV for audit trail."""
        rows = []
        for mod in modifications:
            details = mod.get("details", {})
            rows.append({
                "timestamp": mod.get("timestamp"),
                "row_index": details.get("row_index"),
                "column": details.get("column"),
                "old_value": details.get("old_value"),
                "new_value": details.get("new_value"),
            })
        
        df = pd.DataFrame(rows)
        output_path = self.output_dir / "modifications_audit.csv"
        df.to_csv(output_path, index=False)
        return output_path
    
    def _export_as_json(self, modifications):
        """Export modifications as formatted JSON."""
        output_path = self.output_dir / "modifications_formatted.json"
        with open(output_path, "w") as f:
            json.dump(modifications, f, indent=2)
        return output_path
    
    def _export_as_sql(self, modifications):
        """Export modifications as SQL UPDATE statements."""
        output_path = self.output_dir / "modifications.sql"
        
        with open(output_path, "w") as f:
            f.write("-- Generated SQL UPDATE statements\n")
            f.write(f"-- Generated: {datetime.now().isoformat()}\n")
            f.write(f"-- Total modifications: {len(modifications)}\n\n")
            
            for mod in modifications:
                details = mod.get("details", {})
                row_idx = details.get("row_index")
                column = details.get("column")
                new_value = details.get("new_value")
                
                if row_idx is not None and column and new_value is not None:
                    from src.config.sql_types import SqlIdentifier, SqlLiteral
                    f.write(f"-- Row {row_idx}: {column}\n")
                    f.write(f"UPDATE epitopes SET {SqlIdentifier(column)} = {SqlLiteral(new_value)} WHERE row_id = {SqlLiteral(int(row_idx))};\n\n")
        
        return output_path
    
    def process_and_save(self):
        """
        Complete workflow: load data, apply modifications, save results.
        
        Returns:
            Dictionary with processing results
        """
        print("Loading original data...")
        df_original = self.load_original_data()
        
        print("Loading modifications...")
        modifications = self.load_modifications()
        
        if not modifications:
            print("No modifications found.")
            return {"status": "no_modifications"}
        
        print(f"Found {len(modifications)} modifications")
        
        print("Applying modifications...")
        df_modified = self.apply_modifications(df_original, modifications)
        
        print("Generating summary...")
        summary = self.get_change_summary(modifications)
        
        # Save modified data
        modified_csv = self.output_dir / "data_transformed.csv"
        df_modified.to_csv(modified_csv, index=False)
        print(f"Saved transformed data to {modified_csv}")
        
        # Export modifications in multiple formats
        print("Exporting modifications...")
        audit_csv = self.export_transformations(modifications, "csv")
        audit_json = self.export_transformations(modifications, "json")
        audit_sql = self.export_transformations(modifications, "sql")
        
        print(f"Exported audit trail to {audit_csv}")
        print(f"Exported formatted JSON to {audit_json}")
        print(f"Exported SQL statements to {audit_sql}")
        
        # Save summary
        summary_file = self.output_dir / "summary.json"
        with open(summary_file, "w") as f:
            json.dump(summary, f, indent=2)
        print(f"Saved summary to {summary_file}")
        
        return {
            "status": "success",
            "modifications_count": len(modifications),
            "summary": summary,
            "output_files": {
                "data": str(modified_csv),
                "audit_csv": str(audit_csv),
                "audit_json": str(audit_json),
                "sql": str(audit_sql),
                "summary": str(summary_file),
            }
        }


def main():
    """Run the modification processor."""
    import sys
    
    # Determine data directory
    data_dir = "data"
    if len(sys.argv) > 1:
        data_dir = sys.argv[1]
    
    processor = ModificationsProcessor(data_dir)
    results = processor.process_and_save()
    
    if results["status"] == "success":
        print("\n✅ Processing complete!")
        print(f"\nSummary:")
        print(f"  Total modifications: {results['summary']['total_modifications']}")
        print(f"  Modified columns: {', '.join(results['summary']['modified_columns'])}")
        print(f"  Modified rows: {len(results['summary']['modified_rows'])}")
        print(f"\nOutput files saved to: processed/")
    else:
        print("\n⚠️  No modifications to process")


if __name__ == "__main__":
    main()
