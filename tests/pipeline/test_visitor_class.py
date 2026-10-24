# SPDX-License-Identifier: AGPL-3.0-only
"""pipeline.visitor_class — Besucherklassen: Sitzungen (Umami) über
stats_analysis.sessions_from_rows mit Fixture-Zeilen in der Form von
SQL_SESSION_EVENTS, Anfragen (nginx requests.log) über request_class()."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipeline import stats_analysis as fs
from pipeline import visitor_class as vc

#: A Thursday afternoon after CAPTURE_FIX: a second URL no longer proves a
#: person on a direct entry.
T = datetime(2026, 10, 22, 16, 0, tzinfo=UTC)
#: Before CAPTURE_FIX, when a second URL still proved one.
EARLY = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
SG = {"browser": "chrome", "os": "Windows 10", "screen": "1280x1200", "language": "en-US"}
CN = {"browser": "chrome", "os": "Windows 10", "screen": "1600x1600", "language": "zh-CN"}


def row(
    sid,
    at,
    *,
    path=None,
    name=None,
    data=None,
    referrer=None,
    visit=None,
    created=None,
    country="SG",
    fp=SG,
):
    return {
        "session_id": sid,
        "created_at": at,
        "event_type": 2 if name else 1,
        "event_name": name,
        "url_path": path or f"/sites/sg/{sid}",
        "referrer_domain": referrer,
        "utm_source": None,
        "country": country,
        "device": "laptop",
        "data": data or {},
        **fp,
        "session_created": created or at,
        "visit_id": visit or f"v-{sid}",
    }


def starts(n, first, step, prefix="s", **kw):
    """`n` one-page sessions, one start every `step`."""
    return [row(f"{prefix}{i}", first + i * step, **kw) for i in range(n)]


def classes(rows, now=T + timedelta(hours=2)):
    return {s.id: vc.session_class(s, now) for s in fs.sessions_from_rows(rows)}


def crawl(sid, at, urls=5, fp=CN, **kw):
    """A direct session that walks `urls` site pages, each opened by the page
    itself: crawl-shaped."""
    out = []
    for i in range(urls):
        out.append(
            row(
                sid,
                at + timedelta(seconds=10 * i),
                path=f"/sites/cn/{sid}-{i}",
                fp=fp,
                created=at,
                **kw,
            )
        )
        out.append(
            row(
                sid,
                at + timedelta(seconds=10 * i + 1),
                name="site_open",
                data={"context": "site"},
                fp=fp,
                created=at,
                **kw,
            )
        )
    return out


# ---- burst ----------------------------------------------------------------


def test_eight_starts_in_ten_minutes_are_a_burst_and_seven_are_not():
    eight = classes(starts(8, T, timedelta(minutes=1)))
    assert set(eight.values()) == {("scraper_js", "burst")}
    seven = classes(starts(7, T, timedelta(minutes=1)))
    assert {c for c, _ in seven.values()} == {"unclear"}


def test_a_burst_ignores_the_country_but_not_the_screen():
    rows = starts(8, T, timedelta(minutes=1))
    for i, r in enumerate(rows):
        r["country"] = f"C{i}"  # the 800x600 rotation went through 101 countries
    assert set(classes(rows).values()) == {("scraper_js", "burst")}
    rows[0]["screen"] = "1920x1080"
    assert "burst" not in {r for _, r in classes(rows).values()}


def test_the_burst_window_is_half_open_and_marks_only_the_sessions_inside_it():
    # Seven starts within a minute, the eighth exactly ten minutes after the
    # first: no ten-minute window holds eight.
    rows = starts(7, T, timedelta(seconds=5))
    rows.append(row("edge", T + vc.BURST_WINDOW))
    assert "burst" not in {r for _, r in classes(rows).values()}
    # A second earlier it is inside, and a ninth half an hour later is not.
    rows[-1] = row("edge", T + vc.BURST_WINDOW - timedelta(seconds=1))
    rows.append(row("late", T + timedelta(minutes=40)))
    out = classes(rows)
    assert sum(r == "burst" for _, r in out.values()) == 8
    assert out["late"] == ("unclear", "one_page")


def test_the_burst_keys_on_the_session_start_not_on_its_events():
    # Eight sessions created within minutes whose page views come hours apart.
    rows = [
        row(f"s{i}", T + timedelta(hours=i), created=T + timedelta(minutes=i)) for i in range(8)
    ]
    assert set(classes(rows, now=T + timedelta(hours=12)).values()) == {("scraper_js", "burst")}


# ---- volume ---------------------------------------------------------------


def test_fifty_starts_on_one_utc_day_are_volume_and_forty_nine_are_not():
    day = T.replace(hour=0)
    fifty = classes(starts(50, day, timedelta(minutes=20)), now=day + timedelta(days=1))
    assert set(fifty.values()) == {("scraper_js", "volume")}
    forty_nine = classes(starts(49, day, timedelta(minutes=20)), now=day + timedelta(days=1))
    assert "volume" not in {r for _, r in forty_nine.values()}


def test_volume_counts_per_utc_day_so_a_drip_across_midnight_is_two_days():
    rows = starts(50, T.replace(hour=15, minute=40), timedelta(minutes=20))  # 25 + 25
    assert "volume" not in {r for _, r in classes(rows, now=T + timedelta(days=2)).values()}


# ---- machine marks never override a human --------------------------------


def test_a_human_inside_a_burst_stays_human_and_is_counted_as_a_warning():
    rows = starts(8, T, timedelta(minutes=1))
    rows.append(row("s3", T + timedelta(minutes=3, seconds=5), name="search", data={"q": "giza"}))
    sessions = fs.sessions_from_rows(rows)
    out = {s.id: vc.session_class(s, T + timedelta(hours=1)) for s in sessions}
    assert out["s3"] == ("human", None)
    assert sum(c == ("scraper_js", "burst") for c in out.values()) == 7
    assert vc.machine_marks(sessions).get("s3") is None
    assert vc.humans_in_machine_groups(sessions) == 1
    counts = vc.session_counts(sessions, T + timedelta(hours=1))
    assert counts["classes"]["human"] == 1
    assert counts["classes"]["scraper_js"] == 7
    assert counts["reasons"]["burst"] == 7
    assert counts["humans_in_machine_groups"] == 1


def test_no_pageview_alone_is_unclear_and_inside_a_burst_is_a_scraper():
    lone = classes([row("x", T, name="scroll_depth", data={"depth": "50"})])
    assert lone["x"] == ("unclear", "no_pageview")
    rows = [row(f"s{i}", T + timedelta(seconds=i), name="vital") for i in range(8)]
    assert set(classes(rows).values()) == {("scraper_js", "burst")}


# ---- lockstep: the one rule that overrides Session.human ------------------


def test_three_crawls_started_in_one_minute_are_lockstep_even_when_human():
    rows = [
        *crawl("a", EARLY),
        *crawl("b", EARLY + timedelta(seconds=2)),
        *crawl("c", EARLY + timedelta(seconds=58)),
    ]
    # Under the pre-CAPTURE_FIX rule each of them is a person: five URLs.
    unmarked = fs.sessions_from_rows(rows, marks={})
    assert all(s.human for s in unmarked)
    sessions = fs.sessions_from_rows(rows)
    assert {s.id: s.machine for s in sessions} == {
        "a": "lockstep",
        "b": "lockstep",
        "c": "lockstep",
    }
    assert not any(s.human for s in sessions)
    now = EARLY + timedelta(hours=2)
    assert {vc.session_class(s, now) for s in sessions} == {("scraper_js", "lockstep")}
    assert fs.human_ids(sessions) == []


def test_two_crawls_in_one_minute_are_no_lockstep():
    # chrome/Mac OS/1920x1080/en-US had such a pair on 2026-10-06: two tabs.
    rows = [*crawl("a", EARLY), *crawl("b", EARLY + timedelta(seconds=30))]
    assert all(s.human and s.machine is None for s in fs.sessions_from_rows(rows))


def test_a_session_with_an_act_or_too_few_urls_is_no_crawl():
    rows = [
        *crawl("a", EARLY),
        *crawl("b", EARLY + timedelta(seconds=2)),
        *crawl("c", EARLY + timedelta(seconds=4), urls=vc.LOCKSTEP_URLS - 1),
    ]
    assert not any(s.machine for s in fs.sessions_from_rows(rows))
    rows = [
        *crawl("a", EARLY),
        *crawl("b", EARLY + timedelta(seconds=2)),
        *crawl("c", EARLY + timedelta(seconds=4)),
        row("c", EARLY + timedelta(minutes=2), name="search", data={"q": "x"}, fp=CN),
    ]
    assert not any(s.machine for s in fs.sessions_from_rows(rows))


def test_lockstep_reaches_the_fingerprint_s_lone_crawls_for_seven_days():
    lock = [
        *crawl("a", EARLY),
        *crawl("b", EARLY + timedelta(seconds=1)),
        *crawl("c", EARLY + timedelta(seconds=2)),
    ]
    near = crawl("near", EARLY + timedelta(days=6))
    far = crawl("far", EARLY - timedelta(days=8))
    other_fp = crawl("other", EARLY + timedelta(days=1), fp=SG)
    reader = [
        row("reader", EARLY + timedelta(days=1), fp=CN),
        row("reader", EARLY + timedelta(days=1, minutes=1), name="search", fp=CN),
    ]
    marks = {
        s.id: s.machine for s in fs.sessions_from_rows([*lock, *near, *far, *other_fp, *reader])
    }
    assert marks == {
        "a": "lockstep",
        "b": "lockstep",
        "c": "lockstep",
        "near": "lockstep",
        "far": None,
        "other": None,
        "reader": None,
    }


# ---- undecided and the reasons it stays unclear --------------------------


def test_undecided_is_keyed_on_the_latest_visit_not_on_the_session():
    old = T - timedelta(days=3)
    rows = [
        row("back", old, visit="v1", created=old),
        row("back", T, visit="v2", created=old, path="/sites/sg/other"),
        row("once", old, created=old),
    ]
    out = classes(rows, now=T + timedelta(minutes=10))
    assert out["back"] == ("undecided", None)
    assert out["once"] == ("unclear", "one_page")
    assert classes(rows, now=T + vc.UNDECIDED_WINDOW)["back"] == ("unclear", "multi_direct")


def test_a_human_from_an_ai_answer_comes_first():
    rows = [
        row("ai", T, referrer="chatgpt.com"),
        row("ai", T + timedelta(minutes=1), name="search", data={"q": "x"}),
    ]
    assert classes(rows)["ai"] == ("human_ai", None)


def test_cluster_then_multi_direct_then_one_page():
    rows = [row(f"k{i}", T + timedelta(seconds=i), path="/sites/x/same") for i in range(3)]
    rows += [row("walk", T, path="/a"), row("walk", T + timedelta(minutes=1), path="/b")]
    rows += [row("one", T + timedelta(minutes=5), path="/c")]
    out = classes(rows)
    assert [out[f"k{i}"] for i in range(3)] == [("unclear", "cluster")] * 3
    assert out["walk"] == ("unclear", "multi_direct")
    assert out["one"] == ("unclear", "one_page")


def test_cluster_ids_group_every_event_by_path_and_clock_minute():
    rows = [
        row("a", T, path="/p"),
        row("b", T + timedelta(seconds=59), name="vital", path="/p"),
        row("c", T + timedelta(seconds=30), path="/p"),
        row("d", T + timedelta(seconds=60), path="/p"),  # next minute
    ]
    assert vc.cluster_ids(rows) == {"a", "b", "c"}


def test_session_counts_name_every_class_and_reason():
    counts = vc.session_counts(fs.sessions_from_rows([]), T)
    assert counts == {
        "total": 0,
        "classes": dict.fromkeys(vc.SESSION_CLASSES, 0),
        "reasons": dict.fromkeys(vc.SESSION_REASONS, 0),
        "humans_in_machine_groups": 0,
    }
    assert set(vc.LABELS) >= set(vc.SESSION_CLASSES) | set(vc.SESSION_REASONS) | set(
        vc.REQUEST_CLASSES
    )


# ---- bursts ---------------------------------------------------------------


def test_bursts_are_runs_of_one_fingerprint_newest_first():
    rows = starts(8, T, timedelta(seconds=30), prefix="early")
    rows += starts(9, T + timedelta(hours=1), timedelta(seconds=30), prefix="late", country="VN")
    rows[0]["country"] = "US"
    out = vc.bursts(fs.sessions_from_rows(rows))
    assert [(b["start"], b["end"], b["sessions"], b["country"]) for b in out] == [
        (T + timedelta(hours=1), T + timedelta(hours=1, minutes=4), 9, "VN"),
        (T, T + timedelta(minutes=3, seconds=30), 8, "SG"),
    ]
    assert (out[0]["browser"], out[0]["os"], out[0]["screen"], out[0]["language"]) == tuple(
        SG.values()
    )


# ---- requests -------------------------------------------------------------

BROWSER = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/141.0 Safari/537.36"


def rc(**kw):
    args = {
        "purpose": "",
        "ua": BROWSER,
        "bot_kind": None,
        "verified": None,
        "self_declared": False,
        "honeypot": False,
        "beacon": False,
        "dnt": "",
        "gpc": "",
    }
    return vc.request_class(**(args | kw))


def test_request_rules_apply_in_their_order():
    # A prefetch wins over everything, even a crawler UA.
    assert rc(purpose="prefetch;prerender", bot_kind="search", verified=False) == (
        "prefetch",
        False,
    )
    # Known bots by their operator's ranges.
    assert rc(bot_kind="search", verified=True) == ("search", False)
    assert rc(bot_kind="training", verified=True) == ("ai_training", False)
    assert rc(bot_kind="ai_search", verified=True) == ("ai_live", False)
    assert rc(bot_kind="ai_user", verified=True) == ("ai_live", False)
    assert rc(bot_kind="other", verified=True) == ("bot_other", False)
    assert rc(bot_kind="search", verified=False) == ("impostor", False)
    assert rc(bot_kind="training", verified=None) == ("ai_training", True)
    # robots.txt-only tokens never appear in a real UA.
    assert rc(ua="Mozilla/5.0 (compatible; Google-Extended)") == ("impostor", False)
    assert rc(ua="Applebot-Extended/0.1", bot_kind="search", verified=True) == ("impostor", False)
    # Self-declared tools: a crawler and a link preview.
    assert rc(ua="AhrefsBot/7.0", self_declared=True, honeypot=True) == ("self_declared_bot", False)
    assert rc(ua="WhatsApp/2.23", self_declared=True) == ("self_declared_bot", False)
    # The honeypot, before the beacon; a verified assistant keeps its class.
    assert rc(honeypot=True, beacon=True) == ("robots_ignorer", False)
    assert rc(bot_kind="ai_user", verified=True, honeypot=True) == ("ai_live", False)
    # A browser page with a beacon, with DNT or GPC, with neither.
    assert rc(beacon=True) == ("browser_js", False)
    assert rc(dnt="1") == ("unclear", False)
    assert rc(gpc="1") == ("unclear", False)
    assert rc() == ("scraper_nojs", False)


def test_every_request_class_is_reachable_and_named():
    seen = {
        rc(purpose="prefetch")[0],
        rc(bot_kind="search", verified=True)[0],
        rc(bot_kind="training", verified=True)[0],
        rc(bot_kind="ai_user", verified=True)[0],
        rc(bot_kind="other", verified=True)[0],
        rc(bot_kind="search", verified=False)[0],
        rc(self_declared=True)[0],
        rc(honeypot=True)[0],
        rc(beacon=True)[0],
        rc(dnt="1")[0],
        rc()[0],
    }
    assert seen == set(vc.REQUEST_CLASSES)


def test_a_beacon_counts_within_120_seconds_either_side_and_not_at_121():
    at = T
    assert vc.beacon_near(at, [at + timedelta(seconds=120)])
    assert vc.beacon_near(at, [at - timedelta(seconds=120)])
    assert not vc.beacon_near(at, [at + timedelta(seconds=121)])
    assert not vc.beacon_near(at, [at - timedelta(seconds=121), at + timedelta(seconds=121)])
    assert not vc.beacon_near(at, [])


def test_pages_beacons_and_the_honeypot():
    assert vc.is_beacon("POST", "/api/pulse")
    assert vc.is_beacon("GET", "/pulse.js?v=3")
    assert vc.is_beacon("GET", "/api/app/interactive")
    assert not vc.is_beacon("GET", "/api/pulse")
    assert vc.is_page("GET", "/sites/peru/x-1?ref=a", 200)
    assert vc.is_page("GET", "/news-archive/gone", 410)
    assert not vc.is_page("GET", "/sites/peru/x-1", 404)
    assert not vc.is_page("HEAD", "/", 200)
    assert not vc.is_page("POST", "/api/pulse", 200)
    assert not vc.is_page("GET", "/pulse.js", 200)
    assert not vc.is_page("GET", "/sitemap-sites.xml", 200)
    assert not vc.is_page("GET", "/robots.txt", 200)
    assert not vc.is_page("GET", "/feeds/stories", 200)
    assert vc.is_honeypot("/index-all/")
    assert vc.is_honeypot("/index-all/deeper?x=1")
    assert not vc.is_honeypot("/index-all")
    assert vc.is_prefetch("prefetch")
    assert not vc.is_prefetch("")


# ---- one definition -------------------------------------------------------


def test_the_live_window_of_the_dashboard_is_the_undecided_window():
    from api.routes import founders_stats

    assert founders_stats.HERE_WINDOW is vc.UNDECIDED_WINDOW


@pytest.mark.parametrize("name", ["SESSION_CLASSES", "SESSION_REASONS", "REQUEST_CLASSES"])
def test_the_class_tuples_hold_no_duplicates(name):
    values = getattr(vc, name)
    assert len(values) == len(set(values))
