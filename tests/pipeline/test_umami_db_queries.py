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
from types import SimpleNamespace

import pytest

from pipeline import umami_db as u

QUERIES = (
    "overview",
    "map",
    "hour_buckets",
    "session_events",
    "content",
    "feedback",
    "sources",
    "not_found",
    "vitals",
    "errors",
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
    assert "count(DISTINCT session_id) AS sessions" in u.SQL_ERRORS


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
