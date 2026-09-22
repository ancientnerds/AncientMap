# SPDX-License-Identifier: AGPL-3.0-only
"""api/routes/sites.py hides retired sites (E4, migration 0020) and answers 410 for them.

DB-less (there is no local database): the routes run against tests/fake_sql.RecordingSession,
which refuses plain strings as SQLAlchemy 2 does and records every statement. Each test pins
that the scope predicate sits in the WHERE of the statement that selects the sites, with the
alias that statement uses - the predicate's NULL semantics are proven against a real engine
in tests/pipeline/test_public_sites.py.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from api.routes import sites as sr
from api.services.background_jobs import JobAlreadyRunning
from pipeline.utils.public_sites import not_retired
from tests.fake_sql import RecordingSession

US = not_retired("us")
U = not_retired("u")
BARE = not_retired()

SITE_ID = "9c8b7a65-4321-4cba-8000-111122223333"


@pytest.fixture(autouse=True)
def _no_cache_no_limits(monkeypatch):
    monkeypatch.setattr(sr, "cache_get", lambda key: None)
    monkeypatch.setattr(sr, "cache_set", lambda *a, **k: None)
    monkeypatch.setattr(sr, "get_client_ip", lambda req: "203.0.113.9")
    for limiter in (sr._heavy_limiter, sr._viewport_limiter, sr._search_limiter):
        monkeypatch.setattr(limiter, "check", lambda ip: True)


def _where(sql: str) -> str:
    """Everything after the last top-level FROM ... WHERE of a statement."""
    return sql.split("WHERE", 1)[1]


# --------------------------------------------------------------------------------------
# /all
# --------------------------------------------------------------------------------------


def _all(db, **kw):
    params = {"source": None, "site_type": None, "period_max": None, "skip": 0, "limit": 100000}
    params.update(kw)
    return sr.get_all_sites(req=None, db=db, **params)


def test_all_filters_retired_sites_in_the_live_query():
    db = RecordingSession()
    with patch("api.routes.snapshots.get_active_pins", return_value={}):
        _all(db)
    sql = db.statement_with("FROM unified_sites us")
    assert US in _where(sql)
    assert "us.source_id = ANY(:sources)" in sql


def test_all_has_no_static_json_fallback():
    """An empty answer is the answer: no 362 MB index loaded into API memory."""
    db = RecordingSession()
    with patch("api.routes.snapshots.get_active_pins", return_value={}):
        resp = _all(db, source=["david_rumsey"])
    assert resp == {"count": 0, "sites": [], "dataSource": "postgres"}
    for gone in ("_load_static_sites", "_filter_static_sites", "_convert_static_site"):
        assert not hasattr(sr, gone), gone


def test_all_drops_retired_sites_from_a_pinned_snapshot(tmp_path, monkeypatch):
    """A snapshot predates the retirement; E4 hides the site anyway."""
    snap = {
        "sites": [
            {"id": "keep-1", "n": "Stonehenge", "s": "ancient_nerds", "p": -3000},
            {"id": "gone-1", "n": "Damascus Gate", "s": "ancient_nerds", "p": 1537},
        ]
    }
    (tmp_path / "2026-09-01_120000.json").write_text(json.dumps(snap), encoding="utf-8")
    monkeypatch.setattr("api.routes.snapshots.SNAPSHOTS_DIR", tmp_path)
    db = RecordingSession({"scope_status = 'retired'": [SimpleNamespace(id="gone-1")]})
    with patch(
        "api.routes.snapshots.get_active_pins",
        return_value={"ancient_nerds": "2026-09-01_120000"},
    ):
        resp = _all(db, source=["ancient_nerds"])
    assert [s["id"] for s in resp["sites"]] == ["keep-1"]
    assert resp["dataSource"] == "snapshot"
    retired_sql = db.statement_with("scope_status = 'retired'")
    assert "source_id = ANY(:sources)" in retired_sql


# --------------------------------------------------------------------------------------
# /viewport, /clustered, /random, /search
# --------------------------------------------------------------------------------------


def test_viewport_filters_retired_sites():
    db = RecordingSession()
    sr.get_sites_in_viewport(
        req=None, min_lat=40, max_lat=45, min_lon=10, max_lon=15, source=None, limit=10, db=db
    )
    assert BARE in _where(db.statement_with("FROM unified_sites"))


def test_clustered_filters_retired_sites():
    db = RecordingSession()
    sr.get_clustered_sites(req=None, resolution=3, source=None, db=db)
    assert BARE in _where(db.statement_with("FROM unified_sites"))


def test_random_filters_retired_sites_in_the_counts_and_in_every_slice():
    db = RecordingSession(
        {"GROUP BY source_id": [SimpleNamespace(source_id="ancient_nerds", cnt=5004)]}
    )
    sr.random_sites(req=None, limit=10, db=db)
    assert BARE in _where(db.statement_with("GROUP BY source_id"))
    lateral = db.statement_with("CROSS JOIN LATERAL")
    assert f"u.source_id = alloc.source_id AND {U}" in lateral


def test_search_filters_retired_sites_outside_the_name_alternatives():
    """The name matches are ORs; the scope predicate must bind to all of them."""
    db = RecordingSession()
    sr.search_sites(req=None, q="damascus", limit=20, db=db)
    sql = db.statement_with("FROM unified_sites us")
    where = _where(sql)
    assert where.lstrip().startswith("(unaccent(us.name_normalized) = :norm")
    assert f") AND {US}" in " ".join(where.split())


# --------------------------------------------------------------------------------------
# /{site_id} and /{site_id}/alternates
# --------------------------------------------------------------------------------------


def _detail_row(scope_status):
    return SimpleNamespace(
        id=SITE_ID,
        source_id="ancient_nerds",
        source_record_id="an-1",
        name="Damascus Gate",
        lat=33.5,
        lon=36.3,
        site_type="Gate/archway/bridge",
        period_start=1537,
        period_end=None,
        period_name="1500+ AD",
        country="Syria",
        description="A gate.",
        thumbnail_url=None,
        source_url=None,
        raw_data=None,
        scope_status=scope_status,
        card_description=None,
        best_wiki_url=None,
        source_language=None,
    )


def test_a_retired_id_answers_410():
    db = RecordingSession({"WHERE us.id::text = :site_id": [_detail_row("retired")]})
    with pytest.raises(HTTPException) as exc:
        sr.get_site_detail(SITE_ID, db=db)
    assert exc.value.status_code == 410


@pytest.mark.parametrize("status", [None, "in_scope", "pending"])
def test_a_shown_id_answers_200(status):
    db = RecordingSession({"WHERE us.id::text = :site_id": [_detail_row(status)]})
    resp = sr.get_site_detail(SITE_ID, db=db)
    assert resp["name"] == "Damascus Gate"


def test_an_unknown_id_stays_404():
    with pytest.raises(HTTPException) as exc:
        sr.get_site_detail(SITE_ID, db=RecordingSession())
    assert exc.value.status_code == 404


def test_a_name_lookup_never_resolves_to_a_retired_site():
    db = RecordingSession()
    with pytest.raises(HTTPException) as exc:
        sr.get_site_detail("Damascus Gate", db=db)
    assert exc.value.status_code == 404
    sql = db.statement_with("unaccent(us.name) ILIKE")
    assert f") AND {US}" in " ".join(_where(sql).split())


def test_alternates_of_a_retired_site_answer_410():
    db = RecordingSession(
        {
            "SELECT id, lat, lon, scope_status": [
                SimpleNamespace(id=SITE_ID, lat=1, lon=2, scope_status="retired")
            ]
        }
    )
    with pytest.raises(HTTPException) as exc:
        sr.get_site_alternates(SITE_ID, db=db)
    assert exc.value.status_code == 410


def test_alternates_never_list_a_retired_row():
    db = RecordingSession(
        {
            "SELECT id, lat, lon, scope_status": [
                SimpleNamespace(id=SITE_ID, lat=1, lon=2, scope_status=None)
            ]
        }
    )
    sr.get_site_alternates(SITE_ID, db=db)
    assert US in db.statement_with("DISTINCT ON (us.source_id)")


# --------------------------------------------------------------------------------------
# DELETE /{site_id} - curated sites are retired, never deleted
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("source", ["ancient_nerds", "lyra", "ancient_nerds_community"])
def test_delete_refuses_every_curated_source_and_deletes_nothing(source):
    db = RecordingSession(
        {
            "SELECT id, name, source_id": [
                SimpleNamespace(id=SITE_ID, name="Petra", source_id=source)
            ]
        }
    )
    with pytest.raises(HTTPException) as exc:
        sr.delete_site(SITE_ID, user=SimpleNamespace(username="founder"), db=db)
    assert exc.value.status_code == 409
    assert "E4" in exc.value.detail and "scope_status" in exc.value.detail
    assert not [sql for sql in db.statements() if sql.lstrip().startswith("DELETE")]
    assert db.commits == 0


def test_delete_of_another_source_snapshots_before_it_deletes():
    db = RecordingSession(
        {
            "SELECT id, name, source_id": [
                SimpleNamespace(id=SITE_ID, name="Tell X", source_id="wikidata")
            ]
        }
    )
    calls: list[str] = []

    def snapshot(session, ids, **kw):
        calls.append("snapshot")
        assert kw["snapshot_type"] == "delete" and kw["source_id"] == "wikidata"
        assert ids == [SITE_ID]
        assert not [s for s in session.statements() if s.lstrip().startswith("DELETE")]
        return "snap-1"

    with patch("api.services.snapshots.create_snapshot", side_effect=snapshot):
        resp = sr.delete_site(SITE_ID, user=SimpleNamespace(username="founder"), db=db)
    assert calls == ["snapshot"]
    assert resp["snapshot_id"] == "snap-1"
    deletes = [sql for sql in db.statements() if sql.lstrip().startswith("DELETE")]
    assert len(deletes) == 2 and db.commits == 1


def test_delete_without_a_snapshot_deletes_nothing():
    db = RecordingSession(
        {
            "SELECT id, name, source_id": [
                SimpleNamespace(id=SITE_ID, name="Tell X", source_id="osm")
            ]
        }
    )
    with (
        patch("api.services.snapshots.create_snapshot", return_value=None),
        pytest.raises(HTTPException) as exc,
    ):
        sr.delete_site(SITE_ID, user=SimpleNamespace(username="founder"), db=db)
    assert exc.value.status_code == 500
    assert not [sql for sql in db.statements() if sql.lstrip().startswith("DELETE")]


# --------------------------------------------------------------------------------------
# restore-all-uploads carries the scope columns
# --------------------------------------------------------------------------------------


def test_restore_all_uploads_restores_the_scope_columns():
    db = RecordingSession({"COUNT(DISTINCT sr.site_id)": [(3,)]})
    with patch.object(sr, "cache_delete_pattern", lambda p: 0):
        sr.restore_all_upload_snapshots(_user=SimpleNamespace(username="f"), db=db)
    update = db.statement_with("UPDATE unified_sites us SET")
    assert "scope_status = snap.old_data->>'scope_status'" in update
    assert "scope_reason = snap.old_data->>'scope_reason'" in update


# --------------------------------------------------------------------------------------
# rebuild-static is a background job
# --------------------------------------------------------------------------------------


def test_rebuild_static_starts_a_job_and_returns_at_once():
    with patch.object(
        sr, "start_job", return_value={"job": "rebuild-static", "state": "running"}
    ) as start:
        resp = sr.rebuild_static_json(user=SimpleNamespace(username="founder"))
    assert resp["state"] == "running"
    name, work = start.call_args.args
    assert name == sr.REBUILD_STATIC_JOB and work is sr._run_static_export
    route = next(r for r in sr.router.routes if r.path == "/rebuild-static")
    assert route.status_code == 202


def test_rebuild_static_refuses_a_second_run_with_409():
    with (
        patch.object(sr, "start_job", side_effect=JobAlreadyRunning("rebuild-static")),
        pytest.raises(HTTPException) as exc,
    ):
        sr.rebuild_static_json(user=SimpleNamespace(username="founder"))
    assert exc.value.status_code == 409


def test_the_export_runs_in_a_child_process():
    """The 1.76M-site index must not be built inside the serving API process."""
    with patch.object(sr, "run_module", return_value={"elapsed_seconds": 1.0}) as run:
        assert sr._run_static_export() == {"elapsed_seconds": 1.0}
    assert run.call_args.args == ("pipeline.static_exporter",)
    assert run.call_args.kwargs["timeout_s"] == sr._REBUILD_STATIC_TIMEOUT_S


def test_rebuild_static_status_reads_the_shared_job_row():
    db = RecordingSession()
    with patch.object(sr, "read_status", return_value={"state": "ok"}) as read:
        assert sr.rebuild_static_status(_user=None, db=db) == {"state": "ok"}
    assert read.call_args.args == (db, sr.REBUILD_STATIC_JOB)
