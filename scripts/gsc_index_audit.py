"""Sample URL-inspection audit: why are sitemap URLs not indexed?

The GSC coverage report (indexed / not-indexed reasons) has no API, but the
URL Inspection API returns the per-URL reason. This samples URLs from each
child sitemap and aggregates coverageState so we can see the breakdown.

Usage:
    python scripts/gsc_index_audit.py [--per-type N]

Quota: 2000 inspections/day per property, 600/min.
"""

import argparse
import random
import re
import sys
from collections import Counter, defaultdict

import requests
from gsc_report import INSPECT_API, detect_property, get_session

SITEMAPS = {
    "static": 4,
    "sites": 30,
    "countries": 6,
    "stories": 20,
    "research": 4,
    "articles": 4,
}


def sitemap_urls(name: str) -> list[str]:
    resp = requests.get(f"https://ancientnerds.com/sitemap-{name}.xml", timeout=30)
    resp.raise_for_status()
    return re.findall(r"<loc>(.*?)</loc>", resp.text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-type", type=int, help="override sample size for every type")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = random.Random(args.seed)  # noqa: S311 — reproducible sampling, nothing cryptographic
    session = get_session()
    site_url = detect_property(session)

    counts = defaultdict(Counter)
    examples = defaultdict(dict)

    for name, default_n in SITEMAPS.items():
        urls = sitemap_urls(name)
        n = args.per_type or default_n
        sample = rng.sample(urls, min(n, len(urls)))
        for url in sample:
            resp = session.post(INSPECT_API, json={"inspectionUrl": url, "siteUrl": site_url})
            resp.raise_for_status()
            idx = resp.json()["inspectionResult"]["indexStatusResult"]
            state = idx.get("coverageState", "?")
            crawled = "crawled" if idx.get("lastCrawlTime") else "never crawled"
            key = f"{state} [{crawled}]"
            counts[name][key] += 1
            examples[name].setdefault(key, url)
            print(f"  {name:10} {state:55} {url}", flush=True)

    print("\n=== Breakdown by type ===")
    for name in SITEMAPS:
        total = sum(counts[name].values())
        print(f"\n{name} (sample {total}):")
        for state, c in counts[name].most_common():
            print(f"  {c:>3}  {state}")
            print(f"       e.g. {examples[name][state]}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
