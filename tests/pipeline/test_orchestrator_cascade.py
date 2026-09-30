"""The watch loop runs beside the event cascade (the nesting defect, fixed 2026-09-26).

Before the fix the whole run executed inside `await decomposition.decompose()`,
so the deadline check, the 30 s DB flush and the external-cancellation check
never ran in any production run since 2026-08-20.
"""

from __future__ import annotations

import asyncio

import pytest

from pipeline.lyra import convergence_orchestrator as co
from pipeline.lyra.minimax_limiter import QuotaExhaustedError
from pipeline.lyra.research_state import ResearchState

REQ = "11111111-2222-3333-4444-555555555555"


class _Deadline:
    def __init__(self) -> None:
        self.calls = 0

    async def check_deadline(self) -> bool:
        self.calls += 1
        return False


@pytest.fixture
def flushes(monkeypatch) -> list[str]:
    recorded: list[str] = []
    monkeypatch.setattr(co, "_TICK_S", 0.01)
    monkeypatch.setattr(co, "_UNWIND_GRACE_S", 1.0)
    monkeypatch.setattr(co, "_flush_progress_to_db", lambda state, rid: recorded.append(rid))
    monkeypatch.setattr(co, "_check_external_cancellation", lambda rid: None)
    return recorded


def _state() -> ResearchState:
    return ResearchState(question="Who cut the Baalbek monoliths?", request_id=REQ)


async def _drive(state, cascade, done, *, deadline=None, emit=None):
    await co._drive_cascade(
        state,
        cascade,
        done,
        deadline or _Deadline(),
        request_id=REQ,
        emit=emit or (lambda event: None),
        t0=0.0,
    )


async def test_the_done_signal_ends_the_watch(flushes):
    state, done = _state(), asyncio.Event()

    async def cascade():
        done.set()

    await _drive(state, cascade(), done)
    assert state.error == ""


async def test_a_cascade_that_ends_without_the_done_signal_is_an_error(flushes):
    state, done = _state(), asyncio.Event()

    async def cascade():
        return None

    await _drive(state, cascade(), done)
    assert state.error == co._NO_DOSSIER_ERROR


async def test_the_watch_ticks_while_the_cascade_runs(flushes):
    state, done = _state(), asyncio.Event()
    events: list[dict] = []
    deadline = _Deadline()

    async def cascade():
        await asyncio.sleep(0.2)
        done.set()

    await _drive(state, cascade(), done, deadline=deadline, emit=events.append)
    assert flushes, "the 30 s DB flush never ran during the cascade"
    assert deadline.calls >= 2
    assert any(event["type"] == "progress" for event in events)


async def test_external_cancellation_now_stops_the_cascade(flushes, monkeypatch):
    state, done = _state(), asyncio.Event()
    cancelled: list[bool] = []

    def cancelled_in_db(rid):
        raise co._CancelledByUser(f"{rid} status changed to 'cancelled'")

    monkeypatch.setattr(co, "_check_external_cancellation", cancelled_in_db)

    async def cascade():
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelled.append(True)
            raise

    with pytest.raises(co._CancelledByUser):
        await _drive(state, cascade(), done)
    assert cancelled == [True]


async def test_a_quota_error_in_the_cascade_propagates(flushes):
    state, done = _state(), asyncio.Event()

    async def cascade():
        raise QuotaExhaustedError("weekly wall")

    with pytest.raises(QuotaExhaustedError):
        await _drive(state, cascade(), done)


async def test_a_handler_error_stops_the_run_at_the_next_tick(flushes):
    state, done = _state(), asyncio.Event()
    cancelled: list[bool] = []

    async def cascade():
        state.error = "Handler failed on ContentFetched: RuntimeError('boom')"
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelled.append(True)
            raise

    await _drive(state, cascade(), done)
    assert cancelled == [True]
    assert state.error.startswith("Handler failed")


async def test_the_cascade_may_unwind_after_the_done_signal(flushes):
    state, done = _state(), asyncio.Event()
    unwound: list[bool] = []

    async def cascade():
        done.set()
        await asyncio.sleep(0.05)
        unwound.append(True)

    await _drive(state, cascade(), done)
    assert unwound == [True]


async def test_a_cascade_that_raises_right_after_the_done_signal_is_still_done(flushes):
    """Whether the cascade's exception arrives in the same wait as the done signal or later
    must not decide the run: the dossier is complete either way, the error is logged."""
    state, done = _state(), asyncio.Event()

    async def cascade():
        done.set()
        raise RuntimeError("unwinding failed")

    await _drive(state, cascade(), done)
    assert state.error == ""
    assert any("Cascade raised after the run was done" in entry["msg"] for entry in state.debug_log)


async def test_a_cancelled_watch_never_leaves_the_cascade_running(flushes):
    """The worker's stall guard and hard timeout cancel the run from outside, also while a
    finished run's cascade is still unwinding."""
    state, done = _state(), asyncio.Event()
    unwinding = asyncio.Event()
    cancelled: list[bool] = []

    async def cascade():
        done.set()
        unwinding.set()
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelled.append(True)
            raise

    watch = asyncio.create_task(_drive(state, cascade(), done))
    await unwinding.wait()
    await asyncio.sleep(0.05)  # the watch is inside the unwind grace wait now
    watch.cancel()
    with pytest.raises(asyncio.CancelledError):
        await watch
    await asyncio.sleep(0)
    assert cancelled == [True]
