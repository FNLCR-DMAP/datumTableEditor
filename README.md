# Epitopes Data Editor - PyShiny App

This PyShiny application provides an interactive web-based interface for editing epitope data with full modification tracking.

## Features

- **Editable Table View**: Display CSV data in an interactive table format
- **Direct Cell Editing**: Modify any cell value directly in the table
- **Row Selection**: Select multiple rows with checkboxes
- **Modification Tracking**: All changes are logged with timestamps
- **Data Export**: Save modified data as CSV
- **JSON Logging**: All modifications are saved to `modifications_log.json` for audit trails

## File Structure

```
igv_demo/
├── data/
│   ├── dummy_data_50rows.csv          # Sample data to edit
│   ├── schema_data.json               # Data schema/structure
│   ├── modifications_log.json         # Auto-generated log of all changes
│   ├── data_state.json                # Auto-generated current data state
│   └── data_modified.csv              # Exported modified data
├── src/
│   ├── app.py                         # Main PyShiny application
│   └── tab_config.json                # Table configuration based on object schema
└── requirements.txt                   # Python dependencies
```

## Installation

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

   Or manually:
   ```bash
   pip install shiny pandas shinywidgets
   ```

## Running the App

1. **Navigate to the project directory**:
   ```bash
   cd /Users/her2/Desktop/presentation/igv_demo
   ```

2. **Run the Shiny app**:
   ```bash
   shiny run src/app.py
   ```

3. **Open in browser**: The app will typically open at `http://localhost:8000`

## How to Use

### Editing Data
1. Click on any cell in the table to edit its value
2. Changes are automatically tracked
3. View modifications in the "Modifications Log" section below the table

### Saving Your Work
- **Save Modifications**: Click "💾 Save Modifications" to persist changes to JSON files
  - Saves to `data/modifications_log.json` (all changes with timestamps)
  - Saves to `data/data_state.json` (current data snapshot)

- **Export to CSV**: Click "📥 Export to CSV" to save the current state as CSV
  - Exports to `data/data_modified.csv`

### Other Operations
- **Reload Data**: Click "🔄 Reload Data" to restore original data and clear modifications
- **Clear Log**: Click "🗑️ Clear Log" to remove all modification records

## Output Files

### modifications_log.json
Records all field modifications with this structure:
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

### data_state.json
Current snapshot of all data in JSON format (records oriented).

### data_modified.csv
Export of current data in CSV format for use in other applications.

## Configuration

### Display Columns
Edit the `display_columns` list in `src/app.py` to change which columns are displayed:

```python
display_columns = [
    "PatientID",
    "Variant_key",
    "Gene_names",
    # Add/remove columns as needed
]
```

## Column Mapping from tab_config.json

The app references column definitions from `src/tab_config.json`:
- Property columns (direct fields): `variant_key`, `gene_names`, `status`, etc.
- Derived columns: `AA Change`, `Mut Nmer`, `Wt Nmer`
- Linked objects: Links to related records (MHCflurry, HLA data)

Currently, the app displays a curated subset of key columns. The full configuration supports many more columns if needed.

## Architecture

- **UI**: Pure Shiny UI components (no external JavaScript frameworks)
- **Data Handling**: Pandas DataFrames for in-memory operations
- **Persistence**: JSON files for modification logs, CSV for data exports
- **Reactivity**: Shiny reactive values and effects for state management

## Advanced Usage

### Ingesting Modifications
Use the `modifications_log.json` to automate data transformations:

```python
import json
import pandas as pd

# Load original data
df = pd.read_csv('data/dummy_data_50rows.csv')

# Load modifications
with open('data/modifications_log.json') as f:
    mods = json.load(f)

# Apply modifications
for mod in mods:
    details = mod['details']
    row_idx = details['row_index']
    col = details['column']
    new_value = details['new_value']
    df.at[row_idx, col] = new_value

# Save transformed data
df.to_csv('data/transformed.csv', index=False)
```

## Troubleshooting

- **Port already in use**: The app will automatically use the next available port
- **Missing dependencies**: Run `pip install -r requirements.txt`
- **Columns not showing**: Verify column names in `display_columns` match CSV headers
- **Large datasets**: For datasets > 1000 rows, consider pagination

## Future Enhancements

- Row-level undo/redo
- Batch operations on selected rows
- Data validation rules
- User authentication and audit trails
- Real-time collaboration features
