# Database Audit & Enrichment Framework

A unified playbook for auditing and enriching the entire Ancient Nerds database. Combines mechanical fixes, Wikidata enrichment, agent-based verification, and card description generation into a single "press a button" system.

All 3 sources are covered:

| source_id | Name | ~Sites | Role |
|-----------|------|--------|------|
| `ancient_nerds` | Originals | 5,005 | Core curated sites. Full audit + enrichment + card descriptions. |
| `lyra` | Radar | varies | Pipeline-discovered sites. Enrich + verify. Stay in their DB. |
| `ancient_nerds_community` | Community | varies | User submissions. Enrich + verify. Stay in their DB. |

**Critical rule**: Community and Radar sites are enriched but NEVER auto-promoted to Originals. Only the admin does that.

**Data flow**: Sync production → audit locally → package → upload via db.html (creates rollback snapshot).

```
Production API ──GET /api/v1/sites.geojson──→ Local DB ──audit waves 0-3──→ Package JSON
                                                                                │
db.html ◄──── upload JSON ◄─────────────────────────────────────────────────────┘
  └── auto-creates snapshot (rollback point) before applying changes
```

This ensures manual edits made via `db.html` on production are never overwritten, and every audit result can be rolled back.

**Current scope:** `ancient_nerds` only. Lyra and Community sources will be added later once their API endpoints are ready.

---

## Overview: 4-Wave Architecture

Claude Code can launch ~10 parallel agents per message. The system uses a 4-wave architecture where each wave reduces work for the next:

| Wave | Type | What it does | Sites | Time |
|------|------|-------------|-------|------|
| **0: Mechanical** | Python script (no agents) | Deterministic fixes: site_type normalization, period_name recomputation, raw_year parsing, compound capitalization | All ~5000+ | 2-3 min |
| **1: Wikidata Enrichment** | Python scripts (no agents) | Existing `enrich_reconcile.py` → `enrich_fetch_claims.py` → `enrich_wiki_select.py` pipeline. IO-bound HTTP, not LLM-bound. | All matched sites | 30-60 min |
| **2: Agent Verification & Gap Fill** | 10 parallel agents per round, multiple rounds | WebSearch + Consensus + Scholar Gateway research for gaps/discrepancies remaining after Waves 0-1. ~50 sites per agent. | ~500-1500 remaining | 10-20 min/round |
| **3: Card Descriptions** | 10 parallel agents per round | Generate/update 200-char descriptions using enriched context. Only for `ancient_nerds`. Delegates to `CARD_DESCRIPTIONS.md`. | ~5000 | 10-20 min/round |

Waves 0 and 1 are deterministic (no LLM reasoning needed) and eliminate ~80% of the work. Only Wave 2 gap-fill needs agent parallelism.

---

## Protecting User Edits

Sites can be edited manually via `db.html` on the production database. Audit migrations **must not blindly overwrite** these edits. Every `UPDATE` statement must use **conditional WHERE clauses** that check the current (wrong) value — not just the row ID.

```sql
-- SAFE: Only fires if the bad value is still there.
-- If a user already corrected country to 'Italy', this is a no-op.
UPDATE unified_sites SET country = 'Greece'
WHERE id = '<uuid>' AND (country IS NULL OR country = 'Unknown');

-- DANGEROUS: Overwrites whatever the current value is, including user corrections.
UPDATE unified_sites SET country = 'Greece'
WHERE id = '<uuid>';
```

This applies to **all** audit-generated SQL — migrations, `database_fixes.sql`, and one-off fixes. The rule is: if the current value doesn't match what the audit expected, a human changed it since the audit ran, and the audit should not second-guess that.

If an audit wants to change a field that a user already edited to a *different* value, that's a conflict. Flag it as `MANUAL_FIX` with both the audit's proposed value and what the user set, and let a human decide.

---

## Source-Aware Strategies

| Source | Wave 0 | Wave 1 | Wave 2 | Wave 3 |
|--------|--------|--------|--------|--------|
| `ancient_nerds` | Full mechanical fixes | Full Wikidata enrichment | Gap fill + verify | Card descriptions |
| `lyra` | site_type/country normalization | Wikidata enrichment (verify existing `enrichment_data`) | Verify enrichment claims | NO card descriptions |
| `ancient_nerds_community` | site_type/country normalization | Wikidata enrichment | Fill missing fields | NO card descriptions |

Lyra/Community enrichment writes to `user_contributions.enrichment_data` and the promoted copy in `unified_sites`, but does NOT create `card_stats` rows or promote to Originals.

### How to identify source-specific data

```sql
-- ancient_nerds sites with Wikipedia source_url
SELECT id, name, source_url FROM unified_sites
WHERE source_id = 'ancient_nerds' AND source_url LIKE '%wikipedia%';

-- lyra sites with enrichment context
SELECT u.id, u.name, u.raw_data, uc.enrichment_data, uc.enrichment_status
FROM unified_sites u
JOIN user_contributions uc ON u.source_record_id = CONCAT('lyra-', uc.id::text)
WHERE u.source_id = 'lyra';

-- Any site's original source data
SELECT id, name, source_id, raw_data FROM unified_sites WHERE name ILIKE '%site name%';
```

---

## SOTA Verification Tools

Use these tools during Wave 2 agent batches. Listed in order of preference.

| Tool | Purpose | How to invoke |
|------|---------|---------------|
| **Wikidata API** | Batch-verify period, type, country, coords for sites with Wikipedia URLs | Resolve Wikipedia URL → Wikidata QID, then fetch claims via `curl -H "User-Agent: AncientNerdsMap/1.0" "https://www.wikidata.org/w/api.php?action=wbgetentities&ids={QID}&format=json&props=claims\|labels&languages=en"`. |
| **Wikipedia REST API** | Extract metadata from linked articles | `https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}` — returns description, extract, coordinates, `wikibase_item` (QID). **Requires User-Agent header.** |
| **Consensus MCP** | Search 200M+ academic papers for disputed archaeological claims | `mcp__claude_ai_Consensus__search` — e.g., query: "dating of Baalbek temple complex" |
| **Scholar Gateway MCP** | Semantic search over peer-reviewed literature | `mcp__claude_ai_Scholar_Gateway__semanticSearch` — full natural language queries |
| **WebSearch** | General verification for sites without academic coverage | Wikipedia, museum sites, UNESCO heritage pages |
| **Pipeline utilities** | Existing normalization functions (see Utility References) | `categorize_period()`, `normalize_site_type()`, `normalize_country()`, `lookup_country()` |

### Wikidata property reference

| Property | Meaning | Audit use |
|----------|---------|-----------|
| P625 | Coordinate location | Verify lat/lon |
| P17 | Country | Verify country — P17 value is a QID (e.g., Q43 = Turkey). Resolve to label via `entities[QID].labels.en.value`. |
| P31 | Instance of | Verify site_type — **but** P31 often returns generic "archaeological site" instead of specific type. Never downgrade a specific type. |
| P571 | Inception | Verify period_start — **but** inception is often discovery/museum/renovation date, NOT historical period. Always ask: "Is this when the site was BUILT/ACTIVE, or when it was FOUND/RESTORED?" |
| P580 | Start time | Alternative to P571 for period_start — same caveats apply |
| P582 | End time | Verify period_end |
| P1435 | Heritage designation | heritage_designation field |
| P18 | Image | commons_image field |
| P373 | Commons category | Image gallery |
| P2596 | Culture/civilization | Context |
| P149 | Architectural style | Context |
| P361 | Part of | Verify parent_site_id |
| P1612 | Pleiades ID | Cross-reference |
| P1566 | GeoNames ID | Cross-reference |

---

## Execution Procedure

### Step 0 — Run the orchestrator

```bash
# Default: sync production → audit → package for upload
python scripts/audit_enrich.py

# Force re-audit everything
python scripts/audit_enrich.py --mode full

# Single source only
python scripts/audit_enrich.py --source ancient_nerds

# Use production API instead of local dev server
python scripts/audit_enrich.py --api-url https://ancientnerds.com

# Individual phases
python scripts/audit_enrich.py --phase sync           # Fetch production → local DB
python scripts/audit_enrich.py --phase mechanical      # Wave 0 only
python scripts/audit_enrich.py --phase enrich          # Wave 1 only
python scripts/audit_enrich.py --phase verify          # Wave 2 prep (create batch files)
python scripts/audit_enrich.py --phase agents          # Wave 2 batch status + handoff instructions
python scripts/audit_enrich.py --phase merge --dry-run # Preview agent results merge
python scripts/audit_enrich.py --phase merge           # Merge agent results → DB
python scripts/audit_enrich.py --phase package         # Export cleaned DB for db.html upload
python scripts/audit_enrich.py --phase export          # Re-export static JSON
```

The orchestrator handles:
1. **Sync** from production API (capture manual edits from db.html)
2. Fetching candidates from all 3 sources (respecting `last_audited` freshness)
3. Running Wave 0 mechanical fixes
4. Running Wave 1 enrichment pipeline (calls existing scripts)
5. Preparing Wave 2 agent batch files
6. Marking sites as audited
7. **Package** cleaned data as JSON for db.html upload (auto-snapshot on upload)
8. Re-exporting static JSON

### Step 0b — Sync from Production

```bash
python scripts/audit_enrich.py --phase sync
# Or against a different API:
python scripts/audit_enrich.py --phase sync --api-url https://ancientnerds.com
```

Fetches `GET /api/v1/sites.geojson?source=ancient_nerds` from the API (default: `http://localhost:5175`) and upserts every site into the local database. This captures any manual edits made via `db.html` that aren't reflected locally.

**Why this matters:** If you edited a site's country on production via db.html, and the local DB still has the old value, the audit would "fix" it back to the wrong value. Syncing first prevents this.

The sync runs automatically as the first step when you run `python scripts/audit_enrich.py` without `--phase`.

### Step 1 — Wave 0: Mechanical Fixes (auto)

These fixes require **no research** — they are deterministic corrections:

| Fix | Detection | Correction |
|-----|-----------|------------|
| **Suspect modern flagging** | Name matches modern-institution phrases (wildlife sanctuary, safari park, botanical garden, theme park, amusement park, aquarium, planetarium, etc.) AND site has a vague type (Unknown/NULL/site) | Set `site_type = 'suspect_modern'`. Logged for admin review. Sites with specific archaeological types (heritage_site, temple, fortress, etc.) are never flagged — "Masada National Park" stays as Fortress/citadel. |
| `site_type` normalization | Value differs from `normalize_site_type(site_type)` | Replace with canonical form |
| `period_name` recomputation | `period_name` doesn't match `categorize_period(period_start)` | Recompute from `period_start` |
| Raw year parsing | `raw_data->>'year'` parseable but `period_start` is NULL | Parse and set `period_start` |
| Compound capitalization | `site_type ~ '^[a-z].*/'` | Capitalize first letter |

Common raw_year patterns:

| Pattern | Example | Parse rule |
|---------|---------|------------|
| `N BC` | `48000 BC` | Negate the number |
| `N AD` | `300 AD` | Use the number |
| `Nth ml. BC` | `9th ml. BC` | `-(N * 1000)` — millennium |
| `Nth - Nth ml. BC` | `3rd - 2nd ml. BC` | Use the earlier (larger) millennium |
| `N BC - N AD` | `500 BC - 200 AD` | Use the BC value (start of range) |
| `Nth c. BC` | `5th c. BC` | `-(N * 100)` — century |
| `N,NNN BC` | `48,000 BC` | Strip commas, negate |

Trust hierarchy for period data:
1. `raw_data->>'year'` (most specific)
2. Wikidata P571/P580 (cross-referenced)
3. `raw_data->>'period'` (pre-computed bucket — can be WRONG when raw_year exists)
4. Claude's knowledge / WebSearch (last resort)

The orchestrator writes all SQL to `output/audit_mechanical_fixes.sql` for review and VPS sync.

### Step 2 — Wave 1: Wikidata Enrichment Pipeline (auto)

Runs the existing enrichment scripts in sequence:

```bash
python scripts/export_card_sites.py      # Export sites
python scripts/enrich_reconcile.py       # Match sites → Wikidata QIDs
python scripts/enrich_fetch_claims.py    # Fetch structured claims
python scripts/enrich_wiki_select.py     # Select best Wikipedia articles
```

**Outputs:**
- `output/enrichment_qids.json` — QID matches (expect >80% match rate)
- `output/enrichment_claims.json` — Wikidata claims (inception dates, heritage, images)
- `output/enrichment_wiki.json` — Best Wikipedia articles (multilingual)

### Step 3 — Wave 2: Prepare Agent Batches

```bash
python scripts/audit_enrich.py --phase verify
```

The orchestrator creates batch input files in `output/audit_batches/batch_NNN_input.json`, each containing ~50 sites that need research. It detects:

- `period_start` is NULL (with or without Wikidata enrichment data)
- `period_start > 1500` on non-museum sites (P1 suspect modern)
- Low-confidence Wikidata matches (< 0.8) excluded from auto-apply
- No Wikidata match at all
- Missing country or site_type
- No description and no wiki extract

After preparing batches, check status:

```bash
python scripts/audit_enrich.py --phase agents
```

This prints a summary of pending batches, issue breakdown, and handoff instructions.

**Batch input format:**
```json
{
  "batch_id": "001",
  "sites": [
    {
      "site_id": "uuid",
      "name": "Gobekli Tepe",
      "source_id": "ancient_nerds",
      "lat": 37.22, "lon": 38.92,
      "country": "Turkey",
      "site_type": "temple",
      "period_start": null,
      "source_url": "https://en.wikipedia.org/wiki/Gobekli_Tepe",
      "enrichment": { "qid": "Q187402", "inception": -9500, "heritage": "UNESCO..." },
      "wiki_extract": "...",
      "needs_fix": ["period_start is NULL — enrichment says -9500, verify"]
    }
  ]
}
```

**Batch output format:**
```json
{
  "batch_id": "001",
  "sites": {
    "uuid": {
      "status": "fixed",
      "fixes": [
        {"field": "period_start", "old": null, "new": -9500, "confidence": "high", "evidence": "Wikidata P571 + UNESCO listing + Wikipedia article"}
      ],
      "enrichment": { "confidence_score": 0.95 },
      "card_description": "Built 9,600 BC — 6,000 years before Stonehenge...",
      "manual_notes": null
    }
  },
  "stats": {"fixed": 35, "verified": 10, "manual": 5}
}
```

### Step 3b — Wave 2: Execute Agent Research (Claude Code Procedure)

**Trigger:** The user says "run Wave 2 agent research" (or similar).

Claude Code follows this procedure to launch parallel research agents that process the batch files created by Step 3.

#### Prerequisites

1. Read `output/audit_batches/merge_manifest.json`
2. Identify all batches with `"status": "pending"` that do NOT yet have a `batch_NNN_results.json` file
3. Report: "Found N pending batches (M total sites). Launching in waves of 10."

#### Launch agents — 10 parallel per wave

For each wave of up to 10 pending batches, launch Task agents with `subagent_type: "general-purpose"`. Wait for all 10 to complete before launching the next wave.

Each agent receives the prompt below (with `NNN` replaced by the batch number):

````
You are a research agent auditing archaeological sites for the Ancient Nerds database.

## Your task

1. Read the batch input file: `output/audit_batches/batch_NNN_input.json`
2. For each site, research the issues listed in its `needs_fix` array
3. Write results to: `output/audit_batches/batch_NNN_results.json`

## Research tools (use in this order of preference)

1. **WebSearch** — primary tool. Search for the site name + country, check Wikipedia, UNESCO, museum sites.
2. **Consensus MCP** (`mcp__claude_ai_Consensus__search`) — for disputed archaeological dating claims.
3. **Scholar Gateway MCP** (`mcp__claude_ai_Scholar_Gateway__semanticSearch`) — for peer-reviewed evidence on specific sites.

## Verification rules (MANDATORY)

- **Never use discovery/renovation/museum-opening dates as period_start.** The year Schliemann excavated Troy (1870) is NOT Troy's period. Ask: "Is this when the site was BUILT/ACTIVE, or when it was FOUND/RESTORED?"
- **Never downgrade site_type specificity.** If current type is "Temple", do NOT change to "Archaeological site" even if a source says so.
- **Never use historical country names.** Use current UN-recognized names: "Turkey" not "Anatolia", "Iraq" not "Mesopotamia".
- **Cross-reference at least 2 sources** for any fix you mark as "high" confidence.
- **If uncertain, classify as "manual"** — an empty field is better than a wrong one.
- **Do NOT auto-fix coordinates** — flag for manual review unless the error is extreme (wrong continent).
- **Do NOT trust a single source blindly** — especially Wikidata inception dates which are often wrong.
- **period_name must always match period_start** — do not set period_name independently; the merge script auto-computes it.

## Valid site_type values (CANONICAL_TYPES)

Only use these exact strings for site_type fixes:

**Settlements:** City, Town, Village, Settlement, Urban, Villa, City/town/settlement, Residence/villa/farmhouse
**Fortifications:** Castle, Citadel, Fort, Fortress, Military, Wall, Gate, Fortress/citadel, Castle/palace, Gate/archway/bridge, Fortification
**Religious:** Church, Mosque, Temple, Monastery, Sacred site, Sanctuary, Religious, Temple complex, Church/cathedral, Minaret/tower, Stone cross
**Burial:** Cemetery, Necropolis, Tomb, Burial, Funerary, Necropolis/tombs complex, Barrow, Mound/tumulus, Cairn, Elongated skulls
**Megalithic:** Megalithic, Megalithic stones, Megalithic structures, Megalithic statues, Megalithic walls, Stone circle, Dolmen, Standing stone, Henge, Timber circle, Polygonal masonry
**Rock & Cave:** Cave, Cave Structures, Rock relief/carving, Rock art, Petroglyphs, Sculptured stone, Geoglyphs
**Infrastructure:** Road, Bridge, Mine, Quarry, Infrastructure, Road/avenue/trackway, Reservoir/aqueduct/canal, Mine/quarry, Earthwork, Well
**Water & Ports:** Aqueduct, Bath, Harbor, Port, Underwater structures, Shipwreck
**Monuments:** Monument, Memorial, Stadium, Theater, Theatre, Forum, Palace, Pyramid complex, Museum, Amphitheatre, Scheduled monument, Heritage site, Archaeological site
**Other:** Site, Ruin, Inscription, Natural feature, Impact crater, Geological interest, Magnetic anomaly, Unknown

## Period buckets (for reference — merge script auto-computes period_name from period_start)

| period_start range | period_name |
|--------------------|-------------|
| < -4500 | < 4500 BC |
| -4500 to -3001 | 4500 - 3000 BC |
| -3000 to -1501 | 3000 - 1500 BC |
| -1500 to -501 | 1500 - 500 BC |
| -500 to 0 | 500 BC - 1 AD |
| 1 to 499 | 1 - 500 AD |
| 500 to 999 | 500 - 1000 AD |
| 1000 to 1499 | 1000 - 1500 AD |
| >= 1500 | 1500+ AD |

## Confidence classification

- **high**: 2+ independent sources agree (e.g., Wikipedia + UNESCO listing + Wikidata). Auto-applied by merge.
- **medium**: 1 strong source (e.g., Wikipedia article with citations). Deferred to manual review file.
- **low**: Inference only, no direct source found. Skipped by merge entirely.

## Output format

Write this exact JSON structure to `output/audit_batches/batch_NNN_results.json`:

```json
{
  "batch_id": "NNN",
  "sites": {
    "<site_id>": {
      "status": "fixed|verified|manual",
      "fixes": [
        {
          "field": "period_start",
          "old": null,
          "new": -9500,
          "confidence": "high",
          "evidence": "Wikipedia article states construction began c. 9500 BC, confirmed by UNESCO listing"
        }
      ],
      "enrichment": { "confidence_score": 0.95 },
      "manual_notes": null
    }
  },
  "stats": { "fixed": 0, "verified": 0, "manual": 0 }
}
```

**Status values:**
- `"fixed"` — at least one field was corrected with evidence
- `"verified"` — all current values are correct, no changes needed
- `"manual"` — cannot determine correct value, needs human review. Set `manual_notes` explaining why.

**IMPORTANT:** Every site_id from the input MUST appear in the output. Do not skip any site.

## Process each site

For each site in the batch:
1. Read its `needs_fix` array to understand what needs research
2. Check existing `enrichment` and `wiki_extract` data first — these are already fetched from Wikidata/Wikipedia
3. If enrichment data answers the question, verify it with a WebSearch and classify confidence
4. If enrichment data is missing or contradicts the issue, do WebSearch research
5. For disputed archaeological claims (e.g., controversial dating), use Consensus or Scholar Gateway
6. Produce a result entry with the appropriate status, fixes, and evidence

After processing all sites, count the stats and write the output file.
Print a one-line summary: "Batch NNN complete: X fixed, Y verified, Z manual"
````

#### Validate results

After all agents complete:

1. Read each `batch_NNN_results.json`
2. For each batch, load the corresponding `batch_NNN_input.json` and verify every input `site_id` appears in the output
3. Validate that any `site_type` fix values are in the canonical list above
4. Report aggregate stats: total fixed, verified, manual across all batches
5. Flag any batches with missing site_ids for re-processing

#### Handoff

Tell the user:
```
Agent research complete. X sites fixed, Y verified, Z flagged for manual review.

Next steps:
  python scripts/audit_enrich.py --phase merge --dry-run   # Preview changes
  python scripts/audit_enrich.py --phase merge              # Apply to DB
```

### Step 4 — Merge Agent Results → DB

```bash
# Preview what will change (no DB writes):
python scripts/audit_enrich.py --phase merge --dry-run

# Apply changes:
python scripts/audit_enrich.py --phase merge
```

Reads all `batch_NNN_results.json` files and:
- **Validates** `site_type` against `CANONICAL_TYPES` (normalizes via `normalize_site_type()`)
- **Auto-computes** `period_name` from `period_start` via `categorize_period()` — never trusts agent's `period_name` value
- **Auto-applies** only `high` confidence fixes
- **Defers** `medium` confidence fixes to `output/audit_manual_review.json` for human review
- **Skips** `low` confidence fixes entirely
- Applies fixes with conditional WHERE clauses (protecting user edits)
- Updates `unified_sites.last_audited = NOW()`
- Updates `card_stats` enrichment columns + `last_enriched = NOW()`

### Step 5 — Wave 3: Card Descriptions

For `ancient_nerds` sites only. Delegates to `CARD_DESCRIPTIONS.md`.

### Step 5b — Package for db.html Upload

```bash
python scripts/audit_enrich.py --phase package
# Or for a single source:
python scripts/audit_enrich.py --phase package --source ancient_nerds
```

Exports the cleaned local database as GeoJSON files ready for db.html upload:
- `output/audit_upload_ancient_nerds.geojson`

The GeoJSON format matches what db.html's own "Export GeoJSON" button produces, so it round-trips cleanly. db.html matches uploaded sites to existing ones **by name** — only the sites in the file get updated (like a GitHub diff). Sites not in the file are untouched.

**To apply to production:**
1. Open `db.html` in the browser
2. Upload the `.geojson` file
3. db.html auto-creates a snapshot before applying changes
4. If anything looks wrong, roll back to the pre-upload snapshot

This runs automatically as the second-to-last step in a full run.

### Step 6 — Re-export Static JSON

```bash
python scripts/audit_enrich.py --phase export
# Or directly:
python -m pipeline.static_exporter --sites-only
```

### Step 7 — Quality Gate & Final Report

Run the quality gate query:
```sql
SELECT
  source_id,
  COUNT(*) AS total,
  ROUND(100.0 * COUNT(*) FILTER (WHERE period_start IS NOT NULL) / COUNT(*), 1) AS period_pct,
  ROUND(100.0 * COUNT(*) FILTER (WHERE site_type IS NOT NULL AND site_type NOT ILIKE 'Unknown') / COUNT(*), 1) AS type_pct,
  ROUND(100.0 * COUNT(*) FILTER (WHERE country IS NOT NULL) / COUNT(*), 1) AS country_pct,
  COUNT(*) FILTER (WHERE last_audited IS NOT NULL) AS audited,
  COUNT(*) FILTER (WHERE last_audited IS NULL) AS unaudited
FROM unified_sites
WHERE source_id IN ('ancient_nerds', 'lyra', 'ancient_nerds_community')
GROUP BY source_id
ORDER BY total DESC;
```

---

## Resumability

Three levels of resume tracking:

1. **Site-level**: `unified_sites.last_audited` timestamp — `WHERE last_audited IS NULL OR last_audited < NOW() - INTERVAL '90 days'`
2. **Batch-level**: `output/audit_batches/merge_manifest.json` tracks which batches are complete/in-progress/pending
3. **Phase-level**: `--phase` argument lets you re-run any phase independently

Full phase order: `sync` → `mechanical` → `enrich` → `apply` → `verify` → `agents` → (Claude Code agents) → `merge` → `package` → `export`

You can re-run any phase safely. Sync is idempotent (upserts). Package overwrites previous output files.

---

## Audit Dimensions

| Code | Dimension | Key checks |
|------|-----------|------------|
| D1-PERIOD | Period accuracy | `period_start` historically correct; `period_name` matches `categorize_period(period_start)`; not a museum opening, discovery, or renovation date |
| D2-TYPE | Site type accuracy | In valid types list; reflects original function not current state; "Ruin"/"Archaeological Site" never overwrites a more specific type |
| D3-LOCATION | Location accuracy | Coords in correct country; not in ocean; country is modern name not historical polity |
| D4-NAME | Name quality | No "Name, Country" suffixes; no encoding artifacts; consistent English naming; no whitespace issues |
| D5-PARENT | Parent links | No self-refs or circular refs; semantically correct (part-of not "near"); parent exists in DB |
| D6-DUPES | Duplicates | Same `name_normalized` across sources; spatial proximity <1km with similar name |
| D7-COMPLETE | Completeness | Missing description, source_url, thumbnail_url |
| D8-URL | Source URLs | Not 404; about THIS site not a generic list |

---

## Priority Tiers

| Tier | Criteria | Query |
|------|----------|-------|
| P0 | **Suspect modern** — name matches modern-institution phrases (wildlife sanctuary, safari park, aquarium, etc.) AND has a vague type (Unknown/NULL/site). Specific archaeological types are never overwritten. | Detected automatically in Wave 0. See `SUSPECT_MODERN_PHRASES` in `audit_enrich.py`. |
| P1 | `period_start > 1500` + non-museum type — likely Wikidata false positives | `WHERE period_start > 1500 AND site_type NOT IN ('museum', 'Museum', 'geological interest') AND site_type NOT ILIKE '%museum%'` |
| P2 | `period_start IS NULL` — dots have no color on globe | `WHERE period_start IS NULL` |
| P3 | `site_type IS NULL OR site_type = 'Unknown'` — can't be filtered | `WHERE site_type IS NULL OR site_type = 'Unknown'` |
| P3.5 | Non-canonical `site_type` variants | Compare each distinct `site_type` against `normalize_site_type()` output |
| P4 | `country IS NULL` — can't be filtered by region | `WHERE country IS NULL` |
| P5 | `period_name` inconsistent or non-canonical | `WHERE period_start IS NOT NULL AND period_name != categorize_period(period_start)` |
| P6 | Duplicate candidates | `SELECT name_normalized, COUNT(*) FROM unified_sites GROUP BY name_normalized HAVING COUNT(*) > 1` |
| P7 | Random 5% spot-check | `WHERE period_start IS NOT NULL AND site_type IS NOT NULL AND country IS NOT NULL ORDER BY RANDOM() LIMIT ...` |

---

## Anti-Patterns

These are explicit "do NOT" rules:

1. **Do NOT batch-apply Wikidata claims without per-site review.** Wikidata inception dates are often discovery/excavation/renovation dates, not historical period dates.
2. **Do NOT use "Ruin" or "Archaeological Site" to replace more specific types.** If a site is typed "Temple", it stays "Temple" even though it's technically a ruin today.
3. **Do NOT use museum/discovery/renovation dates as `period_start`.** The year Schliemann excavated Troy (1870) is not Troy's period.
4. **Do NOT auto-fix coordinates.** Flag for manual review unless the error is extreme (wrong continent, in the ocean).
5. **Do NOT guess when uncertain.** An empty `period_start` is better than a wrong one. Leave it NULL and classify as MANUAL_RESEARCH.
6. **Do NOT trust a single source blindly.** Cross-reference at least two sources for medium-confidence fixes.
7. **Do NOT use historical country names.** Use current UN-recognized names (e.g., "Turkey" not "Anatolia").
8. **Do NOT fix `period_name` independently of `period_start`.** Always keep them consistent via `categorize_period()`.
9. **Do NOT downgrade site_type specificity.** If Wikidata P31 says "archaeological site" but the DB has "Temple", keep "Temple".
10. **Do NOT skip the raw_data cross-reference.** The `raw_data` JSONB column contains original source data.
11. **Do NOT trust `raw_period` when `raw_year` exists.** Parse `raw_year` first; only fall back to `raw_period` when `raw_year` is NULL.
12. **Do NOT modify sites from sources outside the audit scope.** Always include `AND source_id = '<target>'` in every UPDATE.
13. **Do NOT write raw strings for `site_type` — always run through `normalize_site_type()`.** Fix the data AND the ingestion path.
14. **Do NOT overwrite user-edited values without a conditional WHERE clause.** See "Protecting User Edits" section.
15. **Do NOT add a site type to one canonical source without the other.** `CANONICAL_TYPES` in `pipeline/normalizers/site_type.py` and `CATEGORY_COLORS` in `ancient-nerds-map/src/constants/colors.ts` must stay in sync.

---

## Quality Gate

The audit targets **100% coverage** for all fields. The audit passes when all conditions are met — any remaining gaps must have corresponding MANUAL entries.

| Condition | Target |
|-----------|--------|
| Period coverage (`period_start IS NOT NULL` OR flagged MANUAL) | 100% |
| Type coverage (`site_type` valid and not 'Unknown' OR flagged MANUAL) | 100% |
| Country coverage (`country IS NOT NULL` OR flagged MANUAL) | 100% |
| `period_name` ↔ `period_start` consistency | 100% |
| No self-referencing `parent_site_id` | 0 |
| No same-source duplicates | 0 |
| All `site_type` values in canonical form | 0 non-canonical |
| P1 critical findings remaining | 0 |

"100%" means every site is either **fixed**, **verified correct**, or **flagged MANUAL**.

---

## SQL Conventions

- **Conditional WHERE clauses (MANDATORY):** Always include the current (wrong) value:
  ```sql
  -- GOOD
  UPDATE unified_sites SET period_start = -9000 WHERE id = '<uuid>' AND period_start IS NULL;
  -- BAD
  UPDATE unified_sites SET period_start = -9000 WHERE id = '<uuid>';
  ```
- **File-based execution for large batches:** Heredocs hit OS limits for >100 statements. Write SQL to a file:
  ```bash
  cat fixes.sql | docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map
  ```
- **`edited_by = 'audit'`:** Every audit UPDATE must include this to mark rows as audit-touched.

**Windows notes:**
- `docker cp` + `psql -f` can fail silently. Prefer piping: `cat file.sql | docker exec -i ...`
- Set `PYTHONIOENCODING=utf-8` before running Python scripts with Unicode output
- `gzip.open()` needs `str()` conversion for `Path` objects on Windows

---

## Wikidata Enrichment Pipeline (Wave 1 Detail)

### Phase 1: Entity Reconciliation

**Script:** `python scripts/enrich_reconcile.py`

Matches all sites to Wikidata Q-items:
1. **Extract QIDs from existing `source_url`** — regex patterns, 0 API calls, highest confidence
2. **W3C Reconciliation API** (`wikidata.reconci.link`) — batch POST site name + coordinates
3. **SPARQL geo-search fallback** — `SERVICE wikibase:around` with fuzzy name matching

**Output:** `output/enrichment_qids.json` — expected >80% match rate

### Phase 2: Structured Data Pull

**Script:** `python scripts/enrich_fetch_claims.py`

Batch-fetches Wikidata claims via `wbgetentities` API (50 QIDs per request): inception (P571), heritage (P1435), Commons image (P18), sitelinks, and more.

**Output:** `output/enrichment_claims.json`

### Phase 3: Multilingual Wikipedia Article Selection

**Script:** `python scripts/enrich_wiki_select.py`

For each site, selects the best Wikipedia article:
1. Check English article > 2000 bytes → use it
2. Otherwise check priority languages: local language, de, fr, it, es, etc.
3. Pick longest article exceeding 2000 bytes
4. Fetch article extract via REST API

**Output:** `output/enrichment_wiki.json`

### Confidence Scoring

| Component | Weight | Criteria |
|-----------|--------|----------|
| Source count | 0-0.3 | How many sources corroborate |
| Coordinate agreement | 0-0.2 | Coords match across sources |
| Heritage designation | 0.15 | Has P1435 |
| Wikidata reference count | 0.1 | Claims have citations |
| Wikipedia article quality | 0.1 | Article byte size > 5000 |
| Date precision | 0.15 | Has inception and/or end dates |

Flag low-confidence (<0.5) items for human review.

---

## Agent Prompt Template (Wave 2)

Each Wave 2 agent receives this prompt structure:

```
You are auditing archaeological sites for the Ancient Nerds database. For each site
in your batch, research the issues listed in `needs_fix` and produce fixes or flag
for manual review.

Rules:
- Use conditional WHERE clauses (protect user edits)
- Never downgrade site_type specificity
- Never use discovery/renovation dates as period_start
- Cross-reference at least 2 sources for medium-confidence fixes
- If uncertain, classify as "manual" — an empty field is better than a wrong one

For each site, produce a result entry with:
- status: "fixed" | "verified" | "manual"
- fixes: array of {field, old, new, confidence, evidence}
- enrichment: {confidence_score}
- manual_notes: string explaining why (if manual)

Read your batch from: output/audit_batches/batch_NNN_input.json
Write results to: output/audit_batches/batch_NNN_results.json
```

---

## Utility References

| Function | File | Line |
|----------|------|------|
| `categorize_period(year)` | `pipeline/utils/text.py` | 219 |
| `normalize_site_type(type)` | `pipeline/normalizers/site_type.py` | 120 |
| `normalize_name(name)` | `pipeline/utils/text.py` | 7 |
| `normalize_country(country)` | `pipeline/utils/country_lookup.py` | 532 |
| `lookup_country(lat, lon)` | `pipeline/utils/country_lookup.py` | 271 |

### Reused Infrastructure

| What | Where |
|------|-------|
| QID extraction | `pipeline/connectors/imagery/wikimedia_resolver.py` (`extract_qid_from_url`, `extract_article_from_wikipedia_url`) |
| SPARQL protocol | `pipeline/connectors/protocols/sparql.py` |
| Site type normalizer | `pipeline/normalizers/site_type.py` (`normalize_site_type`) |
| Period categorizer | `pipeline/utils/text.py` (`categorize_period`) |
| Country lookup | `pipeline/utils/country_lookup.py:271` (`lookup_country`) |
| Enrichment scripts | `scripts/enrich_reconcile.py`, `enrich_fetch_claims.py`, `enrich_wiki_select.py` |
| Enrichment import | `scripts/enrich_import.py` |
| Audit log table | `database_audit_log` (created by Step 1 audit inventory) |
| Snapshot service | `api/services/snapshots.py` (pre-change state capture) |

Period buckets (from `categorize_period`):

| Range | Label |
|-------|-------|
| < -4500 | `< 4500 BC` |
| -4500 to -3000 | `4500 - 3000 BC` |
| -3000 to -1500 | `3000 - 1500 BC` |
| -1500 to -500 | `1500 - 500 BC` |
| -500 to 1 | `500 BC - 1 AD` |
| 1 to 500 | `1 - 500 AD` |
| 500 to 1000 | `500 - 1000 AD` |
| 1000 to 1500 | `1000 - 1500 AD` |
| >= 1500 | `1500+ AD` |

> **Boundary trap:** `categorize_period()` uses strict `<`, so boundary values fall into the NEXT bucket: `-3000` → "3000 - 1500 BC", `500` → "500 - 1000 AD". Always verify `period_name` after setting `period_start` to a boundary value.
