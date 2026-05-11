"""Cross-pollination --- share findings across angles between round 1 and round 2.

After all angles complete their first specialist round, this handler examines
all findings together and enriches each angle with insights from other angles.
This enables round 2 to search for interdisciplinary connections that isolated
research would miss.

Also runs a second cross-pollination after round 2 completes, enriching angles
with deeper connections discovered during the verification phase.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
from pathlib import Path

from pipeline.lyra.config import _get_settings
from pipeline.lyra.handlers import BaseHandler
from pipeline.lyra.minimax_shared import structured_llm_call
from pipeline.lyra.research_events import (
    AllAnglesRound1Complete,
    AllAnglesRound2Complete,
    CrossPollinationComplete,
)
from pipeline.lyra.schemas import CROSS_POLLINATION_SCHEMA

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

# Threshold for the Voyage-embedding cosine gate that keeps enriched
# cross-pollination queries on-topic. Voyage-4 query/document relevance
# pairs typically land in 0.45-0.7 for genuinely related text; 0.4 is a
# conservative floor that drops obvious drift (e.g. Sphinx queries on a
# Sea Peoples question) without rejecting legitimate cross-angle leads.
_DRIFT_COSINE_FLOOR = float(os.getenv("THEO_DRIFT_COSINE_FLOOR", "0.4"))


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity for two equal-length dense vectors."""
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class CrossPollinationHandler(BaseHandler):
    def register(self):
        self.bus.on(AllAnglesRound1Complete, self._on_round1_complete)
        self.bus.on(AllAnglesRound2Complete, self._on_round1_complete)

    async def _on_round1_complete(self, event: AllAnglesRound1Complete | AllAnglesRound2Complete):
        """Cross-pollinate findings across all angles."""
        round_label = "round 2" if isinstance(event, AllAnglesRound2Complete) else "round 1"

        self.emit_sse(
            {
                "type": "pipeline",
                "stage": "cross_pollination",
                "status": "start",
                "meta": {
                    "subtask_total": 1,
                    "angles": len(self.state.angles),
                    "after_round": round_label,
                },
            }
        )
        self.emit_sse(
            {
                "type": "status",
                "content": f"Cross-pollinating findings across research angles (after {round_label})...",
            }
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
            )[:15]
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
            f"## Angle findings from {round_label}\n\n{all_summaries}"
        )

        settings = _get_settings()
        async with self.semaphore:
            result = await asyncio.to_thread(
                structured_llm_call,
                prompt,
                user_msg,
                CROSS_POLLINATION_SCHEMA,
                self.state.config.max_tokens_per_call,
                settings,
                temperature=settings.temperature_synthesis,
            )
        self.state.llm_call_count += 1

        # ---- Drift gate prep -----------------------------------------------
        # Collect all candidate enriched_queries across angles, batch-embed
        # them via Voyage, and drop any whose cosine to the original
        # question vector falls below _DRIFT_COSINE_FLOOR. This stops
        # specialist or LLM hallucinations (e.g. "Great Sphinx of Giza" on a
        # Sea Peoples question) from being adopted as next-round queries.
        valid_cps = [cp for cp in result.get("cross_pollination", []) if isinstance(cp, dict)]
        for cp in result.get("cross_pollination", []):
            if not isinstance(cp, dict):
                logger.warning(
                    "cross_pollination: skipping non-dict item: %s",
                    repr(cp)[:120],
                )

        candidate_pool: list[str] = []
        for cp in valid_cps:
            for q in cp.get("enriched_queries", []):
                if isinstance(q, str) and q.strip():
                    candidate_pool.append(q.strip())

        # Compute embeddings only if we have something to gate. Reuses the
        # same Voyage client + voyage-4 query model the rest of Lyra uses.
        query_to_score: dict[str, float] = {}
        if candidate_pool:
            try:
                from api.services.lyra_embeddings import get_embeddings

                embedder = get_embeddings("query")
                if self.state.question_embedding is None:
                    self.state.question_embedding = embedder.embed_query(self.state.question)
                # Deduplicate before embedding to avoid paying for repeats.
                unique_queries = list(dict.fromkeys(candidate_pool))
                query_vectors = await asyncio.to_thread(
                    embedder.embed_documents, unique_queries
                )
                for q, vec in zip(unique_queries, query_vectors, strict=True):
                    query_to_score[q] = _cosine(self.state.question_embedding, vec)
            except Exception as exc:
                # Drift gate is defence-in-depth; if Voyage fails we let
                # queries through (failing closed would break the pipeline
                # over an embedding-API hiccup).
                logger.warning(
                    "cross_pollination: drift-gate embedding failed (%s) — letting queries through",
                    exc,
                )

        # Apply cross-pollinated queries to each angle
        enriched_count = 0
        dropped_count = 0
        for cp in valid_cps:
            angle_id = cp.get("angle_id", "")
            enriched_queries = cp.get("enriched_queries", [])
            cross_insights = cp.get("cross_insights", [])

            angle = next((a for a in self.state.angles if a.id == angle_id), None)
            if not angle:
                continue

            # Filter enriched queries via the drift gate (only when scores
            # were computed; otherwise keep the LLM list as-is).
            filtered: list[str] = []
            for q in enriched_queries:
                if not isinstance(q, str) or not q.strip():
                    continue
                q = q.strip()
                score = query_to_score.get(q)
                if score is not None and score < _DRIFT_COSINE_FLOOR:
                    dropped_count += 1
                    self.state.log(
                        "cross_pollination",
                        f"dropped off-topic query (cos={score:.2f}): {q[:80]}",
                    )
                    continue
                filtered.append(q)

            # Add enriched queries for the next round. If everything got
            # dropped, leave the angle's pre-enrichment queries in place.
            if filtered:
                angle.search_queries = filtered[: self.state.config.queries_per_angle]
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
                    "after_round": round_label,
                },
            }
        )
        self.state.log(
            "cross_pollination",
            f"Enriched {enriched_count}/{len(self.state.angles)} angles "
            f"with cross-angle queries (after {round_label})",
        )

        # Now trigger next round search for all angles
        await self.bus.emit(CrossPollinationComplete())
