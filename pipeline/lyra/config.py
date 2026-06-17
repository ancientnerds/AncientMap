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
class Citation:
    """A single citation pointer into a source document."""

    cited_text: str = ""
    document_index: int = 0
    document_title: str = ""
    start_char_index: int = 0
    end_char_index: int = 0
    type: str = "char_location"


@dataclass
class TextBlock:
    type: str = "text"
    text: str = ""
    citations: list[Citation] = field(default_factory=list)


@dataclass
class NormalizedResponse:
    """Normalized LLM response so callers work unchanged."""

    content: list[TextBlock] = field(default_factory=list)
    stop_reason: str = "end_turn"
    model: str = ""
    usage: dict = field(default_factory=dict)

    @property
    def text(self) -> str:
        """Join all text blocks into a single string.

        Citations split responses into many small fragments — this
        reassembles them into the full text for callers that don't
        need per-block citation data.
        """
        return "".join(b.text for b in self.content if b.type == "text")


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

    # Per-stage MiniMax temperatures for the Theo V2 research pipeline.
    # Research/extraction/verification stay cold to preserve faithfulness to sources;
    # synthesis gets a modest bump to help cross-source connections;
    # narrative writing warms up so the Why Files prose has voice.
    temperature_research: float = 0.2
    temperature_synthesis: float = 0.3
    temperature_verification: float = 0.1
    temperature_narrative: float = 0.8

    # MiniMax-M3 thinking control. RE-VERIFIED LIVE 2026-06-16 — the contract
    # CHANGED since 2026-06-01: M3 now only honors thinking modes "adaptive" (ON)
    # and "disabled" (OFF); `budget_tokens` is accepted but IGNORED (probe: budget
    # 128 → 3448 chars of thinking). So the budget ladder below is DEAD CONFIG,
    # kept only to avoid breaking any LYRA_MINIMAX_THINKING_BUDGET_* env overrides.
    # The live mapping is binary and lives in thinking_for_effort():
    # instant/low → disabled, medium/high → adaptive. Since per-TOKEN metering
    # (2026-06-02) thinking (~89% of M3 output) is the dominant quota cost, so
    # mechanical calls run thinking OFF.
    minimax_thinking_enabled: bool = True
    minimax_thinking_budget_instant: int = 256  # dead config — see note above
    minimax_thinking_budget_low: int = 1024  # dead config
    minimax_thinking_budget_medium: int = 4096  # dead config
    minimax_thinking_budget_high: int = 8192  # dead config

    # Long-context (M3 1M window). Per-call billing → context is free; the only
    # guard is the ~1M hard request limit (avoid HTTP 400), NOT cost.
    # MiniMax default raised 2000 -> 12000 (2026-06-02). Validated at the
    # specialist stage: feeding fuller source text (vs 2000-char snippets)
    # roughly DOUBLED extracted findings (5-6 -> 10-14) with NO structured-output
    # breakage (the retry fix handles the larger prompts). 12000 captures typical
    # full articles; beyond that gave no gain (40000 = needless prompt bloat).
    # Anthropic backend stays at 2000.
    source_max_content_chars: int = 2000
    minimax_source_max_content_chars: int = 12000
    long_context_hard_ceiling_tokens: int = 1_000_000

    # MiniMax recommended sampling + latency knobs (verified accepted on /anthropic).
    # top_p=0.95 is MiniMax's own recommendation for M3 (trims the improbable
    # token tail without over-constraining). Applied for the MiniMax backend only;
    # per-stage temperatures stay as-is. Override via LYRA_MINIMAX_TOP_P; set None
    # to fall back to the model default. service_tier stays off by default.
    minimax_top_p: float | None = 0.95
    minimax_service_tier: str | None = None

    model_summarize: str = "claude-haiku-4-5-20251001"
    model_post: str = "claude-sonnet-4-6"
    model_verify: str = "claude-opus-4-6"
    model_article: str = "claude-opus-4-6"
    model_article_verify: str = "claude-opus-4-6"
    model_identify: str = "claude-haiku-4-5-20251001"
    model_identify_escalation: str = "claude-haiku-4-5-20251001"
    model_rescore: str = "claude-haiku-4-5-20251001"
    model_relevance: str = "claude-haiku-4-5-20251001"
    model_cluster: str = "claude-sonnet-4-6"

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
    dedup_similarity_threshold: float = 0.40

    # Web verification for stories (0 = disabled)
    story_web_verify_min_significance: int = 2

    # Generic HTTP proxy for all YouTube-facing requests (transcripts +
    # storyboards). Takes precedence over Webshare when set. Used for the
    # home-IP exit via Tailscale: http://<pi-tailnet-ip>:8888 (tinyproxy).
    proxy_url: str = ""

    # Webshare proxy (for YouTube transcript fetching from VPS)
    webshare_username: str = ""
    webshare_password: str = ""

    # YouTube Data API key (for video metadata — no cookies/OAuth needed)
    youtube_api_key: str = ""

    # LLM backend: "anthropic" (default) or "minimax"
    llm_backend: str = "anthropic"

    # MiniMax via Anthropic-compatible endpoint (all calls use the Anthropic SDK)
    minimax_api_key: str = ""
    minimax_base_url: str = "https://api.minimax.io/anthropic"

    # Article web verification backend: "minimax" (MiniMax search API + M3
    # per-section structured corrections) or "anthropic" (Opus + web_search tool)
    article_web_backend: str = "minimax"

    # Probative-images feature — when False, skip the whole new stage
    probative_images_enabled: bool = True
    # Candidates to fetch per opportunity before gating (raised for density)
    probative_images_candidates_per_opportunity: int = 20
    # Target minimum images per substantial paragraph (soft target, not hard cap)
    images_per_paragraph_target: int = 3
    # Max images to embed per single opportunity (VLM-accepted candidates, dedup by source)
    probative_images_max_per_opportunity: int = 3
    # When True, pass the image candidate pool for this section's angles into the
    # paper-writer prompt and allow the writer to emit [[IMG:candidate_id]] markers
    # that PIH resolves. Markers the writer doesn't use fall through to PIH's
    # auto-selection so "writer ignores the list entirely" is a safe no-op.
    paper_writer_sees_images: bool = True

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


def thinking_for_effort(effort: str | None, settings: LyraSettings | None = None) -> dict | None:
    """Map a reasoning_effort level to a MiniMax-M3 ``thinking`` config block.

    Single source of truth for the effort→thinking mapping.

    M3 contract, RE-VERIFIED LIVE 2026-06-16 (api.minimax.io/anthropic) — it
    CHANGED since the 2026-06-01 notes:
    - The only honored modes are ``{"type":"adaptive"}`` (reasoning ON) and
      ``{"type":"disabled"}`` (reasoning OFF). Omitting thinking also = OFF.
    - ``{"type":"enabled","budget_tokens":N}`` is accepted but ``budget_tokens``
      is IGNORED (probe: budget 128 → 3448 chars of thinking). The old
      256/1024/4096/8192 budget ladder was therefore dead config and the source
      of the ``max_tokens`` truncation/empty-output failures.
    - ``disabled`` returns non-empty text (the old "disabled = empty" is FALSE
      for current M3) and does NOT break the forced tool-call trick (3/3 probe).

    QUALITY-MAX premise (token cost is irrelevant): M3 reasoning improves output
    quality (2026-06-03 A/B: adaptive = 100% source-grounding vs 75% bounded), so
    EVERY call reasons — `effort` no longer gates thinking on/off. We always
    return ``{"type":"adaptive"}``. ``disabled`` is kept only as an explicit
    per-call override (callers pass ``thinking={"type":"disabled"}`` directly,
    e.g. a genuinely trivial extraction where reasoning adds nothing); it is
    never produced from an effort level. `effort` is retained for signature
    compatibility with the call sites.

    Returns None only when thinking is globally disabled in settings.
    """
    if settings is None:
        settings = _get_settings()
    if not settings.minimax_thinking_enabled:
        return None
    return {"type": "adaptive"}


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


def _get_anthropic_client(api_key: str):
    """Return a cached synchronous Anthropic client."""
    global _cached_anthropic_client, _cached_anthropic_key

    import anthropic

    if _cached_anthropic_client is None or _cached_anthropic_key != api_key:
        _cached_anthropic_client = anthropic.Anthropic(api_key=api_key, timeout=120.0)
        _cached_anthropic_key = api_key
    return _cached_anthropic_client


# M3's adaptive thinking shares the output budget and is effectively unbounded
# (budget_tokens is ignored — verified 2026-06-16). When thinking is ON, give the
# call a generous max_tokens floor so reasoning can't starve the answer or the
# forced structured-output tool call (which degrades to plain text when starved).
# Quality-max premise: tokens are free, so floor high (M3 output ceiling is 512k).
_MINIMAX_ADAPTIVE_MAX_TOKENS_FLOOR = 16384


def _call_anthropic_api(
    settings: LyraSettings,
    *,
    prefill: str | None = None,
    documents: list[dict] | None = None,
    timeout: float | None = None,
    **kwargs,
) -> NormalizedResponse:
    """Call LLM via Anthropic SDK — works for both Anthropic and MiniMax backends.

    MiniMax adaptation points are clearly marked with # [MINIMAX].
    """
    is_minimax = settings.llm_backend == "minimax"
    client = _get_client(settings)

    # --- Extract params from kwargs ---
    system_blocks = kwargs.pop("system", None)
    system_text = ""
    if system_blocks:
        if isinstance(system_blocks, str):
            system_text = system_blocks
        elif isinstance(system_blocks, list):
            system_text = "\n\n".join(
                b["text"] if isinstance(b, dict) else str(b) for b in system_blocks
            )

    messages: list[dict] = []
    for msg in kwargs.pop("messages", []):
        messages.append({"role": msg["role"], "content": msg["content"]})

    response_format = kwargs.pop("response_format", None)
    thinking_config = kwargs.pop("thinking", None)
    tool_choice = kwargs.pop("tool_choice", None)
    tools = kwargs.pop("tools", None)
    reasoning_effort = kwargs.pop("reasoning_effort", None)

    model = kwargs.pop("model", settings.model_summarize)
    max_tokens = kwargs.pop("max_tokens", settings.max_tokens)
    temperature = kwargs.pop("temperature", None)
    top_p = kwargs.pop("top_p", None)

    # [MINIMAX] Adaptation 1: Model override — all calls use the MiniMax model
    if is_minimax:
        from pipeline.lyra.minimax_shared import MINIMAX_MODEL

        model = MINIMAX_MODEL

    # [MINIMAX] Adaptation 6: native M3 thinking. On Anthropic this is a no-op
    # (Claude has no such knob); on MiniMax we default EVERY call to adaptive
    # reasoning (quality-max premise — tokens are free, and M3 reasoning lifts
    # output quality). thinking_for_effort() returns adaptive regardless of
    # effort (or None if globally disabled in settings). Callers that genuinely
    # want reasoning OFF pass an explicit thinking={"type":"disabled"} block,
    # which is preserved here.
    if is_minimax and thinking_config is None:
        thinking_config = thinking_for_effort(reasoning_effort, settings)

    # M3's adaptive thinking shares the output budget and is effectively unbounded
    # (budget_tokens is ignored — verified 2026-06-16), so a small max_tokens lets
    # reasoning starve the answer / the forced tool call. When thinking is ON,
    # raise max_tokens to a generous floor.
    if (
        is_minimax
        and isinstance(thinking_config, dict)
        and thinking_config.get("type") == "adaptive"
        and max_tokens < _MINIMAX_ADAPTIVE_MAX_TOKENS_FLOOR
    ):
        max_tokens = _MINIMAX_ADAPTIVE_MAX_TOKENS_FLOOR

    # [MINIMAX] Adaptation 2: Documents — inline into user message
    # (MiniMax doesn't support document content blocks or citations)
    if documents and is_minimax:
        docs_text = "\n\n".join(
            f"--- {doc.get('title', 'Source')} ---\n{doc['data']}" for doc in documents
        )
        for i in range(len(messages) - 1, -1, -1):
            if messages[i]["role"] == "user":
                original = messages[i]["content"]
                if isinstance(original, str):
                    messages[i]["content"] = f"{docs_text}\n\n{original}"
                break
        documents = None  # consumed

    # Anthropic: wrap documents as content blocks with citations
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

    # Extended thinking is incompatible with prefill and temperature
    if thinking_config is not None:
        prefill = None

    # --- Structured output handling ---
    use_structured_output = response_format and response_format.get("type") == "json_schema"
    use_tool_trick = False

    if use_structured_output:
        prefill = None
        schema = response_format["json_schema"]["schema"]

        if is_minimax:
            # [MINIMAX] Adaptation 3: Structured output via tool-use trick
            tool = _build_structured_output_tool(schema)
            tools = [tool] if not tools else [tool] + list(tools)
            tool_choice = {"type": "tool", "name": "structured_output"}
            use_tool_trick = True

    # Handle prefill
    if prefill:
        messages.append({"role": "assistant", "content": prefill})

    # --- Build request kwargs ---
    create_kwargs: dict = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }

    # Anthropic native structured output
    if use_structured_output and not use_tool_trick:
        js = response_format["json_schema"]
        create_kwargs["output_config"] = {
            "format": {
                "type": "json_schema",
                "schema": js["schema"],
            }
        }

    if tools:
        create_kwargs["tools"] = tools
    if tool_choice:
        create_kwargs["tool_choice"] = tool_choice
    if system_text:
        create_kwargs["system"] = [
            {
                "type": "text",
                "text": system_text,
                "cache_control": {"type": "ephemeral"},
            }
        ]

    if thinking_config is not None:
        create_kwargs["thinking"] = thinking_config

    # Temperature: on Anthropic it is mutually exclusive with extended thinking
    # (the API rejects both together); on MiniMax-M3 they coexist (verified
    # 2026-06-01), so MiniMax always applies temperature alongside any thinking.
    if temperature is not None and (is_minimax or thinking_config is None):
        # [MINIMAX] Adaptation 4: Temperature clamping (0,1] — exclusive of 0
        if is_minimax and temperature <= 0.0:
            temperature = 0.01
        else:
            temperature = max(settings.temperature_min, temperature)
        create_kwargs["temperature"] = temperature

    # [MINIMAX] top_p — apply the configured MiniMax default when the caller
    # didn't pass one. Defaults to None (no change); set LYRA_MINIMAX_TOP_P=0.95
    # (MiniMax's recommendation) once validated.
    if is_minimax and top_p is None and settings.minimax_top_p is not None:
        top_p = settings.minimax_top_p
    if top_p is not None:
        create_kwargs["top_p"] = top_p

    # [MINIMAX] service_tier — optional latency tier (e.g. "priority"). Passed
    # via extra_body since it's a MiniMax extension, not a native Anthropic param.
    if is_minimax and settings.minimax_service_tier:
        create_kwargs["extra_body"] = {"service_tier": settings.minimax_service_tier}

    if timeout is not None:
        import httpx

        create_kwargs["timeout"] = httpx.Timeout(timeout, connect=30.0)

    # --- Make the API call (with retry + global rate limiter) ---
    from pipeline.lyra.minimax_limiter import limiter

    # Total attempts: transient errors AND unusable structured output both retry
    # here. The forced tool call is stochastic on MiniMax (it sometimes answers
    # in prose instead of calling the tool). We only retry when the response is
    # genuinely unusable — i.e. NO tool_use block AND the text isn't parseable
    # JSON. When M3 returns valid JSON as a text block we accept it immediately
    # (the text fallback parses it), which avoids multiplying latency on the
    # large structured calls that fail the tool call but still emit usable JSON.
    # Quality-max premise (tokens free): retry the stochastic tool call up to 5x —
    # the extra attempts only fire when the output is genuinely unusable, so the
    # cost is latency on otherwise-failed calls, which is worth a reliable result.
    _max_attempts = 5
    last_exc = None
    response = None
    for _attempt in range(_max_attempts):
        with limiter.request() as slot:
            try:
                response = client.messages.create(**create_kwargs)
                slot.report_success()
            except Exception as exc:
                last_exc = exc
                error_str = str(exc)
                is_rate_limit = "429" in error_str or "rate_limit" in error_str
                is_transient = is_rate_limit or any(
                    code in error_str
                    for code in ("500", "520", "529", "503", "timeout", "timed out")
                )
                if is_rate_limit:
                    slot.report_rate_limit()
                if is_transient and _attempt < _max_attempts - 1:
                    import time as _time

                    is_overload = "529" in error_str or "overloaded" in error_str
                    delay = (_attempt + 1) * (10 if is_overload else 3)
                    logger.warning(
                        "LLM call transient error (attempt %d/%d), retrying in %ds: %s",
                        _attempt + 1,
                        _max_attempts,
                        delay,
                        exc,
                    )
                    _time.sleep(delay)
                    continue
                raise
        # Retry only when the structured response is unusable: no tool_use block
        # AND no parseable JSON in the text. A valid JSON text block is accepted
        # as-is (the downstream text fallback parses it) — no wasted retry.
        if (
            use_tool_trick
            and _attempt < _max_attempts - 1
            and _extract_tool_use_json(response.content) is None
            and not _text_parses_as_json(response.content)
        ):
            logger.info(
                "MiniMax returned no usable structured output, retrying (%d/%d)",
                _attempt + 1,
                _max_attempts,
            )
            continue
        break
    else:
        # Loop exhausted. If a response exists (missing-tool_use case) fall
        # through to the text fallback below; only raise on a real error.
        if response is None:
            raise last_exc  # type: ignore[misc]

    # --- Normalize the response ---
    # [MINIMAX] Adaptation 5: Extract tool result if tool-use trick was used
    if use_tool_trick:
        tool_json = _extract_tool_use_json(response.content)
        if tool_json is not None:
            stop_reason = response.stop_reason or "end_turn"
            usage_dict = {
                "input_tokens": response.usage.input_tokens if response.usage else 0,
                "output_tokens": response.usage.output_tokens if response.usage else 0,
            }
            # Credit tokens back to the active ResearchState if one is bound
            # (Theo runs via convergence_orchestrator bind theirs at startup).
            try:
                from pipeline.lyra import token_accounting

                token_accounting.add_usage(usage_dict)
            except Exception:
                pass
            return NormalizedResponse(
                content=[TextBlock(text=tool_json)],
                stop_reason=stop_reason,
                model=response.model or "",
                usage=usage_dict,
            )
        # No tool_use block. When M3 emitted valid JSON as a text block this is a
        # normal fast path (the downstream structured parser handles it) — only
        # warn when the text isn't usable JSON after exhausting retries.
        if _text_parses_as_json(response.content):
            logger.debug("MiniMax returned JSON as a text block (no tool_use) — accepted")
        else:
            logger.warning(
                "MiniMax returned no tool_use block and no parseable JSON after "
                "%d attempts — using lossy text fallback",
                _max_attempts,
            )

    return _normalize_anthropic_response(response)


def _normalize_anthropic_response(response) -> NormalizedResponse:
    """Wrap Anthropic Messages response into NormalizedResponse."""
    blocks = []
    for b in response.content:
        if hasattr(b, "text") and b.type == "text":
            cites = []
            if hasattr(b, "citations") and b.citations:
                for c in b.citations:
                    cites.append(
                        Citation(
                            cited_text=getattr(c, "cited_text", ""),
                            document_index=getattr(c, "document_index", 0),
                            document_title=getattr(c, "document_title", ""),
                            start_char_index=getattr(c, "start_char_index", 0),
                            end_char_index=getattr(c, "end_char_index", 0),
                            type=getattr(c, "type", "char_location"),
                        )
                    )
            blocks.append(TextBlock(text=b.text, citations=cites))

    stop_reason = response.stop_reason or "end_turn"
    usage_dict = {
        "input_tokens": response.usage.input_tokens if response.usage else 0,
        "output_tokens": response.usage.output_tokens if response.usage else 0,
    }
    # Credit tokens back to the active ResearchState if one is bound
    # (Theo runs via convergence_orchestrator bind theirs at startup).
    try:
        from pipeline.lyra import token_accounting

        token_accounting.add_usage(usage_dict)
    except Exception:
        pass
    return NormalizedResponse(
        content=blocks,
        stop_reason=stop_reason,
        model=response.model or "",
        usage=usage_dict,
    )


# ---------------------------------------------------------------------------
# MiniMax Anthropic-compatible client (cached)
# ---------------------------------------------------------------------------
_cached_minimax_anthropic_client = None
_cached_minimax_anthropic_key: str = ""


def _get_minimax_anthropic_client(settings: LyraSettings):
    """Return a cached Anthropic client pointed at MiniMax's Anthropic endpoint."""
    global _cached_minimax_anthropic_client, _cached_minimax_anthropic_key

    import anthropic

    cache_key = f"{settings.minimax_api_key}:{settings.minimax_base_url}"
    if _cached_minimax_anthropic_client is None or _cached_minimax_anthropic_key != cache_key:
        _cached_minimax_anthropic_client = anthropic.Anthropic(
            api_key=settings.minimax_api_key,
            base_url=settings.minimax_base_url,
            timeout=600.0,
            max_retries=2,
        )
        _cached_minimax_anthropic_key = cache_key
    return _cached_minimax_anthropic_client


def _get_client(settings: LyraSettings):
    """Return the appropriate Anthropic SDK client for the configured backend."""
    if settings.llm_backend == "minimax":
        return _get_minimax_anthropic_client(settings)
    return _get_anthropic_client(settings.anthropic_api_key)


# ---------------------------------------------------------------------------
# Structured output via tool-use trick (MiniMax)
# ---------------------------------------------------------------------------


def _build_structured_output_tool(schema: dict) -> dict:
    """Build an Anthropic tool definition that forces JSON matching the schema.

    MiniMax's Anthropic endpoint accepts output_config/json_schema but does NOT
    enforce it on M3 — verified 2026-06-01 it returned fenced/invalid JSON
    (e.g. `{relevant: true}`). So we force the model to "call" a tool whose
    input_schema IS the schema. Combined with
    tool_choice={"type": "tool", "name": "structured_output"}, the model must
    produce valid JSON matching the schema.
    """
    return {
        "name": "structured_output",
        "description": (
            "Return the result by calling THIS tool with structured JSON. "
            "You MUST call structured_output — never answer in prose or explain. "
            "If you have no data, call it with empty arrays/strings rather than "
            "replying with text. All fields are required and must match the "
            "schema exactly."
        ),
        "input_schema": schema,
    }


def _text_parses_as_json(content: list) -> bool:
    """True if any text block in the response parses as JSON (markdown fences
    stripped). Used to decide whether a missing tool_use block is still usable —
    M3 frequently emits valid JSON as text instead of calling the forced tool,
    and that is perfectly fine, so it should NOT trigger a retry.
    """
    for block in content or []:
        if getattr(block, "type", None) == "text":
            cleaned = (getattr(block, "text", "") or "").strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
                cleaned = cleaned.rsplit("```", 1)[0].strip()
            try:
                json.loads(cleaned)
                return True
            except (json.JSONDecodeError, ValueError):
                continue
    return False


def _extract_tool_use_json(content: list) -> str | None:
    """Extract JSON string from a tool_use block in the response.

    Scans content blocks (skipping thinking blocks) for a tool_use block
    named 'structured_output'. Returns the input as a JSON string,
    or None if no tool_use block is found.
    """
    for block in content:
        if (
            getattr(block, "type", None) == "tool_use"
            and getattr(block, "name", None) == "structured_output"
        ):
            return json.dumps(block.input)
    return None


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
    timeout: float | None = None,
    **kwargs,
) -> NormalizedResponse:
    """Unified LLM call — dispatches to Anthropic or MiniMax via Anthropic SDK.

    Both backends use the same code path. MiniMax differences (model override,
    structured output via tool trick, temperature clamping) are handled inside
    _call_anthropic_api().
    """
    settings = _get_settings()

    try:
        return _call_anthropic_api(
            settings, prefill=prefill, documents=documents, timeout=timeout, **kwargs
        )
    except LyraAPIError:
        raise
    except Exception as e:
        raise LyraAPIError(f"{settings.llm_backend.title()} API error: {e}") from e
