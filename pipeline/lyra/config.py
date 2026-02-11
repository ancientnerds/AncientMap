"""Configuration for the Lyra news pipeline."""

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

    # Anthropic API
    anthropic_api_key: str = ""
    model_summarize: str = "claude-haiku-4-5-20251001"
    model_post: str = "claude-sonnet-4-5-20250929"
    model_verify: str = "claude-haiku-4-5-20251001"
    model_article: str = "claude-sonnet-4-5-20250929"
    model_identify: str = "claude-haiku-4-5-20251001"
    model_identify_escalation: str = "claude-sonnet-4-5-20250929"
    model_rescore: str = "claude-haiku-4-5-20251001"
    model_relevance: str = "claude-haiku-4-5-20251001"

    # Site identification settings
    min_score_for_promotion: int = 55
    max_identifications_per_cycle: int = 20
    pg_trgm_threshold: float = 0.35
    identify_thinking_budget: int = 4096

    # Pipeline settings
    channel_balance_factor: float = 2.0  # Throttle channels with >Nx average item count
    lookup_days: int = 14
    retry_delay_hours: int = 12  # Hours between retry attempts for failed transcripts
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


def get_anthropic_client(settings: "LyraSettings") -> anthropic.Anthropic:
    """Return a module-level cached Anthropic client for connection reuse."""
    global _cached_client, _cached_client_key
    if _cached_client is None or _cached_client_key != settings.anthropic_api_key:
        _cached_client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key, timeout=120.0, max_retries=5,
        )
        _cached_client_key = settings.anthropic_api_key
    return _cached_client


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
    """
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
