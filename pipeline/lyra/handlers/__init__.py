"""Handler base class for research pipeline event-driven architecture."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pipeline.lyra.research_events import EventBus
    from pipeline.lyra.research_state import ResearchState


class BaseHandler(ABC):
    """Base class for all research pipeline handlers."""

    def __init__(self, state: ResearchState, bus: EventBus, semaphore: asyncio.Semaphore):
        self.state = state
        self.bus = bus
        self.semaphore = semaphore

    def emit_sse(self, event: dict):
        """Emit SSE event to frontend."""
        if self.state.emit:
            self.state.emit(event)

    @abstractmethod
    def register(self):
        """Register event handlers on the bus. Called once during setup."""
        ...
