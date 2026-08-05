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
from pipeline.lyra.minimax_shared import MINIMAX_MODEL, minimax_chat_anthropic
from pipeline.lyra.theo_citations import CitationRegistry, audit_citations
from pipeline.lyra.theo_quality_judge import get_restart_stage, judge_paper
from pipeline.lyra.theo_sources import MultiSourceSearch
from pipeline.lyra.theo_specialists import build_specialist_prompt, select_specialists

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"

# ---------------------------------------------------------------------------
# Journal-tier config (compact pipeline for weekly journal articles)
# ---------------------------------------------------------------------------
_SPECIALISTS_COUNT = 3
_MAX_SEARCH_QUERIES = 8
# Quality-max (tokens free): M3 adaptive thinking shares the output budget, so
# provision generously above the desired prose length (M3 ceiling is 512k). Was
# 16384/16384; synthesis raised highest since the narrative paper is the longest
# output and reasoning consumes the majority of tokens before prose is emitted.
_MAX_TOKENS_PER_CALL = 32768
_MAX_TOKENS_SYNTHESIS = 49152
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
    sources: list[dict]  # web/academic sources with [N] citations
    video_sources: list[dict]  # YouTube sources with [VN] citations
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
    """Parse JSON from M3 response, handling markdown fencing."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        cleaned = cleaned.rsplit("```", 1)[0].strip()
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        logger.warning("Failed to parse JSON from M3 response: %s", cleaned[:200])
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
            f"Source #{sid}: {source.title}{tier_str}\n"
            f"URL: {source.url}\n"
            f"Snippet: {source.snippet}\n"
        )
    return "\n".join(lines)


def _build_source_list(registry: CitationRegistry) -> list[dict]:
    """Build the web/academic sources list for ClusterResult (excludes YouTube)."""
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
                "snippet": source.snippet or source.title,
                "type": _classify_source_type(source.url),
            }
        )
    return result


def _build_video_source_list(registry: CitationRegistry) -> list[dict]:
    """Build the YouTube video sources list for ClusterResult."""
    yt_domains = ("youtu.be/", "youtube.com/")
    result: list[dict] = []
    num = 0
    for sid in sorted(registry.sources.keys()):
        source = registry.get_reference(sid)
        if source is None:
            continue
        if not (source.url and any(d in source.url for d in yt_domains)):
            continue
        num += 1
        result.append(
            {
                "v_citation": num,
                "url": source.url,
                "label": source.title,
                "snippet": source.snippet or source.title,
                "type": "youtube",
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
        # No reliability_tier==0 backfill here (Follow-up-Ticket 1, removed
        # 2026-08-05): register_source always assigns a real tier at
        # registration (score_tier_by_domain never returns 0; self_source
        # forces 4), so that guard was dead since inception.
        registry.register_source(
            url=r.url,
            title=r.title,
            snippet=r.snippet,
            date=r.date,
            doi=r.doi,
            authors=r.authors,
            venue=r.venue,
            citation_count=r.citation_count,
            self_source=r.self_source,
        )

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
    protected_sids: set[str] | None = None,
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
            f"Source #{sid}: {source.title}{tier_str}\n"
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
                # self_source's tier 4 is authoritative (theo_citations.py
                # register_source forces it) — the audit prompt only scores
                # tiers 1-3 (_audit_one's tier_str never shows "[self]"), so
                # an unconditional overwrite would clobber it back down to a
                # plain external tier (Follow-up-Ticket 5).
                if source and not source.self_source:
                    source.reliability_tier = tier_val
                    total_scored += 1
            for entry in parsed.get("rejected_sources", []):
                rid = entry.get("id", "") or original_sid
                if rid:
                    rejected_ids.add(rid)

    # Remove rejected sources — protect YouTube, pre-verified story sources,
    # and self-source (own prior papers) records. self_source is provenance
    # metadata the audit prompt never sees (it only shows [Academic]/
    # [Reputable] tier hints, never a self-source marker) — an LLM "reject"
    # verdict on our own paper is a false positive from missing context, not
    # a real quality signal (Follow-up-Ticket 10, same guard style as the
    # YouTube/story protection above).
    yt_domains = ("youtu.be/", "youtube.com/")
    _protected_sids = protected_sids or set()
    protected = 0
    for rid in rejected_ids:
        source = registry.sources.get(rid)
        is_youtube = source and source.url and any(d in source.url for d in yt_domains)
        is_story_source = rid in _protected_sids
        is_self_source = bool(source and source.self_source)
        if is_youtube or is_story_source or is_self_source:
            protected += 1
            continue
        registry.sources.pop(rid, None)
    if protected:
        logger.info(
            "[journal] Protected %d source(s) from rejection (YouTube + story + self)", protected
        )

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
        # Retry up to 2 times on unparseable JSON
        for attempt in range(3):
            raw = minimax_chat_anthropic(
                system_prompt, user_prompt, _MAX_TOKENS_PER_CALL, settings=settings
            )
            parsed = _parse_json(raw)
            if isinstance(parsed, dict) and parsed:
                return spec.id, parsed
            if attempt < 2:
                logger.info(
                    "[journal] Specialist %s returned unparseable output, retrying (%d/3)",
                    spec.id,
                    attempt + 1,
                )
        logger.warning("[journal] Specialist %s failed after 3 attempts", spec.id)
        return spec.id, {}

    with ThreadPoolExecutor(max_workers=_SPECIALISTS_COUNT) as pool:
        futures = [pool.submit(_run_one, spec) for spec in specialists]
        for future in futures:
            try:
                spec_id, parsed = future.result(timeout=300)
            except Exception as exc:
                logger.warning("[journal] Specialist call failed: %s", exc)
                continue
            if not isinstance(parsed, dict) or not parsed:
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
    """Write journal section prose with inline [N] citations.

    Gives the LLM numbered findings + a source key so it places [N]
    citations naturally in prose.  The downstream citation verifier
    (verify_all_citations) catches any wrong attributions.
    """
    t0 = time.monotonic()
    logger.info("[journal] Writing section prose with inline citations...")

    # Assign reference numbers: [N] for web sources, [VN] for YouTube
    all_source_ids: set[str] = set()
    for claim in synthesis.get("consensus_claims", []):
        all_source_ids.update(claim.get("source_ids", []))
    for insight in synthesis.get("unique_insights", []):
        all_source_ids.update(insight.get("source_ids", []))
    for claim in registry.claims:
        all_source_ids.update(claim.source_ids)

    # Also include YouTube sources so they get [VN] markers
    yt_domains = ("youtu.be/", "youtube.com/")
    for sid, source in registry.sources.items():
        if source.url and any(d in source.url for d in yt_domains):
            all_source_ids.add(sid)

    # Split into web and YouTube, assign numbers separately
    sid_to_label: dict[str, str] = {}  # sid -> "[N]" or "[VN]"
    web_num = 0
    yt_num = 0
    for sid in sorted(all_source_ids):
        source = registry.get_reference(sid)
        if source is None:
            continue
        is_yt = source.url and any(d in source.url for d in yt_domains)
        if is_yt:
            yt_num += 1
            sid_to_label[sid] = f"[V{yt_num}]"
        else:
            web_num += 1
            registry.assign_reference_number(sid)
            sid_to_label[sid] = f"[{web_num}]"

    # Build findings with citation markers attached
    findings_lines: list[str] = []
    for claim_data in synthesis.get("consensus_claims", []):
        claim_text = claim_data.get("claim", "")
        source_ids = claim_data.get("source_ids", [])
        markers = " ".join(sid_to_label[sid] for sid in source_ids if sid in sid_to_label)
        if claim_text and markers:
            findings_lines.append(f"- {claim_text} {markers}")
    for claim_data in synthesis.get("contested_claims", []):
        claim_text = claim_data.get("claim", "")
        source_ids = claim_data.get("source_ids", [])
        markers = " ".join(sid_to_label[sid] for sid in source_ids if sid in sid_to_label)
        if claim_text and markers:
            findings_lines.append(f"- CONTESTED: {claim_text} {markers}")
    for claim_data in synthesis.get("unique_insights", []):
        claim_text = claim_data.get("claim", claim_data.get("insight", ""))
        source_ids = claim_data.get("source_ids", [])
        markers = " ".join(sid_to_label[sid] for sid in source_ids if sid in sid_to_label)
        if claim_text and markers:
            findings_lines.append(f"- {claim_text} {markers}")

    # Build source key — web [N] and YouTube [VN] clearly separated
    source_key_lines: list[str] = []
    source_key_lines.append("Web/academic sources:")
    for sid, label in sorted(sid_to_label.items(), key=lambda kv: kv[1]):
        source = registry.get_reference(sid)
        if source and not label.startswith("[V"):
            source_key_lines.append(f"{label} {source.title}")
    source_key_lines.append("")
    source_key_lines.append("YouTube videos:")
    for sid, label in sorted(sid_to_label.items(), key=lambda kv: kv[1]):
        source = registry.get_reference(sid)
        if source and label.startswith("[V"):
            source_key_lines.append(f"{label} {source.title}")

    system = _load_prompt("journal_section")
    user_msg = (
        f"## Research question\n\n{question}\n\n"
        f"## Key findings (use the [N] and [VN] markers shown when citing)\n\n"
        + "\n".join(findings_lines)
        + "\n\n## Source key\n\n"
        + "\n".join(source_key_lines)
    )

    # Retry up to 2 times on empty prose
    prose = ""
    for _write_attempt in range(3):
        prose = minimax_chat_anthropic(system, user_msg, _MAX_TOKENS_SYNTHESIS, settings=settings)
        if prose.strip():
            break
        logger.info("[journal] Write returned empty, retrying (%d/3)", _write_attempt + 1)

    # Strip invalid markers — keep only valid [N] and [VN]
    valid_web = {str(i) for i in range(1, web_num + 1)}
    valid_yt = {f"V{i}" for i in range(1, yt_num + 1)}

    def _filter_citation(m: re.Match) -> str:
        ref = m.group(1)
        return m.group() if ref in valid_web or ref in valid_yt else ""

    prose = re.sub(r"\[(V?\d+)\]", _filter_citation, prose)

    ms = int((time.monotonic() - t0) * 1000)
    cited_count = len(re.findall(r"\[\d+\]", prose))
    logger.info(
        "[journal] Section written in %dms (%d chars, %d inline citations)",
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

    Preserves paragraph structure by processing each paragraph independently.
    """
    claims_lower = []
    for problem in problems:
        claim = problem.get("claim", "")
        if claim and len(claim) >= 10:
            claims_lower.append(claim.lower())

    if not claims_lower:
        return prose

    # Process per-paragraph to preserve structure
    paragraphs = prose.split("\n\n")
    result_paragraphs: list[str] = []

    for para in paragraphs:
        sentences = re.split(r"(?<=[.!?])\s+", para)
        kept = []
        for sentence in sentences:
            sent_lower = sentence.lower()
            # Only strip on exact substring match — no fuzzy overlap
            if any(claim in sent_lower for claim in claims_lower):
                logger.info("[journal] Stripped unsupported claim: %s", sentence[:80])
            else:
                kept.append(sentence)

        if kept:
            result_paragraphs.append(" ".join(kept))

    prose = "\n\n".join(result_paragraphs)
    prose = re.sub(r"  +", " ", prose)
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
        model=MINIMAX_MODEL,
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
    *,
    web_sources: list[dict] | None = None,
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
        web_sources: Pre-verified web sources from the story's tweet verifier.
            Each dict has keys: title, url, snippet.

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

    # Register pre-verified web sources from the story (tweet verifier / Lyra agent)
    # Track their SIDs so the audit stage won't reject them
    story_source_sids: set[str] = set()
    if web_sources:
        for ws in web_sources:
            url = ws.get("url", "")
            if not url:
                continue
            sid = registry.register_source(
                url=url,
                title=ws.get("title", ""),
                snippet=ws.get("snippet", ""),
            )
            story_source_sids.add(sid)
            # No reliability_tier==0 backfill here (Follow-up-Ticket 1,
            # removed 2026-08-05) — same dead pattern as _stage_search
            # above; register_source never leaves a source at tier 0.
        logger.info(
            "[journal] Pre-registered %d web sources from story",
            len(story_source_sids),
        )

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
            video_sources=[],
            score=0,
            passed=False,
            error="No sources found for this research question.",
        )

    # ---- Stage 3: Audit ----
    sources_context = _stage_audit(question, registry, settings, protected_sids=story_source_sids)
    if not registry.sources:
        # All sources rejected
        total_ms = int((time.monotonic() - t0) * 1000)
        logger.warning("[journal] All sources rejected by audit (%dms)", total_ms)
        return ClusterResult(
            prose="",
            sources=[],
            video_sources=[],
            score=0,
            passed=False,
            error="All sources were rejected during reliability audit.",
        )

    # ---- MASTER CONVERGENCE LOOP ----
    best_prose = ""
    best_score = 0
    best_passed = False
    restart_stage = 4  # start from specialists on first iteration
    specialist_analyses: dict[str, dict] = {}
    synthesis: dict = {}

    for iteration in range(_MAX_PIPELINE_ITERATIONS):
        if iteration > 0:
            logger.info(
                "[journal] Retry iteration %d/%d",
                iteration + 1,
                _MAX_PIPELINE_ITERATIONS,
            )

        # ---- Stage 4: Specialists (skip if restart_stage > 4) ----
        if iteration == 0 or restart_stage <= 4:
            specialist_analyses = _stage_specialists(question, sources_context, registry, settings)
            if not specialist_analyses:
                total_ms = int((time.monotonic() - t0) * 1000)
                logger.warning("[journal] No specialist analyses completed (%dms)", total_ms)
                return ClusterResult(
                    prose=best_prose,
                    sources=_build_source_list(registry),
                    video_sources=_build_video_source_list(registry),
                    score=best_score,
                    passed=False,
                    error="All specialist analyses failed.",
                )

        # ---- Stage 5: Synthesis (skip if restart_stage > 5) ----
        if iteration == 0 or restart_stage <= 5:
            synthesis = _stage_synthesis(question, specialist_analyses, settings)

        # Guard: empty synthesis means the LLM call failed silently
        has_findings = (
            synthesis.get("consensus_claims")
            or synthesis.get("contested_claims")
            or synthesis.get("unique_insights")
        )
        if not has_findings:
            logger.warning("[journal] Synthesis produced no findings, skipping write")
            continue

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
        video_sources=_build_video_source_list(registry),
        score=best_score,
        passed=best_passed,
    )
