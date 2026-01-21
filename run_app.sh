#!/bin/bash
# Start the PyShiny app

cd "$(dirname "$0")"

echo "🚀 Starting Epitopes Data Editor..."
echo ""
echo "Installing dependencies if needed..."
pip install -q -r requirements.txt

echo ""
echo "Starting Shiny app..."
echo "The app will open in your browser at http://localhost:8000"
echo ""

python -m shiny run app.py
