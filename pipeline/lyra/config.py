"""Configuration for the Lyra news pipeline."""

import json
import logging
import time

import anthropic
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {
    "excavation", "artifact", "architecture", "bioarchaeology", "dating",
    "remote_sensing", "underwater", "epigraphy", "conservation", "heritage",
    "theory", "technology", "archaeoastronomy", "survey", "art", "general",
    "speculative",
}

VALID_SPECULATIVE_TAGS = {
    "ancient_astronauts", "annunaki", "lost_civilization",
    "giants", "supernatural", "conspiracy",
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

    # Site identification settings
    min_score_for_promotion: int = 55
    max_identifications_per_cycle: int = 20
    pg_trgm_threshold: float = 0.35
    identify_thinking_budget: int = 4096

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
    post_threshold_short: int = 15   # minutes
    post_threshold_medium: int = 30
    post_threshold_long: int = 60

    # Deduplication
    dedup_similarity_threshold: float = 0.25

    # Webshare proxy (for YouTube transcript fetching from VPS)
    webshare_username: str = ""
    webshare_password: str = ""


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


def _is_native_anthropic(settings: "LyraSettings") -> bool:
    """Check if we're using the native Anthropic API (vs a compatible provider)."""
    return not settings.anthropic_base_url or "anthropic.com" in settings.anthropic_base_url


def get_anthropic_client(settings: "LyraSettings") -> anthropic.Anthropic:
    """Return a module-level cached Anthropic client for connection reuse."""
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


def parse_json_response(text: str) -> dict:
    """Parse JSON from an LLM response, stripping markdown fences if present."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        cleaned = cleaned.rsplit("```", 1)[0].strip()
    return json.loads(cleaned)


# Rate throttle — auto-tunes from API response headers.
# Conservative default until the first response reveals the actual RPM limit.
_DEFAULT_RPM = 50  # Tier 1 minimum, safe starting point
_SAFETY_MARGIN = 0.9  # Use 90% of the limit
_min_call_gap = 60.0 / (_DEFAULT_RPM * _SAFETY_MARGIN)
_last_call_time = 0.0


def call_api(client: anthropic.Anthropic, **kwargs) -> anthropic.types.Message:
    """Throttled wrapper around client.messages.create().

    Enforces a minimum gap between calls to stay under rate limits.
    Auto-reads `anthropic-ratelimit-requests-limit` from response headers
    and adjusts the gap for the actual tier (Tier 1 = 50, Tier 2 = 1000, etc.).
    The SDK's built-in retry (max_retries=5) handles transient 429/500/529.

    When using a non-Anthropic base_url (e.g. MiniMax), automatically:
    - Clamps temperature to settings.temperature_min (MiniMax rejects 0.0)
    - Strips output_config (not supported by MiniMax)
    """
    global _last_call_time, _min_call_gap

    # Load settings for compatibility guards
    settings = _get_settings()
    native = _is_native_anthropic(settings)

    # Guard 1: Clamp temperature (MiniMax rejects temperature=0.0)
    if "temperature" in kwargs:
        kwargs["temperature"] = max(settings.temperature_min, kwargs["temperature"])

    if not native:
        # Guard 2: Strip output_config (not supported by non-Anthropic providers)
        kwargs.pop("output_config", None)

        # Guard 3: Enforce min max_tokens (MiniMax thinks by default, eating
        # the token budget; calls under 1024 produce empty/truncated responses)
        if "max_tokens" in kwargs and "thinking" not in kwargs:
            kwargs["max_tokens"] = max(1024, kwargs["max_tokens"])

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
