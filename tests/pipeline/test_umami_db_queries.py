# SPDX-License-Identifier: AGPL-3.0-only
"""pipeline.umami_db — Leseschicht auf Umamis Tabellen für das Founders-Dashboard.

DB-los: geprüft wird die Form der SQL-Texte (parametrisiert, auf eine Website
und ein Zeitfenster begrenzt), die träge Engine (Import ohne Passwort darf
nicht knallen) und dass fetch() die Fensterparameter wirklich bindet.
"""

from __future__ import annotations

import importlib
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
    assert "'webgl_lost'" in sql and "phase = 'loading'" in sql
    # globe_bg fires after the globe is up: nothing here may count it.
    assert "'globe_bg'" not in sql
    assert "AS first_view" in sql and "AS endings_since" in sql
    # endings_since is the first ending ever recorded on the path, not the
    # first inside the window: a window that starts after the instrumentation
    # went live must not call its own early loads "before these were recorded".
    sub = sql[sql.index("SELECT min(e2.created_at)") : sql.index("AS endings_since")]
    assert ":since" not in sub and ":until" not in sub
    assert "e2.website_id = :website_id" in sub and "e2.url_path = :path" in sub


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
