"""Cross-angle synthesis — combines findings from all saturated angles."""

import asyncio
import json
import logging
from pathlib import Path

from pipeline.lyra.config import _get_settings
from pipeline.lyra.handlers import BaseHandler
from pipeline.lyra.minimax_shared import minimax_chat_anthropic
from pipeline.lyra.research_events import AllAnglesSaturated, SynthesisReady
from pipeline.lyra.research_state import ResearchPhase

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


class SynthesisHandler(BaseHandler):
    def register(self):
        self.bus.on(AllAnglesSaturated, self._on_all_saturated)

    async def _on_all_saturated(self, event: AllAnglesSaturated):
        self.state.phase = ResearchPhase.SYNTHESIZING
        self.emit_sse(
            {
                "type": "pipeline",
                "stage": "synthesis",
                "status": "start",
                "meta": {"subtask_total": 2},
            }
        )

        # Step 1: Standard synthesis across all findings
        self.emit_sse(
            {
                "type": "status",
                "content": "Synthesizing findings across all angles...",
                "subtask_done": 0,
                "subtask_total": 2,
            }
        )

        # Build input: all specialist findings grouped by angle
        angle_summaries = []
        for angle in self.state.angles:
            findings_text = (
                json.dumps(angle.findings, indent=2) if angle.findings else "No findings"
            )
            angle_summaries.append(
                f"### Angle: {angle.topic}\n\n"
                f"Description: {angle.description}\n"
                f"Sources: {len(angle.source_ids)}\n"
                f"Search rounds: {angle.search_rounds}\n\n"
                f"Findings:\n{findings_text}\n"
            )

        all_findings_text = "\n---\n".join(angle_summaries)

        synthesis_prompt = (PROMPTS_DIR / "theo_synthesis.txt").read_text(encoding="utf-8")
        user_msg = f"## Research question\n\n{self.state.question}\n\n## Specialist analyses (by angle)\n\n{all_findings_text}"

        async with self.semaphore:
            raw = await asyncio.to_thread(
                minimax_chat_anthropic,
                synthesis_prompt,
                user_msg,
                self.state.config.max_tokens_synthesis,
                _get_settings(),
            )
        self.state.llm_call_count += 1
        self.state.synthesis = self._parse_json(raw)

        # Step 2: Cross-angle connection detection
        self.emit_sse(
            {
                "type": "status",
                "content": "Detecting cross-angle connections...",
                "subtask_done": 1,
                "subtask_total": 2,
            }
        )

        cross_prompt_path = PROMPTS_DIR / "v2_cross_angle.txt"
        if cross_prompt_path.exists():
            cross_prompt = cross_prompt_path.read_text(encoding="utf-8")
            async with self.semaphore:
                raw_cross = await asyncio.to_thread(
                    minimax_chat_anthropic,
                    cross_prompt,
                    user_msg,
                    self.state.config.max_tokens_synthesis,
                    _get_settings(),
                )
            self.state.llm_call_count += 1
            cross_result = self._parse_json(raw_cross)
            self.state.cross_angle_connections = cross_result.get("connections", [])

            convergent = len(cross_result.get("convergent_findings", []))
            contradictions = len(cross_result.get("contradictions", []))
            connections = len(self.state.cross_angle_connections)
            self.state.log(
                "synthesis",
                f"Cross-angle: {convergent} convergent, {contradictions} contradictions, {connections} connections",
            )
        else:
            self.state.log("synthesis", "Skipped cross-angle detection (prompt not found)")

        consensus = len(self.state.synthesis.get("consensus_claims", []))
        contested = len(self.state.synthesis.get("contested_claims", []))
        unique = len(self.state.synthesis.get("unique_insights", []))

        self.emit_sse(
            {
                "type": "pipeline",
                "stage": "synthesis",
                "status": "done",
                "meta": {
                    "consensus": consensus,
                    "contested": contested,
                    "unique": unique,
                    "cross_angle_connections": len(self.state.cross_angle_connections),
                },
            }
        )
        self.state.log(
            "synthesis",
            f"Synthesis complete: {consensus} consensus, {contested} contested, {unique} unique",
        )

        await self.bus.emit(SynthesisReady())

    @staticmethod
    def _parse_json(text: str) -> dict:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            cleaned = cleaned.rsplit("```", 1)[0].strip()
        try:
            return json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            logger.warning("Failed to parse synthesis JSON: %s", cleaned[:200])
            return {}
