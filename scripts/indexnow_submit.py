# SPDX-License-Identifier: AGPL-3.0-only
"""Submit URLs to IndexNow by hand — the one-off bulk run after setup, or a
few URLs after a manual fix.

    python scripts/indexnow_submit.py --all          # every URL the live sitemap lists
    python scripts/indexnow_submit.py --all --dry-run
    python scripts/indexnow_submit.py https://ancientnerds.com/sites/ https://ancientnerds.com/research/

--all reads https://ancientnerds.com/sitemap.xml and its parts over HTTP (the
local DB is empty, the live sitemap is the truth) and skips sitemap-legacy.xml:
those URLs answer 301 and are for Google's redirect processing, not for Bing.
The day-to-day announcements come from the orchestrator step and the publish
hooks (pipeline/indexnow.py); this script is not needed for them.
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.indexnow import CHUNK, submit  # noqa: E402

SITEMAP_INDEX = "https://ancientnerds.com/sitemap.xml"
_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def sitemap_urls(index_url: str = SITEMAP_INDEX) -> list[str]:
    """Every <loc> of every part the index lists, except the legacy part."""
    index = httpx.get(index_url, timeout=30.0)
    index.raise_for_status()
    parts = [el.text.strip() for el in ET.fromstring(index.content).findall(".//sm:loc", _NS)]
    urls: list[str] = []
    for part in parts:
        if part.endswith("sitemap-legacy.xml"):
            continue
        resp = httpx.get(part, timeout=60.0)
        resp.raise_for_status()
        urls += [
            el.text.strip() for el in ET.fromstring(resp.content).findall(".//sm:url/sm:loc", _NS)
        ]
    return urls


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("urls", nargs="*", help="URLs to submit")
    parser.add_argument("--all", action="store_true", help="submit every URL in the live sitemap")
    parser.add_argument("--dry-run", action="store_true", help="only count, do not submit")
    args = parser.parse_args()

    urls = sitemap_urls() if args.all else args.urls
    if not urls:
        parser.error("give URLs or --all")
    chunks = -(-len(urls) // CHUNK)
    print(f"{len(urls)} URLs in {chunks} request(s) of up to {CHUNK}")
    if args.dry_run:
        return
    print("accepted" if submit(urls) else "REJECTED or failed — see log")


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
