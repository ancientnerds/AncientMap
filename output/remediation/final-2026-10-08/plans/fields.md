# Workstream `fields`: plan (D10, D12, D19, D25 fields part)

Everything is read-only so far. Scratch is in `C:/tmp/wf_map_fields/` (`x.csv` = live period state joined to the journal, `j.csv` = fields-lane journal cells, `py/a1..a12.py`, `types.txt`, `cc.json`, `ids.csv`). Production was read through `ssh ancientnerds`. Numbers marked "measured" come from there.

## 0. Measured baseline

**Rule-made periods.** There are 1,254 shown sites whose live `period_start` equals a journal row with `status: RULE`. The census digest says 1,260.

| rule kind | sites | Africa | Americas | Asia | Europe | Oceania |
|---|---|---|---|---|---|---|
| derived (site_type rule) | 698 | 20 | 62 | 64 | 545 | 7 |
| band (2025 import band) | 511 | 5 | 107 | 75 | 306 | 18 |
| structured (Wikidata P2348) | 45 | 2 | 1 | 3 | 39 | 0 |

- Continent is my country list; England alone is 484 of the Europe cell.
- Derived rule: 453 of the 698 are UK or Ireland, 245 are elsewhere. The digest says 258 non-UK.
- Cave, geology, natural or rock site types: 155 (band 93, derived 50, structured 12), of which 64 sit at "< 4500 BC", 52 at "500 BC - 1 AD" and 20 at "1 - 500 AD". 170 sit in the Americas. The caves-first and Americas-first group is 295.
- All 1,254 have `period_end` NULL and `raw_data` has only 4 keys (`_description_provenance`, `description_citations`, `_card_provenance`, `_description_check`).
- `raw_data._period_provenance` exists on 0 sites. The journal calls all 1,254 rows `one_source`.
- Stamps: `2026-10-04_fields-wd3-s001..s023`. The evidence of each row is `{"source": "WD3 decision (derived|band|structured, round 0, ...)", "status": "RULE", "model": null}`.
- No code in the repo generates `DERIVED.jsonl`. Only the data survives: `output/remediation/period_wave/*.json`, `fields/wd3/DERIVED.jsonl`, `fields/wd4/ORIGINAL_PERIODS.jsonl`. D12 replaces it, so nothing needs regenerating.

**Provenance of all 4,900 shown periods (the marker input).**
- 1,835 have no journal row (the import value, mostly kept by WD1 with two quotes).
- 1,254 are rule rows.
- 897 are `one_source` quote writes.
- 562 are `two_source` quote writes.
- 269 are `authoritative` (Phase 3 and reversal lanes).
- 83 are Undated.

**MiniMax-answered decisions** (`model` field in `fields/wd3|wd4/DECISIONS.jsonl`; WD1 has `model` null):

| field | WD3+WD4 keep | replace | unresolved |
|---|---|---|---|
| coordinates | 130 | 28 | 168 |
| period_start | 0 | 265 | 417 |
| site_type | 49 | 102 | 30 |
| source_url | 1 | 9 | 27 |

- 782 shown sites carry at least one MiniMax decision; 362 carry a MiniMax `replace`.
- Written to production: 405 replaces became 690 journal cells (+25 geom = 715) at 359 sites (WD3 293, WD4 68).
- All 690 cells still hold their written value (0 moved since). WD3's Sonnet-stamped rows are the other 2,595 decisions.

**Coordinates.** 4,470 of 4,900 are sourced; 430 are not (352 WD3 unresolved + 43 WD4 + 12 WD1 unresolved + 23 refused better points). The scratch script is `C:/tmp/wf_fields/py/coords.py`; its output sits in `unsourced_points.json`.

**The 23 refused points.** The distance is to the stored country's polygon (`output/remediation/tools/country_census.py`, `data/boundaries/countries.geojson`). 14 refusals are WD1 and 18 are WD3; 32 refusals over 23 sites. All 23 are still unwritten and shown.

| class | sites |
|---|---|
| Sea within 2 km of the stored country | Els Munts .84, Paphos .35, Odessus .34, Fournou Korifi .73, Castro de Porto de Baixo .69, Manika .56, Pozzuoli .20, Crikvenica .36, Eleusis .16, Clachtoll Broch .95, Stairhaven .22 (11); Achladia: the new point is inside Greece, an old refusal, re-plan accepts it |
| Sea just over 2 km | Marco Gonzalez 2.35 km, Lost City of Heracleion 3.83 km (underwater site) |
| Political line, stored country is Cyprus | Kokkinokremmos (Dhekelia SBA, 1.07 km), Mersinaki, Karpasia, Aghios Epiktitos, Kastros, Nitovikla (Northern Cyprus) |
| Kosovo vs Serbia | Kaljaja |
| Land border | Narona (2.51 km inside Bosnia) |
| Wrong country | Flevum (new point is in the Netherlands, stored Germany) |

**External ids** (`site_external_ids`, kinds `wikidata_qid` and `enwiki_title` only):
- 4,623 sites have a QID row and 4,602 an enwiki row; 361 shown sites have no QID (all without an en.wikipedia source_url).
- 82 shown sites have an enwiki row that matches no title in their `source_url` after case-folding (96 before folding).
- `source_url` writes that can stale ids: WD1 503 (369+111+21+2), WD3 21, L5 48.
- HANDOFF.json exists only for `fields/wd3/write/2026-10-02b`, `2026-10-04` and `fields/wd4/write/2026-10-04a`. WD1's four waves never got one.
- 43 QIDs are shared by 98 shown sites (the duplicates workstream).

**card_stats.**
- Dead columns, all 5,004 rows NULL: `wikidata_qid`, `best_wiki_url`, `heritage_designation`, `inception_year`, `commons_image`.
- `civilization` equals `country` on all rows.
- Last wave: `2026-10-04f` (4 cells). Journal high-water mark is 345369.
- Since then import-hero (9,690 journal rows), 2,880 inserts, 1,017 WC description rows and the WB cards have moved the inputs. The digest counts about 2,687 sites stale.
- `category_group` is also stale: Theatre sites show 'Megalithic' as well as 'Monuments'.

**site_type.** 86 distinct values plus 78 NULL over 4,900 sites.

## 1. Existing tools

All paths are under `C:/PythonProjects/AncientMap/.worktrees/db-final/`.

| piece | file | what it does |
|---|---|---|
| Field lanes WD1, WD3, WD4 | `scripts/remediation/fields/{harvest,classify,population,handoff,answers,plan,owner_list,rule,seeds}.py`, runbooks `docs/procedures/FIELDS_WD1.md` (sections 3.x and 15), `FIELDS_WD3.md` (4.1-4.7), `FIELD_CONTRACT.md` | Question per site, batches of 8, one-family quote rule, fill-only plan, steps of at most 100 sites |
| Writer | `scripts/remediation/mechanical/apply.py`, `lane.py` (`FIELDS_LANE` regexp, `FIELDS_CELLS`, `FIELDS_INVARIANTS`, `fields_lane`, `resolve_lane`) | Lane sequence `--emit --verify --rehearse --probe-guards --apply --verify --rehearse-rollback`, then `plan.py accept` with 0 deviations |
| Period vocabulary | `pipeline/periods.py`, `pipeline/utils/text.py` (`PERIOD_BUCKETS`, `bucket_edge`, `UNDATED`) | Period name to years; `answers._check_period` (line 400), `states_year` (348) |
| Undated label lane | `mechanical/residue_period.py`, `lane.bucket_case` | NULL start means label 'Undated' |
| Coordinate guard | `fields/plan.py` lines 415-445 (`country_check`, refusal `country-changes`), `bcases/classify.country_after_move`, `output/remediation/tools/country_census.py` | Point-in-polygon only, no tolerance |
| Id repair | `output/remediation/tools/qid_repair.py` (waves 1-4 are hand-researched; `resolve`/`render --wave 4` is automated), `scripts/remediation/l5/{population,questions,handoff,decide,plan,links,run}.py` (question, answer and journalled link steps; population groups hard-coded) | Id rows and `source_url` written through `apply_remediation_change`, run stamps `…_external-id-repair…` and `…_l5-links-001` |
| card_stats | `mechanical/card_stats.py` (`CELLS` = 12 columns, `--export`, `--write` with counterfactual proof, `BASIS.json`), lane `card-stats-<wave>` | `generator.site_card_stats` is reused, never re-typed |
| Calibration | `scripts/remediation/mcode_driver.py` (`compare_answers`, `_fill_units`, `calibration_run`, `AGREEMENT_FLOOR = 0.9`; `calibrate --lane fields` is MiniMax-only), `output/remediation/calibration/fields-01`, `fields-02` | Pure comparison function, reusable |
| Handoff and stamps | `scripts/remediation/opus_handoff.py` (`ANSWER_MODELS`: opus-5-5, sonnet-5-5, MiniMax only; `ANSWER_FAMILIES`), `fields/handoff.py` (`BRIEF_PARTS`, `export --model`, `_answering_model`) | One model per round, validated stamp |
| Pool scripts | `output/remediation/orchestration/wd3-handoff-pool.js`, `wd3_wave.sh` | Sonnet answer agents, Opus operator |
| Mutation sweep | `mechanical/mutation_sweep.py` (`WD1_CASES`; guard `wd3:` cases; run `mutation_sweep.py wd1:`) | Pattern is `guard(label, file, source_line, test_name, test_file)` |
| Tests | `tests/remediation/test_fields_{answers,classify,handoff,harvest,period,plan,seeds,wd3}.py`, `test_mechanical_fields_lane.py`, `test_mechanical_card_stats.py`, `test_residue_period.py`, `test_l5.py` | |

## 2. Run state

- **WD1, WD3, WD4:** all waves are accepted and written. The WD3 and WD4 `ROUNDS.jsonl` exist, so `population.build` refuses to rebuild them ("a run is built once"). `FIELDS_WD3.md` still says Sonnet answered; the files show MiniMax answered a third of WD3 and all of WD4 (counts in section 0).
- **Calibration of 2026-10-04:** `fields-02` failed at 64.71 % (22 of 34, MiniMax, bar 90 %). The MiniMax answers were used anyway. There is no recorded owner release (AUDIT_LOG line 13478).
- **Owner list defect:** `OWNER_LIST.jsonl` reports about 1,252 written cells as "refused" (`moved-since-classification: decided about None`). The cause is that the live value equals the lane's own journal row.
- **Never run:** the site_external_ids follow-up, any marker lane, any card_stats wave since 10-04f, `plan.py handoff` for the WD1 waves.
- **Half-way:** nothing in my area. Every step directory has `ACCEPTED.json`; the journal holds no half-applied stamp.
- **Not durable:** the agent scratch under `C:/tmp/wf_*`. Tracked records are the `output/remediation/**` files in the worktree.

## 3. Steps per decision

### Build once: code (Sonnet high builds, Opus high reviews; tests plus mutation cases for every guard)

1. **BP reader.** In `answers.py` add `states_bp(quote, year)` and call it from `states_year`. It covers "N years ago", "N BP", "cal BP", "N ka/kya" and "N Ma/mya". Year = 1950 − N. Tolerance = max(76, one unit of N's last significant digit). Anything older than 6,450 BP is bucket "< 4500 BC". `dated()` already passes any digit. Tests in `test_fields_answers.py` or `test_fields_period.py`. Cases `wd5: a BP quote states its year` and `wd5: a quote without a unit states nothing`.
   - About 250 earlier answers were lost to this: 91 WD1 clears and 158 WD3/WD4 unresolved mention BP or "years ago".
2. **New rule `recheck`, stage `wd5`** (`fields/rule.py`: `min_quotes 1, min_families 1, FORBIDDEN_FAMILIES, fill_only False`). Also change:
   - `lane.py`: add `wd5` to `FIELDS_LANE`, `FIELDS_STAGES`, `FIELDS_ROOTS`, `FIELDS_CONFIDENCE` (`"one_source"`).
   - `population.py`: add `open_fields` reasons `rule-made`, `minimax-answered`, `unsourced-point`.
   - `plan.py` for `wd5`:
     - drop `not-empty` and `not-an-open-field`;
     - permit a replace only where the stored value is rule-made (journal evidence `status: RULE`) or MiniMax-written (decision `model` contains MiniMax);
     - permit a period clear only for a rule-made value, with the label 'Undated'. Today line 515 gives a NULL label for no start. Add `UNDATED` to `FIELDS_CELLS` `period_name` allowed values; the invariant already expects it.
   - A MiniMax `keep` that Claude confirms writes nothing.
   - Cases `wd5: a sourced value is never replaced`, `wd5: only a rule-made start clears to Undated`.
3. **Coastal guard** in `country_after_move`:
   - Add `tolerance_km=2.5`. It applies only when the new point lies in no polygon (sea) and the geodesic distance (pyproj and shapely are in the venv) to the stored country's polygons is within the tolerance; note "coast, x km".
   - A political-equivalence table, B10-style: Cyprus ≡ Northern Cyprus and the Dhekelia/Akrotiri bases; Ukraine/Crimea stays. Kosovo ≡ Serbia is an orchestrator decision, not in the D19 text.
   - Narona (inside Bosnia) stays refused; Flevum goes to `wrong-both` (its cells include `country`, `lane.py` `_WRONG_BOTH_CELLS`) or a country change in the wd5 lane.
   - Result: 12 within 2 km, +Marco Gonzalez at 2.5, +Kokkinokremmos +5 Northern Cyprus = 19 writes; Kaljaja if Kosovo is decided; Heracleion, Narona and Flevum are not written by the guard alone.
   - Tests in `test_fields_plan.py`; cases `wd5: the coast tolerance never crosses a land border`, `wd5: the tolerance needs an empty polygon query`.
4. **Models.** Add `claude-haiku-5-5` to `ANSWER_MODELS` (stamp `anthropic/claude-haiku-5-5 (Claude Code agent)`) and `ANSWER_FAMILIES` ("haiku") in `opus_handoff.py`. Check `scope_review.judged_by`, `served_image/mcode_driver.py`, `teaser/run.py`, `phase4/handoff4.py`, `model4.AI_SYSTEM*`, which all read these dicts. The stamp stays the real model; the role goes into `--answered-by <role>:<batch>`. `fields/handoff.py` `BRIEF_PARTS["recheck"]["model"] = "claude-sonnet-5-5"`; a tier move uses `handoff.py export --model claude-opus-5-5`.
5. **Claude calibration helper** (`scripts/remediation/calibrate_claude.py`, new):
   - `seal` writes `CALIBRATION_SEAL.json` with case ids, sha256 and the threshold before any run;
   - `prepare` copies the already-answered batches into `output/remediation/calibration/<id>`, reusing `mcode_driver.calibration_run` and `prepare_only`;
   - `compare` calls `mcode_driver.compare_answers` / `_fill_units`;
   - `verdict` states `passed` and the tier move.
6. **Marker lane** `period-prov-<wave>`:
   - Writes `raw_data._period_provenance` = `{kind: quote|two_source|authoritative|import_kept|structured|derived|band|undated, run, journal_id, sha}` as one `raw_data` jsonb cell per site. The pattern is `teaser-prov-sNNN` / `lane.TEASER_LANE`, and the hash pinning mirrors `_description_provenance.desc_sha256`.
   - It is computed from the journal and `DECISIONS.jsonl` (all 4,900 sites, steps of 100).
   - Register it in `lane.resolve_lane`, then guards, probes, rollback.
   - Cases `wd5: a marker never names a kind the journal does not`, `wd5: a rule row is never marked quote`.
   - A coordinate marker `raw_data._coord_provenance` has the same shape. The 4,470 sourced and 430 unsourced split exists only in decision files, not in the database.
7. **Stale-id wave** (`output/remediation/tools/qid_repair.py`, new `WAVE5`):
   - `resolve --wave 5` resolves the title of the current `source_url` through the harvest's `urls/` and `enwiki/` caches plus `wbgetentities`, for the 82 mismatches and the 572 sites whose `source_url` a WD/L5 lane wrote.
   - Gate as wave 2: item is a site kind (`bcases.qid_research.is_site_kind`), P625 or article coordinates within 1 km, item not carried by another curated site.
   - A site the gate cannot settle becomes an L5 question (new `l5/population.py` group `stale-id`, Sonnet).
   - Rows are written through `render_split`, `l5/links.py` commands, run stamp `<date>_external-id-repair-wave5`.
   - After applying, re-run `pipeline.wikidata_name_backfill` for the changed QIDs and remove alias rows of replaced items.
8. **site_type merge lane** `site-type-merge-<wave>`:
   - Style of `mechanical/site_type_shape.py`.
   - Map file `site_type_merge.json` of strict aliases inside one `CATEGORY_GROUP` (api/cardgame/constants.py). Every target must be in `CANONICAL_TYPES` and a fixed point of `normalize_site_type`, because Lyra normalises at boot.
   - Proposed pairs (Opus high decides the final map, adversarial check): Fortress 19 and Citadel 3 → Fortress/citadel; Theater 1 → Theatre; Settlement 108, Town 12, Urban 2 → City/town/settlement; Necropolis 9 → Necropolis/tombs complex; Cave 14 → Cave Structures; Church 7 → Church/cathedral; Mine 2 and Quarry 3 → Mine/quarry; Road 3 → Road/avenue/trackway; Villa 11 → Residence/villa/farmhouse; Gate 9 → Gate/archway/bridge; Megalithic 5 → Megalithic structures. About 210 sites.
   - Do not merge across groups (Aqueduct vs Reservoir/aqueduct/canal, Bridge vs Gate/archway/bridge).
   - Update `fields/p31_site_types.json` and `classify.TABLE_SHA256` in the same commit, or later waves reintroduce the old names.
   - Museum 33, Geological interest 19, Natural feature 13 and Magnetic anomaly 1 are scope questions, not vocabulary.
   - The 78 NULL stay empty (O14).
9. **card_stats extension lane** `card-stats-ext-<wave>` (or add 5 `Column`s to `card_stats.CELLS`):
   - `wikidata_qid` and `best_wiki_url` come from `site_external_ids`. The URL is `https://en.wikipedia.org/wiki/<title>`; no network needed.
   - `commons_image` is P18, `heritage_designation` is P1435 (labels), `inception_year` is P571 at year precision or better, refused for the modern-institution cases the `period_wave/structured_refused.json` documents. Source: the harvest entity cache (`output/remediation/fields/harvest/entities/`, 4,517 items, 205 MB) after `harvest.py export` and `fetch` for the roughly 100 new items.
   - Do not touch `source_language`: with it NULL the site API's `bestWikiUrl` shows nothing (`DescriptionSection.tsx` links only when `sourceLanguage !== 'en'`; `static_exporter` writes `wu` only for non-English).
   - Test that `civilization` is not touched.
10. **Owner-list fix** in `owner_list.py`: a live value equal to the lane's own journal row is "filled"; a rule-made period is its own state "rule". Regenerate with `owner_list.py build --runs …`.

### Calibration (D6, thresholds sealed before the run)

Pass = at least 90 % agreement on cells where both sides decide, plus 0 false sources (spot-check every disagreement's URL and quote, O18), plus the fresh unresolved rate not more than 10 points above the gold's.

| role | model, effort | gold (already judged) | size |
|---|---|---|---|
| Period/field research | Sonnet 5.5 high | WD1 two-source decisions from `handoff/fields-wd1-*-r0` (period 582+1205 keeps, coordinates 482 keeps, types, urls; Opus-era). Draw 60 sites stratified by field, answers hidden | 60 sites (8 batches) |
| Same role, BP set | Sonnet 5.5 high | The 91 WD1-cleared and 158 WD3/WD4-unresolved period answers whose reasoning names BP or years ago; true bucket "< 4500 BC" confirmed on Le Moustier, Bruniquel, Cro-Magnon, Apidima, Boxgrove, Lake Mungo and similar in the 30-site audit | 25 sites (4 batches); must resolve at least 90 % into the right bucket with a found quote |
| Adversarial re-check | Opus 5.5 high | `output/remediation/opus_audit/DECISIONS.jsonl`, 481 keep + 453 revert verdicts | 40 cells (20 and 20). It is Opus re-judging Opus, so it measures stability only |
| Operators (workflow pool, batch/validate/import runners) | Haiku 5.5 low | A scripted dry run (no judgement), checked by `opus_handoff.py validate` | 1 batch |

A failing role moves up one tier (Haiku to Sonnet, Sonnet to Opus), is re-calibrated, and the result is recorded in AUDIT_LOG. Sonnet research failing means Opus research for everything below, which roughly triples the cost.

### D10 + D12 + D19: one combined re-research round `wd5`

Re-asking a site once for all its fields is cheaper than three rounds. Population measured: 1,883 shown sites with 2,392 fields (period_start 1,604, coordinates 584, site_type 167, source_url 37); 381 sites have more than one field. Composition:
- 1,254 rule-made periods;
- 782 sites with MiniMax decisions (299 of them overlap the rule set);
- 430 unsourced points (179 overlap the rule set; 146 are in no other group).

Steps, in order:

1. **Refresh the harvest** (`FIELDS_WD3.md` 4.1): `cp -r` the harvest, then `harvest.py export`, `population.py export`, `harvest.py fetch` (only changed items), and `classify.py unmapped` must print `[]`. WD3 spent about 25 minutes on 503 URLs.
2. **Build** `population.py --out fields/wd5 build --stage wd5 --pilot 80 --seed N`, then the rest `--without` the pilot.
3. **Pilot** of 80 sites with Sonnet high: `handoff.py export`, `brief`, `check-answer`, `opus_handoff.py validate`, `import`, `pilot-report` (gate: at most 20 % held, at most 60 % hinted-unresolved). Its `ORIGINAL_PERIODS.jsonl` band hint is shown, and an answer is never accepted because it equals the hint.
4. **Order of the rest:** (a) caves, geology, rock and Palaeolithic sites plus the Americas (about 295); (b) other band-rule and non-UK derived (about 450); (c) UK/IE derived (453); (d) MiniMax-only sites; (e) the 407 unresolved unsourced points. This is the order D12 and D20 name; the same waves feed the D20 scope review.
5. **Rounds r0, r1, r2** as `FIELDS_WD3.md` 4.3.
6. **Opus adversarial re-check** (separate handoff, check question per written cell) of every replace and of 10 % of the keeps. It sees the quote and the fetched page, and answers confirm / reject / unclear. A reject drops the cell back to unresolved and the cell goes to the owner list.
7. **Outcome per field:**
   - period: a quote-backed year or period; or no source and rule-made, which writes 'Undated' with a NULL start; or a keep.
   - coordinates: a sourced replace or keep; an unsourced point keeps its position and goes to the owner list. Those sites get no Short (D19).
   - site_type, source_url: replace or keep.
8. **Write** `plan.py wave --wave 2026-10-NNx --run output/remediation/fields/wd5`, then per step (at most 100 sites) `step --stage wd5`, apply sequence as `FIELDS_WD3.md` 4.5, `accept --stage wd5`, 0 deviations. Waves by the priority groups of step 4, so Shorts-relevant sites are fixed first. Journal stamp `<wave>_fields-wd5-sNNN`, `confidence one_source`, `test_id WD5/structured-fields`, rollback `…-rollback`.
9. **Rollback of MiniMax rows that Claude rejects:** a replace by Claude is an ordinary wd5 cell (old value = the MiniMax value, journalled). A reject without a replacement uses the same `ROLLBACK.sql` mechanics through a plan cell that restores the journal's `old_value` (the restore-from-journal pattern of `mechanical/reversal*.py`). Fold the 25 geom cells in with their lat/lon.
10. **D19 coordinate writes of the 23 refused points** run in the same lane once the guard of build step 3 is in: they come from `WAVE.json` decisions that already exist (`replace` with a quote), so the plan only re-evaluates the country check. No new question for the 19 passing points; Marco, Heracleion, Narona and Flevum get a wd5 question or a hand decision.
11. **Marker lane** over all 4,900 after the last wd5 wave: sections 3.6 of build.
12. **Scope hand-off:** `plan.py handoff --stage wd5 --wave W` writes `HANDOFF.json` (starts, source_urls, sites written). Feed `starts` to the D20 scope review (116 sites after the window, 5 pending).

### D25 external ids

1. `plan.py handoff` for the 3 existing HANDOFF waves and generate it for the 4 WD1 waves; commit all.
2. Run `qid_repair.py resolve --wave 5` and `render --wave 5`, `check`, rehearse, `probe-guards`, apply, `verify`, rehearse-rollback. Order: the 82 mismatches first, then the 572 whose `source_url` a lane wrote.
3. L5 questions for the residue (Sonnet high, an estimated 100-150 sites).
4. Re-run `wikidata_name_backfill` for changed QIDs; remove alias rows of replaced items.
5. The 43 shared QIDs belong to the duplicates workstream; wave 5 refuses a replacement item that another curated site carries (guard 5/6 of `render_split`).
6. Do not QID-backfill the 361 sites without an id here: "a wrong replacement QID is worse than a generic one, because dedup trusts QIDs". That is a separate decision.

### Type merge, then card_stats (last)

1. Run the `site-type-merge` lane after the last wd5 wave (otherwise wd5 re-asks use old names).
2. card_stats, in this order:
   - Wave `Z`: `card_stats.py --wave Z --export`, `--write` (refuses unless its counterfactual reproduces every cell), `apply.py --lane card-stats-Z` with the 7-step sequence, then `--wave Zb --export --write` printing `"cells": 0`.
   - Then the ext lane for the five dead columns, with its own read-back.
   - A type or period write voids every earlier wave's `ROLLBACK.sql`, so run the card_stats wave after all field and type writes.
3. Run a second card_stats wave after the description and image lanes (other workstreams) so `has_description` and `wiki_image_count` are current before the Shorts filter on `rarity_tier`.

## 4. Dependencies on other workstreams

- **Cards and Shorts:** `category_group`, `antiquity`, `mystery` and `empires` change with periods, coordinates and types, so every card pilot needs the final card_stats wave. The card writer must only state a period where `_period_provenance.kind` is quote, two_source, authoritative, import_kept or structured (the digest's recommendation). Shorts exclude unsourced-point sites and 'Undated' sites. Flag period-changed sites as stale for the card lane.
- **Descriptions:** a changed period can contradict a description sentence (the digest cites Alba Fucens, Ake). WD5 hands the list of changed periods to the description-repair step.
- **Scope (D20):** needs wd5 starts before the 116+5 review; the stale list is the `starts` of each `HANDOFF.json`.
- **Identity re-target (D13) and duplicates (D14):** change names, QIDs and enwiki ids, and retire a loser. Run the stale-id wave before D13, and let D13/D14 own the QIDs they touch. Never put two sites with one QID into wave 5.
- **Images (D15, D17):** the 952-without-image lane wants `site_external_ids` as the single QID source; run the id wave first (digest: 11 sites carry an image claim the pre-check never read).
- **Models:** the Haiku stamp in `opus_handoff.py` is shared with every other workstream; land it first, in one commit.
- **Push and deploy:** none of my lanes needs a code deploy except the Python change to `api/cardgame/generator.py` if the dead-column fill is moved into the generator (do not; keep it a lane).

## 5. Estimated model answers

| stage | model, effort | answers |
|---|---|---|
| Calibration (3 roles) | Sonnet high; Opus high | about 85 site answers + 40 Opus cell checks; if Sonnet fails, +85 on Opus |
| wd5 pilot | Sonnet high | 80 site answers (10 batches) |
| wd5 r0 | Sonnet high | 1,803 site answers (about 225 batches of 8) |
| wd5 re-asks r1+r2 | Sonnet high | about 440 (20 % and 5 % of fields, estimate) |
| Adversarial re-check | Opus high | about 1,200 cells (about 150 batches): 55 % of 1,604 period fields, 15 % of coordinates, 60 % of types, plus 10 % of keeps; estimate |
| L5 residue for ids | Sonnet high | about 100-150 sites |
| Type merge map | Opus high | 2 (decide, check) |
| Marker, id resolver, card_stats, ext lane | none (code and rules) | 0 |
| **Total** | | roughly 3,800 answers; about 290 Sonnet batches and 150 Opus batches |

At the Wikimedia limit of 2-3 parallel fetchers, round r0 takes about 16-20 hours wall time (WC measured about 11 minutes per 5-question batch).

## 6. Risks and traps

1. **Wikimedia throttling.** The WD3 pool ran 14-16 agents in parallel. Run width 3 or less. 403 and 429 are throttles, never findings: a throttled fetch becomes `held`, never `unresolved` (`checker cannot read` already does that). Search engines are blocked here; WebSearch works.
2. **Agent edits tracked files.** WD3 batch b0296 rewrote five production files and the tree guard voided it (AUDIT_LOG, driver section). Claude agents get a scratch directory only and a `git status` guard around each batch, as `mcode_driver` did.
3. **Wrong stamp.** An invented stamp voided eight answers (WD3 round 1). The stamp must be one of `ANSWER_MODELS`; `handoff.py brief` already prints the exact `--model` for the round.
4. **PowerShell traps** (memory): `1> file` writes UTF-16 and the gate reads UTF-8; heredocs eat backslashes (write helper scripts as files); `python` bare is the wrong interpreter. Use `./.venv/Scripts/python.exe`.
5. **Moved-since-classification** is the refusal that lost 1,252 cells in the owner list; a wd5 population must be exported straight before it is built (`harvest.py export` then `population.py export`), and `WAVE.json` pins `DECISIONS.jsonl` and `DERIVED.jsonl` by sha256.
6. **period_name must follow period_start in the same transaction.** The invariant expects 'Undated' for NULL. Do not repeat WD1's NULL label.
7. **Rule rows and journal.** A wd5 replace of a rule-made start must pass `journal_break` (the journal ends at the live value). It does today (1,254 of 1,254 live-equal).
8. **BP precision.** "Years ago" is relative to the present and BP to 1950; the 76-year slack only changes bucket edges near 6,450 BP (4500 BC). Calibration set must include one such edge case.
9. **Structured P571.** 29 of 43 Wikidata inception claims record the modern institution (museum, park). `inception_year` in card_stats must reuse the existing `usable_as_period` refusals (`output/remediation/period_wave/structured_refused.json`) or be left empty.
10. **Vocabulary merge is not isolated.** `CANONICAL_TYPES` mirrors `ancient-nerds-map/src/constants/colors.ts` (`CATEGORY_COLORS`); keep both lists unchanged, merge data only. `mystery` counts `(site_type, period_name)` combos, so a merge changes the card of every site of both types.
11. **Disk.** C: has about 20 GB free. This workstream downloads little (about 100 changed Wikidata items, a few hundred article pages), but the harvest copy for a new run is 205 MB and WD3's `pages/` and `cache/` are kept per run. I could not measure their size (the `du` timed out); check `du` before copying, do not copy `wd3/pages`.
12. **Not decided by owner:** Kosovo ≡ Serbia, Heracleion (3.83 km), Narona, the 73 collective entities. The orchestrator decides under D8; I recommend keeping them refused and listed.
13. **Records disagree.** `FIELDS_WD3.md` and CLAUDE.md say Sonnet / no MiniMax; the files show 968 of 3,563 WD3 and all 260 WD4 decisions are MiniMax. Correct `FIELDS_WD3.md` and CLAUDE.md in the docs pass (D25).
14. **`output/` is gitignored in the main checkout but tracked in this worktree for some files** (`output/remediation/…` appears in `git`). Check `git status` before committing any run directory; bulk `DECISIONS.jsonl` stays unversioned and goes into the tgz archive at the end (`FIELDS_WD3.md` 4.6, 18).