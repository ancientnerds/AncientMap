#!/usr/bin/env python3
"""Entrypoint for the standalone Theo worker container.

The worker used to run as a background task inside the API process, which
meant every API rebuild killed the research run in flight — a 15h paper and
~9% of the weekly token budget, gone (observed 2026-08-07, twice). It now
owns its own container so a deploy can ship API/frontend changes while a run
continues; the deploy skips rebuilding this container while a run is active
and picks the new code up on the next deploy after it finishes.

Runs the same async entrypoints the API lifespan used to create:
  start_worker()    poll loop, batch pacing, stale-deferred cleanup, feeder
  start_watchdog()  MiniMax quota probe (the poll loop gates on its verdict)
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger("theo_worker_main")


async def _main() -> None:
    from api.services.theo_quota_monitor import start_watchdog
    from api.services.theo_worker import start_worker, stop_worker

    stop = asyncio.Event()

    def _request_stop(signum, _frame) -> None:
        # SIGTERM arrives on `docker stop` / compose recreate. Ask the worker
        # to stop claiming new work; the run in flight is still lost on the
        # container's grace-period kill — that is what the deploy-side skip
        # exists to prevent.
        logger.info("[THEO-CONTAINER] signal %s — shutting down", signum)
        stop.set()

    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)

    start_watchdog()
    worker = asyncio.create_task(start_worker())
    logger.info("[THEO-CONTAINER] worker + quota watchdog started")

    await stop.wait()
    stop_worker()
    worker.cancel()
    try:
        await worker
    except asyncio.CancelledError:
        pass
    logger.info("[THEO-CONTAINER] stopped")


if __name__ == "__main__":
    if os.environ.get("THEO_WORKER_DISABLED") == "1":
        logger.info("[THEO-CONTAINER] THEO_WORKER_DISABLED=1 — idling")
        # Keep the container up so compose does not restart-loop it.
        signal.pause()
        sys.exit(0)
    asyncio.run(_main())
