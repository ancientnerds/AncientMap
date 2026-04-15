"""Cross-pollination — share findings across angles between round 1 and round 2.

After all angles complete their first specialist round, this handler examines
all findings together and enriches each angle with insights from other angles.
This enables round 2 to search for interdisciplinary connections that isolated
research would miss.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from pipeline.lyra.config import _get_settings
from pipeline.lyra.handlers import BaseHandler
from pipeline.lyra.minimax_shared import minimax_chat_anthropic
from pipeline.lyra.research_events import AllAnglesRound1Complete, CrossPollinationComplete

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


class CrossPollinationHandler(BaseHandler):
    def register(self):
        self.bus.on(AllAnglesRound1Complete, self._on_round1_complete)

    async def _on_round1_complete(self, event: AllAnglesRound1Complete):
        """Cross-pollinate findings across all angles."""
        self.emit_sse(
            {
                "type": "pipeline",
                "stage": "cross_pollination",
                "status": "start",
                "meta": {"subtask_total": 1, "angles": len(self.state.angles)},
            }
        )
        self.emit_sse(
            {"type": "status", "content": "Cross-pollinating findings across research angles..."}
        )

        # Build input: all angle summaries
        angle_summaries = []
        for angle in self.state.angles:
            # Summarize key findings (top 10 by confidence)
            top_findings = sorted(
                angle.findings,
                key=lambda f: {"high": 0, "medium": 1, "low": 2}.get(
                    f.get("confidence", "medium"), 1
                ),
            )[:10]
            findings_text = "\n".join(f"- {f.get('claim', '')}" for f in top_findings)
            angle_summaries.append(
                f"### Angle: {angle.topic} (ID: {angle.id})\n"
                f"Description: {angle.description}\n"
                f"Claims found: {len(angle.findings)}\n"
                f"Key findings:\n{findings_text}\n"
            )

        all_summaries = "\n---\n".join(angle_summaries)
        prompt = (PROMPTS_DIR / "v2_cross_pollination.txt").read_text(encoding="utf-8")
        user_msg = (
            f"## Research question\n\n{self.state.question}\n\n"
            f"## Angle findings from round 1\n\n{all_summaries}"
        )

        async with self.semaphore:
            raw = await asyncio.to_thread(
                minimax_chat_anthropic,
                prompt,
                user_msg,
                self.state.config.max_tokens_per_call,
                _get_settings(),
            )
        self.state.llm_call_count += 1

        result = self._parse_json(raw)

        # Apply cross-pollinated queries to each angle
        enriched_count = 0
        for cp in result.get("cross_pollination", []):
            angle_id = cp.get("angle_id", "")
            enriched_queries = cp.get("enriched_queries", [])
            cross_insights = cp.get("cross_insights", [])

            angle = next((a for a in self.state.angles if a.id == angle_id), None)
            if not angle:
                continue

            # Add enriched queries for round 2
            if enriched_queries:
                angle.search_queries = enriched_queries[: self.state.config.queries_per_angle]
                enriched_count += 1

            # Log cross-insights
            for insight in cross_insights:
                self.state.log(
                    "cross_pollination",
                    f"Angle '{angle.topic}': {insight[:100]}",
                )

        # Log convergent patterns
        for pattern in result.get("convergent_patterns", []):
            self.state.log("cross_pollination", f"Convergent pattern: {pattern[:150]}")
            self.emit_sse(
                {"type": "status", "content": f"Convergent pattern found: {pattern[:100]}"}
            )

        self.state.cross_pollinated = True

        self.emit_sse(
            {
                "type": "pipeline",
                "stage": "cross_pollination",
                "status": "done",
                "meta": {
                    "enriched_angles": enriched_count,
                    "convergent_patterns": len(result.get("convergent_patterns", [])),
                },
            }
        )
        self.state.log(
            "cross_pollination",
            f"Enriched {enriched_count}/{len(self.state.angles)} angles with cross-angle queries",
        )

        # Now trigger round 2 search for all angles
        await self.bus.emit(CrossPollinationComplete())

    @staticmethod
    def _parse_json(text: str) -> dict:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            cleaned = cleaned.rsplit("```", 1)[0].strip()
        try:
            return json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            logger.warning("Failed to parse cross-pollination JSON: %s", cleaned[:200])
            return {}
