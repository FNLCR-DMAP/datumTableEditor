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

### Running Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests with coverage
pytest tests/ --cov=src --cov-report=term-missing
```

### Current Test Coverage

- **1237+ tests passing** (~1.5s runtime)
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
