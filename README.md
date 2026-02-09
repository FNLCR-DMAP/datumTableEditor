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

The package auto-creates required tables if they don't exist:

### Modifications Table
```sql
CREATE TABLE modifications (
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
```

### UI State Table
```sql
CREATE TABLE ui_state (
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
