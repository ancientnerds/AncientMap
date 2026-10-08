# Plan: images workstream (D15, D17, D18; D16 deferred)

Everything below was read or measured read-only on 2026-10-08. The only SQL files are `C:/tmp/wf_map_images/q1..q3.sql`. The probe scripts are in `C:/tmp/wf_map_images/py/`. No production write and no Shorts work.

## 0. Findings that change the brief

1. **The 5,739 candidate verdicts are not a gold set.** `candidates-2026-10-06/VERDICTS.jsonl` was answered 100 % by `MiniMax-M3.1-Flash-Preview`. The judge never had a calibration entry, and `judge.check_answer` accepts any non-empty `model` string.
   - Use them as a pool of hard negatives, to be re-judged by Claude.
   - They are also a D10 re-check population (the 192 first heroes came from them).
   - The gold has to be Claude- or human-made (section 4).
2. **The "owner-labelled" 652 rows are Claude-labelled.** The fixture `tests/remediation/fixtures/gallery_labels_652.jsonl` comes from the 2026-09-19 audit workflow, not from the owner by hand.
   - It holds `fremde_staette` 64, `karte_oder_plan` 22, `gemaelde_oder_zeichnung` 23, `diagramm_oder_text` 19, `modernes_umfeld` 13, `sonstiges` 31.
   - The only hand-set truths are the owner's 2025 hand-links (positives) and the 42 gold-gallery rows (12 foreign, 13 correct named).
   - The 2026-09-25 Opus C1 calibration failed every admission: X1 precision 0.515 against the labels, so label noise is real. Thresholds must therefore be on false-depicts, and disagreements must be adjudicated, not scored against the raw labels.
3. **The 09-30 served-image verdicts are Claude's.**
   - `served-image-2026-09-30/CHECK.jsonl`: 4,084 verdicts from Opus (180 batches) and Sonnet (158 batches).
   - `REPLACE.jsonl`: 15,279 candidate verdicts.
   - Together they are the best large reference set for Haiku and Sonnet agreement.
4. **The two sample batches cover the claim population only partly.** 72 of the 133 claim-bearing sites in the 952 are not in `REPLACE.jsonl` of 09-30. Those are the "P18/P373 never read" sites; the census counted 11 with confirmed claims.
5. **Wikidata-only identity gives almost no images.** On a 30-site sample of the 531 sites that have a QID but no claim and no Wikipedia lead image:
   - commonswiki sitelink: 0 of 30
   - Commons structured-data search `haswbstatement:P180=Q…`: 2 of 30
   - Commons category files: 0
   - Geotagged Commons files (`list=geosearch`, namespace 6): at least 1 file within 1 km for 18 of 30 sites, within 300 m for 15 of 30. Mostly UK, Greece and Italy.
   - This is a new candidate route. It is high recall, low precision, and needs sourced coordinates.
6. **D18 backfill is only about 23 % possible from Commons.** Live rows on shown sites that need attribution and have no author: 408 now (census 419), 277 sites, 48 heroes, all created 2026-03. I probed all 408 file pages against Commons today.
   - 250 have no `{{Information}}` template at all.
   - 66 have an empty `author=`.
   - About 84 are self-licensed (`{{self|…}}` or own work), so the uploader is the author.
   - About 8 have an author text.
   - Roughly 90 to 100 rows are deterministically fillable. About 300 have no author on Commons.
   - The T09 lane of 2026-09-23 already resolved 72 and refused 455. Of the refusals, 438 were "no route applies".
   - Using the uploader for non-self files would be a guess, which the T09 rule forbids ("a wrong credit is worse than none").
7. **License URL rule trap.** `license_url` is empty for all 5,285 "Public domain" rows, all 124 "Attribution" rows and all 106 "Copyrighted free use" rows. A literal "author + licence URL required" would refuse every public-domain file. Recommend: `license_url` required only for attribution-requiring licences. Public domain and CC0 need neither author nor URL. The existing gallery has `author_url` empty on thousands of CC rows (about 1,222 of 10,555 CC BY-SA 3.0).

## 1. Existing tools (paths and commands)

All paths are under `.worktrees/db-final/`.

| need | tool | where it is documented |
|---|---|---|
| Doc | `docs/procedures/WD2_SERVED_IMAGE_AND_SCOPE.md` | §3.5 served-image runbook, §3.7 import-hero and INSERT lane, §3.7.3 candidate search and judge, §4 tests |
| Check and replace stages | `scripts/remediation/served_image/run.py` | `read, precheck, export-check, brief, check-answer, import-check, export-replace [--claimed-only], import-replace, no-image-report, plan, accept` |
| Writer | `scripts/remediation/gallery_audit/chunk_writer.py` | `--check, --rehearse, --apply, --readback, --rehearse-rollback`, one at a time. Rules `wd2-exclude`, `wd2-hero`, `wd2-align`, `wd2-thumb` |
| Candidate search | `candidate_search/{search,run}.py` | Commons name search, `intitle:`, category by name. 12 hits per query, floor 800x300 |
| Candidate judge | `candidate_search/{judge,judge_run}.py` | `judge-export`, `judge-import`, `write-targets`, `insert-claims`. Batches of 36 images, at most 6 sites, folders `cand-NNNN` |
| INSERT lane | `import_hero/run.py` (`read, fetch --target insert, insert-plan, insert-accept, insert-seed`) and `import_hero/insert_writer.py` | `FETCH_COLUMNS` (11) and `INSERT_COLUMNS = FETCH_COLUMNS` (14 journal rows per site). The floor is a run parameter (`FLOOR.json`) |
| Attribution lane | `gallery_audit/attribution.py` (`--plan`, `--recheck`, then `chunk_writer` chunks) | Routes A1 to A4. Output `gallery_audit/attribution-2026-09-23/` (72 evidence lines, 455 unresolved) |
| Handoff transport | `scripts/remediation/opus_handoff.py` | `validate`, `answer`. `ANSWER_MODELS` and `ANSWER_FAMILIES` hold only opus-5-5, sonnet-5-5 and MiniMax-M3.1-Flash-Preview |
| Calibration pattern | `gallery_audit/calibrate.py` (`seal, jobs, vision, evaluate`), `labels.py`, `gold_standard/compare_fnr.py::clopper_pearson` | Thresholds sealed in `THRESHOLDS.json` and `SEAL.jsonl` before any answer. Today it refuses a directory sealed for another model (`vision.MODEL = OPUS_MODEL`) |
| Mutation sweep | `scripts/remediation/mechanical/mutation_sweep.py wd2` | `WD2_CASES` has 84 cases. Tests: `tests/remediation/test_import_hero*.py`, `test_candidate_*.py`, `test_served_image.py`, `test_gallery_attribution.py`, `test_opus_handoff.py` |

`scripts/remediation/{,served_image/}mcode_driver.py` drive MiniMax. They are not used here (D6). Claude subagents answer through the handoff files instead.

## 2. Current run state (measured today)

- **Production read at 19:09 UTC.** 952 shown curated sites serve nothing: 723 with no row, 229 with every row excluded. The set is the same as RESTBESTAND_2026-10-07 (952 of 952). All 952 have a card. Tiers: 4 = 24, 3 = 312, 2 = 495, 1 = 121.
- **Closers** (`rest.jsonl`):
  - `search_no_candidate` 461
  - `judged_no_depicts` 369
  - `not_reached` 49
  - `insert_refused` 48
  - `search_all_too_small` 25
- **Identity** (`noimg_probe.json`):
  - 756 have a QID and 751 have an enwiki title.
  - **196 have neither** (tier 1: 6, tier 2: 75, tier 3: 98, tier 4: 17).
  - 124 have P18 and 85 have P373. Together 133 sites carry a claim.
  - 182 have an enwiki lead image. 225 sites have a claim or a lead.
  - 727 sites have nothing on the Wikidata or Wikipedia side.
  - Several enwiki links are known wrong: Pukara, Vilcas Huamán, Blaškovina, Sallachy Broch, three Gyeongju "Belt" sites. Identity must be verified before any image follows.
- **Coordinates.** All 952 have lat/lon. 178 have a description under 300 characters and 12 have none. Whether each point is sourced is not measured per site (430 are unsourced in all 4,900).
- **Candidate run state** (db-finish worktree):
  - Pictures still exist locally in `candidates-2026-10-06/pictures`: 5,756 files, 2.5 GB. No re-download is needed to re-judge.
  - 589 sites have verdicts. Of those, 411 are still in the 952: 3,153 verdicts at 363 sites (`judged_no_depicts`) and 597 verdicts at 48 sites (`insert_refused`).
  - 226 targets were set, 178 were written and 48 were refused.
- **INSERT waves** `insert-2026-10-06-001` to `insert-2026-10-07-011` are all `ok: true`. The tree is at 50,428 `.webp`. Nothing is half-way.
- **D15 population.** `C:/tmp/wf_images/os_ids.txt` holds 47 `wiki_images` ids. All 47 are still live heroes today (query q1).
  - Original judges: 41 Sonnet and 6 Opus. 34 came from the REPLACE stage and 13 from CHECK.
  - Sizes: 41 are at least 1600x900, and 3 are under 800x300 (Land of Tema 800x340 is one).
  - **23 of the 47 sites have no other judged-`depicts` row** (single-row sites). Clearing them puts them into the D17 pool. 24 have an alternative hero.
  - Names: Talaiot y Taula de Trepucó, Caunos Tombs of The Kings, Luoyang, Lygourio, Plain of Jars Site 3, Amman Citadel, Seville, Glevum, Colebrooke, and others.
- **D18.** 408 attribution rows without an author (see section 0).
  - Fetch refusals among the 48 `insert_refused`: `author_url` only 13, `author_url` + `license_url` 10, `license_url` only 3, filename or type 6, others (size, upscale, already held).
  - D18 as written releases only the 13 certain ones. The 10 "both" need a `license_url`. The 3 are probably public-domain or free-use licences.
- **Disk.** C: has 24 GB free. The local candidate pictures are 2.5 GB. A new run is estimated at 1 to 2 GB, and the INSERT fetch at about 100 to 200 MB.

## 3. Steps per decision

### Shared first change (coordinate with the cards workstream; one commit)

`scripts/remediation/opus_handoff.py` needs:
- `HAIKU_MODEL = "anthropic/claude-haiku-5-5 (Claude Code agent)"`
- `ANSWER_MODELS["claude-haiku-5-5"]`
- `ANSWER_FAMILIES["claude-haiku-5-5"] = "haiku"`
- the pinned stamp test in `tests/remediation/test_opus_handoff.py`
- the other importers: `fields/handoff.py`, `phase3/model_stage.py`, `phase4/handoff4.py`, `teaser/run.py`, `mechanical/scope_review.py`, `served_image/vision.py` (`MODEL`).

Add a new `scripts/remediation/roles.py`: `ROLE_MODELS = {role: (model, effort)}`, plus a `calibration_sha256` field in every answer.
- The stamp stays the real model. `answered_by` gets the role prefix (for example `img-prefilter-haiku-low-0007`).
- `judge.check_answer` must also validate `model` against `ANSWER_MODELS`.
- For this work, reject the MiniMax stamp.

### D15: the 47 heroes

1. **Reuse, small change.** Add `--sites FILE` to `served_image/run.py export-check` and `export-replace`. Make a fresh run directory `served-image-2026-10-08-os47` with `read`, `precheck`, then the two stages restricted to the 47 sites.
2. **Re-check (Opus, high).**
   - Check stage: 47 images in 4 batches of 12. The prompt carries the site's description, coordinates, the Wikipedia lead image and the 2025 link.
   - Replace stage: roughly 24 sites with other rows, about 8 batches.
   - A verdict of `other_site` needs a written reason naming what the picture shows. An `other_site` also needs a Commons category or file-page check by the agent.
3. **Outcomes** (the `plan.py` table):
   - Confirmed `other_site` with a `G` depicts pick: row excluded, hero flag and thumbnail moved to the pick.
   - Confirmed `other_site` with no pick: cleared. The site joins the D17 pool, and its excluded file is listed so it is not re-offered.
   - `depicts` or `region_or_type`: the hero stays (the owner's 2025 link).
4. **Write.** One chunk through `chunk_writer.py` (`--check`, `--rehearse`, `--apply`, `--readback`, `--rehearse-rollback`) and then `run.py accept` with 0 deviations. Stamp `served-image-2026-10-08-os47`. Estimated 100 to 150 journal rows.
5. **Follow-up.** A `card_stats` recompute is needed because `thumbnail_url` is a card input. Include the 19 strip heroes (Gyeongju 800x128 and others) in this chunk. That is a recommendation only: the owner called swapping to a larger row his decision in the 2025-link context.

### D17: the 952 (plus up to 23 cleared by D15)

**Stage 0: population.** Re-derive it at write time with the `pic0.csv` query (shown, not retired, no live row, `thumbnail_url` empty). Drop sites retired by D20 or merged by D14 meanwhile.

**Stage A: identity, mostly code.**
- Read QID, enwiki and the Wikidata coordinates from `site_external_ids`, as the single source (the pre-check used the WD1 harvest instead).
- Flag a site when its Wikidata point is more than 10 km from the site point, or the label shares no token with the name. Expected 100 to 150 sites, which go to a **Sonnet high** web verifier, batches of 5, about 30 answers.
- 196 sites have no identity: **Sonnet high** with WebSearch, finding the Commons category, the Wikipedia article and the local name. The 461 sites where Commons has no file under the curated name need the local name too, so about 727 sites are researched in batches of 4 (about 180 answers).
- Output: a per-site `IDENTITY.jsonl` with the evidence URL of every link claimed.

**Stage B: candidates** (extend `candidate_search/search.py`, `why` tagged per route):
1. P18 and the first 12 P373 files (the existing `served_image.vision.wanted_files`; `export-replace --claimed-only` covers this and reads `site_external_ids`).
2. The commonswiki category, SDC `haswbstatement:P180=Q`, and the enwiki lead and page images.
3. The existing name queries, plus the researched local names.
4. `list=geosearch` within 300 m, at most 20 per site, ordered by distance. Only for sites with a sourced point, so it should run after D19.
- Exclude files the site already holds or that a previous pass judged not-depicts.
- Floor 800x300, the existing run parameter.
- Cache and pace as today (1 request per second, at most 2 parallel).

**Stage C: Claude vision roles.**
- **C1 prefilter, Haiku 5.5 low.** Per candidate, at 640 px, kind from the existing `KINDS` (`site_photo, artifact, map_or_document, painting_or_artwork, people, other`) plus a "usable for a site page" flag. Batches of 60.
- **C2 "shows this site", Sonnet 5.5 medium.** Survivors at 1280 px, batches of 36 packed by site. The prompt is English and richer than the old name-and-country one: type, description lead, coordinates, Wikipedia lead sentence, candidate source and geotag distance, and the judge line recorded for streets, museum coins and generic names (a refusal beats a false `depicts`; the filename lies). One verdict per candidate, plus a quality score so the hero is the best row, not the largest.
- **C3 adversarial re-check of each hero pick, Opus 5.5 high.** About 250 to 350 images, 12 per batch.
- **C4 re-judge the MiniMax pool** (D10). The 3,750 verdicts at the 411 still-pictureless sites go through C1 and C2 using the pictures already on disk (about 100 answers). The 226 targets go through C3 (about 20 answers). Any MiniMax `depicts` that Claude denies and that was already written (among the 192 first heroes) is excluded or swapped through the writer.

**Stage D: write.** Per wave of at most 50 sites:
```bash
PY=./.venv/Scripts/python.exe; IH=scripts/remediation/import_hero
$PY scripts/remediation/candidate_search/judge_run.py write-targets  --run-dir <run>
$PY scripts/remediation/candidate_search/judge_run.py insert-claims  --run-dir <run> --insert-run $I
$PY $IH/run.py read   --run-dir $I
$PY $IH/run.py fetch  --run-dir $I --root $OFFSITE --target insert    # floor 800x300
$PY $IH/run.py insert-plan --run-dir $I
for s in --check --rehearse --apply --readback --rehearse-rollback; do $PY $IH/insert_writer.py $I/chunk-001 $s; done
$PY $IH/run.py insert-accept --run-dir $I
```
- Then pack the files, transfer them to the VPS, and verify byte-exact in the api container and over HTTP.
- After the last wave: a `card_stats` recompute and the static export (stale since 10-06).
- Journal: 14 rows per inserted site.
- `write-targets` today takes only the largest `depicts`, one row per site. Change it to take the best-quality pick. Extra gallery rows per site are D16 and are not done here.

**Expected yield (honest estimate, uncertain).** The earlier name search gave 226 of 595 sites. Of the 952, about 225 sites have a claim or lead and about 727 have nothing on the Wikidata side. I expect 150 to 300 new heroes (16 to 31 %). The rest stay empty and go to the owner list as "unsourced, no image", with the measured reason per site. No Commons-only image source exists for the unnamed ones.

### D18: credit rule and author backfill

1. **Rule change.** In `import_hero/fetch.py::manifest_entry`, replace the check `missing = [c for c in FETCH_COLUMNS if not entry.get(c)]` with one that exempts `author_url` always, and exempts `author` and `license_url` for non-attribution licences. Define "attribution-requiring" as CC BY*, CC BY-SA*, GFDL, OGL and the other licence names found in the data. `plan._fetch_changes` already tests `is None`, and the INSERT temp table takes TEXT, so an empty string passes. Store the missing `author_url` as NULL, the form the gallery uses.
2. **Tests and mutation cases.** `test_import_hero.py` and `test_import_hero_insert.py` (the rows with `author_url` None at lines 102 and 803), plus new `WD2_CASES` for: author required, `author_url` not required, `license_url` required only for attribution licences, public domain passes with neither.
3. **Re-ask the 48 `insert_refused`** (plus the 26 credit refusals recorded across the earlier waves) as an `insert-seed` wave. Expected release: the 13 `author_url`-only sites certainly, up to 26 with the exempted licences. The size, upscale, filename (`"` in the name) and type refusals stay refused by name.
4. **Backfill.**
   - Extend `gallery_audit/attribution.py` with route A5: self-licensed (`{{self|…}}` or Credit "Own work") plus the file's first-version uploader as author, with `author_url` = the user page.
   - Re-run `--plan` on the 408. Expected 90 to 100 rows. Chunks of 100 sites through `chunk_writer`, stamp `attribution-2026-10-08`. Only rows with an empty author are touched.
   - The roughly 300 without an author on Commons go to the owner list. The Shorts exporter must refuse such a row (today it prints "Unknown"; that is a Shorts-side change the card lane needs).
   - For the 48 heroes in that set, use the D15-style swap to a credited row where one exists.
   - Ask Sonnet nothing here: it is deterministic and needs no model.

## 4. Calibration (sealed before the run; a failing role moves up one tier)

Use the `calibrate.py` pattern: seal `THRESHOLDS.json`, then `JOBS.jsonl`, then run, then `evaluate`. Make it role-aware in a new `image_roles/calibrate.py`. Report Clopper-Pearson intervals.

- **Gold set.**
  - Adjudication: Opus xhigh labels 150 candidates drawn from the MiniMax pool (50 per verdict class), with web evidence. That is the pilot-judge gold.
  - Positives: 150 owner 2025 hand-linked heroes, excluding the 47 and the 192.
  - Hard negatives: the 64 `fremde_staette` rows, the 12 gold-foreign rows, 60 of the 192 Claude `other_site` verdicts, and the Mars-map, coin and modern-scene cases.
  - Kind gold: Opus C1 `VERDICTS.jsonl` (939), 300 stratified.
- **Haiku prefilter.** Photo versus non-photo agreement at least 0.92, and recall of items Opus would call depicts-capable at least 0.98. Failing moves it to Sonnet low.
- **Sonnet "shows this site".**
  - Sensitivity on the owner-linked heroes at least 0.90.
  - False-`depicts` rate on the hard negatives at most 3 % (precision at least 0.95, lower interval bound reported).
  - All gold-foreign rows flagged not-depicts.
  - Failing moves it to Sonnet high, then Opus medium.
- **Opus re-check.** Agreement with the xhigh adjudication at least 0.95.
- **Identity researcher, Sonnet high.** On the 5 known wrong links plus 20 known good ones: at least 0.90 correct, and all 5 wrong links flagged.

The numeric thresholds are my proposal; the orchestrator must seal them before the first call.

## 5. Estimated model answers (agent responses)

| stage | role | answers |
|---|---|---:|
| D15 check and replace | Opus high | about 12 |
| Identity verify | Sonnet high | about 30 |
| Name and identity research | Sonnet high | about 180 |
| Prefilter (about 11k items) | Haiku low | about 180 |
| Prefilter, MiniMax pool re-judge (3,750 items) | Haiku low | about 60 |
| "Shows this site" (about 6k survivors) | Sonnet medium | about 170 |
| "Shows this site", pool re-judge (about 2.2k) | Sonnet medium | about 60 |
| Hero re-check (about 300 + 226) | Opus high | about 45 |
| Calibration, all roles | mixed | about 40 |
| **Total** | | **about 780** |

## 6. Dependencies on other workstreams

- **D13 re-target and D14 merge.** They change the site's name, QID and gallery. Eight shown picture-less twins (Tarxien, Dodona and others) hold 18 to 20 images on their duplicate; the merge moves the rows, so remove them from D17. Run D17 after D13, or re-derive the population at write time.
- **D19 coordinates.** The geosearch route needs a sourced point. Run it after D19, and skip it for the unsourced points.
- **D20 scope.** Retired sites drop out of the population.
- **D23 name cleaning.** Search terms change, and the old name becomes an alias.
- **Cards.** Image writes change card inputs (`has_thumbnail`, `thumbnail_url`). A `card_stats` recompute follows each chunk batch, and the static export is needed for the globe. Shorts eligibility needs at least 6 images, which D16 defers; a hero alone does not make a Short.
- **Shared stamp change.** The `opus_handoff.py` Haiku stamp is also needed by the cards workstream. Decide one owner.

## 7. Risks and traps (from AUDIT_LOG, runbooks and memory)

- **Wikimedia throttle.** At most 2 to 3 parallel fetchers, 1 second pace. A 429 on `judge-export` is recorded as a refused candidate, so the site silently loses a picture (the `PACE` constant was once dead code). General search engines are blocked here; Wikipedia and Wikidata APIs and the WebSearch tool work.
- **Rate-limit sizing.** About 16k thumbnail requests serial is roughly 4 to 5 hours. The 5,756 pictures already on disk need no re-download.
- **Disk.** 24 GB free. Keep Haiku at 640 px, delete pictures after the verdicts are stored, and keep only the verdict and sha. No step downloads at scale beyond about 2 GB.
- **The five writer steps exclude each other.** They are five separate calls in the stated order. Do not chain them on one command line.
- **Floor is a run parameter.** It must reach the SQL guard (`render_apply(..., floor=)`), or the rehearsal fails on its own rows (found on wave -010).
- **`ih4`.** The thumbnail must name the row the site serves, not the fetched name (found on wave -004).
- **`Commons.sizes` lookup.** Key by the canonical name. A `File:` prefix returned (0,0) and produced two false refusals.
- **`imageinfo` returns no size** unless `dimensions` is requested.
- **WD2 rule.** Unhiding a judged row needs a new judgement. D15 is exactly that; the 47 un-excluded heroes contradicted the rule.
- **A retired-site filter is mandatory** in every count (54 false "thumbnail mismatches" were retired sites).
- **Wikidata label is not the Wikipedia title.** Check identity before any Wikipedia-led search.
- **Wikidata and enwiki links are not trustworthy** for the known cases in section 2.
- **Museum objects, coins, street names, generic names** produced 1 `depicts` in 57. The filename lies.
- **Names with `"`,** `.tif` and SVG files are refused by the lane's own rules (about 9 sites); the original-smaller-than-floor and no-file classes are facts about the files.
- **Python on this machine.** `print` of non-cp1252 characters crashes. Use `sys.stdout.reconfigure(encoding="utf-8")` in scratch scripts. Downloaded content is untrusted: run readers with `-I` and keep scripts in a different directory.
- **Static export.** `public/data/sites/index.json` is stale since 2026-10-06 (983 sites differ). Hero changes show on the page at once but on the globe only after the next export.
- **Not decided by D15 to D18, but adjacent:** 22 broken or third-party thumbnails (9 hotlinked, 12 `/thumb/`), 20 sites with a lead row but no hero flag, 433 small heroes. Handle them with the D15 chunk or list them for the owner.