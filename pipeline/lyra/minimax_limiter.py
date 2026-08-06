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

import contextvars
import logging
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# --- Run-priority lanes (2026-07-26 permanent-researcher design) -------------
# Batch research runs are LOW priority: their calls pace on the crawl lane
# (concurrency 1, >= crawl delay apart) so background research can never
# outpace the shared 5h window. Interactive (UI) runs and everything else are
# HIGH priority and use the adaptive lane at full speed — concurrently.
# The flag travels with the run via contextvar; like token_accounting's, it
# propagates through asyncio.create_task and asyncio.to_thread.
_run_low_priority: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "minimax_low_priority", default=False
)


def bind_low_priority(flag: bool) -> None:
    """Tag the current async context (and every task/thread it spawns) as a
    low-priority (crawl lane) or high-priority (full speed) MiniMax consumer.
    Called once at research-run start by the ConvergenceOrchestrator."""
    _run_low_priority.set(flag)


class QuotaExhaustedError(RuntimeError):
    """Raised by limiter.request() when the quota freeze outlives the
    in-place wait cap (`quota_wait_max_s`, default 6h). Short freezes are
    slept out inside request() since 2026-07-06 — a 2.5h research run must
    survive a 30min quota trough instead of dying mid-flight. Only a
    long trough (weekly cap, dead key) surfaces this error, and the worker
    responds by deferring the run."""


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

# Delay forced between crawl-lane calls (and between all calls while the
# watchdog reports the THROTTLED band). Deliberately above _max_delay: crawl
# is about letting the rolling window's refill outpace the burn, not about
# RPS smoothing. The saturation controller adjusts the live value via
# set_crawl_delay_s() based on the 5h window headroom.
_THROTTLE_DELAY_S = 60.0
_crawl_delay_s: float = _THROTTLE_DELAY_S


def set_crawl_delay_s(seconds: float) -> None:
    """Saturation controller hook: the quota watchdog sets the crawl-lane
    delay from the live 5h headroom (see crawl_delay_for_window)."""
    global _crawl_delay_s
    if seconds != _crawl_delay_s:
        logger.info("[minimax-limiter] Crawl delay %.0fs -> %.0fs", _crawl_delay_s, seconds)
        _crawl_delay_s = seconds


def crawl_delay_for_window(five_hour_remaining_pct: float | None) -> float:
    """Percentage-based crawl-delay ladder — survives the Plus→Max plan
    upgrade unchanged because it keys on remaining %, not absolute tokens.

    >= 60% headroom → 30s (saturate the flat plan)
    >= 40%          → 60s (steady state)
    <  40%          → 90s (back off; watchdog THROTTLED/EXHAUSTED bands
                      below 20%/5% stay in charge of hard clamping)
    """
    if five_hour_remaining_pct is None:
        return _THROTTLE_DELAY_S
    if five_hour_remaining_pct >= 60:
        return 30.0
    if five_hour_remaining_pct >= 40:
        return 60.0
    return 90.0


# Maximum cumulative time a single request() acquisition sleeps in place
# waiting for a quota freeze to lift, before giving up and raising
# QuotaExhaustedError. 6h covers a full rollover of the 5h window — if the
# quota hasn't recovered by then, this is a weekly-cap trough and the run
# should defer instead of holding its worker slot.
_QUOTA_WAIT_MAX_S = 6 * 3600

# Substrings that identify a *budget* 429 (the plan's token allowance is
# spent). The MiniMax Anthropic-compatible endpoint returns these in the
# error message body (e.g. `'message': 'Token Plan usage limit reached:
# Upgrade your Token Plan or purchase Credits for more usage. (2056)'`).
# Case-insensitive match.
#
# History: 2026-06-29 added "(2062)" here on the assumption that both Token
# Plan flavors mean the same thing. 2026-07-29 disproved that: a (2062)
# "rate limit reached" fired at 5h=71% / weekly=27% REMAINING and killed a
# 15h run at FactCheckComplete — 2062 is the plan's short-window rate cap
# (per-minute), not the budget. It now lives in
# _PLAN_RATE_THROTTLE_MARKERS below and call sites retry it with a
# window-clearing backoff instead of failing fast.
_QUOTA_ERROR_MARKERS = (
    "token plan usage limit reached",
    "usage limit reached",
    "usage limit exceeded",
    "credit balance",
    "insufficient credit",
    "5-hour usage limit",
    "(2056)",
    # Our own QuotaExhaustedError text. Call sites wrap it into plain
    # RuntimeErrors ("Minimax API error: MiniMax quota exhausted — ...");
    # without this marker the event bus cannot recognize those copies and
    # the worker marks quota deaths 'failed' instead of 'deferred'.
    "quota exhausted",
)

# The plan's SHORT-WINDOW rate cap (requests/tokens per minute-ish). Distinct
# from budget exhaustion: the right response is a backoff long enough to roll
# the window, then retry — the SDK's own sub-second retries land in the same
# window and always fail. Only a throttle that persists through the backoffs
# is treated as a genuine trough (freeze + QuotaExhaustedError -> defer).
_PLAN_RATE_THROTTLE_MARKERS = (
    "token plan rate limit reached",
    "(2062)",
)


def is_quota_error(error_str: str) -> bool:
    """True when an error string indicates a *budget* exhaustion 429 (plan
    allowance spent — 2056/credits), not a short-window rate throttle and not
    a transient RPS throttle. Public so call sites (minimax_shared.py,
    config.py) can branch on it before calling report_quota_exhausted()."""
    lower = error_str.lower()
    return any(marker in lower for marker in _QUOTA_ERROR_MARKERS)


def is_plan_rate_throttle(error_str: str) -> bool:
    """True for the Token Plan's short-window rate cap (2062).

    Call sites must check `is_quota_error` FIRST — a message carrying both
    flavors' markers is treated as budget exhaustion (conservative)."""
    lower = error_str.lower()
    return any(marker in lower for marker in _PLAN_RATE_THROTTLE_MARKERS)


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
        quota_wait_max_s: float = _QUOTA_WAIT_MAX_S,
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
        self._quota_wait_max_s = quota_wait_max_s
        self._frozen_until: float = 0.0  # time.monotonic() — 0 means not frozen

        # Crawl lane (2026-07-26): low-priority runs (batch research) pace
        # here — at most 1 in flight, >= _crawl_delay_s between calls —
        # while high-priority callers use the adaptive state concurrently.
        self._low_active_count = 0
        self._low_last_call_time = 0.0
        self._low_lane_calls = 0

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

    def throttle(self) -> None:
        """Clamp to crawl mode: concurrency floor + throttle delay. Called
        by the quota watchdog on every probe while the 5h window sits in
        the THROTTLED band (5-20% remaining) — the run keeps finishing
        work slowly instead of freezing. No unthrottle() needed: once the
        watchdog stops re-asserting, sustained successes regrow
        concurrency adaptively and the delay decays via _on_success."""
        with self._lock:
            if (
                self._current_concurrency != self._min_concurrency
                or self._current_delay != _THROTTLE_DELAY_S
            ):
                logger.warning(
                    "[minimax-limiter] THROTTLED to crawl: concurrency %d -> %d, "
                    "delay %.1fs -> %.1fs.",
                    self._current_concurrency,
                    self._min_concurrency,
                    self._current_delay,
                    _THROTTLE_DELAY_S,
                )
            self._current_concurrency = self._min_concurrency
            self._current_delay = _THROTTLE_DELAY_S

    def _wait_while_frozen(self) -> None:
        """Sleep in place while the limiter is quota-frozen (2026-07-06).

        Raising instantly killed multi-hour research runs over a 30min
        quota trough (E2E 2026-07-05: 4 runs dead, 0 papers). The rolling
        5h window refills as the run's own early burn ages out — so the
        right response to a freeze is to wait, not to die. Only when the
        cumulative wait exceeds `quota_wait_max_s` (weekly-cap trough) do
        we raise QuotaExhaustedError for the worker's defer path.

        Polls in short steps so a watchdog unfreeze (quota recovered) or
        freeze extension (still exhausted) is noticed within ~15s.
        """
        if not self.is_frozen():
            return
        waited = 0.0
        logger.warning(
            "[minimax-limiter] Quota-frozen — sleeping in place "
            "(freeze %.0fs remaining, wait cap %.0fs).",
            self.freeze_remaining_seconds(),
            self._quota_wait_max_s,
        )
        while self.is_frozen():
            if waited >= self._quota_wait_max_s:
                raise QuotaExhaustedError(
                    f"MiniMax quota exhausted — waited {waited:.0f}s in place "
                    f"(cap {self._quota_wait_max_s:.0f}s) and the limiter is still "
                    f"frozen. The 5h window did not recover; deferring the run."
                )
            step = min(
                15.0,
                self._quota_wait_max_s - waited,
                max(0.05, self.freeze_remaining_seconds()),
            )
            time.sleep(step)
            waited += step
        logger.info(
            "[minimax-limiter] Freeze lifted after %.0fs of in-place waiting — resuming.",
            waited,
        )

    @contextmanager
    def request(self):
        """Acquire a rate-limited slot. Blocks while the caller's lane is at
        its concurrency limit. A quota freeze is slept out in place (see
        _wait_while_frozen); QuotaExhaustedError only fires after the wait
        cap. The freeze is re-checked AFTER slot acquisition — a thread that
        passed the pre-check (or slept in condition.wait()) while another
        thread reported quota exhaustion releases its slot and goes back to
        waiting instead of firing into a known-empty quota (audit P17a).
        Low-priority contexts (bind_low_priority) pace on the crawl lane —
        1 in flight, >= _crawl_delay_s between calls — while high-priority
        callers use the adaptive lane concurrently."""
        low = _run_low_priority.get()
        while True:
            self._wait_while_frozen()

            with self._condition:
                if low:
                    while self._low_active_count >= 1:
                        self._condition.wait()
                    self._low_active_count += 1
                else:
                    while self._active_count >= self._current_concurrency:
                        self._condition.wait()
                    self._active_count += 1

                # Freeze re-check under the lock: without it, a thread past
                # the pre-check above proceeds straight into a freshly-set
                # freeze. Release the slot and wait the freeze out.
                if self._is_frozen_locked():
                    if low:
                        self._low_active_count -= 1
                    else:
                        self._active_count -= 1
                    self._condition.notify_all()
                    continue

                # Claim the next send-slot timestamp UNDER the lock (same
                # pattern as SemanticScholarAdapter._wait_for_rate_limit in
                # theo_sources, audit P17b): previously _last_call_time was
                # read here but compared/re-stamped outside the lock, so N
                # concurrent threads could read the same value, compute the
                # same wait, and send simultaneously. Each thread now
                # reserves its own slot; the sleep happens outside the lock
                # so later claimants aren't serialized behind it.
                now = time.monotonic()
                if low:
                    delay = max(self._current_delay, _crawl_delay_s)
                    sleep_s = max(0.0, self._low_last_call_time + delay - now)
                    self._low_last_call_time = now + sleep_s
                    self._low_lane_calls += 1
                else:
                    delay = self._current_delay
                    sleep_s = max(0.0, self._last_call_time + delay - now)
                    self._last_call_time = now + sleep_s
                self._total_requests += 1
                break

        # Sleep out the claimed inter-request gap, per lane
        if sleep_s > 0:
            time.sleep(sleep_s)

        slot = _Slot(_limiter=self)
        try:
            yield slot
        finally:
            with self._condition:
                if low:
                    self._low_active_count -= 1
                else:
                    self._active_count -= 1
                # Both lane populations wait on the same condition — wake
                # everyone and let each waiter recheck its own predicate.
                self._condition.notify_all()

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

    def restore_full_speed(self) -> None:
        """Reset pacing (concurrency + delay) to full speed after a real
        quota recovery. Called by the quota watchdog when the tier
        transitions to HEALTHY: the 5h budget is a fixed block, so a block
        reset (5% -> 100%) makes any leftover crawl clamp pure waste —
        observed live 2026-07-19: 20+ min at delay 42s / concurrency 2
        against a fresh 100% window, because the adaptive ramp (+1
        concurrency per 20 successes) needs over an hour to undo a
        THROTTLE clamp.

        Differs from the deprecated reset(): probe-driven (fires only on
        an actual quota recovery, not per-task), and it leaves the freeze
        state and lifetime stats untouched — the stall guard reads
        total_requests as a liveness signal."""
        with self._lock:
            if (
                self._current_concurrency == self._max_concurrency
                and self._current_delay == self._base_delay
            ):
                return
            logger.info(
                "[minimax-limiter] Full speed restored: concurrency %d -> %d, "
                "delay %.1fs -> %.1fs.",
                self._current_concurrency,
                self._max_concurrency,
                self._current_delay,
                self._base_delay,
            )
            self._current_concurrency = self._max_concurrency
            self._current_delay = self._base_delay
            self._consecutive_429s = 0
            self._consecutive_successes = 0

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
                "low_lane_calls": self._low_lane_calls,
                "low_lane_active": self._low_active_count,
                "crawl_delay_s": _crawl_delay_s,
            }


# Singleton
limiter = MiniMaxLimiter()
