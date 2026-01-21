# Modification Status Retrieval API

## Overview
The app now provides the ability to retrieve modification status for rows, both through the UI and programmatically through Python functions.

## UI Feature: Status Report Export

### Export Status Report Button
A new button **"📊 Export Status Report"** has been added to the action buttons section.

**Functionality:**
- Exports a CSV file containing the modification status for each row
- File name: `modification_status_report.csv`
- Saved in the `data/` directory
- Shows a summary notification with total counts by status

**Output Columns:**
- `row_index` - Row number (1-based)
- `status` - Current status (unprocessed, edited, approved, rejected)
- `modifications_count` - Number of field modifications for that row
- `patient_id` - Patient ID from the data
- `variant_key` - Variant key from the data

**Example Output:**
```
row_index,status,modifications_count,patient_id,variant_key
1,edited,2,Patient001,chr1:12345
2,unprocessed,0,Patient002,chr1:54321
3,approved,1,Patient003,chr2:67890
```

## Python API: Programmatic Status Retrieval

### Function 1: `get_modification_status(row_index)`

Get the modification status for a specific row.

**Parameters:**
- `row_index` (int): Row index (0-based, so row 0 is the first data row)

**Returns:** Dictionary with the following keys:
```python
{
    "row_index": 0,
    "status": "edited",  # "unprocessed", "edited", "approved", or "rejected"
    "modifications_count": 2,  # Number of field modifications
    "last_modified": "2026-01-21T14:30:45.123456",  # ISO timestamp
    "modifications": [  # List of modification objects
        {
            "timestamp": "2026-01-21T14:30:45.123456",
            "type": "field_modification",
            "details": {
                "row_index": 0,
                "column": "Gene_names",
                "old_value": "TP53",
                "new_value": "BRCA1"
            }
        }
    ]
}
```

**Example Usage:**
```python
from app import get_modification_status

# Get status for first row (row_index=0)
status = get_modification_status(0)
print(f"Row 0 status: {status['status']}")
print(f"Modifications: {status['modifications_count']}")

# Check if row has been edited
if status['modifications_count'] > 0:
    print("Row has pending modifications")
```

### Function 2: `get_all_modification_statuses()`

Get the modification status for all rows at once.

**Parameters:** None

**Returns:** Dictionary with the following structure:
```python
{
    "rows": [
        {
            "row_index": 0,
            "status": "edited",
            "modifications_count": 2,
            "last_modified": "2026-01-21T14:30:45.123456"
        },
        {
            "row_index": 1,
            "status": "unprocessed",
            "modifications_count": 0,
            "last_modified": None
        },
        # ... more rows
    ],
    "summary": {
        "total": 50,
        "unprocessed": 30,
        "edited": 10,
        "approved": 8,
        "rejected": 2
    }
}
```

**Example Usage:**
```python
from app import get_all_modification_statuses

# Get all statuses
all_statuses = get_all_modification_statuses()

# Print summary
summary = all_statuses['summary']
print(f"Total rows: {summary['total']}")
print(f"Edited: {summary['edited']}")
print(f"Approved: {summary['approved']}")
print(f"Rejected: {summary['rejected']}")

# Find all edited rows
edited_rows = [r for r in all_statuses['rows'] if r['status'] == 'edited']
print(f"Rows needing review: {len(edited_rows)}")
```

## Row Status Values

The status field can have one of these values:

| Status | Meaning |
|--------|---------|
| `unprocessed` | Row has no modifications and has not been approved/rejected |
| `edited` | Row has field modifications but has not been approved/rejected |
| `approved` | Row has been approved (marks entire dataset as approved) |
| `rejected` | Row has been rejected (marks entire dataset as rejected) |

## Integration Examples

### Example 1: Quality Control Script
```python
from app import get_all_modification_statuses

# Check if all critical rows have been approved
statuses = get_all_modification_statuses()
summary = statuses['summary']

if summary['approved'] > 0:
    print("✅ Data has been approved")
else:
    print("❌ Data not yet approved")
    print(f"  Edited rows pending review: {summary['edited']}")
```

### Example 2: Batch Status Update Report
```python
from app import get_all_modification_statuses
import json

statuses = get_all_modification_statuses()

# Create a simple report
report = {
    "timestamp": datetime.now().isoformat(),
    "total_rows": statuses['summary']['total'],
    "status_breakdown": statuses['summary'],
    "high_priority_rows": [
        r['row_index'] for r in statuses['rows'] 
        if r['modifications_count'] > 5
    ]
}

with open("status_report.json", "w") as f:
    json.dump(report, f, indent=2)
```

### Example 3: Monitor for Changes
```python
from app import get_modification_status

def row_has_pending_changes(row_idx):
    status = get_modification_status(row_idx)
    return status['modifications_count'] > 0

# Check if specific rows need attention
critical_rows = [0, 5, 10, 15]
for row_idx in critical_rows:
    if row_has_pending_changes(row_idx):
        print(f"Row {row_idx} has pending changes")
```

## Technical Details

### How Status is Determined

1. **Overall Approval Status**: The app tracks whether the entire dataset has been approved or rejected
2. **Row Modifications**: Each row can have one or more field modifications tracked
3. **Status Logic**:
   - If overall status is "approved" → all rows are "approved"
   - If overall status is "rejected" → all rows are "rejected"
   - If row has modifications and no overall approval → row is "edited"
   - If row has no modifications and no overall approval → row is "unprocessed"

### Data Storage

- Modification status is persisted in: `data/modifications_log.json`
- Status report CSV is saved to: `data/modification_status_report.csv`
- The log contains detailed timestamps and change information for auditing

## Error Handling

Both public functions handle missing data gracefully:

```python
# If no log exists yet, returns default unprocessed status
status = get_modification_status(0)
# Returns: {"status": "unprocessed", "modifications_count": 0, ...}

# If no log exists, returns empty summary
statuses = get_all_modification_statuses()
# Returns: {"rows": [], "summary": {"total": 0, ...}}
```

## Browser vs. Script Usage

**In the Browser UI:**
- Click "📊 Export Status Report" button
- Downloads CSV file with all statuses
- Useful for reports and external processing

**In Python Scripts:**
- Import the functions directly
- Process status data programmatically
- Integrate with other workflows
- No UI interaction needed

## Use Cases

1. **Quality Control**: Export status reports for compliance and auditing
2. **Batch Processing**: Check which rows need modifications before processing
3. **Workflow Integration**: Query status from external scripts
4. **Reporting**: Generate automated reports of modification progress
5. **Data Validation**: Verify all rows are in the correct state before export
