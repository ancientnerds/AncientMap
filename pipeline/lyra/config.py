"""Configuration for the Lyra news pipeline."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Unified error type — callers catch this instead of SDK-specific errors
# ---------------------------------------------------------------------------
class LyraAPIError(Exception):
    """Wraps OpenAI SDK errors for uniform caller handling."""

    pass


# ---------------------------------------------------------------------------
# Normalized response — common shape for all backends
# ---------------------------------------------------------------------------
@dataclass
class TextBlock:
    type: str = "text"
    text: str = ""


@dataclass
class NormalizedResponse:
    """Normalized LLM response so callers work unchanged."""

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

    # LLM API (OpenAI-compatible — Mercury 2 by Inception Labs)
    api_key: str = ""
    base_url: str = "https://api.inceptionlabs.ai/v1"
    temperature_min: float = 0.0
    model_summarize: str = "mercury-2"
    model_post: str = "mercury-2"
    model_verify: str = "mercury-2"
    model_article: str = "mercury-2"
    model_identify: str = "mercury-2"
    model_identify_escalation: str = "mercury-2"
    model_rescore: str = "mercury-2"
    model_relevance: str = "mercury-2"

    # Max output tokens per LLM call (32000 = Mercury 2 model max)
    max_tokens: int = 32000

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
    transcript_fetch_timeout: int = 120  # Max seconds per transcript fetch

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

    # LLM backend: "mercury" (default, OpenAI-compatible cloud) or "ollama" (local)
    llm_backend: str = "mercury"

    # Ollama endpoint (OpenAI-compatible API, used when llm_backend="ollama")
    ollama_base_url: str = ""
    ollama_api_key: str = ""
    ollama_model: str = "qwen3:8b"

    @classmethod
    def _resolve_env_fallbacks(cls) -> None:
        """Set env vars from legacy LYRA_ANTHROPIC_* names if new ones aren't set."""
        if not os.getenv("LYRA_API_KEY") and os.getenv("LYRA_ANTHROPIC_API_KEY"):
            os.environ["LYRA_API_KEY"] = os.environ["LYRA_ANTHROPIC_API_KEY"]
        if not os.getenv("LYRA_BASE_URL") and os.getenv("LYRA_ANTHROPIC_BASE_URL"):
            os.environ["LYRA_BASE_URL"] = os.environ["LYRA_ANTHROPIC_BASE_URL"]


_cached_settings: LyraSettings | None = None


def _get_settings() -> LyraSettings:
    """Return a module-level cached LyraSettings instance.

    Safe because env vars don't change during a pipeline run.
    Avoids re-reading .env + env vars on every call_api() invocation.
    """
    global _cached_settings
    if _cached_settings is None:
        LyraSettings._resolve_env_fallbacks()
        _cached_settings = LyraSettings()
    return _cached_settings


def get_max_tokens() -> int:
    """Return the configured max_tokens value."""
    return _get_settings().max_tokens


# ---------------------------------------------------------------------------
# OpenAI clients (Mercury cloud + Ollama local)
# ---------------------------------------------------------------------------
_cached_mercury_client = None
_cached_mercury_key: str = ""
_cached_ollama_client = None
_cached_ollama_key: str = ""


def _get_mercury_client(settings: LyraSettings):
    """Return a cached OpenAI client for the Mercury backend."""
    global _cached_mercury_client, _cached_mercury_key

    from openai import OpenAI

    cache_key = f"{settings.api_key}:{settings.base_url}"
    if _cached_mercury_client is None or _cached_mercury_key != cache_key:
        _cached_mercury_client = OpenAI(
            base_url=settings.base_url,
            api_key=settings.api_key,
            timeout=120.0,
            max_retries=5,
        )
        _cached_mercury_key = cache_key
    return _cached_mercury_client


def _get_ollama_client(settings: LyraSettings):
    """Return a cached OpenAI client for the Ollama backend."""
    global _cached_ollama_client, _cached_ollama_key

    from openai import OpenAI

    cache_key = f"{settings.ollama_api_key}:{settings.ollama_base_url}"
    if _cached_ollama_client is None or _cached_ollama_key != cache_key:
        _cached_ollama_client = OpenAI(
            base_url=settings.ollama_base_url,
            api_key=settings.ollama_api_key,
            timeout=300.0,
            max_retries=3,
        )
        _cached_ollama_key = cache_key
    return _cached_ollama_client


def _call_openai_api(
    settings: LyraSettings,
    *,
    prefill: str | None = None,
    is_ollama: bool = False,
    **kwargs,
) -> NormalizedResponse:
    """Translate Anthropic-style kwargs to OpenAI format and call the backend."""
    client = _get_ollama_client(settings) if is_ollama else _get_mercury_client(settings)

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
            messages.insert(
                0, {"role": "system", "content": f"Start your response with: {prefill}"}
            )

    if is_ollama:
        # Ollama: override model and cap max_tokens
        model = settings.ollama_model
        max_tokens = min(kwargs.pop("max_tokens", 4096), 4096)
        kwargs.pop("model", None)
        kwargs.pop("temperature", None)  # Let Ollama use default
    else:
        # Mercury: use the model from kwargs (caller passes settings.model_*) with full max_tokens
        model = kwargs.pop("model", "mercury-2")
        max_tokens = kwargs.pop("max_tokens", settings.max_tokens)
        temperature = kwargs.pop("temperature", None)

    create_kwargs: dict = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if not is_ollama and temperature is not None:
        create_kwargs["temperature"] = max(settings.temperature_min, temperature)
    if response_format:
        create_kwargs["response_format"] = response_format

    response = client.chat.completions.create(**create_kwargs)
    return _normalize_openai_response(response)


def _normalize_openai_response(response) -> NormalizedResponse:
    """Wrap OpenAI ChatCompletion into NormalizedResponse."""
    choice = response.choices[0] if response.choices else None
    text = choice.message.content or "" if choice else ""

    # Map OpenAI finish_reason to stop_reason
    finish = choice.finish_reason if choice else "stop"
    stop_reason = "max_tokens" if finish == "length" else "end_turn"

    return NormalizedResponse(
        content=[TextBlock(text=text)],
        stop_reason=stop_reason,
        model=response.model or "",
        usage={
            "input_tokens": getattr(response.usage, "prompt_tokens", 0) if response.usage else 0,
            "output_tokens": getattr(response.usage, "completion_tokens", 0)
            if response.usage
            else 0,
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
    """Parse JSON from an LLM response that was asked for JSON output.

    Handles both complete JSON and responses that may have markdown fencing.
    """
    stripped = text.strip()
    if stripped.startswith("{"):
        return parse_json_response(stripped)
    return parse_json_response("{" + stripped)


def call_api(
    *,
    prefill: str | None = None,
    **kwargs,
) -> NormalizedResponse:
    """Unified LLM call — dispatches to Mercury (cloud) or Ollama (local).

    Both paths translate Anthropic-style kwargs to OpenAI format,
    catch SDK errors, and raise LyraAPIError.
    """
    settings = _get_settings()

    is_ollama = settings.llm_backend == "ollama"
    try:
        return _call_openai_api(settings, prefill=prefill, is_ollama=is_ollama, **kwargs)
    except Exception as e:
        backend_name = "Ollama" if is_ollama else "Mercury"
        raise LyraAPIError(f"{backend_name} API error: {e}") from e
