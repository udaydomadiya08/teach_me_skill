#!/usr/bin/env bash
set -euo pipefail

if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

echo "==> Running ruff static analysis..."
ruff check .

echo "==> Verifying code formatting..."
ruff format --check .
