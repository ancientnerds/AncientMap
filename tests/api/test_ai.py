# SPDX-License-Identifier: MIT
"""Tests for AI/chat API endpoints."""

import pytest


class TestAIModes:
    """Test /api/ai/modes endpoint."""

    def test_get_modes_endpoint(self, test_client):
        """Modes endpoint should return available AI modes."""
        response = test_client.get("/api/ai/modes")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, (list, dict))


class TestAccessStatus:
    """Test /api/ai/access-status endpoint."""

    def test_access_status_endpoint(self, test_client):
        """Access status endpoint should return current status."""
        response = test_client.get("/api/ai/access-status")
        assert response.status_code == 200


class TestPinVerification:
    """Test /api/ai/verify endpoint."""

    def test_verify_requires_fields(self, test_client):
        """Verify endpoint requires pin and turnstile_token."""
        response = test_client.post("/api/ai/verify", json={})
        assert response.status_code == 422  # Validation error

    def test_verify_pin_format_validation(self, test_client):
        """Verify endpoint validates PIN format (4 digits)."""
        response = test_client.post(
            "/api/ai/verify",
            json={
                "pin": "abc",  # Invalid - not 4 digits
                "turnstile_token": "test-token"
            }
        )
        assert response.status_code == 422

    def test_verify_with_invalid_turnstile(self, test_client):
        """Verify endpoint should fail with invalid turnstile token."""
        response = test_client.post(
            "/api/ai/verify",
            json={
                "pin": "1234",
                "turnstile_token": "invalid"
            }
        )
        # Should return 200 with verified=False (not 4xx)
        assert response.status_code == 200
        data = response.json()
        assert data["verified"] is False


class TestChatSecurity:
    """Test chat endpoint security."""

    def test_chat_requires_session(self, test_client):
        """Chat endpoint requires valid session token."""
        response = test_client.post(
            "/api/ai/chat",
            json={
                "session_token": "invalid-token",
                "message": "Test message"
            }
        )
        assert response.status_code == 401

    def test_stream_requires_session(self, test_client):
        """Stream endpoint requires valid session token."""
        response = test_client.get(
            "/api/ai/stream",
            params={
                "session_token": "invalid-token",
                "message": "Test message"
            }
        )
        # SSE returns 200 with error event
        assert response.status_code == 200


class TestSessionInfo:
    """Test /api/ai/session-info endpoint."""

    def test_session_info_invalid_token(self, test_client):
        """Session info should reject invalid tokens."""
        response = test_client.get(
            "/api/ai/session-info",
            params={"session_token": "invalid"}
        )
        assert response.status_code == 401
