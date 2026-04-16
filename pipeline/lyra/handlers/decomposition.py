"""Topic decomposition --- break question into independent research angles."""

import asyncio
import logging
import uuid
from pathlib import Path

from pipeline.lyra.config import _get_settings
from pipeline.lyra.handlers import BaseHandler
from pipeline.lyra.minimax_shared import structured_llm_call
from pipeline.lyra.research_events import AngleCreated
from pipeline.lyra.research_state import ResearchAngle, ResearchPhase
from pipeline.lyra.schemas import DECOMPOSITION_SCHEMA

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


class DecompositionHandler(BaseHandler):
    def register(self):
        # No event triggers --- called directly by orchestrator at start
        pass

    async def decompose(self):
        """Phase A+B: Propose angles, validate with quick search, register on state."""
        self.state.phase = ResearchPhase.DECOMPOSING
        self.emit_sse(
            {
                "type": "pipeline",
                "stage": "decomposition",
                "status": "start",
                "meta": {"subtask_total": 2},
            }
        )
        self.emit_sse(
            {
                "type": "status",
                "content": "Decomposing research question into angles...",
                "subtask_done": 0,
                "subtask_total": 2,
            }
        )

        # Phase A: LLM proposes angles
        prompt = (PROMPTS_DIR / "v2_decomposition.txt").read_text(encoding="utf-8")
        proposed = await asyncio.to_thread(
            structured_llm_call,
            prompt,
            self.state.question,
            DECOMPOSITION_SCHEMA,
            self.state.config.max_tokens_per_call,
            _get_settings(),
        )
        self.state.llm_call_count += 1

        angles_data = proposed.get("angles", [])
        if not angles_data:
            self.state.error = "Decomposition produced no research angles"
            return

        self.emit_sse(
            {
                "type": "status",
                "content": f"Proposed {len(angles_data)} research angles, validating...",
                "subtask_done": 1,
                "subtask_total": 2,
            }
        )

        # Phase B: Validation search per angle
        from pipeline.lyra.theo_sources import MultiSourceSearch

        settings = _get_settings()
        searcher = MultiSourceSearch(settings)

        validated: list[ResearchAngle] = []
        for ad in angles_data[: self.state.config.max_angles]:
            queries = ad.get("search_queries", [])[:3]  # 2-3 validation queries
            if not queries:
                continue

            async with self.semaphore:
                results = await searcher.search(queries, "standard", self.state.disabled_adapters)

            if len(results) < 2:
                self.state.log(
                    "decomposition",
                    f"Dropped angle '{ad.get('topic', '?')}' --- insufficient sources ({len(results)})",
                )
                continue

            angle = ResearchAngle(
                id=uuid.uuid4().hex[:8],
                topic=ad.get("topic", ""),
                description=ad.get("description", ""),
                search_queries=ad.get("search_queries", [])[: self.state.config.queries_per_angle],
                specialist_domains=ad.get("specialist_domains", []),
            )

            # Validation only checks existence --- don't register sources here.
            # The search handler registers sources properly during the research loop.
            self.state.log(
                "decomposition",
                f"Validated angle '{ad.get('topic', '?')}' --- {len(results)} sources available",
            )
            validated.append(angle)

        if not validated:
            self.state.error = "No research angles had sufficient source coverage"
            return

        self.state.angles = validated
        self.state.phase = ResearchPhase.EXPLORING

        self.emit_sse(
            {
                "type": "pipeline",
                "stage": "decomposition",
                "status": "done",
                "meta": {"angles": len(validated), "angle_topics": [a.topic for a in validated]},
            }
        )
        self.emit_sse(
            {
                "type": "status",
                "content": f"Research decomposed into {len(validated)} angles",
                "subtask_done": 2,
                "subtask_total": 2,
            }
        )

        self.state.log(
            "decomposition", f"Validated {len(validated)} angles from {len(angles_data)} proposed"
        )

        # Emit AngleCreated for each validated angle
        for angle in validated:
            await self.bus.emit(AngleCreated(angle_id=angle.id))
