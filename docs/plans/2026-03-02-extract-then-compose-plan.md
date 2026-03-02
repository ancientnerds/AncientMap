# Extract-then-Compose Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restructure the cited-description pipeline from "write freely then verify" to "extract facts first, compose from facts only, then verify" — targeting 95% verification pass rate (up from 44%).

**Architecture:** Three sequential LLM calls per site: (1) Extract facts with verbatim quotes from source excerpts, (2) Compose description using only extracted facts, (3) Verify claims against quotes and excerpts. The extract step constrains the compose step, making hallucination structurally difficult.

**Tech Stack:** Python 3.13, httpx (async), MiniMax-M2.5 LLM via Anthropic-compatible API, JSON batch files.

---

## Context for the implementer

### Key files
- `scripts/process_cited_desc_batch.py` — The generation script. Currently does: fetch URLs → single LLM call → write results. Will be rewritten to: fetch URLs → extract call → compose call → write results.
- `scripts/process_verification_batch.py` — The verification script. Currently checks claims against excerpts. Will be enhanced to also check claims against extracted_facts quotes.
- `scripts/audit_enrich.py` — The merge pipeline. Reads results JSON. The `merge_cited_descriptions()` function (line 2074) validates format; `merge_verification()` (line 2432) writes to DB. Both need minor updates to handle the new `extracted_facts` field.

### Batch file structure
- Input: `output/cited_description_batches/batch_NNN_input.json` — has `sites[]` with fields: `site_id, name, country, site_type, period_start, period_name, source_url, current_description, wiki_extract, reference_links[]`
- Results: `output/cited_description_batches/batch_NNN_results.json` — has `sites{}` keyed by site_id with fields: `status, description{text, char_count, citations[]}, card_description{text, char_count}, fetched_excerpts{}, fetch_errors[]`
- Verification input: `output/verification_batches/batch_NNN_input.json` — has `sites[]` with fields derived from cited-desc results
- Verification results: `output/verification_batches/batch_NNN_results.json` — has `sites{}` keyed by site_id with fields: `verified_description, verified_citations[], card_description, removed_claims[], verification_score, verdict`

### LLM API
- Endpoint: `{API_BASE}/v1/messages` (Anthropic-compatible)
- Auth header: `x-api-key: {API_KEY}`
- Model: `MiniMax-M2.5` (env var `LYRA_LLM_MODEL`)
- The `call_llm()` function at line 121 handles this. It accepts a prompt string and returns the text response or None.

### Important constraints
- Results files act as idempotency guards — if `batch_NNN_results.json` exists, that batch is skipped
- The audit merge reads `status` field: "improved", "unchanged", "failed"
- Citations must have fields: `n, url, title, domain, claim`
- `fetched_excerpts` dict must exist in results — the audit validation checks that cited URLs have excerpts (line 2144-2149)

---

## Task 1: Add EXTRACT_PROMPT and extract_facts() function

**Files:**
- Modify: `scripts/process_cited_desc_batch.py`

**Step 1: Add the EXTRACT_PROMPT constant after the existing SITE_PROMPT (line 87)**

Insert this after line 87 (`"""`), before the `fetch_url` function:

```python
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
```

**Step 2: Add the extract_facts() async function after call_llm() (after line 146)**

```python
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

    try:
        clean = response.strip()
        if clean.startswith("```"):
            clean = re.sub(r'^```(?:json)?\s*', '', clean)
            clean = re.sub(r'```\s*$', '', clean)
        result = json.loads(clean)
        facts = result.get("extracted_facts", [])
        if not facts or not isinstance(facts, list):
            return None
        # Validate each fact has required fields
        valid_facts = []
        for f in facts:
            if isinstance(f, dict) and f.get("url") and f.get("quote") and f.get("fact"):
                valid_facts.append(f)
        return valid_facts if valid_facts else None
    except json.JSONDecodeError:
        return None
```

**Step 3: Verify syntax**

Run: `ruff check scripts/process_cited_desc_batch.py`
Expected: Only pre-existing B905 warning on the `zip()` call, no new errors.

---

## Task 2: Add COMPOSE_PROMPT and replace SITE_PROMPT usage in process_site()

**Files:**
- Modify: `scripts/process_cited_desc_batch.py`

**Step 1: Add COMPOSE_PROMPT after EXTRACT_PROMPT**

```python
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
```

**Step 2: Rewrite process_site() to use the 2-call flow**

Replace the entire `process_site()` function (lines 149-234) with:

```python
async def process_site(fetch_client: httpx.AsyncClient, llm_client: httpx.AsyncClient, site: dict) -> dict:
    """Process one site: fetch refs → extract facts → compose description."""
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

    try:
        clean = response.strip()
        if clean.startswith("```"):
            clean = re.sub(r'^```(?:json)?\s*', '', clean)
            clean = re.sub(r'```\s*$', '', clean)
        result = json.loads(clean)
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
    except json.JSONDecodeError:
        return {
            "status": "failed",
            "description": {"text": current_desc or "", "char_count": len(current_desc or ""), "citations": []},
            "card_description": {"text": "", "char_count": 0},
            "extracted_facts": facts,
            "fetched_excerpts": excerpts,
            "fetch_errors": fetch_errors + ["compose LLM bad JSON"],
        }
```

**Step 3: Remove the old SITE_PROMPT constant (lines 32-87)**

It is no longer used. Delete the entire `SITE_PROMPT = """\..."""` block.

**Step 4: Verify syntax**

Run: `ruff check scripts/process_cited_desc_batch.py`
Expected: Only pre-existing B905 warning.

**Step 5: Commit**

```bash
git add scripts/process_cited_desc_batch.py
git commit -m "Refactor cited-desc to extract-then-compose 2-call architecture

Split single LLM call into: (1) extract facts with verbatim quotes from
source excerpts, (2) compose description constrained to extracted facts only.
This prevents hallucination by making the compose step work from a pre-validated
fact list rather than raw excerpts."
```

---

## Task 3: Enhance verification to use extracted_facts

**Files:**
- Modify: `scripts/process_verification_batch.py`

**Step 1: Update SITE_PROMPT to include extracted_facts and quote-checking guidance**

Replace the entire `SITE_PROMPT` (lines 30-82) with:

```python
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

- If a claim is NOT supported by any source → mark for removal
- Remove the ENTIRE sentence containing the unverifiable [N]
- Renumber remaining [N] citations sequentially from [1]
- Update the citations array to match the renumbered markers
- If ALL claims fail → verdict: "fail", keep the original description

## Scoring

verification_score = verified_claims / total_claims
- score >= 0.7 → verdict: "pass"
- score < 0.7 → verdict: "fail"

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
```

**Step 2: Update process_site() to pass extracted_facts to the prompt**

In the `process_site()` function (line 113), add `extracted_facts` extraction and pass it to the prompt:

Change lines 113-135 from:

```python
async def process_site(client: httpx.AsyncClient, site: dict) -> dict:
    """Verify one site's citations."""
    description = site.get("description", "")
    citations = site.get("citations", [])
    excerpts = site.get("fetched_excerpts", {})
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
        excerpts_json=json.dumps(excerpts, ensure_ascii=False)[:3000],
        card_description=card_desc,
    )
```

To:

```python
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
```

**Step 3: Verify syntax**

Run: `ruff check scripts/process_verification_batch.py`
Expected: Only pre-existing B905 warning.

**Step 4: Commit**

```bash
git add scripts/process_verification_batch.py
git commit -m "Enhance verification to use extracted_facts with source quotes

The verifier now receives extracted_facts from the extract-then-compose pipeline.
It checks the evidence chain: quote in excerpt → fact matches claim → cross-reference.
This gives the verifier much better signal to distinguish real vs hallucinated claims."
```

---

## Task 4: Update audit_enrich.py to handle extracted_facts in validation

**Files:**
- Modify: `scripts/audit_enrich.py`

**Step 1: Update merge_cited_descriptions() validation**

In the `merge_cited_descriptions()` function, around line 2126, after the `fetched_excerpts` line, the existing validation checks that cited URLs have excerpts. No structural changes needed here — the new `extracted_facts` field is just extra data that flows through.

However, update the verification batch preparation (`--phase verify-citations`) to pass `extracted_facts` through to the verification input. Find where verification batch inputs are built (search for `verify-citations` phase). The function that builds verification inputs needs to include `extracted_facts` from cited-desc results.

Search for the function that prepares verification batches. It's the `prepare_verification_batches()` function. Find it with:
```
grep -n "def prepare_verification" scripts/audit_enrich.py
```

In that function, find where it builds the site dict for verification input (look for where it reads from cited-desc results and constructs the verification input site). Add `"extracted_facts": site_result.get("extracted_facts", [])` to the verification input site dict.

**Step 2: Verify syntax**

Run: `ruff check scripts/audit_enrich.py`

**Step 3: Commit**

```bash
git add scripts/audit_enrich.py
git commit -m "Pass extracted_facts through to verification batch inputs"
```

---

## Task 5: Delete existing results and test with 3 batches

**Files:**
- No code changes. Operational testing.

**Step 1: Delete results for batches 1-3 to allow re-processing**

```bash
rm -f output/cited_description_batches/batch_001_results.json
rm -f output/cited_description_batches/batch_002_results.json
rm -f output/cited_description_batches/batch_003_results.json
```

**Step 2: Run cited-desc generation on 3 batches**

```bash
python scripts/process_cited_desc_batch.py 1-3
```

Expected: 3 batches processed, most sites "improved" or "unchanged", few "failed".

**Step 3: Inspect the results — check extracted_facts quality**

```bash
python -c "
import json
data = json.load(open('output/cited_description_batches/batch_001_results.json', encoding='utf-8'))
for sid, site in list(data['sites'].items())[:2]:
    print(f'=== {sid[:8]} ===')
    print(f'Status: {site.get(\"status\")}')
    facts = site.get('extracted_facts', [])
    print(f'Extracted facts: {len(facts)}')
    for f in facts[:3]:
        print(f'  - Quote: \"{f.get(\"quote\", \"\")[:80]}...\"')
        print(f'    Fact: {f.get(\"fact\", \"\")[:80]}')
    desc = site.get('description', {})
    print(f'Description: {desc.get(\"text\", \"\")[:200]}...')
    print(f'Citations: {len(desc.get(\"citations\", []))}')
    print()
"
```

Verify:
- `extracted_facts` array is non-empty (4-10 facts)
- Each fact has `url`, `quote`, `fact` fields
- Quotes look like actual verbatim text from the excerpts (not paraphrased)
- Description references facts that appear in extracted_facts

**Step 4: Delete verification results and re-prepare verification batches**

```bash
rm -f output/verification_batches/batch_001_results.json
rm -f output/verification_batches/batch_002_results.json
rm -f output/verification_batches/batch_003_results.json
```

Note: Verification batch inputs may need to be regenerated via `python scripts/audit_enrich.py --phase verify-citations` to include the new `extracted_facts` field. Check if this is needed.

**Step 5: Run verification on 3 batches**

```bash
python scripts/process_verification_batch.py 1-3
```

**Step 6: Check pass rate**

```bash
python -c "
import json
p = f = 0
for i in range(1, 4):
    data = json.load(open(f'output/verification_batches/batch_{i:03d}_results.json', encoding='utf-8'))
    for sid, site in data['sites'].items():
        if site.get('verdict') == 'pass': p += 1
        else: f += 1
print(f'Pass: {p}, Fail: {f}, Rate: {100*p/(p+f):.1f}%')
"
```

Expected: Pass rate > 80% (target: 90-95%).

---

## Task 6: Final lint check and commit

**Step 1:** Run final lint

```bash
ruff check scripts/process_cited_desc_batch.py scripts/process_verification_batch.py scripts/audit_enrich.py
```

**Step 2:** If pass rate from Task 5 looks good, commit the test results or delete them for a clean full run later.
