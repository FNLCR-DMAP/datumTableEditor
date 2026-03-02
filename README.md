# dmapTableEditor

A reusable PyShiny table editor widget with PostgreSQL database support for data management applications.

## Features

- **Database-Backed Table Editor**: Edit data directly connected to PostgreSQL
- **Primary Key Based Tracking**: Track modifications using composite primary keys
- **Session Book Management**: Efficient pagination with in-memory caching
- **Modification History**: Full audit trail of all changes with undo support
- **Column Presets**: Save and load custom column configurations per user
- **Status Workflow**: Built-in approval/rejection workflow
- **Real-time Filtering & Sorting**: Database-level query optimization

## Installation

```bash
pip install dmapTableEditor
```

Or install from source:

```bash
git clone https://github.com/yourusername/dmapTableEditor.git
cd dmapTableEditor
pip install -e .
```

## Quick Start

### 1. Create Configuration File

Copy the template and customize for your database:

```bash
cp app_config.template.json app_config.json
```

Edit `app_config.json`:

```json
{
  "app_title": "My Data Editor",
  "database": {
    "enabled": true,
    "connection_string": "postgresql://user:pass@localhost/mydb",
    "data_table": "my_table",
    "mods_table": "my_modifications",
    "state_table": "my_ui_state"
  },
  "table": {
    "primary_key": ["id"],
    "editable_columns": ["status", "comments"],
    "display_columns": ["id", "name", "status", "comments"]
  }
}
```

### 2. Create Your App

```python
from shiny import App, ui
from dmapTableEditor import table_editor_ui, table_editor_server
from dmapTableEditor.config import load_app_config

# Load configuration
config = load_app_config("app_config.json")

app_ui = ui.page_fluid(
    ui.h1(config.app_title),
    table_editor_ui("editor")
)

def server(input, output, session):
    table_editor_server("editor", config=config)

app = App(app_ui, server)
```

### 3. Run the App

```bash
shiny run app.py
```

## Configuration Reference

See **template/app_config.template.json** for a fully annotated example and **docs/REFERENCE.md** for every key with defaults.

### Database Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `enabled` | bool | `false` | Enable PostgreSQL mode |
| `mode` | string | `"direct"` | `direct` (SQLAlchemy) or `datum` (proxy) |
| `connection_string` | string | — | PostgreSQL connection URL (direct mode) |
| `source_table` | string | `""` | Source table to copy from (optional) |
| `data_table` | string | `"epitopes_data"` | Working data table |
| `mods_table` | string | `"epitopes_modifications"` | Modifications tracking table |
| `state_table` | string | `"epitopes_ui_state"` | UI state persistence table |
| `status_column` | string | `"Status"` | Column holding row status |
| `auto_detect_pk` | bool | `true` | Auto-detect primary key from DB schema |
| `lazy_loading` | bool | `false` | DB-level pagination (fetch only current page) |
| `page_buffer_size` | int | `300` | Rows per query when lazy loading |
| `max_rows` | int\|null | `null` | Max rows to load (`null` = all) |
| `max_rows_per_page` | int | `100` | Hard upper limit per page |
| `shared_cache_key` | string\|null | `null` | Share loaded data across sessions using this key |
| `shared_cache_ttl` | int | `300` | Seconds to keep shared cache alive (5 min default) |

### Table Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `primary_key` | list | `["id"]` | Primary key column(s) |
| `default_columns` | list | `[]` | Columns visible by default (empty = all) |
| `editable_columns` | list | `[]` | Columns users can edit (empty = all) |
| `readonly_columns` | list | `[]` | Columns that cannot be edited |
| `column_masks` | object | `{}` | Display-name overrides: `{"real_name": "Display Name"}` |
| `default_sort_column` | string | `null` | Initial sort column |
| `default_sort_ascending` | bool | `true` | Initial sort direction |
| `presets_enabled` | bool | `true` | Enable column presets |

### Query Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `searchable_columns` | list | `[]` | Columns for text search (empty = all) |
| `filter_columns` | object | `{}` | Column filter types: `"select"`, `"text"`, `"numeric"`, `"date"` |
| `default_filters` | object | `{}` | Filters applied on load (see Filter Operators below) |
| `status_filter_enabled` | bool | `true` | Show status filter in sidebar |
| `search_case_sensitive` | bool | `false` | Case-sensitive search |
| `search_regex_enabled` | bool | `false` | Allow regex in search input |

### Feature Flags

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `enable_approval_workflow` | bool | `true` | Show approve/reject buttons and status column |
| `enable_save_button` | bool | `true` | Show the save button |
| `enable_export` | bool | `true` | Show the export button |
| `enable_undo` | bool | `true` | Show the undo button |
| `enable_copy_column` | bool | `true` | Allow copying column values |
| `enable_status_filter` | bool | `true` | Show status distribution in sidebar |
| `enable_synthesis` | bool | `false` | Enable the synthesis transform feature |
| `fix_filter` | bool | `false` | Lock filters to only `default_filters` |

### Synthesis

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `query` | string | `""` | SQL SELECT to materialize |
| `result_table_prefix` | string | `"_synthesis_result"` | Table name for cached result |
| `ttl_minutes` | int | `10` | Cache lifetime (0 = always regenerate) |
| `label` | string | `"Synthesis"` | Button and modal title label |

### Status Labels

```json
{
  "status_labels": {
    "unprocessed": "Unreviewed",
    "edited": "Edited",
    "approved": "Accepted",
    "rejected": "Rejected"
  }
}
```

Internal keys (`unprocessed`, `edited`, `approved`, `rejected`) must not change. Values are displayed in the UI and also recognized in the database `status_column`.

### Permissions

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `default_role` | string | `"viewer"` | Role for users not in `user_roles` |
| `user_roles` | object | `{}` | Map of `username → role` (`"editor"` or `"viewer"`) |

### Filter Operators

The `default_filters` object supports plain values (`"Clinical"`) or operator objects:

| Operator | Value Type | Description |
|----------|-----------|-------------|
| `in` | array | Match any value in list |
| `not_in` | array | Exclude values in list |
| `contains` | string | Case-insensitive substring |
| `not_contains` | string | Exclude substring matches |
| `between` | `[min, max]` | Inclusive range |
| `gt`, `gte`, `lt`, `lte` | number/string | Comparison |
| `last_n_days` | integer | Date column within last N days |
| `not_empty` | *(none)* | Non-null, non-blank |
| `regex` | string | PostgreSQL regex (`~*`) |

Example:
```json
{
  "default_filters": {
    "sequencing_date": {"op": "last_n_days", "value": 7},
    "status": {"op": "in", "value": ["Completed", "Others"]},
    "clinical_or_research": "Clinical"
  }
}
```

## Environment Variables

All configuration can be overridden via environment variables, which is useful for production deployments (e.g., RStudio Connect) where you don't want secrets in config files.

### Database Settings

| Environment Variable | Config Field | Description |
|---------------------|--------------|-------------|
| `APP_DATABASE_ENABLED` | `database.enabled` | Enable database mode (`true`/`false`) |
| `APP_DATABASE_MODE` | `database.mode` | `datum` (Datum proxy; only supported mode) |
| `APP_DB_CONNECTION_STRING` | `database.connection_string` | PostgreSQL connection URL |
| `APP_DB_DATA_TABLE` | `database.data_table` | Main data table name |
| `APP_DB_MODS_TABLE` | `database.mods_table` | Modifications table name |
| `APP_DB_STATE_TABLE` | `database.state_table` | UI state table name |

### Datum Proxy Settings

For deployments using the Datum proxy service (e.g., RStudio Connect without direct DB access):

| Environment Variable | Config Field | Description |
|---------------------|--------------|-------------|
| `DATUM_BASE_URL` | `database.datum_base_url` | Datum proxy base URL |
| `DATUM_API_TOKEN` | `database.datum_token` | API authentication token |
| `DATUM_DATABASE` | `database.datum_database` | Target database name |
| `DATUM_SCHEMA` | `database.datum_schema` | Database schema (default: `public`) |
| `DATUM_SERVICE_NAME` | `database.datum_service_name` | Service name (default: `postgres_sql`) |

### Data Source Settings

| Environment Variable | Config Field | Description |
|---------------------|--------------|-------------|
| `APP_DATA_SOURCE_TYPE` | `data_source.source_type` | Source type (`csv`, `json`, `api`, `database`) |
| `APP_DATA_FILE_PATH` | `data_source.file_path` | Path to data file |
| `APP_DATA_API_URL` | `data_source.api_url` | API endpoint URL |

### Persistence Settings

| Environment Variable | Config Field | Description |
|---------------------|--------------|-------------|
| `APP_PERSISTENCE_TYPE` | `persistence.persistence_type` | `local`, `api`, or `database` |
| `APP_MODIFICATIONS_LOG_PATH` | `persistence.modifications_log_path` | Path to modifications log |
| `APP_SAVE_API_URL` | `persistence.api_save_url` | API endpoint for saving |

### Example: RStudio Connect Deployment

Set these environment variables in RStudio Connect:

```bash
APP_DATABASE_MODE=datum
DATUM_BASE_URL=https://datum-proxy.yourcompany.com
DATUM_API_TOKEN=your-secret-token
DATUM_DATABASE=epitopes_db
DATUM_SCHEMA=public
```

## Package Structure

```
dmapTableEditor/
├── config/           # Configuration schema and loading
├── data/             # Data loading utilities
├── db/               # Database operations
│   ├── db_operations.py   # High-level DB interface
│   ├── db_schema.py       # Schema introspection
│   ├── query_builder.py   # SQL query construction
│   ├── session_book.py    # Session data management
│   └── user_presets.py    # User preferences storage
├── processing/       # Data processing utilities
├── utils/            # Helper utilities
│   ├── column_utils.py    # Column handling
│   ├── data_operations.py # Edit/undo operations
│   ├── filter_utils.py    # Filter handling
│   ├── modal_utils.py     # Modal dialogs
│   ├── pagination_utils.py
│   └── table_utils.py     # Table rendering
├── widgets/          # Shiny widget modules
├── css/              # Stylesheets
└── js/               # JavaScript utilities
```

## Database Schema

The package auto-creates required tables if they don't exist. Tables are typically created under a schema (e.g., `epitopes.modifications`, `epitopes.ui_state`):

### Modifications Table
```sql
CREATE TABLE <schema>.modifications (
    id SERIAL PRIMARY KEY,
    row_pk JSONB NOT NULL,
    column_name VARCHAR(255) NOT NULL,
    old_value TEXT,
    new_value TEXT,
    mod_type VARCHAR(50) NOT NULL,
    undone BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    created_by VARCHAR(255)
);
CREATE INDEX idx_modifications_row_pk ON <schema>.modifications USING GIN (row_pk);
CREATE INDEX idx_modifications_created_at ON <schema>.modifications (created_at DESC);
```

### UI State Table (Per-User)

UI state tables are created per-user. The table name is constructed as `<base_state_table>.<username>`.

For example, if `state_table` is configured as `epitopes.ui_state` and the username is `testuser`, the actual table will be `epitopes.ui_state.testuser`.

```sql
CREATE TABLE <schema>.ui_state.<username> (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255),
    session_id VARCHAR(255),
    filters JSONB,
    sort_column VARCHAR(255),
    sort_ascending BOOLEAN DEFAULT TRUE,
    current_page INT DEFAULT 1,
    rows_per_page INT DEFAULT 25,
    column_preset VARCHAR(255),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, session_id)
);
CREATE INDEX idx_ui_state_user_session ON <schema>.ui_state.<username> (user_id, session_id);
```

## Development

### UI Operations — ASCII Flowcharts

Every user-facing interaction mapped from trigger → server → data flow.

---

#### 1. Search

```
┌─────────────────────────────────────────────────────────┐
│  User types query  ──►  Picks column (or "All")         │
│  Clicks [Search]                                        │
└──────────────┬──────────────────────────────────────────┘
               │
               ▼
  ┌──────────────────────────┐
  │  _handle_search()        │
  │  read input.search_input │
  │  read input.search_column│
  └────────────┬─────────────┘
               │
       ┌───────┴───────┐
       │               │
       ▼               ▼
  ┌──────────┐  ┌─────────────┐
  │ search   │  │ current_page│
  │ _state   │  │  .set(1)    │
  │ .set()   │  └─────────────┘
  └────┬─────┘
       │
       ▼
  ┌───────────────────────────────────────────────────┐
  │  Lazy mode?                                       │
  │  YES ─► _build_query_params() ─► SQL WHERE ILIKE  │
  │  NO  ─► _get_filtered_rows() ─► pandas str.contains│
  └───────────────────────┬───────────────────────────┘
                          │
                          ▼
                ┌──────────────────┐
                │  table_container  │
                │  re-renders       │
                └──────────────────┘
```

---

#### 2. Status Filter (Histogram)

```
┌──────────────────────────────────────────┐
│  User clicks status bar in histogram     │
│  (e.g. uncheck "Unreviewed")             │
└──────────────────┬───────────────────────┘
                   │
                   ▼
      ┌────────────────────────────┐
      │  JS: initHistogramCheckboxes│
      │  syncs .status-checkbox     │
      │  ──► input.status_filter_   │
      │       multi (hidden select) │
      └────────────┬───────────────┘
                   │
                   ▼
      ┌────────────────────────────┐
      │  _reset_page_on_filter...  │
      │  current_page.set(1)       │
      └────────────┬───────────────┘
                   │
           ┌───────┴───────┐
           │               │
           ▼               ▼
  ┌──────────────┐  ┌──────────────────┐
  │ Lazy: SQL    │  │ In-memory:       │
  │ WHERE status │  │ _get_filtered_   │
  │ IN (...)     │  │ rows() filters   │
  └──────┬───────┘  │ by _get_row_     │
         │          │ status()         │
         │          └────────┬─────────┘
         └────────┬──────────┘
                  ▼
        ┌──────────────────┐
        │  table_container  │
        │  + stats_histogram│
        │  re-render        │
        └──────────────────┘
```

---

#### 3. Facet Filters

```
┌────────────────────────────────────────────────┐
│  User checks/unchecks value in facet panel     │
│  e.g. ☑ "RNA_Access" under NGS_TEST            │
└────────────────────┬───────────────────────────┘
                     │
                     ▼
      ┌──────────────────────────────────┐
      │  JS: initFacetCheckboxes()       │
      │  collect checked values per col  │
      │  ──► setShinyInput(              │
      │       "facet_filter_change",     │
      │       {col: [values]} )          │
      └──────────────┬───────────────────┘
                     │
                     ▼
      ┌──────────────────────────────────┐
      │  _handle_facet_filter()          │
      │  merge into active_filters       │
      │  (null = clear that column)      │
      │  current_page.set(1)             │
      └──────────────┬───────────────────┘
                     │
             ┌───────┴───────┐
             │               │
             ▼               ▼
      ┌────────────┐  ┌───────────────┐
      │ table re-  │  │ facet_panels  │
      │ renders    │  │ _ui re-renders│
      │ with new   │  │ with updated  │
      │ filters    │  │ checkmarks    │
      └────────────┘  └───────────────┘
```

---

#### 4. Dynamic Column Filters

```
 ┌──────────────┐    ┌──────────────────────────────────────┐
 │ Click [+]    │    │  Existing filter actions:             │
 │ Add Filter   │    │  ✕ remove │ ✎ edit │ op dropdown     │
 └──────┬───────┘    └────┬──────────┬──────────┬───────────┘
        │                 │          │          │
        ▼                 ▼          ▼          ▼
 ┌─────────────┐   ┌──────────┐ ┌────────┐ ┌─────────────────┐
 │ JS: open    │   │_remove_  │ │_apply_ │ │_set_filter_     │
 │ AddFilter   │   │filter()  │ │filter_ │ │operator()       │
 │ Modal       │   │          │ │value() │ │{col, op}        │
 └──────┬──────┘   └────┬─────┘ └───┬────┘ └────────┬────────┘
        │               │           │               │
        ▼               │           │               │
 ┌─────────────────┐    │           │               │
 │ Pick column     │    │           │               │
 │ ──► JS addFilter│    │           │               │
 │ ──► _add_filter │    │           │               │
 └────────┬────────┘    │           │               │
          │             │           │               │
          ▼             ▼           ▼               ▼
     ┌──────────────────────────────────────────────────┐
     │              active_filters.set(...)              │
     │              current_page.set(1)                  │
     └──────────────────────┬───────────────────────────┘
                            │
                    ┌───────┴───────┐
                    │               │
                    ▼               ▼
           ┌──────────────┐  ┌─────────────────┐
           │ table re-    │  │ dynamic_filters  │
           │ renders      │  │ panel re-renders │
           └──────────────┘  └─────────────────┘
```

---

#### 5. Sort

```
┌─────────────────────────────────────────────┐
│  Click column header ⋮ ──► Sort Asc / Desc  │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
          ┌───────────────────────────┐
          │  JS sends input.sort_     │
          │  column = {col, direction}│
          └─────────────┬─────────────┘
                        │
                        ▼
          ┌───────────────────────────┐
          │  _sort_column()           │
          │                           │
          │  Lazy?                    │
          │  YES ─► current_sort.set()│
          │         (SQL ORDER BY)    │
          │  NO  ─► sort_dataframe()  │
          │         on data reactive  │
          └─────────────┬─────────────┘
                        │
                ┌───────┴───────┐
                │               │
                ▼               ▼
       ┌──────────────┐  ┌────────────────┐
       │ current_page  │  │ save_ui_state  │
       │ .set(1)       │  │ (persist sort) │
       └──────┬────────┘  └────────────────┘
              │
              ▼
     ┌──────────────────┐
     │  table_container  │
     │  re-renders       │
     └──────────────────┘
```

---

#### 6. Pagination

```
┌──────────────────────────────────────────────────────────┐
│         ⏮ First  ◀ Prev  [3/12]  Next ▶  Last ⏭        │
│                    Go to: [__] [Go]                       │
│                    Rows/page: [25 ▾]                      │
└───┬──────────┬──────────┬──────────┬──────────┬──────────┘
    │          │          │          │          │
    ▼          ▼          ▼          ▼          ▼
 set(1)    set(p-1)   set(p+1)   set(max)  set(input)
    │          │          │          │          │
    └──────────┴──────────┴──────────┴──────────┘
                          │
                          ▼
             ┌──────────────────────┐
             │  current_page.set(N) │
             │  save_ui_state()     │
             └──────────┬───────────┘
                        │
                ┌───────┴───────┐
                │               │
                ▼               ▼
       ┌──────────────┐  ┌──────────────────┐
       │ Lazy: SQL    │  │ In-memory:       │
       │ LIMIT/OFFSET │  │ DataFrame slice  │
       │ new page     │  │ [start:end]      │
       └──────┬───────┘  └────────┬─────────┘
              └────────┬──────────┘
                       ▼
             ┌──────────────────┐
             │  table_container  │
             │  + pagination_    │
             │  controls render  │
             └──────────────────┘
```

---

#### 7. Cell Edit

```
┌───────────────────────────┐
│  Click editable cell      │
│  (double-click/single)    │
└─────────────┬─────────────┘
              │
              ▼
  ┌────────────────────────────────┐
  │  JS: openCellPopup()          │
  │  Shows popup with:            │
  │  Current value │ Original val │
  │  [Save] [Copy] [Cancel]       │
  └──┬──────────┬──────────┬──────┘
     │          │          │
     ▼          ▼          ▼
 ┌────────┐ ┌────────┐ ┌────────────┐
 │ Save   │ │ Copy to│ │ Cancel:    │
 │ sends  │ │ clip-  │ │ close popup│
 │ cell_  │ │ board  │ │ (no server │
 │ edit   │ │ (JS)   │ │  call)     │
 └───┬────┘ └────────┘ └────────────┘
     │
     ▼
  ┌──────────────────────────────┐
  │  _handle_cell_edit()         │
  │  perform_cell_edit()         │
  │  {row, col, old, new}       │
  └──────────────┬───────────────┘
                 │
      ┌──────────┼──────────┐
      │          │          │
      ▼          ▼          ▼
 ┌─────────┐ ┌────────┐ ┌──────────┐
 │ data    │ │mods_log│ │ edited_  │
 │ .set()  │ │.set()  │ │ cells    │
 │ update  │ │append  │ │ track    │
 │ cell    │ │entry   │ │ {r,c}    │
 └─────────┘ └────────┘ └──────────┘
                 │
                 ▼
      ┌───────────────────────────┐
      │ auto-save to DB / file    │
      │ table re-renders with     │
      │ highlighted edited cell   │
      └───────────────────────────┘
```

---

#### 8. Row Selection + Approve/Reject

```
┌──────────────────────────────────────────────────┐
│  ☐ Select rows (click/shift-click/select-all)    │
└──────────────────────┬───────────────────────────┘
                       │
              ┌────────┴────────┐
              │                 │
              ▼                 ▼
     ┌──────────────┐  ┌───────────────┐
     │  [Approve]   │  │  [Reject]     │
     └──────┬───────┘  └───────┬───────┘
            │                  │
            ▼                  ▼
  ┌──────────────────────────────────────┐
  │  _approve_data() / _reject_data()   │
  │  1. get_selected_row_indices()      │
  │  2. _get_selected_pks(indices, df)  │
  │  3. create_approval/rejection_entry │
  └──────────────────┬───────────────────┘
                     │
          ┌──────────┼──────────┐
          │          │          │
          ▼          ▼          ▼
    ┌──────────┐ ┌────────┐ ┌────────────────┐
    │ mods_log │ │ save   │ │ _save_status_  │
    │ .set()   │ │ log to │ │ to_db() per PK │
    │ append   │ │ file   │ │ INSERT INTO    │
    │ entries  │ │        │ │ mods table     │
    └──────────┘ └────────┘ └────────────────┘
                     │
                     ▼
           ┌──────────────────┐
           │ table re-renders │
           │ with status color│
           │ histogram updates│
           └──────────────────┘
```

---

#### 9. Export

```
┌─────────────────────────────────────┐
│  Click [Export Selected] or         │
│        [Export All]                  │
└──────────────────┬──────────────────┘
                   │
                   ▼
      ┌────────────────────────────┐
      │  JS: openExportConfirmModal│
      │  PHI/PII warning dialog    │
      │  [I Understand] [Cancel]   │
      └─────────┬──────────────────┘
                │
                ▼
      ┌────────────────────────────────┐
      │  _prepare_export()             │
      │  export_state = "preparing"    │
      │                                │
      │  type == "selected"?           │
      │  YES ─► get selected row PKs   │
      │         filter df to those PKs │
      │  NO  ─► use full filtered/     │
      │         sorted df              │
      └────────────────┬───────────────┘
                       │
                       ▼
      ┌────────────────────────────────┐
      │  df.to_csv() ──► export_csv   │
      │  export_state = "ready"        │
      └────────────────┬───────────────┘
                       │
                       ▼
      ┌────────────────────────────────┐
      │  export_download_ui renders    │
      │  [Download CSV] button         │
      │  ──► browser downloads file    │
      │  export_state = "idle"         │
      └────────────────────────────────┘
```

---

#### 10. Column Management (Manage Layout)

```
┌──────────────────────────┐
│  Click [Manage Layout]   │
└────────────┬─────────────┘
             │
             ▼
  ┌─────────────────────────────────────────────┐
  │  Add Column Modal                           │
  │  ┌─────────────────────────────────────┐    │
  │  │  Active: [col1] [col2] [col3] [×]   │    │
  │  │  (drag to reorder)                  │    │
  │  ├─────────────────────────────────────┤    │
  │  │  Available: [col4] [col5] [col6]    │    │
  │  │  (click to add)                     │    │
  │  ├─────────────────────────────────────┤    │
  │  │  [Add All] [Remove All] [Update]    │    │
  │  └─────────────────────────────────────┘    │
  └──────────┬──────────────────────────────────┘
             │
     ┌───────┼───────┬───────┬───────┐
     │       │       │       │       │
     ▼       ▼       ▼       ▼       ▼
  drag    click    click    click   click
  reorder  add     remove   add    remove
  cols     col     col ×    all    all
     │       │       │       │       │
     └───────┴───────┴───────┴───────┘
                     │
                     ▼
         ┌───────────────────────┐
         │  active_columns.set() │
         │  + column_order input │
         └───────────┬───────────┘
                     │
             ┌───────┴───────┐
             │               │
             ▼               ▼
    ┌──────────────┐  ┌────────────────┐
    │ table re-    │  │ modal content  │
    │ renders with │  │ re-renders     │
    │ new columns  │  │ available list │
    └──────────────┘  └────────────────┘
```

---

#### 11. Column Resize & Drag (Table Headers)

```
┌───────────────────────────────────────────────────┐
│  Table Header Row                                 │
│  ┌──────┬──────┬──────┬──────┐                    │
│  │ ColA ↔ ColB ↔ ColC ↔ ColD │  ← drag to reorder│
│  │   ║     ║     ║     ║     │  ← drag ║ to resize│
│  └──────┴──────┴──────┴──────┘                    │
└───────────┬──────────────┬────────────────────────┘
            │              │
            ▼              ▼
    ┌──────────────┐  ┌───────────────────┐
    │  Drag header │  │  Drag resize      │
    │  to reorder  │  │  handle ║         │
    └──────┬───────┘  └───────┬───────────┘
           │                  │
           ▼                  ▼
  ┌──────────────────┐  ┌──────────────────┐
  │ JS: updateHeader │  │ JS: saveColumn   │
  │ Order() sends    │  │ Widths() sends   │
  │ input.column_    │  │ input.column_    │
  │ order = [...]    │  │ widths = {...}   │
  └────────┬─────────┘  └────────┬─────────┘
           │                     │
           ▼                     ▼
  ┌──────────────────┐  ┌──────────────────┐
  │ active_columns   │  │ column_widths    │
  │ .set(new order)  │  │ .set(new widths) │
  └──────────────────┘  └──────────────────┘
           │                     │
           └──────────┬──────────┘
                      ▼
             ┌──────────────────┐
             │ table re-renders │
             │ save_ui_state()  │
             └──────────────────┘
```

---

#### 12. Presets

```
┌───────────────────────────────────────┐
│  Click [Preset ▾] dropdown           │
└──────────────────┬────────────────────┘
                   │
                   ▼
  ┌───────────────────────────────────────────┐
  │  ● Default                                │
  │  ○ My Variant View              [×]       │
  │  ○ Clinical Review              [×]       │
  │  ─────────────────────────────────         │
  │  Save as: [________] [Save]               │
  │  [Save Layout] [Reset to Default] [⟳]     │
  └──┬──────┬─────────┬──────────┬────────────┘
     │      │         │          │
     ▼      ▼         ▼          ▼
  load   save new  save layout  delete
  preset  preset   to current   preset
     │      │         │          │
     ▼      ▼         ▼          ▼
  ┌────────────────────────────────────────┐
  │  column_presets reactive updated       │
  │  active_columns.set(preset cols)       │
  │  column_widths.set(preset widths)      │
  │  active_preset.set(name)               │
  └────────────────┬───────────────────────┘
                   │
           ┌───────┴───────┐
           │               │
           ▼               ▼
  ┌──────────────┐  ┌────────────────┐
  │ table re-    │  │ _save_presets  │
  │ renders with │  │ to file / DB   │
  │ new layout   │  │                │
  └──────────────┘  └────────────────┘
```

---

#### 13. Undo

```
┌────────────────────────────────────────┐
│  Modifications Log Modal               │
│  ┌──────────────────────────────────┐  │
│  │ #1  ColA: "old" → "new"  [Undo] │  │
│  │ #2  ColB: "x"   → "y"   [Undo] │  │
│  │ #3  Approved row PK={..} [Undo] │  │
│  └──────────────────────────────────┘  │
└───────────────────┬────────────────────┘
                    │
                    ▼
       ┌─────────────────────────┐
       │  _handle_undo()         │
       │  process_undo_action()  │
       │  perform_undo()         │
       └─────────────┬───────────┘
                     │
          ┌──────────┼──────────┐
          │          │          │
          ▼          ▼          ▼
    ┌──────────┐ ┌────────┐ ┌──────────┐
    │ data     │ │mods_log│ │ auto-save│
    │ .set()   │ │.set()  │ │ log +    │
    │ revert   │ │remove  │ │ data     │
    │ cell     │ │entry   │ │ state    │
    └──────────┘ └────────┘ └──────────┘
                     │
                     ▼
           ┌──────────────────┐
           │ table re-renders │
           │ cell un-highlighted│
           └──────────────────┘
```

---

#### 14. Save

```
┌──────────────────┐
│  Click [Save]    │
└────────┬─────────┘
         │
         ▼
┌──────────────────────────────────────────┐
│  _save_modifications()                   │
│  save_modifications_to_file(data, log)   │
└────────────────────┬─────────────────────┘
                     │
          ┌──────────┼──────────┐
          │          │          │
          ▼          ▼          ▼
   ┌───────────┐ ┌────────┐ ┌───────────┐
   │ Write     │ │ Write  │ │ DB mode:  │
   │ mods log  │ │ data   │ │ already   │
   │ JSON file │ │ state  │ │ persisted │
   │           │ │ JSON   │ │ per-edit  │
   └───────────┘ └────────┘ └───────────┘
         │
         ▼
┌──────────────────────┐
│  notification_show() │
│  "Saved successfully"│
└──────────────────────┘
```

---

#### 15. Synthesis (Materialized View Transform)

```
┌────────────────────────────────────────────────────────────────┐
│                     Synthesis Modal                            │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  SQL Query (read-only preview)                           │  │
│  │  SELECT ... FROM ... WHERE ... GROUP BY ...              │  │
│  ├──────────────────────────────────────────────────────────┤  │
│  │  Status: ✓ Ready — 1,234 rows  (cached 3m ago, TTL 10m) │  │
│  │  [Run Transform]  [Regenerate]  [Exit Synthesis]         │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────┬──────────────┬──────────────────┬─────────────────────┘
         │              │                  │
         ▼              ▼                  ▼
   ┌──────────┐   ┌───────────┐    ┌──────────────┐
   │ Run      │   │ Regenerate│    │ Exit         │
   │ (use     │   │ (force    │    │ (deactivate  │
   │ cache if │   │ refresh   │    │ synthesis    │
   │ valid)   │   │ matview)  │    │ fetcher)     │
   └────┬─────┘   └─────┬─────┘   └──────┬───────┘
        │                │                │
        ▼                ▼                │
   ┌─────────────────────────────┐        │
   │  config.run_synthesis()     │        │
   │  CREATE MATERIALIZED VIEW   │        │
   │       AS (user query)       │        │
   │  or REFRESH MATERIALIZED    │        │
   │       VIEW (force=True)     │        │
   └──────────────┬──────────────┘        │
                  │                       │
                  ▼                       │
   ┌──────────────────────────────┐       │
   │  activate_synthesis_fetcher  │       │
   │  DataFetcher._table_override │       │
   │  = matview table name        │       │
   │  active_columns synced       │       │
   └──────────────┬───────────────┘       │
                  │                       │
                  ▼                       ▼
   ┌──────────────────────────────────────────┐
   │  data.set(result_df)                     │
   │  _table_reload_trigger + 1               │
   │  table re-renders with synthesis data    │
   │  all filters/sort/pagination work on     │
   │  the materialized view via SQL           │
   └──────────────────────────────────────────┘
```

---

#### 16. Data Reload

```
┌──────────────────┐
│  Click [Reload]  │
└────────┬─────────┘
         │
         ▼
  ┌──────────────────────────────┐
  │  _reload_data()              │
  │                              │
  │  Lazy mode?                  │
  │  YES ─► refresh total_rows   │
  │         from DB COUNT(*)     │
  │  NO  ─► load_data_from_      │
  │         source() full reload │
  └──────────────┬───────────────┘
                 │
                 ▼
  ┌──────────────────────────────┐
  │  mods_log reloaded from DB   │
  │  current_page.set(1)         │
  │  table_container re-renders  │
  └──────────────────────────────┘
```

---

#### 17. Sidebar Toggle

```
  ┌──────────────────────────────────────────────┐
  │  ◀ Sidebar  │          Table Content          │
  │  ┌────────┐ │                                 │
  │  │Filters │ │                                 │
  │  │Search  │ │                                 │
  │  │Facets  │ │                                 │
  │  └────────┘ │                                 │
  └──────┬──────┴─────────────────────────────────┘
         │  Click ◀
         ▼
  ┌──────────────────────────────────────────────┐
  │ ▶ │              Table Content                │
  │   │          (full width now)                  │
  └───┴───────────────────────────────────────────┘
         │  Click ▶
         ▼
  (toggles back to expanded sidebar)

  JS: toggleLeftPanel()
  Scoped to containing widget via closest()
```

---

#### 18. Copy Column Values

```
┌──────────────────┐
│  Click [Copy]    │
│  in toolbar      │
└────────┬─────────┘
         │
         ▼
  ┌────────────────────────────┐
  │  Copy Column Modal         │
  │  ┌──────────────────────┐  │
  │  │  [Column A]          │  │
  │  │  [Column B]          │  │
  │  │  [Column C]          │  │
  │  └──────────────────────┘  │
  └──────────┬─────────────────┘
             │ click column name
             ▼
  ┌────────────────────────────────┐
  │  _handle_copy_request()        │
  │  process_copy_request()        │
  │  extract values for selected   │
  │  rows (or all on page)         │
  └────────────────┬───────────────┘
                   │
                   ▼
  ┌────────────────────────────────┐
  │  JS: navigator.clipboard      │
  │  .writeText(values)            │
  │  notification: "Copied!"       │
  └────────────────────────────────┘
```

---

#### 19. Full Render Pipeline

```
          ┌─────────────────────────────────┐
          │  Any reactive trigger fires:    │
          │  • search_state                 │
          │  • active_filters               │
          │  • status_filter_multi          │
          │  • current_sort                 │
          │  • current_page                 │
          │  • rows_per_page_value          │
          │  • mods_log                     │
          │  • data                         │
          │  • active_columns               │
          │  • _table_reload_trigger        │
          └───────────────┬─────────────────┘
                          │
                          ▼
               ┌─────────────────────┐
               │  is_lazy_loading()? │
               └──┬──────────────┬───┘
                  │              │
              YES ▼          NO  ▼
   ┌──────────────────┐  ┌──────────────────────┐
   │ _build_query_    │  │ _get_filtered_rows() │
   │ params()         │  │ pandas filtering     │
   │ ──► DataFetcher  │  │ + sort + slice       │
   │ .fetch_page()    │  │                      │
   │ SQL query with:  │  │                      │
   │  WHERE + ORDER   │  │                      │
   │  + LIMIT/OFFSET  │  │                      │
   └────────┬─────────┘  └──────────┬───────────┘
            │                       │
            └───────────┬───────────┘
                        │
                        ▼
            ┌──────────────────────────┐
            │  build_table_container() │
            │  HTML table with:        │
            │  • header (⋮ menus)      │
            │  • rows (editable cells) │
            │  • selection checkboxes  │
            │  • status highlighting   │
            │  • edit highlighting     │
            └──────────────┬───────────┘
                           │
                           ▼
            ┌──────────────────────────┐
            │  JS post-render inits:   │
            │  • initRowSelection()    │
            │  • initHeaderDrag()      │
            │  • initColumnResize()    │
            │  • initHistogramCBs()    │
            │  • initFacetCBs()        │
            └──────────────────────────┘
```

### Running Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests with coverage
pytest tests/ --cov=src --cov-report=term-missing
```

### Current Test Coverage

- **1277+ tests passing** (~1.5s runtime)
- **96.5% public function coverage** (222/230 functions)
- Database modules: 90–100% coverage
- Utility modules: 93–100% coverage
- Security: 5-layer SQL injection defense, golden-SQL regression tests

## Requirements

- Python 3.10+
- shiny >= 1.0.0
- pandas >= 2.0.0
- sqlalchemy >= 2.0.0
- psycopg2-binary >= 2.9.0

## License

MIT License
