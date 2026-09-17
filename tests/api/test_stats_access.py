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


def test_gate_rejects_missing_expired_foreign_and_login_tokens():
    assert asyncio.run(sa.stats_gate(_request())).status_code == 401
    expired = sa.mint_stats_token("42", "martin", now=datetime.now(UTC) - timedelta(hours=13))
    assert asyncio.run(sa.stats_gate(_request({sa.COOKIE_NAME: expired}))).status_code == 401
    foreign = jwt.encode({"sub": "42", "scope": "stats"}, "another-key", algorithm="HS256")
    assert asyncio.run(sa.stats_gate(_request({sa.COOKIE_NAME: foreign}))).status_code == 401
    # A normal user login token has no stats scope: it must not open the dashboard.
    login = jwt_auth.create_token("1", "42")
    assert asyncio.run(sa.stats_gate(_request({sa.COOKIE_NAME: login}))).status_code == 401


# ---- handoff ------------------------------------------------------------


def test_handoff_issues_the_cookie_for_a_founder(monkeypatch):
    monkeypatch.setattr(
        sa, "get_session", _fake_session(SimpleNamespace(roles=[FOUNDER], username="martin"))
    )
    resp = asyncio.run(sa.stats_handoff(_request({"an_auth_token": jwt_auth.create_token("1", "42")})))
    assert resp.status_code == 302
    assert resp.headers["location"] == "https://stats.ancientnerds.com/"
    cookie = resp.headers["set-cookie"]
    assert cookie.startswith(f"{sa.COOKIE_NAME}=")
    for flag in ("Domain=.ancientnerds.com", "HttpOnly", "Secure", "SameSite=lax", "Path=/"):
        assert flag.lower() in cookie.lower(), flag
    token = cookie.split(";")[0].split("=", 1)[1]
    payload = jwt.decode(token, KEY, algorithms=["HS256"])
    assert payload["scope"] == "stats" and payload["sub"] == "42" and payload["name"] == "martin"


def test_handoff_refuses_without_founder_role(monkeypatch):
    monkeypatch.setattr(sa, "get_session", _fake_session(SimpleNamespace(roles=["1"], username="x")))
    resp = asyncio.run(sa.stats_handoff(_request({"an_auth_token": jwt_auth.create_token("1", "42")})))
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
    assert 'href="/api/auth/discord?return_to=%2Fapi%2Fauth%2Fstats-handoff"' in html
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
