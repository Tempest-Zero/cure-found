"""Integration-test-package fixtures.

These fixtures are scoped to `tests/integration/` and override the top-level
conftest for backend-aware testing.

Default run (networkx):
    pytest tests/integration

Step-6 backend-parity run (neo4j):
    KG_BACKEND=neo4j pytest tests/integration

The `int_client` fixture reads `KG_BACKEND` from the environment so the exact
same test assertions verify both backends -- the design goal stated in
Step 5.6 of the pre-Phase-1 plan.  Neo4j tests skip automatically when
NEO4J_URI is not reachable (i.e. Docker is not up or Step 3 ingest hasn't run).
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

_BACKEND: str = os.getenv("KG_BACKEND", "networkx")


@pytest.fixture(scope="module")
def int_client():
    """Module-scoped TestClient backed by the selected KG backend.

    Scope is module (not session) so that future tests using
    ``app.dependency_overrides`` don't bleed across test modules.
    """
    if _BACKEND == "neo4j":
        neo4j_uri = os.getenv("NEO4J_URI", "")
        if not neo4j_uri:
            pytest.skip(
                "KG_BACKEND=neo4j but NEO4J_URI is not set. "
                "Run `docker compose up -d neo4j` and set NEO4J_URI in your environment."
            )
    settings = Settings(
        ENVIRONMENT="local",
        PROJECT_NAME="CureFound-integration-test",
        KG_BACKEND=_BACKEND,
        LOG_LEVEL="WARNING",
        # Neo4j creds: honour env overrides; fall back to the Docker Compose dev defaults
        NEO4J_URI=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        NEO4J_USER=os.getenv("NEO4J_USER", "neo4j"),
        NEO4J_PASSWORD=os.getenv("NEO4J_PASSWORD", "changethis_dev_only"),
    )
    app = create_app(settings=settings)
    with TestClient(app) as c:
        yield c
