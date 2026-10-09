# SPDX-License-Identifier: AGPL-3.0-only
"""api/services/crawler_log.py: nginx's crawler lines, checked against the
operators' published addresses and folded into the dashboard's answer."""

from __future__ import annotations

import ipaddress
import json
from datetime import UTC, datetime, timedelta

from api.services import crawler_log as cl

GOOGLE_IP = "66.249.66.1"
RANGES = {
    "google": [ipaddress.ip_network("66.249.64.0/19")],
    "openai": [ipaddress.ip_network("20.0.0.0/8")],
}
GOOGLEBOT = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
CHATGPT = "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; ChatGPT-User/1.0; +https://openai.com/bot"
CLAUDE = "Mozilla/5.0 (compatible; ClaudeBot/1.0; +claudebot@anthropic.com)"


def line(ua, ip=GOOGLE_IP, req="GET /sites/peru/x-1", status=200, t="2026-10-10T08:00:00+02:00"):
    return json.dumps({"t": t, "ip": ip, "req": req, "status": status, "ua": ua})


def test_parse_keeps_known_bots_and_skips_half_lines_and_strangers():
    fetches = cl.parse_lines(
        [
            'ip":"1.2.3.4","req":"GET /"}',  # the tail starts mid-line
            line(GOOGLEBOT, req="GET /news-archive/x-1?utm_source=a"),
            line("Mozilla/5.0 (Windows NT 10.0) Chrome/130.0"),
            "{broken",
        ]
    )
    assert [(f.bot.name, f.path) for f in fetches] == [("Googlebot", "/news-archive/x-1")]


def test_the_user_agent_tokens_name_distinct_bots():
    assert cl.bot_of(CHATGPT).kind == "ai_user"
    assert cl.bot_of(CLAUDE).name == "ClaudeBot"
    assert cl.bot_of("Mozilla/5.0 (compatible; GPTBot/1.2)").kind == "training"
    assert cl.bot_of("Claude-User/1.0").kind == "ai_user"


def test_an_operator_with_a_list_verifies_and_one_without_stays_unverified():
    google, impostor, claude = cl.parse_lines(
        [line(GOOGLEBOT), line(GOOGLEBOT, ip="47.79.1.1"), line(CLAUDE, ip="160.79.104.10")]
    )
    assert cl.verified(google, RANGES) is True
    assert cl.verified(impostor, RANGES) is False
    assert cl.verified(claude, RANGES) is None


def test_an_ipv6_address_is_not_checked_against_ipv4_networks():
    (fetch,) = cl.parse_lines([line(GOOGLEBOT, ip="2001:db8::1")])
    assert cl.verified(fetch, RANGES) is False


def test_the_report_counts_verified_bots_and_sets_impostors_apart():
    fetches = cl.parse_lines(
        [
            line(GOOGLEBOT, req="GET /a", status=200),
            line(GOOGLEBOT, req="GET /a", status=200),
            line(GOOGLEBOT, req="GET /b", status=410),
            line(GOOGLEBOT, ip="47.79.1.1"),
            line(CHATGPT, ip="20.1.2.3", req="GET /sites/egypt/giza-1"),
            line(CLAUDE, ip="160.79.104.10", req="GET /research/x"),
        ]
    )
    out = cl.crawler_report(fetches, RANGES, datetime(2026, 10, 1, tzinfo=UTC))
    google = next(b for b in out["bots"] if b["bot"] == "Googlebot")
    assert google == {
        "bot": "Googlebot",
        "operator": "google",
        "kind": "search",
        "verified": True,
        "requests": 3,
        "pages": 2,
        "statuses": {"2xx": 2, "4xx": 1},
    }
    assert out["bots"][0]["bot"] == "Googlebot"
    assert next(b for b in out["bots"] if b["bot"] == "ClaudeBot")["verified"] is None
    assert out["impostors"] == [{"bot": "Googlebot", "requests": 1}]
    assert out["ai_user_pages"] == [
        {"path": "/sites/egypt/giza-1", "bot": "ChatGPT-User", "requests": 1}
    ]
    assert out["days"] == [
        {"day": "2026-10-10", "search": 3, "ai_user": 1, "ai_search": 0, "training": 1, "other": 0}
    ]


def test_the_report_buckets_days_in_utc_and_honours_the_window():
    fetches = cl.parse_lines(
        [
            # 00:30 local time on the 10th is still the 9th in UTC.
            line(GOOGLEBOT, t="2026-10-10T00:30:00+02:00"),
            line(GOOGLEBOT, t="2026-09-01T12:00:00+02:00"),
        ]
    )
    out = cl.crawler_report(fetches, RANGES, datetime(2026, 10, 1, tzinfo=UTC))
    assert [d["day"] for d in out["days"]] == ["2026-10-09"]
    assert out["covered_from"] == "2026-09-01T12:00:00+02:00"


def test_reading_a_missing_log_answers_none(monkeypatch, tmp_path):
    monkeypatch.setattr(cl, "LOG_PATH", tmp_path / "crawlers.log")
    monkeypatch.setattr(cl, "_parsed", None)
    assert cl.read_fetches() is None


def test_reading_the_log_parses_its_lines(monkeypatch, tmp_path):
    log = tmp_path / "crawlers.log"
    now = datetime.now(UTC)
    log.write_text(
        line(GOOGLEBOT, t=(now - timedelta(hours=1)).isoformat()) + "\n", encoding="utf-8"
    )
    monkeypatch.setattr(cl, "LOG_PATH", log)
    monkeypatch.setattr(cl, "_parsed", None)
    assert [f.bot.name for f in cl.read_fetches() or []] == ["Googlebot"]


def test_the_nginx_token_list_names_every_bot_the_reader_knows():
    """The two lists must not drift: a token only in BOTS is a bot nginx never logs."""
    from pathlib import Path

    config = (Path(__file__).resolve().parents[2] / "ancientnerds-nginx-config").read_text(
        encoding="utf-8"
    )
    start = config.index("map $http_user_agent $crawler_ua")
    tokens = config[config.index("~*(", start) + 3 : config.index(")", config.index("~*(", start))]
    assert {t.lower() for t in tokens.split("|")} == set(cl.BOTS)
