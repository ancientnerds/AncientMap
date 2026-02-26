# Card Description Enrichment

A procedure for enriching short card descriptions by researching sites online. Claude Code follows this step-by-step when the user says "enrich card descriptions".

## When to use

Run this after card description generation when some descriptions are under 130 characters due to sparse Wikipedia source text. Online research can usually surface enough detail to write a proper 150-200 char description.

## Execution Procedure

**Step 0 — Identify short descriptions**

1. Read `output/card_descriptions.json` and `output/card_sites.json`
2. Find all descriptions under 130 characters
3. Export them to `output/enrichment_input.json` with fields: site_id, name, current_desc, current_len, wiki_text, period_name, period_start, site_type, country
4. Report: `Found N descriptions under 130 chars`

**Step 1 — Prepare batches**

1. Split `output/enrichment_input.json` into batches of ~13 sites each (10 batches)
2. Write each to `output/enrich_batch_NNN.json`

**Step 2 — Research and rewrite (parallel agents)**

Launch **10 agents in parallel** (subagent_type: `research-analyst`), each with:
- Its batch file to read
- Instructions to web-search each site and rewrite the description
- The Tone & Style Guide from `CARD_DESCRIPTIONS.md`

Each agent's task:
1. Read its batch file
2. For each site:
   a. Search the web for: `"{site_name}" archaeological site {country}` (and variations)
   b. Gather key facts: what it is, when it was built/used, what's notable about it
   c. Write a new 150-200 char description using the researched facts
   d. If no useful info found online, keep the original description
3. Write results to `output/enrich_results_NNN.json` as: `{"site_id": "new description", ...}`
4. Also write `output/enrich_sources_NNN.json` as: `{"site_id": "key facts found: ...", ...}` (for audit trail)

**Step 3 — Verify and merge**

1. Read all `output/enrich_results_NNN.json` files
2. Validate: all descriptions <= 200 chars, no country mentions, no generic filler
3. Merge into `output/card_descriptions.json`
4. Clean up batch files
5. Report: `Enriched N descriptions. New average length: X chars`

**Step 4 — Import to DB**

Run: `python scripts/import_card_descriptions.py`

## Research Tips

- Try multiple search queries if the first returns nothing
- Tourism sites (visit-corsica.com, lonelyplanet.com, tripadvisor.com) often have good summaries
- Academic sources (journals.openedition.org, researchgate.net) have precise details
- The Megalithic Portal (megalithic.co.uk) is excellent for European prehistoric sites
- For Peruvian/Andean sites, try Spanish search terms too
