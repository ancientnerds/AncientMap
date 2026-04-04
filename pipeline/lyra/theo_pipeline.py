"""Main orchestrator for Theo's archaeological research pipeline.

Runs a research question through 8 stages, producing an academic paper
with citations.  Each stage receives and updates a shared PipelineContext.
The tier config (from theo_config.py) controls which stages run and with
what parameters.

Usage:
    from pipeline.lyra.theo_pipeline import TheoPipeline

    pipeline = TheoPipeline()
    ctx = await pipeline.run("Was Gobekli Tepe a temple?", effort="paper", emit=sse_emit)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from api.services.theo_config import EFFORT_CONFIG, TierConfig
from pipeline.lyra.config import LyraSettings, _get_settings
from pipeline.lyra.minimax_shared import (
    create_minimax_client,
    minimax_chat,
)
from pipeline.lyra.theo_citations import CitationRegistry, audit_citations
from pipeline.lyra.theo_sources import MultiSourceSearch
from pipeline.lyra.theo_specialists import (
    Specialist,
    build_specialist_prompt,
    select_specialists,
)

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"

# Max parallel specialist calls to MiniMax
_SPECIALIST_WORKERS = 3


# ---------------------------------------------------------------------------
# Pipeline context — mutable state passed through all stages
# ---------------------------------------------------------------------------


@dataclass
class PipelineContext:
    """Mutable state passed through all pipeline stages."""

    question: str
    effort: str
    tier: TierConfig
    registry: CitationRegistry

    # Stage 1 outputs
    domain_tags: list[str] = field(default_factory=list)
    sub_questions: list[str] = field(default_factory=list)
    search_queries: list[str] = field(default_factory=list)
    temporal_scope: str = ""
    geographic_scope: str = ""
    specialists: list[Specialist] = field(default_factory=list)

    # Stage 2 outputs
    sources_context: str = ""  # formatted source snippets for specialist prompts

    # Stage 4 outputs
    specialist_analyses: dict[str, dict] = field(default_factory=dict)

    # Stage 5 outputs
    synthesis: dict = field(default_factory=dict)

    # Stage 6 outputs (Thesis only)
    debate_result: dict = field(default_factory=dict)

    # Stage 7 outputs
    moderated_result: dict = field(default_factory=dict)

    # Stage 8 outputs
    paper_text: str = ""
    paper_title: str = ""
    audit_result: dict = field(default_factory=dict)

    # Tracking
    total_tokens: int = 0
    pipeline_trace: list[dict] = field(default_factory=list)
    error: str = ""


# ---------------------------------------------------------------------------
# The pipeline
# ---------------------------------------------------------------------------


class TheoPipeline:
    """Orchestrates all 8 stages of Theo's research pipeline."""

    def __init__(self, settings: LyraSettings | None = None) -> None:
        self._settings = settings or _get_settings()
        self._client = create_minimax_client(
            self._settings.minimax_base_url,
            self._settings.minimax_api_key,
        )
        self._model = self._settings.minimax_model
        self._searcher = MultiSourceSearch(self._settings)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run(
        self,
        question: str,
        effort: str,
        emit: Callable[[dict], None],
    ) -> PipelineContext:
        """Run the full pipeline.  *emit* sends SSE events to the client."""
        tier = EFFORT_CONFIG.get(effort, EFFORT_CONFIG["article"])

        ctx = PipelineContext(
            question=question,
            effort=effort,
            tier=tier,
            registry=CitationRegistry(),
        )

        pipeline_start = time.monotonic()

        # Relevancy gate — reject questions unrelated to archaeology/history
        rejection = await self._check_relevance(question, emit)
        if rejection:
            ctx.error = rejection
            return ctx

        # Stages 1-3 are fatal — if they fail the pipeline cannot continue.
        for stage_fn, stage_name in [
            (self._stage_1_analyze, "question_analysis"),
            (self._stage_2_search, "web_search"),
            (self._stage_3_audit, "source_audit"),
        ]:
            try:
                await stage_fn(ctx, emit)
            except Exception as exc:
                logger.exception("Fatal failure in %s", stage_name)
                ctx.error = f"Pipeline failed at {stage_name}: {exc}"
                emit(
                    {"type": "pipeline", "stage": stage_name, "status": "error", "error": str(exc)}
                )
                return ctx

        # Stages 4-7 are non-fatal — continue with available data on failure.
        for stage_fn, stage_name in [
            (self._stage_4_specialists, "specialist_analysis"),
            (self._stage_5_synthesize, "synthesis"),
            (self._stage_6_debate, "debate"),
            (self._stage_7_moderate, "moderator"),
        ]:
            try:
                await stage_fn(ctx, emit)
            except Exception as exc:
                logger.exception("Non-fatal failure in %s", stage_name)
                emit(
                    {
                        "type": "pipeline",
                        "stage": stage_name,
                        "status": "warning",
                        "warning": f"Stage {stage_name} failed: {exc}",
                    }
                )

        # Stage 8 — paper assembly.  On failure, dump raw findings.
        try:
            await self._stage_8_paper(ctx, emit)
        except Exception as exc:
            logger.exception("Paper assembly failed, dumping raw findings")
            emit(
                {
                    "type": "pipeline",
                    "stage": "paper_assembly",
                    "status": "warning",
                    "warning": f"Paper assembly failed: {exc}",
                }
            )
            ctx.paper_text = self._fallback_paper(ctx)
            ctx.paper_title = "Research Findings (unformatted)"

        total_ms = int((time.monotonic() - pipeline_start) * 1000)
        emit(
            {
                "type": "pipeline",
                "stage": "complete",
                "status": "done",
                "duration_ms": total_ms,
                "meta": {
                    "total_sources": len(ctx.registry.sources),
                    "specialists": len(ctx.specialists),
                    "effort": effort,
                },
            }
        )
        return ctx

    # ------------------------------------------------------------------
    # Stage 1: Question analysis + specialist selection
    # ------------------------------------------------------------------

    async def _stage_1_analyze(
        self,
        ctx: PipelineContext,
        emit: Callable[[dict], None],
    ) -> None:
        stage = "question_analysis"
        t0 = time.monotonic()
        emit({"type": "pipeline", "stage": stage, "status": "start"})
        emit({"type": "status", "content": "Analyzing research question..."})

        system = self._load_prompt("theo_question_analysis")

        if ctx.tier.convergence_stage1 > 0:
            critic_prompt = self._load_prompt("theo_question_critic")
            raw = await self._run_convergence_loop(
                generator_prompt=system,
                critic_prompt=critic_prompt,
                initial_input=ctx.question,
                max_iterations=ctx.tier.convergence_stage1,
                max_tokens=ctx.tier.max_tokens_per_call,
                emit=emit,
                stage_name=stage,
            )
        else:
            raw = await self._m27_call_async(system, ctx.question, ctx.tier.max_tokens_per_call)

        parsed = self._parse_json(raw)

        ctx.domain_tags = parsed.get("domain_tags", [])
        ctx.sub_questions = parsed.get("sub_questions", [])
        ctx.search_queries = parsed.get("search_queries", [])
        ctx.temporal_scope = parsed.get("temporal_scope", "")
        ctx.geographic_scope = parsed.get("geographic_scope", "")

        # Select specialists based on domain tags
        emit({"type": "status", "content": "Selecting specialist panel..."})
        ctx.specialists = select_specialists(
            domain_tags=ctx.domain_tags,
            question=ctx.question,
            count=ctx.tier.specialists_count,
        )

        ms = int((time.monotonic() - t0) * 1000)
        emit(
            {
                "type": "pipeline",
                "stage": stage,
                "status": "done",
                "duration_ms": ms,
                "meta": {
                    "domain_tags": ctx.domain_tags,
                    "queries": len(ctx.search_queries),
                    "specialists": [s.id for s in ctx.specialists],
                },
            }
        )

    # ------------------------------------------------------------------
    # Stage 2: Multi-source academic + web research
    # ------------------------------------------------------------------

    async def _stage_2_search(
        self,
        ctx: PipelineContext,
        emit: Callable[[dict], None],
    ) -> None:
        stage = "web_search"
        t0 = time.monotonic()
        emit({"type": "pipeline", "stage": stage, "status": "start"})

        queries = ctx.search_queries[: ctx.tier.max_search_queries]
        source_group = ctx.tier.source_apis

        emit(
            {
                "type": "status",
                "content": f"Searching {len(queries)} queries across "
                f"{source_group} source group...",
            }
        )

        # Run multi-source parallel search
        raw_sources = await self._searcher.search(queries, source_group)

        if not raw_sources:
            ctx.error = "No sources found — all search APIs returned zero results."
            emit({"type": "status", "content": "No sources found in any search API."})
            return

        # Register all sources in the citation registry
        for r in raw_sources:
            sid = ctx.registry.register_source(
                url=r.url,
                title=r.title,
                snippet=r.snippet,
                date=r.date,
                search_query="",
            )
            # Apply default tier from the source API
            source = ctx.registry.get_reference(sid)
            if source and source.reliability_tier == 0:
                source.reliability_tier = r.default_tier

        # Build formatted sources_context for specialist prompts — ALL sources
        lines: list[str] = []
        for sid, source in ctx.registry.sources.items():
            tier_str = ""
            if source.reliability_tier == 1:
                tier_str = " [Academic]"
            elif source.reliability_tier == 2:
                tier_str = " [Reputable]"
            lines.append(
                f"Source [{sid}]: {source.title}{tier_str}\n"
                f"URL: {source.url}\n"
                f"Snippet: {source.snippet}\n"
            )
        ctx.sources_context = "\n".join(lines)

        total_results = len(ctx.registry.sources)
        academic_count = sum(
            1 for s in ctx.registry.sources.values() if s.reliability_tier == 1
        )

        ms = int((time.monotonic() - t0) * 1000)
        emit(
            {
                "type": "pipeline",
                "stage": stage,
                "status": "done",
                "duration_ms": ms,
                "meta": {
                    "queries_run": len(queries),
                    "unique_sources": total_results,
                    "academic_sources": academic_count,
                    "source_group": source_group,
                },
            }
        )

    # ------------------------------------------------------------------
    # Stage 3: Source reliability audit
    # ------------------------------------------------------------------

    async def _stage_3_audit(
        self,
        ctx: PipelineContext,
        emit: Callable[[dict], None],
    ) -> None:
        stage = "source_audit"
        t0 = time.monotonic()
        emit({"type": "pipeline", "stage": stage, "status": "start"})

        if not ctx.sources_context.strip():
            ctx.error = "No sources available for reliability audit."
            emit({"type": "pipeline", "stage": stage, "status": "error"})
            return

        # Batch sources into chunks of 40 to avoid M2.7 timeout on large sets
        source_items = list(ctx.registry.sources.items())
        batch_size = 40
        batches = [
            source_items[i : i + batch_size]
            for i in range(0, len(source_items), batch_size)
        ]

        emit(
            {
                "type": "status",
                "content": f"Auditing {len(source_items)} sources "
                f"in {len(batches)} batch(es)...",
            }
        )

        system = self._load_prompt("theo_source_audit")
        rejected_ids: set[str] = set()
        total_scored = 0

        for batch_idx, batch in enumerate(batches):
            # Format this batch
            batch_lines = []
            for sid, source in batch:
                tier_str = ""
                if source.reliability_tier == 1:
                    tier_str = " [Academic]"
                elif source.reliability_tier == 2:
                    tier_str = " [Reputable]"
                batch_lines.append(
                    f"Source [{sid}]: {source.title}{tier_str}\n"
                    f"URL: {source.url}\nSnippet: {source.snippet}\n"
                )
            batch_context = "\n".join(batch_lines)
            user_msg = (
                f"## Research question\n\n{ctx.question}\n\n"
                f"## Sources (batch {batch_idx + 1}/{len(batches)})\n\n{batch_context}"
            )

            if len(batches) > 1:
                emit(
                    {
                        "type": "status",
                        "content": f"Auditing batch {batch_idx + 1}/{len(batches)} "
                        f"({len(batch)} sources)...",
                    }
                )

            raw = await self._m27_call_async(system, user_msg, ctx.tier.max_tokens_per_call)
            parsed = self._parse_json(raw)

            # Apply reliability tiers from this batch
            for entry in parsed.get("scored_sources", []):
                sid = entry.get("id", "")
                tier_val = entry.get("reliability_tier", 0)
                source = ctx.registry.sources.get(sid)
                if source:
                    source.reliability_tier = tier_val
                    total_scored += 1

            for entry in parsed.get("rejected_sources", []):
                rejected_ids.add(entry.get("id", ""))

        # Use coverage from the last batch (it sees the final state)
        parsed = self._parse_json(raw) if raw else {}

        coverage_sufficient = parsed.get("coverage_sufficient", True)

        # Convergence: if coverage insufficient and tier allows retry, fill gaps
        if not coverage_sufficient and ctx.tier.convergence_stage3:
            gaps = parsed.get("coverage_gaps", [])
            if gaps:
                emit(
                    {
                        "type": "status",
                        "content": "Coverage gaps found, running supplementary searches...",
                    }
                )

                gap_results = await self._searcher.search(
                    gaps[:3], ctx.tier.source_apis
                )
                for r in gap_results:
                    sid = ctx.registry.register_source(
                        url=r.url,
                        title=r.title,
                        snippet=r.snippet,
                        date=r.date,
                        search_query="gap_fill",
                    )
                    source = ctx.registry.get_reference(sid)
                    if source and source.reliability_tier == 0:
                        source.reliability_tier = r.default_tier

                # Rebuild sources_context with new sources
                lines: list[str] = []
                for sid, source in ctx.registry.sources.items():
                    lines.append(
                        f"Source [{sid}]: {source.title}\n"
                        f"URL: {source.url}\n"
                        f"Snippet: {source.snippet}\n"
                    )
                ctx.sources_context = "\n".join(lines)

                # Re-audit the expanded source set
                emit({"type": "status", "content": "Re-auditing expanded source set..."})
                user_msg_2 = (
                    f"## Research question\n\n{ctx.question}\n\n## Sources\n\n{ctx.sources_context}"
                )
                raw_2 = await self._m27_call_async(
                    system,
                    user_msg_2,
                    ctx.tier.max_tokens_per_call,
                )
                parsed_2 = self._parse_json(raw_2)
                for entry in parsed_2.get("scored_sources", []):
                    sid = entry.get("id", "")
                    tier_val = entry.get("reliability_tier", 0)
                    source = ctx.registry.sources.get(sid)
                    if source:
                        source.reliability_tier = tier_val

        ms = int((time.monotonic() - t0) * 1000)
        emit(
            {
                "type": "pipeline",
                "stage": stage,
                "status": "done",
                "duration_ms": ms,
                "meta": {
                    "scored": total_scored,
                    "rejected": len(rejected_ids),
                    "coverage_sufficient": coverage_sufficient,
                },
            }
        )

    # ------------------------------------------------------------------
    # Stage 4: Parallel specialist analysis
    # ------------------------------------------------------------------

    async def _stage_4_specialists(
        self,
        ctx: PipelineContext,
        emit: Callable[[dict], None],
    ) -> None:
        stage = "specialist_analysis"
        t0 = time.monotonic()
        emit({"type": "pipeline", "stage": stage, "status": "start"})

        loop = asyncio.get_running_loop()
        executor = ThreadPoolExecutor(max_workers=_SPECIALIST_WORKERS)

        def _run_specialist(spec: Specialist) -> tuple[str, str]:
            """Synchronous specialist call, returns (specialist_id, raw_json).

            Creates a fresh httpx.Client per call because httpx.Client is not
            thread-safe and we run multiple specialists in parallel via
            ThreadPoolExecutor.
            """
            system_prompt, user_prompt = build_specialist_prompt(
                spec,
                ctx.question,
                ctx.sources_context,
            )
            client = create_minimax_client(
                self._settings.minimax_base_url,
                self._settings.minimax_api_key,
            )
            try:
                raw = minimax_chat(
                    client,
                    self._model,
                    system_prompt,
                    user_prompt,
                    ctx.tier.max_tokens_per_call,
                )
            finally:
                client.close()
            return spec.id, raw

        # Launch all specialist calls in parallel
        futures = [
            loop.run_in_executor(executor, _run_specialist, spec) for spec in ctx.specialists
        ]

        emit(
            {
                "type": "status",
                "content": f"Running {len(ctx.specialists)} specialist analyses in parallel...",
            }
        )

        results = await asyncio.gather(*futures, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.warning("Specialist call failed: %s", result)
                continue

            spec_id, raw = result
            try:
                parsed = self._parse_json(raw)
            except (json.JSONDecodeError, ValueError):
                logger.warning("Failed to parse JSON from specialist %s", spec_id)
                continue

            ctx.specialist_analyses[spec_id] = parsed

            # Register claims from this specialist
            for finding in parsed.get("findings", []):
                source_ids = finding.get("source_ids", [])
                ctx.registry.add_claim(
                    claim_text=finding.get("claim", ""),
                    source_ids=source_ids,
                    specialist_id=spec_id,
                    confidence=finding.get("confidence", "medium"),
                )

            emit({"type": "status", "content": f"Specialist {spec_id} completed analysis."})

        executor.shutdown(wait=False)

        ms = int((time.monotonic() - t0) * 1000)
        emit(
            {
                "type": "pipeline",
                "stage": stage,
                "status": "done",
                "duration_ms": ms,
                "meta": {
                    "completed": len(ctx.specialist_analyses),
                    "requested": len(ctx.specialists),
                },
            }
        )

    # ------------------------------------------------------------------
    # Stage 5: Cross-source synthesis
    # ------------------------------------------------------------------

    async def _stage_5_synthesize(
        self,
        ctx: PipelineContext,
        emit: Callable[[dict], None],
    ) -> None:
        stage = "synthesis"
        t0 = time.monotonic()
        emit({"type": "pipeline", "stage": stage, "status": "start"})

        if not ctx.specialist_analyses:
            logger.warning("[THEO] Stage 5: No specialist analyses — using empty synthesis")
            ctx.synthesis = {"consensus_claims": [], "contested_claims": [], "unique_insights": [], "open_questions": []}
            emit({"type": "pipeline", "stage": stage, "status": "done", "duration_ms": 0, "meta": {"consensus": 0, "contested": 0, "unique": 0}})
            return

        emit({"type": "status", "content": "Synthesizing specialist findings..."})

        system = self._load_prompt("theo_synthesis")

        # Build input from all specialist analyses
        analyses_text = self._format_specialist_analyses(ctx)
        user_msg = (
            f"## Research question\n\n{ctx.question}\n\n## Specialist analyses\n\n{analyses_text}"
        )

        if ctx.tier.convergence_stage5 > 0:
            critic_prompt = self._load_prompt("theo_synthesis_critic")
            raw = await self._run_convergence_loop(
                generator_prompt=system,
                critic_prompt=critic_prompt,
                initial_input=user_msg,
                max_iterations=ctx.tier.convergence_stage5,
                max_tokens=ctx.tier.max_tokens_synthesis,
                emit=emit,
                stage_name=stage,
            )
        else:
            raw = await self._m27_call_async(
                system,
                user_msg,
                ctx.tier.max_tokens_synthesis,
            )

        ctx.synthesis = self._parse_json(raw)

        ms = int((time.monotonic() - t0) * 1000)
        emit(
            {
                "type": "pipeline",
                "stage": stage,
                "status": "done",
                "duration_ms": ms,
                "meta": {
                    "consensus": len(ctx.synthesis.get("consensus_claims", [])),
                    "contested": len(ctx.synthesis.get("contested_claims", [])),
                    "unique": len(ctx.synthesis.get("unique_insights", [])),
                },
            }
        )

    # ------------------------------------------------------------------
    # Stage 6: Multi-agent debate (Thesis only)
    # ------------------------------------------------------------------

    async def _stage_6_debate(
        self,
        ctx: PipelineContext,
        emit: Callable[[dict], None],
    ) -> None:
        if ctx.tier.debate_rounds <= 0:
            return

        stage = "debate"
        t0 = time.monotonic()
        emit({"type": "pipeline", "stage": stage, "status": "start"})
        emit(
            {
                "type": "status",
                "content": f"Running {ctx.tier.debate_rounds}-round specialist debate...",
            }
        )

        challenge_prompt = self._load_prompt("theo_debate_challenge")
        defense_prompt = self._load_prompt("theo_debate_defense")
        synthesis_json = json.dumps(ctx.synthesis, indent=2)

        all_challenges: list[dict] = []
        all_defenses: list[dict] = []

        for rnd in range(1, ctx.tier.debate_rounds + 1):
            emit(
                {
                    "type": "status",
                    "content": f"Debate round {rnd}/{ctx.tier.debate_rounds}: "
                    f"gathering challenges...",
                }
            )

            # Each specialist challenges the synthesis from their perspective
            round_challenges: list[dict] = []
            for spec in ctx.specialists:
                system_msg = (
                    f"You are {spec.name}, {spec.title}.\n\n"
                    f"{spec.perspective}\n\n{challenge_prompt}"
                )
                user_msg = (
                    f"## Synthesis to challenge\n\n{synthesis_json}\n\n"
                    f"## Your original findings\n\n"
                    f"{json.dumps(ctx.specialist_analyses.get(spec.id, {}), indent=2)}"
                )
                raw = await self._m27_call_async(
                    system_msg,
                    user_msg,
                    ctx.tier.max_tokens_per_call,
                )
                parsed = self._parse_json(raw)
                challenges = parsed.get("challenges", [])
                for c in challenges:
                    c["challenger_id"] = spec.id
                round_challenges.extend(challenges)

            all_challenges.extend(round_challenges)

            if not round_challenges:
                emit({"type": "status", "content": f"Round {rnd}: no challenges raised."})
                break

            # Defenders respond
            emit(
                {
                    "type": "status",
                    "content": f"Debate round {rnd}/{ctx.tier.debate_rounds}: "
                    f"gathering defenses...",
                }
            )

            for spec in ctx.specialists:
                # Find challenges targeting this specialist
                my_challenges = [
                    c for c in round_challenges if c.get("target_specialist") == spec.id
                ]
                if not my_challenges:
                    continue

                system_msg = (
                    f"You are {spec.name}, {spec.title}.\n\n{spec.perspective}\n\n{defense_prompt}"
                )
                user_msg = (
                    f"## Challenges directed at you\n\n"
                    f"{json.dumps(my_challenges, indent=2)}\n\n"
                    f"## Your original findings\n\n"
                    f"{json.dumps(ctx.specialist_analyses.get(spec.id, {}), indent=2)}"
                )
                raw = await self._m27_call_async(
                    system_msg,
                    user_msg,
                    ctx.tier.max_tokens_per_call,
                )
                parsed = self._parse_json(raw)
                defenses = parsed.get("defenses", [])
                for d in defenses:
                    d["defender_id"] = spec.id
                all_defenses.extend(defenses)

        ctx.debate_result = {
            "rounds": ctx.tier.debate_rounds,
            "challenges": all_challenges,
            "defenses": all_defenses,
        }

        ms = int((time.monotonic() - t0) * 1000)
        emit(
            {
                "type": "pipeline",
                "stage": stage,
                "status": "done",
                "duration_ms": ms,
                "meta": {"challenges": len(all_challenges), "defenses": len(all_defenses)},
            }
        )

    # ------------------------------------------------------------------
    # Stage 7: Moderator + devil's advocate
    # ------------------------------------------------------------------

    async def _stage_7_moderate(
        self,
        ctx: PipelineContext,
        emit: Callable[[dict], None],
    ) -> None:
        # Brief tier skips moderation entirely
        if ctx.effort == "brief" and ctx.tier.simplified_moderator is False:
            return

        stage = "moderator"
        t0 = time.monotonic()
        emit({"type": "pipeline", "stage": stage, "status": "start"})
        emit({"type": "status", "content": "Moderator reviewing findings..."})

        moderator_system = self._load_prompt("theo_moderator")

        # Build moderator input from synthesis + debate (if any)
        mod_input_parts = [
            f"## Research question\n\n{ctx.question}\n\n",
            f"## Synthesis\n\n{json.dumps(ctx.synthesis, indent=2)}\n\n",
        ]
        if ctx.debate_result:
            mod_input_parts.append(
                f"## Debate outcome\n\n{json.dumps(ctx.debate_result, indent=2)}\n\n"
            )
        mod_input = "".join(mod_input_parts)

        raw = await self._m27_call_async(
            moderator_system,
            mod_input,
            ctx.tier.max_tokens_synthesis,
        )
        moderated = self._parse_json(raw)

        # Devil's advocate pass
        if ctx.tier.devils_advocate:
            emit({"type": "status", "content": "Running devil's advocate review..."})
            da_system = self._load_prompt("theo_devils_advocate")
            da_input = (
                f"## Research question\n\n{ctx.question}\n\n"
                f"## Moderated conclusions\n\n{json.dumps(moderated, indent=2)}"
            )
            da_raw = await self._m27_call_async(
                da_system,
                da_input,
                ctx.tier.max_tokens_per_call,
            )
            da_parsed = self._parse_json(da_raw)

            # Check for critical attacks
            critical_attacks = [
                a for a in da_parsed.get("attacks", []) if a.get("severity") == "critical"
            ]

            if critical_attacks:
                emit(
                    {
                        "type": "status",
                        "content": f"Devil's advocate found {len(critical_attacks)} "
                        f"critical issue(s), re-running moderator...",
                    }
                )

                # Re-run moderator with devil's advocate feedback
                feedback_input = (
                    f"{mod_input}"
                    f"## Devil's advocate feedback\n\n"
                    f"{json.dumps(da_parsed, indent=2)}\n\n"
                    "IMPORTANT: The devil's advocate found critical weaknesses. "
                    "Revise the moderated conclusions to address these issues. "
                    "Drop or revise claims that cannot withstand the criticism."
                )
                raw_2 = await self._m27_call_async(
                    moderator_system,
                    feedback_input,
                    ctx.tier.max_tokens_synthesis,
                )
                moderated = self._parse_json(raw_2)

            moderated["devils_advocate"] = da_parsed

        ctx.moderated_result = moderated

        ms = int((time.monotonic() - t0) * 1000)
        emit(
            {
                "type": "pipeline",
                "stage": stage,
                "status": "done",
                "duration_ms": ms,
                "meta": {
                    "final_claims": len(moderated.get("final_claims", [])),
                    "revised": len(moderated.get("revised_claims", [])),
                    "dropped": len(moderated.get("dropped_claims", [])),
                },
            }
        )

    # ------------------------------------------------------------------
    # Stage 8: Paper assembly + citation audit
    # ------------------------------------------------------------------

    async def _stage_8_paper(
        self,
        ctx: PipelineContext,
        emit: Callable[[dict], None],
    ) -> None:
        stage = "paper_assembly"
        t0 = time.monotonic()
        emit({"type": "pipeline", "stage": stage, "status": "start"})
        emit({"type": "status", "content": "Assembling research paper..."})

        # Choose prompt based on effort tier
        if ctx.effort == "brief":
            paper_system = self._load_prompt("theo_paper_brief")
        else:
            paper_system = self._load_prompt("theo_paper_full")

        # Build reference map: assign numbers to all cited sources
        # Collect all source_ids mentioned across findings
        all_source_ids: set[str] = set()
        for claim in ctx.registry.claims:
            all_source_ids.update(claim.source_ids)

        # Also collect from moderated/synthesis results
        for claim_data in ctx.moderated_result.get("final_claims", []):
            all_source_ids.update(claim_data.get("source_ids", []))
        for claim_data in ctx.moderated_result.get("revised_claims", []):
            all_source_ids.update(claim_data.get("source_ids", []))

        for claim_data in ctx.synthesis.get("consensus_claims", []):
            all_source_ids.update(claim_data.get("source_ids", []))
        for insight in ctx.synthesis.get("unique_insights", []):
            all_source_ids.update(insight.get("source_ids", []))

        # Assign reference numbers to all cited sources
        ref_map_lines: list[str] = []
        sid_to_num: dict[str, int] = {}
        for sid in sorted(all_source_ids):
            source = ctx.registry.get_reference(sid)
            if source is None:
                continue
            num = ctx.registry.assign_reference_number(sid)
            sid_to_num[sid] = num
            ref_map_lines.append(f"[{num}] {source.title} — {source.url}")

        ref_map_text = "\n".join(ref_map_lines) if ref_map_lines else "(no references)"

        # Replace source_ids with [N] numbers in findings so the LLM
        # only ever sees [N] format — same pattern as article pipeline
        def _replace_source_ids(obj: dict | list) -> dict | list:
            """Recursively replace source_ids lists with [N] citation strings."""
            if isinstance(obj, dict):
                result = {}
                for k, v in obj.items():
                    if k == "source_ids" and isinstance(v, list):
                        result["citations"] = " ".join(
                            f"[{sid_to_num[sid]}]" for sid in v if sid in sid_to_num
                        )
                    else:
                        result[k] = _replace_source_ids(v)
                return result
            elif isinstance(obj, list):
                return [_replace_source_ids(item) for item in obj]
            return obj

        # Build the paper input — findings have [N] citations, not source IDs
        paper_input_parts = [
            f"## Research question\n\n{ctx.question}\n\n",
            f"## Reference map (use ONLY these [N] numbers for citations)\n\n{ref_map_text}\n\n",
        ]

        if ctx.moderated_result:
            cleaned = _replace_source_ids(ctx.moderated_result)
            paper_input_parts.append(
                f"## Moderated findings\n\n{json.dumps(cleaned, indent=2)}\n\n"
            )
        elif ctx.synthesis:
            cleaned = _replace_source_ids(ctx.synthesis)
            paper_input_parts.append(f"## Synthesis\n\n{json.dumps(cleaned, indent=2)}\n\n")

        if ctx.debate_result:
            cleaned_debate = _replace_source_ids(ctx.debate_result)
            paper_input_parts.append(
                f"## Debate summary\n\n{json.dumps(cleaned_debate, indent=2)}\n\n"
            )

        paper_input = "".join(paper_input_parts)

        raw_paper = await self._m27_call_async(
            paper_system,
            paper_input,
            ctx.tier.max_tokens_synthesis,
        )

        ctx.paper_text = raw_paper

        # Extract title from the first # heading
        title_match = re.search(r"^#\s+(.+)$", raw_paper, re.MULTILINE)
        ctx.paper_title = title_match.group(1).strip() if title_match else ctx.question

        # Append references list
        refs_md = ctx.registry.format_references_list()
        if refs_md:
            ctx.paper_text += f"\n\n## References\n\n{refs_md}"

        # Run citation audit
        emit({"type": "status", "content": "Auditing citations..."})
        ctx.audit_result = audit_citations(ctx.paper_text, ctx.registry)

        ms = int((time.monotonic() - t0) * 1000)
        emit(
            {
                "type": "pipeline",
                "stage": stage,
                "status": "done",
                "duration_ms": ms,
                "meta": {
                    "title": ctx.paper_title,
                    "audit_passed": ctx.audit_result.get("passed", False),
                    "total_citations": ctx.audit_result.get("total_citations", 0),
                    "total_references": ctx.audit_result.get("total_references", 0),
                },
            }
        )

    # ------------------------------------------------------------------
    # Relevancy gate — fast pre-check before the expensive pipeline
    # ------------------------------------------------------------------

    async def _check_relevance(
        self,
        question: str,
        emit: Callable[[dict], None],
    ) -> str:
        """Return an error message if the question is off-topic, or '' if relevant.

        Accepts anything connected to the ancient/historical world:
        archaeology, ancient history, prehistory, mythology, ancient civilizations,
        geological history, heritage, anthropology, paleontology, ancient technology,
        alternative/fringe ancient history (e.g. Ancient Astronauts, lost civilizations).
        """
        system = (
            "You are a relevancy filter for an archaeological research platform. "
            "Decide whether the user's question is related to ANY of these topics:\n"
            "- Archaeology, excavations, archaeological sites\n"
            "- Ancient history, prehistory, historical civilizations\n"
            "- Mythology, ancient religions, ancient texts\n"
            "- Geology and earth sciences related to human history\n"
            "- Anthropology, ancient cultures, migration\n"
            "- Paleontology, human evolution\n"
            "- Ancient technology, architecture, engineering\n"
            "- Heritage, conservation, museums\n"
            "- Numismatics, epigraphy, ancient languages\n"
            "- Alternative/fringe theories about ancient history "
            "(Ancient Astronauts, lost civilizations, Atlantis, Nibiru, etc.)\n\n"
            "Be VERY inclusive — if there is ANY plausible connection to the "
            "ancient or historical world, it is relevant. Only reject questions "
            "that have absolutely nothing to do with history or archaeology.\n\n"
            'Output ONLY: {"relevant": true} or {"relevant": false, "reason": "brief explanation"}'
        )

        raw = await self._m27_call_async(system, question, 256)
        parsed = self._parse_json(raw)

        if parsed.get("relevant", True):
            return ""

        reason = parsed.get("reason", "Question is not related to archaeology or ancient history")
        logger.info("[THEO] Relevancy gate rejected: %s — %s", question[:80], reason)
        emit({"type": "status", "content": f"Off-topic: {reason}"})
        emit({"type": "done", "status": "failed"})
        return (
            f"This question doesn't appear to be related to archaeology, "
            f"ancient history, or the ancient world. {reason}"
        )

    # ==================================================================
    # Helpers
    # ==================================================================

    def _m27_call(self, system: str, user_message: str, max_tokens: int) -> str:
        """Synchronous M2.7 call via minimax_chat."""
        return minimax_chat(
            self._client,
            self._model,
            system,
            user_message,
            max_tokens,
        )

    async def _m27_call_async(
        self,
        system: str,
        user_message: str,
        max_tokens: int,
    ) -> str:
        """Async wrapper around _m27_call using asyncio.to_thread."""
        return await asyncio.to_thread(self._m27_call, system, user_message, max_tokens)

    async def _run_convergence_loop(
        self,
        generator_prompt: str,
        critic_prompt: str,
        initial_input: str,
        max_iterations: int,
        max_tokens: int,
        emit: Callable[[dict], None],
        stage_name: str,
    ) -> str:
        """Generator-Critic convergence loop.

        1. Generator produces output from initial_input.
        2. Critic evaluates with JSON: {"pass": bool, "issues": [...], "suggestions": [...]}.
        3. If pass=True or max_iterations reached, return generator output.
        4. Else append critic feedback to generator prompt and retry.
        """
        generator_output = await self._m27_call_async(
            generator_prompt,
            initial_input,
            max_tokens,
        )

        for iteration in range(1, max_iterations + 1):
            # Critic evaluates
            critic_input = (
                f"## Original question\n\n{initial_input}\n\n"
                f"## Generated output to evaluate\n\n{generator_output}"
            )
            critic_raw = await self._m27_call_async(
                critic_prompt,
                critic_input,
                max_tokens,
            )

            critic_result = self._parse_json(critic_raw)

            if not critic_result:
                # If critic output is unparseable, accept generator output
                logger.warning("Critic output unparseable in %s, accepting", stage_name)
                break

            if critic_result.get("pass", False):
                emit({"type": "status", "content": f"Critic passed on iteration {iteration}."})
                break

            # Critic found issues — feed back to generator
            issues = critic_result.get("issues", [])
            suggestions = critic_result.get("suggestions", [])
            feedback = (
                f"The critic found issues with your output:\n"
                f"Issues: {json.dumps(issues)}\n"
                f"Suggestions: {json.dumps(suggestions)}\n\n"
                f"Revise your output to address these concerns. "
                f"Original question:\n{initial_input}"
            )

            emit(
                {
                    "type": "status",
                    "content": f"Critic found gaps, refining... "
                    f"(iteration {iteration}/{max_iterations})",
                }
            )

            generator_output = await self._m27_call_async(
                generator_prompt,
                feedback,
                max_tokens,
            )

        return generator_output

    def _load_prompt(self, name: str) -> str:
        """Load a prompt file from pipeline/lyra/prompts/."""
        path = PROMPTS_DIR / f"{name}.txt"
        return path.read_text(encoding="utf-8")

    def _parse_json(self, text: str) -> dict | list:
        """Parse JSON from M2.7 response, handling markdown fencing.

        Returns an empty dict on parse failure instead of raising, since
        callers use .get() on the result and the pipeline must not crash
        on malformed LLM output.
        """
        cleaned = text.strip()

        # Strip markdown code fences
        if cleaned.startswith("```"):
            # Remove opening fence (with optional language tag)
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            # Remove closing fence
            cleaned = cleaned.rsplit("```", 1)[0].strip()

        try:
            return json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            logger.warning("Failed to parse JSON from M2.7 response: %s", cleaned[:200])
            return {}

    def _format_specialist_analyses(self, ctx: PipelineContext) -> str:
        """Format all specialist analyses into a readable block for synthesis."""
        parts: list[str] = []
        for spec in ctx.specialists:
            analysis = ctx.specialist_analyses.get(spec.id)
            if analysis is None:
                continue
            parts.append(
                f"### {spec.name} ({spec.title}, {spec.domain})\n\n"
                f"{json.dumps(analysis, indent=2)}\n"
            )
        return "\n".join(parts)

    def _fallback_paper(self, ctx: PipelineContext) -> str:
        """Dump raw findings as a fallback when paper assembly fails."""
        parts = [f"# Research Findings: {ctx.question}\n"]

        if ctx.synthesis:
            parts.append("## Synthesis\n")
            parts.append(json.dumps(ctx.synthesis, indent=2))
            parts.append("")

        if ctx.moderated_result:
            parts.append("## Moderated Result\n")
            parts.append(json.dumps(ctx.moderated_result, indent=2))
            parts.append("")

        if ctx.specialist_analyses:
            parts.append("## Specialist Analyses\n")
            for spec_id, analysis in ctx.specialist_analyses.items():
                parts.append(f"### {spec_id}\n")
                parts.append(json.dumps(analysis, indent=2))
                parts.append("")

        refs_md = ctx.registry.format_references_list()
        if refs_md:
            parts.append(f"## References\n\n{refs_md}")

        return "\n\n".join(parts)
