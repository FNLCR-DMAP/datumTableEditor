#!/bin/bash
# Run tests for dmapTableEditor
# Usage: ./run_tests.sh [pytest options]

set -e

# Activate conda environment if available
if command -v conda &> /dev/null; then
    eval "$(conda shell.bash hook)"
    conda activate demo_igv 2>/dev/null || true
fi

# Ensure we're in the project root
cd "$(dirname "$0")"

echo "=========================================="
echo "Running dmapTableEditor Tests"
echo "=========================================="

# Install test dependencies if needed
pip install pytest pytest-cov pytest-mock --quiet 2>/dev/null || true

# Run tests with coverage
if [ "$1" == "--coverage" ]; then
    echo "Running with coverage..."
    shift
    /Users/her2/miniconda3/envs/demo_igv/bin/python -m pytest tests/ \
        --cov=src \
        --cov-report=term-missing \
        --cov-report=html:htmlcov \
        "$@"
    echo ""
    echo "Coverage report generated: htmlcov/index.html"
else
    /Users/her2/miniconda3/envs/demo_igv/bin/python -m pytest tests/ "$@"
fi

echo ""
echo "=========================================="
echo "Tests Complete"
echo "=========================================="
