"""Shared pytest fixtures for CureFound.

Scope strategy
--------------
session  -- Settings + kg_small (cheap, immutable across the whole run)
module   -- test_app, sync_client, async_client (one server per test module;
            avoids cross-module dependency-override bleed)
function -- default for anything with mutable state / dependency overrides

Regression tests (tests/regression/test_backend.py) define their own local
`client` and `kg` fixtures (module scope) that take precedence inside that
file -- no conflict with the fixtures here.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings, reset_settings_cache
from app.main import create_app

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """A local-env Settings instance shared by the whole test session.

    Passing explicit values here means the tests do **not** depend on a
    `.env` file being present in the working directory.
    """
    reset_settings_cache()
    return Settings(
        ENVIRONMENT="local",
        PROJECT_NAME="CureFound-test",
        KG_BACKEND="networkx",
        LOG_LEVEL="WARNING",  # keep test output quiet
    )


# ---------------------------------------------------------------------------
# App + HTTP clients
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def test_app(test_settings: Settings) -> FastAPI:
    """FastAPI app built from test_settings.

    Module-scoped so that integration tests which call
    ``app.dependency_overrides[dep] = fake`` don't bleed into other modules.
    """
    return create_app(settings=test_settings)


@pytest.fixture(scope="module")
def sync_client(test_app: FastAPI):
    """Synchronous TestClient for integration tests that prefer the sync API."""
    with TestClient(test_app) as c:
        yield c


@pytest.fixture(scope="module")
async def async_client(test_app: FastAPI) -> AsyncClient:
    """Async HTTPX client backed by ASGITransport.

    Preferred client for new integration tests -- avoids the "event loop
    already running" footgun that plagued the old TestClient in async contexts.
    """
    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# Lightweight KG fixture for unit tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def kg_small():
    """Real KG loaded once from data/seed/kg.json.

    Provides the full seed graph to unit tests that exercise pure-Python
    logic (service methods, path walkers, etc.) without the HTTP stack.
    Session-scoped: construction is I/O-bound (~0.2 s) and the object is
    read-only, so sharing across the session is safe.
    """
    from app.kg.loader import load_kg

    return load_kg()
