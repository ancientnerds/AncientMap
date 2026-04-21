"""Handler: populates state.image_candidate_pool per angle.

Runs in parallel with angle_search (both listen on AngleCreated). For each
angle, asks a specialist for 3-5 short image queries, fans those out across
the imagery connectors, dedupes, and stores serialized ImageCandidate dicts
in the state pool. ProbativeImagesHandler later selects from this pool.

If the feature flag is off, this handler no-ops so the pool stays empty and
PIH's on-demand fetch fallback takes over transparently.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict

from pipeline.lyra.angle_image_queries import generate_queries_for_angle
from pipeline.lyra.config import _get_settings
from pipeline.lyra.handlers import BaseHandler
from pipeline.lyra.image_fetcher import fetch_candidates
from pipeline.lyra.research_events import AngleCreated

logger = logging.getLogger(__name__)

_MAX_CANDIDATES_PER_ANGLE = 60
_QUERY_CANDIDATE_LIMIT = 8  # per connector per query


class AngleImageResearchHandler(BaseHandler):
    """Builds state.image_candidate_pool[angle.id] with probative image candidates."""

    def register(self):
        self.bus.on(AngleCreated, self._on_angle_created)

    async def _on_angle_created(self, event: AngleCreated):
        settings = _get_settings()
        if not getattr(settings, "probative_images_enabled", True):
            return

        angle = next((a for a in self.state.angles if a.id == event.angle_id), None)
        if angle is None:
            return

        self.emit_sse(
            {
                "type": "pipeline",
                "stage": f"image_research_{angle.id}",
                "status": "start",
                "meta": {"angle": angle.topic},
            }
        )

        # 1. Generate queries for this angle
        try:
            queries = await generate_queries_for_angle(
                angle.topic, getattr(angle, "description", "") or "", settings
            )
        except Exception as exc:
            logger.warning("image_research: query generation failed for %s: %s", angle.topic, exc)
            queries = []

        if not queries:
            self.state.image_candidate_pool[angle.id] = []
            print(
                f"[image_research] no queries generated for angle {angle.id} ({angle.topic}) — pool empty",
                flush=True,
            )
            self.emit_sse(
                {
                    "type": "pipeline",
                    "stage": f"image_research_{angle.id}",
                    "status": "done",
                    "meta": {"candidates": 0, "queries": 0},
                }
            )
            return

        # 2. Fan out across queries in parallel
        results = await asyncio.gather(
            *[fetch_candidates(q, limit_per_source=_QUERY_CANDIDATE_LIMIT) for q in queries],
            return_exceptions=True,
        )

        # 3. Flatten + dedupe by URL (preserve order of first occurrence)
        seen_urls: set[str] = set()
        pool: list[dict] = []
        query_failures: list[tuple[str, Exception]] = []
        per_query_counts: list[int] = []
        for q, batch in zip(queries, results, strict=False):
            if isinstance(batch, Exception):
                query_failures.append((q, batch))
                per_query_counts.append(0)
                continue
            added = 0
            for cand in batch or []:
                if not cand.url or cand.url in seen_urls:
                    continue
                seen_urls.add(cand.url)
                pool.append(asdict(cand))
                added += 1
                if len(pool) >= _MAX_CANDIDATES_PER_ANGLE:
                    break
            per_query_counts.append(added)
            if len(pool) >= _MAX_CANDIDATES_PER_ANGLE:
                break

        for q, exc in query_failures:
            logger.warning("image_research: query '%s' failed: %s", q[:80], exc)

        if not pool:
            print(
                f"[image_research] EMPTY pool for angle {angle.id} ({angle.topic}) — "
                f"{len(queries)} queries, {len(query_failures)} failed, 0 candidates returned "
                f"(per-query: {per_query_counts})",
                flush=True,
            )

        self.state.image_candidate_pool[angle.id] = pool

        self.emit_sse(
            {
                "type": "pipeline",
                "stage": f"image_research_{angle.id}",
                "status": "done",
                "meta": {"candidates": len(pool), "queries": len(queries)},
            }
        )
        logger.info(
            "image_research: angle '%s' — %d candidates from %d queries",
            angle.topic[:60],
            len(pool),
            len(queries),
        )
