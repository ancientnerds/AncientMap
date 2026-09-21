# Phase-3 runner, PIECE 1 — schema, ledger, offline CLI

Written 2026-09-21 by the `worker` lane. Scope of this piece: the finding schema, the measured
cost and time ledger, and an offline CLI skeleton. **No model call and no network fetch was made
in this piece** — that is piece 2.

## 1. What was built, and why it is shaped that way

| File | What it is |
|---|---|
| `scripts/remediation/phase3/__init__.py` | package docstring: what piece 1 covers, what piece 2 adds |
| `scripts/remediation/phase3/model.py` | `Verdict`, `Finding`, `StageResult` (+ the census enums, imported) |
| `scripts/remediation/phase3/ledger.py` | `Entry`, `Ledger`, `summarise`, `StageTotals`, `LedgerSummary` |
| `scripts/remediation/phase3/run.py` | `plan` / `prepare` / `status`, offline and deterministic |
| `tests/remediation/test_phase3_runner.py` | 28 tests, all shown able to fail (§4) |

### The three verdict kinds, and why `defect` is derived

`Verdict` has exactly the three values the plan needs and the repo has no producer for:
`defect`, `true_but_no_correction`, `unverifiable`. `output/remediation/AUDIT_LOG.md` names the
gap ("Decisions 2 and 11 introduce a required `defect` flag and a `true_but_no_correction`
verdict. Neither has a producer ... whoever builds the Phase-3 runner must emit both, or the two
decisions are decoration"). `Finding.defect` is therefore a **property derived from the verdict**,
not a second stored field: the flag both briefs require is emitted into the JSONL, and flag and
verdict cannot disagree — a `defect: false` next to a wrong value is unrepresentable.

The vocabulary is not re-declared: `Severity`, `Confidence`, `Proposal` and `Evidence` are
imported from `scripts/remediation/census/model.py`, because the finder brief says "same schema as
the census" and a second spelling of the same words would let the two drift.

### The rules the schema refuses (fail-closed)

* a `Verdict.TRUE_BUT_NO_CORRECTION` or `Verdict.UNVERIFIABLE` cannot carry `proposal=set|clear`
  or a `proposed_value` — "no write" is enforced, not documented;
* `Verdict.DEFECT` cannot be recorded as `proposal=none` ("nothing to see");
* `description` and `card_description` are **report-only** on two different grounds, both of which
  the module docstring names with file:line: `card_description` is re-derived on every API boot
  (`api/main.py:506` → `api/services/card_descriptions.py:35-48`), `unified_sites.description` has
  no boot overwriter at all and is report-only because of the Phase-5 split;
* a `site_type` write must be a fixed point of its own boot producer: the check calls
  `pipeline.normalizers.site_type.normalize_site_type` — the same function
  `pipeline/lyra/orchestrator.py:1476-1488` uses — so a value that would be rewritten on the next
  start is not accepted as a correction;
* a proposed write needs evidence and a confidence above `unverifiable`;
* an unknown verdict/severity/proposal string raises instead of passing through;
* a `StageResult` refuses findings for sites outside its batch, needs a non-empty unique site list
  for its stage, and a crash is a recorded `status=error` **with its error message** — a batch that
  errors can never be written as clean.

**Not checked at this layer, said out loud so it is not mistaken for covered:**
`name_normalized`'s fixed point needs Postgres `unaccent` (`FIELD_CONTRACT.md` §2.2) and is
unverified here. `unified_sites.country` turned out not to be re-derived for these rows at all —
`pipeline/lyra/data_patches.py:54-64` guards that UPDATE with `source_id = 'lyra' AND country IS
NULL`, while Phase 3 works on `source_id='ancient_nerds'`.

### The ledger: measured, append-only, crash-safe

One line per model call and per fetch; `Ledger.append` writes a single `\n`-terminated line in
append mode, then `flush()` + `os.fsync()`, so a crash loses at most the call in flight and never
leaves a half line (a half line would make every later `summarise()` a guess). Token counts are
**recorded per call and never estimated**: a model entry without `input_tokens`/`output_tokens`
raises, and a fetch without the status actually observed raises ("a network failure raises in the
fetcher and is never written as an empty result"). `summarise()` totals per stage — calls,
fetches, input/output/cache tokens, fetched bytes, first and last timestamp.

**USD is deliberately not computed here.** A price table is an assumption (the plan's own prices
are dated 2026-09-19 assumptions), and a dollar figure derived from an assumed price is exactly the
invention this runner must not contain. The ledger produces the measured token counts the plan's
two disagreeing anchors (~40,000 vs ~20,295 tokens/site, `BATCH_PLAN.md`) need replaced; the money
is applied to those numbers outside this file.

### The CLI: `plan` is deterministic by construction

`plan` selects `phase3=true` records from `WORKLIST.jsonl` **in file order** (the worklist is
already sorted worst-first) and chunks them into batches of K (default 15, brief decision 12).
Batch ids come from the ordinal (`batch-0001`), every JSON object is written with `sort_keys=True`,
the newline is pinned to LF and the file is written with `encoding="utf-8", newline="\n"`. **No
timestamp is written anywhere**, so the artefact cannot depend on when it was produced.
`prepare` writes one `input.json` per batch under the run directory; `status` reports what is
actually on disk plus the ledger summary. A worklist record without a `phase3` flag or without a
`site_id` raises — a silently smaller plan is the failure this phase is paid to prevent.

## 2. Gates — exact commands, real output

```
$ ./.venv/Scripts/python.exe -m pytest tests/remediation/test_phase3_runner.py -q -rs
tests\remediation\test_phase3_runner.py ............................     [100%]
============================= 28 passed in 0.48s ==============================

$ ./.venv/Scripts/python.exe -m ruff check scripts/remediation/phase3/
All checks passed!                              (exit=0)

$ ./.venv/Scripts/python.exe -m ruff format --check scripts/remediation/phase3/
4 files already formatted                       (exit=0)

$ ./.venv/Scripts/python.exe -m mypy scripts/remediation/phase3/
Success: no issues found in 4 source files      (exit=0)
```

`mypy` is not a local gate of this project; reported because the task asked for it. It first
reported `scripts\remediation\phase3\model.py:113:32: error: "str" not callable [operator]` — the
`field: str` attribute of `Finding` shadowing the `dataclasses.field` import inside the class body.
Fixed by `import dataclasses` + `dataclasses.field(...)`. `ruff check` first reported `C416` and one
unformatted file; both fixed before the run quoted above.

## 3. Deterministic-output proof for `plan` (both hashes)

```
$ ./.venv/Scripts/python.exe scripts/remediation/phase3/run.py plan --out output/remediation/phase3_runner/PLAN.jsonl
{
 "batch_size": 15,
 "batches": 121,
 "out": "output/remediation/phase3_runner/PLAN.jsonl",
 "sites": 1813,
 "worklist": "C:\\PythonProjects\\AncientMap\\output\\remediation\\phase3_worklist\\WORKLIST.jsonl"
}
$ ./.venv/Scripts/python.exe scripts/remediation/phase3/run.py plan --out /tmp/plan_repeat.jsonl

$ sha256sum output/remediation/phase3_runner/PLAN.jsonl /tmp/plan_repeat.jsonl
96704b808ae1b29d694806934569bd0265aa369d0b0532a6e6a8f35e4f6c8001 *output/remediation/phase3_runner/PLAN.jsonl
96704b808ae1b29d694806934569bd0265aa369d0b0532a6e6a8f35e4f6c8001 */tmp/plan_repeat.jsonl
```

Both files: **96704b808ae1b29d694806934569bd0265aa369d0b0532a6e6a8f35e4f6c8001** (1,533,078 bytes,
121 lines, LF only). The same run is asserted in
`test_plan_of_the_real_worklist_is_byte_identical_across_runs`, together with the absence of any
`at|ts|timestamp|generated_at|date` key. The batch arithmetic on the real worklist is asserted in
`test_plan_has_the_ratified_batch_arithmetic`: 1,813 sites → 121 batches, first two 15 each, last
13, first batch = the first 15 `phase3` records **in file order**.

## 4. Mutation evidence — every test shown able to fail

Method per mutation: back up the file, break exactly the guard, run the named test, observe the
failure, restore the file from the backup, print the sha256 to prove the restore. Hashes before and
after the whole sweep are identical (below), so the shipped files are the files that passed the
gates.

| # | Mutation | Test that went red (real output) |
|---|---|---|
| M1 | `Batch.to_json` wrote a `"generated_at"` key | `1 failed, 27 deselected` — the determinism/timestamp test |
| M2 | the two `_NO_WRITE_VERDICTS` guards disabled in `model.py` | `3 failed, 25 deselected` (incl. `Failed: DID NOT RAISE <class 'ValueError'>`) |
| M3 | `Ledger.append` opened with mode `"w"` instead of `"a"` | `2 failed, 26 deselected` — `At index 0 diff: 'reviewer' != 'finder'` (the second append overwrote the first) |
| M4 | the `size < 1` guard in `assign_batches` disabled | `1 failed, 27 deselected` — `ValueError: range() arg 3 must not be zero` instead of `InputError` |
| M5 | the foreign-site check in `StageResult` disabled | `1 failed, 27 deselected` — `Failed: DID NOT RAISE <class 'ValueError'>` |

Restore hashes printed after each mutation, and again at the end:

```
49111176fa9ad2bd553adaaf4f836a695a8dca43147ccfae44eca8ad52ad376e *scripts/remediation/phase3/__init__.py
d927f67cee6da9aae6b9aea433b44edc36747404bf05834d5aa6d331fd93f26c *scripts/remediation/phase3/ledger.py
004ee03535f7a13825a025bffdff6ec8d759c280f5951e100df36173c00742fd *scripts/remediation/phase3/model.py
0f136d94c2f636d3c1a4ec521c31277360cdd4ade0619d62d0693fefae00c70d *scripts/remediation/phase3/run.py
```

Full suite after the last restore: `28 passed in 0.52s`.

## 5. Unverified / not done in this piece

* **Unverified: no real model call and no real fetch has ever written a ledger line.** The ledger's
  shapes are exercised only with hand-built entries in tests. That is piece 2, and the plan's two
  cost anchors stay unreplaced until then.
* **Unverified: `name_normalized`'s boot fixed point** (needs Postgres `unaccent`, no local
  database in this project).
* **Unverified: the country write surface** is stated from a code read
  (`pipeline/lyra/data_patches.py:54-64` guards on `source_id='lyra' AND country IS NULL`); it was
  not executed against production.
* **Not implemented (piece 2):** fetch cap enforcement, the finder/reviewer stage drivers, result
  persistence (`result.json`), and the applier. `status` already looks for `result.json` but nothing
  writes it yet.
* **Not verified by this lane:** the 60 KB per-page fetch cap and the "named features instead of raw
  geometry" rule from decision 12 are not enforced by any code in this piece; `plan` writes no cap
  value, because 60 KB vs 61,440 bytes is a detail no source I read pins down.
* **`--batch-size` is a CLI parameter with the ratified default 15**; no `plan` run at another size
  was made, and no per-block ordering (the "severe first" blocks) was re-derived — `plan` relies on
  `WORKLIST.jsonl` already being in that order, as `BATCH_PLAN.md` states.
