"""24h deadline safety net --- forces convergence if time is running out."""

import logging

from pipeline.lyra.handlers import BaseHandler
from pipeline.lyra.research_events import AllAnglesSaturated, DebateComplete
from pipeline.lyra.research_state import ResearchPhase

logger = logging.getLogger(__name__)


class DeadlineHandler(BaseHandler):
    """Monitors deadline and forces convergence when time runs out."""

    def register(self):
        # No event trigger --- called periodically by orchestrator
        pass

    async def check_deadline(self) -> bool:
        """Check if deadline is approaching and force convergence if needed.

        Returns True if action was taken (caller should stop waiting).
        """
        hours_left = self.state.time_remaining_hours

        if hours_left <= 0:
            # Deadline passed --- force completion
            self.state.log("deadline", "Deadline reached --- forcing completion")
            self.emit_sse(
                {"type": "status", "content": "Deadline reached --- finalizing research..."}
            )
            await self._force_convergence()
            return True

        if hours_left <= 3 and self.state.phase == ResearchPhase.EXPLORING:
            # Less than 3 hours --- force-saturate all angles
            self.state.log(
                "deadline", f"Deadline approaching ({hours_left:.1f}h left) --- forcing saturation"
            )
            self.emit_sse(
                {
                    "type": "status",
                    "content": f"Deadline approaching ({hours_left:.1f}h left) --- finalizing research...",
                }
            )
            await self._force_convergence()
            return True

        if hours_left <= 1 and self.state.phase in (
            ResearchPhase.SYNTHESIZING,
            ResearchPhase.DEBATING,
        ):
            # Less than 1 hour --- skip to writing and emit DebateComplete to trigger paper
            self.state.log(
                "deadline",
                f"Deadline imminent ({hours_left:.1f}h left) --- forcing paper assembly",
            )
            self.state.phase = ResearchPhase.WRITING
            await self.bus.emit(DebateComplete())
            return True

        return False

    async def _force_convergence(self):
        """Force-saturate all unsaturated angles and trigger synthesis."""
        for angle in self.state.angles:
            if not angle.saturated:
                angle.saturated = True
                self.state.log("deadline", f"Force-saturated angle '{angle.topic}'")

        if self.state.phase == ResearchPhase.EXPLORING:
            self.state.phase = ResearchPhase.SYNTHESIZING
            await self.bus.emit(AllAnglesSaturated())
