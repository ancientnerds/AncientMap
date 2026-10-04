# Paper image floor, section structure and production run — goal and plan

**Date:** 2026-10-04
**Branch:** `feat/2026-10-04-paper-image-floor` (base `1de5ae5`)
**Status:** in progress, **nothing started on the VPS**, no push
**Predecessor:** `2026-10-04-A-theo-paper-optimization.md` (the process map and the measured
baseline this plan executes)
**Owner instruction 2026-10-04 17:57:** own branch, do not start yet, plan and goal first.

## 1. The goal

> **Der beste Research-Paper-Generator, den das kostenlose MiniMax-M3.1-Kontingent bis 07.10.
> hergibt — und die 31 Live-Papers auf dieselbe Hausregel bringen.**

### Acceptance criteria (each one measurable with the scripts of plan A §2)

| # | Criterion | Today (measured 2026-10-04) |
|---|---|---|
| G1 | Every content section of every published paper carries at least one image | **109 of 189 sections empty** (58 %) |
| G2 | Every new paper passes `paper check`, which refuses a section without an image | not enforced anywhere |
| G3 | Investigation sections 3–6 (was 2–4; 14 of 31 papers sat on the old cap) | cap binds |
| G4 | No machine marker visible on a paper page | **52 occurrences** of `gallery:…\|verified:yes\|…` in the served HTML |
| G5 | Every reference line carries a resolvable URL or a DOI, and no raw HTML | **83 without URL**, 3 with raw HTML |
| G6 | Production: as many new papers as the measured budget allows, published with the new rules | 0 papers ever published through the new chain |

**What "done" explicitly does not mean:** four images in every section of every paper. The measured
loss is dominated by rejected candidates (36–189 per paper lost to `embed_skip_no_safe_candidates`),
not by the budget. Four per section is the reported target, one per section is the hard rule, and a
section that stays below four is named in the report instead of hidden.

### The production ceiling, measured not estimated

| Quantity | Value | Source |
|---|---|---|
| Weekly plan remaining now | **62 %** | `probe_minimax_quota()`, 2026-10-04 15:20 UTC |
| Weekly window | Mo 2026-09-28 00:00 UTC → **Mo 2026-10-05 00:00 UTC** (resets in 8.6 h) | probe `weekly_start_time` / `weekly_end_time` |
| Free allowance ends | 2026-10-07 — so exactly **one** more full weekly window falls inside it | owner |
| **Cost until 07.10.2026** | **nothing is charged** — the allowance may be spent in full with no cost consequence | owner, 2026-10-04 18:14 |
| Cost of one full-depth research run | ~380 LLM calls, ~25 M reported tokens, 10–20 h | 29 completed runs in `research_requests` |
| Plan cost of that run | **≈ 25–33 % of one weekly window** | 49.6 M reported for 3 papers = 64 % of a 597 M window (2026-08-07) |
| ⇒ Papers until 07.10. | **≈ 5–6 full-depth papers** (62 % + 100 %, minus Lyra's reserve) | arithmetic on the two rows above |

**Parallelism does not raise this number.** The plan's limit is a token budget, not a concurrency
cap: measured on 2026-10-04, 8 concurrent calls are clean, 16 are clean, and once the short-window
burst bucket is drained even **1.9 calls/s** returns `429 … Token Plan rate limit reached (2062)`.
Running four papers at once would not produce four times the papers, it would make all four hit 2062
and retry. The only lever on paper count is depth per paper.

**What "nothing is charged until 07.10.2026" does and does not change.** It removes the cost
consequence, so the allowance can be spent in full and freely — a quota ceiling of the kind one
would set against a bill is not needed here. It does **not** remove the 5-hour window, the weekly
window, or the 2062 rate cap: those are Token Plan mechanics, not accounting, and they are what
limit throughput. Whether the plan keeps resetting weekly after 07.10 (and is then billed) or the
access ends is not yet answered, and it decides whether everything has to be finished before the
07.10.

## 2. What is already written (this branch, uncommitted until the suite is green)

| Change | File | Effect |
|---|---|---|
| Image budget is a real setting | `pipeline/lyra/config.py` | was a `getattr` literal (24) in `probative_images.py:475`, so no environment could move it |
| The dead setting is gone | same | `images_per_paragraph_target: int = 3` was defined and never read |
| New per-section settings | same | `probative_images_min_per_section: 1`, `probative_images_target_per_section: 4` |
| **Section round-robin** | `pipeline/lyra/handlers/probative_images.py` | `order_opportunities_by_section()` — the budget now reaches every section before it deepens one. This is the fix for G1 |
| Coverage measurement | `pipeline/lyra/theo_image_captions.py` | `images_per_section(report)` — an empty section is reported as 0, not missing |
| The backfill reports it | `pipeline/lyra/backfill_probative_images.py` | writes `probative_images_coverage` with `per_section`, `sections_without_image`, `sections_below_target` |
| **The gate** | `pipeline/studio/paper/gates.py` | `IMAGES_MIN_PER_SECTION = 1`; `gate_images` now fails with the list of sections that have none (G2) |
| 3–6 investigation sections | same | `INVESTIGATIONS = (3, 6)` (G3) |
| The brief says so | `pipeline/studio/paper/brief_template.md` | "every section needs at least one opportunity", 4 per section as the goal, 24–36 opportunities for a 6–9 section paper |
| **The marker is gone from the page** | `pipeline/article_html_renderer.py` | `clean_gallery_alt()` strips `gallery:<hash>\|verified:<y\|n>\|` from the figcaption **and** from the `alt` attribute, so a screen reader no longer reads the hash (G4) |
| One cleaner, not three | `api/services/theo_blocks.py` | had its own copy of the regex; now imports the canonical one from the module that writes the marker |

The limiter needed **no change**, which is a finding rather than a skipped task: the default
`max_concurrency` is 8, `reset()` is already deprecated, and `is_quota_error()` correctly returns
`False` for the measured `2062`, so a rate throttle is backed off instead of freezing the run for
five minutes as a budget death would.

## 3. Phases

### Phase 1 — this branch: land the rules (no VPS, no quota)

1. Run the full gate suite and the frontend gates.
2. Commit with explicit paths only — the other session commits to the same repository.
3. **No push.** A push to `main` is a live deploy and would take the other session's in-flight
   paper repairs with it.

*Acceptance:* suite green, `git show --stat` lists only the files of this plan.

### Phase 2 — the visible defect, independently deployable (G4)

Ships on its own because it is small, user-visible today, and costs no quota. The marker has been in
the reader's face on every gallery image since the 2026-04 rework.

*Acceptance:* a paper page's HTML contains no `gallery:` outside a data attribute; the 4 new figure
tests pass; the other renderer consumers (journals, Medium copies) unaffected.

### Phase 3 — the corpus campaign (G1), quota-neutral first

Three stages, cheapest first, each separately measurable and abortable:

- **3a Place what we already own.** 530 pool images are on disk with `section_heading` and
  `paragraph_index` (measured 530/530), 482 are in the text. Placing the missing 48 needs **no
  image search and no VLM call**. Blocked today by `backfill_probative_images.py:182-184`, which
  hard-codes an empty candidate pool and forces an on-demand re-search, and by `--replace`, which
  strips the inline images first. Needs: pass the stored pool into `embed_probative_images`.
  *Acceptance:* pool = text for all 31 papers; `the-enuma-elish-…` goes from 0 to 24 visible images.
- **3b One image per section.** The backfill's floor pass over the sections still empty. ~140 images
  across the corpus.
  *Acceptance:* `sections_without_image` empty, or a named list with the reason.
- **3c Top up to four.** Only for sections at 1–3, budget `4 × n_sections` (max 28).
  *Acceptance:* per paper the sections that reached four and the ones that did not, with the
  rejection reason from the image counters.

Every write goes through the journalled CLI: dry run (exit 1 = gate red, nothing written), then
apply, then read `theo_paper_publications` to confirm exactly one row per write. A `bundle_sha256`
matching the sent bundle means the write committed — never re-run it.

### Phase 4 — the new chain, before its first paper (G2, G3, G6)

Apply the brief, the gate and the settings to the authoring path, then start the worker. The first
paper published through `action='publish'` is the real acceptance test: the corpus work cannot prove
the new path, because the new path has never run.

*Acceptance:* one paper published with 3–6 investigation sections, ≥1 image per section, an
independently written `claims_check`, and a clean `theo_paper_publications` row.

### Phase 5 — production until 07.10. (G6)

Run one research paper at a time. The measured numbers say parallel runs buy no papers and only
multiply 2062 retries. Watch the weekly percentage, not the call count: `probe_minimax_quota()` is
the only trustworthy signal (`total_tokens` understates the plan by ~7×).

*Acceptance per paper:* `paper check` green, published with a journal row, the coverage block
written, one new row in `theo_paper_publications`.

## 4. Cost of the plan against the free allowance

| Item | Plan tokens | Share of a weekly window |
|---|---|---|
| Phase 1–2 (code + one deploy) | none | 0 % |
| Phase 3a (48 images placed) | none — no search, no VLM | 0 % |
| Phase 3b (~140 images) | ~1 VLM call per candidate | ~2 % |
| Phase 3c (top up to 4) | the expensive one | ~3–5 % |
| Phase 5 (production) | ~25–33 % per paper | the whole allowance |

Lyra's daily reserve stays in the batch gate, so Lyra must not be starved on Monday 06:00 UTC when
its journal run starts.

## 5. Risks

| Risk | Why it is real | What bounds it |
|---|---|---|
| The other session's commits collide | it committed `1de5ae5` to the shared branch three minutes before this branch was cut; HEAD moves under an agent | explicit-path staging, own branch, no push until the owner says |
| A deploy takes their in-flight repairs live | a push to `main` deploys whatever the commit contains | no push from this session |
| 4 images per section is unreachable | 36–189 candidates per paper rejected by the VLM | 1 is the hard rule, 4 is reported, the shortfall is named |
| The weekly budget is spent before 07.10. | the window resets Mo 00:00 UTC, the allowance ends Wed | the percentage is checked before every paper, the run stops at a threshold the owner sets |
| The stricter gate blocks a publication | a section whose subject has no probative image at all | the report names it; the owner decides per paper |

## 6. Open decisions for the owner

1. **Push:** who pushes, and does it wait for the other session to finish? (A push is a live
   deploy of both efforts.)
2. **Phase 3 quota ceiling:** the measured full-backfill cost is ~2 % of a weekly window per paper,
   i.e. ~60 % for all 31 in one sweep. A per-run ceiling the driver stops at would be safer.
3. **The remaining 9 papers** the other session has not touched: does Phase 3a–c wait for them, or
   run on the 22 already journaled?
4. **Production depth:** full depth (5–6 papers, ~14 h each) or a cheaper configuration for more,
   shallower papers. The lever is `minimax_source_max_content_chars` (12 000 now, was 2 000) and the
   number of angles — not concurrency.
5. **After 07.10.:** does the Token Plan keep resetting weekly and is then billed, or does the access
   end? Nothing is charged until that date either way, so the answer decides whether the work has to
   be finished before it or may simply continue.
