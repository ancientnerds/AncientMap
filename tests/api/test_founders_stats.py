# SPDX-License-Identifier: AGPL-3.0-only
"""api.services.founders_stats — Sessions, Mensch-Filter, Sitzungstypen und
Journeys aus Umami-Zeilen. Reine Funktionen, hier mit Fixture-Zeilen in der
Form, die pipeline.umami_db.SQL_SESSION_EVENTS liefert."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from api.services import founders_stats as fs

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
    assert types == {"r": "leser", "e": "entdecker", "f": "forscher", "s": "sucher"}


def test_type_order_is_forscher_entdecker_sucher_leser_sonstige():
    rows = [
        # searched AND opened a site: Entdecker wins over Sucher
        ev("x", path="/globe.html"),
        ev("x", "search", event_type=2, data={"q": "giza", "results": "3"}),
        ev("x", "site_open", event_type=2, data={"site": "1"}, minute=1),
        # story reader who also chatted with Lyra: Forscher wins over Leser
        ev("y", path="/news-archive/x-1"),
        ev("y", "lyra_chat", event_type=2, data={"page": "story"}),
        # globe with filters only: Entdecker; globe alone: Sonstige
        ev("g", path="/globe.html"),
        ev("g", "filter_toggle", event_type=2, data={"filter": "source", "on": "true"}),
        ev("h", path="/globe.html"),
        ev("h", path="/globe.html", minute=1),
    ]
    types = {s.id: s.kind for s in fs.sessions_from_rows(rows)}
    assert types == {"x": "entdecker", "y": "forscher", "g": "entdecker", "h": "sonstige"}


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
    assert fs.session_type_shares(fs.sessions_from_rows(rows)) == {"leser": 1, "entdecker": 1}


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
