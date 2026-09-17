# SPDX-License-Identifier: AGPL-3.0-only
"""Referral report: who sends people here, and whether they are human.

nginx writes one JSON line per request that arrives with a referer from
another host or with a utm_source (ancientnerds-nginx-config, log_format
``referral``) to /var/www/ancientnerds/logs/referrals.log:

    {"t":"2026-09-17T12:00:00+00:00","ref":"https://chatgpt.com/",
     "req":"GET /sites/egypt","status":200,"ua":"Mozilla/5.0 ..."}

No client IP is logged. This script groups those lines by referrer host and
family — AI assistant, search engine, social, other — and splits humans
from bots with the rule the Discord funnel uses (api.routes.goto.BOT_UA_RE).
Only page views count by default: assets and API calls that carry a foreign
referer are hotlinks, not visits.

Two caveats built into the data, not the script:

- A click out of a Google AI Overview arrives with a google.com referer and
  is indistinguishable from a classic search click. Only assistant apps
  (chatgpt.com, perplexity.ai, ...) are separable.
- ChatGPT appends ``utm_source=chatgpt.com`` to outbound links because its
  apps often send no referer at all. A utm_source that names a known host is
  therefore taken as the source when the referer is missing.

Usage:
    python scripts/referral_report.py                 # ssh ancientnerds, last 7 days
    python scripts/referral_report.py --since 28d
    python scripts/referral_report.py --since 2026-09-17T00:00:00+00:00 --all
    ssh ancientnerds cat /var/www/ancientnerds/logs/referrals.log \\
        | python scripts/referral_report.py --stdin
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

# Run from anywhere: the repo root must be importable for api.routes.goto.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.routes.goto import BOT_UA_RE  # noqa: E402

LOG_PATH = "/var/www/ancientnerds/logs/referrals.log"
SSH_HOST = "ancientnerds"

#: Referrer host families, first match wins. Hosts are matched as the host
#: itself or any subdomain of it.
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

#: Request paths that are not page views even with a foreign referer.
_NON_PAGE_PREFIX = ("/api/", "/assets/", "/data/", "/fonts/", "/landing/", "/goto/")
_NON_PAGE_SUFFIX = re.compile(r"\.(?!html$)[a-z0-9]{1,5}$", re.IGNORECASE)


def family_of(host: str) -> str:
    for name, pattern in FAMILIES:
        if pattern.search(host):
            return name
    return "other"


def source_host(ref: str, req: str) -> str:
    """Referrer host, lower-case, ``www.`` stripped; utm_source when there is
    no referer and the utm_source names a known host."""
    host = urlsplit(ref).hostname or ""
    if not host:
        query = urlsplit(req.split(" ", 1)[-1]).query
        utm = parse_qs(query).get("utm_source", [""])[0].lower()
        if "." in utm and family_of(utm) != "other":
            host = utm
    return host.lower().removeprefix("www.")


def is_page(req: str) -> bool:
    path = urlsplit(req.split(" ", 1)[-1]).path
    if path.startswith(_NON_PAGE_PREFIX):
        return False
    return not _NON_PAGE_SUFFIX.search(path)


def parse_since(value: str, now: datetime | None = None) -> datetime:
    """``7d`` / ``24h`` relative to now, or an ISO 8601 timestamp."""
    now = now or datetime.now(UTC)
    m = re.fullmatch(r"(\d+)([dh])", value)
    if m:
        amount, unit = int(m.group(1)), m.group(2)
        return now - (timedelta(days=amount) if unit == "d" else timedelta(hours=amount))
    since = datetime.fromisoformat(value)
    return since if since.tzinfo else since.replace(tzinfo=UTC)


def aggregate(
    lines: Iterable[str], since: datetime, pages_only: bool = True
) -> dict[str, dict[str, Counter]]:
    """{family: {host: Counter(human=…, bot=…)}} for entries at or after ``since``."""
    result: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    for line in lines:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if datetime.fromisoformat(entry["t"]) < since:
            continue
        if pages_only and not is_page(entry["req"]):
            continue
        host = source_host(entry.get("ref", ""), entry["req"])
        if not host:
            continue
        kind = "bot" if BOT_UA_RE.search(entry.get("ua", "")) else "human"
        result[family_of(host)][host][kind] += 1
    return result


def print_report(result: dict[str, dict[str, Counter]], since: datetime) -> None:
    print(f"Referrals since {since.isoformat(timespec='minutes')} (page views unless --all)\n")
    print(f"  {'human':>6} {'bot':>5}  family / host")
    for family in ("ai", "search", "social", "other"):
        hosts = result.get(family, {})
        human = sum(c["human"] for c in hosts.values())
        bot = sum(c["bot"] for c in hosts.values())
        print(f"  {human:>6} {bot:>5}  {family.upper()}")
        for host, counts in sorted(hosts.items(), key=lambda kv: (-kv[1]["human"], -kv[1]["bot"])):
            print(f"  {counts['human']:>6} {counts['bot']:>5}    {host}")


def read_log() -> list[str]:
    out = subprocess.run(
        ["ssh", SSH_HOST, "cat", LOG_PATH], capture_output=True, text=True, check=True
    )
    return out.stdout.splitlines()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--since", default="7d", help="7d, 24h or ISO 8601 (default 7d)")
    parser.add_argument("--all", action="store_true", help="count assets and API calls too")
    parser.add_argument("--stdin", action="store_true", help="read log lines from stdin")
    args = parser.parse_args()

    since = parse_since(args.since)
    lines = sys.stdin.read().splitlines() if args.stdin else read_log()
    print_report(aggregate(lines, since, pages_only=not args.all), since)


if __name__ == "__main__":
    main()
