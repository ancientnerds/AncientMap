# SPDX-License-Identifier: MIT
"""Tests for health check endpoints."""

import pytest


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
