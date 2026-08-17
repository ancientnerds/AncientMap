"""Discord funnel report: who clicks the CTA, from where, human or bot.

Every human-facing Discord link points at /goto/discord?src={surface}
(api/routes/goto.py), which logs exactly one line per click:

    INFO | api.routes.goto | goto_discord src=seo bot=0

This script aggregates those lines by source and bot flag and prints a
table. The bot flag is computed by the API from the user agent at click
time (known bot substrings, see _BOT_UA_RE in goto.py) — nothing else is
logged, so this is the whole dataset.

The nginx access log is deliberately NOT used: naive log counting
overstates clicks by ~3x because crawlers follow the link too. The API
containers' own logs carry the bot flag, so read those.

Usage on the VPS (both API instances serve behind the an_api upstream,
so both logs count):

    cd /var/www/ancientnerds
    python3 scripts/funnel_report.py --since 24h
    python3 scripts/funnel_report.py --since 2026-08-17T00:00:00

which runs, per container:

    docker logs --since <X> ancient_nerds_api
    docker logs --since <X> ancient_nerds_api2

From anywhere with SSH access, pipe the logs in instead:

    ssh ancientnerds 'docker logs --since 24h ancient_nerds_api 2>&1;
                      docker logs --since 24h ancient_nerds_api2 2>&1' \
        | python scripts/funnel_report.py --stdin
"""

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Iterable

#: Both API containers behind the an_api nginx upstream (8000 + 8001).
CONTAINERS = ("ancient_nerds_api", "ancient_nerds_api2")

#: The structured line goto_discord() writes — src is allowlisted by the
#: API, so this never matches free text.
_LINE_RE = re.compile(r"goto_discord src=(?P<src>[a-z]+) bot=(?P<bot>[01])")

#: Row order for the table; matches ALLOWED_SOURCES in api/routes/goto.py
#: plus the catch-all bucket.
SOURCES = ("seo", "landing", "app", "account", "lyra", "disclaimer", "unknown")


def parse_lines(lines: Iterable[str]) -> Counter:
    """Count (src, is_bot) pairs from raw log lines.

    Accepts both `docker logs` output (plain text) and raw json-file driver
    lines ({"log": "...", ...}) — the latter appear when reading
    /var/lib/docker/containers/*/*-json.log directly.
    """
    counts: Counter = Counter()
    for line in lines:
        if line.startswith("{"):
            try:
                line = json.loads(line).get("log", "")
            except json.JSONDecodeError:
                pass
        m = _LINE_RE.search(line)
        if m:
            counts[(m.group("src"), m.group("bot") == "1")] += 1
    return counts


def docker_lines(since: str) -> Iterable[str]:
    """Yield log lines of both API containers via `docker logs`."""
    for name in CONTAINERS:
        # uvicorn logs to stderr; a missing container (e.g. api2 during a
        # deploy window) must not kill the report for the other one.
        proc = subprocess.run(
            ["docker", "logs", "--since", since, name],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            print(f"warning: docker logs {name} failed: {proc.stderr.strip()}", file=sys.stderr)
            continue
        yield from proc.stdout.splitlines()
        yield from proc.stderr.splitlines()


def print_table(counts: Counter) -> None:
    total_humans = sum(n for (_, bot), n in counts.items() if not bot)
    total_bots = sum(n for (_, bot), n in counts.items() if bot)

    print(f"{'source':<12} {'humans':>7} {'bots':>7} {'total':>7}")
    print("-" * 36)
    for src in SOURCES:
        humans = counts.get((src, False), 0)
        bots = counts.get((src, True), 0)
        if humans or bots:
            print(f"{src:<12} {humans:>7} {bots:>7} {humans + bots:>7}")
    print("-" * 36)
    print(f"{'total':<12} {total_humans:>7} {total_bots:>7} {total_humans + total_bots:>7}")

    if not counts:
        print("(no goto_discord entries in the given window)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate Discord CTA clicks by source")
    parser.add_argument(
        "--since",
        default="24h",
        help="docker logs --since value: 24h, 30m, or an ISO timestamp (default: 24h)",
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="read log lines from stdin instead of running docker logs",
    )
    args = parser.parse_args()

    lines = sys.stdin if args.stdin else docker_lines(args.since)
    print_table(parse_lines(lines))


if __name__ == "__main__":
    main()
