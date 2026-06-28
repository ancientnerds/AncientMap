"""Shared MiniMax utilities for search and M3 chat.

Used by the article verification pipeline (web_research.py), Theo's
convergence orchestrator, and the standalone relevancy gate.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

from pipeline.lyra.minimax_limiter import QuotaExhaustedError, is_quota_error

# MiniMax model — single source of truth for every call site (config.py,
# web_research.py, tweet_verifier.py, research_stages.py all import this).
# Upgraded M3 → M3 on 2026-06-01; verified live via the Anthropic endpoint
# (MiniMax-M3.0 aliases to MiniMax-M3; M3 still served as the prior model).
MINIMAX_MODEL = "MiniMax-M3"

# MiniMax search endpoint (Token Plan / Coding Plan)
MINIMAX_SEARCH_PATH = "/v1/coding_plan/search"
MINIMAX_SEARCH_TIMEOUT = 15.0
MINIMAX_CHAT_PATH = "/v1/chat/completions"
MINIMAX_CHAT_TIMEOUT = 300.0  # 5 min — M3 reasoning + long paper generation needs time


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
    """Call MiniMax M3 chat completion, strip thinking tags.

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
            logger.warning(f"MiniMax M3 chat failed: {e}")
            return ""

    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    # M3 wraps reasoning in <think>...</think> tags -- strip them
    clean = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    return clean


def minimax_chat_anthropic(
    system: str,
    user_message: str,
    max_tokens: int,
    settings=None,
    *,
    temperature: float | None = None,
    thinking: dict | None = None,
) -> str:
    """Call MiniMax-M3 via the Anthropic SDK (unified plain-text path).

    This replaces the old httpx-based minimax_chat() for the Theo pipeline.
    Uses the same Anthropic SDK client as the Lyra pipeline.

    `temperature` is keyword-only. When None, MiniMax picks its own default
    (≈1.0 for M3). Theo V2 handlers should always pass an explicit stage
    temperature from LyraSettings (temperature_research/synthesis/verification/narrative).

    `thinking` is an optional MiniMax-M3 thinking block. The only modes M3
    honors are ``{"type": "adaptive"}`` (reasoning ON) and
    ``{"type": "disabled"}`` (reasoning OFF) — ``budget_tokens`` is ignored
    (verified 2026-06-16). This is the narrative/synthesis path, which is
    quality-critical for reasoning, so when the caller passes None we DEFAULT
    TO ADAPTIVE. Mechanical callers that want the lean path should pass
    ``{"type": "disabled"}`` explicitly. thinking and temperature coexist on M3.
    """
    from pipeline.lyra.config import (
        _MINIMAX_ADAPTIVE_MAX_TOKENS_FLOOR,
        _get_minimax_anthropic_client,
        _get_settings,
    )

    if settings is None:
        settings = _get_settings()

    client = _get_minimax_anthropic_client(settings)

    # Narrative/synthesis benefits from full reasoning (2026-06-03 A/B: adaptive
    # thinking gave 100% source-grounding vs 75% bounded), so default to adaptive
    # here. (This is the prose path; the structured/mechanical calls go through
    # call_api with thinking OFF unless they pass reasoning_effort.)
    if thinking is None:
        thinking = {"type": "adaptive"}

    # M3's adaptive thinking shares the output budget and is effectively unbounded
    # (budget_tokens ignored), so a small max_tokens lets reasoning starve the
    # answer. When thinking is ON, raise max_tokens to a generous floor.
    if isinstance(thinking, dict) and thinking.get("type") == "adaptive":
        if max_tokens < _MINIMAX_ADAPTIVE_MAX_TOKENS_FLOOR:
            max_tokens = _MINIMAX_ADAPTIVE_MAX_TOKENS_FLOOR

    # MiniMax requires temperature in (0, 1] — clamp any <=0 up to 0.01.
    create_kwargs: dict = {
        "model": MINIMAX_MODEL,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user_message}],
    }
    if thinking is not None:
        create_kwargs["thinking"] = thinking
    if temperature is not None:
        create_kwargs["temperature"] = 0.01 if temperature <= 0.0 else temperature
    # MiniMax sampling/latency knobs (default None -> inert). Mirrors config.py.
    if settings.minimax_top_p is not None:
        create_kwargs["top_p"] = settings.minimax_top_p
    if settings.minimax_service_tier:
        create_kwargs["extra_body"] = {"service_tier": settings.minimax_service_tier}

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
                # M3 may still wrap reasoning in <think>...</think> tags -- strip them
                clean = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
                # Surface silent truncation: M3's interleaved thinking can
                # consume the entire max_tokens budget, leaving zero/partial
                # output. Log it so the caller can raise max_tokens if needed.
                stop_reason = getattr(response, "stop_reason", None)
                if stop_reason == "max_tokens":
                    logger.warning(
                        "MiniMax M3 hit max_tokens=%d before finishing output "
                        "(output len=%d chars). Consider raising the budget.",
                        max_tokens,
                        len(clean),
                    )
                # Credit tokens back to the active ResearchState if any —
                # otherwise minimax_chat_anthropic calls (which bypass
                # call_api) would never advance state.total_tokens.
                try:
                    from pipeline.lyra import token_accounting

                    usage = getattr(response, "usage", None)
                    if usage is not None:
                        token_accounting.add_usage(
                            {
                                "input_tokens": getattr(usage, "input_tokens", 0) or 0,
                                "output_tokens": getattr(usage, "output_tokens", 0) or 0,
                            }
                        )
                except Exception:
                    pass
                return clean
            except Exception as e:
                last_error = e
                error_str = str(e)
                is_rate_limit = "429" in error_str or "rate_limit" in error_str
                is_quota = is_rate_limit and is_quota_error(error_str)
                is_transient = is_rate_limit or any(
                    code in error_str
                    for code in ("500", "520", "529", "503", "timeout", "timed out")
                )
                if is_quota:
                    # Quota exhaustion — freeze the limiter and fail fast.
                    # The 5h rolling window must reset; retrying only wastes
                    # 3-6s of wall clock. The orchestrator catches this and
                    # sets status='deferred'.
                    slot.report_quota_exhausted()
                    logger.error(
                        "MiniMax M3 quota exhausted (no retry): %s",
                        e,
                    )
                    raise QuotaExhaustedError(
                        f"MiniMax quota exhausted during M3 call: {error_str[:200]}"
                    ) from e
                if is_rate_limit:
                    slot.report_rate_limit()
                if is_transient and attempt < 2:
                    is_overload = "529" in error_str or "overloaded" in error_str
                    delay = (attempt + 1) * (10 if is_overload else 3)
                    logger.warning(
                        "MiniMax M3 transient error (attempt %d/3), retrying in %ds: %s",
                        attempt + 1,
                        delay,
                        e,
                    )
                    import time

                    time.sleep(delay)
                    continue
                break

    logger.warning(
        f"MiniMax M3 Anthropic SDK call failed after {attempt + 1} attempts: {last_error}"
    )
    return ""


# --- Quota probe --------------------------------------------------------
# GET /v1/token_plan/remains is the documented MiniMax endpoint for the
# 5h-rolling and weekly Token Plan usage. Used by the orchestrator to refuse
# new runs when the 5h budget is too low to finish. See plan
# docs/superpowers/plans/2026-06-28-theo-rate-limit-defense.md Layer 2.

MINIMAX_TOKEN_PLAN_REMAINS_PATH = "/v1/token_plan/remains"  # noqa: S105 (URL path, not password)
MINIMAX_TOKEN_PLAN_REMAINS_TIMEOUT = 10.0
_QUOTA_CACHE_TTL_SECONDS = 60.0

_quota_cache: dict[str, tuple[float, dict]] = {}
_quota_cache_lock = threading.Lock()


def probe_minimax_quota(force: bool = False) -> dict:
    """Probe the MiniMax Token Plan remaining quota.

    Returns a dict — on success the keys match whatever the MiniMax
    endpoint returns (typical: five_hour_remaining, five_hour_limit,
    weekly_remaining, weekly_limit — but accept anything). On any HTTP
    error (404 if the endpoint doesn't exist on this plan, 401, timeout)
    returns {"ok": False, "error": "<reason>"} so the caller can treat
    the quota as "unknown" and decide accordingly.

    Cached for 60s to avoid hammering the endpoint on every run; pass
    force=True to bypass.
    """
    cache_key = "quota"
    now = time.monotonic()
    if not force:
        with _quota_cache_lock:
            cached = _quota_cache.get(cache_key)
            if cached and (now - cached[0]) < _QUOTA_CACHE_TTL_SECONDS:
                return cached[1]

    from pipeline.lyra.config import _get_settings  # avoid cycle

    settings = _get_settings()
    api_key = getattr(settings, "minimax_api_key", "") or ""
    base_url = getattr(settings, "minimax_base_url", "") or ""
    if not api_key or not base_url:
        result = {"ok": False, "error": "no_api_key_or_base_url"}
    else:
        try:
            # Raw httpx — /v1/token_plan/remains isn't an Anthropic-SDK path.
            with create_minimax_client(base_url, api_key) as client:
                resp = client.get(
                    MINIMAX_TOKEN_PLAN_REMAINS_PATH,
                    timeout=MINIMAX_TOKEN_PLAN_REMAINS_TIMEOUT,
                )
            if resp.status_code == 200:
                data = resp.json() if resp.content else {}
                data["ok"] = True
                # Normalise the MiniMax-native field names into a stable
                # shape callers can rely on. The endpoint returns a
                # `model_remains` array (one entry per model family) —
                # pick the "general" model which is what M3 falls under.
                if isinstance(data.get("model_remains"), list):
                    for entry in data["model_remains"]:
                        if entry.get("model_name") in ("general", "MiniMax-M3"):
                            data["five_hour_remaining_percent"] = entry.get(
                                "current_interval_remaining_percent"
                            )
                            data["weekly_remaining_percent"] = entry.get(
                                "current_weekly_remaining_percent"
                            )
                            data["five_hour_end_time"] = entry.get("end_time")
                            data["weekly_end_time"] = entry.get("weekly_end_time")
                            break
                result = data
            else:
                result = {
                    "ok": False,
                    "error": f"http_{resp.status_code}",
                    "body": (resp.text or "")[:300],
                }
        except Exception as exc:  # noqa: BLE001 — quota probe must never raise
            result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:200]}

    with _quota_cache_lock:
        _quota_cache[cache_key] = (now, result)
    return result


def clear_quota_cache() -> None:
    """Drop the cached quota probe (used by tests + after a manual unfreeze)."""
    with _quota_cache_lock:
        _quota_cache.clear()


# --- /Quota probe -------------------------------------------------------


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


def _coerce_to_schema(value, schema: dict, path: str = "") -> object:
    """Drop schema-violating items from an LLM response in place.

    MiniMax (and any other tool-use trick LLM under load) periodically
    emits a *bare string* inside an array typed as `items: {type: object}`,
    even with json_schema. Every downstream handler that iterates the
    array and calls `.get()` on items then crashes with
    `AttributeError("'str' object has no attribute 'get'")` — that's the
    pattern that took down four separate Theo handlers in a single
    debugging session (cross_pollination, decomposition, angle_audit,
    angle_specialist) and forced four near-identical isinstance() guards.

    Instead of guarding at every consumer, normalise at the boundary:
    walk the response against the schema and drop anything whose runtime
    type doesn't match the declared type. The handlers then receive a
    well-shaped dict and don't need per-site guards (the existing ones
    stay as belt-and-braces).

    Supported schema types: object (with properties + additionalProperties),
    array (with items), string, integer, number, boolean. Unknown types
    pass through unchanged.
    """
    if not isinstance(schema, dict):
        return value
    expected = schema.get("type")

    # JSON-schema union types — `"type": ["string", "null"]` etc. Coerce
    # only when ALL alternatives are primitive scalars; if any is "object"
    # or "array" we'd have to combine multiple structural walks, which
    # nobody in this codebase needs yet. Pass the value through unchanged
    # when it matches any of the listed types.
    if isinstance(expected, list):
        type_map = {
            "string": (str,),
            "integer": (int,),
            "number": (int, float),
            "boolean": (bool,),
            "null": (type(None),),
            "object": (dict,),
            "array": (list,),
        }
        runtime_types: tuple = ()
        for t in expected:
            runtime_types += type_map.get(t, ())
        if not runtime_types or isinstance(value, runtime_types):
            return value
        logger.warning(
            "schema-coerce: expected one of %s at %s, got %s — dropping",
            expected,
            path or "<root>",
            type(value).__name__,
        )
        return _SCHEMA_DROP

    # Array — walk items, drop those whose type doesn't match `items.type`.
    if expected == "array":
        if not isinstance(value, list):
            logger.warning(
                "schema-coerce: expected array at %s, got %s — replacing with []",
                path or "<root>",
                type(value).__name__,
            )
            return []
        item_schema = schema.get("items") or {}
        out: list = []
        for i, item in enumerate(value):
            cleaned = _coerce_to_schema(item, item_schema, f"{path}[{i}]")
            if cleaned is _SCHEMA_DROP:
                continue
            out.append(cleaned)
        return out

    # Object — walk properties, drop fields whose type doesn't match,
    # and drop the WHOLE object if any required field ends up missing.
    if expected == "object":
        if not isinstance(value, dict):
            logger.warning(
                "schema-coerce: expected object at %s, got %s — dropping",
                path or "<root>",
                type(value).__name__,
            )
            return _SCHEMA_DROP
        properties = schema.get("properties") or {}
        required = set(schema.get("required") or ())
        out_obj: dict = {}
        for k, v in value.items():
            sub_schema = properties.get(k)
            if sub_schema is None:
                # No declared property — keep as-is. Schemas in this codebase
                # don't use additionalProperties:false, so unknown keys are
                # acceptable and may carry useful debug info.
                out_obj[k] = v
                continue
            cleaned = _coerce_to_schema(v, sub_schema, f"{path}.{k}" if path else k)
            if cleaned is _SCHEMA_DROP:
                continue
            out_obj[k] = cleaned
        # Half-formed object recovery. MiniMax occasionally drops required
        # fields entirely from an object (Run #16 returned 7 angles all
        # missing `topic`). Two recovery modes:
        #
        # 1. Required STRING/INTEGER/NUMBER/BOOLEAN fields — fill with a
        #    safe default ("" / 0 / 0.0 / False). Downstream handlers
        #    already have `.get(field, default)` patterns for these and
        #    log them as "Validated angle '?'" etc. — much better than
        #    dropping the whole object.
        # 2. Required OBJECT/ARRAY fields — there's no sensible default,
        #    so drop the whole parent object as before.
        missing_required = required - out_obj.keys()
        if missing_required:
            # Factories so each filled field gets its own fresh container —
            # avoid the mutable-default trap where every dropped-array field
            # would alias the same underlying list across objects.
            primitive_defaults: dict[str, callable] = {
                "string": lambda: "",
                "integer": lambda: 0,
                "number": lambda: 0.0,
                "boolean": lambda: False,
                "array": lambda: [],
            }
            fatal_missing: list[str] = []
            filled: list[str] = []
            for field in sorted(missing_required):
                sub = properties.get(field, {})
                sub_type = sub.get("type") if isinstance(sub, dict) else None
                # Union types: accept any of the listed scalars; prefer
                # the first primitive default that exists.
                if isinstance(sub_type, list):
                    chosen = next(
                        (t for t in sub_type if t in primitive_defaults),
                        None,
                    )
                    if chosen is None:
                        fatal_missing.append(field)
                        continue
                    out_obj[field] = primitive_defaults[chosen]()
                    filled.append(field)
                elif isinstance(sub_type, str) and sub_type in primitive_defaults:
                    out_obj[field] = primitive_defaults[sub_type]()
                    filled.append(field)
                else:
                    fatal_missing.append(field)
            if filled:
                logger.warning(
                    "schema-coerce: object at %s filled missing required %s with defaults",
                    path or "<root>",
                    filled,
                )
            if fatal_missing:
                logger.warning(
                    "schema-coerce: object at %s missing required field(s) %s "
                    "with no safe default — dropping",
                    path or "<root>",
                    fatal_missing,
                )
                return _SCHEMA_DROP
        return out_obj

    # Primitive type mismatch — drop.
    type_check = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
    }.get(expected)
    if type_check is not None and not isinstance(value, type_check):
        # Allow ints to satisfy 'number'; bool/None are dropped strictly.
        logger.warning(
            "schema-coerce: expected %s at %s, got %s (%r) — dropping",
            expected,
            path or "<root>",
            type(value).__name__,
            value if not isinstance(value, str) else value[:60],
        )
        return _SCHEMA_DROP

    return value


# Sentinel used by _coerce_to_schema to indicate "drop this whole element"
# without conflating with legitimate None / "" / 0 values that callers may
# rely on.
_SCHEMA_DROP = object()


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
        parsed = json.loads(cleaned)
        # Boundary normalisation — drop schema-violating items so handlers
        # never see a string where they expect a dict (etc.). The same
        # AttributeError took down 4 separate handlers in one debugging
        # session before this hook was added.
        coerced = _coerce_to_schema(parsed, schema)
        return coerced if coerced is not _SCHEMA_DROP else {}
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
        parsed = json.loads(cleaned)
        coerced = _coerce_to_schema(parsed, schema)
        return coerced if coerced is not _SCHEMA_DROP else {}
    except Exception as exc:
        logger.error("Structured LLM call failed after retry: %s", exc)
        return {}
