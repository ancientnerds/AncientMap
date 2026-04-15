"""Convergence checker -- monitors angle saturation and triggers transitions."""

import logging
import uuid

from pipeline.lyra.handlers import BaseHandler
from pipeline.lyra.research_events import (
    AllAnglesRound1Complete,
    AllAnglesSaturated,
    AngleCreated,
    AngleSaturated,
    FindingsProduced,
    NewAngleDiscovered,
)
from pipeline.lyra.research_state import ResearchAngle, ResearchPhase

logger = logging.getLogger(__name__)


class ConvergenceChecker(BaseHandler):
    def __init__(self, state, bus, semaphore):
        super().__init__(state, bus, semaphore)
        self._round1_triggered = False

    def register(self):
        self.bus.on(AngleSaturated, self._on_angle_saturated)
        self.bus.on(FindingsProduced, self._on_findings_produced)
        self.bus.on(NewAngleDiscovered, self._on_new_angle)

    async def _on_angle_saturated(self, event: AngleSaturated):
        angle = next((a for a in self.state.angles if a.id == event.angle_id), None)
        if angle:
            self.emit_sse(
                {
                    "type": "status",
                    "content": f"Angle '{angle.topic}' saturated -- no new findings",
                }
            )
            self.state.log(
                "convergence",
                f"Angle '{angle.topic}' saturated after {angle.search_rounds} rounds",
            )

        if self.state.all_angles_saturated:
            self.emit_sse(
                {
                    "type": "status",
                    "content": (
                        f"All {len(self.state.angles)} angles saturated -- proceeding to synthesis"
                    ),
                }
            )
            self.state.phase = ResearchPhase.SYNTHESIZING
            await self.bus.emit(AllAnglesSaturated())

    async def _on_findings_produced(self, event: FindingsProduced):
        """After findings, report progress and detect round 1 completion."""
        angle = next((a for a in self.state.angles if a.id == event.angle_id), None)
        if not angle or angle.saturated:
            return

        total_saturated = sum(1 for a in self.state.angles if a.saturated)
        total = len(self.state.angles)
        self.emit_sse(
            {
                "type": "status",
                "content": f"Progress: {total_saturated}/{total} angles saturated",
            }
        )

        # Detect when ALL angles have completed at least 1 specialist round
        if not self.state.cross_pollinated and not self._round1_triggered:
            all_have_findings = all(len(a.findings) > 0 for a in self.state.angles)
            if all_have_findings:
                self._round1_triggered = True
                self.emit_sse(
                    {
                        "type": "status",
                        "content": "All angles completed round 1 -- cross-pollinating findings...",
                    }
                )
                self.state.log(
                    "convergence", "All angles completed round 1, triggering cross-pollination"
                )
                await self.bus.emit(AllAnglesRound1Complete())

    async def _on_new_angle(self, event: NewAngleDiscovered):
        """Handle dynamically spawned rabbit-hole angles."""
        if len(self.state.angles) >= self.state.config.max_angles:
            self.state.log(
                "convergence",
                f"Max angles ({self.state.config.max_angles}) reached, "
                f"ignoring new angle: {event.topic}",
            )
            return

        new_angle = ResearchAngle(
            id=uuid.uuid4().hex[:8],
            topic=event.topic,
            description=event.description,
            spawned_from=event.spawned_from,
        )
        self.state.angles.append(new_angle)
        self.emit_sse(
            {
                "type": "status",
                "content": f"New research angle discovered: '{event.topic}'",
            }
        )
        self.state.log(
            "convergence",
            f"Spawned new angle '{event.topic}' from '{event.spawned_from}'",
        )

        # Trigger search for the new angle
        await self.bus.emit(AngleCreated(angle_id=new_angle.id))
