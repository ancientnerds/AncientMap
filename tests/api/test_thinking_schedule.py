"""Schedule characterization for the nightly thinking pass (spec §3).

`thinking_pass_due`/`thinking_window_open` gate the pass to Mon-Thu
02:00-05:00 UTC; `_maybe_run_thinking_pass` (api.services.theo_worker) wires
that gate into the feeder loop without an unconditional DB read on every
10-minute poll.
"""

from datetime import UTC, datetime

import pytest

import pipeline.lyra.curator as curator
from api.services import theo_worker as tw
from pipeline.lyra.curator import thinking_pass_due


def test_weekend_nights_never_think():
    # Fri–Sun nights belong to the research runs (weekend batch gate).
    for day in (7, 8, 9):  # Fri, Sat, Sun 2026-08
        assert thinking_pass_due(datetime(2026, 8, day, 3, 0, tzinfo=UTC), None) is False


class _FakeRow:
    def __init__(self, ts):
        self.ts = ts


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeSession:
    def __init__(self, row):
        self._row = row

    def execute(self, *args, **kwargs):
        return _FakeResult(self._row)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.mark.asyncio
async def test_maybe_run_thinking_pass_window_shut_skips_db(monkeypatch):
    """The window check runs BEFORE any DB access — the window is shut
    ~93% of the week, so most feeder polls must not touch the database."""
    monkeypatch.setattr(curator, "thinking_window_open", lambda now: False)

    def _boom():
        raise AssertionError("must not call get_session while the window is shut")

    monkeypatch.setattr(tw, "get_session", _boom)

    await tw._maybe_run_thinking_pass()  # must not raise


@pytest.mark.asyncio
async def test_maybe_run_thinking_pass_coerces_naive_timestamp(monkeypatch):
    """thinking_log.created_at is `timestamp without time zone` — a naive ts
    from the fake row must be coerced to aware UTC before it reaches
    thinking_pass_due, which raises TypeError on a naive/aware mismatch."""
    monkeypatch.setattr(curator, "thinking_window_open", lambda now: True)
    naive_ts = datetime(2026, 8, 3, 2, 0)  # no tzinfo, like the raw DB column
    monkeypatch.setattr(tw, "get_session", lambda: _FakeSession(_FakeRow(naive_ts)))

    seen = {}

    def _fake_due(now, last_pass_at):
        seen["last_pass_at"] = last_pass_at
        return False

    monkeypatch.setattr(curator, "thinking_pass_due", _fake_due)

    await tw._maybe_run_thinking_pass()  # must not raise TypeError

    assert seen["last_pass_at"] == naive_ts.replace(tzinfo=UTC)
    assert seen["last_pass_at"].tzinfo is not None


@pytest.mark.asyncio
async def test_maybe_run_thinking_pass_handles_row_with_none_ts(monkeypatch):
    """MAX(created_at) with no prior curator rows returns a row whose ts is
    NULL — last_pass_at must become None, not blow up on `.replace`."""
    monkeypatch.setattr(curator, "thinking_window_open", lambda now: True)
    monkeypatch.setattr(tw, "get_session", lambda: _FakeSession(_FakeRow(None)))

    seen = {"last_pass_at": "unset"}

    def _fake_due(now, last_pass_at):
        seen["last_pass_at"] = last_pass_at
        return False

    monkeypatch.setattr(curator, "thinking_pass_due", _fake_due)

    await tw._maybe_run_thinking_pass()

    assert seen["last_pass_at"] is None


@pytest.mark.asyncio
async def test_maybe_run_thinking_pass_handles_no_row_at_all(monkeypatch):
    """Defensive branch: fetchone() itself returns None (no aggregate row) —
    last_pass_at must still become None rather than raising AttributeError."""
    monkeypatch.setattr(curator, "thinking_window_open", lambda now: True)
    monkeypatch.setattr(tw, "get_session", lambda: _FakeSession(None))

    seen = {"last_pass_at": "unset"}

    def _fake_due(now, last_pass_at):
        seen["last_pass_at"] = last_pass_at
        return False

    monkeypatch.setattr(curator, "thinking_pass_due", _fake_due)

    await tw._maybe_run_thinking_pass()

    assert seen["last_pass_at"] is None


@pytest.mark.asyncio
async def test_maybe_run_thinking_pass_runs_curator_when_due(monkeypatch):
    """When the window is open and the 20h cooldown has cleared, the
    curator pass actually fires."""
    monkeypatch.setattr(curator, "thinking_window_open", lambda now: True)
    monkeypatch.setattr(tw, "get_session", lambda: _FakeSession(_FakeRow(None)))
    monkeypatch.setattr(curator, "thinking_pass_due", lambda now, last_pass_at: True)

    called = {"v": False}
    monkeypatch.setattr(curator, "run_curator_pass", lambda: called.__setitem__("v", True))

    await tw._maybe_run_thinking_pass()

    assert called["v"] is True
