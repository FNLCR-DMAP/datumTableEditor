# PyShiny Epitopes Data Editor - Complete Guide

## Overview

This project provides a full-featured web application for editing epitope data with complete modification tracking. Built with PyShiny, it allows users to:

1. **View data** from CSV files in an interactive table
2. **Edit fields** directly in the UI
3. **Track changes** with automatic JSON logging
4. **Export results** in multiple formats (CSV, JSON, SQL)
5. **Apply transformations** using the modification log

## Quick Start

### 1. Install Dependencies
```bash
cd /Users/her2/Desktop/presentation/igv_demo
pip install -r requirements.txt
```

### 2. Run the App
```bash
# Option A: Using the provided script
bash run_app.sh

# Option B: Direct command
python -m shiny run src/app.py
```

### 3. Access the Application
Open your browser and navigate to: `http://localhost:8000`

## Application Features

### Data Editing
- **Inline Editing**: Click any cell to edit its value
- **Live Updates**: Changes are tracked in real-time
- **Row Selection**: Use checkboxes to select rows (for future batch operations)
- **Visual Feedback**: Editable cells have focus indicators

### Modification Tracking
All changes are automatically logged to `data/modifications_log.json` with:
- **Timestamp**: ISO 8601 format for precise audit trails
- **Row Index**: Which row was modified (0-indexed)
- **Column Name**: Which field was changed
- **Old & New Values**: Before/after values for comparison

### Data Management
- **Save Modifications**: Persist changes to JSON files
- **Export as CSV**: Save modified data for external use
- **Reload Data**: Restore original data and clear all modifications
- **Clear Log**: Remove modification history

## File Structure

```
igv_demo/
├── src/
│   ├── app.py                 # Main PyShiny application
│   └── tab_config.json        # Table configuration
├── data/
│   ├── dummy_data_50rows.csv  # Sample data
│   ├── schema_data.json       # Data schema
│   ├── modifications_log.json # Modification history (auto-updated)
│   ├── data_state.json        # Current data snapshot (auto-generated)
│   ├── data_modified.csv      # Exported CSV (auto-generated)
│   └── processed/             # Output directory for transformations
├── process_modifications.py   # Utility to apply modifications
├── run_app.sh                 # Quick start script
├── requirements.txt           # Python dependencies
└── README.md                  # Documentation
```

## Usage Workflow

### Scenario 1: Simple Data Editing

1. Start the app: `bash run_app.sh`
2. Browse the table and locate data to edit
3. Click any cell to edit
4. View changes in the "Modifications Log" below
5. Click "💾 Save Modifications" to persist changes
6. Click "📥 Export to CSV" to get the modified data

### Scenario 2: Batch Processing

1. Edit multiple cells and save
2. Run the processor script:
   ```bash
   python process_modifications.py data
   ```
3. Check `data/processed/` directory for:
   - `data_transformed.csv` - Modified data
   - `modifications_audit.csv` - Change audit trail
   - `modifications.sql` - SQL update statements
   - `summary.json` - Change statistics

### Scenario 3: Pipeline Integration

Integrate modifications into your data pipeline:

```python
from process_modifications import ModificationsProcessor

processor = ModificationsProcessor("data")
results = processor.process_and_save()

# Access results
print(f"Applied {results['modifications_count']} modifications")
for file_type, path in results['output_files'].items():
    print(f"{file_type}: {path}")
```

## JSON Modification Log Format

Each entry in `modifications_log.json` has this structure:

```json
{
  "timestamp": "2024-01-21T10:30:45.123456",
  "type": "field_modification",
  "details": {
    "row_index": 0,
    "column": "Comments",
    "old_value": "Original value",
    "new_value": "Modified value"
  }
}
```

### How to Use the Log

**Load and apply modifications:**
```python
import json
import pandas as pd

df = pd.read_csv("data/dummy_data_50rows.csv")

with open("data/modifications_log.json") as f:
    mods = json.load(f)

for mod in mods:
    details = mod['details']
    df.at[details['row_index'], details['column']] = details['new_value']
```

**Generate SQL statements:**
```python
with open("data/modifications_log.json") as f:
    mods = json.load(f)

for mod in mods:
    d = mod['details']
    print(f"UPDATE table SET {d['column']} = '{d['new_value']}' WHERE id = {d['row_index']};")
```

## Configuring Display Columns

Edit `src/app.py` to control which columns appear in the editor:

```python
display_columns = [
    "PatientID",        # Add these columns
    "Variant_key",
    "Gene_names",
    "Comments",         # Remove ones you don't need
    # ... etc
]
```

Available columns from the CSV:
- PatientID
- Variant_key
- Wt_nmer
- Mut_nmer
- Status
- Comments
- aa_changes
- cDNA_changes
- WtNMerReviewed
- MutNMerReviewed
- Max_Read2Count
- (and many more - see data/schema_data.json)

## Statistics Dashboard

The app displays real-time statistics:
- **Total Rows**: Number of data records
- **Modifications**: Count of changes made
- **Editable Columns**: Number of fields available for editing

## Output Files Explained

### modifications_log.json
- **Purpose**: Complete audit trail of all changes
- **Use Case**: Compliance, tracking changes, applying transformations
- **Format**: JSON array of modification objects
- **When Created**: Auto-updated when you click "Save Modifications"

### data_state.json
- **Purpose**: Snapshot of current data state
- **Use Case**: Checkpointing, comparison with original
- **Format**: JSON array of records
- **When Created**: Auto-generated when saving

### data_modified.csv
- **Purpose**: Export for use in other tools
- **Use Case**: Sharing data, importing to Excel, etc.
- **Format**: CSV with same schema as input
- **When Created**: Auto-generated when clicking "Export to CSV"

### processed/modifications_audit.csv
- **Purpose**: Human-readable change audit trail
- **Columns**: timestamp, row_index, column, old_value, new_value
- **Generated**: By process_modifications.py

### processed/modifications.sql
- **Purpose**: SQL UPDATE statements for database integration
- **Use Case**: Apply changes to database backend
- **Format**: Standard SQL
- **Generated**: By process_modifications.py

## Troubleshooting

### Issue: "Address already in use"
The port 8000 is already in use.
**Solution**: Shiny will auto-increment to the next available port (8001, 8002, etc.)

### Issue: "Module not found: shiny"
Dependencies not installed.
**Solution**: Run `pip install -r requirements.txt`

### Issue: Table doesn't show all columns
Columns were removed in `display_columns` list or don't exist in CSV.
**Solution**: Check column names in `dummy_data_50rows.csv` and update `src/app.py`

### Issue: Changes not persisting
You didn't click "Save Modifications".
**Solution**: Click the save button to write changes to JSON files

## Advanced Features

### Custom Validation
Extend the app to validate changes:

```python
def validate_cell_change(column, new_value):
    if column == "Status" and new_value not in ["Active", "Inactive", "Pending"]:
        raise ValueError(f"Invalid status: {new_value}")
    return True
```

### Selective Exports
Export only modified rows:

```python
mods = json.load(open("data/modifications_log.json"))
modified_rows = {m['details']['row_index'] for m in mods}
df = pd.read_csv("data/dummy_data_50rows.csv")
df.iloc[list(modified_rows)].to_csv("modified_rows_only.csv", index=False)
```

### Change Diffing
Generate before/after comparisons:

```python
original = pd.read_csv("data/dummy_data_50rows.csv")
modified = pd.read_json("data/data_state.json")
diff = original.compare(modified)
```

## Architecture

**Frontend**: PyShiny + Bootstrap CSS
**Backend**: Python with Pandas
**Storage**: JSON files (modifications) + CSV (data)
**Reactivity**: Shiny reactive values and effects

## Integration with tab_config.json

The `src/tab_config.json` file defines the table structure using a schema similar to Palantir Foundry's object configuration. The app currently displays a subset of the available columns. To add more:

1. Find the column name in `data/dummy_data_50rows.csv`
2. Add it to `display_columns` in `src/app.py`
3. Restart the app

The config file supports:
- **Properties**: Direct field mappings
- **Derived properties**: Computed columns
- **Linked objects**: References to related data
- **Formatting**: Custom display rules

## Performance Notes

- **Recommended for**: Datasets up to 10,000 rows
- **Large datasets**: Consider pagination or filtering
- **Memory**: Each cell edit creates a temporary copy of the dataframe

## Security Considerations

- No authentication (add if needed)
- All changes logged to JSON files (no encryption by default)
- SQL exports are unencoded (sanitize before use with real databases)

## Next Steps

1. Start editing data: `bash run_app.sh`
2. Make some changes and save
3. View `data/modifications_log.json` to see the format
4. Run `python process_modifications.py data` to generate transforms
5. Check `data/processed/` for exported files

## Support

For issues or questions:
1. Check the Troubleshooting section
2. Review the app console for error messages
3. Verify all dependencies are installed
4. Check file permissions in the `data/` directory
