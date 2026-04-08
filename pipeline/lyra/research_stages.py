"""Synchronous research functions for the weekly journal pipeline.

Wraps Theo pipeline components (search, audit, specialist analysis,
synthesis, quality judge) into a simple sync interface that
``article_generator.py`` calls per research cluster.

Usage:
    from pipeline.lyra.research_stages import research_cluster, ClusterResult

    result = research_cluster(
        question="What is known about the 13,500-year-old settlement at Sahout?",
        youtube_facts=[...],
        settings=settings,
    )
    if result.passed:
        use(result.prose, result.sources)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from pipeline.lyra.config import LyraSettings, _get_settings
from pipeline.lyra.minimax_shared import minimax_chat_anthropic
from pipeline.lyra.theo_citations import CitationRegistry, audit_citations
from pipeline.lyra.theo_quality_judge import get_restart_stage, judge_paper
from pipeline.lyra.theo_sources import MultiSourceSearch
from pipeline.lyra.theo_specialists import build_specialist_prompt, select_specialists

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"

# ---------------------------------------------------------------------------
# Journal-tier config (based on "note" tier, with reduced retries)
# ---------------------------------------------------------------------------
_SPECIALISTS_COUNT = 3
_MAX_SEARCH_QUERIES = 8
_MAX_TOKENS_PER_CALL = 16384
_MAX_TOKENS_SYNTHESIS = 16384
_SOURCE_APIS = "standard"
_MAX_PIPELINE_ITERATIONS = 2
_MAX_PARALLEL_AUDIT = 10
_QUALITY_PASS_THRESHOLD = 72


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------


@dataclass
class ClusterResult:
    """Result of researching a single question cluster."""

    prose: str
    sources: list[dict]
    score: int
    passed: bool
    error: str = ""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_prompt(name: str) -> str:
    """Load a prompt file from pipeline/lyra/prompts/."""
    path = PROMPTS_DIR / f"{name}.txt"
    return path.read_text(encoding="utf-8")


def _parse_json(text: str) -> dict | list:
    """Parse JSON from M2.7 response, handling markdown fencing."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        cleaned = cleaned.rsplit("```", 1)[0].strip()
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        logger.warning("Failed to parse JSON from M2.7 response: %s", cleaned[:200])
        return {}


def _classify_source_type(url: str) -> str:
    """Classify a URL into a source type label."""
    domain = url.lower()
    if "youtube.com" in domain or "youtu.be" in domain:
        return "youtube"
    if "wikipedia.org" in domain:
        return "wiki"
    if any(
        d in domain
        for d in (
            "semanticscholar.org",
            "doi.org",
            "jstor.org",
            "arxiv.org",
            "springer.com",
            "elsevier.com",
            "cambridge.org",
            "oxford",
            "wiley.com",
            "researchgate.net",
            "academia.edu",
            "core.ac.uk",
            "openalex.org",
            ".edu",
            ".ac.uk",
        )
    ):
        return "academic"
    return "news"


def _build_sources_context(registry: CitationRegistry) -> str:
    """Format all registry sources into a text block for prompts."""
    lines: list[str] = []
    for sid, source in registry.sources.items():
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
    return "\n".join(lines)


def _build_source_list(registry: CitationRegistry) -> list[dict]:
    """Build the unified sources list for ClusterResult."""
    result: list[dict] = []
    for sid, num in sorted(registry.reference_numbers.items(), key=lambda kv: kv[1]):
        source = registry.get_reference(sid)
        if source is None:
            continue
        result.append(
            {
                "citation": num,
                "url": source.url,
                "label": source.title,
                "type": _classify_source_type(source.url),
            }
        )
    return result


# ---------------------------------------------------------------------------
# Stage implementations
# ---------------------------------------------------------------------------


def _stage_search(
    queries: list[str],
    registry: CitationRegistry,
    settings: LyraSettings,
) -> str:
    """Stage 2: Multi-source search. Returns sources_context string."""
    t0 = time.monotonic()
    logger.info("[journal] Search: running %d queries across %s", len(queries), _SOURCE_APIS)

    searcher = MultiSourceSearch(settings)
    raw_sources = asyncio.run(searcher.search(queries[:_MAX_SEARCH_QUERIES], _SOURCE_APIS))

    if not raw_sources:
        logger.warning("[journal] Search returned zero results")
        return ""

    for r in raw_sources:
        sid = registry.register_source(
            url=r.url,
            title=r.title,
            snippet=r.snippet,
            date=r.date,
        )
        source = registry.get_reference(sid)
        if source and source.reliability_tier == 0:
            source.reliability_tier = r.default_tier

    ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "[journal] Search done in %dms: %d unique sources (%d academic)",
        ms,
        len(registry.sources),
        sum(1 for s in registry.sources.values() if s.reliability_tier == 1),
    )
    return _build_sources_context(registry)


def _stage_audit(
    question: str,
    registry: CitationRegistry,
    settings: LyraSettings,
) -> str:
    """Stage 3: Source reliability audit. Returns updated sources_context."""
    t0 = time.monotonic()
    source_items = list(registry.sources.items())
    if not source_items:
        return ""

    logger.info("[journal] Audit: evaluating %d sources", len(source_items))

    system = _load_prompt("theo_source_audit")
    rejected_ids: set[str] = set()
    total_scored = 0

    def _audit_one(sid: str, source) -> dict | list:
        tier_str = ""
        if source.reliability_tier == 1:
            tier_str = " [Academic]"
        elif source.reliability_tier == 2:
            tier_str = " [Reputable]"
        user_msg = (
            f"## Research question\n\n{question}\n\n"
            f"## Source to evaluate\n\n"
            f"Source [{sid}]: {source.title}{tier_str}\n"
            f"URL: {source.url}\n"
            f"Snippet: {source.snippet}\n"
        )
        raw = minimax_chat_anthropic(system, user_msg, _MAX_TOKENS_PER_CALL, settings=settings)
        parsed = _parse_json(raw)
        if isinstance(parsed, dict):
            parsed["_sid"] = sid
        return parsed

    # Run audits in parallel batches
    with ThreadPoolExecutor(max_workers=_MAX_PARALLEL_AUDIT) as pool:
        futures = {pool.submit(_audit_one, sid, source): sid for sid, source in source_items}
        for future in futures:
            try:
                parsed = future.result(timeout=120)
            except Exception as exc:
                logger.warning("[journal] Audit call failed for %s: %s", futures[future], exc)
                continue
            if not isinstance(parsed, dict):
                continue
            original_sid = parsed.get("_sid", "")
            for entry in parsed.get("scored_sources", []):
                sid = entry.get("id", "") or original_sid
                tier_val = entry.get("reliability_tier", 0)
                source = registry.sources.get(sid)
                if source:
                    source.reliability_tier = tier_val
                    total_scored += 1
            for entry in parsed.get("rejected_sources", []):
                rid = entry.get("id", "") or original_sid
                if rid:
                    rejected_ids.add(rid)

    # Remove rejected sources
    for rid in rejected_ids:
        registry.sources.pop(rid, None)

    ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "[journal] Audit done in %dms: %d scored, %d rejected, %d remaining",
        ms,
        total_scored,
        len(rejected_ids),
        len(registry.sources),
    )
    return _build_sources_context(registry)


def _stage_specialists(
    question: str,
    sources_context: str,
    registry: CitationRegistry,
    settings: LyraSettings,
) -> dict[str, dict]:
    """Stage 4: Parallel specialist analysis. Returns {specialist_id: analysis_dict}."""
    t0 = time.monotonic()

    # Use the question itself as a domain hint — select_specialists extracts
    # keywords from the question text.
    specialists = select_specialists(
        domain_tags=[],
        question=question,
        count=_SPECIALISTS_COUNT,
    )
    logger.info(
        "[journal] Specialists: selected %s",
        [s.id for s in specialists],
    )

    analyses: dict[str, dict] = {}

    def _run_one(spec):
        system_prompt, user_prompt = build_specialist_prompt(spec, question, sources_context)
        raw = minimax_chat_anthropic(
            system_prompt, user_prompt, _MAX_TOKENS_PER_CALL, settings=settings
        )
        return spec.id, raw

    with ThreadPoolExecutor(max_workers=_SPECIALISTS_COUNT) as pool:
        futures = [pool.submit(_run_one, spec) for spec in specialists]
        for future in futures:
            try:
                spec_id, raw = future.result(timeout=180)
            except Exception as exc:
                logger.warning("[journal] Specialist call failed: %s", exc)
                continue
            parsed = _parse_json(raw)
            if not isinstance(parsed, dict) or not parsed:
                logger.warning("[journal] Specialist %s returned unparseable output", spec_id)
                continue
            analyses[spec_id] = parsed

            # Register claims
            for finding in parsed.get("findings", []):
                registry.add_claim(
                    claim_text=finding.get("claim", ""),
                    source_ids=finding.get("source_ids", []),
                    specialist_id=spec_id,
                    confidence=finding.get("confidence", "medium"),
                )

    ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "[journal] Specialists done in %dms: %d/%d completed",
        ms,
        len(analyses),
        len(specialists),
    )
    return analyses


def _stage_synthesis(
    question: str,
    specialist_analyses: dict[str, dict],
    settings: LyraSettings,
) -> dict:
    """Stage 5: Cross-source synthesis. Returns synthesis dict."""
    t0 = time.monotonic()
    logger.info("[journal] Synthesis: combining %d specialist analyses", len(specialist_analyses))

    system = _load_prompt("theo_synthesis")

    # Format analyses
    parts: list[str] = []
    for spec_id, analysis in specialist_analyses.items():
        parts.append(f"### Specialist: {spec_id}\n\n{json.dumps(analysis, indent=2)}\n")
    analyses_text = "\n".join(parts)

    user_msg = f"## Research question\n\n{question}\n\n## Specialist analyses\n\n{analyses_text}"
    raw = minimax_chat_anthropic(system, user_msg, _MAX_TOKENS_SYNTHESIS, settings=settings)
    result = _parse_json(raw)
    if not isinstance(result, dict):
        result = {}

    ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "[journal] Synthesis done in %dms: %d consensus, %d contested, %d unique",
        ms,
        len(result.get("consensus_claims", [])),
        len(result.get("contested_claims", [])),
        len(result.get("unique_insights", [])),
    )
    return result


def _stage_write_section(
    question: str,
    synthesis: dict,
    registry: CitationRegistry,
    settings: LyraSettings,
) -> str:
    """Write journal section prose, then mechanically insert citations.

    Two-step process to guarantee citation accuracy:
    1. LLM writes prose WITHOUT any [N] markers (pure content)
    2. Python matches each sentence to synthesis claims and inserts
       the correct [N] citations mechanically

    This prevents the LLM from placing wrong citation numbers.
    """
    t0 = time.monotonic()
    logger.info("[journal] Writing section prose (two-step)...")

    # Assign reference numbers to all cited source_ids from synthesis
    all_source_ids: set[str] = set()
    for claim in synthesis.get("consensus_claims", []):
        all_source_ids.update(claim.get("source_ids", []))
    for insight in synthesis.get("unique_insights", []):
        all_source_ids.update(insight.get("source_ids", []))
    for claim in registry.claims:
        all_source_ids.update(claim.source_ids)

    sid_to_num: dict[str, int] = {}
    for sid in sorted(all_source_ids):
        source = registry.get_reference(sid)
        if source is None:
            continue
        num = registry.assign_reference_number(sid)
        sid_to_num[sid] = num

    # Build claim-to-citations mapping for mechanical insertion
    # Each claim has text + the [N] numbers that support it
    claim_citations: list[tuple[str, str]] = []  # (claim_text, "[N] [M]")
    for claim_data in synthesis.get("consensus_claims", []):
        claim_text = claim_data.get("claim", "")
        source_ids = claim_data.get("source_ids", [])
        nums = " ".join(f"[{sid_to_num[sid]}]" for sid in source_ids if sid in sid_to_num)
        if claim_text and nums:
            claim_citations.append((claim_text, nums))
    for claim_data in synthesis.get("contested_claims", []):
        claim_text = claim_data.get("claim", "")
        source_ids = claim_data.get("source_ids", [])
        nums = " ".join(f"[{sid_to_num[sid]}]" for sid in source_ids if sid in sid_to_num)
        if claim_text and nums:
            claim_citations.append((claim_text, nums))
    for claim_data in synthesis.get("unique_insights", []):
        claim_text = claim_data.get("claim", claim_data.get("insight", ""))
        source_ids = claim_data.get("source_ids", [])
        nums = " ".join(f"[{sid_to_num[sid]}]" for sid in source_ids if sid in sid_to_num)
        if claim_text and nums:
            claim_citations.append((claim_text, nums))

    # Step 1: LLM writes prose WITHOUT citations
    system = _load_prompt("journal_section")
    # Give the LLM the synthesis findings (without source_ids — just the claims)
    findings_text = []
    for claim_text, _nums in claim_citations:
        findings_text.append(f"- {claim_text}")
    user_msg = f"## Research question\n\n{question}\n\n## Key findings to cover\n\n" + "\n".join(
        findings_text
    )

    prose = minimax_chat_anthropic(system, user_msg, _MAX_TOKENS_SYNTHESIS, settings=settings)

    # Strip any [N] markers the LLM might have added despite instructions
    prose = re.sub(r"\[\d+\]", "", prose)

    # Step 2: Mechanically insert citations by matching sentences to claims
    sentences = re.split(r"(?<=[.!?])\s+", prose)
    cited_sentences = []

    for sentence in sentences:
        sent_lower = sentence.lower()
        sent_words = set(sent_lower.split())

        # Find the best matching claim for this sentence
        best_match_nums = ""
        best_overlap = 0

        for claim_text, nums in claim_citations:
            claim_words = set(claim_text.lower().split())
            # Remove stop words for matching
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
            }
            claim_content = claim_words - stop
            sent_content = sent_words - stop

            if not claim_content:
                continue

            overlap = len(claim_content & sent_content)
            overlap_ratio = overlap / len(claim_content)

            if overlap_ratio > best_overlap and overlap_ratio >= 0.3:
                best_overlap = overlap_ratio
                best_match_nums = nums

        if best_match_nums:
            # Insert citation at end of sentence (before period)
            cited_sentences.append(f"{sentence.rstrip('.')} {best_match_nums}.")
        else:
            cited_sentences.append(sentence)

    prose = " ".join(cited_sentences)

    ms = int((time.monotonic() - t0) * 1000)
    cited_count = len(re.findall(r"\[\d+\]", prose))
    logger.info(
        "[journal] Section written in %dms (%d chars, %d citations inserted mechanically)",
        ms,
        len(prose),
        cited_count,
    )
    return prose


def _strip_unsupported_claims(prose: str, problems: list[dict]) -> str:
    """Remove sentences containing claims the judge identified as unsupported.

    Each problem has a 'claim' field with the text of the unsupported claim.
    We find the sentence in the prose that contains this claim and remove it entirely.
    An unsupported claim must not exist in the output — not even without a citation.
    """
    for problem in problems:
        claim = problem.get("claim", "")
        if not claim or len(claim) < 10:
            continue

        # Find sentences in prose that contain the claim text (or a close match)
        sentences = re.split(r"(?<=[.!?])\s+", prose)
        claim_lower = claim.lower()

        kept = []
        removed = 0
        for sentence in sentences:
            # Check if this sentence contains the unsupported claim
            if claim_lower in sentence.lower():
                removed += 1
                logger.info("[journal] Stripped unsupported claim: %s", sentence[:80])
            else:
                # Also check for partial match (claim may be paraphrased)
                # Use word overlap — if >60% of claim words appear in sentence, strip it
                claim_words = set(claim_lower.split())
                sent_words = set(sentence.lower().split())
                if claim_words and len(claim_words & sent_words) / len(claim_words) > 0.6:
                    removed += 1
                    logger.info("[journal] Stripped paraphrased claim: %s", sentence[:80])
                else:
                    kept.append(sentence)

        if removed > 0:
            prose = " ".join(kept)

    # Clean up double spaces and orphaned citations
    prose = re.sub(r"  +", " ", prose)
    prose = re.sub(r"\n\n\n+", "\n\n", prose)
    return prose.strip()


def _stage_judge(
    prose: str,
    question: str,
    registry: CitationRegistry,
    settings: LyraSettings,
) -> dict:
    """Run the quality judge on the written section."""
    t0 = time.monotonic()

    # Append references for the citation audit
    refs_md = registry.format_references_list()
    full_text = prose
    if refs_md:
        full_text += f"\n\n## References\n\n{refs_md}"

    audit_result = audit_citations(full_text, registry)

    # Build source snippets for the judge
    source_snippets = []
    for sid, num in sorted(registry.reference_numbers.items(), key=lambda kv: kv[1]):
        source = registry.get_reference(sid)
        if source:
            source_snippets.append(
                {
                    "ref_num": num,
                    "title": source.title,
                    "snippet": source.snippet,
                }
            )

    def _chat(_model, system, user, max_tokens):
        return minimax_chat_anthropic(system, user, max_tokens, settings=settings)

    result = judge_paper(
        paper_text=full_text,
        question=question,
        audit_result=audit_result,
        source_snippets=source_snippets,
        chat_fn=_chat,
        model="MiniMax-M2.7",
    )

    ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "[journal] Quality judge in %dms: score=%d passed=%s badge=%s",
        ms,
        result.get("score", 0),
        result.get("passed", False),
        result.get("badge", ""),
    )
    return result


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def research_cluster(
    question: str,
    youtube_facts: list[dict],
    settings: LyraSettings | None = None,
) -> ClusterResult:
    """Run a single research question through all stages.

    Stages: search -> audit -> specialists -> synthesis -> write -> judge.
    Retries from the failing stage on quality judge failure (max 2 iterations).

    Args:
        question: Research question (e.g., "What is known about the
            13,500-year-old settlement at Sahout?")
        youtube_facts: Pre-existing facts from YouTube. Each dict has keys:
            title, url, snippet, facts, video_id, timestamp_seconds, channel_name.
        settings: LyraSettings instance (uses default if None).

    Returns:
        ClusterResult with prose, sources, score, passed, and error fields.
    """
    if settings is None:
        settings = _get_settings()

    t0 = time.monotonic()
    logger.info("[journal] === research_cluster START: %s ===", question[:80])

    registry = CitationRegistry()

    # Register YouTube facts as pre-existing Tier 2 sources
    for fact in youtube_facts:
        url = fact.get("url", "")
        if not url:
            vid = fact.get("video_id", "")
            ts = fact.get("timestamp_seconds", 0)
            url = f"https://youtu.be/{vid}?t={ts}" if vid else ""
        if not url:
            continue
        sid = registry.register_source(
            url=url,
            title=fact.get("title", "YouTube"),
            snippet=fact.get("snippet", ""),
        )
        source = registry.get_reference(sid)
        if source:
            source.reliability_tier = 2

    # Build initial search queries from the question
    search_queries = [question]
    # Add a few variant queries for broader coverage
    # Strip question marks and split long questions
    clean_q = question.rstrip("?").strip()
    if len(clean_q.split()) > 8:
        # Take key noun phrases as a shorter query
        words = clean_q.split()
        search_queries.append(" ".join(words[:6]))
        search_queries.append(" ".join(words[-6:]))

    # ---- Stage 2: Search ----
    sources_context = _stage_search(search_queries, registry, settings)
    if not sources_context and not registry.sources:
        total_ms = int((time.monotonic() - t0) * 1000)
        logger.warning("[journal] No sources found, aborting cluster (%dms)", total_ms)
        return ClusterResult(
            prose="",
            sources=[],
            score=0,
            passed=False,
            error="No sources found for this research question.",
        )

    # ---- Stage 3: Audit ----
    sources_context = _stage_audit(question, registry, settings)
    if not registry.sources:
        # All sources rejected
        total_ms = int((time.monotonic() - t0) * 1000)
        logger.warning("[journal] All sources rejected by audit (%dms)", total_ms)
        return ClusterResult(
            prose="",
            sources=[],
            score=0,
            passed=False,
            error="All sources were rejected during reliability audit.",
        )

    # ---- MASTER CONVERGENCE LOOP ----
    best_prose = ""
    best_score = 0
    best_passed = False
    specialist_analyses: dict[str, dict] = {}
    synthesis: dict = {}

    for iteration in range(_MAX_PIPELINE_ITERATIONS):
        if iteration > 0:
            logger.info(
                "[journal] Retry iteration %d/%d",
                iteration + 1,
                _MAX_PIPELINE_ITERATIONS,
            )

        # ---- Stage 4: Specialists ----
        specialist_analyses = _stage_specialists(question, sources_context, registry, settings)
        if not specialist_analyses:
            total_ms = int((time.monotonic() - t0) * 1000)
            logger.warning("[journal] No specialist analyses completed (%dms)", total_ms)
            return ClusterResult(
                prose=best_prose,
                sources=_build_source_list(registry),
                score=best_score,
                passed=False,
                error="All specialist analyses failed.",
            )

        # ---- Stage 5: Synthesis ----
        synthesis = _stage_synthesis(question, specialist_analyses, settings)

        # ---- Write section ----
        prose = _stage_write_section(question, synthesis, registry, settings)
        if not prose:
            logger.warning("[journal] Section writing returned empty prose")
            continue

        # ---- Quality judge ----
        judge_result = _stage_judge(prose, question, registry, settings)
        score = judge_result.get("score", 0)
        passed = judge_result.get("passed", False)

        # Strip claims the judge identified as unsupported BEFORE tracking
        problems = judge_result.get("problems", [])
        critical = [
            p
            for p in problems
            if p.get("type") in ("source_fidelity_failure", "attribution_failure")
            and p.get("action") == "strip_claim"
        ]
        if critical:
            prose = _strip_unsupported_claims(prose, critical)
            logger.info("[journal] Stripped %d unsupported claims from prose", len(critical))

        # Track best attempt
        if score > best_score:
            best_prose = prose
            best_score = score
            best_passed = passed

        if passed:
            logger.info("[journal] Quality judge PASSED on iteration %d", iteration + 1)
            break

        # Judge failed — check if we should retry
        if iteration >= _MAX_PIPELINE_ITERATIONS - 1:
            logger.info(
                "[journal] Max iterations reached (score=%d), shipping best attempt",
                best_score,
            )
            break

        if not problems:
            logger.info("[journal] Judge failed but no actionable problems, shipping as-is")
            break

        restart_stage = get_restart_stage(problems)
        problem_types = [p.get("type", "unknown") for p in problems[:3]]
        logger.info(
            "[journal] Judge failed (score=%d), problems: %s, restarting from stage %d",
            score,
            problem_types,
            restart_stage,
        )

    total_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "[journal] === research_cluster DONE in %dms: score=%d passed=%s ===",
        total_ms,
        best_score,
        best_passed,
    )

    return ClusterResult(
        prose=best_prose,
        sources=_build_source_list(registry),
        score=best_score,
        passed=best_passed,
    )
