"""Global adaptive rate limiter for all MiniMax API calls.

Sits at the lowest level — both call_api() and minimax_chat_anthropic()
go through this limiter. One singleton shared across all pipelines
(Lyra stories, journals, radar, Theo research, etc.).

Design:
- BoundedSemaphore controls max concurrency (default 3)
- Adaptive delay between requests: increases on 429, decreases on success
- Thread-safe (both call paths are synchronous, called via to_thread)
- Stats tracking for observability

Usage:
    from pipeline.lyra.minimax_limiter import limiter

    with limiter.request() as slot:
        response = client.messages.create(...)
        slot.report_success()
    # or on 429:
        slot.report_rate_limit()

MiniMax Token Plan limits (2026):
- Starter: 1,500 req/5hr, concurrency=1 during peak
- Plus: 4,500 req/5hr, concurrency=1 during peak
- Max: 15,000 req/5hr, concurrency=2 during peak
- Pay-as-you-go: 500 RPM
"""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Slot — returned by the context manager, caller reports success/failure
# ---------------------------------------------------------------------------


@dataclass
class _Slot:
    """Handle returned to the caller inside a `with limiter.request()` block."""

    _limiter: MiniMaxLimiter
    _was_rate_limited: bool = False

    def report_success(self) -> None:
        """Call after a successful API response."""
        self._limiter._on_success()

    def report_rate_limit(self) -> None:
        """Call when the API returns 429 or concurrency-related error."""
        self._was_rate_limited = True
        self._limiter._on_rate_limit()


# ---------------------------------------------------------------------------
# Limiter — singleton
# ---------------------------------------------------------------------------


class MiniMaxLimiter:
    """Adaptive rate limiter with concurrency control and backoff.

    Thread-safe. All MiniMax call paths must go through this.
    """

    def __init__(
        self,
        max_concurrency: int = 100,
        base_delay: float = 0.3,
        max_delay: float = 30.0,
    ):
        self._semaphore = threading.BoundedSemaphore(max_concurrency)
        self._lock = threading.Lock()
        self._max_concurrency = max_concurrency
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._current_delay = base_delay
        self._last_call_time = 0.0

        # Stats
        self._total_requests = 0
        self._total_429s = 0
        self._consecutive_429s = 0
        self._consecutive_successes = 0

    @contextmanager
    def request(self):
        """Acquire a rate-limited slot. Blocks if at concurrency limit.

        Usage:
            with limiter.request() as slot:
                try:
                    response = client.messages.create(...)
                    slot.report_success()
                except RateLimitError:
                    slot.report_rate_limit()
                    raise
        """
        self._semaphore.acquire()
        try:
            # Enforce minimum delay between requests
            with self._lock:
                now = time.monotonic()
                wait = self._current_delay - (now - self._last_call_time)
                self._total_requests += 1

            if wait > 0:
                time.sleep(wait)

            with self._lock:
                self._last_call_time = time.monotonic()

            slot = _Slot(_limiter=self)
            yield slot
        finally:
            self._semaphore.release()

    def _on_success(self) -> None:
        with self._lock:
            self._consecutive_successes += 1
            self._consecutive_429s = 0
            # Gradually reduce delay back toward base after sustained success
            if self._consecutive_successes >= 10 and self._current_delay > self._base_delay:
                old = self._current_delay
                self._current_delay = max(self._base_delay, self._current_delay * 0.7)
                if old != self._current_delay:
                    logger.debug(
                        "[minimax-limiter] Delay reduced: %.2fs -> %.2fs (after %d successes)",
                        old,
                        self._current_delay,
                        self._consecutive_successes,
                    )

    def _on_rate_limit(self) -> None:
        with self._lock:
            self._total_429s += 1
            self._consecutive_429s += 1
            self._consecutive_successes = 0
            old = self._current_delay
            # Double the delay, capped at max_delay
            self._current_delay = min(self._max_delay, self._current_delay * 2)
            logger.warning(
                "[minimax-limiter] Rate limited (429 #%d). Delay: %.2fs -> %.2fs. "
                "Total: %d requests, %d rate-limited.",
                self._consecutive_429s,
                old,
                self._current_delay,
                self._total_requests,
                self._total_429s,
            )

    @property
    def stats(self) -> dict:
        with self._lock:
            return {
                "total_requests": self._total_requests,
                "total_429s": self._total_429s,
                "current_delay": round(self._current_delay, 3),
                "consecutive_429s": self._consecutive_429s,
                "consecutive_successes": self._consecutive_successes,
            }


# ---------------------------------------------------------------------------
# Singleton instance — import this
# ---------------------------------------------------------------------------

limiter = MiniMaxLimiter()
