# WD1: the structured fields - coordinates, period, site type, source URL

Status: **built 2026-09-26, reviewed and fixed the same day (section 6); harvested and classified
read-only on the population; nothing written.** FINISH_PLAN_2026-09-26 workstream WD, lane WD1. The
code is `scripts/remediation/fields/`; the writer is the mechanical one
(`scripts/remediation/mechanical/apply.py`, lane family `fields-wd1-<wave>-s<NNN>` in
`mechanical/lane.py`). Read `FIELD_CONTRACT.md` (the write path, the column shapes) and
`PROJECT_LESSONS.md` before a production step.

## 1. What WD1 decides, and under which rule

| field | written columns | what an Opus answer may do | no counted answer after 3 rounds |
|---|---|---|---|
| coordinates | `lat`, `lon`, `geom` (`SRID=4326;POINT(lon lat)`: `geom` is `geometry(Point,4326)` and no trigger keeps it in step with `lat`/`lon` - read on production 2026-09-26, PostGIS 3.4.3), all three or none | keep, replace (> 1 km away), unresolved | **held** (`unresolved`) - `lat`/`lon` are NOT NULL (FIELD_CONTRACT 3); the stored point stays and WF counts it as unsourced |
| period_start | `period_start`, and `period_name` derived as its bucket (`categorize_period`, the period-name lane's rule, checked against the frontend's `categorizePeriod`); a start is written only with its label | keep (same bucket), replace, clear | **cleared**, and its label with it - or **held** when the last answer failed only on pages the checker could not read |
| site_type | `site_type` (one of `CANONICAL_TYPES`, a fixed point of `normalize_site_type` - FIELD_CONTRACT 2.1) | keep, replace, clear | cleared - or held (as above) |
| source_url | `source_url` (a public page about this very site: served 2xx at that URL, not redirected elsewhere, no `#fragment`; on Wikipedia an article of its own), written percent-encoded as httpx sends it | keep, replace, clear | cleared - or held (as above) |

The owner's rule is O6 (2026-09-26): **"Belegt ersetzen, sonst leeren"** - a field is replaced only
with a sourced value, else emptied. "Sourced" means: at least two verbatim quotes from two
independent source families (one Wikipedia article in any language, its Wikidata item and Commons are
one family; otherwise the registrable domain), every quote found by machine in its page as fetched
(`opus_audit/quotes.py`), plus the field's own checks (`fields/answers.py`):

* **coordinates** - every quote holds the point within 1 km, written no coarser than whole arcminutes;
* **period_start** - every quote carries a date, and at least one states the value itself: its year
  (thousands separators read) or its century or millennium beside that word (arabic, Roman, an
  English ordinal) - "12 hectares" and "3 km" do not source -3000;
* **site_type** - a quote holds a word of the type where a word begins ("temp" is not in
  "contemporary");
* **source_url** - a quote is from the value's own page (either spelling of its URL) and a quote
  names the site: a distinctive word of the stored name, or - for the 169 live names without one
  ("Huaca del Sol", "Seven Barrows") - the whole name or its core without a generic frame
  ("Archaeological Site of the Tombs of the Kings" -> "tombs of the kings"). The item's own labels
  are not read: the item was derived from the stored URL, so its label always names the page that
  URL leads to. The value carries no `#fragment` and is written as httpx sends it
  (`classify.url_form`: percent-encoded, the host in lower case; check-answer prints the form).

"The checker could not read the page" is not "no source exists": a field whose last answer failed
only on unreadable pages (no answer, 401/403/406/429, a server error, content it cannot read) is
**held** - neither written nor cleared - and listed in the wave's HELD.jsonl for WF's report. A quote
that is not on its page, or a page that is gone (404), still counts against the answer. O8 lets
every accepted step go live without asking.

**What is never worked around.** The lane sends one User-Agent, `AncientMapRemediation/1.0
(https://ancientnerds.com; research)` - the project's public site as its contact (Wikimedia's policy),
no personal data - through httpx's own transport. Measured 2026-09-26: Wikimedia answers an agent
without a contact with `403 Please respect our robot policy`, this one with 200. A host that
refuses it is recorded as unreadable, never evaded: Historic England's list, the Heritage Gateway,
whc.unesco.org (a Cloudflare challenge), Atlas Obscura and Britannica answered 403 on 2026-09-26;
the brief tells the agents so.

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
| `harvest.py` | the shared, read-only harvest (WD2 reads it too; the layout is a contract): one SELECT on production, then Wikidata entities (50 per request), the P31 classes, each item's English article coordinates, each stored source_url (a Wikipedia title through its wiki's API, any other page by one GET). The agent of section 1, httpx only. Paced, cached, resumable; a record of a URL the site no longer holds is asked again | production (1 SELECT), the web (GET only) | `<root>/SITES.jsonl`, `entities/<QID>.json`, `CLASSES.json`, `enwiki/<QID>.json`, `urls/<site_id>.json`, `HARVEST.json`, `cache/` |
| `seeds.py` | the fields an earlier reading found wrong: the counted WRONG verdicts of the acceptance `draw-2026-09-25b` stage 1 (canaries left out; `period_name` asks `period_start`) and B13's 21 cells | `acceptance/draw-2026-09-25b/`, `mechanical_wrong_both/SKIPPED.jsonl` | `<run>/SEEDS.jsonl` |
| `classify.py` | one deterministic status per field: CONFIRMED / CONFLICT / MISSING (rules in its docstring), flags from the seeds, the P31 table `p31_site_types.json` (769 classes, pinned by sha256); `--part conflict|rest|all`, `--pilot N --seed S` (a seeded sample of the part's asked sites), `--without RUN` (the part less a pilot) | the harvest, `STORED.jsonl` (1 SELECT), `SEEDS.jsonl` | `<run>/CLASSIFIED.jsonl`, `COUNTS.json` |
| `handoff.py` | the Opus handoff: `export` (one question per site with exactly its asked fields, batches of 8 by country and name), `brief` (a batch agent's full instruction), `check-answer` (shape and page-free checks of one answer), `import` (forget transient fetch failures, fetch each quoted page and each source_url value, quote-check, decide), `export-reask` (rounds 1 and 2; each re-ask shows why the last answer did not count), `pilot-report` (a finished pilot's gate), `status` | `CLASSIFIED.jsonl`, the answers | `ROUNDS.jsonl`, `ATTEMPTS.jsonl`, `DECISIONS.jsonl`, `REASK.json`, `PAGES.jsonl`, `pages/`, `PILOT.json` |
| `answers.py` | the strict answer parser and every check that needs no page (used by `check-answer` and `import`) | - | - |
| `plan.py` | the journalled write: `wave` (the sites with a replace or clear, or a label that is not its start's bucket, cut into steps of 100 sites; HELD.jsonl), `step` (one step's plan from a read-only read), `accept` (the step read back, cell by cell), `handoff` (what the wave wrote, for the derived stores), `status` | `DECISIONS.jsonl`, production (read-only) | `write/<wave>/WAVE.json` + `WAVE.sha256`, `HELD.jsonl`, `HANDOFF.json`, `write/<wave>/sNNN/` |

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
RP=output/remediation/fields/wd1-pilot          # part 1's pilot
R2=output/remediation/fields/wd1-rest           # part 2, "rest"
R2P=output/remediation/fields/wd1-rest-pilot    # part 2's pilot
H=output/remediation/handoff/fields-wd1         # handoff rounds: $H-r0 ..; $H-pilot-r0 ..;
                                                # $H-rest-r0 ..; $H-rest-pilot-r0 ..
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
   from the files. Measured 2026-09-26: the web-page step took about 50 minutes for 270 pages (60 s
   timeout, 1 s between two requests to one host); the API steps a few minutes.

### 3.2 Classify and cut the pilots (files only)

4. `$PY $F/seeds.py build` - `$R/SEEDS.jsonl` (65 seeds on 54 cells of 46 sites on 2026-09-26).
   Gate: the classification's own reader accepts the file; a final verdict that is not its counted
   attempt's is refused.
5. `$PY $F/classify.py unmapped` - must print `[]`. Otherwise add each class to
   `p31_site_types.json` (kind `site` / `generic` / `container` / `other`, canonical types only),
   review, and move `classify.TABLE_SHA256` in the same commit (the table is refused until the pin
   moves; the classification refuses a class the table lacks).
6. Part 1 and its pilot, from the same exports - the pilot first, then the part less the pilot:

   ```bash
   mkdir -p $RP && cp $R/STORED.jsonl $R/SEEDS.jsonl $RP/
   $PY $F/classify.py --out $RP classify --part conflict --pilot 80 --seed 20260927
   $PY $F/classify.py classify --part conflict --without $RP
   ```

   Part 2 the same way:

   ```bash
   mkdir -p $R2 $R2P && cp $R/STORED.jsonl $R/SEEDS.jsonl $R2/ && cp $R/STORED.jsonl $R/SEEDS.jsonl $R2P/
   $PY $F/classify.py --out $R2P classify --part rest --pilot 80 --seed 20260928
   $PY $F/classify.py --out $R2 classify --part rest --without $R2P
   ```

   Part 1 holds the sites with a field a machine source contradicts or a seed flags (**1,349 sites,
   4,013 fields** on 2026-09-26, section 5); part 2 every other site (**3,577 sites, 3,411 of them
   asked, 5,483 fields** - most only because no machine source dates their start). A pilot is 80
   asked sites (10 batches), drawn proportionally, so England (about a fifth of all questions) is in
   it as it is in its part. The four runs are disjoint: no run's writes touch another's sites. Read
   COUNTS: `sites_asked`, `fields_asked`, `flagged_only`, `stacked_points`, `pilot`, `without`,
   `seeds.sites_not_classified` (retired sites - nothing of theirs is written). `--part all` takes
   every site in one run instead.

### 3.3 Ask Opus (the handoff; no model is called by the code)

The runs go in this order, each through all its rounds before the next begins: **part-1 pilot
(`RUN=$RP HO=$H-pilot`), part 1 (`RUN=$R HO=$H`), part-2 pilot (`RUN=$R2P HO=$H-rest-pilot`),
part 2 (`RUN=$R2 HO=$H-rest`).** A part's bulk starts only after its pilot's gate (step 12) passes.

7. `$PY $F/handoff.py export --run $RUN --handoff $HO-r0` - one question per asked site, batches of
   8. Gate: a round is exported once, into an empty directory of its own.
8. For each batch `B` of `$RUN/ROUNDS.jsonl` (14-16 agents in parallel, O11; batches are independent
   and each agent's scratch is `$HO-r0-scratch/B/`): start one fresh Opus agent with the text of
   `$PY $F/handoff.py brief --run $RUN --handoff $HO-r0 --batch-id B`. The agent researches each
   site, checks its answer with `handoff.py check-answer` (the shape and every page-free rule, per
   field; exit 1 with the problems) and records it with `opus_handoff.py answer` (write-once).
9. `$PY scripts/remediation/opus_handoff.py validate --dir $HO-r0` - clean: every question answered,
   in shape, by Opus, nothing stale or orphaned.
10. `$PY $F/handoff.py import --run $RUN` - every round's answers: each round validated again, the
    prompt re-rendered and matched to the manifest's sha256, parsed; the kept fetch of every cited
    URL that failed transiently (no answer, 429, 5xx) forgotten and fetched again (`refetched` in the
    output; a 401/403/406 is kept - it is the host's answer); each quoted page and each source_url
    value fetched, each quote checked, each source_url value resolved (2xx, not redirected; on
    Wikipedia not missing, not a redirect, not a disambiguation page - its item recorded). The latest
    counted answer of a field decides (an earlier round's answer may count once its page is read).
    Writes ATTEMPTS.jsonl, DECISIONS.jsonl, REASK.json and PAGES.jsonl. Gate: a field that counted at
    the last import must still count.
11. While REASK.json names fields: `$PY $F/handoff.py export-reask --run $RUN --handoff $HO-r1`, then
    8-10 on `$HO-r1` (and once more on `$HO-r2`). Each re-ask shows why the field's last answer did
    not count. Gate: refuses a REASK.json that names a field with a counted answer. After round 2 a
    field without a counted answer is decided `clear` - `held` when its last answer failed only on
    unreadable pages, `unresolved` (held) for coordinates. `$PY $F/handoff.py status --run $RUN` shows
    the decisions.
12. **The pilot's gate** (on `$RP` and `$R2P` only, after their last import):
    `$PY $F/handoff.py pilot-report --run $RUN` - PILOT.json with the fields cleared on exhaustion,
    overall and per country. **Exit 0 (PASS)**: at most 10 % of the pilot's fields cleared on
    exhaustion, and at most 20 % in every country with at least 10 fields (a chosen line, not a
    measured one) - write the pilot's own wave (3.4) and go on with the part. **Exit 1 (STOP)**: the
    part stops. Read `stopped_by` and, for those countries, the reasons in ATTEMPTS.jsonl (a host
    that refuses the checker, a rule agents keep missing); fix the cause (the brief's
    `KNOWN_FETCH_TROUBLE`, the prompt), move the pilot directory aside (local, kept), and cut a new
    pilot with a new `--seed` and the part again `--without` it (step 6). Nothing of a stopped
    pilot is written. Commit `COUNTS.json` and `PILOT.json` of the pilot either way.

### 3.4 Write (journalled, steps of at most 100 sites)

For each run, in the order of 3.3, with an unused wave label of its own (a date and at most one
letter: e.g. `2026-09-27a` part-1 pilot, `2026-09-27b` part 1, `2026-09-27c` part-2 pilot,
`2026-09-27d` part 2).

13. `$PY $F/plan.py wave --wave W --run $RUN` - `output/remediation/fields/wd1/write/W/WAVE.json`,
    pinned to DECISIONS.jsonl and CLASSIFIED.jsonl by sha256 and itself pinned by `WAVE.sha256`, and
    `HELD.jsonl` (every `unresolved` and `held` field, also of sites with nothing to write). Gate:
    refuses while REASK.json names a field; a wave is planned once; an edited WAVE.json is refused
    by every later command.
14. For N = 1, 2, ... - `L=fields-wd1-$W-s$(printf %03d $N)` (e.g. `fields-wd1-2026-09-27b-s001`,
    `fields-wd1-2026-09-27b-s012`), step directory `D=output/remediation/fields/wd1/write/$W/s$(printf %03d $N)`:
    1. `$PY $F/plan.py step --wave W --step N` - a read-only read of the step's sites and
       their journals: PLAN.jsonl, SKIPPED.jsonl (every refusal with its reason, section 4), PLAN.md,
       ROLLBACK.sql (written before any statement, pinned to the plan). Gate: refuses until step
       N-1 is ACCEPTED with 0 deviations, when DECISIONS.jsonl is not the wave's, when the step
       holds more than 100 sites, and when the step is already emitted or accepted. A step with
       nothing to write leaves NOTHING_TO_WRITE.json; go to ix.
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
       **A refusal at iv or v** (exit non-zero; nothing was written): keep the step for the record
       with `mv $D $D.refused-$(date -u +%Y%m%dT%H%M%SZ)`, find the cause, and plan the step again
       from i (`plan.py step` refuses only while `$D` holds APPLY.sql or ACCEPTED.json). Commit the
       refused directory with the next step.
    6. `$PY $A --lane $L --apply` - `APPLY OK`. Exit 3 NOT COMMITTED, 4/6 COMMITTED (read the
       message), 5 OUTCOME UNKNOWN: read the journal for the stamp before anything else, never apply
       twice.
    7. `$PY $A --lane $L --verify` - journal rows for the stamp = the plan's cells; geom-not-point
       and the period-pair residual not raised by this step.
    8. `$PY $A --lane $L --rehearse-rollback` - on the landed rows: the NOTICE, ROLLBACK, the cells
       still holding the written values.
    9. `$PY $F/plan.py accept --wave W --step N` - ACCEPTED.json with **0 deviations**:
       every planned cell holds its new value, one journal row per cell with exactly the planned old
       and new value, no other stamp wrote a planned cell since, no planned site breaks an invariant,
       the step holds at most 100 sites. Any deviation refuses the step (no ACCEPTED.json) and stops
       the wave.
    10. Commit `$D` (REHEARSAL.sql stays out by .gitignore), with WAVE.json, WAVE.sha256 and
        HELD.jsonl on the first step, and the run's COUNTS.json.
    `$PY $F/plan.py status --wave W` shows each step's state.
15. After a wave's last step - **what the written fields feed** (`$PY $F/plan.py handoff --wave W`
    writes `write/W/HANDOFF.json`, versioned; it refuses unless every step is accepted with 0
    deviations):
    1. **card_stats** - `api/cardgame/generator.site_card_stats` derives category group, antiquity,
       mystery (site_type x period_name), rarity and the empire tags (lat/lon with period_start)
       from exactly these columns, and nothing re-runs it after a field write
       (`mechanical/card_stats.py`). After the run's last wave (at the latest after part 2's), run
       a card_stats wave with an unused label C: `$PY scripts/remediation/mechanical/card_stats.py
       --wave C --export`, then `--write` (refuses unless its counterfactual reproduces every stored
       cell), then `$A --lane card-stats-C` with `--emit`, `--verify`, `--rehearse`,
       `--probe-guards`, `--rehearse-rollback`, `--apply`, `--verify` - the sequence and the
       read-backs AUDIT_LOG gives for "card-stats-2026-09-23, last, re-planned". Completion: `card_stats.py
       --wave Cb --export --write` prints `"cells": 0` (a read-back, not applied). `sites_written`
       of HANDOFF.json names the sites whose inputs moved; the wave recomputes every card and plans
       only the cells that differ. A WD1 write to `site_type` or `period_name` voids every earlier
       card_stats wave's ROLLBACK.sql (its guard 5 premise), as that module's docstring says.
    2. **site_external_ids** - the item a site's harvest, WD2 and the prospector's dedup read
       (rung 0) was derived from the old source_url. `source_urls` of HANDOFF.json lists each written
       URL with the item its new article names (`wikibase_item`, `lang`, `resolved_title`; a cleared
       URL has none - the ids derived from the old one are stale). It is the input of the next
       journalled site_external_ids wave with L5's tool (`output/remediation/tools/qid_repair.py`,
       HUMAN_ONLY_DECISIONS B1-L: an id is written only when its item or article is this very site).
       WD1 writes no site_external_ids row; until that wave runs, the ids of these sites still name
       the old items.
    3. **scope (WD2)** - `starts` of HANDOFF.json: a written start can move a site out of the E3
       window (rest of the world to 500 AD, the Americas and Oceania to 1500 AD - O7), and a cleared
       start makes it an E3 case (b), a site without a date (HUMAN_ONLY_DECISIONS B13); WD1 writes
       no `scope_status`.
    4. **WF** - HELD.jsonl of every wave: the held fields (unresolved points, fields whose pages the
       checker could not read) are counted as unsourced in the final measurement.
    5. The static export, IndexNow and the push (O8, WF). The FINISH_PLAN progress log records the
       card_stats and site_external_ids follow-ups (FINISH_PLAN is not on the lane's branch).
16. Archive the runs (`$R`, `$RP`, `$R2`, `$R2P`, `$H*-r*`) as a tgz beside the other run archives -
    DECISIONS.jsonl holds every answer's quotes and reasoning (the keeps included) and is not
    versioned (bulk).

### 3.5 Undo

Every step's `ROLLBACK.sql` restores each old value under the stamp `<wave>_fields-wd1-s<NNN>-rollback`,
conditioned on the value the step wrote (a cell another writer changed since is refused, and the
whole reversal with it). Rehearsed in 14.viii. Running it is a decision, never automatic:
`ssh ancientnerds "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map -v ON_ERROR_STOP=1" < ROLLBACK.sql`,
then `$A --lane $L --verify`. Reverse steps newest first. The site invariants are not checked on a
reversal: it restores the state before the write, which may not have held them (one curated site
carried a NULL `geom` on 2026-09-26). After a reversal, a card_stats wave recomputes the cards again
(15.i), and HANDOFF.json no longer describes the database - write it again after re-planned steps.

## 4. What each write refuses (SKIPPED.jsonl reasons)

| reason | meaning |
|---|---|
| `not-a-curated-live-site` | the site is retired or not `ancient_nerds` now |
| `moved-since-classification` | the row no longer holds the value the decision was made about |
| `journal-disagrees` / `journal-*` | the column's journal does not end at the live value (a write around the journal) |
| `coordinates-unresolved` | no two sources for the point: held, the stored point stays |
| `held-unreadable` | the field's last answer failed only on pages the checker could not read: held, neither written nor cleared |
| `country-changes` | the new point lies in another country than the stored one (`bcases.classify.country_after_move`): held, a country is the country lanes' question |
| `geom-not-point` | the live geom is neither NULL nor the live point |
| `point-incomplete` | another cell of the point (lat, lon or geom) is refused: a point is written whole or not at all |
| `period-end-precedes-start` | the new start lies after the stored `period_end` (a `period_end` of 0 is none, as in the codebase's `period_end or period_start`; `period_end` was NULL on every curated site in the 2026-09 census) |
| `period-start-journal` / `implementations-disagree` | the label cannot follow its start (a start written around the journal; the Python and the frontend buckets disagree) |
| `period-name-refused` | the start's label cell is refused: a start is written only with its label |

## 5. Measured 2026-09-26 (read-only; no write)

How: `harvest.py --root output/remediation/fields/harvest-sample-200 export --sample 200 --seed
20260926` and `fetch` for the sample; the population the same without `--sample` (the default root);
`classify.py export`, `seeds.py build`. Production was asked four export SELECTs (two harvest
exports, two stored-field exports) plus the coverage and catalog SELECTs behind sections 1 and 2; the
web only GET. After the review (section 6) the 270 web source pages of the population and the 9 of the
sample were fetched again with the lane's httpx client and agent (copies of both harvests, the other
records unchanged), and everything was classified again with the fixed code, files only:
`classify.py --root <copy> --out <dir> classify --part all|conflict|rest`. The counts and the
breakdowns are versioned in `output/remediation/fields/measurements/2026-09-26/`
(`population-*.COUNTS.json`, `sample-200.COUNTS.json`, `breakdown.json`).

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
article files (3,835 with coordinates), 5,004 URL records. With the httpx client the 46 Megalithic
Portal pages answered 200 (all had timed out or given 503 through the earlier urllib3 transport);
whc.unesco.org (11), Atlas Obscura (8) and Britannica (3) answered 403.

### 5.2 Expected statuses - the sample of 200 and the population

| field | sample 200: CONFIRMED / CONFLICT / MISSING | population 4,926: CONFIRMED / CONFLICT / MISSING |
|---|---|---|
| coordinates | 126 / 46 / 28 | 3,108 / 948 / 870 |
| period_start | 13 / 3 / 184 | 233 / 68 / 4,625 |
| site_type | 112 / 40 / 48 | 2,738 / 763 / 1,425 |
| source_url | 170 / 27 / 3 | 4,131 / 618 / 177 |
| sites asked / fields asked | 189 / 379 | 4,760 / 9,496 |
| item in identity doubt | 25 | 494 |

Parts: conflict 1,349 sites (all asked), 4,013 fields; rest 3,577 sites, 3,411 asked, 5,483 fields.
England carries 1,672 of the 9,496 fields and 1,020 of the 4,694 period questions (207 in part 1, 813
in part 2). The sample's rates match the population's within sampling error (coordinates CONFLICT 23 %
vs 19 %, site_type 20 % vs 15 %, source_url 14 % vs 13 %).

What the CONFLICTs and MISSINGs are (population):

- **coordinates 948 CONFLICT**: the item is a container (settlement, island, hill, museum) none of
  whose classes holds the stored type - 494; the stored point 1-10 km from a witness - 306; more than
  10 km - 119; a point another live site holds exactly (a placeholder) - 24; P625 and the article
  disagree - 5. **870 MISSING**: no source point 622; one source point only 248 (246 P625, 2 the
  article) - the stored point is often a copy of the one P625, so it confirms nothing (section 6,
  finding 8).
- **period_start 68 CONFLICT**: the item's earliest start lies wholly in another bucket. The 4,625
  MISSING are 4,079 items without a dated start, 491 items in identity doubt, 13 empty values without
  a date and 42 spans that straddle the stored bucket (a century- or millennium-precision date).
- **site_type 763 CONFLICT**: identity doubt 494; a specific site class that names other types 269.
  MISSING: only generic classes 899, no item 362, an item without P31 164.
- **source_url 618 CONFLICT**: identity doubt 474; another item's article 33; a redirect to another
  article 31; dead (a missing article 13, 404/410 13) 26; a redirect to another page 16; a search or
  proxy URL 13; a redirect into a section 8; a section link of its own 7; malformed 6; a
  disambiguation page 4. **177 MISSING**: not readable by machine 64 (HTTP 403 37 - UNESCO 11, Atlas
  Obscura 8, tuerkei-antik.de 6, Britannica 3 -; connection errors and timeouts 23; 5xx 3; 429 1),
  empty 42, an article no item confirms 39, a page whose title names nothing of the site 32. Of the
  169 live names without a distinctive word, 38 have source_url asked (44 before the naming fix) -
  and now a correct keep or replace of theirs can pass check-answer.

### 5.3 How the machine rates what an earlier reading found wrong

The 54 seed cells (the acceptance's stage-1 WRONG verdicts and B13's cells, 46 sites) by the machine's
own status, before the seed flag is applied: coordinates 2 CONFLICT, 2 MISSING (of 4); period_start 2
CONFLICT, 28 MISSING, 1 CONFIRMED (of 31); site_type 10 CONFLICT, 5 MISSING, 1 CONFIRMED (of 16);
source_url 3 CONFLICT (of 3). So the machine alone asks 52 of the 54 known-wrong cells; the two it
confirms (the Temple of Bel's start - P580 AD 17 against an older Hellenistic sanctuary; the Baltic
Sea Anomaly's type - the class "anomaly" allows "Underwater structures") are interpretive and reach
Opus through their seed. A CONFIRMED field is asked of nobody, so this escape rate (2 of 54) is the
lane's blind spot, and the final WF measurement is where it shows. (The review's first naming fix
also read the item's labels and turned the seed "Ramesses III Temple" - stored on an article that
redirects to Medinet Habu - CONFIRMED; that is why labels are not read.)

### 5.4 The load

Part 1 (conflict): 1,349 sites, 4,013 fields - its pilot 80 sites (10 batches), the rest about 159
batches of 8, at 16 agents about 11 rounds of agents. Part 2 (rest): 3,411 asked sites, 5,483 fields -
its pilot 10 batches, the rest about 417. Stage-1 context: 22 of 60 period_name, 16 period_start, 8
site_type, 7 coordinates and 4 source_url verdicts were WRONG.

## 6. The review of 2026-09-26 and what changed

An independent review of the built lane reported 5 major and 9 minor findings. Fixed (tests first,
each guard in the WD1 mutation sweep - `mutation_sweep.py wd1:`, 72 cases, all fire):

1. **The transport evaded a robot-policy block** (major): `fields/transport.py` sent every request
   through urllib3 because Wikimedia refused httpx's TLS handshake with an agent without a contact.
   Removed; the agent names the project's public site and goes through httpx (section 1).
2. **Names without a distinctive word could never pass** (major): source_url keeps and replaces of
   the 169 such sites were refused by rule. The whole name, or its core without a generic frame,
   now names the site; the item's labels do not (5.3).
3. **Exhaustion cleared what the checker could not read** (major): transient fetch failures are
   fetched again before every import; a field that failed only on unreadable pages is held; each
   part runs an 80-site pilot through all rounds and stops above a stated clear rate (3.3, step 12).
4. **Non-ASCII URLs looked like redirects** (major): URLs are compared in httpx's form with the path
   unquoted; a value is written percent-encoded and without a fragment; the value's own page is
   fetched whatever the quotes' spelling (the last found while re-testing).
5. **Derived stores did not follow** (major): `plan.py handoff` and step 15 - a card_stats wave, the
   site_external_ids hand-off, the scope hand-off.
6. A point is written whole, a start only with its label (minor). 7. A period quote must state the
   value, a type word must begin a word (minor). 8. One coordinate witness is MISSING, not
   CONFIRMED (minor; 248 more questions). 9. The lane template reads `s$(printf %03d N)` (minor).
10. A step of more than 100 sites is refused at `step` and `accept`; WAVE.json is pinned (minor).
11. HELD.jsonl lists every held field per wave (minor). 12. The measured counts are versioned
   (`measurements/2026-09-26/`; minor). 13. A source_url value with a `#fragment` is refused, a
   stored one is a CONFLICT (minor).

Not changed: the keeps with their quotes stay only in the local DECISIONS.jsonl (archived with the
runs, 16) - they write nothing, and the file is bulk.
