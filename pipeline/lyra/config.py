"""Configuration for the Lyra news pipeline."""

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # Site identification settings
    min_score_for_promotion: int = 55
    max_identifications_per_cycle: int = 20
    pg_trgm_threshold: float = 0.35

    # Pipeline settings
    lookup_days: int = 3
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

    # Webshare proxy (for YouTube transcript fetching from VPS)
    webshare_username: str = ""
    webshare_password: str = ""

    # Queue management
    post_queue_soft_cap: int = 32
    post_queue_hard_cap: int = 48
