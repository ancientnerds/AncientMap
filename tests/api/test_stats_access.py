# SPDX-License-Identifier: AGPL-3.0-only
"""stats.ancientnerds.com gate — Discord login, Founder role, signed cookie.

DB-less: the handoff's user lookup runs against a fake session; tokens are
signed with a test key set on jwt_auth.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import jwt
import pytest
from starlette.requests import Request

from api.routes import auth as auth_routes
from api.routes import stats_access as sa
from api.services import jwt_auth

KEY = "test-secret-key-for-stats-access-0123456789"
FOUNDER = jwt_auth.FOUNDER_ROLE_ID


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setattr(jwt_auth, "SECRET_KEY", KEY)


def _request(cookies: dict[str, str] | None = None, query: str = "") -> Request:
    cookie_header = "; ".join(f"{k}={v}" for k, v in (cookies or {}).items())
    headers = [(b"cookie", cookie_header.encode())] if cookie_header else []
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/auth/stats-gate",
        "query_string": query.encode(),
        "headers": headers,
    }
    return Request(scope)


def _fake_session(user):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = user

    @contextmanager
    def session():
        yield db

    return session


# ---- gate ---------------------------------------------------------------


def test_gate_lets_a_stats_session_through():
    token = sa.mint_stats_token("42", "martin")
    resp = asyncio.run(sa.stats_gate(_request({sa.COOKIE_NAME: token})))
    assert resp.status_code == 204


def test_gate_keeps_a_founder_signed_in_for_30_days():
    # Owner decision 2026-09-24: one Discord login per month, not per half day.
    day_29 = sa.mint_stats_token("42", "martin", now=datetime.now(UTC) - timedelta(days=29))
    assert asyncio.run(sa.stats_gate(_request({sa.COOKIE_NAME: day_29}))).status_code == 204
    day_31 = sa.mint_stats_token("42", "martin", now=datetime.now(UTC) - timedelta(days=31))
    assert asyncio.run(sa.stats_gate(_request({sa.COOKIE_NAME: day_31}))).status_code == 401


def test_gate_rejects_missing_expired_foreign_and_login_tokens():
    assert asyncio.run(sa.stats_gate(_request())).status_code == 401
    expired = sa.mint_stats_token(
        "42", "martin", now=datetime.now(UTC) - timedelta(days=sa.SESSION_DAYS, hours=1)
    )
    assert asyncio.run(sa.stats_gate(_request({sa.COOKIE_NAME: expired}))).status_code == 401
    foreign = jwt.encode({"sub": "42", "scope": "stats"}, "another-key", algorithm="HS256")
    assert asyncio.run(sa.stats_gate(_request({sa.COOKIE_NAME: foreign}))).status_code == 401
    # A normal user login token has no stats scope: it must not open the dashboard.
    login = jwt_auth.create_token("1", "42")
    assert asyncio.run(sa.stats_gate(_request({sa.COOKIE_NAME: login}))).status_code == 401


# ---- handoff ------------------------------------------------------------


def test_handoff_issues_the_cookie_and_the_umami_sso_hop_for_a_founder(monkeypatch):
    monkeypatch.setattr(
        sa, "get_session", _fake_session(SimpleNamespace(roles=[FOUNDER], username="martin"))
    )
    monkeypatch.setattr(sa, "umami_login_token", lambda: "umami-token-xyz")
    resp = asyncio.run(
        sa.stats_handoff(_request({"an_auth_token": jwt_auth.create_token("1", "42")}))
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == "https://stats.ancientnerds.com/sso#umami-token-xyz"
    cookie = resp.headers["set-cookie"]
    assert cookie.startswith(f"{sa.COOKIE_NAME}=")
    for flag in ("Domain=.ancientnerds.com", "HttpOnly", "Secure", "SameSite=lax", "Path=/"):
        assert flag.lower() in cookie.lower(), flag
    token = cookie.split(";")[0].split("=", 1)[1]
    payload = jwt.decode(token, KEY, algorithms=["HS256"])
    assert payload["scope"] == "stats" and payload["sub"] == "42" and payload["name"] == "martin"
    # Cookie and token end together, after 30 days.
    assert "max-age=2592000" in cookie.lower()
    assert payload["exp"] - payload["iat"] == 30 * 24 * 3600


def test_handoff_refuses_without_founder_role(monkeypatch):
    monkeypatch.setattr(
        sa, "get_session", _fake_session(SimpleNamespace(roles=["1"], username="x"))
    )
    resp = asyncio.run(
        sa.stats_handoff(_request({"an_auth_token": jwt_auth.create_token("1", "42")}))
    )
    assert resp.status_code == 403
    assert "set-cookie" not in resp.headers
    assert "No Founder role" in resp.body.decode()


def test_handoff_without_login_cookie_starts_the_discord_flow():
    resp = asyncio.run(sa.stats_handoff(_request()))
    assert resp.status_code == 307 or resp.status_code == 302
    assert resp.headers["location"] == "/api/auth/discord?return_to=%2Fapi%2Fauth%2Fstats-handoff"


def test_handoff_path_is_an_allowed_return_target():
    assert auth_routes._is_allowed_return(sa.HANDOFF_PATH)


# ---- entry page ---------------------------------------------------------


def test_login_page_is_mobile_first_and_links_only_to_our_hosts():
    html = sa.gate_html()
    assert 'name="viewport" content="width=device-width, initial-scale=1' in html
    # Absolute on purpose: the page lives on the stats host, the OAuth route on the main one.
    assert (
        'href="https://ancientnerds.com/api/auth/discord?return_to=%2Fapi%2Fauth%2Fstats-handoff"'
        in html
    )
    assert "Continue with Discord" in html
    assert 'name="robots" content="noindex' in html
    import re

    hosts = set(re.findall(r"https?://([a-z0-9.-]+)", html))
    assert hosts == {"ancientnerds.com"}
    denied = sa.gate_html(denied=True)
    assert "No Founder role" in denied and "Try another account" in denied


def test_logout_clears_the_cookie():
    resp = asyncio.run(sa.stats_logout())
    assert resp.status_code == 302
    assert f"{sa.COOKIE_NAME}=" in resp.headers["set-cookie"]
    assert "max-age=0" in resp.headers["set-cookie"].lower()


def test_handoff_falls_back_to_the_dashboard_login_when_sso_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        sa, "get_session", _fake_session(SimpleNamespace(roles=[FOUNDER], username="martin"))
    )
    monkeypatch.setattr(sa, "umami_login_token", lambda: None)
    resp = asyncio.run(
        sa.stats_handoff(_request({"an_auth_token": jwt_auth.create_token("1", "42")}))
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == "https://stats.ancientnerds.com/"
    assert resp.headers["set-cookie"].startswith(f"{sa.COOKIE_NAME}=")


def test_umami_login_token_paths(monkeypatch):
    monkeypatch.delenv("UMAMI_SSO_USERNAME", raising=False)
    monkeypatch.delenv("UMAMI_SSO_PASSWORD", raising=False)
    assert sa.umami_login_token() is None  # not configured

    monkeypatch.setenv("UMAMI_SSO_USERNAME", "founders")
    monkeypatch.setenv("UMAMI_SSO_PASSWORD", "pw")
    calls = []

    class Resp:
        def __init__(self, status, body):
            self.status_code, self._body, self.text = status, body, str(body)

        def json(self):
            return self._body

    def fake_post(url, json, timeout):
        calls.append((url, json))
        return Resp(200, {"token": "tok", "user": {"username": "founders"}})

    monkeypatch.setattr(sa.httpx, "post", fake_post)
    assert sa.umami_login_token() == "tok"
    assert calls[0][0].endswith("/api/auth/login")
    assert calls[0][1] == {"username": "founders", "password": "pw"}

    monkeypatch.setattr(sa.httpx, "post", lambda *a, **k: Resp(401, {"error": "bad"}))
    assert sa.umami_login_token() is None

    def boom(*a, **k):
        raise OSError("down")

    monkeypatch.setattr(sa.httpx, "post", boom)
    assert sa.umami_login_token() is None


def test_sso_page_stores_the_token_like_umami_does():
    resp = asyncio.run(sa.stats_sso())
    html = resp.body.decode()
    assert "localStorage.setItem('umami.auth', JSON.stringify(token))" in html
    assert "location.hash" in html and "location.replace('/')" in html
    assert resp.headers["cache-control"] == "no-store"
