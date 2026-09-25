# SPDX-License-Identifier: AGPL-3.0-only
"""pipeline.umami_db — Leseschicht auf Umamis Tabellen für das Founders-Dashboard.

DB-los: geprüft wird die Form der SQL-Texte (parametrisiert, auf eine Website
und ein Zeitfenster begrenzt), die träge Engine (Import ohne Passwort darf
nicht knallen) und dass fetch() die Fensterparameter wirklich bindet.
"""

from __future__ import annotations

import importlib
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline import umami_db as u

QUERIES = (
    "overview",
    "map",
    "session_events",
    "content",
    "feedback",
    "sources",
    "not_found",
    "vitals",
    "errors",
    "globe",
    "clusters",
    "devices",
    "webgl_lost",
    "live",
)


def test_queries_are_parameterised_and_scoped_to_the_website():
    for name in QUERIES:
        sql = getattr(u, f"SQL_{name.upper()}")
        assert ":website_id" in sql and ":since" in sql and ":until" in sql, name
        assert "'%" not in sql and "%s" not in sql and "{" not in sql, name  # no interpolation


def test_queries_only_read():
    for name in QUERIES:
        sql = getattr(u, f"SQL_{name.upper()}").upper()
        # A read-only statement starts with SELECT, or with a WITH clause whose
        # body is a SELECT (SQL_CONTENT groups per event before ranking). The
        # verb list below still catches a data-modifying CTE.
        assert sql.lstrip().startswith(("SELECT", "WITH")), name
        for verb in ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE"):
            assert verb not in sql, (name, verb)


def test_problem_queries_read_the_events_the_frontend_actually_sends():
    """not_found comes from the 404 page (pipeline/article_html_renderer.py),
    vital and js_error from src/analytics/boot.ts — the data keys below are the
    ones those three call sites put into the event."""
    assert "'not_found'" in u.SQL_NOT_FOUND
    assert "'path'" in u.SQL_NOT_FOUND and "'referrer'" in u.SQL_NOT_FOUND
    assert "'vital'" in u.SQL_VITALS
    for key in ("'page'", "'name'", "'value'"):
        assert key in u.SQL_VITALS, key
    # The value is a number: Umami keeps it in number_value, not string_value.
    assert "number_value" in u.SQL_VITALS
    assert "percentile_cont(0.75)" in u.SQL_VITALS
    assert "'js_error'" in u.SQL_ERRORS
    assert "'message'" in u.SQL_ERRORS and "'page'" in u.SQL_ERRORS
    # How many visitors it reached, not only how often it fired: boot.ts sends
    # up to three per page view, so the event count alone overstates the damage.
    # The same for the other two kinds the panel scores by people: one visitor
    # reloading a dead link is one broken link, and a slow page is weighed by
    # the visitors it reached (the samples stay, because a percentile needs
    # measurements — stats_analysis.VITAL_MIN_SAMPLES).
    for name in ("SQL_ERRORS", "SQL_NOT_FOUND", "SQL_VITALS"):
        assert "count(DISTINCT session_id) AS sessions" in getattr(u, name), name
    assert "count(*) AS samples" in u.SQL_VITALS
    # Date, time and visitor on every kind the problems panel shows.
    for name in ("SQL_ERRORS", "SQL_NOT_FOUND", "SQL_VITALS", "SQL_CONTENT", "SQL_WEBGL_LOST"):
        sql = getattr(u, name)
        assert "max(created_at) AS last_at" in sql, name
        for column in ("last_session", "last_country", "last_device", "last_browser"):
            assert column in sql, (name, column)
    # The bounce rows come from the folded sessions, which need the browser too.
    assert "s.browser" in u.SQL_SESSION_EVENTS
    # The globe funnel and its times come from one scan, and it never asks
    # whether a Core Web Vital arrived (see the constant's own comment).
    assert "'globe_ready'" in u.SQL_GLOBE and ":path" in u.SQL_GLOBE
    assert "'vital'" not in u.SQL_GLOBE
    # The cluster rule is one rule: a path several session ids share in a minute.
    assert ":min_ids" in u.SQL_CLUSTERS and "date_trunc('minute'" in u.SQL_CLUSTERS
    assert "'webgl_lost'" in u.SQL_WEBGL_LOST
    for key in ("'reason'", "'phase'"):
        assert key in u.SQL_WEBGL_LOST, key
    # The live list names the page, which is a plain column, not event_data.
    assert "page_title" in u.SQL_LIVE
    # Devices and languages are two plain session columns, one scan.
    assert "s.device" in u.SQL_DEVICES and "s.language" in u.SQL_DEVICES


def test_the_globe_query_reads_how_the_unreached_loads_ended():
    """The split of the loads that never reached globe_ready rides on the one
    /globe.html scan (the dashboard contract forbids a second one): the four
    ending events, the two string keys they carry, the start failure the globe
    already reports as webgl_lost, and the moment the endings began."""
    sql = u.SQL_GLOBE
    for name in ("'globe_gate'", "'globe_unsupported'", "'globe_error'", "'globe_abandon'"):
        assert name in sql, name
    assert "'choice'" in sql and "'phase'" in sql
    # A gate choice of the globe itself is not an ending; the gate phase of an
    # abandon is the gate bucket, not "left while loading".
    assert "choice <> 'globe'" in sql
    assert "phase = 'gate'" in sql and "phase IS DISTINCT FROM 'gate'" in sql
    # Background failures belong to loads that reached the globe. left(), not
    # LIKE: a LIKE pattern needs the percent sign the guard above forbids.
    assert "left(phase, 3) <> 'bg:'" in sql
    # A globe_error after globe_ready (phase 'live': the error boundary caught
    # a render error of a globe that was up, or a loader failed later) is no
    # start failure either.
    assert "phase <> 'live'" in sql
    assert "'webgl_lost'" in sql and "phase = 'loading'" in sql
    # globe_bg fires after the globe is up: nothing here may count it.
    assert "'globe_bg'" not in sql
    # endings_since is the first ending ever recorded on the path, not the
    # first inside the window: a window that starts after the instrumentation
    # went live must not cut its own early loads away as the old build.
    sub = sql[sql.index("WITH first_ending AS (") : sql.index("ev AS (")]
    assert "SELECT min(e2.created_at) AS endings_since" in sub
    assert ":since" not in sub and ":until" not in sub
    assert "e2.website_id = :website_id" in sub and "e2.url_path = :path" in sub
    # Every column counts from measured_from on, per load and not per session:
    # an Umami session is one browser for a calendar month, so it holds loads
    # from both sides. The loads of the old build are left out entirely,
    # successes included (founders, 2026-09-25). An inner join: a session
    # without a measured_from has no load of the new build.
    flat = " ".join(sql.split())
    assert (
        "FROM ev JOIN measured m USING (session_id) WHERE ev.created_at >= m.measured_from" in flat
    )
    assert "views_before" not in sql and "ready_before" not in sql
    # Except the session's first load at or after endings_since, when the session
    # had opened the globe before it: the globe page installed the service
    # worker, which serves globe.html and its JS cache-first, so that load still
    # ran the previous build, which sends no ending
    # (ancient-nerds-map/src/pwa/globeStartPrecache.ts). The next one is measured.
    sub = " ".join(sql[sql.index("switched AS (") : sql.index("measured AS (")].split())
    assert (
        "CASE WHEN bool_or(v.event_type = 1 AND v.created_at < f.endings_since) "
        "THEN (array_agg(v.created_at ORDER BY v.created_at) "
        "FILTER (WHERE v.event_type = 1 AND v.created_at >= f.endings_since))[2] "
        "ELSE f.endings_since END AS worker_from"
    ) in sub
    # The session's whole history on the path, not the window: the view before the
    # endings began can lie before :since while the stale load lies inside it
    assert ":since" not in sub and ":until" not in sub
    assert "v.website_id = :website_id AND v.url_path = :path" in sub
    assert "v.session_id IN (SELECT session_id FROM ev)" in sub
    assert "FROM website_event v CROSS JOIN first_ending f" in sub
    assert "GROUP BY v.session_id, f.endings_since" in sub
    # Only views and the four endings: the session's first ending of its own
    # must not be a vital or a globe_ready.
    assert (
        "AND (v.event_type = 1 OR v.event_name IN "
        "('globe_gate', 'globe_unsupported', 'globe_error', 'globe_abandon'))"
    ) in sub
    assert "min(v.created_at) FILTER (WHERE v.event_type <> 1) AS own_first_ending" in sub
    # Or earlier: the load that sent the session's first ending ran the new
    # build, whatever the worker rule says. Live 2026-09-24: the load that sent
    # the very first ending had its view 40 s before endings_since.
    sub = " ".join(sql[sql.index("measured AS (") : sql.index("SELECT session_id,")].split())
    assert "least(s.worker_from, (SELECT max(w.created_at) FROM website_event w" in sub
    assert "w.event_type = 1 AND w.session_id = s.session_id" in sub
    assert "AND w.created_at <= s.own_first_ending)) AS measured_from" in sub
    assert "w.website_id = :website_id AND w.url_path = :path" in sub
    assert ":since" not in sub and ":until" not in sub


def test_the_ending_events_the_globe_query_reads_are_in_the_frontend_taxonomy():
    """The event names are written twice, in two languages: SQL_GLOBE reads
    them and src/analytics/index.ts's EventName is the only vocabulary track()
    accepts. A rename on one side would turn a bucket into a silent zero."""
    index_ts = (
        Path(__file__).resolve().parents[2] / "ancient-nerds-map" / "src" / "analytics" / "index.ts"
    ).read_text(encoding="utf-8")
    union = index_ts[
        index_ts.index("export type EventName") : index_ts.index("export type EventProps")
    ]
    for name in (
        "globe_gate",
        "globe_unsupported",
        "globe_error",
        "globe_abandon",
        "globe_ready",
        "webgl_lost",
    ):
        assert f"| '{name}'" in union, name
        assert f"'{name}'" in u.SQL_GLOBE, name


def test_the_globe_event_docs_name_the_senders_the_frontend_uses():
    """The founders dashboard is read through these comments. globe_ready is
    sent by App when the loading overlay fades (sites, critical layers, focus
    lookup), not by Globe at onLayersReady, and App sends webgl_lost through
    analytics/globeAbandon.ts. Docs naming the old sender invite reading
    ready_ms as the layers moment."""
    root = Path(__file__).resolve().parents[2]
    src = root / "ancient-nerds-map" / "src"
    umami_doc = Path(u.__file__).read_text(encoding="utf-8")
    stats_doc = (root / "pipeline" / "stats_analysis.py").read_text(encoding="utf-8")
    for doc in (umami_doc, stats_doc):
        assert "onLayersReady" not in doc
        assert "src/components/Globe.tsx sends" not in doc
    assert "hooks/useGlobeReady.ts" in umami_doc
    assert "track('globe_ready'" in (src / "hooks" / "useGlobeReady.ts").read_text(encoding="utf-8")
    assert "analytics/globeAbandon.ts reportWebglLost" in umami_doc
    assert "analytics/globeAbandon.ts reportWebglLost" in stats_doc
    assert "export function reportWebglLost(" in (src / "analytics" / "globeAbandon.ts").read_text(
        encoding="utf-8"
    )


def test_the_literals_the_globe_query_depends_on_are_the_ones_the_frontend_sends():
    """SQL_GLOBE buckets the unreached loads by string literals that the
    frontend writes in another language: the gate choice 'globe' (not an
    ending), the abandon phase 'gate', the error phases 'live' and 'bg:<task>'
    (not start failures) and webgl_lost's 'loading'. A rename on either side
    would silently move loads between buckets, so both sides are pinned here."""
    src = Path(__file__).resolve().parents[2] / "ancient-nerds-map" / "src"

    def read(*parts: str) -> str:
        return src.joinpath(*parts).read_text(encoding="utf-8")

    sql = u.SQL_GLOBE
    abandon = read("analytics", "globeAbandon.ts")
    # The globe button is the one gate choice that is no ending
    assert "if (choice === 'globe') track('globe_gate', { choice })" in abandon
    assert "choice <> 'globe'" in sql
    # globe_abandon's phase while the gate shows
    assert "if (gateShowing) return 'gate'" in abandon
    assert "installGlobeAbandon" in read("App.tsx")
    assert "phase = 'gate'" in sql
    # The prop keys the phase and the wait travel under: renamed keys would read as NULL, so
    # every gate quit would count as 'Left while loading' and the abandon median would vanish
    assert (
        "opts.latch.end('globe_abandon', { ms: Math.round(opts.now()), phase: opts.getPhase() })"
        in abandon
    )
    assert "max(d.string_value) FILTER (WHERE d.data_key = 'phase')" in sql
    assert "(max(d.number_value) FILTER (WHERE d.data_key = 'ms'))::float8 AS ms" in sql
    # The abandon wait counts from the start of the load, not from navigation: on a phone the
    # Globe mounts only once the gate goes away, and reading the gate is no loading wait
    assert "now: () => loadClock.elapsed()," in read("App.tsx")
    assert "if (gate && !showing) start = now()" in abandon
    # A start failure's globe_error, sent when its screen shows, carries its phase the same way
    assert (
        "return { name: 'globe_error', props: { phase: globeFailure.phase, message: globeFailure.message } }"
        in read("App.tsx")
    )
    # Errors after globe_ready carry 'live', from App (boundary) and the Globe's loaders
    assert "export const LIVE_PHASE = 'live'" in read("utils", "globeStartError.ts")
    assert "if (phase === LIVE_PHASE) track('globe_error', { phase, message })" in read("App.tsx")
    assert "track('globe_error', { phase: LIVE_PHASE," in read(
        "components", "GlobeErrorBoundary.tsx"
    )
    assert "phase <> 'live'" in sql
    # A start failure after the load already ended (a tab switch sent globe_abandon) keeps its
    # diagnostics but is no second ending: the frontend marks it, `failed` skips the mark
    assert "track('globe_error', { ...ending.props, ending: 'no' })" in read(
        "hooks", "useGlobeScreenEnding.ts"
    )
    assert "max(d.string_value) FILTER (WHERE d.data_key = 'ending') AS ending" in sql
    assert "ending IS DISTINCT FROM 'no'" in sql
    # Background failures carry 'bg:<task>', built in one place: every sender goes through
    # trackBackgroundFailure (the hi-res coastline too), none writes a bg: phase of its own
    assert "phase: `bg:${task}`" in read("analytics", "globeBackground.ts")
    assert "trackBackgroundFailure('hires', err)" in read("components", "Globe.tsx")
    own_bg_phase = [
        str(f.relative_to(src))
        for f in src.rglob("*.ts*")
        if "__tests__" not in f.parts
        and f.name != "globeBackground.ts"
        and re.search(r"phase: ['`]bg:", f.read_text(encoding="utf-8"))
    ]
    assert own_bg_phase == []
    assert "left(phase, 3) <> 'bg:'" in sql
    # webgl_lost before globe_ready is a start failure (test_stats_analysis pins the ternary too)
    assert "const phase = globeReady ? 'live' : 'loading'" in abandon
    assert "reportWebglLost(endingLatch, reason, globeReadyRef.current)" in read("App.tsx")
    assert "phase = 'loading'" in sql


def test_the_scroll_depth_funnel_needs_no_query_of_its_own():
    """boot.ts sends scroll_depth with its own `page` and `depth`, and those
    events already travel inside SQL_SESSION_EVENTS' `data` column — the
    reading funnel folds from the rows /journeys fetches anyway."""
    assert "scroll_depth" not in "".join(getattr(u, f"SQL_{name.upper()}") for name in QUERIES)
    assert "jsonb_object_agg" in u.SQL_SESSION_EVENTS


def test_the_hour_bucket_query_is_gone():
    """The strip folds its 48 fixed buckets out of the session rows /overview
    already fetches. SQL_HOUR_BUCKETS returned one row per hour that had
    events - 45 for a 48-hour window on 2026-09-19 - and every gap shifted
    the bars left of it."""
    assert not hasattr(u, "SQL_HOUR_BUCKETS")


def test_import_without_password_is_fine_and_engine_is_lazy(monkeypatch):
    monkeypatch.delenv("UMAMI_DB_PASSWORD", raising=False)
    sys.modules.pop("pipeline.umami_db", None)
    mod = importlib.import_module("pipeline.umami_db")
    mod.engine.cache_clear()
    with pytest.raises(KeyError):  # misconfigured deploy fails loudly, at first use
        mod.engine()


def test_engine_keeps_special_characters_in_the_password(monkeypatch):
    """Ein Passwort mit @ oder # darf die DSN nicht zerlegen."""
    probe = "p@ss#w:rd/1"  # every character a naive f-string DSN would misparse
    monkeypatch.setenv("UMAMI_DB_PASSWORD", probe)
    u.engine.cache_clear()
    try:
        url = u.engine().url
    finally:
        u.engine.cache_clear()
    assert url.username == "umami" and url.database == "umami"
    assert url.password == probe
    assert url.host == u.settings.database.host and url.port == u.settings.database.port


def test_fetch_binds_website_and_window_and_extra_params(monkeypatch):
    calls: list[tuple[str, dict]] = []

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, stmt, params):
            calls.append((str(stmt), params))
            return [SimpleNamespace(_mapping={"views": 3, "sessions": 2, "live_sessions": 1})]

    monkeypatch.setattr(u, "engine", lambda: SimpleNamespace(connect=Conn))
    monkeypatch.setattr(u, "WEBSITE_ID", "02372c1d-0000-4000-8000-000000000000")
    since, until = datetime(2026, 9, 10, tzinfo=UTC), datetime(2026, 9, 17, tzinfo=UTC)
    rows = u.fetch(u.SQL_OVERVIEW, since, until, live=until)
    assert rows == [{"views": 3, "sessions": 2, "live_sessions": 1}]
    sql, params = calls[0]
    assert "live_sessions" in sql
    assert params == {
        "website_id": "02372c1d-0000-4000-8000-000000000000",
        "since": since,
        "until": until,
        "live": until,
    }
