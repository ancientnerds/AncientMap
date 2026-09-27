"""Persists a run's intermediate reasoning to the training corpus as it happens.

Each angle's findings, the specialist analyses behind them, the synthesis and
the debate are written when the stage that produces them finishes, so a run
that dies later (quota, crash, cancellation) still leaves them behind. The
dossier itself (moderated claims, citation registry, image pool, manifest) is
written by handlers/dossier.py on ModeratorComplete, which also rewrites these
kinds with their final content.

Writes use replace semantics when the run has a request_id: one current row per
(request_id, kind, ref), so a re-emitted event or a deferred re-run does not
stack duplicate rows.

Nothing here can fail a research run: these are passenger writes, logged loudly
and recorded in the run's debug_log when they fail. The dossier writes are the
hard ones.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from typing import Any

from pipeline.lyra.handlers import BaseHandler
from pipeline.lyra.research_events import (
    AllAnglesSaturated,
    AngleSaturated,
    DebateComplete,
    SynthesisReady,
)
from pipeline.lyra.research_state import findings_by_specialist
from pipeline.lyra.training_corpus import save_artifact

logger = logging.getLogger(__name__)


class StatePersistHandler(BaseHandler):
    """Writes intermediate research state to research_artifacts."""

    def register(self):
        self.bus.on(AngleSaturated, self._on_angle_saturated)
        self.bus.on(AllAnglesSaturated, self._on_all_angles_saturated)
        self.bus.on(SynthesisReady, self._on_synthesis_ready)
        self.bus.on(DebateComplete, self._on_debate_complete)

    async def _on_angle_saturated(self, event: AngleSaturated):
        angle = next((a for a in self.state.angles if a.id == event.angle_id), None)
        if angle is None:
            return
        await self._save("angle_findings", angle, ref=angle.id)

    async def _on_all_angles_saturated(self, event: AllAnglesSaturated):
        # Grouped from the angles' findings at this moment. state.specialist_analyses
        # is only assembled after the run, so reading it here stored an empty dict
        # in every production row until 2026-09-26.
        await self._save(
            "specialist_analyses",
            {
                "analyses": findings_by_specialist(self.state.angles),
                "panel": [asdict(s) for s in self.state.panel],
            },
        )

    async def _on_synthesis_ready(self, event: SynthesisReady):
        await self._save(
            "synthesis",
            {
                "synthesis": self.state.synthesis,
                "cross_angle_connections": self.state.cross_angle_connections,
            },
        )

    async def _on_debate_complete(self, event: DebateComplete):
        await self._save("debate", self.state.debate_result)

    async def _save(self, kind: str, payload: Any, ref: str = "") -> None:
        try:
            body = asdict(payload) if hasattr(payload, "__dataclass_fields__") else payload
            await asyncio.to_thread(
                save_artifact,
                self.state.request_id or None,
                kind,
                body,
                ref,
                replace=bool(self.state.request_id),
            )
        except Exception as exc:
            logger.error("[archive] artifact '%s' failed: %s", kind, exc)
            self.state.log("archive", f"ARTIFACT WRITE FAILED ({kind}): {exc}")
