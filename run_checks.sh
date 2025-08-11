#!/bin/bash

# This script runs a linter and tests for the project.
# It's configured to exit immediately if any command fails.
set -e

# --- Configuration ---
SRC_DIR="src"
TEST_DIR="tests" # Assuming your tests are in a 'tests' directory

# --- 1. Run Linter ---
echo "---  Linting Code ---"
pylint $SRC_DIR
echo "✅ Linter passed."
echo "" # Add a newline for readability

# --- 2. Run Tests ---
echo "--- Running Tests ---"
pytest -q $TEST_DIR
echo "✅ Tests passed."
echo ""

# --- Success ---
echo "🎉 All checks passed successfully!"


# --- 3. Freeze PIP ---
echo "---  Freezing PIP ---"
pip freeze > requirements.txt

# --- 4. Freeze PIP Dev ---
echo "---  Freezing PIP Dev ---"
pip freeze > requirements-dev.txt


echo "---  Job's Done. ---"