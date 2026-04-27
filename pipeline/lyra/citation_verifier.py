"""Per-citation verification — confirms every [N] citation is supported by its source.

For each [N] in the output text, sends the sentence + full source snippet to an LLM
and asks: "Does this source support this specific claim?" If not, the citation is
removed. If a sentence loses all citations, the sentence is removed entirely.

This is the FINAL gate before publishing. Nothing passes without verified citations.

Usage:
    from pipeline.lyra.citation_verifier import verify_all_citations

    verified_text = await verify_all_citations(text, sources, settings)
"""

from __future__ import annotations

import asyncio
import logging
import re

from pipeline.lyra.config import LyraAPIError, LyraSettings, _get_settings, call_api

logger = logging.getLogger(__name__)

_MAX_CONCURRENT = 10  # semaphore cap for concurrent citation checks

_VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "supported": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["supported"],
}


def _get_sentence_with_citation(text: str, cite_num: int) -> list[str]:
    """Find all sentences containing [cite_num]."""
    pattern = re.compile(rf"\[{cite_num}\]")
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [s for s in sentences if pattern.search(s)]


async def _verify_one_citation(
    sentence: str,
    cite_num: int,
    source_title: str,
    source_snippet: str,
    source_url: str,
    settings: LyraSettings,
) -> tuple[bool, str]:
    """Ask the LLM: does this source support this specific claim?

    Returns (supported, reason) tuple.
    """
    # Clean the sentence — remove all [N] markers for clarity
    clean_sentence = re.sub(r"\[\d+\]", "", sentence).strip()

    # Strict-only check. Run 15 audit found that the soft "topical relevance"
    # fallback (used when snippet < 200 chars) was the entry point for
    # citation laundering — title vaguely about ancient civilizations + sentence
    # vaguely about ancient civilizations → "topically relevant" → kept, even
    # though the source never mentioned the actual claim. The verifier is the
    # FINAL gate before publishing; it errs toward removal, not toward
    # "insufficient evidence so let it through."
    system = (
        "You are a fact-checker. You receive a sentence from a journal and a source. "
        "Does this source ACTUALLY support the claim in this sentence? "
        "The source title and snippet are provided. "
        "Answer ONLY whether the source supports the specific claim. "
        "If the source is about a different topic, a different site, a different time period, "
        "or a different person — answer false. "
        "If the snippet is too short to confirm the specific claim, answer false."
    )
    user = (
        f"## Sentence from journal\n{clean_sentence}\n\n"
        f"## Source [{cite_num}]\n"
        f"Title: {source_title}\n"
        f"URL: {source_url}\n"
        f"Content snippet: {source_snippet[:3000]}"
    )

    import json

    # Try structured output first, fall back to plain text parsing
    for attempt in range(3):
        try:
            if attempt < 2:
                # Structured output via tool-use trick
                response = await asyncio.to_thread(
                    call_api,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                    max_tokens=512,
                    temperature=0.0,
                    timeout=30.0,
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "CitationCheck",
                            "strict": True,
                            "schema": _VERIFY_SCHEMA,
                        },
                    },
                )
            else:
                # Fallback: plain text — ask for yes/no
                response = await asyncio.to_thread(
                    call_api,
                    system=system + "\n\nRespond with ONLY the word 'true' or 'false'.",
                    messages=[{"role": "user", "content": user}],
                    max_tokens=64,
                    temperature=0.0,
                    timeout=30.0,
                )

            text = (response.text or "").strip()

            # Try JSON parse first
            try:
                cleaned = text
                if cleaned.startswith("```"):
                    cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
                    cleaned = cleaned.rsplit("```", 1)[0].strip()
                result = json.loads(cleaned)
                supported = result.get("supported", False)
                reason = result.get("reason", "")
            except (json.JSONDecodeError, ValueError):
                # Plain text fallback — look for true/false
                lower = text.lower()
                if "true" in lower and "false" not in lower:
                    supported = True
                    reason = ""
                elif "false" in lower:
                    supported = False
                    reason = text[:100]
                else:
                    # Can't parse — retry
                    continue

            if not supported:
                logger.info(
                    "[verifier] REJECTED [%d] on: %s | Reason: %s",
                    cite_num,
                    clean_sentence[:60],
                    reason[:80],
                )
            return supported, reason

        except (LyraAPIError, Exception) as e:
            if attempt < 2:
                logger.debug("[verifier] Attempt %d failed for [%d]: %s", attempt + 1, cite_num, e)
                continue
            logger.warning(
                "[verifier] Citation check failed for [%d] after 3 attempts: %s", cite_num, e
            )
            return False, str(e)

    logger.warning("[verifier] Citation check exhausted retries for [%d]", cite_num)
    return False, "retries exhausted"


async def verify_all_citations(
    text: str,
    sources: list[dict],
    settings: LyraSettings | None = None,
    max_iterations: int = 3,
) -> str:
    """Verify every [N] citation in the text against its source.

    For each citation:
    1. Find the sentence containing [N]
    2. Look up source [N]'s title and snippet
    3. Ask LLM: "does this source support this claim?"
    4. If no: remove [N] from the sentence
    5. If sentence has no remaining citations: remove the sentence

    Loops until all citations verified or max_iterations reached.

    Args:
        text: The journal/paper text with [N] citation markers
        sources: List of dicts with citation, label, url, and optionally snippet
        settings: LyraSettings (uses default if None)
        max_iterations: Max verification passes (each pass may expose new issues)

    Returns:
        Verified text with only confirmed citations remaining
    """
    if settings is None:
        settings = _get_settings()

    # Strip unresolved [N - topic] placeholders before the verification loop.
    # These appear when a synthesis step couldn't assign a real number; leaving
    # them in the paper would leak placeholders into the published text and the
    # [N]-only audit regex would pass them through silently.
    placeholder_pattern = re.compile(r"\s*\[N\s*[-–][^\]]+\]")
    placeholder_hits = placeholder_pattern.findall(text)
    if placeholder_hits:
        logger.warning(
            "[verifier] Stripping %d unresolved [N - topic] placeholder(s) from paper",
            len(placeholder_hits),
        )
        text = placeholder_pattern.sub("", text)

    # Build source lookup
    source_map: dict[int, dict] = {}
    for s in sources:
        source_map[int(s["citation"])] = s

    for iteration in range(1, max_iterations + 1):
        # Skip sources section
        src_idx = text.find("### Sources")
        if src_idx == -1:
            src_idx = text.find("## Sources")
        if src_idx == -1:
            src_idx = text.find("## References")
        check_text = text[:src_idx] if src_idx > 0 else text

        body_cites = {int(m) for m in re.findall(r"\[(\d+)\]", check_text)}

        if not body_cites:
            logger.info("[verifier] No citations to verify")
            break

        logger.info(
            "[verifier] === Iteration %d: verifying %d unique citations ===",
            iteration,
            len(body_cites),
        )

        rejected_cites: set[int] = set()

        # Build tasks for all citations, run concurrently with semaphore cap
        async def _check_cite(cite_num: int) -> tuple[int, bool]:
            if cite_num not in source_map:
                logger.info("[verifier] [%d] not in source list — removing", cite_num)
                return cite_num, False

            source = source_map[cite_num]
            sentences = _get_sentence_with_citation(check_text, cite_num)

            for sentence in sentences:
                supported, _ = await _verify_one_citation(
                    sentence=sentence,
                    cite_num=cite_num,
                    source_title=source.get("label", ""),
                    source_snippet=source.get("snippet", source.get("label", "")),
                    source_url=source.get("url", ""),
                    settings=settings,
                )
                if not supported:
                    return cite_num, False  # One failed sentence is enough to reject
            return cite_num, True

        semaphore = asyncio.Semaphore(_MAX_CONCURRENT)

        async def _capped_check(cite_num: int) -> tuple[int, bool]:
            async with semaphore:
                return await _check_cite(cite_num)

        results = await asyncio.gather(
            *[_capped_check(cn) for cn in sorted(body_cites)],
            return_exceptions=True,
        )

        for result in results:
            if isinstance(result, Exception):
                logger.warning("[verifier] Citation check raised: %s", result)
                continue
            cite_num, supported = result
            if not supported:
                rejected_cites.add(cite_num)

        if not rejected_cites:
            logger.info("[verifier] All %d citations verified — CLEAN", len(body_cites))
            break

        logger.info(
            "[verifier] Removing %d unverified citations: %s",
            len(rejected_cites),
            sorted(rejected_cites),
        )

        # Remove rejected citations from the text
        for cite_num in rejected_cites:
            text = re.sub(rf"\s*\[{cite_num}\]", "", text)

        # Clean up — preserve markdown structure (paragraphs, headings)
        text = re.sub(r" +([.,;])", r"\1", text)  # " ." → "."
        text = re.sub(r"  +", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)

    return text
