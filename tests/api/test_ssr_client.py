# SPDX-License-Identifier: AGPL-3.0-only
"""Der SSR-Dienst ist eine harte Abhängigkeit — Ausfall muss laut sein."""

from __future__ import annotations

import httpx
import pytest

from api.ssr_client import SsrUnavailableError, render_page


def test_returns_head_and_html(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/render"
        return httpx.Response(200, json={"head": "<title>x</title>", "html": "<div>y</div>"})

    monkeypatch.setattr(
        "api.ssr_client._client",
        httpx.Client(transport=httpx.MockTransport(handler), base_url="http://ssr:8500"),
    )
    head, html = render_page({"type": "sitesIndex", "countries": []})
    assert head == "<title>x</title>"
    assert html == "<div>y</div>"


def test_raises_loudly_when_the_service_is_down(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(
        "api.ssr_client._client",
        httpx.Client(transport=httpx.MockTransport(handler), base_url="http://ssr:8500"),
    )
    with pytest.raises(SsrUnavailableError):
        render_page({"type": "sitesIndex", "countries": []})


def test_raises_on_render_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "unknown route type: nope"})

    monkeypatch.setattr(
        "api.ssr_client._client",
        httpx.Client(transport=httpx.MockTransport(handler), base_url="http://ssr:8500"),
    )
    with pytest.raises(SsrUnavailableError, match="unknown route type"):
        render_page({"type": "nope"})
