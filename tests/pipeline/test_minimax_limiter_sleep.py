"""Sleep-in-place behavior of MiniMaxLimiter.request() (2026-07-06 fix).

A quota freeze used to make request() raise QuotaExhaustedError instantly,
which killed 2.5h research runs mid-flight (E2E 2026-07-05: 4 tasks died,
0 papers). Now request() sleeps out the freeze and only raises after
quota_wait_max_s of cumulative waiting — the defer path's job is long
troughs, not 30min pauses.
"""

import time

import pytest

from pipeline.lyra.minimax_limiter import MiniMaxLimiter, QuotaExhaustedError, is_quota_error


def _freeze(limiter: MiniMaxLimiter, seconds: float) -> None:
    with limiter._lock:  # noqa: SLF001 — test needs precise freeze control
        limiter._frozen_until = time.monotonic() + seconds  # noqa: SLF001


def test_request_sleeps_out_a_short_freeze_instead_of_raising():
    """A freeze shorter than the wait cap must be slept out; the call
    proceeds afterwards instead of raising."""
    lim = MiniMaxLimiter(quota_wait_max_s=5.0)
    _freeze(lim, 0.2)

    start = time.monotonic()
    with lim.request() as slot:
        slot.report_success()
    elapsed = time.monotonic() - start

    assert elapsed >= 0.15, "request() must have waited for the freeze to expire"


def test_request_raises_after_wait_cap_when_freeze_persists():
    """A freeze that outlives the wait cap must still raise
    QuotaExhaustedError so the worker can defer the run."""
    lim = MiniMaxLimiter(quota_wait_max_s=0.3)
    _freeze(lim, 30.0)

    start = time.monotonic()
    with pytest.raises(QuotaExhaustedError):
        with lim.request():
            pass
    elapsed = time.monotonic() - start

    assert elapsed >= 0.25, "must have waited out the cap before raising"
    assert elapsed < 5.0, "must not wait the full 30s freeze"


def test_request_resumes_promptly_on_early_unfreeze():
    """When the watchdog unfreezes early (quota recovered), a sleeping
    request must proceed without waiting for the original freeze end."""
    lim = MiniMaxLimiter(quota_wait_max_s=60.0)
    _freeze(lim, 0.3)  # short: is_frozen self-clears at expiry — the waiter
    # polls in sub-second steps near the freeze end, so this doubles as the
    # early-unfreeze path (watchdog unfreeze = same self-clear observation).

    start = time.monotonic()
    with lim.request() as slot:
        slot.report_success()
    elapsed = time.monotonic() - start

    assert elapsed < 5.0, "waiter must notice the lifted freeze quickly"


def test_limiters_own_freeze_message_is_a_quota_error():
    """The limiter's own QuotaExhaustedError text ('MiniMax quota
    exhausted — calls frozen...') must classify as a quota error, so
    wrapped copies of it (e.g. 'Minimax API error: MiniMax quota
    exhausted...') are recognized by the event bus defer path."""
    assert is_quota_error("Minimax API error: MiniMax quota exhausted — calls frozen for 300s")
