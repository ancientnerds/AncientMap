"""
Fair FIFO queue for Lyra inference requests.

Single queue with configurable parallel inference slots. FIFO ordering
with real-time position feedback via SSE.

Module-level singleton — works because uvicorn runs 1 worker.
"""

import asyncio
import time
import uuid
from collections import deque
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Tunable constants
# ---------------------------------------------------------------------------

QUEUE_TIMEOUT_SECONDS = 300  # 5 minutes
MAX_QUEUE_SIZE = 20
PARALLEL_SLOTS = 2


# ---------------------------------------------------------------------------
# Queue entry
# ---------------------------------------------------------------------------


@dataclass
class QueueEntry:
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: uuid.UUID = field(default_factory=uuid.uuid4)
    ready_event: asyncio.Event = field(default_factory=asyncio.Event)
    cancelled: bool = False
    enqueued_at: float = field(default_factory=time.monotonic)


# ---------------------------------------------------------------------------
# LyraQueue — single FIFO + semaphore
# ---------------------------------------------------------------------------


class LyraQueue:
    def __init__(self, parallel_slots: int = PARALLEL_SLOTS) -> None:
        self._parallel_slots = parallel_slots
        self._inference_lock = asyncio.Semaphore(parallel_slots)
        self._queue: deque[QueueEntry] = deque()
        self._active_count = 0

    # -- Queue management --------------------------------------------------

    def has_active_request(self, user_id: uuid.UUID) -> bool:
        """Check if user already has a non-cancelled entry in the queue."""
        return any(e.user_id == user_id and not e.cancelled for e in self._queue)

    def enqueue(self, user_id: uuid.UUID) -> QueueEntry:
        """Add a request to the FIFO queue."""
        entry = QueueEntry(user_id=user_id)
        self._queue.append(entry)
        self._signal_next()  # Immediately signal if slots are free
        return entry

    def cancel(self, request_id: str) -> None:
        """Mark an entry as cancelled so _signal_next skips it."""
        for entry in self._queue:
            if entry.request_id == request_id:
                entry.cancelled = True
                entry.ready_event.set()  # Unblock any waiter
                break

    def release(self) -> None:
        """Release an inference slot and signal the next queued entry."""
        self._active_count = max(0, self._active_count - 1)
        self._inference_lock.release()
        self._signal_next()

    def _signal_next(self) -> None:
        """Pop cancelled entries, then signal entries that can acquire a slot."""
        while self._queue and self._queue[0].cancelled:
            self._queue.popleft()
        # Signal up to parallel_slots entries (they'll race for the semaphore)
        signalled = 0
        for entry in self._queue:
            if entry.cancelled:
                continue
            if signalled >= self._parallel_slots:
                break
            entry.ready_event.set()
            signalled += 1

    def get_queue_position(self, request_id: str) -> int | None:
        """0-based position among non-cancelled entries, or None if not found."""
        pos = 0
        for entry in self._queue:
            if entry.cancelled:
                continue
            if entry.request_id == request_id:
                return pos
            pos += 1
        return None

    def get_queue_length(self) -> int:
        return sum(1 for e in self._queue if not e.cancelled)

    def get_status(self) -> dict:
        """Public status snapshot for the /queue-status endpoint."""
        return {
            "queue_length": self.get_queue_length(),
            "active": self._active_count,
            "slots": self._parallel_slots,
        }

    async def acquire(self) -> None:
        """Acquire an inference slot (blocks until one is available)."""
        await self._inference_lock.acquire()
        self._active_count += 1

    def remove_entry(self, request_id: str) -> None:
        """Remove a completed/cancelled entry from the queue."""
        self._queue = deque(e for e in self._queue if e.request_id != request_id)


# Module-level singleton
lyra_queue = LyraQueue()
