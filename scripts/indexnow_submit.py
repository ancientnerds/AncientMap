# SPDX-License-Identifier: AGPL-3.0-only
"""Submit URLs to IndexNow by hand — the one-off bulk run after setup, or a
few URLs after a manual fix.

    python scripts/indexnow_submit.py --all          # every URL the live sitemap lists
    python scripts/indexnow_submit.py --all --dry-run
    python scripts/indexnow_submit.py --all --lastmod-since 2026-09-20   # changed pages only
    python scripts/indexnow_submit.py https://ancientnerds.com/sites/ https://ancientnerds.com/research/

--all reads https://ancientnerds.com/sitemap.xml and its parts over HTTP (the
local DB is empty, the live sitemap is the truth) and skips sitemap-legacy.xml:
those URLs answer 301 and are for Google's redirect processing, not for Bing.
The day-to-day announcements come from the orchestrator step and the publish
hooks (pipeline/indexnow.py); this script is not needed for them.

--lastmod-since keeps only the URLs whose <lastmod> is on or after the date. It is
the catch-up for changes older than the orchestrator's two-hour window - the 2026-09
remediation wrote 984 sites through the journal between 09-20 and 09-22, before the
sitemap's lastmod knew about journal writes. Once the sitemap carries the journal
(api/routes/sitemap.py), the pages those writes changed are exactly the ones with a
lastmod on or after the first write. The /sites/ template floor
(_SITES_TEMPLATE_CHANGED, 2026-09-12) lies before that, so it does not pull in the rest.
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.indexnow import CHUNK, submit  # noqa: E402

SITEMAP_INDEX = "https://ancientnerds.com/sitemap.xml"
_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def part_urls(xml: bytes, since: date | None = None) -> list[str]:
    """The <loc> of every <url> in one sitemap part; with ``since``, only those whose
    <lastmod> is on or after it (a URL without a lastmod never qualifies then)."""
    urls: list[str] = []
    for url in ET.fromstring(xml).findall(".//sm:url", _NS):
        loc = url.findtext("sm:loc", default="", namespaces=_NS).strip()
        if not loc:
            continue
        if since is not None:
            lastmod = url.findtext("sm:lastmod", default="", namespaces=_NS).strip()
            if not lastmod or date.fromisoformat(lastmod[:10]) < since:
                continue
        urls.append(loc)
    return urls


def sitemap_urls(index_url: str = SITEMAP_INDEX, since: date | None = None) -> list[str]:
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
        urls += part_urls(resp.content, since)
    return urls


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("urls", nargs="*", help="URLs to submit")
    parser.add_argument("--all", action="store_true", help="submit every URL in the live sitemap")
    parser.add_argument(
        "--lastmod-since",
        type=date.fromisoformat,
        help="with --all: only URLs whose sitemap lastmod is on or after this date (YYYY-MM-DD)",
    )
    parser.add_argument("--dry-run", action="store_true", help="only count, do not submit")
    args = parser.parse_args()

    if args.lastmod_since and not args.all:
        parser.error("--lastmod-since filters the sitemap; use it with --all")
    urls = sitemap_urls(since=args.lastmod_since) if args.all else args.urls
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
