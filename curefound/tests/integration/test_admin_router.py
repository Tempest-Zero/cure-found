"""Integration tests for the admin router.

Routes tested
-------------
  GET /health
  GET /api/v1/health   (dual-mount parity)

These tests run against whatever KG backend is active (controlled by the
``KG_BACKEND`` env var via the ``int_client`` fixture in conftest.py).
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


class TestHealthEndpoint:
    def test_health_returns_200(self, int_client) -> None:
        r = int_client.get("/health")
        assert r.status_code == 200

    def test_health_status_ok(self, int_client) -> None:
        body = int_client.get("/health").json()
        assert body["status"] == "ok"

    def test_health_schema_fields(self, int_client) -> None:
        body = int_client.get("/health").json()
        assert "status" in body, "health response must contain 'status'"
        assert "kg_version" in body, "health response must contain 'kg_version'"
        assert "kg_backend" in body, "health response must contain 'kg_backend'"

    def test_health_kg_version_nonempty(self, int_client) -> None:
        body = int_client.get("/health").json()
        assert body["kg_version"], "kg_version must be a non-empty string"

    def test_health_v1_prefix_identical(self, int_client) -> None:
        """/health and /api/v1/health must return byte-identical bodies."""
        bare = int_client.get("/health").json()
        prefixed = int_client.get("/api/v1/health").json()
        assert bare == prefixed, "/health and /api/v1/health diverged -- dual-mount is broken"
