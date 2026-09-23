# SPDX-License-Identifier: AGPL-3.0-only
"""POST /api/library/refresh answers at once and runs the refresh as a background job.

The deploy curls it with --max-time 120 and reported a failure whenever the synchronous
refresh took longer - which it did, the site scan alone took 112 s (2026-09-22).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from api.routes import library
from api.services.background_jobs import JobAlreadyRunning
from tests.fake_sql import RecordingSession

REPO = Path(__file__).resolve().parents[2]


def _req(key: str | None) -> SimpleNamespace:
    headers = {"X-Internal-Key": key} if key is not None else {}
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host="127.0.0.1"))


@pytest.fixture(autouse=True)
def _key_and_limits(monkeypatch):
    monkeypatch.setenv("LIBRARY_REFRESH_KEY", "k3y")
    monkeypatch.setattr(library, "get_client_ip", lambda req: "127.0.0.1")
    monkeypatch.setattr(library._refresh_limiter, "check", lambda ip: True)


def test_refresh_starts_the_job_and_returns_202():
    with patch.object(
        library, "start_job", return_value={"job": "library-refresh", "state": "running"}
    ) as start:
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
        patch(
            "pipeline.library_aggregator.aggregate_library",
            side_effect=lambda: calls.append("aggregate") or 14241,
        ),
        patch(
            "pipeline.static_exporter.StaticExporter._export_library",
            side_effect=lambda self=None: calls.append("export"),
        ),
    ):
        assert library._refresh_library_job() == {"sources": 14241}
    assert calls == ["aggregate", "export"]


def test_status_reads_the_shared_job_row():
    db = RecordingSession()
    with patch.object(library, "read_status", return_value={"state": "ok"}) as read:
        assert library.refresh_library_status(_req("k3y"), db=db) == {"state": "ok"}
    assert read.call_args.args == (db, library.LIBRARY_REFRESH_JOB)


# --------------------------------------------------------------------------------------
# the deploy's library step (.github/workflows/ci.yml)
# --------------------------------------------------------------------------------------


def _deploy_library_step() -> str:
    ci = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    start = ci.index('echo "==> Refreshing library data..."')
    end = ci.index('echo "==> Restarting log streaming..."')
    return ci[start:end]


def _code(block: str) -> str:
    return "\n".join(line for line in block.splitlines() if not line.strip().startswith("#"))


def test_the_deploy_reports_the_refresh_outcome_not_its_start():
    """The POST answers 202 as soon as the job starts. The deploy printed 'Library
    refreshed' on that alone, so a refresh that failed a minute later looked like a
    success in every deploy log. It now polls the status endpoint and reports the state
    the job ended in, with the job's error."""
    code = _code(_deploy_library_step())
    assert "curl -sf --max-time 30 -X POST" in code and "/api/library/refresh >" in code
    assert "http://localhost:8000/api/library/refresh/status" in code
    assert '[ "$LIB_STATE" = "running" ] || break' in code
    assert code.count("Library refreshed") == 1
    assert code.index('if [ "$LIB_STATE" = "ok" ]; then') < code.index("Library refreshed")
    assert ".error // empty" in code
    assert "WARNING: Library refresh did not start (non-fatal)" in code


def test_the_deploy_library_step_survives_set_e_and_the_ssh_quoting():
    """The deploy body runs under `set -e` inside ONE single-quoted ssh argument: a bare
    single quote ends that argument early (the 2026-08-08 truncation), and a failing
    command substitution in an assignment aborts the whole deploy."""
    block = _deploy_library_step()
    assert "'" not in block
    polls = [line for line in _code(block).splitlines() if "LIB_" in line and "=$(" in line]
    assert len(polls) == 2
    for line in polls:
        assert line.rstrip().endswith((' || echo "{}")', " || echo unreadable)")), line
