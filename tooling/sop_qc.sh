#!/usr/bin/env bash
# ==============================================================================
# SOP: Quality Control & Coverage Pipeline
# ==============================================================================
# Runs the full QC sequence:
#   1. Function extraction (QC metrics per module)
#   2. Function coverage check (public functions vs test references)
#   3. Golden SQL extraction (snapshot of all generated SQL)
#   4. SQL golden test (pin SQL strings against snapshot)
#   5. Full pytest suite with line coverage
#
# Usage:
#   bash tooling/sop_qc.sh          # run all steps
#   bash tooling/sop_qc.sh --step N # run only step N (1-5)
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Read config
QC_CONFIG="$SCRIPT_DIR/qc_config.json"
if [[ ! -f "$QC_CONFIG" ]]; then
    echo "ERROR: $QC_CONFIG not found"
    exit 1
fi

# Extract configurable values
GOLDEN_SQL_SCRIPT=$(python3 -c "import json; c=json.load(open('$QC_CONFIG')); print(c['golden_sql']['script'])")
GOLDEN_SQL_TEST=$(python3 -c "import json; c=json.load(open('$QC_CONFIG')); print(c['golden_sql']['test_file'])")
COVERAGE_CMD=$(python3 -c "import json; c=json.load(open('$QC_CONFIG')); print(c['coverage']['test_command'])")

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

STEP_FILTER="${2:-}"
FAILED=0

run_step() {
    local step_num="$1"
    local step_name="$2"
    shift 2

    if [[ -n "$STEP_FILTER" && "$STEP_FILTER" != "$step_num" ]]; then
        return 0
    fi

    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}  STEP $step_num: $step_name${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    if "$@"; then
        echo -e "${GREEN}  ✓ STEP $step_num PASSED${NC}"
    else
        echo -e "${RED}  ✗ STEP $step_num FAILED${NC}"
        FAILED=1
    fi
}

# Step 1: Function Extraction (QC metrics)
run_step 1 "Function Extraction (QC Metrics)" \
    python tooling/src/qc/generate_qc.py

# Step 2: Function Coverage Check
run_step 2 "Function Coverage (public funcs vs tests)" \
    python tooling/src/qc/check_test_coverage.py

# Step 3: Golden SQL Extraction
run_step 3 "Golden SQL Extraction" \
    python "$GOLDEN_SQL_SCRIPT"

# Step 4: SQL Golden Snapshot Test
run_step 4 "SQL Golden Snapshot Test" \
    python -m pytest "$GOLDEN_SQL_TEST" -x -q

# Step 5: Full Pytest with Coverage
run_step 5 "Pytest Suite + Line Coverage" \
    bash -c "$COVERAGE_CMD"

# Step 6: Frontend QC (JS/CSS validation)
run_step 6 "Frontend QC (JS + CSS checks)" \
    python tooling/src/qc/check_frontend.py

# Step 7: Type Annotation QC
run_step 7 "Type Annotation QC" \
    python tooling/src/qc/generate_type_qc.py

# Step 8: Function Mapping (unused function detection)
run_step 8 "Function Mapping (cross-reference)" \
    python tooling/src/qc/generate_mapping.py

# Summary
echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
if [[ $FAILED -eq 0 ]]; then
    echo -e "${GREEN}  ALL STEPS PASSED${NC}"
else
    echo -e "${RED}  ONE OR MORE STEPS FAILED${NC}"
    exit 1
fi
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
