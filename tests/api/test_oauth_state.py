# SPDX-License-Identifier: AGPL-3.0-only
"""Tests for the signed Discord OAuth state token.

Previously the OAuth flow stored CSRF state in a process-local dict, so every
API restart silently invalidated all in-flight logins. The flow now signs the
state with API_SECRET_KEY (HMAC via PyJWT), making it stateless. These tests
guard the round-trip + every failure mode.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from api.services import jwt_auth


@pytest.fixture
def signing_key(monkeypatch):
    """Pin a known SECRET_KEY for state signing/verification."""
    monkeypatch.setattr(jwt_auth, "SECRET_KEY", "test-secret-do-not-use-in-prod")
    return jwt_auth.SECRET_KEY


@pytest.fixture
def oauth_module(signing_key):
    """Import the auth router lazily so it sees the patched SECRET_KEY."""
    from api.routes import auth

    return auth


class TestCreateAndConsume:
    def test_round_trip_returns_original_return_to(self, oauth_module):
        state = oauth_module._create_oauth_state("/theo.html")
        assert oauth_module._consume_oauth_state(state) == "/theo.html"

    def test_round_trip_for_every_allowlisted_path(self, oauth_module):
        for path in oauth_module._ALLOWED_RETURN_PATHS:
            state = oauth_module._create_oauth_state(path)
            assert oauth_module._consume_oauth_state(state) == path


class TestRejection:
    def test_empty_state_rejected(self, oauth_module):
        assert oauth_module._consume_oauth_state("") is None

    def test_garbage_state_rejected(self, oauth_module):
        assert oauth_module._consume_oauth_state("not-a-jwt") is None

    def test_state_signed_with_wrong_key_rejected(self, oauth_module):
        payload = {
            "aud": oauth_module._OAUTH_STATE_AUDIENCE,
            "rt": "/theo.html",
            "exp": datetime.now(UTC) + timedelta(seconds=600),
            "iat": datetime.now(UTC),
        }
        forged = jwt.encode(payload, "different-secret", algorithm=jwt_auth.ALGORITHM)
        assert oauth_module._consume_oauth_state(forged) is None

    def test_expired_state_rejected(self, oauth_module, signing_key):
        # Forge a token with `exp` already in the past.
        payload = {
            "aud": oauth_module._OAUTH_STATE_AUDIENCE,
            "rt": "/theo.html",
            "exp": datetime.now(UTC) - timedelta(seconds=1),
            "iat": datetime.now(UTC) - timedelta(seconds=2),
        }
        stale = jwt.encode(payload, signing_key, algorithm=jwt_auth.ALGORITHM)
        assert oauth_module._consume_oauth_state(stale) is None

    def test_wrong_audience_rejected(self, oauth_module, signing_key):
        # A JWT signed with our key but for a different purpose (e.g. a leaked
        # session token) must not be accepted as OAuth state.
        payload = {
            "aud": "some-other-purpose",
            "rt": "/theo.html",
            "exp": datetime.now(UTC) + timedelta(seconds=600),
            "iat": datetime.now(UTC),
        }
        misissued = jwt.encode(payload, signing_key, algorithm=jwt_auth.ALGORITHM)
        assert oauth_module._consume_oauth_state(misissued) is None

    def test_return_to_outside_allowlist_rejected(self, oauth_module, signing_key):
        # Open-redirect guard: even a valid signature can't smuggle an
        # arbitrary return_to value through. _create_oauth_state allows any
        # string in; _consume_oauth_state is the chokepoint.
        payload = {
            "aud": oauth_module._OAUTH_STATE_AUDIENCE,
            "rt": "https://evil.example/phish",
            "exp": datetime.now(UTC) + timedelta(seconds=600),
            "iat": datetime.now(UTC),
        }
        smuggled = jwt.encode(payload, signing_key, algorithm=jwt_auth.ALGORITHM)
        assert oauth_module._consume_oauth_state(smuggled) is None


class TestUnconfigured:
    def test_missing_secret_key_returns_none(self, monkeypatch, oauth_module):
        # Mid-flight callback after the operator has cleared API_SECRET_KEY.
        # Must not crash, must not accept the token.
        monkeypatch.setattr(jwt_auth, "SECRET_KEY", "")
        # Build a real-ish-looking token (won't verify because key is empty).
        bogus = jwt.encode({"rt": "/theo.html"}, "anything", algorithm=jwt_auth.ALGORITHM)
        assert oauth_module._consume_oauth_state(bogus) is None
