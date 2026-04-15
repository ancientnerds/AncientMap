"""Moderator handler -- reviews claims from synthesis + debate, drops weak
claims, revises contested claims, and produces a filtered set of claims
for the paper writer."""

import asyncio
import json
import logging
from pathlib import Path

from pipeline.lyra.config import _get_settings
from pipeline.lyra.handlers import BaseHandler
from pipeline.lyra.minimax_shared import minimax_chat_anthropic
from pipeline.lyra.research_events import DebateComplete, ModeratorComplete

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
            raw = await asyncio.to_thread(
                minimax_chat_anthropic,
                system_prompt,
                user_msg,
                self.state.config.max_tokens_per_call,
                settings,
            )
        self.state.llm_call_count += 1

        parsed = self._parse_json(raw)

        final_claims = parsed.get("final_claims", [])
        revised_claims = parsed.get("revised_claims", [])
        dropped_claims = parsed.get("dropped_claims", [])

        self.state.moderated_result = {
            "final_claims": final_claims,
            "revised_claims": revised_claims,
            "dropped_claims": dropped_claims,
        }

        self.state.log(
            "moderator",
            f"Moderation complete: {len(final_claims)} final, "
            f"{len(revised_claims)} revised, {len(dropped_claims)} dropped",
        )

        self.emit_sse(
            {
                "type": "pipeline",
                "stage": "moderator",
                "status": "done",
                "meta": {
                    "final_claims": len(final_claims),
                    "revised_claims": len(revised_claims),
                    "dropped_claims": len(dropped_claims),
                },
            }
        )

        await self.bus.emit(ModeratorComplete())

    @staticmethod
    def _parse_json(text: str) -> dict:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            cleaned = cleaned.rsplit("```", 1)[0].strip()
        try:
            return json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            logger.warning("[moderator] Failed to parse JSON: %s", cleaned[:200])
            return {}
