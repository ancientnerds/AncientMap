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
import ipaddress
import json
import logging
import re
import time
import urllib.parse
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from api.services.theo_config import EFFORT_CONFIG, TierConfig
from pipeline.lyra.config import LyraSettings, _get_settings
from pipeline.lyra.minimax_shared import (
    create_minimax_client,
    minimax_chat,
    minimax_chat_anthropic,
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
_SPECIALIST_WORKERS = 5


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

    # Request identity (set by worker, used for image storage path)
    request_id: str = ""

    # User overrides for specialist selection
    force_include: list[str] = field(default_factory=list)
    force_exclude: list[str] = field(default_factory=list)

    # User-provided YouTube video IDs for transcript extraction
    video_ids: list[str] = field(default_factory=list)

    # User-provided web article URLs to include as sources
    web_urls: list[str] = field(default_factory=list)

    # User-disabled source adapters (e.g. ["wikipedia", "minimax"])
    disabled_adapters: list[str] = field(default_factory=list)

    # Track what was already searched/fetched (avoid re-doing work on re-runs)
    searched_queries: set = field(default_factory=set)
    fetched_urls: set = field(default_factory=set)

    # Pipeline iteration tracking
    pipeline_iteration: int = 0

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
    card_description: str = ""
    audit_result: dict = field(default_factory=dict)
    quality_score: dict = field(default_factory=dict)

    # Source images (populated in Stage 3.5, injected in Stage 9.5)
    source_images: list = field(default_factory=list)

    # Tracking
    total_tokens: int = 0
    llm_call_count: int = 0
    pipeline_trace: list[dict] = field(default_factory=list)
    debug_log: list[dict] = field(default_factory=list)
    error: str = ""

    def log(self, stage: str, msg: str, level: str = "info", **data) -> None:
        """Append a structured debug entry."""
        from datetime import datetime, timezone
        self.debug_log.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "stage": stage,
            "level": level,
            "msg": msg,
            "data": data if data else {},
        })


# ---------------------------------------------------------------------------
# SSRF protection
# ---------------------------------------------------------------------------


def _is_safe_url(url: str) -> bool:
    """Block SSRF: reject internal IPs, non-HTTP schemes, metadata endpoints."""
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname or ""
        # Block cloud metadata
        if hostname in ("169.254.169.254", "metadata.google.internal"):
            return False
        # Block localhost
        if hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
            return False
        # Block private IPs
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return False
        except ValueError:
            pass  # hostname is a domain, not an IP — OK
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# The pipeline
# ---------------------------------------------------------------------------


class TheoPipeline:
    """Orchestrates all 8 stages of Theo's research pipeline."""

    def __init__(self, settings: LyraSettings | None = None) -> None:
        self._settings = settings or _get_settings()
        self._model = "MiniMax-M2.7"
        self._searcher = MultiSourceSearch(self._settings)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run(
        self,
        question: str,
        effort: str,
        emit: Callable[[dict], None],
        force_include: list[str] | None = None,
        force_exclude: list[str] | None = None,
        request_id: str = "",
        video_ids: list[str] | None = None,
        web_urls: list[str] | None = None,
        disabled_adapters: list[str] | None = None,
    ) -> PipelineContext:
        """Run the full pipeline.  *emit* sends SSE events to the client."""
        tier = EFFORT_CONFIG.get(effort, EFFORT_CONFIG["article"])

        ctx = PipelineContext(
            question=question,
            effort=effort,
            tier=tier,
            registry=CitationRegistry(),
            request_id=request_id,
            force_include=force_include or [],
            force_exclude=force_exclude or [],
            video_ids=video_ids or [],
            web_urls=web_urls or [],
            disabled_adapters=disabled_adapters or [],
        )

        self._ctx = ctx
        pipeline_start = time.monotonic()

        # Relevancy gate
        rejection = await self._check_relevance(question, emit)
        if rejection:
            ctx.error = rejection
            return ctx

        # Stage 0.5 — YouTube transcripts (runs once)
        if ctx.video_ids:
            try:
                await self._stage_0_transcripts(ctx, emit)
            except Exception as exc:
                logger.warning("Transcript extraction failed (non-fatal): %s", exc)

        # Register user-provided web URLs
        if ctx.web_urls:
            emit(
                {
                    "type": "status",
                    "content": f"Adding {len(ctx.web_urls)} user-provided web source(s)...",
                }
            )
            for url in ctx.web_urls[:10]:
                ctx.registry.register_source(
                    url=url,
                    title=url.split("/")[-1].replace("-", " ").replace("_", " ")[:80] or url[:80],
                    snippet="User-provided source — content will be fetched",
                    search_query="user_provided",
                )

        # Stage 1 — Question analysis (runs ONCE, never re-runs)
        for stage_fn, stage_name in [(self._stage_1_analyze, "question_analysis")]:
            if await self._is_cancelled(ctx, emit):
                return ctx
            try:
                await stage_fn(ctx, emit)
            except Exception as exc:
                logger.exception("Fatal failure in %s", stage_name)
                ctx.error = f"Pipeline failed at {stage_name}: {exc}"
                emit(
                    {
                        "type": "pipeline",
                        "stage": stage_name,
                        "status": "error",
                        "error": str(exc),
                        "meta": {"llm_calls": ctx.llm_call_count},
                    }
                )
                return ctx
            if ctx.error:
                emit(
                    {
                        "type": "pipeline",
                        "stage": stage_name,
                        "status": "error",
                        "error": ctx.error,
                        "meta": {"llm_calls": ctx.llm_call_count},
                    }
                )
                return ctx

        # Track searched queries to avoid re-searching on loop iterations
        ctx.searched_queries = set(ctx.search_queries)

        # ====== MASTER CONVERGENCE LOOP ======
        max_iterations = ctx.tier.max_pipeline_iterations
        restart_stage = 2  # start from search
        best_paper_text = ""
        best_paper_title = ""
        best_audit_result: dict = {}
        best_score = 0

        for iteration in range(max_iterations):
            ctx.pipeline_iteration = iteration + 1
            if await self._is_cancelled(ctx, emit):
                return ctx

            if iteration > 0:
                emit(
                    {
                        "type": "status",
                        "content": f"Pipeline iteration {iteration + 1}/{max_iterations} "
                        f"— re-running from stage {restart_stage}...",
                    }
                )

            # Stage 2: Search
            if restart_stage <= 2:
                if await self._is_cancelled(ctx, emit):
                    return ctx
                try:
                    await self._stage_2_search(ctx, emit)
                except Exception as exc:
                    logger.exception("Fatal failure in web_search")
                    ctx.error = f"Pipeline failed at web_search: {exc}"
                    return ctx
                if ctx.error:
                    return ctx

            # Stage 3: Audit + remove rejected
            if restart_stage <= 3:
                if await self._is_cancelled(ctx, emit):
                    return ctx
                try:
                    await self._stage_3_audit(ctx, emit)
                except Exception as exc:
                    logger.exception("Fatal failure in source_audit")
                    ctx.error = f"Pipeline failed at source_audit: {exc}"
                    return ctx
                if ctx.error:
                    return ctx

            # Stage 3.5: Content fetch
            if restart_stage <= 3:
                try:
                    await self._stage_3_5_fetch_content(ctx, emit)
                except Exception as exc:
                    logger.warning("Content fetch failed (non-fatal): %s", exc)

            # Stage 4: Specialists (fatal if none complete)
            if restart_stage <= 4:
                if await self._is_cancelled(ctx, emit):
                    return ctx
                try:
                    await self._stage_4_specialists(ctx, emit)
                except Exception as exc:
                    logger.exception("Fatal failure in specialist_analysis")
                    ctx.error = f"Pipeline failed at specialist_analysis: {exc}"
                    return ctx
                if not ctx.specialist_analyses:
                    ctx.error = "No specialist analyses completed"
                    return ctx

            # Stage 5: Synthesis
            if restart_stage <= 5:
                if await self._is_cancelled(ctx, emit):
                    return ctx
                try:
                    await self._stage_5_synthesize(ctx, emit)
                except Exception:
                    logger.exception("Non-fatal failure in synthesis")

            # Stage 6: Debate
            if restart_stage <= 6:
                if await self._is_cancelled(ctx, emit):
                    return ctx
                try:
                    await self._stage_6_debate(ctx, emit)
                except Exception:
                    logger.exception("Non-fatal failure in debate")

            # Stage 7: Moderator
            if restart_stage <= 7:
                if await self._is_cancelled(ctx, emit):
                    return ctx
                try:
                    await self._stage_7_moderate(ctx, emit)
                except Exception:
                    logger.exception("Non-fatal failure in moderator")

            # Stage 8: Paper assembly (always runs)
            if await self._is_cancelled(ctx, emit):
                return ctx
            try:
                await self._stage_8_paper(ctx, emit)
            except Exception:
                logger.exception("Paper assembly failed, dumping raw findings")
                ctx.paper_text = self._fallback_paper(ctx)
                ctx.paper_title = "Research Findings (unformatted)"

            # ====== JUDGE ======
            judge_result = await self._judge_paper(ctx, emit)
            ctx.quality_score = {
                "total": judge_result.get("score", 0),
                "badge": judge_result.get("badge", "Unverified"),
                "passed": judge_result.get("passed", False),
                "dimensions": judge_result.get("dimensions", {}),
            }

            # Keep the best paper across iterations (including refs + audit)
            current_score = judge_result.get("score", 0)
            if current_score > best_score or not best_paper_text:
                best_paper_text = ctx.paper_text
                best_paper_title = ctx.paper_title
                best_audit_result = dict(ctx.audit_result)
                best_score = current_score

            if judge_result.get("passed", False):
                emit(
                    {
                        "type": "status",
                        "content": f"Quality judge PASSED: {judge_result['score']}/100 "
                        f"({judge_result['badge']})",
                    }
                )
                break

            # Judge failed — route backward
            problems = judge_result.get("problems", [])
            if not problems or iteration >= max_iterations - 1:
                emit(
                    {
                        "type": "status",
                        "content": f"Quality score {judge_result['score']}/100 "
                        "— max iterations reached, shipping as-is.",
                    }
                )
                break

            # Apply feedback and determine restart stage
            from pipeline.lyra.theo_quality_judge import (
                apply_feedback_to_context,
                get_restart_stage,
            )

            restart_stage = get_restart_stage(problems)
            apply_feedback_to_context(ctx, problems)

            problem_summary = ", ".join(f"{p['type']}" for p in problems[:3])
            emit(
                {
                    "type": "status",
                    "content": f"Quality score {judge_result['score']}/100 — "
                    f"found {len(problems)} problem(s) ({problem_summary}). "
                    f"Re-running from stage {restart_stage}...",
                }
            )

        # Restore best paper if current iteration produced worse results
        if best_paper_text and best_score > ctx.quality_score.get("total", 0):
            logger.info(
                "[THEO] Restoring best paper from earlier iteration (score %d > %d)",
                best_score,
                ctx.quality_score.get("total", 0),
            )
            ctx.paper_text = best_paper_text
            ctx.paper_title = best_paper_title
            ctx.audit_result = best_audit_result

        # ====== PRESENTATION ASSESSOR (runs once after judge passes) ======
        # Same 10-dimension quality assessor used by the journal pipeline.
        # Catches proper noun errors, spelling, citation format, section balance.
        # Skips D4 (screenshots) and D8 (week date) — not applicable to research papers.
        try:
            from pipeline.lyra.journal_assessor import assess_and_fix

            # Build sources list from citation registry
            assess_sources = []
            for sid, num in sorted(ctx.registry.reference_numbers.items(), key=lambda kv: kv[1]):
                source = ctx.registry.get_reference(sid)
                if source:
                    assess_sources.append(
                        {
                            "citation": num,
                            "url": source.url,
                            "label": source.title,
                            "type": "academic" if source.reliability_tier == 1 else "news",
                        }
                    )

            emit({"type": "status", "content": "Running presentation quality assessor..."})
            ctx.paper_text, assess_result = assess_and_fix(
                ctx.paper_text,
                assess_sources,
                week_start=None,  # skip D8 week date check
                settings=self._settings,
                max_iterations=5,
            )
            emit(
                {
                    "type": "status",
                    "content": f"Presentation assessor: {assess_result.score}/10 "
                    f"in {assess_result.iteration} iteration(s), "
                    f"{len(assess_result.fixes_applied)} fix(es) applied.",
                }
            )
        except Exception as exc:
            logger.warning("Presentation assessor failed (non-fatal): %s", exc)

        # ====== PROGRAMMATIC CHECKLIST (runs once after assessor) ======
        try:
            from pipeline.lyra.research_checklist import run_research_checklist

            emit({"type": "status", "content": "Running programmatic quality checklist..."})
            checklist_result = run_research_checklist(ctx.paper_text, ctx.registry, ctx.effort)
            ctx.audit_result["checklist"] = checklist_result.to_dict()
            emit(
                {
                    "type": "status",
                    "content": f"Checklist: {checklist_result.summary}",
                }
            )
        except Exception as exc:
            logger.warning("Research checklist failed (non-fatal): %s", exc)

        # ====== POST-LOOP STAGES (run once) ======
        # Stage 9 — Cover image
        try:
            await self._stage_9_images(ctx, emit)
        except Exception as exc:
            logger.warning("Image generation failed (non-fatal): %s", exc)

        # Stage 9.5 — Source image injection (licensed images only)
        if ctx.source_images:
            try:
                from pipeline.lyra.research_images import inject_source_images

                emit({"type": "pipeline", "stage": "source_image_injection", "status": "start"})
                ctx.paper_text = inject_source_images(
                    ctx.paper_text, ctx.source_images, max_images=4
                )
                emit(
                    {
                        "type": "pipeline",
                        "stage": "source_image_injection",
                        "status": "done",
                        "meta": {"candidates": len(ctx.source_images), "llm_calls": ctx.llm_call_count},
                    }
                )
            except Exception as exc:
                logger.warning("Source image injection failed (non-fatal): %s", exc)

        # Stage 10 — Card description
        try:
            await self._stage_10_card_description(ctx, emit)
        except Exception as exc:
            logger.warning("Card description failed (non-fatal): %s", exc)

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
                    "llm_calls": ctx.llm_call_count,
                },
            }
        )
        return ctx

    # ------------------------------------------------------------------
    # Stage 0.5: YouTube transcript extraction for user-provided videos
    # ------------------------------------------------------------------

    async def _stage_0_transcripts(
        self,
        ctx: PipelineContext,
        emit: Callable[[dict], None],
    ) -> None:
        """Extract transcripts for user-provided YouTube videos.

        Reuses the Lyra news pipeline infrastructure:
        - transcript_fetcher.fetch_transcript() for extraction
        - transcript_fetcher._fetch_metadata_youtube_api() for metadata
        - build_lyra_index._chunk_transcript() pattern for Qdrant indexing
        - Stores in news_videos table (same as news pipeline)
        """
        import re as _re
        import uuid as _uuid

        from sqlalchemy import text as sql_text

        from pipeline.database import get_session

        stage = "transcript_extraction"
        t0 = time.monotonic()
        emit({"type": "pipeline", "stage": stage, "status": "start"})
        emit(
            {
                "type": "status",
                "content": f"Extracting transcripts from {len(ctx.video_ids)} video(s)...",
            }
        )

        extracted = 0
        skipped = 0

        for vid in ctx.video_ids[:5]:
            # Check if already in database
            with get_session() as session:
                exists = session.execute(
                    sql_text(
                        "SELECT 1 FROM news_videos WHERE id = :vid AND status = 'transcribed'"
                    ),
                    {"vid": vid},
                ).fetchone()

            if exists:
                skipped += 1
                emit(
                    {
                        "type": "status",
                        "content": f"[{vid}] Already in database — skipping extraction.",
                    }
                )
                continue

            try:
                from pipeline.lyra.transcript_fetcher import (
                    _fetch_metadata_youtube_api,
                    fetch_transcript,
                )

                # Step 1: Fetch video metadata
                emit({"type": "status", "content": f"[{vid}] Fetching video metadata..."})
                meta = await asyncio.to_thread(
                    _fetch_metadata_youtube_api, vid, self._settings.youtube_api_key
                )
                title = meta.get("title", "") if meta else ""
                description = meta.get("description", "")[:500] if meta else ""
                tags = ", ".join(meta.get("tags", [])[:10]) if meta else ""

                if title:
                    emit({"type": "status", "content": f'[{vid}] Found: "{title[:80]}"'})
                else:
                    emit(
                        {
                            "type": "status",
                            "content": f"[{vid}] Could not fetch metadata — skipping.",
                        }
                    )
                    continue

                # Step 2: Relevancy gate on metadata
                emit(
                    {
                        "type": "status",
                        "content": f"[{vid}] Running relevancy gate on title + description + tags...",
                    }
                )
                relevance_input = f"Title: {title}\nDescription: {description}\nTags: {tags}"
                rejection = await self._check_relevance(relevance_input, lambda _: None)
                if rejection:
                    emit(
                        {
                            "type": "status",
                            "content": f"[{vid}] Rejected — not related to archaeology/history.",
                        }
                    )
                    continue
                emit({"type": "status", "content": f"[{vid}] Relevancy check passed."})

                # Step 3: Extract transcript
                emit(
                    {
                        "type": "status",
                        "content": f"[{vid}] Extracting transcript (this may take 10-30s)...",
                    }
                )
                transcript_text, duration_min = await asyncio.to_thread(
                    fetch_transcript, vid, self._settings
                )

                if not transcript_text:
                    emit(
                        {
                            "type": "status",
                            "content": f"[{vid}] No transcript available (no captions on this video).",
                        }
                    )
                    continue
                emit(
                    {
                        "type": "status",
                        "content": f"[{vid}] Transcript extracted: {duration_min:.0f} min, {len(transcript_text)} chars.",
                    }
                )

                # Step 4: Store in database
                emit({"type": "status", "content": f"[{vid}] Saving to database..."})
                thumbnail = meta.get("thumbnail", "") if meta else ""
                with get_session() as session:
                    session.execute(
                        sql_text("""
                            INSERT INTO news_videos (
                                id, title, description, transcript_text, duration_minutes,
                                thumbnail_url, tags, status, published_at, processed_at
                            ) VALUES (
                                :id, :title, :desc, :transcript, :duration,
                                :thumb, :tags, 'transcribed', NOW(), NOW()
                            ) ON CONFLICT (id) DO UPDATE SET
                                transcript_text = :transcript,
                                status = 'transcribed',
                                processed_at = NOW()
                        """),
                        {
                            "id": vid,
                            "title": title,
                            "desc": description,
                            "transcript": transcript_text,
                            "duration": duration_min,
                            "thumb": thumbnail,
                            "tags": json.dumps(meta.get("tags", []) if meta else []),
                        },
                    )
                    session.commit()

                # Step 5: Index in Qdrant for search
                emit(
                    {
                        "type": "status",
                        "content": f"[{vid}] Indexing transcript chunks in vector database...",
                    }
                )
                await self._index_transcript_chunks(vid, title, transcript_text, "")

                extracted += 1
                emit(
                    {
                        "type": "status",
                        "content": f"[{vid}] Done — {duration_min:.0f} min transcript ready for research.",
                    }
                )

            except Exception as exc:
                logger.warning("Failed to extract transcript for %s: %s", vid, exc)
                emit({"type": "status", "content": f"[{vid}] Error: {exc}"})

        ms = int((time.monotonic() - t0) * 1000)
        emit(
            {
                "type": "pipeline",
                "stage": stage,
                "status": "done",
                "duration_ms": ms,
                "meta": {"extracted": extracted, "skipped": skipped, "llm_calls": ctx.llm_call_count},
            }
        )

    async def _index_transcript_chunks(
        self,
        video_id: str,
        video_title: str,
        transcript_text: str,
        channel: str,
    ) -> None:
        """Chunk a transcript and upsert to the Qdrant transcripts collection.

        Reuses the same chunking pattern and point ID scheme as
        scripts/build_lyra_index.py so chunks are deduplicated correctly.
        """
        import re as _re
        import uuid as _uuid

        from qdrant_client.models import PointStruct

        from api.services.lyra_embeddings import (
            get_embeddings,
            get_qdrant_client,
            get_sparse_model,
        )

        def _parse_ts(ts: str) -> int:
            parts = ts.split(":")
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            return int(parts[0]) * 60 + int(parts[1])

        # Chunk the transcript (inline, same logic as build_lyra_index._chunk_transcript)
        lines = transcript_text.strip().split("\n")
        ts_pat = _re.compile(r"\[(\d+:\d{2}(?::\d{2})?)\]")
        chunks: list[dict] = []
        chunk_idx = 0
        start_line = 0
        chunk_size = 2000
        overlap = 500

        parsed_lines: list[tuple[str, int | None]] = []
        for line in lines:
            m = ts_pat.match(line)
            secs = _parse_ts(m.group(1)) if m else None
            parsed_lines.append((line, secs))

        while start_line < len(parsed_lines):
            current_text = ""
            end_line = start_line
            while end_line < len(parsed_lines):
                candidate = current_text + parsed_lines[end_line][0] + "\n"
                if len(candidate) > chunk_size and end_line > start_line:
                    break
                current_text = candidate
                end_line += 1

            if not current_text.strip():
                start_line = end_line
                continue

            start_secs = None
            end_secs = None
            for i in range(start_line, end_line):
                s = parsed_lines[i][1]
                if s is not None:
                    if start_secs is None:
                        start_secs = s
                    end_secs = s

            chunks.append(
                {
                    "text": current_text.strip(),
                    "start_seconds": start_secs or 0,
                    "end_seconds": end_secs or 0,
                    "chunk_index": chunk_idx,
                }
            )
            chunk_idx += 1

            if end_line >= len(parsed_lines):
                break
            overlap_text = ""
            overlap_start = end_line
            for j in range(end_line - 1, start_line - 1, -1):
                overlap_text = parsed_lines[j][0] + "\n" + overlap_text
                if len(overlap_text) >= overlap:
                    overlap_start = j
                    break
            start_line = overlap_start if overlap_start > start_line else end_line

        if not chunks:
            return

        def _do_index() -> None:
            embedder = get_embeddings("index")
            sparse_model = get_sparse_model()
            client = get_qdrant_client()

            texts = [f"{video_title} | {c['text']}" for c in chunks]
            dense_vecs = embedder.embed_documents(texts)
            sparse_vecs = list(sparse_model.embed(texts))

            points = []
            for i, chunk in enumerate(chunks):
                point_id = str(
                    _uuid.uuid5(
                        _uuid.NAMESPACE_URL, f"transcript-{video_id}-{chunk['chunk_index']}"
                    )
                )
                from qdrant_client.models import SparseVector

                points.append(
                    PointStruct(
                        id=point_id,
                        vector={
                            "dense": dense_vecs[i],
                            "bm25": SparseVector(
                                indices=sparse_vecs[i].indices.tolist(),
                                values=sparse_vecs[i].values.tolist(),
                            ),
                        },
                        payload={
                            "video_id": video_id,
                            "video_title": video_title,
                            "channel": channel,
                            "start_seconds": chunk["start_seconds"],
                            "end_seconds": chunk["end_seconds"],
                            "chunk_index": chunk["chunk_index"],
                            "published_at": "",
                            "text_preview": chunk["text"][:2000],
                            "content_hash": "",
                        },
                    )
                )

            client.upsert(collection_name="transcripts", points=points)
            logger.info("Indexed %d transcript chunks for video %s", len(points), video_id)

        await asyncio.to_thread(_do_index)

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
        emit({"type": "pipeline", "stage": stage, "status": "start", "meta": {"subtask_total": 2}})
        emit({"type": "status", "content": "Analyzing research question...", "subtask_done": 0, "subtask_total": 2})

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
        emit({"type": "status", "content": "Selecting specialist panel...", "subtask_done": 1, "subtask_total": 2})
        ctx.specialists = select_specialists(
            domain_tags=ctx.domain_tags,
            question=ctx.question,
            count=ctx.tier.specialists_count,
            force_include=ctx.force_include or None,
            force_exclude=ctx.force_exclude or None,
        )

        ctx.log("question_analysis", f"Selected {len(ctx.specialists)} specialists", specialists=[s.id for s in ctx.specialists], domain_tags=ctx.domain_tags)

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
                    "specialist_names": [s.name for s in ctx.specialists],
                    "llm_calls": ctx.llm_call_count,
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
        emit({"type": "pipeline", "stage": stage, "status": "start", "meta": {"subtask_total": 1}})

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
        raw_sources = await self._searcher.search(
            queries, source_group, disabled_adapters=ctx.disabled_adapters
        )

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
        academic_count = sum(1 for s in ctx.registry.sources.values() if s.reliability_tier == 1)

        ctx.log("web_search", f"Found {total_results} sources ({academic_count} academic)", queries_run=len(queries), source_group=source_group)

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
                    "sources_found": total_results,
                    "llm_calls": ctx.llm_call_count,
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

        if not ctx.sources_context.strip():
            ctx.error = "No sources available for reliability audit."
            emit({"type": "pipeline", "stage": stage, "status": "start", "meta": {"subtask_total": 0}})
            emit({"type": "pipeline", "stage": stage, "status": "error", "meta": {"llm_calls": ctx.llm_call_count}})
            return

        # 1 source per prompt, 10 parallel — quality over speed.
        # MiniMax Token Plan has no per-second limit (15K req/5hr on Max plan).
        source_items = list(ctx.registry.sources.items())
        max_parallel = 10

        emit({"type": "pipeline", "stage": stage, "status": "start", "meta": {"subtask_total": len(source_items)}})
        emit(
            {
                "type": "status",
                "content": f"Auditing {len(source_items)} sources individually "
                f"({max_parallel} parallel)...",
                "subtask_done": 0,
                "subtask_total": len(source_items),
            }
        )

        system = self._load_prompt("theo_source_audit")
        rejected_ids: set[str] = set()
        total_scored = 0

        async def _audit_one(sid: str, source) -> dict:
            """Audit a single source with full LLM attention."""
            tier_str = ""
            if source.reliability_tier == 1:
                tier_str = " [Academic]"
            elif source.reliability_tier == 2:
                tier_str = " [Reputable]"
            user_msg = (
                f"## Research question\n\n{ctx.question}\n\n"
                f"## Source to evaluate\n\n"
                f"Source [{sid}]: {source.title}{tier_str}\n"
                f"URL: {source.url}\n"
                f"Snippet: {source.snippet}\n"
            )
            raw = await self._m27_call_async(system, user_msg, ctx.tier.max_tokens_per_call)
            parsed = self._parse_json(raw)
            parsed["_sid"] = sid
            return parsed

        # Run in parallel groups of 10
        for group_start in range(0, len(source_items), max_parallel):
            group = source_items[group_start : group_start + max_parallel]

            done_count = group_start + len(group)
            emit(
                {
                    "type": "status",
                    "content": f"Auditing sources {group_start + 1}-{done_count}"
                    f" of {len(source_items)}...",
                    "subtask_done": done_count,
                    "subtask_total": len(source_items),
                }
            )

            results = await asyncio.gather(
                *[_audit_one(sid, source) for sid, source in group],
                return_exceptions=True,
            )

            for result in results:
                if isinstance(result, Exception):
                    logger.warning("Audit source failed: %s", result)
                    continue
                parsed = result
                original_sid = parsed.get("_sid", "")
                for entry in parsed.get("scored_sources", []):
                    sid = entry.get("id", "") or original_sid
                    tier_val = entry.get("reliability_tier", 0)
                    source = ctx.registry.sources.get(sid)
                    if source:
                        source.reliability_tier = tier_val
                        total_scored += 1
                for entry in parsed.get("rejected_sources", []):
                    rid = entry.get("id", "") or original_sid
                    if rid:
                        rejected_ids.add(rid)

        # REMOVE rejected sources — specialists must NEVER see them
        if rejected_ids:
            for rid in rejected_ids:
                ctx.registry.sources.pop(rid, None)
            emit(
                {
                    "type": "status",
                    "content": f"Removed {len(rejected_ids)} rejected sources from pool.",
                }
            )

        # Rebuild sources_context without rejected sources
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

        accepted_count = total_scored - len(rejected_ids)
        ctx.log("source_audit", f"Audited {total_scored} sources: {accepted_count} accepted, {len(rejected_ids)} rejected", accepted=accepted_count, rejected=len(rejected_ids))

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
                    "accepted": accepted_count,
                    "llm_calls": ctx.llm_call_count,
                },
            }
        )

    # ------------------------------------------------------------------
    # Stage 3.5: Fetch actual content from source URLs
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_text_from_html(html: str) -> str:
        """Extract readable text from HTML, strip tags."""
        # Remove script and style tags with their content
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
        # Remove all remaining HTML tags
        text = re.sub(r"<[^>]+>", " ", text)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text

    async def _stage_3_5_fetch_content(
        self,
        ctx: PipelineContext,
        emit: Callable[[dict], None],
    ) -> None:
        """Fetch full page content for Tier 1 and Tier 2 sources.

        Replaces short search snippets with up to 2000 chars of actual page text
        so specialists have real source material instead of 1-3 sentence abstracts.
        Skips doi.org (paywalls), youtube.com (already have transcripts), and
        wikipedia.org (API snippets are already high quality).
        """
        stage = "content_fetch"
        t0 = time.monotonic()

        # Collect sources eligible for content fetch
        _SKIP_DOMAINS = {"doi.org", "youtube.com", "youtu.be", "wikipedia.org"}

        candidates = [
            (sid, source)
            for sid, source in ctx.registry.sources.items()
            if source.reliability_tier in (1, 2)
            and not any(skip in source.url for skip in _SKIP_DOMAINS)
        ]

        if not candidates:
            return

        emit(
            {
                "type": "status",
                "content": f"Fetching content from {len(candidates)} sources...",
            }
        )
        emit({"type": "pipeline", "stage": stage, "status": "start"})

        semaphore = asyncio.Semaphore(10)

        async def _fetch_one(sid: str, url: str) -> tuple[str, str | None]:
            """Fetch URL and return (sid, extracted_text | None)."""
            if not _is_safe_url(url):
                logger.debug("SSRF check blocked URL: %s", url)
                return sid, None
            async with semaphore:
                try:
                    async with httpx.AsyncClient(
                        timeout=15.0,
                        follow_redirects=True,
                        headers={"User-Agent": "Mozilla/5.0 (research bot)"},
                    ) as client:
                        resp = await client.get(url)
                        if resp.status_code == 200:
                            content_type = resp.headers.get("content-type", "")
                            if "html" in content_type or not content_type:
                                text = self._extract_text_from_html(resp.text)
                                return sid, text[:2000] if text else None
                except Exception as exc:
                    logger.debug("Content fetch failed for %s: %s", url, exc)
            return sid, None

        tasks = [_fetch_one(sid, source.url) for sid, source in candidates]
        results = await asyncio.gather(*tasks)

        fetched = 0
        for sid, text in results:
            if text and len(text) > len(ctx.registry.sources[sid].snippet):
                ctx.registry.sources[sid].snippet = text
                fetched += 1

        # Rebuild sources_context with enriched snippets
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

        # Licensed image search — Wikimedia Commons + Met Museum (parallel)
        try:
            from pipeline.lyra.research_images import search_museum_images, search_wikimedia_images

            wiki_imgs, museum_imgs = await asyncio.gather(
                asyncio.to_thread(search_wikimedia_images, ctx.question, ctx.domain_tags[:5]),
                asyncio.to_thread(search_museum_images, ctx.question, ctx.domain_tags[:5]),
            )
            ctx.source_images.extend(wiki_imgs)
            ctx.source_images.extend(museum_imgs)
            if ctx.source_images:
                emit(
                    {
                        "type": "status",
                        "content": f"Found {len(ctx.source_images)} licensed images "
                        f"(Wikimedia: {len(wiki_imgs)}, Met Museum: {len(museum_imgs)})",
                    }
                )
        except Exception as exc:
            logger.warning("Licensed image search failed (non-fatal): %s", exc)

        ms = int((time.monotonic() - t0) * 1000)
        emit(
            {
                "type": "pipeline",
                "stage": stage,
                "status": "done",
                "duration_ms": ms,
                "meta": {"candidates": len(candidates), "fetched": fetched, "llm_calls": ctx.llm_call_count},
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
        emit({"type": "pipeline", "stage": stage, "status": "start", "meta": {"subtask_total": len(ctx.specialists)}})

        loop = asyncio.get_running_loop()
        executor = ThreadPoolExecutor(max_workers=_SPECIALIST_WORKERS)

        def _run_specialist(spec: Specialist) -> tuple[str, str]:
            """Synchronous specialist call, returns (specialist_id, raw_json).

            Uses minimax_chat_anthropic which is thread-safe (each call
            creates its own request via the Anthropic SDK).
            """
            system_prompt, user_prompt = build_specialist_prompt(
                spec,
                ctx.question,
                ctx.sources_context,
            )
            raw = minimax_chat_anthropic(
                system_prompt,
                user_prompt,
                ctx.tier.max_tokens_per_call,
                settings=self._settings,
            )
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

        completed_count = 0
        for result in results:
            if isinstance(result, Exception):
                logger.warning("Specialist call failed: %s", result)
                continue

            spec_id, raw = result
            ctx.llm_call_count += 1  # specialist calls bypass _m27_call
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

            completed_count += 1
            # Find specialist name for enriched status
            spec_name = spec_id
            for s in ctx.specialists:
                if s.id == spec_id:
                    spec_name = s.name
                    break
            emit({
                "type": "status",
                "content": f"Specialist {spec_name} completed analysis.",
                "specialist_name": spec_name,
                "specialist_index": completed_count,
                "specialist_total": len(ctx.specialists),
                "subtask_done": completed_count,
                "subtask_total": len(ctx.specialists),
            })
            ctx.log("specialist_analysis", f"Specialist {spec_name} completed", specialist_id=spec_id, findings=len(parsed.get("findings", [])))

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
                    "specialist_names": {s.id: s.name for s in ctx.specialists},
                    "llm_calls": ctx.llm_call_count,
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
        emit({"type": "pipeline", "stage": stage, "status": "start", "meta": {"subtask_total": 1}})

        if not ctx.specialist_analyses:
            logger.warning("[THEO] Stage 5: No specialist analyses — using empty synthesis")
            ctx.synthesis = {
                "consensus_claims": [],
                "contested_claims": [],
                "unique_insights": [],
                "open_questions": [],
            }
            emit(
                {
                    "type": "pipeline",
                    "stage": stage,
                    "status": "done",
                    "duration_ms": 0,
                    "meta": {"consensus": 0, "contested": 0, "unique": 0, "llm_calls": ctx.llm_call_count},
                }
            )
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

        consensus_count = len(ctx.synthesis.get("consensus_claims", []))
        contested_count = len(ctx.synthesis.get("contested_claims", []))
        unique_count = len(ctx.synthesis.get("unique_insights", []))
        ctx.log("synthesis", f"Synthesized: {consensus_count} consensus, {contested_count} contested, {unique_count} unique", consensus=consensus_count, contested=contested_count, unique=unique_count)

        ms = int((time.monotonic() - t0) * 1000)
        emit(
            {
                "type": "pipeline",
                "stage": stage,
                "status": "done",
                "duration_ms": ms,
                "meta": {
                    "consensus": consensus_count,
                    "contested": contested_count,
                    "unique": unique_count,
                    "llm_calls": ctx.llm_call_count,
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
        emit({"type": "pipeline", "stage": stage, "status": "start", "meta": {"subtask_total": ctx.tier.debate_rounds}})
        emit(
            {
                "type": "status",
                "content": f"Running {ctx.tier.debate_rounds}-round specialist debate...",
                "subtask_done": 0,
                "subtask_total": ctx.tier.debate_rounds,
            }
        )

        challenge_prompt = self._load_prompt("theo_debate_challenge")
        defense_prompt = self._load_prompt("theo_debate_defense")
        synthesis_json = json.dumps(ctx.synthesis, indent=2)

        all_challenges: list[dict] = []
        all_defenses: list[dict] = []

        for rnd in range(1, ctx.tier.debate_rounds + 1):
            emit({"type": "status", "content": f"Debate round {rnd}/{ctx.tier.debate_rounds}...", "round": rnd, "total_rounds": ctx.tier.debate_rounds, "subtask_done": rnd - 1, "subtask_total": ctx.tier.debate_rounds})
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

            ctx.log("debate", f"Round {rnd}: {len(round_challenges)} challenges, defenses collected", round=rnd, challenges=len(round_challenges))

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
                "meta": {"challenges": len(all_challenges), "defenses": len(all_defenses), "llm_calls": ctx.llm_call_count},
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
        emit({"type": "pipeline", "stage": stage, "status": "start", "meta": {"subtask_total": 1}})
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

        final_count = len(moderated.get("final_claims", []))
        revised_count = len(moderated.get("revised_claims", []))
        dropped_count = len(moderated.get("dropped_claims", []))
        ctx.log("moderator", f"Moderated: {final_count} final, {revised_count} revised, {dropped_count} dropped", final_claims=final_count, revised=revised_count, dropped=dropped_count)

        ms = int((time.monotonic() - t0) * 1000)
        emit(
            {
                "type": "pipeline",
                "stage": stage,
                "status": "done",
                "duration_ms": ms,
                "meta": {
                    "final_claims": final_count,
                    "revised": revised_count,
                    "dropped": dropped_count,
                    "llm_calls": ctx.llm_call_count,
                },
            }
        )

    # ------------------------------------------------------------------
    # Stage 8: Paper assembly + citation audit
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Stage 8 helpers: build claims list and ref map
    # ------------------------------------------------------------------

    def _build_claims_and_refs(
        self, ctx: PipelineContext
    ) -> tuple[list[dict], dict[str, int], str]:
        """Extract all claims with [N] citations and build the reference map.

        Returns (claims_list, sid_to_num, ref_map_text).
        """
        # Collect all source_ids mentioned across findings
        all_source_ids: set[str] = set()
        for claim in ctx.registry.claims:
            all_source_ids.update(claim.source_ids)
        for claim_data in ctx.moderated_result.get("final_claims", []):
            all_source_ids.update(claim_data.get("source_ids", []))
        for claim_data in ctx.moderated_result.get("revised_claims", []):
            all_source_ids.update(claim_data.get("source_ids", []))
        for claim_data in ctx.synthesis.get("consensus_claims", []):
            all_source_ids.update(claim_data.get("source_ids", []))
        for insight in ctx.synthesis.get("unique_insights", []):
            all_source_ids.update(insight.get("source_ids", []))

        # Assign reference numbers
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

        # Build numbered claims list with [N] citations
        claims_list: list[dict] = []
        for claim_data in ctx.moderated_result.get("final_claims", []):
            sids = claim_data.get("source_ids", [])
            cites = " ".join(f"[{sid_to_num[s]}]" for s in sids if s in sid_to_num)
            claims_list.append(
                {
                    "claim": claim_data.get("claim", ""),
                    "citations": cites,
                    "confidence": claim_data.get("confidence", "medium"),
                    "notes": claim_data.get("notes", ""),
                    "type": "final",
                }
            )
        for claim_data in ctx.moderated_result.get("revised_claims", []):
            sids = claim_data.get("source_ids", [])
            cites = " ".join(f"[{sid_to_num[s]}]" for s in sids if s in sid_to_num)
            claims_list.append(
                {
                    "claim": claim_data.get("revised", claim_data.get("original", "")),
                    "citations": cites,
                    "confidence": claim_data.get("confidence", "medium"),
                    "notes": claim_data.get("reason", ""),
                    "type": "revised",
                }
            )
        # Fallback: use synthesis claims if no moderated results
        if not claims_list:
            for claim_data in ctx.synthesis.get("consensus_claims", []):
                sids = claim_data.get("source_ids", [])
                cites = " ".join(f"[{sid_to_num[s]}]" for s in sids if s in sid_to_num)
                claims_list.append(
                    {
                        "claim": claim_data.get("claim", ""),
                        "citations": cites,
                        "confidence": claim_data.get("confidence", "medium"),
                        "notes": "",
                        "type": "consensus",
                    }
                )
            for insight in ctx.synthesis.get("unique_insights", []):
                sids = insight.get("source_ids", [])
                cites = " ".join(f"[{sid_to_num[s]}]" for s in sids if s in sid_to_num)
                claims_list.append(
                    {
                        "claim": insight.get("insight", ""),
                        "citations": cites,
                        "confidence": insight.get("confidence", "medium"),
                        "notes": "",
                        "type": "unique",
                    }
                )

        return claims_list, sid_to_num, ref_map_text

    def _format_claims_for_prompt(self, claims: list[dict]) -> str:
        """Format claims as a numbered list for LLM prompts."""
        lines: list[str] = []
        for i, c in enumerate(claims):
            conf = c.get("confidence", "medium")
            cites = c.get("citations", "")
            notes = c.get("notes", "")
            lines.append(
                f"{i}. [{conf}] {c['claim']}\n"
                f"   Sources: {cites}" + (f"\n   Notes: {notes}" if notes else "")
            )
        return "\n\n".join(lines)

    # ------------------------------------------------------------------
    # Stage 8: Paper assembly (sectional for non-brief tiers)
    # ------------------------------------------------------------------

    async def _stage_8_paper(
        self,
        ctx: PipelineContext,
        emit: Callable[[dict], None],
    ) -> None:
        stage = "paper_assembly"
        t0 = time.monotonic()
        # Brief: write + verify = 2 subtasks; sectional: outline + sections + frame + verify = 4
        paper_subtasks = 2 if ctx.effort == "brief" else 4
        emit({"type": "pipeline", "stage": stage, "status": "start", "meta": {"subtask_total": paper_subtasks}})
        emit({"type": "status", "content": "Assembling research paper...", "subtask_done": 0, "subtask_total": paper_subtasks})

        claims_list, sid_to_num, ref_map_text = self._build_claims_and_refs(ctx)

        if ctx.effort == "brief":
            await self._stage_8_brief(ctx, emit, claims_list, sid_to_num, ref_map_text)
        else:
            await self._stage_8_sectional(ctx, emit, claims_list, sid_to_num, ref_map_text)

        # Verify every citation — the FINAL GATE
        from pipeline.lyra.citation_verifier import verify_all_citations

        verify_sources = []
        for sid, num in sorted(sid_to_num.items(), key=lambda kv: kv[1]):
            source = ctx.registry.get_reference(sid)
            if source:
                verify_sources.append(
                    {
                        "citation": num,
                        "label": source.title,
                        "url": source.url,
                        "snippet": source.snippet,
                    }
                )

        # For sectional: step 3 = frame done, now verifying. For brief: step 1 = write done.
        verify_subtask = 3 if ctx.effort != "brief" else 1
        emit({"type": "status", "content": "Verifying every citation against its source...", "subtask_done": verify_subtask, "subtask_total": paper_subtasks})
        ctx.paper_text = verify_all_citations(
            ctx.paper_text, verify_sources, settings=self._settings
        )

        # Extract title from the first # heading
        title_match = re.search(r"^#\s+(.+)$", ctx.paper_text, re.MULTILINE)
        ctx.paper_title = title_match.group(1).strip() if title_match else ctx.question

        # Append references list
        refs_md = ctx.registry.format_references_list()
        if refs_md:
            ctx.paper_text += f"\n\n## References\n\n{refs_md}"

        # Check paper length against tier expectations
        _MIN_WORDS = {
            "brief": 200,
            "note": 500,
            "article": 1200,
            "review": 2000,
            "thesis": 3000,
            "dissertation": 4000,
        }
        word_count = len(ctx.paper_text.split())
        min_words = _MIN_WORDS.get(ctx.effort, 500)
        if word_count < min_words:
            logger.warning(
                "[THEO] Paper too short: %d words (min %d for %s tier)",
                word_count,
                min_words,
                ctx.effort,
            )
            emit(
                {
                    "type": "status",
                    "content": f"Warning: paper is {word_count} words "
                    f"(expected {min_words}+ for {ctx.effort} tier)",
                }
            )

        # Run citation audit
        emit({"type": "status", "content": "Auditing citations..."})
        ctx.audit_result = audit_citations(ctx.paper_text, ctx.registry)

        paper_word_count = len(ctx.paper_text.split())
        ctx.log("paper_assembly", f"Paper assembled: {paper_word_count} words, {ctx.audit_result.get('total_citations', 0)} citations, {ctx.audit_result.get('total_references', 0)} references", word_count=paper_word_count, total_citations=ctx.audit_result.get("total_citations", 0), total_references=ctx.audit_result.get("total_references", 0))

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
                    "word_count": paper_word_count,
                    "llm_calls": ctx.llm_call_count,
                },
            }
        )

    async def _stage_8_brief(
        self,
        ctx: PipelineContext,
        emit: Callable[[dict], None],
        claims_list: list[dict],
        sid_to_num: dict[str, int],
        ref_map_text: str,
    ) -> None:
        """Single-shot paper assembly for brief tier."""
        paper_system = self._load_prompt("theo_paper_brief")
        readable = (
            self._format_moderated_readable(
                self._replace_source_ids_in(ctx.moderated_result, sid_to_num)
            )
            if ctx.moderated_result
            else self._format_claims_for_prompt(claims_list)
        )

        paper_input = (
            f"## Research question\n\n{ctx.question}\n\n"
            f"## Reference map\n\n{ref_map_text}\n\n"
            f"## Findings\n\n{readable}\n\n"
        )

        raw_paper = await self._m27_call_async(
            paper_system, paper_input, ctx.tier.max_tokens_synthesis
        )
        raw_paper = re.sub(r"\[\d+\]", "", raw_paper)
        raw_paper = self._insert_citations_mechanically(raw_paper, ctx, sid_to_num)
        ctx.paper_text = raw_paper

    async def _stage_8_sectional(
        self,
        ctx: PipelineContext,
        emit: Callable[[dict], None],
        claims_list: list[dict],
        sid_to_num: dict[str, int],
        ref_map_text: str,
    ) -> None:
        """Multi-step paper assembly: outline → sections → frame → assemble."""
        claims_text = self._format_claims_for_prompt(claims_list)
        logger.info("[THEO] Sectional writing with %d claims", len(claims_list))

        # Step 1: Generate outline
        emit({"type": "status", "content": "Planning paper structure...", "subtask_done": 0, "subtask_total": 4})
        outline_system = self._load_prompt("theo_paper_outline")
        outline_input = (
            f"## Research question\n\n{ctx.question}\n\n"
            f"## Claims ({len(claims_list)} total)\n\n{claims_text}\n\n"
        )
        raw_outline = await self._m27_call_async(outline_system, outline_input, 4096)
        outline = self._parse_json(raw_outline)

        title = outline.get("title", ctx.question[:60])
        sections = outline.get("sections", [])

        if not sections:
            sections = [
                {
                    "heading": "Findings",
                    "purpose": "All findings",
                    "claim_indices": list(range(len(claims_list))),
                }
            ]

        logger.info(
            "[THEO] Paper outline: %s — %d sections: %s",
            title,
            len(sections),
            [s.get("heading", "?") for s in sections],
        )

        # Step 2: Write each body section in parallel
        emit(
            {
                "type": "status",
                "content": f"Writing {len(sections)} paper sections...",
                "subtask_done": 1,
                "subtask_total": 4,
            }
        )
        section_system = self._load_prompt("theo_paper_section")

        async def _write_section(sec: dict) -> tuple[str, str]:
            heading = sec.get("heading", "Untitled")
            purpose = sec.get("purpose", "")
            indices = sec.get("claim_indices", [])

            sec_claims = []
            for idx in indices:
                if 0 <= idx < len(claims_list):
                    sec_claims.append(claims_list[idx])

            if not sec_claims:
                logger.warning(
                    "[THEO] Section '%s' has no valid claims (indices: %s)", heading, indices
                )
                return heading, ""

            sec_claims_text = self._format_claims_for_prompt(sec_claims)
            sec_input = (
                f"## Section: {heading}\n"
                f"Purpose: {purpose}\n\n"
                f"## Claims for this section\n\n{sec_claims_text}\n\n"
                f"## Reference map\n\n{ref_map_text}\n\n"
            )

            raw = await self._m27_call_async(
                section_system, sec_input, ctx.tier.max_tokens_per_call
            )
            logger.info("[THEO] Section '%s': %d chars", heading, len(raw))
            return heading, raw.strip()

        section_tasks = [_write_section(sec) for sec in sections]
        section_results = await asyncio.gather(*section_tasks)

        # Step 3: Assemble body sections
        body_parts: list[str] = []
        for heading, content in section_results:
            if content:
                body_parts.append(f"## {heading}\n\n{content}")

        body_text = "\n\n".join(body_parts)

        logger.info(
            "[THEO] Body assembled: %d chars across %d sections", len(body_text), len(body_parts)
        )

        # Step 4: Write framing sections (Abstract, Introduction, Discussion, Conclusion)
        emit({"type": "status", "content": "Writing introduction and conclusion...", "subtask_done": 2, "subtask_total": 4})
        frame_system = self._load_prompt("theo_paper_frame")
        frame_input = (
            f"## Research question\n\n{ctx.question}\n\n## Paper body sections\n\n{body_text}\n\n"
        )
        raw_frame = await self._m27_call_async(
            frame_system, frame_input, ctx.tier.max_tokens_synthesis
        )

        # Step 5: Parse framing sections
        frame_sections: dict[str, str] = {}
        current_key = ""
        current_lines: list[str] = []
        for line in raw_frame.split("\n"):
            heading_match = re.match(r"^##\s+(.+)$", line)
            if heading_match:
                if current_key:
                    frame_sections[current_key] = "\n".join(current_lines).strip()
                current_key = heading_match.group(1).strip()
                current_lines = []
            else:
                current_lines.append(line)
        if current_key:
            frame_sections[current_key] = "\n".join(current_lines).strip()

        logger.info("[THEO] Frame sections parsed: %s", list(frame_sections.keys()))

        # Guard: if frame parsing got nothing, use raw text as abstract
        if not frame_sections:
            logger.warning("[THEO] Frame parsing found no ## headings — using raw text as abstract")
            frame_sections["Abstract"] = raw_frame.strip()[:2000]

        # Step 6: Source Assessment — the "reality check"
        emit({"type": "status", "content": "Writing source assessment..."})
        assessment_system = self._load_prompt("theo_source_assessment")

        # Build source tier summary for the assessment
        tier_counts = {"Academic": 0, "Reputable": 0, "General": 0}
        source_lines: list[str] = []
        for sid, num in sorted(ctx.registry.reference_numbers.items(), key=lambda kv: kv[1]):
            source = ctx.registry.get_reference(sid)
            if source:
                tier_label = (
                    "Academic"
                    if source.reliability_tier == 1
                    else "Reputable"
                    if source.reliability_tier == 2
                    else "General"
                )
                tier_counts[tier_label] += 1
                source_lines.append(f"[{num}] {source.title} — {source.url} [{tier_label}]")

        tier_summary = ", ".join(f"{v} {k}" for k, v in tier_counts.items() if v > 0)
        sources_text = "\n".join(source_lines) if source_lines else "(no sources)"

        assessment_input = (
            f"## Research question\n\n{ctx.question}\n\n"
            f"## Paper body\n\n{body_text[:8000]}\n\n"
            f"## Sources ({tier_summary})\n\n{sources_text}\n\n"
            f"## Effort tier: {ctx.effort}\n"
        )

        raw_assessment = await self._m27_call_async(
            assessment_system, assessment_input, ctx.tier.max_tokens_per_call
        )
        source_assessment = raw_assessment.strip()
        logger.info("[THEO] Source Assessment: %d chars", len(source_assessment))
        ctx.log("source_assessment", f"Source assessment: {len(source_assessment)} chars, {tier_summary}", tier_summary=tier_summary)

        # Step 7: Assemble final paper
        paper_parts = [f"# {title}\n"]

        for key in ["Abstract", "Introduction"]:
            if key in frame_sections and frame_sections[key]:
                paper_parts.append(f"## {key}\n\n{frame_sections[key]}")

        paper_parts.append(body_text)

        if source_assessment:
            paper_parts.append(f"## Source Assessment\n\n{source_assessment}")

        for key in ["Conclusion", "Methodology"]:
            if key in frame_sections and frame_sections[key]:
                paper_parts.append(f"## {key}\n\n{frame_sections[key]}")

        # Thesis/dissertation: append debate summary
        if ctx.effort in ("thesis", "dissertation") and ctx.debate_result:
            debate_summary = self._format_debate_summary(ctx.debate_result)
            if debate_summary:
                paper_parts.append(f"## Appendix: Specialist Debate Summary\n\n{debate_summary}")

        raw_paper = "\n\n".join(paper_parts)

        # Clean up LLM artifacts
        raw_paper = re.sub(r"\s*---\s*$", "", raw_paper, flags=re.MULTILINE)
        raw_paper = re.sub(r"^\s*---\s*$", "", raw_paper, flags=re.MULTILINE)
        # Ensure ## headings are on their own line with a blank line before them
        raw_paper = re.sub(r"([^\n])\s*(## )", r"\1\n\n\2", raw_paper)

        # Strip LLM-placed citations, re-insert mechanically
        raw_paper = re.sub(r"\[\d+\]", "", raw_paper)
        raw_paper = self._insert_citations_mechanically(raw_paper, ctx, sid_to_num)
        # Clean up orphaned punctuation from stripped citations (" ." → ".")
        raw_paper = re.sub(r" +([.,;])", r"\1", raw_paper)
        raw_paper = re.sub(r"  +", " ", raw_paper)
        ctx.paper_text = raw_paper

        logger.info(
            "[THEO] Sectional paper complete: %d chars, %d body sections",
            len(raw_paper),
            len(body_parts),
        )

    def _replace_source_ids_in(self, obj: dict | list, sid_to_num: dict[str, int]) -> dict | list:
        """Recursively replace source_ids lists with [N] citation strings."""
        if isinstance(obj, dict):
            result = {}
            for k, v in obj.items():
                if k == "source_ids" and isinstance(v, list):
                    result["citations"] = " ".join(
                        f"[{sid_to_num[sid]}]" for sid in v if sid in sid_to_num
                    )
                else:
                    result[k] = self._replace_source_ids_in(v, sid_to_num)
            return result
        elif isinstance(obj, list):
            return [self._replace_source_ids_in(item, sid_to_num) for item in obj]
        return obj

    def _format_debate_summary(self, debate_result: dict) -> str:
        """Format debate results as bullet points for the appendix."""
        parts: list[str] = []
        for challenge in debate_result.get("challenges", []):
            claim = challenge.get("claim", "")
            attack = challenge.get("attack", "")
            defense = challenge.get("defense", "")
            outcome = challenge.get("outcome", "")
            parts.append(
                f"- **Challenge**: {claim}\n"
                f"  - Attack: {attack}\n"
                f"  - Defense: {defense}\n"
                f"  - Outcome: {outcome}"
            )
        return "\n\n".join(parts) if parts else ""

    # ------------------------------------------------------------------
    # Quality judge (called inside the master convergence loop)
    # ------------------------------------------------------------------

    async def _judge_paper(
        self,
        ctx: PipelineContext,
        emit: Callable[[dict], None],
    ) -> dict:
        """Run the quality judge on the assembled paper. Returns routing decisions."""
        emit({"type": "pipeline", "stage": "quality_judge", "status": "start", "meta": {"subtask_total": 1}})
        emit({"type": "status", "content": "Running quality judge..."})
        t0 = time.monotonic()

        from pipeline.lyra.theo_quality_judge import judge_paper

        # Build source snippets for the judge
        source_snippets = []
        for sid, num in sorted(ctx.registry.reference_numbers.items(), key=lambda kv: kv[1]):
            source = ctx.registry.get_reference(sid)
            if source:
                source_snippets.append(
                    {
                        "ref_num": num,
                        "title": source.title,
                        "snippet": source.snippet,
                    }
                )

        def _chat(model, system, user, max_tokens):
            return minimax_chat_anthropic(system, user, max_tokens, settings=self._settings)

        result = judge_paper(
            ctx.paper_text,
            ctx.question,
            ctx.audit_result,
            source_snippets,
            _chat,
            self._model,
        )

        ctx.llm_call_count += 1  # judge_paper calls minimax_chat_anthropic directly

        judge_score = result.get("score", 0)
        judge_badge = result.get("badge", "")
        judge_passed = result.get("passed", False)
        judge_dimensions = result.get("dimensions", {})
        ctx.log("quality_judge", f"Score {judge_score}/100 ({judge_badge}), passed={judge_passed}", score=judge_score, badge=judge_badge, passed=judge_passed, dimensions=judge_dimensions)

        ms = int((time.monotonic() - t0) * 1000)
        emit(
            {
                "type": "pipeline",
                "stage": "quality_judge",
                "status": "done",
                "duration_ms": ms,
                "meta": {
                    "score": judge_score,
                    "badge": judge_badge,
                    "passed": judge_passed,
                    "problems": len(result.get("problems", [])),
                    "llm_calls": ctx.llm_call_count,
                },
            }
        )
        return result

    # ------------------------------------------------------------------
    # Stage 9: Illustration generation (post paper assembly)
    # ------------------------------------------------------------------

    async def _stage_9_images(
        self,
        ctx: PipelineContext,
        emit: Callable[[dict], None],
    ) -> None:
        """Generate a cover image for the paper using MiniMax image-01."""
        if not ctx.paper_text:
            return

        stage = "image_generation"
        t0 = time.monotonic()
        emit({"type": "pipeline", "stage": stage, "status": "start", "meta": {"subtask_total": 1}})

        from pipeline.lyra.theo_images import generate_cover_image, insert_cover_image

        paper_id = ctx.request_id or "unknown"
        cover_url = await generate_cover_image(paper_id, ctx.paper_text, emit)

        if cover_url:
            ctx.paper_text = insert_cover_image(ctx.paper_text, cover_url)

        ms = int((time.monotonic() - t0) * 1000)
        emit(
            {
                "type": "pipeline",
                "stage": stage,
                "status": "done",
                "duration_ms": ms,
                "meta": {"cover_image": bool(cover_url), "llm_calls": ctx.llm_call_count},
            }
        )

    # ------------------------------------------------------------------
    # Stage 10: Card description (1-3 sentence summary for library cards)
    # ------------------------------------------------------------------

    async def _stage_10_card_description(
        self,
        ctx: PipelineContext,
        emit: Callable[[dict], None],
    ) -> None:
        """Generate a 1-3 sentence card description for the public library."""
        if not ctx.paper_text or not ctx.paper_title:
            return

        emit({"type": "status", "content": "Writing card description..."})

        system = (
            "Write a 1-3 sentence description of this research paper for a card preview. "
            "Be specific about what was investigated and what was found. "
            "Write in third person. No citations, no markdown. Plain text only."
        )
        # Send just the title + abstract (first 1000 chars) to keep it fast
        abstract = ctx.paper_text[:1000]
        user_msg = f"Title: {ctx.paper_title}\n\n{abstract}"

        raw = await self._m27_call_async(system, user_msg, 256)
        ctx.card_description = raw.strip().strip('"')

    # ------------------------------------------------------------------
    # Cancellation check — polled between stages
    # ------------------------------------------------------------------

    async def _is_cancelled(
        self,
        ctx: PipelineContext,
        emit: Callable[[dict], None],
    ) -> bool:
        """Check if the research request was cancelled by the user.

        Queries the DB for the current status. If cancelled, sets ctx.error
        and emits a done event. Returns True if cancelled.
        """
        if not ctx.request_id:
            return False

        from sqlalchemy import text as sql_text

        from pipeline.database import get_session

        def _check() -> bool:
            with get_session() as session:
                row = session.execute(
                    sql_text("SELECT status FROM research_requests WHERE id = :id"),
                    {"id": ctx.request_id},
                ).fetchone()
                return row is not None and row.status == "cancelled"

        cancelled = await asyncio.to_thread(_check)
        if cancelled:
            ctx.error = "Research cancelled by user"
            emit({"type": "done", "status": "cancelled"})
            logger.info("[THEO] Request %s cancelled by user", ctx.request_id)
        return cancelled

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
    # Mechanical citation insertion
    # ==================================================================

    def _insert_citations_mechanically(
        self,
        paper_text: str,
        ctx: PipelineContext,
        sid_to_num: dict[str, int],
    ) -> str:
        """Insert [N] citations mechanically by matching sentences to claims.

        The LLM writes prose WITHOUT citations. This method matches each
        sentence to synthesis/moderated claims via keyword overlap, then
        appends the correct [N] markers. Guarantees every citation traces
        back to the claim it was assigned to.
        """
        # Build claim → citations mapping from all available findings
        claim_citations: list[tuple[str, str]] = []

        # From moderated results (thesis/review tiers)
        for claim_data in ctx.moderated_result.get("final_claims", []):
            claim_text = claim_data.get("claim", "")
            source_ids = claim_data.get("source_ids", [])
            nums = " ".join(f"[{sid_to_num[sid]}]" for sid in source_ids if sid in sid_to_num)
            if claim_text and nums:
                claim_citations.append((claim_text, nums))
        for claim_data in ctx.moderated_result.get("revised_claims", []):
            claim_text = claim_data.get("claim", "")
            source_ids = claim_data.get("source_ids", [])
            nums = " ".join(f"[{sid_to_num[sid]}]" for sid in source_ids if sid in sid_to_num)
            if claim_text and nums:
                claim_citations.append((claim_text, nums))

        # From synthesis (note/article tiers without moderation)
        for claim_data in ctx.synthesis.get("consensus_claims", []):
            claim_text = claim_data.get("claim", "")
            source_ids = claim_data.get("source_ids", [])
            nums = " ".join(f"[{sid_to_num[sid]}]" for sid in source_ids if sid in sid_to_num)
            if claim_text and nums:
                claim_citations.append((claim_text, nums))
        for claim_data in ctx.synthesis.get("contested_claims", []):
            claim_text = claim_data.get("claim", "")
            source_ids = claim_data.get("source_ids", [])
            nums = " ".join(f"[{sid_to_num[sid]}]" for sid in source_ids if sid in sid_to_num)
            if claim_text and nums:
                claim_citations.append((claim_text, nums))
        for claim_data in ctx.synthesis.get("unique_insights", []):
            claim_text = claim_data.get("claim", claim_data.get("insight", ""))
            source_ids = claim_data.get("source_ids", [])
            nums = " ".join(f"[{sid_to_num[sid]}]" for sid in source_ids if sid in sid_to_num)
            if claim_text and nums:
                claim_citations.append((claim_text, nums))

        # From specialist claims
        for claim in ctx.registry.claims:
            claim_text = claim.claim_text
            nums = " ".join(f"[{sid_to_num[sid]}]" for sid in claim.source_ids if sid in sid_to_num)
            if claim_text and nums:
                claim_citations.append((claim_text, nums))

        if not claim_citations:
            logger.warning("[theo] No claims found for mechanical citation insertion")
            return paper_text

        # Stop words for matching
        stop = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "of",
            "in",
            "to",
            "and",
            "that",
            "this",
            "for",
            "with",
            "from",
            "has",
            "have",
            "had",
            "been",
            "not",
            "but",
            "its",
            "also",
            "by",
            "on",
            "as",
            "at",
            "or",
        }

        # Match each sentence to claims and insert citations
        sentences = re.split(r"(?<=[.!?])\s+", paper_text)
        cited_sentences = []
        citations_inserted = 0

        for sentence in sentences:
            # Skip headings, short lines, abstract markers
            if sentence.startswith("#") or len(sentence) < 30:
                cited_sentences.append(sentence)
                continue

            sent_words = set(sentence.lower().split()) - stop
            best_nums = ""
            best_overlap = 0.0

            for claim_text, nums in claim_citations:
                claim_words = set(claim_text.lower().split()) - stop
                if not claim_words:
                    continue
                overlap = len(claim_words & sent_words) / len(claim_words)
                if overlap > best_overlap and overlap >= 0.3:
                    best_overlap = overlap
                    best_nums = nums

            if best_nums:
                cited_sentences.append(f"{sentence.rstrip('.')} {best_nums}.")
                citations_inserted += 1
            else:
                cited_sentences.append(sentence)

        logger.info(
            "[theo] Mechanical citation: inserted %d citations across %d sentences",
            citations_inserted,
            len(sentences),
        )
        return " ".join(cited_sentences)

    # ==================================================================
    # Helpers
    # ==================================================================

    def _m27_call(self, system: str, user_message: str, max_tokens: int) -> str:
        """Synchronous M2.7 call via Anthropic SDK (unified path)."""
        if hasattr(self, '_ctx') and self._ctx:
            self._ctx.llm_call_count += 1
        return minimax_chat_anthropic(
            system,
            user_message,
            max_tokens,
            settings=self._settings,
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

    @staticmethod
    def _format_moderated_readable(moderated: dict) -> str:
        """Convert moderated findings JSON into human-readable text.

        Makes it easier for the paper writer to understand the claims
        without parsing nested JSON, reducing misinterpretation.
        """
        parts: list[str] = []

        for claim in moderated.get("final_claims", []):
            citations = claim.get("citations", "")
            conf = claim.get("confidence", "medium")
            parts.append(
                f"FINAL CLAIM ({conf} confidence): {claim.get('claim', '')}\n"
                f"  Sources: {citations}\n"
                f"  Notes: {claim.get('notes', '')}\n"
            )

        for claim in moderated.get("revised_claims", []):
            citations = claim.get("citations", "")
            parts.append(
                f"REVISED CLAIM: {claim.get('revised', claim.get('original', ''))}\n"
                f"  Original: {claim.get('original', '')}\n"
                f"  Reason for revision: {claim.get('reason', '')}\n"
                f"  Sources: {citations}\n"
            )

        for claim in moderated.get("dropped_claims", []):
            parts.append(
                f"DROPPED (do NOT include): {claim.get('claim', '')}\n"
                f"  Reason: {claim.get('reason', '')}\n"
            )

        if not parts:
            return json.dumps(moderated, indent=2)

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
