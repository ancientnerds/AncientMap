"""EventBus must flag quota exhaustion on the state (2026-07-06 fix).

The bus catches ALL handler exceptions into state.error ("Handler failed
on X: ...") to unblock the orchestrator's deadline loop. That swallowed
QuotaExhaustedError before it could reach the worker's defer branch —
every quota death was marked 'failed' (E2E 2026-07-05, plus the 6 tasks
on 2026-06-28). Re-raising through the bus would hang done_event.wait(),
so instead the bus sets state.quota_exhausted for the worker to route on.
"""

import pytest

from pipeline.lyra.minimax_limiter import QuotaExhaustedError
from pipeline.lyra.research_events import ContentFetched, EventBus
from pipeline.lyra.research_state import ResearchState


@pytest.mark.asyncio
async def test_quota_error_in_handler_sets_flag_and_error():
    state = ResearchState(question="test")
    bus = EventBus(state=state)

    async def quota_dying_handler(event):
        raise QuotaExhaustedError("MiniMax quota exhausted — calls frozen for 1656s more.")

    bus.on(ContentFetched, quota_dying_handler)
    await bus.emit(ContentFetched(angle_id="a1"))

    assert state.quota_exhausted is True
    assert "Handler failed on ContentFetched" in state.error


@pytest.mark.asyncio
async def test_wrapped_quota_error_string_sets_flag():
    """minimax_shared wraps limiter errors into plain RuntimeErrors
    ('Minimax API error: MiniMax quota exhausted ...') — the string
    classifier must catch those too."""
    state = ResearchState(question="test")
    bus = EventBus(state=state)

    async def wrapped_handler(event):
        raise RuntimeError("Minimax API error: MiniMax quota exhausted — calls frozen for 300s")

    bus.on(ContentFetched, wrapped_handler)
    await bus.emit(ContentFetched(angle_id="a1"))

    assert state.quota_exhausted is True


@pytest.mark.asyncio
async def test_plain_handler_error_does_not_set_flag():
    state = ResearchState(question="test")
    bus = EventBus(state=state)

    async def plain_dying_handler(event):
        raise ValueError("something unrelated broke")

    bus.on(ContentFetched, plain_dying_handler)
    await bus.emit(ContentFetched(angle_id="a1"))

    assert state.quota_exhausted is False
    assert "Handler failed on ContentFetched" in state.error
