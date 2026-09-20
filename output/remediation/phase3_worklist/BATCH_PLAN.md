# Phase 3 batching plan — the arithmetic, not a vibe

Input: **1,813** Phase-3 sites (`WORKLIST.jsonl`, records with `"phase3": true`).
All token/time/cost figures below are **derived from the plan's own measured anchors**
(`docs/procedures/SITES_DB_REMEDIATION_2026-09.md` §13) — none was measured by this lane.
Where the plan's two anchors disagree, both readings are shown and flagged.

## Measured / plan inputs

| Input | Value | Source |
|---|---|---|
| Phase-3 sites | 1,813 | measured here (`_counts.json`) |
| Sites per agent | 5 | plan §Phase 3 (“pilot value”) |
| Tokens per site (both stages) | ~40,000 | plan §13 “measured anchor” |
| Run-1 anchor | 36 agents / 3,653,051 tokens / 37 min at 10–14 parallel | plan §13 |

## Agent runs and batches

```
batches           = ceil(1813 / 5)            = 363 batches
agent runs        = 363 finder + 363 reviewer = 726 model runs
                    (each batch runs the finder, then the reviewer on its findings)
```

The last batch holds 3 sites (363×5 = 1,815 ≥ 1,813).

## Token budget

```
Per-site anchor:   1813 × 40,000            = 72,520,000 tokens
Run-1 anchor:      3,653,051 / 40,000       = 91.3 sites processed in run 1
```

**The plan's two anchors do not reconcile, and the gap is 2×.**

* If run 1 covered 36 agents × 5 sites = **180 sites**, its effective rate is
  `3,653,051 / 180 = 20,293 tokens/site` → this worklist ≈ **36.8 M tokens**.
* If the **40,000 tokens/site** anchor is right, run 1 could only have covered
  **~91 sites** (~2.5 sites/agent, not 5) → this worklist ≈ **72.5 M tokens**.

Both cannot be true with 5 sites/agent. **The supervisor must pin which anchor holds before
approving the budget** — it is the difference between a ~6-hour and a ~12-hour run.

## Wall clock

Run 1's throughput is `3,653,051 / 37 = 98,731 tokens/min` at 10–14 parallel.

| Reading | Extrapolation | Wall clock |
|---|---|---|
| 180-site run 1 (throughput ≈ 4.86 sites/min) | 1813 / 4.86 | **≈ 373 min ≈ 6.2 h** |
| 40k-tokens/site anchor | 72.52 M / 98,731 | **≈ 734 min ≈ 12.2 h** |

At 12 parallel: `363 / 12 = 30.25 waves`; at ~12.3 min/wave (180-site reading) → 6.2 h.
The two walls differ by the same 2× as the tokens; they are one uncertainty, not two.

## Cost

The plan's cost table gives **~$350 for the reduced two-stage audit of ~2,217 sites**
(`$0.158/site`). Scaling to this measured worklist:

```
1813 × (350 / 2217) = ~$286
```

That is a plan-derived estimate, **not measured here**. At list prices it brackets
$100 (Haiku) … $500 (Opus) depending on model; the binding input is which of the two
token anchors above is used.

## Order — worst first

`WORKLIST.jsonl` is already sorted `max_severity DESC, n_checks DESC, n_findings DESC`.
The run order is that file, top to bottom, in batches of 5:

| Priority block | Sites | Batches (5/agent) | Why first |
|---|---|---|---|
| 3 factual checks agree | 11 | 3 | Three independent signals say something is wrong — highest confidence of a real error. |
| severe, 1–2 checks | 457 | 92 | Would be read aloud wrong or move the pin/title (`Severity.SEVERE`). |
| moderate | 1,174 | 235 | Visibly wrong on an indexed page. |
| cosmetic | 171 | 35 | Recorded for completeness (e.g. T02 borders, T05 name variants). |

The first 95 batches cover every `severe` site; a run stopped after them still removes all
468 loud errors. Blocks are `ceil`-per-block, so they sum to 365 against the true 363 — the
batch count is the whole-list `ceil(1813/5)`, not the sum of rounded blocks. Spreading severe sites across the whole run instead would mean a budget
stop leaves severe errors untouched.

## Guard rails for the run

* **5 sites per agent, 10–14 parallel** — the plan's measured pilot values; more parallel
  does not shorten a wave, fewer does.
* **Attention threshold 600 s** for the fleet (AGENTS.md), so a long finder does not ping.
* **Fresh context per agent**, not a fork (self-contained briefs).
* Reviewer runs after the finder on the same batch; **only `refuted=false` is applied**, with
  a conditional `WHERE` carrying the old value and a journal entry (plan §Phase 3).
* A batch that errors is recorded as an error, never as “clean”.
