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
    free_api_keys: str = ""  # Comma-separated free keys (used before main key)
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
# Key pool — rotates through free API keys before using the main (paid) key
# ---------------------------------------------------------------------------


class _KeyPool:
    """Rotates through free API keys with cooldown, falling back to the main key.

    When a key hits a rate limit, it's cooled down for 60 seconds (not permanently
    removed). After cooldown, the key becomes available again. This handles
    per-minute rate limits without wasting the key's remaining quota.
    """

    COOLDOWN_SECONDS = 60

    def __init__(self):
        self._free_keys: list[str] = []
        self._main_key: str = ""
        self._cooldowns: dict[int, float] = {}  # index -> time.monotonic() when available
        self._initialized: bool = False

    def _init(self, settings: LyraSettings) -> None:
        if self._initialized:
            return
        self._main_key = settings.api_key
        self._free_keys = [k.strip() for k in settings.free_api_keys.split(",") if k.strip()]
        self._initialized = True
        if self._free_keys:
            logger.info(f"Key pool: {len(self._free_keys)} free keys + 1 main key")

    def _is_available(self, index: int) -> bool:
        import time

        if index not in self._cooldowns:
            return True
        return time.monotonic() >= self._cooldowns[index]

    @property
    def current_key(self) -> str:
        # Find first available free key
        for i in range(len(self._free_keys)):
            if self._is_available(i):
                return self._free_keys[i]
        return self._main_key

    @property
    def using_free_key(self) -> bool:
        return self.current_key != self._main_key

    def mark_rate_limited(self) -> str:
        """Put the current free key on cooldown and return the next available key."""
        import time

        for i in range(len(self._free_keys)):
            if self._is_available(i):
                self._cooldowns[i] = time.monotonic() + self.COOLDOWN_SECONDS
                cooling = sum(1 for j in range(len(self._free_keys)) if not self._is_available(j))
                available = len(self._free_keys) - cooling
                next_key = self.current_key
                is_main = next_key == self._main_key
                logger.info(
                    f"Key {i + 1} rate-limited (cooldown {self.COOLDOWN_SECONDS}s): "
                    f"{'using main key' if is_main else f'{available} free keys available'}"
                )
                return next_key
        return self._main_key


_key_pool = _KeyPool()


def get_current_api_key() -> str:
    """Return the current API key from the pool (for background/pipeline tasks)."""
    _key_pool._init(_get_settings())
    return _key_pool.current_key


def get_main_api_key() -> str:
    """Return the main (paid) API key directly, bypassing the free key pool.

    Use this for user-facing chat to avoid rate limits from free keys.
    """
    _key_pool._init(_get_settings())
    return _key_pool._main_key


def mark_api_key_exhausted() -> str:
    """Mark the current key as rate-limited (60s cooldown) and return the next one."""
    return _key_pool.mark_rate_limited()


# ---------------------------------------------------------------------------
# OpenAI clients (Mercury cloud + Ollama local)
# ---------------------------------------------------------------------------
_cached_mercury_client = None
_cached_mercury_key: str = ""
_cached_ollama_client = None
_cached_ollama_key: str = ""


def _get_mercury_client(api_key: str, base_url: str):
    """Return a cached OpenAI client for the given key + URL."""
    global _cached_mercury_client, _cached_mercury_key

    from openai import OpenAI

    cache_key = f"{api_key}:{base_url}"
    if _cached_mercury_client is None or _cached_mercury_key != cache_key:
        _cached_mercury_client = OpenAI(
            base_url=base_url,
            api_key=api_key,
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


def _is_rate_limit_error(exc: Exception) -> bool:
    """Check if an exception indicates rate limiting or quota exhaustion."""
    try:
        from openai import RateLimitError

        if isinstance(exc, RateLimitError):
            return True
    except ImportError:
        pass
    msg = str(exc).lower()
    return "rate limit" in msg or "quota" in msg or "429" in msg


def _call_openai_api(
    settings: LyraSettings,
    *,
    prefill: str | None = None,
    is_ollama: bool = False,
    reasoning_effort: str | None = None,
    **kwargs,
) -> NormalizedResponse:
    """Translate kwargs to OpenAI format and call the Mercury/Ollama backend."""
    if is_ollama:
        client = _get_ollama_client(settings)
    else:
        _key_pool._init(settings)
        client = _get_mercury_client(_key_pool.current_key, settings.base_url)

    # Build OpenAI messages from system + user/assistant messages
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

    # Translate legacy thinking param → reasoning_effort
    thinking = kwargs.pop("thinking", None)
    reasoning_effort_from_thinking = None
    if thinking and isinstance(thinking, dict) and thinking.get("type") == "enabled":
        reasoning_effort_from_thinking = "high"

    # Drop unsupported params
    kwargs.pop("tool_choice", None)
    kwargs.pop("tools", None)

    # Merge explicit reasoning_effort with thinking-derived value
    effective_effort = reasoning_effort or reasoning_effort_from_thinking

    # Handle response_format (native pass-through)
    response_format = kwargs.pop("response_format", None)

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
    if not is_ollama and effective_effort:
        create_kwargs["reasoning_effort"] = effective_effort

    try:
        response = client.chat.completions.create(**create_kwargs)
    except Exception as e:
        # Rotate to next key on rate limit / quota exhaustion (free keys only)
        if not is_ollama and _key_pool.using_free_key and _is_rate_limit_error(e):
            next_key = _key_pool.mark_rate_limited()
            client = _get_mercury_client(next_key, settings.base_url)
            response = client.chat.completions.create(**create_kwargs)
        else:
            raise
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
    reasoning_effort: str | None = None,
    **kwargs,
) -> NormalizedResponse:
    """Unified LLM call — dispatches to Mercury (cloud) or Ollama (local).

    Args:
        prefill: Prefix for the response (e.g. "{" for JSON).
        reasoning_effort: Mercury reasoning level — "instant", "low", "medium", or "high".
            Also derived from legacy thinking={"type": "enabled"} → "high".
        **kwargs: model, max_tokens, messages, system, temperature, response_format, etc.
    """
    settings = _get_settings()

    is_ollama = settings.llm_backend == "ollama"
    try:
        return _call_openai_api(
            settings,
            prefill=prefill,
            is_ollama=is_ollama,
            reasoning_effort=reasoning_effort,
            **kwargs,
        )
    except Exception as e:
        backend_name = "Ollama" if is_ollama else "Mercury"
        raise LyraAPIError(f"{backend_name} API error: {e}") from e
