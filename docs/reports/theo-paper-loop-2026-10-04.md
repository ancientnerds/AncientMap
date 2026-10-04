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
