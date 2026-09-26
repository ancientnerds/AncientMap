# WD1: the structured fields - coordinates, period, site type, source URL

Status: **built 2026-09-26; harvested and classified read-only on the population; nothing written.**
FINISH_PLAN_2026-09-26 workstream WD, lane WD1. The code is `scripts/remediation/fields/`; the
writer is the mechanical one (`scripts/remediation/mechanical/apply.py`, lane family
`fields-wd1-<wave>-s<NNN>` in `mechanical/lane.py`). Read `FIELD_CONTRACT.md` (the write path, the
column shapes) and `PROJECT_LESSONS.md` before a production step.

## 1. What WD1 decides, and under which rule

| field | written columns | what an Opus answer may do | exhausted after 3 rounds |
|---|---|---|---|
| coordinates | `lat`, `lon`, `geom` (`SRID=4326;POINT(lon lat)`: `geom` is `geometry(Point,4326)` and no trigger keeps it in step with `lat`/`lon` - read on production 2026-09-26, PostGIS 3.4.3) | keep, replace (> 1 km away), unresolved | **held** - `lat`/`lon` are NOT NULL (FIELD_CONTRACT 3); the stored point stays and WF counts it as unsourced |
| period_start | `period_start`, and `period_name` derived as its bucket (`categorize_period`, the period-name lane's rule, checked against the frontend's `categorizePeriod`) | keep (same bucket), replace, clear | cleared, and its label with it |
| site_type | `site_type` (one of `CANONICAL_TYPES`, a fixed point of `normalize_site_type` - FIELD_CONTRACT 2.1) | keep, replace, clear | cleared |
| source_url | `source_url` (a public page about this very site: served 2xx at that URL, not redirected elsewhere; on Wikipedia an article of its own) | keep, replace, clear | cleared |

The owner's rule is O6 (2026-09-26): **"Belegt ersetzen, sonst leeren"** - a field is replaced only
with a sourced value, else emptied. "Sourced" means: at least two verbatim quotes from two
independent source families (one Wikipedia article in any language, its Wikidata item and Commons are
one family; otherwise the registrable domain), every quote found by machine in its page as fetched
once (`opus_audit/quotes.py`), plus the field's own checks (`fields/answers.py`: a coordinate quote
holds the point within 1 km and is written no coarser than whole arcminutes; a period quote carries a
date; a type quote holds a word of the type; a source_url is quoted from its own page and names the
site). O8 lets every accepted step go live without asking.

HUMAN_ONLY_DECISIONS_2026-09-26 routes these items here: **B1-K** (coordinates: the 171 open cases,
the witness cases, the stacked points, Kirkûk and Qsarnaba), **B3** (the 42 sites without a
source_url get a sourced one or stay empty), **B13** (the 21 "both wrong" cells, as seeds), **Nr. 4**
(Ahin Posh Tape's point - its stored point is ~95 km from every witness, so the classification asks
it). Ordering constraint from the same file: **L5 (B1-L/B1-N, the link and name wave on up to 120
sites) runs before the harvest that WD1 trusts** - otherwise P625, P571 and the sitelinks come from
generic or wrong items.

## 2. The pieces

| module | does | reads | writes |
|---|---|---|---|
| `harvest.py` | the shared, read-only harvest (WD2 reads it too; the layout is a contract): one SELECT on production, then Wikidata entities (50 per request), the P31 classes, each item's English article coordinates, each stored source_url (a Wikipedia title through its wiki's API, any other page by one GET). User-Agent `AncientMapRemediation/1.0 (research)`, no contact address; requests go through `fields/transport.py` (Wikimedia and UNESCO refuse httpx's own TLS handshake with that agent). Paced, cached, resumable; a record of a URL the site no longer holds is asked again | production (1 SELECT), the web (GET only) | `<root>/SITES.jsonl`, `entities/<QID>.json`, `CLASSES.json`, `enwiki/<QID>.json`, `urls/<site_id>.json`, `HARVEST.json`, `cache/` |
| `seeds.py` | the fields an earlier reading found wrong: the counted WRONG verdicts of the acceptance `draw-2026-09-25b` stage 1 (canaries left out; `period_name` asks `period_start`) and B13's 21 cells | `acceptance/draw-2026-09-25b/`, `mechanical_wrong_both/SKIPPED.jsonl` | `<run>/SEEDS.jsonl` |
| `classify.py` | one deterministic status per field: CONFIRMED / CONFLICT / MISSING (rules in its docstring), flags from the seeds, the P31 table `p31_site_types.json` (766 classes, pinned by sha256) | the harvest, `STORED.jsonl` (1 SELECT), `SEEDS.jsonl` | `<run>/CLASSIFIED.jsonl`, `COUNTS.json` |
| `handoff.py` | the Opus handoff: `export` (one question per site with exactly its asked fields, batches of 8 by country and name), `brief` (a batch agent's full instruction), `check-answer` (shape and page-free checks of one answer), `import` (parse, fetch each quoted page once, quote-check, decide), `export-reask` (rounds 1 and 2), `status` | `CLASSIFIED.jsonl`, the answers | `ROUNDS.jsonl`, `ATTEMPTS.jsonl`, `DECISIONS.jsonl`, `REASK.json`, `PAGES.jsonl`, `pages/` |
| `answers.py` | the strict answer parser and every check that needs no page (used by `check-answer` and `import`) | - | - |
| `plan.py` | the journalled write: `wave` (the sites with a replace or clear, or a label that is not its start's bucket, cut into steps of 100 sites), `step` (one step's plan from a read-only read), `accept` (the step read back, cell by cell), `status` | `DECISIONS.jsonl`, production (read-only) | `write/<wave>/WAVE.json`, `write/<wave>/sNNN/` |

Where the site's item comes from (measured read-only 2026-09-26): `site_external_ids`
(`kind = 'wikidata_qid'`): 4,633 of the 5,004 curated sites, 4,564 of the 4,926 not retired.
`card_stats.wikidata_qid` is NULL on every curated card and `raw_data` holds no item key (its keys are
`_description_provenance` and `description_citations` only).

## 3. The runbook

From the repository root of the main checkout, with the main venv. Every step names its gate.

```bash
PY=./.venv/Scripts/python.exe
F=scripts/remediation/fields
A=scripts/remediation/mechanical/apply.py
R=output/remediation/fields/wd1                 # part 1, "conflict" (default of every --out/--run)
R2=output/remediation/fields/wd1-rest           # part 2, "rest"
H=output/remediation/handoff/fields-wd1         # part 1's rounds: $H-r0, $H-r1, $H-r2
H2=output/remediation/handoff/fields-wd1-rest   # part 2's rounds: $H2-r0, $H2-r1, $H2-r2
```

Argument positions differ per script: `classify.py --out DIR <command>` (before the command);
`seeds.py build --out DIR`, `handoff.py <command> --run DIR`, `plan.py wave --run DIR` (after it).

### 3.1 Harvest (read-only; after L5 is accepted)

1. `$PY $F/harvest.py export` - SITES.jsonl and HARVEST.json from one SELECT. Gate: refuses an empty
   export and an item id that is not `Q<digits>`. (`--sample N --seed S` draws a reproducible sample
   of sites that are not retired, for a measurement.)
2. `$PY $F/classify.py export` - `$R/STORED.jsonl`, **straight after step 1** (one SELECT). The
   classification refuses a site whose point or URL differs between the two exports.
3. `$PY $F/harvest.py fetch` - entities, classes, articles, source URLs, each step recorded in
   HARVEST.json when it finishes. Re-run it until every step reports nothing fetched (entities
   `fetched: 0`, classes `fetched: 0`, enwiki `articles: 0`) and the URL step asks only what failed; a
   Wikimedia failure stops the run and nothing half-written stays. `--refetch-failed` asks the web
   pages that failed (network error, 5xx) once more. `$PY $F/harvest.py status` shows the coverage
   from the files. Measured 2026-09-26: export 00:08 UTC, every step finished by 02:06 UTC; the
   web-page step alone took about 50 minutes (267 GETs, 60 s timeout, 1 s between two requests to one
   host).

### 3.2 Classify (files only)

4. `$PY $F/seeds.py build` - `$R/SEEDS.jsonl` (65 seeds on 54 cells of 46 sites on 2026-09-26).
   Gate: the classification's own reader accepts the file; a final verdict that is not its counted
   attempt's is refused.
5. `$PY $F/classify.py unmapped` - must print `[]`. Otherwise add each class to
   `p31_site_types.json` (kind `site` / `generic` / `container` / `other`, canonical types only),
   review, and move `classify.TABLE_SHA256` in the same commit (the table is refused until the pin
   moves; the classification refuses a class the table lacks).
6. Part 1: `$PY $F/classify.py classify --part conflict` - `$R/CLASSIFIED.jsonl` and `COUNTS.json`
   for the sites with a field a machine source contradicts or a seed flags (**1,349 sites, 3,974
   fields** on 2026-09-26). Part 2, cut from the same exports:
   `mkdir -p $R2 && cp $R/STORED.jsonl $R/SEEDS.jsonl $R2/ && $PY $F/classify.py --out $R2 classify --part rest`
   (**3,577 sites, 3,403 of them asked, 5,312 fields** - almost all only because no machine source
   dates their start). Each part runs 3.3 and 3.4 on its own, part 1 first, so the contradicted
   fields are decided and written first; the parts are disjoint, so neither's writes touch the
   other's sites. `--part all` takes every site in one run instead. Read COUNTS: `sites_asked`,
   `fields_asked`, `flagged_only` (fields asked only because of a seed), `stacked_points`,
   `seeds.sites_not_classified` (retired sites - nothing of theirs is written).

### 3.3 Ask Opus (the handoff; no model is called by the code)

For part 1 `RUN=$R HO=$H`; for part 2 `RUN=$R2 HO=$H2`.

7. `$PY $F/handoff.py export --run $RUN --handoff $HO-r0` - one question per asked site, batches of
   8 (part 1: 169 batches; part 2: 426). Gate: a round is exported once, into an empty directory of
   its own.
8. For each batch `B` of `$RUN/ROUNDS.jsonl` (14-16 agents in parallel, O11; batches are independent
   and each agent's scratch is `$HO-r0-scratch/B/`): start one fresh Opus agent with the text of
   `$PY $F/handoff.py brief --run $RUN --handoff $HO-r0 --batch-id B`. The agent researches each
   site, checks its answer with `handoff.py check-answer` (the shape and every page-free rule, per
   field; exit 1 with the problems) and records it with `opus_handoff.py answer` (write-once).
9. `$PY scripts/remediation/opus_handoff.py validate --dir $HO-r0` - clean: every question answered,
   in shape, by Opus, nothing stale or orphaned.
10. `$PY $F/handoff.py import --run $RUN` - every round's answers: each round validated again, the
    prompt re-rendered and matched to the manifest's sha256, parsed, each quoted page fetched once,
    each quote checked, each source_url value resolved (2xx, not redirected; on Wikipedia not
    missing, not a redirect, not a disambiguation page). Writes ATTEMPTS.jsonl, DECISIONS.jsonl,
    REASK.json and PAGES.jsonl.
11. While REASK.json names fields: `$PY $F/handoff.py export-reask --run $RUN --handoff $HO-r1`, then
    8-10 on `$HO-r1` (and once more on `$HO-r2`). After round 2 a field without a counted answer is
    decided `clear` (coordinates: `unresolved`, held). `$PY $F/handoff.py status --run $RUN` shows
    the decisions.

### 3.4 Write (journalled, steps of at most 100 sites)

12. `$PY $F/plan.py wave --wave W --run $RUN` with an unused date label per part (e.g. `2026-09-27`
    for part 1, `2026-09-27b` for part 2) - `output/remediation/fields/wd1/write/W/WAVE.json`,
    pinned to DECISIONS.jsonl and CLASSIFIED.jsonl by sha256. Gate: refuses while REASK.json names a
    field; a wave is planned once.
13. For N = 1, 2, ... (lane `L=fields-wd1-W-s00N`):
    1. `$PY $F/plan.py step --wave W --step N` - a read-only read of the step's sites and
       their journals: PLAN.jsonl, SKIPPED.jsonl (every refusal with its reason, section 4), PLAN.md,
       ROLLBACK.sql (written before any statement, pinned to the plan). Gate: refuses until step
       N-1 is ACCEPTED with 0 deviations, when DECISIONS.jsonl is not the wave's, and when the step is
       already emitted or accepted. A step with nothing to write leaves NOTHING_TO_WRITE.json; go
       to ix.
    2. `$PY $A --lane $L --emit` - APPLY.sql, pinned to the plan; refuses without the undo.
    3. `$PY $A --lane $L --verify` - the read-only read-back before (journal rows for the stamp 0;
       the period pair, geom-not-point and the empty-field counts).
    4. `$PY $A --lane $L --rehearse` - the statement with ROLLBACK: the NOTICE `WD1 field correction:
       <n> of <n> planned cell(s) changed and journalled over <m> curated site(s)`, nothing kept.
    5. `$PY $A --lane $L --probe-guards` - exit 0: each corrupted copy is refused by its own guard -
       guard3-foreign-old-value, guard2-no-op, guard2-foreign-column, guard2-too-long,
       guard1-other-source, guard4-not-owned, invariant-geom (a planned site's geom is its point),
       invariant-period_name (its period_name is the bucket of its period_start). guard2-too-long
       and guard4-not-owned run when the step plans a `period_name` or `site_type` cell (the columns
       with a width and an owned vocabulary); an invariant the plan cannot probe (no cell of its
       column in this step) is printed as not probed.
    6. `$PY $A --lane $L --apply` - `APPLY OK`. Exit 3 NOT COMMITTED, 4/6 COMMITTED (read the
       message), 5 OUTCOME UNKNOWN: read the journal for the stamp before anything else, never apply
       twice.
    7. `$PY $A --lane $L --verify` - journal rows for the stamp = the plan's cells; geom-not-point
       and the period-pair residual not raised by this step.
    8. `$PY $A --lane $L --rehearse-rollback` - on the landed rows: the NOTICE, ROLLBACK, the cells
       still holding the written values.
    9. `$PY $F/plan.py accept --wave W --step N` - ACCEPTED.json with **0 deviations**:
       every planned cell holds its new value, one journal row per cell with exactly the planned old
       and new value, no other stamp wrote a planned cell since, no planned site breaks an invariant.
       Any deviation refuses the step (no ACCEPTED.json) and stops the wave.
    10. Commit the step directory (`output/remediation/fields/wd1/write/W/s00N/`; REHEARSAL.sql
        stays out by .gitignore) with `$R/COUNTS.json`, `$R/SEEDS.jsonl` and `$R2/COUNTS.json`.
    `$PY $F/plan.py status --wave W` shows each step's state.
14. After the last step: the static export, IndexNow and the push (O8, WF). Archive the runs
    (`$R`, `$R2`, `$H-r*`, `$H2-r*`) as a tgz beside the other run archives - DECISIONS.jsonl holds
    every answer's quotes and reasoning and is not versioned (bulk). **Hand-off to the scope check
    (WD2):** a written start can move a site out of the E3 window (rest of the world to 500 AD, the
    Americas and Oceania to 1500 AD - O7), and a cleared start makes it an E3 case (b), a site without
    a date (HUMAN_ONLY_DECISIONS B13); WD1 writes no `scope_status`.

### 3.5 Undo

Every step's `ROLLBACK.sql` restores each old value under the stamp `<wave>_fields-wd1-s<NNN>-rollback`,
conditioned on the value the step wrote (a cell another writer changed since is refused, and the
whole reversal with it). Rehearsed in 13.viii. Running it is a decision, never automatic:
`ssh ancientnerds "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map -v ON_ERROR_STOP=1" < ROLLBACK.sql`,
then `$A --lane $L --verify`. Reverse steps newest first. The site invariants are not checked on a
reversal: it restores the state before the write, which may not have held them (one curated site
carried a NULL `geom` on 2026-09-26).

## 4. What each write refuses (SKIPPED.jsonl reasons)

| reason | meaning |
|---|---|
| `not-a-curated-live-site` | the site is retired or not `ancient_nerds` now |
| `moved-since-classification` | the row no longer holds the value the decision was made about |
| `journal-disagrees` / `journal-*` | the column's journal does not end at the live value (a write around the journal) |
| `coordinates-unresolved` | no two sources for the point: held, the stored point stays |
| `country-changes` | the new point lies in another country than the stored one (`bcases.classify.country_after_move`): held, a country is the country lanes' question |
| `geom-not-point` | the live geom is neither NULL nor the live point |
| `period-end-precedes-start` | the new start lies after the stored `period_end` (a `period_end` of 0 is none, as in the codebase's `period_end or period_start`; `period_end` was NULL on every curated site in the 2026-09 census) |
| `period-start-journal` / `implementations-disagree` | the label cannot follow its start (a start written around the journal; the Python and the frontend buckets disagree) |

## 5. Measured 2026-09-26 (read-only; no write)

How: `harvest.py --root output/remediation/fields/harvest-sample-200 export --sample 200 --seed
20260926` and `fetch` on that root, `classify.py export`, `seeds.py build`, `classify.py --root
output/remediation/fields/harvest-sample-200 classify --part all` for the sample; the population the same without `--sample` (the default root), classified `--part all`,
`conflict` and `rest`. Production was asked four export SELECTs (two harvest exports, two
stored-field exports) plus the coverage and catalog SELECTs behind sections 1 and 2; the web only GET. The classification is files-only
and was re-run on the final code: `--part all` reproduced the earlier CLASSIFIED.jsonl in every
status (65 lines differ only in the source_url evidence of pages the interrupted `--refetch-failed`
asked again - fetch time and error text, no status).

### 5.1 Harvest coverage (population, 4,926 sites not retired)

| what | sites |
|---|---|
| with a Wikidata item (`site_external_ids`) | 4,564 (4,486 distinct items; 58 items are shared by 136 sites) |
| with an English article (sitelink) | 4,543 |
| coordinate witnesses: P625 and the article's point / P625 only / article only / none | 3,856 / 401 / 3 / 666 |
| a dated start before 1500 AD on the item (P571, P580, P1319; items in identity doubt not read) | 343 (41 more carry only a modern date, which is not read) |
| P31 classes: a specific site class / generic only / container or other only / no class / no item | 2,492 / 1,002 / 906 / 164 / 362 |
| source_url: a Wikipedia article / another web page / empty / a search or proxy URL / malformed | 4,602 / 263 / 42 / 13 / 6 |

The harvest on disk: 4,536 entity files (all 5,004 curated sites' items), 766 P31 classes, 4,515
article files (3,835 with coordinates), 5,004 URL records.

### 5.2 Expected statuses - the sample of 200 and the population

| field | sample 200: CONFIRMED / CONFLICT / MISSING | population 4,926: CONFIRMED / CONFLICT / MISSING |
|---|---|---|
| coordinates | 138 / 46 / 16 | 3,356 / 948 / 622 |
| period_start | 13 / 3 / 184 | 233 / 68 / 4,625 |
| site_type | 112 / 40 / 48 | 2,738 / 763 / 1,425 |
| source_url | 168 / 27 / 5 | 4,093 / 617 / 216 |
| sites asked / fields asked | 188 / 369 | 4,752 / 9,286 |
| item in identity doubt | 25 | 494 |

The sample's rates match the population's within sampling error (coordinates CONFLICT 23 % vs 19 %,
site_type 20 % vs 15 %, source_url 14 % vs 13 %).

What the CONFLICTs are (population):

- **coordinates 948**: the item is a container (settlement, island, hill, museum) none of whose
  classes holds the stored type - 494; the stored point 1-10 km from a witness - 306; more than
  10 km - 119; a point another live site holds exactly (a placeholder) - 24; P625 and the article
  disagree - 5.
- **period_start 68**: the item's earliest start lies wholly in another bucket. The 4,625 MISSING are
  4,079 items without a dated start, 491 items in identity doubt, 13 empty values without a date and
  42 spans that straddle the stored bucket (a century- or millennium-precision date).
- **site_type 763**: identity doubt 494; a specific site class that names other types 269. MISSING:
  only generic classes 899, no item 362, an item without P31 164.
- **source_url 617**: identity doubt 474; a redirect to another article 34; dead (a missing article,
  404/410) 28; a redirect to another page 17; a search or proxy URL 13; a redirect into a section 8;
  malformed 6; a disambiguation page 4; another item's article 33. MISSING: a page whose title names
  nothing of the site 48, empty 42, an article no item confirms 39, not readable by machine 87
  (timeouts 36 - mostly the Megalithic Portal -, connection errors 19, HTTP 403 16, 5xx 14, 406/429
  2).

### 5.3 How the machine rates what an earlier reading found wrong

The 54 seed cells (the acceptance's stage-1 WRONG verdicts and B13's cells) by the machine's own
status, before the seed flag is applied: coordinates 2 CONFLICT, 2 MISSING (of 4); period_start 2
CONFLICT, 28 MISSING, 1 CONFIRMED (of 31); site_type 10 CONFLICT, 5 MISSING, 1 CONFIRMED (of 16);
source_url 3 CONFLICT (of 3). So the machine alone asks 52 of the 54 known-wrong cells; the two it
confirms (the Temple of Bel's start - P580 AD 17 against an older Hellenistic sanctuary; the Baltic
Sea Anomaly's type - the class "anomaly" allows "Underwater structures") are interpretive and reach
Opus through their seed. A CONFIRMED field is asked of nobody, so this escape rate (2 of 54) is the
lane's blind spot, and the final WF measurement is where it shows.

### 5.4 The load

Part 1 (conflict): 1,349 sites, 3,974 fields, 169 batches of 8 - at 16 agents about 11 rounds of
agents. Part 2 (rest): 3,403 asked sites, 5,312 fields, 426 batches. Stage-1 context: 22 of 60
period_name, 16 period_start, 8 site_type, 7 coordinates and 4 source_url verdicts were WRONG.
