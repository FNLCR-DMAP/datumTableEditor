# Quick Reference Card

## Starting the App

```bash
# Standalone
shiny run app.py

# As a widget (multi-tab)
from dmapTableEditor import table_editor_ui, table_editor_server
```

Browser: `http://localhost:8000` (auto-increments if in use)

## Project Structure

```
dmapTableEditor/
├── app_config.json          # Per-deployment configuration
├── template/
│   └── app_config.template.json   # Full annotated template
├── src/
│   ├── server.py            # Shiny server logic
│   ├── ui.py                # Shiny UI definition
│   ├── config/              # Configuration schema & loader
│   ├── db/                  # Database layer (query builder, session book)
│   ├── utils/               # Filters, modals, column helpers, pagination
│   ├── processing/          # Data processing utilities
│   ├── widgets/             # Reusable Shiny widget modules
│   ├── css/                 # Stylesheets (table, layout, modal, etc.)
│   └── js/                  # JavaScript (drag, selection, cell-edit, etc.)
├── tests/                   # pytest suite (1237+ tests)
└── tooling/                 # QC, coverage, golden-SQL extraction
```

## UI Buttons

| Button | Action |
|--------|--------|
| 💾 Save | Persist edits to database |
| 📥 Export | Download current view as CSV |
| ↩ Undo | Revert last modification |
| ✅ Approve | Mark selected rows as approved |
| ❌ Reject | Mark selected rows as rejected |
| Clear Selection | Deselect all row checkboxes |
| Synthesis | Run configured SQL transform (when enabled) |
| Column Presets | Switch between saved column sets |

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Tab | Move to next editable cell |
| Shift+Tab | Move to previous cell |
| Enter | Confirm edit |
| Esc | Cancel edit / close modal |
| Shift+Click (row checkbox) | Range-select rows |

---

## `app_config.json` — Complete Reference

### Top-Level Keys

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `app_title` | string | `"Epitopes Data Editor"` | Title displayed in the header |
| `app_version` | string | `"1.0.0"` | Version string |

### `data_source`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `source_type` | string | `"csv"` | `csv`, `json`, `api`, or `database` |
| `table_name` | string | `"data"` | Identifier for the dataset |
| `file_path` | string | `null` | Path to CSV/JSON file |
| `api_url` | string | `null` | API endpoint for remote data |
| `api_headers` | object | `{}` | HTTP headers for API calls |

### `database`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | bool | `false` | Enable PostgreSQL mode |
| `mode` | string | `"direct"` | `direct` (SQLAlchemy) or `datum` (proxy) |
| `connection_string` | string | `null` | PostgreSQL connection URL (direct mode) |
| `source_table` | string | `""` | Source table to copy from (optional) |
| `data_table` | string | `"epitopes_data"` | Working data table |
| `mods_table` | string | `"epitopes_modifications"` | Modifications tracking table |
| `state_table` | string | `"epitopes_ui_state"` | UI state persistence table |
| `status_column` | string | `"Status"` | Column holding row status |
| `auto_detect_pk` | bool | `true` | Auto-detect primary key from DB schema |
| `pool_size` | int | `5` | Connection pool size (direct mode) |
| `max_overflow` | int | `10` | Max pool overflow connections |
| `pool_timeout` | int | `30` | Seconds to wait for a connection |
| `max_rows` | int\|null | `null` | Maximum rows to load (`null` = all) |
| `lazy_loading` | bool | `false` | DB-level pagination (fetch only current page) |
| `page_buffer_size` | int | `300` | Rows per query when lazy loading |
| `max_rows_per_page` | int | `100` | Hard upper limit per page |
| `default_rows_per_page` | int | `25` | Initial page size |
| `datum_base_url` | string | `""` | Datum proxy base URL |
| `datum_token` | string | `""` | Datum API token |
| `datum_database` | string | `""` | Target database (datum mode) |
| `datum_schema` | string | `"public"` | Database schema (datum mode) |
| `datum_service_name` | string | `"postgres_sql"` | Service name (datum mode) |

### `persistence`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `persistence_type` | string | `"local"` | `local`, `api`, or `database` |
| `export_path` | string | `null` | Directory for exports |
| `auto_save` | bool | `true` | Auto-save on edit |

### `query`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `searchable_columns` | array | `[]` | Columns included in text search (empty = all) |
| `filter_columns` | object | `{}` | Filterable columns with type: `"select"`, `"text"`, `"numeric"`, `"date"` |
| `default_filters` | object | `{}` | Filters applied on initial load (see [Filter Operators](#filter-operators)) |
| `status_filter_enabled` | bool | `true` | Show status filter in sidebar |
| `status_column` | string | `"Status"` | Column for status filtering |
| `search_case_sensitive` | bool | `false` | Case-sensitive search |
| `search_regex_enabled` | bool | `false` | Allow regex in search input |

### `state`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `persist_state` | bool | `true` | Persist UI state across sessions |
| `state_storage` | string | `"local"` | `local`, `session`, or `url` |
| `state_file_path` | string | `null` | Path for local state file |
| `persist_filters` | bool | `true` | Remember active filters |
| `persist_sort` | bool | `true` | Remember sort column/direction |
| `persist_page` | bool | `true` | Remember current page |
| `persist_column_selection` | bool | `true` | Remember visible columns |
| `persist_column_widths` | bool | `true` | Remember column widths |
| `session_timeout_minutes` | int | `30` | Session TTL |

### `table`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `title` | string | `"Data Table"` | Title shown above the table |
| `primary_key` | array | `["id"]` | Primary key column(s) |
| `default_columns` | array | `[]` | Columns visible by default (empty = all) |
| `default_column_width` | int | `130` | Default pixel width for columns |
| `default_column_widths` | object | `{}` | Per-column widths: `{"col": 200}` |
| `default_sort_column` | string | `null` | Initial sort column |
| `default_sort_ascending` | bool | `true` | Initial sort direction |
| `default_rows_per_page` | int | `25` | Initial rows per page |
| `rows_per_page_options` | array | `[10,25,50,100,"all"]` | Page-size dropdown choices |
| `editable_columns` | array | `[]` | Columns users can edit (empty = all) |
| `readonly_columns` | array | `[]` | Columns that cannot be edited |
| `column_masks` | object | `{}` | Display-name overrides: `{"real_name": "Display Name"}` |
| `presets_enabled` | bool | `true` | Enable column presets |
| `presets_file_path` | string | `null` | Path to column presets file |
| `default_preset` | string | `"Default"` | Preset to activate on load |

### Feature Flags

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enable_approval_workflow` | bool | `true` | Show approve/reject buttons and status column |
| `enable_save_button` | bool | `true` | Show the save button in toolbar |
| `enable_export` | bool | `true` | Show the export button |
| `enable_undo` | bool | `true` | Show the undo button |
| `enable_copy_column` | bool | `true` | Allow copying column values |
| `enable_status_filter` | bool | `true` | Show status distribution in sidebar |
| `enable_synthesis` | bool | `false` | Enable the synthesis transform feature |
| `fix_filter` | bool | `false` | Lock filters to only `default_filters` (users cannot add/remove) |

### `synthesis`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `query` | string | `""` | SQL SELECT to materialize |
| `result_table_prefix` | string | `"_synthesis_result"` | Table name for cached result |
| `ttl_minutes` | int | `10` | Cache lifetime (0 = always regenerate) |
| `label` | string | `"Synthesis"` | Button and modal title label |

### `status_labels`

Customize the display labels for each internal status. Internal keys **must not change**.

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

Values set here also serve as recognized values in the `status_column` when reading from database.

### `permissions`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `default_role` | string | `"viewer"` | Role for users not in `user_roles` |
| `user_roles` | object | `{}` | Map of `username → role` (e.g. `{"alice": "editor"}`) |

Roles: `editor` (full access), `viewer` (read-only — can view, search, filter, export).

---

## Filter Operators

The `default_filters` object in `query` supports three formats:

### Simple Values

```json
{
  "clinical_or_research": "Clinical",
  "Status": ["Completed", "Others"]
}
```

A plain string performs exact match. An array matches any value in the list (`IN`).

### Operator Objects

```json
{
  "column_name": {"op": "<operator>", "value": <value>}
}
```

### Available Operators

| Operator | Value Type | SQL Equivalent | Description |
|----------|-----------|----------------|-------------|
| `in` | array | `col IN (...)` | Match any value in list |
| `not_in` | array | `col NOT IN (...)` | Exclude values in list |
| `contains` | string | `col ILIKE '%v%'` | Case-insensitive substring match |
| `not_contains` | string | `col NOT ILIKE '%v%'` | Exclude substring matches |
| `between` | `[min, max]` | `col BETWEEN a AND b` | Inclusive range |
| `gt` | number/string | `col > v` | Greater than |
| `gte` | number/string | `col >= v` | Greater than or equal |
| `lt` | number/string | `col < v` | Less than |
| `lte` | number/string | `col <= v` | Less than or equal |
| `last_n_days` | integer | `CAST(col AS DATE) >= CURRENT_DATE - N` | Rows within last N days |
| `not_empty` | *(none)* | `col IS NOT NULL AND col != ''` | Non-null, non-blank values |
| `regex` | string | `col ~* pattern` | PostgreSQL case-insensitive regex |

### Filter Examples

```json
{
  "default_filters": {
    "sequencing_date": {"op": "last_n_days", "value": 7},
    "ngs_test": {"op": "in", "value": ["RNA_Access", "RNA_Access_v1"]},
    "status": {"op": "in", "value": ["Completed", "Others"]},
    "clinical_or_research": "Clinical",
    "gene": {"op": "contains", "value": "TP53"},
    "library_id": {"op": "not_contains", "value": "RT"},
    "score": {"op": "between", "value": [0.5, 1.0]},
    "age": {"op": "gte", "value": 18},
    "comments": {"op": "not_empty"},
    "variant": {"op": "regex", "value": "^chr[0-9]+"}
  }
}
```

> **Note:** `last_n_days` value can be an integer or a single-element list (e.g. `[7]`). Both forms are accepted.

---

## Environment Variables

All configuration can be overridden via environment variables for production deployments.

### Database

| Variable | Config Field |
|----------|--------------|
| `APP_DATABASE_ENABLED` | `database.enabled` |
| `APP_DATABASE_MODE` | `database.mode` |
| `APP_DB_CONNECTION_STRING` | `database.connection_string` |
| `APP_DB_DATA_TABLE` | `database.data_table` |
| `APP_DB_MODS_TABLE` | `database.mods_table` |
| `APP_DB_STATE_TABLE` | `database.state_table` |

### Datum Proxy

| Variable | Config Field |
|----------|--------------|
| `DATUM_BASE_URL` | `database.datum_base_url` |
| `DATUM_API_TOKEN` | `database.datum_token` |
| `DATUM_DATABASE` | `database.datum_database` |
| `DATUM_SCHEMA` | `database.datum_schema` |
| `DATUM_SERVICE_NAME` | `database.datum_service_name` |

### Data Source / Persistence

| Variable | Config Field |
|----------|--------------|
| `APP_DATA_SOURCE_TYPE` | `data_source.source_type` |
| `APP_DATA_FILE_PATH` | `data_source.file_path` |
| `APP_PERSISTENCE_TYPE` | `persistence.persistence_type` |

---

## Database Schema

Tables are auto-created if they don't exist:

### Modifications Table

```sql
CREATE TABLE <schema>.modifications (
    id SERIAL PRIMARY KEY,
    row_pk JSONB NOT NULL,
    column_name VARCHAR(255),
    old_value TEXT,
    new_value TEXT,
    mod_type VARCHAR(50) NOT NULL,
    undone BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    created_by VARCHAR(255)
);
```

### UI State Table (per-user)

```sql
CREATE TABLE <schema>.ui_state_<username> (
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
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Port in use | App auto-increments to next available port |
| Module not found | `pip install -e ".[dev]"` or `pip install -r requirements.txt` |
| No columns shown | Check `table.default_columns` in config; empty = all columns |
| Changes not saved | Click "Save" or ensure `persistence.auto_save` is `true` |
| Filter not working | Verify column name matches database (case-sensitive) |
| `last_n_days` error | Ensure value is an integer, not a string (e.g. `7` not `"7 days"`) |
| Lazy loading slow | Increase `database.page_buffer_size` |
| Status labels wrong | Check `status_labels` keys match internal keys exactly |

## Performance Tips

- **Large datasets**: Enable `lazy_loading` for DB-level pagination
- **Slow startup**: Set `max_rows` to limit initial load
- **Many columns**: Use column presets to show only relevant columns
- **Frequent edits**: `auto_save: true` persists changes immediately
- **Export**: Exports honour current filters and sort order

---

**Last Updated:** February 2026
