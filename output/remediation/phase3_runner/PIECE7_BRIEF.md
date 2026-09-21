# Piece 7 — the mass-run driver: many batches, unattended, resumable, bounded

**Status:** brief, not yet built. Follows piece 5 (discover pass) and piece 6 (the writer).
**Written:** 2026-09-21 by the supervisor.

## 1. Why this piece exists

Pieces 1–4 built the runner and piece 5 makes it able to reach every site. Neither runs 334 batches.
This piece is the thing that actually does the work: a script, driven by `bg_run`, that walks the plan
and runs `prepare` → `fetch` → `judge` per batch until it is done or the budget says stop.

It is a **script, not a subagent lane**, and that is a measured decision, not a preference: the
30-minute subagent ceiling binds *lanes*, while a `bg_run`-driven script has no such ceiling. Every
batch this session that failed inside a lane failed for reasons that had nothing to do with the work
(two fixers timed out at 30 min; the workflow receipt then reported a file list that was false). A
script that logs to files it controls cannot lose its evidence that way.

## 2. The arithmetic that shapes it

All fetched evidence is stored by (site, feature), so a re-run re-fetches nothing — the reason
resumability is cheap here and must not be traded away.

| measured | value | source |
| --- | --- | --- |
| fetch cost per target | ~8.8 s | pilot `COST.md` |
| fetches per site | **15.2** | pilot `COST.md` (76 fetches / 5 sites) |
| judge cost per call | ~2.6 s | batch-0001 (15 calls in 39 s) |
| cost per call | **$0.000486** | batch-0001 ledger |

So one 15-site batch is roughly **225 fetches ≈ 30 minutes** of wall clock, against **39 seconds** of
judgement. With 121 batches for the 1,813-site worklist and ~334 for all 5,004, one batch at a time is
**~60 h / ~167 h per stage** — and two stages double it. The money is not the constraint (**$2.43** per
stage for 5,004 sites); the wall clock is.

Two conclusions, both of which the driver has to carry:

1. **Batches must run in parallel**, bounded and configurable (start at 4; the bottleneck is per-host
   network latency, not CPU). That is what makes 5,004 sites a night's work instead of a week's.
2. **Politeness is a hard requirement, not a nice-to-have.** Parallel batches hitting the same hosts
   multiply the request rate. One shared per-host rate limit (a small global minimum interval between
   requests to the same host) and one honest `User-Agent` naming the project and a contact. No retry
   storm: piece 4b already cut a dead host to one request per run.

## 3. Requirements

1. **Resumable by construction.** A batch is done when its artefacts exist and are complete; the driver
   skips it and says so. Killing the driver and restarting it must never lose the ledger and never
   re-buy a call already paid for. The ledger is the record of what was bought — an unrecorded or
   duplicated charge is exactly what it exists to prevent.
2. **A real budget, checked before each batch.** Hard ceilings in calls and in USD, taken from the
   ledger's own summed `cost_usd` (provider-reported, never computed from a price table). On reaching a
   ceiling the driver stops **between** batches and writes a summary naming what it did and what it did
   not reach.
3. **A circuit breaker.** N consecutive batch failures (default 3) stop the run rather than burning
   through 300 batches against a broken assumption. Failures are recorded per batch with their reason.
4. **A progress record a human can read at any time**, not only at the end: batches planned / done /
   failed, sites judged, calls made, dollars spent, and the per-stage split. One file, rewritten
   atomically, plus the append-only ledger.
5. **Logs go to files the driver owns** (`output/remediation/logs/massrun/<run>/…`). A bounded `bg_run`
   log keeps only a tail and has been observed to keep 7 bytes and no output at all — a run whose
   evidence lives only in that log has no evidence.
6. **One writer per tree.** The driver must refuse to start if the phase-3 sources change underneath it
   (hash the package at start, compare before each batch, stop with a clear message on a change).
   `fetch` and `judge` are separate processes, so a mid-run edit makes one batch execute two versions
   of the code — a hazard already identified this session.
7. **Dry-run by default**, and the dry run must print the plan's shape (batches, sites, calls, expected
   cost from the measured per-call figure) without buying anything.
8. **No database, no writes.** This piece produces findings. Piece 6 turns confirmed findings into
   guarded writes; keeping the two apart is what makes the findings safe to produce in bulk.

## 4. Tests

* Resume: a batch whose artefacts exist is skipped; a batch whose artefacts are half-written is redone
  rather than trusted (a truncated artefact is not evidence).
* The budget stops the run between batches, never mid-call, and the summary names what was not reached.
* The circuit breaker trips after N consecutive failures and says which batch and why.
* The source-hash guard refuses a run whose sources changed under it.
* The dry run buys nothing: assert zero ledger lines, not "no error was raised".
* Each of the above is mutation-proven.

## 5. Non-goals

* Applying anything (piece 6).
* Deciding the scope: 1,813 or all 5,004 is the owner's call, and the driver takes it as a parameter so
  either answer costs no new code.
* Re-running the census, the image work, or the gold standard.
