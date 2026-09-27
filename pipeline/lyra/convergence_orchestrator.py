"""Convergence-based research orchestrator: one Theo research run, research only.

Event-driven state machine. The question is decomposed into angles that
converge independently via specialist consensus; synthesis, debate and
moderation follow, and the run ends when the DossierHandler has persisted the
dossier and emitted DossierReady (spec
docs/superpowers/specs/2026-09-26-studio-and-claude-write-design.md, 2.1). The
paper is written afterwards in a Claude session, not here.

Usage (from theo_worker.py):
    orchestrator = ConvergenceOrchestrator()
    state = await orchestrator.run(question, emit, ...)
    # state has: dossier_ref, dossier_summary, error, quota_exhausted,
    # total_tokens, llm_call_count, debug_log, registry, specialist_analyses
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any, NamedTuple

from pipeline.lyra.config import _get_settings
from pipeline.lyra.research_events import (
    AngleCreated,
    CrossPollinationComplete,
    DossierReady,
    EventBus,
)
from pipeline.lyra.research_state import (
    ResearchConfig,
    ResearchPhase,
    ResearchState,
    findings_by_specialist,
)

logger = logging.getLogger(__name__)

# Wall time between two ticks of the watch loop (_drive_cascade): progress log,
# DB flush, external-cancellation check and the SSE progress snapshot.
_TICK_S = 30.0

# After DossierReady the cascade only unwinds (StatePersist's last passenger
# writes run on the way back up). It gets this long before it is cancelled.
_UNWIND_GRACE_S = 120.0

_NO_DOSSIER_ERROR = (
    "Research ended without a dossier: the event cascade finished but DossierReady never fired"
)

_DOSSIER_GUARD_ERROR = (
    "Research finished without a persisted dossier: no DossierReady with at least one "
    "moderated final claim was recorded"
)


class _Wiring(NamedTuple):
    """The handlers of one run in bus registration order, plus the two the loop drives."""

    handlers: list
    decomposition: Any
    deadline: Any


def _build_handlers(state: ResearchState, bus: EventBus, semaphore: asyncio.Semaphore) -> _Wiring:
    """Instantiate and register every handler of a research-only run.

    Event flow:
    AngleCreated -> search -> SourcesFound -> audit -> SourcesAudited
                \\-> angle_image_research -> (pool populated, no blocking event)
    -> content_fetch -> ContentFetched -> specialist -> FindingsProduced
    -> convergence check -> (loop or saturate)
    AllAnglesSaturated -> synthesis -> SynthesisReady -> debate
    -> DebateComplete -> moderator -> ModeratorComplete -> dossier -> DossierReady

    Registration order is dispatch order per event: the DossierHandler is the
    only listener on ModeratorComplete; StatePersist, registered last, writes
    its passenger artifacts after the stage handlers of the same event.
    """
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
    from pipeline.lyra.handlers.dossier import DossierHandler
    from pipeline.lyra.handlers.moderator import ModeratorHandler
    from pipeline.lyra.handlers.state_persist import StatePersistHandler
    from pipeline.lyra.handlers.synthesis import SynthesisHandler

    decomposition = DecompositionHandler(state, bus, semaphore)
    deadline = DeadlineHandler(state, bus, semaphore)
    handlers = [
        decomposition,
        SearchHandler(state, bus, semaphore),
        AngleImageResearchHandler(state, bus, semaphore),
        AuditHandler(state, bus, semaphore),
        ContentFetchHandler(state, bus, semaphore),
        SpecialistHandler(state, bus, semaphore),
        ConvergenceChecker(state, bus, semaphore),
        CrossPollinationHandler(state, bus, semaphore),
        SynthesisHandler(state, bus, semaphore),
        DebateHandler(state, bus, semaphore),
        ModeratorHandler(state, bus, semaphore),
        DossierHandler(state, bus, semaphore),
        deadline,
        StatePersistHandler(state, bus, semaphore),
    ]
    for handler in handlers:
        handler.register()
        # angle_specialist looks the SearchHandler up by class (bus.get_handler).
        bus.register_instance(handler)
    return _Wiring(handlers=handlers, decomposition=decomposition, deadline=deadline)


def _wire_done_signal(
    bus: EventBus, state: ResearchState, emit: Callable[[dict], None]
) -> asyncio.Event:
    """DossierReady ends the run (it replaced QualityPassed with the research-only split)."""
    done_event = asyncio.Event()

    async def _on_dossier_ready(event: DossierReady):
        state.log("orchestrator", f"Dossier ready for {event.request_id}")
        emit(
            {
                "type": "status",
                "content": "Dossier ready: research complete, the paper is written next",
            }
        )
        done_event.set()

    bus.on(DossierReady, _on_dossier_ready)
    return done_event


def _dossier_guard(state: ResearchState) -> None:
    """Spec 2.1: a run succeeds only with a persisted dossier (replaces the empty-paper guard)."""
    if state.error or state.dossier_ref is not None:
        return
    state.error = _DOSSIER_GUARD_ERROR
    logger.error("[THEO] dossier guard tripped, failing the run: %s", _DOSSIER_GUARD_ERROR)


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
        """Run one research-only convergence pipeline.

        Returns the ResearchState the worker reads: dossier_ref and
        dossier_summary on success, error / quota_exhausted otherwise, plus
        total_tokens, llm_call_count, debug_log, registry and specialist_analyses.
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

        # Event bus and handlers. The bus surfaces handler exceptions into
        # state.error, which the watch loop (_drive_cascade) reads.
        bus = EventBus(state=state)
        semaphore = asyncio.Semaphore(config.max_concurrent_llm_calls)
        wiring = _build_handlers(state, bus, semaphore)

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

        done_event = _wire_done_signal(bus, state, emit)

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
            await _drive_cascade(
                state,
                wiring.decomposition.decompose(),
                done_event,
                wiring.deadline,
                request_id=request_id,
                emit=emit,
                t0=t0,
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
                # Flush progress before re-raising (audit P19): the deferred
                # run is re-claimed after the 5h window resets, and without
                # this flush the research_requests row loses everything since
                # the last 30s tick — debug_log/tokens/llm_calls read as
                # stale/NULL while the request sits in 'deferred'.
                # _flush_progress_to_db is best-effort and never raises.
                _flush_progress_to_db(state, request_id)
                raise
            state.error = f"Pipeline error: {exc}"
            logger.exception("Convergence pipeline failed")

        duration_ms = int((time.monotonic() - t0) * 1000)
        state.log(
            "orchestrator", f"Pipeline finished in {duration_ms}ms, phase={state.phase.value}"
        )

        # The worker reports len(specialist_analyses) as tools_used.
        state.specialist_analyses = findings_by_specialist(state.angles)

        _dossier_guard(state)

        # Persist the run's knowledge-graph contribution (angle tree + open
        # rabbit holes as frontier). The paper node is labelled with the
        # question (there is no paper title at research end). Best-effort inside.
        if request_id and not state.error:
            from pipeline.lyra.research_graph import persist_state_graph

            persist_state_graph(state, request_id)

        return state


async def _drive_cascade(
    state: ResearchState,
    cascade_coro: Coroutine[Any, Any, None],
    done_event: asyncio.Event,
    deadline_handler: Any,
    *,
    request_id: str,
    emit: Callable[[dict], None],
    t0: float,
) -> None:
    """Run the event cascade as a task and watch it until the run is done.

    The whole run executes inside the cascade (EventBus.emit awaits every
    handler inline), so the watch loop must run beside it, not after it: only
    then do the deadline check, the 30 s DB flush and the external-cancellation
    check actually run. Returns when DossierReady fired, when state.error is
    set, or when the cascade finished (without DossierReady that is an error).
    Raises _CancelledByUser and whatever the cascade raised (quota errors
    included). The cascade never outlives this call.
    """
    cascade = asyncio.create_task(cascade_coro)
    try:
        while not done_event.is_set():
            forced = await deadline_handler.check_deadline()
            if forced and state.phase == ResearchPhase.DONE:
                break
            done_wait = asyncio.create_task(done_event.wait())
            try:
                await asyncio.wait(
                    {cascade, done_wait}, timeout=_TICK_S, return_when=asyncio.FIRST_COMPLETED
                )
            finally:
                done_wait.cancel()
            if cascade.done():
                cascade.result()
                if not done_event.is_set() and not state.error:
                    state.error = _NO_DOSSIER_ERROR
                break
            if done_event.is_set() or state.error:
                break
            _tick(state, request_id, emit, t0)
    finally:
        await _settle_cascade(state, cascade, done_event, request_id)


def _tick(state: ResearchState, request_id: str, emit: Callable[[dict], None], t0: float) -> None:
    """One watch-loop tick: progress log, DB flush, external cancellation, live snapshot."""
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
    # Promote to logger so docker logs are no longer blind; the rest of the
    # pipeline emits via SSE only.
    logger.info("[THEO] %s %s", request_id, progress_msg)
    # Counters + recent debug_log to the DB, so the run is diagnosable from psql.
    _flush_progress_to_db(state, request_id)
    # Ghost-task guard (2026-06-29): the DB row's status is the source of truth.
    # If the user cancelled via the API (or the watchdog deferred the run), this
    # raises _CancelledByUser and _drive_cascade cancels the cascade. Live since
    # the cascade runs as a task (2026-09-26); before, it never ran.
    _check_external_cancellation(request_id)
    spec_count = len({f.get("specialist_id", "unknown") for a in state.angles for f in a.findings})
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


async def _settle_cascade(
    state: ResearchState, cascade: asyncio.Task, done_event: asyncio.Event, request_id: str
) -> None:
    """Let a finished run's cascade unwind for a grace period, cancel everything else."""
    if not cascade.done() and done_event.is_set() and not state.error:
        await asyncio.wait({cascade}, timeout=_UNWIND_GRACE_S)
    if not cascade.done():
        cascade.cancel()
    (outcome,) = await asyncio.gather(cascade, return_exceptions=True)
    if (
        done_event.is_set()
        and isinstance(outcome, BaseException)
        and not isinstance(outcome, asyncio.CancelledError)
    ):
        # The dossier is complete; an error while unwinding does not undo it,
        # but it must be visible.
        state.log("orchestrator", f"Cascade raised after the run was done: {outcome!r}")
        logger.error("[THEO] %s cascade raised after the run was done: %r", request_id, outcome)


def _flush_progress_to_db(state, request_id: str) -> None:
    """Persist in-flight counters + recent debug_log to research_requests.

    Called on every watch-loop tick (every 30s) and piggybacked on
    EventBus.emit, so a stalled vs healthy run can be distinguished from psql
    alone. The final write in theo_worker.py overwrites everything anyway, so
    partial values here are safe to keep loose.
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
    signal. The watch loop polls the DB every 30s; if status != 'running',
    this is raised so the worker can catch it cleanly and unwind credits.
    """


def _check_external_cancellation(request_id: str) -> None:
    """Read research_requests.status for `request_id`. If it's no longer
    'running' (e.g. user cancelled via API, watchdog marked deferred, etc.),
    raise ``_CancelledByUser`` so the watch loop unwinds.

    Called on every watch-loop tick. Best-effort: a transient DB error must NOT
    kill the pipeline — only a confirmed non-'running' status triggers the cancel.
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
