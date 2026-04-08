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
    dedup_similarity_threshold: float = 0.25

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

    # Article web verification backend: "minimax" (MiniMax search API + M2.7
    # per-section structured corrections) or "anthropic" (Opus + web_search tool)
    article_web_backend: str = "minimax"

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


def _get_anthropic_client(api_key: str):
    """Return a cached synchronous Anthropic client."""
    global _cached_anthropic_client, _cached_anthropic_key

    import anthropic

    if _cached_anthropic_client is None or _cached_anthropic_key != api_key:
        _cached_anthropic_client = anthropic.Anthropic(api_key=api_key, timeout=120.0)
        _cached_anthropic_key = api_key
    return _cached_anthropic_client


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
    kwargs.pop("reasoning_effort", None)

    model = kwargs.pop("model", settings.model_summarize)
    max_tokens = kwargs.pop("max_tokens", settings.max_tokens)
    temperature = kwargs.pop("temperature", None)
    top_p = kwargs.pop("top_p", None)

    # [MINIMAX] Adaptation 1: Model override — all calls use MiniMax-M2.7
    if is_minimax:
        model = "MiniMax-M2.7"

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
    elif temperature is not None:
        # [MINIMAX] Adaptation 4: Temperature clamping (0,1] — exclusive of 0
        if is_minimax and temperature <= 0.0:
            temperature = 0.01
        else:
            temperature = max(settings.temperature_min, temperature)
        create_kwargs["temperature"] = temperature

    if top_p is not None:
        create_kwargs["top_p"] = top_p

    if timeout is not None:
        import httpx

        create_kwargs["timeout"] = httpx.Timeout(timeout, connect=30.0)

    # --- Make the API call ---
    response = client.messages.create(**create_kwargs)

    # --- Normalize the response ---
    # [MINIMAX] Adaptation 5: Extract tool result if tool-use trick was used
    if use_tool_trick:
        tool_json = _extract_tool_use_json(response.content)
        if tool_json is not None:
            stop_reason = response.stop_reason or "end_turn"
            return NormalizedResponse(
                content=[TextBlock(text=tool_json)],
                stop_reason=stop_reason,
                model=response.model or "",
                usage={
                    "input_tokens": response.usage.input_tokens if response.usage else 0,
                    "output_tokens": response.usage.output_tokens if response.usage else 0,
                },
            )
        logger.warning("MiniMax did not return tool_use block — falling back to text response")

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
    return NormalizedResponse(
        content=blocks,
        stop_reason=stop_reason,
        model=response.model or "",
        usage={
            "input_tokens": response.usage.input_tokens if response.usage else 0,
            "output_tokens": response.usage.output_tokens if response.usage else 0,
        },
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

    MiniMax's Anthropic endpoint doesn't support output_config/json_schema,
    so we force the model to "call" a tool whose input_schema IS the schema.
    Combined with tool_choice={"type": "tool", "name": "structured_output"},
    the model must produce valid JSON matching the schema.
    """
    return {
        "name": "structured_output",
        "description": (
            "Return the result as structured JSON. "
            "All fields are required and must match the schema exactly."
        ),
        "input_schema": schema,
    }


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
