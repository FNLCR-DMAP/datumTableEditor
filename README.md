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

### Database Settings

| Setting | Type | Description |
|---------|------|-------------|
| `enabled` | bool | Enable database mode |
| `connection_string` | str | PostgreSQL connection URL |
| `data_table` | str | Main data table name |
| `mods_table` | str | Modifications tracking table |
| `state_table` | str | UI state persistence table |
| `auto_detect_pk` | bool | Auto-detect primary key from schema |
| `max_rows_per_page` | int | Maximum rows per page (default: 100) |

### Table Settings

| Setting | Type | Description |
|---------|------|-------------|
| `primary_key` | list | Primary key column(s) |
| `editable_columns` | list | Columns users can edit |
| `display_columns` | list | Columns to display |
| `status_column` | str | Column for status workflow |

### Query Settings

| Setting | Type | Description |
|---------|------|-------------|
| `searchable_columns` | list | Columns for text search |
| `filter_columns` | dict | Column filter types (select/text/range) |
| `default_sort_column` | str | Initial sort column |
| `default_sort_ascending` | bool | Initial sort direction |

## Environment Variables

All configuration can be overridden via environment variables, which is useful for production deployments (e.g., RStudio Connect) where you don't want secrets in config files.

### Database Settings

| Environment Variable | Config Field | Description |
|---------------------|--------------|-------------|
| `APP_DATABASE_ENABLED` | `database.enabled` | Enable database mode (`true`/`false`) |
| `APP_DATABASE_MODE` | `database.mode` | `direct` (SQLAlchemy) or `datum` (proxy) |
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

- **497 tests passing**
- **62% overall coverage**
- Database modules: 90-100% coverage
- Utility modules: 93-100% coverage

## Requirements

- Python 3.9+
- shiny >= 0.6.0
- pandas >= 1.5.0
- sqlalchemy >= 2.0.0
- psycopg2-binary >= 2.9.0

## License

MIT License
