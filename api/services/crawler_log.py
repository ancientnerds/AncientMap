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
Perplexity, Apple), a line counts only when its IP is inside one of the
published ranges; a line outside them is an impostor and is counted apart.
Anthropic publishes no list, so its bots stay "unverified".

The log starts with the deploy that added it (2026-10-09): the main access
log is 0640 www-data:adm and the deploy user cannot read its history.
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

LOG_PATH = Path(os.getenv("CRAWLER_LOG_PATH", "/app/logs/crawlers.log"))
#: How much of the file one parse reads, from the end. Page fetches only, so a
#: line is ~250 bytes; 32 MiB holds ~130,000 of them.
MAX_TAIL_BYTES = 32 * 1024 * 1024
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


#: User-agent token -> bot. Order matters only where one token contains
#: another; none of these does. Matched case-insensitively.
BOTS: dict[str, Bot] = {
    "googlebot": Bot("Googlebot", "google", "search"),
    "google-inspectiontool": Bot("Google-InspectionTool", "google", "search"),
    "googleother": Bot("GoogleOther", "google", "other"),
    "bingbot": Bot("Bingbot", "bing", "search"),
    "applebot": Bot("Applebot", "apple", "search"),
    "duckduckbot": Bot("DuckDuckBot", "duckduckgo", "search"),
    "yandexbot": Bot("YandexBot", "yandex", "search"),
    "baiduspider": Bot("Baiduspider", "baidu", "search"),
    "petalbot": Bot("PetalBot", "huawei", "search"),
    "chatgpt-user": Bot("ChatGPT-User", "openai", "ai_user"),
    "oai-searchbot": Bot("OAI-SearchBot", "openai", "ai_search"),
    "gptbot": Bot("GPTBot", "openai", "training"),
    "claude-user": Bot("Claude-User", "anthropic", "ai_user"),
    "claude-searchbot": Bot("Claude-SearchBot", "anthropic", "ai_search"),
    "claudebot": Bot("ClaudeBot", "anthropic", "training"),
    "perplexity-user": Bot("Perplexity-User", "perplexity", "ai_user"),
    "perplexitybot": Bot("PerplexityBot", "perplexity", "ai_search"),
    "mistralai-user": Bot("MistralAI-User", "mistral", "ai_user"),
    "ccbot": Bot("CCBot", "commoncrawl", "training"),
    "bytespider": Bot("Bytespider", "bytedance", "training"),
    "meta-externalagent": Bot("meta-externalagent", "meta", "training"),
    "amazonbot": Bot("Amazonbot", "amazon", "other"),
}
BOT_RE = re.compile("|".join(re.escape(t) for t in BOTS), re.IGNORECASE)

#: The operators' published address lists, all in the same JSON shape
#: ({"prefixes": [{"ipv4Prefix": ...} | {"ipv6Prefix": ...}]}). Each URL
#: answered 200 on 2026-10-09; Google's moved from /search/apis/ipranges/ to
#: /crawling/ipranges/ and the old one now redirects.
RANGE_URLS: dict[str, list[str]] = {
    "google": [
        "https://developers.google.com/static/crawling/ipranges/common-crawlers.json",
        "https://developers.google.com/static/crawling/ipranges/special-crawlers.json",
        "https://developers.google.com/static/crawling/ipranges/user-triggered-fetchers-google.json",
    ],
    "bing": ["https://www.bing.com/toolbox/bingbot.json"],
    "openai": [
        "https://openai.com/gptbot.json",
        "https://openai.com/searchbot.json",
        "https://openai.com/chatgpt-user.json",
    ],
    "perplexity": [
        "https://www.perplexity.com/perplexitybot.json",
        "https://www.perplexity.com/perplexity-user.json",
    ],
    "apple": ["https://search.developer.apple.com/applebot.json"],
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
    """Every line naming a known bot. The tail is read from a byte offset, so
    the first line is regularly half a line and is skipped like broken JSON."""
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


_parsed: tuple[tuple[int, int], float, list[Fetch]] | None = None


def read_fetches() -> list[Fetch] | None:
    """The log's tail, parsed; None when the file is not there (every dev box,
    and the VPS before the deploy that adds it)."""
    global _parsed
    try:
        stat = LOG_PATH.stat()
    except OSError:
        return None
    identity = (stat.st_mtime_ns, stat.st_size)
    now = time.monotonic()
    if _parsed is not None and (_parsed[0] == identity or now - _parsed[1] < CACHE_MIN_SECONDS):
        return _parsed[2]
    with LOG_PATH.open("rb") as fh:
        if stat.st_size > MAX_TAIL_BYTES:
            fh.seek(stat.st_size - MAX_TAIL_BYTES)
        blob = fh.read()
    fetches = parse_lines(blob.decode("utf-8", "replace").splitlines())
    _parsed = (identity, now, fetches)
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
    networks = ranges.get(fetch.bot.operator)
    if networks is None:
        return None
    ip = ipaddress.ip_address(fetch.ip)
    return any(ip in net for net in networks if net.version == ip.version)


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
