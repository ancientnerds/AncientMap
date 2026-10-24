# SPDX-License-Identifier: AGPL-3.0-only
"""pipeline/request_log.py: nginx's request lines, grouped into clients and
counted per class (the rules themselves are pipeline/visitor_class.py's and
tested in test_visitor_class.py)."""

from __future__ import annotations

import gzip
import ipaddress
import json
from datetime import UTC, datetime, timedelta

import pytest

from pipeline import asn, request_log

BROWSER = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"
GOOGLEBOT = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
BYTESPIDER = "Mozilla/5.0 (compatible; Bytespider; spider-feedback@bytedance.com)"
CURL = "curl/8.5.0"
RANGES = {"google": [ipaddress.ip_network("66.249.64.0/19")]}
T0 = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
NOW = datetime(2026, 10, 23, 0, 0, tzinfo=UTC)


def line(
    ip="203.0.113.9",
    req="GET /sites/peru/x-1",
    status=200,
    ua=BROWSER,
    at=T0,
    ref="",
    purpose="",
    dnt="",
    gpc="",
):
    return json.dumps(
        {
            "t": at.isoformat(),
            "ip": ip,
            "req": req,
            "status": status,
            "ua": ua,
            "ref": ref,
            "proto": "HTTP/2.0",
            "purpose": purpose,
            "dest": "document",
            "dnt": dnt,
            "gpc": gpc,
        }
    )


def classify(*lines, table=None):
    return request_log.classify(request_log.parse_lines(list(lines)), RANGES, table)


@pytest.fixture
def table(tmp_path, monkeypatch):
    """Two networks: 203.0.113.0/24 a home ISP, 198.51.100.0/24 Hetzner (a
    datacenter in the vendored list)."""
    rows = [
        (
            int(ipaddress.IPv4Address("198.51.100.0")),
            int(ipaddress.IPv4Address("198.51.100.255")),
            24940,
            "DE",
            "HETZNER-AS",
        ),
        (
            int(ipaddress.IPv4Address("203.0.113.0")),
            int(ipaddress.IPv4Address("203.0.113.255")),
            3320,
            "DE",
            "DTAG",
        ),
    ]
    path = tmp_path / "ip2asn-v4-u32.tsv.gz"
    text = "".join("\t".join(str(v) for v in row) + "\n" for row in rows)
    path.write_bytes(gzip.compress(text.encode()))
    monkeypatch.setattr(asn, "ASN_DB_PATH", path)
    monkeypatch.setattr(asn, "_loaded", None)
    return asn.load()


def test_parse_skips_half_lines_and_broken_json_and_strips_the_query():
    (r,) = request_log.parse_lines(
        ['ip":"1.2.3.4","req":"GET /"}', line(req="GET /sites/x?utm_source=a"), "{broken"]
    )
    assert (r.method, r.path, r.status, r.proto, r.dest) == (
        "GET",
        "/sites/x",
        200,
        "HTTP/2.0",
        "document",
    )


def test_a_page_with_a_beacon_is_a_browser_with_javascript():
    out = classify(
        line(),
        line(req="POST /api/pulse", at=T0 + timedelta(seconds=3)),
        line(req="GET /pulse.js", at=T0 + timedelta(seconds=1)),
    )
    assert out["classes"]["browser_js"] == {
        "requests": 1,
        "clients": 1,
        "honeypot": 0,
        "unverified": 0,
    }
    assert out["classes"]["scraper_nojs"]["requests"] == 0


def test_a_page_without_a_beacon_is_a_scraper_and_with_dnt_unclear():
    out = classify(
        line(ip="203.0.113.1"),
        line(ip="203.0.113.2", dnt="1"),
        line(ip="203.0.113.3", req="POST /api/pulse", at=T0 - timedelta(seconds=121)),
        line(ip="203.0.113.3"),
    )
    assert out["classes"]["scraper_nojs"]["clients"] == 2
    assert out["classes"]["unclear"]["clients"] == 1


def test_a_beacon_of_another_client_does_not_count():
    out = classify(line(ip="203.0.113.1"), line(ip="203.0.113.2", req="POST /api/pulse"))
    assert out["classes"]["scraper_nojs"]["clients"] == 1
    out = classify(line(), line(req="POST /api/pulse", ua=BROWSER.replace("130", "131")))
    assert out["classes"]["scraper_nojs"]["clients"] == 1


def test_a_beacon_does_not_carry_over_midnight_utc():
    # The client is (ip, ua) on one UTC day.
    late = datetime(2026, 10, 21, 23, 59, 30, tzinfo=UTC)
    out = classify(line(at=late), line(req="POST /api/pulse", at=late + timedelta(seconds=60)))
    assert out["classes"]["scraper_nojs"]["requests"] == 1


def test_only_pages_and_the_honeypot_are_classed():
    out = classify(
        line(req="GET /sitemap.xml"),
        line(req="GET /robots.txt"),
        line(req="GET /feeds/stories"),
        line(req="POST /sites/x"),
        line(req="GET /missing", status=404),
        line(req="GET /pulse.js"),
        line(req="GET /story/withdrawn", status=410),
    )
    assert sum(c["requests"] for c in out["classes"].values()) == 1


def test_a_honeypot_fetch_marks_the_client_and_counts_once():
    out = classify(
        line(req="GET /index-all/", status=404),
        line(req="GET /sites/a"),
        line(ip="198.51.100.7", ua=BYTESPIDER, req="GET /index-all/", status=404),
        line(ip="198.51.100.7", ua=BYTESPIDER, req="GET /sites/a"),
    )
    assert out["classes"]["robots_ignorer"]["requests"] == 2
    assert out["classes"]["robots_ignorer"]["honeypot"] == 1
    # A known bot keeps its class; the trap shows as an attribute.
    assert out["classes"]["ai_training"] == {
        "requests": 2,
        "clients": 1,
        "honeypot": 1,
        "unverified": 1,
    }


def test_a_honeypot_prefetch_does_not_trap():
    out = classify(
        line(req="GET /index-all/", status=404, purpose="prefetch"),
        line(req="GET /sites/a"),
    )
    assert out["classes"]["robots_ignorer"]["requests"] == 0
    assert out["classes"]["prefetch"]["requests"] == 1


def test_bots_are_verified_once_per_address_and_impostors_set_apart():
    out = classify(
        line(ip="66.249.66.1", ua=GOOGLEBOT),
        line(ip="66.249.66.1", ua=GOOGLEBOT, req="GET /sites/b"),
        line(ip="47.79.1.1", ua=GOOGLEBOT),
        line(ip="47.79.1.2", ua=CURL),
    )
    assert out["classes"]["search"]["requests"] == 2
    assert out["classes"]["search"]["unverified"] == 0
    assert out["classes"]["impostor"]["requests"] == 1
    assert out["classes"]["self_declared_bot"]["requests"] == 1


def test_datacenter_is_an_attribute_and_top_networks_are_listed(table):
    out = classify(
        line(ip="198.51.100.7"),
        line(ip="198.51.100.7", req="POST /api/pulse"),
        line(ip="203.0.113.9"),
        line(ip="203.0.113.9", req="POST /api/pulse"),
        line(ip="203.0.113.10"),
        table=table,
    )
    assert out["classes"]["browser_js"]["clients"] == 2
    assert out["classes"]["browser_js"]["datacenter"] == 1
    assert out["top_asns"]["browser_js"] == [
        {"asn": 3320, "name": "DTAG", "clients": 1},
        {"asn": 24940, "name": "HETZNER-AS", "clients": 1},
    ]
    assert out["top_asns"]["scraper_nojs"] == [{"asn": 3320, "name": "DTAG", "clients": 1}]
    assert out["asn_as_of"] == table.as_of.isoformat()


def test_without_the_asn_table_the_network_columns_are_absent():
    out = classify(line())
    assert "top_asns" not in out
    assert "datacenter" not in out["classes"]["scraper_nojs"]
    assert out["asn_as_of"] is None


def test_beacon_check_counts_server_rendered_pages_with_javascript_only():
    beacon = "POST /api/pulse"
    pages = ["GET /", "GET /sites/a", "GET /articles/b", "GET /research/c", "GET /news-archive/d"]
    other = ["GET /map.html", "GET /stats.html"]
    lines = []
    for i, req in enumerate(pages + other):
        ip = f"203.0.113.{i + 1}"
        lines += [line(ip=ip, req=req), line(ip=ip, req=beacon)]
    # A search arrival is left out: Google's prefetch proxy fetches the HTML
    # under its own address, so Umami's side leaves search entries out too.
    lines += [
        line(ip="203.0.113.99", req="GET /sites/e", ref="https://www.google.com/"),
        line(ip="203.0.113.99", req=beacon),
        line(ip="203.0.113.98", req="GET /sites/f"),  # no JavaScript
    ]
    out = classify(*lines)
    assert out["beacon_check"] == {"pages_with_js": 5}
    assert out["classes"]["browser_js"]["requests"] == 8


def test_daily_counts_per_utc_day_and_class():
    out = classify(line(), line(at=T0 - timedelta(days=1)), line(ua=CURL))
    assert [(d["day"], d["scraper_nojs"], d["self_declared_bot"]) for d in out["daily"]] == [
        ("2026-10-21", 1, 0),
        ("2026-10-22", 1, 1),
    ]


def test_report_is_none_while_the_log_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(request_log, "LOG_PATH", tmp_path / "requests.log")
    assert request_log.report(RANGES, NOW) is None
    assert "requests.log does not exist yet" in request_log.unavailable_reason()


def test_report_reads_the_family_inside_the_window_and_is_reused(tmp_path, monkeypatch):
    log = tmp_path / "requests.log"
    (tmp_path / "requests.log-20261001.gz").write_bytes(
        gzip.compress((line(at=datetime(2026, 9, 30, 12, tzinfo=UTC)) + "\n").encode())
    )
    # dateyesterday names this file after the 15th, but the timer fired after
    # local midnight: it also holds a line of the 16th, inside the window.
    (tmp_path / "requests.log-20261015").write_text(
        line(at=datetime(2026, 10, 15, 23, tzinfo=UTC))
        + "\n"
        + line(at=datetime(2026, 10, 16, 1, tzinfo=UTC))
        + "\n",
        encoding="utf-8",
    )
    log.write_text(line(ip="203.0.113.2") + "\n", encoding="utf-8")
    monkeypatch.setattr(request_log, "LOG_PATH", log)
    monkeypatch.setattr(request_log, "_files", {})
    monkeypatch.setattr(request_log, "_report", None)
    monkeypatch.setattr(asn, "ASN_DB_PATH", tmp_path / "no-asn.tsv.gz")
    monkeypatch.setattr(asn, "_loaded", None)
    out = request_log.report(RANGES, NOW)
    assert out is not None
    # Seven days back from 2026-10-23 00:00 UTC: the 16th from 00:00 on.
    assert out["classes"]["scraper_nojs"]["requests"] == 2
    assert out["covered_from"] == "2026-10-16T01:00:00+00:00"
    assert request_log.report(RANGES, NOW) is out
    # Other ranges (a new fetch) or a grown log: a new answer.
    assert request_log.report(dict(RANGES), NOW) is not out
    with log.open("a", encoding="utf-8") as fh:
        fh.write(line(ip="203.0.113.3") + "\n")
    assert request_log.report(RANGES, NOW)["classes"]["scraper_nojs"]["requests"] == 3


def test_asn_reason_names_the_missing_table(tmp_path, monkeypatch, table):
    assert request_log.asn_reason() is None
    monkeypatch.setattr(asn, "ASN_DB_PATH", tmp_path / "gone.tsv.gz")
    assert "iptoasn" in request_log.asn_reason()
