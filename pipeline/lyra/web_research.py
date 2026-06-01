"""Web-grounded article verification backends.

Provides an abstraction layer for web search + LLM verification so the
article pipeline can switch between Anthropic (Opus + built-in web search)
and MiniMax (search API + M3 per-section verification).

Usage:
    backend = get_web_research_backend(settings)
    corrected, web_refs = backend.verify_article(article_body)
"""

from __future__ import annotations

import json
import logging
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from pipeline.lyra.config import LyraAPIError, LyraSettings, call_api
from pipeline.lyra.minimax_shared import (
    MINIMAX_MODEL,
    WebSearchResult,
    create_minimax_client,
    minimax_chat,
    minimax_search,
)

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"
ARTICLE_TIMEOUT = 600.0

# M3 is a reasoning model — thinking consumes ~2-4K tokens from the budget
MINIMAX_CLAIM_MAX_TOKENS = 4096
MINIMAX_VERIFY_MAX_TOKENS = 8192


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class SectionVerification:
    """Result of verifying one article section."""

    corrected_text: str
    web_citations: list[WebSearchResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Abstract backend
# ---------------------------------------------------------------------------


class WebResearchBackend(ABC):
    """Base class for web-grounded article verification."""

    @abstractmethod
    def verify_article(self, body: str) -> tuple[str, list[WebSearchResult]]:
        """Verify an article body using web search.

        Returns (corrected_body, web_citations_used).
        """
        ...


# ---------------------------------------------------------------------------
# Anthropic backend — Opus + built-in web_search tool
# ---------------------------------------------------------------------------


WEB_SEARCH_TOOL = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 20,
}


class AnthropicWebResearch(WebResearchBackend):
    """Uses Claude Opus with built-in web_search tool for full-article verification."""

    def __init__(self, settings: LyraSettings):
        self.settings = settings

    def verify_article(self, body: str) -> tuple[str, list[WebSearchResult]]:
        instructions = _load_prompt("article_web_verify.txt")

        try:
            response = call_api(
                model=self.settings.model_article,
                max_tokens=32000,
                timeout=ARTICLE_TIMEOUT,
                system=instructions,
                tools=[WEB_SEARCH_TOOL],
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "Fact-check this archaeological news digest using web search. "
                            "Correct errors, add hedging for contested claims, and fix "
                            "vague attributions where the real identity is findable.\n\n"
                            f"<article>\n{body}\n</article>"
                        ),
                    }
                ],
            )
        except LyraAPIError as e:
            logger.warning(f"Anthropic web verification error: {e}")
            return body, []

        if response.stop_reason not in ("end_turn", "max_tokens"):
            logger.warning("Anthropic web verify stopped unexpectedly (%s)", response.stop_reason)
            return body, []

        text = response.text.strip()

        # Extract between markers if present
        start_marker = "[START_WEB_VERIFIED]"
        end_marker = "[END_WEB_VERIFIED]"
        if start_marker in text:
            text = text[text.index(start_marker) + len(start_marker) :]
            if end_marker in text:
                text = text[: text.index(end_marker)]
            text = text.strip()
        elif text and not text.startswith("##"):
            heading_idx = text.find("## ")
            if heading_idx > 0:
                text = text[heading_idx:]

        if len(text) < 200:
            logger.warning("Anthropic web-verified body too short (%d chars)", len(text))
            return body, []

        # Anthropic's built-in search doesn't give us structured result URLs,
        # so we return empty citations — the corrections are baked into the text.
        return text, []


# ---------------------------------------------------------------------------
# MiniMax backend — search API + M3 per-section verification
# ---------------------------------------------------------------------------


class MiniMaxWebResearch(WebResearchBackend):
    """Uses MiniMax search API for web search + M3 for per-section verification.

    Flow per section:
      1. M3 extracts 3-7 verifiable claims as search queries
      2. MiniMax search API runs each query → structured results
      3. M3 verifies section text against search results → corrections + citations
    """

    def __init__(self, settings: LyraSettings):
        self.settings = settings
        self._client = create_minimax_client(settings.minimax_base_url, settings.minimax_api_key)

    # -- Web search --

    def _search(self, query: str) -> list[WebSearchResult]:
        """Call MiniMax search endpoint."""
        return minimax_search(self._client, query)

    # -- M3 chat --

    def _chat(self, system: str, user_message: str, max_tokens: int) -> str:
        """Call MiniMax M3 chat completion, strip thinking tags."""
        return minimax_chat(self._client, MINIMAX_MODEL, system, user_message, max_tokens)

    # -- Claim extraction --

    def _extract_claims(self, section_text: str) -> list[str]:
        """Use M3 to extract verifiable claims as search queries."""
        system = _load_prompt("article_web_claims.txt")
        text = self._chat(system, section_text, MINIMAX_CLAIM_MAX_TOKENS)
        if not text:
            return []

        # Parse JSON — handle markdown fencing
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            cleaned = cleaned.rsplit("```", 1)[0].strip()

        try:
            result = json.loads(cleaned)
            queries = result.get("queries", [])
            if isinstance(queries, list):
                return [q for q in queries if isinstance(q, str)]
        except (json.JSONDecodeError, KeyError):
            logger.warning(f"Failed to parse M3 claims JSON: {cleaned[:200]}")
        return []

    # -- Section verification (structured corrections) --

    @staticmethod
    def _parse_json(text: str) -> list | dict:
        """Parse JSON from M3 response, stripping markdown fences."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            cleaned = cleaned.rsplit("```", 1)[0].strip()
        return json.loads(cleaned)

    def _verify_section(
        self, section_text: str, search_results: list[WebSearchResult]
    ) -> SectionVerification:
        """Use M3 to identify corrections as structured JSON, then apply them.

        M3 never rewrites text — it outputs find/replace pairs.  We apply
        them programmatically so [N] citation markers are never touched.
        """
        if not search_results:
            return SectionVerification(corrected_text=section_text)

        # Format search results as context
        context_lines = []
        for i, r in enumerate(search_results, 1):
            date_str = f" ({r.date})" if r.date else ""
            context_lines.append(f"{i}. {r.title}{date_str}\n   URL: {r.url}\n   {r.snippet}")

        system = _load_prompt("article_web_verify_section.txt")
        user_message = (
            f"<article_section>\n{section_text}\n</article_section>\n\n"
            f"<search_results>\n" + "\n\n".join(context_lines) + "\n</search_results>"
        )

        text = self._chat(system, user_message, MINIMAX_VERIFY_MAX_TOKENS)
        if not text:
            return SectionVerification(corrected_text=section_text)

        # Parse structured corrections
        try:
            corrections = self._parse_json(text)
        except (json.JSONDecodeError, ValueError):
            logger.warning(f"Failed to parse corrections JSON: {text[:200]}")
            return SectionVerification(corrected_text=section_text)

        if not isinstance(corrections, list) or not corrections:
            return SectionVerification(corrected_text=section_text)

        # Apply corrections to original text and collect web citations.
        # When a correction has a valid source URL, we insert a [wN] marker
        # right after the replacement text.  verify_article() later renumbers
        # these to global [a], [b], [c] markers.
        corrected = section_text
        web_refs: list[WebSearchResult] = []
        seen_urls: dict[str, int] = {}  # url → local marker number
        applied = 0
        marker_num = 0

        for c in corrections:
            if not isinstance(c, dict):
                continue
            find = c.get("find", "")
            replace = c.get("replace", "")
            source_url = c.get("source_url", "")

            if not find or not replace:
                continue

            is_confirmation = find == replace
            if find not in corrected:
                logger.debug(f"Correction target not found in text: {find[:60]}")
                continue

            # Build the replacement — append [wN] marker if we have a valid URL
            # Filter out unreliable sources (social media, forums, tourism, fringe)
            BLOCKED_DOMAINS = (
                "reddit.com", "instagram.com", "facebook.com", "tiktok.com",
                "twitter.com", "x.com", "pinterest.com", "linkedin.com",
                "quora.com", "medium.com", "tumblr.com", "4chan.org",
                "tripadvisor.com", "yelp.com", "booking.com",
                "gaia.com", "ancient-origins.net", "ancient-code.com",
                "amazon.com", "ebay.com", "etsy.com",
            )  # fmt: skip
            replacement = replace if not is_confirmation else find
            is_reliable = (
                source_url
                and source_url.startswith(("http://", "https://"))
                and not any(d in source_url for d in BLOCKED_DOMAINS)
            )
            if is_reliable:
                if source_url not in seen_urls:
                    marker_num += 1
                    seen_urls[source_url] = marker_num
                    # Find matching search result for full metadata
                    ref = None
                    for r in search_results:
                        if r.url == source_url or source_url in r.url:
                            ref = r
                            break
                    if ref is None:
                        from urllib.parse import urlparse

                        domain = urlparse(source_url).netloc.replace("www.", "")
                        ref = WebSearchResult(title=domain, url=source_url, snippet="")
                    web_refs.append(ref)
                mn = seen_urls[source_url]
                replacement = f"{replacement} [w{mn}]"

            corrected = corrected.replace(find, replacement, 1)
            if not is_confirmation:
                applied += 1

        if applied or marker_num:
            logger.info(f"  Applied {applied} corrections + {marker_num} web citations")

        return SectionVerification(corrected_text=corrected, web_citations=web_refs)

    # -- Split article into sections --

    @staticmethod
    def _split_sections(body: str) -> list[str]:
        """Split article body by ## headings, keeping headings with their content."""
        parts = re.split(r"(?=^## )", body, flags=re.MULTILINE)
        return [p.strip() for p in parts if p.strip()]

    # -- Single section pipeline --

    def _verify_one_section(self, i: int, total: int, section: str) -> SectionVerification:
        """Run the full claim→search→verify pipeline for one section."""
        section_name = section.split("\n", 1)[0][:60]
        logger.info(f"Web-verifying section {i + 1}/{total}: {section_name}")

        # Step 1: Extract claims
        claims = self._extract_claims(section)
        if not claims:
            logger.info(f"  [{i + 1}] No verifiable claims, keeping as-is")
            return SectionVerification(corrected_text=section)

        logger.info(f"  [{i + 1}] Extracted {len(claims)} search queries")

        # Step 2: Search each claim
        all_results: list[WebSearchResult] = []
        for query in claims:
            results = self._search(query)
            all_results.extend(results)
            time.sleep(0.2)

        # Deduplicate by URL
        unique_results: list[WebSearchResult] = []
        result_urls: set[str] = set()
        for r in all_results:
            if r.url not in result_urls:
                unique_results.append(r)
                result_urls.add(r.url)

        logger.info(f"  [{i + 1}] Collected {len(unique_results)} unique search results")

        # Step 3: Verify section
        verification = self._verify_section(section, unique_results)
        logger.info(f"  [{i + 1}] Done — {len(verification.web_citations)} web refs")
        return verification

    # -- Main entry point --

    def verify_article(self, body: str) -> tuple[str, list[WebSearchResult]]:
        """Per-section web verification with MiniMax search + M3.

        Sections are verified in parallel using a thread pool — each section
        runs its own claim→search→verify pipeline independently.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        sections = self._split_sections(body)
        if not sections:
            return body, []

        total = len(sections)
        logger.info(f"Web-verifying {total} sections in parallel")

        # Run sections concurrently — cap at 3 workers to stay under rate limits
        results: dict[int, SectionVerification] = {}
        with ThreadPoolExecutor(max_workers=min(3, total)) as pool:
            futures = {
                pool.submit(self._verify_one_section, i, total, section): i
                for i, section in enumerate(sections)
            }
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    logger.warning(f"Section {idx + 1} verification failed: {e}")
                    results[idx] = SectionVerification(corrected_text=sections[idx])

        # Reassemble in original order, renumbering section-local [wN] to
        # globally unique [wN] so each marker maps to exactly one URL.
        corrected_sections: list[str] = []
        all_citations: list[WebSearchResult] = []
        seen_urls: dict[str, int] = {}  # url → global marker number
        global_w = 0

        for i in range(total):
            v = results[i]
            section_text = v.corrected_text

            # Renumber section-local [w1],[w2] to global [wG],[wG+1]
            local_markers = sorted(
                set(re.findall(r"\[w(\d+)\]", section_text)),
                key=int,
            )
            local_to_global: dict[str, str] = {}
            for local_num_str in local_markers:
                local_idx = int(local_num_str) - 1
                if local_idx < 0 or local_idx >= len(v.web_citations):
                    local_to_global[f"[w{local_num_str}]"] = ""
                    continue
                ref = v.web_citations[local_idx]
                if ref.url in seen_urls:
                    # Reuse existing global number for same URL
                    gn = seen_urls[ref.url]
                    local_to_global[f"[w{local_num_str}]"] = f"[w{gn}]"
                else:
                    global_w += 1
                    seen_urls[ref.url] = global_w
                    all_citations.append(ref)
                    local_to_global[f"[w{local_num_str}]"] = f"[w{global_w}]"

            for local_marker, global_marker in local_to_global.items():
                section_text = section_text.replace(local_marker, global_marker)

            corrected_sections.append(section_text)

        corrected_body = "\n\n".join(corrected_sections)
        logger.info(f"Web verification complete: {len(all_citations)} web citations")
        return corrected_body, all_citations


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_web_research_backend(settings: LyraSettings) -> WebResearchBackend:
    """Return the configured web research backend."""
    backend = settings.article_web_backend

    if backend == "minimax":
        if not settings.minimax_api_key:
            logger.warning("MiniMax API key not set, falling back to Anthropic web verify")
            return AnthropicWebResearch(settings)
        return MiniMaxWebResearch(settings)

    return AnthropicWebResearch(settings)
