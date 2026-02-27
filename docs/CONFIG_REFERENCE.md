# Configuration Reference

Complete reference for every option in `app_config.json`.

```
Configuration priority (highest → lowest):
  1. Environment variables  (APP_*, DATUM_*)
  2. Config file            (app_config.json)
  3. Schema defaults        (app_config_schema.py)
```

Start from the annotated template:

```bash
cp template/app_config.template.json app_config.json
```

---

## Table of Contents

- [Top-Level](#top-level)
- [data_source](#data_source)
- [database](#database)
- [persistence](#persistence)
- [query](#query)
- [state](#state)
- [table](#table)
- [permissions](#permissions)
- [synthesis](#synthesis)
- [Feature Flags](#feature-flags)
- [Status Labels](#status_labels)
- [Status Values](#status_values)
- [Approval Assignment](#approval_assignment)
- [Environment Variables](#environment-variables)

---

## Top-Level

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `app_title` | string | `"Epitopes Data Editor"` | Title shown in the browser tab and header |
| `app_version` | string | `"1.0.0"` | Version string (informational) |

---

## data_source

Legacy data source configuration. When `database.enabled = true`, only `source_type` and `table_name` matter.

```json
"data_source": { ... }
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `source_type` | `"csv"` \| `"json"` \| `"api"` \| `"database"` | `"csv"` | Where to load data from |
| `table_name` | string | `"data"` | Identifier for the dataset |
| `file_path` | string \| null | `null` | Path to CSV or JSON file |
| `api_url` | string \| null | `null` | HTTP endpoint for API-based data |
| `api_headers` | object | `{}` | HTTP headers sent with API requests |
| `api_method` | string | `"GET"` | HTTP method for API requests |
| `db_connection_string` | string \| null | `null` | SQLAlchemy connection string (legacy) |
| `db_query` | string \| null | `null` | SQL query to load data (legacy) |
| `db_table` | string \| null | `null` | Table name to load (legacy) |
| `date_columns` | array | `[]` | Columns to parse as dates |
| `numeric_columns` | array | `[]` | Columns to parse as numbers |

---

## database

PostgreSQL database configuration. This section controls how the widget connects to the database, which tables to use, and connection pool tuning.

```json
"database": { ... }
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | bool | `false` | Enable database mode. When `false`, uses local CSV mode |
| `mode` | `"direct"` \| `"datum"` | `"direct"` | `direct` = SQLAlchemy. `datum` = via Datum proxy service |
| `connection_string` | string \| null | `null` | PostgreSQL connection string (direct mode). Example: `postgresql://user@host/dbname` |
| `source_table` | string \| null | `null` | Optional read-only source table. If `data_table` doesn't exist, it is created as a copy |
| `data_table` | string | `"epitopes_data"` | Working data table name |
| `mods_table` | string | `"epitopes_modifications"` | Modifications tracking table (auto-created) |
| `state_table` | string | `"epitopes_ui_state"` | UI state persistence table (per-user: `{state_table}_{username}`) |
| `status_column` | string | `"Status"` | Column in the data table used for modification status tracking |
| `auto_detect_pk` | bool | `true` | Auto-detect primary key from database schema |
| `pool_size` | int | `5` | SQLAlchemy connection pool size (direct mode only) |
| `max_overflow` | int | `10` | Max overflow connections beyond pool_size |
| `pool_timeout` | int | `30` | Seconds to wait for a connection from the pool |
| `max_rows` | int \| null | `null` | Maximum rows to load. `null` = no limit |
| `lazy_loading` | bool | `false` | When `true`, uses DB-level pagination (fetches only current page). Faster startup, less memory |
| `page_buffer_size` | int | `300` | Rows per query when `lazy_loading` is enabled |
| `max_rows_per_page` | int | `100` | Hard upper limit for rows per page |
| `default_rows_per_page` | int | `25` | Default rows per page when lazy loading |

### Datum Proxy Settings

Only used when `mode = "datum"`.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `datum_base_url` | string \| null | `null` | Datum proxy base URL |
| `datum_token` | string \| null | `null` | Datum API authentication token |
| `datum_service_name` | string | `"postgres_sql"` | Datum service name |
| `datum_database` | string \| null | `null` | Database name in Datum |
| `datum_schema` | string \| null | `null` | Schema name in Datum (e.g. `"public"`) |

---

## persistence

Controls how edits and state are saved.

```json
"persistence": { ... }
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `persistence_type` | `"local"` \| `"api"` \| `"database"` | `"local"` | Where to persist modifications |
| `modifications_log_path` | string \| null | `null` | Path for the local JSON modifications log |
| `data_state_path` | string \| null | `null` | Path for the data state snapshot |
| `export_path` | string \| null | `null` | Default directory for CSV exports |
| `api_save_url` | string \| null | `null` | HTTP endpoint for API-based saving |
| `api_headers` | object | `{}` | HTTP headers for save requests |
| `auto_save` | bool | `true` | Auto-save modifications |
| `auto_save_interval_ms` | int | `0` | Auto-save interval in milliseconds. `0` = immediate |

---

## query

Controls search, filtering, and faceted sidebar filters.

```json
"query": { ... }
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `searchable_columns` | array | `[]` | Columns to include in text search. Empty = all text columns |
| `enable_search` | bool | `true` | Show the search bar. Set `false` to hide |
| `search_case_sensitive` | bool | `false` | Case-sensitive search |
| `search_regex_enabled` | bool | `false` | Allow regex in search |
| `filter_columns` | object | `{}` | Columns available as dropdown filters. Format: `{"ColName": "text"|"numeric"|"date"|"select"}` |
| `default_filters` | object | `{}` | Filters applied on load (see below) |
| `status_filter_enabled` | bool | `true` | Show status filter in sidebar |
| `status_column` | string | `"Status"` | Column name for status tracking |
| `facet_columns` | array | `[]` | Columns shown as faceted checkbox+count panels in sidebar |
| `facet_max_values` | int | `5` | Values to show per facet before "Show more" |

### Default Filters Format

Default filters support both simple values and operator objects:

```json
"default_filters": {
  "Status": ["Completed", "Others"],
  "Gene_names": "TP53",
  "Date": {"op": "last_n_days", "value": 7},
  "ID": {"op": "not_contains", "value": "RT"},
  "Library": {"op": "not_empty"}
}
```

**Supported operators:**

| Operator | Description | Example |
|----------|-------------|---------|
| `in` | Value in list | `{"op": "in", "value": ["A", "B"]}` |
| `not_in` | Value not in list | `{"op": "not_in", "value": ["X"]}` |
| `contains` | Substring match | `{"op": "contains", "value": "TP53"}` |
| `not_contains` | Exclude substring | `{"op": "not_contains", "value": "RT"}` |
| `between` | Range (inclusive) | `{"op": "between", "value": [0, 100]}` |
| `gt` / `gte` | Greater than / or equal | `{"op": "gt", "value": 50}` |
| `lt` / `lte` | Less than / or equal | `{"op": "lte", "value": 99}` |
| `last_n_days` | Within last N days | `{"op": "last_n_days", "value": 7}` |
| `not_empty` | Column is not null/empty | `{"op": "not_empty"}` |
| `regex` | Regular expression match | `{"op": "regex", "value": "^TP\\d+"}` |

---

## state

Controls what UI state to persist across sessions.

```json
"state": { ... }
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `persist_state` | bool | `true` | Enable state persistence |
| `state_storage` | `"local"` \| `"session"` \| `"url"` | `"local"` | Where to store state |
| `state_file_path` | string \| null | `null` | Path for local state file |
| `persist_filters` | bool | `true` | Remember active filters |
| `persist_sort` | bool | `true` | Remember sort order |
| `persist_page` | bool | `true` | Remember current page |
| `persist_column_selection` | bool | `true` | Remember visible columns |
| `persist_column_widths` | bool | `true` | Remember column widths |
| `session_timeout_minutes` | int | `30` | Session timeout |

---

## table

Table display defaults — columns, sorting, pagination, editing rules.

```json
"table": { ... }
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `title` | string | `"Data Table"` | Table title shown in header |
| `primary_key` | array | `["id"]` | Primary key column(s) for row identification |
| `default_columns` | array | `[]` | Columns visible on load. Empty = all columns |
| `default_column_widths` | object | `{}` | Column widths in pixels. Format: `{"ColName": 150}` |
| `default_sort_column` | string \| null | `null` | Column to sort by on load |
| `default_sort_ascending` | bool | `true` | Sort direction |
| `default_rows_per_page` | int | `25` | Rows per page |
| `rows_per_page_options` | array | `[10, 25, 50, 100, "all"]` | Page size options |
| `editable_columns` | array | `[]` | Columns users can edit. Empty = all editable |
| `readonly_columns` | array | `[]` | Columns that are never editable (overrides `editable_columns`) |
| `column_masks` | object | `{}` | Display name overrides. Format: `{"real_col": "Display Name"}` |
| `presets_enabled` | bool | `true` | Enable column preset switching |
| `presets_file_path` | string \| null | `null` | Path to saved presets JSON file |
| `default_preset` | string | `"Default"` | Name of the preset to load on startup |

---

## permissions

Role-based access control.

```json
"permissions": { ... }
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `default_role` | `"viewer"` \| `"editor"` | `"viewer"` | Role for users not in `user_roles` |
| `user_roles` | object | `{}` | Map of `username → role`. Example: `{"alice": "editor", "bob": "viewer"}` |

**Roles:**

| Role | Can View | Can Edit | Can Save | Can Approve/Reject | Can Undo |
|------|----------|----------|----------|-------------------|----------|
| `editor` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `viewer` | ✓ | ✗ | ✗ | ✗ | ✗ |

---

## synthesis

SQL transform feature. When enabled, a button appears in the toolbar that runs a configured SQL query, materialises the result into a temporary table, and caches it with a TTL.

```json
"synthesis": { ... }
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `query` | string | `""` | SQL SELECT query to execute. Result is materialised via `CREATE TABLE AS` |
| `result_table_prefix` | string | `"_synthesis_result"` | Name for the materialised result table (shared across users) |
| `ttl_minutes` | int | `10` | Cache lifetime in minutes. `0` = always regenerate |
| `label` | string | `"Synthesis"` | Button and modal title text |

---

## Feature Flags

Top-level boolean flags that toggle UI features on or off.

```json
{
  "enable_approval_workflow": true,
  "enable_save_button": true,
  "enable_export": true,
  "enable_undo": true,
  "enable_copy_column": true,
  "enable_status_filter": true,
  "enable_synthesis": false,
  "enable_review_detail": false,
  "fix_filter": false
}
```

| Key | Default | Description |
|-----|---------|-------------|
| `enable_approval_workflow` | `true` | Show Approve/Reject buttons and status column |
| `enable_save_button` | `true` | Show the Save button in toolbar |
| `enable_export` | `true` | Show the Export button |
| `enable_undo` | `true` | Show the Undo button |
| `enable_copy_column` | `true` | Show "Copy Column Values" in column menu |
| `enable_status_filter` | `true` | Show status distribution and filter in sidebar |
| `enable_synthesis` | `false` | Show the Synthesis transform button |
| `enable_review_detail` | `false` | Show the Review Detail button. Emits an event via commute layer with the selected row PK for cross-widget communication |
| `fix_filter` | `false` | Lock filters to only the `default_filters` from config. Users cannot add or remove filters |

---

## status_labels

Maps internal status keys to display labels. Internal keys **must not change**.

```json
"status_labels": {
  "unprocessed": "Unreviewed",
  "edited": "Edited",
  "approved": "Accepted",
  "rejected": "Rejected"
}
```

| Internal Key | Schema Default | Description |
|-------------|----------------|-------------|
| `unprocessed` | `"Unprocessed"` | Row has no modifications |
| `edited` | `"Edited"` | Row has field modifications |
| `approved` | `"Approved"` | Row has been approved |
| `rejected` | `"Rejected"` | Row has been rejected |

Display labels are used in:
- Status column badges in the table
- Status filter sidebar
- Status distribution counts

Values in the database `status_column` that match these labels (case-insensitive) are also recognised and mapped to the internal key.

---

## status_values

Controls what value is **written to the database** when Approve/Reject buttons are clicked.

```json
"status_values": {
  "approved": "approved",
  "rejected": "rejected"
}
```

| Key | Default | Description |
|-----|---------|-------------|
| `approved` | `"approved"` | Value written to DB status column on Approve |
| `rejected` | `"rejected"` | Value written to DB status column on Reject |

**Example** — if your database uses `"Accepted"`/`"Declined"`:

```json
"status_values": {
  "approved": "Accepted",
  "rejected": "Declined"
}
```

The SQL `_mod_status` expression automatically normalises these custom values back to internal keys for status filtering and display.

---

## approval_assignment

Column-to-column copy that runs automatically when rows are approved.

For each `{source: target}` pair, the value in the source column is read from the approved row and written to the target column in the database.

```json
"approval_assignment": {
  "Draft_Value": "Final_Value",
  "Notes": "Approved_Notes"
}
```

| Key (source column) | Value (target column) | What happens |
|---------------------|----------------------|--------------|
| `"Draft_Value"` | `"Final_Value"` | `Draft_Value` is copied into `Final_Value` |
| `"Notes"` | `"Approved_Notes"` | `Notes` is copied into `Approved_Notes` |

- **Only runs on Approve**, not Reject
- Writes are saved as `field_modification` entries in the modifications table
- Set to `{}` (empty object) to disable — this is the default

---

## Environment Variables

Environment variables override config file values (highest priority).

### Data Source

| Variable | Maps to |
|----------|---------|
| `APP_DATA_SOURCE_TYPE` | `data_source.source_type` |
| `APP_DATA_FILE_PATH` | `data_source.file_path` |
| `APP_DATA_API_URL` | `data_source.api_url` |

### Persistence

| Variable | Maps to |
|----------|---------|
| `APP_PERSISTENCE_TYPE` | `persistence.persistence_type` |
| `APP_MODIFICATIONS_LOG_PATH` | `persistence.modifications_log_path` |
| `APP_SAVE_API_URL` | `persistence.api_save_url` |

### Database

| Variable | Maps to |
|----------|---------|
| `APP_DATABASE_ENABLED` | `database.enabled` (accepts `true`, `1`, `yes`) |
| `APP_DATABASE_MODE` | `database.mode` |
| `APP_DB_CONNECTION_STRING` | `database.connection_string` |
| `APP_DB_DATA_TABLE` | `database.data_table` |
| `APP_DB_MODS_TABLE` | `database.mods_table` |
| `APP_DB_STATE_TABLE` | `database.state_table` |

### Datum Proxy

| Variable | Maps to |
|----------|---------|
| `DATUM_BASE_URL` | `database.datum_base_url` |
| `DATUM_API_TOKEN` | `database.datum_token` |
| `DATUM_DATABASE` | `database.datum_database` |
| `DATUM_SCHEMA` | `database.datum_schema` |
| `DATUM_SERVICE_NAME` | `database.datum_service_name` |

---

## Minimal Examples

### CSV Mode (Simplest)

```json
{
  "data_source": {
    "source_type": "csv",
    "file_path": "data/my_data.csv"
  },
  "table": {
    "primary_key": ["id"]
  }
}
```

### Database Mode (Direct)

```json
{
  "data_source": { "source_type": "database" },
  "database": {
    "enabled": true,
    "mode": "direct",
    "connection_string": "postgresql://user@localhost/mydb",
    "data_table": "my_schema.my_table",
    "mods_table": "my_schema.modifications",
    "auto_detect_pk": true
  },
  "table": {
    "primary_key": ["id"]
  }
}
```

### Database Mode (Datum Proxy)

```json
{
  "data_source": { "source_type": "database" },
  "database": {
    "enabled": true,
    "mode": "datum",
    "datum_base_url": "https://datum.example.com",
    "datum_token": "your-token-here",
    "datum_database": "mydb",
    "datum_schema": "public",
    "data_table": "my_table"
  }
}
```

### Read-Only Viewer

```json
{
  "permissions": {
    "default_role": "viewer"
  },
  "enable_approval_workflow": false,
  "enable_save_button": false,
  "enable_undo": false
}
```

### Custom Approval Workflow

```json
{
  "status_labels": {
    "unprocessed": "Pending",
    "edited": "Modified",
    "approved": "Accepted",
    "rejected": "Declined"
  },
  "status_values": {
    "approved": "Accepted",
    "rejected": "Declined"
  },
  "approval_assignment": {
    "draft_result": "final_result",
    "reviewer_notes": "approved_notes"
  }
}
```

### Lazy Loading with Facets

```json
{
  "database": {
    "enabled": true,
    "lazy_loading": true,
    "max_rows_per_page": 50,
    "default_rows_per_page": 25
  },
  "query": {
    "facet_columns": ["Status", "Gene_names", "PatientID"],
    "facet_max_values": 10,
    "default_filters": {
      "ngs_test": {"op": "in", "value": ["RNA_Access"]},
      "sequencing_date": {"op": "last_n_days", "value": 30}
    }
  },
  "fix_filter": true
}
```
