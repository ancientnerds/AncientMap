# SPDX-License-Identifier: AGPL-3.0-only
"""Tests for Open Graph image generation endpoints."""

import pytest

# Needs the local Postgres/Redis containers (TestClient startup connects) —
# skipped by the DB-less CI test job (audit P3-13, 2026-08-06).
pytestmark = pytest.mark.integration


# Mark tests that require database connection
requires_db = pytest.mark.skipif(
    True,  # Skip by default in CI without DB
    reason="Requires PostgreSQL database connection",
)


class TestOGHomepage:
    """Test /api/og/homepage endpoint."""

    def test_homepage_og_returns_image(self, test_client):
        """Homepage OG endpoint should return JPEG image."""
        response = test_client.get("/api/og/homepage")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"


@pytest.mark.integration
class TestOGSiteImage:
    """Test /api/og/{site_id} endpoint (requires DB)."""

    @requires_db
    def test_site_og_image_returns_jpeg(self, test_client):
        """Site OG image should return JPEG."""
        response = test_client.get("/api/og/test-site-id")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"
