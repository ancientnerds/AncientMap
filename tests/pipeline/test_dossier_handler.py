"""DossierHandler: the end of a research run (spec 2.1-2.3)."""

from __future__ import annotations

import asyncio

import pytest

from pipeline.lyra import convergence_orchestrator
from pipeline.lyra.archive_completion import ArchiveStats
from pipeline.lyra.handlers import dossier as dossier_module
from pipeline.lyra.handlers.dossier import DossierHandler
from pipeline.lyra.research_events import DossierReady, EventBus, ModeratorComplete
from pipeline.lyra.research_state import (
    ActiveSpecialist,
    ResearchAngle,
    ResearchPhase,
    ResearchState,
)

REQ = "11111111-2222-3333-4444-555555555555"
EXPECTED_KINDS = [
    "moderated",
    "synthesis",
    "debate",
    "angle_findings",
    "specialist_analyses",
    "citation_registry",
    "image_candidate_pool",
    "dossier",
]


@pytest.fixture
def saved(monkeypatch):
    rows: list[tuple] = []

    def fake_save(request_id, kind, payload, ref="", *, replace=False):
        rows.append((request_id, kind, ref, replace, payload))
        return len(rows)

    async def fake_complete(request_id, registry, moderated, angles, *, max_seconds, concurrency):
        assert (max_seconds, concurrency) == (1800.0, 4)
        return ArchiveStats(cited_sources=1, full_text=1, duration_s=2.5)

    monkeypatch.setattr(dossier_module, "save_artifact", fake_save)
    monkeypatch.setattr(dossier_module, "complete_archive", fake_complete)
    monkeypatch.setattr(dossier_module, "archive_completion_limits", lambda: (1800.0, 4))
    # EventBus.emit piggybacks a DB progress flush for runs with a request_id.
    monkeypatch.setattr(convergence_orchestrator, "_flush_progress_to_db", lambda state, rid: None)
    return rows


def _state() -> ResearchState:
    state = ResearchState(question="Who cut the Baalbek monoliths?", request_id=REQ)
    source = state.registry.register_source(
        url="https://a.example/survey", title="Survey", snippet="abstract"
    )
    state.angles = [
        ResearchAngle(
            id="ang1",
            topic="Quarry",
            description="The quarry",
            source_ids=[source],
            findings=[{"claim": "c1", "source_ids": [source], "specialist_id": "geo"}],
        )
    ]
    state.panel = [ActiveSpecialist(specialist_id="geo", name="Geologist", domain="geology")]
    state.synthesis = {"consensus_claims": []}
    state.cross_angle_connections = [{"from_angle": "ang1", "to_angle": "ang1", "description": "x"}]
    state.debate_result = {"rounds": 1}
    state.moderated_result = {
        "final_claims": [{"claim": "c1", "source_ids": [source]}],
        "revised_claims": [],
        "speculative_claims": [],
        "dropped_claims": [],
    }
    state.image_candidate_pool = {"ang1": [{"url": "https://commons.example/File:A.jpg"}]}
    return state


def _wire(state: ResearchState) -> tuple[EventBus, list[str]]:
    bus = EventBus(state=state)
    DossierHandler(state, bus, asyncio.Semaphore(1)).register()
    ready: list[str] = []

    async def on_ready(event: DossierReady):
        ready.append(event.request_id)

    bus.on(DossierReady, on_ready)
    return bus, ready


async def test_dossier_is_persisted_manifest_last_and_the_run_ends(saved):
    state = _state()
    bus, ready = _wire(state)

    await bus.emit(ModeratorComplete())

    assert [kind for _rid, kind, _ref, _replace, _payload in saved] == EXPECTED_KINDS
    assert all(replace for _rid, _kind, _ref, replace, _payload in saved)
    assert {rid for rid, *_rest in saved} == {REQ}
    assert saved[3][2] == "ang1"  # angle_findings is scoped by the angle id
    analyses = saved[4][4]["analyses"]
    assert analyses["geo"][0]["angle_id"] == "ang1"
    manifest = saved[-1][4]
    assert manifest["counts"]["final_claims"] == 1
    assert manifest["archive"]["full_text"] == 1
    assert manifest["angle_ids"] == ["ang1"]
    assert state.dossier_ref == len(EXPECTED_KINDS)
    assert state.dossier_summary["artifact_id"] == len(EXPECTED_KINDS)
    assert state.phase is ResearchPhase.DONE
    assert ready == [REQ]
    assert state.error == ""


async def test_a_second_moderator_complete_is_ignored(saved):
    state = _state()
    bus, ready = _wire(state)

    await bus.emit(ModeratorComplete())
    await bus.emit(ModeratorComplete())

    assert len(saved) == len(EXPECTED_KINDS)
    assert ready == [REQ]


async def test_no_final_claims_fails_the_run_without_a_dossier(saved):
    state = _state()
    state.moderated_result["final_claims"] = []
    bus, ready = _wire(state)

    await bus.emit(ModeratorComplete())

    assert saved == []
    assert ready == []
    assert state.dossier_ref is None
    assert state.error.startswith("Moderator produced no final claims")


async def test_a_dossier_write_failure_fails_the_run_loudly(saved, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(dossier_module, "save_artifact", broken)
    state = _state()
    bus, ready = _wire(state)

    await bus.emit(ModeratorComplete())

    assert state.error == "Handler failed on ModeratorComplete: RuntimeError('disk full')"
    assert ready == []
    assert state.dossier_ref is None
