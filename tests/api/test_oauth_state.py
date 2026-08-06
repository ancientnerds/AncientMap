# SPDX-License-Identifier: AGPL-3.0-only
"""Tests for the signed Discord OAuth state token.

Previously the OAuth flow stored CSRF state in a process-local dict, so every
API restart silently invalidated all in-flight logins. The flow now signs the
state with API_SECRET_KEY (HMAC via PyJWT), making it stateless, AND binds it
to the starting browser via a nonce cookie (audit 2026-08-05, M3): the state
carries sha256(nonce), the cookie carries the nonce, the callback requires
both. These tests guard the round-trip + every failure mode.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from api.services import jwt_auth

NONCE = "test-nonce-0123456789abcdef"
NONCE_HASH = hashlib.sha256(NONCE.encode()).hexdigest()


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


def _forge(oauth_module, signing_key, **overrides):
    """Build a state payload with valid defaults, then apply overrides."""
    payload = {
        "aud": oauth_module._OAUTH_STATE_AUDIENCE,
        "rt": "/theo.html",
        "nh": NONCE_HASH,
        "exp": datetime.now(UTC) + timedelta(seconds=600),
        "iat": datetime.now(UTC),
    }
    payload.update(overrides)
    return jwt.encode(payload, signing_key, algorithm=jwt_auth.ALGORITHM)


class TestCreateAndConsume:
    def test_round_trip_returns_original_return_to(self, oauth_module):
        state = oauth_module._create_oauth_state("/theo.html", NONCE)
        assert oauth_module._consume_oauth_state(state, NONCE) == "/theo.html"

    def test_round_trip_for_every_allowlisted_path(self, oauth_module):
        for path in oauth_module._ALLOWED_RETURN_PATHS:
            state = oauth_module._create_oauth_state(path, NONCE)
            assert oauth_module._consume_oauth_state(state, NONCE) == path


class TestNonceBinding:
    def test_missing_nonce_cookie_rejected(self, oauth_module):
        # Callback URL opened in a browser that never started the flow
        # (cross-device link or CSRF attempt) — no cookie, no login.
        state = oauth_module._create_oauth_state("/theo.html", NONCE)
        assert oauth_module._consume_oauth_state(state, None) is None
        assert oauth_module._consume_oauth_state(state, "") is None

    def test_wrong_nonce_cookie_rejected(self, oauth_module):
        # Attacker-minted state in a victim browser: victim's cookie (if any)
        # never matches the attacker state's nonce hash.
        state = oauth_module._create_oauth_state("/theo.html", NONCE)
        assert oauth_module._consume_oauth_state(state, "different-nonce") is None

    def test_state_without_nonce_hash_rejected(self, oauth_module, signing_key):
        # Legacy/forged state lacking the nh claim must not pass even with
        # a cookie present.
        payload = {
            "aud": oauth_module._OAUTH_STATE_AUDIENCE,
            "rt": "/theo.html",
            "exp": datetime.now(UTC) + timedelta(seconds=600),
            "iat": datetime.now(UTC),
        }
        legacy = jwt.encode(payload, signing_key, algorithm=jwt_auth.ALGORITHM)
        assert oauth_module._consume_oauth_state(legacy, NONCE) is None


class TestRejection:
    def test_empty_state_rejected(self, oauth_module):
        assert oauth_module._consume_oauth_state("", NONCE) is None

    def test_garbage_state_rejected(self, oauth_module):
        assert oauth_module._consume_oauth_state("not-a-jwt", NONCE) is None

    def test_state_signed_with_wrong_key_rejected(self, oauth_module):
        forged = jwt.encode(
            {
                "aud": oauth_module._OAUTH_STATE_AUDIENCE,
                "rt": "/theo.html",
                "nh": NONCE_HASH,
                "exp": datetime.now(UTC) + timedelta(seconds=600),
                "iat": datetime.now(UTC),
            },
            "different-secret",
            algorithm=jwt_auth.ALGORITHM,
        )
        assert oauth_module._consume_oauth_state(forged, NONCE) is None

    def test_expired_state_rejected(self, oauth_module, signing_key):
        stale = _forge(
            oauth_module,
            signing_key,
            exp=datetime.now(UTC) - timedelta(seconds=1),
            iat=datetime.now(UTC) - timedelta(seconds=2),
        )
        assert oauth_module._consume_oauth_state(stale, NONCE) is None

    def test_wrong_audience_rejected(self, oauth_module, signing_key):
        # A JWT signed with our key but for a different purpose (e.g. a leaked
        # session token) must not be accepted as OAuth state.
        misissued = _forge(oauth_module, signing_key, aud="some-other-purpose")
        assert oauth_module._consume_oauth_state(misissued, NONCE) is None

    def test_return_to_outside_allowlist_rejected(self, oauth_module, signing_key):
        # Open-redirect guard: even a valid signature + matching nonce can't
        # smuggle an arbitrary return_to through. The nonce here is CORRECT so
        # the test exercises the allowlist check, not the nonce check.
        smuggled = _forge(oauth_module, signing_key, rt="https://evil.example/phish")
        assert oauth_module._consume_oauth_state(smuggled, NONCE) is None


class TestUnconfigured:
    def test_missing_secret_key_returns_none(self, monkeypatch, oauth_module):
        # Mid-flight callback after the operator has cleared API_SECRET_KEY.
        # Must not crash, must not accept the token.
        monkeypatch.setattr(jwt_auth, "SECRET_KEY", "")
        bogus = jwt.encode({"rt": "/theo.html"}, "anything", algorithm=jwt_auth.ALGORITHM)
        assert oauth_module._consume_oauth_state(bogus, NONCE) is None
