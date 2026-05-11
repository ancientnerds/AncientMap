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
        settings = _get_settings()
        proposed = await asyncio.to_thread(
            structured_llm_call,
            prompt,
            self.state.question,
            DECOMPOSITION_SCHEMA,
            self.state.config.max_tokens_per_call,
            settings,
            temperature=settings.temperature_research,
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
            # Belt-and-braces: even with strict json_schema, treat the LLM
            # output as boundary data — a single bare string in the angles
            # array would otherwise abort the whole pipeline at phase 1.
            if not isinstance(ad, dict):
                self.state.log(
                    "decomposition",
                    f"Skipping non-dict angle entry: {repr(ad)[:80]}",
                )
                continue
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

        # -------------------------------------------------------------
        # Phase C: Inject user sub-questions as their own angles
        # -------------------------------------------------------------
        from pipeline.lyra import canonical_coverage
        from pipeline.lyra.minimax_shared import minimax_chat_anthropic

        async def _cov_llm(sys_prompt, usr, max_tok, s, temp):
            return await asyncio.to_thread(
                minimax_chat_anthropic, sys_prompt, usr, max_tok, s, temperature=temp
            )

        subquestions = canonical_coverage.extract_user_subquestions(self.state.question)
        for sq in subquestions:
            sq_key = sq.lower()[:60]
            if any(sq_key in a.topic.lower() or sq_key in a.description.lower() for a in validated):
                continue  # already covered
            validated.append(
                ResearchAngle(
                    id=uuid.uuid4().hex[:8],
                    topic=f"User sub-question: {sq[:80]}",
                    description=sq,
                    search_queries=[sq][: self.state.config.queries_per_angle],
                    specialist_domains=[],
                )
            )
            self.state.log(
                "decomposition",
                f"Injected user-subquestion angle: {sq[:60]}",
            )

        # -------------------------------------------------------------
        # Phase D: LLM-driven canonical coverage gap check
        # -------------------------------------------------------------
        try:
            gaps = await canonical_coverage.find_coverage_gaps(
                question=self.state.question,
                proposed_angle_topics=[a.topic for a in validated],
                llm_call=_cov_llm,
                settings=settings,
            )
            self.state.llm_call_count += 2  # enumerate + gap check
        except Exception as exc:
            logger.warning("canonical coverage check failed: %s", exc)
            gaps = []

        for subtopic in gaps:
            validated.append(
                ResearchAngle(
                    id=uuid.uuid4().hex[:8],
                    topic=f"Canonical: {subtopic}",
                    description=(
                        f"Required canonical coverage of '{subtopic}'. "
                        "Investigate scholarly and alternative perspectives on this subtopic."
                    ),
                    search_queries=[subtopic][: self.state.config.queries_per_angle],
                    specialist_domains=[],
                )
            )
            self.state.log(
                "decomposition",
                f"Injected canonical-coverage angle: {subtopic}",
            )

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
