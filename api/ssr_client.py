# SPDX-License-Identifier: AGPL-3.0-only
"""
Client zum SSR-Sidecar.

Der Dienst ist eine harte Abhängigkeit, kein Bonus: fällt er aus, sollen die
indexierten Routen mit 502 antworten (Handler in api/main.py). Ein Rückfall
auf einen zweiten Renderer wäre genau die Doppelung, die dieser Umbau
beseitigt.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

SSR_SERVICE_URL = os.getenv("SSR_SERVICE_URL", "http://ssr:8500")

_client = httpx.Client(base_url=SSR_SERVICE_URL, timeout=10.0)


class SsrUnavailableError(RuntimeError):
    """Der SSR-Dienst hat nicht geliefert — Betriebsfehler, nicht Anfragefehler."""


def render_page(route: dict[str, Any]) -> tuple[str, str]:
    """Rendert ein Route-Payload. Liefert (head, html)."""
    try:
        response = _client.post("/render", json=route)
    except httpx.HTTPError as exc:
        raise SsrUnavailableError(f"SSR service at {SSR_SERVICE_URL} unreachable: {exc}") from exc

    if response.status_code != 200:
        detail = response.json().get("error", response.text) if response.content else response.text
        raise SsrUnavailableError(f"SSR render failed: {detail}")

    data = response.json()
    return data["head"], data["html"]
