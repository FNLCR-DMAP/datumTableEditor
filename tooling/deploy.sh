#!/bin/bash
# ============================================================
#  deploy.sh — Orchestrator for all tooling tasks
# ============================================================
#
#  Usage:
#      ./tooling/deploy.sh              # run everything
#      ./tooling/deploy.sh qc           # QC only (functions + viz)
#      ./tooling/deploy.sh sql          # SQL extraction only
#      ./tooling/deploy.sh --help       # show usage
#
#  Output goes to qcmetric/ in the project root.
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SRC_DIR="$SCRIPT_DIR/src"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

FAILED=0

# -------- helpers ---------------------------------------------------
banner()  { echo -e "\n${BLUE}═══════════════════════════════════════════════${NC}"; echo -e "${BLUE}  $1${NC}"; echo -e "${BLUE}═══════════════════════════════════════════════${NC}"; }
step()    { echo -e "\n${YELLOW}[$1] $2${NC}"; }
ok()      { echo -e "${GREEN}  ✓ $1${NC}"; }
warn()    { echo -e "${YELLOW}  ⚠  $1${NC}"; }
fail()    { echo -e "${RED}  ✗ $1${NC}"; FAILED=1; }

usage() {
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  qc       Run function QC checks + visualizations"
    echo "  sql      Extract golden SQL strings to qcmetric/sql_golden.json"
    echo "  (none)   Run everything"
    echo ""
    echo "Output is written to <project_root>/qcmetric/"
    exit 0
}

# -------- ensure we are in the project root ---------------------
cd "$PROJECT_ROOT"
mkdir -p qcmetric

# ================================================================
#  TASK 1: QC — function mapping, type coverage, frontend, viz
# ================================================================
run_qc() {
    banner "QC — Functions & Visualisation"

    # 1a. Python syntax check
    step "1a/6" "Python syntax check"
    SYNTAX_ERRORS=0
    FILE_COUNT=0
    for pyfile in $(find src/ -name "*.py" -not -path "*/__pycache__/*" | sort); do
        if ! python -m py_compile "$pyfile" 2>/dev/null; then
            fail "Syntax error: $pyfile"
            SYNTAX_ERRORS=$((SYNTAX_ERRORS + 1))
        fi
        FILE_COUNT=$((FILE_COUNT + 1))
    done
    [ "$SYNTAX_ERRORS" -eq 0 ] && ok "All $FILE_COUNT Python files valid" || fail "$SYNTAX_ERRORS syntax errors"

    # 1b. Function mapping & unused code
    step "1b/6" "Function mapping (generate_qc)"
    if python "$SRC_DIR/qc/generate_qc.py" 2>&1 | tail -3; then
        # Summarise unused count
        TOTAL_UNUSED=$(python -c "
import json, pathlib, sys
total = 0
for f in pathlib.Path('qcmetric').glob('*_qc.json'):
    data = json.load(open(f))
    s = data.get('_summary', {})
    total += s.get('unused_functions', 0)
print(total)
")
        [ "$TOTAL_UNUSED" -gt 0 ] && warn "$TOTAL_UNUSED unused functions" || ok "No unused functions"
    else
        fail "generate_qc.py failed"
    fi

    # 1c. Server function mapping
    step "1c/6" "Server function mapping"
    if python "$SRC_DIR/qc/generate_mapping.py" 2>&1 | tail -1; then
        ok "qcmetric/server_function_qc.json written"
    else
        fail "generate_mapping.py failed"
    fi

    # 1d. Type annotation coverage
    step "1d/6" "Type annotation coverage"
    if python "$SRC_DIR/qc/generate_type_qc.py" 2>&1 | tail -1; then
        ok "Type QC complete"
    else
        fail "generate_type_qc.py failed"
    fi

    # 1e. Frontend (JS/CSS) checks
    step "1e/6" "Frontend (JS/CSS) validation"
    if python "$SRC_DIR/qc/check_frontend.py" 2>&1 | tail -3; then
        FE_ERRORS=$(python -c "import json; d=json.load(open('qcmetric/frontend_qc.json')); print(d['_summary']['js_errors']+d['_summary']['css_errors'])" 2>/dev/null || echo 0)
        [ "$FE_ERRORS" -gt 0 ] && fail "$FE_ERRORS frontend errors" || ok "No frontend errors"
    else
        fail "check_frontend.py failed"
    fi

    # 1f. Function test coverage report
    step "1f/6" "Function test coverage"
    python "$SRC_DIR/qc/check_test_coverage.py" 2>&1 | tail -4

    # 1g. Visualisations (app graph, architecture, function tree)
    step "VIZ" "Generating visualisations"
    python "$SRC_DIR/viz/visualize_app.py" 2>&1 | tail -1 && ok "app_graph.html" || warn "visualize_app skipped (pyvis may not be installed)"
    python "$SRC_DIR/viz/visualize_architecture.py" 2>&1 | tail -1 && ok "app_architecture.html" || warn "visualize_architecture failed"
    python "$SRC_DIR/viz/visualize_tree.py" 2>&1 | tail -1 && ok "function_tree.html" || warn "visualize_tree failed"
    python "$SRC_DIR/qc/qc_check.py" 2>&1 | tail -1 && ok "app_mapping.json" || warn "qc_check failed"
}


# ================================================================
#  TASK 2: SQL — golden string extraction
# ================================================================
run_sql() {
    banner "SQL — Golden String Extraction"

    step "SQL" "Extracting QueryBuilder + DataFetcher SQL strings"
    if python "$SRC_DIR/sql/extract_golden_sql.py" 2>&1; then
        ok "qcmetric/sql_golden.json written"
    else
        fail "extract_golden_sql.py failed"
    fi
}


# ================================================================
#  Dispatch
# ================================================================
case "${1:-all}" in
    qc)       run_qc ;;
    sql)      run_sql ;;
    all)      run_qc; run_sql ;;
    -h|--help) usage ;;
    *)
        echo -e "${RED}Unknown command: $1${NC}"
        usage
        ;;
esac

# -------- summary ---------------------------------------------------
banner "Summary"
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}  All tasks completed successfully${NC}"
else
    echo -e "${RED}  Some tasks failed (see above)${NC}"
fi

echo -e "\n${CYAN}  Output directory: qcmetric/${NC}"
echo -e "${CYAN}  Files:${NC}"
ls -1 qcmetric/ 2>/dev/null | sed 's/^/    /'
echo ""

exit $FAILED
