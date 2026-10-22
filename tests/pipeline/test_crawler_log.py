# SPDX-License-Identifier: AGPL-3.0-only
"""pipeline/crawler_log.py: nginx's crawler lines, checked against the
operators' published addresses and folded into the dashboard's answer."""

from __future__ import annotations

import gzip
import ipaddress
import json
import re
from datetime import UTC, datetime, timedelta

from pipeline import crawler_log as cl

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
            'ip":"1.2.3.4","req":"GET /"}',  # a half line
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
    monkeypatch.setattr(cl, "_files", {})
    assert cl.read_fetches() is None


def test_reading_the_log_parses_its_lines(monkeypatch, tmp_path):
    log = tmp_path / "crawlers.log"
    now = datetime.now(UTC)
    log.write_text(
        line(GOOGLEBOT, t=(now - timedelta(hours=1)).isoformat()) + "\n", encoding="utf-8"
    )
    monkeypatch.setattr(cl, "LOG_PATH", log)
    monkeypatch.setattr(cl, "_parsed", None)
    monkeypatch.setattr(cl, "_files", {})
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


def test_every_bots_key_is_lower_case():
    """bot_of looks the matched token up lower-cased."""
    assert all(k == k.lower() for k in cl.BOTS)


def test_the_longest_token_wins():
    # A token inside a longer one must not shadow it, whatever the dict order:
    # every token, alone in a user agent, names its own bot.
    for token, bot in cl.BOTS.items():
        assert cl.bot_of(f"Mozilla/5.0 (compatible; {bot.name}/1.0)") is bot, token
    tokens = [re.sub(r"\\(.)", r"\1", t) for t in cl.BOT_RE.pattern.split("|")]
    assert [len(t) for t in tokens] == sorted((len(t) for t in tokens), reverse=True)
    assert cl.bot_of("Mozilla/5.0 (compatible; OAI-AdsBot/1.0)").name == "OAI-AdsBot"
    assert cl.bot_of("Mozilla/5.0 (compatible; DuckAssistBot/1.2)").kind == "ai_search"
    assert cl.bot_of("Mozilla/5.0 (compatible; Google-GeminiNotebook)").kind == "ai_user"
    assert cl.bot_of("facebookexternalhit/1.1").operator == "meta"


def test_amazonbot_is_a_training_crawler():
    assert cl.bot_of("Mozilla/5.0 (compatible; Amazonbot/0.1)").kind == "training"


def test_mistral_training_has_no_list_and_is_never_an_impostor():
    ranges = {"mistral": [ipaddress.ip_network("20.240.160.0/24")]}
    (training,) = cl.parse_lines([line("MistralAI-Training/1.0", ip="47.79.1.1")])
    (user,) = cl.parse_lines([line("MistralAI-User/1.0", ip="47.79.1.1")])
    assert cl.verified(training, ranges) is None
    assert cl.verified(user, ranges) is False


def test_verified_ip_checks_a_bot_and_an_address_from_any_log():
    googlebot = cl.BOTS["googlebot"]
    assert cl.verified_ip(googlebot, GOOGLE_IP, RANGES) is True
    assert cl.verified_ip(googlebot, "47.79.1.1", RANGES) is False
    assert cl.verified_ip(cl.BOTS["bytespider"], "47.79.1.1", RANGES) is None


def test_every_operator_list_url_is_https_json():
    for urls in cl.RANGE_URLS.values():
        assert all(u.startswith("https://") and u.endswith(".json") for u in urls)
    assert "amazon" not in cl.RANGE_URLS  # HTML only, no scraper for it


def test_reading_the_log_reads_the_rotated_family_oldest_first(monkeypatch, tmp_path):
    log = tmp_path / "crawlers.log"
    (tmp_path / "crawlers.log-20261020.gz").write_bytes(
        gzip.compress((line(GOOGLEBOT, req="GET /a") + "\n").encode())
    )
    (tmp_path / "crawlers.log-20261021").write_text(
        line(GOOGLEBOT, req="GET /b") + "\n", encoding="utf-8"
    )
    log.write_text(line(GOOGLEBOT, req="GET /c") + "\n", encoding="utf-8")
    monkeypatch.setattr(cl, "LOG_PATH", log)
    monkeypatch.setattr(cl, "_parsed", None)
    monkeypatch.setattr(cl, "_files", {})
    assert [f.path for f in cl.read_fetches() or []] == ["/a", "/b", "/c"]


def test_a_rotated_file_is_parsed_once_and_the_live_one_again(monkeypatch, tmp_path):
    log = tmp_path / "crawlers.log"
    (tmp_path / "crawlers.log-20261021").write_text(
        line(GOOGLEBOT, req="GET /a") + "\n", encoding="utf-8"
    )
    log.write_text(line(GOOGLEBOT, req="GET /b") + "\n", encoding="utf-8")
    monkeypatch.setattr(cl, "LOG_PATH", log)
    monkeypatch.setattr(cl, "CACHE_MIN_SECONDS", 0.0)
    monkeypatch.setattr(cl, "_parsed", None)
    monkeypatch.setattr(cl, "_files", {})
    parsed: list[str] = []
    real = cl.parse_lines
    monkeypatch.setattr(cl, "parse_lines", lambda lines: parsed.extend(lines) or real(lines))
    cl.read_fetches()
    with log.open("a", encoding="utf-8") as fh:
        fh.write(line(GOOGLEBOT, req="GET /c") + "\n")
    assert [f.path for f in cl.read_fetches() or []] == ["/a", "/b", "/c"]
    assert sum('"GET /a"' in p for p in parsed) == 1
