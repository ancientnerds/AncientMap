# Phase 3 batching plan — the arithmetic, not a vibe

Input: **1,813** Phase-3 sites (`WORKLIST.jsonl`, records with `"phase3": true`).
All token/time/cost figures below are **derived from the plan's own measured anchors**
(`docs/procedures/SITES_DB_REMEDIATION_2026-09.md` §13) — none was measured by this lane.
Where the plan's two anchors disagree, both readings are shown and flagged.

## Superseded, 2026-09-21 (ratified decision 12)

**Superseded figures, kept for the record:** 5 sites per batch, 363 batches, 726 agent runs over
1,813 sites. **Reason:** 5 sites per batch means 726 agent lifecycles, and the project's own
measured fixed overhead is ~31,500 tokens per lifecycle → ~22.9 M tokens of pure overhead versus
~1.3 M for 40 lifecycles. **What holds now:** **15 sites per run** (about **121 runs per stage**
over **1,813** sites), the reviewer stage kept, a 60 KB per-page fetch cap, named features instead
of raw geometry dumps, and T02 as one human vocabulary decision plus a short exception list rather
than 117 reviews. Token accounting must be **MEASURED** on the first instrumented run: the plan's
two anchors differ by 2× and must not be averaged.

### Second supersession, 2026-09-21 (Wave 7): the "285 coords-only sites excluded entirely"

**Superseded figures, kept for the record:** 1,528 sites, 102 runs per stage, 204 model runs, and
the clause "the **285 coords-only sites excluded entirely** (`FIELD_CONTRACT.md` §4 item 6 makes
every coordinate correction human, so those 570 runs can write nothing)". **Reason:** that
exclusion rested on a claim the cited rules do not support. `FIELD_CONTRACT.md` §4 item 6 and
`ENRICHMENT_AUDIT.md` anti-pattern 4 speak only about **coordinate** findings, and the census says
nothing about those sites' other fields. What is supported is the narrower statement: **no *census
finding* of these 285 sites is writable** — re-verified on `WORKLIST.jsonl` 2026-09-21: 285 records
whose only finding is `T01/coords`, exactly one finding each (202 `moderate`, 83 `severe`). The
pilot then found **three defects the census never named, two of them prose** — exactly what "only
T01/coords" does not exclude. **What holds now:** the 285 are **in** Phase 3, so the scope is
**1,813 sites**; 15 sites per run; and the fixed-overhead figure for the ratified shape is 242
lifecycles × ~31,500 ≈ **7.6 M tokens** (not 726 × 31,500 ≈ 22.9 M). Everything else in decision
12 is unchanged and still binding.

## Measured / plan inputs

| Input | Value | Source |
|---|---|---|
| Phase-3 sites | **1,813**, all of them — including the 285 coords-only sites (second supersession above; as first ratified: "1,813, of which **285 coords-only are excluded** → **1,528 worked**") | measured here (`_counts.json`: `phase3_sites: 1813`; re-verified on `WORKLIST.jsonl` 2026-09-21: 1,840 records, 1,813 with `phase3=true`, 285 whose only finding is `T01/coords`) |
| Sites per agent | **15** (superseded: 5 — decision 12) | ratified 2026-09-21 |
| Tokens per site (both stages) | ~40,000 | plan §13 “measured anchor” |
| Run-1 anchor | 36 agents / 3,653,051 tokens / 37 min at 10–14 parallel | plan §13 |

## Agent runs and batches

```
batches           = ceil(1813 / 15)            = 121 batches per stage
agent runs        = 121 finder + 121 reviewer  = 242 model runs
                    (each batch runs the finder, then the reviewer on its findings)

superseded (15 sites per run over the 1,528 worked set, 2026-09-21):
batches           = ceil(1528 / 15)            = 102 batches per stage, 204 model runs

superseded (5 sites per run, all 1,813 sites):
batches           = ceil(1813 / 5)             = 363 batches, 726 model runs
```

The last batch holds 13 sites (121×15 = 1,815 ≥ 1,813). No site class is held back: the 285
coords-only sites are batched with the rest (second supersession above).

## Token budget

```
Per-site anchor:   1813 × 40,000            = 72,520,000 tokens
Run-1 anchor:      3,653,051 / 40,000       = 91.3 sites processed in run 1

superseded: 1528 × 40,000 = 61,120,000 tokens (worked set was 1,528)
```

**The plan's two anchors do not reconcile, and the gap is 2×.**

* If run 1 covered 36 agents × 5 sites = **180 sites**, its effective rate is
  `3,653,051 / 180 = 20,294.7 ≈ 20,295 tokens/site` → this worklist ≈ **36.8 M tokens**
  (*as first published: "20,293 tokens/site … ≈ 36.8 M (≈ 31.0 M over the 1,528 worked sites)" —
  the division is corrected to its true quotient and the 1,528 figure no longer applies*).
* If the **40,000 tokens/site** anchor is right, run 1 could only have covered
  **~91 sites** (~2.5 sites/agent, not 5) → this worklist ≈ **72.5 M tokens** (*as first
  published, with the superseded second reading: "≈ 72.5 M (≈ 61.1 M over the 1,528 worked
  sites)"*).

Both cannot be true with 5 sites/agent. **The supervisor must pin which anchor holds before
approving the budget** — it is the difference between a ~6-hour and a ~12-hour run.

## Wall clock

Run 1's throughput is `3,653,051 / 37 = 98,731 tokens/min` at 10–14 parallel.

| Reading | Extrapolation | Wall clock |
|---|---|---|
| 180-site run 1 (throughput ≈ 4.86 sites/min) | 1813 / 4.86 | **≈ 373 min ≈ 6.2 h** (*as first published, worked set 1,528: ≈ 315 min ≈ 5.2 h*) |
| 40k-tokens/site anchor | 72.52 M / 98,731 | **≈ 734 min ≈ 12.2 h** (*as first published: ≈ 619 min ≈ 10.3 h over the worked 1,528*) |

At 12 parallel: `121 / 12 = 10.1 waves` per stage (superseded: `102 / 12 = 8.5 waves` over the
1,528 worked set, and `363 / 12 = 30.25 waves` at 5 sites per run). A 15-site run takes
correspondingly longer than the pilot's ~12.3 min/wave at 5 sites, so the wave count and the
per-site extrapolation above tell the same story — ~6.2 h at the 180-site reading. The two walls
differ by the same 2× as the tokens; they are one uncertainty, not two.

## Cost

The plan's cost table gives **~$350 for the reduced two-stage audit of ~2,217 sites**
(`$0.158/site`). Scaling to this measured worklist:

```
1813 × (350 / 2217) = ~$286
superseded: 1528 × (350 / 2217) = ~$241 over the 1,528 worked set
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
decision 12); the site counts are the full **1,813** and no site class is removed (second
supersession above; as first ratified the 285 coords-only sites were removed and the worked total
was 1,528).

The first 32 batches cover every `severe` site (superseded: 95 at 5 sites per agent); a run stopped
after them still removes all 468 loud errors. Blocks are `ceil`-per-block, so they sum to 123
against the true 121 — the batch count is the whole-list `ceil(1813/15)`, not the sum of rounded
blocks (superseded: 123 against the true 102 when the worked set was 1,528; and 365 against 363 at
5 sites per batch). Spreading severe sites across the whole run instead would mean a budget
stop leaves severe errors untouched.

## Guard rails for the run

* **15 sites per agent** (superseded: 5 — decision 12), **10–14 parallel** — more parallel does not
  shorten a wave, fewer does.
* **The 285 coords-only sites ARE batched** (2026-09-21 — decision 12 excluded them and that
  exclusion is superseded, see above; what the two cited rules forbid is a *coordinate write*, not
  a visit), and **T02 is one human vocabulary decision plus a short exception list**, not 117
  reviews.
* **Attention threshold 600 s** for the fleet (AGENTS.md), so a long finder does not ping.
* **Fresh context per agent**, not a fork (self-contained briefs).
* Reviewer runs after the finder on the same batch; **only `refuted=false` is applied**, with
  a conditional `WHERE` carrying the old value and a journal entry (plan §Phase 3).
* A batch that errors is recorded as an error, never as “clean”.
