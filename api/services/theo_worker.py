"""
Background worker for Theodore Furcade — processes research requests asynchronously.

Polls the research_requests table for queued requests (FIFO),
runs the agent pipeline, and saves structured reports to the DB.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import text

from api.services.theo_config import (
    THEO_MIN_TASK_INTERVAL_S,
    THEO_PARALLEL_SLOTS,
    THEO_RESEARCH_COST,
)
from pipeline.database import get_session

logger = logging.getLogger(__name__)


def _plan_balance_snapshot() -> tuple[int, int] | None:
    """(weekly_remains_tokens, weekly_start_ms) from the MiniMax plan probe.

    The absolute balance is the only honest cost signal: the API `usage`
    field we store as total_tokens misses billed reasoning tokens by ~7.7x
    (measured 2026-08-07). Subtracting an end snapshot from a start snapshot
    gives what a run REALLY cost. Returns None when the probe fails — a
    measurement is never worth failing a run over. Blocking HTTP: call via
    asyncio.to_thread.
    """
    try:
        from pipeline.lyra.minimax_shared import probe_minimax_quota

        probe = probe_minimax_quota(force=True)
        balance = probe.get("weekly_remains_tokens")
        week = probe.get("weekly_start_time")
        if balance is None or week is None:
            return None
        return int(balance), int(week)
    except Exception as exc:  # noqa: BLE001 — measurement must never break a run
        logger.warning("[THEO] plan balance probe failed: %s", exc)
        return None


def _record_plan_cost(request_id: str, plan_start: tuple[int, int] | None) -> None:
    """Snapshot the end balance and log the measured cost of this run.

    Skips the subtraction when the run crossed the Monday reset (different
    billing week) — the balance refilled, so the difference is meaningless.
    Parallel Lyra/curator traffic is included, so the number is an upper
    bound for this run, not a pure isolate.
    """
    plan_end = _plan_balance_snapshot()
    if not plan_end:
        return
    with get_session() as session:
        session.execute(
            text("UPDATE research_requests SET plan_weekly_remains_end = :bal WHERE id = :id"),
            {"bal": plan_end[0], "id": request_id},
        )
        session.commit()
    if not plan_start:
        return
    if plan_start[1] != plan_end[1]:
        logger.info("[THEO] %s crossed the weekly reset — plan cost not comparable", request_id)
        return
    used = plan_start[0] - plan_end[0]
    logger.info(
        "[THEO] %s real plan cost: %.1fM tokens (weekly balance %.0fM -> %.0fM)",
        request_id,
        used / 1e6,
        plan_start[0] / 1e6,
        plan_end[0] / 1e6,
    )


def release_reservation_in_session(session, request_id: str) -> None:
    """Release the request's credit reservation EXACTLY ONCE inside the
    caller's open transaction (no commit here — the caller owns it).

    Idempotent via research_requests.reservation_released (migration 0010,
    audit 2026-08-05): defer -> re-claim -> second defer/failure,
    stale-deferred cleanup, and DELETE-cancel can all call this for the same
    row — only the first call decrements reserved_credits, so drained
    reservations can no longer eat other requests' holds.

    Shared by the worker's failure/cancel paths below and by the
    queued->cancelled branch of DELETE /theo/research/{id} (api/routes/theo.py),
    which must release atomically with the status flip — a queued row is
    never claimed by the worker, so no worker path would ever release it.
    """
    row = session.execute(
        text("""
            UPDATE research_requests SET reservation_released = TRUE
            WHERE id = :id AND reservation_released = FALSE
            RETURNING user_id
        """),
        {"id": request_id},
    ).fetchone()
    if row is None:
        return  # already released (or unknown id) — exactly-once guard
    session.execute(
        text("""
            UPDATE discord_users SET reserved_credits = GREATEST(reserved_credits - :cost, 0)
            WHERE discord_id = :uid AND is_unlimited = FALSE
        """),
        {"uid": row.user_id, "cost": THEO_RESEARCH_COST},
    )


def _release_reservation(request_id: str) -> None:
    """Release reserved credits when a research request fails or is cancelled."""
    try:
        with get_session() as session:
            release_reservation_in_session(session, request_id)
            session.commit()
    except Exception as exc:
        logger.warning(f"[THEO] Reservation release failed for {request_id}: {exc}")


def _deduct_credits(request_id: str) -> None:
    """Deduct credits and release reservation on successful completion."""
    try:
        with get_session() as session:
            row = session.execute(
                text("SELECT user_id FROM research_requests WHERE id = :id"),
                {"id": request_id},
            ).fetchone()
            if not row:
                return
            # Deduct ALWAYS on completion; release the reservation only when
            # this request still holds one (a deferred run already released
            # at defer time — the flag guard prevents a double decrement).
            session.execute(
                text("""
                    UPDATE discord_users SET credits = credits - :cost
                    WHERE discord_id = :uid AND is_unlimited = FALSE
                """),
                {"uid": row.user_id, "cost": THEO_RESEARCH_COST},
            )
            release_reservation_in_session(session, request_id)
            session.commit()
    except Exception as exc:
        logger.warning(f"[THEO] Credit deduction failed for {request_id}: {exc}")


# Active supervised runs: request_id -> (task, is_batch). Capacity is
# THEO_PARALLEL_SLOTS with at most ONE batch run — the second slot exists so
# a website submission executes concurrently (full-speed lane) instead of
# waiting behind a 12-18h batch crawl (2026-07-26 two-lane design).
_active_runs: dict[str, tuple[asyncio.Task, bool]] = {}

# Per-request live events for SSE streaming (request_id -> list[dict])
_live_events: dict[str, list[dict]] = {}
_MAX_EVENTS_PER_REQUEST = 500
_MAX_LIVE_ENTRIES = 100

# Cap on the per-run in-memory pipeline_trace list (audit 2026-08-05): a
# 72h low-priority batch run emits events the whole time, so the list must
# be bounded. When the cap is exceeded the OLDEST entries are dropped.
_PIPELINE_TRACE_MAX = 5000

_shutdown = False


def _append_event(request_id: str, event: dict) -> None:
    """Append an event to the live events list with bounds checking."""
    events = _live_events.get(request_id)
    if events is None:
        return
    if len(events) < _MAX_EVENTS_PER_REQUEST:
        events.append(event)


def get_live_events(request_id: str) -> list[dict]:
    """Return accumulated live events for a request (for SSE streaming)."""
    return _live_events.get(request_id, [])


def _terminal_status_for_error(ctx) -> str:
    """Route a run that ended with ctx.error to its terminal status.

    'cancelled' wins (user intent), then 'deferred' for quota deaths
    (ctx.quota_exhausted is set by EventBus.emit — the exception itself
    never propagates), then 'failed' for everything real.
    """
    if "cancelled" in ctx.error.lower():
        return "cancelled"
    if getattr(ctx, "quota_exhausted", False):
        return "deferred"
    return "failed"


async def _process_request(
    request_id: str,
    question: str,
    specialist_options: dict | None = None,
    is_batch: bool = False,
) -> None:
    """Process a single research request using the V2 convergence pipeline."""
    logger.info(f"[THEO] Starting request {request_id}")

    # Register live events buffer before pipeline starts so SSE streaming works immediately
    _live_events[request_id] = []

    # Mark request as running. started_at is the batch-pacing clock: the next
    # batch task may only start THEO_MIN_TASK_INTERVAL_S after this moment.
    # The UPDATE is conditional on a still-claimable status: a DELETE can flip
    # the row to 'cancelled' between the poll loop's SELECT and this claim, and
    # an unconditional UPDATE would resurrect it to 'running'. 'deferred' is
    # claimable too — the poll loop re-claims deferred rows after the back-off.
    with get_session() as session:
        claimed = session.execute(
            text(
                "UPDATE research_requests SET status = 'running', started_at = NOW() "
                "WHERE id = :id AND status IN ('queued', 'deferred')"
            ),
            {"id": request_id},
        )
        session.commit()
    if claimed.rowcount == 0:
        _live_events.pop(request_id, None)
        logger.info(
            "[THEO] Request %s no longer claimable (cancelled or picked up elsewhere) — skipping.",
            request_id,
        )
        return

    pipeline_trace: list[dict] = []
    start = time.monotonic()
    plan_start = await asyncio.to_thread(_plan_balance_snapshot)
    if plan_start:
        with get_session() as session:
            session.execute(
                text("""
                    UPDATE research_requests
                    SET plan_weekly_remains_start = :bal, plan_week_start_ms = :week
                    WHERE id = :id
                """),
                {"bal": plan_start[0], "week": plan_start[1], "id": request_id},
            )
            session.commit()

    def emit(event: dict) -> None:
        _append_event(request_id, event)
        pipeline_trace.append(event)
        # Cap the in-memory trace: a multi-day batch run emits events for
        # 72h+ and the list would otherwise grow unbounded in worker memory.
        # Oldest entries drop first. (The DB flush caps separately — this
        # bound is only about the worker process's RAM.)
        if len(pipeline_trace) > _PIPELINE_TRACE_MAX:
            del pipeline_trace[: len(pipeline_trace) - _PIPELINE_TRACE_MAX]

    try:
        force_include = (specialist_options or {}).get("force_include", [])
        force_exclude = (specialist_options or {}).get("force_exclude", [])
        video_ids = (specialist_options or {}).get("video_ids", [])
        web_urls = (specialist_options or {}).get("web_urls", [])
        disabled_adapters = (specialist_options or {}).get("disabled_adapters", [])

        from pipeline.lyra.convergence_orchestrator import ConvergenceOrchestrator

        orchestrator = ConvergenceOrchestrator()
        ctx: Any = await orchestrator.run(
            question,
            emit,
            request_id=request_id,
            force_include=force_include,
            force_exclude=force_exclude,
            video_ids=video_ids,
            web_urls=web_urls,
            disabled_adapters=disabled_adapters,
            # UI submissions run at full speed (a human is waiting); only
            # batch rows crawl at low priority.
            low_priority=is_batch,
        )

        duration_ms = int((time.monotonic() - start) * 1000)
        # Measure the real plan cost before any post-processing spends more.
        await asyncio.to_thread(_record_plan_cost, request_id, plan_start)

        if ctx.error:
            # Release reserved credits on failure/cancel/defer
            _release_reservation(request_id)

            status = _terminal_status_for_error(ctx)
            if is_batch:
                from pipeline.lyra.thinking_log import log_thinking

                log_thinking(
                    "run_event",
                    f"Research {status}: {question[:200]}",
                    {"request_id": request_id, "failed": True},
                )
            if status in ("cancelled", "failed"):
                # The run will never complete — reset its seed node to
                # frontier so it can be requeued (Follow-up-Ticket 6).
                # 'deferred' is deliberately excluded: it retries and still
                # holds a legitimate claim on the node.
                from pipeline.lyra.research_graph import reset_node_for_failed_request

                reset_node_for_failed_request(request_id)

            if status == "cancelled":
                emit({"type": "done", "status": "cancelled"})
                logger.info(f"[THEO] Request {request_id} cancelled by user")
            else:
                # 'deferred' = quota death swallowed into ctx.error by the
                # event bus (ctx.quota_exhausted) — retry when the window
                # recovers. 'failed' = a real failure.
                emit({"type": "done", "status": status})
                with get_session() as session:
                    # Persist the in-memory diagnostic state on failure so
                    # we can post-mortem from psql alone — previously the
                    # failure path threw away debug_log + counters, which
                    # is exactly when we most want them.
                    session.execute(
                        text("""
                            UPDATE research_requests
                            SET status = :status,
                                error_message = :msg,
                                debug_log = :debug_log,
                                total_tokens = :tokens,
                                llm_calls = :llm_calls,
                                sites_found = :sites,
                                duration_ms = :duration,
                                completed_at = NOW()
                            WHERE id = :id
                        """),
                        {
                            "status": status,
                            "id": request_id,
                            "msg": ctx.error,
                            "debug_log": json.dumps(ctx.debug_log),
                            "tokens": ctx.total_tokens,
                            "llm_calls": ctx.llm_call_count,
                            "sites": len(ctx.registry.sources) if hasattr(ctx, "registry") else 0,
                            "duration": duration_ms,
                        },
                    )
                    session.commit()
                log = logger.warning if status == "deferred" else logger.error
                log(f"[THEO] Request {request_id} {status}: {ctx.error}")
        else:
            # Deduct credits and release reservation on success
            _deduct_credits(request_id)

            result = {
                "report": ctx.paper_text,
                "title": ctx.paper_title,
                "card_description": ctx.card_description,
                "audit": ctx.audit_result,
                "quality_score": ctx.quality_score,
                # Persist probative image metadata so reflow/rewrite backfills
                # can rebuild captions against the source list without
                # re-fetching from connectors.
                "probative_images": getattr(ctx, "probative_images", []) or [],
                # Hero banner picked from the probative_images list — used as
                # the page-top banner and og:image. None when no probative
                # images were embedded.
                "hero_image": getattr(ctx, "hero_image", None),
            }
            emit({"type": "done", "status": "completed"})
            try:
                with get_session() as session:
                    # Guarded on status='running': a DELETE that cancelled the
                    # row mid-run must not be overwritten back to 'completed'.
                    completed = session.execute(
                        text("""
                            UPDATE research_requests
                            SET status = 'completed',
                                result_json = :result,
                                pipeline_trace = :trace,
                                debug_log = :debug_log,
                                total_tokens = :tokens,
                                llm_calls = :llm_calls,
                                duration_ms = :duration,
                                sites_found = :sites,
                                tools_used = :tools,
                                completed_at = NOW()
                            WHERE id = :id AND status = 'running'
                        """),
                        {
                            "id": request_id,
                            "result": json.dumps(result),
                            "trace": json.dumps(pipeline_trace),
                            "debug_log": json.dumps(ctx.debug_log),
                            "tokens": ctx.total_tokens,
                            "llm_calls": ctx.llm_call_count,
                            "duration": duration_ms,
                            "sites": len(ctx.registry.sources),
                            "tools": len(ctx.specialist_analyses),
                        },
                    )
                    session.commit()
                    if completed.rowcount == 0:
                        logger.warning(
                            "[THEO] Request %s was no longer 'running' at completion "
                            "(cancelled mid-run?) — result not written.",
                            request_id,
                        )
            except Exception as db_exc:
                logger.error(f"[THEO] DB commit failed for {request_id}: {db_exc}")
            logger.info(
                f"[THEO] Request {request_id} completed in {duration_ms}ms"
                f" ({ctx.total_tokens} tokens)"
            )
            if is_batch:
                # Permanent-researcher flow (2026-07-26): the frontier node
                # is explored either way; gate-passing papers go live
                # immediately, gate failures ping Discord for manual review.
                from pipeline.lyra.research_graph import mark_node_explored

                mark_node_explored(request_id)

                from pipeline.lyra.thinking_log import log_thinking

                # This completion event fires BEFORE _auto_publish runs, so
                # the activity feed reports "completed" a moment ahead of
                # publish/gate-review outcome — a pre-existing visibility
                # gap (the feed reflects pipeline completion, not
                # publication status).
                log_thinking(
                    "run_event",
                    f"Research completed: {question[:200]}",
                    {"request_id": request_id},
                )
                # Sync DB + citation work — run in a thread so the event loop
                # (SSE streams, other runs) is not blocked for its duration.
                await asyncio.to_thread(_auto_publish, request_id)

    except Exception as exc:
        from pipeline.lyra.minimax_limiter import (
            InsufficientQuotaError,
            QuotaExhaustedError,
        )

        # 2026-06-28: quota errors are *deferred* not failed — the 5h window
        # will reset. The worker re-queues deferred rows after 1h.
        is_quota_error = isinstance(exc, (InsufficientQuotaError, QuotaExhaustedError))
        duration_ms = int((time.monotonic() - start) * 1000)
        if is_quota_error:
            logger.warning(f"[THEO] Quota hit on request {request_id} — deferring: {exc}")
        else:
            logger.error(
                f"[THEO] Unexpected error for request {request_id}: {exc}",
                exc_info=True,
            )
        _release_reservation(request_id)
        outer_status = "deferred" if is_quota_error else "failed"
        if outer_status == "failed":
            # Same terminal-failure reset as the ctx.error branch above —
            # this is the crash path (exception raised before/outside
            # orchestrator.run returning ctx), 'deferred' still excluded.
            from pipeline.lyra.research_graph import reset_node_for_failed_request

            reset_node_for_failed_request(request_id)
        emit({"type": "done", "status": outer_status})
        if is_batch:
            from pipeline.lyra.thinking_log import log_thinking

            log_thinking(
                "run_event",
                f"Research {outer_status}: {question[:200]}",
                {"request_id": request_id, "failed": True},
            )
        with get_session() as session:
            # Even on an unexpected crash, try to persist whatever
            # diagnostic state the orchestrator already built up. `ctx`
            # may not exist if the exception fired before orchestrator.run
            # returned, so guard everything with getattr.
            ctx_local = locals().get("ctx", None)
            target_status = outer_status
            session.execute(
                text("""
                    UPDATE research_requests
                    SET status = :status,
                        error_message = :msg,
                        debug_log = :debug_log,
                        total_tokens = :tokens,
                        llm_calls = :llm_calls,
                        sites_found = :sites,
                        duration_ms = :duration,
                        completed_at = NOW()
                    WHERE id = :id
                """),
                {
                    "status": target_status,
                    "id": request_id,
                    "msg": str(exc),
                    "debug_log": json.dumps(
                        getattr(ctx_local, "debug_log", []) if ctx_local else []
                    ),
                    "tokens": getattr(ctx_local, "total_tokens", 0) if ctx_local else 0,
                    "llm_calls": getattr(ctx_local, "llm_call_count", 0) if ctx_local else 0,
                    "sites": len(ctx_local.registry.sources)
                    if ctx_local and hasattr(ctx_local, "registry")
                    else 0,
                    "duration": duration_ms,
                },
            )
            session.commit()

    finally:
        # Delay cleanup so SSE streams have time to read the terminal event
        try:
            loop = asyncio.get_running_loop()
            loop.call_later(10, _live_events.pop, request_id, None)
        except RuntimeError:
            _live_events.pop(request_id, None)


# Hard ceiling on a single research run. The user's explicit guidance is that
# research QUALITY (sources, citations, image grounding) is paramount — the
# pipeline must be free to do as many saturation rounds + cross-pollinations as
# the angles need. Since 2026-07-26 runs crawl at low priority (~12-18h normal,
# quota troughs stack on top) against a 72h orchestrator deadline
# (ResearchConfig.deadline_hours) that force-finishes gracefully. This worker
# ceiling sits just above it as the stuck-process safety net — it must only
# fire when the orchestrator's own deadline handling is itself wedged.
_REQUEST_TIMEOUT_SECONDS = 73 * 3600  # 73 hours (orchestrator deadline + 1h)

# --- Stall detection -------------------------------------------------------
# A healthy run flushes climbing counters to the DB every ~30s
# (convergence_orchestrator._flush_progress_to_db). A stalled run — e.g. M3
# structured-output never letting an angle saturate — freezes those counters
# while still heartbeating, so it would otherwise sit until the 12h hard
# timeout above and hold the single worker slot the whole time. We cancel a run
# whose counters show ZERO movement for _STALL_GRACE_SECONDS. Because the signal
# is "no progress" (not wall-clock), a slow-but-healthy long run that keeps
# advancing is never killed early.
_STALL_GRACE_SECONDS = 2700  # 45 min of zero progress => stalled
_STALL_POLL_SECONDS = 180  # re-check the DB counters every 3 min


class _StallDetected(Exception):
    """Raised when a running request stops making any progress."""


def _limiter_frozen() -> bool:
    """True while the MiniMax limiter is quota-frozen. Used by the stall
    guard: frozen counters during a quota pause are expected, not a stall."""
    try:
        from pipeline.lyra.minimax_limiter import limiter

        return limiter.is_frozen()
    except Exception:  # noqa: BLE001 — a read failure must not kill the guard
        return False


def _read_limiter_activity(is_batch: bool) -> int | None:
    """The limiter's lifetime request count — a liveness signal for the
    stall guard (2026-07-19). The DB progress counters only flush on event
    emissions, and event gaps stretch past the stall grace when the
    limiter crawls after a quota trough (observed live: 16min gap at
    delay 42s / concurrency 2; ee3493e8 on 07-13 was killed at 45min with
    349 calls / 1M tokens on the clock — almost certainly a healthy
    crawling run, not a hang). A climbing count means LLM calls are
    flowing, so the run is NOT stalled regardless of the DB sig. Caveat:
    the counters are process-wide per lane, so a true stall is only
    detected once that lane goes quiet — the 73h hard timeout backstops
    that corner."""
    try:
        from pipeline.lyra.minimax_limiter import limiter

        stats = limiter.stats
        # Lane-aware (2026-07-26): a batch run reads its own crawl-lane
        # counter — otherwise a concurrent full-speed UI run would keep
        # total_requests climbing and mask a genuinely stalled batch run.
        return stats["low_lane_calls"] if is_batch else stats["total_requests"]
    except Exception:  # noqa: BLE001 — a read failure must not kill the guard
        return None


def _mark_failed_running(request_id: str, msg: str) -> None:
    """Mark a still-'running' request failed and release its credit reservation."""
    _release_reservation(request_id)
    from pipeline.lyra.research_graph import reset_node_for_failed_request

    # Timeout/stall kills land here — the seed node would otherwise sit
    # 'researching' forever (Follow-up-Ticket 6).
    reset_node_for_failed_request(request_id)
    try:
        with get_session() as session:
            session.execute(
                text(
                    "UPDATE research_requests SET status = 'failed', "
                    "error_message = :msg, completed_at = NOW() "
                    "WHERE id = :id AND status = 'running'"
                ),
                {"id": request_id, "msg": msg},
            )
            session.commit()
    except Exception as exc:
        logger.warning("[THEO] Failed to mark request %s as failed: %s", request_id, exc)


def _read_progress_sig(request_id: str) -> tuple | None:
    """(llm_calls, total_tokens, sites_found, tools_used) from the DB, or None."""
    try:
        with get_session() as session:
            row = session.execute(
                text(
                    "SELECT llm_calls, total_tokens, sites_found, tools_used "
                    "FROM research_requests WHERE id = :id"
                ),
                {"id": request_id},
            ).fetchone()
        return (row.llm_calls, row.total_tokens, row.sites_found, row.tools_used) if row else None
    except Exception as exc:
        logger.warning("[THEO] progress read failed for %s: %s", request_id, exc)
        return None


def _auto_publish(request_id: str) -> None:
    """DB-level publish for quality-gate-passing batch papers (2026-07-26).

    Mirrors POST /theo/research/{id}/publish minus the HTTP layer: fresh
    papers have no section approvals, so the legacy approved_by path applies
    with the full report as the published view. No Discord role refresh —
    the feeder's papers are system-authored ('Theo'). Gate failures leave
    the paper unpublished and ping the Discord webhook for manual review.
    """
    from datetime import UTC, datetime

    from api.routes.theo import _make_slug
    from api.services.theo_config import THEO_AUTO_PUBLISH_AUTHOR

    try:
        with get_session() as session:
            row = session.execute(
                text("""
                    SELECT question, result_json, is_public, user_id
                    FROM research_requests WHERE id = :id
                """),
                {"id": request_id},
            ).fetchone()
            if not row or row.is_public:
                return
            result = json.loads(row.result_json) if row.result_json else {}
            quality = result.get("quality_score") or {}

            # Citation integrity is recomputed on the artifact — the stored
            # audit can be stale. The deterministic repair never fabricates
            # or remaps a citation, so auto-publish may apply it directly.
            from pipeline.lyra.theo_citations import validate_or_repair

            report_text = result.get("report") or ""
            repaired_text, artifact_report = validate_or_repair(report_text)
            if repaired_text != report_text:
                logger.info("[THEO] Auto-repaired citations for %s before publish", request_id)
                result["report"] = repaired_text
            result["audit"] = artifact_report

            if not (quality.get("passed") and artifact_report["passed"]):
                logger.warning(
                    "[THEO] Auto-publish gate failed for %s (quality=%s audit=%s) — held.",
                    request_id,
                    quality.get("passed"),
                    artifact_report["passed"],
                )
                try:
                    from api.services.notify import send_discord_webhook

                    send_discord_webhook(
                        {
                            "embeds": [
                                {
                                    "title": "Theo paper held — quality gate failed",
                                    "description": (
                                        f"`{request_id}`\n"
                                        f"**{(result.get('title') or row.question)[:200]}**\n"
                                        f"quality_passed={quality.get('passed')} "
                                        f"recomputed_audit_passed={artifact_report['passed']}\n"
                                        f"issues: {(artifact_report.get('issues') or [])[:3]}"
                                    ),
                                    "color": 0xE67E22,
                                }
                            ]
                        }
                    )
                except Exception:  # noqa: BLE001 — notification is best-effort
                    pass
                return

            title = result.get("title") or row.question
            slug = _make_slug(title)
            collision = session.execute(
                text("SELECT 1 FROM research_requests WHERE slug = :slug AND id != :id"),
                {"slug": slug, "id": request_id},
            ).fetchone()
            if collision:
                slug = f"{slug}-{request_id[:8]}"

            now_iso = datetime.now(UTC).isoformat()
            result["approved_by"] = THEO_AUTO_PUBLISH_AUTHOR
            result["approved_at"] = now_iso
            result["published_report"] = result.get("report") or ""
            result["published_block_ids"] = []
            result["published_hero_image"] = result.get("hero_image")

            session.execute(
                text("""
                    UPDATE research_requests
                    SET is_public = TRUE,
                        published_at = NOW(),
                        published_by = :author,
                        slug = :slug,
                        result_json = :result
                    WHERE id = :id
                """),
                {
                    "id": request_id,
                    "author": THEO_AUTO_PUBLISH_AUTHOR,
                    "slug": slug,
                    "result": json.dumps(result),
                },
            )
            session.commit()
            author_discord_id = row.user_id

        logger.info("[THEO] Auto-published %s as %r", request_id, slug)
        try:
            from pipeline.lyra.theo_research_index import index_paper

            index_paper(
                paper_id=request_id,
                paper_text=result["published_report"],
                paper_title=title,
                paper_slug=slug,
                author_username=THEO_AUTO_PUBLISH_AUTHOR,
                author_discord_id=author_discord_id,
                published_at=now_iso,
            )
        except Exception as exc:  # noqa: BLE001 — same best-effort as the route
            logger.error("[THEO] Qdrant indexing failed for %s: %s", request_id, exc)
    except Exception as exc:  # noqa: BLE001 — auto-publish must never kill the worker
        logger.error("[THEO] Auto-publish crashed for %s: %s", request_id, exc, exc_info=True)
        try:
            from api.services.notify import send_discord_webhook

            send_discord_webhook(
                {
                    "embeds": [
                        {
                            "title": "Theo auto-publish CRASHED — paper stuck unpublished",
                            "description": f"`{request_id}`\n{type(exc).__name__}: {exc}",
                            "color": 0xE74C3C,
                        }
                    ]
                }
            )
        except Exception:  # noqa: BLE001 — notification is best-effort
            pass


async def _run_with_stall_guard(
    request_id: str, question: str, specialist_options: dict | None, is_batch: bool
) -> None:
    """Run a request, cancelling it if its progress counters freeze.

    Raises ``_StallDetected`` when no counter has moved for
    ``_STALL_GRACE_SECONDS``; a still-advancing run is left alone no matter how
    long it takes.
    """
    task = asyncio.create_task(_process_request(request_id, question, specialist_options, is_batch))
    last_sig = _read_progress_sig(request_id)
    last_activity = _read_limiter_activity(is_batch)
    last_change = time.monotonic()
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=_STALL_POLL_SECONDS)
            if task in done:
                return task.result()
            sig = _read_progress_sig(request_id)
            activity = _read_limiter_activity(is_batch)
            now = time.monotonic()
            if sig is not None and sig != last_sig:
                last_sig, last_change = sig, now
            elif _limiter_frozen():
                # Quota pause: the run's LLM calls are sleeping inside the
                # frozen limiter, so counters CANNOT move. Known cause, not
                # a stall — reset the clock so the pause doesn't accumulate
                # toward the grace window.
                last_change = now
            elif activity is not None and activity != last_activity:
                # LLM calls are flowing even though no event has flushed
                # the DB counters yet — a slow phase (e.g. post-trough
                # crawl), not a stall (2026-07-19).
                last_change = now
            elif (now - last_change) >= _STALL_GRACE_SECONDS:
                logger.error(
                    "[THEO] Request %s no progress for %ss (sig=%s) — cancelling stalled run.",
                    request_id,
                    _STALL_GRACE_SECONDS,
                    last_sig,
                )
                task.cancel()
                try:
                    await task
                except BaseException:  # noqa: BLE001 — swallow CancelledError + cleanup errors
                    pass
                raise _StallDetected
            if activity is not None:
                last_activity = activity
    finally:
        if not task.done():
            task.cancel()


# --- Batch pacing gate (2026-07-04) ----------------------------------------
# Batch tasks (is_batch=TRUE) start at most once per THEO_MIN_TASK_INTERVAL_S,
# start-to-start. The clock is MAX(started_at) over ALL tasks — a manual UI
# run burns the same shared quota, so it pushes the next batch slot back. UI
# rows themselves bypass the gate entirely (they are is_batch=FALSE in the
# claim query). DB-based, so the pacing survives worker restarts and deploys.


def _batch_gate_open(last_start_age_s: float | None, min_interval_s: float) -> bool:
    """True when a batch task may start: nothing ever started, or the most
    recent start is at least min_interval_s ago."""
    return last_start_age_s is None or last_start_age_s >= min_interval_s


def _hours_until_weekly_reset(now_utc: datetime) -> float:
    """Hours until the next MiniMax weekly reset (Monday 00:00 UTC)."""
    days_ahead = (7 - now_utc.weekday()) % 7
    reset = (now_utc + timedelta(days=days_ahead)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    if reset <= now_utc:
        reset += timedelta(days=7)
    return (reset - now_utc).total_seconds() / 3600


# 10-min cache for the measured batch-run duration — the poll loop calls the
# gate every ~3s and the average only moves when a paper completes.
_avg_run_cache: tuple[float, float] | None = None


def _avg_batch_run_hours() -> float:
    """Measured wall-clock hours of one batch paper: average of the last 5
    completed batch runs (duration_ms includes crawl-lane pacing and quota
    sleeps). Falls back to THEO_PAPER_EST_HOURS without history."""
    global _avg_run_cache
    from api.services.theo_config import THEO_PAPER_EST_HOURS

    now = time.monotonic()
    if _avg_run_cache and now - _avg_run_cache[1] < 600:
        return _avg_run_cache[0]
    hours = THEO_PAPER_EST_HOURS
    try:
        with get_session() as session:
            avg_ms = session.execute(
                text("""
                    SELECT AVG(duration_ms) FROM (
                        SELECT duration_ms FROM research_requests
                        WHERE is_batch = TRUE AND status = 'completed'
                          AND duration_ms IS NOT NULL
                        ORDER BY completed_at DESC LIMIT 5
                    ) recent
                """)
            ).scalar()
        if avg_ms:
            hours = float(avg_ms) / 3_600_000
    except Exception as exc:
        logger.warning("[THEO] batch run duration read failed: %s", exc)
    _avg_run_cache = (hours, now)
    return hours


def _batch_claim_allowed(
    gate_open: bool,
    tier: str,
    weekly_pct: float | None,
    now_utc: datetime | None = None,
    avg_run_hours: float | None = None,
) -> bool:
    """Batch rows need an open pacing gate, a positively HEALTHY watchdog,
    and an end-of-week start that the weekly budget can afford (2026-08-04).

    The weekly MiniMax budget resets Monday 00:00 UTC; batch runs spend the
    week's SURPLUS instead of starving Lyra and interactive research right
    after the reset. Two adaptive conditions, env-tunable:

    1. Window: at most THEO_BATCH_MAX_DAYS_TO_RESET days before the reset
       (default 3 = Friday 00:00 UTC) — surplus is use-it-or-lose-it there.
    2. Budget: the weekly remaining must cover the share of one paper that
       burns BEFORE the reset (uniform burn at the measured pace of recent
       batch papers) plus the Lyra reserve for every remaining day. The
       weekend's LAST run may cross the reset — it finishes on Monday's
       fresh budget, and the window condition keeps Monday itself free of
       NEW starts. What must never happen is the weekly hitting 0%
       mid-run: that aborts the run (error 2056) and freezes everything
       else on the shared plan with it.

    UNKNOWN tier (no probe yet / watchdog down) and a missing weekly value
    block: batch runs never start blind (2026-07-19). The tier ladder is
    the deeper backstop — weekly <= QUOTA_WEEKLY_FREEZE_PCT reads
    EXHAUSTED and never claims."""
    from api.services.theo_config import (
        THEO_BATCH_MAX_DAYS_TO_RESET,
        THEO_LYRA_DAILY_RESERVE_PCT,
        THEO_PAPER_COST_PCT,
    )

    if not gate_open or tier != "HEALTHY":
        return False
    if weekly_pct is None:
        return False
    hours_left = _hours_until_weekly_reset(now_utc or datetime.now(UTC))
    days_left = hours_left / 24
    if days_left > THEO_BATCH_MAX_DAYS_TO_RESET:
        return False
    run_hours = max(avg_run_hours if avg_run_hours is not None else _avg_batch_run_hours(), 0.1)
    pre_reset_share = min(1.0, hours_left / run_hours)
    required = pre_reset_share * THEO_PAPER_COST_PCT + days_left * THEO_LYRA_DAILY_RESERVE_PCT
    return weekly_pct >= required


def _read_last_start_age_s() -> float | None:
    """Seconds since the most recent task start (any kind), or None if no
    task has ever started."""
    try:
        with get_session() as session:
            row = session.execute(
                text("SELECT EXTRACT(EPOCH FROM (NOW() - MAX(started_at))) FROM research_requests")
            ).fetchone()
        return float(row[0]) if row and row[0] is not None else None
    except Exception as exc:
        logger.warning("[THEO] last-start read failed: %s", exc)
        return None


async def _poll_loop() -> None:
    """Main polling loop — picks up queued requests and processes them."""
    print("[THEO] Worker poll loop started", flush=True)
    logger.info("[THEO] Worker poll loop started")
    gate_was_open: bool | None = None
    while not _shutdown:
        _touch_worker_heartbeat()
        try:
            # Quota watchdog gate (2026-06-28). When the tier is EXHAUSTED
            # the limiter is already frozen, so any run we pick up would
            # sleep inside the limiter from its very first LLM call. Sleep
            # and skip; the watchdog lifts the gate once the window has
            # recovered past QUOTA_RESUME_PCT.
            tier = "UNKNOWN"
            weekly_pct = None
            try:
                from api.services.theo_quota_monitor import get_watchdog_state

                watchdog = get_watchdog_state()
                tier = watchdog.get("tier", "UNKNOWN")
                weekly_pct = watchdog.get("weekly_remaining_percent")
                if tier == "EXHAUSTED":
                    await asyncio.sleep(60)
                    continue
            except Exception:  # noqa: BLE001 — never let a watchdog read kill the poll loop
                pass
            # Batch pacing: while the gate is closed (or the watchdog is not
            # positively HEALTHY, or the weekly budget won't fit a whole
            # paper, or it is not an end-of-week start day), batch rows are
            # invisible to the claim query below — a younger UI row still
            # gets picked up immediately.
            gate_open = _batch_gate_open(_read_last_start_age_s(), THEO_MIN_TASK_INTERVAL_S)
            batch_allowed = _batch_claim_allowed(gate_open, tier, weekly_pct)
            if gate_open != gate_was_open:
                logger.info(
                    "[THEO] Batch pacing gate %s (min start-to-start interval %ss, "
                    "tier=%s, weekly=%s%%)",
                    "OPEN" if gate_open else "CLOSED",
                    THEO_MIN_TASK_INTERVAL_S,
                    tier,
                    weekly_pct,
                )
                gate_was_open = gate_open

            # Prune finished supervisors (defensive — _supervise removes
            # itself in its finally; this also catches cancelled tasks).
            for rid in [r for r, (t, _b) in _active_runs.items() if t.done()]:
                _active_runs.pop(rid, None)

            if len(_active_runs) >= THEO_PARALLEL_SLOTS:
                await asyncio.sleep(3)
                continue

            # Two-lane slot rule: at most ONE batch run at a time — the
            # remaining slot is reserved for interactive (UI) submissions.
            batch_running = any(b for (_t, b) in _active_runs.values())
            batch_claimable = batch_allowed and not batch_running

            # Find the oldest runnable request. 'queued' = freshly submitted;
            # 'deferred' = quota hit earlier, ready for a retry after the 5min
            # back-off window. Without the timestamp check a deferred row would
            # get re-claimed on the very next poll iteration and re-defer
            # immediately, creating a tight loop. Rows already being processed
            # are excluded in-process — the run only flips the DB row to
            # 'running' asynchronously, so the claim query alone would
            # re-claim it on the next iteration.
            active_ids = list(_active_runs.keys()) or [""]
            with get_session() as session:
                row = session.execute(
                    text("""
                        SELECT id::text, question, specialist_options, is_batch
                        FROM research_requests
                        WHERE (status = 'queued'
                               OR (status = 'deferred'
                                   AND completed_at < NOW() - INTERVAL '5 minutes'))
                          AND (is_batch = FALSE OR :batch_claimable)
                          AND NOT (id::text = ANY(:active_ids))
                        -- UI submissions (is_batch=FALSE) always outrank the
                        -- batch backlog: without this, a fresh UI task sorted
                        -- behind 47 July batch rows on created_at alone.
                        ORDER BY is_batch ASC, created_at ASC
                        LIMIT 1
                    """),
                    {"batch_claimable": batch_claimable, "active_ids": active_ids},
                ).fetchone()

            if row:
                task = asyncio.create_task(
                    _supervise(row.id, row.question, row.specialist_options, bool(row.is_batch))
                )
                _active_runs[row.id] = (task, bool(row.is_batch))
                logger.info(
                    "[THEO] Claimed %s (batch=%s) — %d/%d slots busy",
                    row.id,
                    bool(row.is_batch),
                    len(_active_runs),
                    THEO_PARALLEL_SLOTS,
                )
                # Inter-claim backoff (2026-06-29): give the watchdog probe
                # time to flag DEGRADED/EXHAUSTED before the next claim.
                from api.services.theo_config import THEO_INTER_TASK_BACKOFF_S

                await asyncio.sleep(THEO_INTER_TASK_BACKOFF_S)
            else:
                await asyncio.sleep(3)  # No work — wait before polling again

        except Exception as e:
            logger.error(f"[THEO] Poll loop error: {e}", exc_info=True)
            await asyncio.sleep(5)


async def _supervise(
    request_id: str, question: str, specialist_options: dict | None, is_batch: bool
) -> None:
    """Run one request to completion with timeout + stall handling.

    Runs as its own task so the poll loop keeps claiming: a full-speed UI
    run executes concurrently with a crawling batch run."""
    try:
        try:
            await asyncio.wait_for(
                _run_with_stall_guard(request_id, question, specialist_options, is_batch),
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            logger.error(
                "[THEO] Request %s exceeded %ss hard timeout — marking failed.",
                request_id,
                _REQUEST_TIMEOUT_SECONDS,
            )
            _mark_failed_running(
                request_id,
                f"Request exceeded {_REQUEST_TIMEOUT_SECONDS}s timeout and was force-cancelled.",
            )
        except _StallDetected:
            logger.error(
                "[THEO] Request %s stalled (no progress for %ss) — marking failed.",
                request_id,
                _STALL_GRACE_SECONDS,
            )
            _mark_failed_running(
                request_id,
                f"Request made no progress for {_STALL_GRACE_SECONDS}s "
                "(stalled) and was cancelled.",
            )
        except Exception:
            logger.exception("[THEO] Supervisor for %s crashed", request_id)
    finally:
        _active_runs.pop(request_id, None)


async def _maybe_run_thinking_pass() -> None:
    """Nightly thinking pass (Mon-Thu 02-05 UTC): miner + curator.

    `thinking_window_open` is checked FIRST and needs no DB access — the
    window is shut ~93% of the week, so most feeder polls return here
    without ever touching the database. Only inside the window do we read
    thinking_log for the last pass timestamp (coerced to tz-aware UTC: the
    column is `timestamp without time zone`, and thinking_pass_due requires
    aware datetimes on both sides — a naive value raises TypeError) and
    apply the 20h cooldown via thinking_pass_due().
    """
    from datetime import UTC as _UTC
    from datetime import datetime as _dt

    from pipeline.lyra.curator import (
        run_curator_pass,
        thinking_pass_due,
        thinking_window_open,
    )

    now = _dt.now(_UTC)
    if not thinking_window_open(now):
        return

    with get_session() as session:
        last_curator = session.execute(
            text("SELECT MAX(created_at) AS ts FROM thinking_log WHERE kind = 'curator'")
        ).fetchone()
    last_ts = last_curator.ts.replace(tzinfo=_UTC) if last_curator and last_curator.ts else None
    if thinking_pass_due(now, last_ts):
        logger.info("[THINK] Nightly thinking pass starting")
        # Pathological ceiling: a frozen limiter can hold this to_thread
        # call up to _QUOTA_WAIT_MAX_S (6h, minimax_limiter.py) before
        # QuotaExhaustedError unwinds it — accepted risk. The feeder's
        # injector/enqueue work catches up next iteration, and
        # run_curator_pass's failure row still closes the 20h gate either
        # way (it never raises past this call).
        await asyncio.to_thread(run_curator_pass)


async def _feeder_loop() -> None:
    """Keep the batch queue fed from the knowledge-graph frontier.

    Every 10 min: when no batch row is queued/running/deferred and the batch
    gate inputs allow a start, promote the best frontier node to a queued
    research_request. Source injectors run hourly from the same loop (cheap
    SQL only). Pre-existing batch rows always drain first — the feeder only
    acts on an EMPTY batch queue.
    """
    import uuid as _uuid

    injector_last = 0.0
    full_ingest_last: float | None = None
    while not _shutdown:
        try:
            now = time.monotonic()
            if now - injector_last >= 3600:
                from pipeline.lyra.graph_injectors import run_all_injectors

                await asyncio.to_thread(run_all_injectors)
                injector_last = now
            # Full structural ingest (sites, periods, empires, stories,
            # videos, journals, entities): once at startup — so a deploy
            # refreshes the graph without manual steps — then nightly.
            if full_ingest_last is None or now - full_ingest_last >= 24 * 3600:
                from pipeline.lyra.graph_full_ingest import run_full_ingest

                await asyncio.to_thread(run_full_ingest)
                full_ingest_last = now

            # Nightly thinking pass (Mon-Thu 02-05 UTC): miner + curator.
            # last_pass comes from thinking_log so restarts don't double-run.
            await _maybe_run_thinking_pass()

            with get_session() as session:
                pending = session.execute(
                    text("""
                        SELECT COUNT(*) FROM research_requests
                        WHERE is_batch = TRUE
                          AND status IN ('queued', 'running', 'deferred')
                    """)
                ).scalar()

            if not pending:
                # Mirror the claim-side gating so we never enqueue into a
                # quota wall — the row would only sit and count against the
                # pacing clock.
                tier = "UNKNOWN"
                weekly_pct = None
                try:
                    from api.services.theo_quota_monitor import get_watchdog_state

                    watchdog = get_watchdog_state()
                    tier = watchdog.get("tier", "UNKNOWN")
                    weekly_pct = watchdog.get("weekly_remaining_percent")
                except Exception:  # noqa: BLE001 — watchdog read is best-effort
                    pass
                gate_open = _batch_gate_open(_read_last_start_age_s(), THEO_MIN_TASK_INTERVAL_S)
                if _batch_claim_allowed(gate_open, tier, weekly_pct):
                    from api.services.theo_config import THEO_FEEDER_USER_ID
                    from pipeline.lyra.research_graph import (
                        allow_synthesis,
                        link_node_to_request,
                        pick_next_frontier_topic,
                        question_for_node,
                        recent_batch_seed_kinds,
                    )

                    with get_session() as session:
                        recent_kinds = recent_batch_seed_kinds(session)
                        node = pick_next_frontier_topic(
                            session, include_synthesis=allow_synthesis(recent_kinds)
                        )
                        if node:
                            request_id = str(_uuid.uuid4())
                            session.execute(
                                text("""
                                    INSERT INTO research_requests
                                        (id, user_id, question, effort, status, is_batch)
                                    VALUES
                                        (CAST(:id AS uuid), :uid, :question, 'high',
                                         'queued', TRUE)
                                """),
                                {
                                    "id": request_id,
                                    "uid": THEO_FEEDER_USER_ID,
                                    "question": question_for_node(node),
                                },
                            )
                            session.commit()
                            link_node_to_request(node["id"], request_id, session)

                            from pipeline.lyra.thinking_log import log_thinking

                            log_thinking(
                                "run_event",
                                f"Queued from frontier: {node['label'][:200]}",
                                {"request_id": request_id, "kind": node["kind"]},
                            )
                            logger.info(
                                "[THEO] Feeder queued %s from frontier node %r",
                                request_id,
                                node["label"][:80],
                            )
        except Exception as exc:  # noqa: BLE001 — the feeder must keep running
            logger.error("[THEO] Feeder loop error: %s", exc)
        await asyncio.sleep(600)


async def cleanup_stale_deferred() -> None:
    """Fail out research requests stuck in 'deferred' too long.

    Runs hourly. A 'deferred' request is one that hit a quota exhaustion
    (2026-06-28 plan) and is waiting for the 5h-rolling window to reset.
    If quota does not recover within DEFERRED_MAX_AGE_HOURS, the request
    is marked 'failed' with a clear reason so the queue does not grow
    forever. The user's reserved credits are released.
    """
    from api.services.theo_config import DEFERRED_MAX_AGE_HOURS

    while not _shutdown:
        try:
            with get_session() as session:
                rows = session.execute(
                    text(
                        """
                        SELECT id::text, user_id
                        FROM research_requests
                        WHERE status = 'deferred'
                          AND completed_at < NOW() - (:hours * INTERVAL '1 hour')
                        """
                    ),
                    {"hours": DEFERRED_MAX_AGE_HOURS},
                ).fetchall()
                stale_ids = [r.id for r in rows]
            # NOTHING may await inside the session block: sleeping in here
            # parked an open transaction on research_requests for a full
            # hour, which blocked every ALTER TABLE behind it — it killed
            # two deploys (2026-08-06 migration 0010, 2026-08-07 0013).
            if not stale_ids:
                await asyncio.sleep(3600)
                continue
            with get_session() as session:
                reason = (
                    f"Quota did not recover within {DEFERRED_MAX_AGE_HOURS} hours "
                    f"after the run was deferred. Marked failed to keep the queue bounded."
                )
                # Reset seed nodes BEFORE committing the deferred -> failed
                # flip (atomicity fix, final review): reset_node_for_failed_request
                # only checks research_nodes.status = 'researching' — it
                # never looks at the request's status — so doing it first is
                # always safe, and it closes the window where the DB could
                # show request=failed with its node still stuck
                # 'researching' (e.g. on a crash between the two steps,
                # which the feeder's failure-cooldown NOT EXISTS clause
                # assumes never persists). Node claim is dead either way —
                # unlike 'deferred' itself, a request this stale is not
                # coming back (Ticket 6).
                from pipeline.lyra.research_graph import reset_node_for_failed_request

                for rid in stale_ids:
                    reset_node_for_failed_request(rid)
                session.execute(
                    text(
                        """
                        UPDATE research_requests
                        SET status = 'failed',
                            error_message = :msg,
                            completed_at = NOW()
                        WHERE id = ANY(:ids)
                          AND status = 'deferred'
                        """
                    ),
                    {"msg": reason, "ids": stale_ids},
                )
                session.commit()
            # Release credit reservations outside the session above — the
            # helper uses its own session, so the order relative to the
            # commit above doesn't matter.
            for rid in stale_ids:
                _release_reservation(rid)
            logger.warning(
                f"[THEO] Marked {len(stale_ids)} stale-deferred request(s) failed "
                f"(>{DEFERRED_MAX_AGE_HOURS}h without quota recovery)."
            )
        except Exception as e:
            logger.warning(f"[THEO] Stale-deferred cleanup error: {e}")
        await asyncio.sleep(3600)  # Every hour


_HEARTBEAT_FILE = Path("/tmp/theo_worker_heartbeat")  # noqa: S108 — container scratch


def _touch_worker_heartbeat() -> None:
    """Refresh the liveness file the theo-worker container's healthcheck reads.

    The poll loop wakes every few seconds and sleeps at most 60s (EXHAUSTED
    tier), so a file older than the compose threshold means the loop is
    wedged — not merely idle. Crash-safe by contract: liveness reporting must
    never be the thing that kills the worker.
    """
    try:
        _HEARTBEAT_FILE.touch()
    except OSError as exc:
        logger.debug("[THEO] heartbeat touch failed: %s", exc)


def stop_worker() -> None:
    """Ask every worker loop to exit at its next iteration.

    Used by the standalone worker container's SIGTERM handler
    (scripts/run_theo_worker.py); inside the API process the lifespan simply
    tears the task down.
    """
    global _shutdown
    _shutdown = True


async def start_worker() -> None:
    """Start the Theo worker background tasks."""
    global _shutdown
    _shutdown = False

    # Recover orphaned requests left in 'running' state from a previous crash
    try:
        with get_session() as session:
            result = session.execute(
                text("UPDATE research_requests SET status = 'queued' WHERE status = 'running'")
            )
            session.commit()
            if result.rowcount:
                logger.info(f"[THEO] Recovered {result.rowcount} orphaned running request(s)")
    except Exception as e:
        logger.warning(f"[THEO] Recovery check failed: {e}")

    async def _safe_poll_loop() -> None:
        """Wrapper that restarts _poll_loop on crash."""
        while not _shutdown:
            try:
                await _poll_loop()
            except Exception as exc:
                logger.error(f"[THEO] Poll loop crashed, restarting in 10s: {exc}", exc_info=True)
                await asyncio.sleep(10)

    asyncio.create_task(_safe_poll_loop())
    asyncio.create_task(_feeder_loop())
    asyncio.create_task(cleanup_stale_deferred())
    # Quota watchdog (2026-06-28 plan): a background daemon that probes
    # the MiniMax Token Plan every 60s, classifies the 5h-rolling
    # remaining budget into HEALTHY/DEGRADED/EXHAUSTED, freezes the
    # limiter on EXHAUSTED, and sends a Discord webhook on transitions.
    # The poll loop above also consults get_watchdog_state() and skips
    # pickup while EXHAUSTED, so this is the *active* half of the
    # self-throttling story.
    from api.services.theo_quota_monitor import start_watchdog

    start_watchdog()
    print("[THEO] Background worker tasks created", flush=True)
    logger.info("[THEO] Background worker tasks created")
