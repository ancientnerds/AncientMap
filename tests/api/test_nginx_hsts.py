# SPDX-License-Identifier: AGPL-3.0-only
"""ancientnerds-nginx-config sends HSTS on the homepage.

TTFB audit 2026-10-20 (output/seo-audit-2026-10-19/ttfb.md): 52 of 868 browser
requests for "/" in the access log of 05.-20.10. arrived after an http:// 301,
a hop of ~2 round trips before the TLS connection starts. A browser that has
seen Strict-Transport-Security skips it. nginx hands a server-level add_header
only to locations without one of their own, so the homepage location must stay
without one.
"""

from __future__ import annotations

import re
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[2] / "ancientnerds-nginx-config"
HSTS = 'add_header Strict-Transport-Security "max-age=31536000" always;'


def _blocks(text: str) -> list[tuple[str, str]]:
    """(header, body) of every top-level block, comments stripped."""
    text = re.sub(r"#[^\n]*", "", text)
    blocks, depth, start, header_start = [], 0, 0, 0
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i + 1
                header = text[header_start:i].strip().split(";")[-1].strip()
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                blocks.append((header, text[start:i]))
                header_start = i + 1
        elif ch == ";" and depth == 0:
            header_start = i + 1
    return blocks


def _top_level(body: str) -> str:
    """The body without its nested blocks: the directives at this level."""
    out, depth = [], 0
    for ch in body:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif depth == 0:
            out.append(ch)
    return "".join(out)


def _main_server() -> str:
    servers = [b for h, b in _blocks(CONFIG.read_text(encoding="utf-8")) if h == "server"]
    (main,) = [b for b in servers if "listen 443 ssl http2 default_server;" in b]
    return main


def test_the_main_https_server_sends_hsts_at_server_level():
    assert HSTS in " ".join(_top_level(_main_server()).split())


def test_the_homepage_location_inherits_it():
    body = _main_server()
    m = re.search(r"location = / \{", body)
    assert m, "location = / is gone"
    depth, i = 1, m.end()
    while depth:
        depth += {"{": 1, "}": -1}.get(body[i], 0)
        i += 1
    assert "add_header" not in re.sub(r"#[^\n]*", "", body[m.end() : i])
