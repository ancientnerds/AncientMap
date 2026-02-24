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
    post_threshold_short: int = 15   # minutes
    post_threshold_medium: int = 30
    post_threshold_long: int = 60

    # Deduplication
    dedup_similarity_threshold: float = 0.25

    # Webshare proxy (for YouTube transcript fetching from VPS)
    webshare_username: str = ""
    webshare_password: str = ""

    # YouTube Data API key (for video metadata — no cookies/OAuth needed)
    youtube_api_key: str = ""


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
            return response.model_copy(update={
                "content": [anthropic.types.TextBlock(type="text", text=json_str)],
                "stop_reason": "end_turn",
            })
    return response


def call_api(
    client: anthropic.Anthropic, *, prefill: str | None = None, **kwargs,
) -> anthropic.types.Message:
    """Throttled wrapper around client.messages.create().

    Enforces a minimum gap between calls to stay under rate limits.
    Auto-reads `anthropic-ratelimit-requests-limit` from response headers
    and adjusts the gap for the actual tier (Tier 1 = 50, Tier 2 = 1000, etc.).
    The SDK's built-in retry (max_retries=5) handles transient 429/500/529.

    When using a non-Anthropic base_url (e.g. MiniMax), automatically:
    - Clamps temperature to settings.temperature_min (MiniMax rejects 0.0)
    - Converts output_config to tool calling (forces valid JSON without
      native json_schema support). Falls back to prefill + retry when
      thinking is enabled (MiniMax only supports tool_choice="auto" with
      thinking, which can't force tool use).
    - Retries once on truncated or malformed JSON for the prefill path

    If prefill is set, appends an assistant message so the model continues
    from inside the expected format (e.g. prefill="{" for JSON responses).
    """
    # Load settings for compatibility guards
    settings = _get_settings()
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
            # Extract the JSON schema from output_config and wrap it as a tool.
            schema = output_config.get("format", {}).get("schema", {})
            if schema:
                kwargs["tools"] = [{
                    "name": "structured_output",
                    "description": "Return the structured JSON result.",
                    "input_schema": schema,
                }]
                kwargs["tool_choice"] = {"type": "any"}
                # Suppress prefill — incompatible with tool calling and not needed
                prefill = None
                used_tool_calling = True

        # Guard 3: Enforce min max_tokens (MiniMax thinks by default, eating
        # the token budget; calls under settings.max_tokens risk truncation)
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

    # Prefill path: validate JSON on non-native providers (no json_schema enforcement)
    if not native and prefill == "{":
        text = next((b.text for b in response.content if hasattr(b, "text")), None)

        if response.stop_reason == "max_tokens" and text:
            # Response was truncated — retry with 2x token budget
            orig_max = kwargs.get("max_tokens", 4096)
            kwargs["max_tokens"] = orig_max * 2
            logger.warning(
                f"JSON truncated (stop_reason=max_tokens, max_tokens was {orig_max}), "
                f"retrying with {kwargs['max_tokens']}"
            )
            response = _throttled_create(client, **kwargs)
        elif text:
            # Got a complete response — verify it's valid JSON
            try:
                parse_prefilled_json(text)
            except (json.JSONDecodeError, ValueError):
                logger.warning(
                    f"Malformed JSON from non-native provider, retrying once: "
                    f"{text[:200]}"
                )
                response = _throttled_create(client, **kwargs)

    return response
