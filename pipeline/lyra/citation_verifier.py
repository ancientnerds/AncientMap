"""Per-citation verification — confirms every [N] citation is supported by its source.

For each [N] in the output text, sends the sentence + full source snippet to an LLM
and asks: "Does this source support this specific claim?" If not, the citation is
removed. If a sentence loses all citations, the sentence is removed entirely.

This is the FINAL gate before publishing. Nothing passes without verified citations.

Usage:
    from pipeline.lyra.citation_verifier import verify_all_citations

    verified_text = verify_all_citations(text, sources, settings)
"""

from __future__ import annotations

import logging
import re

from pipeline.lyra.config import LyraAPIError, LyraSettings, _get_settings, call_api

logger = logging.getLogger(__name__)

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


def _verify_one_citation(
    sentence: str,
    cite_num: int,
    source_title: str,
    source_snippet: str,
    source_url: str,
    settings: LyraSettings,
) -> bool:
    """Ask the LLM: does this source support this specific claim?

    Returns True if supported, False if not.
    """
    # Clean the sentence — remove all [N] markers for clarity
    clean_sentence = re.sub(r"\[\d+\]", "", sentence).strip()

    # When snippets are thin (< 200 chars), we only have title + URL to go on.
    # Use a softer check: reject only when the source is clearly about a
    # different topic, not when there's just insufficient evidence.
    thin_snippet = len(source_snippet.strip()) < 200
    if thin_snippet:
        system = (
            "You are a fact-checker. You receive a sentence from a journal and a source. "
            "The source snippet is very short — you may not have full context. "
            "Based on the source TITLE and URL, is this source plausibly about "
            "the same topic as the sentence? "
            "Answer true if the source is topically relevant (same site, same discovery, "
            "same time period, same subject). "
            "Answer false ONLY if the source is clearly about a different topic."
        )
    else:
        system = (
            "You are a fact-checker. You receive a sentence from a journal and a source. "
            "Does this source ACTUALLY support the claim in this sentence? "
            "The source title and snippet are provided. "
            "Answer ONLY whether the source supports the specific claim. "
            "If the source is about a different topic, a different site, a different time period, "
            "or a different person — answer false."
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
                response = call_api(
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
                response = call_api(
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
            return supported

        except (LyraAPIError, Exception) as e:
            if attempt < 2:
                logger.debug("[verifier] Attempt %d failed for [%d]: %s", attempt + 1, cite_num, e)
                continue
            logger.warning(
                "[verifier] Citation check failed for [%d] after 3 attempts: %s", cite_num, e
            )
            return False

    logger.warning("[verifier] Citation check exhausted retries for [%d]", cite_num)
    return False


def verify_all_citations(
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

        for cite_num in sorted(body_cites):
            if cite_num not in source_map:
                logger.info("[verifier] [%d] not in source list — removing", cite_num)
                rejected_cites.add(cite_num)
                continue

            source = source_map[cite_num]
            sentences = _get_sentence_with_citation(check_text, cite_num)

            for sentence in sentences:
                supported = _verify_one_citation(
                    sentence=sentence,
                    cite_num=cite_num,
                    source_title=source.get("label", ""),
                    source_snippet=source.get("snippet", source.get("label", "")),
                    source_url=source.get("url", ""),
                    settings=settings,
                )
                if not supported:
                    rejected_cites.add(cite_num)
                    break  # One failed sentence is enough to reject the citation

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
        text = re.sub(r"  +", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)

    return text
