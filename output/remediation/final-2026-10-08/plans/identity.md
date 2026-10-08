# Identity workstream plan: duplicates, scope, names, modern-town records, parents (2026-10-08)

Everything below was measured read-only. Work files are in `C:/tmp/wf_map_identity/`: `shown.csv`, `identity_candidates.csv`, `p31_tierA.csv`, `p31_tierB.csv`, `dups.csv`, `q1`–`q10.sql` and `py/`. No production writes and no downloads at scale. Wikidata entities for the P31 check come from the local harvest `output/remediation/fields/harvest/entities/` (2026-09-26, 205 MB).

## 1. Existing tools

All code is in the db-final worktree, `scripts/remediation/`. Run state is in the main checkout's `output/remediation/`.

| Need | Tool and runbook | Status |
|---|---|---|
| Duplicate retire | `mechanical/dups.py`, lane `dup-retire` (`lane.DUP_RETIRE`). Pinned to 5 pairs. Writes only `scope_status` and `scope_reason`, with `duplicate_of:<uuid>`. Three survivor invariants, 2 km cap (`DUP_RETIRE_METRES`). Run with `apply.py --lane dup-retire` (SITES_DB_REMEDIATION "Owner decision O9"). | Written 2026-10-01 (10 journal rows). Nothing half-way. |
| Duplicate scan | `scope.py` rule (c): within 100 m, both names are names of the shared item. `scope.survivor_rank`: older row, then more links, citations and images, then lower id. `bcases/classify.py` plus `bcases/dup_pairs.jsonl` (181 pairs: DUP 20, PART-OF 59, NEITHER 83, WRONG-ID 19), `DUPLICATES.jsonl` (19), `DUPLICATES_HELD.jsonl` (Banias). | Done. It does not move images or links. |
| Link, item and name repair | `l5/` is the best skeleton: `population`, `questions`, `decide`, `web`, `plan`, `run` (runbook "L5", SITES_DB_REMEDIATION line 1143). Link steps go through `output/remediation/tools/qid_repair.py render_split` (composite key, ≤100 sites per step). The name lane is `mechanical/lane.NAME_L5` and `name_fix.py` (the key comes from `site_key_sql` in SQL, never Python). | 159 decisions, written. 221 `site_external_ids` journal rows. 5 name writes. |
| Scope: not a site | `mechanical/scope_review.py` and lane `scope-review-<wave>` (WD2 doc §2). Needs ≥2 distinct websites with machine-found quotes (`opus_audit/quotes.py`). | R0 asked 567, R1 asked 3, R2 asked 2. Wave 2026-09-30 retired 20. |
| Scope: date window | `scope.py` rules (a), (b), (d), reading `DECISIONS.json`. | `scope-e4` applied 2026-09-23 (218 rows). The 2026-09-26 re-run of this rule after WD3/WD4 (`SCOPE_HANDOFF`) never ran. |
| Window SQL | `lane.outside_e3_window()`. Uses `period_end` if set, else `period_start`. Cutoffs: 500 rest of world, 1500 Americas and Oceania. | Used for the counts below. |
| Image moves and hero | `gallery_audit/chunk_writer.py` (UPDATE chunks, 0 DELETE). `import_hero/insert_writer.py` (INSERT lane). `hero_repair/`. | Not written for the duplicate case. |
| Calibration seal | `gallery_audit/calibrate.py` (seal, then jobs, then evaluate), `acceptance/SEAL.json`, `acceptance/PROTOCOL.md`. | Reuse as the pattern. |
| Answer registry | `opus_handoff.py` `ANSWER_MODELS` and `ANSWER_FAMILIES`. | Holds only opus-5-5, sonnet-5-5 and MiniMax. |

**What D6 requires in the registry.**
- Add `claude-haiku-5-5`: a `HAIKU_MODEL` stamp, an `ANSWER_FAMILIES` entry, and the `answer --model` choices.
- `model4.AI_SYSTEM*` is MiniMax-flavoured. Add a Claude-only disclosure string and add it to `AI_SYSTEMS`, keeping the old strings valid.
- About 12 test modules pin the model sets: `test_opus_handoff.py`, `test_phase4_model.py`, `test_scope_review.py`, `test_wn.py`, `test_teaser.py`, `test_fields_wd3.py` and others.
- `ANSWER_KEYS` is exactly 5 keys, so role and effort cannot be added as keys. Put `<role>:<effort>:<batch>` into `answered_by`, with a validator.

## 2. Measured state

**Scope**
- Production has 104 retired and 4,900 shown.
- Among curated rows: 17 `in_scope` (museums), 5 `pending`, 4,878 NULL.
- The 5 pending are Keno Daas, Situs Megalit Tebing Tinggi, Church of the Holy Apostles Peter and Paul in Serbia, Chacamarca and Northern Avenue Petroglyph.
- 127 shown sites are outside the window under the lane's own SQL: 110 undecided, 15 museums already `in_scope`, 2 pending. The census said 116 using another method.
- Origin of those 127: 77 come from WD3/WD4 `one_source` writes (45 + 28 + 2 + 2). WD3/WD4 were partly MiniMax-answered. Another 38 are WD1 `two_source`, and 11 were never written.
- Site types in the window: Museum 22, City/town/settlement 18, Minaret/tower 10 (brochs), Castle 5, Church 8.
- Hadrian's Wall Path (`360a4afb`): footpath opened 2003, `period_start` 2003, no scope decision.
- The only uncounted `not_a_site` left from the scope review is Pilares do Lena (3 asks, a 403 quote). Zenobia Cham Palace Hotel and Ġebel ġol-Baħar were counted and retired.

**Duplicates**
- 43 QIDs are shared by 98 shown sites. Group sizes: 38 of 2, 4 of 3, 1 of 10 (Kilmartin).
- Reading the names, about 25 of the 43 groups are real duplicates, about 8 are parts, and about 5 are wrong or class IDs.
  - Wrong or class IDs: Q927825 (Mortuary Temple of Seti I, Hawara and Khufu, 494 km apart), Q940097 (Taula, 18.7 km), Q1234523 (9 km), Q5276996, Q42873620.
  - Parts: Abu Simbel 3, Aspendos 3, Kilmartin 10.
- Distance bands per group: ≤200 m 27, ≤2 km 11, ≤20 km 4, >20 km 1.
- Extra funnels beyond shared QIDs: 12 enwiki-title groups with differing QIDs, and 81 pairs within 300 m with trigram name similarity above 0.5.
- 25 losers are already retired as `duplicate_of:`. 22 of them still hold images and 12 hold links.
- Dodona and Tarxien Temples hold 20 images while their survivors hold 0.
- Of the 25 retired losers, 12 have the loser name as an alias of the survivor.

**Modern-town records.** I built a three-signal funnel over the 4,900:

| Signal | Count |
|---|---|
| P31 of the linked item is a modern settlement class, with no archaeological class (tier A) | 346 |
| P31 modern plus an archaeological class (tier B) | 64 |
| Description sentence 1 opens "is a village/town/municipality/mountain…" | 129 (rx_pure 64) |
| Both P31 modern and description opening (A ∩ rx) | 97 |
| Union of P31 and description signals | **506** |
| Shared-QID sites (the Alba Fucens amphitheatre type) | 98 (5 overlap with the 506) |
| Combined funnel | ≈ 600 |

- Recall check: the 4 identity defects found by the sample audit were Bayston Hill, Chania, Ravenglass and Alba Fucens. The 506 catches the first three. Alba Fucens is caught by the shared-QID funnel.
- The census regex found 103.
- P31 alone is noisy. 265 of the 346 tier-A sites are typed City/town/settlement, and some Wikidata items are simply the municipality (Cave of Ardales). So the funnel only chooses what to ask.
- 28 entity files are missing from the harvest, and the harvest is from 2026-09-26. Refetch with `wbgetentities` (50 per call).
- Of the 506, description lane L is 305, W 177, S 19, N 4.

**Names**
- Union of hard defect signals: **1,030** names.
  - 457 have a comma qualifier, 61 a foreign-language prefix, 59 are longer than 40 characters, 43 have a parenthesis, and 15 are non-Latin script.
  - 8 mix scripts inside a word (for example `Κourion` with a Greek Kappa, `Roman Τheatre of Bosra`). 14 have digits. 2 have double spaces. 1 is all caps. 375 are comma-only.
  - 1,151 names differ from the English label (not a defect by itself).
- Name rows in `unified_site_names`: `wikidata_alias` 38,424, `wikipedia_title` 7,515, `label` 5,010. The code `lyra/site_identifier.py:2545` already writes `name_type='alias'`.
- 6 stale `label` rows exist, and the search reads `name_type <> 'label'`.
- 2,713 of 4,737 live card texts contain the site name. That conflicts with D1 and belongs to the card workstream.

**Parents.** `parent_site_id` is set on 0 rows. The column exists, with an FK of SET NULL, and `sites_html.py:466` already renders the "part of" link. Name-contained pairs by distance (same country, token subset):
- ≤200 m: 90
- ≤500 m: 147
- ≤1 km: 186 (100 distinct parents)
- ≤2 km: 203

**Spoken name.** There is no column and no key. `pipeline/video/shorts_tts.spoken_name(name, country)` builds the closing line from `name` alone.

## 3. Plan per decision

Order: 3.0 foundation, then D14 and D25 shared pieces, D13, D23, D20. Every write is a wave of ≤100 sites with its own stamp, run through the gates in this order: emit, check, verify, rehearse, probe-guards, apply, read-back, rehearse-rollback, 0 deviations.

### 3.0 Foundation (code, shared)

1. Registry changes from section 1, plus a role registry in a new `scripts/remediation/roles.py`. Each role is `(model, effort, calibration_set, threshold)`.
2. `lane.py` additions:
   - `CELL_TYPES` gets `uuid` and `boolean`.
   - `TARGET_KEYS` gets `wiki_images` and `site_content_links`, keyed by `id`.
   - New lane factories with wave labels, registered in `resolve_lane` (patterns `dup-merge-move-<wave>`, `dup-merge-retire-<wave>`, `parent-<wave>`, `name-clean-<wave>`, `spoken-<wave>`, `scope-window-<wave>`).
3. SEO fix before the first merge. In `api/routes/sites_html.py` (the `_site_410()` branches around lines 253 and 351), a loser whose `scope_reason` is `duplicate_of:<uuid>` with a shown survivor answers a 301 to the survivor's canonical URL instead of 410. Update `tests/api/test_sites_html_scope.py`. Renames already 301 through the id suffix. Retirements stay 410.
4. Migration `0029_unified_sites_spoken_name.sql`: `ADD COLUMN spoken_name text NULL`. Also update the `pipeline/database.py` model and `api/services/snapshots.py` `restore_snapshot` (which already omits `parent_site_id`). It runs in the deploy and is applied once.
   - I chose a column over a `raw_data` key. `raw_data` lanes compare the whole jsonb, and four writers already share it (provenance, citations, check, card).
   - Flag: memory says to ask the owner before pushing a migration, while D8 says deploy without asking. Confirm once.
5. Tests and mutation sweep: add sections to `mutation_sweep.py` for every new lane (new needles, as the `_DUPS_*` block at line 7691 does), plus `test_mechanical_dups_merge.py`, `test_identity_*.py`. Run `ruff format --check` on `scripts/` by hand, because CI does not cover it.

### 3.1 D14: merge the duplicates

**Discovery** (no model).
- Clusters from: the 43 shared QIDs, the 12 shared-enwiki groups with differing QIDs, the 81 name/point pairs, and `bcases/dup_pairs.jsonl` DUP and PART-OF.
- Output `DUP_CLUSTERS.jsonl` with the facts the judge needs: distance, images, links, text lane, QID items, `created_at`.

**Question stages** (one per cluster, about 100 clusters, 5 per batch).
1. **Verdict.** Sonnet 5.5 high, as web verifier. Verdict is one of MERGE(survivor), PART_OF(parent), WRONG_ID(repair via `qid_repair`), DISTINCT. It needs quotes from Wikipedia and Wikidata, and it must not use `scope.survivor_rank` blindly.
2. **Adversarial re-check.** Opus 5.5 high on every MERGE and PART_OF, about 60 clusters.
   - Survivor criteria: English name, a Phase-4 W text, images (Tarxien and Dodona swap survivors), links, item match.
   - Pilot judge: Opus xhigh over the first 10 verdicts.

**Calibration** (threshold sealed first).
- Positives, 25 judged: the 19 in `DUPLICATES.jsonl`, the 5 O9 pairs and Banias.
- Negatives, 15: Lycian Mezari 2 / Amyntas, Themistoclean Wall, and `NEITHER` and `WRONG-ID` pairs.
- The negatives are not Opus-judged today. One Opus xhigh gold labelling must fill them first.
- Seal at ≥92 % verdict agreement and 0 false MERGE. A role below that moves up one tier.

**Write path** (two lanes per wave, ≤100 sites).
1. `dup-merge-move-<wave>`:
   - `wiki_images.site_id` and `site_content_links.site_id` go from loser to survivor via `apply_remediation_change` (key `id`). A row whose `(site_id, original_url)` or `(site_id, content_source, content_id)` already exists on the survivor stays on the loser.
   - Moved rows get `is_hero=false` when the survivor has a hero. The loser's name goes to the survivor as a `unified_site_names` alias, written in the same transaction.
   - Invariants: at most one hero per site, a survivor with images keeps ≥1 live image.
   - The loser's premise (guard 5) is re-read after the move.
2. `dup-merge-retire-<wave>`: reuse `DUP_RETIRE` cells and invariants, data-driven from `DUP_DECISIONS.jsonl` instead of the hard-coded `PAIRS`. Distance limit is 2 km by default; pairs beyond it (Kilmartin at 2.1 km, Engomi at 2.06 km) need an explicit per-pair override with evidence.
3. Afterwards run `hero_repair` on the survivors and a `card_stats` wave. The `card_stats` premise includes images and links, so earlier ROLLBACK files expire.
- Rollback order: retire first, then move.

**Population.** About 25–30 retire pairs. The 8 PART_OF groups go to D25. The 5 wrong-ID groups go to `qid_repair`.
**Model answers.** About 100 Sonnet cluster verdicts plus about 60 Opus re-checks, plus the gold-labelling set of about 15, plus the pilot judge. Roughly 180 answers, around 36 agent calls.

### 3.2 D13: re-target the modern-town records

**Discovery.** New `scripts/remediation/identity/funnel.py`: P31 and description signals plus shared QIDs, deterministic, over the harvest entities and a current export. Output `IDENTITY_FUNNEL.jsonl` of about 600 sites, tiered (A ∩ rx first).

**Question** (`identity/questions.py`, modelled on `l5/questions.py`). The existing L5 gates can be reused: P625 within 1 km, article exists with no redirect and no disambiguation, quotes found.
- Q: what does this record designate at its stored point, and what is the ancient feature?
- Verdicts: KEEP (the ancient site is the subject, only the description opening needs work), RETARGET (name, new QID, enwiki title, new `source_url` and new coordinates, each with a quote), RETIRE (no ancient feature, goes to the scope lane), MERGE (to D14).
- Sonnet 5.5 high, 5 sites per batch. Opus 5.5 high re-checks every non-KEEP verdict, with the old and new item side by side.

**Calibration.**
- `bcases/names.jsonl` N7 (46: 27 `anchor-is-a-site` vs 19 `anchor-is-locality`) is the cleanest already-judged set.
- Add the 159 L5 decisions and the 4 sample-audit defects (Alba Fucens, Chania, Ravenglass, Bayston Hill), plus 26 non-defect sample sites.
- Seal at ≥90 % verdict agreement, 0 false RETARGET, 0 unverified quotes.

**Writes per RETARGET site, in this order.** One site finishes the lane chain before the next dependent lane starts.
1. **Links.** `l5/plan.py` link steps via `qid_repair.render_split`. `source_url` changes in the same step. L5 learned that the daily `refresh_site_external_ids` re-derives wrong IDs from `source_url` otherwise (invariant 4).
2. **Name.** `name-l5` pattern (`name` plus the key computed in SQL). The old name goes to `unified_site_names` as `name_type='alias'`. Lyra's boot adds the new label row.
3. **Point and type.** WD1/WD3 plan with the relaxed coastline guard from D19, and the site_type lane.
4. **Description.** Phase-4 lane W, which reads the site's `enwiki_title`, then WC. The pinned scope `SCOPE4.v3.json` (4,954 sites) must admit the site again, because the existing text carries the old basis. If it does not, use a new scope v4 or WN. WN could not be calibrated (1 site), so this needs a decision.
5. **Gallery.** Old rows from the town are marked `is_excluded` via `chunk_writer`. New rows come from the new item's Commons category through `candidate_search/` and the INSERT lane.
6. **Period.** Re-research (D12), which only makes sense after step 1.
7. **Card.** WB card lane and `card_stats`. The description hash changes, so every earlier card for the site is stale.

**Population.** Expect about 60–150 RETARGET sites; the pilot (20 sites) will measure the rate. The census named 103 and the A ∩ rx set is 97.
**Model answers.** About 600 Sonnet verdicts (120 calls) plus about 200 Opus re-checks (40 calls) plus 1 pilot judge.

### 3.3 D20: scope review

**Population.** About 131 sites: the 127 in-window, the 3 pending not in window, and Hadrian's Wall Path (already among the 110). Add the 7 undecided in-window museums to the museum sub-question (scope rule (d): ancient exhibits, with a quote). Pilares do Lena is a leftover `not_a_site` case.

**Order.** Run after the D12 period re-research of those 127. 77 of them have MiniMax `one_source` periods that may be rule-made.

**Question** (new `scope_window.py`, prompt `scope-window-v1`). It gets the site's own description, the period evidence and the sources.
- Verdicts: PERIOD_WRONG (corrected sourced start, which goes through the WD4 fields lane), OUT_OF_WINDOW (retire), MUSEUM_KEEP, NOT_A_SITE (modern; Hadrian's Wall Path, 2 websites).
- Sonnet 5.5 high does the research. Opus 5.5 high re-checks every OUT_OF_WINDOW and NOT_A_SITE, because a retire becomes a 410 for that URL.

**Calibration.**
- The 51 museum decisions of scope-e4 (41 stay, 3 leave, plus `DECISIONS.json` with 36 entries: 17 in_scope, 14 pending, 5 retired).
- The 11 Phase-3 moved-out cases.
- R0's 20 counted `not_a_site` against 20 sampled `site` verdicts.
- Seal at ≥90 % agreement and 0 false retire.

**Write path.** `scope-window-<wave>` is the `scope_review_lane` shape (cells `scope_status`, `scope_reason`, guard 5 premise). Transitions `pending`→`retired` and `in_scope`→`retired` must be proven by probes. The `scope_reason` text is `E3: period_start N is past the cutoff; <quote>`. A site a model wants to keep gets `in_scope`.
**Model answers.** About 131 Sonnet verdicts (27 calls) plus about 100 Opus re-checks (20 calls) plus a pilot judge.

### 3.4 D23: names

1. **Clean name.**
   - **Triage.** Deterministic triage of the 1,030 funnel names into: mixed-script (8), whitespace/caps (3), digit and parenthesis, foreign prefix, comma-only (375), and the rest.
   - **Decision.** Cases where the English name is not an attested form get a Sonnet 5.5 high web verifier (about 150–300 sites). The accepted new name must be the English label or alias of the linked item, or its `enwiki_title` (the `name_fix` and L5 rule). Opus re-checks each rename.
   - **Write.** `name-clean-<wave>` using `NAME_FIX`. It converts the old name to `name_type='alias'`.
   - **Calibration.** The 2 `name_fix` renames, the 5 journalled renames, and the N7 `RENAME` verdicts.
2. **Spoken name.**
   - **Derivation.** For every Shorts-pool site (about 3,751 sites with an accepted text; D4's pool is about 2,300).
     - Rule first: drop `, <qualifier>`, parentheses, trailing numerals, and pick the shortest attested English form among label, alias and `enwiki_title`.
     - A rule-resolved name never needs a model. About 85 % should resolve that way (estimate; measure at the pilot).
     - The rest, about 350–550 names, go to Sonnet 5.5 medium, constrained to attested forms plus a TTS-safe spelling (for example `Qʼumarkaj`, `Jabal al-ʿHayn`).
   - **Write.** `spoken-<wave>`, a text cell, fills NULL.
   - **Shorts side.** Only a one-line change in `shorts_tts.spoken_name`: use `site["spoken_name"] or site["name"]` and add the field in `shorts_export.assemble_site`.

### 3.5 D25: `parent_site_id` for component sites

**Candidates.** 203 name-contained pairs within 2 km (100 distinct parents) plus the PART_OF verdicts of D14 (Abu Simbel, Aspendos, Kilmartin 9 children, Paphos).

**Question.** Per parent, Sonnet 5.5 high, with a Wikipedia or Wikidata `P361` or quote that the child is a part. Opus 5.5 high re-checks the parent choice.

**Write.** `parent-<wave>`, column `parent_site_id` (a `uuid` cell). Invariants:
- parent is shown, not retired, and not itself (depth 1)
- same country
- distance ≤ 5 km
- the parent is not a duplicate loser

**Order.** After D14. A merged loser must never be a parent.

**Calibration.** The `PART-OF` class of `dup_pairs` and the 8 PART_OF groups from D14.
**Model answers.** About 100 Sonnet clusters (20 calls) plus about 50 Opus re-checks.

## 4. Dependencies on other workstreams

- D12 period research must come first for the 127 window sites. It must run after D13 for retargeted sites, because the referent has to be settled first.
- A retarget or a merge makes the description, gallery, hero and card stale. They need W/WN/WC, D15/D17 image lanes, WB, and `card_stats`.
- D19 coordinates: retarget steps need the relaxed coast guard. Do not research coordinates of a site that may be retired.
- D17 (952 no-image sites) overlaps merge survivors, which gain images. Run D17 after D14.
- D1 and the card lane: names should be settled before cards are rewritten, so the "no name token" check is stable. The D13 funnel sites must stay out of the card pilot until resolved.
- D25's other items (static export automation, `card_stats`, 82 stale Wikipedia IDs) overlap the link repair: handle the 82 stale IDs in the same `qid_repair` steps.
- The model registry (3.0) blocks every other workstream's Haiku use. It should land first, owned by the orchestration workstream.

## 5. Answer estimates (Sonnet and Opus, per D6)

| Stage | Role | Model, effort | Answers |
|---|---|---|---|
| D14 verdict | web verifier | Sonnet high | ~100 |
| D14 re-check | adversarial | Opus high | ~60 |
| D13 identity | web verifier | Sonnet high | ~600 |
| D13 re-check | adversarial | Opus high | ~200 |
| D20 window | period/field research | Sonnet high | ~131 |
| D20 re-check | adversarial | Opus high | ~100 |
| D23 clean name | web verifier, then re-check | Sonnet high, Opus high | ~250, ~100 |
| D23 spoken | research | Sonnet medium | ~450 |
| D25 parents | web verifier, then re-check | Sonnet high, Opus high | ~100, ~50 |
| Calibration sets | roles under test | one tier each | ~60 per role |
| Pilot judges | pilot verdict | Opus xhigh | 5 pilots × ~20–30 |

Total about 2,100 answers, about 450 agent calls at 5 sites per batch. Haiku low is only used for operator commands, not for judgements. At most 2–3 parallel fetchers, so run the wave stages sequentially.

## 6. Risks and traps

- **Wikimedia throttling.** At 4+ parallel fetchers, 403 or 429 gets recorded as `UNVERIFIABLE`. Never score a 403 or 429 as a finding. Re-test with curl.
- **Lanes write once.** A lane that has written is never re-planned (its stamp is used up). Plan waves from a fresh export, and re-ask `premise-moved` sites in the next round.
- **Retire is a 410, merge must be a 301.** Fix `sites_html.py` before the first merge (3.0 step 3), or Search Console keeps a 410 for a page that now has a canonical twin.
- **`card_stats` guard 5.** It hashes images, links, description and `(site_type, period_name)`. A merge or a retarget expires earlier card ROLLBACK files.
- **`name_normalized`** is a Postgres key (`left(lower(unaccent(name)),500)`); compute it in SQL via `site_key_sql`, never in Python. 80,083 rows are divergent across 28 external sources, so the Lyra boot reconcile is scoped.
- **Daily external-ID refresh.** `refresh_site_external_ids` re-derives IDs from `source_url`, so a link repair without a `source_url` change is undone.
- **MiniMax history.** 77 of the 127 window starts, and the 361 WD3/WD4 sites in D10, were MiniMax-answered with no recorded owner release. D10 re-check must cover any of them before they decide a retire.
- **The model census issue.** FIELDS_WD3.md claims Sonnet, but the decision files show MiniMax. Do not trust prose; read the answer stamp.
- **Ambiguous owner call.** The 73 "collective entities" with unsourced points (Danubian Limes and similar) are not covered by D13/D14/D19 and need a decision before they are retired or merged.
- **UNESCO** (`whc.unesco.org`) answers httpx with a Cloudflare challenge, so it counts as unverifiable for quotes. The two-website rule needs another host.
- **Windows.** `PYTHONIOENCODING=utf-8` for all runs (a cp1252 crash killed a wave once). Scratch scripts go in a subfolder of `C:/tmp`, never `%TEMP%` itself (the `gettext.py` shadow). `ruff format` 0.15.11 by hand for `scripts/`.
- **Disk.** This workstream is small: ~50 KB per cached page, so ~600 sites × 5 pages is under 200 MB. Nothing here needs the 14 GB.