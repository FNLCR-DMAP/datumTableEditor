# Modification Status Retrieval - Quick Start

## What's New?

You can now easily retrieve the modification status of rows in two ways:

### 1. **Export Status Report (UI)**

Click the new **"📊 Export Status Report"** button in the app to:
- Generate a CSV file with status for every row
- See a summary: Total rows, Unprocessed, Edited, Approved, Rejected
- File saved to: `data/modification_status_report.csv`

### 2. **Retrieve Status Programmatically (Python)**

Call functions directly from Python scripts:

```python
from app import get_modification_status, get_all_modification_statuses

# Get status for one row
status = get_modification_status(0)  # First row
print(status['status'])  # 'approved', 'rejected', 'edited', or 'unprocessed'

# Get status for all rows
all_statuses = get_all_modification_statuses()
print(all_statuses['summary'])  # See counts of each status
```

## Status Values

- **unprocessed** - No changes, not approved
- **edited** - Has field modifications, not approved  
- **approved** - Approved
- **rejected** - Rejected

## Common Tasks

### Check if row was edited
```python
status = get_modification_status(row_idx)
if status['modifications_count'] > 0:
    print("Row has changes")
```

### Count edited rows
```python
all_statuses = get_all_modification_statuses()
edited_count = all_statuses['summary']['edited']
print(f"Rows awaiting review: {edited_count}")
```

### Find rows with many edits
```python
all_statuses = get_all_modification_statuses()
high_change_rows = [r for r in all_statuses['rows'] if r['modifications_count'] > 5]
```

### Export to different format
```python
all_statuses = get_all_modification_statuses()
import json

# Save as JSON instead of CSV
with open('status.json', 'w') as f:
    json.dump(all_statuses, f, indent=2)
```

## Full API Reference

See [MODIFICATION_STATUS_API.md](MODIFICATION_STATUS_API.md) for complete documentation with examples.
