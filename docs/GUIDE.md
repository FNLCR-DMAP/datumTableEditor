# dmapTableEditor — User Guide

## Overview

dmapTableEditor is a reusable PyShiny table-editor widget backed by PostgreSQL. It can run standalone or be embedded as a module in multi-tab Shiny applications. Key capabilities:

- **Inline cell editing** with full modification audit trail
- **Database-backed persistence** via SQLAlchemy (direct) or Datum proxy
- **Rich filtering** — 12 filter operators including date ranges, regex, and set membership
- **Column presets** — save/restore custom column views per user
- **Approval workflow** — approve, reject, and undo row-level actions
- **Synthesis transforms** — run cached SQL materializations on demand
- **Role-based permissions** — editor vs. viewer access

## Quick Start

### 1. Install

```bash
pip install dmapTableEditor
# or from source
pip install -e ".[dev]"
```

### 2. Configure

```bash
cp template/app_config.template.json app_config.json
# Edit app_config.json with your database settings
```

### 3. Run

```bash
shiny run app.py
```

Open `http://localhost:8000` in your browser.

---

## Configuration

All behaviour is controlled by `app_config.json`. See **template/app_config.template.json** for a fully annotated example and **docs/CONFIG_REFERENCE.md** for the complete schema reference with every option documented.

### Minimal Config (Database Mode)

```json
{
  "app_title": "My Editor",
  "database": {
    "enabled": true,
    "mode": "direct",
    "connection_string": "postgresql://user:pass@localhost/mydb",
    "data_table": "my_data",
    "mods_table": "my_schema.modifications",
    "state_table": "my_schema.ui_state"
  },
  "table": {
    "primary_key": ["id"],
    "default_columns": ["id", "name", "status", "date"]
  }
}
```

### Configuration Priority

1. **Environment variables** (`APP_DATABASE_ENABLED`, `DATUM_BASE_URL`, etc.)
2. **Config file** (`app_config.json`)
3. **Built-in defaults**

---

## Features

### Inline Cell Editing

Click any cell in an editable column to open the edit popup. Changes are tracked in the modifications table with full before/after values.

- **Editable columns**: Controlled by `table.editable_columns` (empty = all editable)
- **Readonly columns**: Explicitly locked via `table.readonly_columns`
- **Auto-save**: When `persistence.auto_save` is `true`, edits persist immediately

### Column Management

- **Drag to reorder** — drag column headers to rearrange
- **Resize** — drag header borders to adjust width
- **Sort** — click the column header dropdown to sort ascending/descending
- **Remove/Add** — use the header dropdown or the column management modal
- **Presets** — save named column configurations and switch between them

### Search & Filter

#### Text Search

The search bar filters rows across all `query.searchable_columns` (or all text columns if empty). Case-sensitivity and regex support are controlled by `query.search_case_sensitive` and `query.search_regex_enabled`.

#### Column Filters

Dynamic column filters can be added from the sidebar. Each filter supports plain value matching or operator-based filtering.

#### Default Filters

Pre-configured filters applied on startup via `query.default_filters`:

```json
{
  "query": {
    "default_filters": {
      "status": {"op": "in", "value": ["Completed", "Others"]},
      "sequencing_date": {"op": "last_n_days", "value": 7},
      "clinical_or_research": "Clinical"
    }
  }
}
```

#### Filter Operators

| Operator | Value | Description |
|----------|-------|-------------|
| `in` | `["a","b"]` | Match any value in list |
| `not_in` | `["a","b"]` | Exclude values in list |
| `contains` | `"text"` | Case-insensitive substring match |
| `not_contains` | `"text"` | Exclude matching substrings |
| `between` | `[min, max]` | Inclusive range |
| `gt`, `gte`, `lt`, `lte` | number | Numeric comparison |
| `last_n_days` | integer | Date within last N days from today |
| `not_empty` | *(none)* | Non-null, non-blank |
| `regex` | `"pattern"` | PostgreSQL case-insensitive regex |

#### Fixed Filters

Set `"fix_filter": true` at the top level to lock filters to only those defined in `default_filters`. Users will not be able to add or remove filters.

### Status Workflow

When `enable_approval_workflow` is `true`:

- **Status badges** appear on each row (colour-coded)
- **Approve/Reject buttons** update selected rows
- **Undo** reverts the last modification
- **Status filter** in the sidebar shows distribution

Custom status display labels via `status_labels`:

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

### Row Selection

- Click a row's checkbox to select it
- **Shift+Click** to range-select multiple rows
- **Select All** toggles all rows on the current page
- **Clear Selection** deselects all

### Pagination

- Page size controlled by `table.rows_per_page_options`
- `"all"` option loads every row (use with caution on large datasets)
- Hard cap at `database.max_rows_per_page` (default 100)

### Export

Click **Export** to download the current filtered/sorted view as CSV.

### Synthesis (SQL Transform)

When `enable_synthesis` is `true`, a Synthesis button appears in the toolbar. Clicking it runs the SQL query defined in `synthesis.query`, materialises the result into a PostgreSQL table, and displays it.

Results are cached for `synthesis.ttl_minutes`. Subsequent clicks within the TTL serve the cached table instantly.

```json
{
  "enable_synthesis": true,
  "synthesis": {
    "query": "SELECT * FROM my_view WHERE score > 0.5",
    "result_table_prefix": "_synthesis_result",
    "ttl_minutes": 10,
    "label": "Run Analysis"
  }
}
```

### Permissions

Role-based access control via the `permissions` section:

```json
{
  "permissions": {
    "default_role": "viewer",
    "user_roles": {
      "alice": "editor",
      "bob": "viewer"
    }
  }
}
```

| Role | Can Edit | Can Save | Can Approve | Can Export | Can View |
|------|----------|----------|-------------|-----------|----------|
| `editor` | Yes | Yes | Yes | Yes | Yes |
| `viewer` | No | No | No | Yes | Yes |

---

## Database Modes

### Direct Mode (SQLAlchemy)

```json
{
  "database": {
    "mode": "direct",
    "connection_string": "postgresql://user:pass@host/db"
  }
}
```

Uses SQLAlchemy connection pools. Configure `pool_size`, `max_overflow`, and `pool_timeout` for tuning.

### Datum Proxy Mode

```json
{
  "database": {
    "mode": "datum",
    "datum_base_url": "https://datum-proxy.example.com",
    "datum_token": "your-token",
    "datum_database": "mydb",
    "datum_schema": "public",
    "datum_service_name": "postgres_sql"
  }
}
```

Used for environments without direct database access (e.g., RStudio Connect behind a proxy).

### Lazy Loading

For large tables, enable DB-level pagination:

```json
{
  "database": {
    "lazy_loading": true,
    "page_buffer_size": 300
  }
}
```

Only the current page is fetched from the database. Filters and sorting happen at the SQL level.

---

## Multi-Tab / Widget Usage

dmapTableEditor is designed as a reusable Shiny module. Each instance operates independently in its own tab with isolated state.

```python
from shiny import App, ui
from dmapTableEditor import table_editor_ui, table_editor_server

app_ui = ui.page_navbar(
    ui.nav_panel("Tab 1", table_editor_ui("editor1")),
    ui.nav_panel("Tab 2", table_editor_ui("editor2")),
)

def server(input, output, session):
    table_editor_server("editor1", config=config1)
    table_editor_server("editor2", config=config2)

app = App(app_ui, server)
```

All JavaScript (drag-and-drop, row selection, cell editing, histograms, synthesis modal) is context-scoped to the active tab to prevent cross-tab interference.

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Port in use | App auto-increments to next available port |
| Module not found | `pip install -e ".[dev]"` |
| No columns shown | Set `table.default_columns` or leave empty for all |
| Changes not persisting | Check `persistence.auto_save` or click Save |
| Filter not matching | Column names are case-sensitive — must match database |
| `last_n_days` error | Use integer value (e.g. `7`), not string |
| Lazy loading slow | Increase `database.page_buffer_size` |
| Status labels don't show | Ensure `status_labels` keys are `unprocessed/edited/approved/rejected` |
| Multi-tab renders wrong tab | Ensure widget IDs are unique per tab |

## Performance

| Scenario | Recommendation |
|----------|---------------|
| < 10,000 rows | Default mode (load all into memory) |
| 10,000–100,000 rows | Enable `lazy_loading` with `page_buffer_size: 500` |
| > 100,000 rows | Enable `lazy_loading`, set `max_rows`, use column presets |
| Many concurrent users | Increase `pool_size` and `max_overflow` |

---

## Further Reading

- **REFERENCE.md** — Complete config key reference with all defaults
- **ARCHITECTURE.md** — System architecture and data flow diagrams
- **TESTING_REALITY.md** — Test posture, security guardrails, adversarial audit
- **template/app_config.template.json** — Fully annotated config template

---

**Last Updated:** February 2026
