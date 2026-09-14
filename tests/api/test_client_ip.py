"""Tests for get_client_ip — which IP a rate-limit bucket is keyed on.

Regression: our nginx `location /api/` block sets X-Real-IP but not
X-Forwarded-For. get_client_ip only read XFF, so behind the proxy every
request keyed on request.client.host — the docker gateway. On 2026-09-14 the
entire heavy_radar namespace on prod held one Redis key,
rate_limit:heavy_radar:172.18.0.1: the 10-requests-per-minute radar budget was
shared by the founder, every visitor and every bot simultaneously.
"""

import importlib

import pytest


class FakeClient:
    def __init__(self, host):
        self.host = host


class FakeRequest:
    def __init__(self, headers=None, host="172.18.0.1"):
        self.headers = headers or {}
        self.client = FakeClient(host) if host else None


@pytest.fixture
def behind_proxy(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY", "1")
    import api.services.rate_limiter as rl

    return importlib.reload(rl)


@pytest.fixture
def direct(monkeypatch):
    monkeypatch.delenv("TRUSTED_PROXY", raising=False)
    import api.services.rate_limiter as rl

    return importlib.reload(rl)


def test_x_real_ip_is_used_when_forwarded_for_is_absent(behind_proxy):
    req = FakeRequest({"X-Real-IP": "203.0.113.7"}, host="172.18.0.1")
    assert behind_proxy.get_client_ip(req) == "203.0.113.7"


def test_forwarded_for_still_wins_when_both_are_present(behind_proxy):
    req = FakeRequest(
        {"X-Forwarded-For": "198.51.100.4", "X-Real-IP": "203.0.113.7"}, host="172.18.0.1"
    )
    assert behind_proxy.get_client_ip(req) == "198.51.100.4"


def test_forwarded_for_takes_the_last_hop(behind_proxy):
    req = FakeRequest({"X-Forwarded-For": "1.2.3.4, 198.51.100.4"}, host="172.18.0.1")
    assert behind_proxy.get_client_ip(req) == "198.51.100.4"


def test_falls_back_to_socket_peer_when_no_proxy_header(behind_proxy):
    assert behind_proxy.get_client_ip(FakeRequest({}, host="172.18.0.1")) == "172.18.0.1"


def test_proxy_headers_are_ignored_without_trusted_proxy(direct):
    """Untrusted deployments must not let a client pick its own bucket."""
    req = FakeRequest({"X-Real-IP": "203.0.113.7", "X-Forwarded-For": "1.2.3.4"}, host="10.0.0.9")
    assert direct.get_client_ip(req) == "10.0.0.9"


def test_missing_client_is_not_an_error(behind_proxy):
    assert behind_proxy.get_client_ip(FakeRequest({}, host=None)) == "unknown"
