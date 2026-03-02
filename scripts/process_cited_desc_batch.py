#!/usr/bin/env python3
"""Process cited-description batches using MiniMax LLM API (async).

Usage:
    python scripts/process_cited_desc_batch.py all
    python scripts/process_cited_desc_batch.py 1-50
    python scripts/process_cited_desc_batch.py 5
    python scripts/process_cited_desc_batch.py all --retry
"""

import asyncio
import json
import os
import re
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

BATCH_DIR = Path(__file__).parent.parent / "output" / "cited_description_batches"
API_KEY = os.environ.get("LYRA_ANTHROPIC_API_KEY", "")
API_BASE = os.environ.get("LYRA_ANTHROPIC_BASE_URL", "https://api.minimax.io/anthropic")
LLM_MODEL = os.environ.get("LYRA_LLM_MODEL", "MiniMax-M2.5")

# Process 5 batches concurrently, 10 sites each with parallel URL fetches
BATCH_CONCURRENCY = 5
FETCH_TIMEOUT = 8  # seconds — academic sites need more time
LLM_TIMEOUT = 45


def parse_llm_json(response: str) -> dict | None:
    """Parse JSON from LLM response, with fallback regex extraction."""
    clean = response.strip()
    if clean.startswith("```"):
        clean = re.sub(r'^```(?:json)?\s*', '', clean)
        clean = re.sub(r'```\s*$', '', clean)
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        pass
    # Fallback: find the outermost JSON object
    match = re.search(r'\{[\s\S]*\}', clean)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None


EXTRACT_PROMPT = """\
You are a fact extractor for an archaeological site database. Read the source texts below and extract every factual claim you can find.

## Site
- Name: {name}
- Country: {country}

## Wikipedia extract
{wiki_extract}

## Reference page excerpts
{reference_content}

## Rules

1. For EACH fact you find, output:
   - "url": the source URL where you found it
   - "quote": an EXACT verbatim substring from the source text (10-60 words). This must be copy-pasted, not paraphrased.
   - "fact": your one-sentence summary of what the quote says
2. ONLY extract facts that literally appear in the text above. Do NOT add facts from your own knowledge.
3. If a source has fewer than 50 characters of content, skip it entirely.
4. Extract: dates, dimensions, names, events, materials, UNESCO status, excavation history, architectural features, cultural significance.
5. Aim for 4-10 facts total. Prefer the most specific and interesting facts.

Return ONLY valid JSON (no markdown fences):
{{
  "extracted_facts": [
    {{"url": "https://...", "quote": "exact words from source", "fact": "Summary of the fact"}},
    {{"url": "https://...", "quote": "exact words from source", "fact": "Summary of the fact"}}
  ]
}}
"""

COMPOSE_PROMPT = """\
Write a cited description for this archaeological site using ONLY the extracted facts below.

## Site info
- Name: {name}
- Country: {country}
- Type: {site_type}
- Period: {period_name} (start: {period_start})

## Extracted facts (from source analysis)
{facts_list}

## Instructions

CRITICAL RULE: You may ONLY use the facts listed above. Do NOT add any details, dates, dimensions,
or names that are not explicitly stated in the extracted facts. If the facts are sparse, write a
shorter description. A verified short description is better than a long hallucinated one.

1. Write a description (500-800 chars, HARD LIMIT 900 chars) with [1][2][3] citation markers.
   Each [N] MUST correspond to one of the extracted facts above.
   Count characters carefully.
2. Write a card_description (max 200 chars):
   - Start with age/period anchor if known: "Built 9,600 BC", "3rd-century fortress"
   - ONE outstanding fact — the single most remarkable thing
   - Never mention the country (shown on card already)
   - No generic filler. Concrete details over vague adjectives.
3. Number citations sequentially from [1].
4. Each citation must include the "quote" field from the extracted fact it references.

Return ONLY valid JSON (no markdown fences):
{{
  "status": "improved",
  "description": {{
    "text": "Description with [1][2] markers...",
    "char_count": 650,
    "citations": [
      {{"n": 1, "url": "https://...", "title": "Page Title", "domain": "example.com", "claim": "the claim", "quote": "exact words from source"}}
    ]
  }},
  "card_description": {{
    "text": "Built 300 BC — massive carved pillars...",
    "char_count": 120
  }}
}}
"""


async def fetch_url(client: httpx.AsyncClient, url: str) -> tuple[str, str | None]:
    """Fetch URL, return (url, text_content|None). Retries once on timeout."""
    for attempt in range(2):
        try:
            resp = await client.get(url, timeout=FETCH_TIMEOUT)
            if resp.status_code != 200:
                return url, None
            html = resp.text
            # Try to extract main content area first
            for pattern in [
                r'<article[^>]*>(.*?)</article>',
                r'<main[^>]*>(.*?)</main>',
                r'<div[^>]*class="[^"]*mw-parser-output[^"]*"[^>]*>(.*?)</div>',
                r'<div[^>]*class="[^"]*content[^"]*"[^>]*>(.*?)</div>',
            ]:
                m = re.search(pattern, html, flags=re.DOTALL | re.IGNORECASE)
                if m and len(m.group(1)) > 200:
                    html = m.group(1)
                    break
            # Strip non-content elements
            for tag in ['script', 'style', 'nav', 'header', 'footer', 'aside', 'noscript']:
                html = re.sub(rf'<{tag}[^>]*>.*?</{tag}>', '', html, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<[^>]+>', ' ', html)
            text = re.sub(r'\s+', ' ', text).strip()
            # Skip title-only pages
            if len(text) < 100:
                return url, None
            return url, text[:3000]
        except httpx.TimeoutException:
            if attempt == 0:
                await asyncio.sleep(1)
                continue
            return url, None
        except Exception:
            return url, None
    return url, None


async def call_llm(client: httpx.AsyncClient, prompt: str) -> str | None:
    """Call MiniMax LLM API with retry."""
    for attempt in range(3):
        try:
            resp = await client.post(
                f"{API_BASE}/v1/messages",
                headers={
                    "x-api-key": API_KEY,
                    "content-type": "application/json",
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": LLM_MODEL,
                    "max_tokens": 2000,
                    "temperature": 0.15,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=LLM_TIMEOUT,
            )
            if resp.status_code == 200:
                for block in resp.json().get("content", []):
                    if block.get("type") == "text":
                        return block["text"]
                return None
            # Retry on 429 (rate limit) or 5xx (server error)
            if resp.status_code in (429, 500, 502, 503, 529) and attempt < 2:
                await asyncio.sleep(2 ** (attempt + 1))
                continue
            return None
        except Exception:
            if attempt < 2:
                await asyncio.sleep(2 ** (attempt + 1))
                continue
            return None
    return None


async def extract_facts(
    llm_client: httpx.AsyncClient,
    site: dict,
    excerpts: dict[str, str],
    wiki_extract: str,
) -> list[dict] | None:
    """Call 1: Extract facts with verbatim quotes from source excerpts."""
    ref_content = ""
    for url, text in excerpts.items():
        ref_content += f"\n[{url}] ({len(text)} chars)\n{text}\n"
    if not ref_content and not wiki_extract:
        return None

    prompt = EXTRACT_PROMPT.format(
        name=site["name"],
        country=site.get("country") or "Unknown",
        wiki_extract=wiki_extract[:3000] if wiki_extract else "(None)",
        reference_content=ref_content or "(No reference pages fetched)",
    )

    response = await call_llm(llm_client, prompt)
    if not response:
        return None

    result = parse_llm_json(response)
    if not result:
        return None
    facts = result.get("extracted_facts", [])
    if not facts or not isinstance(facts, list):
        return None
    # Validate each fact has required fields
    valid_facts = []
    for f in facts:
        if isinstance(f, dict) and f.get("url") and f.get("quote") and f.get("fact"):
            valid_facts.append(f)
    return valid_facts if valid_facts else None


async def process_site(fetch_client: httpx.AsyncClient, llm_client: httpx.AsyncClient, site: dict) -> dict:
    """Process one site: fetch refs -> extract facts -> compose description."""
    name = site["name"]
    wiki_extract = site.get("wiki_extract") or ""
    current_desc = site.get("current_description") or ""
    ref_links = site.get("reference_links") or []

    # Parallel-fetch top 5 ref URLs, keep best 3
    urls_to_fetch = []
    for ref in ref_links[:5]:
        url = ref.get("content_url") or ref.get("url") or ""
        if url:
            urls_to_fetch.append(url)

    excerpts = {}
    fetch_errors = []
    if urls_to_fetch:
        results = await asyncio.gather(*[fetch_url(fetch_client, u) for u in urls_to_fetch])
        for url, content in results:
            if content:
                excerpts[url] = content[:2000]
            else:
                fetch_errors.append(f"{url} — failed")

    # Keep the 3 longest excerpts (best quality)
    if len(excerpts) > 3:
        sorted_excerpts = sorted(excerpts.items(), key=lambda x: len(x[1]), reverse=True)
        excerpts = dict(sorted_excerpts[:3])

    # Fallback to wiki extract
    if not excerpts and wiki_extract:
        wiki_url = site.get("source_url") or "wikipedia"
        excerpts[wiki_url] = wiki_extract[:2000]

    # === Call 1: Extract facts ===
    facts = await extract_facts(llm_client, site, excerpts, wiki_extract)
    if not facts:
        return {
            "status": "unchanged",
            "description": {"text": current_desc or "", "char_count": len(current_desc or ""), "citations": []},
            "card_description": {"text": "", "char_count": 0},
            "extracted_facts": [],
            "fetched_excerpts": excerpts,
            "fetch_errors": fetch_errors + ["extraction failed — no facts found"],
        }

    # === Call 2: Compose from extracted facts ===
    facts_list = ""
    for i, f in enumerate(facts, 1):
        facts_list += f"\n{i}. [{f['url']}]\n   Quote: \"{f['quote']}\"\n   Fact: {f['fact']}\n"

    prompt = COMPOSE_PROMPT.format(
        name=name,
        country=site.get("country") or "Unknown",
        site_type=site.get("site_type") or "Unknown",
        period_name=site.get("period_name") or "Unknown",
        period_start=site.get("period_start") or "Unknown",
        facts_list=facts_list,
    )

    response = await call_llm(llm_client, prompt)
    if not response:
        return {
            "status": "failed",
            "description": {"text": current_desc or "", "char_count": len(current_desc or ""), "citations": []},
            "card_description": {"text": "", "char_count": 0},
            "extracted_facts": facts,
            "fetched_excerpts": excerpts,
            "fetch_errors": fetch_errors + ["compose LLM call failed"],
        }

    result = parse_llm_json(response)
    if not result:
        return {
            "status": "failed",
            "description": {"text": current_desc or "", "char_count": len(current_desc or ""), "citations": []},
            "card_description": {"text": "", "char_count": 0},
            "extracted_facts": facts,
            "fetched_excerpts": excerpts,
            "fetch_errors": fetch_errors + ["compose LLM bad JSON"],
        }
    result.setdefault("status", "improved")
    result["extracted_facts"] = facts
    result.setdefault("fetched_excerpts", excerpts)
    result.setdefault("fetch_errors", fetch_errors)
    desc = result.get("description", {})
    if isinstance(desc, dict):
        desc["char_count"] = len(desc.get("text", ""))
    card = result.get("card_description", {})
    if isinstance(card, dict):
        card["char_count"] = len(card.get("text", ""))
    return result


async def process_batch(batch_id: str, fetch_client: httpx.AsyncClient, llm_client: httpx.AsyncClient) -> bool:
    """Process one batch — all 10 sites concurrently."""
    input_path = BATCH_DIR / f"batch_{batch_id}_input.json"
    output_path = BATCH_DIR / f"batch_{batch_id}_results.json"

    if output_path.exists():
        return False
    if not input_path.exists():
        return False

    with open(input_path, encoding="utf-8") as f:
        batch = json.load(f)

    sites = batch.get("sites", [])

    # Process all sites in the batch concurrently
    tasks = [process_site(fetch_client, llm_client, s) for s in sites]
    site_results = await asyncio.gather(*tasks)

    results = {}
    stats = {"improved": 0, "unchanged": 0, "failed": 0}
    for site, result in zip(sites, site_results):
        results[site["site_id"]] = result
        s = result.get("status", "failed")
        stats[s] = stats.get(s, 0) + 1

    output = {"batch_id": batch_id, "sites": results, "stats": stats}
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"  {batch_id}: {stats['improved']}ok {stats['failed']}fail", flush=True)
    return True


async def run_all(batch_ids: list[str]):
    """Process batches with bounded concurrency."""
    fetch_client = httpx.AsyncClient(
        follow_redirects=True,
        timeout=FETCH_TIMEOUT,
        limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
        headers={"User-Agent": "AncientNerdsMap/1.0"},
    )
    llm_client = httpx.AsyncClient(
        timeout=LLM_TIMEOUT,
        limits=httpx.Limits(max_connections=BATCH_CONCURRENCY * 10, max_keepalive_connections=20),
    )

    sem = asyncio.Semaphore(BATCH_CONCURRENCY)
    processed = 0
    total = len(batch_ids)

    async def sem_batch(bid: str) -> bool:
        async with sem:
            return await process_batch(bid, fetch_client, llm_client)

    # Launch all batches (semaphore limits concurrency)
    chunk_size = 50
    for chunk_start in range(0, total, chunk_size):
        chunk = batch_ids[chunk_start:chunk_start + chunk_size]
        results = await asyncio.gather(*[sem_batch(bid) for bid in chunk])
        done = sum(1 for r in results if r)
        processed += done
        print(f"  Progress: {min(chunk_start + chunk_size, total)}/{total} ({processed} new)", flush=True)

    await fetch_client.aclose()
    await llm_client.aclose()
    print(f"\nDone. {processed}/{total} batches processed.", flush=True)


def main():
    if not API_KEY:
        print("Error: LYRA_ANTHROPIC_API_KEY not set")
        sys.exit(1)
    if len(sys.argv) < 2:
        print("Usage: python scripts/process_cited_desc_batch.py <batch_id|range|all> [--retry]")
        sys.exit(1)

    retry_mode = "--retry" in sys.argv
    arg = sys.argv[1]

    if arg == "all":
        manifest_path = BATCH_DIR / "manifest.json"
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
        batch_ids = sorted(manifest.get("batches", {}).keys())
    elif "-" in arg:
        start, end = arg.split("-")
        batch_ids = [f"{i:03d}" for i in range(int(start), int(end) + 1)]
    else:
        batch_ids = [f"{int(arg):03d}"]

    if retry_mode:
        # Delete results for batches that have failures, so they get re-processed
        retryable = []
        for bid in batch_ids:
            result_path = BATCH_DIR / f"batch_{bid}_results.json"
            if not result_path.exists():
                continue
            with open(result_path, encoding="utf-8") as f:
                results = json.load(f)
            has_failures = any(
                s.get("status") in ("failed", "unchanged")
                for s in results.get("sites", {}).values()
            )
            if has_failures:
                result_path.unlink()
                retryable.append(bid)
        print(f"Retry mode: {len(retryable)} batches with failures to re-process", flush=True)

    remaining = [b for b in batch_ids if not (BATCH_DIR / f"batch_{b}_results.json").exists()]
    print(f"Processing {len(remaining)} cited-desc batches ({BATCH_CONCURRENCY} concurrent)...", flush=True)
    asyncio.run(run_all(remaining))


if __name__ == "__main__":
    main()
