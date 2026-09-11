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

    def emit_connector_breakdown(self):
        """Emit which search connectors the run has sourced from, and how many.

        A run-wide snapshot rather than a delta, so the UI can replace its
        state outright and never drift. Counted off the registry, so the
        numbers are post-dedup: a paper that OpenAlex and Crossref both
        surfaced counts once, under whichever adapter registered it first.
        """
        counts: dict[str, int] = {}
        for source in self.state.registry.sources.values():
            # Sources carried in by force_include/web_urls have no adapter.
            name = source.source_api or "direct"
            counts[name] = counts.get(name, 0) + 1
        if counts:
            self.emit_sse({"type": "connectors", "counts": counts})

    @abstractmethod
    def register(self):
        """Register event handlers on the bus. Called once during setup."""
        ...
