# SPDX-License-Identifier: AGPL-3.0-only
"""nginx's referral log: who sends people here, and what we answered them.

nginx writes one JSON line per request that arrives with a referer from
another host or with a utm_source (log_format ``referral``) to
/var/www/ancientnerds/logs/referrals.log, which docker-compose binds into the
API containers read-only at /app/logs:

    {"t":"2026-09-17T12:00:00+02:00","ref":"https://chatgpt.com/",
     "req":"GET /sites/egypt","status":200,"ua":"Mozilla/5.0 ..."}

This is the only view we have of two things Umami cannot see: arrivals whose
tracker never ran, and the status code we served. Measured 2026-09-19 over
407 lines: nginx answered 189 Google page arrivals while Umami recorded 62
views from 51 sessions, and 21 of those 189 were a 410 for a retracted story
- an answer no event reports, because the 410 page raises none
(pipeline/article_html_renderer.py, render_error_html).

Five things the parser has to get right, each of them measured:

* ``$time_iso8601`` is VPS local time (+02:00 now, +01:00 after October).
  ``datetime.fromisoformat`` handles the offset; ``strptime`` without it or
  any string slicing is a silent two-hour window shift.
* Browsers do not all send a scheme. 55 of 407 lines carried a bare
  ``www.google.com`` or ``binance.com``, for which ``urlsplit(...).hostname``
  is None. Those lines have to be parsed to be *rejected* on their status:
  unparsed they are invisible, parsed and unfiltered they are the whole
  error list.
* A utm_source need not contain a dot: Perplexity tags its links
  ``utm_source=perplexity`` and our own Discord bot tags them
  ``utm_source=discord``. UTM_ALIASES maps every bare label we emit or
  receive onto a host, so family_of() can see it.
* 47 of 407 lines (11.5 %) come from ``http://localhost:5199/`` - a founder's
  own Vite dev server calling production. Left in, it is us looking at
  ourselves.
* A user agent cannot separate a scanner from a visitor here. BOT_UA_RE
  flagged 1 of 360 kept lines; the busiest scanner forges a plain
  ``Mozilla/5.0 ... Chrome/90.0.4430.85`` and probes /wp-admin/,
  /.well-known/ and /uploads/, none of which has a file extension, so
  is_page() says yes to all of them. The **status code** carries most of that
  job - measured over the live log, every single 404 and 403 is a forged
  referer - but it does not carry all of it: 17 lines of the same log are an
  SEO referrer-spam campaign that asks for ``/``, is answered 200 and forges
  a plain browser UA. It is one request per throwaway host, all with the same
  referer path, and it was the entire "other" family. Hence the second rule in
  coverage_report(): a host in no known family has to be seen
  UNKNOWN_HOST_MIN times in the window before it counts as an arrival.

Read-only. Nothing here writes into /app/logs.

The CLI on top of this module is scripts/referral_report.py.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

#: Where the log is mounted inside the API container (docker-compose.yml binds
#: ./logs:/app/logs:ro on the api service anchor, which api2 inherits). The
#: environment variable exists so the CLI and the tests can point elsewhere.
LOG_PATH = Path(os.getenv("REFERRAL_LOG_PATH", "/app/logs/referrals.log"))

#: How much of the tail is ever read. Measured inside ancient_nerds_api on
#: 2026-09-19: 408 lines / 110 KB parse in 8.6 ms, i.e. 21 us per line and
#: ~80 ms per megabyte. The log grows ~56 KB a day at today's rate, so one
#: megabyte is about 19 days of history and costs about 80 ms to parse.
#: That parse blocks the event loop of whichever API container serves
#: /sources, once per CACHE_MIN_SECONDS, so the ceiling is a deliberate
#: trade and not a round number: 19 days comfortably covers the panel's
#: 7-day default, and the response carries covered_days so a founder asking
#: for 30 or 90 days can see how far back the log actually reaches. Ticket
#: T10 moves the parse onto asyncio.to_thread when this stops being enough.
MAX_TAIL_BYTES = 1024 * 1024

#: The parse is skipped unless the file changed AND this long has passed. The
#: file identity alone is not enough: at ten times today's traffic a new line
#: arrives every 43 seconds, which is shorter than the dashboard's refresh, so
#: every refresh would re-parse.
CACHE_MIN_SECONDS = 55.0

#: Our own machines. A localhost referer is the founder's dev server, not a
#: referral.
OWN_HOSTS = ("localhost", "127.0.0.1")

#: UA substrings that mark automated clients. Deliberately broad: the point is
#: separating "a person arrived" from "a crawler followed a link", not perfect
#: bot taxonomy. Misclassified stragglers land in the bot bucket, which only
#: makes the human count conservative. The Discord funnel redirect
#: (api/routes/goto.py) imports this - one definition in the repo.
BOT_UA_RE = re.compile(
    r"bot|crawl|spider|slurp|scrapy|curl|wget|python-requests|python-httpx|aiohttp"
    r"|headless|phantom|lighthouse|facebookexternalhit|whatsapp|telegram|preview"
    r"|go-http-client|okhttp|java/|libwww",
    re.IGNORECASE,
)

#: Referrer host families, first match wins. Hosts match as the host itself or
#: any subdomain of it.
FAMILIES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "ai",
        re.compile(
            r"(^|\.)(chatgpt\.com|openai\.com|perplexity\.ai|copilot\.microsoft\.com"
            r"|gemini\.google\.com|claude\.ai|you\.com|mistral\.ai|chat\.deepseek\.com"
            r"|phind\.com|grok\.com|meta\.ai)$"
        ),
    ),
    (
        "search",
        re.compile(
            r"(^|\.)(google\.[a-z.]+|bing\.com|duckduckgo\.com|yandex\.[a-z]+|ecosia\.org"
            r"|baidu\.com|search\.brave\.com|qwant\.com|startpage\.com|yahoo\.com|kagi\.com)$"
        ),
    ),
    (
        "social",
        re.compile(
            r"(^|\.)(discord\.com|discordapp\.com|reddit\.com|x\.com|twitter\.com|t\.co"
            r"|facebook\.com|instagram\.com|youtube\.com|linkedin\.com|threads\.net"
            r"|mastodon\.[a-z]+|bsky\.app|tiktok\.com|pinterest\.[a-z.]+)$"
        ),
    ),
)

#: A bare utm label that names a source without naming a host. Every value
#: live in the log on 2026-09-19 is covered: chatgpt.com (19 lines, already a
#: host), discord (2 - our own bot's links, which without the alias render as
#: a "host" literally called discord in the "other" family) and perplexity
#: (1). reddit and youtube are listed because the bot can post there too.
UTM_ALIASES = {
    "perplexity": "perplexity.ai",
    "chatgpt": "chatgpt.com",
    "openai": "openai.com",
    "discord": "discord.com",
    "reddit": "reddit.com",
    "youtube": "youtube.com",
}

#: Request paths that are not page views even with a foreign referer.
_NON_PAGE_PREFIX = ("/api/", "/assets/", "/data/", "/fonts/", "/landing/", "/goto/")
_NON_PAGE_SUFFIX = re.compile(r"\.(?!html$)[a-z0-9]{1,5}$", re.IGNORECASE)

#: A Referer header logged without a scheme: "www.google.com" or
#: "binance.com/x". Anchored, so a full URL never reaches this branch.
_BARE_HOST = re.compile(r"^[a-z0-9.-]+(?::\d+)?(?:/|$)", re.IGNORECASE)

#: How many host rows the coverage block hands to the panel. The families and
#: the statuses are never truncated - there are four of one and three of the
#: other.
REPORT_ROWS = 8

#: A status that means "nginx handed this visitor a page". 200 is the good
#: case; 410 is a story we withdrew on purpose, which is still an arrival and
#: is the single biggest thing Umami cannot see. Everything else is counted
#: out of `families` and `hosts`: a 3xx is a redirect on its way to its own
#: 200 (19 of the live 27 are the legacy /site.html rule) and counting both
#: would count one visitor twice, and a 4xx is a forged referer - measured
#: 2026-09-19, all 50 of the live 404s and all 4 of the 403s are, and a real
#: 404 raises a not_found event that the Problems panel already ranks.
ARRIVAL_STATUSES = frozenset({200, 410})

#: What family_of() answers for a host in none of FAMILIES.
OTHER_FAMILY = "other"

#: How many arrivals a host in OTHER_FAMILY needs in the window before it is
#: reported as an arrival. Measured 2026-09-19 over the live 417-line log: all
#: 17 arrivals of the "other" family were one referrer-spam campaign - one
#: request per throwaway host (seostatschecker.space, daparankchecker.store,
#: bulkbacklinkanalysis.shop, …), every one of them "GET /" answered 200 with
#: the identical referer path /dir/white-hat-link-building-9465 and a forged
#: browser UA. At 2 they all disappear and not one real referrer moves:
#: google.com, chatgpt.com, duckduckgo.com, bing.com, perplexity.ai,
#: gemini.google.com and discord.com are all family-matched and never pass
#: through this gate. A host that sends us two people is a referral worth
#: seeing, and it enters the list on its second visit.
UNKNOWN_HOST_MIN = 2


def is_bad_answer(status: int) -> bool:
    """An answer a founder has to know about, and that nothing else on the
    dashboard can see. 410 (a retracted story Google still links to, 21 live),
    499 (the visitor closed the tab before we finished, 4 live) and every 5xx
    (1 live). Deliberately not 404: see ARRIVAL_STATUSES."""
    return status in (410, 499) or status >= 500


def family_of(host: str) -> str:
    for name, pattern in FAMILIES:
        if pattern.search(host):
            return name
    return "other"


def referrer_host(ref: str, req: str) -> str:
    """The referring host: lower case, no scheme, no port, no ``www.``.

    Two legal shapes for one field, both live: a full URL and a bare host.
    When there is no referer at all, a utm_source on the request names the
    source instead - ChatGPT tags its outbound links and sends no referer.
    """
    host = urlsplit(ref).hostname or ""
    if not host and _BARE_HOST.match(ref):
        host = ref.split("/", 1)[0]
    if not host:
        query = urlsplit(req.split(" ", 1)[-1]).query
        utm = parse_qs(query).get("utm_source", [""])[0].lower()
        host = UTM_ALIASES.get(utm, utm)
    return host.lower().split(":", 1)[0].removeprefix("www.")


def is_page(req: str) -> bool:
    path = urlsplit(req.split(" ", 1)[-1]).path
    if path.startswith(_NON_PAGE_PREFIX):
        return False
    return not _NON_PAGE_SUFFIX.search(path)


@dataclass(frozen=True, slots=True)
class Visit:
    at: datetime
    host: str
    family: str
    status: int
    bot: bool
    page: bool


def parse_lines(lines: Iterable[str]) -> list[Visit]:
    """Every line the log can answer for. A line without a JSON object, with
    broken JSON or without an attributable host is skipped - the tail is read
    from a byte offset, so the first line is regularly half a line."""
    out: list[Visit] = []
    for raw in lines:
        line = raw.strip()
        if not line.startswith("{"):
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        host = referrer_host(entry.get("ref", ""), entry["req"])
        if not host or host in OWN_HOSTS:
            continue
        out.append(
            Visit(
                at=datetime.fromisoformat(entry["t"]),
                host=host,
                family=family_of(host),
                status=int(entry["status"]),
                bot=bool(BOT_UA_RE.search(entry.get("ua", ""))),
                page=is_page(entry["req"]),
            )
        )
    return out


_cache: tuple[tuple[int, int], float, list[Visit]] | None = None


def read_visits() -> list[Visit] | None:
    """The log's tail, parsed. None when the file is not there - every dev box.

    Re-parsed only when the file changed and at least CACHE_MIN_SECONDS have
    passed since the last parse, so a busy log cannot turn the dashboard's
    once-a-minute refresh into a once-a-minute file read.
    """
    global _cache
    try:
        stat = LOG_PATH.stat()
    except OSError:
        return None
    identity = (stat.st_mtime_ns, stat.st_size)
    now = time.monotonic()
    if _cache is not None and (_cache[0] == identity or now - _cache[1] < CACHE_MIN_SECONDS):
        return _cache[2]
    with LOG_PATH.open("rb") as fh:
        if stat.st_size > MAX_TAIL_BYTES:
            fh.seek(stat.st_size - MAX_TAIL_BYTES)
        blob = fh.read()
    visits = parse_lines(blob.decode("utf-8", "replace").splitlines())
    _cache = (identity, now, visits)
    return visits


def unavailable_reason() -> str:
    """Why the coverage block is empty, in one English sentence for the panel."""
    return (
        f"nginx's referral log is not readable at {LOG_PATH}. "
        "It is bind-mounted read-only into the API containers on the VPS "
        "(docker-compose.yml, ./logs:/app/logs:ro); a development box has none."
    )


def aggregate(
    visits: Iterable[Visit], since: datetime, pages_only: bool = True
) -> dict[str, dict[str, Counter]]:
    """{family: {host: Counter(human=..., bot=...)}} - the CLI's table.

    Scanners send fake referers to paths that do not exist (/wp-admin/ from
    "binance.com"): a page view needs a page, so errors only count with --all.
    """
    result: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    for v in visits:
        if v.at < since:
            continue
        if pages_only and (v.status >= 400 or not v.page):
            continue
        result[v.family][v.host]["bot" if v.bot else "human"] += 1
    return result


def coverage_report(visits: Iterable[Visit], since: datetime, until: datetime) -> dict[str, Any]:
    """What nginx saw in the same window the panel is showing.

    An arrival is a page request from a non-bot UA that we answered with an
    ARRIVAL_STATUS, from a host that is either in a known family or was seen
    UNKNOWN_HOST_MIN times. All three parts are load-bearing and all three
    were measured on 2026-09-19 by running this module over the live log:

    * Without the status filter, `binance.com` is the second-largest host
      (28 visits), "other" is the second-largest family (48), and the status
      list reads 301x27, 404x21, 410x21, 403x4, 499x4, 405x2, 500x1 - i.e.
      21 scanner probes printed as "answers we gave referred visitors" and a
      redirect that works as designed printed as the biggest problem. That
      was the single biggest error in the drafts this plan replaces.
    * With it, and without the host rule: families search 210 / ai 22 /
      other 17 / social 1 - and every one of those 17 is the referrer-spam
      campaign the module docstring describes, three of them inside the eight
      host rows the panel prints.
    * With both: families search 210 / ai 22 / social 1, hosts google.com 196,
      chatgpt.com 20, duckduckgo.com 7, bing.com 4, and `unverified` 17.
      "other 0" is the honest reading of this log.

    The UA test cannot do this job - it caught 1 of 360 kept lines - so it
    only ever moves a visit into `bots`, never out of the error list.

    `unverified` is reported, not swallowed: it is the same treatment the bad
    statuses get, and a founder can see the size of what the rule removed.
    """
    window = [v for v in visits if since <= v.at < until]
    pages = [v for v in window if v.page]
    families: Counter[str] = Counter()
    bots: Counter[str] = Counter()
    hosts: Counter[str] = Counter()
    statuses: Counter[int] = Counter()
    arrivals = [v for v in pages if not v.bot and v.status in ARRIVAL_STATUSES]
    seen: Counter[str] = Counter(v.host for v in arrivals)
    unverified = 0
    for v in pages:
        if v.bot:
            bots[v.family] += 1
            continue
        if v.status in ARRIVAL_STATUSES:
            if v.family == OTHER_FAMILY and seen[v.host] < UNKNOWN_HOST_MIN:
                unverified += 1
            else:
                families[v.family] += 1
                hosts[v.host] += 1
        if is_bad_answer(v.status):
            statuses[v.status] += 1
    first = min((v.at for v in window), default=until)
    return {
        "covered_from": first.astimezone(UTC).isoformat(),
        "covered_days": round((until - first) / timedelta(days=1), 2),
        "lines": len(window),
        "unverified": unverified,
        "families": [
            {"family": f, "visits": n, "bots": bots.get(f, 0)}
            for f, n in sorted(families.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        "hosts": [
            {"host": h, "visits": n}
            for h, n in sorted(hosts.items(), key=lambda kv: (-kv[1], kv[0]))[:REPORT_ROWS]
        ],
        "statuses": [
            {"status": s, "visits": n}
            for s, n in sorted(statuses.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
    }
