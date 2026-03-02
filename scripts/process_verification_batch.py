#!/usr/bin/env python3
"""Process verification batches using MiniMax LLM API (async).

Usage:
    python scripts/process_verification_batch.py all
    python scripts/process_verification_batch.py 1-50
    python scripts/process_verification_batch.py 5
    python scripts/process_verification_batch.py all --retry
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

BATCH_DIR = Path(__file__).parent.parent / "output" / "verification_batches"
API_KEY = os.environ.get("LYRA_ANTHROPIC_API_KEY", "")
API_BASE = os.environ.get("LYRA_ANTHROPIC_BASE_URL", "https://api.minimax.io/anthropic")
LLM_MODEL = os.environ.get("LYRA_LLM_MODEL", "MiniMax-M2.5")

BATCH_CONCURRENCY = 5
LLM_TIMEOUT = 60


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


SITE_PROMPT = """\
You are an independent fact-checker for archaeological site descriptions.

## Input

- Description: {description}
- Citations: {citations_json}
- Extracted facts (with source quotes): {extracted_facts_json}
- Fetched excerpts: {excerpts_json}
- Card description: {card_description}

## Verification rules

For each [N] citation, verify using this evidence chain:

1. Check if the citation includes a "quote" field. If so, verify:
   a. Does the quote appear (approximately) in the fetched excerpt for that URL?
   b. Does the claim accurately represent what the quote says?

2. If no quote is available, check the extracted_facts for a matching fact from the same URL.

3. If neither quote nor extracted fact is available, check the fetched excerpt directly:
   - Numbers/dates must match (exactly or approximately)
   - Proper nouns must match
   - The fact must be present or clearly implied in the excerpt

4. Cross-referencing: if a claim is supported by ANY provided source (excerpts, extracted facts,
   or Wikipedia extract), it counts as verified even if the specific cited URL's excerpt is missing.

5. Only mark as unverifiable if NO provided source supports the claim.

## What to do with unverified claims

- If a claim is NOT supported by any source -> mark for removal
- Remove the ENTIRE sentence containing the unverifiable [N]
- Renumber remaining [N] citations sequentially from [1]
- Update the citations array to match the renumbered markers
- If ALL claims fail -> verdict: "fail", keep the original description

## Scoring

verification_score = verified_claims / total_claims
- score >= 0.7 -> verdict: "pass"
- score < 0.7 -> verdict: "fail"

Return ONLY valid JSON (no markdown fences):
{{
  "verified_description": "Text with renumbered [1][2] markers...",
  "verified_citations": [
    {{"n": 1, "url": "https://...", "title": "...", "domain": "...", "claim": "..."}}
  ],
  "card_description": "{card_description}",
  "removed_claims": [
    {{"original_n": 2, "claim": "...", "reason": "..."}}
  ],
  "verification_score": 0.85,
  "verdict": "pass"
}}
"""


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
                    "temperature": 0.1,
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


async def process_site(client: httpx.AsyncClient, site: dict) -> dict:
    """Verify one site's citations."""
    description = site.get("description", "")
    citations = site.get("citations", [])
    excerpts = site.get("fetched_excerpts", {})
    extracted_facts = site.get("extracted_facts", [])
    card_desc = site.get("card_description", "")

    if not citations:
        return {
            "verified_description": description,
            "verified_citations": [],
            "card_description": card_desc,
            "removed_claims": [],
            "verification_score": 0.0,
            "verdict": "fail",
        }

    prompt = SITE_PROMPT.format(
        description=description[:1500],
        citations_json=json.dumps(citations, ensure_ascii=False)[:2000],
        extracted_facts_json=json.dumps(extracted_facts, ensure_ascii=False)[:3000],
        excerpts_json=json.dumps(excerpts, ensure_ascii=False)[:3000],
        card_description=card_desc,
    )

    response = await call_llm(client, prompt)
    if not response:
        return {
            "verified_description": description,
            "verified_citations": citations,
            "card_description": card_desc,
            "removed_claims": [],
            "verification_score": 0.0,
            "verdict": "fail",
            "error": "LLM call failed",
        }

    result = parse_llm_json(response)
    if not result:
        return {
            "verified_description": description,
            "verified_citations": citations,
            "card_description": card_desc,
            "removed_claims": [],
            "verification_score": 0.0,
            "verdict": "fail",
            "error": "LLM bad JSON",
        }
    result.setdefault("card_description", card_desc)
    result.setdefault("removed_claims", [])
    result.setdefault("verification_score", 0.0)
    result.setdefault("verdict", "fail")
    return result


async def process_batch(batch_id: str, client: httpx.AsyncClient) -> bool:
    """Process one batch — all sites concurrently."""
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
    stats = {"pass": 0, "fail": 0, "total_claims_checked": 0, "total_claims_verified": 0, "total_claims_removed": 0}
    for site, result in zip(sites, site_results):
        site_id = site.get("site_id", "unknown")
        results[site_id] = result
        v = result.get("verdict", "fail")
        stats["pass" if v == "pass" else "fail"] += 1
        removed = result.get("removed_claims", [])
        verified_cits = result.get("verified_citations", [])
        stats["total_claims_checked"] += len(verified_cits) + len(removed)
        stats["total_claims_verified"] += len(verified_cits)
        stats["total_claims_removed"] += len(removed)

    output = {"batch_id": batch_id, "sites": results, "stats": stats}
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"  {batch_id}: {stats['pass']}pass {stats['fail']}fail", flush=True)
    return True


async def run_all(batch_ids: list[str]):
    """Process batches with bounded concurrency."""
    client = httpx.AsyncClient(
        timeout=LLM_TIMEOUT,
        limits=httpx.Limits(max_connections=BATCH_CONCURRENCY * 10, max_keepalive_connections=20),
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
        print(f"  Progress: {min(chunk_start + chunk_size, total)}/{total} ({processed} new)", flush=True)

    await client.aclose()
    print(f"\nDone. {processed}/{total} batches processed.", flush=True)


def main():
    if not API_KEY:
        print("Error: LYRA_ANTHROPIC_API_KEY not set")
        sys.exit(1)
    if len(sys.argv) < 2:
        print("Usage: python scripts/process_verification_batch.py <batch_id|range|all> [--retry]")
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
        # Delete results for batches with LLM failures (not genuine content failures)
        retryable = []
        for bid in batch_ids:
            result_path = BATCH_DIR / f"batch_{bid}_results.json"
            if not result_path.exists():
                continue
            with open(result_path, encoding="utf-8") as f:
                results = json.load(f)
            has_llm_failures = any(
                s.get("error") in ("LLM call failed", "LLM bad JSON")
                for s in results.get("sites", {}).values()
            )
            if has_llm_failures:
                result_path.unlink()
                retryable.append(bid)
        print(f"Retry mode: {len(retryable)} batches with LLM failures to re-process", flush=True)

    remaining = [b for b in batch_ids if not (BATCH_DIR / f"batch_{b}_results.json").exists()]
    print(f"Processing {len(remaining)} verification batches ({BATCH_CONCURRENCY} concurrent)...", flush=True)
    asyncio.run(run_all(remaining))


if __name__ == "__main__":
    main()
