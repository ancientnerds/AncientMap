"""Event types and async event bus for research pipeline coordination.

Handlers register interest in specific event types.  The bus dispatches
events to all registered handlers, keeping a full history for debugging.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


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
class PresentationChecked(ResearchEvent):
    """Presentation assessor has reviewed and corrected the paper."""

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

    def __init__(self):
        self._handlers: dict[type, list[EventHandler]] = {}
        self._history: list[ResearchEvent] = []
        self._handler_instances: dict[type, object] = {}  # class -> instance registry

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
            except Exception:
                logger.exception("Handler failed for %s", event_type.__name__)

    @property
    def history(self) -> list[ResearchEvent]:
        return self._history
