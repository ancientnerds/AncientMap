#!/usr/bin/env python3
"""Process web-links batches: search for reference links via Serper.dev (async).

Usage:
    python scripts/process_weblink_batch.py all
    python scripts/process_weblink_batch.py 111-120
    python scripts/process_weblink_batch.py 111
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

load_dotenv()

BATCH_DIR = Path(__file__).parent.parent / "output" / "weblink_batches"
SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "a80494d8a70b5533b5eb289f3917bf9c48f29ed5")

# 10 concurrent batches, each with 10 sites searched in parallel
BATCH_CONCURRENCY = 3
SEARCH_TIMEOUT = 10

EXCLUDE_DOMAINS = {
    "tripadvisor.com", "booking.com", "viator.com", "getyourguide.com",
    "facebook.com", "instagram.com", "twitter.com", "x.com", "tiktok.com",
    "pinterest.com", "reddit.com", "quora.com",
    "youtube.com", "amazon.com", "ebay.com",
}

QUALITY_DOMAINS = {
    "wikipedia.org": "high",
    "unesco.org": "high", "whc.unesco.org": "high",
    "britannica.com": "high",
    "worldhistory.org": "high",
    "metmuseum.org": "high", "britishmuseum.org": "high",
    "jstor.org": "medium",
    "academia.edu": "medium",
    "pleiades.stoa.org": "high",
    "topostext.org": "high",
    "madainproject.com": "medium",
    "livius.org": "medium",
    "archaeology.org": "high",
    "smithsonianmag.com": "medium",
    "nationalgeographic.com": "medium",
    "heritagedaily.com": "medium",
    "ancient-origins.net": "medium",
    "historyextra.com": "medium",
}


def classify_link_type(domain: str) -> str:
    if "wikipedia.org" in domain:
        return "article"
    if "unesco.org" in domain:
        return "unesco"
    if any(d in domain for d in ("museum", "britishmuseum", "metmuseum", "louvre")):
        return "museum"
    if any(d in domain for d in ("jstor", "academia.edu", "springer", "arxiv")):
        return "academic"
    if any(d in domain for d in ("pleiades", "topostext", "dare.ht")):
        return "database"
    if any(d in domain for d in (".gov", ".edu")):
        return "government"
    return "article"


def get_quality(domain: str) -> str:
    for pattern, quality in QUALITY_DOMAINS.items():
        if pattern in domain:
            return quality
    return "medium"


# Track API usage globally
api_calls_made = 0
api_calls_lock = asyncio.Lock()


async def search_serper(client: httpx.AsyncClient, query: str) -> list[dict]:
    """Search via Serper.dev Google Search API."""
    global api_calls_made
    try:
        resp = await client.post(
            "https://google.serper.dev/search",
            headers={
                "X-API-KEY": SERPER_API_KEY,
                "Content-Type": "application/json",
            },
            json={"q": query, "num": 15},
            timeout=SEARCH_TIMEOUT,
        )

        async with api_calls_lock:
            api_calls_made += 1

        if resp.status_code == 429:
            print("  RATE LIMITED — waiting 5s...", flush=True)
            await asyncio.sleep(5)
            return []
        if resp.status_code == 403:
            print("  API KEY EXHAUSTED (403)", flush=True)
            return []
        if resp.status_code != 200:
            return []

        data = resp.json()
        results = []
        for r in data.get("organic", [])[:15]:
            url = r.get("link", "")
            if not url:
                continue
            parsed = urlparse(url)
            domain = (parsed.hostname or "").replace("www.", "")
            if any(excl in domain for excl in EXCLUDE_DOMAINS):
                continue
            results.append({
                "url": url,
                "title": r.get("title", ""),
                "domain": domain,
            })
        return results
    except Exception as e:
        print(f"  Search error: {e}", flush=True)
        return []


async def process_site(client: httpx.AsyncClient, site: dict) -> list[dict]:
    """Search for reference links for a single site."""
    name = site["name"]
    country = site.get("country") or ""
    site_type = site.get("site_type") or ""
    existing_url = site.get("source_url") or ""
    existing_domain = ""
    if existing_url:
        try:
            existing_domain = (urlparse(existing_url).hostname or "").replace("www.", "")
        except Exception:
            pass

    query = f"{name} {country} archaeological site"
    if site_type and "unknown" not in site_type.lower():
        query = f"{name} {country} {site_type}"

    results = await search_serper(client, query)

    # Filter and format
    links = []
    seen_domains = set()
    for r in results:
        domain = r["domain"]
        if existing_domain and existing_domain in domain:
            continue
        if domain in seen_domains:
            continue
        seen_domains.add(domain)

        links.append({
            "url": r["url"],
            "title": r["title"],
            "domain": domain,
            "link_type": classify_link_type(domain),
            "quality": get_quality(domain),
            "reason": f"Found via web search for {name}",
        })
        if len(links) >= 5:
            break

    return links


async def process_batch(batch_id: str, client: httpx.AsyncClient) -> bool:
    """Process one batch — all sites searched concurrently."""
    input_path = BATCH_DIR / f"batch_{batch_id}_input.json"
    output_path = BATCH_DIR / f"batch_{batch_id}_results.json"

    if output_path.exists():
        return False
    if not input_path.exists():
        return False

    with open(input_path, encoding="utf-8") as f:
        batch = json.load(f)

    sites = batch.get("sites", [])
    site_results = await asyncio.gather(*[process_site(client, s) for s in sites])

    results = {}
    for site, links in zip(sites, site_results):
        results[site["site_id"]] = links

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    total_links = sum(len(v) for v in results.values())
    print(f"  Batch {batch_id}: {len(sites)} sites, {total_links} links", flush=True)
    return True


async def run_all(batch_ids: list[str]):
    """Process batches with bounded concurrency."""
    client = httpx.AsyncClient(
        follow_redirects=True,
        timeout=SEARCH_TIMEOUT,
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=50),
    )

    sem = asyncio.Semaphore(BATCH_CONCURRENCY)
    processed = 0
    total = len(batch_ids)

    async def sem_batch(bid: str) -> bool:
        async with sem:
            return await process_batch(bid, client)

    chunk_size = 50
    for chunk_start in range(0, total, chunk_size):
        chunk = batch_ids[chunk_start:chunk_start + chunk_size]
        results = await asyncio.gather(*[sem_batch(bid) for bid in chunk])
        done = sum(1 for r in results if r)
        processed += done
        print(f"  Progress: {min(chunk_start + chunk_size, total)}/{total} ({processed} new, {api_calls_made} API calls)", flush=True)

    await client.aclose()
    print(f"\nDone. {processed}/{total} batches processed. {api_calls_made} Serper API calls used.", flush=True)


def main():
    if not SERPER_API_KEY:
        print("Error: SERPER_API_KEY not set")
        sys.exit(1)
    if len(sys.argv) < 2:
        print("Usage: python scripts/process_weblink_batch.py <batch_id|range|all>")
        sys.exit(1)

    arg = sys.argv[1]
    if arg == "all":
        manifest_path = BATCH_DIR / "manifest.json"
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
        batch_ids = [
            b for b in sorted(manifest.get("batches", {}).keys())
            if not (BATCH_DIR / f"batch_{b}_results.json").exists()
        ]
    elif "-" in arg:
        start, end = arg.split("-")
        batch_ids = [f"{i:03d}" for i in range(int(start), int(end) + 1)]
    else:
        batch_ids = [f"{int(arg):03d}"]

    remaining = [b for b in batch_ids if not (BATCH_DIR / f"batch_{b}_results.json").exists()]
    print(f"Processing {len(remaining)} web-links batches via Serper.dev ({BATCH_CONCURRENCY} concurrent)...", flush=True)
    asyncio.run(run_all(remaining))


if __name__ == "__main__":
    main()
