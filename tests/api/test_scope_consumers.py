# SPDX-License-Identifier: AGPL-3.0-only
"""E4 (migration 0020) in the other api/ consumers: sitemap, stats, public API, snapshots,
sources, likes/bookmarks, radar count, Lyra's site tools.

DB-less against tests/fake_sql.RecordingSession (refuses plain strings, records every
statement). Each test pins the scope predicate into the statement that selects sites.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from pipeline.utils.public_sites import journal_join, last_change, not_retired
from tests.fake_sql import OrmSession, RecordingSession

SHOWN = not_retired()
US = not_retired("us")
U = not_retired("u")
SITE_ID = "9c8b7a65-4321-4cba-8000-111122223333"


# --------------------------------------------------------------------------------------
# sitemap: retired pages are not advertised, journaled writes move lastmod
# --------------------------------------------------------------------------------------


def test_sitemap_parts_list_only_shown_sites():
    from api.routes import sitemap as sm

    for sql in (sm._SITES_SQL.text, sm._LEGACY_SQL.text, sm._COUNTRIES_SQL.text):
        assert U in sql, sql
        assert "u.source_id = 'ancient_nerds'" in sql


def test_sitemap_lastmod_includes_the_remediation_journal():
    """apply_remediation_change() does not touch updated_at: 0 of 984 corrected pages
    carried a newer lastmod on 2026-09-22. The journal's applied_at is their change date."""
    from api.routes import sitemap as sm

    for sql in (sm._SITES_SQL.text, sm._COUNTRIES_SQL.text):
        assert last_change("u") in sql
        assert journal_join("u") in sql


def test_sitemap_serves_the_journal_date_it_is_given():
    from api.routes import sitemap as sm

    journaled = datetime(2026, 9, 21, 18, 10)
    db = RecordingSession(
        {
            "FROM unified_sites u": [
                SimpleNamespace(
                    name="Damascus Gate", country="Syria", id=SITE_ID, lastmod=journaled
                )
            ]
        }
    )
    resp = asyncio.run(sm.sitemap_sites(db=db))
    assert b"<lastmod>2026-09-21</lastmod>" in resp.body


# --------------------------------------------------------------------------------------
# site_stats (homepage hero + /api/stats)
# --------------------------------------------------------------------------------------


def test_site_stats_counts_no_retired_site():
    from api.services import site_stats

    db = RecordingSession({"COUNT(*) FROM": [(10,)], "COUNT(DISTINCT country)": [(95,)]})
    with (
        patch.object(site_stats, "cache_get", return_value=None),
        patch.object(site_stats, "cache_set"),
        patch.object(site_stats, "get_session", return_value=db),
    ):
        site_stats.get_site_stats()
    assert len(db.statements()) == 3
    for sql in db.statements():
        assert SHOWN in sql, sql


# --------------------------------------------------------------------------------------
# public API v1
# --------------------------------------------------------------------------------------


@pytest.fixture
def public_api():
    from api.routes import public_v1

    app = public_v1.create_public_api()
    db = RecordingSession()
    app.dependency_overrides[public_v1.get_db] = lambda: db
    app.dependency_overrides[public_v1.rate_limit_dependency] = lambda: None
    with (
        patch.object(public_v1, "cache_get", return_value=None),
        patch.object(public_v1, "cache_set"),
    ):
        # Server errors from the canned rows do not matter here: the statements were
        # recorded before the response was built.
        yield TestClient(app, raise_server_exceptions=False), db


@pytest.mark.parametrize(
    "path",
    [
        "/status",
        "/sites.geojson",
        "/sites/search?q=petra",
        "/sources",
        "/sources/ancient_nerds",
        "/stats",
        "/facets",
        "/cards",
    ],
)
def test_public_api_site_reads_carry_the_scope_filter(public_api, path):
    client, db = public_api
    client.get(path)
    site_reads = [sql for sql in db.statements() if "unified_sites" in sql]
    assert site_reads, path
    for sql in site_reads:
        assert SHOWN in sql or US in sql, (path, sql)


def test_public_api_answers_410_for_a_retired_site(public_api):
    client, db = public_api
    db.answers["WHERE id::text = :site_id"] = [
        SimpleNamespace(
            id=SITE_ID,
            name="Damascus Gate",
            lat=1.0,
            lon=2.0,
            source_id="ancient_nerds",
            site_type=None,
            period_start=1537,
            period_end=None,
            period_name=None,
            country="Syria",
            description=None,
            source_url=None,
            thumbnail_url=None,
            scope_status="retired",
        )
    ]
    assert client.get(f"/sites/{SITE_ID}").status_code == 410


def test_public_api_serves_no_images_of_a_retired_site(public_api):
    client, db = public_api
    client.get(f"/sites/{SITE_ID}/images")
    sql = db.statement_with("FROM wiki_images")
    assert "NOT EXISTS" in sql and "us.scope_status = 'retired'" in sql


# --------------------------------------------------------------------------------------
# snapshots carry the scope columns both ways
# --------------------------------------------------------------------------------------


def test_create_snapshot_captures_the_scope_columns():
    from api.services import snapshots

    db = RecordingSession({"SELECT COUNT(*) FROM unified_sites": [(1,)]})
    snapshots.create_snapshot(db, [SITE_ID], created_by="t", description="d", snapshot_type="edit")
    capture = db.statement_with("INSERT INTO snapshot_rows")
    assert "'scope_status', scope_status" in capture
    assert "'scope_reason', scope_reason" in capture


def test_restore_brings_scope_back_only_from_a_snapshot_that_recorded_it():
    from api.services import snapshots

    db = RecordingSession(
        {
            "FROM db_snapshots": [SimpleNamespace(source_id="ancient_nerds", snapshot_type="edit")],
            "FROM snapshot_rows WHERE snapshot_id": [SimpleNamespace(site_id=SITE_ID)],
        }
    )
    with (
        patch.object(snapshots, "create_snapshot", return_value="undo"),
        patch.object(snapshots, "cache_delete_pattern", return_value=0),
    ):
        snapshots.restore_snapshot(db, "snap", restored_by="t")
    # The upsert leaves scope alone: a pre-0020 snapshot has no scope key, and NULL from
    # it would un-retire a site without a journal row.
    upsert = db.statement_with("ON CONFLICT (id) DO UPDATE SET")
    assert "scope_status" not in upsert and "scope_reason" not in upsert
    # A follow-up UPDATE restores it from the rows that recorded it, after the upsert.
    scope = db.statement_with("sr.old_data ? 'scope_status'")
    assert "scope_status = sr.old_data->>'scope_status'" in scope
    assert "scope_reason = sr.old_data->>'scope_reason'" in scope
    statements = db.statements()
    assert statements.index(scope) > statements.index(upsert)


def test_preview_shows_an_un_retirement():
    from api.services import snapshots

    db = RecordingSession(
        {
            "FROM db_snapshots WHERE": [
                SimpleNamespace(
                    id="snap",
                    created_at=datetime(2026, 9, 1),
                    created_by="t",
                    description="d",
                    snapshot_type="edit",
                    row_count=1,
                    source_id="ancient_nerds",
                )
            ],
            "FROM snapshot_rows WHERE": [
                SimpleNamespace(site_id=SITE_ID, old_data={"name": "Damascus Gate"})
            ],
            "FROM unified_sites WHERE id::text = ANY": [
                SimpleNamespace(
                    id=SITE_ID,
                    name="Damascus Gate",
                    site_type=None,
                    period_start=None,
                    period_name=None,
                    country=None,
                    description=None,
                    source_url=None,
                    thumbnail_url=None,
                    scope_status="retired",
                )
            ],
        }
    )
    preview = snapshots.preview_snapshot(db, "snap")
    (site,) = preview["sites"]
    assert site["fields"] == [{"field": "scope_status", "current": "retired", "restore_to": None}]


def test_the_file_snapshot_has_one_writer():
    """rebuild-static used to write two manifest entries per run (two writers)."""
    from api.services import snapshots
    from pipeline import static_exporter

    db = RecordingSession()
    with patch.object(snapshots, "write_file_snapshot", return_value="k") as write:
        assert snapshots.export_file_snapshot(db) == "k"
    write.assert_called_once_with(db, snapshots.SNAPSHOTS_DIR)
    assert snapshots.write_file_snapshot is static_exporter.write_file_snapshot


# --------------------------------------------------------------------------------------
# /api/sources, likes and bookmarks, radar count, Lyra's site tools
# --------------------------------------------------------------------------------------


def test_source_counts_on_the_globe_exclude_retired_sites():
    from api.routes import sources

    db = RecordingSession(
        {
            "FROM source_meta sm": [
                SimpleNamespace(
                    source_id="ancient_nerds",
                    count=5004,
                    name="Ancient Nerds",
                    color="#FFD700",
                    is_primary=True,
                    enabled_by_default=True,
                    priority=0,
                    category=None,
                    description=None,
                )
            ]
        }
    )
    with patch.object(sources, "cache_get", return_value=None), patch.object(sources, "cache_set"):
        asyncio.run(sources.get_sources(db=db))
    assert SHOWN in db.statement_with("FROM unified_sites")


def test_source_detail_counts_exclude_retired_sites():
    from api.routes import sources

    db = RecordingSession({"SELECT COUNT(*) FROM unified_sites": [(5,)]})
    with patch.object(sources, "cache_get", return_value=None), patch.object(sources, "cache_set"):
        asyncio.run(sources.get_source_detail("ancient_nerds", db=db))
    site_reads = [sql for sql in db.statements() if "FROM unified_sites" in sql]
    assert len(site_reads) == 3
    for sql in site_reads:
        assert SHOWN in sql


@pytest.mark.parametrize("route", ["get_my_likes", "get_my_bookmarks"])
def test_saved_sites_lists_hide_retired_sites(route):
    from api.routes import interactions

    session = OrmSession()
    with patch.object(interactions, "get_session", return_value=_ctx(session)):
        getattr(interactions, route)(user=SimpleNamespace(id="u1"))
    (sql,) = session.sql
    assert "unified_sites.scope_status IS DISTINCT FROM 'retired'" in sql


def test_radar_curated_count_excludes_retired_sites():
    from api.routes import radar

    db = RecordingSession({"FROM user_contributions": [None]})
    with patch.object(radar, "cache_get", return_value=None), patch.object(radar, "cache_set"):
        radar.get_radar_stats(db=db)
    assert SHOWN in db.statement_with("FROM unified_sites WHERE source_id = 'ancient_nerds'")


def test_lyra_site_details_never_resolve_a_retired_site():
    from api.services import lyra_tools

    session = RecordingSession()
    with patch.object(lyra_tools, "get_session", return_value=_ctx(session)):
        lyra_tools.get_site_details.invoke({"site_id": SITE_ID})
        lyra_tools.get_site_details.invoke({"site_id": "damascus-gate"})
    lookups = [sql for sql in session.statements() if "FROM unified_sites s" in sql]
    assert len(lookups) == 2
    for sql in lookups:
        assert not_retired("s") in sql


def test_lyra_site_search_hides_retired_sites():
    from pipeline.lyra import site_search

    session = RecordingSession()
    with patch.object(site_search, "get_session", return_value=_ctx(session)):
        site_search.search_sites("damascus")
    assert not_retired("s") in session.statement_with("FROM unified_sites s")


class _ctx:
    """get_session() stand-in: a context manager yielding the given fake session."""

    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, *exc):
        return False


def test_sources_have_no_static_json_fallback():
    """An empty source_meta is a broken table, not a reason to serve a stale file."""
    from fastapi import HTTPException

    from api.routes import sources

    assert not hasattr(sources, "_load_static_sources")
    with (
        patch.object(sources, "cache_get", return_value=None),
        pytest.raises(HTTPException) as exc,
    ):
        asyncio.run(sources.get_sources(db=RecordingSession()))
    assert exc.value.status_code == 500
