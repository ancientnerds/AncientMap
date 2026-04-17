"""Moderator handler -- reviews claims from synthesis + debate, drops weak
claims, revises contested claims, and produces a filtered set of claims
for the paper writer."""

import asyncio
import json
import logging
from pathlib import Path

from pipeline.lyra.config import _get_settings
from pipeline.lyra.handlers import BaseHandler
from pipeline.lyra.minimax_shared import structured_llm_call
from pipeline.lyra.research_events import DebateComplete, ModeratorComplete
from pipeline.lyra.schemas import MODERATOR_SCHEMA

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


class ModeratorHandler(BaseHandler):
    """Reviews all claims post-debate, drops weak ones, revises contested ones."""

    def register(self):
        self.bus.on(DebateComplete, self._on_debate_complete)

    async def _on_debate_complete(self, event: DebateComplete):
        self.emit_sse(
            {
                "type": "pipeline",
                "stage": "moderator",
                "status": "start",
                "meta": {"subtask_total": 1},
            }
        )
        self.emit_sse({"type": "status", "content": "Moderator reviewing claims..."})

        prompt_path = PROMPTS_DIR / "theo_moderator.txt"
        if not prompt_path.exists():
            self.state.log("moderator", "Moderator prompt not found, skipping moderation")
            self.state.moderated_result = {}
            await self.bus.emit(ModeratorComplete())
            return
        system_prompt = prompt_path.read_text(encoding="utf-8")

        # Build input: research question + synthesis JSON + debate result
        synthesis_json = (
            json.dumps(self.state.synthesis, indent=2) if self.state.synthesis else "{}"
        )

        debate_json = (
            json.dumps(self.state.debate_result, indent=2) if self.state.debate_result else "{}"
        )

        user_msg = (
            f"## Research question\n\n{self.state.question}\n\n"
            f"## Synthesis\n\n{synthesis_json}\n\n"
            f"## Debate result\n\n{debate_json}\n"
        )

        settings = _get_settings()
        async with self.semaphore:
            parsed = await asyncio.to_thread(
                structured_llm_call,
                system_prompt,
                user_msg,
                MODERATOR_SCHEMA,
                self.state.config.max_tokens_per_call,
                settings,
                temperature=settings.temperature_verification,
            )
        self.state.llm_call_count += 1

        final_claims = parsed.get("final_claims", [])
        revised_claims = parsed.get("revised_claims", [])
        speculative_claims = parsed.get("speculative_claims", [])
        dropped_claims = parsed.get("dropped_claims", [])

        self.state.moderated_result = {
            "final_claims": final_claims,
            "revised_claims": revised_claims,
            "speculative_claims": speculative_claims,
            "dropped_claims": dropped_claims,
        }

        self.state.log(
            "moderator",
            f"Moderation complete: {len(final_claims)} final, "
            f"{len(revised_claims)} revised, {len(speculative_claims)} speculative, "
            f"{len(dropped_claims)} dropped",
        )

        self.emit_sse(
            {
                "type": "pipeline",
                "stage": "moderator",
                "status": "done",
                "meta": {
                    "final_claims": len(final_claims),
                    "revised_claims": len(revised_claims),
                    "speculative_claims": len(speculative_claims),
                    "dropped_claims": len(dropped_claims),
                },
            }
        )

        await self.bus.emit(ModeratorComplete())
