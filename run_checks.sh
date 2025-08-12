#!/usr/bin/env bash
set -Eeuo pipefail

SRC_DIR="src"
TEST_DIR="tests"

need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "❌ Missing required tool: $1"
    echo "   Run: python -m pip install $1"
    exit 127
  fi
}

echo "--- Checking tooling ---"
need python
need pylint
need pytest

echo "--- Linting Code ---"
pylint "$SRC_DIR"
echo "✅ Linter passed."
echo

echo "--- Running Tests ---"
pytest -q "$TEST_DIR"
echo "✅ Tests passed."
echo

# Optional: only freeze if explicitly requested
if [[ "${1-}" == "--freeze" ]]; then
  echo "--- Freezing dependencies ---"
  # Prod requirements (your app deps)
  python -m pip freeze > requirements.txt
  # Dev requirements (include lint/test tools)
  python -m pip freeze > requirements-dev.txt
  echo "✅ Requirements frozen."
fi

echo "🎉 All checks passed successfully!"
