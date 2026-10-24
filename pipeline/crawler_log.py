# SPDX-License-Identifier: AGPL-3.0-only
"""nginx's crawler log: which search engines and AI systems fetch our pages.

nginx writes one JSON line per page request whose user agent names a known
crawler (log_format ``crawler`` in ancientnerds-nginx-config; assets, data
files and images are left out) to /var/www/ancientnerds/logs/crawlers.log,
bind-mounted read-only into the API containers at /app/logs:

    {"t":"2026-10-10T08:00:00+02:00","ip":"66.249.66.1",
     "req":"GET /sites/peru/x-1","status":200,"ua":"Mozilla/5.0 ... Googlebot/2.1 ..."}

A user agent is a claim, not an identity: anyone can send "Googlebot". Where
the operator publishes its crawler addresses (Google, Bing, OpenAI,
Perplexity, Apple, Anthropic, Common Crawl, DuckDuckGo, Mistral), a line
counts only when its IP is inside one of the published ranges; a line
outside them is an impostor and is counted apart. The others (Amazon
publishes HTML only, ByteDance, Meta, Yandex, Baidu, Huawei and Mistral's
training crawler none) stay "unverified".

The log starts with the deploy that added it (2026-10-09): the main access
log is 0640 www-data:adm and the deploy user cannot read its history.
logrotate turns it into a family of one file per day, kept 30 days
(ops/logrotate/ancientnerds); read_fetches reads all of it
(pipeline/log_files.py). Moved here from api/services/ on 2026-10-22 so the
request log (pipeline/request_log.py) shares one BOTS table.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from pipeline import log_files

LOG_PATH = Path(os.getenv("CRAWLER_LOG_PATH", "/app/logs/crawlers.log"))
#: How long a parse is reused when the file has not been read for this long.
CACHE_MIN_SECONDS = 55.0
#: How long the operators' address lists are reused; they change monthly.
RANGES_TTL_SECONDS = 24 * 3600

#: What a fetch is for. "ai_user" is the strongest GEO signal on the page: a
#: person asked an assistant something and it read our page to answer.
KINDS = ("search", "ai_user", "ai_search", "training", "other")


@dataclass(frozen=True)
class Bot:
    name: str
    operator: str
    kind: str


#: User-agent token -> bot. Every key is lower case: bot_of looks the matched
#: token up lower-cased. Matched case-insensitively, the longest token first
#: (BOT_RE), so a token that contains another one wins over it.
BOTS: dict[str, Bot] = {
    "googlebot": Bot("Googlebot", "google", "search"),
    "google-inspectiontool": Bot("Google-InspectionTool", "google", "search"),
    "googleother": Bot("GoogleOther", "google", "other"),
    "google-agent": Bot("Google-Agent", "google", "ai_user"),
    "google-gemininotebook": Bot("Google-GeminiNotebook", "google", "ai_user"),
    "google-cloudvertexbot": Bot("Google-CloudVertexBot", "google", "other"),
    "bingbot": Bot("Bingbot", "bing", "search"),
    "applebot": Bot("Applebot", "apple", "search"),
    "duckduckbot": Bot("DuckDuckBot", "duckduckgo", "search"),
    "duckassistbot": Bot("DuckAssistBot", "duckduckgo", "ai_search"),
    "yandexbot": Bot("YandexBot", "yandex", "search"),
    "baiduspider": Bot("Baiduspider", "baidu", "search"),
    "petalbot": Bot("PetalBot", "huawei", "search"),
    "chatgpt-user": Bot("ChatGPT-User", "openai", "ai_user"),
    "oai-searchbot": Bot("OAI-SearchBot", "openai", "ai_search"),
    "gptbot": Bot("GPTBot", "openai", "training"),
    "oai-adsbot": Bot("OAI-AdsBot", "openai", "other"),
    "claude-user": Bot("Claude-User", "anthropic", "ai_user"),
    "claude-searchbot": Bot("Claude-SearchBot", "anthropic", "ai_search"),
    "claudebot": Bot("ClaudeBot", "anthropic", "training"),
    "perplexity-user": Bot("Perplexity-User", "perplexity", "ai_user"),
    "perplexitybot": Bot("PerplexityBot", "perplexity", "ai_search"),
    "mistralai-user": Bot("MistralAI-User", "mistral", "ai_user"),
    "mistralai-index": Bot("MistralAI-Index", "mistral", "ai_search"),
    # Its own operator: Mistral publishes no list for it, so it is never
    # checked against the user and index lists and never called an impostor.
    "mistralai-training": Bot("MistralAI-Training", "mistral-training", "training"),
    "ccbot": Bot("CCBot", "commoncrawl", "training"),
    "bytespider": Bot("Bytespider", "bytedance", "training"),
    "meta-externalagent": Bot("meta-externalagent", "meta", "training"),
    "meta-externalfetcher": Bot("meta-externalfetcher", "meta", "ai_user"),
    "meta-webindexer": Bot("meta-webindexer", "meta", "ai_search"),
    "facebookexternalhit": Bot("facebookexternalhit", "meta", "other"),
    # Amazon says what Amazonbot fetches may train its AI models.
    "amazonbot": Bot("Amazonbot", "amazon", "training"),
    "amzn-searchbot": Bot("Amzn-SearchBot", "amazon", "search"),
    "amzn-user": Bot("Amzn-User", "amazon", "ai_user"),
}
BOT_RE = re.compile(
    "|".join(re.escape(t) for t in sorted(BOTS, key=len, reverse=True)), re.IGNORECASE
)

#: The operators' published address lists, all in the same JSON shape
#: ({"prefixes": [{"ipv4Prefix": ...} | {"ipv6Prefix": ...}]}). Each URL
#: answered 200 in that shape on 2026-10-22; Google's moved from
#: /search/apis/ipranges/ to /crawling/ipranges/ on 2026-10-09 and the old one
#: now redirects, and perplexity.com is now a redirect to perplexity.ai.
#: Amazon publishes its addresses as an HTML page only, so it has no entry.
RANGE_URLS: dict[str, list[str]] = {
    "google": [
        "https://developers.google.com/static/crawling/ipranges/common-crawlers.json",
        "https://developers.google.com/static/crawling/ipranges/special-crawlers.json",
        "https://developers.google.com/static/crawling/ipranges/user-triggered-fetchers-google.json",
        "https://developers.google.com/static/crawling/ipranges/user-triggered-agents.json",
    ],
    "bing": ["https://www.bing.com/toolbox/bingbot.json"],
    "openai": [
        "https://openai.com/gptbot.json",
        "https://openai.com/searchbot.json",
        "https://openai.com/chatgpt-user.json",
        "https://openai.com/adsbot.json",
    ],
    "perplexity": [
        "https://www.perplexity.ai/perplexitybot.json",
        "https://www.perplexity.ai/perplexity-user.json",
    ],
    "apple": ["https://search.developer.apple.com/applebot.json"],
    "anthropic": ["https://claude.com/crawling/bots.json"],
    "commoncrawl": ["https://index.commoncrawl.org/ccbot.json"],
    "duckduckgo": [
        "https://duckduckgo.com/duckduckbot.json",
        "https://duckduckgo.com/duckassistbot.json",
    ],
    "mistral": [
        "https://mistral.ai/mistralai-user-ips.json",
        "https://mistral.ai/mistralai-index-ips.json",
    ],
}

Network = ipaddress.IPv4Network | ipaddress.IPv6Network


@dataclass(frozen=True)
class Fetch:
    at: datetime
    ip: str
    path: str
    status: int
    bot: Bot


def bot_of(ua: str) -> Bot | None:
    match = BOT_RE.search(ua)
    return BOTS[match.group(0).lower()] if match else None


def parse_lines(lines: list[str]) -> list[Fetch]:
    """Every line naming a known bot. A half line (nginx still writing it, or
    a crash) is skipped like broken JSON."""
    out: list[Fetch] = []
    for raw in lines:
        line = raw.strip()
        if not line.startswith("{"):
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        bot = bot_of(entry["ua"])
        if bot is None:
            continue
        _method, _, target = entry["req"].partition(" ")
        out.append(
            Fetch(
                at=datetime.fromisoformat(entry["t"]),
                ip=entry["ip"],
                path=target.split("?", 1)[0],
                status=int(entry["status"]),
                bot=bot,
            )
        )
    return out


#: Per file of the family: its identity when parsed and what it held. A
#: rotated file never changes, so only the live one is ever parsed again.
_files: dict[Path, tuple[tuple[int, int, int], list[Fetch]]] = {}
#: The last answer and when it was put together.
_parsed: tuple[float, list[Fetch]] | None = None


def read_fetches() -> list[Fetch] | None:
    """Every fetch of the whole family (log_files.family), oldest first; None
    when the current file is not there (every dev box, and the VPS before
    the deploy that added it)."""
    global _parsed
    if not LOG_PATH.exists():
        return None
    now = time.monotonic()
    if _parsed is not None and now - _parsed[0] < CACHE_MIN_SECONDS:
        return _parsed[1]
    paths = log_files.family(LOG_PATH)
    for gone in set(_files) - set(paths):
        del _files[gone]
    for p in paths:
        identity = log_files.file_identity(p)
        if p not in _files or _files[p][0] != identity:
            _files[p] = (identity, parse_lines(log_files.read_file(p)))
    fetches = [f for p in paths for f in _files[p][1]]
    _parsed = (now, fetches)
    return fetches


def unavailable_reason() -> str:
    return (
        f"nginx's crawler log is not readable at {LOG_PATH}. It is bind-mounted read-only "
        "into the API containers on the VPS (./logs:/app/logs:ro); a development box has none."
    )


_ranges: tuple[float, dict[str, list[Network]]] | None = None


async def published_ranges() -> dict[str, list[Network]]:
    """Every operator's published networks, fetched once a day."""
    global _ranges
    now = time.monotonic()
    if _ranges is not None and now - _ranges[0] < RANGES_TTL_SECONDS:
        return _ranges[1]
    out: dict[str, list[Network]] = {}
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        for operator, urls in RANGE_URLS.items():
            networks: list[Network] = []
            for url in urls:
                response = await client.get(url)
                response.raise_for_status()
                for prefix in response.json()["prefixes"]:
                    networks.append(
                        ipaddress.ip_network(prefix.get("ipv4Prefix") or prefix["ipv6Prefix"])
                    )
            out[operator] = networks
    _ranges = (now, out)
    return out


def verified(fetch: Fetch, ranges: dict[str, list[Network]]) -> bool | None:
    """True inside the operator's published ranges, False outside them (an
    impostor), None for an operator that publishes none."""
    return verified_ip(fetch.bot, fetch.ip, ranges)


def verified_ip(bot: Bot, ip: str, ranges: dict[str, list[Network]]) -> bool | None:
    """verified() for a bot and an address from any log (pipeline/request_log.py)."""
    networks = ranges.get(bot.operator)
    if networks is None:
        return None
    address = ipaddress.ip_address(ip)
    return any(address in net for net in networks if net.version == address.version)


def _status_class(status: int) -> str:
    return f"{status // 100}xx"


#: Paths the AI-for-a-user list shows.
TOP_PAGES = 10


def crawler_report(
    fetches: list[Fetch], ranges: dict[str, list[Network]], since: datetime
) -> dict[str, Any]:
    """The panel's answer for the window: per bot its requests, distinct pages
    and status classes; per day the requests of each kind; the pages AI
    assistants read for a person; and what impostors claimed to be."""
    by_bot: dict[str, dict[str, Any]] = {}
    paths: defaultdict[str, set[str]] = defaultdict(set)
    statuses: defaultdict[str, Counter[str]] = defaultdict(Counter)
    per_day: defaultdict[str, Counter[str]] = defaultdict(Counter)
    impostors: Counter[str] = Counter()
    ai_pages: Counter[tuple[str, str]] = Counter()
    # One check per address, not per line: a crawler fetches from a handful
    # of IPs, and Google alone publishes a few hundred networks.
    checked: dict[tuple[str, str], bool | None] = {}
    for f in (f for f in fetches if f.at >= since):
        key = (f.bot.operator, f.ip)
        if key not in checked:
            checked[key] = verified(f, ranges)
        check = checked[key]
        if check is False:
            impostors[f.bot.name] += 1
            continue
        row = by_bot.setdefault(
            f.bot.name,
            {
                "bot": f.bot.name,
                "operator": f.bot.operator,
                "kind": f.bot.kind,
                "verified": check,
                "requests": 0,
            },
        )
        row["requests"] += 1
        paths[f.bot.name].add(f.path)
        statuses[f.bot.name][_status_class(f.status)] += 1
        # UTC days, like every other line on the page; the log writes VPS local time.
        per_day[f.at.astimezone(UTC).date().isoformat()][f.bot.kind] += 1
        if f.bot.kind == "ai_user":
            ai_pages[(f.path, f.bot.name)] += 1
    bots = sorted(by_bot.values(), key=lambda r: -r["requests"])
    for row in bots:
        row["pages"] = len(paths[row["bot"]])
        row["statuses"] = dict(statuses[row["bot"]])
    return {
        "covered_from": min(f.at for f in fetches).isoformat() if fetches else None,
        "bots": bots,
        "days": [
            {"day": day, **{k: counts[k] for k in KINDS}} for day, counts in sorted(per_day.items())
        ],
        "ai_user_pages": [
            {"path": path, "bot": bot, "requests": n}
            for (path, bot), n in ai_pages.most_common(TOP_PAGES)
        ],
        "impostors": [{"bot": bot, "requests": n} for bot, n in impostors.most_common()],
    }
