# Curated Sites Database — Assessment and Remediation Plan

**Date:** 2026-09-19 · **Status:** assessment complete, remediation not started
**Scope:** the 5,004 sites with `source_id = 'ancient_nerds'` in the production database
**Basis:** two autonomous multi-agent runs, 59 agents, 6.9M tokens, 2 h wall clock

---

## 0. Instructions for the implementing model

This document is written to be executable **without the conversation that produced it**.

Working rules:

1. **Every number here was measured, not estimated.** Where something is an assumption, it says so.
   If a measurement contradicts your own fresh observation, trust your measurement — but document the
   discrepancy instead of silently overwriting it.
2. **The two-stage review is not optional.** In the pilot, 140 error claims were raised and **86 of them
   (61 %) were refuted by an independent second reviewer.** A single-stage run would have caused more damage
   than it repaired. The faster and cheaper the model in use, the more important this stage becomes.
3. **Evidence is mandatory.** Without a verifiable source the verdict is `unverifiable`, never `wrong`.
   An empty field beats a wrong one. See `docs/procedures/ENRICHMENT_AUDIT.md`, section "Anti-Patterns".
4. **Conditional WHERE clauses are mandatory** on every `UPDATE`. The old (wrong) value must appear in the
   condition so that manual corrections made in the meantime are not clobbered.
5. **No `DELETE`.** Out-of-scope sites are flagged and hidden, never deleted.

Related documents: `docs/procedures/ENRICHMENT_AUDIT.md` (procedure, anti-patterns, canonical types),
`docs/procedures/CARD_DESCRIPTIONS.md` (card-text generation spec), `CLAUDE.md` (project rules).

---

## 1. Mandate and binding decisions

### 1.1 Why this project exists

A public short-form video ("site short") with spoken narration is to be generated for **every** one of the
5,004 curated sites. That means every data error gets **read aloud and published**. The bar moves from
"good enough for a map pin" to **"sourced or absent"**.

### 1.2 Owner decisions, 2026-09-19 (binding)

| # | Topic | Decision |
|---|---|---|
| E1 | Write access | The audit **may** apply confirmed fixes. Preconditions: backup + snapshot first, conditional WHERE clauses, change journal as a file. No `DELETE`. No bulk rewrite of descriptions without separate approval. |
| E2 | Coverage | **All 5,004 sites**, two-stage (finder + adversarial reviewer). |
| E3 | Scope | Museums stay **if they exhibit ancient material**. Cutoff: **Americas through 1500 AD, rest of world through 500 AD.** Since O7 (owner, 2026-09-26: "Ozeanien wie Amerika") **Oceania through 1500 AD** like the Americas - the one coded rule is `pipeline/normalizers/dates.py` (`e3_region`, `passes_date_cutoff`), its SQL `mechanical/lane.py` (`outside_e3_window`); runbook `WD2_SERVED_IMAGE_AND_SCOPE.md`. |
| E4 | Out-of-scope handling | **Flag it AND hide it platform-wide.** A new column for this is approved — but only during implementation, not during assessment. |
| E5 | Card texts | Deferred to the end: review them once the rest of the database is 100 % clean. *(See section 5 — this finding arrived after the decision and should reopen it.)* |
| E6 | MiniMax | **Not** for the audit. **Explicitly approved for the VLM image scan**, and free to use in live operation later. |
| E7 | Code | **No code changes during assessment** — a parallel session is working in the repo. Lifted for implementation. |

### 1.3 Definition of "clean"

A site counts as clean when **all** of the following hold:

- Every shipped field is either confirmed against at least two independent sources, or empty.
- The description carries `[N]` markers, and every marker has an entry in `raw_data->description_citations`.
- The card text (the spoken narration) contains no claim absent from the sourced description.
- The site is in scope (E3), or flagged as out of scope and hidden.
- Every gallery image depicts this site, or is marked `is_excluded`.

---

## 2. Method and evidence base

| Measurement | Method | Sample |
|---|---|---|
| Full census | direct `SELECT` against production | all 5,004 sites, all 49,691 images |
| Error rate | stratified random sample by `rarity_tier`, two-stage | 60 sites, 140 claims |
| Image quality | per-image agent verdict against title, filename, Commons page | 652 images across 40 sites |
| Signal strength | precision/recall against the labelled image set | 652 images |
| Wikidata coverage | 300 random QIDs, 291 resolved, field-by-field comparison | 291 sites |
| Card-text grounding | number matching against snapshot `d4526691` (the text state at generation time) | 4,997 card texts |
| Tooling audit | code reading plus adversarial refutation of every reuse claim | 8 building blocks |

**Known weaknesses of this assessment** — account for them when planning:

- The 60-site sample is stratified by `rarity_tier`; tiers 4/5 are over-weighted at 25 % (7.5 % of the
  population). The 53 % figure is **not** inverse-probability weighted.
- **The false-negative rate is unknown.** What was measured is how often stage 1 claims nonsense, not how
  often both stages miss a real error. A gold standard (30–40 double-blind sites) is missing and should be
  established before the full run.
- Image labels were themselves produced by a language model. Ground truth was corrected in run 2
  (65 rather than 45 foreign images), but it is not a human reference.
- 652 labelled images are 1.3 % of the corpus.

**Raw data** (not in git, held locally): `output/audit_inventory/_wf_result.json`, `_wf2_result.json`,
`_kontext.md`, `_labeled_sites.json` (140 findings), `_labeled_images.json` (652 images),
`scripts/_audit_inventory*.sql`, `scripts/_audit_sample.sql`, `scripts/_backup_curated.sh`.

---

## 3. Current state

### 3.1 Field coverage in `unified_sites` (source_id = 'ancient_nerds', n = 5,004)

| Field | State |
|---|---|
| `period_start` | 15 NULL. **75 % (3,753) sit exactly on a bucket lower bound** (−4500/−3000/−1500/−500/1/500/1000/1500) — there the value is a sort key, not a date. Most common value: `1` on 1,133 sites. |
| `period_end` | **NULL on all 5,004.** `passes_date_cutoff()` therefore falls back to `period_start` 100 % of the time. |
| `period_name` | 15 NULL, 1 non-canonical (`> 1500 AD`) |
| `site_type` | 0 NULL, **70 distinct values** with synonyms alongside the canonical form |
| `country` | 0 NULL, **98 distinct**, including broken values: `Georgia (country)` 27, `Chile, Easter Island` 8, `Baltic Sea` 1 |
| `description` | 0 empty, 47–1,096 chars, concentrated at 400–599 |
| `source_url` | 42 missing · 4,689 Wikipedia · 9 fragment URLs · 7 non-http · 1 blog |
| `thumbnail_url` | 988 empty · 2,283 local (`/data/images/wiki/<hash8>/hero.webp`) · 1,709 `upload.wikimedia.org` |
| `parent_site_id` | 0 set, 0 self-references, 0 dangling |
| `last_audited` | 4,997 carry the **same** value `2026-03-14 13:25:43` — a single blanket UPDATE, not an audit status |
| `edited_by` | the uploader's Discord name, not an audit status: `MrSchneebly` 4,974, `audit` 23, `QuetzalcoatlCat` 7 |
| `raw_data` | only key present is `description_citations`, on 2,217 rows. No `year`, no `period`. |
| `h3_index` | 100 % NULL |

### 3.2 Non-canonical `site_type` values (selection; full list via SQL)

`Temple` 6 alongside `Temple complex` 427 · `Fortress` 3 and `Fortification` 7 alongside `Fortress/citadel` 619 ·
`Quarry` 2 alongside `Mine/quarry` 27 · `Palace` 2 alongside `Castle/palace` 43 · `Bridge` 2 and `Road` 1
alongside their compound forms · `Ruin` 1 · `Natural feature` 1 · `suspect_modern` 1 ·
`Archaeological site` 15 · `Geological interest` 39 · `Museum` 51

> **Important:** `normalize_site_type()` is a **no-op** on today's production data — all 93 values were run
> through it, producing 0 changes. Resolving these synonyms requires a **hand-written mapping table**;
> the existing function will not do it.

### 3.3 Adjacent tables

| Table | State | Note |
|---|---|---|
| `card_stats` | 5,004 rows | `card_description` missing on 7 · `confidence_score` missing on 8, 585 below 0.8 |
| `card_stats` enrichment | `wikidata_qid`, `best_wiki_url`, `inception_year`, `last_enriched`, `heritage_designation`, `commons_image` are **NULL on all 5,004** | The columns exist; they were simply never populated |
| `card_stats.civilization` | **== `unified_sites.country` on 5,004 of 5,004** | A copy, not a claim. Drives only the expedition filter (`api/cardgame/expedition.py`), not SEO-visible. **Not an audit target.** |
| `site_external_ids` | **4,618 `wikidata_qid` + 4,619 `enwiki_title`** | The Wikidata anchor exists. 385 sites have no anchor at all. |
| `site_content_links` | 16,029 links across 3,575 sites, all `content_type='reference'`, `content_source='web_discovery'` | **1,429 sites have no reference link at all.** Never checked for HTTP status. |
| `unified_site_names` | exactly 1 row per site, `language_code` empty | no local-language names exist |
| `wiki_images` | 49,691 rows across 4,010 sites, 659 `is_excluded` | 1,677 without `author`, 657 without `license`, 3 without dimensions |

### 3.4 Duplicates

- Name duplicates via `name_normalized`: **0**
- Spatial neighbours < 300 m with name similarity > 0.5: **95 pairs**, mostly genuine sub-sites
  (Kilmartin cairns, Delphi treasuries, Pompeii houses). **Real duplicates ≈ 8**, e.g.
  `Templos de Tarxien` ↔ `Tarxien Temples` (38 m), `Stadium at Nemea` ↔ `Ancient Stadium of Nemea` (24 m),
  `Biniai Nou Hypogea` ↔ `Hipogeo de Biniai nou` (16 m), `Dolmen del prado de Lácara` ↔ `Dolmen de Lácara` (38 m).
- **16 curated sites share a name with another site** (`pipeline/sites_html_renderer.py:30-32`) — relevant
  because the shorts directory name is `slugify(name)` with no suffix.

---

## 4. Measured error rate

Sample: 60 sites, stratified by `rarity_tier`. Method: a finder agent checks every field against sources;
a reviewer then attempts to **refute** each error claim. Only independently confirmed errors count.

| Metric | Value |
|---|---|
| Sites with at least one confirmed error | **32 of 60 (53 %)** |
| Confirmed errors total | 54 — of which **7 severe**, 34 moderate, 13 cosmetic |
| **Refuted first-stage claims** | **86 of 140 (61 %)** |

### 4.1 Distribution by field (claimed / confirmed)

| Field | Claimed | Confirmed | Confirmation rate |
|---|---|---|---|
| `civilization` | 53 | **0** | 0 % — pure false alarm; the field is a copy of `country` |
| `description` | 22 | 15 | 68 % |
| `card_description` | 15 | 10 | 67 % |
| `period_start` | 11 | 9 | 82 % |
| `name` | 11 | 2 | 18 % |
| `site_type` | 10 | 6 | 60 % |
| `period_name` | 6 | 3 | 50 % |
| `coordinates` | 3 | 2 | 67 % |
| `scope` | 3 | 2 | 67 % |
| `country` | 3 | 2 | 67 % |
| `thumbnail_url` | 2 | 2 | 100 % |
| `source_url` | 1 | 1 | 100 % |

**25 of the 54 confirmed errors (46 %) live in `description` and `card_description`** — exactly what gets
read aloud, and exactly where no deterministic test can reach.

### 4.2 Severe confirmed errors (examples, all evidenced)

| Site | Finding |
|---|---|
| Hatunmarka | Card text describes **Choquequirao**, 400 km away |
| Neos Panteleimonas | A 20th-century village carrying `period_start = -1000`; does not belong in an archaeology database |
| El Tintal | Coordinate sits 11–12 km off the actual site (correct: 17.5744 / −89.9958) |
| Kit Hill | Description asserts a hillfort — there is none |
| Justinianopolis (Epirus) | `period_start = -500`, actually 6th c. AD → off by 1,000 years and several buckets |
| Eileithyia Cave | `period_start = -500`, actually in use from the Neolithic |
| Partiscum (Castra) | Description invents a fort in Dacia; it was a settlement / road station |

### 4.3 Correctly refuted false alarms — the reviewer must know these patterns

1. **Bucket boundary values.** `period_start` is a sort key on 75 % of sites. A round value alone is **not**
   an error. Report it only when the real dating belongs in a **different bucket**.
2. **`England` / `Scotland` / `Wales` instead of `United Kingdom`** is deliberate project design.
3. **`Archaeological Site of Olympia`** and similar are not prefix clutter but the official UNESCO title
   (34 sites carry this form).
4. **`civilization`** is a denormalised country copy, not a cultural attribution.
5. **Never downgrade specificity.** If Wikidata P31 says "archaeological site" and the database says "Temple",
   it stays "Temple".
6. **Same-name different site.** Before any verdict, confirm that name **and** coordinate refer to the same place.
7. **The card's only dated claim is the terminus.** Pannonian's card ends "…to the 5th century AD" while its
   bucket `500 BC - 1 AD` covers the *beginning* (Augustus, 31 BC). T03 compares the text's latest year with
   the bucket and calls it `all-outside`/severe. One of the two T03 false alarms in the five-site pilot.
8. **The date belongs to a person, not the site.** Karpasia: 334 BC is Zeno of Citium's birth year, the site
   is 7th-century BC. A date attached to a named person (or to a "most famous resident") is not a dating of
   the site.
9. **Wikidata `P625` is the parent city's or state's coordinate — and it is wrong on Wikipedia itself.**
   Petroglyph Beach: both Wikidata (58.301061/−134.413121) and the Wikipedia article's own `{{Coord}}`
   template carry downtown **Juneau**, 235 km from the beach in Wrangell, and GeoNames reproduces the same
   point, so the error propagates and *looks* corroborated. T01's 235.60 km lead was right about the
   *distance* and wrong about which side was broken.
10. **The item's own precision is an alibi.** Satsurblia: `P625` precision `0.01216°` = 1.35 km, larger than
    the 1.28 km difference T01 flagged. Any distance threshold below the item's own precision is
    unfalsifiable — and nothing in the census output exposes that precision, so a finder cannot apply the
    "do not refute on a sub-precision difference" rule without fetching Wikidata itself.
11. **Natural Earth draws de-facto borders and drops small islands.** Measured over the 117 T02 findings:
    45 open water (real coastline generalisation — Petroglyph's 1.1 km), 22 United Kingdom (points in
    Northern Ireland against the value `Ireland`), 9 Russia (Crimea), 7 Northern Cyprus, 4 "'Northern
    Ireland' matches no Natural Earth admin-0 feature", 2 Akrotiri Sovereign Base Area, 2 Kosovo,
    1 Palestine, 1 Baltic Sea, 17 singles. Pattern 2 explains England/Scotland/Wales (a deliberate
    sub-national vocabulary) but says nothing about `Ireland` vs `Northern Ireland`, the second-largest T02
    class. All three T02 findings in the pilot batch were refuted as data errors.

Patterns 7–11 were measured in the five-site Phase-3 pilot and ratified as part of the Phase-3 decisions of
2026-09-21; the underlying measurements are listed in `output/remediation/phase3_pilot/BRIEF_GAPS.md` §7.

---

## 5. The spoken text — the most serious finding

`card_stats.card_description` is the text a short **reads aloud** (`pipeline/video/__main__.py:328-331`,
`shorts_render.py:860`). It appears on no indexed page, has **no evidence column** (`card_stats` has 23 columns,
none for sources), and has never been verified.

### 5.1 Grounding measurement

Method: every number in the card text checked against the text state the generator was given.
The generator received only `LEFT(us.description, 500)` (`scripts/export_card_sites.py:36`).
Reference: full snapshot `d4526691` of 2026-03-05.

| Cohort | Count | Meaning |
|---|---|---|
| Number **never** appeared in the 500-char input | **904** | ungrounded — model memory or fabrication |
| Number was sourced, no longer present in today's description | 1,225 | the March truncation removed the evidence |
| Still checkable against its own description today | 1,925 | |
| Card text contains no number at all | 943 | not reachable by this method |

Evidenced examples from the 904: *"House of Taga … from a site occupied as early as 10,000 BC"* (the Marianas
were settled around 1500 BC) · *"Hatunmarka … below Choquequirao, above the Apurímac gorge"* (identical to the
independently confirmed wrong-site error) · *"Maray Qalla … Inca road system that stretched over 30,000 km"*.

### 5.2 The generation spec permits invention

`docs/procedures/CARD_DESCRIPTIONS.md` (commit `c677f3b`), Tone & Style Guide:
> *"If the wiki excerpt is empty/missing, write a brief factual description based on the site name, type, and period."*

### 5.3 The QA tool made it worse

`scripts/verify_descriptions.py` checks **no facts at all**. It counts repeated openers (`:190-197`),
overused 4-grams (`:221-230`) and length (`:371-373`). And it **penalises hedging**:
`HEDGING_PATTERNS:126-143` lists `"it is believed"`, `"it is thought"`, `"thought to be"`, `"possibly"`,
`"probably"`, `"some scholars"`.

**Commit `6c85da0` rewrote 1,107 descriptions on that basis.** The tool meant to ensure quality converted
hedged statements into confident ones.

**Action:** retire the script as a quality gate rather than repairing it. The 1,107 affected texts are
identifiable via git (diff `card_descriptions.json` against its predecessor).

### 5.4 Consequence for decision E5

E5 defers card texts to the end. This finding arrived **after** that decision. For reconsideration:
the card text is the **only** field that gets read aloud, and the **least verified** field in the database.
Recommendation: reverse E5 and fold the card text into the same run — it then becomes an **extractive
condensation of an already-sourced description sentence** rather than a second free generation. That is
cheaper than a separate pass and removes the error source at the root.

---

## 6. Images

### 6.1 Quality (652 labelled images across 40 sites)

| Metric | Value |
|---|---|
| Usable photographs of **this** site | **63.5 %** |
| Images showing a **different** site | **10.0 % (65)** — corrected ground truth |
| Problem classes | too small 84 · foreign site 65 · duplicate 36 · painting/drawing 23 · map/plan 22 · diagram/text 19 · missing attribution 17 · modern surroundings 13 |

**The structural effect the algorithm rests on: contamination clusters by site.**
**54 of the 65 foreign images sit in 6 of 40 sites.** Ishtar Gate 16/20 · La Cobata 15/20 ·
Castell Bryn Gwyn 7/11 · Overton Hill 6/10 · Puma Punku 5/19 · Kerbatch 5/8.
It follows that **per-site sampling works** — one hit exposes the whole gallery.

### 6.2 Root cause

`pipeline/wiki_image_downloader.py` pulls **every** image in the Wikipedia media list, plus Wikidata
P18/P3451/P4291/P5775, plus up to 20 files from the Commons category P373 including one subcategory level.
**No content relevance check exists anywhere.** The only filter is a filename regex against icons/logos/flags
(`:79-89`).

Furthermore, the production corpus did **not** come from this downloader: all 49,693 rows have
`thumb_width IS NULL` (the downloader always sets it), `source_type` is `wikimedia`/`manual` rather than
`wikipedia`/`commons_category`/`wikidata_p18`, and 49,687 rows carry `created_at = 2026-03-14`. The shape
matches `scripts/reindex_wiki_images.py` (re-indexes files from disk: `is_lead = is_hero`, alphabetical
`sort_order`, `original_url` = local path).
**The original importer no longer exists in the repo** (`pipeline/image_attribution_backfill.py:5-8`).

There is **no field and no concept for image kind** (photo / painting / map / diagram).

### 6.3 Every hero image is broken — full census, not a sample

```sql
SELECT count(*) AS heroes,
       count(*) FILTER (WHERE width = 800)               AS width_exactly_800,
       count(*) FILTER (WHERE least(width,height) < 900) AS short_side_under_900,
       count(*) FILTER (WHERE height < 400)              AS strips,
       round(avg(width)) AS avg_w, round(avg(height)) AS avg_h
FROM wiki_images w JOIN unified_sites u ON u.id = w.site_id
WHERE u.source_id = 'ancient_nerds' AND w.is_hero;
-- heroes 3858 | width_exactly_800 3850 | short_side_under_900 3858 | strips 914 | 800 x 498
```

Two causes: `THUMB_WIDTH = 800` (`pipeline/wiki_image_downloader.py:47` — fetches an 800 px Commons thumbnail
directly, so **the original never lands on disk**) and `HERO_WIDTH = 800`
(`api/routes/wiki_images.py:22`, PIL resize + WEBP q82).

Examples: Nazca Lines 800×173 · Lake Mungo 800×97 · Pont du Gard 800×271.

**Important framing: the 800 px cap does NOT block the shorts.**
`pipeline/video/shorts_images.py:1-7` downloads the Commons **originals** via
`pipeline.lyra.image_fetcher.download_candidate` and re-measures dimensions with PIL —
*"the 800 px thumbnails the web pages use are never touched"*.
The cap is an `og:image` / LCP / SEO defect, not a shorts defect.

**Cheapest repair path:** 3,264 of the 3,858 heroes can be replaced **without any download** by an already-local
1600 px gallery image — just move the `is_hero` flag. SSR and hub pages read live
`ORDER BY is_hero DESC, is_lead DESC, sort_order`. For the remainder: 3,840 of the 3,858 hero rows carry a
direct Commons original URL.

### 6.4 Measured signal strength (precision / recall against 652 labelled images)

| Signal | Definition | Flagged | Precision | Recall |
|---|---|---|---|---|
| **B** | museum city > 150 km away named in the title (41-city list with coordinates) | 14 (2.1 %) | **92.9 %** | 20.0 % |
| **E** | non-photo word (67 terms: map, plan, drawing, painting, diagram, engraving, …) | 15 (2.3 %) | **93.3 %** for "not a photo of this site" | 10.1 % |
| **D** | place token of a curated site > 50 km away (dictionary of 4,396 tokens) | 11 (1.7 %) | 54.5 % | 9.2 % |
| **S** | same Commons file also attached to a differently named site | 78 (12.0 %) | 38.5 % | 46.2 % |
| **A** | museum word in title or Commons category | 62 (9.5 %) | 35.5 % | 33.8 % |
| **P** | file is **not** in the site's P373 category | 296 (45.4 %) | 17.6 % | **80.0 %** |
| **F** | own site name absent from title + filename + Commons name | 232 (35.6 %) | 16.8 % | 60.0 % |
| **CORE** | `S ∣ A ∣ B ∣ D ∣ E` | **151 (23.2 %)** | 33.1 % | **76.9 %** |

**Measured useless — do not use:** aspect ratio < 0.5 or > 2.5 (P 4.0 %) ·
`sort_order >= 10` (P 3.3 % — `sort_order` is purely alphabetical and carries no information) ·
`author IS NULL` (P 6.7 %) · foreign country name (P 30.0 % at R 4.6 %).

**Safe class (tier D):** in the P373 category **and** no word signal **and** own name in the filename
→ 197 of 652 images (30.2 %) containing **0 of the 65 foreign images** and 5.1 % other content errors.
Rule-of-three upper bound: 3/197 = **1.5 %**.

**Sample stratification:** tier A hero 38 images (18.4 % foreign) · tier B suspect 141 (31.9 %) ·
tier C grey 276 (4.7 %) · **tier D clean 197 (0.0 %)**.

**Extrapolation to production** (49,691 images, 4,010 sites): tier B ≈ 10,525 · tier C ≈ 20,602 ·
tier D ≈ 14,705 · heroes 3,858.

### 6.5 The gallery audit algorithm

Three independent designs were scored by three juries; none survived intact (the arithmetic juror found one
design's core figure 26 % too low, the risk juror found two mutually exclusive publication policies in another).
The synthesis below uses only **measured** signals.

| Stage | Rule | Volume | VLM calls |
|---|---|---|---|
| **0 — clear** | tier D (see 6.4) | ≈ 14,705 images | **0** |
| **1 — suspect** | CORE signal `S∣A∣B∣D∣E` | ≈ 10,525 images | every one |
| **2 — heroes** | all, because maximally visible | 3,858 | every one |
| **3 — grey zone** | **3 samples per site**; one hit escalates that site's entire gallery | ≈ 20,602 images → ≈ 10,500 probes, escalation on ≈ 14 % of sites | sampled |

Total ≈ **25,000–30,000 VLM calls**. Marginally $0 under the MiniMax flat plan; the binding constraint is the
weekly budget shared with Lyra and Theo.

**Expected residual error:** tier D carries ≤ 1.5 % residual risk (upper bound from 0 hits in 197 images).
Stage 3 reliably catches clustered contamination; isolated strays in otherwise clean galleries can slip through.
For shorts this is acceptable: only the **selected stills** need to be safe, not the entire gallery — see gate S11.

---

## 7. The shorts gate

13 machine-checkable conditions, all counted against production.

| ID | Condition | Pass | Fail |
|---|---|---|---|
| S1 | `card_description` present | 4,997 | 7 |
| S2 | `card_description` length 80–300 chars | 4,997 | 7 (same set) |
| S3 | every caption word fits the frame (≤ 1080 − 2·40 px) | 4,934 | 70 |
| S4 | all characters of name + card text renderable | 5,001 | 3 |
| S5 | name fits in ≤ 3 lines | 5,003 | 1 |
| S6 | `country` yields an ISO-3166 alpha-2 code | 4,999 | 5 |
| S7 | `country` speakable without a parenthetical | 4,977 | **27** |
| S8 | coordinates plausible | 5,004 | 0 |
| S9 | `site_type` known to `ORBIT_ZOOM_BY_TYPE` | 4,989 | 15 |
| S10 | **≥ 6 non-excluded `wiki_images`** | **2,708** | **2,296** |
| S11 | ≥ 6 images with author + licence, non-panoramic, from `upload.wikimedia.org` | 2,663 | 2,341 |
| S12 | within the time window (Americas ≤ 1500, RoW ≤ 500) | 4,920 | 84 |
| S13 | card-text number check (section 5) | — | see 5.1 |
| | **all 13 simultaneously** | **1,888 (37.7 %)** | |

Without S13: 2,557 · without any image condition: 4,799 · with `n_ok >= 10` plus S13: 1,637.

**Failure detail:**
- S3 worst case `Buckinghamshire-Bedfordshire` (Woburn Sands) at 1,628 px, then `longest-continuously-occupied` at 1,620 px
- S4: `Jabal al-ʿHayn` (U+02BF), `Ərəbyengicə`, `Gate of All Nations Persepolis` (invisible U+200C in the name)
- S5: `Cathedral and Churches of Echmiatsin and the Archaeological Site of Zvartnots`
- S6: 4 × `Northern Ireland` (no code), 1 × `Baltic Sea Anomaly` → pseudo-code `BALTIC` (`countryFlags.ts:285`)
  sends `ensure_flag` into a RuntimeError
- S7: all 27 are `Georgia (country)` — **the narrator reads the parenthetical aloud, verbatim**
- S9: Amphitheatre 2, Bridge 2, Aqueduct 2, Monastery 2, Stadium 2, suspect_modern 1, Elongated skulls 1,
  Ruin 1, Road 1, Stone cross 1

**The binding constraint is image supply, not data quality.**
`MIN_SITE_IMAGES = 6` (`pipeline/video/__main__.py:44`). 2,296 sites fall below it.
**Gallery cleanup lowers this number further** — 405 sites sit at 6–10 images and 274 at 6–8;
each removed foreign image tips them under the threshold.

---

## 8. Scope

### 8.1 Mechanically detectable violations

```sql
SELECT count(*) FROM unified_sites
WHERE source_id = 'ancient_nerds'
  AND ((lon <  -30 AND period_start > 1500)     -- Americas
    OR (lon >= -30 AND period_start >  500));   -- rest of world
-- 69
```
Split: Americas 10 · Old World 59. Of these, **18 carry `site_type = 'Museum'`** where `period_start` is the
founding year (Museo de la Arquitectura Maya 2005, Maria Reiche 1994, Carlos Pellicer 1980, …).

Largest block among genuine candidates: **Pakistan 12** (Mughal/Talpur forts: Ali Masjid 1837, Jamrud 1836,
Naukot 1810, Manora 1797, Kot Diji 1795, Attock 1580, Sheikhupura 1607, tombs of Ali Mardan Khan 1630 and
Jahangir 1627), plus Japan (Osaka Castle 1583, Kagoshima 1601, Naegi 1532), Portugal, Albania, Spain.

**Boundary trap:** 9 Old World sites have `period_start` **exactly 500** and pass, because
`passes_date_cutoff()` tests `date <= cutoff` (Furby/SE, Nashtifan Windmills/IR, Kaljaja Tenes Do/RS,
Mount William Stone Axe Quarry/AU, …).

### 8.2 The 51 `Museum` rows after individual review

- **41 stay** — they exhibit ancient material
- **3 out** — King Richard III Visitor Centre (1485), Khushuu Tsaidam Museum (Göktürk Orkhon stelae, 8th c.),
  Groß Raden (Slavic settlement/temple, 9th c.)
- **9 are not museums at all** — 5 finds (Appleby Logboat, Aymestrey Burial, Fiskerton Log Boat,
  North Bersted Man, Schöningen Spears) and 4 places/landscapes (Kilmartin Glen, Federsee,
  Krapina Neanderthal Site, …). These need a `site_type` correction, not a scope decision.

### 8.3 The real difficulty

**1,295 sites (25.9 %) cannot be decided from the bucket value.**
Composition: Old World with `period_start >= 1` → 1,057 (of which **964 carry the literal value 1**);
Americas with `period_start >= 1000` → 223 (of which 128 carry the literal value 1000); plus the 15 with no
`period_start`.

Because `period_end` is NULL on 100 % of sites, no date test can see the span of occupation.
**For this quarter of the database, scope is a question for the factual audit, not for a SQL query.**

### 8.4 Implementing E4

A new column is approved (E4). Proposal: `unified_sites.scope_status`
(`in_scope` / `retired` / `pending`) plus `scope_reason text`.

**Every consumer that must honour it** — this list is part of the deliverable so implementation misses nothing:

| Consumer | Location |
|---|---|
| Globe / point rendering | `App.tsx:182` → `sitesRenderer.ts:150-154` |
| Filter panel | frontend filter logic |
| SSR detail page | `pipeline/sites_html_renderer.py`, `sites_html.py:281-284` |
| Country hub page | same, grouped by `country` |
| `sitemap.xml` | sitemap generator |
| Static export | `pipeline/static_exporter.py` |
| Qdrant search index | `scripts/build_lyra_index.py`, nightly sync 03:00 UTC |
| **Shorts batch** | `pipeline/video/__main__.py:385-391` — **currently filters only on `rarity_tier` + `card_description` + image count; knows nothing about scope** |
| Card game / expedition | `api/cardgame/expedition.py` |
| Public API | `api/routes/public_v1.py` |

---

## 9. Tooling inventory

### 9.1 What survived adversarial review

| Building block | Location | Value |
|---|---|---|
| `audit_wikidata_batch.py` | `scripts/` | fetches P625/P17/P31/P571/P580/P582 in batches of 50. Because the 4,618 QIDs already live in `site_external_ids`, its expensive resolution step is unnecessary → **a 20-line adapter, ~4 minutes, $0** |
| `generate_stats()` | `api/cardgame/generator.py` | recomputes `card_stats` completely and **leaves `card_description` untouched** |
| Wave-4 chain | `scripts/audit_enrich.py:1608-2810` | 6 phases, **demonstrably executed once in March 2026** (2,217 sites received citations between 03-06 and 03-14). **Not used by Phases 4/5** (2026-09-23): `sync_from_production` UPDATEs every row, `merge_verification` is an unconditional, unjournalled UPDATE, and `content_id` comes from a salted `hash()` - see the script's docstring and 12, Phase 4 |
| Transport path to production | `audit_enrich.py:1528-1540` → `api/routes/sites.py:1560-1561, 1756-1836` | `description_citations` and `reference_links` **do** reach production |
| Batch fan-out | `scripts/prepare_verify_batches.py`, `verify_agent.py`, `merge_rewrites.py` | ready-made scaffold - **retired for card texts** (2026-09-23): cards are extractive, `docs/procedures/CARD_DESCRIPTIONS.md` |
| Phase-3 runner seams | `scripts/remediation/phase3/` (`model_stage.HandoffRunner` - the Opus handoff since 2026-09-23, `judge_site`, `fetch_stage.EvidenceStore`, `write_stage.run_sql`/`change_key`, `mass_run`) | what Phases 4/5 import instead of the Wave-4 chain; `scripts/remediation/phase4/` builds on them (`docs/procedures/PHASE4_CONTRACTS.md`) |
| **Prospector `dedup.py`** | `pipeline/…/prospector/` | LLM-free four-rung ladder (hard identifier → exact name key → trigram/Levenshtein/PostGIS → gates for country/distance/rare token). Already adjudicated **5,260 candidates and written 26,515 verbatim evidence rows** in production |
| Prospector `resolve.py` | same | exactly the rejection filters needed here: no P625 coordinate, P625 precision ≥ 0.1°, P31 region denylist, off-Earth, and `passes_date_cutoff()` carrying the project scope |
| Theo citation integrity gate | `pipeline/lyra/theo_citations.py` (1,953 lines), `hallucination_gate.py`, `citation_verifier.py` | **deterministic, no LLM**, 206 green tests in 0.39 s, live in production. Built for markdown papers, so **not directly** applicable to sites — but its components are: `strip_orphan_citation_markers`, `normalize_grouped_markers`, `_collect_non_numeric_markers`, `detect_placeholder_markers`, `score_tier_by_domain` |
| Long-run template | `scripts/rework_paper_images.sh` | `setsid nohup`, own progress log, budget gates before each item, fail-closed on unreadable measurement |
| External observer | `scripts/monitor_theo_run.py` | resumes from the issue file |
| Heartbeat | table `pipeline_heartbeats` (PK `pipeline_name`, `step_data` jsonb) | generic, reusable immediately |
| `pipeline/utils/imagehash.py` | | usable for **exact** reuses, **not** for cropped ones (see 9.2) |

**Correction to the initial finding:** the six enrichment columns in `card_stats` **are** populatable after all.
Verified live: `pipeline.database.engine` sees the production database **inside container `ancient_nerds_api`**
(5,004 rows), and the columns already exist there. The `enrich_*` scripts can therefore run against production
if started **inside the API container** — no schema change and no upload detour required.

### 9.2 What failed — do not build on these

| Claim | Reality |
|---|---|
| `dhash` finds gallery duplicates | **0 of 36** real duplicates at `d <= 6`. **Not crop-invariant**: the cropped twin measures `d = 19`. Minimum pair distance across all 140 images of the affected sites exceeded the threshold |
| `image_gates.metadata_gate_passes` pre-sorts filenames | The tokeniser counts `_` as a **word character** → `Dolmen_at_Ganghwa` is **one** token. Also, `wiki_images` has no `description` field at all (`pipeline/database.py:601-641`) |
| `minimax_vlm()` is a ready VLM transport | Does **not** check `base_resp` (`minimax_shared.py:560-561`) → **quota and rate-limit errors are silently recorded as rejections**. No rate limiting, contrary to the documentation |
| `shorts_select.judge_all()` is production-ready | Substantively correct, but **664 of 733 VLM calls failed at the transport layer** from the workstation (WinError 10053/10054, `SSL: UNEXPECTED_EOF_WHILE_READING`). **Must run from the VPS.** The `RuntimeError` guard (`:244`) fires only on 100 % failure, not partial |
| `POST /{site_id}/set-hero` repairs heroes | `HERO_WIDTH = 800` (`api/routes/wiki_images.py:22, :103-105`) — **the endpoint is the defect** |
| `STRICT_VLM_PROMPT` filters strictly | The prompt says *"SUBJECT, NOT INSTANCE … place … even when it is not the specific instance"* (`meaningful_images.py:320-328`) — it explicitly declares a Delphi photo valid for Puma Punku. `verdict_is_safe` additionally lets `weak` through |
| `image_attribution_backfill.backfill_heroes()` | The run is finished; the remaining 130 rows are precisely those where the August run failed. A rerun yields nothing |
| Theo for fact-checking | **Categorically unusable**: 30 completed runs in total, averaging 778 minutes (13 h), 23.2M tokens and 369 LLM calls **per run**, `THEO_PARALLEL_SLOTS=2`, `THEO_MIN_TASK_INTERVAL_S=6h`. 5,004 sites would be a multi-year project |

### 9.3 The major synergy in the image workstream

`pipeline/video/shorts_select.py:judge_all` (prompt `:51-75`, call `:213-248`) **already sends every downloaded
image** through the MiniMax VLM — default 40 images per site (`__main__.py:58`) — and receives exactly the
labels needed:

```
kind (site_photo | artifact | map_or_document | painting_or_artwork | people | other)
subject, people_prominent, text_or_overlay, quality 1-5, relevance 1-5,
illustrates, focus{x,y}, vertical_crop_ok, other_site
```

`other_site` is literally the foreign-image detector; `kind` is the missing image-kind column.
**Today these verdicts land only in a throwaway file in the render directory**
(`video-assets/shorts/*/selection.json`; 280 stored verdicts from 16 sites already sit there).

**If every site gets a short, those ≈ 49,000 VLM calls are paid for anyway.**
Persisting them into `wiki_images` converts throwaway work into the permanent gallery audit.
This is the single most valuable economic measure in this document.

### 9.4 What does not exist and must be built

1. **No link checker** — the HEAD sweep over the 16,029 reference links must be written.
2. **No country polygons.** `build_country_centroids.py` yields only bbox centroids, `world_land.json` only
   land outlines, and Postgres has no country table. The point-in-polygon test needs a Natural Earth 10m import.
3. **No `site_type` synonym table** (see 3.2).
4. **No `card_stats` recompute script** other than `generate_stats()`; `POST /api/sites/rebuild-static` is
   broken in production (the API runs as uid 1000, `public/data` is owned by root).
5. **No evidence column for `card_description`.**
6. **No render ledger** for shorts (see 10.4).
7. **No change journal.** `database_audit_log` does not exist; `review_queue` and `match_decisions` are empty.

### 9.5 The hard limit of deterministic checking

Measurement against Wikidata: 300 random QIDs from production, 291 resolved, field-by-field comparison.

| Field | Result |
|---|---|
| `name` | **97.3 % confirmed** |
| `country` | **96.6 % confirmed** — only 2 genuine conflicts; England/UK is resolved cleanly by `normalize_country` |
| Coordinates | **88.0 % within 1 km** |
| `period_start` | **P571 coverage only 10.3 %. P580/P582 exactly 0 %.** Of 25 available dates, **6** agree within 100 years; **6 of the 11 deviations are pure designation dates** (Museum 1969, Historical Park 1989) |
| `site_type` via P31 | unusable — P31 returns mostly generic classes |

> **The consequence that shapes the plan: Wikidata can verify names, countries and coordinates — not periods.**
> The 9 confirmed `period_start` errors in the sample are **not** solvable deterministically.
> The earlier assumption that the deterministic pass covers 27 of the 54 errors is therefore **too optimistic**;
> the realistic figure is around 18 (name 2, country 2, coordinates 2, site_type 6, period_name 3,
> thumbnail 2, source_url 1).

Additionally: `enrich_fetch_claims.py` blindly takes `prop_claims[0]`, ignores `rank=deprecated` and ignores
time precision — even though `extract_year_from_wikidata_time()` (`pipeline/normalizers/dates.py:118`) does
exactly that. There are **three parallel Wikidata time parsers** in the repo.

---

## 10. Landmines — defuse before the first write

### 10.1 Two processes overwrite remediation values on restart

| Location | What it does |
|---|---|
| `api/main.py::lifespan` -> `api/services/card_descriptions.py::import_card_descriptions` | imports `public/data/card_descriptions.json` into `card_stats` **on API startup** |
| `pipeline/lyra/orchestrator.py::_run_migrations` | runs on **every** container restart, globally normalises `site_type`, rewrites `name_normalized`, and issues ALTER TABLE on `card_stats.card_description` (only while the catalog says the column is missing or not `varchar(200)`, `pipeline/utils/boot_ddl.py`) |
| `api/main.py::lifespan` (until 2026-09-23) | a third boot writer this section first missed: it `jsonb_set` a hard-coded `description_citations` array (grokipedia among the sources) into the `raw_data` of 10 sites on every API start where the key was absent. A read-only check on 2026-09-23 found all 10 carrying the key, so it was removed with Push #1 (WB-D4); the Phase-4 verifier's V12 keeps the key non-empty, so it could never have fired again anyway |

A deploy or container restart during or after the run can revert corrected values.
**Resolve and lock this down for the duration of the run before any write.**

### 10.2 Wave 0 of the orchestrator has no `source_id` filter

`scripts/audit_enrich.py` lines `444-453`, `477-490`, `497-502`, `529-547` operate on the **entire**
`unified_sites` table, not on the candidate list passed in (the `sites` argument is used only for
`stats['total_sites']`, line 427).

**Production blast radius: 1,759,675 rows across 30 sources**, including 1,030,041 individual UPDATEs for the
country backfill inside a Python loop. This violates anti-pattern 12 of the project's own procedure.
**Must be fixed before use.**

### 10.3 Further tooling defects

- The flat-dict fallback in merge (`audit_enrich.py:1223-1234`) stamps **every** fix as `confidence='high'`,
  bypassing the confidence gate entirely.
- `--phase sync` does **not** transfer `name_normalized`, `raw_data`, `period_end` or `parent_site_id`
  (`:161-176`, `:283-299`) — a locally built database ends up with 5,004 rows of `name_normalized = NULL`,
  rendering duplicate dimension D6 and tier P6 worthless.
- Wave 0 "raw year parsing" is **phantom documentation**: `run_mechanical_fixes` (`:400-570`) never touches
  `raw_data`. In production `raw_data` is empty apart from `description_citations` anyway.
- `restore_snapshot()` (`api/services/snapshots.py`) does **not** write `raw_data` back in its ON CONFLICT
  branch. After a restore, the 2,216 `description_citations` point at text that no longer exists.
- `batch-upload` cannot **clear** a field (COALESCE), only overwrite it.
- `DELETE /api/sites/{id}` creates **no** snapshot and cascades to `wiki_images`, `site_content_links`,
  `unified_site_names` and `site_external_ids`.

### 10.4 No render ledger

Production has 62 tables and **not one for site shorts** (`news_videos` is the old weekly-video pipeline).
`site.json` in the render directory carries no timestamp, no hash, no data version.

**A published short is completely decoupled from the data state it asserts.**
If a card text changes later, nobody knows which video still carries the old claim.

**Action before the first batch run:** create table `site_shorts` with
`site_id, slug, rendered_at, card_text_at_render, card_text_sha256, image_ids[], voice_id, pipeline_commit, youtube_id, published_at, status`.

### 10.5 Circular dependency between text and image selection

`shorts_select.VLM_PROMPT` injects `card_text` as *narration* and has `relevance` scored **against that text**.
`score()` (`:150-159`) weights `relevance` triple against `quality` single, and `shorts_render.py:870` orders
the stills accordingly.

**The unverified spoken text therefore drives both the selection and the ordering of images.**
Mitigation (no code change required): allow `card_text` to steer image selection only once it is sourced —
until then use `--no-vlm` with geometric selection, or decouple the VLM question from the card text.

### 10.6 Slug collision

`__main__.py:153/399/469` and `shorts_export.site_dir` build everything on `slugify(name)`.
The web URL deliberately appends an 8-hex suffix **because 16 curated sites share a name**
(`pipeline/sites_html_renderer.py:30-32`). The shorts directory name does not —
two same-named sites overwrite each other, and the resume marker points at the wrong site.

### 10.7 Duplicate Qdrant sync

The sites index is incrementally refreshed nightly at 03:00 UTC (content-hash based, last run 27 s) —
**twice**, because `api` and `api2` both start the scheduler.

---

## 11. Legal exposure

| Topic | Finding | Immediate mitigation |
|---|---|---|
| **Image licences in video** | **33,454 of 49,032** live images are CC BY-SA (ShareAlike): 4.0 → 17,287, 3.0 → 11,583, 2.0 → 3,561, 2.5 → 393, plus localised variants. Whether a short (9:16 crop, Ken Burns move, narration, music bed) constitutes an **adaptation** under the licence is unresolved | Low-risk: restrict still selection to the **7,719** images under Public Domain / CC0 / No restrictions |
| **Missing attribution** | 1,021 live images without `author`, of which **546 fall under a licence requiring attribution**. `shorts_render.py:465-466` writes `Unknown` into the video description for these | Hard-exclude images without `author` from still selection (costs 546 of 49,032) |
| **Special licences** | 27 images under Licence Ouverte (21), OS OpenData (3), GODL-India (3), each with its own attribution formula | smallest cohort; review once by hand (~15 min) |
| **EU AI Act** | Papers, news and articles carry Art. 50(2) disclosures (`article_html_renderer.py:293-300`, `api/routes/news.py:105/126`, `api/schemas/public_v1.py:188/447/551`). **The 5,004 site detail pages carry none**, and neither does the video | decision required |
| **Text provenance** | `description` derives from Wikipedia (CC BY-SA) on 4,689 of 5,004 sites. The detail page shows only a favicon with a link (`DescriptionSection.tsx:106-112`), no licence notice. 315 sites have no Wikipedia source at all | legal question: after the March rewrite, are these still derivative works or independent rewordings? |

---

## 12. Remediation plan

### Phase 0 — Safeguards *(complete 2026-09-20, residuals named per row)*

| Step | Status |
|---|---|
| Targeted backup of the six affected tables | ✅ **done 2026-09-19 11:22** — `/var/www/ancientnerds/backups/2026-09-19_pre-audit/` (VPS) and `output/backups/2026-09-19_pre-audit/` (local), 8.1 MB gzip, CSV each filtered to `source_id='ancient_nerds'`. Produced by `scripts/_backup_curated.sh` |
| Full `pg_dump` + **tested restore drill** | ✅ **done 2026-09-20** — `scripts/remediation/00_backup_and_drill.sh`, deployed to `/var/www/ancientnerds/scripts/remediation/` and on cron. Dump **654,604,671 B** into `backups/2026-09-20_remediation/` (a later cron run: 654,621,587 B). Drill **PASSED**: `pg_restore exit=0`, 1 m 36 s, six tables verified row-for-row, against `DRILL_REPORT.txt`. **Two false greens were found and root-caused on the way** (see below) |
| Arm the backup cron / systemd timer | ✅ **done 2026-09-20** — crontab installed: Mon–Sat **03:15** `DO_DRILL=0`, Sun **04:15** `DO_DRILL=1`. Propagation **proven end-to-end** with a stub drill that always exits 1: `DO_DRILL=1` → exit 1; `DO_DRILL=0` → exit 0 **and** prints `drill SKIPPED (DO_DRILL=0). The dump is NOT verified by this run.` Retention is step 4: only `<date>_remediation` dirs are ever pruned, never `2026-09-19_pre-audit`. Residual: no `MAILTO`, so a failure is silent unless the exit code is watched |
| Offsite copy of the 20 GB of images under `public/data/images` | ✅ **done 2026-09-20** — VPS **49,790** files; local **49,787** + **3** in `AncientMap-Offsite/images-case-collisions/` = **49,790**, all three sha256-identical. Root cause of the count gap: **Windows' case-insensitive filesystem** cannot hold case-only-differing filenames that Linux can, and those were genuinely different images. The sidecar README carries the mapping; the Linux VPS stays authoritative. Residual: two filesystems, no third party |
| Offsite copy of `video-assets/` | ✅ **done 2026-09-20** — VPS **4.6 G / 1,415 files / 0 `*.env`**; local **1,416** = 1,415 + the deliberately excluded `prod-db.env`. Offsite is **cross-machine, not third-party**: the repo and its copies are on machines Martin controls. Residual named, not hidden |
| Define the change journal file format | ✅ **done 2026-09-20, with one deliberate deviation** — `migrations/0017_remediation_change_log.sql`, **applied to production**. E1 asked for "the change journal as a **file**"; it is a **table**, because `apply_remediation_change()` performs the conditional UPDATE and the journal INSERT *in one statement*, so a rolled-back change cannot leave a journal entry behind. A file cannot give that guarantee. Self-test `scripts/remediation/0017_migration_selftest.sql`; production `change_log rows (must be 0): 0` |
| Gold standard: 30–40 double-blind sites for the false-negative rate | ✅ **done 2026-09-20** — **36 sites**, **540 field verdicts**: 449 CORRECT / 40 WRONG / 51 UNVERIFIABLE. Field-level, not site-level, because T10 flags 4,010 sites and T09 all 5,004 — a site-level match would read near-100 % and measure nothing. **FNR 24/40 = 60.0 %**, Clopper-Pearson [43.3 %, 75.1 %], inverse-probability weighted **62.4 %**. Deliverables + the comparison script: `output/remediation/gold_standard/`. The rate is only useful decomposed: **3** errors have no check at all (all E3 scope), **13** have a check that under-fires, **8** need the semantic/VLM pass |
| Field contract (data dictionary with acceptance criteria per field) | ✅ **done 2026-09-20** — `docs/procedures/FIELD_CONTRACT.md`, committed `9789048` and extended since. Its card-description chain was **corrected twice, both times by checking instead of reasoning**: the section first claimed a workflow that is broken at step 1 (the file does not exist by default), and the generator behind it turned out to be unable to fail at all |
| Fix the `source_id` filter in Wave 0 (10.2) | ✅ **done 2026-09-20** — `scripts/audit_enrich.py`, 6 edits, guarded by `tests/remediation/test_wave0_scoping.py` (3 tests, mutation-proven). Commits `5d0d7e9` and `96b365d`; the full gate suite was green at 1,879 passed / 3 skipped |
| Lock down the restart overwriters (10.1) | ✅ **done 2026-09-20** — `api/services/card_descriptions.py` (startup import extracted; the values it discards are now logged instead of vanishing), `pipeline/lyra/orchestrator.py::_run_migrations` (reconciles curated sites' `name_normalized` against its producer, **scoped** after measuring **80,083 divergent rows across 28 external sources**), `pipeline/lyra/site_key.py:1-14` (docstring), `api/services/snapshots.py:351-358` (`restore_snapshot()`'s UPDATE branch now restores `raw_data`). `tests/remediation/test_restart_overwriters.py`, 14 tests, **6 fail before → 14 pass after**. Decisive result for Phase 2: **`wiki_images.is_hero` has no restart writer**, so hero repairs survive a restart. Residual: `restore_snapshot()` still omits `parent_site_id` / `source_record_id`, and §10.3's two `audit_enrich.py` defects are report-only |

**The two false greens, recorded because the lesson is the point.** Two earlier drill tasks reported exit 0 on a *failed* restore. Both were root-caused, not excused: `pg_restore` on the **host** fails with `fe_sendauth: no password supplied`, because the host-side client arrives as **`172.18.0.1/32`** (the Docker gateway), which misses the `trust` lines scoped to local/127.0.0.1/::1 and falls through to the `scram-sha-256` catch-all. The fix is to copy the dump **into** the container and restore from there with a file argument. Every prior exit-0 claim in the session was then re-read: **2 false, 3 sound.** The rule now applied everywhere: **trust the printed verdict, not the exit code** — a self-verifying task can print its own `VERDICT: … MISMATCH` and still exit 0, because the final `echo` returns 0.

> **Backup-script pitfall:** `docker exec -i` consumes a shell script piped in via stdin.
> Drop `-i` and append `</dev/null` to the container call.

**Snapshot situation** (better than initially assumed): snapshot `d4526691` genuinely carries the pre-March
descriptions (5,005 rows, 20 of 23 columns, averaging 802 chars versus 521 today) and covers 4,996 of today's
5,004 sites. Three further snapshots (`5d0dbe25`, `89f2a5e7`, `493e91da`) are **byte-identical** — there is
exactly one prior state, quadruply secured. Mind the `raw_data` gap from 10.3.

### Phase 1 — Deterministic full census *(no LLM, ~1 day, ~$0)*

Across all 5,004 sites and all 49,032 live images:

1. Wikidata claim comparison using the existing 4,618 QIDs — `name`, `country`, coordinates.
   **Not** for periods (9.5).
2. Centroid and point-in-polygon test (requires a Natural Earth 10m import).
3. Years mentioned in the description text versus `period_start` — catches contradictions Wikidata cannot see.
4. `site_type` synonym resolution via a hand-written mapping table.
5. Country values: `Georgia (country)` 27, `Chile, Easter Island` 8, `Baltic Sea` 1.
6. URL shapes: 7 non-http, 9 fragment URLs, 42 missing.
7. HEAD sweep over 15,230 distinct reference-link URLs (~45 min at 24 parallel).
8. Citation integrity check, markers ↔ array — **immediately actionable:** 76 sites carry an evidence array
   with no `[N]` marker in the text at all, 11 have a marker without a matching entry, and 8 have an entry
   that is never cited.
9. True Commons original dimensions per image (981 `imageinfo` batches).
10. Compute gallery signals S/A/B/D/E/P/F → tier assignment per image.
11. **E3 scope window** *(added 2026-09-20, after the gold standard exposed the gap)* — §1.3 lists
    in-scope-or-flagged as a condition of "clean" and §7 gate S12 already measures it (4,920 pass /
    84 fail), but **no census check covered it**, so the census could not certify a site clean by its
    own acceptance rule. Two of the three blinded E3 errors in the gold-standard sample are pure
    comparisons of stored values and need no network. Also open: the plan's **84** versus an earlier
    baseline's **69** — to be settled by running both rules over the snapshot, not by splitting.

**Output:** the flag list that steers the entire expensive phase. Covers roughly **18 of the 54** measured
error classes.

**Acceptance criterion:** each of the 5,004 sites has a record holding the result of all ten tests.

### Phase 2 — Image remediation

1. **Hero repair** (mechanical, no LLM): replace 3,264 heroes with an already-local 1600 px gallery image
   (move the `is_hero` flag only); fetch originals via `commons_page_url` for the rest.
   Raise `THUMB_WIDTH` / `HERO_WIDTH`.
2. **Gallery audit** per the algorithm in 6.5.
3. **Image-kind column** added to `wiki_images`, populated from the VLM `kind` field.
4. **Persist the VLM verdicts** (9.3) — the most valuable single economic measure.
5. **Image acquisition** for the 2,296 sites below threshold; the lever is the 1,448 sites with a missing or
   wrong P373 anchor.

**Important:** run VLM work **from the VPS**, not from the workstation (9.2).
`minimax_vlm()` must check `base_resp` first, otherwise quota errors are recorded as rejections.

### Phase 3 — Two-stage factual audit

Only for sites Phase 1 could not conclusively settle. Method exactly as in the pilot:

- **Stage 1 (finder):** checks every field against at least two independent sources.
- **Stage 2 (reviewer):** attempts to refute **every** error claim using **its own** research — not by
  re-reading stage 1's evidence. Must be briefed on the false-alarm patterns in 4.3.
- Only `refuted = false` is applied, with a conditional WHERE clause and a journal entry.

**Batch size:** 5 sites per agent (pilot value, ~40,000 tokens per site across both stages).

### Phase 4 — Sourced descriptions *(design of 2026-09-22; built 2026-09-23, tracks A-D)*

The final design is entry [6] of `output/remediation/logs/design_texts_images_2026-09-22.json`
("Phases 4 and 5, final design"); the contracts the four build tracks share are
`docs/procedures/PHASE4_CONTRACTS.md`, the code is `scripts/remediation/phase4/`. It replaced the
Wave-4 plan that stood here (`web-links` -> `cited-description` -> `verify-citations`), which is not
used: its sync UPDATEs every row, its merge is an unconditional, unjournalled UPDATE, and its
content ids come from a salted `hash()` (9.1, and the docstring of `scripts/audit_enrich.py`).

**Extractive-first.** A description is assembled by code, byte for byte, from sentences of a pinned
Wikipedia revision (the oldid permalink plus the sha256 of the exact text). The model (one call per
site, answered by Opus through the handoff since the owner order of 2026-09-23 -
`phase3/model_stage.HandoffRunner`, `scripts/remediation/opus_handoff.py`) returns only sentence and
span ids; code applies the closed
edit list (drop an offered span with one delimiter, collapse spaces, repair `' ,'`, restore a capital,
insert `' [n]'`); citation numbers are assigned by code. An independent verifier that never imports
the assembler re-derives every byte (V1-V15), a drop-only reviewer in a separate context checks every
sentence, and a Claude Code audit reads the whole pilot, every lane-T/R site and samples of the rest.

**Lanes**, assigned once from recorded facts, never changed: W (own English article), S (a shared or
parent article: name-bearing sentences only), T (own article only in another language: selected, then
translated), R (only non-free pages: facts restated, wording never published), 0 (nothing: held).
A site that fails inside its lane is held with a named reason.

**Written** through `apply_remediation_change()` in three row groups, each with its own journal family
(`output/remediation/tools/lanes.py`: `p4`, `p4l`, `p5`): P4 `description` + `raw_data` (site-atomic,
`raw_data._description_provenance` v1 added, `description_citations` replaced by permalink citations),
L (legacy disclosure: `ai: 'generated'` provenance for held sites whose text differs from snapshot
`d4526691`) and P5 (cards). `scripts/remediation/phase4/write4.py` renders each write batch as one
transaction with guards before the loop, the journal agreement and two in-database sha256 invariants
after it; `output/remediation/tools/write_gate4.py` runs one step of 100 sites per invocation
(preflight, write, read-back, inverse proof), `verify_writes4.py` accepts each step, and
`scripts/remediation/phase4/revert4.py` reverts from the journal alone. `unified_sites.updated_at` is
not written; the sitemap lastmod reads the journal.

**Disclosure** (O4, O5 resolved by design): the render key is `raw_data._description_provenance.ai`.
'selected' text (W, S) shows the attribution line under the description; 'generated' text (T, R, L)
shows the existing AI footnote; lane T shows both. `/api/sites/{id}`, the SSR payload and the public
API carry the marking (`api/services/description_provenance.py`), the site JSON-LD carries
`isBasedOn`/`license` and the IPTC type for generated text. Push #1 ships all of it before the first
write.

### Phase 5 — Card texts *(same run, extractive; O3 resolved)*

A card is an extractive condensation of the site's own published description: 1-2 of its `DESC`
sentences minus offered spans, assembled by code, the only non-source edit `c.`/`ca.` -> `circa`
(`docs/procedures/CARD_DESCRIPTIONS.md`, the contract). V10 checks 80-200 characters, no country, no
marker, no parentheses, no pronoun opener, no unattributed superlative, glyphs and caption width; V13
and the shorts gate's S13 check `sha256(card) == provenance.card.text_sha256`. A held card keeps its
old text; one with a Phase-3 reviewer-cleared defect is cleared (`P5/card-clear`). The P5 sitting
writes the database first and the file (`scripts/remediation/phase4/card_json.py`, pre-rendered and
regenerated byte for byte) second; pushing the file first is forbidden (`docs/procedures/FIELD_CONTRACT.md`
2.3). `scripts/verify_descriptions.py` and `verify_agent.py` are retired as gates.

### Phase 6 — Follow-through

1. Recompute `card_stats` via `generate_stats()` (**all seven combat values** derive from the corrected fields;
   47 collection entries hang off `rarity_tier`).
2. Recompute `name_normalized` in SQL using `unaccent` — **not** via Python `normalize_name()`.
3. Fix `rebuild-static`, run the static export, resync Qdrant.
4. Introduce the scope column and update **every consumer listed in 8.4**.
5. Create the `site_shorts` ledger (10.4).
6. **Acceptance:** 60 freshly drawn sites (not the pilot set) run through the same two-stage method, with a
   pass threshold fixed in advance.

### Phase 6b — The WE lanes *(HUMAN_ONLY decisions of 2026-09-26, built on `wip/we1`)*

The owner's O9 of 2026-09-26 ("nach meiner Empfehlung entscheiden") decided every open HUMAN_ONLY
item by its recorded recommendation (`output/remediation/HUMAN_ONLY_DECISIONS_2026-09-26.md`). Four
of them are data actions no other workstream covers; this section is their runbook. Every
production write is journalled, rehearsed, probed, applied in steps of at most 100 sites, read back
and its reversal rehearsed; nothing here deletes a `unified_sites` row. All commands run from the
root of the checkout that holds the plans, with `PY=./.venv/Scripts/python.exe`.

**Order.** L5 (B1-L, B1-N) runs **before WD1's Wikidata harvest is trusted**: WD1 reads each site's
item and English article from `site_external_ids` (`kind = 'wikidata_qid'` and `'enwiki_title'`),
and on a generic or wrong item it would harvest `P625`, `P571` and `P18` of the wrong object. L5
writes its corrections exactly there. The country lane and the Lyra key lane are independent of
everything else. The L5 name lane runs after the L5 import (its plan is built from the answers).

**What WD1 may trust (hand this to WD1).** WD1's harvest export (`wip/wd1`,
`scripts/remediation/fields/harvest.py`, `EXPORT_SQL`) reads the links of every curated site and
excludes none. Two rules make its harvest safe:

1. The export is taken only **after every L5 link step has landed** (`run.py step verify --step N`
   reads 0 deviations for each step `plan` wrote).
2. For every site in `output/remediation/l5/UNTRUSTED_LINKS.jsonl` (written by `run.py plan`),
   WD1 treats every Wikidata- or Wikipedia-derived value (`P625`, `P571`, `P18`, the article's
   coordinates, the item's classes) as **absent** - not harvested, never a witness. Each line
   names the site, its stored links and its `status`: `excluded` (retired, or not one item and
   one article), `held` (no answer passed the machine checks by the last round), `skipped` (the
   plan did not write it: it changed since the question, or its new item is carried by or
   decided for another site) or `shared-item` (it keeps an item another visible curated row
   carries - B1-D makes that WD2's question). A `shared-item` site becomes trusted once only one
   visible curated row carries the item; read-only, at WD1's export:

   ```sql
   SELECT e.value, count(*) FROM site_external_ids e JOIN unified_sites u ON u.id = e.site_id
    WHERE e.kind = 'wikidata_qid' AND u.source_id = 'ancient_nerds'
      AND u.scope_status IS DISTINCT FROM 'retired' AND e.value IN (<the shared-item QIDs>)
    GROUP BY e.value HAVING count(*) > 1;   -- the items still shared: their sites stay untrusted
   ```

**Hand-offs to WD2.** (1) HUMAN_ONLY Nr. 7: the empty row "Chiapa de Corzo"
(`24aa135d-4714-47f5-96c0-d58f0bc04b6f`, 0 links, 0 images) is hidden by WD2 as
`duplicate_of:ed186ea9-9ed1-415d-828b-97d9f21401d2` (the 20th duplicate entry, 2 cells); the rename
of the kept row "Zoque Culture Archaeological Zone" to "Chiapa de Corzo" (the English label of its
item Q4384315) is L5's name lane, pinned in `l5/population.py` (`PINNED_NAMES`). **WD2 has not
built that entry yet** (`wip/wd2` at `e1ba2de`: no `24aa135d` in `bcases/DUPLICATES.jsonl` nor in
any script; production 2026-09-26: both rows visible, scope NULL). `run.py plan` therefore plans
the rename only when the row is retired with exactly that `scope_reason`, and otherwise skips it
(`duplicate-not-hidden-yet` in `SKIPPED.jsonl`) - two visible rows 7.4 m apart would both carry the
name. Since `plan` runs once, WD2's hide lands **before** L5's `plan`; check it read-only first:

```sql
SELECT scope_status, scope_reason FROM unified_sites
 WHERE id = '24aa135d-4714-47f5-96c0-d58f0bc04b6f';
-- expected: retired | duplicate_of:ed186ea9-9ed1-415d-828b-97d9f21401d2
```

If `plan` has to run before it (WD1 waiting), the Nr. 7 rename stays open and needs a name lane of
its own stamp later - report it, do not re-run `plan`. (2) HUMAN_ONLY B1-D and B6: one rule for
every duplicate candidate. The nine rows L5's sources list (Amathunta/Amathus, Tel Hermal
Fort/Shaduppum, Ñustahispana, 39 Bridge Street Chester, the Lycian tomb entry and Amyntas Rock
Tombs, both Temple of Artemis rows, Caesarea Philippi) are **asked** like wave 3's
`duplicate-candidate` rows (Enkomi/Engomi, the Biniai Nou pair, Hattusas, Qorikancha, ...): the
question names the pair (`DUPLICATE_CANDIDATES`) and every curated row sharing the item, and a
shared item that names exactly this site is kept. Which row stays is WD2's retirement; the links of
a pair WD2 cannot prove to be one site (Tel Hermal Fort/Shaduppum 1.7 km, the Lycian tomb
entry/Amyntas 1.1 km) are the ones L5 decided for each row. A site that keeps a shared item is
listed `shared-item` for WD1 until WD2 has retired all but one of its rows.

#### B2-L — the two country cells (lane `country-b2`)

Decided: Achladia (`74145e9b…`) `Germany -> Greece`, Delphinion (`6aa4c8de…`) `Greece -> Türkiye`
(the dataset spells `Türkiye`: 218 curated rows, 0 `Turkey`). `scripts/remediation/mechanical/
country_b2.py` decides each row (curated, not retired, still the decided old value, its `country`
journal ending there, the new value canonical in T05's vocabulary, the stored point inside the new
country by Natural Earth, the row's own item not contradicting by `P17` or `P625`); the lane owns
exactly the two new values (guard 4) and conditions each row on its point (guard 5). The plan is
delivered (`output/remediation/mechanical_country_b2/`: 2 rows, 0 refused; its statements pinned in
`tests/remediation/test_mechanical.py`).

```bash
$PY scripts/remediation/mechanical/country_b2.py --collect   # only to re-plan: Wikidata + read-only
$PY scripts/remediation/mechanical/country_b2.py --write     # only to re-plan: read-only
$PY scripts/remediation/mechanical/apply.py --lane country-b2 --verify   # before: residual 2
$PY scripts/remediation/mechanical/apply.py --lane country-b2 --emit     # offline, byte-identical
$PY scripts/remediation/mechanical/apply.py --lane country-b2 --rehearse
$PY scripts/remediation/mechanical/apply.py --lane country-b2 --probe-guards
$PY scripts/remediation/mechanical/apply.py --lane country-b2 --apply
$PY scripts/remediation/mechanical/apply.py --lane country-b2 --verify   # after: residual 0
$PY scripts/remediation/mechanical/apply.py --lane country-b2 --rehearse-rollback
```

`card_stats.civilization` follows a site's country only through the next card_stats wave: after this
lane the read-back metric "card_stats rows whose civilization differs from the site country" reads
2 until then.

#### Nr. 9 — the eleven Lyra alias keys (lane `name-key-lyra`)

Decided: repair them. The shared chunk writer (`gallery_audit/chunk_writer.py`) takes a lane source
other than `ancient_nerds` - only `lyra`, and only for `unified_site_names.name_normalized`
(`KEY_ONLY_SOURCES`, `validate_lane_rows`); guard 1 then requires every planned site to be a `lyra`
site, guard 2b the row to belong to the planned site, guard 2c the key to be the key Postgres
derives from the row's name at write time. `name_key/plan.py` plans exactly the decided rows
(`LYRA_ALIAS_ROWS`: 3616643, 3616936, 3616938, 3617031, 3617034-3617036, 3617283, 3617346, 3617349,
3617350). The chunk is delivered: `output/remediation/name_key/name-key-lyra-2026-09-26/chunk-001/`
(11 keys on 6 sites, run stamp `name-key-lyra-2026-09-26-001`, journal test id `P6/name-key-lyra`).

```bash
D=output/remediation/name_key/name-key-lyra-2026-09-26/chunk-001
$PY scripts/remediation/gallery_audit/chunk_writer.py $D --check
$PY scripts/remediation/gallery_audit/chunk_writer.py $D --rehearse
$PY scripts/remediation/gallery_audit/chunk_writer.py $D --apply     # write + two-way read-back
$PY scripts/remediation/gallery_audit/chunk_writer.py $D --readback
$PY scripts/remediation/gallery_audit/chunk_writer.py $D --rehearse-rollback
# only if a row moved before the apply: re-plan into a new directory (never over a delivered one)
$PY scripts/remediation/name_key/plan.py chunk --out output/remediation/name_key/name-key-lyra-<date>
```

`pipeline/` is untouched (the writer was fixed in `370babf`); the boot migration's alias UPDATE is a
no-op on a key that is already `left(lower(unaccent(name)), 500)`.

#### L5 — the link and name pass (B1-L, B1-N, Nr. 7; `scripts/remediation/l5/`)

**Who.** `run.py population` (read-only) builds the population from the waves' records and
`bcases/names.jsonl`: wave 1's unresolved Tikal, wave 2's 47 unchanged wrong links, the 72
link-suspect kept names, the 46 N7 names and Delphinion (its item Q2677787 is a class). A retired
site and a site without exactly one item and one article are listed, not asked; every duplicate
candidate is asked (above). The name is asked of the N7 names only (B1-N); Zoque's rename is
pinned. The three self-contradicting records (Tikal, Ramesses III Temple, Rocca San Felice) are
asked their links and told that their name and point define the site - their description and
source are WA/WC's to rewrite, and Tikal is the only curated "Tikal".

**The question** (`questions.py`): the rules of B1-L/B1-N/O6 - this site is the place its name
designates at its stored point; a link names exactly this site (no type, container, sibling or
namesake) or it goes, and an item a duplicate row shares is kept when it names this site; a
replacement item cites its `Special:EntityData/<QID>.json`, a replacement article its own page; both
links removed on an English-Wikipedia `source_url` forces a decision on the URL (REPLACE with a
non-Wikipedia page about the site, or CLEAR), because the daily `refresh_site_external_ids` would
derive the links from it again; a rename takes the English label or alias of the item kept or
written, or the title of the article kept or written, and quotes a page with the new name. Every
verdict but a KEEP of the URL or the name carries verbatim quotes.

**The machine checks** (`decide.py`, on import): every quote found in its fetched page
(`opus_audit/quotes.py`); a replacement item is the item its entity page serves (not a redirect)
and lies within 1 km of the stored point by `P625` or by its article's coordinates (waves 2-3's
gate - otherwise a coordinate question for WD1 first); the article kept or written exists under
exactly that title (no redirect, no disambiguation page), resolved with the refresh's own query,
and belongs to the item kept or written; a rename's new name is an English (`en`, `en-*`, `mul`)
label or alias of the item kept or written - its entity page is read even when no quote cites it -
or the title of the article kept or written, with or without its bracketed qualifier, and the item
is carried by no other visible curated row (two rows named after one item is WD2's). A site failing
any check is **held** with its reason and asked again in a new round, the reason in its prompt.

**The rounds.** Round 1 asks every asked site; a re-ask round asks the held sites, at most twice
(`MAX_ROUNDS = 3`). Only the newest round is imported (an older one would overwrite newer
decisions), and `export-reask` and `plan` refuse until it is.

**The writes.** `run.py plan` (read-only live read, after the newest round's import) skips a site
whose links, URL, name or scope changed since the question's read, a replacement item another
curated site carries, and a replacement item decided for two sites (both are skipped:
`item-planned-for-another-site`, WD2's), and writes: link steps of at most 100 sites into
`output/remediation/qid_repair/l5/step-NNN/` through `qid_repair.render_split(removals=True)` - a
removal deletes exactly the journalled `(site_id, kind, value)` row and its reversal re-inserts it;
guard 6 refuses one new item planned for two sites and invariant 5 checks after the writes that
every item written is carried by exactly one curated site (both in the write only, not in the
reversal); invariant 4 refuses a site left without any link on an English-Wikipedia `source_url` -
the name lane `name-l5` (`output/remediation/mechanical_name_l5/`: `name` and its key in one
transaction, the key computed by Postgres and not written when a rename changes only case or
accents, the lane invariant refusing a key that is not the new name's), `SKIPPED.jsonl`,
`UNTRUSTED_LINKS.jsonl` (above) and `PLAN_COUNTS.json`. Everything that can refuse is computed
before the first file is written, and no step is written while any step directory holds another
plan. Lyra's next boot adds each new name to `unified_site_names` as a `label` row; the old name
stays there, so an exact search finds both.

**User-Agent.** `l5/web.py`: `AncientMapRemediation/1.0 (research; https://ancientnerds.com)` -
measured 2026-09-26, Wikimedia answers the bare `AncientMapRemediation/1.0 (research)` with 403
through `httpx` (the page fetcher's client) on all four URL shapes L5 reads, and 200 with the
project URL added; no contact address, no name.

```bash
$PY scripts/remediation/l5/run.py population            # read-only; refused once a round exists
$PY scripts/remediation/l5/run.py export --handoff output/remediation/l5/handoff-r1
# one Opus agent per batch (O11: up to 16 at a time); each agent's instruction:
$PY scripts/remediation/l5/run.py brief --round r1 --batch-id r1-b01     # ... r1-b16
$PY scripts/remediation/opus_handoff.py validate --dir output/remediation/l5/handoff-r1
$PY scripts/remediation/l5/run.py import --round r1     # fetches, checks, decides: DECISIONS.jsonl
# held sites, at most twice more (r2, r3), each in a new directory, after the newest import:
$PY scripts/remediation/l5/run.py export-reask --handoff output/remediation/l5/handoff-r2
#   brief / validate / import --round r2 as above
# before the plan: WD2's hide of 24aa135d has landed (the SQL under "Hand-offs to WD2")
$PY scripts/remediation/l5/run.py plan                  # read-only; ONCE, after the last import
$PY scripts/remediation/l5/run.py step check --step 1   # read-only: files = plan, old values hold
$PY scripts/remediation/l5/run.py step rehearse --step 1
$PY scripts/remediation/l5/run.py step probe-guards --step 1   # guards 1, 2, 3, 5, 6, invariant 4
$PY scripts/remediation/l5/run.py step apply --step 1
$PY scripts/remediation/l5/run.py step verify --step 1
$PY scripts/remediation/l5/run.py step rehearse-rollback --step 1
#   ... --step 2 when the plan has one
$PY scripts/remediation/mechanical/apply.py --lane name-l5 --emit
$PY scripts/remediation/mechanical/apply.py --lane name-l5 --rehearse
$PY scripts/remediation/mechanical/apply.py --lane name-l5 --probe-guards
$PY scripts/remediation/mechanical/apply.py --lane name-l5 --apply
$PY scripts/remediation/mechanical/apply.py --lane name-l5 --verify
$PY scripts/remediation/mechanical/apply.py --lane name-l5 --rehearse-rollback
```

`plan` runs once: a step directory that holds a plan is never replaced (its ROLLBACK.sql may be
the only undo of a landed write), and a site written by step 1 reads as changed on a second plan.
`probe-guards` probes each guard the step can exercise: guard 2 needs a `source_url` row, guard 5
a replaced item, guard 6 a replaced item and a second site's item row in the same step; invariant 5
is the after-write form of guards 5 and 6 and cannot fire while they pass (its SQL is tested in
`tests/remediation/test_l5.py`), so it is not probed.
Exit codes of `step`: 0 OK, 1 REFUSED, 3 NOT COMMITTED, 4 COMMITTED (psql unclean, read-back
confirmed), 5 OUTCOME UNKNOWN, 6 COMMITTED BUT NOT CONFIRMED, 7 a rehearsal or probe fell short. An
outcome is settled from the journal (`run_stamp = '2026-09-26_l5-links-NNN'`), never by a retry.
Files: `output/remediation/l5/` (`POPULATION.jsonl`, `COUNTS.json`, `ROUNDS.jsonl`,
`answers/<round>.jsonl`, `DECISIONS.jsonl`, `TITLES.json`, `PAGES.jsonl`, `SKIPPED.jsonl`,
`UNTRUSTED_LINKS.jsonl`, `PLAN_COUNTS.json` versioned; `export/READ.json`, `handoff-*`, `pages/`
local).

#### Nr. 8 — the six local copies of Commons-deleted files (a VPS step, run by the orchestrator)

Decided: delete them; the `wiki_images` rows (70233, 80453, 87351, 87352, 97070, 107331, all
`is_excluded`) and their journal rows stay as the record. The files are root-owned, the `deploy`
user is in the `docker` group, so the deletion runs as root in a throw-away container without
network. `public/data/images/` is ignored by git, so the deploy's `git clean -fd` neither restores
nor touches them.

Pre-check, read-only - all four must hold before the deletion:

```bash
# 1. the database: the six rows excluded, not a hero, and nothing live names the files
#    (expected: 6 rows t|f, then 0, 0, and 5 directories each of exactly one site)
ssh ancientnerds "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map -At" <<'SQL'
SELECT w.id, w.is_excluded, w.is_hero, left(w.site_id::text, 8) || '/' || w.filename AS file FROM wiki_images w WHERE w.id IN (70233, 80453, 87351, 87352, 97070, 107331) ORDER BY w.id;
SELECT 'live rows naming the files', count(*) FROM wiki_images w WHERE w.is_excluded IS NOT TRUE AND (left(w.site_id::text, 8), w.filename) IN (('403e3c53', 'Infopanel hardloopbaan Olympia.webp'), ('75374382', 'Athens Acropolis Stoa of Eumenes II (28437052525).webp'), ('9a9a0dca', 'Dedan_tomb_1.webp'), ('9a9a0dca', 'hero.webp'), ('cb039044', 'Athens Acropolis Sanctuary of Dionysos Eleuthereus (28154647030).webp'), ('fe252099', 'A Minecraft Movie McDonald''s promotion - 3 May 2025.webp'));
SELECT 'thumbnails naming the files', count(*) FROM unified_sites WHERE thumbnail_url LIKE ANY (ARRAY['%/403e3c53/Infopanel hardloopbaan Olympia.webp', '%/75374382/Athens Acropolis Stoa of Eumenes II (28437052525).webp', '%/9a9a0dca/Dedan_tomb_1.webp', '%/9a9a0dca/hero.webp', '%/cb039044/Athens Acropolis Sanctuary of Dionysos Eleuthereus (28154647030).webp', '%/fe252099/A Minecraft Movie McDonald''s promotion - 3 May 2025.webp']);
SELECT 'sites sharing a directory', count(*) FROM unified_sites WHERE left(id::text, 8) IN ('403e3c53', '75374382', '9a9a0dca', 'cb039044', 'fe252099');
SQL
# 2. the files: list the six (and fail if one is missing), their sha256, and whether alpine is there
ssh ancientnerds 'cd /var/www/ancientnerds/public/data/images/wiki && ls -ln -- "403e3c53/Infopanel hardloopbaan Olympia.webp" "75374382/Athens Acropolis Stoa of Eumenes II (28437052525).webp" 9a9a0dca/Dedan_tomb_1.webp 9a9a0dca/hero.webp "cb039044/Athens Acropolis Sanctuary of Dionysos Eleuthereus (28154647030).webp" && find fe252099 -maxdepth 1 -name "A Minecraft Movie McDonald*s promotion - 3 May 2025.webp" -exec ls -ln -- {} + && sha256sum -- 9a9a0dca/*.webp && docker image ls alpine'
# 3. the web: each answers 200 now (fe252099/hero.webp is the control that must stay)
for f in "403e3c53/Infopanel%20hardloopbaan%20Olympia.webp" "75374382/Athens%20Acropolis%20Stoa%20of%20Eumenes%20II%20%2828437052525%29.webp" 9a9a0dca/Dedan_tomb_1.webp 9a9a0dca/hero.webp "cb039044/Athens%20Acropolis%20Sanctuary%20of%20Dionysos%20Eleuthereus%20%2828154647030%29.webp" "fe252099/A%20Minecraft%20Movie%20McDonald%27s%20promotion%20-%203%20May%202025.webp" fe252099/hero.webp; do
  curl -s -o /dev/null -w "%{http_code} $f\n" -A "AncientMapRemediation/1.0 (research)" "https://ancientnerds.com/data/images/wiki/$f"
done
# 4. the static export: the globe builds a site's `im` as /data/images/wiki/<id8>/<hero_filename>
#    (pipeline/static_exporter.py), so an export older than the 2026-09-25 exclusion still names
#    9a9a0dca/hero.webp (this machine's March export does: index.json, details/africa.json,
#    details/middle_east.json and their .gz). Expected: "no static JSON names one of the six".
#    "NAMED BY THE STATIC EXPORT" means: run Nr. 8 after WF's static export instead.
ssh ancientnerds 'sh -s' <<'SH'
cd /var/www/ancientnerds/public/data/sites
set -- -e '403e3c53/Infopanel hardloopbaan Olympia.webp' \
  -e '75374382/Athens Acropolis Stoa of Eumenes II (28437052525).webp' \
  -e '9a9a0dca/Dedan_tomb_1.webp' -e '9a9a0dca/hero.webp' \
  -e 'cb039044/Athens Acropolis Sanctuary of Dionysos Eleuthereus (28154647030).webp' \
  -e "fe252099/A Minecraft Movie McDonald's promotion - 3 May 2025.webp"
named=$(grep -rlF --include='*.json' "$@" .; find . -name '*.json.gz' | while read -r f; do
  if gzip -dc "$f" | grep -qF "$@"; then echo "$f"; fi
done)
if [ -n "$named" ]; then
  printf 'NAMED BY THE STATIC EXPORT - wait for the next static export:\n%s\n' "$named"
  exit 1
fi
echo "no static JSON names one of the six"
SH
```

Pre-check 4 was run locally (the script with only its `cd` pointed elsewhere): against this
machine's March export it listed those six files and exited 1 (5.5 min on Windows, the 87 MB
`index.json.gz` dominating); against a mock tree holding only `fe252099/hero.webp` in a `.json` and a
`.json.gz` it exited 0; with the McDonald's path added in a `.json.gz` it listed that file and
exited 1.

The deletion (reviewed 2026-09-26; the script was run against a mock of the six files and the
control: it removed exactly the six, left `fe252099/hero.webp`, and a second run exits 1 without
removing anything). It checks every file first and deletes nothing unless all six are there; the
McDonald's file is matched by a glob (`*` for the apostrophe) that must match exactly one file:

```bash
ssh ancientnerds 'docker run --rm -i --network none -v /var/www/ancientnerds/public/data/images/wiki:/w alpine sh -eu' <<'SH'
cd /w
set -- '403e3c53/Infopanel hardloopbaan Olympia.webp' '75374382/Athens Acropolis Stoa of Eumenes II (28437052525).webp' '9a9a0dca/Dedan_tomb_1.webp' '9a9a0dca/hero.webp' 'cb039044/Athens Acropolis Sanctuary of Dionysos Eleuthereus (28154647030).webp'
for f in "$@"; do test -f "$f"; done
test "$(find fe252099 -maxdepth 1 -name 'A Minecraft Movie McDonald*s promotion - 3 May 2025.webp' | wc -l)" -eq 1
rm -v -- "$@"
find fe252099 -maxdepth 1 -name 'A Minecraft Movie McDonald*s promotion - 3 May 2025.webp' -print -delete
SH
```

Post-check: the web loop of pre-check 3 again - the six answer 404 (the decision names
`/data/images/wiki/9a9a0dca/hero.webp`) and `fe252099/hero.webp` still 200. Browsers may keep a copy
for up to a day (`Cache-Control: public, max-age=86400`).

#### Measured 2026-09-26 (read-only)

| what | count |
|---|---|
| B2-L rows holding the country the decision replaces | 2 (Germany 107, Greece 402, Türkiye 218 curated rows) |
| Lyra alias rows whose key is not Postgres's key of their name | 11 on 6 sites, 0 colliding |
| curated rows whose key is not their name's key (the name lane's residual) | 0 |
| L5 population (read again 08:43Z after the review's fixes; nothing in production had moved) | 167: wave1-unresolved 1, wave2-unresolved 47, link-suspect 72, name-n7 46, found-by-we 1 |
| L5 asked | 159 (names asked 43 - the N7 names less Zoque's pinned rename and 2 retired; duplicate candidates 9); not asked: 8 retired |
| L5 asked on an English-Wikipedia `source_url` | 159 |
| L5 asked sites whose item another curated row carries | 56 (48 with a visible row) |
| L5 prompts (dry build from the read) | 3,997-5,928 characters, median 4,836; 16 batches of 10 |
| Chiapa de Corzo (`24aa135d`) / Zoque row | both visible, scope NULL: WD2's hide has not landed |
| journal maximum `remediation_change_log.id`; rows under L5's stamps | 73911; 0 |
| Nr. 8 image rows excluded / live rows naming the files / thumbnails naming them | 6 / 0 / 0; each file served 200 |

---

## 13. Cost model

**Price assumptions** (checked 2026-09-19): Opus 5 $5/$25 per MTok · Sonnet 5 $2/$10 · Haiku 4.5 $1/$5 ·
cache read Opus $0.50 / Sonnet $0.20 · Batch API −50 %.
Computed conservatively at 90 % input / 10 % output **without** cache credit; with realistic prompt caching
(70 % cache hits) the text workstream drops to roughly 60 %.

**Measured anchor:** ~40,000 tokens per two-stage-reviewed site record;
run 1 = 36 agents / 3,653,051 tokens / 37 min at 10–14 parallel.

| Workstream | Volume | LLM | Cost | Runtime |
|---|---|---|---|---|
| Deterministic full census | 5,004 sites | no | ~$0 (development only) | 1 day |
| HEAD sweep of reference links | 15,230 URLs | no | $0 | ~45 min |
| Wikidata claim comparison | 4,618 QIDs, ~93 batches | no | $0 | ~4 min |
| Two-stage factual audit (reduced) | ~2,217 sites | yes | ~$350 | 2–3 nights |
| Sourced rewrites | 2,787 sites | yes — **most expensive** | $600–1,230 | ~42 h at 12 parallel |
| Hero re-derivation | 3,858 | no | $0 | ~30 min |
| Image VLM | 25,000–30,000 calls | VLM | **$0 on the MiniMax flat plan** | binding: weekly budget |
| Follow-through + acceptance | 5,004 + 200 | partly | ~$72 | ~1 day |

| Scenario | USD | Calendar time | Not covered |
|---|---|---|---|
| (a) Minimal — shorts-critical only | 650–900 | ~4 days | `description` as Google snippet stays unverified; heroes stay at 800 px |
| (b) Full — all 5,004 to 100 % | 2,200–3,400 | ~10 days | the 386 sites without a QID keep no external cross-check; the false-negative rate stays unknown |
| **(c) Recommended — middle path** | **1,100–1,400** | **~6 days** | long descriptions of unflagged, non-shorts-eligible sites (a 5 % control sample measures risk rather than repairing it) |

> **Billing note:** all USD figures are API list-price equivalents. If the work runs in a subscription
> environment as the assessment did, the marginal cost is $0 and the binding constraints are the 5-hour and
> weekly quotas.

**Collision situation at assessment time (favourable):** MiniMax weekly budget at **9 %**, while the batch gate
requires roughly 20 % → Theo will start no new paper before Monday 00:00 UTC despite 26 queued batch rows.
The Lyra orchestrator runs hourly; its last cycle took 11.9 s and touched 0 rows.
Its only writing contact with `unified_sites` comes **not** from the cycle but from `_run_migrations()` on
container restart (10.1).

---

## 14. Open decisions

| # | Question | Options |
|---|---|---|
| O1 | **Image licensing in video** | (a) PD/CC0/No-restrictions only = 7,719 images — pushes shorts-eligible sites well below 2,708 · (b) accept CC BY-SA with an attribution line and carry the adaptation risk |
| O2 | **The 2,296 image-poor sites** | (a) acquire from Commons via the 1,448 sites with a missing/wrong P373 anchor · (b) a shorts format without stills · (c) no video for now |
| O3 | **The 904 ungrounded card texts** | **Resolved 2026-09-22 (design entry [6], card_texts):** same run, extractive - a card is condensed by code from the site's own published description (12, Phase 5) |
| O4 | EU AI Act disclosure for site pages and video | **Resolved for site pages by design (entry [6], licensing_and_ai_act):** graded by `_description_provenance.ai` - attribution line for selected text, the AI footnote for generated text, IPTC type in the JSON-LD; built 2026-09-23 (WB-D4). The exact wording of the line and the video part stay with Martin (`HUMAN_ONLY.md` A1; the shorts publishing step) |
| O5 | Text provenance versus Wikipedia | **Resolved by design:** W/S/T text is an adaptation of Wikipedia under CC BY-SA 4.0, the licence the curated layer already declares; per-site attribution (title, oldid permalink, licence link, change note); R wording is never published; quotes live only in the journal. The disclaimer/terms sentence awaits Martin's confirmation (`HUMAN_ONLY.md` A1) |

---

## 15. Appendix

### 15.1 Access

```bash
# Production DB, read-only
ssh ancientnerds "docker exec ancient_nerds_db psql -U ancient_map -d ancient_map -c \"SELECT ...\""

# Longer SQL from a file (docker exec WITHOUT -i, otherwise it eats stdin)
ssh ancientnerds "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map" < file.sql
```
Database `ancient_map`, user `ancient_map`. Containers: `ancient_nerds_db`, `ancient_nerds_api`.
The deploy user has Docker without sudo, but no general sudo.

### 15.2 Quality gate

```sql
SELECT source_id, count(*) AS total,
  round(100.0*count(*) FILTER (WHERE period_start IS NOT NULL)/count(*),1) AS period_pct,
  round(100.0*count(*) FILTER (WHERE site_type IS NOT NULL AND site_type NOT ILIKE 'Unknown')/count(*),1) AS type_pct,
  round(100.0*count(*) FILTER (WHERE country IS NOT NULL)/count(*),1) AS country_pct,
  count(*) FILTER (WHERE last_audited IS NOT NULL) AS audited
FROM unified_sites
WHERE source_id IN ('ancient_nerds','lyra','ancient_nerds_community')
GROUP BY 1 ORDER BY 2 DESC;
```

### 15.3 History: what actually happened in March 2026

Not an audit run in the procedural sense, but a manual `db.html` upload: **4,961 rows in 500 chunks of 10 sites**
via `POST /sites/batch-upload` between 12:30:21 and 13:25:41, followed two seconds after the last chunk by a
single `UPDATE unified_sites SET last_audited = NOW()`. Hence the identical timestamp on 4,997 rows.
`edited_by` is the uploader's Discord name, not an audit status.

Descriptions shrank in the process from an average of 802 to 521 characters (~1.76M characters removed,
4,985 of 4,996 changed). For the 2,217 sites that received citations between 03-06 and 03-14, the reduction
from 818 to 436 characters is **the verifier working as designed** (it strips unsupported sentences).
The prior state is preserved in snapshot `d4526691`.

The rollback documented in `ENRICHMENT_AUDIT.md:986-1012` via `raw_data->description_pre_enrichment` exists on
production for **0 of 1,759,675 rows** — `merge_verification()` writes the backup into the local dev database,
`package_for_upload()` does not serialise it, and `batch_upload_sites()` writes only `description_citations`
into `raw_data`. The key could never reach production, ever since its introduction on 2026-03-01 (`ef2fc34`).

### 15.4 Field visibility — this determines the blast radius of an error

| Field | Where it surfaces |
|---|---|
| `name`, `country` | canonical path (`sites_html.py:281-284`, `meta.ts:119-132`), `<title>`, `sitemap.xml`, JSON-LD. `country` additionally generates **its own indexed hub page per value** — live today: *"Archaeological Sites in Georgia (country) (27)"* and *"… in Baltic Sea (1)"* |
| `site_type` | unfiltered in the `<title>` of **all 5,004** detail pages; drives the H2 sections of the country page |
| `description` | verbatim the Google snippet source (`meta.ts:261/289`) and the JSON-LD `Place.description` |
| `period_start` | **default point colour on the globe** (`App.tsx:182` → `sitesRenderer.ts:150-154`); feeds the time span in the country meta description — live it reads *"Spanning 8500 BC – 1994 AD"* because of the museum sites |
| `wiki_images` | `og:image`, JSON-LD `image`, LCP image. `thumbnail_url` is only a fallback now |
| **`card_description`** | **on no indexed page — but it is the spoken narration and the caption of every short** (`pipeline/video/__main__.py:328-331`, `shorts_render.py:860`) |
| `civilization`, `rarity_tier`, `total_power` | pure game/pipeline fields, no SEO surface |
| `site_external_ids` | entirely internal |
