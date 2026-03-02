# Extract-then-Compose Pipeline Design

## Problem

The cited-description pipeline has a 44% verification pass rate. The generator LLM writes freely, hallucinating details beyond what excerpts contain, then the verifier correctly strips them — wasting ~7,300 LLM calls to produce only 1,020 usable descriptions from 5,005 sites.

Root cause: 42% of fetched excerpts are < 200 chars (titles/nav chrome). The LLM fills in details from training data and cites the thin excerpts anyway.

## Solution: 3-call extract-then-compose architecture

```
excerpts --> [Call 1: EXTRACT] --> extracted_facts
                                       |
site_info ---------------------------->|
                                       v
                                 [Call 2: COMPOSE] --> description + citations
                                                            |
excerpts + extracted_facts ---------------------------->    |
                                                            v
                                                      [Call 3: VERIFY] --> final output
```

### Call 1 — Extract (reading comprehension)

Input: Site name, excerpts with URLs, Wikipedia extract.

The LLM reads each source and lists every factual claim found, outputting:
- Source URL
- Exact verbatim quote from the source (10-50 words)
- Normalized fact (rephrased)

Rules: only extract facts literally present in text. Quote must be a verbatim substring. Skip sources with < 50 chars of content.

Output: `{"extracted_facts": [{"url": "...", "quote": "...", "fact": "..."}]}`

### Call 2 — Compose (constrained writing)

Input: extracted_facts from Call 1, site info (name, country, type, period).

The LLM writes a description using ONLY the extracted facts. Every sentence traces to one or more facts. Uses [N] citation markers. 500-800 chars, hard limit 900. Also writes card_description (max 200 chars).

The LLM has no excerpts — only the pre-extracted fact list. Cannot hallucinate beyond it.

### Call 3 — Verify (enhanced existing)

Same as current verification but also receives extracted_facts with quotes. The verifier checks:
1. Does each claim map to an extracted fact?
2. Does the quote appear in the excerpt? (substring match)
3. Does the claim accurately represent the quote?

### Expected results

| Metric | Current | Expected |
|--------|---------|----------|
| Verification pass rate | 44% | 90-95% |
| Usable descriptions | 1,020 | ~4,300-4,500 |
| LLM calls per site | 2 | 3 |
| Net wasted calls | ~7,300 | ~750 |

### Files to modify

- `scripts/process_cited_desc_batch.py` — Split into extract + compose calls
- `scripts/process_verification_batch.py` — Enhanced prompt with extracted_facts
- `scripts/audit_enrich.py` — Handle new extracted_facts field (minor)

### What stays the same

- Batch structure, concurrency, manifest system
- HTML extraction improvements (smart content detection, 8s timeout, 3000 char limit)
- Audit/merge pipeline
