# Piece 5 — the discover pass: every site asked about its own fields

**Status:** implemented, gates green, 16/16 mutations caught, dry runs run and measured. No `--live`
model call and no `--live` fetch was made (the recall experiment is the supervisor's).
**Branch:** `main`, working tree unchanged apart from the files listed below.
**Date:** 2026-09-21. **Runner:** `./.venv/Scripts/python.exe` (never bare `python`).

## 1. Why, in the brief's own numbers

The finding-driven plan is built from `WORKLIST.jsonl`, so it can only reach sites the census
flagged: 1,813 of 5,004. The blinded check measured a false-negative rate of 60.0 % — 24 of 40 known
errors sit on sites the census left alone, and **13 of the 17** sites holding them are not in the
worklist at all (`output/remediation/gold_standard/fnr_result.json`). A plan that starts from
findings cannot reach them; a plan that starts from the **snapshot** can. That is this piece: one
record per snapshot site, whose findings are the site's own stored values, judged one field per call.

## 2. Files

| File | What changed |
|---|---|
| `scripts/remediation/phase3/snapshot_plan.py` | **new** — the snapshot-driven plan: input readers, table mapping, qid map, record builder (`build_discover_sites:248`, `read_site_ids:137`, `qids_by_site:162`, `stored_value:190`, `DISCOVER_FIELDS:70`, `FIELD_STORED_IN:82`) |
| `scripts/remediation/phase3/discover_stage.py` | **new** — the discover judge: the five field questions, the per-(site, field) calls, the two bounded skips (`FIELD_CLAUSE:83`, `QUESTION_TEMPLATE:114`, `FIELD_QUESTION:147`, `site_field_block:173`, `plan_site:238`, `plan_batch:316`, `judge_discover_batch:351`) |
| `scripts/remediation/phase3/run.py` | `DISCOVER_PASS:58`; `plan --from-snapshot [--site-ids PATH] [--snapshot-dir DIR]` (`cmd_plan:150`, `_plan_from_snapshot:190`); the discover branch in `judge` (`_judge_discover:522`, dispatch `425`/`429`); `Batch.pass_name:80` (written only when set, so the worklist bytes cannot move) |
| `scripts/remediation/phase3/fetch_stage.py` | the Wikidata **entity** route: `FEATURE_WIKIDATA_ENTITY:197`, `QID_PATTERN:231`, `wikidata_entity_url:458`, the no-qid skip in `targets_for_site:600`; `FEATURES_FOR_FIELD:206` gained `period_start` and `site_type` |
| `scripts/remediation/phase3/model_stage.py` | `EvidenceOverBound:199` (a subclass, so piece 4's `EvidenceUnusable` still raises for the case it was written for); `ModelCall.field`/`answer_key:393`/`label:403`; `evidence_excerpts:628` and `check_evidence_bound:671` extracted from `prepare_call`; `SkippedSite.field:822` and `SiteJudgement.field:801` |
| `tests/remediation/test_phase3_discover.py` | **new** — 29 tests |
| `tests/remediation/test_phase3_fetch.py` | one test's example field `period_start` → `scope_status` (it asserted that an unroutable field raises, and `period_start` is routable now; `census/tests/t11_scope_window.py:146`) |

Nothing outside `scripts/remediation/phase3/` and `tests/remediation/` was touched. No `AUDIT_LOG.md`,
no existing `LEDGER.jsonl` row, no database, no git.

## 3. Deliverable 1 — the snapshot plan, byte-identical, and the old plan unmoved

```
$ ./.venv/Scripts/python.exe scripts/remediation/phase3/run.py plan --from-snapshot \
    --site-ids output/remediation/gold_standard/truth_sites.txt \
    --out output/remediation/logs/piece5/truth_plan.jsonl
{ "batches": 2, "batch_size": 15, "calls": 85, "fields": ["description","period_start",
  "site_type","country","card_description"], "pass": "discover", "sites": 17,
  "sha256": "ad32d26fccb3913b2656d70df5485f9185bbe956a343f4476668e6e00dcbb9c0" }

$ ./.venv/Scripts/python.exe scripts/remediation/phase3/run.py plan --from-snapshot \
    --out output/remediation/logs/piece5/snapshot_plan.jsonl
{ "batches": 334, "calls": 25020, "pass": "discover", "sites": 5004,
  "sha256": "a5786f102c8352bbfe94eb9ecfd9dc7d0b8b15625f4ac94b6753a245572716bb" }
```

Real byte counts and hashes (second run into `logs/piece5/again/`, same digests):

| artefact | bytes | sha256 |
|---|---|---|
| truth plan (17 sites) | 40,096 | `ad32d26fccb3913b2656d70df5485f9185bbe956a343f4476668e6e00dcbb9c0` |
| snapshot plan (5,004 sites) | 12,042,556 | `a5786f102c8352bbfe94eb9ecfd9dc7d0b8b15625f4ac94b6753a245572716bb` |
| worklist plan (re-generated from the same code) | 1,533,078 | `96704b808ae1b29d694806934569bd0265aa369d0b0532a6e6a8f35e4f6c8001` |

**The worklist plan is unmoved, proven on the real artefact and on a fresh run:**

```
$ sha256sum output/remediation/phase3_runner/PLAN.jsonl
96704b808ae1b29d694806934569bd0265aa369d0b0532a6e6a8f35e4f6c8001 *output/remediation/phase3_runner/PLAN.jsonl
$ sha256sum output/remediation/logs/piece5/worklist_plan.jsonl
96704b808ae1b29d694806934569bd0265aa369d0b0532a6e6a8f35e4f6c8001 *output/remediation/logs/piece5/worklist_plan.jsonl
```

That is `PIECE1.md:120-124`'s anchor (`96704b80…`, 1,533,078 bytes, 121 lines).
`test_the_worklist_plan_still_hashes_to_the_piece_1_anchor` pins it, and its mutation (making the
plan write a `pass` marker) is caught.

Determinism, as piece 1 defines it: snapshot **file order** is the plan's order; the id list
*selects*, it does not order (`test_the_order_of_the_site_id_list_cannot_change_the_plan`); keys
sorted, LF, `ensure_ascii=False`, no timestamp; a blank, repeated or unknown id, a duplicate snapshot
row and a row without a name are **refused**, never skipped — a plan that silently drops a site it
was asked for audits fewer sites than its own count says.

## 4. Deliverable 2 — one call per (site, field), one question per call

Per brief §8: 85 calls for the 17 sites (`batch-0001` 75 = 15 sites × 5 fields, `batch-0002` 10),
25,020 for the snapshot. The question is per field (`DISCOVER_FIELDS` order frozen:
description, period_start, site_type, country, card_description), each call carries its field in the
label (`<site_id>/<field>`) and in the answer file, and `ModelCall.answer_key:393` is what keeps five
answers per site from overwriting each other — the mutation that makes it the stage instead loses
four of five files (`test_judge_live_stores_one_answer_per_field_and_one_ledger_line_each`).

Observable in the preview (real output of a dry run, no process started):

```
$ ... judge --run-dir .../runs --batch-id batch-0001 --stage finder     # no --live
{ "calls": 75, "fields": [...5...], "pass": "discover", "skipped": [],
  "sites": [ { "field": "description", "label": "<site>/description", "prompt_chars": 2168, ... }, ... ] }
```

prompt sizes for batch-0001: min 2,168 / median 2,667 / max 3,325 chars (batch-0002: 2,620 / 2,686 /
3,166). Those are the **fixed** part only — the dry run has no fetched page on disk, so the evidence
block shows `[absent: …]` placeholders. What the fetch adds is bounded by
`MAX_EVIDENCE_CHARS = 32_000` (`model_stage.py:148`) per call, so the worst case is arithmetic, not a
guess.

### Wrong vs missing — the case a value question tends to lose

Three of the 24 truth entries are **missing values, not wrong ones** (brief §8), and across the
snapshot **22 of the 25,020 (site, field) pairs hold nothing** (measured on the delivered plan:
`card_description` 7, `period_start` 15; 24,998 hold a value). Two structural things answer them:

* `site_field_block:173` marks the value `stored="absent"` / `stored="present"` (a stored `0` is
  *present* — pinned by a test);
* the question's `WRONG` branch says it covers "the evidence contradicts the stored value, **or** the
  field stores no value at all where one belongs", and its closing paragraph says a field whose
  `stored` attribute is `absent` "holds nothing: no text, no number, not the string `"null"`".

Verdict vocabulary is unchanged (`CORRECT` / `WRONG` / `UNVERIFIABLE`); the record keeps the absent
fact structurally, so a model that answered "nothing to report" for an empty field contradicts the
prompt rather than the parser.

## 5. Deliverable 3 — routing, and one deviation from the brief that needs your call

Routing is enwiki **by the site's name** and Wikidata **by the site's `wikidata_qid`**
(`fetch_stage.targets_for_site`), the URL is
`…/w/api.php?action=wbgetentities&ids=<qid>&props=claims|labels|descriptions&languages=en&format=json`
(`wikidata_entity_url:458`, the project's own pattern in `scripts/audit_wikidata_batch.py:56`, same
host as the existing `wikidata_search`). A non-`Q<n>` id raises instead of building an `ids=` value
that answers `{"entities":{}}` — an empty set would read as "the item says nothing", i.e. evidence
against the stored value that nobody fetched.

**Deviation (measured, please confirm):** the qid is read from `site_external_ids`
(`kind='wikidata_qid'`, 4,618 of 9,237 rows), **not** from `card_stats.wikidata_qid` as the brief's
§3 sentence has it. `card_stats.wikidata_qid` is **NULL in all 5,004 exported rows**
(`test_the_snapshot_qid_comes_from_site_external_ids_not_from_the_vestigial_column` asserts exactly
that), the column is only ever created by `api/main.py:126` (`ADD COLUMN IF NOT EXISTS`) and nothing in
the repository writes it; the only writer of a Q-id is
`pipeline/lyra/prospector/external_ids.py:55`, into `site_external_ids`
(`pipeline/database.py:1577-1605`). `recon/reusable-tooling.md:292` names the same 4,618 QIDs in that
same file. **Reading the column the brief names would route no site to Wikidata at all**, so this is a
deviation in the letter of §3 and not in its purpose. It is a small change to
`snapshot_plan.qids_by_site:162` if you want the brief's table instead.

`card_description` and `wikidata_qid` both live in another table — the mistake the fixture's
`stored_in` key was added to prevent. `FIELD_STORED_IN:82` names one table per field and
`test_every_planned_value_comes_from_the_table_truth_fields_json_names` cross-checks all 21 entries
that name a table against their planned value; the 5 `card_stats` entries are exactly the 5
`card_description` ones.

## 6. Deliverable 4 — nothing about one record may end a batch

* **Oversized site → that site's own outcome.** `plan_site:238` reads the evidence once, checks the
  bound once, and turns `EvidenceOverBound` into **five** `unverifiable` skips with the arithmetic in
  the reason (`the evidence is 32010 characters, over the 32000-character bound … the batch carries
  on`); the batch's other sites are still judged (test with a 32,010-byte page next to a small one).
  The check is a plan-time decision, so the preview shows the same outcome as the live run.
* **Field whose evidence could not be fetched → recorded, not attempted.** With a recorded fetch
  failure and no usable page, no call is bought and the five fields are recorded with the failure
  quoted (`judge_discover_batch:385`). With **partial** evidence the call *is* bought and the prompt
  carries `<evidence … status="failed">` plus the failure text — "asked and failed" is never blurred
  into "nothing there".
* **Unchanged from piece 4:** a missing evidence file with **no** recorded failure still raises
  (`evidence_excerpts`, `test_a_missing_evidence_file_with_no_recorded_failure_still_raises`), and a
  call that cannot be measured still exits 2 with the calls that happened in the ledger.
* Overpass never enters this pass (text fields only), so the §8 constraint does not bite: the full
  snapshot's 9,622 targets are `enwiki` 5,004 + `wikidata_entity` 4,618.

## 7. Deliverable 5 — no writes, no network in tests

No DB write, no schema change, no `apply_remediation_change` call. All five fields are *judged* here;
writing is later pieces' business (`card_description` and `description` are report-only in
`model.REPORT_ONLY_FIELDS` anyway, so their findings cannot carry a write). Every network path sits
behind the existing `--live` switch and behind `fetch_stage`'s injectable fetcher; the discover
modules themselves import no client (`test_the_discover_modules_reach_no_network_client_and_no_shell`)
and the dry-run tests fail the test if a process is started at all.

## 8. Validation

```
$ ./.venv/Scripts/python.exe -m pytest tests/remediation/ -q -rs
639 passed in 96.42s
$ ./.venv/Scripts/python.exe -m pytest tests/remediation/test_phase3_discover.py -q
29 passed in 5.77s
$ ./.venv/Scripts/python.exe -m ruff check scripts/remediation/phase3/ tests/remediation/
All checks passed!
$ ./.venv/Scripts/python.exe -m mypy scripts/remediation/phase3/
Success: no issues found in 8 source files
```

(610 of those tests existed before this piece; the 29 new ones are `test_phase3_discover.py`. No
`ruff format` was run on any file this piece did not otherwise change — the 14 deliberately
unformatted files under `tests/remediation/` stay as they are; `snapshot_plan.py`,
`discover_stage.py` and the new test file are format-clean.)

### Mutation proofs — 16/16 caught

Each row: back the file up, break exactly that guard, run the one test that must catch it, restore,
and compare the sha256 (the script aborts if a restore is not byte-identical and if a test node was
not collected). The table is the script's own output; `output/remediation/logs/piece5/mutations.py`
reproduces it.

| # | mutation | caught by (failing assertion) |
|---|---|---|
| 1 | field order reversed | `assert [item.call.label …] == […]` |
| 2 | `FIELD_STORED_IN["card_description"] = "unified_sites"` | `assert SP.FIELD_STORED_IN[field] == stored_in` |
| 3 | `country` dropped from `DISCOVER_FIELDS` | `assert [item.call.label …] == […]` |
| 4 | over-bound no longer becomes the site's outcome | `E EvidenceOverBound: … 32010 characters, over the 32000-character bound` |
| 5 | `answer_key` = stage instead of field | `assert [j["label"] …] == […]` |
| 6 | question no longer asks about a missing value | `assert "or is it missing where a value belongs" in empty` |
| 7 | every value marked `present` | `assert 'stored="absent"' in empty` |
| 8 | no-qid skip in `targets_for_site` removed | `E InputError: site-2: finding carries no 'wikidata_qid'` |
| 9 | duplicate snapshot ids accepted | `Failed: DID NOT RAISE InputError` |
| 10 | site with no readable evidence judged anyway | `assert [call.site_id …] == ["site-2"]*5` |
| 11 | `--site-ids` accepted without `--from-snapshot` | `Failed: DID NOT RAISE InputError` |
| 12 | `--stage reviewer` accepted for a discover batch | `Failed: DID NOT RAISE InputError` |
| 13 | discover batch judged with the finding-driven path | `E InputError: the batch carries pass='discover' …` |
| 14 | unknown `pass` marker judged as the default | `Failed: DID NOT RAISE InputError` |
| 15 | worklist plan grows a `pass` marker | `assert sha256(bytes) == PIECE1_PLAN_SHA256` |
| 16 | snapshot plan drops its `pass` marker | `assert {b["pass"] …} == {"discover"}` |

Restored sha256 (prefixes from the run, equal to the files' current digests):
`discover_stage.py 61df86a530db4ad0` · `snapshot_plan.py 9257da451c6ada58` ·
`model_stage.py 2810315bc048a1ef` · `fetch_stage.py 880e49d57eb13855` · `run.py 4c15fe8a2616eb02`.

Two guards were **found by the tests rather than written into them**: (a) a snapshot row without an
`id` raised a bare `KeyError` from `build_discover_sites` before `discover_site_record` could report
it (now `InputError: a unified_sites.jsonl row carries no 'id'`, single check, `build_discover_sites`);
(b) the count of truth sites with a qid is 16, not 17 — see §10.

## 9. What the dry run buys — the numbers to spend against

| | 17 truth sites | all 5,004 sites |
|---|---|---|
| (site, field) model calls | **85** | **25,020** |
| calls at the brief's $0.000486/call | ≈ **$0.041** | ≈ **$12.16** |
| … of which fixed per-call overhead (437 tok ≈ $0.000066) | ≈ $0.0056 | ≈ $1.65 |
| evidence pages to fetch (keyed by (site, feature), written once) | **33** | **9,622** (enwiki 5,004 + Wikidata 4,618) |
| plan size on disk | 40,096 B | 12,042,556 B |

The fetch is identical under either call shape (the store is keyed by (site, feature)), so the
difference between one call per site and one per (site, field) is the per-call overhead only —
which is what §8 computed, and what these call counts now let you look up directly. The paid
experiment's subject is the 17-site list (85 calls ≈ $0.04 at provider-reported prices plus the
fetch), and its ceiling is the 12 MB full-snapshot plan above: nothing is hidden behind a re-plan.
Also measured on the delivered plan: 22 of the 25,020 pairs store nothing (7 `card_description`,
15 `period_start`), i.e. the missing-value branch is not a theoretical case.

## 10. Open questions and known caps (not silently absorbed)

1. **qid source (§5).** Read from `site_external_ids` because `card_stats.wikidata_qid` is NULL
   everywhere and written by nothing. Overrule me if the brief's §3 table was itself the decision.
2. **Recall is capped at 21/24 by construction.** The truth fixture's 3 remaining entries are `scope`
   decisions (`stored_in: null`, `stored_value: null`, correct value = "out of scope — the record
   should be hidden or removed"). No column holds that, so no per-field value question can produce
   it. Reaching them needs a **6th** `P3/scope` question on the record's *scope status*
   (`census/tests/t11_scope_window.py:146` calls the field `scope_status`), which adds 20 % to the
   call count (25,020 → 30,024). Not decided here, not escalated as a blocker — the cap is pinned by
   `test_the_three_truth_entries_a_value_question_cannot_reach_are_scope_entries`.
3. **`country` has no gold answer** (`truth_fields.json.fields_to_catch` = card_description,
   description, period_start, scope, site_type — no country), so the 5,004 country calls of the full
   plan are spend without a truth-set recall measurement behind them.
4. **One truth site has no qid** (`Font dels Coms`, `58a2be59-…`): no `site_external_ids` row at all,
   so it is judged on its article alone (found by name). 16 of 17 carry a qid; the other 386 of 5,004
   sites are in the same position.
5. **Severity is a placeholder.** `DISCOVER_SEVERITY = "moderate"` (`snapshot_plan.py:99`) with a
   stated reason (the census's own words for a visibly wrong indexed field). The real severity, if it
   is to differ, belongs to the piece that writes findings from answers.
6. **Unproven here, on purpose:** anything about what the model *answers* — the recall experiment is
   yours, and no `--live` call or fetch was made. The prompt's effect on recall is the one thing this
   report cannot measure.
