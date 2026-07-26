"""Tests for the no-progress stall guard in api.services.theo_worker.

A stalled run freezes its DB progress counters; a healthy run keeps advancing
them. The guard must cancel the former without ever killing the latter.
"""

import asyncio

import pytest

from api.services import theo_worker as tw


@pytest.mark.asyncio
async def test_stall_guard_cancels_frozen_run(monkeypatch):
    """Frozen counters past the grace window => _StallDetected + task cancelled."""
    monkeypatch.setattr(tw, "_STALL_GRACE_SECONDS", 0.3)
    monkeypatch.setattr(tw, "_STALL_POLL_SECONDS", 0.05)
    monkeypatch.setattr(tw, "_read_progress_sig", lambda rid: (0, 0, 0, 0))  # never moves

    cancelled = {"v": False}

    async def fake_process(rid, q, opts, is_batch=False):
        try:
            await asyncio.sleep(100)
        except asyncio.CancelledError:
            cancelled["v"] = True
            raise

    monkeypatch.setattr(tw, "_process_request", fake_process)

    with pytest.raises(tw._StallDetected):
        await tw._run_with_stall_guard("rid", "q", None, False)
    assert cancelled["v"] is True


@pytest.mark.asyncio
async def test_stall_guard_passes_through_normal_completion(monkeypatch):
    """A run that finishes returns normally even with flat counters."""
    monkeypatch.setattr(tw, "_STALL_GRACE_SECONDS", 5)
    monkeypatch.setattr(tw, "_STALL_POLL_SECONDS", 0.05)
    monkeypatch.setattr(tw, "_read_progress_sig", lambda rid: (0, 0, 0, 0))

    async def fake_process(rid, q, opts, is_batch=False):
        await asyncio.sleep(0.1)
        return None

    monkeypatch.setattr(tw, "_process_request", fake_process)

    await tw._run_with_stall_guard("rid", "q", None, False)  # must not raise


@pytest.mark.asyncio
async def test_stall_guard_allows_slow_but_progressing_run(monkeypatch):
    """Counters that keep changing must NOT trip the guard, even past the grace."""
    monkeypatch.setattr(tw, "_STALL_GRACE_SECONDS", 0.3)
    monkeypatch.setattr(tw, "_STALL_POLL_SECONDS", 0.05)

    n = {"v": 0}

    def moving_sig(rid):
        n["v"] += 1
        return (n["v"], 0, 0, 0)  # always advancing

    monkeypatch.setattr(tw, "_read_progress_sig", moving_sig)

    async def fake_process(rid, q, opts, is_batch=False):
        await asyncio.sleep(0.6)  # well past the 0.3s grace, but progress keeps moving
        return None

    monkeypatch.setattr(tw, "_process_request", fake_process)

    await tw._run_with_stall_guard("rid", "q", None, False)  # must not raise
