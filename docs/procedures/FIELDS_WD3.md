# WD3: fill every open structured field from online research

Status: **built 2026-10-01 on branch `wip/wd3` (base `wip/model-stamp`); population measured read-only on
production; nothing written, no agent asked.** The code is `scripts/remediation/fields/` (WD1's package:
`rule.py`, `population.py` and `owner_list.py` are new, `answers.py`, `handoff.py`, `plan.py`,
`classify.py` and the lane in `mechanical/lane.py` take a rule switch); the writer is the mechanical one
(`mechanical/apply.py`, lane family `fields-wd3-<wave>-s<NNN>`). Read `FIELDS_WD1.md` (the pieces, the
write path, the traps) and `FIELD_CONTRACT.md` first: WD3 is WD1 again, and everything not stated here
is as it is there. `scripts/remediation/phase4/` is untouched; no existing check or verify prompt template
of lane WC is touched either (WD3 only adds texts).

## 1. What WD3 decides, and under which rule

Owner decisions of 2026-10-01 (verbatim answers): (1) "Wikipedia/Wikidata reicht" - one source suffices;
(2) "Feld bleibt leer" - a field the research cannot source stays empty, the owner gets a list; (3)
"Recherchieren, sonst behalten" - a point without a sourced witness is researched, else it stays (owner
list); (5) the orchestrator is Opus 5.5, every answering agent is Sonnet 5.5, answers are recorded with
`opus_handoff.py answer ... --model claude-sonnet-5-5`.

| | WD1 (`two-families`, default) | WD3 (`one-family`) |
|---|---|---|
| asked | every field a machine source contradicts or cannot confirm | **only open fields** (section 2) |
| evidence | at least two quotes from two source families | **one verbatim quote from one source**, found by machine in the page as fetched (`opus_audit/quotes.py`); one Wikipedia article in any language + its Wikidata item + Commons = one family, else the registrable domain |
| refused sources | - | `ancientnerds.com`, known Wikipedia mirrors (`rule.FORBIDDEN_FAMILIES`: Wikiwand, DBpedia, ...), also behind a web.archive.org copy with or without the scheme of the archived URL (`answers.family_of` unwraps it); archive and cache proxies whose original cannot be attributed (archive.org itself when it cannot be unwrapped, archive.ph/today/is/md/vn/li/fo, `googleusercontent.com` cache, `translate.goog`, `translate.google.com`); the brief forbids AI content farms (no list can be machine-checked) |
| field checks | `answers.py` | **the same, unchanged**: a coordinate quote within 1 km of the value and written at least to whole arcminutes; a period quote carries a date and one states the value's year / century / millennium; a type quote holds a word of the type; a source_url quote is from the value's own page and one names the site; the value page is served 2xx, not redirected, on Wikipedia an article of its own |
| answers | keep / replace / clear (coordinates: unresolved) | keep / replace / **unresolved** (every field) |
| nothing sourced after 3 rounds | cleared (a point is held) | **stays**: `unresolved`, or `held` when the last answer failed only on pages the checker could not read; both go to the owner list |
| write | replace and clear; a period label repaired on every site of its wave | **fill only** (below) |
| model | Opus agents | **Sonnet 5.5 agents** (`--model claude-sonnet-5-5`), orchestrated by Opus 5.5 |

**Fill only** (`plan.py`, rule `one-family`): an answer is written only when it is a `replace` of a field the
question named open (`CLASSIFIED.jsonl` `open`) **and that is empty** now (NULL or blank), or of the stored
point of a site without a sourced point (replaced only when the sourced point is more than 1 km away; within
1 km it is a `keep`: recorded as sourced, no write). A stored scalar value is never replaced, even one WD1 held
or could not source: the `replace` is refused as `not-empty` and goes to the owner list with the value found (a
`keep` on such a value records its source and writes nothing). Replacing an unsourced non-empty value would be a
widening of the owner's rule ("fill") that only the owner can decide. A field that holds a sourced value is
never in a WD3 question; neither is a point a journalled lane wrote with sourced evidence (section 2). A `clear` decision cannot exist (the parser refuses it, `plan.py wave` refuses a
DECISIONS file that holds one, `site_cells` refuses it per cell). A `period_name` is written only beside the
`period_start` written in the same step (derived as in WD1); a label that merely disagrees with its start
is not repaired by WD3. The point is still written whole (`lat`, `lon`, `geom`) and never across a country
border (`country-changes`).

**The rule is a switch, not a copy.** `RUN.json` of a run names it (`rule.py`: `{"rule": "one-family",
"stage": "wd3"}`), written once by `population.py build` (a run of the other rule is refused); a run without
`RUN.json` is a WD1 run, so WD1's runs and its prompts (pinned by sha256) re-import byte for byte. `plan.py
wave` copies the rule into the pinned `WAVE.json`; `step` / `accept` / `handoff` / `status` take `--stage wd3`
(default `wd1`) and refuse a wave planned under the other rule. WD1's tests run unchanged beside WD3's.

**Lane identity.** Step lane `fields-wd3-<wave>-sNNN`, run stamp `<wave>_fields-wd3-sNNN`, rollback stamp
`<run stamp>-rollback`, test id `WD3/structured-fields`, journal confidence `one_source` (WD1's: `two_source`;
the column is free text), plan table `_fields_wd3_plan`, directory `output/remediation/fields/wd3/write/<wave>/sNNN`,
NOTICE `WD3 field correction: <n> of <n> planned cell(s) changed and journalled over <m> curated site(s)`.
The cells, guards and invariants are WD1's. Every journalled cell carries its quote(s), their outcomes and the
model that answered (`evidence[].model`): the derived `period_name` cell carries the start's decision entry (and
so its model) beside its derivation.

## 2. The population (measured read-only, 2026-10-01)

A curated, not retired (`scope_status`) site is asked when at least one field is **open**:

* `empty` - `period_start` NULL, `site_type` or `source_url` NULL or `''` (read from production now, after
  WD1's clears landed; `lat`/`lon` are NOT NULL);
* `unresolved` - the stored point: WD1's decision for it is `unresolved` (a counted answer, or exhausted),
  or - for a site WD1 never classified - the machine status is not CONFIRMED. **Not open**, whatever WD1
  decided: a point whose newest `lat`/`lon` journal row (`remediation_change_log`, `POINTS.jsonl`, one SELECT)
  carries `two_source`, `authoritative` or `one_source` confidence and the value the row holds now - another
  lane's sourced write. Measured 2026-10-01: Kephala (Kea, `294968f3-036b-44ff-b704-91593648927d`), written by
  `2026-09-23_owner-case-coordinates-wave2` from Wikidata P625 and topostext.org, the only one of WD1's 969
  unresolved/held coordinates. COUNTS.json of the build lists them (`journal_sourced_points`);
* `held` - WD1 held the field (pages its agents cited were unreadable): the stored value neither got a source nor
  was cleared. It is asked (a `keep` records a source) but a different value is never written (`not-empty`);
* `unsourced` - WD1 decided `clear`, the value is still stored (its write was refused).

A field WD1 decided `keep` or `replace` is never asked (an empty one is listed as a contradiction, not asked).
Read from WD1's own records - four runs' `DECISIONS.jsonl` / `CLASSIFIED.jsonl` and the waves' `HELD.jsonl`
(`population.read_wd1` refuses a WD1 wave with a step not accepted with 0 deviations, an edited `WAVE.json`, a
cell decided twice, a run still waiting for a re-ask, and a run whose unresolved/held decisions are not exactly
what its waves listed).

Measured against production (the harvest refreshed, `STORED.jsonl` read the same minute; 4,905 curated sites live,
99 retired):

| field | open | of which | production now |
|---|---|---|---|
| coordinates | **956** | 956 unresolved (WD1: 969 unresolved/held fields, 13 of them on sites retired since) | - |
| period_start | **2,240** | 2,235 empty, 5 held | 2,235 NULL of 4,905 |
| site_type | **411** | 410 empty, 1 held | 410 NULL, none `''` |
| source_url | **67** | 67 empty | 67 NULL |
| **fields / sites** | **3,674** | in **2,694 sites** (one question each) | `unsourced`: 0; WD1 sourced-but-empty: 0; sites WD1 never saw: 0 |

Field sets per site: period_start alone 1,556; coordinates alone 385; coordinates+period_start 321; period_start
+site_type 145; coordinates+period_start+site_type 162; the rest 125. Countries: England 694, Peru 265, Greece 183,
Turkey 111, France 102, Spain 96, Mexico 96, Italy 92. 211 sites carry an item in identity doubt (shown in the
question), 2,376 have a Wikidata item, 1,912 have links on their site page. WD1: 9,524 decisions in four runs
(`wd1-pilot`, `wd1`, `wd1-rest-pilot`, `wd1-rest`), 975 unresolved/held, waves `2026-09-26a`-`d` all accepted.
Counts are versioned in `output/remediation/fields/measurements/2026-10-01/wd3-population.COUNTS.json` (measured
before the journal witness: the build of a run leaves out Kephala's point, so 955 coordinates and 2,693 sites - the
COUNTS.json of that build is the record).

**The harvest refresh found four P31 classes the table lacked** (25 new items since 2026-09-26): former capital
(container), tourist attraction (generic), prefecture-level city of China (container), portal (site: gate types).
They are added to `p31_site_types.json` (769 to 773 classes) and `classify.TABLE_SHA256` moved with it
(`7be7543d...` to `38140ab2...`), as the table's own rule demands; WD1's classification of its four runs is not
re-run (none of the four classes is on a WD1 site).

What a WD3 question shows beyond WD1's: why the field is open, WD1's reasoning for it (600 characters, a lead and
no evidence), the stored `source_url`, and the pages the site's own page links to (`site_content_links`, the link
icons: title, kind, URL, best first, ten at most; `LINKS.jsonl`). The brief tells the agent to start from the site's
Wikidata item, its Wikipedia article and its other-language articles, the stored source_url and those links, then
reputable sources (registers, museums, universities, journals, Pleiades, excavation reports) - never
`ancientnerds.com`, AI content farms, Wikipedia mirrors. Hosts that refuse the lane's User-Agent (FIELDS_WD1.md
section 1: Historic England, Heritage Gateway, whc.unesco.org, Atlas Obscura, Britannica) are recorded unreadable,
never evaded.

## 3. The pieces added

| module | does |
|---|---|
| `rule.py` | the two rules, `RUN.json` (`read_rule`, `write_run`), the forbidden families |
| `population.py` | `export` (STORED.jsonl via `classify.export_stored`, LINKS.jsonl, POINTS.jsonl, an empty SEEDS.jsonl), `build` (WD1's records read and gated, the open fields, RUN.json, CLASSIFIED.jsonl through `classify.classify_all(refine=...)`, COUNTS.json with the population per field); `--pilot N --seed S` / `--without RUN` as WD1 |
| `answers.py`, `handoff.py` | the rule parameter: quotes needed, forbidden families, decisions, the WD3 question / brief / exhaustion / pilot gate; each answer and decision records the model |
| `plan.py` | `--stage`, fill-only cells, `never-clears`, `not-an-open-field`, `not-empty`, `field-unresolved` |
| `owner_list.py` | `build`: OWNER_LIST.md / OWNER_LIST.jsonl from the runs and their waves |
| `mechanical/lane.py` | `fields_lane(wave, step, stage)`, `FIELDS_ROOTS`, the lane regexp over `wd1|wd3` |
| `output/remediation/orchestration/wd3_wave.sh`, `wd3-handoff-pool.js` | the write loop; the answer pool (Sonnet 5.5 agents, an Opus operator) |

## 4. The runbook

From the repository root of the **main checkout** (it holds WD1's runs and the harvest), main venv, after the
branch is merged. Every step names its gate. Nothing below writes to production until 4.5.

```bash
PY=./.venv/Scripts/python.exe
F=scripts/remediation/fields
A=scripts/remediation/mechanical/apply.py
W3=output/remediation/fields/wd3                 # the run (the population less the pilot); also the harvest copy and the waves
W3P=output/remediation/fields/wd3-pilot          # the pilot (80 sites)
H=output/remediation/handoff/fields-wd3          # handoff rounds: $H-r0 ..; $H-pilot-r0 ..
```

Argument positions: `population.py --out DIR <command>` (before the command); `classify.py --root H unmapped`;
`handoff.py <command> --run DIR`; `plan.py <command> --stage wd3 --wave W` (`wave --wave W --run DIR`).

### 4.1 Refresh the harvest and export (read-only)

1. `mkdir -p $W3 && cp -r output/remediation/fields/harvest $W3/harvest` - a copy: the shared harvest stays as
   WD2 reads it.
2. `$PY $F/harvest.py --root $W3/harvest export` - one SELECT (the sites, their items, their URLs now).
3. `$PY $F/population.py --out $W3 export` - **straight after step 2**: STORED.jsonl, LINKS.jsonl, POINTS.jsonl, an
   empty SEEDS.jsonl (three SELECTs). Classification refuses a harvest and a stored export of different states.
4. `$PY $F/harvest.py --root $W3/harvest fetch` - only what changed (measured 2026-10-01: 25 items, 4 classes, 503
   source URLs, about 25 minutes); re-run until nothing is fetched.
5. `$PY $F/classify.py --root $W3/harvest unmapped` - must print `[]`; else add each class to `p31_site_types.json`
   (kind and canonical types), review, move `classify.TABLE_SHA256` in the same commit.

### 4.2 Build the pilot and the run (files only)

```bash
mkdir -p $W3P && cp $W3/STORED.jsonl $W3/LINKS.jsonl $W3/POINTS.jsonl $W3/SEEDS.jsonl $W3P/
$PY $F/population.py --out $W3P build --root $W3/harvest --pilot 80 --seed 20261002
$PY $F/population.py --out $W3 build --root $W3/harvest --without $W3P
```

Gate: the build refuses an unfinished WD1, a run asked already (`ROUNDS.jsonl`), a run pinned to another rule, a
missing LINKS or POINTS file, an unmapped class. Read `COUNTS.json` (`population.fields`, `population.why`,
`wd1_sourced_but_empty` must be `{}`, `wd1_unseen_sites` should be `[]`, `journal_sourced_points` lists the points
left out) and commit it with `RUN.json`.

### 4.3 Ask the Sonnet agents (no code calls a model)

Order: pilot (`RUN=$W3P HO=$H-pilot`), then the run (`RUN=$W3 HO=$H`). Each through all its rounds; the run starts
only after the pilot's gate (4.4).

6. `$PY $F/handoff.py export --run $RUN --handoff $HO-r0` - one question per site with exactly its open fields,
   batches of 8 by country and name (`wd3-r0-b0001` ...).
7. For each batch B (14-16 in parallel): a fresh **Sonnet 5.5** agent with the text of `$PY $F/handoff.py brief
   --run $RUN --handoff $HO-r0 --batch-id B`. It researches, checks each answer with `handoff.py check-answer` and
   records it with `opus_handoff.py answer ... --model claude-sonnet-5-5` (write-once). The workflow script
   `output/remediation/orchestration/wd3-handoff-pool.js` does 6-11 for one run (`args`: `{run, ho, pilot, width}`;
   answer agents `model: 'sonnet'`, the operator inherits Opus).
8. `$PY scripts/remediation/opus_handoff.py validate --dir $HO-r0` - clean: every question answered, in shape, by
   one of the two stamps, nothing stale or orphaned.
9. `$PY $F/handoff.py import --run $RUN` - as WD1 (prompts re-rendered and matched to the manifest's sha256; each
   quoted page and source_url value fetched, each quote checked; transient fetch failures forgotten and asked
   again; the latest counted answer decides). Writes ATTEMPTS.jsonl (with `model`), DECISIONS.jsonl, REASK.json,
   PAGES.jsonl.
10. While REASK.json names fields: `handoff.py export-reask --run $RUN --handoff $HO-r1`, then 7-9; once more on
    `-r2`. After round 2 a field without a counted answer is `unresolved`, or `held` when its last answer failed
    only on pages the checker could not read. `handoff.py status --run $RUN` shows the decisions.

### 4.4 The pilot's gate

11. `$PY $F/handoff.py pilot-report --run $W3P` - PILOT.json. **Exit 0 (PASS)**: at most 20 % of the pilot's fields
    ended `held` (the checker cannot read what the agents cite), and at most 30 % in a country with at least 10
    fields (chosen lines, not measured). Every `unresolved` decision, whether the agent answered it outright or it
    came from exhaustion, is reported (`unresolved_rate`) and not gated by itself: the population is what WD1 could not
    source. What is gated against laziness: of the fields of sites whose question showed a Wikidata item or an
    English Wikipedia article (`hinted`), at most 60 % may be answered `unresolved` outright
    (`hinted_unresolved_rate`, once at least 10 such fields were asked; chosen line). **Spot-check** a PASS anyway:
    read 10 `unresolved` answers of sites with an article and look whether the article states the value. **Exit 1 (STOP)**: read `stopped_by` and the reasons in
    ATTEMPTS.jsonl, fix the cause (the brief's `KNOWN_FETCH_TROUBLE`, the sources the agents choose), move
    `$W3P` aside, build a new pilot with a new `--seed` and the run again `--without` it. Nothing of a stopped
    pilot is written. Commit COUNTS.json and PILOT.json either way.

### 4.5 Write (journalled, steps of at most 100 sites)

Each run with a wave label of its own (a date and at most one letter), pilot first: `2026-10-02a` for `$W3P`,
`2026-10-02b` for `$W3`.

12. `bash output/remediation/orchestration/wd3_wave.sh 2026-10-02a $W3P` - the loop below for every step (it stops at
    the first refusal: exit code and the failed command are printed); then the same with `2026-10-02b $W3`.
    By hand, for each step N (`L=fields-wd3-$W-s$(printf %03d $N)`, `D=$W3/write/$W/s$(printf %03d $N)`):
    1. `$PY $F/plan.py wave --wave W --run $RUN` (once; the stage comes from RUN.json): WAVE.json + WAVE.sha256 +
       HELD.jsonl. Gate: refuses while REASK.json names a field, a wave planned twice, a `clear` decision.
    2. `$PY $F/plan.py step --stage wd3 --wave W --step N`: PLAN.jsonl, SKIPPED.jsonl, PLAN.md, ROLLBACK.sql. Gate:
       refuses until step N-1 is ACCEPTED with 0 deviations. A step with nothing to write leaves
       NOTHING_TO_WRITE.json; accept it (`plan.py accept`) and go on.
    3. `$PY $A --lane $L --emit`, `--verify`, `--rehearse` (NOTICE `WD3 field correction: <n> of <n> planned
       cell(s) ...`, nothing kept), `--probe-guards` (exit 0), `--apply` (`APPLY OK`; exit 3 NOT COMMITTED, 4/6
       COMMITTED, 5 OUTCOME UNKNOWN: read the journal for the stamp, never apply twice), `--verify`,
       `--rehearse-rollback`.
    4. `$PY $F/plan.py accept --stage wd3 --wave W --step N`: ACCEPTED.json with **0 deviations**.
    5. Commit `$D` (REHEARSAL.sql stays out by .gitignore), with WAVE.json, WAVE.sha256, HELD.jsonl on the first
       step and the run's COUNTS.json. `plan.py status --stage wd3 --wave W` shows each step's state.

    **A refusal at `--rehearse` or `--probe-guards`**: nothing was written. `mv $D $D.refused-$(date -u
    +%Y%m%dT%H%M%SZ)`, find the cause, plan the step again from 2, commit the refused directory with the next step.
    What each write refuses besides WD1's table (FIELDS_WD1.md section 4): `never-clears`, `not-an-open-field`
    (the field was not open in the question), `not-empty` (a replace of a stored scalar value: listed for the owner), `field-unresolved` (an unresolved period, type or URL: listed, not
    written), `coordinates-unresolved`, `held-unreadable`, `country-changes`, `period-end-precedes-start`,
    `moved-since-classification`, the journal refusals.

### 4.6 After the last wave

13. `$PY $F/plan.py handoff --stage wd3 --wave W` (each wave; refuses unless every step is accepted with 0
    deviations): HANDOFF.json - `sites_written`, `source_urls` (each written URL with the item its article names),
    `starts`.
14. **card_stats** - `api/cardgame/generator.site_card_stats` derives category group, antiquity, mystery (site_type x
    period_name), rarity and the empire tags (lat/lon with period_start) from exactly the columns WD3 fills, and
    nothing re-runs it after a field write. **After WD3's last wave a card_stats wave runs** with an unused label C:
    `$PY scripts/remediation/mechanical/card_stats.py --wave C --export`, then `--write` (refuses unless its
    counterfactual reproduces every stored cell), then `$A --lane card-stats-C` with `--emit`, `--verify`,
    `--rehearse`, `--probe-guards`, `--rehearse-rollback`, `--apply`, `--verify`; completion: `card_stats.py --wave
    Cb --export --write` prints `"cells": 0`. A WD3 write to `site_type` or `period_name` voids every earlier
    card_stats wave's ROLLBACK.sql (its guard 5 premise).
15. **site_external_ids** - `source_urls` of HANDOFF.json is the input of the next journalled wave with L5's tool
    (`output/remediation/tools/qid_repair.py`): an id is written only when its item or article is this very site.
    WD3 writes no `site_external_ids` row.
16. **Scope (WD2)** - a filled start can put a site that had none (an E3 case (b)) inside or outside the window (rest
    of the world to 500 AD, the Americas and Oceania to 1500 AD - O7); `starts` of HANDOFF.json goes to WD2's scope
    review. WD3 writes no `scope_status`.
17. **The owner list** - `$PY $F/owner_list.py build --runs $W3P $W3 --final` writes
    `output/remediation/fields/wd3/OWNER_LIST.md` and `OWNER_LIST.jsonl`: per field and site what stays open and
    why (no source found; the pages the checker could not read - listed with their URLs; a sourced value the write
    plan refused, with the plan's reason; decided but not written). `--final` refuses while a field is still pending
    (no decision, or a step not accepted). Version both files.
18. The static export, IndexNow and the push (O8, WF) as in FIELDS_WD1.md 15.5. Archive the runs (`$W3`, `$W3P`,
    `$H*-r*`) as a tgz beside the other run archives: DECISIONS.jsonl holds every answer's quotes and reasoning.

### 4.7 Undo

Every step's `ROLLBACK.sql` restores each old value under `<wave>_fields-wd3-sNNN-rollback`, conditioned on the value
the step wrote (a cell another writer changed since refuses the whole reversal); rehearsed in 12.3. Running it is a
decision, never automatic: `ssh ancientnerds "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map -v
ON_ERROR_STOP=1" < ROLLBACK.sql`, then `$A --lane $L --verify`. Reverse steps newest first. After a reversal a
card_stats wave recomputes the cards (14), and HANDOFF.json no longer describes the database.

## 5. Gates built and tested (`tests/remediation/test_fields_wd3.py`, WD1's tests unchanged beside it)

The rule file and its refusals; one quote suffices but each field check still applies; WD1 still wants two families;
no clear under WD3; the project's own pages, mirrors, archive and cache proxies (also behind a scheme-less Wayback URL) refused; the WD3 question's content and WD1's
byte-identical prompt (the sha256 of 300 real WD1 prompts compared before and after, equal); the brief names the
Sonnet model and `--stage wd3`; export batches `wd3-r<N>-b<NNNN>`; the answer's model recorded in attempts and
decisions; exhaustion is `unresolved` / `held`, never `clear`; the pilot gate; the open fields of every kind and
WD1's records gated; population build per field, pilot and rest disjoint; fill-only cells; the lane's stamp, table,
directory and NOTICE distinct from WD1's; the owner list's states; the scripts. The mutation sweep has the cases
`wd3:` (`python scripts/remediation/mechanical/mutation_sweep.py wd3:`) beside WD1's `wd1:`.
