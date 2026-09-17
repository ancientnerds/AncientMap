# SPDX-License-Identifier: AGPL-3.0-only
"""scripts/referral_report.py — Referrer-Log nach Familie, Host und Mensch/Bot.

Die Zeilen sind das JSON, das nginx per log_format ``referral`` schreibt.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

# By file: a dependency installs a top-level package named `scripts` into
# site-packages, which shadows our scripts/ directory for a plain import.
_SPEC = importlib.util.spec_from_file_location(
    "referral_report", Path(__file__).resolve().parents[2] / "scripts" / "referral_report.py"
)
assert _SPEC is not None and _SPEC.loader is not None
rr = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rr)

SINCE = datetime(2026, 9, 17, tzinfo=UTC)
HUMAN = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0 Safari/537.36"
BOT = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"


def _line(
    ref: str,
    req: str,
    ua: str = HUMAN,
    t: str = "2026-09-17T12:00:00+00:00",
    status: int = 200,
) -> str:
    return json.dumps({"t": t, "ref": ref, "req": req, "status": status, "ua": ua})


def test_ai_suche_social_und_rest_werden_nach_host_gezaehlt():
    lines = [
        _line("https://chatgpt.com/", "GET /sites/egypt"),
        _line("https://chatgpt.com/c/abc", "GET /research/"),
        _line("https://www.google.com/", "GET /sites/", ua=BOT),
        _line("https://www.google.de/search?q=x", "GET /globe.html"),
        _line("https://discord.com/channels/1/2", "GET /news-archive/"),
        _line("https://example.org/blog", "GET /"),
    ]
    result = rr.aggregate(lines, SINCE)
    assert result["ai"]["chatgpt.com"] == {"human": 2}
    assert result["search"]["google.com"] == {"bot": 1}
    assert result["search"]["google.de"] == {"human": 1}
    assert result["social"]["discord.com"] == {"human": 1}
    assert result["other"]["example.org"] == {"human": 1}


def test_utm_source_ersetzt_fehlenden_referer_nur_fuer_bekannte_hosts():
    lines = [
        _line("", "GET /sites/peru?utm_source=chatgpt.com"),
        _line("", "GET /sites/peru?utm_source=newsletter"),
    ]
    result = rr.aggregate(lines, SINCE)
    assert result["ai"]["chatgpt.com"] == {"human": 1}
    assert "other" not in result


def test_assets_und_api_zaehlen_nur_mit_all():
    lines = [
        _line("https://example.org/", "GET /data/images/x.webp"),
        _line("https://example.org/", "GET /api/sites/abc"),
        _line("https://example.org/", "GET /assets/main-abc.js"),
        _line("https://example.org/", "GET /sites/egypt"),
    ]
    assert rr.aggregate(lines, SINCE)["other"]["example.org"] == {"human": 1}
    assert rr.aggregate(lines, SINCE, pages_only=False)["other"]["example.org"] == {"human": 4}


def test_aeltere_zeilen_und_muell_werden_ignoriert():
    lines = [
        _line("https://example.org/", "GET /", t="2026-09-16T23:59:00+00:00"),
        "not json at all",
        '{"t":"2026-09-17T01:00:00+00:00","ref":"https://example.org/","req":"GET /",',
        _line("https://example.org/", "GET /"),
    ]
    assert rr.aggregate(lines, SINCE)["other"]["example.org"] == {"human": 1}


def test_since_relativ_und_absolut():
    now = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)
    assert rr.parse_since("7d", now) == datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
    assert rr.parse_since("6h", now) == datetime(2026, 9, 17, 6, 0, tzinfo=UTC)
    assert rr.parse_since("2026-09-01T00:00:00", now) == datetime(2026, 9, 1, tzinfo=UTC)


def test_fehlerantworten_sind_scanner_rauschen_und_zaehlen_nur_mit_all():
    lines = [
        _line("https://binance.com/", "GET /wp-admin/css/", status=404),
        _line("https://binance.com/", "GET /", status=200),
    ]
    assert rr.aggregate(lines, SINCE)["other"]["binance.com"] == {"human": 1}
    assert rr.aggregate(lines, SINCE, pages_only=False)["other"]["binance.com"] == {"human": 2}
