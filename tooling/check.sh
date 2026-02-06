#!/bin/bash
# ============================================
# QC Check Suite for Epitopes Data Editor
# ============================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}  QC Check Suite - Epitopes Data Editor${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

# Track overall status
FAILED=0

# --------------------------------------------
# 1. Python Syntax Check (py_compile)
# --------------------------------------------
echo -e "${YELLOW}[1/4] Running Python syntax check...${NC}"
cd "$PROJECT_ROOT"

SYNTAX_ERRORS=0
for pyfile in $(find . -name "*.py" -not -path "./__pycache__/*" -not -path "./tooling/*" -not -path "./.git/*"); do
    if ! python -m py_compile "$pyfile" 2>/dev/null; then
        echo -e "${RED}  ✗ Syntax error in: $pyfile${NC}"
        python -m py_compile "$pyfile" 2>&1 | head -5
        SYNTAX_ERRORS=$((SYNTAX_ERRORS + 1))
    fi
done

if [ "$SYNTAX_ERRORS" -eq 0 ]; then
    echo -e "${GREEN}✓ All Python files have valid syntax${NC}"
else
    echo -e "${RED}✗ Found $SYNTAX_ERRORS files with syntax errors${NC}"
    FAILED=1
fi

echo ""

# --------------------------------------------
# 2. Function Mapping & Unused Code Detection
# --------------------------------------------
echo -e "${YELLOW}[2/4] Running function mapping analysis...${NC}"

# Run the unified QC generator
if python tooling/generate_qc.py; then
    # Check server QC
    SERVER_UNUSED=$(python -c "import json; data=json.load(open('qcmetric/server_qc.json')); print(data['_summary']['unused_functions'])")
    UI_UNUSED=$(python -c "import json; data=json.load(open('qcmetric/ui_qc.json')); print(data['_summary']['unused_functions'])")
    APP_UNUSED=$(python -c "import json; data=json.load(open('qcmetric/app_qc.json')); print(data['_summary']['unused_functions'])")
    
    TOTAL_UNUSED=$((SERVER_UNUSED + UI_UNUSED + APP_UNUSED))
    
    if [ "$TOTAL_UNUSED" -gt 0 ]; then
        echo -e "${YELLOW}⚠️  Warning: Found $TOTAL_UNUSED unused functions${NC}"
        echo -e "   server: $SERVER_UNUSED, ui: $UI_UNUSED, app: $APP_UNUSED"
    else
        echo -e "${GREEN}✓ No unused functions detected${NC}"
    fi
else
    echo -e "${RED}✗ Function mapping failed${NC}"
    FAILED=1
fi

echo ""

# --------------------------------------------
# 3. Type Annotation Coverage Summary
# --------------------------------------------
echo -e "${YELLOW}[3/4] Type annotation summary...${NC}"

SERVER_COVERAGE=$(python -c "import json; data=json.load(open('qcmetric/server_qc.json')); print(data['_summary']['function_coverage_percent'])")
UI_COVERAGE=$(python -c "import json; data=json.load(open('qcmetric/ui_qc.json')); print(data['_summary']['function_coverage_percent'])")
APP_COVERAGE=$(python -c "import json; data=json.load(open('qcmetric/app_qc.json')); print(data['_summary']['function_coverage_percent'])")

SERVER_MYPY=$(python -c "import json; data=json.load(open('qcmetric/server_qc.json')); print(data['_summary']['mypy_errors'])")
UI_MYPY=$(python -c "import json; data=json.load(open('qcmetric/ui_qc.json')); print(data['_summary']['mypy_errors'])")
APP_MYPY=$(python -c "import json; data=json.load(open('qcmetric/app_qc.json')); print(data['_summary']['mypy_errors'])")

TOTAL_MYPY=$((SERVER_MYPY + UI_MYPY + APP_MYPY))

if [ "$TOTAL_MYPY" -gt 0 ]; then
    echo -e "${YELLOW}⚠️  Warning: Found $TOTAL_MYPY mypy type errors${NC}"
else
    echo -e "${GREEN}✓ No mypy type errors${NC}"
fi

echo -e "   Type coverage: server=${SERVER_COVERAGE}%, ui=${UI_COVERAGE}%, app=${APP_COVERAGE}%"

echo ""

# --------------------------------------------
# 4. Frontend (JS/CSS) Checks
# --------------------------------------------
echo -e "${YELLOW}[4/4] Running frontend (JS/CSS) checks...${NC}"

if python tooling/check_frontend.py > /dev/null 2>&1; then
    JS_ERRORS=$(python -c "import json; data=json.load(open('qcmetric/frontend_qc.json')); print(data['_summary']['js_errors'])")
    JS_WARNINGS=$(python -c "import json; data=json.load(open('qcmetric/frontend_qc.json')); print(data['_summary']['js_warnings'])")
    CSS_ERRORS=$(python -c "import json; data=json.load(open('qcmetric/frontend_qc.json')); print(data['_summary']['css_errors'])")
    CSS_WARNINGS=$(python -c "import json; data=json.load(open('qcmetric/frontend_qc.json')); print(data['_summary']['css_warnings'])")
    JS_FILES=$(python -c "import json; data=json.load(open('qcmetric/frontend_qc.json')); print(data['_summary']['js_file_count'])")
    CSS_FILES=$(python -c "import json; data=json.load(open('qcmetric/frontend_qc.json')); print(data['_summary']['css_file_count'])")
    JS_FUNCS=$(python -c "import json; data=json.load(open('qcmetric/frontend_qc.json')); print(data['_summary']['total_js_functions'])")
    
    TOTAL_FE_ERRORS=$((JS_ERRORS + CSS_ERRORS))
    
    if [ "$TOTAL_FE_ERRORS" -gt 0 ]; then
        echo -e "${RED}✗ Found $TOTAL_FE_ERRORS frontend errors${NC}"
        echo -e "   JS: $JS_ERRORS errors, $JS_WARNINGS warnings"
        echo -e "   CSS: $CSS_ERRORS errors, $CSS_WARNINGS warnings"
        FAILED=1
    else
        echo -e "${GREEN}✓ No frontend syntax errors${NC}"
        if [ "$JS_WARNINGS" -gt 0 ] || [ "$CSS_WARNINGS" -gt 0 ]; then
            echo -e "${YELLOW}⚠️  Warnings: JS=$JS_WARNINGS, CSS=$CSS_WARNINGS${NC}"
        fi
    fi
    echo -e "   Files: $JS_FILES JS, $CSS_FILES CSS | Functions: $JS_FUNCS JS"
else
    echo -e "${RED}✗ Frontend check failed${NC}"
    FAILED=1
fi

echo ""

# --------------------------------------------
# Summary
# --------------------------------------------
echo -e "${BLUE}============================================${NC}"
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}  All checks passed!${NC}"
else
    echo -e "${RED}  Some checks failed${NC}"
fi
echo -e "${BLUE}============================================${NC}"

exit $FAILED
