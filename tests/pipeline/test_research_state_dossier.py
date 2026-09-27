"""Research-only state: the dossier fields, MODERATING, DossierReady, findings by specialist."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from pipeline.lyra import convergence_orchestrator
from pipeline.lyra.handlers import moderator
from pipeline.lyra.handlers.deadline import DeadlineHandler
from pipeline.lyra.handlers.moderator import ModeratorHandler
from pipeline.lyra.research_events import DebateComplete, DossierReady, EventBus, ModeratorComplete
from pipeline.lyra.research_state import (
    ResearchAngle,
    ResearchPhase,
    ResearchState,
    findings_by_specialist,
)


def test_findings_grouped_by_specialist_keep_their_angle():
    angles = [
        ResearchAngle(
            id="a1",
            topic="Quarry",
            description="d",
            findings=[{"claim": "c1", "specialist_id": "geo"}, {"claim": "c2"}],
        ),
        ResearchAngle(
            id="a2",
            topic="Temple",
            description="d",
            findings=[{"claim": "c3", "specialist_id": "geo"}],
        ),
    ]
    assert findings_by_specialist(angles) == {
        "geo": [
            {"claim": "c1", "specialist_id": "geo", "angle_id": "a1"},
            {"claim": "c3", "specialist_id": "geo", "angle_id": "a2"},
        ],
        "unknown": [{"claim": "c2", "angle_id": "a1"}],
    }


def test_state_starts_without_a_dossier():
    state = ResearchState(question="q")
    assert state.dossier_ref is None
    assert state.dossier_summary == {}


def test_moderating_phase_exists():
    assert ResearchPhase.MODERATING.value == "moderating"


def test_dossier_ready_carries_the_request():
    assert DossierReady(request_id="r1").request_id == "r1"


async def test_imminent_deadline_forces_moderation_once():
    state = ResearchState(question="q")
    state.phase = ResearchPhase.DEBATING
    state.deadline = datetime.now(UTC) + timedelta(minutes=30)
    bus = EventBus(state=state)
    fired: list[ResearchPhase] = []

    async def on_debate_complete(event: DebateComplete):
        fired.append(state.phase)

    bus.on(DebateComplete, on_debate_complete)
    handler = DeadlineHandler(state, bus, asyncio.Semaphore(1))

    assert await handler.check_deadline() is True
    assert fired == [ResearchPhase.MODERATING]
    # MODERATING is outside (SYNTHESIZING, DEBATING): the next tick forces nothing.
    assert await handler.check_deadline() is False
    assert fired == [ResearchPhase.MODERATING]


async def test_moderator_runs_once_per_run(monkeypatch):
    # The forced-deadline path emits DebateComplete while the debate still runs;
    # the debate's own DebateComplete follows later and must not moderate again,
    # or it rewrites state.moderated_result while the DossierHandler persists it.
    calls: list[str] = []

    def fake_llm(*args, **kwargs):
        calls.append("llm")
        return {
            "final_claims": [{"claim": "c", "source_ids": ["s"]}],
            "revised_claims": [],
            "speculative_claims": [],
            "dropped_claims": [],
        }

    monkeypatch.setattr(moderator, "structured_llm_call", fake_llm)
    monkeypatch.setattr(
        moderator, "_get_settings", lambda: SimpleNamespace(temperature_verification=0.1)
    )
    monkeypatch.setattr(convergence_orchestrator, "_flush_progress_to_db", lambda state, rid: None)
    state = ResearchState(question="q")
    bus = EventBus(state=state)
    ModeratorHandler(state, bus, asyncio.Semaphore(1)).register()
    completed: list[ModeratorComplete] = []

    async def on_moderator_complete(event: ModeratorComplete):
        completed.append(event)

    bus.on(ModeratorComplete, on_moderator_complete)

    await bus.emit(DebateComplete())
    await bus.emit(DebateComplete())

    assert calls == ["llm"]
    assert len(completed) == 1
    assert state.moderated_result["final_claims"] == [{"claim": "c", "source_ids": ["s"]}]
    assert state.phase is ResearchPhase.MODERATING
    assert state.error == ""
