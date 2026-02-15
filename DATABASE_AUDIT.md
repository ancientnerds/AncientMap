# Database Audit Framework

A playbook for AI-assisted audits of the AncientMap database. Uses a three-phase approach: mechanical fixes, API-assisted batch verification, and per-site research. Every field must reach **100% coverage** — anything unfixable is surfaced in a MANUAL FIXES REQUIRED section.

All operations run against the **local** PostgreSQL database (Docker container `ancient_nerds_db` on `localhost:5432`). After fixing the DB, re-export static JSON and push via git.

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

## Workflow

```
Local PostgreSQL ──(audit + fix)──→ Re-export static JSON ──(git push)──→ Production
                                         │
                                    database_fixes.sql ──(apply to VPS DB)──→ VPS sync
```

---

## Source-Aware Audit Strategies

Not all sources are equal. The audit approach varies by data provenance.

| Source | Sites | Strategy | Tools |
|--------|-------|----------|-------|
| `ancient_nerds` | ~5,000 | **Full audit** — most sites have Wikipedia `source_url`. Batch-resolve to Wikidata QIDs, fetch claims P625/P17/P31/P571, compare against DB. Per-site research for discrepancies. | Wikidata API, Wikipedia REST API, Consensus, Scholar Gateway, WebSearch |
| `lyra` | varies | **Enrichment quality check** — sites have `enrichment_data` JSONB from the Lyra pipeline. Verify enrichment claims, re-research if enrichment_status was "pending" at promotion time. | Check `enrichment_data` JSONB, re-verify via WebSearch |
| Academic (`pleiades`, `dare`, `topostext`, `unesco`, `wikidata`, `osm_historic`) | varies | **Spot-check + gap fill** — generally trustworthy. Cross-reference `raw_data` JSONB, fill missing fields. Don't second-guess authoritative academic data. | `raw_data` comparison, WebSearch for gaps |
| Geological (`volcanic_holvol`, `earth_impacts`, `ncei_*`) | varies | **Data integrity check** — standardized datasets. Verify against `raw_data`, minimal research needed. Focus on format consistency. | `raw_data` comparison |
| Other connectors | varies | **Gap fill** — fill missing period/type/country using WebSearch and Claude's knowledge. | WebSearch, Claude's knowledge |

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

Use these tools during Phases B and C. They are listed in order of preference.

| Tool | Purpose | How to invoke |
|------|---------|---------------|
| **Wikidata API** | Batch-verify period, type, country, coords for sites with Wikipedia URLs | Resolve Wikipedia URL → Wikidata QID, then fetch claims via `curl -H "User-Agent: AncientNerdsMap/1.0" "https://www.wikidata.org/w/api.php?action=wbgetentities&ids={QID}&format=json&props=claims\|labels&languages=en"`. Extract `{lang}` from the source URL (usually `en`, but ~74 sites use `es`, `fr`, `it`, `de`, `ca`, `pt`, `ro`, `tr`). |
| **Wikipedia REST API** | Extract metadata from linked articles | `https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}` — returns description, extract, coordinates, `wikibase_item` (QID). Use the language prefix from the source URL. **Requires User-Agent header.** |
| **Consensus MCP** | Search 200M+ academic papers for disputed archaeological claims | `mcp__claude_ai_Consensus__search` — e.g., query: "dating of Baalbek temple complex" |
| **Scholar Gateway MCP** | Semantic search over peer-reviewed literature | `mcp__claude_ai_Scholar_Gateway__semanticSearch` — full natural language queries |
| **WebSearch** | General verification for sites without academic coverage | Wikipedia, museum sites, UNESCO heritage pages |
| **Pipeline utilities** | Existing normalization functions (see Utility References) | `categorize_period()`, `normalize_site_type()`, `normalize_country()`, `lookup_country()` |

### Wikidata property reference

| Property | Meaning | Audit use |
|----------|---------|-----------|
| P625 | Coordinate location | Verify lat/lon |
| P17 | Country | Verify country — P17 value is a QID (e.g., Q43 = Turkey). Resolve to label via `entities[QID].labels.en.value` in the entity JSON. |
| P31 | Instance of | Verify site_type — **but** P31 often returns generic "archaeological site" instead of specific type like "Temple". Never downgrade a specific type. |
| P571 | Inception | Verify period_start — **but** inception is often discovery/museum/renovation date, NOT historical period. Always ask: "Is this when the site was BUILT/ACTIVE, or when it was FOUND/RESTORED?" |
| P580 | Start time | Alternative to P571 for period_start — same caveats apply |
| P582 | End time | Verify period_end |
| P361 | Part of | Verify parent_site_id — **NOTE:** `parent_site_id` column does not exist in the DB yet (model-only). Skip until migrated. |
| P18 | Image | Fill missing thumbnail_url |

---

## Execution Procedure

### Step 0 — Determine mode

If the user specifies a mode, use it. If not, default to `gaps`.

| Mode | Scope |
|------|-------|
| `full` | All sites in the database |
| `targeted <names>` | Only the named sites (comma-separated) |
| `source <id>` | All sites from one source_id |
| `gaps` | Only sites with missing or suspect fields (default) |
| `spot-check` | Random 5% sample of "complete" sites |

### Step 1 — Connect and take inventory

Connect to the local database:
```bash
docker exec -it ancient_nerds_db psql -U ancient_map -d ancient_map
```

Run the inventory query:
```sql
SELECT
  source_id,
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE period_start IS NULL) AS no_period,
  COUNT(*) FILTER (WHERE site_type IS NULL OR site_type ILIKE 'Unknown') AS no_type,
  COUNT(*) FILTER (WHERE country IS NULL) AS no_country,
  COUNT(*) FILTER (WHERE period_start > 1500
    AND site_type NOT IN ('museum', 'Museum', 'geological interest')
    AND site_type NOT ILIKE '%museum%'
  ) AS suspect_modern
FROM unified_sites
GROUP BY source_id
ORDER BY total DESC;
```

Create the audit log table if it doesn't exist:
```sql
CREATE TABLE IF NOT EXISTS database_audit_log (
  id SERIAL PRIMARY KEY,
  site_id UUID NOT NULL,
  site_name TEXT NOT NULL,
  action TEXT NOT NULL CHECK (action IN ('fix', 'verify', 'flag_manual')),
  field_changed TEXT,           -- NULL for 'verify' action
  old_value TEXT,
  new_value TEXT,
  confidence TEXT NOT NULL CHECK (confidence IN ('high', 'medium', 'low')),
  evidence_source TEXT NOT NULL,
  changed_at TIMESTAMP DEFAULT NOW(),
  changed_by TEXT DEFAULT 'claude_audit'
);
```

The `action` column tracks three outcomes:
- **`fix`**: Value was changed in the database
- **`verify`**: Value was audited and confirmed correct (enables resumability — skip on next run)
- **`flag_manual`**: Issue identified but not auto-fixable (goes to MANUAL FIXES REQUIRED section)

Report the inventory numbers before proceeding.

### Step 2 — Build work queue

Select sites by priority tier (see Priority Tiers below), applying source-aware strategies.

- For `targeted` mode: skip this step — search for the named sites directly.
- For `gaps` mode: work through P1 → P4 tiers.
- For `full` mode: work through P1 → P7 tiers.
- For `spot-check` mode: work P7 only.
- For `source` mode: all tiers, but only for the specified source_id.

**Batch size:** 50 sites per batch. Process all three phases for each batch before moving to the next.

**Resumability:** Before building the queue, check the audit log for already-verified sites:
```sql
-- Skip sites verified in a previous session
SELECT DISTINCT site_id FROM database_audit_log
WHERE action IN ('fix', 'verify') AND changed_at > NOW() - INTERVAL '30 days';
```

### Step 2.5 — Phase A0: Raw data pattern analysis

Before any fixes, run a **pattern coverage report** on the target source's `raw_data` JSONB. This catches bulk-fixable year formats that would otherwise go to expensive per-site research.

**For `ancient_nerds` source:**
```sql
-- Enumerate all distinct raw_data->>'year' patterns
SELECT
  regexp_replace(raw_data->>'year', '[0-9]+', 'N', 'g') AS year_pattern,
  COUNT(*) AS sites,
  COUNT(*) FILTER (WHERE period_start IS NULL) AS unfixed
FROM unified_sites
WHERE source_id = 'ancient_nerds'
  AND raw_data->>'year' IS NOT NULL
GROUP BY year_pattern
ORDER BY unfixed DESC;
```

Common patterns and how to parse them:

| Pattern | Example | Parse rule |
|---------|---------|------------|
| `N BC` | `48000 BC` | Negate the number |
| `N AD` | `300 AD` | Use the number |
| `Nth ml. BC` | `9th ml. BC` | `-(N * 1000)` — this is a millennium, not a century |
| `Nth - Nth ml. BC` | `3rd - 2nd ml. BC` | Use the earlier (larger) millennium |
| `N BC - N AD` | `500 BC - 200 AD` | Use the BC value (start of range) |
| `Nth c. BC` | `5th c. BC` | `-(N * 100)` — century |
| `Nth c. AD` | `3rd c. AD` | `N * 100` — century |
| `N,NNN BC` | `48,000 BC` | Strip commas, negate |

**Any pattern with >10 unfixed sites should get a bulk SQL fix in Phase A**, not per-site research in Phase C.

**Re-validate existing period_start against raw_year:**

Sites that already have a `period_start` may have gotten it from `raw_period` (the pre-computed bucket) instead of `raw_year` (the actual year string). This is a common ingestion error — re-parsing `raw_year` and comparing is a **bulk Phase A fix**, not per-site Phase C research.

```sql
-- Find sites where period_start may have been set from raw_period instead of raw_year
-- Compare parsed raw_year against current period_start
SELECT id, name, period_start, raw_data->>'year' as raw_year, raw_data->>'period' as raw_period
FROM unified_sites
WHERE source_id = 'ancient_nerds'
  AND raw_data->>'year' IS NOT NULL
  AND period_start IS NOT NULL
ORDER BY name;
```

Parse each `raw_year` string using the pattern table above and compare against `period_start`. If they differ by >5% or >100 years, the site likely got its period from `raw_period` instead. Fix these in bulk during Phase A — do not send them to Phase C research.

**Trust hierarchy for period data:**
1. `raw_data->>'year'` (most specific — original source's year string)
2. Wikidata P571/P580 (cross-referenced, not blind)
3. `raw_data->>'period'` (often a pre-computed bucket label — can be WRONG when raw_year exists)
4. Claude's knowledge / WebSearch (last resort)

> **Warning:** `raw_data->>'period'` (the pre-computed bucket) is frequently inconsistent with `raw_data->>'year'`. When both exist, ALWAYS parse `raw_year` and ignore `raw_period`. The millennium pattern miss (819 sites) happened because the parser fell through to `raw_period` which gave wrong values.

### Step 3 — Phase A: Mechanical fixes

These fixes require **no research** — they are deterministic corrections based on internal consistency rules. Auto-apply all of them.

| Fix | Detection | Correction |
|-----|-----------|------------|
| `period_name` ↔ `period_start` inconsistency | Compare `period_name` against `categorize_period(period_start)` | Recompute `period_name` from `period_start` |
| Self-referencing `parent_site_id` *(skip if column not migrated)* | `WHERE parent_site_id = id` | Set `parent_site_id = NULL` |
| Orphan parent references *(skip if column not migrated)* | `LEFT JOIN` where parent doesn't exist | Set `parent_site_id = NULL` |
| Invalid `site_type` values | Value not in canonical list (see Valid Site Types) | Map via `normalize_site_type()` or flag |
| Non-canonical `site_type` variants | Value differs from `normalize_site_type(site_type)` — catches case drift (`Rock ART` vs `Rock art`), separator drift (`rock_art` vs `Rock art`), synonym drift (`ruins` vs `ruin`, `mausoleum` vs `tomb`), plural drift (`Petroglyph` vs `Petroglyphs`) | Replace with `normalize_site_type(site_type)`. Detection query below. |
| Compound type capitalization | Compound types stored lowercase when canonical form has first letter capitalized: `city/town/settlement` → `City/town/settlement`. Detection: `WHERE site_type ~ '^[a-z].*/'` | Capitalize first letter, keep rest as-is. Detection query below. |
| `name_normalized` drift | Compare against `normalize_name(name)` | Recompute `name_normalized` |
| Same-source exact duplicates | `GROUP BY source_id, name_normalized HAVING COUNT(*) > 1` | Flag for merge — do NOT auto-delete |
| Non-archaeological entries | See comprehensive detection query below | Flag for review — museums, geological formations, pseudoarchaeology, wildlife sanctuaries, national parks, and paleontological sites are not archaeological sites |

**Detecting non-archaeological entries:**

```sql
-- Comprehensive non-archaeological detection
SELECT id, name, site_type FROM unified_sites WHERE source_id = 'ancient_nerds' AND (
  site_type IN ('museum', 'Museum', 'geological interest')
  OR name ILIKE '%museum%'
  OR name ILIKE '%wildlife sanctuary%'
  OR name ILIKE '%national park%'
  OR name ILIKE '%bosnian pyramid%'       -- pseudoarchaeology
  OR name ILIKE '%yonaguni monument%'     -- debated geological
  OR name ILIKE '%elongated skull%'       -- museum display
  OR name ILIKE '%lemminkainen%'          -- pseudoarchaeology
);
```

Categories to check: museums, geological formations, pseudoarchaeology (Bosnian pyramids, Temple of Lemminkainen), wildlife sanctuaries, national parks, paleontological sites. Do NOT auto-delete — flag for review, as some site-museum composites (e.g., "Acropolis Museum" at the Acropolis) may be legitimate.

> **Note:** `parent_site_id` exists in the SQLAlchemy model but has never been migrated to the actual DB table. Run `SELECT column_name FROM information_schema.columns WHERE table_name = 'unified_sites' AND column_name = 'parent_site_id';` to check before running parent-related queries. Skip parent checks if the column doesn't exist.

**Detecting non-canonical `site_type` variants:**

This is the most common data hygiene issue. The canonical forms are defined in `pipeline/normalizers/site_type.py` (CANONICAL_TYPES list) and must match `CATEGORY_COLORS` keys in `ancient-nerds-map/src/constants/colors.ts`. Variants slip in when data is ingested without normalization, manually edited, or backfilled from external sources.

```sql
-- Find all site_type values that differ from their normalized form.
-- Run normalize_site_type() from Python against each distinct value.
-- Any mismatch = non-canonical variant that needs fixing.
SELECT site_type, COUNT(*) AS sites
FROM unified_sites
WHERE source_id IN ('ancient_nerds', 'ancient_nerds_radar')
  AND site_type IS NOT NULL
GROUP BY site_type
ORDER BY site_type;
```

**Detecting compound type capitalization:**

This is a high-volume issue — the Feb 2026 audit found **4,791** instances. Compound types like `city/town/settlement` are ingested lowercase but the canonical form capitalizes the first letter.

```sql
-- Find all compound types starting with lowercase
SELECT site_type, COUNT(*) FROM unified_sites
WHERE source_id = 'ancient_nerds' AND site_type ~ '^[a-z].*/'
GROUP BY site_type ORDER BY COUNT(*) DESC;
```

Fix with: `UPDATE unified_sites SET site_type = INITCAP(LEFT(site_type, 1)) || SUBSTRING(site_type FROM 2) WHERE site_type ~ '^[a-z].*/' AND source_id = 'ancient_nerds';`

Then in Python, compare each value against `normalize_site_type()`:
```python
from pipeline.normalizers.site_type import normalize_site_type
# For each distinct site_type from the query above:
# if normalize_site_type(raw) != raw → it's non-canonical, needs UPDATE
```

Common variant classes to watch for:
| Variant class | Example (wrong → right) | How it happens |
|---------------|------------------------|----------------|
| Case drift | `Rock ART` → `Rock art`, `TEMPLE` → `temple` | Manual edits, CSV imports |
| Underscore/space | `rock_art` → `Rock art`, `standing_stone` → `Standing stone` | Legacy data, API responses |
| Plural mismatch | `Petroglyph` → `Petroglyphs`, `ruins` → `ruin` | Source-specific naming |
| Synonym | `mausoleum` → `tomb`, `hillfort` → `fort`, `thermae` → `bath` | Different naming conventions per source |
| Title-case drift | `Monument` → `monument`, `Unknown` → `unknown` | Multiple case forms in CATEGORY_COLORS where lowercase is canonical |
| Compound capitalization | `city/town/settlement` → `City/town/settlement` | Ingestion without normalization — high volume (~4,791 in Feb 2026 audit) |

The bulk fix is a single UPDATE per variant:
```sql
-- Example: Fix all underscore variants
UPDATE unified_sites SET site_type = 'Rock art'
WHERE site_type = 'rock_art' AND source_id IN ('ancient_nerds', 'ancient_nerds_radar');
```

The orchestrator auto-migration (`pipeline/lyra/orchestrator.py`) already runs `normalize_site_type()` across all rows on every startup. But the audit should verify no new variants crept in since last deploy.

For each mechanical fix, log with `action = 'fix'`, `confidence = 'high'`, `evidence_source = 'internal_consistency'`.

**Generate SQL for each fix:**
```sql
-- Example: Fix period_name inconsistency
UPDATE unified_sites SET period_name = '< 4500 BC'
WHERE id = '<uuid>' AND period_start < -4500 AND period_name != '< 4500 BC';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source)
VALUES ('<uuid>', 'Site Name', 'fix', 'period_name', 'old value', '< 4500 BC', 'high', 'internal_consistency: categorize_period(period_start)');
```

### Step 4 — Phase B: API-assisted batch verification

For sites with Wikipedia URLs or Wikidata QIDs — primarily `ancient_nerds` and `lyra` sources.

**4a. Resolve Wikipedia URLs to Wikidata QIDs:**
```
For each site with source_url LIKE '%wikipedia%':
  1. Extract language prefix and article title from URL
     - Parse: https://{lang}.wikipedia.org/wiki/{title}
     - Most are "en", but ~74 sites use es/fr/it/de/ca/pt/ro/tr
  2. Fetch https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}
  3. Extract wikibase_item (QID) from response
```

**Non-English Wikipedia sites:** ~74 `ancient_nerds` sites link to non-English Wikipedia (es, fr, it, de, etc.). For these:
- The Wikipedia REST API still works — just use the correct `{lang}` prefix
- The summary/extract will be in the source language — Claude can read and translate it
- The `wikibase_item` (QID) is the same regardless of language, so Wikidata claims work identically
- Keep `source_url` pointing to the original foreign-language article
- If a site has NO Wikipedia URL but Wikidata has a `sitelinks` section, check for English Wikipedia first, then fall back to any available language

**Rate limiting:** Wikipedia and Wikidata APIs require a `User-Agent` header (requests without one get 403). Use `curl -H "User-Agent: AncientNerdsMap/1.0"` or equivalent. Rate limit: ~200 req/s for Wikipedia, be polite with Wikidata — add 100-200ms delay between requests.

**API endpoint preference:** `WebFetch` may get 403 from Wikipedia/Wikidata. Prefer `curl` via Bash with a User-Agent header, or the Wikidata action API (`wikidata.org/w/api.php?action=wbgetentities&ids={QID}&format=json`) which is more reliable.

**4b. Fetch Wikidata claims:**
```
For each QID:
  1. Fetch via action API (more reliable than Special:EntityData):
     curl -H "User-Agent: AncientNerdsMap/1.0" \
       "https://www.wikidata.org/w/api.php?action=wbgetentities&ids={QID}&format=json&props=claims|labels&languages=en"
  2. Extract claims: P625 (coords), P17 (country), P31 (instance-of), P571 (inception), P580/P582 (start/end time)
  3. For P17 (country) and P31 (instance-of): the claim value is a QID, not a label.
     Batch-resolve referenced QIDs in a single call:
     curl -H "User-Agent: AncientNerdsMap/1.0" \
       "https://www.wikidata.org/w/api.php?action=wbgetentities&ids=Q43|Q755017&format=json&props=labels&languages=en"
     Then read entities[QID].labels.en.value for each.
  4. P571 inception dates use ISO format with a precision field:
     - precision=9 = exact year, precision=8 = decade, precision=7 = century, precision=6 = millennium
     - Time format: "+1500-01-01T00:00:00Z" (positive=AD) or "-9999-01-01T00:00:00Z" (negative=BC)
     - For precision < 9, the year is approximate. E.g., Göbekli Tepe has time=-9999, precision=6
       (millennium) → "10th millennium BC" → use -9500 as period_start (confirmed by UNESCO: 9600 BCE).
     - ALWAYS cross-reference imprecise Wikidata dates with other sources (UNESCO, Britannica, etc.)
       before using them as period_start. Do NOT blindly convert the raw year value.
```

**4c. Compare against DB values — DO NOT AUTO-APPLY:**

Unlike the backfill script (`scripts/backfill_parent_sites.py` lines 402-434), which blindly trusts Wikidata, this phase **compares and classifies** each discrepancy:

| Field | DB value | Wikidata value | Action |
|-------|----------|----------------|--------|
| `period_start` | NULL | P571 year ≤ 1500 | Classify confidence, present for review |
| `period_start` | -3000 | P571 = 1870 | **Reject** — likely discovery date (Wikidata P571 false positive) |
| `site_type` | "Temple" | P31 = "archaeological site" | **Reject** — never downgrade specific to generic |
| `site_type` | "Unknown" | P31 = "temple" | Classify confidence, present for review |
| `country` | NULL | P17 = "Turkey" | High confidence, present for review |
| `lat`/`lon` | (31.2, 29.9) | P625 = (31.2, 29.9) | **Verify** — log as confirmed correct |
| `lat`/`lon` | (31.2, 29.9) | P625 = (40.1, 44.5) | **Flag** — do not auto-fix coords |

**Country discrepancy classification:**

Not all country discrepancies are genuine errors. Classify each one before acting:

| Category | Example | Action | Typical share |
|----------|---------|--------|---------------|
| Historical/political names | "Ottoman Empire" vs "Turkey" | Reject — DB already has modern name | ~40% |
| Naming variants | "United States of America" vs "USA" | Reject — both valid | ~25% |
| Genuine errors | "Germany" vs "Greece" for a Cretan site | Fix — Wikidata P17 is correct | ~5% |
| Disputed territories | Palestine/Israel, Western Sahara | Flag manual — editorial judgment | ~10% |
| Wikidata wrong/outdated | Wikidata has old country name | Reject — DB is correct | ~20% |

Only the "Genuine errors" category (~5%) should result in DB changes. The rest are noise — do not waste time on them.

**4d. Cross-reference raw_data:**

Every site stores original source data in the `raw_data` JSONB column. Compare current DB values against raw_data to detect drift introduced by backfill scripts.

**Note:** Raw data keys vary by source. For `ancient_nerds`, the keys are: `year` (string like "48,000 BC"), `period` (bucket label), `category`/`category_multi` (site type), `location` (country), `title`, `source` (URL), `description`, `image`.

```sql
SELECT id, name,
  raw_data->>'period' AS raw_period,
  period_name,
  raw_data->>'year' AS raw_year,
  period_start,
  raw_data->>'category' AS raw_category,
  site_type,
  raw_data->>'location' AS raw_location,
  country
FROM unified_sites
WHERE source_id = 'ancient_nerds'
AND raw_data IS NOT NULL
LIMIT 50;
```

If `raw_data` values differ from current DB values, investigate whether the backfill improved or corrupted the data.

### Step 5 — Phase C: Per-site research

For gaps and disputes that Phases A and B couldn't resolve.

| Situation | Tool | Approach |
|-----------|------|----------|
| Site with no Wikipedia URL | **WebSearch** | Search for "[site name] archaeological site" and find authoritative sources |
| Disputed period dates | **Consensus** or **Scholar Gateway** | Search academic papers for dating consensus — e.g., "dating of [site name]" |
| Unknown site type | **WebSearch** + Claude's knowledge | Search for site description, classify based on function |
| Missing country | `lookup_country(lat, lon)` | Reverse geocode from coordinates (function at `pipeline/utils/country_lookup.py:271`) |
| Missing period_start for well-known site | Claude's knowledge | Most famous archaeological sites have unambiguous dates — use them |
| Missing period_start for obscure site | **WebSearch** → **Consensus** if uncertain | Search progressively more specific sources |

**Per-site research rules:**
1. For each site, spend at most 2-3 tool calls. If the answer isn't clear, classify as MANUAL.
2. Cross-reference at least two sources for medium-confidence fixes.
3. High-confidence fixes require universally agreed facts or multiple authoritative sources.

**Parallel research:** For large batches (>30 sites), split into groups of ~60 and launch parallel research agents. Each agent independently web-searches its batch and returns SQL UPDATE statements. Consolidate results after all agents complete. This reduces a 300-site research phase from hours to ~20 minutes.

**Batch research output format:** Each research batch should produce:
- SQL UPDATE statements (one per fix)
- `-- MANUAL:` comment lines for unfixable sites (with reason)
- Summary count: N fixed, M manual, K already correct

### Step 6 — Classify all findings

Every finding from Phases A, B, and C gets one of three confidence levels:

| Confidence | Criteria | Action |
|------------|----------|--------|
| **High** | Universally agreed fact, multiple authoritative sources, or obvious data error (e.g., Stonehenge period_start = 2023) | Auto-apply |
| **Medium** | Scholarly consensus exists but some ambiguity (e.g., Baalbek — Bronze Age tell vs Roman temple) | Present to user for approval |
| **Low** | Genuinely disputed, requires specialist knowledge, or insufficient evidence | Flag as MANUAL |

Additionally, classify unfixable items:

| Classification | Meaning | Report section |
|----------------|---------|----------------|
| **MANUAL_FIX** | Claude identified the likely correct value but confidence is too low to auto-apply | MANUAL FIXES REQUIRED |
| **MANUAL_RESEARCH** | Claude couldn't determine the value — needs human expert or deeper research | MANUAL FIXES REQUIRED |

### Step 7 — Present findings report

Output using the Report Format (see below). Group findings by phase and confidence level. **Wait for user approval before proceeding to Step 8.**

### Step 8 — Apply approved fixes

**Rule: Every audit UPDATE must include `edited_by = 'audit'`.** This marks the row as audit-touched, distinguishing it from untouched rows (`edited_by = 'initial'`) and user edits (`edited_by = 'admin'`). Omitting this makes future audits unable to tell which rows were already reviewed.

For each approved fix, UPDATE the local database and log the change:
```sql
-- Fix the field (always include edited_by = 'audit')
UPDATE unified_sites SET period_start = -9500, period_name = '< 4500 BC', edited_by = 'audit'
WHERE id = '<site-uuid>';

-- Log the fix
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source)
VALUES ('<site-uuid>', 'Gobekli Tepe', 'fix', 'period_start', NULL, '-9500', 'high',
        'Wikipedia, UNESCO — earliest known temple, c. 9500 BC');
```

For verified-correct sites, mark as audit-verified and log:
```sql
-- Mark as reviewed even if no value changed
UPDATE unified_sites SET edited_by = 'audit'
WHERE id = '<site-uuid>' AND edited_by = 'initial';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source)
VALUES ('<site-uuid>', 'Gobekli Tepe', 'verify', NULL, NULL, NULL, 'high',
        'Wikidata P625/P17/P31 match DB values');
```

For unfixable items, log the flag:
```sql
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source)
VALUES ('<site-uuid>', 'Obscure Mound', 'flag_manual', 'period_start', NULL, NULL, 'low',
        'No academic sources found. WebSearch returned only tourism blogs.');
```

> **Log BEFORE or track old values:** When bulk-updating a column, a post-update WHERE clause (e.g., `site_type = 'monument'`) will match both previously-canonical rows AND newly-fixed rows, causing overcounts. Either: (a) INSERT audit log entries BEFORE applying the UPDATE, or (b) use `UPDATE ... RETURNING` to capture exactly which rows changed, or (c) use a subquery with the old value. Never INSERT audit logs after the UPDATE using the same WHERE clause as the UPDATE.

Also append each UPDATE statement to `database_fixes.sql` (for VPS sync later).

### Step 9 — Re-export static JSON

After all fixes are applied to the local DB:
```bash
python -m pipeline.static_exporter --sites-only
```

This regenerates `public/data/sites/index.json`, all `details/{region}.json` files, and their `.gz` counterparts.

### Step 10 — Verify fixes

Run spot-check queries on the fixed sites to confirm values landed correctly in both the DB and the re-exported JSON. Re-run the quality gate query (see Quality Gate below) to measure progress.

**Sentinel check (after Phase A):** Before proceeding to Phase C research, spot-check 3-5 well-known sites from the fixed set against their expected values. If a famous site's period is wrong (e.g., a 10th-millennium BC site showing as 500 BC), there is likely a **systematic parser failure** affecting hundreds of sites. Stop and investigate the pattern before continuing.

### Step 11 — Final report

Output the final report with:
1. **Quality gate status** — all conditions must PASS or have MANUAL items accounted for
2. **MANUAL FIXES REQUIRED section** — every item that couldn't be auto-fixed
3. **Resumability info** — which tiers are complete, where to pick up next session
4. **MANUAL sites CSV export** — Export all MANUAL-flagged sites to a CSV file (`manual_sites.csv`) with columns: `id, name, site_type, country, source_url, comment`. The comment column should explain per-site why auto-fix failed (e.g., "Museum, not archaeological site", "No English-language sources", "Pseudoarchaeology — scientific consensus says natural formation"). This file is the handoff artifact for human researchers.

---

## After the Audit

1. **Push:** `git add public/data/sites/ && git commit && git push` deploys fixed data.
2. **Sync VPS DB:** Apply the generated SQL to the VPS database so the next static export doesn't overwrite fixes:
   ```bash
   ssh root@<vps>
   cat database_fixes.sql | docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map
   ```

If the VPS DB is not synced and someone re-runs the static exporter on VPS, it will overwrite the local fixes with unfixed DB values.

### SQL file conventions

- **Block structure:** Organize `database_fixes.sql` into numbered blocks with headers:
  ```sql
  -- ============================================================
  -- Block N: [Description] ([count] fixes)
  -- Applied: [date]
  -- ============================================================
  ```
- **Conditional WHERE clauses (MANDATORY):** Always include the current (wrong) value in the WHERE clause. This prevents both double-application AND overwriting user edits made via db.html:
  ```sql
  -- GOOD: Won't fire if the value was already corrected (by audit OR user)
  UPDATE unified_sites SET period_start = -9000 WHERE id = '<uuid>' AND period_start IS NULL;

  -- GOOD: Multiple acceptable "old" values
  UPDATE unified_sites SET country = 'Greece'
  WHERE id = '<uuid>' AND (country IS NULL OR country = 'Unknown');

  -- BAD: Blindly overwrites — destroys user corrections
  UPDATE unified_sites SET period_start = -9000 WHERE id = '<uuid>';
  ```
- **File-based execution for large batches:** Heredocs hit OS limits (ENAMETOOLONG) for >100 statements. Always write SQL to a file and pipe it in:
  ```bash
  # GOOD: file-based
  docker cp fixes.sql ancient_nerds_db:/tmp/fixes.sql
  docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map < fixes.sql

  # BAD: heredoc for large batches
  docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map <<'EOF'
  ... 500 statements ...
  EOF
  ```
- **psql in docker exec:** Use `<>` instead of `!=` for inequality comparisons — bash can interfere with `!` in some quoting contexts.

**Windows notes:**
- `docker cp` + `psql -f` can fail silently. Prefer piping: `cat file.sql | docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map`
- Set `PYTHONIOENCODING=utf-8` before running Python scripts with Unicode output
- Static exporter: use `--output` with absolute path (relative paths fail intermittently on Windows)
- `gzip.open()` needs `str()` conversion for `Path` objects on Windows

---

## Audit Dimensions

| Code | Dimension | Key checks |
|------|-----------|------------|
| D1-PERIOD | Period accuracy | `period_start` historically correct; `period_name` matches `categorize_period(period_start)`; not a museum opening, discovery, or renovation date |
| D2-TYPE | Site type accuracy | In valid types list; reflects original function not current state; "Ruin"/"Archaeological Site" never overwrites a more specific type |
| D3-LOCATION | Location accuracy | Coords in correct country; not in ocean; country is modern name not historical polity |
| D4-NAME | Name quality | No "Name, Country" suffixes; no encoding artifacts; consistent English naming; no whitespace issues |
| D5-PARENT | Parent links | No self-refs or circular refs; semantically correct (part-of not "near"); parent exists in DB. **Skip if `parent_site_id` column not yet migrated.** |
| D6-DUPES | Duplicates | Same `name_normalized` across sources; spatial proximity <1km with similar name |
| D7-COMPLETE | Completeness | Missing description, source_url, thumbnail_url |
| D8-URL | Source URLs | Not 404; about THIS site not a generic list |

---

## Valid Site Types

Canonical site types are defined in **two places that must stay in sync**:

| Source of truth | File | What it defines |
|----------------|------|-----------------|
| Python normalizer | `pipeline/normalizers/site_type.py` — `CANONICAL_TYPES` list | All valid DB values + synonym mappings |
| Frontend colors | `ancient-nerds-map/src/constants/colors.ts` — `CATEGORY_COLORS` keys | All valid display values + colors |

**Do NOT hardcode a type list in this document.** Always reference the canonical sources above. If you add a type to one, add it to the other.

The canonical types include both simple forms (`city`, `temple`, `cave`) and compound forms from structured sources (`City/town/settlement`, `Fortress/citadel`, `Necropolis/tombs complex`, `Cave Structures, Rock art`). Both are valid — the frontend groups them via `CATEGORY_GROUPS`.

**Normalization rules** (`normalize_site_type()` in `pipeline/normalizers/site_type.py`):
1. Case-insensitive + underscore/space-insensitive lookup against CANONICAL_TYPES
2. First match wins — lowercase forms (`monument`) take priority over title-case (`Monument`)
3. Synonym resolution — `ruins` → `ruin`, `mausoleum` → `tomb`, `hillfort` → `fort`, etc.
4. Unknown input → pass-through as-is (no guessing, no title-casing)

**Frontend normalization** (`normalizeSiteType()` in `ancient-nerds-map/src/constants/colors.ts`):
- Mirrors the Python normalizer at the data load layer
- Ensures any variant that slips past the backend still displays correctly
- Applied in `src/data/sites.ts` when mapping API data to UI models

---

## Priority Tiers

Used in Step 2 to order the work queue.

| Tier | Criteria | Query |
|------|----------|-------|
| P1 | `period_start > 1500` + non-museum type — likely Wikidata false positives | `WHERE period_start > 1500 AND site_type NOT IN ('museum', 'Museum', 'geological interest') AND site_type NOT ILIKE '%museum%'` |
| P2 | `period_start IS NULL` — dots have no color on globe | `WHERE period_start IS NULL` |
| P3 | `site_type IS NULL OR site_type = 'Unknown'` — can't be filtered | `WHERE site_type IS NULL OR site_type = 'Unknown'` |
| P3.5 | Non-canonical `site_type` variants — causes duplicate badges and broken filtering | Compare each distinct `site_type` against `normalize_site_type()` output. Any mismatch is a variant that needs fixing. See Phase A detection query. |
| P4 | `country IS NULL` — can't be filtered by region | `WHERE country IS NULL` |
| P5 | `period_name` inconsistent or non-canonical | Two sub-queries: **(a)** `WHERE period_start IS NOT NULL AND period_name IS NOT NULL AND period_name != CASE WHEN period_start < -4500 THEN '< 4500 BC' WHEN period_start < -3000 THEN '4500 - 3000 BC' WHEN period_start < -1500 THEN '3000 - 1500 BC' WHEN period_start < -500 THEN '1500 - 500 BC' WHEN period_start < 1 THEN '500 BC - 1 AD' WHEN period_start < 500 THEN '1 - 500 AD' WHEN period_start < 1000 THEN '500 - 1000 AD' WHEN period_start < 1500 THEN '1000 - 1500 AD' ELSE '1500+ AD' END` **(b)** Non-canonical labels or orphan period_name: `WHERE period_name IS NOT NULL AND period_name NOT IN ('< 4500 BC','4500 - 3000 BC','3000 - 1500 BC','1500 - 500 BC','500 BC - 1 AD','1 - 500 AD','500 - 1000 AD','1000 - 1500 AD','1500+ AD')` |
| P6 | Duplicate candidates — same `name_normalized` across sources, or <1km apart | `SELECT name_normalized, COUNT(*) FROM unified_sites GROUP BY name_normalized HAVING COUNT(*) > 1` |
| P7 | Random 5% spot-check of "complete" sites | `WHERE period_start IS NOT NULL AND site_type IS NOT NULL AND country IS NOT NULL ORDER BY RANDOM() LIMIT ...` |

---

## Anti-Patterns

These are explicit "do NOT" rules. Violating any of these was the problem with the batch backfill script.

1. **Do NOT batch-apply Wikidata claims without per-site review.** Wikidata inception dates are often discovery/excavation/renovation dates, not historical period dates. This is the core failure mode of `scripts/backfill_parent_sites.py` lines 402-421.
2. **Do NOT use "Ruin" or "Archaeological Site" to replace more specific types.** If a site is typed "Temple", it stays "Temple" even though it's technically a ruin today. The backfill script (lines 424-434) falls into this trap via P31.
3. **Do NOT use museum/discovery/renovation dates as `period_start`.** The year Schliemann excavated Troy (1870) is not Troy's period. When a source gives a date, ask: "Is this when the site was BUILT/ACTIVE, or when it was FOUND/RESTORED?"
4. **Do NOT auto-fix coordinates.** Flag for manual review unless the error is extreme (wrong continent, in the ocean).
5. **Do NOT guess when uncertain.** An empty `period_start` is better than a wrong one. Leave it NULL and classify as MANUAL_RESEARCH.
6. **Do NOT trust a single source blindly.** Cross-reference at least two sources for medium-confidence fixes. High-confidence fixes require universally agreed facts.
7. **Do NOT use historical country names.** Use current UN-recognized names (e.g., "Turkey" not "Anatolia", "Iraq" not "Mesopotamia", "Greece" not "Hellas").
8. **Do NOT fix `period_name` independently of `period_start`.** Always keep them consistent via `categorize_period()`. Fix `period_start` and derive `period_name`.
9. **Do NOT downgrade site_type specificity.** If Wikidata P31 says "archaeological site" but the DB has "Temple", keep "Temple".
10. **Do NOT skip the raw_data cross-reference.** The `raw_data` JSONB column contains original source data. If a backfill changed a value, compare against raw_data to determine if the change was an improvement or corruption.
11. **Do NOT trust `raw_period` when `raw_year` exists.** The `raw_data->>'period'` field is a pre-computed bucket label from the original source. It is frequently WRONG — especially when the raw_year uses formats the source's own parser couldn't handle (e.g., millennium patterns). Always parse `raw_year` first; only fall back to `raw_period` when `raw_year` is NULL.
12. **Do NOT modify sites from sources outside the audit scope.** A `source <id>` or `full` audit of `ancient_nerds` must NEVER touch sites from `lyra`, `pleiades`, `wikidata`, etc. Always include `AND source_id = '<target>'` in every UPDATE and INSERT statement. Forgetting this filter can corrupt curated academic data.
13. **Do NOT write raw strings for `site_type` — always run through `normalize_site_type()`.** Every ingestion path (connectors, API PUT, manual SQL) must normalize before writing. If you find non-canonical variants in the DB (`rock_art` instead of `Rock art`, `Monument` instead of `monument`), fix them AND find which ingestion path skipped normalization. Fixing the data without fixing the source is fighting symptoms — the variants will return on the next import.
14. **Do NOT overwrite user-edited values without a conditional WHERE clause.** Every audit UPDATE must include the expected current (wrong) value in the WHERE clause — e.g., `WHERE id = '<uuid>' AND country IS NULL` instead of just `WHERE id = '<uuid>'`. If a user corrected a field via db.html and the audit proposes a different value, that's a conflict — flag it as MANUAL_FIX, don't silently overwrite. See "Protecting User Edits" section above.
15. **Do NOT add a site type to one canonical source without the other.** `CANONICAL_TYPES` in `pipeline/normalizers/site_type.py` and `CATEGORY_COLORS` in `ancient-nerds-map/src/constants/colors.ts` must stay in sync. A type that exists in the DB but not in `CATEGORY_COLORS` will render with the default gray color. A type in `CATEGORY_COLORS` but not in `CANONICAL_TYPES` won't be normalized and can drift into variants.

---

## Quality Gate

The audit targets **100% coverage** for all fields. The audit passes when all conditions are met for the audited scope — any remaining gaps must have corresponding MANUAL entries in the report.

| Condition | Target |
|-----------|--------|
| Period coverage (`period_start IS NOT NULL` OR flagged MANUAL) | 100% |
| Type coverage (`site_type` valid and not 'Unknown' OR flagged MANUAL) | 100% |
| Country coverage (`country IS NOT NULL` OR flagged MANUAL) | 100% |
| `period_name` ↔ `period_start` consistency | 100% |
| No self-referencing `parent_site_id` *(skip if column not migrated)* | 0 |
| No orphan parent references *(skip if column not migrated)* | 0 |
| No same-source duplicates | 0 |
| All `site_type` values in valid list | 100% |
| All `site_type` values in canonical form (no case/underscore/synonym variants) | 0 non-canonical |
| P1 critical findings remaining | 0 |

"100%" means every site is either **fixed**, **verified correct**, or **flagged MANUAL** in the audit log. No site should be left unaccounted for in the audited scope.

Quality gate query:
```sql
SELECT
  COUNT(*) AS total,
  ROUND(100.0 * COUNT(*) FILTER (WHERE period_start IS NOT NULL) / COUNT(*), 1) AS period_pct,
  ROUND(100.0 * COUNT(*) FILTER (WHERE site_type IS NOT NULL AND site_type NOT ILIKE 'Unknown') / COUNT(*), 1) AS type_pct,
  ROUND(100.0 * COUNT(*) FILTER (WHERE country IS NOT NULL) / COUNT(*), 1) AS country_pct,
  COUNT(*) FILTER (WHERE period_start > 1500
    AND site_type NOT IN ('museum', 'Museum', 'geological interest')
    AND site_type NOT ILIKE '%museum%'
  ) AS suspect_modern
FROM unified_sites;

-- Parent link checks (only if parent_site_id column exists — see note in Phase A)
-- SELECT COUNT(*) FILTER (WHERE parent_site_id = id) AS self_refs FROM unified_sites;
-- SELECT COUNT(*) FROM unified_sites s
-- LEFT JOIN unified_sites p ON s.parent_site_id = p.id
-- WHERE s.parent_site_id IS NOT NULL AND p.id IS NULL;

-- Same-source duplicates
SELECT source_id, name_normalized, COUNT(*)
FROM unified_sites
GROUP BY source_id, name_normalized
HAVING COUNT(*) > 1;

-- MANUAL items accounted for
SELECT
  COUNT(*) FILTER (WHERE action = 'flag_manual' AND field_changed = 'period_start') AS manual_period,
  COUNT(*) FILTER (WHERE action = 'flag_manual' AND field_changed = 'site_type') AS manual_type,
  COUNT(*) FILTER (WHERE action = 'flag_manual' AND field_changed = 'country') AS manual_country
FROM database_audit_log;
```

The gate passes when: `period_pct + (manual_period / total * 100) = 100%` and likewise for type and country.

---

## Utility References

Normalization functions — audit values must be consistent with their output.

| Function | File | Line |
|----------|------|------|
| `categorize_period(year)` | `pipeline/utils/text.py` | 219 |
| `normalize_site_type(type)` | `pipeline/normalizers/site_type.py` | 120 |
| `normalize_name(name)` | `pipeline/utils/text.py` | 7 |
| `normalize_country(country)` | `pipeline/utils/country_lookup.py` | 532 |
| `lookup_country(lat, lon)` | `pipeline/utils/country_lookup.py` | 271 |

### Reusable Audit Scripts

Scripts generated by previous audits — reuse these instead of writing from scratch.

| Script | Purpose | Usage |
|--------|---------|-------|
| `wikidata_verify.py` | Batch Wikipedia→QID resolution + Wikidata claims fetch + discrepancy detection | `PYTHONIOENCODING=utf-8 python wikidata_verify.py` |
| `analyze_discrepancies.py` | Classify period discrepancies against raw_data | Reads `wikidata_results.json`, outputs `discrepancy_analysis.json` |
| `generate_fixes.py` | Generate SQL from classified discrepancies | Reads `wikidata_results.json` + DB, outputs `phase_b_fixes.sql` |

These scripts live in the project root. Check if they exist before writing new ones — they may need minor updates for a new source or scope but the core logic is reusable.

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

> **Boundary trap:** `categorize_period()` uses strict `<`, so boundary values fall into the NEXT bucket: `-3000` → "3000 - 1500 BC" (not "4500 - 3000 BC"), `500` → "500 - 1000 AD" (not "1 - 500 AD"), `1000` → "1000 - 1500 AD" (not "500 - 1000 AD"). Always verify `period_name` after setting `period_start` to a boundary value.

---

## Database Schema Reference

The `unified_sites` table (`pipeline/database.py:390`):

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary key |
| `source_id` | String(50) | Which source loaded this site |
| `source_record_id` | String(255) | Original ID from source |
| `name` | String(500) | Display name |
| `name_normalized` | String(500) | Lowercase, stripped, for dedup/search |
| `lat` / `lon` | Float | WGS84 coordinates |
| `geom` | PostGIS POINT | Spatial geometry (auto-derived) |
| `h3_index` | String(20) | H3 spatial index cell |
| `site_type` | String(100) | Classification |
| `period_start` / `period_end` | Integer | Year (negative = BC) |
| `period_name` | String(100) | Human-readable period label |
| `country` | String(100) | Modern country name |
| `description` | Text | Full description |
| `thumbnail_url` | Text | Image URL |
| `source_url` | Text | Link to source page |
| `raw_data` | JSONB | Original source data — **always cross-reference during audit** |
| `created_at` | DateTime | Row creation timestamp |
| `parent_site_id` | UUID FK → self | **MODEL ONLY — not yet migrated to DB.** Hierarchy (e.g., Sphinx → Giza). Exists in SQLAlchemy model (`database.py:440`) but `CREATE TABLE` doesn't add columns to existing tables. Check `information_schema.columns` before using. |

The `user_contributions` table (`pipeline/database.py:669`):

| Column | Type | Notes |
|--------|------|-------|
| `enrichment_status` | String(20) | Lifecycle: pending → enriched → promoted |
| `enrichment_data` | JSONB | Wikidata/Wikipedia/GeoNames enrichment results |
| `wikidata_id` | String | Wikidata QID if resolved |
| `wikipedia_url` | String | Wikipedia article URL if found |

Unique constraint on unified_sites: `(source_id, source_record_id)`.

---

## Useful Queries

```sql
-- Get a site's full record including raw_data
SELECT id, name, site_type, period_start, period_name, country, lat, lon,
       source_id, source_url, raw_data
FROM unified_sites WHERE name ILIKE '%site name%';

-- Check parent link validity (only if parent_site_id column exists)
-- SELECT s.id, s.name, s.parent_site_id, p.name AS parent_name
-- FROM unified_sites s
-- LEFT JOIN unified_sites p ON s.parent_site_id = p.id
-- WHERE s.parent_site_id IS NOT NULL AND p.id IS NULL;

-- Self-referencing parents (only if parent_site_id column exists)
-- SELECT id, name FROM unified_sites WHERE parent_site_id = id;

-- Find duplicates by normalized name
SELECT name_normalized, array_agg(DISTINCT source_id), COUNT(*)
FROM unified_sites
GROUP BY name_normalized
HAVING COUNT(*) > 1
ORDER BY COUNT(*) DESC;

-- Sites with suspect modern dates (excludes museums and geological sites)
SELECT name, site_type, period_start, source_id
FROM unified_sites
WHERE period_start > 1500
AND site_type NOT IN ('museum', 'Museum', 'geological interest')
AND site_type NOT ILIKE '%museum%'
ORDER BY period_start DESC;

-- Audit progress: what's been verified/fixed this session
SELECT action, COUNT(*), MAX(changed_at)
FROM database_audit_log
GROUP BY action;

-- Sites NOT yet audited (for resumability)
SELECT u.id, u.name, u.source_id
FROM unified_sites u
LEFT JOIN database_audit_log a ON u.id = a.site_id
WHERE a.id IS NULL
AND u.period_start IS NULL  -- example: find un-audited sites with no period
LIMIT 50;
```

---

## Report Format

```markdown
# Database Audit Report — [mode] — [YYYY-MM-DD]

## Inventory

| Source | Total | No Period | No Type | No Country | Suspect Modern |
|--------|-------|-----------|---------|------------|----------------|
| ... | ... | ... | ... | ... | ... |
| **Total** | **N** | **N** | **N** | **N** | **N** |

## Batch Progress

Audited: X / Y sites (Z%)
Session: [sites covered this session]
Previously verified (from audit log): N sites skipped

## Phase A — Mechanical Fixes

| Site | Field | Old Value | New Value | Rule |
|------|-------|-----------|-----------|------|
| Site Name | period_name | "Bronze Age" | "3000 - 1500 BC" | categorize_period(period_start) |

Applied: N fixes

## Phase B — Wikidata/Wikipedia Verification

### Confirmed correct (no change needed)

N sites verified against Wikidata — DB values match.

### Discrepancies found

| Site | Field | DB Value | Wikidata Value | Assessment | Confidence |
|------|-------|----------|----------------|------------|------------|
| Troy | period_start | -3000 | 1870 | Reject — 1870 is Schliemann's excavation date | high |
| Unknown Ruin | country | NULL | "Greece" | Accept — P17 matches coordinates | high |

## Phase C — Per-Site Research

### High Confidence (auto-apply)

| Site | Field | Current | Proposed | Evidence |
|------|-------|---------|----------|----------|
| Gobekli Tepe | period_start | NULL | -9500 | Wikipedia, UNESCO — earliest known temple, c. 9500 BC |

### Medium Confidence (user review required)

| Site | Field | Current | Proposed | Evidence | Notes |
|------|-------|---------|----------|----------|-------|
| Baalbek | period_start | 1000 | -2900 | Tell beneath Roman temple ~2900 BC (Marfoe 1998) | Could argue 15 BC for Roman construction |

## Quality Gate: PASS / FAIL

| Condition | Result | Value |
|-----------|--------|-------|
| Period coverage (filled + MANUAL) = 100% | PASS/FAIL | X% filled, N flagged MANUAL |
| Type coverage (filled + MANUAL) = 100% | PASS/FAIL | X% filled, N flagged MANUAL |
| Country coverage (filled + MANUAL) = 100% | PASS/FAIL | X% filled, N flagged MANUAL |
| period_name consistency | PASS/FAIL | X% |
| P1 suspect modern = 0 | PASS/FAIL | N |

## Changes Applied

| Site | Field | Old | New | Confidence |
|------|-------|-----|-----|------------|
| ... | ... | ... | ... | ... |

All changes logged in `database_audit_log` table.
SQL migration written to `database_fixes.sql`.

## MANUAL FIXES REQUIRED

Items that could not be auto-fixed. Each needs human research or expert judgment.

### MANUAL_FIX (likely value identified, low confidence)

| Site | UUID | Field | Current | Suggested | Why not auto-applied | Suggested research |
|------|------|-------|---------|-----------|---------------------|--------------------|
| Obscure Temple | abc-123 | period_start | NULL | -500 | Only one blog source found | Search JSTOR for "[site name] dating" |

### MANUAL_RESEARCH (no value determined)

| Site | UUID | Field | Current | What was tried | Suggested next step |
|------|------|-------|---------|----------------|---------------------|
| Unknown Mound | def-456 | period_start | NULL | WebSearch, Consensus — no results | Contact regional archaeology department |

## Next Steps

- Remaining P1 sites: N
- Remaining P2 sites: N
- Total MANUAL items: N (M fixes, R research)
- Resume from: [last site audited or tier]
- Verified sites (skip next run): N
```

---

## Lessons Learned

Dated notes from past audits. Read these before starting a new audit — they capture operational surprises the framework didn't originally account for.

### Feb 2026 — First full `ancient_nerds` audit (5,005 sites)

**Scale surprises:**
- Framework estimated ~65 non-canonical types. Actual: **4,791** — almost all compound type capitalizations (`city/town/settlement` → `City/town/settlement`). The compound capitalization pattern was not in the original framework.
- 212 sites had `period_start` set from `raw_period` instead of `raw_year`. Re-parsing `raw_year` was the biggest single Phase A win after type normalization.
- Only 4 genuine country errors out of 99 Wikidata discrepancies (~4%). The rest were historical names, naming variants, or Wikidata being wrong.

**Operational failures (Windows/Docker):**
- `docker cp` + `psql -f` silently failed. Piping via `cat file.sql | docker exec -i` works reliably.
- Python scripts with Unicode site names crashed without `PYTHONIOENCODING=utf-8`.
- `gzip.open()` on Windows needs `str()` for `Path` objects.

**Parser lessons:**
- The `raw_period` → `period_start` mis-parse affected sites using millennium/century notation: "9th c. AD" was parsed as `-9000` instead of `800`. Always parse `raw_year` first.
- `categorize_period()` boundary values caused 3 separate errors: `-3000` falls into "3000 - 1500 BC", not "4500 - 3000 BC".

**Phase C research results:**
- 12/42 missing-period sites found dates via web research
- 16/42 were non-archaeological (museums, pseudoarchaeology, wildlife sanctuaries)
- 14/42 genuinely unfindable — flagged MANUAL

**Audit log gotcha:**
- Type normalization logged 4,791 fixes but initially overcounted because the post-UPDATE WHERE clause matched both already-canonical and newly-fixed rows. Always log BEFORE the UPDATE or use `RETURNING`.
