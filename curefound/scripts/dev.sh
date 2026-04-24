#!/usr/bin/env bash
# ============================================================================
# scripts/dev.sh — local development helper
#
# Usage:
#   ./scripts/dev.sh           # start FastAPI with hot-reload
#   ./scripts/dev.sh neo4j     # also bring up Neo4j in Docker first
#   ./scripts/dev.sh smoke     # run end-to-end smoke test
#   ./scripts/dev.sh seed      # rebuild the seed KG from ETL scripts
#   ./scripts/dev.sh train     # train / retrain TransE
#   ./scripts/dev.sh eval      # run the leave-one-out evaluation
# ============================================================================
set -euo pipefail

CMD="${1:-serve}"

if [[ "$CMD" == "neo4j" ]]; then
    echo "▶ Starting Neo4j service via Docker Compose..."
    docker compose up -d neo4j
    echo "   Waiting for Neo4j healthcheck to pass..."
    until docker compose exec neo4j wget -q --spider http://localhost:7474 2>/dev/null; do
        printf "."
        sleep 2
    done
    echo ""
    echo "✓ Neo4j is up. Browser: http://localhost:7474"
    CMD="serve"  # fall through to start the backend too
fi

case "$CMD" in
  serve)
    echo "▶ Starting CureFound backend (hot-reload)..."
    python run.py serve
    ;;
  smoke)
    python run.py smoke
    ;;
  seed)
    python run.py seed
    ;;
  train)
    python run.py train
    ;;
  eval)
    python run.py eval
    ;;
  *)
    echo "Unknown command: $CMD"
    echo "Usage: $0 [serve|neo4j|smoke|seed|train|eval]"
    exit 1
    ;;
esac
