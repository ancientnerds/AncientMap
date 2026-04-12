"""Shared MiniMax utilities for search and M2.7 chat.

Used by both the article verification pipeline (web_research.py) and
Theo's research pipeline (theo_pipeline.py).
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

# MiniMax search endpoint (Token Plan / Coding Plan)
MINIMAX_SEARCH_PATH = "/v1/coding_plan/search"
MINIMAX_SEARCH_TIMEOUT = 15.0
MINIMAX_CHAT_PATH = "/v1/chat/completions"
MINIMAX_CHAT_TIMEOUT = 300.0  # 5 min — M2.7 reasoning + long paper generation needs time


@dataclass
class WebSearchResult:
    """A single web search result."""

    title: str
    url: str
    snippet: str
    date: str = ""


def create_minimax_client(base_url: str, api_key: str) -> httpx.Client:
    """Create an httpx client configured for MiniMax API calls.

    Strips /anthropic suffix if present — this client uses the OpenAI-compatible
    endpoints (/v1/coding_plan/search, /v1/chat/completions), not the Anthropic
    endpoint.  The setting minimax_base_url may point to the Anthropic endpoint
    for the Anthropic SDK, but raw httpx callers need the base URL.
    """
    if base_url.endswith("/anthropic"):
        base_url = base_url.removesuffix("/anthropic")
    return httpx.Client(
        base_url=base_url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        timeout=MINIMAX_SEARCH_TIMEOUT,
    )


def minimax_search(client: httpx.Client, query: str) -> list[WebSearchResult]:
    """Call MiniMax search endpoint."""
    try:
        resp = client.post(MINIMAX_SEARCH_PATH, json={"q": query})
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


def minimax_chat(
    client: httpx.Client,
    model: str,
    system: str,
    user_message: str,
    max_tokens: int,
) -> str:
    """Call MiniMax M2.7 chat completion, strip thinking tags.

    Retries up to 3 times on 429 rate limit with exponential backoff.
    """
    max_retries = 3
    for attempt in range(max_retries + 1):
        try:
            resp = client.post(
                MINIMAX_CHAT_PATH,
                json={
                    "model": model,
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
    # M2.7 wraps reasoning in <think>...</think> tags -- strip them
    clean = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    return clean


def minimax_chat_anthropic(
    system: str,
    user_message: str,
    max_tokens: int,
    settings=None,
) -> str:
    """Call MiniMax M2.7 via the Anthropic SDK (unified path).

    This replaces the old httpx-based minimax_chat() for the Theo pipeline.
    Uses the same Anthropic SDK client as the Lyra pipeline.
    """
    from pipeline.lyra.config import _get_minimax_anthropic_client, _get_settings

    if settings is None:
        settings = _get_settings()

    client = _get_minimax_anthropic_client(settings)

    last_error = None
    for attempt in range(3):
        try:
            response = client.messages.create(
                model="MiniMax-M2.7",
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user_message}],
            )
            # Extract text from response, skipping ThinkingBlock objects
            parts = []
            for block in response.content or []:
                if hasattr(block, "text"):
                    parts.append(block.text)
            content = "\n".join(parts)
            # M2.7 may still wrap reasoning in <think>...</think> tags -- strip them
            clean = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
            return clean
        except Exception as e:
            last_error = e
            error_str = str(e)
            # Retry on transient server errors (500, 529, timeout)
            is_transient = any(
                code in error_str for code in ("500", "529", "503", "timeout", "timed out")
            )
            if is_transient and attempt < 2:
                delay = (attempt + 1) * 3  # 3s, 6s
                logger.warning(
                    "MiniMax M2.7 transient error (attempt %d/3), retrying in %ds: %s",
                    attempt + 1,
                    delay,
                    e,
                )
                import time

                time.sleep(delay)
                continue
            break

    logger.warning(
        f"MiniMax M2.7 Anthropic SDK call failed after {attempt + 1} attempts: {last_error}"
    )
    return ""
