# Architecture & Data Flow

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      WEB BROWSER                                │
│                   (http://localhost:8000)                       │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │              PyShiny UI Components                      │  │
│  │  ┌──────────────────────────────────────────────────┐  │  │
│  │  │  Interactive Data Table                          │  │  │
│  │  │  - Editable cells with text inputs              │  │  │
│  │  │  - Row selection checkboxes                     │  │  │
│  │  │  - Live statistics display                      │  │  │
│  │  └──────────────────────────────────────────────────┘  │  │
│  │  ┌──────────────────────────────────────────────────┐  │  │
│  │  │  Action Buttons                                  │  │  │
│  │  │  - Save Modifications                           │  │  │
│  │  │  - Export to CSV                                │  │  │
│  │  │  - Reload Data                                  │  │  │
│  │  │  - Clear Log                                    │  │  │
│  │  └──────────────────────────────────────────────────┘  │  │
│  │  ┌──────────────────────────────────────────────────┐  │  │
│  │  │  Modifications Log Display                       │  │  │
│  │  │  - Real-time change feed                        │  │  │
│  │  │  - Timestamp + before/after values              │  │  │
│  │  └──────────────────────────────────────────────────┘  │  │
│  └─────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              ↓ (WebSocket/HTTP)
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    PYTHON BACKEND                               │
│                    (src/app.py)                                 │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │              Shiny Server Functions                     │  │
│  │                                                         │  │
│  │  Reactive Values:                                      │  │
│  │  ├─ data: Current DataFrame                           │  │
│  │  ├─ mods_log: List of modifications                   │  │
│  │  └─ selected_rows: Row selection set                  │  │
│  │                                                         │  │
│  │  Event Handlers:                                       │  │
│  │  ├─ _save_modifications()                             │  │
│  │  ├─ _export_csv()                                     │  │
│  │  ├─ _reload_data()                                    │  │
│  │  └─ _clear_log()                                      │  │
│  └─────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                              ↓
          ┌───────────────────────────────────────┐
          │     FILE SYSTEM (data/)               │
          │                                       │
          ├─ dummy_data_50rows.csv                │ (Input)
          ├─ schema_data.json                     │ (Schema)
          ├─ tab_config.json                      │ (Config)
          │                                       │
          ├─ modifications_log.json               │ (Output)
          ├─ data_state.json                      │ (Output)
          ├─ data_modified.csv                    │ (Output)
          │                                       │
          └─ processed/                           │ (Output dir)
             ├─ data_transformed.csv              │
             ├─ modifications_audit.csv           │
             ├─ modifications.sql                 │
             └─ summary.json                      │
          └───────────────────────────────────────┘
                              ↑
                              ↑
          ┌───────────────────────────────────────┐
          │  Processing Scripts                   │
          │  (process_modifications.py)           │
          │                                       │
          │  ModificationsProcessor Class:        │
          │  ├─ load_original_data()              │
          │  ├─ load_modifications()              │
          │  ├─ apply_modifications()             │
          │  ├─ export_transformations()          │
          │  └─ process_and_save()                │
          └───────────────────────────────────────┘
```

## Data Flow Diagram

### Editing Flow

```
User Edits Cell
      ↓
HTML Input Event Captured
      ↓
Shiny Backend Detects Change
      ↓
Check Old vs New Value
      ↓
Create Modification Record:
{
  "timestamp": "2024-01-21T10:30:45.123",
  "type": "field_modification",
  "details": {
    "row_index": 0,
    "column": "Comments",
    "old_value": "old",
    "new_value": "new"
  }
}
      ↓
Append to mods_log (in memory)
      ↓
Update Display (show in log section)
      ↓
Update Statistics (increment counter)
```

### Saving Flow

```
User Clicks "Save Modifications"
      ↓
Collect all modifications from memory
      ↓
Write modifications_log.json
{
  "timestamp": "2024-01-21...",
  "type": "field_modification",
  "details": { ... }
}
      ↓
Write data_state.json (current DataFrame state)
      ↓
Show Notification: "✅ Saved N modifications!"
      ↓
Files Persisted to Disk
```

### Export Flow

```
User Clicks "Export to CSV"
      ↓
Get Current DataFrame
      ↓
Write to data_modified.csv
      ↓
Show Notification: "📥 Exported to data_modified.csv!"
      ↓
File Available for Download/Use
```

### Processing Flow

```
python process_modifications.py data
      ↓
Load Original CSV
      ↓
Load modifications_log.json
      ↓
For Each Modification:
  - Update DataFrame[row][column] = new_value
      ↓
Generate Outputs:
  ├─ data_transformed.csv (modified data)
  ├─ modifications_audit.csv (human-readable log)
  ├─ modifications.sql (database statements)
  └─ summary.json (statistics)
      ↓
Display Summary Report
```

## Column Data Type Support

```
Current Data Types:
├─ String (default)
│  └─ Examples: PatientID, Gene_names, Comments
├─ Numeric (editable as strings)
│  └─ Examples: Max_Read2Count, age values
└─ Boolean (editable as Y/N or 0/1)
   └─ Examples: WtNMerReviewed, MutNMerReviewed

In Modification Log:
  All values stored as strings (no type encoding)
  Type conversion happens during application
```

## State Management

```
Reactive Flow:

data.Value
├─ Initial: df_original.copy()
├─ Trigger: Cell edit detected
├─ Change: DataFrame updated with new value
└─ Result: Re-render table UI

mods_log.Value
├─ Initial: _load_modifications_log()
├─ Trigger: Cell edit detected
├─ Change: New modification appended
└─ Result: Update log display

selected_rows.Value
├─ Initial: set()
├─ Trigger: Checkbox clicked
├─ Change: Row ID added/removed
└─ Result: Visual highlighting (future use)
```

## File Persistence Timeline

```
Application Start
      ↓
  ├─ Load CSV
  ├─ Load existing modifications_log.json (if exists)
  └─ Initialize UI
      ↓
User Makes Edits
      ↓
  ├─ Changes stored in memory (mods_log)
  └─ Display updated immediately
      ↓
User Clicks "Save Modifications"
      ↓
  ├─ Write modifications_log.json ← Contains ALL edits
  ├─ Write data_state.json ← Current DataFrame snapshot
  └─ Show success notification
      ↓
[Later] python process_modifications.py data
      ↓
  ├─ Read modifications_log.json
  ├─ Apply all changes to fresh CSV
  └─ Generate outputs (CSV, SQL, JSON, summary)
```

## Error Handling Flow

```
Cell Edit Attempt
      ↓
Try:
  ├─ Get cell ID from input
  ├─ Compare old vs new
  ├─ Update DataFrame
  ├─ Create log entry
  └─ Update reactive values
      ↓
Except:
  ├─ Log error to console
  ├─ Skip update
  └─ Continue (no user notification)
      ↓
Result: Graceful degradation
        (app continues working)
```

## Performance Characteristics

```
Table Rendering (Initial)
  50 rows × 12 columns = 600 input widgets
  Load time: ~500ms
  Memory: ~20MB

Cell Edit Detection
  Checks: 50 rows × 12 cols = 600 inputs per trigger
  Frequency: ~1s (Shiny default refresh)
  CPU impact: Low

Saving Modifications
  File I/O: ~100ms
  JSON serialization: ~50ms
  Total: ~150ms

Processing (process_modifications.py)
  Load CSV: ~100ms
  Apply mods: ~10-50ms (depends on count)
  Export CSV: ~100ms
  Total: ~200-300ms
```

## Security Boundaries

```
User Input (Untrusted)
      ↓
HTML Input Element
      ↓
Shiny Framework (Sanitized)
      ↓
Python Backend
      ↓
String Storage (Not Executed)
      ↓
File System
```

## Integration Points

For external systems:

```
Python/Pandas:
  ├─ Load modifications_log.json
  ├─ Apply to fresh data
  └─ Process as needed

SQL Databases:
  ├─ Load modifications.sql
  ├─ Execute statements
  └─ Sync database

Data Pipelines:
  ├─ Read data_state.json
  ├─ Process transformed data
  └─ Load to warehouse

Workflows:
  ├─ Monitor modifications_log.json
  ├─ Trigger actions on changes
  └─ Automate downstream tasks
```

## Scaling Considerations

```
Small Dataset (50-100 rows)
  └─ Current implementation works well
  
Medium Dataset (100-1000 rows)
  └─ Same architecture, may add pagination
  
Large Dataset (1000+ rows)
  ├─ Consider virtual scrolling
  ├─ Batch UI updates
  └─ Stream processing for output

Very Large Dataset (10000+ rows)
  ├─ Split into chunks
  ├─ Background processing
  └─ Different architecture needed
```
