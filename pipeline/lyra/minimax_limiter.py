"""Global adaptive rate limiter for all MiniMax API calls.

Sits at the lowest level — both call_api() and minimax_chat_anthropic()
go through this limiter. One singleton shared across all pipelines
(Lyra stories, journals, radar, Theo research, etc.).

Design (2026-06-28 rewrite — see docs/superpowers/plans/2026-06-28-theo-rate-limit-defense.md):
- Adaptive concurrency (small range: 1-8) — for a *token-quota* bottleneck,
  pumping parallelism just burns budget faster. Old defaults (100 max,
  +5 per 10 successes) actively made it worse.
- Distinguishes RPS throttling (429 without quota text → adaptive backoff,
  the old behavior) from quota exhaustion (`"Token Plan usage limit
  reached"`, error code 2056, or `"usage limit"` substring) → FREEZE all
  new calls for `_QUOTA_FREEZE_SECONDS` (5min default). A 5h rolling
  window doesn't get shorter by retrying.
- The freeze self-clears on the next successful call (so a quick
  `probe_quota()` returning 200 will unfreeze for everyone).
- `reset()` is deprecated: it wipes learned state and previously reset
  to max_concurrency=100 at every new Theo run, which is the direct
  cause of the 82%-rate-limited 52-prompt batch on 2026-06-28.

Usage:
    from pipeline.lyra.minimax_limiter import limiter, QuotaExhaustedError

    with limiter.request() as slot:
        response = client.messages.create(...)
        slot.report_success()
    # or on a real 429:
        slot.report_rate_limit()
    # or on a quota-exhaustion 429 (Token Plan, error 2056, etc.):
        slot.report_quota_exhausted()  # next .request() raises QuotaExhaustedError
"""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class QuotaExhaustedError(RuntimeError):
    """Raised by limiter.request() when MiniMax reports a *quota* exhaustion 429
    (not a transient RPS throttle). Retrying won't help — the 5h rolling
    window must reset. The freeze self-clears after `_QUOTA_FREEZE_SECONDS`
    (default 300s) or on the next successful call."""


class InsufficientQuotaError(RuntimeError):
    """Raised by the orchestrator preflight when probe_minimax_quota() reports
    the 5h-rolling remaining budget is below a sane floor for a full run
    (default 500k tokens). Different from QuotaExhaustedError: this one fires
    *before* the run starts, never making any LLM calls. The worker should
    mark the request 'deferred' rather than 'failed'."""


# How long to refuse all new MiniMax calls after a quota-exhaustion 429.
# 5min is enough that probe_quota() (cache 60s) sees a fresh window; cheap
# to wait out if the rolling window already reset.
_QUOTA_FREEZE_SECONDS = 300

# Substrings that identify a *quota* 429 vs a transient RPS 429. The MiniMax
# Anthropic-compatible endpoint returns these in the error message body
# (e.g. `'message': 'Token Plan usage limit reached: Upgrade your Token Plan
# or purchase Credits for more usage. (2056)'`). Case-insensitive match.
#
# 2026-06-29: added "token plan rate limit reached" and "(2062)" — MiniMax
# distinguishes two flavors of Token Plan cap: (2056) hard-quota-exhausted,
# (2062) rate-limit-on-plan. Both have the same remediation (upgrade or
# buy credits), so the limiter must treat both as quota freezes, not as
# transient throttles. Without these markers, 2062s were slipping through
# as "transient" and only adaptive-backoff'ing — wasting the probe-based
# freeze the watchdog sets up.
_QUOTA_ERROR_MARKERS = (
    "token plan usage limit reached",
    "token plan rate limit reached",
    "usage limit reached",
    "usage limit exceeded",
    "credit balance",
    "insufficient credit",
    "5-hour usage limit",
    "(2056)",
    "(2062)",
)


def is_quota_error(error_str: str) -> bool:
    """True when an error string indicates a *quota* exhaustion 429 (not a
    transient RPS throttle). Public so call sites (minimax_shared.py,
    config.py) can branch on it before calling report_quota_exhausted()."""
    lower = error_str.lower()
    return any(marker in lower for marker in _QUOTA_ERROR_MARKERS)


@dataclass
class _Slot:
    """Handle returned to the caller inside a `with limiter.request()` block."""

    _limiter: MiniMaxLimiter
    _was_rate_limited: bool = False

    def report_success(self) -> None:
        """Call after a successful API response."""
        self._limiter._on_success()

    def report_rate_limit(self) -> None:
        """Call on a transient 429 (RPS throttle). Use report_quota_exhausted()
        instead when the error indicates a Token Plan / Credits quota hit."""
        self._was_rate_limited = True
        self._limiter._on_rate_limit()

    def report_quota_exhausted(self) -> None:
        """Call when the API returns 2056 / 'Token Plan usage limit reached' /
        'usage limit exceeded'. Freezes the limiter for _QUOTA_FREEZE_SECONDS."""
        self._was_rate_limited = True
        self._limiter._on_quota_exhausted()


class MiniMaxLimiter:
    """Adaptive rate limiter with quota-aware freeze.

    Concurrency is bounded to a small range (1-8 by default). At a token
    quota, parallelism past ~8 is self-defeating. RPS throttles get the
    old adaptive backoff; quota hits freeze all new calls for a short
    window (the rolling 5h quota can only be waited out, not backoff'd
    out of).
    """

    def __init__(
        self,
        max_concurrency: int = 8,
        min_concurrency: int = 1,
        base_delay: float = 0.5,
        max_delay: float = 30.0,
        grow_after_successes: int = 20,
        grow_step: int = 1,
        quota_freeze_seconds: int = _QUOTA_FREEZE_SECONDS,
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
        self._total_quota_freezes = 0
        self._consecutive_429s = 0
        self._consecutive_successes = 0

        # Quota freeze
        self._quota_freeze_seconds = quota_freeze_seconds
        self._frozen_until: float = 0.0  # time.monotonic() — 0 means not frozen

    def is_frozen(self) -> bool:
        # NOTE: caller must NOT hold self._lock — this is called from stats
        # which is itself under the lock, hence the `_locked` variant below.
        with self._lock:
            return self._is_frozen_locked()

    def _is_frozen_locked(self) -> bool:
        """Same as is_frozen() but assumes self._lock is already held. Used
        from inside stats() to avoid deadlock on the non-reentrant Lock."""
        if self._frozen_until == 0.0:
            return False
        if time.monotonic() >= self._frozen_until:
            # Self-clear expired freeze so a successful probe unfreezes
            # everyone without needing an explicit unfreeze() call.
            self._frozen_until = 0.0
            return False
        return True

    def freeze_remaining_seconds(self) -> float:
        with self._lock:
            return self._freeze_remaining_seconds_locked()

    def _freeze_remaining_seconds_locked(self) -> float:
        """Same as freeze_remaining_seconds() but assumes self._lock is held."""
        if self._frozen_until == 0.0:
            return 0.0
        remaining = self._frozen_until - time.monotonic()
        return max(0.0, remaining)

    def unfreeze(self) -> None:
        """Manually clear a quota freeze (e.g. after probe_quota() reports
        the 5h window has reset). Normally self-clears on expiry."""
        with self._lock:
            if self._frozen_until != 0.0:
                self._frozen_until = 0.0
                logger.info("[minimax-limiter] Manually unfrozen")

    @contextmanager
    def request(self):
        """Acquire a rate-limited slot. Blocks if at concurrency limit.
        Raises QuotaExhaustedError if the limiter is currently frozen
        from a quota-exhaustion 429."""
        if self.is_frozen():
            remaining = self.freeze_remaining_seconds()
            raise QuotaExhaustedError(
                f"MiniMax quota exhausted — calls frozen for {remaining:.0f}s more. "
                f"Wait for the 5h rolling window to reset, or call probe_quota() "
                f"and unfreeze() if the window has cleared."
            )

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

            # NOTE: a successful call cannot auto-unfreeze — request() blocks
            # when is_frozen() is true, so _on_success() is unreachable while
            # frozen. The unfreeze paths are: (a) is_frozen() self-clears when
            # the freeze window expires, (b) explicit limiter.unfreeze() call
            # (e.g. by the orchestrator after a healthy probe_minimax_quota()).

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

            # Grow concurrency after sustained success (slowly: +1 per 20
            # successes). At a token quota, parallelism past ~8 is harmful.
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
        """Transient RPS 429 — adaptive backoff (doubled delay, halved concurrency)."""
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
                "[minimax-limiter] Rate limited (#%d, transient). Delay: %.2fs -> %.2fs. "
                "Concurrency: %d -> %d. Total: %d req, %d limited.",
                self._consecutive_429s,
                old_delay,
                self._current_delay,
                old_conc,
                self._current_concurrency,
                self._total_requests,
                self._total_429s,
            )

    def _on_quota_exhausted(self) -> None:
        """Quota 429 — freeze the limiter. Retrying won't help; the rolling
        window must reset. The freeze self-clears on expiry or on the next
        successful call."""
        with self._lock:
            self._total_429s += 1
            self._total_quota_freezes += 1
            self._consecutive_429s += 1
            self._consecutive_successes = 0

            # Drop concurrency to floor — no point burning through a quota
            # we know is empty.
            old_conc = self._current_concurrency
            self._current_concurrency = self._min_concurrency
            self._current_delay = self._max_delay

            # Set the freeze
            self._frozen_until = time.monotonic() + self._quota_freeze_seconds

            logger.error(
                "[minimax-limiter] QUOTA EXHAUSTED (freeze #%d). All calls blocked for %ds. "
                "Concurrency: %d -> %d. Total: %d req, %d limited, %d freezes. "
                "Probe /v1/token_plan/remains to check window reset.",
                self._total_quota_freezes,
                self._quota_freeze_seconds,
                old_conc,
                self._current_concurrency,
                self._total_requests,
                self._total_429s,
                self._total_quota_freezes,
            )

    def reset(self) -> None:
        """DEPRECATED 2026-06-28. Resetting the limiter at the start of each
        Theo task (was the previous pattern in convergence_orchestrator.py)
        wipes learned backoff state and sets concurrency back to max — which
        is the direct cause of the 82% rate-limited batch on 2026-06-28.
        Kept for backward compat with any test fixtures; emits a warning."""
        import warnings

        warnings.warn(
            "MiniMaxLimiter.reset() is deprecated — token-quota is global, "
            "not per-task. Remove the call site. (see 2026-06-28 plan)",
            DeprecationWarning,
            stacklevel=2,
        )
        with self._lock:
            self._current_concurrency = self._max_concurrency
            self._current_delay = self._base_delay
            self._consecutive_429s = 0
            self._consecutive_successes = 0
            logger.info(
                "[minimax-limiter] Reset (deprecated): concurrency=%d, delay=%.2fs",
                self._current_concurrency,
                self._current_delay,
            )

    @property
    def stats(self) -> dict:
        with self._lock:
            return {
                "total_requests": self._total_requests,
                "total_429s": self._total_429s,
                "total_quota_freezes": self._total_quota_freezes,
                "current_delay": round(self._current_delay, 3),
                "current_concurrency": self._current_concurrency,
                "active_count": self._active_count,
                "consecutive_429s": self._consecutive_429s,
                "consecutive_successes": self._consecutive_successes,
                "is_frozen": self._is_frozen_locked(),
                "freeze_remaining_seconds": round(self._freeze_remaining_seconds_locked(), 1),
            }


# Singleton
limiter = MiniMaxLimiter()
