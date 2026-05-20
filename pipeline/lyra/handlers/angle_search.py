"""Per-angle search --- iterative query execution with source registration."""

import asyncio
import json
import logging
from pathlib import Path

from pipeline.lyra.config import _get_settings
from pipeline.lyra.handlers import BaseHandler
from pipeline.lyra.minimax_shared import minimax_chat_anthropic
from pipeline.lyra.research_events import AngleCreated, AngleSaturated, SourcesFound

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


class SearchHandler(BaseHandler):
    def register(self):
        self.bus.on(AngleCreated, self._on_angle_created)

    async def _on_angle_created(self, event: AngleCreated):
        await self.search_angle(event.angle_id)

    async def search_angle(self, angle_id: str):
        """Run search queries for an angle and register sources."""
        angle = next((a for a in self.state.angles if a.id == angle_id), None)
        if not angle or angle.saturated:
            return

        from pipeline.lyra.theo_sources import MultiSourceSearch

        settings = _get_settings()
        searcher = MultiSourceSearch(settings)

        queries = angle.search_queries[: self.state.config.queries_per_angle]
        if not queries:
            return

        self.emit_sse(
            {
                "type": "pipeline",
                "stage": f"search_{angle_id}",
                "status": "start",
                "meta": {"subtask_total": len(queries), "angle": angle.topic},
            }
        )
        self.emit_sse(
            {
                "type": "status",
                "content": f"Searching for '{angle.topic}' ({len(queries)} queries)...",
            }
        )

        # No semaphore --- search uses HTTP APIs, not LLM calls
        results = await searcher.search(
            queries, self.state.config.source_apis, self.state.disabled_adapters
        )

        new_sources = 0
        for r in results:
            sid = self.state.registry.register_source(
                url=r.url,
                title=r.title,
                snippet=r.snippet,
                date=r.date,
                doi=r.doi,
                authors=r.authors,
                venue=r.venue,
                citation_count=r.citation_count,
            )
            if sid not in angle.source_ids:
                angle.source_ids.append(sid)
                new_sources += 1
            source = self.state.registry.get_reference(sid)
            if source and source.reliability_tier == 0:
                source.reliability_tier = r.default_tier

        angle.search_rounds += 1

        self.emit_sse(
            {
                "type": "pipeline",
                "stage": f"search_{angle_id}",
                "status": "done",
                "meta": {
                    "new_sources": new_sources,
                    "total_sources": len(angle.source_ids),
                    "round": angle.search_rounds,
                },
            }
        )
        self.state.log(
            "search",
            f"Angle '{angle.topic}' round {angle.search_rounds}: {new_sources} new sources ({len(angle.source_ids)} total)",
        )

        await self.bus.emit(SourcesFound(angle_id=angle_id, count=new_sources))

    async def refine_and_search(self, angle_id: str, specialist_gaps: list[str]):
        """Generate refined queries based on specialist feedback, then search again."""
        angle = next((a for a in self.state.angles if a.id == angle_id), None)
        if not angle or angle.saturated:
            return

        # Use effective_max_rounds if rabbit holes granted bonus rounds
        max_rounds = max(
            self.state.config.max_search_rounds_per_angle,
            angle.effective_max_rounds,
        )
        if angle.search_rounds >= max_rounds:
            angle.saturated = True
            self.state.log(
                "search", f"Angle '{angle.topic}' hit max search rounds ({angle.search_rounds})"
            )
            await self.bus.emit(AngleSaturated(angle_id=angle.id))
            return

        # Generate refined queries using LLM
        prompt_path = PROMPTS_DIR / "v2_query_refinement.txt"
        if prompt_path.exists():
            prompt = prompt_path.read_text(encoding="utf-8")
            user_msg = (
                f"## Angle topic\n\n{angle.topic}\n\n"
                f"## Previous queries\n\n{json.dumps(angle.search_queries)}\n\n"
                f"## Gaps identified by specialists\n\n"
                + "\n".join(f"- {g}" for g in specialist_gaps)
            )
            settings = _get_settings()
            async with self.semaphore:
                raw = await asyncio.to_thread(
                    minimax_chat_anthropic,
                    prompt,
                    user_msg,
                    4096,
                    settings,
                    temperature=settings.temperature_research,
                )
            self.state.llm_call_count += 1
            parsed = self._parse_json(raw)
            new_queries = parsed.get("refined_queries", [])
            # The prompt may return objects {"query": "...", "targets_gap": "..."}
            new_queries = [
                item["query"] if isinstance(item, dict) else item for item in new_queries
            ]
            if new_queries:
                angle.search_queries = new_queries[: self.state.config.queries_per_angle]

        await self.search_angle(angle_id)

    @staticmethod
    def _parse_json(text: str) -> dict:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            cleaned = cleaned.rsplit("```", 1)[0].strip()
        try:
            return json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            return {}
