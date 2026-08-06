"""Best-effort writer for the thinking-layer activity feed (spec §7).

Every curator pass, miner batch and research-run lifecycle event lands here;
GET /api/v1/knowledge/activity serves it to the Knowledge page. A write
failure must never break the caller (injector pattern). Nothing in the
system ever reads thinking_log back for control flow — it is display-only
for the Knowledge timeline, which is what makes the blanket except
legitimate here.
"""

from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy import text

logger = logging.getLogger(__name__)


# Lazy + wrapped: keeps pipeline.database out of the import graph and gives tests a seam.
def _session_factory():
    from pipeline.database import get_session

    return get_session()


# Retention (audit P12, 2026-08-06): the feed was append-only with no pruning.
# Entries older than _PRUNE_DEFAULT_DAYS are deleted; failure entries
# (details.failed = true — the curator's "Denkstunde failed" rows) are kept
# for _PRUNE_FAILURE_DAYS because they are the only durable trace of why
# nightly passes died.
_PRUNE_DEFAULT_DAYS = 90
_PRUNE_FAILURE_DAYS = 365


def prune_thinking_log(session) -> int:
    """Delete aged thinking_log rows; returns the number deleted.

    Non-failure entries older than 90 days go; failure entries
    (details.failed = true) survive until 365 days. Commits itself (mirrors
    log_thinking). Deliberately not wrapped in try/except — the only caller
    is log_thinking's curator hook, which already sits inside its blanket
    best-effort except."""
    result = session.execute(
        text("""
            DELETE FROM thinking_log
            WHERE created_at < NOW() - make_interval(days => :failure_days)
               OR (created_at < NOW() - make_interval(days => :default_days)
                   AND COALESCE(details->>'failed', 'false') <> 'true')
        """),
        {"default_days": _PRUNE_DEFAULT_DAYS, "failure_days": _PRUNE_FAILURE_DAYS},
    )
    session.commit()
    return result.rowcount


def log_thinking(kind: str, summary: str, details: dict | None = None) -> None:
    """Append one activity-feed event. kind: curator | miner | run_event."""
    try:
        with _session_factory() as session:
            session.execute(
                text("""
                    INSERT INTO thinking_log (id, kind, summary, details, created_at)
                    VALUES (:id, :kind, :summary, CAST(:details AS jsonb), NOW())
                """),
                {
                    "id": str(uuid.uuid4()),
                    "kind": kind,
                    "summary": summary[:500],
                    "details": json.dumps(details, default=str) if details is not None else None,
                },
            )
            session.commit()
            if kind == "curator":
                # Retention hook: run_curator_pass writes exactly ONE
                # curator entry per nightly pass (success, empty-output or
                # failure branch), so pruning here fires once per pass —
                # after the entry committed — without touching the hot
                # miner/run_event write paths.
                deleted = prune_thinking_log(session)
                if deleted:
                    logger.info("[THINK] pruned %d aged thinking_log entries", deleted)
    except Exception as exc:  # noqa: BLE001 — feed is observability, never load-bearing
        logger.error("[THINK] log_thinking failed: %s", exc)
