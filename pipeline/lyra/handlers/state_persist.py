"""Persists a run's intermediate reasoning to the training corpus.

The convergence pipeline produces far more than the paper it ships: each
angle's findings, the specialist analyses behind them, the synthesis, the
debate rounds and the moderator's verdicts. All of that lives on the
in-memory ResearchState and is gone the moment the run ends — only the
finished paper reaches the database.

This handler writes each of those artifacts when it becomes final, so the
chain "question -> research -> argument -> paper" survives as training
material. The run-closing artifacts (final paper metrics, citation registry)
are NOT written here: reference pruning happens after PaperReady, so they are
written by the worker once the run is genuinely over.

Nothing here can fail a research run. EventBus.emit turns a handler exception
into state.error, which the deadline loop reads as a failed run — so every
write, including its own serialization, is wrapped. Failures are loud in the
log and in the run's debug_log, never silent.
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
    ModeratorComplete,
    SynthesisReady,
)
from pipeline.lyra.training_corpus import save_artifact

logger = logging.getLogger(__name__)


class StatePersistHandler(BaseHandler):
    """Writes intermediate research state to research_artifacts."""

    def register(self):
        self.bus.on(AngleSaturated, self._on_angle_saturated)
        self.bus.on(AllAnglesSaturated, self._on_all_angles_saturated)
        self.bus.on(SynthesisReady, self._on_synthesis_ready)
        self.bus.on(DebateComplete, self._on_debate_complete)
        self.bus.on(ModeratorComplete, self._on_moderator_complete)

    async def _on_angle_saturated(self, event: AngleSaturated):
        angle = next((a for a in self.state.angles if a.id == event.angle_id), None)
        if angle is None:
            return
        await self._save("angle_findings", angle, ref=angle.id)

    async def _on_all_angles_saturated(self, event: AllAnglesSaturated):
        # The densest supervised-fine-tuning material in the pipeline: a
        # specialist's full analysis of one angle, not just the claims that
        # survived into the paper.
        await self._save(
            "specialist_analyses",
            {
                "analyses": self.state.specialist_analyses,
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

    async def _on_moderator_complete(self, event: ModeratorComplete):
        await self._save("moderated", self.state.moderated_result)

    async def _save(self, kind: str, payload: Any, ref: str = "") -> None:
        try:
            body = asdict(payload) if hasattr(payload, "__dataclass_fields__") else payload
            await asyncio.to_thread(save_artifact, self.state.request_id or None, kind, body, ref)
        except Exception as exc:
            logger.error("[archive] artifact '%s' failed: %s", kind, exc)
            self.state.log("archive", f"ARTIFACT WRITE FAILED ({kind}): {exc}")
