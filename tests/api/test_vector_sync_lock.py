# SPDX-License-Identifier: AGPL-3.0-only
"""One Qdrant reindex at a time across api and api2 (plan 10.7).

Both instances start the nightly scheduler and both logged "Starting nightly auto-reindex"
at 03:00 UTC. The runs are now serialised by the advisory lock of
api/services/background_jobs.InstanceLock (its semantics are tested in
test_background_jobs.py); these tests pin how the scheduler and the manual route use it.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.routes import vector_sync as vs
from tests.fake_sql import RecordingSession


class FakeLock:
    """InstanceLock stand-in: grants or refuses, and records releases."""

    free = True
    events: list[str] = []

    def __init__(self, name: str) -> None:
        assert name == vs.REINDEX_LOCK
        self.held = False

    def try_acquire(self) -> bool:
        if not FakeLock.free:
            return False
        FakeLock.free = False
        self.held = True
        FakeLock.events.append("acquire")
        return True

    def release(self) -> None:
        assert self.held, "released a lock it did not hold"
        self.held = False
        FakeLock.free = True
        FakeLock.events.append("release")


@pytest.fixture(autouse=True)
def fake_lock(monkeypatch):
    FakeLock.free = True
    FakeLock.events = []
    monkeypatch.setattr(vs, "InstanceLock", FakeLock)
    monkeypatch.setattr(vs, "_persist_state", lambda collection: None)
    return FakeLock


SCHEDULED = datetime(2026, 9, 23, 3, 0, tzinfo=UTC)


def test_the_second_instance_skips_while_the_first_holds_the_lock(monkeypatch):
    FakeLock.free = False  # api is running tonight's reindex
    ran: list[object] = []
    monkeypatch.setattr(vs, "_run_reindex_sequence", lambda *a: ran.append(a))
    assert asyncio.run(vs.nightly_reindex_once(SCHEDULED)) == "locked"
    assert ran == []


def test_a_late_wakeup_after_the_other_instance_finished_skips_too(monkeypatch):
    monkeypatch.setattr(vs, "_nightly_already_ran", lambda scheduled_for: True)
    ran: list[object] = []
    monkeypatch.setattr(vs, "_run_reindex_sequence", lambda *a: ran.append(a))
    assert asyncio.run(vs.nightly_reindex_once(SCHEDULED)) == "done"
    assert ran == []
    assert FakeLock.events == ["acquire", "release"]


def test_the_night_runs_once_and_releases_the_lock(monkeypatch):
    monkeypatch.setattr(vs, "_nightly_already_ran", lambda scheduled_for: False)

    class _Proc:
        returncode = 0

        async def communicate(self):
            return b"", b""

    async def fake_exec(*cmd, **kw):
        assert cmd[-1] == "scripts/build_lyra_index.py"
        return _Proc()

    monkeypatch.setattr(vs.asyncio, "create_subprocess_exec", fake_exec)
    assert asyncio.run(vs.nightly_reindex_once(SCHEDULED)) == "ran"
    assert FakeLock.events == ["acquire", "release"]
    assert vs._reindex_state["running"] is False


def test_an_error_before_the_run_still_releases_the_lock(monkeypatch):
    def broken(scheduled_for):
        raise RuntimeError("database gone")

    monkeypatch.setattr(vs, "_nightly_already_ran", broken)
    with pytest.raises(RuntimeError):
        asyncio.run(vs.nightly_reindex_once(SCHEDULED))
    assert FakeLock.events == ["acquire", "release"]


def test_a_failed_run_releases_the_lock(monkeypatch):
    monkeypatch.setattr(vs, "_nightly_already_ran", lambda scheduled_for: False)

    async def fake_exec(*cmd, **kw):
        raise OSError("no python")

    monkeypatch.setattr(vs.asyncio, "create_subprocess_exec", fake_exec)
    assert asyncio.run(vs.nightly_reindex_once(SCHEDULED)) == "ran"
    assert FakeLock.events == ["acquire", "release"]
    assert vs._reindex_state["last_result"].startswith("error:")


def test_already_ran_compares_with_the_naive_utc_column(monkeypatch):
    """vector_sync_state.last_completed_at is a naive UTC timestamp."""
    session = RecordingSession({"FROM vector_sync_state": [(datetime(2026, 9, 23, 3, 0, 34),)]})

    class _ctx:
        def __enter__(self):
            return session

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(vs, "get_session", lambda: _ctx())
    assert vs._nightly_already_ran(SCHEDULED) is True
    session.answers["FROM vector_sync_state"] = [(datetime(2026, 9, 22, 3, 0, 34),)]
    assert vs._nightly_already_ran(SCHEDULED) is False
    # only a SUCCESSFUL run counts: a failed one leaves the night to the other instance
    assert "last_result = 'success'" in session.statements()[0]


def test_a_manual_reindex_is_refused_while_any_instance_runs_one():
    FakeLock.free = False
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            vs.vector_reindex(vs.ReindexRequest(collection="sites"), _user=SimpleNamespace())
        )
    assert exc.value.status_code == 409
