"""StatePersist passenger writes: specialist analyses carry findings; the dossier owns 'moderated'."""

from __future__ import annotations

import asyncio

import pytest

from pipeline.lyra import convergence_orchestrator
from pipeline.lyra.handlers import state_persist as sp
from pipeline.lyra.handlers.state_persist import StatePersistHandler
from pipeline.lyra.research_events import AllAnglesSaturated, EventBus, ModeratorComplete
from pipeline.lyra.research_state import ActiveSpecialist, ResearchAngle, ResearchState

REQ = "11111111-2222-3333-4444-555555555555"


@pytest.fixture
def saved(monkeypatch):
    rows: list[tuple] = []
    monkeypatch.setattr(
        sp,
        "save_artifact",
        lambda request_id, kind, payload, ref="", *, replace=False: rows.append(
            (request_id, kind, payload, ref, replace)
        ),
    )
    monkeypatch.setattr(convergence_orchestrator, "_flush_progress_to_db", lambda state, rid: None)
    return rows


def _handler(request_id: str) -> tuple[ResearchState, EventBus]:
    state = ResearchState(question="q", request_id=request_id)
    state.angles = [
        ResearchAngle(
            id="a1",
            topic="t",
            description="d",
            findings=[
                {"claim": "c1", "specialist_id": "geo"},
                {"claim": "c2", "specialist_id": "arch"},
            ],
        )
    ]
    state.panel = [ActiveSpecialist(specialist_id="geo", name="G", domain="geology")]
    bus = EventBus(state=state)
    StatePersistHandler(state, bus, asyncio.Semaphore(1)).register()
    return state, bus


async def test_specialist_analyses_carry_the_findings(saved):
    _state, bus = _handler(REQ)
    await bus.emit(AllAnglesSaturated())
    ((request_id, kind, payload, ref, replace),) = saved
    assert (request_id, kind, ref, replace) == (REQ, "specialist_analyses", "", True)
    assert payload["analyses"]["geo"] == [{"claim": "c1", "specialist_id": "geo", "angle_id": "a1"}]
    assert payload["panel"][0]["specialist_id"] == "geo"


async def test_moderated_is_left_to_the_dossier_handler(saved):
    _state, bus = _handler(REQ)
    await bus.emit(ModeratorComplete())
    assert saved == []


async def test_a_run_without_request_id_appends(saved):
    _state, bus = _handler("")
    await bus.emit(AllAnglesSaturated())
    ((request_id, _kind, _payload, _ref, replace),) = saved
    assert request_id is None
    assert replace is False
