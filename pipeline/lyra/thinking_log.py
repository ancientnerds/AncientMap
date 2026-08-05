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
    except Exception as exc:  # noqa: BLE001 — feed is observability, never load-bearing
        logger.error("[THINK] log_thinking failed: %s", exc)
