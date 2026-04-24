#!/usr/bin/env bash
# ============================================================================
# scripts/lint.sh — run Ruff check + format over the codebase
#
# Usage:
#   ./scripts/lint.sh          # check + format (writes fixes in place)
#   ./scripts/lint.sh --check  # check only, exit non-zero if there are issues
# ============================================================================
set -euo pipefail

CHECK_ONLY="${1:-}"

if [[ "$CHECK_ONLY" == "--check" ]]; then
    echo "▶ ruff check (no fixes)..."
    ruff check app tests run.py
    echo "▶ ruff format --check..."
    ruff format --check app tests run.py
    echo "✓ All lint checks passed."
else
    echo "▶ ruff check --fix..."
    ruff check --fix app tests run.py
    echo "▶ ruff format..."
    ruff format app tests run.py
    echo "✓ Lint + format complete."
fi
