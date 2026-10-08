# SPDX-License-Identifier: AGPL-3.0-only
"""The nightly static export, 04:30 UTC.

D25 (2026-10-08): the files under ``public/data/`` carry the descriptions, names and images
the database repair changes, and nothing refreshed them but a hand-started export. After the
03:00 UTC reindex and the 03:15 backup, every night the export starts as the same background
job ``POST /api/sites/rebuild-static`` starts.

Both API instances run this loop; the job's advisory lock lets one of them export, and the
other logs the known state "already running". A deploy during the four-minute run kills the
child and leaves the status "interrupted"; the next night repairs it. The export is a child
process of the API container, which runs as uid 1000 - never root.
"""

from __future__ import annotations

import asyncio
import logging

from api.routes.vector_sync import _seconds_until_next
from api.services.background_jobs import JobAlreadyRunning, start_job
from api.services.rebuild_static import REBUILD_STATIC_JOB, run_static_export

logger = logging.getLogger(__name__)

EXPORT_HOUR_UTC = 4
EXPORT_MINUTE_UTC = 30

_export_task: asyncio.Task | None = None


def start_nightly_export() -> str:
    """Start tonight's export job: "started", or "running" when one already runs anywhere."""
    try:
        start_job(REBUILD_STATIC_JOB, run_static_export)
    except JobAlreadyRunning:
        logger.info("[STATIC-EXPORT] Nightly export skipped - a static export is already running")
        return "running"
    logger.info("[STATIC-EXPORT] Nightly export started")
    return "started"


async def schedule_static_export() -> None:
    """Loop forever: sleep until 04:30 UTC, then start the export job."""
    while True:
        wait = _seconds_until_next(EXPORT_HOUR_UTC, EXPORT_MINUTE_UTC)
        logger.info("[STATIC-EXPORT] Next nightly export in %.1fh", wait / 3600)
        await asyncio.sleep(wait)
        try:
            await asyncio.to_thread(start_nightly_export)
        except Exception:
            # The job could not start (the database is down): tonight's export is lost and
            # said so loudly; the loop goes on to tomorrow's.
            logger.exception("[STATIC-EXPORT] Nightly export could not start")


def start_static_export_scheduler() -> None:
    """Create the nightly export task. Call from lifespan."""
    global _export_task
    _export_task = asyncio.create_task(schedule_static_export())
    logger.info("[STATIC-EXPORT] Nightly export scheduler started")
