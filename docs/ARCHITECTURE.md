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
Filter to active_columns (UI-visible columns only)
      ↓
Reorder columns to match UI display order
      ↓
Apply column_masks (rename headers to display names)
      ↓
Write CSV
      ↓
Show Notification: "📥 Exported!"
      ↓
File Available for Download/Use
```

### Cell Click Flow

```
User clicks a cell in a cell_click_columns column
      ↓
JS: handleCellClick() fires with column name + row PK
      ↓
Shiny.setInputValue("cell_click_event", {column, pk})
      ↓
Server: @reactive.effect on input.cell_click_event
      ↓
WidgetAPI.cell_click_event updated for downstream consumption
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

---

## JS-First Interactive Architecture (March 2026)

The application is **not** a traditional pure-Shiny app. It uses a **JS-first interactive layer** on top of a Shiny rendering backend, where the majority of UI interaction logic lives in client-side JavaScript that communicates with the server through a custom `setShinyInput` bridge function.

### Architecture Summary

```
┌─────────────────────────────────────────────────────────────────┐
│                        BROWSER                                  │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  JS Interactive Layer (1,613 lines / 9 files)           │   │
│  │                                                         │   │
│  │  cell-edit.js ─── inline edit popup, copy-to-clipboard  │   │
│  │  modal.js ─────── 6 modals, drag-and-drop, filter UI   │   │
│  │  table-drag.js ── column reorder, resize, header menus  │   │
│  │  row-selection.js  Shift+Click range select, Select All │   │
│  │  preset.js ────── preset dropdown load/save/delete      │   │
│  │  synthesis.js ─── synthesis modal, live countdown timer │   │
│  │  facet-filter.js ─ facet checkbox sync                  │   │
│  │  histogram.js ─── status histogram checkbox sync        │   │
│  │  panel-toggle.js ─ sidebar collapse/expand              │   │
│  │                                                         │   │
│  │  76 setShinyInput() call sites → 23 unique input names  │   │
│  └────────────────────────┬────────────────────────────────┘   │
│                           │ setShinyInput(name, value)          │
│                           ▼                                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Shiny-Rendered HTML (server → browser)                 │   │
│  │  47 onclick= attributes wiring back into JS functions   │   │
│  └─────────────────────────────────────────────────────────┘   │
└───────────────────────────────┬─────────────────────────────────┘
                                │ WebSocket
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     PYTHON BACKEND                              │
│                     server.py (2,068 lines)                     │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  42 Reactive Handlers                                   │   │
│  │                                                         │   │
│  │  21 JS-Input-Driven (50%)                               │   │
│  │  ├─ Triggered by setShinyInput from browser JS          │   │
│  │  ├─ cell_edit, column_order, sort_column, add_column,   │   │
│  │  │  remove_column, column_widths, load_preset,          │   │
│  │  │  save_preset_name, delete_preset, copy_column_req,   │   │
│  │  │  add_filter_column, remove_filter_column,            │   │
│  │  │  set_filter_operator, apply_filter_value,            │   │
│  │  │  facet_filter_change, undo_modification,             │   │
│  │  │  confirm_export, etc.                                │   │
│  │  └─ Server processes data then re-renders HTML          │   │
│  │                                                         │   │
│  │  21 Pure Server-Side (50%)                              │   │
│  │  ├─ render.ui: table, pagination, histogram, filters,   │   │
│  │  │  modals, presets, synthesis UI, export status         │   │
│  │  ├─ Shiny action buttons: approve, reject, save,        │   │
│  │  │  reload, export, synthesis run/regen/exit             │   │
│  │  └─ DB queries, DataFrame ops, state persistence        │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Data Layer                                             │   │
│  │  config_instance.py │ db_operations.py │ query_builder  │   │
│  │  data_loader.py │ session_book.py │ user_presets.py     │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### Key Metrics

| Metric | Value |
|--------|------:|
| JS code (src/js/) | 1,613 lines across 9 files |
| server.py | 2,068 lines |
| JS : server.py ratio | 0.78 : 1 |
| Total reactive handlers | 42 |
| Handlers triggered by JS `setShinyInput` | 21 (50%) |
| Handlers using pure Shiny inputs or render-only | 21 (50%) |
| Unique JS→Shiny input channels | 23 |
| `setShinyInput` call sites in JS | 76 |
| `onclick=` bindings in Python HTML templates | 47 |
| Inline `<script>` injections from server.py | 3 |

### JS-Driven Features

All UI interaction is handled in the browser with data dispatched to the server via `setShinyInput`:

- Cell editing popup (create, position, animate popup, capture edits)
- Column drag-and-drop reordering (table header and modal)
- Column resizing via mouse drag
- Header action dropdowns (sort asc/desc, remove column)
- Row selection with Shift+Click range select
- Select All / Deselect All / Toggle All Page
- All modal open/close/positioning (6 modals)
- Preset dropdown menu (load, save, delete, save layout)
- Facet filter checkbox synchronization
- Status histogram checkbox synchronization
- Filter textarea edit/confirm toggle
- Filter values modal (search, select all, clear all, apply)
- Date filter application
- Sidebar panel collapse/expand
- Copy column values to clipboard
- Export confirmation flow
- Synthesis modal with live countdown timer

### Purely Server-Side Features

No JS-driven input; standard Shiny reactivity or backend-only logic:

- Data loading from PostgreSQL (direct or via Datum proxy)
- Lazy loading / DataFetcher page queries
- SQL query building with type-safe wrappers
- Synthesis (run/refresh materialized view)
- Approval/rejection workflow (DB writes)
- Undo modification logic
- Pagination calculation
- Search and filter application to DataFrame
- Status count computation
- CSV export preparation
- UI state persistence to database
- Preset storage to database
- Viewer permission enforcement
- Data reload
- Event emission via commute layer

### Testing Implications

Because the server acts primarily as a data-processing backend receiving JS-dispatched events, the testing strategy focuses on:

1. **Pure function tests** (1,406 passing) — validate every data transformation the server performs
2. **Contract tests** (F1–F4) — verify the data shape at each boundary
3. **SQL golden snapshots** — ensure query generation is deterministic
4. **Security tests** — harden every SQL interpolation surface

The Shiny reactive plumbing itself (the `@Effect` / `@render.ui` wiring) is treated as framework infrastructure. The JS interactive layer is validated via the 34 E2E test scaffolds (currently skipped, pending staging environment with SSO bypass).

Server.py's 1% line coverage is expected and acceptable — the reactive handlers are thin dispatchers that call into the fully-tested utility and data layers.
