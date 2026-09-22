"""Shared MiniMax utilities for search and M3 chat.

Used by the article verification pipeline (web_research.py), Theo's
convergence orchestrator, and the standalone relevancy gate.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, NamedTuple

import httpx

logger = logging.getLogger(__name__)


class MiniMaxAuthError(RuntimeError):
    """Terminal MiniMax failure no retry can fix (invalid/expired key, 403).

    Raised instead of the old silent `return ""` — an auth-dead key producing
    empty specialists/audits/prose for hours was the root cause of the empty
    papers on 2026-06-03/06-17. Non-auth terminal failures raise
    MiniMaxTerminalError (per-handler audit completed 2026-08-06).
    """


class MiniMaxTerminalError(RuntimeError):
    """Non-auth terminal MiniMax failure after all retries are exhausted.

    Replaces the old silent-empty returns: `minimax_chat_anthropic` /
    `minimax_chat` returning "" and `structured_llm_call` returning {}
    after their final retry. Those empties cascaded into empty specialist
    findings, fake debate convergence, and near-empty papers discovered
    hours later — the failure class behind the 2026-06-03/06-17 incidents.

    NOT for quota errors: budget exhaustion / persistent plan throttling
    stay QuotaExhaustedError / InsufficientQuotaError, which the worker's
    defer path needs to mark runs 'deferred' instead of 'failed'.

    Optional stages (image queries, illustration picks, presentation
    polish, card description, novelty check, cross-pollination enrichment)
    catch this at the call site, log a WARNING with the stage name, and
    run their explicit degraded path. Everything else lets it propagate —
    the EventBus/orchestrator failure path records it into state.error.
    """


def _is_auth_error(err: object) -> bool:
    """Match HTTP 401/403 / auth wording in an error string."""
    s = str(err or "").lower()
    return (
        re.search(r"\b40[13]\b", s) is not None or "authentication" in s or "invalid api key" in s
    )


from pipeline.lyra.minimax_limiter import (
    InsufficientQuotaError,
    QuotaExhaustedError,
    is_plan_rate_throttle,
    is_quota_error,
)

# ---------------------------------------------------------------------------
# Shared LLM-output parsing helpers — the ONE canonical implementation of the
# fence-strip + json.loads block (and the <think>-tag strip) that used to be
# copy-pasted across ~12 modules (audit P7-17).
# ---------------------------------------------------------------------------

# M3 wraps reasoning in <think>...</think> tags.
_THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL)

# Sentinel for parse_fenced_json: "no default — re-raise the parse error".
_PARSE_RAISE = object()


def strip_think_tags(text: str) -> str:
    """Strip M3 ``<think>...</think>`` reasoning blocks and trim whitespace."""
    return _THINK_TAG_RE.sub("", text or "").strip()


def strip_code_fences(text: str) -> str:
    """Strip a wrapping markdown code fence (```json ... ```) if present."""
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        cleaned = cleaned.rsplit("```", 1)[0].strip()
    return cleaned


def parse_fenced_json(
    text: str,
    *,
    default: object = _PARSE_RAISE,
    extract_object: bool = False,
    log_label: str = "",
) -> dict | list:
    """Parse JSON from an LLM response, stripping markdown fences first.

    Args:
        default: value returned when parsing fails. When omitted, the
            ``json.JSONDecodeError`` propagates to the caller (callers with
            their own try/except keep their existing error handling).
        extract_object: on parse failure, additionally try the outermost
            ``{...}`` block in the text (LLMs love prepending prose).
        log_label: when set, a parse failure that returns ``default`` is
            logged as a WARNING tagged with this label so call sites stay
            distinguishable in the logs.
    """
    cleaned = strip_code_fences(text)
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        if extract_object:
            m = re.search(r"\{[\s\S]*\}", cleaned)
            if m:
                try:
                    return json.loads(m.group(0))
                except (json.JSONDecodeError, ValueError):
                    pass
        if default is _PARSE_RAISE:
            raise
        if log_label:
            logger.warning("%s: failed to parse JSON: %s", log_label, cleaned[:200])
        return default  # type: ignore[return-value]


# MiniMax model — single source of truth for every call site (config.py,
# web_research.py, tweet_verifier.py, research_stages.py all import this).
# Upgraded M3 → M3 on 2026-06-01; verified live via the Anthropic endpoint
# (MiniMax-M3.0 aliases to MiniMax-M3; M3 still served as the prior model).
# Env-overridable so a successor model (e.g. M3 Pro, expected Q3 2026) can be
# switched on the VPS without a code deploy: set MINIMAX_MODEL in .env.
MINIMAX_MODEL = os.getenv("MINIMAX_MODEL", "MiniMax-M3")

# MiniMax search endpoint (Token Plan / Coding Plan)
MINIMAX_SEARCH_PATH = "/v1/coding_plan/search"
MINIMAX_SEARCH_TIMEOUT = 15.0
MINIMAX_CHAT_PATH = "/v1/chat/completions"
MINIMAX_CHAT_TIMEOUT = 300.0  # 5 min — M3 reasoning + long paper generation needs time


@dataclass
class WebSearchResult:
    """A single web search result."""

    title: str
    url: str
    snippet: str
    date: str = ""


def create_minimax_client(base_url: str, api_key: str) -> httpx.Client:
    """Create an httpx client configured for MiniMax API calls.

    Strips /anthropic suffix if present — this client uses the OpenAI-compatible
    endpoints (/v1/coding_plan/search, /v1/chat/completions), not the Anthropic
    endpoint.  The setting minimax_base_url may point to the Anthropic endpoint
    for the Anthropic SDK, but raw httpx callers need the base URL.
    """
    if base_url.endswith("/anthropic"):
        base_url = base_url.removesuffix("/anthropic")
    return httpx.Client(
        base_url=base_url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        timeout=MINIMAX_SEARCH_TIMEOUT,
    )


# --- Coding-plan endpoints (search, VLM): one strict call, typed errors ------
# `/v1/coding_plan/search` and `/v1/coding_plan/vlm` share one failure grammar:
# an HTTP status, and inside a 2xx body a `base_resp.status_code` that is 0 on
# success (docs/research/minimax-web-search-mcp-research.md: 1004 invalid key,
# 2038 real-name verification; minimax_limiter: 2056 budget, 2062 plan rate
# cap). Until 2026-09-22 both helpers turned every one of those into an empty
# result, so "the key is dead" and "nothing was found" were the same value.
# The strict functions below raise instead; `minimax_search` / `minimax_vlm`
# stay as thin wrappers that keep their callers' empty-on-failure behaviour.

#: `base_resp.status_code` values that mean the account cannot use the
#: endpoint at all: an invalid key (1004) and a missing real-name
#: verification (2038). No retry changes either, so both are auth failures.
_CODING_PLAN_AUTH_CODES = frozenset({1004, 2038})


class CodingPlanError(RuntimeError):
    """A `/v1/coding_plan/*` call that produced no usable answer.

    `http_status` is the status that arrived (None when no response arrived
    at all) and `body_bytes` the length of the body that was read, so a
    caller that records every request - the phase-3 search stage writes one
    ledger line per call - can do so without re-deriving either.
    """

    def __init__(self, message: str, *, http_status: int | None = None, body_bytes: int = 0):
        super().__init__(message)
        self.http_status = http_status
        self.body_bytes = body_bytes


class CodingPlanTransportError(CodingPlanError):
    """No response arrived (DNS, connect, TLS, reset, timeout mid-body)."""


class CodingPlanAuthError(MiniMaxAuthError, CodingPlanError):
    """401/403, an auth-worded error body, or base_resp 1004/2038."""


class CodingPlanQuotaError(QuotaExhaustedError, CodingPlanError):
    """The plan's budget is spent (2056 / 'usage limit reached')."""


class CodingPlanThrottleError(CodingPlanError):
    """The plan's short-window rate cap (2062): a trough, not the budget."""


class CodingPlanHTTPError(MiniMaxTerminalError, CodingPlanError):
    """Any other non-2xx answer (5xx, a plain 429, 400, 404 ...)."""


class CodingPlanResponseError(CodingPlanError):
    """A 2xx answer that carries no usable result: a body that is not JSON,
    a non-zero `base_resp.status_code` that is none of the codes above, or a
    required field (`organic`, `content`) that is absent or empty."""


class CodingPlanShapeError(CodingPlanError):
    """A 2xx JSON body that contradicts the documented shape (not an object,
    `organic` not a list, a result that is not an object, `content` that is
    not text). A contract break, not an empty answer."""


def _coding_plan_post(
    client: httpx.Client, path: str, payload: dict, *, timeout: float | None = None
) -> httpx.Response:
    """POST once. Only a transport failure is turned into a typed error here."""
    try:
        if timeout is None:
            return client.post(path, json=payload)
        return client.post(path, json=payload, timeout=timeout)
    except httpx.HTTPError as exc:
        raise CodingPlanTransportError(f"POST {path}: {type(exc).__name__}: {exc}") from exc


def _raise_for_coding_plan_status(resp: httpx.Response, *, what: str) -> None:
    """Raise the typed error a non-2xx answer stands for. A 2xx returns."""
    status = resp.status_code
    if 200 <= status < 300:
        return
    body = resp.text or ""
    size = len(resp.content)
    detail = f"{what}: HTTP {status}: {body[:300]}"
    if status in (401, 403):
        raise CodingPlanAuthError(detail, http_status=status, body_bytes=size)
    # Budget before throttle: a body carrying both markers is read as the
    # budget (minimax_limiter.is_plan_rate_throttle's own rule).
    if is_quota_error(body):
        raise CodingPlanQuotaError(detail, http_status=status, body_bytes=size)
    if is_plan_rate_throttle(body):
        raise CodingPlanThrottleError(detail, http_status=status, body_bytes=size)
    if _is_auth_error(body):
        raise CodingPlanAuthError(detail, http_status=status, body_bytes=size)
    raise CodingPlanHTTPError(detail, http_status=status, body_bytes=size)


def _coding_plan_json(resp: httpx.Response, *, what: str) -> dict[str, Any]:
    """The 2xx body as a JSON object whose `base_resp` signals no error.

    A `base_resp` without a `status_code` signals nothing and is accepted;
    a present, non-zero code raises the typed error it stands for.
    """
    status = resp.status_code
    size = len(resp.content)
    try:
        data = resp.json()
    except ValueError as exc:  # json.JSONDecodeError and UnicodeDecodeError
        raise CodingPlanResponseError(
            f"{what}: HTTP {status} body is not JSON: {exc}", http_status=status, body_bytes=size
        ) from exc
    if not isinstance(data, dict):
        raise CodingPlanShapeError(
            f"{what}: HTTP {status} body is {type(data).__name__}, not a JSON object",
            http_status=status,
            body_bytes=size,
        )
    base = data.get("base_resp")
    if base is None:
        return data
    if not isinstance(base, dict):
        raise CodingPlanShapeError(
            f"{what}: base_resp is {type(base).__name__}, not an object",
            http_status=status,
            body_bytes=size,
        )
    code = base.get("status_code")
    if code is None:
        return data
    if not isinstance(code, int) or isinstance(code, bool):
        raise CodingPlanShapeError(
            f"{what}: base_resp.status_code={code!r} is not an integer",
            http_status=status,
            body_bytes=size,
        )
    if code == 0:
        return data
    message = base.get("status_msg")
    detail = f"{what}: base_resp.status_code={code} ({message!r})"
    marker = f"{message} ({code})"
    if code in _CODING_PLAN_AUTH_CODES:
        raise CodingPlanAuthError(detail, http_status=status, body_bytes=size)
    if is_quota_error(marker):
        raise CodingPlanQuotaError(detail, http_status=status, body_bytes=size)
    if is_plan_rate_throttle(marker):
        raise CodingPlanThrottleError(detail, http_status=status, body_bytes=size)
    raise CodingPlanResponseError(detail, http_status=status, body_bytes=size)


class SearchHit(NamedTuple):
    """One organic result that names a page, with its 1-based engine rank."""

    rank: int
    result: WebSearchResult


@dataclass(frozen=True)
class SearchResponse:
    """One answered search.

    `items` is every organic entry in engine order, built exactly as the
    legacy loop built them (`.get(key, "")`) - that is what `minimax_search`
    returns, so its three callers see the same objects as before. `hits` is
    the strict view: only the entries whose `link` is a non-empty string, each
    with its engine rank. An entry without a link names no page and cannot be
    cited; it is counted in `linkless`, never turned into a url of "".
    """

    query: str
    items: tuple[WebSearchResult, ...]
    http_status: int
    body_bytes: int

    @property
    def hits(self) -> tuple[SearchHit, ...]:
        return tuple(
            SearchHit(rank=rank, result=item)
            for rank, item in enumerate(self.items, start=1)
            if isinstance(item.url, str) and item.url
        )

    @property
    def linkless(self) -> int:
        return len(self.items) - len(self.hits)


def minimax_search_strict(client: httpx.Client, query: str) -> SearchResponse:
    """Call the MiniMax search endpoint once; raise a typed error on failure.

    `organic: []` is a real "no hits" and comes back as an empty response;
    a body without `organic` is not one and raises. Nothing is retried here.
    """
    what = f"MiniMax search {query!r}"
    resp = _coding_plan_post(client, MINIMAX_SEARCH_PATH, {"q": query})
    _raise_for_coding_plan_status(resp, what=what)
    data = _coding_plan_json(resp, what=what)
    status = resp.status_code
    size = len(resp.content)
    if "organic" not in data:
        raise CodingPlanResponseError(
            f"{what}: the answer carries no `organic` field", http_status=status, body_bytes=size
        )
    organic = data["organic"]
    if not isinstance(organic, list):
        raise CodingPlanShapeError(
            f"{what}: `organic` is {type(organic).__name__}, not a list",
            http_status=status,
            body_bytes=size,
        )
    items: list[WebSearchResult] = []
    for position, item in enumerate(organic, start=1):
        if not isinstance(item, dict):
            raise CodingPlanShapeError(
                f"{what}: organic result {position} is {type(item).__name__}, not an object",
                http_status=status,
                body_bytes=size,
            )
        items.append(
            WebSearchResult(
                title=item.get("title", ""),
                url=item.get("link", ""),
                snippet=item.get("snippet", ""),
                date=item.get("date", ""),
            )
        )
    return SearchResponse(query=query, items=tuple(items), http_status=status, body_bytes=size)


def minimax_search(client: httpx.Client, query: str) -> list[WebSearchResult]:
    """Call MiniMax search endpoint. Legacy contract: a failed call is ``[]``.

    A thin wrapper over `minimax_search_strict` for the three callers written
    against that contract (web_research.MiniMaxWebResearch._search,
    tweet_verifier._web_verify_items, theo_sources.MiniMaxSearchAdapter).
    For the documented success body and every HTTP, transport and JSON failure
    the result is the same as before, entries without a link included.
    Differences, all outside that envelope: a 2xx body whose ``base_resp``
    reports an error is ``[]`` even if it also carries results (the old code
    read them as hits); a contract break (`CodingPlanShapeError`) raises, as
    the old code raised AttributeError/TypeError on the same bodies - except
    an `organic` that is an empty non-list, which the old loop read as ``[]``;
    and an exception from the client that is not an ``httpx.HTTPError``
    (a malformed base URL's InvalidURL) propagates instead of reading as ``[]``.
    """
    try:
        return list(minimax_search_strict(client, query).items)
    except CodingPlanShapeError:
        raise
    except CodingPlanError as e:
        logger.warning(f"MiniMax search failed for '{query}': {e}")
        return []


def minimax_chat(
    client: httpx.Client,
    model: str,
    system: str,
    user_message: str,
    max_tokens: int,
) -> str:
    """Call MiniMax M3 chat completion, strip thinking tags.

    Retries up to 3 times on 429 rate limit with exponential backoff.
    """
    max_retries = 3
    for attempt in range(max_retries + 1):
        try:
            resp = client.post(
                MINIMAX_CHAT_PATH,
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_message},
                    ],
                    "max_tokens": max_tokens,
                },
                timeout=MINIMAX_CHAT_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            break
        except Exception as e:
            err_str = str(e)
            is_retryable = "429" in err_str or "10054" in err_str or "timed out" in err_str
            if is_retryable and attempt < max_retries:
                wait = 3 * (attempt + 1)  # 3, 6, 9 seconds
                logger.info(f"MiniMax error ({err_str[:50]}), retrying in {wait}s...")
                time.sleep(wait)
                continue
            if _is_auth_error(e):
                raise MiniMaxAuthError(f"MiniMax auth failure: {e}") from e
            logger.error(f"MiniMax M3 chat failed terminally: {e}")
            raise MiniMaxTerminalError(f"MiniMax M3 chat failed terminally: {e}") from e

    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    # M3 wraps reasoning in <think>...</think> tags -- strip them
    return strip_think_tags(content)


def minimax_chat_anthropic(
    system: str,
    user_message: str,
    max_tokens: int,
    settings=None,
    *,
    temperature: float | None = None,
    thinking: dict | None = None,
) -> str:
    """Call MiniMax-M3 via the Anthropic SDK (unified plain-text path).

    This replaces the old httpx-based minimax_chat() for the Theo pipeline.
    Uses the same Anthropic SDK client as the Lyra pipeline.

    `temperature` is keyword-only. When None, MiniMax picks its own default
    (≈1.0 for M3). Theo V2 handlers should always pass an explicit stage
    temperature from LyraSettings (temperature_research/synthesis/verification/narrative).

    `thinking` is an optional MiniMax-M3 thinking block. The only modes M3
    honors are ``{"type": "adaptive"}`` (reasoning ON) and
    ``{"type": "disabled"}`` (reasoning OFF) — ``budget_tokens`` is ignored
    (verified 2026-06-16). This is the narrative/synthesis path, which is
    quality-critical for reasoning, so when the caller passes None we DEFAULT
    TO ADAPTIVE. Mechanical callers that want the lean path should pass
    ``{"type": "disabled"}`` explicitly. thinking and temperature coexist on M3.
    """
    from pipeline.lyra.config import (
        _MINIMAX_ADAPTIVE_MAX_TOKENS_FLOOR,
        _get_minimax_anthropic_client,
        _get_settings,
    )

    if settings is None:
        settings = _get_settings()

    client = _get_minimax_anthropic_client(settings)

    # Narrative/synthesis benefits from full reasoning (2026-06-03 A/B: adaptive
    # thinking gave 100% source-grounding vs 75% bounded), so default to adaptive
    # here. (This is the prose path; the structured/mechanical calls go through
    # call_api with thinking OFF unless they pass reasoning_effort.)
    if thinking is None:
        thinking = {"type": "adaptive"}

    # M3's adaptive thinking shares the output budget and is effectively unbounded
    # (budget_tokens ignored), so a small max_tokens lets reasoning starve the
    # answer. When thinking is ON, raise max_tokens to a generous floor.
    if isinstance(thinking, dict) and thinking.get("type") == "adaptive":
        if max_tokens < _MINIMAX_ADAPTIVE_MAX_TOKENS_FLOOR:
            max_tokens = _MINIMAX_ADAPTIVE_MAX_TOKENS_FLOOR

    # MiniMax requires temperature in (0, 1] — clamp any <=0 up to 0.01.
    create_kwargs: dict = {
        "model": MINIMAX_MODEL,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user_message}],
    }
    if thinking is not None:
        create_kwargs["thinking"] = thinking
    if temperature is not None:
        create_kwargs["temperature"] = 0.01 if temperature <= 0.0 else temperature
    # MiniMax sampling/latency knobs (default None -> inert). Mirrors config.py.
    if settings.minimax_top_p is not None:
        create_kwargs["top_p"] = settings.minimax_top_p
    if settings.minimax_service_tier:
        create_kwargs["extra_body"] = {"service_tier": settings.minimax_service_tier}

    from pipeline.lyra.minimax_limiter import limiter

    last_error = None
    for attempt in range(3):
        with limiter.request() as slot:
            try:
                response = client.messages.create(**create_kwargs)
                slot.report_success()
                # Extract text from response, skipping ThinkingBlock objects
                parts = []
                for block in response.content or []:
                    if hasattr(block, "text"):
                        parts.append(block.text)
                content = "\n".join(parts)
                # M3 may still wrap reasoning in <think>...</think> tags -- strip them
                clean = strip_think_tags(content)
                # Surface silent truncation: M3's interleaved thinking can
                # consume the entire max_tokens budget, leaving zero/partial
                # output. Log it so the caller can raise max_tokens if needed.
                stop_reason = getattr(response, "stop_reason", None)
                if stop_reason == "max_tokens":
                    logger.warning(
                        "MiniMax M3 hit max_tokens=%d before finishing output "
                        "(output len=%d chars). Consider raising the budget.",
                        max_tokens,
                        len(clean),
                    )
                # Credit tokens back to the active ResearchState if any —
                # otherwise minimax_chat_anthropic calls (which bypass
                # call_api) would never advance state.total_tokens.
                # usage_to_dict includes the cache_read/cache_creation fields
                # (omitting them undercounted runs ~20x, 2026-07-19).
                try:
                    from pipeline.lyra import token_accounting

                    token_accounting.add_usage(
                        token_accounting.usage_to_dict(getattr(response, "usage", None))
                    )
                except Exception:
                    pass
                return clean
            except Exception as e:
                last_error = e
                error_str = str(e)
                is_rate_limit = "429" in error_str or "rate_limit" in error_str
                is_quota = is_rate_limit and is_quota_error(error_str)
                is_throttle = is_rate_limit and is_plan_rate_throttle(error_str)
                is_transient = is_rate_limit or any(
                    code in error_str
                    for code in ("500", "520", "529", "503", "timeout", "timed out")
                )
                if is_quota:
                    # Budget exhaustion (2056/credits) — freeze the limiter
                    # and fail fast. The window must reset; retrying only
                    # wastes wall clock. The orchestrator catches this and
                    # sets status='deferred'.
                    slot.report_quota_exhausted()
                    logger.error(
                        "MiniMax M3 quota exhausted (no retry): %s",
                        e,
                    )
                    raise QuotaExhaustedError(
                        f"MiniMax quota exhausted during M3 call: {error_str[:200]}"
                    ) from e
                if is_throttle:
                    # Plan rate cap (2062) — a short-window throttle, NOT the
                    # budget (2026-07-29: fired at 5h=71% remaining and killed
                    # a 15h run). Sub-minute retries land in the same window,
                    # so back off long enough to roll it. A throttle that
                    # persists through every backoff is a genuine trough:
                    # freeze + typed raise so the worker defers, not fails.
                    slot.report_rate_limit()
                    if attempt < 2:
                        delay = 60 * (attempt + 1)
                        logger.warning(
                            "MiniMax M3 plan rate limit (attempt %d/3), retrying in %ds: %s",
                            attempt + 1,
                            delay,
                            e,
                        )
                        import time

                        time.sleep(delay)
                        continue
                    slot.report_quota_exhausted()
                    logger.error("MiniMax M3 plan rate limit persisted through backoff: %s", e)
                    raise QuotaExhaustedError(
                        f"MiniMax plan rate limit persisted through backoff: {error_str[:200]}"
                    ) from e
                if is_rate_limit:
                    slot.report_rate_limit()
                if is_transient and attempt < 2:
                    is_overload = "529" in error_str or "overloaded" in error_str
                    delay = (attempt + 1) * (10 if is_overload else 3)
                    logger.warning(
                        "MiniMax M3 transient error (attempt %d/3), retrying in %ds: %s",
                        attempt + 1,
                        delay,
                        e,
                    )
                    import time

                    time.sleep(delay)
                    continue
                break

    if _is_auth_error(last_error):
        raise MiniMaxAuthError(f"MiniMax auth failure: {last_error}") from (
            last_error if isinstance(last_error, BaseException) else None
        )
    logger.error(
        f"MiniMax M3 Anthropic SDK call failed terminally after {attempt + 1} attempts: "
        f"{last_error}"
    )
    raise MiniMaxTerminalError(
        f"MiniMax M3 Anthropic SDK call failed terminally after {attempt + 1} attempts: "
        f"{last_error}"
    ) from (last_error if isinstance(last_error, BaseException) else None)


# --- Quota probe --------------------------------------------------------
# GET /v1/token_plan/remains is the documented MiniMax endpoint for the
# 5h-rolling and weekly Token Plan usage. Used by the orchestrator to refuse
# new runs when the 5h budget is too low to finish. See plan
# docs/superpowers/plans/2026-06-28-theo-rate-limit-defense.md Layer 2.

MINIMAX_TOKEN_PLAN_REMAINS_PATH = "/v1/token_plan/remains"  # noqa: S105 (URL path, not password)
MINIMAX_TOKEN_PLAN_REMAINS_TIMEOUT = 10.0
_QUOTA_CACHE_TTL_SECONDS = 60.0

_quota_cache: dict[str, tuple[float, dict]] = {}
_quota_cache_lock = threading.Lock()


def probe_minimax_quota(force: bool = False) -> dict:
    """Probe the MiniMax Token Plan remaining quota.

    Returns a dict — on success the keys match whatever the MiniMax
    endpoint returns (typical: five_hour_remaining, five_hour_limit,
    weekly_remaining, weekly_limit — but accept anything). On any HTTP
    error (404 if the endpoint doesn't exist on this plan, 401, timeout)
    returns {"ok": False, "error": "<reason>"} so the caller can treat
    the quota as "unknown" and decide accordingly.

    Cached for 60s to avoid hammering the endpoint on every run; pass
    force=True to bypass.
    """
    cache_key = "quota"
    now = time.monotonic()
    if not force:
        with _quota_cache_lock:
            cached = _quota_cache.get(cache_key)
            if cached and (now - cached[0]) < _QUOTA_CACHE_TTL_SECONDS:
                return cached[1]

    from pipeline.lyra.config import _get_settings  # avoid cycle

    settings = _get_settings()
    api_key = getattr(settings, "minimax_api_key", "") or ""
    base_url = getattr(settings, "minimax_base_url", "") or ""
    if not api_key or not base_url:
        result = {"ok": False, "error": "no_api_key_or_base_url"}
    else:
        try:
            # Raw httpx — /v1/token_plan/remains isn't an Anthropic-SDK path.
            with create_minimax_client(base_url, api_key) as client:
                resp = client.get(
                    MINIMAX_TOKEN_PLAN_REMAINS_PATH,
                    timeout=MINIMAX_TOKEN_PLAN_REMAINS_TIMEOUT,
                )
            if resp.status_code == 200:
                data = resp.json() if resp.content else {}
                data["ok"] = True
                # Normalise the MiniMax-native field names into a stable
                # shape callers can rely on. The endpoint returns a
                # `model_remains` array (one entry per model family) —
                # pick the "general" model which is what M3 falls under.
                if isinstance(data.get("model_remains"), list):
                    for entry in data["model_remains"]:
                        if entry.get("model_name") in ("general", MINIMAX_MODEL):
                            data["five_hour_remaining_percent"] = entry.get(
                                "current_interval_remaining_percent"
                            )
                            data["weekly_remaining_percent"] = entry.get(
                                "current_weekly_remaining_percent"
                            )
                            data["five_hour_end_time"] = entry.get("end_time")
                            data["weekly_end_time"] = entry.get("weekly_end_time")
                            # Absolute token balances — the ONLY trustworthy
                            # cost signal. The API `usage` field (our
                            # total_tokens) misses billed reasoning tokens by
                            # ~7.7x, measured 2026-08-07. The worker snapshots
                            # weekly_remains_time at run start/end to measure
                            # what a paper really costs.
                            data["weekly_remains_tokens"] = entry.get("weekly_remains_time")
                            data["five_hour_remains_tokens"] = entry.get("remains_time")
                            data["weekly_start_time"] = entry.get("weekly_start_time")
                            break
                result = data
            else:
                result = {
                    "ok": False,
                    "error": f"http_{resp.status_code}",
                    "body": (resp.text or "")[:300],
                }
        except Exception as exc:  # noqa: BLE001 — quota probe must never raise
            result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:200]}

    with _quota_cache_lock:
        _quota_cache[cache_key] = (now, result)
    return result


def clear_quota_cache() -> None:
    """Drop the cached quota probe (used by tests + after a manual unfreeze)."""
    with _quota_cache_lock:
        _quota_cache.clear()


def hours_until_weekly_reset(now_utc: datetime) -> float:
    """Hours until the next MiniMax weekly reset (Monday 00:00 UTC).

    Moved here from api/services/theo_worker.py (2026-09-22) so the phase-3
    search stage, which runs without the api package, reads Theo's batch
    window off the same function instead of a copy of it.
    """
    days_ahead = (7 - now_utc.weekday()) % 7
    reset = (now_utc + timedelta(days=days_ahead)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    if reset <= now_utc:
        reset += timedelta(days=7)
    return (reset - now_utc).total_seconds() / 3600


# --- /Quota probe -------------------------------------------------------


MINIMAX_VLM_PATH = "/v1/coding_plan/vlm"
MINIMAX_VLM_TIMEOUT = 90.0


def minimax_vlm_strict(client: httpx.Client, image_bytes: bytes, prompt: str) -> str:
    """Call MiniMax's Coding-Plan VLM endpoint once; raise a typed error on failure.

    Returns the model's non-empty `content` string (the caller parses JSON
    out of it). The endpoint answers 200; any other 2xx is not its answer.
    """
    import base64

    what = "MiniMax VLM"
    data_uri = f"data:image/jpeg;base64,{base64.b64encode(image_bytes).decode('ascii')}"
    resp = _coding_plan_post(
        client,
        MINIMAX_VLM_PATH,
        {"prompt": prompt, "image_url": data_uri},
        timeout=MINIMAX_VLM_TIMEOUT,
    )
    _raise_for_coding_plan_status(resp, what=what)
    status = resp.status_code
    size = len(resp.content)
    if status != 200:
        raise CodingPlanResponseError(
            f"{what}: HTTP {status}, not the 200 this endpoint answers with",
            http_status=status,
            body_bytes=size,
        )
    data = _coding_plan_json(resp, what=what)
    content = data.get("content")
    if content is None:
        raise CodingPlanResponseError(
            f"{what}: the answer carries no `content`", http_status=status, body_bytes=size
        )
    if not isinstance(content, str):
        raise CodingPlanShapeError(
            f"{what}: `content` is {type(content).__name__}, not text",
            http_status=status,
            body_bytes=size,
        )
    if not content:
        raise CodingPlanResponseError(
            f"{what}: `content` is empty", http_status=status, body_bytes=size
        )
    return content


def minimax_vlm(client: httpx.Client, image_bytes: bytes, prompt: str) -> str:
    """Call MiniMax's Coding-Plan VLM endpoint for image understanding.

    Legacy contract: returns the model's `content` string, or an empty string
    for any failure, so callers can treat absence as a reject verdict. A thin
    wrapper over `minimax_vlm_strict` for the callers written against that
    contract (handlers/probative_images, video/shorts_select,
    scripts/pick_meaningful_gallery and two e2e scripts). For the documented
    success body and every HTTP, transport and JSON failure the result is the
    same as before. Differences, all outside that envelope: a 200 whose
    ``base_resp`` reports an error, or whose `content` is not text, is ``""``
    (the old code returned what it found); and an exception from the client
    that is not an ``httpx.HTTPError`` (a malformed base URL's InvalidURL, a
    test double's RuntimeError) propagates instead of reading as a reject.
    """
    try:
        return minimax_vlm_strict(client, image_bytes, prompt)
    except CodingPlanError as exc:
        logger.warning("MiniMax VLM failed: %s", exc)
        return ""


def _coerce_to_schema(value, schema: dict, path: str = "") -> object:
    """Drop schema-violating items from an LLM response in place.

    MiniMax (and any other tool-use trick LLM under load) periodically
    emits a *bare string* inside an array typed as `items: {type: object}`,
    even with json_schema. Every downstream handler that iterates the
    array and calls `.get()` on items then crashes with
    `AttributeError("'str' object has no attribute 'get'")` — that's the
    pattern that took down four separate Theo handlers in a single
    debugging session (cross_pollination, decomposition, angle_audit,
    angle_specialist) and forced four near-identical isinstance() guards.

    Instead of guarding at every consumer, normalise at the boundary:
    walk the response against the schema and drop anything whose runtime
    type doesn't match the declared type. The handlers then receive a
    well-shaped dict and don't need per-site guards (the existing ones
    stay as belt-and-braces).

    Supported schema types: object (with properties + additionalProperties),
    array (with items), string, integer, number, boolean. Unknown types
    pass through unchanged.
    """
    if not isinstance(schema, dict):
        return value
    expected = schema.get("type")

    # JSON-schema union types — `"type": ["string", "null"]` etc. Coerce
    # only when ALL alternatives are primitive scalars; if any is "object"
    # or "array" we'd have to combine multiple structural walks, which
    # nobody in this codebase needs yet. Pass the value through unchanged
    # when it matches any of the listed types.
    if isinstance(expected, list):
        type_map = {
            "string": (str,),
            "integer": (int,),
            "number": (int, float),
            "boolean": (bool,),
            "null": (type(None),),
            "object": (dict,),
            "array": (list,),
        }
        runtime_types: tuple = ()
        for t in expected:
            runtime_types += type_map.get(t, ())
        if not runtime_types or isinstance(value, runtime_types):
            return value
        logger.warning(
            "schema-coerce: expected one of %s at %s, got %s — dropping",
            expected,
            path or "<root>",
            type(value).__name__,
        )
        return _SCHEMA_DROP

    # Array — walk items, drop those whose type doesn't match `items.type`.
    if expected == "array":
        if not isinstance(value, list):
            logger.warning(
                "schema-coerce: expected array at %s, got %s — replacing with []",
                path or "<root>",
                type(value).__name__,
            )
            return []
        item_schema = schema.get("items") or {}
        out: list = []
        for i, item in enumerate(value):
            cleaned = _coerce_to_schema(item, item_schema, f"{path}[{i}]")
            if cleaned is _SCHEMA_DROP:
                continue
            out.append(cleaned)
        return out

    # Object — walk properties, drop fields whose type doesn't match,
    # and drop the WHOLE object if any required field ends up missing.
    if expected == "object":
        if not isinstance(value, dict):
            logger.warning(
                "schema-coerce: expected object at %s, got %s — dropping",
                path or "<root>",
                type(value).__name__,
            )
            return _SCHEMA_DROP
        properties = schema.get("properties") or {}
        required = set(schema.get("required") or ())
        out_obj: dict = {}
        for k, v in value.items():
            sub_schema = properties.get(k)
            if sub_schema is None:
                # No declared property — keep as-is. Schemas in this codebase
                # don't use additionalProperties:false, so unknown keys are
                # acceptable and may carry useful debug info.
                out_obj[k] = v
                continue
            cleaned = _coerce_to_schema(v, sub_schema, f"{path}.{k}" if path else k)
            if cleaned is _SCHEMA_DROP:
                continue
            out_obj[k] = cleaned
        # Half-formed object recovery. MiniMax occasionally drops required
        # fields entirely from an object (Run #16 returned 7 angles all
        # missing `topic`). Two recovery modes:
        #
        # 1. Required STRING/INTEGER/NUMBER/BOOLEAN fields — fill with a
        #    safe default ("" / 0 / 0.0 / False). Downstream handlers
        #    already have `.get(field, default)` patterns for these and
        #    log them as "Validated angle '?'" etc. — much better than
        #    dropping the whole object.
        # 2. Required OBJECT/ARRAY fields — there's no sensible default,
        #    so drop the whole parent object as before.
        missing_required = required - out_obj.keys()
        if missing_required:
            # Factories so each filled field gets its own fresh container —
            # avoid the mutable-default trap where every dropped-array field
            # would alias the same underlying list across objects.
            primitive_defaults: dict[str, callable] = {
                "string": lambda: "",
                "integer": lambda: 0,
                "number": lambda: 0.0,
                "boolean": lambda: False,
                "array": lambda: [],
            }
            fatal_missing: list[str] = []
            filled: list[str] = []
            for field in sorted(missing_required):
                sub = properties.get(field, {})
                sub_type = sub.get("type") if isinstance(sub, dict) else None
                # Union types: accept any of the listed scalars; prefer
                # the first primitive default that exists.
                if isinstance(sub_type, list):
                    chosen = next(
                        (t for t in sub_type if t in primitive_defaults),
                        None,
                    )
                    if chosen is None:
                        fatal_missing.append(field)
                        continue
                    out_obj[field] = primitive_defaults[chosen]()
                    filled.append(field)
                elif isinstance(sub_type, str) and sub_type in primitive_defaults:
                    out_obj[field] = primitive_defaults[sub_type]()
                    filled.append(field)
                else:
                    fatal_missing.append(field)
            if filled:
                logger.warning(
                    "schema-coerce: object at %s filled missing required %s with defaults",
                    path or "<root>",
                    filled,
                )
            if fatal_missing:
                logger.warning(
                    "schema-coerce: object at %s missing required field(s) %s "
                    "with no safe default — dropping",
                    path or "<root>",
                    fatal_missing,
                )
                return _SCHEMA_DROP
        return out_obj

    # Primitive type mismatch — drop.
    type_check = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
    }.get(expected)
    if type_check is not None and not isinstance(value, type_check):
        # Allow ints to satisfy 'number'; bool/None are dropped strictly.
        logger.warning(
            "schema-coerce: expected %s at %s, got %s (%r) — dropping",
            expected,
            path or "<root>",
            type(value).__name__,
            value if not isinstance(value, str) else value[:60],
        )
        return _SCHEMA_DROP

    return value


# Sentinel used by _coerce_to_schema to indicate "drop this whole element"
# without conflating with legitimate None / "" / 0 values that callers may
# rely on.
_SCHEMA_DROP = object()


def structured_llm_call(
    system: str,
    user_message: str,
    schema: dict,
    max_tokens: int,
    settings=None,
    *,
    temperature: float,
    thinking: dict | None = None,
    usage: dict | None = None,
) -> dict:
    """Call MiniMax/Anthropic with structured output enforcement.

    Uses call_api() which handles:
    - MiniMax: tool-use trick (_build_structured_output_tool)
    - Anthropic: native output_config json_schema
    - Retry logic + rate limiter

    `temperature` is a required keyword argument so every call site picks a
    stage explicitly (no accidental defaults). Use the per-stage values on
    LyraSettings: temperature_research/synthesis/verification/narrative.

    `thinking` is forwarded to call_api unchanged. Mechanical callers (the
    prospector's mention extraction) pass ``{"type": "disabled"}``: with
    thinking left to default, thinking_for_effort() returns adaptive for
    EVERY effort level and reasoning tokens cost ~7x the visible output.

    `usage`, when a dict is passed, receives the response's token usage
    (input_tokens/output_tokens/cache fields) so a caller can enforce its
    own budget — the return value is the parsed object only.

    Returns parsed dict. Falls back to text parsing on failure. If BOTH the
    structured attempt and the text fallback fail, raises MiniMaxTerminalError
    (never silently returns {} — that failure mode produced "no research
    angles" runs and empty papers before 2026-08-06).
    """
    from pipeline.lyra.config import _get_settings, call_api

    if settings is None:
        settings = _get_settings()

    # We avoid strict:true here even though it tightens shape enforcement —
    # MiniMax appears to silently produce no tool call at all when the
    # schema has any loose sub-shape (e.g. `items: {"type": "object"}`
    # without explicit properties / additionalProperties:false), which
    # stalls the entire convergence loop. The defensive isinstance(...)
    # guards in the handlers cover the residual shape-violation risk.
    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "structured_output",
            "schema": schema,
        },
    }

    try:
        # call_api() pulls settings via _get_settings() internally and forwards
        # **kwargs to _call_anthropic_api(settings, ...). Passing settings=
        # here would duplicate the positional arg and raise TypeError, which
        # is exactly what broke every structured Theo call after commit 964a66b.
        call_kwargs: dict = {}
        if thinking is not None:
            call_kwargs["thinking"] = thinking
        resp = call_api(
            system=system,
            messages=[{"role": "user", "content": user_message}],
            max_tokens=max_tokens,
            response_format=response_format,
            temperature=temperature,
            **call_kwargs,
        )
        if usage is not None:
            usage.update(resp.usage or {})
        if resp.stop_reason == "max_tokens":
            logger.warning(
                "Structured LLM call hit max_tokens=%d before finishing "
                "(truncated JSON likely). Consider raising the budget.",
                max_tokens,
            )
        text = resp.content[0].text if resp.content else ""
        parsed = parse_fenced_json(text)
        # Boundary normalisation — drop schema-violating items so handlers
        # never see a string where they expect a dict (etc.). The same
        # AttributeError took down 4 separate handlers in one debugging
        # session before this hook was added.
        coerced = _coerce_to_schema(parsed, schema)
        return coerced if coerced is not _SCHEMA_DROP else {}
    except (QuotaExhaustedError, InsufficientQuotaError, MiniMaxAuthError, MiniMaxTerminalError):
        # Quota death is not retryable here — it must reach the worker's
        # defer path. Swallowing it into {} made decomposition report
        # "no research angles" and marked the run 'failed' permanently:
        # 17 batch tasks died that way on 07-08..07-12 (2026-07-19).
        raise
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Structured output parse failed, retrying: %s", exc)
    except Exception as exc:
        logger.warning("Structured LLM call failed, retrying: %s", exc)

    # Retry once with text fallback — inherit the caller's stage temperature.
    try:
        raw = minimax_chat_anthropic(
            system, user_message, max_tokens, settings, temperature=temperature
        )
        parsed = parse_fenced_json(raw)
        coerced = _coerce_to_schema(parsed, schema)
        return coerced if coerced is not _SCHEMA_DROP else {}
    except (QuotaExhaustedError, InsufficientQuotaError, MiniMaxAuthError, MiniMaxTerminalError):
        raise
    except Exception as exc:
        logger.error("Structured LLM call failed after retry: %s", exc)
        raise MiniMaxTerminalError(
            f"structured_llm_call failed after structured attempt + text fallback: {exc}"
        ) from exc
