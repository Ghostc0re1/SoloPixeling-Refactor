#!/bin/bash

# --- Configuration ---
# Set the source directory where your main Python code resides.
SRC_DIR="src"

echo "Running pylint on directory: '$SRC_DIR'..."

# --- Run Pylint ---
# The command finds all .py files in the source directory and lints them.
# It uses the .pylintrc file in the same directory for configuration.
# The script will exit with a non-zero status code if pylint finds errors.
pylint $SRC_DIR

# --- Report Status ---
# Check the exit code of the last command (pylint).
if [ $? -eq 0 ]; then
    echo "✅ Linting complete. No issues found."
else
    echo "❌ Linting failed. Please fix the issues above."
    # Exit with a failure code to stop CI/CD pipelines if necessary.
    exit 1
fi