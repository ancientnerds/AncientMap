"""Topic decomposition — break question into independent research angles."""

import asyncio
import json
import logging
import uuid
from pathlib import Path

from pipeline.lyra.handlers import BaseHandler
from pipeline.lyra.minimax_shared import minimax_chat_anthropic
from pipeline.lyra.research_events import AngleCreated, SourcesFound
from pipeline.lyra.research_state import ResearchAngle, ResearchPhase
from pipeline.lyra.config import _get_settings

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


class DecompositionHandler(BaseHandler):

    def register(self):
        # No event triggers — called directly by orchestrator at start
        pass

    async def decompose(self):
        """Phase A+B: Propose angles, validate with quick search, register on state."""
        self.state.phase = ResearchPhase.DECOMPOSING
        self.emit_sse({"type": "pipeline", "stage": "decomposition", "status": "start", "meta": {"subtask_total": 2}})
        self.emit_sse({"type": "status", "content": "Decomposing research question into angles...", "subtask_done": 0, "subtask_total": 2})

        # Phase A: LLM proposes angles
        prompt = (PROMPTS_DIR / "v2_decomposition.txt").read_text(encoding="utf-8")
        raw = await asyncio.to_thread(
            minimax_chat_anthropic,
            prompt,
            self.state.question,
            self.state.config.max_tokens_per_call,
            _get_settings(),
        )
        self.state.llm_call_count += 1

        proposed = self._parse_json(raw)
        angles_data = proposed.get("angles", [])
        if not angles_data:
            self.state.error = "Decomposition produced no research angles"
            return

        self.emit_sse({"type": "status", "content": f"Proposed {len(angles_data)} research angles, validating...", "subtask_done": 1, "subtask_total": 2})

        # Phase B: Validation search per angle
        from pipeline.lyra.theo_sources import MultiSourceSearch
        settings = _get_settings()
        searcher = MultiSourceSearch(settings)

        validated: list[ResearchAngle] = []
        for ad in angles_data[:self.state.config.max_angles]:
            queries = ad.get("search_queries", [])[:3]  # 2-3 validation queries
            if not queries:
                continue

            async with self.semaphore:
                results = await searcher.search(queries, "standard", self.state.disabled_adapters)

            if len(results) < 2:
                self.state.log("decomposition", f"Dropped angle '{ad.get('topic', '?')}' — insufficient sources ({len(results)})")
                continue

            angle = ResearchAngle(
                id=uuid.uuid4().hex[:8],
                topic=ad.get("topic", ""),
                description=ad.get("description", ""),
                search_queries=ad.get("search_queries", [])[:self.state.config.queries_per_angle],
                specialist_domains=ad.get("specialist_domains", []),
            )

            # Register validation sources in registry
            for r in results:
                sid = self.state.registry.register_source(
                    url=r.url, title=r.title, snippet=r.snippet, date=r.date,
                )
                angle.source_ids.append(sid)
                source = self.state.registry.get_reference(sid)
                if source and source.reliability_tier == 0:
                    source.reliability_tier = r.default_tier

            validated.append(angle)

        if not validated:
            self.state.error = "No research angles had sufficient source coverage"
            return

        self.state.angles = validated
        self.state.phase = ResearchPhase.EXPLORING

        self.emit_sse({
            "type": "pipeline", "stage": "decomposition", "status": "done",
            "meta": {"angles": len(validated), "angle_topics": [a.topic for a in validated]},
        })
        self.emit_sse({"type": "status", "content": f"Research decomposed into {len(validated)} angles", "subtask_done": 2, "subtask_total": 2})

        self.state.log("decomposition", f"Validated {len(validated)} angles from {len(angles_data)} proposed")

        # Emit AngleCreated for each validated angle
        for angle in validated:
            await self.bus.emit(AngleCreated(angle_id=angle.id))

    @staticmethod
    def _parse_json(text: str) -> dict:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            cleaned = cleaned.rsplit("```", 1)[0].strip()
        try:
            return json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            logger.warning("Failed to parse decomposition JSON: %s", cleaned[:200])
            return {}
