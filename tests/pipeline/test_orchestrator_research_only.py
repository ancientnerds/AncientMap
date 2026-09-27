"""Theo researches only: the run ends at the dossier (spec 2.1)."""

from __future__ import annotations

import asyncio
import importlib.util

from pipeline.lyra import convergence_orchestrator as co
from pipeline.lyra import research_events
from pipeline.lyra.research_events import DossierReady, EventBus, ModeratorComplete
from pipeline.lyra.research_state import ResearchPhase, ResearchState

REMOVED_HANDLERS = {
    "PaperHandler",
    "ProbativeImagesHandler",
    "FactCheckHandler",
    "PresentationHandler",
    "ImageGenerationHandler",
    "JudgeHandler",
}


def test_the_run_ends_at_the_dossier_handler():
    state = ResearchState(question="q", request_id="r")
    bus = EventBus(state=state)
    wiring = co._build_handlers(state, bus, asyncio.Semaphore(1))
    names = [type(handler).__name__ for handler in wiring.handlers]
    assert names.index("DossierHandler") == names.index("ModeratorHandler") + 1
    assert not REMOVED_HANDLERS & set(names)
    listeners = bus._handlers[ModeratorComplete]
    assert [type(listener.__self__).__name__ for listener in listeners] == ["DossierHandler"]
    assert type(wiring.decomposition).__name__ == "DecompositionHandler"
    assert type(wiring.deadline).__name__ == "DeadlineHandler"


async def test_dossier_ready_is_the_done_signal():
    state = ResearchState(question="q")
    bus = EventBus(state=state)
    events: list[dict] = []
    done = co._wire_done_signal(bus, state, events.append)
    await bus.emit(DossierReady(request_id="r1"))
    assert done.is_set()
    assert events[-1]["type"] == "status"


def test_the_dossier_guard_fails_a_run_without_a_dossier():
    state = ResearchState(question="q")
    co._dossier_guard(state)
    assert state.error == co._DOSSIER_GUARD_ERROR


def test_the_dossier_guard_keeps_an_earlier_error_and_passes_a_dossier():
    failed = ResearchState(question="q", error="Decomposition produced no research angles")
    co._dossier_guard(failed)
    assert failed.error == "Decomposition produced no research angles"
    done = ResearchState(question="q", dossier_ref=8)
    co._dossier_guard(done)
    assert done.error == ""


def test_the_writing_chain_is_gone():
    for name in (
        "PaperReady",
        "ProbativeImagesReady",
        "FactCheckComplete",
        "PresentationChecked",
        "ImageGenComplete",
        "QualityPassed",
        "QualityFailed",
    ):
        assert not hasattr(research_events, name), name
    assert {phase.name for phase in ResearchPhase} == {
        "DECOMPOSING",
        "EXPLORING",
        "SYNTHESIZING",
        "DEBATING",
        "MODERATING",
        "DONE",
    }
    for module in ("paper", "fact_check", "presentation", "image_generation", "judge"):
        assert importlib.util.find_spec(f"pipeline.lyra.handlers.{module}") is None, module
    from pipeline.lyra.handlers import probative_images

    assert not hasattr(probative_images, "ProbativeImagesHandler")
    assert callable(probative_images.embed_probative_images)
    assert not hasattr(co, "_empty_paper_error")
