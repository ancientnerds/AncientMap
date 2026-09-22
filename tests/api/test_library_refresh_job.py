# SPDX-License-Identifier: AGPL-3.0-only
"""POST /api/library/refresh answers at once and runs the refresh as a background job.

The deploy curls it with --max-time 120 and reported a failure whenever the synchronous
refresh took longer - which it did, the site scan alone took 112 s (2026-09-22).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from api.routes import library
from api.services.background_jobs import JobAlreadyRunning
from tests.fake_sql import RecordingSession


def _req(key: str | None) -> SimpleNamespace:
    headers = {"X-Internal-Key": key} if key is not None else {}
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host="127.0.0.1"))


@pytest.fixture(autouse=True)
def _key_and_limits(monkeypatch):
    monkeypatch.setenv("LIBRARY_REFRESH_KEY", "k3y")
    monkeypatch.setattr(library, "get_client_ip", lambda req: "127.0.0.1")
    monkeypatch.setattr(library._refresh_limiter, "check", lambda ip: True)


def test_refresh_starts_the_job_and_returns_202():
    with patch.object(library, "start_job", return_value={"job": "library-refresh", "state": "running"}) as start:
        resp = library.refresh_library(_req("k3y"))
    assert resp["state"] == "running"
    name, work = start.call_args.args
    assert name == library.LIBRARY_REFRESH_JOB and work is library._refresh_library_job
    route = next(r for r in library.router.routes if r.path == "/refresh")
    assert route.status_code == 202


def test_a_second_refresh_is_refused_with_409():
    with (
        patch.object(library, "start_job", side_effect=JobAlreadyRunning("library-refresh")),
        pytest.raises(HTTPException) as exc,
    ):
        library.refresh_library(_req("k3y"))
    assert exc.value.status_code == 409


@pytest.mark.parametrize("route", ["refresh_library", "refresh_library_status"])
def test_both_routes_require_the_internal_key(route):
    with patch.object(library, "start_job") as start, pytest.raises(HTTPException) as exc:
        if route == "refresh_library":
            library.refresh_library(_req("wrong"))
        else:
            library.refresh_library_status(_req("wrong"), db=RecordingSession())
    assert exc.value.status_code == 403
    start.assert_not_called()


def test_the_job_aggregates_and_then_exports():
    calls: list[str] = []
    with (
        patch("pipeline.library_aggregator.aggregate_library", side_effect=lambda: calls.append("aggregate") or 14241),
        patch("pipeline.static_exporter.StaticExporter._export_library", side_effect=lambda self=None: calls.append("export")),
    ):
        assert library._refresh_library_job() == {"sources": 14241}
    assert calls == ["aggregate", "export"]


def test_status_reads_the_shared_job_row():
    db = RecordingSession()
    with patch.object(library, "read_status", return_value={"state": "ok"}) as read:
        assert library.refresh_library_status(_req("k3y"), db=db) == {"state": "ok"}
    assert read.call_args.args == (db, library.LIBRARY_REFRESH_JOB)
