# SPDX-License-Identifier: AGPL-3.0-only
"""api.services.founders_stats — Sessions, Mensch-Filter, Sitzungstypen und
Journeys aus Umami-Zeilen. Reine Funktionen, hier mit Fixture-Zeilen in der
Form, die pipeline.umami_db.SQL_SESSION_EVENTS liefert."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pipeline import stats_analysis as fs

T = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)


def ev(
    session,
    name=None,
    path="/",
    event_type=1,
    data=None,
    referrer=None,
    minute=0,
    utm_source=None,
):
    return {
        "session_id": session,
        "created_at": T.replace(minute=minute),
        "event_type": event_type,
        "event_name": name,
        "url_path": path,
        "referrer_domain": referrer,
        "utm_source": utm_source,
        "country": "DE",
        "device": "mobile",
        "data": data or {},
    }


# ---- page_type: mirrors pageType() in src/analytics/index.ts ------------


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/", "home"),
        ("/index.html", "home"),
        ("/globe.html", "globe"),
        ("/news-archive.html", "news-archive"),
        ("/sites", "sites"),
        ("/sites/", "sites"),
        ("/sites/peru", "country"),
        ("/sites/peru/", "country"),
        ("/sites/peru/x-1234abcd", "site"),
        ("/news-archive/", "stories"),
        ("/news-archive/x-1", "story"),
        ("/research/", "papers"),
        ("/research/p", "paper"),
        ("/articles/", "journals"),
        ("/articles/2026-09-01", "journal"),
        ("/sub/page.html", "other"),  # the TS regex only matches top-level names
        ("/Globe.html", "other"),  # ... in lowercase
        ("/privacy", "other"),
        ("", "other"),
    ],
)
def test_page_type_mirrors_the_frontend(path, expected):
    assert fs.page_type(path) == expected


# ---- sessions -------------------------------------------------------------


def test_human_filter_needs_an_interaction_or_a_second_page():
    rows = [
        ev("a", path="/news-archive/x-1"),
        ev("b", path="/globe.html"),
        ev("b", "site_open", event_type=2, data={"site": "1"}),
        ev("c", path="/"),
        ev("c", path="/sites/", minute=1),
    ]
    sessions = fs.sessions_from_rows(rows)
    assert {s.id: s.human for s in sessions} == {"a": False, "b": True, "c": True}


def test_a_site_page_opening_itself_is_not_an_interaction():
    """SitePopup fires site_open on the server-rendered page too, with the page
    type as context. Counting that made every single hit from Google "human"."""
    rows = [
        ev("seo", path="/sites/peru/x-1"),
        ev("seo", "site_open", event_type=2, data={"site": "1", "context": "site"}),
        ev("globe", path="/globe.html"),
        ev("globe", "site_open", event_type=2, data={"site": "1", "context": "globe"}),
        # Two pages stand on their own, whoever opened the site.
        ev("both", path="/sites/peru/x-1"),
        ev("both", "site_open", event_type=2, data={"site": "1", "context": "site"}),
        ev("both", path="/sites/peru/y-2", minute=1),
    ]
    sessions = fs.sessions_from_rows(rows)
    assert {s.id: s.human for s in sessions} == {"seo": False, "globe": True, "both": True}
    # The event itself stays — the session type and the journey still want it.
    assert {s.id: s.events["site_open"] for s in sessions} == {"seo": 1, "globe": 1, "both": 1}


def test_session_types():
    rows = [
        ev("r", path="/news-archive/x-1"),
        ev("r", "scroll_depth", event_type=2, data={"depth": "100"}),
        ev("e", path="/globe.html"),
        ev("e", "site_open", event_type=2, data={"site": "1"}),
        ev("f", path="/research/"),
        ev("f", "paper_open", event_type=2, data={"paper": "/research/p"}),
        ev("s", path="/search.html"),
        ev("s", "search", event_type=2, data={"q": "giza", "results": "0"}),
    ]
    types = {s.id: s.kind for s in fs.sessions_from_rows(rows)}
    assert types == {"r": "reader", "e": "explorer", "f": "researcher", "s": "searcher"}


def test_type_order_is_forscher_entdecker_sucher_leser_sonstige():
    rows = [
        # searched AND opened a site: explorer wins over searcher
        ev("x", path="/globe.html"),
        ev("x", "search", event_type=2, data={"q": "giza", "results": "3"}),
        ev("x", "site_open", event_type=2, data={"site": "1"}, minute=1),
        # story reader who also chatted with Lyra: researcher wins over reader
        ev("y", path="/news-archive/x-1"),
        ev("y", "lyra_chat", event_type=2, data={"page": "story"}),
        # globe with filters only: explorer; globe alone: other
        ev("g", path="/globe.html"),
        ev("g", "filter_toggle", event_type=2, data={"filter": "source", "on": "true"}),
        ev("h", path="/globe.html"),
        ev("h", path="/globe.html", minute=1),
    ]
    types = {s.id: s.kind for s in fs.sessions_from_rows(rows)}
    assert types == {"x": "explorer", "y": "researcher", "g": "explorer", "h": "other"}


def test_sessions_carry_entry_scroll_depth_and_are_ordered_by_start():
    rows = [
        ev("late", path="/", minute=5, referrer="discord.com"),
        ev("early", path="/news-archive/x-1", minute=0, utm_source="youtube"),
        ev("early", "scroll_depth", event_type=2, data={"depth": "50"}, minute=1),
        ev("early", "scroll_depth", event_type=2, data={"depth": "75"}, minute=2),
    ]
    sessions = fs.sessions_from_rows(rows)
    assert [s.id for s in sessions] == ["early", "late"]
    early, late = sessions
    assert early.entry == "youtube"  # utm_source is a website_event column, wins
    assert early.depth == 75 and early.pages == 1
    assert late.entry == "discord.com" and late.country == "DE" and late.device == "mobile"


# ---- journeys and shares --------------------------------------------------


def test_top_journeys_are_page_types_and_actions_not_urls():
    rows = [
        ev("a", path="/news-archive/x-1", referrer="google.com"),
        ev("a", "site_open", event_type=2, data={"site": "1"}, minute=1),
        ev("a", path="/sites/peru/x-1", minute=2),
    ]
    assert fs.journeys(fs.sessions_from_rows(rows))[0] == ("google → story → site_open → site", 1)


def test_journeys_skip_unconfirmed_sessions_and_cap_the_chain():
    rows = [ev("bot", path="/sites/peru/x-1")]  # one page, nothing else
    for i in range(8):
        rows.append(ev("long", path="/", minute=i))
    js = fs.journeys(fs.sessions_from_rows(rows))
    assert js == [("direct → home → home → home → home → home", 1)]  # entry + 5 steps


def test_session_type_shares_count_only_human_sessions():
    rows = [
        ev("a", path="/news-archive/x-1"),  # unconfirmed
        ev("b", path="/news-archive/x-1"),
        ev("b", path="/news-archive/y-2", minute=1),
        ev("c", path="/globe.html"),
        ev("c", "site_open", event_type=2, data={"site": "1"}),
    ]
    assert fs.session_type_shares(fs.sessions_from_rows(rows)) == {"reader": 1, "explorer": 1}


# ---- problems -------------------------------------------------------------

#: Rows in the shape pipeline.umami_db.SQL_NOT_FOUND / SQL_VITALS / SQL_ERRORS return.
NOT_FOUND = [{"path": "/old-story", "referrer": "example.org", "n": 3}]
VITALS = [{"page": "story", "name": "LCP", "p75": 4100.0, "samples": 20}]
ERRORS = [{"message": "x is not a function", "page": "globe", "n": 12, "sessions": 5}]


def _bounce_and_search_rows():
    """Three one-page story sessions that did something of their own (one of
    them scrolled), one crawler-shaped fetch, and one empty search."""
    return [
        ev("a", path="/news-archive/x-1"),
        ev("a", "share", event_type=2, data={"target": "x-1"}),
        ev("b", path="/news-archive/x-1"),
        ev("b", "lyra_chat", event_type=2, data={"page": "story"}),
        ev("c", path="/news-archive/x-1"),
        ev("c", "share", event_type=2, data={"target": "x-1"}),
        ev("c", "scroll_depth", event_type=2, data={"depth": "25"}),
        ev("bot", path="/news-archive/x-1"),  # one page, nothing else
        ev("d", path="/search.html"),
        ev("d", "search", event_type=2, data={"q": "atlantis", "results": "0"}),
        ev("d", "search_empty", event_type=2, data={"chars": "8"}),
    ]


def test_problems_rank_errors_slow_pages_dead_links_bounces_and_empty_searches():
    sessions = fs.sessions_from_rows(_bounce_and_search_rows())
    out = fs.problems(sessions, not_found=NOT_FOUND, vitals=VITALS, errors=ERRORS)
    by_kind = {p["kind"]: p for p in out}
    assert set(by_kind) == {
        "js_error",
        "slow_page",
        "broken_link",
        "shallow_exit",
        "empty_search",
    }
    # Five visitors reached, weighted three — not the twelve times it fired.
    assert by_kind["js_error"]["score"] == 15
    assert by_kind["js_error"]["label"] == "x is not a function"
    assert by_kind["js_error"]["detail"] == "5 visitors, 12× on globe"
    assert by_kind["slow_page"]["score"] == 20  # as many samples as it has
    # The metric is part of the label: one page type can be slow on LCP and INP.
    assert by_kind["slow_page"]["label"] == "story · LCP"
    assert "4100" in by_kind["slow_page"]["detail"]
    assert by_kind["broken_link"]["score"] == 6  # 3 hits, weighted two
    assert by_kind["broken_link"]["label"] == "/old-story"
    assert "example.org" in by_kind["broken_link"]["detail"]
    # a and b; c scrolled to 25 %, and the bare fetch is not a visitor we know.
    assert by_kind["shallow_exit"]["score"] == 2
    assert by_kind["empty_search"]["score"] == 1
    # Worst first, and every entry carries the four keys the panel renders.
    assert [p["score"] for p in out] == sorted((p["score"] for p in out), reverse=True)
    assert all(set(p) == {"kind", "label", "score", "detail"} for p in out)


def test_problems_are_empty_without_findings():
    assert fs.problems([], not_found=[], vitals=[], errors=[]) == []


@pytest.mark.parametrize(
    ("name", "p75", "slow"),
    [
        ("LCP", 2501, True),
        ("LCP", 2500, False),
        ("INP", 201, True),
        ("INP", 200, False),
        ("CLS", 900, False),  # a share, not milliseconds — no threshold, no line
    ],
)
def test_slow_page_uses_the_core_web_vitals_thresholds(name, p75, slow):
    rows = [{"page": "site", "name": name, "p75": p75, "samples": 12}]
    kinds = [p["kind"] for p in fs.problems([], not_found=[], vitals=rows, errors=[])]
    assert ("slow_page" in kinds) is slow


def test_a_percentile_out_of_a_handful_of_loads_is_not_a_slow_page():
    """radar showed "p75 4717 ms" from three measurements on 2026-09-19 — one
    visitor's phone, ranked above real defects."""
    over = {"page": "radar", "name": "LCP", "p75": 4717.0}
    few = [{**over, "samples": fs.VITAL_MIN_SAMPLES - 1}]
    enough = [{**over, "samples": fs.VITAL_MIN_SAMPLES}]
    assert fs.problems([], not_found=[], vitals=few, errors=[]) == []
    assert [p["kind"] for p in fs.problems([], not_found=[], vitals=enough, errors=[])] == [
        "slow_page"
    ]


def test_a_single_dead_hit_is_noise_not_a_broken_link():
    rows = [{"path": "/typo", "referrer": "direkt", "n": 1}]
    assert fs.problems([], not_found=rows, vitals=[], errors=[]) == []


def test_shallow_exit_counts_only_visitors_we_can_tell_from_a_crawler():
    rows = [
        ev("read", path="/news-archive/x-1"),
        ev("read", path="/news-archive/y-2", minute=1),  # two pages: not an exit
        ev("deep", path="/sites/peru/x-1"),
        ev("deep", "site_open", event_type=2, data={"context": "globe"}),
        ev("deep", "scroll_depth", event_type=2, data={"depth": "75"}),
        ev("gone", path="/sites/peru/x-1"),
        ev("gone", "share", event_type=2, data={"target": "x-1"}),
        ev("home", path="/"),  # home is neither story nor site
        ev("home", "search", event_type=2, data={"q": "giza", "results": "3"}),
        ev("bounce1", path="/news-archive/x-1"),
        ev("bounce1", "share", event_type=2, data={"target": "x-1"}),
        ev("bounce2", path="/news-archive/x-1"),  # nothing but the fetch
        ev("seo", path="/sites/peru/x-1"),
        ev("seo", "site_open", event_type=2, data={"context": "site"}),  # the page itself
    ]
    out = fs.problems(fs.sessions_from_rows(rows), not_found=[], vitals=[], errors=[])
    exits = {p["label"]: p["score"] for p in out if p["kind"] == "shallow_exit"}
    assert exits == {"story": 1, "site": 1}


def test_problems_are_capped():
    errors = [
        {"message": f"e{i}", "page": "globe", "n": 30 - i, "sessions": 30 - i} for i in range(20)
    ]
    assert len(fs.problems([], not_found=[], vitals=[], errors=errors, limit=5)) == 5


# ---- source_family --------------------------------------------------------


@pytest.mark.parametrize(
    ("referrer", "utm", "expected"),
    [
        (None, None, "direct"),
        ("", None, "direct"),
        ("www.google.com", None, "google"),
        ("google.co.uk", None, "google"),
        ("duckduckgo.com", None, "search"),
        ("chatgpt.com", None, "ai"),
        ("www.perplexity.ai", None, "ai"),
        ("www.reddit.com", None, "reddit.com"),
        ("discord.com", "youtube", "youtube"),
    ],
)
def test_source_family(referrer, utm, expected):
    assert fs.source_family(referrer, utm) == expected
