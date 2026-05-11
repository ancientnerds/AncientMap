"""Shared MiniMax utilities for search and M2.7 chat.

Used by the article verification pipeline (web_research.py), Theo's
convergence orchestrator, and the standalone relevancy gate.
"""

from __future__ import annotations

import json
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
    *,
    temperature: float | None = None,
) -> str:
    """Call MiniMax M2.7 via the Anthropic SDK (unified path).

    This replaces the old httpx-based minimax_chat() for the Theo pipeline.
    Uses the same Anthropic SDK client as the Lyra pipeline.

    `temperature` is keyword-only. When None, MiniMax picks its own default
    (≈1.0 for M2.7). Theo V2 handlers should always pass an explicit stage
    temperature from LyraSettings (temperature_research/synthesis/verification/narrative).
    """
    from pipeline.lyra.config import _get_minimax_anthropic_client, _get_settings

    if settings is None:
        settings = _get_settings()

    client = _get_minimax_anthropic_client(settings)

    # MiniMax requires temperature in (0, 1] — clamp any <=0 up to 0.01.
    create_kwargs: dict = {
        "model": "MiniMax-M2.7",
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user_message}],
    }
    if temperature is not None:
        create_kwargs["temperature"] = 0.01 if temperature <= 0.0 else temperature

    from pipeline.lyra.minimax_limiter import limiter

    last_error = None
    for attempt in range(3):
        with limiter.request() as slot:
            try:
                response = client.messages.create(**create_kwargs)
                slot.report_success()
                # Extract text from response, skipping ThinkingBlock objects
                parts = []
                for block in response.content or []:
                    if hasattr(block, "text"):
                        parts.append(block.text)
                content = "\n".join(parts)
                # M2.7 may still wrap reasoning in <think>...</think> tags -- strip them
                clean = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
                # Surface silent truncation: M2.7's interleaved thinking can
                # consume the entire max_tokens budget, leaving zero/partial
                # output. Log it so the caller can raise max_tokens if needed.
                stop_reason = getattr(response, "stop_reason", None)
                if stop_reason == "max_tokens":
                    logger.warning(
                        "MiniMax M2.7 hit max_tokens=%d before finishing output "
                        "(output len=%d chars). Consider raising the budget.",
                        max_tokens,
                        len(clean),
                    )
                return clean
            except Exception as e:
                last_error = e
                error_str = str(e)
                is_rate_limit = "429" in error_str or "rate_limit" in error_str
                is_transient = is_rate_limit or any(
                    code in error_str
                    for code in ("500", "520", "529", "503", "timeout", "timed out")
                )
                if is_rate_limit:
                    slot.report_rate_limit()
                if is_transient and attempt < 2:
                    is_overload = "529" in error_str or "overloaded" in error_str
                    delay = (attempt + 1) * (10 if is_overload else 3)
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


MINIMAX_VLM_PATH = "/v1/coding_plan/vlm"
MINIMAX_VLM_TIMEOUT = 90.0


def minimax_vlm(client: httpx.Client, image_bytes: bytes, prompt: str) -> str:
    """Call MiniMax's Coding-Plan VLM endpoint for image understanding.

    Returns the model's `content` string (caller is responsible for parsing
    JSON out of it). Returns empty string on any HTTP error so callers can
    treat absence as a reject verdict.
    """
    import base64

    data_uri = f"data:image/jpeg;base64,{base64.b64encode(image_bytes).decode('ascii')}"
    try:
        resp = client.post(
            MINIMAX_VLM_PATH,
            json={"prompt": prompt, "image_url": data_uri},
            timeout=MINIMAX_VLM_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning("MiniMax VLM HTTP %s: %s", resp.status_code, resp.text[:200])
            return ""
        data = resp.json()
        return data.get("content", "") or ""
    except Exception as exc:
        logger.warning("MiniMax VLM failed: %s", exc)
        return ""


def structured_llm_call(
    system: str,
    user_message: str,
    schema: dict,
    max_tokens: int,
    settings=None,
    *,
    temperature: float,
) -> dict:
    """Call MiniMax/Anthropic with structured output enforcement.

    Uses call_api() which handles:
    - MiniMax: tool-use trick (_build_structured_output_tool)
    - Anthropic: native output_config json_schema
    - Retry logic + rate limiter

    `temperature` is a required keyword argument so every call site picks a
    stage explicitly (no accidental defaults). Use the per-stage values on
    LyraSettings: temperature_research/synthesis/verification/narrative.

    Returns parsed dict. Falls back to text parsing on failure.
    """
    from pipeline.lyra.config import _get_settings, call_api

    if settings is None:
        settings = _get_settings()

    # We avoid strict:true here even though it tightens shape enforcement —
    # MiniMax appears to silently produce no tool call at all when the
    # schema has any loose sub-shape (e.g. `items: {"type": "object"}`
    # without explicit properties / additionalProperties:false), which
    # stalls the entire convergence loop. The defensive isinstance(...)
    # guards in the handlers cover the residual shape-violation risk.
    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "structured_output",
            "schema": schema,
        },
    }

    try:
        # call_api() pulls settings via _get_settings() internally and forwards
        # **kwargs to _call_anthropic_api(settings, ...). Passing settings=
        # here would duplicate the positional arg and raise TypeError, which
        # is exactly what broke every structured Theo call after commit 964a66b.
        resp = call_api(
            system=system,
            messages=[{"role": "user", "content": user_message}],
            max_tokens=max_tokens,
            response_format=response_format,
            temperature=temperature,
        )
        if resp.stop_reason == "max_tokens":
            logger.warning(
                "Structured LLM call hit max_tokens=%d before finishing "
                "(truncated JSON likely). Consider raising the budget.",
                max_tokens,
            )
        text = resp.content[0].text if resp.content else ""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            cleaned = cleaned.rsplit("```", 1)[0].strip()
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Structured output parse failed, retrying: %s", exc)
    except Exception as exc:
        logger.warning("Structured LLM call failed, retrying: %s", exc)

    # Retry once with text fallback — inherit the caller's stage temperature.
    try:
        raw = minimax_chat_anthropic(
            system, user_message, max_tokens, settings, temperature=temperature
        )
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            cleaned = cleaned.rsplit("```", 1)[0].strip()
        return json.loads(cleaned)
    except Exception as exc:
        logger.error("Structured LLM call failed after retry: %s", exc)
        return {}
