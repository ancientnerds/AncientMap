# SPDX-License-Identifier: MIT
"""Tests for sites API endpoints."""

import pytest

# Mark tests that require database connection
requires_db = pytest.mark.skipif(
    True,  # Skip by default in CI without DB
    reason="Requires PostgreSQL database connection"
)


class TestSitesEndpoint:
    """Test /api/sites endpoints."""

    def test_get_all_sites_endpoint_exists(self, test_client):
        """Sites endpoint should be accessible."""
        response = test_client.get("/api/sites/all")
        # Should return 200 even if empty (falls back to static JSON)
        assert response.status_code == 200

    def test_get_all_sites_returns_list(self, test_client):
        """Sites endpoint should return sites array."""
        response = test_client.get("/api/sites/all")
        data = response.json()
        assert "sites" in data
        assert isinstance(data["sites"], list)
        assert "count" in data

    def test_get_all_sites_with_source_filter(self, test_client):
        """Sites endpoint should accept source filter."""
        response = test_client.get("/api/sites/all?source=pleiades")
        assert response.status_code == 200
        data = response.json()
        assert "sites" in data

    def test_get_all_sites_with_pagination(self, test_client):
        """Sites endpoint should support pagination."""
        response = test_client.get("/api/sites/all?skip=0&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data["sites"]) <= 10


@pytest.mark.integration
class TestSitesIntegration:
    """Integration tests requiring database."""

    @requires_db
    def test_get_site_detail_not_found(self, test_client):
        """Non-existent site should return 404."""
        response = test_client.get("/api/sites/nonexistent-site-id-12345")
        assert response.status_code == 404


class TestViewportEndpoint:
    """Test /api/sites/viewport endpoint."""

    def test_viewport_requires_params(self, test_client):
        """Viewport endpoint requires bounding box params."""
        response = test_client.get("/api/sites/viewport")
        assert response.status_code == 422  # Validation error

    @requires_db
    def test_viewport_with_valid_bbox(self, test_client):
        """Viewport endpoint should accept valid bounding box."""
        response = test_client.get(
            "/api/sites/viewport",
            params={
                "min_lat": 40.0,
                "max_lat": 45.0,
                "min_lon": 10.0,
                "max_lon": 15.0,
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "sites" in data


@pytest.mark.integration
class TestClusteredEndpoint:
    """Test /api/sites/clustered endpoint (requires DB)."""

    @requires_db
    def test_clustered_endpoint_exists(self, test_client):
        """Clustered endpoint should be accessible."""
        response = test_client.get("/api/sites/clustered")
        assert response.status_code == 200

    @requires_db
    def test_clustered_with_resolution(self, test_client):
        """Clustered endpoint should accept resolution param."""
        response = test_client.get("/api/sites/clustered?resolution=3")
        assert response.status_code == 200
        data = response.json()
        assert "clusters" in data
        assert "resolution" in data
