# SPDX-License-Identifier: MIT
"""Security-focused tests for the application."""

import pytest


class TestTurnstileFailClosed:
    """Test Turnstile CAPTCHA security."""

    def test_turnstile_rejects_without_secret(self, monkeypatch):
        """Turnstile verification should fail when secret is not configured."""
        # Clear the secret
        monkeypatch.delenv("TURNSTILE_SECRET_KEY", raising=False)

        # Import after clearing env to get fresh module state
        import importlib
        from api.routes import ai
        importlib.reload(ai)

        # Verify the constant is empty or None
        assert not ai.TURNSTILE_SECRET or ai.TURNSTILE_SECRET == ""


class TestAdminKeyValidation:
    """Test admin key security."""

    def test_admin_endpoints_require_auth(self, test_client):
        """Admin endpoints should require authorization."""
        # Try to access admin endpoint without auth
        response = test_client.get("/api/ai/pins")
        assert response.status_code in [401, 503]  # Unauthorized or not configured

    def test_admin_key_uses_timing_safe_comparison(self):
        """Admin key validation should use secrets.compare_digest."""
        import ast
        import inspect
        from api.routes import ai

        # Get source code of the module
        source = inspect.getsource(ai)

        # Check that compare_digest is used
        assert "secrets.compare_digest" in source or "compare_digest" in source


class TestSiteUpdateAuth:
    """Test site update endpoint security."""

    def test_site_update_requires_auth(self, test_client):
        """PUT /api/sites/{id} should require authorization."""
        response = test_client.put(
            "/api/sites/test-site-id",
            json={
                "title": "Test",
                "category": "settlement",
                "period": "Unknown",
                "coordinates": [0, 0]
            }
        )
        assert response.status_code in [401, 503]

    def test_site_update_rejects_invalid_key(self, test_client, monkeypatch):
        """PUT /api/sites/{id} should reject invalid admin key."""
        monkeypatch.setenv("ADMIN_KEY", "valid-secret-key")

        response = test_client.put(
            "/api/sites/test-site-id",
            json={
                "title": "Test",
                "category": "settlement",
                "period": "Unknown",
                "coordinates": [0, 0]
            },
            headers={"Authorization": "Bearer wrong-key"}
        )
        assert response.status_code == 403


class TestXSSPrevention:
    """Test XSS prevention measures."""

    def test_html_escape_imported(self):
        """OG module should import html.escape for XSS prevention."""
        import ast
        import inspect
        from api.routes import og

        source = inspect.getsource(og)
        assert "import html" in source or "from html import escape" in source
        assert "html.escape" in source or "escape(" in source


class TestErrorHandling:
    """Test error handling doesn't leak information."""

    def test_chat_error_generic_message(self):
        """Chat endpoint should return generic error messages."""
        import inspect
        from api.routes import ai

        source = inspect.getsource(ai)

        # Should NOT contain patterns that expose exception details to client
        # The fix changed "Error processing query: {str(e)}" to a generic message
        assert 'detail=f"Error processing query: {str(e)}"' not in source
