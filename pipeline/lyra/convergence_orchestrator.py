"""Convergence-based research orchestrator.

Event-driven state machine driving Theo's research runs. Questions are
decomposed into research angles that converge independently via specialist
consensus, then synthesized into a Why Files narrative paper.

Usage (from theo_worker.py):
    orchestrator = ConvergenceOrchestrator()
    state = await orchestrator.run(question, emit, ...)
    # state has: paper_text, paper_title, audit_result, quality_score, etc.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from pipeline.lyra.config import _get_settings
from pipeline.lyra.research_events import (
    AngleCreated,
    CrossPollinationComplete,
    EventBus,
    QualityPassed,
)
from pipeline.lyra.research_state import (
    ResearchConfig,
    ResearchPhase,
    ResearchState,
)

logger = logging.getLogger(__name__)

# Fail the run if the assembled paper is below this — no real Theo paper is this
# short (healthy runs are 10k–40k chars). A near-empty paper means the writing
# stages returned blank, almost always MiniMax Token-Plan exhaustion (429 ->
# empty) or output truncation. We surface that as a failure rather than publish
# an empty "completed" paper (CLAUDE.md: no silent-empty / graceful degradation).
_MIN_PUBLISHABLE_PAPER_CHARS = 2000


def _empty_paper_error(paper_text: str | None) -> str | None:
    """Return a failure reason if `paper_text` is too short to publish, else None.

    Guards against the 2026-06-16 incident where an 89-char paper was saved as
    "completed" at quality 73 because the writing stages returned empty output
    under MiniMax Token-Plan exhaustion (429) / max_tokens truncation.
    """
    paper_len = len((paper_text or "").strip())
    if paper_len >= _MIN_PUBLISHABLE_PAPER_CHARS:
        return None
    return (
        f"Paper assembly produced only {paper_len} chars "
        f"(< {_MIN_PUBLISHABLE_PAPER_CHARS} minimum). The writing/synthesis stages "
        "returned empty or truncated output — almost always MiniMax Token-Plan "
        "quota exhaustion (429) or max_tokens truncation. Failing the run instead "
        "of publishing an empty paper."
    )


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
        low_priority: bool = True,
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
            started_at=datetime.now(UTC),
            deadline=datetime.now(UTC) + timedelta(hours=config.deadline_hours),
        )

        state.log("orchestrator", f"Starting convergence pipeline for: {question[:80]}...")

        # Quota preflight (2026-06-28, Layer 2 of the rate-limit-defense plan).
        # Probe the MiniMax Token Plan 5h-rolling remaining budget. If it's
        # below a sane floor for a full research run, raise InsufficientQuotaError
        # *before* making any LLM calls — the worker marks the request 'deferred'
        # and re-queues it after the 5h window resets.
        # The probe is fail-soft: if the endpoint doesn't exist (some plans) or
        # any error happens, we proceed. The limiter's quota-freeze still catches
        # mid-run exhaustion.
        from pipeline.lyra.minimax_limiter import InsufficientQuotaError
        from pipeline.lyra.minimax_shared import probe_minimax_quota

        quota = probe_minimax_quota()
        if quota.get("ok"):
            # The normalised fields are set by probe_minimax_quota() from the
            # MiniMax-native model_remains[0]. Floor at 5% — below this a
            # Decomposition call (~5k tokens) plus the cheapest search rounds
            # can't reliably finish, and the run will stall at 45min. The
            # worker marks the request 'deferred' so it's re-claimed after
            # the 5h window resets.
            remaining_5h_pct = quota.get("five_hour_remaining_percent")
            if remaining_5h_pct is not None and remaining_5h_pct < 5:
                state.log(
                    "orchestrator",
                    f"Preflight: 5h remaining={remaining_5h_pct}% < 5% floor — "
                    f"refusing to start, will be deferred by worker.",
                )
                raise InsufficientQuotaError(
                    f"MiniMax 5h-rolling remaining={remaining_5h_pct}% is below "
                    f"the 5% floor; deferring until window resets. Full probe: "
                    f"{json.dumps(quota, default=str)[:300]}"
                )
            # Probe says quota is healthy — if the limiter was frozen from a
            # previous quota hit, lift the freeze so calls can resume.
            from pipeline.lyra.minimax_limiter import limiter as global_limiter

            if global_limiter.is_frozen():
                state.log(
                    "orchestrator",
                    f"Preflight: quota healthy ({remaining_5h_pct}%); "
                    f"unfreezing global limiter (was frozen).",
                )
                global_limiter.unfreeze()
        # else: probe failed (endpoint missing / network error) — proceed and
        # rely on the limiter's quota-freeze for mid-run protection.

        # Run-priority lane (2026-07-26): batch runs bind the crawl lane —
        # their MiniMax calls pace at concurrency 1 with >= crawl-delay gaps
        # so background research never outpaces the shared 5h window.
        # Interactive (UI) runs stay on the full-speed adaptive lane and can
        # execute CONCURRENTLY with a crawling batch run (two worker slots).
        # The contextvar propagates through create_task/to_thread, so every
        # LLM call in this run's handler tree lands on the right lane.
        from pipeline.lyra.minimax_limiter import bind_low_priority

        run_low = bool(low_priority and self._settings.theo_low_priority)
        bind_low_priority(run_low)
        state.log(
            "orchestrator",
            "Crawl lane bound: low-priority run, concurrency 1, >=crawl-delay gaps."
            if run_low
            else "Full-speed lane bound: interactive run.",
        )

        # Bind state for token accounting. LLM helpers (minimax_shared.py,
        # config.call_api) read this contextvar to credit token usage back
        # to state.total_tokens without needing the state object threaded
        # through every signature.
        from pipeline.lyra import token_accounting

        token_accounting.bind(state)

        # NOTE (2026-06-28): The previous call `global_limiter.reset()` was
        # removed. The MiniMax Token Plan is a global 5h-rolling quota shared
        # across all pipelines; resetting to max_concurrency=100 at the start
        # of every Theo run wiped learned backoff state and was the direct
        # cause of the 82%-rate-limited 52-prompt batch. The limiter now
        # learns continuously; no per-task reset.

        # Set up event bus and handlers. Pass state so the bus can surface
        # handler exceptions into state.error (which the deadline loop below
        # already watches at line ~238) — see research_events.py:EventBus.emit.
        bus = EventBus(state=state)
        semaphore = asyncio.Semaphore(config.max_concurrent_llm_calls)

        # Lazy imports to avoid circular dependencies
        from pipeline.lyra.handlers.angle_audit import AuditHandler
        from pipeline.lyra.handlers.angle_image_research import AngleImageResearchHandler
        from pipeline.lyra.handlers.angle_search import SearchHandler
        from pipeline.lyra.handlers.angle_specialist import SpecialistHandler
        from pipeline.lyra.handlers.content_fetch import ContentFetchHandler
        from pipeline.lyra.handlers.convergence_checker import ConvergenceChecker
        from pipeline.lyra.handlers.cross_pollination import CrossPollinationHandler
        from pipeline.lyra.handlers.deadline import DeadlineHandler
        from pipeline.lyra.handlers.debate import DebateHandler
        from pipeline.lyra.handlers.decomposition import DecompositionHandler
        from pipeline.lyra.handlers.fact_check import FactCheckHandler
        from pipeline.lyra.handlers.image_generation import ImageGenerationHandler
        from pipeline.lyra.handlers.judge import JudgeHandler
        from pipeline.lyra.handlers.moderator import ModeratorHandler
        from pipeline.lyra.handlers.paper import PaperHandler
        from pipeline.lyra.handlers.presentation import PresentationHandler
        from pipeline.lyra.handlers.probative_images import ProbativeImagesHandler
        from pipeline.lyra.handlers.synthesis import SynthesisHandler

        # Instantiate handlers
        decomposition = DecompositionHandler(state, bus, semaphore)
        search = SearchHandler(state, bus, semaphore)
        angle_image_research = AngleImageResearchHandler(state, bus, semaphore)
        audit = AuditHandler(state, bus, semaphore)
        content_fetch = ContentFetchHandler(state, bus, semaphore)
        specialist = SpecialistHandler(state, bus, semaphore)
        convergence = ConvergenceChecker(state, bus, semaphore)
        cross_poll = CrossPollinationHandler(state, bus, semaphore)
        synthesis = SynthesisHandler(state, bus, semaphore)
        debate = DebateHandler(state, bus, semaphore)
        moderator = ModeratorHandler(state, bus, semaphore)
        paper = PaperHandler(state, bus, semaphore)
        probative_images = ProbativeImagesHandler(state, bus, semaphore)
        fact_check = FactCheckHandler(state, bus, semaphore)
        presentation = PresentationHandler(state, bus, semaphore)
        image_gen = ImageGenerationHandler(state, bus, semaphore)
        judge = JudgeHandler(state, bus, semaphore)
        deadline_handler = DeadlineHandler(state, bus, semaphore)

        # Register all handlers on the bus
        # Event flow:
        # AngleCreated -> search -> SourcesFound -> audit -> SourcesAudited
        #             \\-> angle_image_research -> (pool populated, no blocking event)
        # -> content_fetch -> ContentFetched -> specialist -> FindingsProduced
        # -> convergence check -> (loop or saturate)
        # AllAnglesSaturated -> synthesis -> SynthesisReady -> debate
        # -> DebateComplete -> moderator -> ModeratorComplete -> paper
        # -> PaperReady -> probative_images -> ProbativeImagesReady -> fact_check
        # -> FactCheckComplete -> presentation -> PresentationChecked
        # -> image_gen -> ImageGenComplete -> judge -> QualityPassed
        all_handlers = [
            decomposition,
            search,
            angle_image_research,
            audit,
            content_fetch,
            specialist,
            convergence,
            cross_poll,
            synthesis,
            debate,
            moderator,
            paper,
            probative_images,
            fact_check,
            presentation,
            image_gen,
            judge,
            deadline_handler,
        ]
        for handler in all_handlers:
            handler.register()
            bus.register_instance(handler)

        # Wire cross-pollination complete -> trigger round 2 via AngleCreated events.
        # This naturally flows: AngleCreated -> search -> audit -> content_fetch -> specialist.
        # The specialist handler skips its own search trigger for round 2
        # (only triggers for round 3+), preventing double-triggering.
        async def _on_cross_pollination_complete(event: CrossPollinationComplete):
            """After cross-pollination, kick off next round for all unsaturated angles."""
            state.log("orchestrator", "Cross-pollination complete, starting next round")
            emit(
                {
                    "type": "status",
                    "content": "Cross-pollination complete -- starting next round...",
                }
            )
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

        # Specialist panel is no longer selected globally at startup.
        # Each angle selects its own specialists dynamically based on its domains
        # (see SpecialistHandler._on_content_fetched). The state.panel list is
        # populated lazily as angles assign specialists.
        state.log("orchestrator", "Specialist selection deferred to per-angle assignment")

        # --- Run the pipeline ---
        t0 = time.monotonic()

        try:
            # Phase 1: Decompose question into angles
            await decomposition.decompose()
            if state.error:
                return state

            # Phase 2+: Event-driven --- handlers react to events
            # The decomposition emits AngleCreated events which trigger:
            # AngleCreated -> search -> SourcesFound -> audit -> SourcesAudited
            # -> content_fetch -> ContentFetched -> specialist
            # -> FindingsProduced -> convergence check -> (loop or saturate)
            # AllAnglesSaturated -> synthesis -> SynthesisReady -> debate
            # -> DebateComplete -> moderator -> ModeratorComplete -> paper
            # -> PaperReady -> probative_images -> ProbativeImagesReady -> fact_check
            # -> FactCheckComplete -> presentation -> PresentationChecked
            # -> image_gen -> ImageGenComplete -> judge -> QualityPassed

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
                    progress_msg = (
                        f"Progress: {saturated}/{total} angles saturated, "
                        f"phase={state.phase.value}, elapsed={elapsed}s, "
                        f"llm_calls={state.llm_call_count}, "
                        f"sources={len(state.registry.sources)}"
                    )
                    state.log("orchestrator", progress_msg)
                    # Promote to logger so docker logs are no longer blind —
                    # the rest of the pipeline emits via SSE only.
                    logger.info("[THEO] %s %s", request_id, progress_msg)
                    # Flush counters + recent debug_log to DB so the run is
                    # diagnosable from psql alone (previously these stayed at
                    # 0 / NULL until completion, making stalls indistinguishable
                    # from healthy long-running stages).
                    _flush_progress_to_db(state, request_id)
                    # Ghost-task guard (2026-06-29). The DB row's status is the
                    # source of truth: if the user cancelled via the API (or
                    # the watchdog marked deferred), the DB says so within
                    # milliseconds, but the in-flight asyncio task has no
                    # direct signal. Without this check, a manually-cancelled
                    # task kept burning tokens for up to the 45min stall
                    # guard — observed when the stuck DMT task burned ~25min
                    # of MiniMax calls after I cancelled it via DB update.
                    _check_external_cancellation(request_id)
                    # Also emit a progress SSE so the live frontend panel
                    # sees fresh counters every ~30s without waiting for
                    # paper_assembly (which only fires ~3h in).
                    spec_count = len(
                        {
                            f.get("specialist_id", "unknown")
                            for a in state.angles
                            for f in a.findings
                        }
                    )
                    emit(
                        {
                            "type": "progress",
                            "stage": "orchestrator",
                            "meta": {
                                "phase": state.phase.value,
                                "elapsed_s": elapsed,
                                "angles_saturated": saturated,
                                "angles_total": total,
                                "llm_calls": state.llm_call_count,
                                "sources_found": len(state.registry.sources),
                                "tools_used": spec_count,
                                "total_tokens": state.total_tokens,
                            },
                        }
                    )

        except _CancelledByUser as exc:
            # User-cancellation (DB status changed to 'cancelled' or 'deferred').
            # Set a clean state.error so the worker's `"cancelled" in ctx.error`
            # branch fires and the task is marked 'cancelled' with credits
            # released. Don't re-raise — the worker should treat this as a
            # graceful stop, not a crash.
            state.error = f"Cancelled by user: {exc}"
            logger.info("[THEO] %s cancelled by user: %s", request_id, exc)
        except Exception as exc:
            # Quota errors must propagate so the worker can mark the request
            # 'deferred' rather than 'failed'. Without the re-raise, the
            # worker only sees state.error and treats it as a generic
            # failure — defeating the 2026-06-28 quota-aware design where
            # deferred rows are re-claimed after the 5h window resets.
            from pipeline.lyra.minimax_limiter import (
                InsufficientQuotaError,
                QuotaExhaustedError,
            )

            if isinstance(exc, (QuotaExhaustedError, InsufficientQuotaError)):
                raise
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

        # Empty-paper guard: never let the worker publish a near-empty paper as
        # "completed" (the 2026-06-16 incident saved an 89-char paper at quality
        # 73). If the run otherwise succeeded but produced no real paper, convert
        # it to a failure with an actionable reason so credits are released and
        # the user sees WHY rather than an empty page.
        if not state.error:
            empty_reason = _empty_paper_error(state.paper_text)
            if empty_reason:
                state.error = empty_reason
                logger.error("[THEO] empty-paper guard tripped — failing run: %s", empty_reason)

        # Persist the run's knowledge-graph contribution (angle tree + open
        # rabbit holes as frontier). Best-effort inside — never fails the run.
        if request_id and not state.error:
            from pipeline.lyra.research_graph import persist_state_graph

            persist_state_graph(state, request_id)

        return state


def _flush_progress_to_db(state, request_id: str) -> None:
    """Persist in-flight counters + recent debug_log to research_requests.

    Called periodically (every 30s, on each orchestrator deadline-loop tick)
    so a stalled vs healthy run can be distinguished from psql alone instead
    of guessing from SSE / docker logs. The final completion write in
    theo_worker.py overwrites everything anyway, so partial values here
    are safe to keep loose.
    """
    if not request_id:
        return
    try:
        from sqlalchemy import text

        from pipeline.database import get_session

        # Count unique specialists with at least one finding so far —
        # matches the completion-time tools_used semantics.
        spec_ids = {
            finding.get("specialist_id", "unknown")
            for angle in state.angles
            for finding in angle.findings
        }
        with get_session() as session:
            session.execute(
                text(
                    """
                    UPDATE research_requests
                    SET llm_calls    = :llm_calls,
                        total_tokens = :tokens,
                        sites_found  = :sites,
                        tools_used   = :tools,
                        debug_log    = :debug_log
                    WHERE id = :id
                    """
                ),
                {
                    "id": request_id,
                    "llm_calls": state.llm_call_count,
                    "tokens": state.total_tokens,
                    "sites": len(state.registry.sources),
                    "tools": len(spec_ids),
                    # Cap to keep the update cheap and avoid bloating the row
                    # mid-run (the completion write later replaces the full log).
                    "debug_log": json.dumps(state.debug_log[-200:]),
                },
            )
            session.commit()
    except Exception as exc:
        # Never let a diagnostic write break the pipeline.
        logger.warning("[THEO] DB progress flush failed: %s", exc)


class _CancelledByUser(Exception):
    """Raised when the orchestrator detects the DB status is no longer 'running'.

    The worker writes status='cancelled' to the DB when a user cancels via
    DELETE /research/{id}, but the in-flight asyncio task has no direct
    signal — it would otherwise keep burning tokens until the stall guard
    fires (45min). The orchestrator polls the DB every 30s as part of its
    progress flush; if status != 'running', raise this so the worker can
    catch it cleanly and unwind credits.
    """


def _check_external_cancellation(request_id: str) -> None:
    """Read research_requests.status for `request_id`. If it's no longer
    'running' (e.g. user cancelled via API, watchdog marked deferred, etc.),
    raise ``_CancelledByUser`` so the orchestrator loop unwinds.

    Called from the orchestrator's deadline loop every ~30s. Best-effort:
    a transient DB error must NOT kill the pipeline — only a confirmed
    non-'running' status triggers the cancel.
    """
    if not request_id:
        return
    try:
        from sqlalchemy import text

        from pipeline.database import get_session

        with get_session() as session:
            row = session.execute(
                text("SELECT status FROM research_requests WHERE id = :id"),
                {"id": request_id},
            ).fetchone()
        if row is None:
            # Row vanished (manual cleanup). Treat as cancellation.
            raise _CancelledByUser(f"Research request {request_id} no longer exists")
        if row[0] != "running":
            raise _CancelledByUser(
                f"Research request {request_id} status changed to '{row[0]}' "
                f"while orchestrator was running"
            )
    except _CancelledByUser:
        raise
    except Exception as exc:
        # Best-effort: never let a DB read error kill the pipeline.
        logger.warning("[THEO] Cancellation check failed (continuing): %s", exc)
