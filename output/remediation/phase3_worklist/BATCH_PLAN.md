# Phase 3 batching plan — the arithmetic, not a vibe

Input: **1,813** Phase-3 sites (`WORKLIST.jsonl`, records with `"phase3": true`).
All token/time/cost figures below are **derived from the plan's own measured anchors**
(`docs/procedures/SITES_DB_REMEDIATION_2026-09.md` §13) — none was measured by this lane.
Where the plan's two anchors disagree, both readings are shown and flagged.

## Superseded, 2026-09-21 (ratified decision 12)

**Superseded figures, kept for the record:** 5 sites per batch, 363 batches, 726 agent runs over
1,813 sites. **Reason:** 5 sites per batch means 726 agent lifecycles, and the project's own
measured fixed overhead is ~31,500 tokens per lifecycle → ~22.9 M tokens of pure overhead versus
~1.3 M for 40 lifecycles. **What holds now:** **15 sites per run** (about **102 runs per stage**
over **1,528** sites), the **285 coords-only sites excluded entirely** (`FIELD_CONTRACT.md` §4
item 6 makes every coordinate correction human, so those 570 runs can write nothing), the reviewer
stage kept, a 60 KB per-page fetch cap, named features instead of raw geometry dumps, and T02 as
one human vocabulary decision plus a short exception list rather than 117 reviews. Token
accounting must be **MEASURED** on the first instrumented run: the plan's two anchors differ by 2×
and must not be averaged.

## Measured / plan inputs

| Input | Value | Source |
|---|---|---|
| Phase-3 sites | 1,813, of which **285 coords-only are excluded** → **1,528 worked** | measured here (`_counts.json`; the 285 re-verified on `WORKLIST.jsonl`: sites whose only findings are `T01/coords`) |
| Sites per agent | **15** (superseded: 5 — decision 12) | ratified 2026-09-21 |
| Tokens per site (both stages) | ~40,000 | plan §13 “measured anchor” |
| Run-1 anchor | 36 agents / 3,653,051 tokens / 37 min at 10–14 parallel | plan §13 |

## Agent runs and batches

```
batches           = ceil(1528 / 15)            = 102 batches per stage
agent runs        = 102 finder + 102 reviewer  = 204 model runs
                    (each batch runs the finder, then the reviewer on its findings)

superseded (5 sites per run, all 1,813 sites):
batches           = ceil(1813 / 5)             = 363 batches
agent runs        = 363 finder + 363 reviewer  = 726 model runs
```

The last batch holds 13 sites (102×15 = 1,530 ≥ 1,528). The 285 coords-only sites stay in
`WORKLIST.jsonl` but are not batched.

## Token budget

```
Per-site anchor:   1813 × 40,000            = 72,520,000 tokens   [superseded: worked set is 1,528]
                                             1528 × 40,000 = 61,120,000 tokens
Run-1 anchor:      3,653,051 / 40,000       = 91.3 sites processed in run 1
```

**The plan's two anchors do not reconcile, and the gap is 2×.**

* If run 1 covered 36 agents × 5 sites = **180 sites**, its effective rate is
  `3,653,051 / 180 = 20,293 tokens/site` → this worklist ≈ **36.8 M tokens** (≈ **31.0 M** over the
  1,528 worked sites).
* If the **40,000 tokens/site** anchor is right, run 1 could only have covered
  **~91 sites** (~2.5 sites/agent, not 5) → this worklist ≈ **72.5 M tokens** (≈ **61.1 M** over
  the 1,528 worked sites).

Both cannot be true with 5 sites/agent. **The supervisor must pin which anchor holds before
approving the budget** — it is the difference between a ~6-hour and a ~12-hour run.

## Wall clock

Run 1's throughput is `3,653,051 / 37 = 98,731 tokens/min` at 10–14 parallel.

| Reading | Extrapolation | Wall clock |
|---|---|---|
| 180-site run 1 (throughput ≈ 4.86 sites/min) | 1813 / 4.86 → 1528 / 4.86 | **≈ 373 min ≈ 6.2 h** → **≈ 315 min ≈ 5.2 h** over the worked 1,528 |
| 40k-tokens/site anchor | 72.52 M / 98,731 → 61.12 M / 98,731 | **≈ 734 min ≈ 12.2 h** → **≈ 619 min ≈ 10.3 h** over the worked 1,528 |

At 12 parallel: `102 / 12 = 8.5 waves` per stage (superseded: `363 / 12 = 30.25 waves` with 5
sites per run). A 15-site run takes correspondingly longer than the pilot's ~12.3 min/wave at 5
sites, so the wave count and the per-site extrapolation above tell the same story — ~5.2 h at the
180-site reading. The two walls differ by the same 2× as the tokens; they are one uncertainty, not
two.

## Cost

The plan's cost table gives **~$350 for the reduced two-stage audit of ~2,217 sites**
(`$0.158/site`). Scaling to this measured worklist:

```
1813 × (350 / 2217) = ~$286   [superseded: worked set is 1,528]
1528 × (350 / 2217) = ~$241 over the worked set
```

That is a plan-derived estimate, **not measured here**. At list prices it brackets
$100 (Haiku) … $500 (Opus) depending on model; the binding input is which of the two
token anchors above is used.

## Order — worst first

`WORKLIST.jsonl` is already sorted `max_severity DESC, n_checks DESC, n_findings DESC`.
The run order is that file, top to bottom, in batches of **15** (superseded: 5 — decision 12):

| Priority block | Sites | Batches (15/agent) | Why first |
|---|---|---|---|
| 3 factual checks agree | 11 | 1 | Three independent signals say something is wrong — highest confidence of a real error. |
| severe, 1–2 checks | 457 | 31 | Would be read aloud wrong or move the pin/title (`Severity.SEVERE`). |
| moderate | 1,174 | 79 | Visibly wrong on an indexed page. |
| cosmetic | 171 | 12 | Recorded for completeness (e.g. T02 borders, T05 name variants). |

The “Batches” column previously read 3 / 92 / 235 / 35 at 5 sites per agent (**superseded** —
decision 12); the site counts are the plan’s pre-exclusion figures, and the 285 coords-only sites
are removed from the run, so the worked total is 1,528 rather than 1,813.

The first 32 batches cover every `severe` site (superseded: 95); a run stopped after them still
removes all 468 loud errors. Blocks are `ceil`-per-block, so they sum to 123 against the true 102 —
the batch count is the whole-list `ceil(1528/15)`, not the sum of rounded blocks (superseded: 365
against 363 at 5 sites per batch). Spreading severe sites across the whole run instead would mean a budget
stop leaves severe errors untouched.

## Guard rails for the run

* **15 sites per agent** (superseded: 5 — decision 12), **10–14 parallel** — more parallel does not
  shorten a wave, fewer does.
* **The 285 coords-only sites are not batched** (decision 12), and **T02 is one human vocabulary
  decision plus a short exception list**, not 117 reviews.
* **Attention threshold 600 s** for the fleet (AGENTS.md), so a long finder does not ping.
* **Fresh context per agent**, not a fork (self-contained briefs).
* Reviewer runs after the finder on the same batch; **only `refuted=false` is applied**, with
  a conditional `WHERE` carrying the old value and a journal entry (plan §Phase 3).
* A batch that errors is recorded as an error, never as “clean”.
