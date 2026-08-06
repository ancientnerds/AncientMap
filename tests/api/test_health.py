# SPDX-License-Identifier: AGPL-3.0-only
"""Tests for health check endpoints."""

import pytest

# Needs the local Postgres/Redis containers (TestClient startup connects) —
# skipped by the DB-less CI test job (audit P3-13, 2026-08-06).
pytestmark = pytest.mark.integration


class TestRootEndpoint:
    """Test root endpoint (health check)."""

    def test_root_endpoint_exists(self, test_client):
        """Root endpoint should return 200."""
        response = test_client.get("/")
        assert response.status_code == 200

    def test_root_returns_status(self, test_client):
        """Root endpoint should return status field."""
        response = test_client.get("/")
        data = response.json()
        assert "status" in data
        assert data["status"] == "ok"

    def test_root_returns_service_name(self, test_client):
        """Root endpoint should return service name."""
        response = test_client.get("/")
        data = response.json()
        assert "service" in data
        assert "Ancient Nerds" in data["service"]
