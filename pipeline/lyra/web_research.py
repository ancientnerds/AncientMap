"""Web-grounded article verification backends.

Provides an abstraction layer for web search + LLM verification so the
article pipeline can switch between Anthropic (Opus + built-in web search)
and MiniMax (search API + M2.7 per-section verification).

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

import httpx

from pipeline.lyra.config import LyraAPIError, LyraSettings, call_api

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"
ARTICLE_TIMEOUT = 600.0

# MiniMax search endpoint (Token Plan / Coding Plan)
MINIMAX_SEARCH_PATH = "/v1/coding_plan/search"
MINIMAX_SEARCH_TIMEOUT = 15.0
MINIMAX_CHAT_PATH = "/v1/chat/completions"
MINIMAX_CHAT_TIMEOUT = 120.0

# M2.7 is a reasoning model — thinking consumes ~2-4K tokens from the budget
MINIMAX_CLAIM_MAX_TOKENS = 4096
MINIMAX_VERIFY_MAX_TOKENS = 8192


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class WebSearchResult:
    """A single web search result."""

    title: str
    url: str
    snippet: str
    date: str = ""


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
# MiniMax backend — search API + M2.7 per-section verification
# ---------------------------------------------------------------------------


class MiniMaxWebResearch(WebResearchBackend):
    """Uses MiniMax search API for web search + M2.7 for per-section verification.

    Flow per section:
      1. M2.7 extracts 3-7 verifiable claims as search queries
      2. MiniMax search API runs each query → structured results
      3. M2.7 verifies section text against search results → corrections + citations
    """

    def __init__(self, settings: LyraSettings):
        self.settings = settings
        self._client = httpx.Client(
            base_url=settings.minimax_base_url,
            headers={
                "Authorization": f"Bearer {settings.minimax_api_key}",
                "Content-Type": "application/json",
            },
            timeout=MINIMAX_SEARCH_TIMEOUT,
        )

    # -- Web search --

    def _search(self, query: str) -> list[WebSearchResult]:
        """Call MiniMax search endpoint."""
        try:
            resp = self._client.post(MINIMAX_SEARCH_PATH, json={"q": query})
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"MiniMax search failed for '{query}': {e}")
            return []

        results = []
        for item in data.get("organic", []):
            results.append(
                WebSearchResult(
                    title=item.get("title", ""),
                    url=item.get("link", ""),
                    snippet=item.get("snippet", ""),
                    date=item.get("date", ""),
                )
            )
        return results

    # -- M2.7 chat --

    def _chat(self, system: str, user_message: str, max_tokens: int) -> str:
        """Call MiniMax M2.7 chat completion, strip thinking tags.

        Retries up to 3 times on 429 rate limit with exponential backoff.
        """
        max_retries = 3
        for attempt in range(max_retries + 1):
            try:
                resp = self._client.post(
                    MINIMAX_CHAT_PATH,
                    json={
                        "model": self.settings.minimax_model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user_message},
                        ],
                        "max_tokens": max_tokens,
                    },
                    timeout=MINIMAX_CHAT_TIMEOUT,
                )
                resp.raise_for_status()
                data = resp.json()
                break
            except Exception as e:
                err_str = str(e)
                is_retryable = "429" in err_str or "10054" in err_str or "timed out" in err_str
                if is_retryable and attempt < max_retries:
                    wait = 3 * (attempt + 1)  # 3, 6, 9 seconds
                    logger.info(f"MiniMax error ({err_str[:50]}), retrying in {wait}s...")
                    time.sleep(wait)
                    continue
                logger.warning(f"MiniMax M2.7 chat failed: {e}")
                return ""

        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        # M2.7 wraps reasoning in <think>...</think> tags — strip them
        clean = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
        return clean

    # -- Claim extraction --

    def _extract_claims(self, section_text: str) -> list[str]:
        """Use M2.7 to extract verifiable claims as search queries."""
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
            logger.warning(f"Failed to parse M2.7 claims JSON: {cleaned[:200]}")
        return []

    # -- Section verification (structured corrections) --

    @staticmethod
    def _parse_json(text: str) -> list | dict:
        """Parse JSON from M2.7 response, stripping markdown fences."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            cleaned = cleaned.rsplit("```", 1)[0].strip()
        return json.loads(cleaned)

    def _verify_section(
        self, section_text: str, search_results: list[WebSearchResult]
    ) -> SectionVerification:
        """Use M2.7 to identify corrections as structured JSON, then apply them.

        M2.7 never rewrites text — it outputs find/replace pairs.  We apply
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

        # Apply corrections to original text and collect web citations
        corrected = section_text
        web_refs: list[WebSearchResult] = []
        seen_urls: set[str] = set()
        applied = 0

        for c in corrections:
            if not isinstance(c, dict):
                continue
            find = c.get("find", "")
            replace = c.get("replace", "")
            source_url = c.get("source_url", "")

            if not find or not replace or find == replace:
                continue

            if find not in corrected:
                logger.debug(f"Correction target not found in text: {find[:60]}")
                continue

            corrected = corrected.replace(find, replace, 1)
            applied += 1

            # Collect web citation if URL is valid
            if source_url and source_url.startswith(("http://", "https://")):
                if source_url not in seen_urls:
                    # Find matching search result for full metadata (title, snippet, date)
                    ref = None
                    for r in search_results:
                        if r.url == source_url or source_url in r.url:
                            ref = r
                            break
                    if ref is None:
                        # Extract domain as fallback title — never use M2.7's "reason"
                        # as a title since it contains commentary, not page titles
                        from urllib.parse import urlparse

                        domain = urlparse(source_url).netloc.replace("www.", "")
                        ref = WebSearchResult(
                            title=domain,
                            url=source_url,
                            snippet="",
                        )
                    web_refs.append(ref)
                    seen_urls.add(source_url)

        if applied:
            logger.info(f"  Applied {applied}/{len(corrections)} corrections")

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
        """Per-section web verification with MiniMax search + M2.7.

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

        # Reassemble in original order — corrections already applied to text
        corrected_sections: list[str] = []
        all_citations: list[WebSearchResult] = []
        seen_urls: set[str] = set()

        for i in range(total):
            v = results[i]
            corrected_sections.append(v.corrected_text)
            for ref in v.web_citations:
                if ref.url not in seen_urls:
                    all_citations.append(ref)
                    seen_urls.add(ref.url)

        corrected_body = "\n\n".join(corrected_sections)
        logger.info(f"Web verification complete: {len(all_citations)} web references collected")
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
