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
    """Wraps LLM SDK errors for uniform caller handling."""

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

    # LLM API (Anthropic)
    anthropic_api_key: str = ""
    temperature_min: float = 0.0
    model_summarize: str = "claude-haiku-4-5-20251001"
    model_post: str = "claude-haiku-4-5-20251001"
    model_verify: str = "claude-sonnet-4-5-20251022"
    model_article: str = "claude-sonnet-4-5-20251022"
    model_identify: str = "claude-haiku-4-5-20251001"
    model_identify_escalation: str = "claude-haiku-4-5-20251001"
    model_rescore: str = "claude-haiku-4-5-20251001"
    model_relevance: str = "claude-haiku-4-5-20251001"

    # Max output tokens per LLM call
    max_tokens: int = 8192

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

    # LLM backend: "anthropic" (default) or "ollama" (local)
    llm_backend: str = "anthropic"

    # Ollama endpoint (OpenAI-compatible API, used when llm_backend="ollama")
    ollama_base_url: str = ""
    ollama_api_key: str = ""
    ollama_model: str = "qwen3:8b"

    @classmethod
    def _resolve_env_fallbacks(cls) -> None:
        """Normalize legacy env var names before settings load."""
        # LYRA_API_KEY was the legacy Mercury key name; map it to LYRA_ANTHROPIC_API_KEY
        # so existing deployments keep working if they only set the old name.
        if not os.getenv("LYRA_ANTHROPIC_API_KEY") and os.getenv("LYRA_API_KEY"):
            os.environ["LYRA_ANTHROPIC_API_KEY"] = os.environ["LYRA_API_KEY"]


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
# API key access
# ---------------------------------------------------------------------------


def get_api_key() -> str:
    """Return the configured Anthropic API key."""
    return _get_settings().anthropic_api_key


# Backwards-compat aliases
get_current_api_key = get_api_key
get_main_api_key = get_api_key


def mark_api_key_exhausted() -> str:
    """No-op — free key pool removed. Returns the main key."""
    return get_api_key()


# ---------------------------------------------------------------------------
# Anthropic client (pipeline — synchronous calls from orchestrator/workers)
# ---------------------------------------------------------------------------
_cached_anthropic_client = None
_cached_anthropic_key: str = ""
_cached_ollama_client = None
_cached_ollama_key: str = ""


def _get_anthropic_client(api_key: str):
    """Return a cached synchronous Anthropic client."""
    global _cached_anthropic_client, _cached_anthropic_key

    import anthropic

    if _cached_anthropic_client is None or _cached_anthropic_key != api_key:
        _cached_anthropic_client = anthropic.Anthropic(api_key=api_key, timeout=120.0)
        _cached_anthropic_key = api_key
    return _cached_anthropic_client


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


def _call_anthropic_api(
    settings: LyraSettings,
    *,
    prefill: str | None = None,
    documents: list[dict] | None = None,
    **kwargs,
) -> NormalizedResponse:
    """Call Anthropic API synchronously and return a NormalizedResponse."""
    client = _get_anthropic_client(settings.anthropic_api_key)

    # Extract system blocks
    system_blocks = kwargs.pop("system", None)
    system_text = ""
    if system_blocks:
        if isinstance(system_blocks, str):
            system_text = system_blocks
        elif isinstance(system_blocks, list):
            system_text = "\n\n".join(
                b["text"] if isinstance(b, dict) else str(b) for b in system_blocks
            )

    # Build messages list
    messages: list[dict] = []
    for msg in kwargs.pop("messages", []):
        messages.append({"role": msg["role"], "content": msg["content"]})

    # If caller provided source documents, wrap last user message as content blocks
    if documents:
        for i in range(len(messages) - 1, -1, -1):
            if messages[i]["role"] == "user":
                question_text = messages[i]["content"]
                if isinstance(question_text, str):
                    content_blocks: list[dict] = [
                        {
                            "type": "document",
                            "source": {
                                "type": "text",
                                "media_type": "text/plain",
                                "data": doc["data"],
                            },
                            "title": doc.get("title", "Source"),
                            "citations": {"enabled": True},
                        }
                        for doc in documents
                    ]
                    content_blocks.append({"type": "text", "text": question_text})
                    messages[i]["content"] = content_blocks
                break

    # Handle prefill — append as assistant message
    if prefill:
        messages.append({"role": "assistant", "content": prefill})

    # Drop unsupported params
    kwargs.pop("thinking", None)
    kwargs.pop("tool_choice", None)
    kwargs.pop("tools", None)
    kwargs.pop("reasoning_effort", None)

    model = kwargs.pop("model", settings.model_summarize)
    max_tokens = kwargs.pop("max_tokens", settings.max_tokens)
    temperature = kwargs.pop("temperature", None)

    create_kwargs: dict = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if system_text:
        create_kwargs["system"] = system_text
    if temperature is not None:
        create_kwargs["temperature"] = max(settings.temperature_min, temperature)

    response = client.messages.create(**create_kwargs)
    return _normalize_anthropic_response(response)


def _normalize_anthropic_response(response) -> NormalizedResponse:
    """Wrap Anthropic Messages response into NormalizedResponse."""
    text = "".join(b.text for b in response.content if hasattr(b, "text") and b.type == "text")
    stop_reason = "max_tokens" if response.stop_reason == "max_tokens" else "end_turn"
    return NormalizedResponse(
        content=[TextBlock(text=text)],
        stop_reason=stop_reason,
        model=response.model or "",
        usage={
            "input_tokens": response.usage.input_tokens if response.usage else 0,
            "output_tokens": response.usage.output_tokens if response.usage else 0,
        },
    )


def _call_ollama_api(
    settings: LyraSettings,
    *,
    prefill: str | None = None,
    **kwargs,
) -> NormalizedResponse:
    """Call Ollama via OpenAI-compatible SDK and return a NormalizedResponse."""
    from openai import OpenAI

    client = _get_ollama_client(settings)

    messages: list[dict] = []
    system_blocks = kwargs.pop("system", None)
    if system_blocks:
        if isinstance(system_blocks, str):
            messages.append({"role": "system", "content": system_blocks})
        elif isinstance(system_blocks, list):
            system_text = "\n\n".join(
                b["text"] if isinstance(b, dict) else str(b) for b in system_blocks
            )
            messages.append({"role": "system", "content": system_text})

    for msg in kwargs.pop("messages", []):
        messages.append({"role": msg["role"], "content": msg["content"]})

    kwargs.pop("thinking", None)
    kwargs.pop("tool_choice", None)
    kwargs.pop("tools", None)
    kwargs.pop("reasoning_effort", None)
    kwargs.pop("temperature", None)

    model = settings.ollama_model
    kwargs.pop("model", None)
    max_tokens = min(kwargs.pop("max_tokens", 4096), 4096)

    create_kwargs: dict = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }

    response = client.chat.completions.create(**create_kwargs)
    choice = response.choices[0] if response.choices else None
    text = choice.message.content or "" if choice else ""
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
    reasoning_effort: str | None = None,
    documents: list[dict] | None = None,
    **kwargs,
) -> NormalizedResponse:
    """Unified LLM call — dispatches to Anthropic (cloud) or Ollama (local).

    Args:
        prefill: Prefix for the response (e.g. "{" for JSON).
        reasoning_effort: Ignored — kept for call-site compat.
        documents: Optional list of source documents to pass as Anthropic content blocks.
            Each dict has shape {"title": str, "data": str}. Anthropic only.
        **kwargs: model, max_tokens, messages, system, temperature, response_format, etc.
    """
    settings = _get_settings()

    is_ollama = settings.llm_backend == "ollama"
    try:
        if is_ollama:
            return _call_ollama_api(settings, prefill=prefill, **kwargs)
        return _call_anthropic_api(settings, prefill=prefill, documents=documents, **kwargs)
    except Exception as e:
        backend_name = "Ollama" if is_ollama else "Anthropic"
        raise LyraAPIError(f"{backend_name} API error: {e}") from e
