"""Configuration for the Lyra news pipeline."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field

import anthropic
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Unified error type — callers catch this instead of SDK-specific errors
# ---------------------------------------------------------------------------
class LyraAPIError(Exception):
    """Wraps both Anthropic and OpenAI SDK errors for uniform caller handling."""

    pass


# ---------------------------------------------------------------------------
# Normalized response — matches Anthropic's response shape for caller compat
# ---------------------------------------------------------------------------
@dataclass
class TextBlock:
    type: str = "text"
    text: str = ""


@dataclass
class NormalizedResponse:
    """Mimics anthropic.types.Message so callers work unchanged."""

    content: list[TextBlock] = field(default_factory=list)
    stop_reason: str = "end_turn"
    model: str = ""
    usage: dict = field(default_factory=dict)

VALID_CATEGORIES = {
    "excavation",
    "artifact",
    "architecture",
    "bioarchaeology",
    "dating",
    "remote_sensing",
    "underwater",
    "epigraphy",
    "conservation",
    "heritage",
    "theory",
    "technology",
    "archaeoastronomy",
    "survey",
    "art",
    "general",
    "speculative",
}

VALID_SPECULATIVE_TAGS = {
    "ancient_astronauts",
    "annunaki",
    "lost_civilization",
    "giants",
    "supernatural",
    "conspiracy",
}


class LyraSettings(BaseSettings):
    """Lyra pipeline settings loaded from LYRA_* environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="LYRA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM API (Anthropic-compatible)
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.minimax.io/anthropic"
    temperature_min: float = 0.01
    model_summarize: str = "MiniMax-M2.5"
    model_post: str = "MiniMax-M2.5"
    model_verify: str = "MiniMax-M2.5"
    model_article: str = "MiniMax-M2.5"
    model_identify: str = "MiniMax-M2.5"
    model_identify_escalation: str = "MiniMax-M2.5"
    model_rescore: str = "MiniMax-M2.5"
    model_relevance: str = "MiniMax-M2.5"

    # Max output tokens per LLM call (65536 = MiniMax M2.5 model max)
    max_tokens: int = 65536

    # Site identification settings
    min_score_for_promotion: int = 55
    max_identifications_per_cycle: int = 20
    pg_trgm_threshold: float = 0.35
    max_research_names: int = 5
    geonames_username: str = "ancientnerds"

    # Pipeline settings
    channel_balance_factor: float = 2.0  # Throttle channels with >Nx average item count
    lookup_days: int = 14
    retry_delay_hours: int = 4  # Hours between retry attempts for failed transcripts
    min_video_minutes: float = 5.0  # Skip videos shorter than this (filters out Shorts)
    transcript_trim_start: int = 120  # Skip first 2 minutes of videos

    # Post generation (short-form news feed posts)
    post_amounts_short: int = 2
    post_amounts_medium: int = 4
    post_amounts_long: int = 6
    post_amounts_very_long: int = 8
    post_threshold_short: int = 15  # minutes
    post_threshold_medium: int = 30
    post_threshold_long: int = 60

    # Deduplication
    dedup_similarity_threshold: float = 0.25

    # Webshare proxy (for YouTube transcript fetching from VPS)
    webshare_username: str = ""
    webshare_password: str = ""

    # YouTube Data API key (for video metadata — no cookies/OAuth needed)
    youtube_api_key: str = ""

    # LLM backend: "minimax" (default, Anthropic-compatible) or "ollama" (OpenAI-compatible)
    llm_backend: str = "minimax"

    # Ollama endpoint (OpenAI-compatible API, used when llm_backend="ollama")
    ollama_base_url: str = ""
    ollama_api_key: str = ""
    ollama_model: str = "qwen3:8b"


_cached_client: anthropic.Anthropic | None = None
_cached_client_key: str = ""

_cached_settings: LyraSettings | None = None


def _get_settings() -> LyraSettings:
    """Return a module-level cached LyraSettings instance.

    Safe because env vars don't change during a pipeline run.
    Avoids re-reading .env + env vars on every call_api() invocation.
    """
    global _cached_settings
    if _cached_settings is None:
        _cached_settings = LyraSettings()
    return _cached_settings


def get_max_tokens() -> int:
    """Return the configured max_tokens value."""
    return _get_settings().max_tokens


def _is_native_anthropic(settings: LyraSettings) -> bool:
    """Check if we're using the native Anthropic API (vs a compatible provider)."""
    return not settings.anthropic_base_url or "anthropic.com" in settings.anthropic_base_url


def get_anthropic_client(settings: LyraSettings) -> anthropic.Anthropic | None:
    """Return a module-level cached Anthropic client for connection reuse.

    Returns None when llm_backend is not anthropic-based (caller passes it but it's unused).
    """
    if settings.llm_backend == "ollama":
        return None

    global _cached_client, _cached_client_key
    cache_key = f"{settings.anthropic_api_key}:{settings.anthropic_base_url}"
    if _cached_client is None or _cached_client_key != cache_key:
        kwargs: dict = {
            "api_key": settings.anthropic_api_key,
            "timeout": 120.0,
            "max_retries": 5,
        }
        if settings.anthropic_base_url:
            kwargs["base_url"] = settings.anthropic_base_url
        _cached_client = anthropic.Anthropic(**kwargs)
        _cached_client_key = cache_key
    return _cached_client


# ---------------------------------------------------------------------------
# OpenAI backend (Ollama with OpenAI-compatible API)
# ---------------------------------------------------------------------------
_cached_openai_client = None
_cached_openai_key: str = ""


def get_openai_client(settings: LyraSettings):
    """Return a cached OpenAI client for the Ollama backend."""
    global _cached_openai_client, _cached_openai_key

    from openai import OpenAI

    cache_key = f"{settings.ollama_api_key}:{settings.ollama_base_url}"
    if _cached_openai_client is None or _cached_openai_key != cache_key:
        _cached_openai_client = OpenAI(
            base_url=settings.ollama_base_url,
            api_key=settings.ollama_api_key,
            timeout=300.0,
            max_retries=3,
        )
        _cached_openai_key = cache_key
    return _cached_openai_client


def _call_openai_api(
    settings: LyraSettings,
    *,
    prefill: str | None = None,
    **kwargs,
) -> NormalizedResponse:
    """Translate Anthropic-style kwargs to OpenAI format and call the Ollama backend."""
    client = get_openai_client(settings)

    # Build OpenAI messages from Anthropic format
    messages: list[dict] = []

    # System blocks → single system message (strip cache_control)
    system_blocks = kwargs.pop("system", None)
    if system_blocks:
        if isinstance(system_blocks, str):
            messages.append({"role": "system", "content": system_blocks})
        elif isinstance(system_blocks, list):
            system_text = "\n\n".join(
                b["text"] if isinstance(b, dict) else str(b) for b in system_blocks
            )
            messages.append({"role": "system", "content": system_text})

    # User/assistant messages
    for msg in kwargs.pop("messages", []):
        messages.append({"role": msg["role"], "content": msg["content"]})

    # Drop unsupported Anthropic params
    kwargs.pop("thinking", None)
    kwargs.pop("tool_choice", None)
    kwargs.pop("tools", None)

    # Handle output_config → response_format
    output_config = kwargs.pop("output_config", None)
    response_format = None
    if output_config:
        schema = output_config.get("format", {}).get("schema")
        if schema:
            response_format = {
                "type": "json_schema",
                "json_schema": {"name": "response", "strict": True, "schema": schema},
            }

    # Handle prefill
    if prefill == "{" and not response_format:
        # Use json_object mode + system instruction for JSON prefills
        response_format = {"type": "json_object"}
        # Add instruction if not already present
        if messages and messages[0]["role"] == "system":
            if "json" not in messages[0]["content"].lower():
                messages[0]["content"] += "\n\nRespond with valid JSON only."
        else:
            messages.insert(0, {"role": "system", "content": "Respond with valid JSON only."})
    elif prefill and prefill != "{":
        # Non-JSON prefill (like "Q") — add as system instruction
        if messages and messages[0]["role"] == "system":
            messages[0]["content"] += f"\n\nStart your response with: {prefill}"
        else:
            messages.insert(0, {"role": "system", "content": f"Start your response with: {prefill}"})

    # Override model and cap max_tokens
    model = settings.ollama_model
    max_tokens = min(kwargs.pop("max_tokens", 4096), 4096)
    kwargs.pop("model", None)
    kwargs.pop("temperature", None)  # Let Ollama use default

    create_kwargs: dict = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if response_format:
        create_kwargs["response_format"] = response_format

    response = client.chat.completions.create(**create_kwargs)
    return _normalize_openai_response(response)


def _normalize_openai_response(response) -> NormalizedResponse:
    """Wrap OpenAI ChatCompletion into NormalizedResponse matching Anthropic shape."""
    choice = response.choices[0] if response.choices else None
    text = choice.message.content or "" if choice else ""

    # Map OpenAI finish_reason to Anthropic stop_reason
    finish = choice.finish_reason if choice else "stop"
    stop_reason = "max_tokens" if finish == "length" else "end_turn"

    return NormalizedResponse(
        content=[TextBlock(text=text)],
        stop_reason=stop_reason,
        model=response.model or "",
        usage={
            "input_tokens": getattr(response.usage, "prompt_tokens", 0) if response.usage else 0,
            "output_tokens": getattr(response.usage, "completion_tokens", 0) if response.usage else 0,
        },
    )


def parse_json_response(text: str) -> dict:
    """Parse JSON from an LLM response, stripping markdown fences if present."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        cleaned = cleaned.rsplit("```", 1)[0].strip()
    return json.loads(cleaned)


def parse_prefilled_json(text: str) -> dict:
    """Parse JSON from a prefill='{' LLM call.

    MiniMax-M2.5 changed behavior: it now returns the full JSON including
    the opening '{', so the old pattern of prepending '{' creates invalid
    '{{...}' JSON. This handles both old and new model behavior.
    """
    stripped = text.strip()
    if stripped.startswith("{"):
        return parse_json_response(stripped)
    return parse_json_response("{" + stripped)


# Rate throttle — auto-tunes from API response headers.
# MiniMax M2.5 text models: 500 RPM, 20M TPM (shared across news, radar, chat).
_DEFAULT_RPM = 500
_SAFETY_MARGIN = 0.85  # Use 85% — budget shared across services
_min_call_gap = 60.0 / (_DEFAULT_RPM * _SAFETY_MARGIN)
_last_call_time = 0.0


def _throttled_create(client: anthropic.Anthropic, **kwargs) -> anthropic.types.Message:
    """Send a single API request with rate throttling and RPM auto-tuning."""
    global _last_call_time, _min_call_gap

    now = time.monotonic()
    elapsed = now - _last_call_time
    if elapsed < _min_call_gap:
        sleep_time = _min_call_gap - elapsed
        logger.debug(f"Rate throttle: sleeping {sleep_time:.2f}s")
        time.sleep(sleep_time)

    raw = client.messages.with_raw_response.create(**kwargs)
    _last_call_time = time.monotonic()

    # Auto-tune gap from actual RPM limit reported by the API
    rpm_header = raw.headers.get("anthropic-ratelimit-requests-limit")
    if rpm_header:
        try:
            rpm = int(rpm_header)
            new_gap = 60.0 / (rpm * _SAFETY_MARGIN)
            if new_gap != _min_call_gap:
                logger.info(f"Rate limit detected: {rpm} RPM → min gap {new_gap:.3f}s")
                _min_call_gap = new_gap
        except (ValueError, ZeroDivisionError):
            pass

    return raw.parse()


def _tool_use_to_text_block(response: anthropic.types.Message) -> anthropic.types.Message:
    """Convert a tool_use response into a TextBlock response.

    When we use tool calling to force structured JSON, the model returns a
    ToolUseBlock with the parsed dict in `.input`. Callers expect a TextBlock
    with a JSON string, so we serialize the dict and swap the content block.
    """
    for block in response.content:
        if block.type == "tool_use":
            json_str = json.dumps(block.input, ensure_ascii=False)
            return response.model_copy(
                update={
                    "content": [anthropic.types.TextBlock(type="text", text=json_str)],
                    "stop_reason": "end_turn",
                }
            )
    return response


def call_api(
    client: anthropic.Anthropic | None,
    *,
    prefill: str | None = None,
    **kwargs,
) -> anthropic.types.Message | NormalizedResponse:
    """Throttled wrapper around the configured LLM backend.

    Dispatches to Anthropic/MiniMax or OpenAI/Ollama based on settings.llm_backend.
    Both paths catch their SDK errors and raise LyraAPIError.

    Anthropic/MiniMax path:
    - Enforces a minimum gap between calls to stay under rate limits.
    - Auto-reads rate limit headers and adjusts the gap.
    - Clamps temperature (MiniMax rejects 0.0).
    - Converts output_config to tool calling for non-native providers.
    - Retries once on truncated or malformed JSON.

    OpenAI/Ollama path:
    - Translates Anthropic kwargs to OpenAI format.
    - Returns NormalizedResponse matching Anthropic's shape.
    """
    settings = _get_settings()

    # --- OpenAI/Ollama backend ---
    if settings.llm_backend == "ollama":
        try:
            return _call_openai_api(settings, prefill=prefill, **kwargs)
        except Exception as e:
            # Catch openai.APIError and any other SDK errors
            raise LyraAPIError(f"OpenAI/Ollama API error: {e}") from e

    # --- Anthropic/MiniMax backend (existing path) ---
    if client is None:
        raise LyraAPIError("Anthropic client is None but llm_backend is not 'ollama'")

    try:
        return _call_anthropic_api(client, settings, prefill=prefill, **kwargs)
    except anthropic.APIError as e:
        raise LyraAPIError(f"Anthropic API error: {e}") from e


def _call_anthropic_api(
    client: anthropic.Anthropic,
    settings: LyraSettings,
    *,
    prefill: str | None = None,
    **kwargs,
) -> anthropic.types.Message:
    """Anthropic/MiniMax backend — all existing logic extracted from old call_api()."""
    native = _is_native_anthropic(settings)

    # Guard 1: Clamp temperature (MiniMax rejects temperature=0.0)
    if "temperature" in kwargs:
        kwargs["temperature"] = max(settings.temperature_min, kwargs["temperature"])

    # Track whether we converted to tool calling (for post-processing)
    used_tool_calling = False

    if not native:
        output_config = kwargs.pop("output_config", None)
        has_thinking = "thinking" in kwargs

        if output_config and not has_thinking:
            # Convert output_config → tool calling for guaranteed JSON.
            schema = output_config.get("format", {}).get("schema", {})
            if schema:
                kwargs["tools"] = [
                    {
                        "name": "structured_output",
                        "description": "Return the structured JSON result.",
                        "input_schema": schema,
                    }
                ]
                kwargs["tool_choice"] = {"type": "any"}
                prefill = None
                used_tool_calling = True

        # Guard 3: Enforce min max_tokens (MiniMax thinks by default)
        if "max_tokens" in kwargs and not has_thinking:
            kwargs["max_tokens"] = max(settings.max_tokens, kwargs["max_tokens"])

    # Append assistant prefill message to force structured output start
    if prefill:
        msgs = list(kwargs.get("messages", []))
        msgs.append({"role": "assistant", "content": prefill})
        kwargs["messages"] = msgs

    response = _throttled_create(client, **kwargs)

    # Tool calling path: convert ToolUseBlock → TextBlock for caller compat
    if used_tool_calling:
        return _tool_use_to_text_block(response)

    # Prefill path: validate JSON on non-native providers
    if not native and prefill == "{":
        text = next((b.text for b in response.content if hasattr(b, "text")), None)

        if response.stop_reason == "max_tokens" and text:
            orig_max = kwargs.get("max_tokens", 4096)
            kwargs["max_tokens"] = orig_max * 2
            logger.warning(
                f"JSON truncated (stop_reason=max_tokens, max_tokens was {orig_max}), "
                f"retrying with {kwargs['max_tokens']}"
            )
            response = _throttled_create(client, **kwargs)
        elif text:
            try:
                parse_prefilled_json(text)
            except (json.JSONDecodeError, ValueError):
                logger.warning(
                    f"Malformed JSON from non-native provider, retrying once: {text[:200]}"
                )
                response = _throttled_create(client, **kwargs)

    return response
