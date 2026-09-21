# Piece 6 — the writer: one row per statement, and the digest that ties a statement to its plan

**Status:** implemented, gates green, **22 new mutations all caught (106/106 in the sweep)**, dry runs run
and measured. **No database was contacted** — not the VPS, not a local one (there is none). The module's
one SQL seam was replaced by a fake in every test; the applier itself has never been executed anywhere.
**Branch:** `main`, nothing pushed. **Date:** 2026-09-21.
**Runner:** `./.venv/Scripts/python.exe` (never bare `python`), `PYTHONIOENCODING=utf-8`.

| part | file | state |
|---|---|---|
| the writer stage | `scripts/remediation/phase3/write_stage.py` (new) | written |
| the tests | `tests/remediation/test_phase3_write.py` (new) | `50 passed` |
| the mutations | `scripts/remediation/phase3/mutation_sweep.py` | +22 entries, `106/106 caught` |
| this report | `output/remediation/phase3_runner/PIECE6.md` | written |

## What it does

`input.json` (the batch's findings) + `review.json` (the reviewer's verdicts) + `answers/` (the finder's
texts) go in; a plan of **single-row updates** comes out, cut into chunks of `--chunk-size` (default
100) in the plan's own order, each chunk rendered to `chunks/<label>/APPLY.sql` and `ROLLBACK.sql` with a
`-- plan digest sha256:<hex>` header over the rows it was generated from. Without `--apply` nothing is
sent to a database: the plan files, the chunk statements and `REPORT.json` are the whole output.

With `--apply`, one chunk is: pre-flight read (which rows still hold the planned old value) → the APPLY
transaction → read-back (value and journal row count) → the ROLLBACK transaction → read-back again →
proof that not one journal row of the reversal's own stamp survived. The first disagreement stops the
run (`ReadBackFailed`, `InverseFailed`) instead of continuing into the next chunk.

## The fixed-point table, as the code has it

| column | producer on a container start | what the writer does |
|---|---|---|
| `unified_sites.site_type` | `pipeline.normalizers.site_type.normalize_site_type`, `orchestrator.py:1476-1488` | re-checks every proposed value with the producer's *own* function (`model.site_type_fixed_point`); a value the normaliser would rewrite is refused, naming it |
| `unified_sites.country` | `data_patches.py:48-61` (`fix_countries`) | **writable**: that `UPDATE` is guarded `source_id = 'lyra' AND country IS NULL`, so no `ancient_nerds` row is re-derived |
| `unified_sites.period_start` | `data_patches.py:64-78` (`backfill_periods`) | **writable**, same reading |
| `unified_sites.description` | none | **report-only**: text regeneration is Phase 5 |
| `card_stats.card_description` | `api/main.py:506` → `api/services/card_descriptions.py:35-48`, every API boot | **report-only**: a database-only write is reverted at the next start while the journal keeps claiming it |

The two `country`/`period_start` verdicts are the interesting ones, because they are *readings*, not
assumptions: `test_the_two_startup_patchers_really_guard_their_updates_on_the_lyra_source` opens
`pipeline/lyra/data_patches.py` and asserts both guard strings. If either guard goes, both columns
become write-and-revert and this table is wrong — so the guard is a test's subject rather than a
sentence in this report.

One thing the brief's landmine table names is **not** in the code, deliberately:
`unified_sites.name_normalized` (producer `orchestrator.py:1694-1702`, `left(lower(unaccent(value)), 500)`)
cannot reach the writer at all — `snapshot_plan.FIELD_STORED_IN` has no table for the column, so the plan
refuses it as `no-table-mapping` before any fixed-point question is asked. A refusal branch keyed on
`unaccent` was written first and then **removed**: no test could have reached it, and a guard no test can
catch is not a guard. If that mapping ever grows the column, the fixed-point table has to grow with it.

## The refusals, by rule

A field is refused, never silently dropped, and every refusal carries a rule slug (the report counts by
slug, not by prose): `reviewer-did-not-clear`, `no-reviewer-verdict`, `finder-answer-missing`,
`finder-proposed-nothing`, `finder-answer-has-problems`, `report-only-field`, `not-a-fixed-point`,
`no-table-mapping`, `not-writable-in-the-columns-shape`, `not-a-change`, `foreign-test-id`, `matched-0`.

Two of them are worth naming here because they are the whole point of the piece:

* **`reviewer-did-not-clear`.** The writer does not read `review.json`'s own `applies` boolean. It
  rebuilds `ReviewVerdict` from the raw dict and consults `review_stage.ReviewVerdict.applies`, i.e.
  `asked and refuted is False and not problems`. The file's boolean is a *copy* of that rule, and a copy
  can disagree with its source. `test_a_verdict_whose_parts_refute_it_is_not_cleared_by_its_own_applies_flag`
  feeds a verdict whose parts refute it while the file says `applies: true`; mutation
  *"the review file's own applies boolean is trusted"* makes that flag win, and the test fails on
  `assert plan.rows == []`.
* **`report-only-field`.** Both report-only fields are refused *even though the reviewer cleared them*,
  with their own reasons kept apart: `description` names the Phase-5 split, `card_description` names
  `api/main.py:506`. Merging them into one "not supported" text would hide which one is a boot overwriter.

## The transaction, and its four guards

`APPLY.sql` is one transaction: `\set ON_ERROR_STOP on`, `BEGIN;`, a temp plan table `ON COMMIT DROP`
holding the rendered rows, then

1. every planned row is an existing `source_id = 'ancient_nerds'` site (`u.id IS NULL OR
   u.source_id <> 'ancient_nerds'`);
2. every planned row is a real, writable change — the column allowlist rendered from
   `WRITABLE_COLUMNS`, the primary key of its own table, no empty value, `IS NOT DISTINCT FROM` for the
   equality;
3. every planned row **still holds** the old value the plan names (`IS DISTINCT FROM`, which is true for
   a NULL old value where `=` would be NULL — the primitive's own conditional `WHERE` is
   `IS NOT DISTINCT FROM $3::<column type>`, `0018`);
4. after the loop: every row holds the new value, `moved = expected`, and the journal and the plan agree
   **row for row in both directions** — a planned row with no journal row, a journal row whose values
   differ, and a journal row of this run stamp that the plan does not account for.

Then the loop calls `apply_remediation_change` with exactly the 12 arguments of
`migrations/0018_remediation_change_log_boolean.sql`, in that order, one row at a time, and `COMMIT;`
follows. The reversal is the same statement with the values swapped, its own `run_stamp`
(`<stamp>-rollback`) and its own `change_key` (`<key>-rollback`), ending in `ROLLBACK;` — a reversal that
is *kept* would be a second write, so the run ends by proving the reversal left no journal row of its own
stamp behind.

`ROLLBACK.sql` is written **before** `APPLY.sql`: a chunk that cannot be undone is visible before
anything is written (the mechanical lane's `apply.emit` rule).

## The digest pin, and what it does not cover

`assert_pinned(sql, rows, what=...)` refuses a statement whose `-- plan digest sha256:` header is not
`plan_digest(rows)` for the rows it is being run for. The case it exists for: a `chunks/` directory
survives a re-render, or the plan grew a row between render and apply, and the file then names an older,
smaller plan. That is the defect the mechanical lane's `--apply` has (`[H] SECURITY 3 / BACKEND B7`).

Honest about the limit: the pin binds a statement to **the rows the plan names**, not to the file's
bytes. A hand-edited value in `APPLY.sql` leaves the digest unchanged. What catches that is guard 3 and
the read-back, which look at the data rather than at the file — the pin and the guards are two different
nets, and the report does not claim the pin covers the second one.

## The tests, and the three defects they caught while being written

50 tests, one per guard, driven by a batch directory in `tmp_path` and a fake psql that answers this
stage's three reads and applies a transaction's `INSERT` rows unless it ends in `ROLLBACK;`. The fake
does **not** re-implement the `DO` block's guards — a fake that simulated the guards would only test
itself, so the guards are asserted on the rendered text instead.

Three real defects of mine, found by running the tests rather than by reading them:

* `read_back` compared `row.change_key + ("" if chunk.rows[0] else "")` — a leftover of a draft, which
  silently reads as "the key, unchanged". Rewritten to the value it meant.
* `_shape_refusal` indexed `COLUMN_SHAPE[field_name]` after a membership test on a *different* mapping,
  so an unmapped column raised `KeyError` instead of a refusal. Every path that refuses now refuses with
  a reason, and `test_a_period_start_that_is_not_a_year_is_refused_before_the_transaction` is the one
  that fails when the shape check is dropped.
* the `same_value` comparison: the reads come back as JSON, so `period_start` arrives as a number while
  the plan carries the string `"1500"`. A plain `!=` would have reported every integer column as a
  mismatch. One type-aware comparison is used by the pre-flight and the read-back alike, so the two
  cannot drift.

## The mutation evidence: 22 new, 106 of 106 caught

`anchor_check.py` first: `Mutationen: 106 | Probleme: 0` (every anchor occurs exactly once, every named
test exists, no no-op mutation, no constant assigned twice). Then the sweep:

```
106/106 mutations caught; missed: []
the tree is byte-identical to the sweep's start for 10 file(s)
```

| mutation | catching test | what failed |
|---|---|---|
| the site_type fixed point is never checked | `…normaliser_would_rewrite_is_refused` | `assert plan.rows == []` |
| the report-only fields are written like any other | `…report_only_fields_are_refused_though…` | the refusal list is empty |
| the width of the varchar column is not checked | `…country_longer_than_the_column…` | `assert plan.rows == []` |
| a value the row already holds is planned as a change | `…row_already_holds_is_not_a_change` | `WriteRefused: 1111…: old and new are both 'Georgia'` |
| the pre-flight stops comparing the stored value | `…moved_since_the_snapshot…` | `outcome.written == 0 and preflight_held == 0` |
| the digest pin accepts any digest of the right shape | `…generated_from_other_rows` | `DID NOT RAISE WriteRefused` |
| the read-back ignores what the database kept | `…kept_differently_is_a_stop` | `DID NOT RAISE ReadBackFailed` |
| the reversal is not checked for having been rolled back | `…reversal_that_is_kept_is_a_stop` | the message no longer says the write was left as it was |
| the reversal reuses the write's own change key | `…values_swapped_and_its_own_change_key` | `insert[0]["key"] == …+ "-rollback"` |
| the reversal commits instead of rolling back | `…ends_in_commit_and_the_reversal_in_rollback` | `"\nROLLBACK;\n" in rollback_sql` |
| the chunk step is one row too long | `…chunks_cut_the_plan_in_its_own_order…` | `[3, 2] != [2, 2, 1]` |
| the statements no longer stop on the first database error | `…both_statements_set_on_error_stop` | `"\set ON_ERROR_STOP on" in apply_sql` |
| the loop passes the new value as the old one | `…twelve_arguments_in_order` | the argument list |
| the write guard no longer checks the source | `…write_inside_the_curated_source` | `u.source_id <> 'ancient_nerds'` missing |
| the period_start comparison loses its integer cast | `…every_writable_column_has_a_comparison…` | `p.old_value::integer` missing |
| the column allowlist is cut down to one column | `…write_guard_refuses_a_value_that_is_not_a_change` | `NOT IN ('country', 'period_start', 'site_type')` |
| the journal invariant only looks one way | `…journal_invariant_covers_both_directions` | the `NOT EXISTS (…)` clause missing |
| the review file's own applies boolean is trusted | `…not_cleared_by_its_own_applies_flag` | `assert plan.rows == []` |
| a review may be joined to any batch's input | `…review_that_names_another_batch` | `DID NOT RAISE InputError` |
| the discover pass marker is not checked | `…batch_that_is_not_the_discover_pass` | `DID NOT RAISE InputError` |
| the read statement takes any column name | `…names_the_row_its_column…` | `DID NOT RAISE WriteRefused` |

## The real dry runs: the yield on today's data is zero, and that is the honest number

Two batch directories of the gold6 run carry a `review.json` and were planned read-only
(`--batch-dir …/runs/gold6/batch-000X --out <temp>`, no database involved):

| batch | verdicts | the reviewer cleared | refused report-only | refused not-cleared | rows planned | chunks |
|---|---|---|---|---|---|---|
| batch-0001 | 75 | 7 | 7 | 68 | **0** | 0 |
| batch-0002 | 10 | 0 | 0 | 10 | **0** | 0 |

All 7 cleared verdicts are report-only fields — 2 `description`, 5 `card_description`, over 6 sites
(`9ed175c7`, `b6af84c5`, `590d3dff`, `9dcc1c87`, `a5d9e9a7`, `e7ee7c00`) — so the writer plans nothing and
says so: `refused_by_rule: {"report-only-field": 7, "reviewer-did-not-clear": 68}`, `rows_planned: 0`,
`journal_rows_added: null` (a dry run has no journal). The first real use of the writer therefore
produces an empty plan from this data, which is the correct result and not a defect: the discover pass's
7 corrections are exactly the two fields Phase 6/5 own. A writable row needs a `country`, `period_start`
or `site_type` the reviewer clears, and the gold6 verdicts contain none.

## Gates, measured on the bytes this commit contains

* `ruff check` + `ruff format --check` clean; `mypy scripts/remediation/phase3/write_stage.py` →
  `Success: no issues found in 1 source file` (CI type-checks `api/` only; this file was checked locally
  as well).
* `pytest tests/remediation/test_phase3_write.py -q` → **50 passed**.
* `anchor_check.py` → `Mutationen: 106 | Probleme: 0`; sweep → `106/106 mutations caught; missed: []`,
  tree byte-identical for the 10 files it touched.
* `pytest -q -rs --timeout 90 -m "not integration and not live_llm"` → **2448 passed, 3 skipped,
  57 deselected, 32 warnings in 145.97s** — 2398 + the 50 tests this piece adds, exactly. The 3 skips are
  the three pre-existing ones (`-rs` names them).
* Another lane was writing into the tree while the suite ran (`LEDGER.jsonl` grew by 10,543 lines from a
  live mass run, `tests/remediation/test_t10.py` changed). Neither file is part of this commit; the
  files this commit contains are the four listed at the top and nothing else.

## Not proven, and named so it is not mistaken for done

* **The applier has never run.** There is no local database (decision 2026-09-21), and this piece did not
  touch the VPS. Everything that touches SQL is either rendered text with an assertion on it, or a call
  through the injectable seam that the tests replace. So: the `DO` block's PL/pgSQL, the 12-argument call
  into `apply_remediation_change`, the read-back's JSON parsing against real `to_jsonb` output, and the
  journal invariants are **unverified against Postgres**. The mechanical lane's 35-row write is the only
  precedent that this primitive works.
* Consequence for a real apply: the first `--apply` should be one chunk against a database whose rows
  have just been snapshotted, with a human reading `REPORT.json` before the next chunk.
* The **fixed point** of `country` and `period_start` rests on reading two `WHERE` clauses, not on running
  `run_data_patches` — a correct reading of the code, but a reading.
* The writer's **yield on real data is zero rows** (above). Whether the reviewer's `applies` set ever
  contains a writable field is a question about the reviewer's sensitivity, not about this stage.
* **Own deviation, recorded:** the standing rule is that `mutation_sweep.py` runs from a parent process,
  never inside a subagent lane, because a lane killed between applying a mutation and restoring it leaves
  the mutant in the tree (the piece-5 `snapshot_plan.py` incident). This sweep ran **inside this lane**.
  It completed, all 106 mutations were restored, and the per-file sha256 and the final tree check both
  say byte-identical — but the hazard was real for the duration of the run, and a re-run from the parent
  process is the safer way to reproduce this evidence.
