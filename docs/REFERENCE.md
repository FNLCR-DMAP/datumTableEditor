# Quick Reference Card

## Starting the App

```bash
cd /Users/her2/Desktop/presentation/igv_demo
bash run_app.sh
```

Browser: `http://localhost:8000`

## File Locations

| File | Purpose |
|------|---------|
| `src/app.py` | Main application |
| `data/dummy_data_50rows.csv` | Data to edit |
| `data/modifications_log.json` | Change log |
| `data/data_state.json` | Current snapshot |
| `data/data_modified.csv` | Exported data |
| `process_modifications.py` | Post-processor |
| `examples.py` | Code examples |

## Common Commands

### Start App
```bash
bash run_app.sh
```

### Install Dependencies
```bash
pip install -r requirements.txt
```

### Process Modifications
```bash
python process_modifications.py data
```

### Run Examples
```bash
python examples.py
```

## UI Buttons

| Button | Action |
|--------|--------|
| 💾 Save Modifications | Persist changes to JSON |
| 📥 Export to CSV | Save data as CSV |
| 🔄 Reload Data | Restore original data |
| 🗑️ Clear Log | Remove modification history |

## Data Types

| Type | Examples |
|------|----------|
| String | PatientID, Comments, Gene_names |
| Numeric | Max_Read2Count, ages |
| Boolean | Y/N flags, True/False |

## Modification Log Entry

```json
{
  "timestamp": "2024-01-21T10:30:45.123456",
  "type": "field_modification",
  "details": {
    "row_index": 0,
    "column": "Comments",
    "old_value": "Old",
    "new_value": "New"
  }
}
```

## Common Workflows

### Editing & Saving
1. Click cell to edit
2. Type new value
3. Tab to next cell
4. Click "Save Modifications"

### Exporting
1. Make edits and save
2. Click "Export to CSV"
3. Find `data_modified.csv`

### Processing for Database
1. Edit and save modifications
2. Run `python process_modifications.py data`
3. Use `data/processed/modifications.sql`

### Auditing Changes
1. Run `python examples.py`
2. Check `data/processed/modifications_audit.csv`

## Configuration

### Add Column to Display
Edit `src/app.py`:
```python
display_columns = [
    "PatientID",
    "NEW_COLUMN",  # Add here
]
```

### Change Port
Run with custom port:
```bash
python -m shiny run src/app.py --port 8888
```

## Output Files Location

After saving:
- `data/modifications_log.json` ← Changes
- `data/data_state.json` ← Snapshot

After exporting:
- `data/data_modified.csv` ← CSV export

After processing:
- `data/processed/data_transformed.csv` ← Transformed
- `data/processed/modifications.sql` ← Database
- `data/processed/modifications_audit.csv` ← Audit
- `data/processed/summary.json` ← Statistics

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Tab | Move to next cell |
| Shift+Tab | Move to previous cell |
| Enter | Confirm edit |
| Esc | Cancel edit |

## Column Names (Editable)

```
PatientID
Variant_key
Gene_names
Wt_nmer
Mut_nmer
Status
Comments
aa_changes
cDNA_changes
WtNMerReviewed
MutNMerReviewed
Max_Read2Count
(+ more from schema)
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Port in use | App auto-increments port |
| Module error | `pip install -r requirements.txt` |
| No columns | Check CSV header names |
| Changes not saved | Click "Save Modifications" |
| File not found | Run from project root directory |

## Performance Tips

- Dataset limit: 10,000 rows recommended
- Large datasets: Consider filtering/pagination
- Slow edits: Check CPU usage, close other apps
- Memory issues: Process in batches

## Integration Examples

### Python/Pandas
```python
import json
import pandas as pd

df = pd.read_csv("data/dummy_data_50rows.csv")
mods = json.load(open("data/modifications_log.json"))

for mod in mods:
    d = mod["details"]
    df.at[d["row_index"], d["column"]] = d["new_value"]
```

### SQL
```bash
# Apply changes to database
cat data/processed/modifications.sql | psql mydb
```

### CSV
```python
# Load transformed data
import pandas as pd
df = pd.read_csv("data/processed/data_transformed.csv")
```

## Statistics

| Item | Value |
|------|-------|
| Rows | 50 |
| Columns | 47 |
| Editable Columns | 12 |
| Load Time | ~500ms |
| File Size | ~20KB CSV |

## Getting Help

1. Check [README.md](README.md)
2. Read [GUIDE.md](docs/GUIDE.md)
3. Review [examples.py](examples.py)
4. See [ARCHITECTURE.md](docs/ARCHITECTURE.md)

## Version Info

- Python: 3.8+
- PyShiny: 0.8.0+
- Pandas: 1.3.0+
- Bootstrap: 5.x

## Next Steps

1. Start app: `bash run_app.sh`
2. Make edits
3. Save changes
4. Run processor
5. Review outputs
6. Integrate with your system

---

**Last Updated:** January 21, 2024
**Status:** Ready to Use
**Location:** `/Users/her2/Desktop/presentation/igv_demo`
