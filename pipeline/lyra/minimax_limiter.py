"""Global adaptive rate limiter for all MiniMax API calls.

Sits at the lowest level — both call_api() and minimax_chat_anthropic()
go through this limiter. One singleton shared across all pipelines
(Lyra stories, journals, radar, Theo research, etc.).

Design:
- Dynamic concurrency: starts at max, halves on rate limit, grows back on success
- Adaptive delay between requests: increases on error, decreases on success
- Thread-safe (both call paths are synchronous, called via to_thread)
- Stats tracking for observability

Usage:
    from pipeline.lyra.minimax_limiter import limiter

    with limiter.request() as slot:
        response = client.messages.create(...)
        slot.report_success()
    # or on error:
        slot.report_rate_limit()
"""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass

logger = logging.getLogger(__name__)


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


class MiniMaxLimiter:
    """Adaptive rate limiter with dynamic concurrency and backoff.

    Concurrency starts at max_concurrency and automatically scales:
    - On rate limit: halve active slots (floor at min_concurrency)
    - On 10 consecutive successes: add 5 slots (ceiling at max_concurrency)

    Thread-safe. All MiniMax call paths must go through this.
    """

    def __init__(
        self,
        max_concurrency: int = 100,
        min_concurrency: int = 3,
        base_delay: float = 0.1,
        max_delay: float = 30.0,
        grow_after_successes: int = 10,
        grow_step: int = 5,
    ):
        self._lock = threading.Lock()
        self._max_concurrency = max_concurrency
        self._min_concurrency = min_concurrency
        self._current_concurrency = max_concurrency
        self._active_count = 0
        self._condition = threading.Condition(self._lock)

        # Delay
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._current_delay = base_delay
        self._last_call_time = 0.0

        # Growth
        self._grow_after = grow_after_successes
        self._grow_step = grow_step

        # Stats
        self._total_requests = 0
        self._total_429s = 0
        self._consecutive_429s = 0
        self._consecutive_successes = 0

    @contextmanager
    def request(self):
        """Acquire a rate-limited slot. Blocks if at concurrency limit."""
        # Wait for an available slot
        with self._condition:
            while self._active_count >= self._current_concurrency:
                self._condition.wait()
            self._active_count += 1
            self._total_requests += 1
            delay = self._current_delay
            last = self._last_call_time

        # Enforce minimum delay between requests
        now = time.monotonic()
        wait = delay - (now - last)
        if wait > 0:
            time.sleep(wait)

        with self._lock:
            self._last_call_time = time.monotonic()

        slot = _Slot(_limiter=self)
        try:
            yield slot
        finally:
            with self._condition:
                self._active_count -= 1
                self._condition.notify()

    def _on_success(self) -> None:
        with self._lock:
            self._consecutive_successes += 1
            self._consecutive_429s = 0

            # Reduce delay after sustained success
            if (
                self._consecutive_successes >= self._grow_after
                and self._current_delay > self._base_delay
            ):
                old = self._current_delay
                self._current_delay = max(self._base_delay, self._current_delay * 0.7)
                if old != self._current_delay:
                    logger.debug(
                        "[minimax-limiter] Delay reduced: %.2fs -> %.2fs",
                        old,
                        self._current_delay,
                    )

            # Grow concurrency after sustained success
            if (
                self._consecutive_successes >= self._grow_after
                and self._current_concurrency < self._max_concurrency
            ):
                old = self._current_concurrency
                self._current_concurrency = min(
                    self._max_concurrency,
                    self._current_concurrency + self._grow_step,
                )
                if old != self._current_concurrency:
                    logger.info(
                        "[minimax-limiter] Concurrency increased: %d -> %d (after %d successes)",
                        old,
                        self._current_concurrency,
                        self._consecutive_successes,
                    )
                self._consecutive_successes = 0  # reset counter after growth

    def _on_rate_limit(self) -> None:
        with self._lock:
            self._total_429s += 1
            self._consecutive_429s += 1
            self._consecutive_successes = 0

            # Double the delay
            old_delay = self._current_delay
            self._current_delay = min(self._max_delay, self._current_delay * 2)

            # Halve concurrency
            old_conc = self._current_concurrency
            self._current_concurrency = max(
                self._min_concurrency,
                self._current_concurrency // 2,
            )

            logger.warning(
                "[minimax-limiter] Rate limited (#%d). Delay: %.2fs -> %.2fs. "
                "Concurrency: %d -> %d. Total: %d req, %d limited.",
                self._consecutive_429s,
                old_delay,
                self._current_delay,
                old_conc,
                self._current_concurrency,
                self._total_requests,
                self._total_429s,
            )

    def reset(self) -> None:
        """Reset to max concurrency and base delay. Call at start of each research task."""
        with self._lock:
            self._current_concurrency = self._max_concurrency
            self._current_delay = self._base_delay
            self._consecutive_429s = 0
            self._consecutive_successes = 0
            logger.info(
                "[minimax-limiter] Reset: concurrency=%d, delay=%.2fs",
                self._current_concurrency,
                self._current_delay,
            )

    @property
    def stats(self) -> dict:
        with self._lock:
            return {
                "total_requests": self._total_requests,
                "total_429s": self._total_429s,
                "current_delay": round(self._current_delay, 3),
                "current_concurrency": self._current_concurrency,
                "active_count": self._active_count,
                "consecutive_429s": self._consecutive_429s,
                "consecutive_successes": self._consecutive_successes,
            }


# Singleton
limiter = MiniMaxLimiter()
