"""Freeze re-check after slot acquisition (audit P17a, 2026-08-06).

The freeze used to be checked only BEFORE condition.wait(): a thread already
past the pre-check (blocked waiting for a concurrency slot) would, once
woken, fire its API call straight into a freeze that another thread's
report_quota_exhausted() had set in the meantime. request() now re-checks
the freeze under the lock after acquiring the slot, releases it, and goes
back to waiting the freeze out.

Also covers the race-free send-slot claim (P17b): the next inter-request
timestamp is reserved UNDER the lock (SemanticScholarAdapter pattern), so N
concurrent threads can no longer read the same _last_call_time and compute
the same wait.
"""

import threading
import time

from pipeline.lyra.minimax_limiter import MiniMaxLimiter


def _freeze(limiter: MiniMaxLimiter, seconds: float) -> None:
    with limiter._lock:  # noqa: SLF001 — test needs precise freeze control
        limiter._frozen_until = time.monotonic() + seconds  # noqa: SLF001


def test_thread_waiting_for_slot_honors_freeze_set_meanwhile():
    lim = MiniMaxLimiter(max_concurrency=1, base_delay=0.0, quota_wait_max_s=30.0)
    a_acquired = threading.Event()
    release_a = threading.Event()
    b_elapsed_after_release = {}
    freeze_s = 0.8

    def hold_slot():
        with lim.request() as slot:
            a_acquired.set()
            release_a.wait(timeout=5)
            slot.report_success()

    def blocked_caller():
        # Enters request() while A holds the only slot -> passes the freeze
        # pre-check (nothing frozen yet), then blocks in condition.wait().
        with lim.request() as slot:
            b_elapsed_after_release["value"] = time.monotonic() - b_elapsed_after_release["t0"]
            slot.report_success()

    thread_a = threading.Thread(target=hold_slot)
    thread_a.start()
    assert a_acquired.wait(timeout=5)

    thread_b = threading.Thread(target=blocked_caller)
    thread_b.start()
    time.sleep(0.2)  # let B get past its freeze pre-check into the slot wait

    # Quota dies while B is already waiting for a slot, then A releases.
    _freeze(lim, freeze_s)
    b_elapsed_after_release["t0"] = time.monotonic()
    release_a.set()

    thread_a.join(timeout=5)
    thread_b.join(timeout=10)
    assert not thread_b.is_alive(), "B must eventually acquire after the freeze lifts"
    # Without the post-acquisition re-check B proceeds immediately (~0s).
    # With it, B releases the slot and waits out the remaining freeze.
    assert b_elapsed_after_release["value"] >= freeze_s - 0.3, b_elapsed_after_release


def test_send_slot_claims_are_serialized_under_the_lock():
    # Two threads race through request() with a 0.3s inter-request delay.
    # With the old read-outside-the-lock pattern both could compute the same
    # wait and start simultaneously; with per-thread slot claims the second
    # start must be >= ~delay after the first.
    lim = MiniMaxLimiter(max_concurrency=8, base_delay=0.3)
    starts = []
    lock = threading.Lock()

    def worker():
        with lim.request() as slot:
            with lock:
                starts.append(time.monotonic())
            slot.report_success()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert len(starts) == 2
    assert abs(starts[1] - starts[0]) >= 0.25, starts
