"""Event types and async event bus for research pipeline coordination.

Handlers register interest in specific event types.  The bus dispatches
events to all registered handlers, keeping a full history for debugging.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Minimum wall-time between DB progress flushes triggered from inside
# EventBus.emit. Cheap enough to call on every event, but the time gate
# keeps the actual UPDATE rate sane (~2/min) during high-frequency event
# bursts like the parallel image-research / search waves.
_FLUSH_INTERVAL_S = 30.0


# ---------------------------------------------------------------------------
# Event Types
# ---------------------------------------------------------------------------


@dataclass
class ResearchEvent:
    """Base event class."""

    pass


@dataclass
class AngleCreated(ResearchEvent):
    angle_id: str


@dataclass
class SourcesFound(ResearchEvent):
    angle_id: str
    count: int


@dataclass
class SourcesAudited(ResearchEvent):
    angle_id: str
    accepted: int
    rejected: int


@dataclass
class ContentFetched(ResearchEvent):
    """Content fetch complete for an angle's sources."""

    angle_id: str


@dataclass
class FindingsProduced(ResearchEvent):
    angle_id: str
    new_claims: int
    total_claims: int


@dataclass
class AngleSaturated(ResearchEvent):
    angle_id: str


@dataclass
class AllAnglesSaturated(ResearchEvent):
    pass


@dataclass
class SynthesisReady(ResearchEvent):
    pass


@dataclass
class DebateComplete(ResearchEvent):
    pass


@dataclass
class ModeratorComplete(ResearchEvent):
    """Moderator has reviewed and filtered claims from debate."""

    pass


@dataclass
class PaperReady(ResearchEvent):
    pass


@dataclass
class ProbativeImagesReady(ResearchEvent):
    """Emitted after probative images are fetched, gated, and inserted.

    Payload: count of images successfully embedded. The paper text on
    state.paper_text has already been mutated by the handler.
    """

    embedded_count: int = 0


@dataclass
class FactCheckComplete(ResearchEvent):
    """Fact-checking stage has verified citations in the paper."""

    pass


@dataclass
class PresentationChecked(ResearchEvent):
    """Presentation assessor has reviewed and corrected the paper."""

    pass


@dataclass
class ImageGenComplete(ResearchEvent):
    """Cover image generation is complete (or skipped)."""

    pass


@dataclass
class QualityPassed(ResearchEvent):
    score: int


@dataclass
class QualityFailed(ResearchEvent):
    score: int
    weak_areas: list[str]


@dataclass
class NewAngleDiscovered(ResearchEvent):
    topic: str
    description: str
    spawned_from: str  # parent angle ID


@dataclass
class AllAnglesRound1Complete(ResearchEvent):
    """All angles have completed at least one specialist round."""

    pass


@dataclass
class AllAnglesRound2Complete(ResearchEvent):
    """All original angles have completed round 2+ (post cross-pollination)."""

    pass


@dataclass
class CrossPollinationComplete(ResearchEvent):
    """Cross-angle insights have been shared, round 2 can begin."""

    pass


@dataclass
class DeadlineApproaching(ResearchEvent):
    hours_remaining: float


@dataclass
class SpecialistPruned(ResearchEvent):
    specialist_id: str


@dataclass
class SpecialistRecruited(ResearchEvent):
    specialist_id: str


# ---------------------------------------------------------------------------
# Event Bus
# ---------------------------------------------------------------------------

EventHandler = Callable[[ResearchEvent], Awaitable[None]]


class EventBus:
    """Simple async event bus for research pipeline coordination."""

    def __init__(self, state=None):
        self._handlers: dict[type, list[EventHandler]] = {}
        # Bounded: a 72h research run emits tens of thousands of events — an
        # unbounded list is a slow memory leak. Nothing indexes the history
        # (debug iteration/len only), so a deque with maxlen is a drop-in.
        self._history: deque[ResearchEvent] = deque(maxlen=2000)
        self._handler_instances: dict[type, object] = {}  # class -> instance registry
        # Optional ResearchState ref so handler exceptions can be surfaced to
        # the orchestrator's deadline loop (it watches state.error). Without
        # this, a crashed handler is logged but downstream events never fire,
        # leaving done_event.wait() blocked until the 12h hard timeout.
        self._state = state
        # Wall-time of last DB progress flush. Decomposition's initial event
        # cascade can keep the orchestrator's deadline loop from starting for
        # 10+ minutes, so we also flush from inside emit() to keep the DB
        # counters / debug_log visible to psql during that whole window.
        self._last_flush_ts: float = 0.0

    def register_instance(self, instance: object):
        """Register a handler instance for lookup by class."""
        self._handler_instances[type(instance)] = instance

    def get_handler(self, cls: type):
        """Get a registered handler instance by class."""
        return self._handler_instances.get(cls)

    def on(self, event_type: type, handler: EventHandler):
        """Register a handler for an event type."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    async def emit(self, event: ResearchEvent):
        """Emit an event, calling all registered handlers."""
        self._history.append(event)
        event_type = type(event)
        handlers = self._handlers.get(event_type, [])
        for handler in handlers:
            try:
                await handler(event)
            except Exception as exc:
                logger.exception("Handler failed for %s", event_type.__name__)
                if self._state is not None:
                    # Quota deaths must be distinguishable from real failures:
                    # the worker routes quota_exhausted runs to 'deferred'
                    # (retry when the window recovers) instead of 'failed'.
                    # Re-raising here is NOT an option — the deadline loop
                    # would block on done_event until the 12h hard timeout.
                    from pipeline.lyra.minimax_limiter import (
                        InsufficientQuotaError,
                        QuotaExhaustedError,
                        is_quota_error,
                    )

                    if isinstance(
                        exc, (QuotaExhaustedError, InsufficientQuotaError)
                    ) or is_quota_error(str(exc)):
                        self._state.quota_exhausted = True
                    # Make the failure visible to the orchestrator's deadline
                    # loop, which only checks state.error — otherwise
                    # done_event.wait() blocks until the 12h hard timeout.
                    if not getattr(self._state, "error", None):
                        self._state.error = f"Handler failed on {event_type.__name__}: {exc!r}"

        # Piggyback a DB progress flush on event emissions. The
        # orchestrator's own deadline-loop flush sits dormant during
        # the synchronous bus.emit cascade triggered by decomposition,
        # which is exactly when the user most needs to see counters
        # moving in psql. Time-gated so the actual UPDATE rate is
        # bounded regardless of event frequency.
        if self._state is not None:
            request_id = getattr(self._state, "request_id", "") or ""
            if request_id:
                now = time.monotonic()
                if now - self._last_flush_ts >= _FLUSH_INTERVAL_S:
                    self._last_flush_ts = now
                    try:
                        # Lazy import to avoid a circular dep with
                        # convergence_orchestrator (which imports EventBus).
                        from pipeline.lyra.convergence_orchestrator import (
                            _flush_progress_to_db,
                        )

                        _flush_progress_to_db(self._state, request_id)
                    except Exception as flush_exc:
                        # Never let an observability write break the pipeline,
                        # but keep the warning visible — silent flush failures
                        # would re-blind us to stalls.
                        logger.warning(
                            "[THEO] %s emit-flush failed: %r",
                            request_id,
                            flush_exc,
                        )

    @property
    def history(self) -> deque[ResearchEvent]:
        return self._history
