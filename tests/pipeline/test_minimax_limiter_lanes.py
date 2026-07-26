"""Tests for the two-lane MiniMax limiter (crawl lane vs full-speed lane)."""

import threading
import time

import pytest

import pipeline.lyra.minimax_limiter as ml


@pytest.fixture(autouse=True)
def _restore_crawl_delay():
    original = ml._crawl_delay_s
    yield
    ml.set_crawl_delay_s(original)


def test_crawl_delay_ladder():
    assert ml.crawl_delay_for_window(93) == 30.0
    assert ml.crawl_delay_for_window(60) == 30.0
    assert ml.crawl_delay_for_window(45) == 60.0
    assert ml.crawl_delay_for_window(39) == 90.0
    assert ml.crawl_delay_for_window(None) == 60.0


def test_low_lane_paces_while_high_lane_runs_free():
    ml.set_crawl_delay_s(1.2)
    lim = ml.MiniMaxLimiter(max_concurrency=4, base_delay=0.0)
    durations = {}

    def low_worker():
        ml.bind_low_priority(True)
        t0 = time.monotonic()
        for _ in range(2):
            with lim.request() as slot:
                slot.report_success()
        durations["low"] = time.monotonic() - t0

    def high_worker():
        # Fresh thread context: low-priority defaults to False.
        t0 = time.monotonic()
        for _ in range(5):
            with lim.request() as slot:
                slot.report_success()
        durations["high"] = time.monotonic() - t0

    threads = [threading.Thread(target=low_worker), threading.Thread(target=high_worker)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    # Second crawl-lane call must wait out the crawl delay...
    assert durations["low"] >= 1.1, durations
    # ...while the high lane was never blocked by it.
    assert durations["high"] < 0.6, durations
    assert lim.stats["low_lane_calls"] == 2


def test_restore_full_speed_after_throttle():
    lim = ml.MiniMaxLimiter(max_concurrency=8, base_delay=0.0)
    lim.throttle()
    assert lim.stats["current_concurrency"] == 1
    lim.restore_full_speed()
    assert lim.stats["current_concurrency"] == 8
