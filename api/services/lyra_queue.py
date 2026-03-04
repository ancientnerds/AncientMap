"""
Fair queue for the local (Qwen) backend.

Concurrency matches ollama parallel slots (default 2) on VPS2.
Per-user burst limit: 3 messages per 10-minute sliding window.
FIFO queue with real-time position feedback via SSE.

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

BURST_LIMIT = 3
BURST_WINDOW_SECONDS = 600  # 10 minutes
QUEUE_TIMEOUT_SECONDS = 300  # 5 minutes
MAX_QUEUE_SIZE = 20
PARALLEL_SLOTS = 2  # ollama OLLAMA_NUM_PARALLEL


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
# LyraQueue singleton
# ---------------------------------------------------------------------------


class LyraQueue:
    def __init__(self) -> None:
        self._inference_lock = asyncio.Semaphore(PARALLEL_SLOTS)
        self._queue: deque[QueueEntry] = deque()
        self._burst_history: dict[uuid.UUID, list[float]] = {}
        self._active_count = 0

    # -- Burst management --------------------------------------------------

    def _prune_burst(self, user_id: uuid.UUID) -> list[float]:
        """Return only timestamps within the sliding window."""
        now = time.monotonic()
        history = self._burst_history.get(user_id, [])
        pruned = [t for t in history if now - t < BURST_WINDOW_SECONDS]
        self._burst_history[user_id] = pruned
        return pruned

    def get_burst_remaining(self, user_id: uuid.UUID) -> tuple[int, float]:
        """Return (remaining_messages, seconds_until_oldest_expires)."""
        history = self._prune_burst(user_id)
        remaining = max(0, BURST_LIMIT - len(history))
        if remaining > 0 or not history:
            return remaining, 0.0
        # Seconds until the oldest burst entry expires
        oldest = min(history)
        wait = max(0.0, BURST_WINDOW_SECONDS - (time.monotonic() - oldest))
        return remaining, wait

    def _record_burst(self, user_id: uuid.UUID) -> None:
        self._prune_burst(user_id)
        self._burst_history.setdefault(user_id, []).append(time.monotonic())

    def _refund_burst(self, user_id: uuid.UUID) -> None:
        """Remove the most recent burst timestamp (request failed before inference)."""
        history = self._burst_history.get(user_id, [])
        if history:
            history.pop()

    # -- Queue management --------------------------------------------------

    def has_active_request(self, user_id: uuid.UUID) -> bool:
        """Check if user already has a non-cancelled entry in the queue."""
        return any(e.user_id == user_id and not e.cancelled for e in self._queue)

    def enqueue(self, user_id: uuid.UUID) -> QueueEntry:
        """Add a request to the FIFO queue and record burst usage."""
        entry = QueueEntry(user_id=user_id)
        self._queue.append(entry)
        self._record_burst(user_id)
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
        # Signal up to PARALLEL_SLOTS entries (they'll race for the semaphore)
        signalled = 0
        for entry in self._queue:
            if entry.cancelled:
                continue
            if signalled >= PARALLEL_SLOTS:
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
            "slots": PARALLEL_SLOTS,
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
