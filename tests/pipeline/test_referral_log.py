# SPDX-License-Identifier: AGPL-3.0-only
"""pipeline.referral_log — nginx' Referral-Log, die einzige Sicht auf
Ankünfte, deren Tracker nie lief, und auf den Status, den wir geantwortet
haben.

Dateilos bis auf die Tail-Tests: geprüft werden die Parserregeln (Referer
ohne Schema, utm-Label, eigener Dev-Server, halbe Zeilen) und die Zählregel
des Coverage-Blocks, die auf dem Status beruht und nicht auf dem User-Agent.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from pipeline import referral_log as rl

SINCE = datetime(2026, 9, 17, tzinfo=UTC)
UNTIL = datetime(2026, 9, 24, tzinfo=UTC)
HUMAN = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0 Safari/537.36"
BOT = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
#: Der lauteste Scanner im Live-Log: gefälschter Referer, ganz normaler Chrome.
SCANNER = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/90.0.4430.85 Safari/537.36"


@pytest.fixture(autouse=True)
def _no_cache(monkeypatch):
    """Der Parse-Cache ist ein Modulglobal — er darf nicht zwischen Tests
    durchschlagen."""
    monkeypatch.setattr(rl, "_cache", None)


def _line(
    ref: str,
    req: str,
    ua: str = HUMAN,
    t: str = "2026-09-18T12:00:00+00:00",
    status: int = 200,
) -> str:
    return json.dumps({"t": t, "ref": ref, "req": req, "status": status, "ua": ua})


def _visit(
    host: str = "google.com",
    status: int = 200,
    bot: bool = False,
    page: bool = True,
    at: datetime | None = None,
) -> rl.Visit:
    return rl.Visit(
        at=at or datetime(2026, 9, 18, 12, 0, tzinfo=UTC),
        host=host,
        family=rl.family_of(host),
        status=status,
        bot=bot,
        page=page,
    )


# ---- referrer_host --------------------------------------------------------


def test_referrer_host_reads_a_scheme_less_referer():
    """55 von 407 Live-Zeilen tragen den Host ohne Schema; für die liefert
    urlsplit().hostname None."""
    assert rl.referrer_host("www.google.com", "GET /x") == "google.com"
    assert rl.referrer_host("binance.com/wp-admin/", "GET /x") == "binance.com"


def test_referrer_host_reads_the_utm_source_when_there_is_no_referer():
    assert rl.referrer_host("", "GET /x?utm_source=perplexity") == "perplexity.ai"
    assert rl.referrer_host("", "GET /x?utm_source=discord&utm_medium=bot") == "discord.com"


def test_an_unknown_utm_label_is_kept_as_it_is():
    """Die alte CLI warf ein Label weg, das nicht wie ein Host aussah — eine
    eigene Kampagne war damit unsichtbar."""
    assert rl.referrer_host("", "GET /x?utm_source=newsletter") == "newsletter"


def test_referrer_host_drops_the_port_and_the_www():
    assert rl.referrer_host("http://localhost:5199/globe.html", "GET /api/x") == "localhost"


# ---- parse_lines ----------------------------------------------------------


def test_our_own_dev_server_is_not_a_referral():
    """47 von 407 Live-Zeilen kommen von http://localhost:5199/ — das sind
    wir selbst."""
    assert rl.parse_lines([_line("http://localhost:5199/globe.html", "GET /sites/egypt")]) == []


def test_parse_lines_skips_a_half_line_and_broken_json():
    lines = [
        '9-17T12:00:00+00:00","ref":"https://example.org/","req":"GET /","status":200}',
        "not json{",
        _line("https://example.org/", "GET /"),
    ]
    assert [v.host for v in rl.parse_lines(lines)] == ["example.org"]


def test_parse_lines_keep_the_logged_offset():
    """$time_iso8601 ist VPS-Ortszeit; strptime ohne Offset verschiebt das
    Fenster um zwei Stunden."""
    [visit] = rl.parse_lines(
        [_line("https://example.org/", "GET /", t="2026-09-17T12:00:00+02:00")]
    )
    assert visit.at.astimezone(UTC) == datetime(2026, 9, 17, 10, 0, tzinfo=UTC)


def test_parse_lines_mark_bots_assets_and_the_family():
    lines = [
        _line("https://chatgpt.com/", "GET /sites/egypt"),
        _line("https://www.google.com/", "GET /assets/main-abc.js", ua=BOT),
    ]
    arrival, asset = rl.parse_lines(lines)
    assert (arrival.family, arrival.bot, arrival.page) == ("ai", False, True)
    assert (asset.family, asset.bot, asset.page) == ("search", True, False)


# ---- coverage_report ------------------------------------------------------


def test_coverage_report_counts_only_answered_page_arrivals():
    """Ohne die Statusregel steht binance.com an zweiter Stelle der Hosts und
    21 Scanner-404 stehen unter "Antworten an geworbene Besucher"."""
    out = rl.coverage_report(
        [
            _visit(),
            _visit(bot=True),
            _visit(page=False),
            _visit(status=410),
            _visit(status=404),
            _visit(status=301),
            # Die beiden anderen is_bad_answer-Fälle: der Besucher hat die
            # Verbindung geschlossen, und wir haben uns selbst verschluckt. Das
            # Sources-Panel ist die einzige Oberfläche, die ein 5xx überhaupt
            # sieht — ein 5xx löst kein Umami-Event aus, und das nginx-
            # Access-Log ist für den Deploy-User nicht lesbar.
            _visit(status=499),
            _visit(status=503),
        ],
        SINCE,
        UNTIL,
    )
    assert out["families"][0] == {"family": "search", "visits": 2, "bots": 1}
    assert out["hosts"] == [{"host": "google.com", "visits": 2}]
    assert out["statuses"] == [
        {"status": 410, "visits": 1},
        {"status": 499, "visits": 1},
        {"status": 503, "visits": 1},
    ]
    # Keiner der beiden ist eine Ankunft: sie zählen nur unter "Antworten".
    assert out["unverified"] == 0


def test_coverage_report_counts_a_scanner_out_of_every_list():
    """Der User-Agent kann das nicht: BOT_UA_RE erkannte 1 von 360 Zeilen."""
    [scanner] = rl.parse_lines([_line("binance.com/", "GET /wp-admin/", ua=SCANNER, status=404)])
    assert scanner.bot is False and scanner.page is True
    out = rl.coverage_report([scanner], SINCE, UNTIL)
    assert out["families"] == [] and out["hosts"] == [] and out["statuses"] == []


def test_referrer_spam_answered_200_is_no_arrival():
    """17 der 425 Live-Zeilen (2026-09-19) sind eine SEO-Spam-Kampagne: je ein
    "GET /" pro Wegwerf-Domain, mit dem gleichen Referer-Pfad, mit gefälschtem
    Browser-UA und mit 200 beantwortet. Sie waren die komplette Familie
    "other" und drei der acht Host-Zeilen des Panels. Der Status trennt sie
    nicht — die einmalige Sichtung tut es."""
    spam = [
        _visit(host=f"{name}.store")
        for name in ("seostatschecker", "daparankchecker", "bulkbacklinkanalysis")
    ]
    out = rl.coverage_report(spam, SINCE, UNTIL)
    assert out["families"] == [] and out["hosts"] == []
    assert out["unverified"] == 3


def test_a_host_outside_the_known_families_counts_from_its_second_visit():
    """Die Regel wirft nichts weg, was zweimal kommt: ein echter Verweis von
    einem Blog oder von Hacker News steht ab dem zweiten Besucher da."""
    visits = [_visit(host="news.ycombinator.com") for _ in range(rl.UNKNOWN_HOST_MIN)]
    out = rl.coverage_report(visits, SINCE, UNTIL)
    assert out["hosts"] == [{"host": "news.ycombinator.com", "visits": rl.UNKNOWN_HOST_MIN}]
    assert out["families"] == [
        {"family": rl.OTHER_FAMILY, "visits": rl.UNKNOWN_HOST_MIN, "bots": 0}
    ]
    assert out["unverified"] == 0


@pytest.mark.parametrize(
    "host", ["google.com", "chatgpt.com", "duckduckgo.com", "bing.com", "discord.com"]
)
def test_a_known_family_never_passes_through_the_unknown_host_gate(host):
    """baidu.com, discord.com, gemini.google.com und google.ca hatten im
    Live-Fenster je einen Besuch. Keiner von ihnen darf durch die Spam-Regel
    fallen — sie ist an die Familie gebunden, nicht an die Zahl allein."""
    out = rl.coverage_report([_visit(host=host)], SINCE, UNTIL)
    assert out["hosts"] == [{"host": host, "visits": 1}]
    assert out["unverified"] == 0


def test_coverage_report_windows_the_visits():
    out = rl.coverage_report(
        [
            _visit(at=SINCE - timedelta(hours=1)),
            _visit(at=SINCE + timedelta(days=2)),
            _visit(at=UNTIL),
        ],
        SINCE,
        UNTIL,
    )
    assert out["lines"] == 1
    assert out["covered_from"] == (SINCE + timedelta(days=2)).isoformat()
    assert out["covered_days"] == 5.0


# ---- the file -------------------------------------------------------------


def test_read_visits_returns_none_when_the_log_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(rl, "LOG_PATH", tmp_path / "nothing-here.log")
    assert rl.read_visits() is None
    assert str(rl.LOG_PATH) in rl.unavailable_reason()
    assert "/app/logs:ro" in rl.unavailable_reason()


def test_read_visits_reads_only_the_tail(monkeypatch, tmp_path):
    log = tmp_path / "referrals.log"
    lines = [_line("https://example.org/", f"GET /page-{i}") for i in range(40)]
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    monkeypatch.setattr(rl, "LOG_PATH", log)
    monkeypatch.setattr(rl, "MAX_TAIL_BYTES", 400)
    visits = rl.read_visits()
    # Die halbe erste Zeile am Sprungpunkt darf nicht knallen und nicht zählen.
    assert visits is not None and 0 < len(visits) < 40


def test_read_visits_does_not_reparse_within_the_minimum(monkeypatch, tmp_path):
    log = tmp_path / "referrals.log"
    log.write_text(_line("https://example.org/", "GET /") + "\n", encoding="utf-8")
    monkeypatch.setattr(rl, "LOG_PATH", log)
    parses = []
    real = rl.parse_lines
    monkeypatch.setattr(rl, "parse_lines", lambda lines: parses.append(1) or real(lines))
    first = rl.read_visits()
    log.write_text(_line("https://chatgpt.com/", "GET /") + "\n", encoding="utf-8")
    assert rl.read_visits() == first
    assert len(parses) == 1


# ---- aggregate (the CLI's table) ------------------------------------------


def test_aggregate_counts_errors_only_with_all():
    visits = [_visit(host="binance.com", status=404), _visit(host="binance.com")]
    assert rl.aggregate(visits, SINCE)["other"]["binance.com"] == {"human": 1}
    assert rl.aggregate(visits, SINCE, pages_only=False)["other"]["binance.com"] == {"human": 2}
