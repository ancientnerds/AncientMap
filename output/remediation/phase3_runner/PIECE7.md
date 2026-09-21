# Piece 7 - the mass-run driver, and the host pacer under it

Piece 7 is the thing that turns a plan into findings: `scripts/remediation/phase3/mass_run.py` walks the
plan and drives every batch through `prepare`, `fetch` and `judge`. The host pacer in `fetch_stage.py`
is its prerequisite, because `--jobs 4` without it means four processes hitting one host at the same
instant, which is how a polite client becomes a blocked one.

Nothing in this piece touches the database. It produces findings; piece 6 is what turns confirmed
findings into guarded writes, and keeping the two apart is what makes findings safe to produce in bulk.

## Why a script, not a subagent lane

The 30-minute subagent ceiling binds *lanes*, not `bg_run` scripts. This session killed two lanes at that
ceiling whose workflow receipts then reported files they had not written - and one of them left a mutant
in the tree. A script that writes to files it owns cannot lose its evidence that way, and a batch that
was interrupted is simply not done.

## The pacer: what it is, and what it is not

`HostPacer` (file mutex in `--pacing-dir`, one lock file per host, stamped with its own acquisition
time, stale takeover after 30 s, fail-closed `PacerTimeout`) plus `PacedFetcher`, which decorates the
`Fetcher.get` seam so that probes, retries and targets are all paced alike.

* **It is** a cross-process handshake: two processes never start a request to the same host inside
  `HOST_MIN_INTERVAL_SECONDS` (0.2 s), and a lock left behind by a killed process is taken over rather
  than wedging the fleet.
* **It is not** a global rate limiter, and it is **not a distributed one**: the state is a file on one
  machine. Two runs on two machines are not coordinated. If the mass run ever moves to the VPS, that
  sentence stays true.

## The driver's guards

Every guard has a test, and every test has been proved able to fail by mutating the guard (43/43 in
`output/remediation/logs/phase3_mutations/sweep_after_massrun.txt`, of which 8 are new here).

| guard | what it protects against | test |
|---|---|---|
| `batch_state` returns `done` only when both artefacts parse **and** every recorded answer is on disk | a truncated `model.json` (a kill mid-write) reading as success | `test_a_truncated_model_json_is_broken_and_never_done`, `test_a_written_judgement_without_its_answer_file_is_broken`, `test_a_count_that_disagrees_with_the_judgements_is_broken` |
| the budget is read from the ledger before each batch is started | a run that spends past its ceiling because nobody looked | `test_the_call_ceiling_stops_between_batches_and_names_what_was_not_reached`, `test_the_dollar_ceiling_stops_the_run` |
| N consecutive failures stop the run | 300 batches burned against one broken assumption | `test_the_circuit_breaker_trips_after_the_configured_number_of_failures` |
| a success clears the failure count | a breaker that is really just a counter | `test_a_success_clears_the_failure_count` |
| the phase-3 sources are hashed at start and compared before every batch | two batches executing two versions of the code | `test_the_source_digest_guard_stops_a_run_whose_sources_changed` |
| the progress file is written to a temp file and swapped in | a reader seeing half a progress report | `test_a_crash_between_the_write_and_the_swap_leaves_the_previous_progress_intact` |
| the dry run writes no ledger line | a "harmless" dry run that quietly bought something | `test_a_dry_run_buys_nothing_and_leaves_the_ledger_exactly_as_it_was`, and the same with no ledger file at all |
| every stage exits non-zero => the batch is a failure, **and** every stage exiting 0 is not enough | `exit 0` being taken as a claim | `test_a_batch_that_ends_incomplete_is_a_failure_even_though_every_stage_exited_zero` |
| a stage that exceeds its wall clock is recorded, not fatal | one hung batch killing a 40-hour run | `test_a_stage_that_runs_too_long_is_recorded_as_a_failure_rather_than_killing_the_run` |

The budget is checked **between** batches, so with `--jobs N` up to `N` batches are already in flight
when the ceiling is reached. That is stated here rather than discovered later: the driver stops naming
what it did not reach, and the overshoot is bounded by the batch wave, not by the run.

## Resumption

`fetch` skips a target whose evidence file exists, and `judge` re-uses an answer it already has
(`wrote=False`). Both are deliberate: a re-run pays only for what is missing, which is what makes
"a half-written batch is redone rather than trusted" cheap enough to be the default. A batch that is
already `done` is skipped without a single call.

## Numbers

| | |
|---|---|
| plan over the whole table | `PLAN.snapshot.jsonl`: **334 batches, 5,004 sites**, sha256 `a5786f102c8352bbfe94eb9ecfd9dc7d0b8b15625f4ac94b6753a245572716bb`, 12,042,556 bytes (identical to the piece-5 figure) |
| plan over the worklist | `PLAN.jsonl`: 121 batches, 1,813 sites, sha256 `96704b808ae1b29d…` (unchanged by generating the other plan) |
| calls | 25,020 = 5,004 sites x 5 fields |
| money | **~$20.6** for the discover stage at the measured $0.000825 per call (round 6). A reviewer stage would roughly double it and is **not built** |
| wall clock | serial: ~76,000 fetches at 8.8 s plus ~25,000 calls at 2.6 s => **~200 h and up**. `--jobs 4` is a first measurement, not a promise: the pacer keeps two processes out of one host, but it does not make the host faster, and every batch wants the same hosts. The judge stage (a local process per call) should scale close to 4x; the fetch stage may scale well under it |

## The one thing to decide before starting it

**`overpass-api.de` is unreachable from this workstation** (all 117 fetch failures of the pilot were
that one host, and piece 4b now probes a host once per run instead of once per target). The VPS *can*
reach it. So a mass run started here collects no `overpass` evidence at all and the discover pass would
answer with strictly less evidence than it was measured with - the six recall rounds all ran with the
same 33 evidence files, fetched here, which is why they are comparable to each other. Either run the
mass run on the VPS, or accept the reduced evidence and say so in the findings. This is in
`HUMAN_ONLY.md` and it is Martin's call.

## Reproduction

```bash
# what would happen, buying nothing (no ledger line, no progress file)
./.venv/Scripts/python.exe scripts/remediation/phase3/mass_run.py \
    --plan output/remediation/phase3_runner/PLAN.snapshot.jsonl \
    --run-dir output/remediation/phase3_runner/runs/mass1 \
    --jobs 4

# for real, with ceilings and the digest guard on
./.venv/Scripts/python.exe scripts/remediation/phase3/mass_run.py --live --jobs 4 \
    --plan output/remediation/phase3_runner/PLAN.snapshot.jsonl \
    --run-dir output/remediation/phase3_runner/runs/mass1 \
    --max-calls 25020 --max-usd 25

# the tests, and the proof that each guard can fail
./.venv/Scripts/python.exe -m pytest tests/remediation/test_phase3_massrun.py -q
./.venv/Scripts/python.exe scripts/remediation/phase3/mutation_sweep.py
```

## Verified

* `tests/remediation/test_phase3_massrun.py`: **29 tests**, green.
* `tests/remediation/test_phase3_fetch.py`: **33 tests** (7 of them the pacer's), green.
* Mutation sweep: **43/43 caught, missed: []**; the eight new ones cover the ceiling, the breaker, the
  breaker reset, the torn artefact, the missing answer, the digest guard, the atomic swap and the
  projection. Restore proved byte-identical for all six files it touches
  (`mass_run.py` `ba511951644ce0b1`, `fetch_stage.py` `126396c218747869`, `discover_stage.py`
  `cd2a3edb3eb104d2`, `snapshot_plan.py` `983b5ea8e8c42798`, `model_stage.py` `2810315bc048a1ef`,
  `run.py` `1f51e01aa3f75d21`).
* Full DB-less gate before this piece: **2316 passed, 3 skipped, 57 deselected**; with this piece's
  tests: see the gate line in `AUDIT_LOG.md`.
* The plan over all 5,004 sites was regenerated and its sha256 equals the piece-5 figure exactly, with
  the worklist plan unchanged.

## Not in this piece

No database writes (piece 6). No reviewer stage - and so no path yet from a discover finding to the
writer, which needs reviewer verdicts with `refuted=false` (recorded gap). No per-field evidence
selection, so an oversized site is still refused as a whole rather than field by field. No search
provider: the answer contract requires a source the run itself fetched, and that is the only kind of
source it can check.
