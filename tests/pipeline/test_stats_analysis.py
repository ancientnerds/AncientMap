# SPDX-License-Identifier: AGPL-3.0-only
"""pipeline.stats_analysis — Sessions, Mensch-Filter, Sitzungstypen und
Journeys aus Umami-Zeilen. Reine Funktionen, hier mit Fixture-Zeilen in der
Form, die pipeline.umami_db.SQL_SESSION_EVENTS liefert."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

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


# ---- countries ------------------------------------------------------------


def test_countries_rank_by_sessions_and_keep_only_humans():
    rows = [
        ev("de1", path="/news-archive/x-1"),
        ev("de1", path="/news-archive/y-2", minute=1),
        ev("de2", path="/globe.html"),
        ev("de2", "search", event_type=2, data={"q": "giza", "results": "3"}),
        ev("us", path="/news-archive/x-1"),
        ev("us", path="/news-archive/y-2", minute=1),
        ev("bot", path="/news-archive/x-1"),  # one page, nothing else
    ]
    for r in rows:
        r["country"] = {"de1": "DE", "de2": "DE", "us": "US", "bot": "SG"}[r["session_id"]]
    sessions = fs.sessions_from_rows(rows)
    assert fs.countries(sessions) == [
        {"country": "DE", "sessions": 2},
        {"country": "US", "sessions": 1},
    ]
    # The live tile counts everybody: nobody has acted thirty seconds in.
    assert fs.countries(sessions, human_only=False) == [
        {"country": "DE", "sessions": 2},
        {"country": "SG", "sessions": 1},
        {"country": "US", "sessions": 1},
    ]


def test_countries_slice_by_the_last_sign_of_life_not_by_arrival():
    """One fetch feeds four windows: a session that started before the cut but
    is still clicking belongs to "now"."""
    rows = [
        ev("staying", path="/globe.html", minute=0),
        ev("staying", "search", event_type=2, data={"q": "x", "results": "1"}, minute=50),
        ev("gone", path="/globe.html", minute=0),
        ev("gone", "search", event_type=2, data={"q": "y", "results": "1"}, minute=5),
    ]
    sessions = fs.sessions_from_rows(rows)
    for s in sessions:
        s.country = "DE"
    recent = fs.countries(sessions, since=T.replace(minute=45))
    assert recent == [{"country": "DE", "sessions": 1}]
    assert fs.countries(sessions, since=None) == [{"country": "DE", "sessions": 2}]


def test_a_country_umami_could_not_place_still_counts():
    rows = [
        ev("a", path="/"),
        ev("a", path="/globe.html", minute=1),
    ]
    rows[0]["country"] = rows[1]["country"] = None
    assert fs.countries(fs.sessions_from_rows(rows)) == [
        {"country": fs.UNKNOWN_COUNTRY, "sessions": 1}
    ]


# ---- problems -------------------------------------------------------------

#: Rows in the shape pipeline.umami_db.SQL_NOT_FOUND / SQL_VITALS / SQL_ERRORS return.
#: `last_*` are the columns every problem query adds so the panel can say when
#: it happened and to whom.
LAST = {
    "last_at": T.replace(minute=30),
    "last_session": "cf01aa30-7c4d-4b5b-ae73-9cf41c550e9c",
    "last_country": "CH",
    "last_device": "laptop",
    "last_browser": "chrome",
}
NOT_FOUND = [{"path": "/old-story", "referrer": "example.org", "n": 3, "sessions": 2, **LAST}]
VITALS = [
    {"page": "story", "name": "LCP", "p75": 4100.0, "samples": 20, "sessions": 16, **LAST}
]
ERRORS = [{"message": "x is not a function", "page": "globe", "n": 12, "sessions": 5, **LAST}]


def _bounce_and_search_rows():
    """Three one-page story sessions that did something of their own (one of
    them scrolled), one crawler-shaped fetch, and one empty search.

    The act is `filter_toggle` and not `share`: sharing a page is engagement,
    and a session that shows engagement is not counted as a bounce (see
    fs.ENGAGEMENTS and the test below it)."""
    return [
        ev("a", path="/news-archive/x-1"),
        ev("a", "filter_toggle", event_type=2, data={"filter": "type"}),
        ev("b", path="/news-archive/x-1"),
        ev("b", "search", event_type=2, data={"q": "giza", "results": "3"}),
        ev("c", path="/news-archive/x-1"),
        ev("c", "filter_toggle", event_type=2, data={"filter": "type"}),
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
    # 16 visitors × 4100 ms against the 2500 ms budget: the visitors it reached,
    # weighted by how far past the budget the page is.
    assert by_kind["slow_page"]["score"] == 26
    # The metric is part of the label: one page type can be slow on LCP and INP.
    assert by_kind["slow_page"]["label"] == "story · LCP"
    assert "4100" in by_kind["slow_page"]["detail"]
    assert by_kind["broken_link"]["score"] == 4  # 2 visitors, weighted two
    assert by_kind["broken_link"]["label"] == "/old-story"
    assert "example.org" in by_kind["broken_link"]["detail"]
    # a and b; c scrolled to 25 %, and the bare fetch is not a visitor we know.
    assert by_kind["shallow_exit"]["score"] == 2
    assert by_kind["shallow_exit"]["detail"].startswith("2 visitors read one page")
    assert by_kind["empty_search"]["score"] == 1
    # Worst first, and every entry carries the six keys the panel renders.
    assert [p["score"] for p in out] == sorted((p["score"] for p in out), reverse=True)
    assert all(set(p) == {"kind", "label", "score", "detail", "at", "last"} for p in out)


def test_every_problem_says_when_it_happened_and_to_whom():
    """The founders' first two questions about any row (owner, 2026-09-19).
    There is no user in cookieless analytics — the visitor is the session."""
    sessions = fs.sessions_from_rows(_bounce_and_search_rows())
    for s in sessions:
        s.country, s.device, s.browser = "PH", "mobile", "ios"
    out = fs.problems(sessions, not_found=NOT_FOUND, vitals=VITALS, errors=ERRORS)
    by_kind = {p["kind"]: p for p in out}
    for kind in ("js_error", "slow_page", "broken_link"):
        assert by_kind[kind]["at"] == LAST["last_at"], kind
        assert by_kind[kind]["last"] == {
            "session": "cf01aa30",  # eight characters, not the whole id
            "country": "CH",
            "device": "laptop",
            "browser": "chrome",
        }, kind
    # The bounce names the session it was folded from, and its last event.
    bounce = by_kind["shallow_exit"]
    assert bounce["last"]["country"] == "PH" and bounce["last"]["browser"] == "ios"
    assert bounce["at"] is not None
    # A row without the columns says so instead of inventing a visitor.
    bare = fs.problems([], not_found=[], vitals=[], errors=[{"message": "m", "page": "p", "n": 1, "sessions": 1}])  # fmt: skip
    assert bare[0]["at"] is None and bare[0]["last"] is None


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
    rows = [{"page": "site", "name": name, "p75": p75, "samples": 12, "sessions": 10}]
    kinds = [p["kind"] for p in fs.problems([], not_found=[], vitals=rows, errors=[])]
    assert ("slow_page" in kinds) is slow


def test_a_page_barely_over_budget_never_outranks_a_worse_one_with_more_traffic():
    """The live seven-day window on 2026-09-19, straight out of SQL_VITALS.

    story · LCP misses the 2500 ms budget by 24 ms (0.96 %) and is the
    most-visited page type; globe · INP is 4.6× its budget. Scored by the
    measurement count, story took the top row of the panel and of the weekly
    digest, globe came second, and a WebGL failure that ended somebody's visit
    came seventh."""
    vitals = [
        {"page": "story", "name": "LCP", "p75": 2524.0, "samples": 35, "sessions": 28},
        {"page": "globe", "name": "INP", "p75": 800.0, "samples": 19, "sessions": 13},
        {"page": "country", "name": "LCP", "p75": 2760.0, "samples": 17, "sessions": 17},
    ]
    out = fs.problems([], not_found=[], vitals=vitals, errors=[])
    assert [p["label"] for p in out] == ["globe · INP", "story · LCP", "country · LCP"]
    assert [p["score"] for p in out] == [52, 28, 19]


def test_one_visitor_reloading_a_dead_link_is_one_broken_link():
    """The score is people, like every other kind on the panel — `n` stays in
    the sentence the panel prints, because that is a view count."""
    rows = [{"path": "/old", "referrer": "reddit.com", "n": 10, "sessions": 1}]
    out = fs.problems([], not_found=rows, vitals=[], errors=[])
    assert out[0]["score"] == 2
    assert out[0]["detail"] == "10 views into nothing, from reddit.com"


def test_a_percentile_out_of_a_handful_of_loads_is_not_a_slow_page():
    """radar showed "p75 4717 ms" from three measurements on 2026-09-19 — one
    visitor's phone, ranked above real defects. The gate reads the number of
    measurements, not the number of visitors: a percentile needs samples."""
    over = {"page": "radar", "name": "LCP", "p75": 4717.0, "sessions": 3}
    few = [{**over, "samples": 3}]
    enough = [{**over, "samples": 12}]
    assert fs.VITAL_MIN_SAMPLES == 10
    assert fs.problems([], not_found=[], vitals=few, errors=[]) == []
    assert [p["kind"] for p in fs.problems([], not_found=[], vitals=enough, errors=[])] == [
        "slow_page"
    ]


def test_a_single_dead_hit_is_noise_not_a_broken_link():
    rows = [{"path": "/typo", "referrer": "direkt", "n": 1, "sessions": 1}]
    assert fs.problems([], not_found=rows, vitals=[], errors=[]) == []


def test_shallow_exit_counts_only_visitors_we_can_tell_from_a_crawler():
    rows = [
        ev("read", path="/news-archive/x-1"),
        ev("read", path="/news-archive/y-2", minute=1),  # two pages: not an exit
        ev("deep", path="/sites/peru/x-1"),
        ev("deep", "site_open", event_type=2, data={"context": "globe"}),
        ev("deep", "scroll_depth", event_type=2, data={"depth": "75"}),
        ev("gone", path="/sites/peru/x-1"),
        ev("gone", "filter_toggle", event_type=2, data={"filter": "type"}),
        ev("home", path="/"),  # home is neither story nor site
        ev("home", "search", event_type=2, data={"q": "giza", "results": "3"}),
        ev("bounce1", path="/news-archive/x-1"),
        ev("bounce1", "filter_toggle", event_type=2, data={"filter": "type"}),
        ev("bounce2", path="/news-archive/x-1"),  # nothing but the fetch
        ev("seo", path="/sites/peru/x-1"),
        ev("seo", "site_open", event_type=2, data={"context": "site"}),  # the page itself
    ]
    out = fs.problems(fs.sessions_from_rows(rows), not_found=[], vitals=[], errors=[])
    exits = {p["label"]: p["score"] for p in out if p["kind"] == "shallow_exit"}
    assert exits == {"story": 1, "site": 1}
    # Singular where it is one — the panel prints these details verbatim.
    assert all("1 visitor read" in p["detail"] for p in out if p["kind"] == "shallow_exit")


def test_a_visitor_who_played_the_video_or_clicked_out_is_not_a_bounce():
    """The five sessions this test caught on 2026-09-19 were the week's most
    engaged: all five played the embedded video, four of them then clicked
    through to youtube.com — and the panel called them "read one page, under
    25 % scrolled" while the Paths panel counted the same clicks as links out
    of the site. A scroll mark is not the only sign that a page was used."""
    rows = [
        ev("watched", path="/news-archive/x-1"),
        ev("watched", "media_play", event_type=2, data={"id": "yt-1"}),
        ev("watched", "outbound_click", event_type=2, data={"host": "youtube.com"}),
        ev("shared", path="/sites/peru/x-1"),
        ev("shared", "share", event_type=2, data={"target": "x-1"}),
        ev("rated", path="/news-archive/y-2"),
        ev("rated", "feedback", event_type=2, data={"answer": "yes"}),
        ev("asked", path="/news-archive/z-3"),
        ev("asked", "lyra_chat", event_type=2, data={"page": "story"}),
        # The one shape that is still a bounce: a human act that says nothing
        # about the page they were on, and no scroll.
        ev("left", path="/news-archive/x-1"),
        ev("left", "filter_toggle", event_type=2, data={"filter": "type"}),
    ]
    out = fs.problems(fs.sessions_from_rows(rows), not_found=[], vitals=[], errors=[])
    exits = {p["label"]: p["score"] for p in out if p["kind"] == "shallow_exit"}
    assert exits == {"story": 1}
    assert exits["story"] == 1  # only "left", none of the four engaged ones


def test_a_click_off_the_site_is_a_person():
    """boot.ts fires outbound_click and discord_click from a click handler and
    from nowhere else. Left out of INTERACTIONS, the one live session that
    opened a story and followed a link off the site (2026-09-19) counted as
    "may be a bot" on the pulse strip, in the country tiles and in every
    human total on the page."""
    rows = [
        ev("out", path="/news-archive/x-1"),
        ev("out", "outbound_click", event_type=2, data={"host": "youtube.com"}),
        ev("dc", path="/"),
        ev("dc", "discord_click", event_type=2, data={"src": "landing"}),
    ]
    assert {s.id: s.human for s in fs.sessions_from_rows(rows)} == {"out": True, "dc": True}
    # Every engagement is an interaction; the reverse does not hold.
    assert set(fs.ENGAGEMENTS) <= fs.INTERACTIONS


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


# ---- is_ai_entry ----------------------------------------------------------


def test_is_ai_entry_reads_both_columns_and_both_vocabularies():
    """Die beiden Spalten sprechen zwei Vokabulare: der Referrer einen Host,
    das utm einen Host ODER ein nacktes Label. Eine Regel nur gegen AI_HOSTS
    findet eine der dreizehn Live-Sessions."""
    assert fs.is_ai_entry(None, "chatgpt.com")
    assert fs.is_ai_entry(None, "perplexity")
    assert fs.is_ai_entry("gemini.google.com")
    assert not fs.is_ai_entry(None, "youtube")
    assert not fs.is_ai_entry("google.com")


def test_source_family_buckets_a_bare_utm_label_as_ai():
    # Ein Argument, positional: so ruft /sources die Funktion auf.
    assert fs.source_family("perplexity") == "ai"
    assert fs.source_family(None, "chatgpt.com") == "ai"
    assert fs.source_family(None, "youtube") == "youtube"
    assert fs.source_family("google.com") == "google"


# ---- pages, page_steps, human ---------------------------------------------


def test_a_session_without_a_page_view_is_not_human():
    """Acht Live-Sessions am 2026-09-19 hatten genau ein scroll_depth und
    keinen einzigen Seitenaufruf - alle acht in den zwei Fingerabdruecken, die
    /clusters als eine Maschine ausweist."""
    ghost = fs.sessions_from_rows([ev("g", "scroll_depth", event_type=2, data={"depth": "50"})])
    assert ghost[0].human is False
    with_page = fs.sessions_from_rows(
        [
            ev("g", path="/news-archive/x-1"),
            ev("g", "scroll_depth", event_type=2, data={"depth": "50"}),
        ]
    )
    assert with_page[0].human is True


def test_pages_is_the_length_of_page_steps():
    rows = [
        ev("a", path="/news-archive/x-1"),
        ev("a", path="/sites/peru/x-1", minute=1),
    ]
    s = fs.sessions_from_rows(rows)[0]
    assert s.pages == 2 == len(s.page_steps)
    assert s.page_steps == ["story", "site"]
    with pytest.raises(AttributeError):
        s.pages = 3


def test_page_steps_keep_only_pages_while_steps_interleave_events():
    """Deshalb gibt es beide Listen: "search" ist ein Ereignisname UND der
    Seitentyp von /search.html."""
    rows = [
        ev("s", path="/search.html"),
        ev("s", "search", event_type=2, data={"q": "giza", "results": "3"}),
    ]
    s = fs.sessions_from_rows(rows)[0]
    assert s.page_steps == ["search"]
    assert s.steps == ["search", "search"]


# ---- hourly_sessions ------------------------------------------------------


def test_hourly_sessions_draws_every_hour_even_the_empty_ones():
    until = T.replace(hour=12, minute=30)
    rows = [
        ev("a", path="/", minute=0),
        {**ev("b", path="/"), "created_at": T.replace(hour=10)},
    ]
    out = fs.hourly_sessions(rows, fs.sessions_from_rows(rows), until, hours=3)
    assert len(out) == 3
    assert [r["hour"] for r in out] == [
        T.replace(hour=10, minute=0),
        T.replace(hour=11, minute=0),
        T.replace(hour=12, minute=0),
    ]
    assert out[1] == {"hour": T.replace(hour=11, minute=0), "sessions": 0, "human": 0, "ai": 0}
    assert out[2]["sessions"] == 1


def test_hourly_sessions_splits_human_from_the_rest_and_counts_ai_separately():
    rows = [
        ev("human", path="/news-archive/x-1"),
        ev("human", path="/news-archive/y-2", minute=1),
        ev("quiet", path="/news-archive/z-3"),
        ev("ai", path="/news-archive/x-1", utm_source="chatgpt.com"),
        ev("ai", path="/news-archive/y-2", minute=1, utm_source="chatgpt.com"),
    ]
    out = fs.hourly_sessions(rows, fs.sessions_from_rows(rows), T.replace(minute=59), hours=1)
    assert out == [{"hour": T.replace(minute=0), "sessions": 3, "human": 2, "ai": 1}]


def test_hourly_sessions_ignores_rows_outside_the_strip():
    rows = [ev("a", path="/")]
    old = {**ev("old", path="/"), "created_at": T.replace(hour=0) - timedelta(hours=100)}
    sessions = fs.sessions_from_rows(rows + [old])
    out = fs.hourly_sessions(rows + [old], sessions, T.replace(minute=59), hours=2)
    assert sum(r["sessions"] for r in out) == 1


# ---- globe ----------------------------------------------------------------


#: The first ending event on /globe.html (SQL_GLOBE's endings_since) and a
#: session that started after it: every default row is a measured one.
ENDINGS_SINCE = T - timedelta(days=3)


def _globe_row(
    session="a",
    views=1,
    ready=0,
    ready_ms=(),
    *,
    gate_left=0,
    gate_quit=0,
    unsupported=0,
    failed=0,
    context_lost=0,
    abandoned=0,
    abandon_ms=(),
    first_view=T,
    endings_since=ENDINGS_SINCE,
):
    return {
        "session_id": session,
        "views": views,
        "ready": ready,
        "ready_ms": list(ready_ms),
        "gate_left": gate_left,
        "gate_quit": gate_quit,
        "unsupported": unsupported,
        "failed": failed,
        "context_lost": context_lost,
        "abandoned": abandoned,
        "abandon_ms": list(abandon_ms),
        "first_view": first_view,
        "endings_since": endings_since,
    }


def test_globe_funnel_counts_loads_and_reaches():
    out = fs.globe_funnel(
        [
            _globe_row("a", views=3, ready=1, ready_ms=[9450.0]),
            _globe_row("b", views=1, ready=0),
            _globe_row("empty", views=0, ready=0),
        ]
    )
    assert (out["loads"], out["reached"], out["gave_up"]) == (4, 1, 3)
    assert out["sessions"] == {"all": 2, "reached": 1}
    # Ein globe_ready kann nach dem Fensterrand ankommen: nie mehr Erfolge
    # als Aufrufe.
    capped = fs.globe_funnel([_globe_row("c", views=1, ready=2, ready_ms=[10.0, 20.0])])
    assert capped["reached"] == 1 and capped["loads"] == 1


def test_globe_funnel_hides_the_middle_below_the_sample_floor():
    few = [_globe_row(ready_ms=[float(i) for i in range(fs.GLOBE_MIN_SAMPLES - 1)], ready=4)]
    out = fs.globe_funnel(few)
    assert out["ready_ms"]["median"] is None
    assert out["ready_ms"]["min"] == 0.0 and out["ready_ms"]["max"] == 3.0
    assert out["ready_ms"]["samples"] == fs.GLOBE_MIN_SAMPLES - 1
    enough = [_globe_row(ready_ms=[float(i) for i in range(fs.GLOBE_MIN_SAMPLES)], ready=5)]
    assert fs.globe_funnel(enough)["ready_ms"]["median"] == 2.0


def test_globe_funnel_keeps_its_ready_times_exactly():
    """The spread helper the abandon times share must not move a single value
    of the times the panel prints today: upper-middle median, uncapped
    samples, floats."""
    rows = [
        _globe_row("a", views=2, ready=3, ready_ms=[19917.0, 9450.0, 80383.0]),
        _globe_row("b", views=4, ready=2, ready_ms=[12000.0, 30000.0]),
    ]
    assert fs.globe_funnel(rows)["ready_ms"] == {
        "min": 9450.0,
        "median": 19917.0,
        "max": 80383.0,
        "samples": 5,
    }


def test_globe_funnel_splits_every_unreached_load_exactly_once():
    rows = [
        _globe_row("gate", views=1, gate_left=1),
        _globe_row("nogl", views=2, unsupported=2),
        _globe_row("err", views=1, failed=1),
        _globe_row("gone", views=3, ready=1, ready_ms=[9000.0], abandoned=1, abandon_ms=[4200.0]),
        _globe_row("quiet", views=2),
        _globe_row("fine", views=1, ready=1, ready_ms=[8000.0]),
    ]
    out = fs.globe_funnel(rows)
    assert out["not_reached"] == {
        "gate": 1,
        "unsupported": 2,
        "error": 1,
        "abandoned": 1,
        "no_signal": 3,
        "unmeasured": 0,
    }
    assert sum(out["not_reached"].values()) == out["gave_up"] == 8
    # The totals the panel printed before the split are untouched.
    assert (out["loads"], out["reached"]) == (10, 2)


def test_globe_funnel_caps_the_endings_at_the_unreached_loads_in_their_order():
    """Umami has no page-load id, so a session with more endings than
    unreached loads is resolved in the order a load meets them: phone gate,
    capability check, start, the visitor leaving."""
    row = _globe_row(
        "many",
        views=2,
        gate_left=1,
        unsupported=1,
        failed=1,
        abandoned=1,
        abandon_ms=[3000.0],
    )
    out = fs.globe_funnel([row])
    assert out["not_reached"] == {
        "gate": 1,
        "unsupported": 1,
        "error": 0,
        "abandoned": 0,
        "no_signal": 0,
        "unmeasured": 0,
    }
    # The abandon that no load was left for is no measurement either.
    assert out["abandon_ms"]["samples"] == 0


def test_globe_funnel_counts_leaving_the_phone_gate_as_the_gate():
    out = fs.globe_funnel([_globe_row("g", views=1, gate_quit=1)])
    assert out["not_reached"]["gate"] == 1 and out["not_reached"]["abandoned"] == 0


def test_globe_funnel_counts_a_context_lost_while_loading_as_an_error():
    """webgl_lost{phase:'loading'} is a start failure the globe reported long
    before globe_error existed; as "no signal" it would read as a crash."""
    out = fs.globe_funnel([_globe_row("ctx", views=2, context_lost=1, failed=1)])
    assert out["not_reached"]["error"] == 2 and out["not_reached"]["no_signal"] == 0


def test_globe_funnel_drops_the_abandon_time_of_a_load_that_arrived():
    """visibilitychange->hidden is not always leaving: a tab switched away and
    back can send globe_abandon and then globe_ready. The ready wins through
    the cap, and `xs[-0:]` would otherwise hand back the whole list."""
    out = fs.globe_funnel(
        [_globe_row("back", views=1, ready=1, ready_ms=[20000.0], abandoned=1, abandon_ms=[5000.0])]
    )
    assert out["not_reached"]["abandoned"] == 0
    assert out["abandon_ms"] == {"min": None, "median": None, "max": None, "samples": 0}


def test_globe_funnel_keeps_the_latest_abandon_times_it_counts():
    out = fs.globe_funnel(
        [
            _globe_row(
                "two", views=2, ready=1, ready_ms=[9000.0], abandoned=2, abandon_ms=[1000.0, 7000.0]
            )
        ]
    )
    assert out["not_reached"]["abandoned"] == 1
    assert out["abandon_ms"]["min"] == 7000.0 and out["abandon_ms"]["samples"] == 1


def test_globe_funnel_hides_the_abandon_middle_below_the_sample_floor():
    def rows(n):
        return [
            _globe_row(f"s{i}", views=1, abandoned=1, abandon_ms=[1000.0 * (i + 1)])
            for i in range(n)
        ]

    few = fs.globe_funnel(rows(fs.GLOBE_MIN_SAMPLES - 1))["abandon_ms"]
    assert few["median"] is None and few["min"] == 1000.0 and few["max"] == 4000.0
    assert few["samples"] == fs.GLOBE_MIN_SAMPLES - 1
    enough = fs.globe_funnel(rows(fs.GLOBE_MIN_SAMPLES))["abandon_ms"]
    assert enough["median"] == 3000.0 and enough["samples"] == fs.GLOBE_MIN_SAMPLES


def test_globe_funnel_does_not_call_loads_before_the_endings_existed_no_signal():
    """A load before the instrumentation went live carries none of the ending
    events. As "no signal" it would read as the crash signature for as long as
    the window reaches back, exactly in the weeks the change is judged."""
    before = T - timedelta(days=5)
    rows = [
        _globe_row("old", views=3, ready=1, ready_ms=[9000.0], first_view=before),
        _globe_row("new", views=1),
    ]
    out = fs.globe_funnel(rows)
    assert out["not_reached"]["unmeasured"] == 2
    assert out["not_reached"]["no_signal"] == 1
    assert sum(out["not_reached"].values()) == out["gave_up"]


def test_globe_funnel_still_counts_the_endings_of_the_session_that_sent_the_first():
    """The very first ending ever recorded belongs to a session whose page
    view came a few seconds earlier - that session is instrumented, and its
    ending counts. Only what would otherwise be "no signal" is unmeasured."""
    first = ENDINGS_SINCE
    row = _globe_row(
        "first",
        views=2,
        gate_left=1,
        first_view=first - timedelta(seconds=4),
        endings_since=first,
    )
    out = fs.globe_funnel([row])
    assert out["not_reached"]["gate"] == 1
    assert out["not_reached"]["unmeasured"] == 1 and out["not_reached"]["no_signal"] == 0


def test_globe_funnel_calls_everything_unmeasured_before_any_ending_was_sent():
    out = fs.globe_funnel([_globe_row("a", views=2, endings_since=None)])
    assert out["not_reached"]["unmeasured"] == 2 and out["not_reached"]["no_signal"] == 0


# ---- clusters -------------------------------------------------------------


def test_clusters_report_the_flagged_total_and_the_fingerprints():
    """Gemessen am 2026-09-19: 1366x1366 chrome Mac OS 22 und 1280x1200
    chrome Windows 10 16 - zusammen 38 von 163 Sessions."""
    rows = [
        {"screen": "1366x1366", "browser": "chrome", "os": "Mac OS", "sessions": 22},
        {"screen": "1280x1200", "browser": "chrome", "os": "Windows 10", "sessions": 16},
    ]
    out = fs.clusters(rows, min_ids=3)
    assert out["flagged"] == 38 and out["min_ids"] == 3
    assert out["clusters"][0] == rows[0]
    # Keine Sitzungssumme: die holt das Panel aus /overview.
    assert set(out) == {"min_ids", "flagged", "clusters"}


# ---- entries, exits, outbound ---------------------------------------------


def test_entry_exit_pages_count_landings_stops_and_one_page_sessions():
    rows = [
        ev("moves", path="/news-archive/x-1"),
        ev("moves", path="/sites/peru/x-1", minute=1),
        ev("stops", path="/news-archive/y-2"),
        ev("stops", "share", event_type=2, data={"target": "y-2"}),
    ]
    out = fs.entry_exit_pages(fs.sessions_from_rows(rows))
    assert (out["sessions"], out["one_page"], out["moving"]) == (2, 1, 1)
    assert out["entries"][0] == {"page": "story", "sessions": 2, "stopped": 1}
    assert out["exits"][0] == {"page": "site", "sessions": 1, "views": 1}
    # Nur Seitentypen, keine Ereignisnamen - dafuer gibt es page_steps.
    assert [r["page"] for r in out["exits"]] == ["site", "story"]
    # Kein `no_page`: seit 9d ist eine Session ohne Seitenaufruf nicht human,
    # die Zahl waere fuer immer 0 von 46.
    assert "no_page" not in out


def test_entry_exit_pages_ignore_sessions_that_are_not_human():
    rows = [
        ev("real", path="/news-archive/x-1"),
        ev("real", path="/news-archive/y-2", minute=1),
        ev("bare", path="/news-archive/z-3"),
        ev("ghost", "scroll_depth", event_type=2, data={"depth": "100"}),
    ]
    out = fs.entry_exit_pages(fs.sessions_from_rows(rows))
    assert out["sessions"] == 1
    assert [r["page"] for r in out["entries"]] == ["story"]


def test_outbound_links_fold_from_the_session_rows():
    rows = [
        ev("a", "outbound_click", event_type=2, data={"host": "youtube.com"}),
        ev("a", "outbound_click", event_type=2, data={"host": "youtube.com"}, minute=1),
        ev("b", "outbound_click", event_type=2, data={"host": "youtube.com"}),
    ]
    assert fs.outbound_links(rows) == [{"host": "youtube.com", "clicks": 3, "visitors": 2}]


def test_outbound_links_fail_loudly_on_drift():
    """boot.ts feuert das Ereignis erst, wenn outboundHost() einen Host
    geliefert hat - eine Zeile ohne Host ist SQL-Drift und darf nicht still
    verschwinden."""
    no_data = [{**ev("a", "outbound_click", event_type=2), "data": None}]
    with pytest.raises(TypeError):
        fs.outbound_links(no_data)
    with pytest.raises(KeyError):
        fs.outbound_links([ev("a", "outbound_click", event_type=2, data={})])


# ---- the live panel's row -------------------------------------------------


def test_without_brand_keeps_a_title_that_carries_no_brand():
    assert fs.without_brand("Goebekli Tepe | Ancient Nerds") == "Goebekli Tepe"
    # Eine von zwei Live-Ueberschriften, die nicht auf die Marke enden.
    assert fs.without_brand("Database - Ancient Nerds") == "Database - Ancient Nerds"
    assert fs.without_brand("Sun | Moon | Ancient Nerds") == "Sun | Moon"


def test_live_row_uses_the_same_visitor_shape_and_id_rule():
    now = T.replace(minute=30)
    row = {
        "session": "cf01aa30-7c4d-4b5b-ae73-9cf41c550e9c",
        "last_seen": T.replace(minute=29),
        "page_since": T.replace(minute=20),
        "url_path": "/sites/peru/x-1",
        "title": "Machu Picchu | Ancient Nerds",
        "country": "CH",
        "device": "laptop",
        "browser": "chrome",
    }
    out = fs.live_row(row, now)
    same = fs._last_visitor(
        {
            "last_session": row["session"],
            "last_country": row["country"],
            "last_device": row["device"],
            "last_browser": row["browser"],
        }
    )
    assert {k: out[k] for k in ("session", "country", "device", "browser")} == same
    assert out["session"] == "cf01aa30"
    assert out["page"] == "site" and out["title"] == "Machu Picchu"
    assert out["here"] == 600
    assert out["last_seen"] == row["last_seen"].isoformat()


# ---- devices and languages ------------------------------------------------


def test_laptop_and_desktop_are_one_machine():
    """Umami schreibt "laptop" fuer einen Desktop unter 1920 px - das ist eine
    Bildschirmgroesse, kein anderes Geraet. Live am 2026-09-19: laptop 117,
    mobile 45, desktop 6 von 168 Sessions, also rund 27 % Telefone."""
    rows = [
        {"device": "laptop", "language": "en-US", "sessions": 117},
        {"device": "mobile", "language": "en-US", "sessions": 45},
        {"device": "desktop", "language": "de-DE", "sessions": 6},
    ]
    out = fs.devices_and_languages(rows)
    assert out["sessions"] == 168
    assert out["devices"] == [
        {"device": "desktop", "sessions": 123},
        {"device": "mobile", "sessions": 45},
    ]


def test_a_session_umami_could_not_place_keeps_its_own_row():
    """Die Zahlen neben den Anteilen muessen die Sessions ergeben, die die
    Seite behauptet - also wird nichts weggelassen."""
    out = fs.devices_and_languages(
        [
            {"device": None, "language": None, "sessions": 2},
            {"device": "smarttv", "language": "en-GB", "sessions": 1},
        ]
    )
    assert out["sessions"] == 3
    assert {r["device"]: r["sessions"] for r in out["devices"]} == {"unknown": 2, "smarttv": 1}
    # Ohne Sprache keine Sprachzeile: eine leere Angabe ist keine Sprache.
    assert out["languages"] == [{"language": "en-GB", "sessions": 1}]


def test_languages_keep_the_full_tag_and_group_by_the_primary_subtag():
    rows = [
        {"device": "laptop", "language": "en-US", "sessions": 93},
        {"device": "mobile", "language": "en-GB", "sessions": 21},
        {"device": "mobile", "language": "zh-CN", "sessions": 11},
        {"device": "laptop", "language": "de-DE", "sessions": 7},
    ]
    out = fs.devices_and_languages(rows)
    assert out["languages"][:2] == [
        {"language": "en-US", "sessions": 93},
        {"language": "en-GB", "sessions": 21},
    ]
    assert out["language_groups"][0] == {"language": "en", "sessions": 114}
    assert [r["language"] for r in out["language_groups"]] == ["en", "zh", "de"]


# ---- the reading funnel ---------------------------------------------------


def _scroll(session, page, depth, minute=0):
    return ev(
        session,
        "scroll_depth",
        event_type=2,
        data={"page": page, "depth": str(depth)},
        minute=minute,
    )


def test_reading_funnel_counts_visitors_per_step_and_never_a_share():
    """boot.ts feuert jede Marke einmal pro Seitenaufruf - wer bei einer Marke
    auftaucht, hat sie erreicht. Live am 2026-09-19 liefert die Funktion
    story 17/15/13/10 bei 20 Lesern."""
    rows = [
        _scroll("a", "story", 25),
        _scroll("a", "story", 50, minute=1),
        _scroll("a", "story", 75, minute=2),
        _scroll("a", "story", 100, minute=3),
        _scroll("b", "story", 25),
        _scroll("b", "story", 50, minute=1),
        _scroll("c", "country", 25),
    ]
    out = fs.reading_funnel(rows)
    assert out["steps"] == [25, 50, 75, 100]
    assert out["readers"] == 3
    assert out["pages"] == [
        {"page": "story", "sessions": [2, 2, 1, 1]},
        {"page": "country", "sessions": [1, 0, 0, 0]},
    ]
    # Keine Prozente, nirgends: zwanzig Lesevorgaenge tragen keine Quote.
    assert "share" not in out and all("share" not in p for p in out["pages"])


def test_reading_funnel_counts_a_visitor_once_per_step():
    rows = [_scroll("a", "story", 100), _scroll("a", "story", 100, minute=5)]
    assert fs.reading_funnel(rows)["pages"] == [{"page": "story", "sessions": [1, 1, 1, 1]}]


def test_reading_funnel_credits_a_deep_mark_that_arrived_alone():
    """Sechs der siebzehn story-Sessions vom 2026-09-19 tragen genau eine tiefe
    Marke und keine flachere - die vier Sendungen aus einem Frame kommen nicht
    alle an. Wer 100 meldet, hat 25 passiert, also zaehlt er auf jeder Stufe;
    sonst waere der Trichterkopf kleiner als seine eigene Mitte."""
    out = fs.reading_funnel([_scroll("a", "story", 100), _scroll("b", "story", 50)])
    assert out["pages"] == [{"page": "story", "sessions": [2, 2, 1, 1]}]
    assert out["readers"] == 2


def test_reading_funnel_fails_loudly_on_drift():
    """boot.ts schickt depth und page zusammen. Eine scroll_depth-Zeile ohne
    die beiden ist SQL- oder Tracker-Drift und darf nicht still als
    "niemand hat gelesen" durchgehen."""
    with pytest.raises(KeyError):
        fs.reading_funnel([ev("a", "scroll_depth", event_type=2, data={"depth": "50"})])
    with pytest.raises(TypeError):
        fs.reading_funnel([{**ev("a", "scroll_depth", event_type=2), "data": None}])


def test_reading_funnel_ignores_everything_that_is_not_a_scroll():
    rows = [
        ev("a", path="/news-archive/x-1"),
        ev("a", "share", event_type=2, data={"target": "x-1"}),
    ]
    assert fs.reading_funnel(rows) == {"steps": [25, 50, 75, 100], "readers": 0, "pages": []}


# ---- problems: the sixth kind ---------------------------------------------


def test_problems_rank_a_lost_webgl_context_by_the_visitors_it_reached():
    webgl = [{"phase": "loading", "reason": "no_shader", "n": 19, "sessions": 16, **LAST}]
    out = fs.problems([], not_found=[], vitals=[], errors=[], webgl=webgl)
    assert out[0]["kind"] == "webgl_lost"
    assert out[0]["score"] == 48
    assert out[0]["label"] == "globe never started"
    assert out[0]["detail"] == "16 visitors, 19× — no_shader"
    # Eine unbekannte Phase fliegt auf, statt still ein falsches Label zu tragen.
    with pytest.raises(KeyError):
        fs.problems([], not_found=[], vitals=[], errors=[], webgl=[{**webgl[0], "phase": "x"}])


def test_the_webgl_phases_are_the_ones_the_globe_sends():
    """WEBGL_PHASES has no default (the test above pins the KeyError), and the
    vocabulary is written in another language in another repo tree: Globe.tsx
    computes `layersReadyCalledRef.current ? 'live' : 'loading'` and sends that
    string. A third phase there would turn every /api/stats/problems call into
    a 500 and every founder's Problems panel into "Data unavailable." Same
    guard as tests/api/test_goto_discord.py::TestAllowlistSync."""
    globe_tsx = (
        Path(__file__).resolve().parents[2]
        / "ancient-nerds-map"
        / "src"
        / "components"
        / "Globe.tsx"
    ).read_text(encoding="utf-8")
    m = re.search(r"const phase = \w+\.current \? '(\w+)' : '(\w+)'", globe_tsx)
    assert m, "the webgl_lost phase ternary is not in Globe.tsx any more"
    assert set(m.groups()) == set(fs.WEBGL_PHASES)
    assert "track('webgl_lost', { reason, phase })" in globe_tsx


def test_problems_list_eight_rows_by_default():
    errors = [
        {"message": f"e{i}", "page": "globe", "n": 30 - i, "sessions": 30 - i} for i in range(12)
    ]
    assert len(fs.problems([], not_found=[], vitals=[], errors=errors)) == 8
    assert len(fs.problems([], not_found=[], vitals=[], errors=errors, limit=5)) == 5
