# SPDX-License-Identifier: AGPL-3.0-only
"""api/services/background_jobs.py: one run at a time across both API instances.

The advisory lock is exercised against a fake Postgres that keeps session-level locks the
way the server does: a lock belongs to the connection that took it, a second session cannot
take it, and closing the owning connection (a dying process) frees it. The fake refuses
plain SQL strings, as SQLAlchemy 2 does.
"""

from __future__ import annotations

import threading
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.exc import ArgumentError
from sqlalchemy.sql.elements import TextClause

from api.services import background_jobs as bj
from tests.fake_sql import FakeResult, RecordingSession


class FakePostgres:
    """Session-level advisory locks keyed by (namespace, key), owned by a connection."""

    def __init__(self) -> None:
        self.locks: dict[tuple[int, int], FakeConnection] = {}

    def connect(self) -> FakeConnection:
        return FakeConnection(self)


class FakeConnection:
    def __init__(self, server: FakePostgres) -> None:
        self.server = server
        self.closed = False

    def execute(self, stmt: Any, params: dict | None = None) -> FakeResult:
        if not isinstance(stmt, TextClause):
            raise ArgumentError("wrap raw SQL in text()")
        assert not self.closed, "statement on a closed connection"
        key = (params["ns"], params["key"])
        if "pg_try_advisory_lock" in stmt.text:
            owner = self.server.locks.get(key)
            if owner is None:
                self.server.locks[key] = self
                return FakeResult([(True,)])
            return FakeResult([(owner is self,)])
        if "pg_advisory_unlock" in stmt.text:
            if self.server.locks.get(key) is self:
                del self.server.locks[key]
                return FakeResult([(True,)])
            return FakeResult([(False,)])
        raise AssertionError(stmt.text)

    def close(self) -> None:
        # Postgres releases every session lock when the session ends.
        self.closed = True
        for key in [k for k, owner in self.server.locks.items() if owner is self]:
            del self.server.locks[key]


def test_the_lock_excludes_a_second_instance_until_released():
    pg = FakePostgres()
    api1 = bj.InstanceLock("rebuild-static", connect=pg.connect)
    api2 = bj.InstanceLock("rebuild-static", connect=pg.connect)
    assert api1.try_acquire()
    assert not api2.try_acquire()
    api1.release()
    assert api2.try_acquire()


def test_a_dead_process_cannot_leave_the_lock_behind():
    pg = FakePostgres()
    api1 = bj.InstanceLock("library-refresh", connect=pg.connect)
    assert api1.try_acquire()
    api1._conn.close()  # the container restarts mid-job
    assert bj.InstanceLock("library-refresh", connect=pg.connect).try_acquire()


def test_locks_of_different_jobs_do_not_collide():
    pg = FakePostgres()
    assert bj.InstanceLock("rebuild-static", connect=pg.connect).try_acquire()
    assert bj.InstanceLock("library-refresh", connect=pg.connect).try_acquire()
    assert bj.lock_id("rebuild-static") != bj.lock_id("library-refresh")
    assert 0 < bj.lock_id("vector-reindex") < 2**31


def _run_job(monkeypatch, work, lock) -> list[tuple[str, dict, str | None]]:
    written: list[tuple[str, dict, str | None]] = []
    monkeypatch.setattr(
        bj,
        "_write_status",
        lambda name, status, data, error=None: written.append((status, data, error)),
    )
    bj.start_job("demo", work, lock=lock)
    for thread in threading.enumerate():
        if thread.name == "job-demo":
            thread.join(timeout=10)
    return written


def test_a_job_records_running_then_ok_and_frees_the_lock(monkeypatch):
    pg = FakePostgres()
    lock = bj.InstanceLock("demo", connect=pg.connect)
    written = _run_job(monkeypatch, lambda: {"sources": 3}, lock)
    assert [status for status, _, _ in written] == ["running", "ok"]
    assert written[1][1]["result"] == {"sources": 3}
    assert "finished_at" in written[1][1]
    assert pg.locks == {}


def test_a_failing_job_records_the_error_and_frees_the_lock(monkeypatch):
    pg = FakePostgres()
    lock = bj.InstanceLock("demo", connect=pg.connect)

    def boom() -> dict:
        raise PermissionError("[Errno 13] Permission denied: 'public/data/sources.json'")

    written = _run_job(monkeypatch, boom, lock)
    assert [status for status, _, _ in written] == ["running", "error"]
    assert "PermissionError" in written[1][2] and "sources.json" in written[1][2]
    assert pg.locks == {}


def test_a_failed_running_write_frees_the_lock_and_raises(monkeypatch):
    """No status row, no job: the error propagates and the lock goes with it. The lock sits
    on a dedicated connection until the process exits, so keeping it would answer every
    later start on both instances with 409 until the next restart."""
    pg = FakePostgres()
    lock = bj.InstanceLock("demo", connect=pg.connect)

    def database_down(*_args, **_kwargs) -> None:
        raise ConnectionError("pipeline_heartbeats unreachable")

    monkeypatch.setattr(bj, "_write_status", database_down)
    with pytest.raises(ConnectionError):
        bj.start_job("demo", lambda: pytest.fail("the job must not run"), lock=lock)
    assert pg.locks == {}
    assert not any(t.name == "job-demo" for t in threading.enumerate())
    assert bj.InstanceLock("demo", connect=pg.connect).try_acquire()


def test_a_second_start_is_refused_while_the_first_runs(monkeypatch):
    pg = FakePostgres()
    holder = bj.InstanceLock("demo", connect=pg.connect)
    assert holder.try_acquire()
    monkeypatch.setattr(bj, "_write_status", lambda *a, **k: pytest.fail("must not write"))
    with pytest.raises(bj.JobAlreadyRunning):
        bj.start_job("demo", lambda: {}, lock=bj.InstanceLock("demo", connect=pg.connect))


def test_status_says_interrupted_when_nobody_holds_the_lock_of_a_running_row():
    db = RecordingSession(
        {
            "FROM pipeline_heartbeats": [
                SimpleNamespace(
                    status="running",
                    last_heartbeat=None,
                    last_error=None,
                    step_data={"started_at": "2026-09-22T20:00:00+00:00", "instance": "api"},
                )
            ],
            "FROM pg_locks": [(False,)],
        }
    )
    status = bj.read_status(db, "rebuild-static")
    assert status["state"] == "interrupted"
    assert status["started_at"] == "2026-09-22T20:00:00+00:00"
    pg_locks = db.statement_with("FROM pg_locks")
    assert "objsubid = 2" in pg_locks and "granted" in pg_locks


def test_status_of_a_job_that_never_ran():
    db = RecordingSession({"FROM pg_locks": [(False,)]})
    assert bj.read_status(db, "rebuild-static") == {"job": "rebuild-static", "state": "never_run"}


def test_run_module_raises_with_the_exit_code_and_output_tail():
    with pytest.raises(RuntimeError) as exc:
        bj.run_module("pipeline.this_module_does_not_exist", timeout_s=60)
    assert "exited 1" in str(exc.value)
    assert "No module named" in str(exc.value)


def test_run_module_reports_a_successful_child():
    result = bj.run_module("json.tool", "--help", timeout_s=60)
    assert result["elapsed_seconds"] >= 0
    assert "--compact" in result["output_tail"]  # the tail of json.tool's help text
