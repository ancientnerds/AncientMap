# SPDX-License-Identifier: AGPL-3.0-only
"""Tests for Lyra FIFO queue system."""

import asyncio
import uuid

import pytest

from api.services.lyra_queue import LyraQueue


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

    def test_get_status(self):
        status = self.queue.get_status()
        assert "queue_length" in status
        assert "active" in status
        assert "slots" in status

    @pytest.mark.asyncio
    async def test_acquire_release(self):
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
        assert self.queue.get_queue_position(e2.request_id) == 0

    def test_position_none_for_unknown_id(self):
        assert self.queue.get_queue_position("nonexistent") is None
