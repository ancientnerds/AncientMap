# Goal: the paper loop — make the writer pass its own gate

**Status:** proposed 2026-10-04, on branch `feat/2026-10-04-paper-image-floor`
(worktree `.claude/worktrees/paper-image-floor`). Copy the objective below into a
new goal.

## Objective

```
Run the Theo paper writer against the new gate until it produces papers that pass,
and fix whatever the loop exposes. Three papers, each taken through the studio chain
to `paper bundle` and never to `publish`, each reaching an all-green `paper check`
in at most TWO check iterations. After every paper, write down what the gate said,
what the writer had to change, and what must change in the system (brief, gate,
writer instructions) so the next paper is cheaper than the one before.

The writer is MiniMax-M3.1-Flash-Preview at max speed through
`python -m pipeline.studio mcode`, two runs at a time. Nothing is billed before
2026-10-07.

DONE WHEN three papers exist as a passing `check_report.json` plus a `bundle.json`,
each within two check iterations, and a per-paper ledger exists that says for each
one: the gate findings by rule, the fix that retired them, and the change made to
the brief, the gate or the writer instructions because of them. A paper that needs
a third iteration is a failure of the system, not of the paper, and the ledger says
which of the two it was.

NEVER: no push to main, no deploy, no `paper publish`, no write to production. The
VPS does not know `sentence_evidence` (theo_publish would refuse it as an unknown
result key) and migration 0028 has not run, so `patch_images` is not writable
either. Everything stops at `bundle`.
```

## The three defects the loop will chase, measured, not guessed

Measured on the one real, fully archived workspace on this machine
(`95fa3798-1678-40a4-ae2e-58595de93918`, 90 references, **all 90** with local
source text, so every rule decides a real question):

| Finding | Count | What it is |
| --- | --- | --- |
| `located_sentence` | 78 | one long, value-dense sentence carrying several markers. 65 of the 78 flagged sentences hold **4 or more** checkable values, 10 hold 3, 3 hold 2, and **none** holds only one. Not a threshold artefact: the writer's habit is the defect |
| `sentence_defect` | 38 | 35 × `no_clause_after_marker`, 3 × `fragment_after_marker`. The writer puts the marker at the **start** of a sentence (`"[7] James McAndrew and concluded…"`) instead of before the full stop. A formatting habit, cheap to retire |
| `number_exact` / `unsupported_specific` | 2 | single cases |

The load-bearing number for `located_sentence`: **0 of 78** are on a sentence with
a single specific. The `locate_support` threshold of two matched specifics is
therefore not what fires; the sentence shape is. Relaxing the gate would be the
wrong fix and the loop must not be used to justify one.

## What each paper costs

Per paper, measured on the production chain: one research run is ≈ 380 calls /
≈ 25 M reported tokens / 10–20 h (weekly plan window 62 % used, nothing billed
before 07.10.). The writing loop on top:

- `claims-export` → `mcode claim-check` → `claims-import`: **one `mcode exec` per
  task**. The abandoned draft above has **85 tasks** (42 evidence, 42 paragraphs,
  1 coherence) and had `answered: 0`.
- the image pass: `images-export` → `mcode image-check` → `images-import`.
- then `number` → `check` → `bundle`, and one rewrite round per failing gate.

So the wall-clock currency is model calls, not ideas. Two runs at a time, and 429
above ≈ 1.9 calls/s (`Token Plan rate limit reached (2062)`).

## The material problem, stated 2026-10-04

`theo_dossier list` is empty. `research_requests` holds 32 `completed`, 24
`paused`, 2 `cancelled`, 1 `failed` — **no `researched`, no `queued`**. The worker
container is up but `THEO_WORKER_DISABLED=1`, and the VPS has never seen this
branch.

So a *fresh* paper cannot be produced today without the owner's decision on the
research side. What exists today is one workspace with a complete archive and a
draft that failed its own gates:

| Workspace | archived texts | state |
| --- | --- | --- |
| `95fa3798-1678-40a4-ae2e-58595de93918` | 387 | draft + evidence + paper.md; claim check **unanswered (85 tasks)**, no images, no hero |
| `099ad920-2e52-4180-915c-c040d316f3d7` | 0 | pulled, no archive |
| `1d0053d4-c28b-45db-a30c-20c6501d6147` | 0 | pulled, no archive |
| `ef52c194-e8c8-42a9-b317-e64a273f7780` | 0 | pulled, no archive |

A workspace without `texts/` cannot be written against: the support gate would
report every marker as `unreadable_marker`, which is correct and useless.

## The three options for material, for the owner to pick

1. **Finish the 95fa3798 workspace** (claim check + image pass + rewrite). No
   research tokens, a real paper at the end, but it tests the writing rules on a
   draft that was written *before* the brief said them.
2. **Resume the 24 `paused` research runs** to `researched` and write from fresh
   dossiers. Real fresh papers, costs research tokens (nothing billed before
   07.10.), and the paused runs are continuations, not clean sheets.
3. **Enable the feeder and queue three questions.** The cleanest test of the whole
   chain, the longest time to first result, and it touches the worker that owner
   question Q1 switched off on 2026-09-26.

Option 1 first is the cheap calibration; 2 or 3 afterwards for the fresh ones.

## Where the loop's findings go

`docs/reports/theo-paper-loop-2026-10-04.md`, one section per paper: the gate
findings by rule, what the writer changed, what the system changed because of it.
The same directory as the defect report it answers.

## Paper 1 — `95fa3798`, iteration 1: what the gate said (measured 2026-10-04 20:54)

The workspace is a **legacy draft**: `draft.md` and `evidence.json` are dated
02.10. 19:31, the gate that carries rules 1-8 landed in `f9647bc` on 04.10. 19:56.
Nothing had ever checked this paper against rule 1, so its first `paper check` is
the gate's first contact with it, not a regression.

| | before | after |
| --- | --- | --- |
| support findings | **118** | **88** |
| `no_clause_after_marker` | 35 | **0** |
| `located_sentence` | 78 | 83 |
| `fragment_after_marker` | 3 | 3 |
| `number_exact` / `unsupported_specific` | 1 / 1 | 1 / 1 |
| `evidence` / `page_anchors` / `coherence` | red | **green** |

`located_sentence` rose by 5 and that is the fix working: a misplaced marker used to
hide behind a structural defect, so the gate never got as far as asking the right
source about the right sentence.

### The one habit behind 113 of the 118

The writer put the marker **after** the full stop instead of before it:

    ...could not be scientifically justified. [S:262eb541b9f7] The 1997 Sturrock Panel...

A marker in that position annotates the *following* sentence, so the gate asked the
Condon source to carry the Sturrock sentence. One habit, both error classes: 35
`no_clause_after_marker` plus the bulk of the 78 `located_sentence`.

A marker that follows a full stop has exactly one possible meaning, so this is code
and not a writer instruction: `normalize_marker_placement()` in
`pipeline/studio/paper/numbering.py`, called by `number_draft()` before the
`[S:<id>]` → `[N]` substitution. Precedent in the same house: `clean_gallery_alt()`.

### What that fix exposed, and the second fix

Moving the marker across the full stop broke **ev-12**: its anchor text ended in a
full stop, and `normalize_anchor_text` replaces a citation marker with a *space*, so
`... literary import [27].` normalised to `literary import .` while the anchor read
`literary import.` — no match. Removing apparatus must not change the prose it
stands in, so `normalize_anchor_text` now drops a space that sits in front of
sentence punctuation or behind an opening one.

This is a **hole that predates the normaliser**: the house form is marker-before-full
stop, so every anchor written on the house form was already exposed. The existing
test `test_citation_and_draft_markers_disappear` had pinned the wrong result
(`"dated to 9600 bc ."`); it now pins the right one.

The change can only **add** matches, never remove one: both sides of every comparison
go through the same function.

### The 88 that are left, classified without a model

Of the 82 `located_sentence` findings, for every marker the gate checks whether a
*different* source already cited in the same paragraph carries the sentence
(`locate_support`, the gate's own function):

| | count | what it costs |
| --- | --- | --- |
| another cited source carries it | **32** | one marker, mechanical |
| the marker itself locates on a narrower sentence | **4** | split or narrow the sentence |
| **no cited source in the paragraph carries it** | **54** | narrow, drop, or find the source |

The 54 are not gate artefacts. Spot-checked by hand: marker `[37]` (a USA Today
article about the June 2021 ODNI report) is cited for "AATIP was a $22 million
Pentagon program that ran from 2007 to 2012", and marker `[28]` (a Metabunk thread
about the GIMBAL video) for a sentence about the British Black Knight rocket. The
texts are the right texts — **8 of 90 archived texts are filed under the wrong
record**, the other 82 are clean — so these are the writer's own mis-citations.

That is the defect the claim check exists to catch: `claims.py` asks each paragraph's
verifier for a `fix_suggestion` naming the marker the claim needs, and
`claim_status` fails the gate on every answer that is not `supported`. The 88 support
findings and the 85 claim tasks are **one job seen from two sides**, so the order is
`claims-export` → mcode → `claims-import` → apply the suggestions → `check`, not a
hand repair of the 88 first.
