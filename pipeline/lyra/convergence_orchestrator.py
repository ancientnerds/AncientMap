"""Convergence-based research orchestrator.

Replaces the fixed-tier TheoPipeline with an event-driven state machine.
Questions are decomposed into research angles that converge independently
via specialist consensus, then synthesized into a Why Files narrative paper.

Usage (from theo_worker.py):
    orchestrator = ConvergenceOrchestrator()
    state = await orchestrator.run(question, emit, ...)
    # state has: paper_text, paper_title, audit_result, quality_score, etc.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from datetime import datetime, timedelta

from pipeline.lyra.config import _get_settings
from pipeline.lyra.research_events import (
    AngleCreated,
    CrossPollinationComplete,
    EventBus,
    QualityFailed,
    QualityPassed,
)
from pipeline.lyra.research_state import (
    ActiveSpecialist,
    ResearchConfig,
    ResearchPhase,
    ResearchState,
)
from pipeline.lyra.theo_specialists import select_specialists

logger = logging.getLogger(__name__)


class ConvergenceOrchestrator:
    """Event-driven research pipeline with convergence-based quality gates."""

    def __init__(self, settings=None):
        self._settings = settings or _get_settings()

    async def run(
        self,
        question: str,
        emit: Callable[[dict], None],
        *,
        request_id: str = "",
        force_include: list[str] | None = None,
        force_exclude: list[str] | None = None,
        video_ids: list[str] | None = None,
        web_urls: list[str] | None = None,
        disabled_adapters: list[str] | None = None,
    ) -> ResearchState:
        """Run the full convergence research pipeline.

        Returns a ResearchState compatible with the worker contract:
        paper_text, paper_title, card_description, audit_result,
        quality_score, error, total_tokens, llm_call_count, debug_log,
        registry (CitationRegistry).
        """
        config = ResearchConfig()
        state = ResearchState(
            question=question,
            request_id=request_id,
            seed_urls=list(web_urls or []),
            seed_video_ids=list(video_ids or []),
            force_include=list(force_include or []),
            force_exclude=list(force_exclude or []),
            disabled_adapters=list(disabled_adapters or []),
            config=config,
            emit=emit,
            started_at=datetime.utcnow(),
            deadline=datetime.utcnow() + timedelta(hours=config.deadline_hours),
        )

        state.log("orchestrator", f"Starting convergence pipeline for: {question[:80]}...")

        # Reset global rate limiter to max concurrency for this task
        from pipeline.lyra.minimax_limiter import limiter as global_limiter

        global_limiter.reset()

        # Set up event bus and handlers
        bus = EventBus()
        semaphore = asyncio.Semaphore(config.max_concurrent_llm_calls)

        # Lazy imports to avoid circular dependencies
        from pipeline.lyra.handlers.angle_audit import AuditHandler
        from pipeline.lyra.handlers.angle_search import SearchHandler
        from pipeline.lyra.handlers.angle_specialist import SpecialistHandler
        from pipeline.lyra.handlers.convergence_checker import ConvergenceChecker
        from pipeline.lyra.handlers.cross_pollination import CrossPollinationHandler
        from pipeline.lyra.handlers.deadline import DeadlineHandler
        from pipeline.lyra.handlers.debate import DebateHandler
        from pipeline.lyra.handlers.decomposition import DecompositionHandler
        from pipeline.lyra.handlers.judge import JudgeHandler
        from pipeline.lyra.handlers.paper import PaperHandler
        from pipeline.lyra.handlers.synthesis import SynthesisHandler

        # Instantiate handlers
        decomposition = DecompositionHandler(state, bus, semaphore)
        search = SearchHandler(state, bus, semaphore)
        audit = AuditHandler(state, bus, semaphore)
        specialist = SpecialistHandler(state, bus, semaphore)
        convergence = ConvergenceChecker(state, bus, semaphore)
        cross_poll = CrossPollinationHandler(state, bus, semaphore)
        synthesis = SynthesisHandler(state, bus, semaphore)
        debate = DebateHandler(state, bus, semaphore)
        paper = PaperHandler(state, bus, semaphore)
        judge = JudgeHandler(state, bus, semaphore)
        deadline_handler = DeadlineHandler(state, bus, semaphore)

        # Register all handlers on the bus
        all_handlers = [
            decomposition,
            search,
            audit,
            specialist,
            convergence,
            cross_poll,
            synthesis,
            debate,
            paper,
            judge,
            deadline_handler,
        ]
        for handler in all_handlers:
            handler.register()
            bus.register_instance(handler)

        # Wire quality failure -> re-exploration
        async def _on_quality_failed(event: QualityFailed):
            """Re-explore weak angles when quality judge fails."""
            state.log(
                "orchestrator", f"Quality failed (score={event.score}), weak: {event.weak_areas}"
            )
            emit(
                {
                    "type": "status",
                    "content": f"Quality check failed (score {event.score}), refining research...",
                }
            )

            # Un-saturate angles related to weak areas and trigger re-search
            for angle in state.angles:
                if angle.saturated:
                    angle.saturated = False
                    angle.recent_claim_counts = []  # reset convergence tracking

            state.phase = ResearchPhase.EXPLORING
            # Trigger refined search for each angle
            for angle in state.angles:
                gaps = [f"Quality judge flagged: {wa}" for wa in event.weak_areas]
                await search.refine_and_search(angle.id, gaps)

        bus.on(QualityFailed, _on_quality_failed)

        # Wire cross-pollination complete -> trigger round 2 via AngleCreated events.
        # This naturally flows: AngleCreated -> search -> audit -> specialist.
        # The specialist handler skips its own search trigger for round 2
        # (only triggers for round 3+), preventing double-triggering.
        async def _on_cross_pollination_complete(event: CrossPollinationComplete):
            """After cross-pollination, kick off round 2 for all unsaturated angles."""
            state.log("orchestrator", "Cross-pollination complete, starting round 2")
            emit({"type": "status", "content": "Cross-pollination complete -- starting round 2..."})
            for angle in state.angles:
                if not angle.saturated:
                    await bus.emit(AngleCreated(angle_id=angle.id))

        bus.on(CrossPollinationComplete, _on_cross_pollination_complete)

        # Wire quality passed -> done
        done_event = asyncio.Event()

        async def _on_quality_passed(event: QualityPassed):
            state.log("orchestrator", f"Quality passed (score={event.score})")
            emit({"type": "status", "content": f"Quality check passed (score {event.score})"})
            done_event.set()

        bus.on(QualityPassed, _on_quality_passed)

        # Register seed URLs as sources
        for url in state.seed_urls:
            state.registry.register_source(
                url=url,
                title=url.split("/")[-1].replace("-", " ").replace("_", " ")[:80] or url[:80],
                snippet="User-provided source -- content will be fetched",
            )

        # Select initial specialist panel
        # Use a preliminary set of domain tags based on question keywords
        initial_specialists = select_specialists(
            domain_tags=[],
            question=question,
            count=config.initial_specialist_count,
            force_include=force_include or None,
            force_exclude=force_exclude or None,
        )
        state.panel = [
            ActiveSpecialist(
                specialist_id=s.id,
                name=s.name,
                domain=s.domain,
            )
            for s in initial_specialists
        ]

        state.log("orchestrator", f"Initial panel: {[s.name for s in initial_specialists]}")
        emit(
            {
                "type": "status",
                "content": f"Assembled panel of {len(initial_specialists)} specialists",
            }
        )

        # --- Run the pipeline ---
        t0 = time.monotonic()

        try:
            # Phase 1: Decompose question into angles
            await decomposition.decompose()
            if state.error:
                return state

            # Phase 2+: Event-driven --- handlers react to events
            # The decomposition emits AngleCreated events which trigger:
            # AngleCreated -> search -> SourcesFound -> audit -> SourcesAudited -> specialist
            # -> FindingsProduced -> convergence check -> (loop or saturate)
            # AllAnglesSaturated -> synthesis -> SynthesisReady -> debate -> DebateComplete
            # -> paper -> PaperReady -> judge -> QualityPassed/QualityFailed

            # Wait for completion with deadline checks
            while not done_event.is_set():
                # Check deadline periodically
                forced = await deadline_handler.check_deadline()
                if forced and state.phase == ResearchPhase.DONE:
                    break

                # Wait a bit for events to process
                try:
                    await asyncio.wait_for(done_event.wait(), timeout=30)
                except TimeoutError:
                    # Check if we're stuck
                    if state.error:
                        break
                    # Log progress
                    saturated = sum(1 for a in state.angles if a.saturated)
                    total = len(state.angles)
                    elapsed = int(time.monotonic() - t0)
                    state.log(
                        "orchestrator",
                        f"Progress: {saturated}/{total} angles saturated, phase={state.phase.value}, elapsed={elapsed}s",
                    )

        except Exception as exc:
            state.error = f"Pipeline error: {exc}"
            logger.exception("Convergence pipeline failed")

        duration_ms = int((time.monotonic() - t0) * 1000)
        state.log(
            "orchestrator", f"Pipeline finished in {duration_ms}ms, phase={state.phase.value}"
        )

        # Build specialist_analyses dict for backward compat (worker uses len() for tools_used)
        for angle in state.angles:
            for finding in angle.findings:
                spec_id = finding.get("specialist_id", "unknown")
                if spec_id not in state.specialist_analyses:
                    state.specialist_analyses[spec_id] = []
                state.specialist_analyses[spec_id].append(finding)

        return state
