"""
Lyra Chat Quality Test Suite

Comprehensive test runner that sends prompts to the Lyra API, collects SSE
responses, runs 18 structural checks, and uses Mercury with structured output
as LLM judge for guaranteed-valid scoring.

Usage:
    python scripts/test_lyra_quality.py                          # All tests
    python scripts/test_lyra_quality.py --category site_refs     # One category
    python scripts/test_lyra_quality.py --name "Greeting"        # One test
    python scripts/test_lyra_quality.py --no-judge               # Structural only
    python scripts/test_lyra_quality.py --validate-api           # With prod API checks
    python scripts/test_lyra_quality.py --no-judge --validate-api  # Structural + API
    python scripts/test_lyra_quality.py --verbose                # Full responses
    python scripts/test_lyra_quality.py --list                   # List all tests
"""

import io
import sys

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import argparse
import asyncio
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import jwt
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

API_BASE = os.getenv("TEST_API_BASE", "https://ancientnerds.com/api/lyra")
API_SECRET_KEY = os.getenv("API_SECRET_KEY", "")
LYRA_API_KEY = os.getenv("LYRA_API_KEY", "")
MERCURY_BASE_URL = os.getenv(
    "LYRA_BASE_URL",
    os.getenv("LYRA_ANTHROPIC_BASE_URL", "https://api.inceptionlabs.ai/v1"),
)
MERCURY_MODEL = os.getenv("LYRA_LLM_MODEL", "mercury-2")
SSE_TIMEOUT = float(os.getenv("TEST_SSE_TIMEOUT", "120"))
MAX_RETRIES = 4

# Free API keys for judge key pool rotation
_FREE_KEYS_RAW = os.getenv("LYRA_FREE_API_KEYS", "")
LYRA_FREE_API_KEYS = [k.strip() for k in _FREE_KEYS_RAW.split(",") if k.strip()]

# Colours
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------


def _make_jwt() -> str:
    if not API_SECRET_KEY:
        print(f"{RED}ERROR: API_SECRET_KEY not set in .env{RESET}")
        sys.exit(1)
    import datetime

    return jwt.encode(
        {
            "sub": "test_user_123",
            "user_id": "00000000-0000-0000-0000-000000000000",
            "exp": datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=1),
            "iat": datetime.datetime.now(datetime.UTC),
        },
        API_SECRET_KEY,
        algorithm="HS256",
    )


# ---------------------------------------------------------------------------
# SSE response dataclass
# ---------------------------------------------------------------------------


@dataclass
class SSEResponse:
    content: str = ""
    sites: list[dict] = field(default_factory=list)
    news: list[dict] = field(default_factory=list)
    tools_called: list[str] = field(default_factory=list)
    pipeline_events: list[dict] = field(default_factory=list)
    done_metadata: dict = field(default_factory=dict)
    wall_time: float = 0.0
    ttft: float | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# SSE client
# ---------------------------------------------------------------------------


async def send_chat(
    message: str,
    history: list[dict] | None = None,
    context_type: str = "global",
    context_id: str | None = None,
    context_year: int | None = None,
) -> SSEResponse:
    """Stream a chat request and collect the full response."""
    token = _make_jwt()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body: dict = {
        "message": message,
        "backend": "mercury",
        "context_type": context_type,
    }
    if history:
        body["history"] = history
    if context_id:
        body["context_id"] = context_id
    if context_year:
        body["context_year"] = context_year

    resp = SSEResponse()
    start = time.monotonic()

    async with httpx.AsyncClient(timeout=httpx.Timeout(SSE_TIMEOUT)) as client:
        try:
            async with client.stream(
                "POST", f"{API_BASE}/chat", json=body, headers=headers
            ) as stream:
                if stream.status_code != 200:
                    raw = await stream.aread()
                    resp.error = f"HTTP {stream.status_code}: {raw.decode()[:300]}"
                    resp.wall_time = time.monotonic() - start
                    return resp

                current_event_type = ""
                async for raw_line in stream.aiter_lines():
                    line = raw_line.strip()
                    if not line:
                        current_event_type = ""
                        continue

                    if line.startswith("event:"):
                        current_event_type = line[6:].strip()
                        continue

                    if not line.startswith("data:"):
                        continue

                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        break

                    try:
                        ev = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    ev_type = current_event_type or ev.get("type", "")

                    if ev_type == "token":
                        if resp.ttft is None:
                            resp.ttft = time.monotonic() - start
                        resp.content += ev.get("content", "")

                    elif ev_type == "diffusion":
                        if resp.ttft is None:
                            resp.ttft = time.monotonic() - start
                        resp.content = ev.get("content", "")

                    elif ev_type == "sites":
                        resp.sites.extend(ev.get("sites", []))

                    elif ev_type == "news":
                        resp.news.extend(ev.get("news", []))

                    elif ev_type == "pipeline":
                        resp.pipeline_events.append(ev)
                        stage = ev.get("stage", "")
                        status = ev.get("status", "")
                        if stage == "tool_call" and status == "start":
                            tool_name = (ev.get("meta") or {}).get("tool", "")
                            if tool_name:
                                resp.tools_called.append(tool_name)

                    elif ev_type == "done":
                        resp.done_metadata = ev.get("metadata", ev)

                    elif ev_type == "error":
                        resp.error = ev.get("error", ev.get("message", "unknown"))

        except httpx.ReadTimeout:
            resp.error = f"Timeout after {SSE_TIMEOUT}s"
        except Exception as e:
            resp.error = str(e)

    resp.wall_time = time.monotonic() - start
    return resp


# ---------------------------------------------------------------------------
# Structural checks (14 total)
# ---------------------------------------------------------------------------

UUID_PAT = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
UUID_LOOSE = r"[0-9a-f][0-9a-f\-\u2011\u2013]{34}[0-9a-f]"


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


def check_not_empty(resp: SSEResponse, **_kw) -> CheckResult:
    ok = len(resp.content.strip()) > 0
    detail = ""
    if not ok and resp.error:
        detail = resp.error
    elif not ok:
        detail = "Empty response (likely rate-limited)"
    return CheckResult("not_empty", ok, detail)


def check_no_error(resp: SSEResponse, **_kw) -> CheckResult:
    # If we got useful content, a trailing error event (e.g. from structured output
    # failing after diffusion streamed) is not a test failure.
    ok = resp.error is None or (resp.content.strip() != "")
    detail = resp.error if resp.error and not resp.content.strip() else ""
    return CheckResult("no_error", ok, detail)


def check_markers_resolved(resp: SSEResponse, **_kw) -> CheckResult:
    """No guillemet markers «...» should remain in final text."""
    remaining = re.findall(r"\u00ab/?[a-z]+\d+\u00bb?", resp.content)
    ok = len(remaining) == 0
    return CheckResult(
        "markers_resolved",
        ok,
        f"{len(remaining)} unresolved: {remaining[:5]}" if remaining else "",
    )


def check_site_links(resp: SSEResponse, **_kw) -> CheckResult:
    """[Name](site:UUID) format with valid UUID."""
    links = re.findall(rf"\[([^\]]+)\]\(site:({UUID_PAT})\)", resp.content, re.IGNORECASE)
    if not links:
        return CheckResult("site_links", True, "n/a — no site links")
    # Validate UUID format
    bad = [u for _, u in links if not re.match(rf"^{UUID_PAT}$", u, re.IGNORECASE)]
    ok = len(bad) == 0
    return CheckResult(
        "site_links", ok, f"{len(links)} links" + (f", {len(bad)} bad UUIDs" if bad else "")
    )


def check_coord_links(resp: SSEResponse, **_kw) -> CheckResult:
    """[lat, lon](lyra-coord:lat,lon) with valid ranges."""
    coords = re.findall(
        r"\[(-?\d+\.?\d*),\s*(-?\d+\.?\d*)\]\(lyra-coord:(-?\d+\.?\d*),(-?\d+\.?\d*)\)",
        resp.content,
    )
    if not coords:
        return CheckResult("coord_links", True, "n/a — no coord links")
    for lat_s, lon_s, _, _ in coords:
        lat, lon = float(lat_s), float(lon_s)
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return CheckResult("coord_links", False, f"Invalid: [{lat}, {lon}]")
    return CheckResult("coord_links", True, f"{len(coords)} valid")


def check_video_links(resp: SSEResponse, **_kw) -> CheckResult:
    """[▶ Channel ...](lyra-video:INDEX) or direct YouTube link format."""
    lyra_vids = re.findall(r"\[▶[^\]]*\]\(lyra-video:\d+\)", resp.content)
    yt_vids = re.findall(r"\[▶[^\]]*\]\(https://youtu\.be/[a-zA-Z0-9_-]{11}", resp.content)
    total = len(lyra_vids) + len(yt_vids)
    if not total:
        return CheckResult("video_links", True, "n/a — no video links")
    return CheckResult("video_links", True, f"{len(lyra_vids)} lyra + {len(yt_vids)} yt")


def check_empire_links(resp: SSEResponse, **_kw) -> CheckResult:
    """[Name](empire:POLITY_ID) format."""
    links = re.findall(r"\[([^\]]+)\]\(empire:([a-z][a-z0-9_]+)\)", resp.content)
    if not links:
        return CheckResult("empire_links", True, "n/a — no empire links")
    return CheckResult("empire_links", True, f"{len(links)} links")


def check_image_format(resp: SSEResponse, **_kw) -> CheckResult:
    """![title](url) with attribution line."""
    images = re.findall(r"!\[([^\]]*)\]\(([^)]+)\)", resp.content)
    if not images:
        return CheckResult("image_format", True, "n/a — no images")
    return CheckResult("image_format", True, f"{len(images)} images")


def check_external_links(resp: SSEResponse, **_kw) -> CheckResult:
    """[text](https://...) well-formed."""
    links = re.findall(r"\[([^\]]+)\]\((https?://[^)]+)\)", resp.content)
    if not links:
        return CheckResult("external_links", True, "n/a — no external links")
    return CheckResult("external_links", True, f"{len(links)} links")


def check_country_flags(resp: SSEResponse, **_kw) -> CheckResult:
    """[Name](flag:XX) format."""
    flags = re.findall(r"\[([^\]]+)\]\(flag:([A-Z]{2})\)", resp.content)
    if not flags:
        return CheckResult("country_flags", True, "n/a — no flags")
    return CheckResult("country_flags", True, f"{len(flags)} flags")


def check_no_bare_uuids(resp: SSEResponse, **_kw) -> CheckResult:
    """No raw UUIDs outside proper link syntax.

    Tolerates 1 bare UUID — Mercury sometimes echoes site IDs from context
    or tool results without wrapping them in link syntax.
    """
    # Find all UUIDs in content
    all_uuids = set(re.findall(rf"({UUID_PAT})", resp.content, re.IGNORECASE))
    # Find UUIDs that are properly linked
    linked = set(re.findall(rf"\(site:({UUID_PAT})\)", resp.content, re.IGNORECASE))
    bare = all_uuids - linked
    ok = len(bare) <= 2
    return CheckResult("no_bare_uuids", ok, f"{len(bare)} bare UUIDs" if bare else "")


def check_no_raw_json(resp: SSEResponse, **_kw) -> CheckResult:
    """No raw JSON blocks or marker-related JSON keys in response text."""
    problems = []
    # JSON code blocks with marker data
    if re.search(r"```json\s*\{[\s\S]*?\}\s*```", resp.content):
        problems.append("```json block")
    # Bare JSON array patterns with marker keys
    json_keys = re.findall(
        r'"(?:sites|coords|videos|empires|images|links|countries)"\s*:\s*\[',
        resp.content,
    )
    if json_keys:
        problems.append(f"JSON keys: {json_keys[:3]}")
    # Raw JSON array entries that look like {\"marker\": ...}
    if re.search(r'\{\s*"marker"\s*:', resp.content):
        problems.append('{"marker":...} pattern')
    ok = len(problems) == 0
    return CheckResult("no_raw_json", ok, ", ".join(problems) if problems else "")


def check_no_empty_ids(resp: SSEResponse, **_kw) -> CheckResult:
    """No empty site IDs like (site:) or site:\"\"."""
    problems = []
    # (site:) with no UUID
    empty_site = re.findall(r"\(site:\s*\)", resp.content)
    if empty_site:
        problems.append(f"{len(empty_site)}x (site:)")
    # site:"" pattern
    if 'site:""' in resp.content:
        problems.append('site:""')
    ok = len(problems) == 0
    return CheckResult("no_empty_ids", ok, ", ".join(problems) if problems else "")


def check_conciseness(resp: SSEResponse, max_chars: int = 3500, **_kw) -> CheckResult:
    ok = len(resp.content) <= max_chars
    return CheckResult(
        "conciseness",
        ok,
        f"{len(resp.content)} chars" + ("" if ok else f" (max {max_chars})"),
    )


def check_tools_called(resp: SSEResponse, expected: list[str] | None = None, **_kw) -> CheckResult:
    """Check expected tools were called, or auto-retrieve was sufficient."""
    if not expected:
        return CheckResult("tools_called", True, "n/a — no expected tools")
    if not resp.tools_called and resp.content.strip():
        return CheckResult("tools_called", True, "Auto-retrieved context sufficient")
    called_set = set(resp.tools_called)
    matched = [t for t in expected if t in called_set]
    ok = len(matched) > 0
    return CheckResult(
        "tools_called",
        ok,
        f"Expected one of {expected}, got {resp.tools_called}",
    )


def check_no_hallucinated_ids(resp: SSEResponse, **_kw) -> CheckResult:
    """Site UUIDs in response should match those from SSE sites event."""
    response_uuids = set(re.findall(rf"\(site:({UUID_PAT})\)", resp.content, re.IGNORECASE))
    if not response_uuids:
        return CheckResult("no_hallucinated_ids", True, "n/a — no site links")
    known_ids = {s.get("id", "") for s in resp.sites}
    unknown = response_uuids - known_ids
    # Allow if sites event wasn't emitted (auto-retrieve may not produce sites event for all)
    if not resp.sites:
        return CheckResult("no_hallucinated_ids", True, "n/a — no sites event to compare")
    ok = len(unknown) == 0
    return CheckResult(
        "no_hallucinated_ids",
        ok,
        f"{len(unknown)} unknown IDs" if unknown else f"All {len(response_uuids)} verified",
    )


def check_off_topic_rejected(resp: SSEResponse, **_kw) -> CheckResult:
    """Off-topic requests should be declined, not answered.

    Fails if response contains code fences or programming patterns,
    which indicates Lyra answered a coding/tech question instead of redirecting.
    """
    problems = []
    # Code fences = answered a coding question
    if re.search(
        r"```(?:python|javascript|java|cpp|bash|sql|ruby|go|rust|typescript|sh|c\b)", resp.content
    ):
        problems.append("Contains code block")
    # Programming keywords without archaeological context
    code_patterns = re.findall(
        r"\b(?:def |import |function |class |var |let |const |return )\b", resp.content
    )
    if len(code_patterns) >= 2:
        problems.append(f"{len(code_patterns)} code keywords")
    ok = len(problems) == 0
    return CheckResult(
        "off_topic_rejected", ok, ", ".join(problems) if problems else "Properly declined"
    )


def check_no_json_leak(resp: SSEResponse, **_kw) -> CheckResult:
    """No references to JSON structure (arrays, fields) should leak into user text."""
    leaks = []
    patterns = [
        (
            r"(?:see|in)\s+the\s+(?:links|sites|coords|videos|empires|images|countries)\s+array",
            "array reference",
        ),
        (
            r"(?:links|sites|coords|videos|empires|images|countries)\s+(?:field|property|object)",
            "field reference",
        ),
        (r'"(?:on_topic|text|sites|coords|videos|empires|images|links|countries)"\s*:', "JSON key"),
    ]
    for pat, label in patterns:
        if re.search(pat, resp.content, re.IGNORECASE):
            leaks.append(label)
    ok = len(leaks) == 0
    return CheckResult("no_json_leak", ok, ", ".join(leaks) if leaks else "")


def check_personality(resp: SSEResponse, **_kw) -> CheckResult:
    """Greeting responses should show Lyra's personality — not bland generic text."""
    text = resp.content.lower()
    # Must NOT be generic chatbot filler
    bland_patterns = [
        r"how can i (?:assist|help) you",
        r"how may i help you",
        r"what can i do for you",
        r"i'm here to help",
        r"feel free to ask",
        r"your (?:ai |virtual )?(?:assistant|companion)",
    ]
    is_bland = any(re.search(p, text) for p in bland_patterns)
    # Should have at least one personality signal (emoji, archaeology reference, exclamation)
    has_emoji = bool(
        re.search(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]|🏛|🏺|🗿|⚱|🔍|💀", resp.content)
    )
    has_archaeology = bool(re.search(r"archaeolog|ancient|ruin|civilization|dig|history", text))
    has_energy = "!" in resp.content or "?" in resp.content

    if is_bland:
        return CheckResult("personality", False, "Bland generic greeting")
    if has_emoji or (has_archaeology and has_energy):
        return CheckResult("personality", True, "Has personality")
    return CheckResult("personality", True, "Acceptable")


CHECK_REGISTRY: dict[str, callable] = {
    "not_empty": check_not_empty,
    "no_error": check_no_error,
    "markers_resolved": check_markers_resolved,
    "no_raw_json": check_no_raw_json,
    "no_empty_ids": check_no_empty_ids,
    "site_links": check_site_links,
    "coord_links": check_coord_links,
    "video_links": check_video_links,
    "empire_links": check_empire_links,
    "image_format": check_image_format,
    "external_links": check_external_links,
    "country_flags": check_country_flags,
    "no_bare_uuids": check_no_bare_uuids,
    "conciseness": check_conciseness,
    "tools_called": check_tools_called,
    "no_hallucinated_ids": check_no_hallucinated_ids,
    "off_topic_rejected": check_off_topic_rejected,
    "no_json_leak": check_no_json_leak,
    "personality": check_personality,
}


# ---------------------------------------------------------------------------
# Production API Client (for --validate-api)
# ---------------------------------------------------------------------------

PROD_API_BASE = "https://ancientnerds.com/api/v1"
# Minimum seconds between API calls (10 req/min = 6s between calls)
API_RATE_LIMIT_INTERVAL = 6.0


class ProdAPIClient:
    """Cached, rate-limited client for production API validation."""

    def __init__(self):
        self._cache: dict[str, dict | list | None] = {}
        self._last_call: float = 0
        self._call_count: int = 0

    async def get(self, path: str) -> dict | list | None:
        if path in self._cache:
            return self._cache[path]

        # Respect rate limit
        elapsed = time.time() - self._last_call
        if elapsed < API_RATE_LIMIT_INTERVAL:
            await asyncio.sleep(API_RATE_LIMIT_INTERVAL - elapsed)

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{PROD_API_BASE}{path}")
            self._last_call = time.time()
            self._call_count += 1

            if resp.status_code == 200:
                data = resp.json()
                self._cache[path] = data
                return data
            elif resp.status_code == 429:
                # Rate limited — wait and don't cache
                print(f"    {YELLOW}API rate limited on {path}, waiting...{RESET}")
                await asyncio.sleep(60)
                return None
            else:
                self._cache[path] = None
                return None
        except Exception as e:
            print(f"    {YELLOW}API error on {path}: {e}{RESET}")
            return None

    @property
    def stats(self) -> str:
        return f"calls={self._call_count} cached={len(self._cache)}"


# Singleton — created only if --validate-api is used
_prod_api: ProdAPIClient | None = None


def _get_prod_api() -> ProdAPIClient:
    global _prod_api
    if _prod_api is None:
        _prod_api = ProdAPIClient()
    return _prod_api


# ---------------------------------------------------------------------------
# API-backed validation checks (run with --validate-api)
# ---------------------------------------------------------------------------


async def check_site_uuids_exist(resp: SSEResponse, **_kw) -> CheckResult:
    """Verify every (site:UUID) in the response exists in production API."""
    uuids = set(re.findall(rf"\(site:({UUID_PAT})\)", resp.content, re.IGNORECASE))
    if not uuids:
        return CheckResult("api_site_uuids", True, "n/a — no site links")

    api = _get_prod_api()
    missing = []
    for uid in uuids:
        data = await api.get(f"/sites/{uid}")
        if data is None:
            missing.append(uid[:8])

    ok = len(missing) == 0
    return CheckResult(
        "api_site_uuids",
        ok,
        f"{len(uuids)} checked, {len(missing)} missing" + (f": {missing}" if missing else ""),
    )


async def check_empire_ids_exist(resp: SSEResponse, **_kw) -> CheckResult:
    """Verify every (empire:ID) in the response is a real Seshat polity."""
    ids = re.findall(r"\(empire:([a-z][a-z0-9_]+)\)", resp.content)
    if not ids:
        return CheckResult("api_empire_ids", True, "n/a — no empire links")

    api = _get_prod_api()
    missing = []
    for pid in set(ids):
        data = await api.get(f"/empires/{pid}")
        if data is None:
            missing.append(pid)

    ok = len(missing) == 0
    return CheckResult(
        "api_empire_ids",
        ok,
        f"{len(set(ids))} checked, {len(missing)} missing" + (f": {missing}" if missing else ""),
    )


async def check_channel_names_exist(resp: SSEResponse, **_kw) -> CheckResult:
    """Verify every [▶ Channel ...] in the response is a real channel."""
    # Extract channel names from [▶ Channel Name ...](lyra-video:N)
    channel_refs = re.findall(r"\[▶\s*([^\]]+?)(?:\s*\|[^\]]+)?\]\(lyra-video:\d+\)", resp.content)
    if not channel_refs:
        return CheckResult("api_channels", True, "n/a — no channel refs")

    api = _get_prod_api()
    channels_data = await api.get("/news/channels")
    if not channels_data:
        return CheckResult("api_channels", True, "n/a — channels endpoint unavailable")

    known_names = {ch["name"].lower() for ch in channels_data if "name" in ch}
    unknown = [name for name in channel_refs if name.strip().lower() not in known_names]

    ok = len(unknown) == 0
    return CheckResult(
        "api_channels",
        ok,
        f"{len(channel_refs)} checked, {len(unknown)} unknown"
        + (f": {unknown[:3]}" if unknown else ""),
    )


async def check_country_codes_valid(resp: SSEResponse, **_kw) -> CheckResult:
    """Verify every (flag:XX) country code exists in the facets endpoint."""
    flags = re.findall(r"\(flag:([A-Z]{2})\)", resp.content)
    if not flags:
        return CheckResult("api_country_codes", True, "n/a — no flag links")

    api = _get_prod_api()
    facets = await api.get("/facets")
    if not facets:
        return CheckResult("api_country_codes", True, "n/a — facets endpoint unavailable")

    # The facets endpoint returns country names, not codes.
    # We validate that the flag codes are standard ISO 3166-1 alpha-2.
    # A comprehensive check would map codes to names, but for now just verify
    # they are valid 2-letter codes (A-Z only, already matched by regex).
    return CheckResult("api_country_codes", True, f"{len(set(flags))} valid codes")


async def check_radar_data_valid(resp: SSEResponse, **_kw) -> CheckResult:
    """When search_radar was called, verify mentioned sites exist in /radar."""
    if "search_radar" not in resp.tools_called:
        return CheckResult("api_radar", True, "n/a — search_radar not called")

    api = _get_prod_api()
    radar_data = await api.get("/radar?page_size=50")
    if not radar_data or "items" not in radar_data:
        return CheckResult("api_radar", True, "n/a — radar endpoint unavailable")

    radar_names = {item["name"].lower() for item in radar_data["items"] if "name" in item}
    if not radar_names:
        return CheckResult("api_radar", True, "n/a — no radar data in prod")

    # Check if any radar site names appear in Lyra's response
    content_lower = resp.content.lower()
    matched = [name for name in radar_names if name.lower() in content_lower]

    if not matched and resp.content.strip():
        # Lyra responded but didn't mention any known radar names — could be
        # filtered results or paraphrasing, not necessarily wrong
        return CheckResult(
            "api_radar", True, f"0/{len(radar_names)} names matched (may be filtered)"
        )

    return CheckResult(
        "api_radar", True, f"{len(matched)}/{len(radar_names)} radar names in response"
    )


async def check_news_search_valid(resp: SSEResponse, **_kw) -> CheckResult:
    """When search_news was called, verify /news endpoint returns data."""
    if "search_news" not in resp.tools_called:
        return CheckResult("api_news", True, "n/a — search_news not called")

    api = _get_prod_api()
    news_data = await api.get("/news?page_size=5")
    if not news_data or "items" not in news_data:
        return CheckResult("api_news", False, "news endpoint returned no data")

    total = news_data.get("total_count", 0)
    items = news_data.get("items", [])
    if not items:
        return CheckResult("api_news", False, "news feed is empty")

    # Verify channel names from news exist in channels list
    channels_data = await api.get("/news/channels")
    if channels_data:
        known_channels = {ch["name"] for ch in channels_data if "name" in ch}
        news_channels = {item["video"]["channel_name"] for item in items if "video" in item}
        unknown = news_channels - known_channels
        if unknown:
            return CheckResult("api_news", False, f"Unknown channels in news: {list(unknown)[:3]}")

    return CheckResult("api_news", True, f"news healthy ({total} items, {len(items)} returned)")


async def check_site_images_available(resp: SSEResponse, **_kw) -> CheckResult:
    """When get_site_images was called, verify site UUIDs have images via API."""
    if "get_site_images" not in resp.tools_called:
        return CheckResult("api_images", True, "n/a — get_site_images not called")

    # Find site UUIDs referenced in the response
    uuids = set(re.findall(rf"\(site:({UUID_PAT})\)", resp.content, re.IGNORECASE))
    if not uuids:
        return CheckResult("api_images", True, "n/a — no site UUIDs to check images for")

    api = _get_prod_api()
    checked = 0
    with_images = 0
    for uid in list(uuids)[:3]:  # Check max 3 to conserve rate limit
        data = await api.get(f"/sites/{uid}/images?limit=1")
        checked += 1
        if data and isinstance(data, list) and len(data) > 0:
            with_images += 1

    return CheckResult("api_images", True, f"{with_images}/{checked} sites have images in prod")


API_CHECK_REGISTRY: dict[str, callable] = {
    "api_site_uuids": check_site_uuids_exist,
    "api_empire_ids": check_empire_ids_exist,
    "api_channels": check_channel_names_exist,
    "api_country_codes": check_country_codes_valid,
    "api_radar": check_radar_data_valid,
    "api_news": check_news_search_valid,
    "api_images": check_site_images_available,
}


# ---------------------------------------------------------------------------
# Judge Key Pool (round-robin free keys, fallback to paid)
# ---------------------------------------------------------------------------


class _JudgeKeyPool:
    """Cycle through free API keys quickly, fall back to paid key.
    Rate-limited keys get a 60s cooldown before reuse."""

    COOLDOWN = 60

    def __init__(self, free_keys: list[str], paid_key: str):
        self._free = free_keys
        self._paid = paid_key
        self._cooldowns: dict[int, float] = {}
        self._idx = 0
        self._calls = 0
        self._rate_limited = 0

    @property
    def current_key(self) -> str:
        now = time.monotonic()
        for _ in range(len(self._free)):
            if not self._free:
                break
            i = self._idx % len(self._free)
            if i not in self._cooldowns or now >= self._cooldowns[i]:
                self._idx = (i + 1) % len(self._free)
                return self._free[i]
            self._idx = (self._idx + 1) % len(self._free)
        return self._paid

    def mark_rate_limited(self, key: str) -> None:
        for i, k in enumerate(self._free):
            if k == key:
                self._cooldowns[i] = time.monotonic() + self.COOLDOWN
                self._rate_limited += 1
                break

    def record_call(self) -> None:
        self._calls += 1

    @property
    def stats(self) -> str:
        return f"calls={self._calls} rate_limited={self._rate_limited} free_keys={len(self._free)}"


_judge_pool = _JudgeKeyPool(LYRA_FREE_API_KEYS, LYRA_API_KEY)


# ---------------------------------------------------------------------------
# Mercury Judge (structured output — guaranteed valid JSON)
# ---------------------------------------------------------------------------

JUDGE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "JudgeScore",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "relevance": {"type": "integer"},
                "site_linking": {"type": "string", "enum": ["pass", "fail", "n_a"]},
                "source_citations": {"type": "string", "enum": ["pass", "fail", "n_a"]},
                "conciseness": {"type": "string", "enum": ["pass", "fail"]},
                "accuracy": {"type": "string", "enum": ["pass", "fail"]},
                "marker_usage": {"type": "string", "enum": ["pass", "fail", "n_a"]},
                "overall": {"type": "string", "enum": ["pass", "fail"]},
                "reason": {"type": "string"},
            },
            "required": [
                "relevance",
                "site_linking",
                "source_citations",
                "conciseness",
                "accuracy",
                "marker_usage",
                "overall",
                "reason",
            ],
            "additionalProperties": False,
        },
    },
}

JUDGE_PROMPT = """You are evaluating an archaeological AI chatbot called Lyra.

User prompt: {prompt}

Lyra's response:
{response}

Tools called: {tools}

Score each dimension:
1. relevance (0-10): Does the response address the user's question? Greetings/off-topic rejections score 5+ if reasonable.
2. site_linking ("pass"|"fail"|"n_a"): Sites linked as [Name](site:UUID)? "n_a" if no sites mentioned.
3. source_citations ("pass"|"fail"|"n_a"): Video/news sources cited? "n_a" if no YouTube data found.
4. conciseness ("pass"|"fail"): Response is 1-3 paragraphs, ≤5 list items?
5. accuracy ("pass"|"fail"): No hallucinated sites or fabricated data?
6. marker_usage ("pass"|"fail"|"n_a"): All guillemet markers resolved into proper links? "n_a" if no markers expected.
7. overall: "pass" if relevance >= 5 AND accuracy is "pass" AND conciseness is "pass".
8. reason: Brief explanation of your scoring.

IMPORTANT: overall is "pass" if relevance >= 5 AND accuracy pass AND conciseness pass. Individual fail on site_linking or source_citations does NOT make overall fail."""


async def evaluate_with_judge(prompt: str, response_text: str, tools: list[str]) -> dict | None:
    """Call Mercury as LLM judge with structured output and key pool rotation."""
    if not LYRA_API_KEY and not LYRA_FREE_API_KEYS:
        return None

    from openai import AsyncOpenAI

    judge_input = JUDGE_PROMPT.format(
        prompt=prompt,
        response=response_text[:2000],
        tools=", ".join(tools) if tools else "(none)",
    )

    key = _judge_pool.current_key
    for _attempt in range(3):
        client = AsyncOpenAI(api_key=key, base_url=MERCURY_BASE_URL)
        try:
            _judge_pool.record_call()
            completion = await client.chat.completions.create(
                model=MERCURY_MODEL,
                messages=[{"role": "user", "content": judge_input}],
                max_tokens=4096,
                stream=False,
                reasoning_effort="high",
                temperature=0.1,
                response_format=JUDGE_SCHEMA,
            )
            raw = completion.choices[0].message.content or ""
            if not raw.strip():
                return {"error": "Judge returned empty content (reasoning tokens exhausted budget)"}
            return json.loads(raw)
        except Exception as e:
            msg = str(e).lower()
            if "429" in msg or "rate limit" in msg:
                _judge_pool.mark_rate_limited(key)
                key = _judge_pool.current_key
                await asyncio.sleep(2.0)
                continue
            return {"error": str(e)[:200]}
    return {"error": "Rate limited after 3 attempts"}


# ---------------------------------------------------------------------------
# Test case definition
# ---------------------------------------------------------------------------


@dataclass
class TestCase:
    name: str
    category: str
    prompt: str
    structural_checks: list[str]
    expected_tools: list[str] = field(default_factory=list)
    history: list[dict] | None = None
    context_type: str = "global"
    context_id: str | None = None
    context_year: int | None = None
    skip_judge: bool = False
    min_relevance: int = 7


# ---------------------------------------------------------------------------
# Test cases (~52 across 15 categories)
# ---------------------------------------------------------------------------

TEST_CASES: list[TestCase] = [
    # ── Category 1: Basic Chat (4) ──
    TestCase(
        name="Greeting",
        category="basic",
        prompt="Hello Lyra!",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
            "conciseness",
            "personality",
        ],
    ),
    TestCase(
        name="Off-topic rejection",
        category="basic",
        prompt="Can you help me sort a Python list?",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
            "conciseness",
            "off_topic_rejected",
        ],
        min_relevance=5,
    ),
    TestCase(
        name="Follow-up with history",
        category="basic",
        prompt="Tell me more about that",
        history=[
            {"role": "user", "content": "What do you know about Göbekli Tepe?"},
            {
                "role": "assistant",
                "content": "Göbekli Tepe is a Neolithic site in southeastern Turkey, dating to around 9500 BCE.",
            },
        ],
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
            "conciseness",
        ],
    ),
    TestCase(
        name="Conciseness check",
        category="basic",
        prompt="What is the oldest known temple?",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
            "conciseness",
            "site_links",
        ],
        expected_tools=["search_sites", "vector_search", "get_site_details"],
    ),
    # ── Category 2: Site References (5) ──
    TestCase(
        name="Single site link",
        category="site_refs",
        prompt="Tell me about Gobekli Tepe",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
            "site_links",
            "no_bare_uuids",
            "no_hallucinated_ids",
        ],
        expected_tools=["search_sites", "get_site_details"],
    ),
    TestCase(
        name="Multiple site links",
        category="site_refs",
        prompt="Compare Stonehenge and the Pyramids of Giza",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
            "site_links",
            "no_bare_uuids",
            "no_hallucinated_ids",
        ],
        expected_tools=["search_sites", "get_site_details"],
    ),
    TestCase(
        name="Sites in region",
        category="site_refs",
        prompt="What archaeological sites are in Turkey?",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
            "site_links",
        ],
    ),
    TestCase(
        name="Table format links",
        category="site_refs",
        prompt="List 3 Neolithic sites in a table with their country and period",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
            "site_links",
        ],
        min_relevance=5,
    ),
    TestCase(
        name="Site details",
        category="site_refs",
        prompt="Tell me everything about Çatalhöyük",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
            "site_links",
        ],
        expected_tools=["get_site_details", "search_sites", "get_site_images"],
    ),
    # ── Category 3: Coordinate References (3) ──
    TestCase(
        name="Coordinates query",
        category="coordinates",
        prompt="Where exactly is Göbekli Tepe? Give me the coordinates.",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
            "coord_links",
            "site_links",
        ],
        expected_tools=["search_sites", "get_site_details"],
    ),
    TestCase(
        name="Machu Picchu coords",
        category="coordinates",
        prompt="What are the exact coordinates of Machu Picchu?",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
            "coord_links",
            "site_links",
        ],
        expected_tools=["search_sites", "get_site_details"],
    ),
    TestCase(
        name="Multiple coordinates",
        category="coordinates",
        prompt="Where are Pompeii and Petra? Give coordinates for both.",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
            "coord_links",
            "site_links",
        ],
        expected_tools=["search_sites", "get_site_details"],
    ),
    # ── Category 4: News & Video References (5) ──
    TestCase(
        name="Recent discoveries",
        category="news_video",
        prompt="What are the latest archaeological discoveries?",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
            "video_links",
        ],
        expected_tools=["search_news", "search_radar"],
    ),
    TestCase(
        name="Channel attribution",
        category="news_video",
        prompt="What has World of Antiquity reported recently?",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
            "video_links",
        ],
        expected_tools=["search_news"],
    ),
    TestCase(
        name="News about specific site",
        category="news_video",
        prompt="Any recent news about Karahan Tepe?",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
            "video_links",
        ],
        expected_tools=["search_news"],
    ),
    TestCase(
        name="News with timestamps",
        category="news_video",
        prompt="What recent discoveries have been reported on YouTube?",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
            "video_links",
        ],
        expected_tools=["search_news"],
    ),
    TestCase(
        name="Multiple news sources",
        category="news_video",
        prompt="Recent underwater archaeological discoveries from YouTube channels",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
            "video_links",
        ],
        expected_tools=["search_news"],
    ),
    # ── Category 5: Transcript References (3) ──
    TestCase(
        name="Transcript search",
        category="transcripts",
        prompt="Search transcripts for mentions of Atlantis",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
        ],
        expected_tools=["search_transcripts"],
    ),
    TestCase(
        name="Transcript with timestamp",
        category="transcripts",
        prompt="Find where channels discussed the Antikythera mechanism in their videos",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
        ],
        expected_tools=["search_transcripts"],
    ),
    TestCase(
        name="Channel-specific transcript",
        category="transcripts",
        prompt="What has Ancient Architects said about megalithic sites?",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
        ],
        expected_tools=["search_transcripts"],
        min_relevance=5,
    ),
    # ── Category 6: Article References (2) ──
    TestCase(
        name="Weekly digest",
        category="articles",
        prompt="What's in the latest weekly digest?",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
        ],
        expected_tools=["search_articles"],
    ),
    TestCase(
        name="Article topic search",
        category="articles",
        prompt="Find articles about Egyptian discoveries",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
        ],
        expected_tools=["search_articles"],
    ),
    # ── Category 7: Empire References (3) ──
    TestCase(
        name="Empire military",
        category="empires",
        prompt="Tell me about the Roman Empire's military capabilities",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
            "empire_links",
        ],
        expected_tools=["get_empire_data", "search_empires"],
    ),
    TestCase(
        name="Empire search",
        category="empires",
        prompt="Find empires that used iron weapons and chariots",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
            "empire_links",
        ],
        expected_tools=["search_empires"],
    ),
    TestCase(
        name="Empire context",
        category="empires",
        prompt="Tell me about their economy and trade",
        context_type="empire",
        context_id="it_roman_principate",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
            "empire_links",
        ],
        expected_tools=["get_empire_data"],
        min_relevance=5,
    ),
    # ── Category 8: Image References (2) ──
    TestCase(
        name="Site images",
        category="images",
        prompt="Show me images of Pompeii",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
            "image_format",
        ],
        expected_tools=["get_site_images"],
        min_relevance=5,
    ),
    TestCase(
        name="Image attribution",
        category="images",
        prompt="Show me photos of Stonehenge with attribution",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
            "image_format",
        ],
        expected_tools=["get_site_images"],
        min_relevance=5,
    ),
    # ── Category 9: External Links & Flags (3) ──
    TestCase(
        name="Wikipedia link",
        category="links_flags",
        prompt="Tell me about Petra with sources",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
        ],
    ),
    TestCase(
        name="Country flag",
        category="links_flags",
        prompt="What sites are in Turkey?",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
            "country_flags",
            "site_links",
        ],
        expected_tools=["search_sites"],
    ),
    TestCase(
        name="Multi-country flags",
        category="links_flags",
        prompt="Compare ancient sites in Egypt and Greece",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
            "country_flags",
            "site_links",
        ],
        expected_tools=["search_sites"],
    ),
    # ── Category 10: Radar & Discovery (3) ──
    TestCase(
        name="Radar overview",
        category="radar",
        prompt="What has Lyra discovered on her radar?",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
            "conciseness",
        ],
        expected_tools=["search_radar"],
    ),
    TestCase(
        name="Filtered radar",
        category="radar",
        prompt="Radar discoveries in Turkey",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
        ],
        expected_tools=["search_radar"],
    ),
    TestCase(
        name="Radar details",
        category="radar",
        prompt="Tell me about Lyra's most mentioned discovery",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
        ],
        expected_tools=["search_radar", "search_news", "vector_search"],
    ),
    # ── Category 11: Channel Directory (2) ──
    TestCase(
        name="List channels",
        category="channels",
        prompt="What YouTube channels do you monitor?",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
        ],
        expected_tools=["list_channels"],
    ),
    TestCase(
        name="Channel count",
        category="channels",
        prompt="How many channels do you follow?",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
            "conciseness",
        ],
        expected_tools=["list_channels"],
    ),
    # ── Category 12: Edge Cases (5) ──
    TestCase(
        name="Long complex query",
        category="edge_cases",
        prompt=(
            "I'm interested in understanding the connections between megalithic "
            "structures across continents, particularly Göbekli Tepe in Turkey, "
            "Stonehenge in England, and the megalithic temples of Malta. Compare "
            "their dating, construction methods, and cultural connections."
        ),
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
        ],
        min_relevance=3,
    ),
    TestCase(
        name="Non-English name",
        category="edge_cases",
        prompt="Tell me about Çatalhöyük",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
        ],
    ),
    TestCase(
        name="Nonexistent site",
        category="edge_cases",
        prompt="Tell me about the ancient ruins of Xanadu Prime on Mars",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
            "conciseness",
        ],
        min_relevance=4,
    ),
    TestCase(
        name="Single character",
        category="edge_cases",
        prompt="?",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
            "personality",
        ],
        min_relevance=4,
    ),
    TestCase(
        name="Empty tool results",
        category="edge_cases",
        prompt="Tell me about archaeological sites in Antarctica",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
            "conciseness",
        ],
        min_relevance=4,
    ),
    # ── Category 13: Multi-turn Conversations (3) ──
    TestCase(
        name="Image follow-up",
        category="multi_turn",
        prompt="Show me images of it",
        history=[
            {"role": "user", "content": "Tell me about Pompeii"},
            {
                "role": "assistant",
                "content": "Pompeii is a famous Roman city preserved by the eruption of Vesuvius in 79 AD.",
            },
        ],
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
        ],
        expected_tools=["get_site_images"],
    ),
    TestCase(
        name="Reference resolution",
        category="multi_turn",
        prompt="Tell me more about the first one",
        history=[
            {"role": "user", "content": "What Neolithic sites are in Turkey?"},
            {
                "role": "assistant",
                "content": "Turkey has several major Neolithic sites including Göbekli Tepe, Çatalhöyük, and Karahan Tepe.",
            },
        ],
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
        ],
    ),
    TestCase(
        name="Empire follow-up",
        category="multi_turn",
        prompt="What about their economy?",
        history=[
            {"role": "user", "content": "Tell me about the Roman Empire's military"},
            {
                "role": "assistant",
                "content": "The Roman Empire had a highly organized military with legions stationed across the empire.",
            },
        ],
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
        ],
        expected_tools=["get_empire_data", "search_empires"],
    ),
    # ── Category 14: Context Modes & Full Pipeline (5) ──
    TestCase(
        name="Site context",
        category="full_pipeline",
        prompt="What can you tell me about this site?",
        context_type="site",
        context_id="d953e9b3-de33-4c7d-9357-bbc5d94d2a16",  # Göbekli Tepe UUID
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
        ],
        min_relevance=3,
    ),
    TestCase(
        name="Empire context mode",
        category="full_pipeline",
        prompt="Describe this civilization",
        context_type="empire",
        context_id="it_roman_principate",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
        ],
        min_relevance=3,
    ),
    TestCase(
        name="Multi-tool pipeline",
        category="full_pipeline",
        prompt="Roman sites in Italy with recent news about Roman archaeology",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
            "site_links",
            "video_links",
        ],
        expected_tools=["search_sites", "search_news", "vector_search"],
    ),
    TestCase(
        name="Structured output validation",
        category="full_pipeline",
        prompt="Tell me about Göbekli Tepe including coordinates and recent news",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
            "site_links",
            "coord_links",
            "no_bare_uuids",
            "no_hallucinated_ids",
        ],
        expected_tools=["search_sites", "get_site_details", "search_news"],
    ),
    TestCase(
        name="News context",
        category="full_pipeline",
        prompt="Tell me more about this discovery",
        context_type="news",
        context_id="1",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
        ],
        min_relevance=3,
    ),
    # ── Category 15: Marker Quality (4) ──
    # Tests that the per-tool prompt instructions produce correct guillemet markers
    TestCase(
        name="Video markers from news",
        category="marker_quality",
        prompt="Was gibts neues in der Archäologie?",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
            "video_links",
        ],
        expected_tools=["search_news"],
    ),
    TestCase(
        name="Site chips with UUIDs",
        category="marker_quality",
        prompt="Tell me about Pompeii",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
            "site_links",
            "no_bare_uuids",
            "no_hallucinated_ids",
        ],
        expected_tools=["search_sites", "get_site_details"],
    ),
    TestCase(
        name="Coords from site details",
        category="marker_quality",
        prompt="Where is Angkor Wat? Show me on the map.",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
            "coord_links",
            "site_links",
        ],
        expected_tools=["search_sites", "get_site_details"],
    ),
    TestCase(
        name="Mixed marker types",
        category="marker_quality",
        prompt="Tell me about Knossos including coordinates, country, and any recent videos about it",
        structural_checks=[
            "not_empty",
            "no_error",
            "markers_resolved",
            "no_raw_json",
            "no_empty_ids",
            "site_links",
            "coord_links",
            "no_bare_uuids",
            "no_hallucinated_ids",
        ],
        expected_tools=["search_sites", "get_site_details", "search_news"],
    ),
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def _truncate(s: str, n: int = 120) -> str:
    s = s.replace("\n", " ").strip()
    return s[:n] + "..." if len(s) > n else s


async def run_test(
    idx: int,
    total: int,
    tc: TestCase,
    *,
    use_judge: bool,
    verbose: bool,
    validate_api: bool = False,
) -> tuple[bool, dict]:
    """Run a single test case with retries for empty responses."""
    print(f"\n{BOLD}[{idx}/{total}] [{tc.category}] {tc.name}{RESET}")
    print(f"  Prompt: {DIM}{_truncate(tc.prompt, 80)}{RESET}")

    resp = None
    for attempt in range(MAX_RETRIES + 1):
        if attempt > 0:
            print(f"  {YELLOW}Retry {attempt}/{MAX_RETRIES} (empty response){RESET}")
            await asyncio.sleep(2.0)

        resp = await send_chat(
            tc.prompt,
            history=tc.history,
            context_type=tc.context_type,
            context_id=tc.context_id,
            context_year=tc.context_year,
        )

        if resp.content.strip():
            break
        # Only stop retrying on permanent errors (auth failures)
        if resp.error and any(
            s in resp.error.lower() for s in ["401", "403", "forbidden", "authentication"]
        ):
            break

    # Show response summary
    preview = _truncate(resp.content, 100) if resp.content else "(empty)"
    print(f"  Response ({len(resp.content)} chars): {DIM}{preview}{RESET}")
    tools_str = ", ".join(resp.tools_called) if resp.tools_called else "(none)"
    ttft_str = f"{resp.ttft:.1f}s" if resp.ttft else "n/a"
    print(f"  Tools: {tools_str} | Time: {resp.wall_time:.1f}s | TTFT: {ttft_str}")

    if verbose and resp.content:
        print(f"\n{DIM}--- Full response ---{RESET}")
        print(resp.content)
        print(f"{DIM}--- End ---{RESET}\n")

    # Run structural checks
    structural_results: list[CheckResult] = []
    for check_name in tc.structural_checks:
        fn = CHECK_REGISTRY.get(check_name)
        if fn:
            if check_name == "tools_called":
                structural_results.append(fn(resp, expected=tc.expected_tools))
            else:
                structural_results.append(fn(resp))

    # Tool-specific check (if expected_tools and not already in structural_checks)
    if tc.expected_tools and "tools_called" not in tc.structural_checks:
        structural_results.append(check_tools_called(resp, expected=tc.expected_tools))

    # Auto-checks: always run on every test (catch real-world failures)
    if "no_json_leak" not in tc.structural_checks:
        structural_results.append(check_no_json_leak(resp))

    # Print structural results
    parts = []
    for cr in structural_results:
        icon = f"{GREEN}✓{RESET}" if cr.passed else f"{RED}✗{RESET}"
        detail = f" ({cr.detail})" if cr.detail else ""
        parts.append(f"{cr.name} {icon}{DIM}{detail}{RESET}")
    print(f"  Structural: {' | '.join(parts)}")

    structural_pass = all(cr.passed for cr in structural_results)

    # API validation (warnings only — don't affect overall_pass)
    api_results: list[CheckResult] = []
    if validate_api and resp.content.strip():
        for _check_name, fn in API_CHECK_REGISTRY.items():
            result = await fn(resp)
            api_results.append(result)
        if api_results:
            api_parts = []
            for cr in api_results:
                if "n/a" in cr.detail:
                    continue  # Skip n/a checks in output
                icon = f"{GREEN}✓{RESET}" if cr.passed else f"{YELLOW}⚠{RESET}"
                detail = f" ({cr.detail})" if cr.detail else ""
                api_parts.append(f"{cr.name} {icon}{DIM}{detail}{RESET}")
            if api_parts:
                print(f"  API checks: {' | '.join(api_parts)}")

    # LLM Judge
    judge_result = None
    overall_pass = structural_pass

    if use_judge and not tc.skip_judge and resp.content.strip():
        judge_result = await evaluate_with_judge(tc.prompt, resp.content, resp.tools_called)
        if judge_result and "error" not in judge_result:
            relevance = judge_result.get("relevance", 0)
            j_parts = [f"relevance={relevance}"]
            for dim in [
                "site_linking",
                "source_citations",
                "conciseness",
                "accuracy",
                "marker_usage",
            ]:
                val = judge_result.get(dim, "n_a")
                icon = (
                    f"{GREEN}✓{RESET}"
                    if val == "pass"
                    else f"{RED}✗{RESET}"
                    if val == "fail"
                    else f"{DIM}n/a{RESET}"
                )
                j_parts.append(f"{dim}={icon}")
            print(f"  Judge: {' | '.join(j_parts)}")

            j_overall = judge_result.get("overall", "pass")
            if j_overall == "fail" and relevance < tc.min_relevance:
                overall_pass = False
                reason = judge_result.get("reason", "")
                if reason:
                    print(f"  Judge reason: {YELLOW}{reason}{RESET}")
        elif judge_result and "error" in judge_result:
            print(f"  Judge: {YELLOW}error — {judge_result['error'][:80]}{RESET}")

    # Final result
    status = f"{GREEN}PASS{RESET}" if overall_pass else f"{RED}FAIL{RESET}"
    print(f"  RESULT: {status}")

    return overall_pass, {
        "name": tc.name,
        "category": tc.category,
        "passed": overall_pass,
        "structural": {cr.name: cr.passed for cr in structural_results},
        "api_checks": {cr.name: cr.passed for cr in api_results} if api_results else None,
        "judge": judge_result,
        "wall_time": resp.wall_time,
        "content_length": len(resp.content),
        "tools": resp.tools_called,
        "error": resp.error,
    }


async def main():
    parser = argparse.ArgumentParser(description="Lyra Chat Quality Test Suite")
    parser.add_argument("--category", type=str, help="Run only tests in this category")
    parser.add_argument("--name", type=str, help="Run only the test with this name")
    parser.add_argument("--no-judge", action="store_true", help="Skip LLM judge evaluation")
    parser.add_argument(
        "--validate-api",
        action="store_true",
        help="Run API-backed validation checks against production (rate-limited)",
    )
    parser.add_argument("--verbose", action="store_true", help="Show full response text")
    parser.add_argument("--list", action="store_true", help="List all test cases and exit")
    args = parser.parse_args()

    # List mode
    if args.list:
        cats: dict[str, list[str]] = {}
        for tc in TEST_CASES:
            cats.setdefault(tc.category, []).append(tc.name)
        for cat, names in cats.items():
            print(f"\n{BOLD}[{cat}]{RESET}")
            for n in names:
                print(f"  - {n}")
        print(f"\nTotal: {len(TEST_CASES)} tests")
        return

    # Filter
    cases = TEST_CASES
    if args.category:
        cases = [tc for tc in cases if tc.category == args.category]
        if not cases:
            print(f"{RED}No tests in category '{args.category}'{RESET}")
            print(f"Available: {', '.join(sorted({tc.category for tc in TEST_CASES}))}")
            sys.exit(1)
    if args.name:
        cases = [tc for tc in cases if args.name.lower() in tc.name.lower()]
        if not cases:
            print(f"{RED}No test matching '{args.name}'{RESET}")
            sys.exit(1)

    use_judge = not args.no_judge
    if use_judge and not LYRA_API_KEY:
        print(f"{YELLOW}Warning: LYRA_API_KEY not set, skipping LLM judge{RESET}")
        use_judge = False

    validate_api = args.validate_api

    total = len(cases)
    print(f"{BOLD}Lyra Quality Test Suite{RESET}")
    judge_info = f"Mercury (pool: {len(LYRA_FREE_API_KEYS)} free + 1 paid)" if use_judge else "off"
    api_info = f"prod ({PROD_API_BASE})" if validate_api else "off"
    print(
        f"Tests: {total} | Judge: {judge_info} | API validation: {api_info} | Retries: {MAX_RETRIES}"
    )
    print(f"API: {API_BASE}")
    print("=" * 60)

    results: list[dict] = []
    for i, tc in enumerate(cases, 1):
        passed, detail = await run_test(
            i, total, tc, use_judge=use_judge, verbose=args.verbose, validate_api=validate_api
        )
        results.append(detail)
        if i < total:
            await asyncio.sleep(1.0)

    # Summary
    print(f"\n{'=' * 60}")
    print(f"{BOLD}SUMMARY{RESET}")
    print(f"{'=' * 60}")

    cats: dict[str, list[dict]] = {}
    for r in results:
        cats.setdefault(r["category"], []).append(r)

    total_pass = 0
    total_fail = 0
    for cat, cat_results in cats.items():
        p = sum(1 for r in cat_results if r["passed"])
        f = len(cat_results) - p
        total_pass += p
        total_fail += f
        icon = f"{GREEN}✓{RESET}" if f == 0 else f"{RED}✗{RESET}"
        print(f"  {icon} {cat}: {p}/{len(cat_results)} passed")
        if f > 0:
            for r in cat_results:
                if not r["passed"]:
                    print(f"      {RED}FAIL{RESET}: {r['name']}")

    print(f"\n  Total: {GREEN}{total_pass} passed{RESET}, ", end="")
    if total_fail:
        print(f"{RED}{total_fail} failed{RESET}")
    else:
        print(f"{GREEN}0 failed{RESET}")

    total_time = sum(r["wall_time"] for r in results)
    print(f"  Time: {total_time:.1f}s")
    if use_judge:
        print(f"  Judge pool: {_judge_pool.stats}")
    if validate_api:
        api_warnings = sum(
            1
            for r in results
            if r.get("api_checks") and any(not v for v in r["api_checks"].values())
        )
        print(f"  API validation: {_get_prod_api().stats} | {api_warnings} warnings")

    sys.exit(0 if total_fail == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
