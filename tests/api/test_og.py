# SPDX-License-Identifier: MIT
"""Tests for Open Graph image generation endpoints."""

import pytest

# Mark tests that require database connection
requires_db = pytest.mark.skipif(
    True,  # Skip by default in CI without DB
    reason="Requires PostgreSQL database connection"
)


class TestOGHomepage:
    """Test /api/og/homepage endpoint."""

    def test_homepage_og_returns_image(self, test_client):
        """Homepage OG endpoint should return JPEG image."""
        response = test_client.get("/api/og/homepage")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"


@pytest.mark.integration
class TestOGSharePage:
    """Test /api/og/share/{site_id} endpoint (requires DB)."""

    @requires_db
    def test_share_page_returns_html(self, test_client):
        """Share page should return HTML with OG meta tags."""
        response = test_client.get("/api/og/share/test-site-id")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @requires_db
    def test_share_page_contains_og_tags(self, test_client):
        """Share page should contain Open Graph meta tags."""
        response = test_client.get("/api/og/share/test-site-id")
        content = response.text
        assert "og:title" in content
        assert "og:description" in content
        assert "og:image" in content

    @requires_db
    def test_share_page_handles_missing_site(self, test_client):
        """Share page should handle non-existent sites gracefully."""
        response = test_client.get("/api/og/share/nonexistent-12345")
        assert response.status_code == 200  # Still returns HTML
        content = response.text
        assert "Site Not Found" in content or "og:title" in content


@pytest.mark.integration
class TestOGSiteImage:
    """Test /api/og/{site_id} endpoint (requires DB)."""

    @requires_db
    def test_site_og_image_returns_jpeg(self, test_client):
        """Site OG image should return JPEG."""
        response = test_client.get("/api/og/test-site-id")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"


class TestXSSPrevention:
    """Test XSS prevention in OG generation (code inspection)."""

    def test_html_module_imported(self):
        """OG module should import html module for escaping."""
        import inspect
        from api.routes import og
        source = inspect.getsource(og)
        assert "import html" in source

    def test_html_escape_used(self):
        """OG module should use html.escape for user data."""
        import inspect
        from api.routes import og
        source = inspect.getsource(og)
        assert "html.escape" in source

    def test_escaped_variables_used_in_template(self):
        """OG module should use escaped variables in HTML template."""
        import inspect
        from api.routes import og
        source = inspect.getsource(og)
        # Check that escaped versions are used
        assert "title_escaped" in source
        assert "og_desc_escaped" in source
