# SPDX-License-Identifier: AGPL-3.0-only
"""Referral report: who sends people here, and whether they are human.

nginx writes one JSON line per request that arrives with a referer from
another host or with a utm_source (ancientnerds-nginx-config, log_format
``referral``) to /var/www/ancientnerds/logs/referrals.log:

    {"t":"2026-09-17T12:00:00+00:00","ref":"https://chatgpt.com/",
     "req":"GET /sites/egypt","status":200,"ua":"Mozilla/5.0 ..."}

No client IP is logged. The parsing lives in pipeline/referral_log.py, which
the /sources panel reads as well — one definition of "referring host",
"page view" and "bot" for the CLI and the dashboard. This script is the
table on top of it: referrer host and family — AI assistant, search engine,
social, other — humans against bots. Only page views count by default:
assets and API calls that carry a foreign referer are hotlinks, not visits,
and 4xx/5xx answers are scanner noise (fake referers on /wp-admin/).

Two caveats built into the data, not the script:

- A click out of a Google AI Overview arrives with a google.com referer and
  is indistinguishable from a classic search click. Only assistant apps
  (chatgpt.com, perplexity.ai, ...) are separable.
- ChatGPT appends ``utm_source=chatgpt.com`` to outbound links because its
  apps often send no referer at all. A utm_source therefore names the source
  when the referer is missing — a bare label too (``perplexity``,
  ``discord``): UTM_ALIASES maps the ones we know onto their host, and one we
  do not know stays as it is rather than being thrown away.

Usage:
    python scripts/referral_report.py                 # ssh ancientnerds, last 7 days
    python scripts/referral_report.py --since 28d
    python scripts/referral_report.py --since 2026-09-17T00:00:00+00:00 --all
    ssh ancientnerds cat /var/www/ancientnerds/logs/referrals.log \\
        | python scripts/referral_report.py --stdin
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Run from anywhere: the repo root must be importable for pipeline.referral_log.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.referral_log import aggregate, parse_lines  # noqa: E402

#: The path on the VPS, which is not the container mount
#: (pipeline.referral_log.LOG_PATH): read_log() hands it to ``ssh … cat``.
LOG_PATH = "/var/www/ancientnerds/logs/referrals.log"
SSH_HOST = "ancientnerds"


def parse_since(value: str, now: datetime | None = None) -> datetime:
    """``7d`` / ``24h`` relative to now, or an ISO 8601 timestamp."""
    now = now or datetime.now(UTC)
    m = re.fullmatch(r"(\d+)([dh])", value)
    if m:
        amount, unit = int(m.group(1)), m.group(2)
        return now - (timedelta(days=amount) if unit == "d" else timedelta(hours=amount))
    since = datetime.fromisoformat(value)
    return since if since.tzinfo else since.replace(tzinfo=UTC)


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
    print_report(aggregate(parse_lines(lines), since, pages_only=not args.all), since)


if __name__ == "__main__":
    main()
