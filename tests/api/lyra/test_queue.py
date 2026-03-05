# SPDX-License-Identifier: AGPL-3.0-only
"""Tests for Lyra fair queue system — burst tracking, FIFO, tiered queues."""

import asyncio
import time
import uuid

import pytest

from api.services.lyra_queue import (
    BURST_LIMIT,
    BURST_WINDOW_SECONDS,
    BurstTracker,
    LyraQueue,
    QueueEntry,
    TieredQueue,
)

# ---------------------------------------------------------------------------
# BurstTracker
# ---------------------------------------------------------------------------


class TestBurstTracker:
    def setup_method(self):
        self.tracker = BurstTracker()
        self.user = uuid.uuid4()

    def test_fresh_user_has_full_remaining(self):
        remaining, wait = self.tracker.get_remaining(self.user)
        assert remaining == BURST_LIMIT
        assert wait == 0.0

    def test_record_decrements_remaining(self):
        self.tracker.record(self.user)
        remaining, _ = self.tracker.get_remaining(self.user)
        assert remaining == BURST_LIMIT - 1

    def test_burst_limit_reached(self):
        for _ in range(BURST_LIMIT):
            self.tracker.record(self.user)
        remaining, wait = self.tracker.get_remaining(self.user)
        assert remaining == 0
        assert wait > 0

    def test_refund_restores_one_slot(self):
        for _ in range(BURST_LIMIT):
            self.tracker.record(self.user)
        self.tracker.refund(self.user)
        remaining, _ = self.tracker.get_remaining(self.user)
        assert remaining == 1

    def test_different_users_independent(self):
        user2 = uuid.uuid4()
        for _ in range(BURST_LIMIT):
            self.tracker.record(self.user)
        remaining, _ = self.tracker.get_remaining(user2)
        assert remaining == BURST_LIMIT

    def test_refund_on_empty_history_is_safe(self):
        self.tracker.refund(self.user)  # Should not raise

    def test_wait_time_is_bounded(self):
        for _ in range(BURST_LIMIT):
            self.tracker.record(self.user)
        _, wait = self.tracker.get_remaining(self.user)
        assert wait <= BURST_WINDOW_SECONDS


# ---------------------------------------------------------------------------
# LyraQueue
# ---------------------------------------------------------------------------


class TestLyraQueue:
    def setup_method(self):
        self.queue = LyraQueue(parallel_slots=1)
        self.user = uuid.uuid4()

    def test_enqueue_creates_entry(self):
        entry = self.queue.enqueue(self.user)
        assert entry.user_id == self.user
        assert not entry.cancelled
        assert self.queue.get_queue_length() == 1

    def test_queue_position(self):
        e1 = self.queue.enqueue(uuid.uuid4())
        e2 = self.queue.enqueue(uuid.uuid4())
        assert self.queue.get_queue_position(e1.request_id) == 0
        assert self.queue.get_queue_position(e2.request_id) == 1

    def test_cancel_marks_entry(self):
        entry = self.queue.enqueue(self.user)
        self.queue.cancel(entry.request_id)
        assert entry.cancelled
        assert entry.ready_event.is_set()  # Unblocks waiter

    def test_cancel_updates_queue_length(self):
        e1 = self.queue.enqueue(uuid.uuid4())
        self.queue.enqueue(uuid.uuid4())
        self.queue.cancel(e1.request_id)
        assert self.queue.get_queue_length() == 1

    def test_has_active_request(self):
        self.queue.enqueue(self.user)
        assert self.queue.has_active_request(self.user)
        assert not self.queue.has_active_request(uuid.uuid4())

    def test_has_active_request_ignores_cancelled(self):
        entry = self.queue.enqueue(self.user)
        self.queue.cancel(entry.request_id)
        assert not self.queue.has_active_request(self.user)

    def test_remove_entry(self):
        entry = self.queue.enqueue(self.user)
        self.queue.remove_entry(entry.request_id)
        assert self.queue.get_queue_length() == 0

    def test_get_active_user_ids(self):
        u1, u2 = uuid.uuid4(), uuid.uuid4()
        self.queue.enqueue(u1)
        self.queue.enqueue(u2)
        assert self.queue.get_active_user_ids() == {u1, u2}

    def test_get_status(self):
        status = self.queue.get_status()
        assert "queue_length" in status
        assert "active" in status
        assert "slots" in status

    @pytest.mark.asyncio
    async def test_acquire_release(self):
        # First acquire should succeed immediately
        await self.queue.acquire()
        assert self.queue._active_count == 1
        self.queue.release()
        assert self.queue._active_count == 0

    @pytest.mark.asyncio
    async def test_acquire_blocks_when_full(self):
        """With 1 slot, second acquire should block until release."""
        await self.queue.acquire()
        acquired = False

        async def try_acquire():
            nonlocal acquired
            await self.queue.acquire()
            acquired = True

        task = asyncio.create_task(try_acquire())
        await asyncio.sleep(0.05)
        assert not acquired  # Should still be blocked
        self.queue.release()
        await asyncio.sleep(0.05)
        assert acquired
        self.queue.release()
        task.cancel()

    def test_signal_next_skips_cancelled(self):
        e1 = self.queue.enqueue(uuid.uuid4())
        e2 = self.queue.enqueue(uuid.uuid4())
        self.queue.cancel(e1.request_id)
        # After cancel, e2's position should be 0
        assert self.queue.get_queue_position(e2.request_id) == 0

    def test_position_none_for_unknown_id(self):
        assert self.queue.get_queue_position("nonexistent") is None


# ---------------------------------------------------------------------------
# TieredQueue
# ---------------------------------------------------------------------------


class TestTieredQueue:
    def setup_method(self):
        self.tq = TieredQueue()

    def test_separate_queues_for_tiers(self):
        fast_q = self.tq.get_queue("fast")
        heavy_q = self.tq.get_queue("heavy")
        assert fast_q is not heavy_q

    def test_unknown_tier_defaults_to_heavy(self):
        q = self.tq.get_queue("unknown")
        assert q is self.tq.get_queue("heavy")

    def test_has_other_users(self):
        u1, u2 = uuid.uuid4(), uuid.uuid4()
        self.tq.get_queue("fast").enqueue(u1)
        assert self.tq.has_other_users(u2)
        assert not self.tq.has_other_users(u1)

    def test_has_other_users_cross_tier(self):
        u1, u2 = uuid.uuid4(), uuid.uuid4()
        self.tq.get_queue("fast").enqueue(u1)
        self.tq.get_queue("heavy").enqueue(u2)
        # Both users see the other
        assert self.tq.has_other_users(u1)
        assert self.tq.has_other_users(u2)

    def test_shared_burst_tracker(self):
        u1 = uuid.uuid4()
        # Record across tiers shares the same burst tracker
        self.tq.burst.record(u1)
        self.tq.burst.record(u1)
        self.tq.burst.record(u1)
        remaining, _ = self.tq.burst.get_remaining(u1)
        assert remaining == 0

    def test_combined_status(self):
        status = self.tq.get_combined_status()
        assert "queue_length" in status
        assert "tiers" in status
        assert "fast" in status["tiers"]
        assert "heavy" in status["tiers"]
