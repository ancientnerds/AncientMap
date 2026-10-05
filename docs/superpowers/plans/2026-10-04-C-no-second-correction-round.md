# What a second correction round must not have to fix

**Date:** 2026-10-04
**Branch:** `feat/2026-10-04-paper-image-floor` (worktree `.claude/worktrees/paper-image-floor`)
**Why this document exists:** the owner asked whether the plan prevents the corrections the other
session is applying right now from having to be made again. **Plan B did not answer that.** It
optimised the generator's shape; it never mapped a correction class onto the gate that prevents it.
This document is that mapping, and it is honest about the classes that remain open.

## 1. What is being corrected, counted from the live data

The correction entries in `research_requests.result_json.corrections` carry only `date` and `text`
(114 entries, 22 papers). The classes are stated in the prose, and
`scripts/theo_paper_acceptance.py` parses them out:

| Fix class | Count | What the writer did wrong |
|---|---|---|
| replace claim | **381** | stated the claim more strongly than the source does |
| delete claim | **201** | asserted something no source supports |
| reattribute | **155** | cited a reference that does not support the sentence |
| replace number | **30** | a measurement that the source does not carry |
| replace date | **17** | a date that the source does not carry |
| **total fixes applied** | **784** | |
| assertions on unreadable sources | **155** | rests on a paywall, bot protection or a video without a transcript |

> The first version of this table counted the *mentions* of a class instead of summing the numbers
> in the prose ("8 reattribute" is eight fixes, not one) and was low by a factor of ten. The test
> `tests/scripts/test_theo_paper_acceptance.py::test_fix_classes_are_parsed_out_of_a_correction_entry`
> pins the summing behaviour.

The audit behind one of them, verbatim from the stored entry: *"Of 72 verifiable assertions, 44 did
not hold up: they were unsupported, attributed to the wrong reference, or contradicted by the very
source cited. 19 were confirmed as written."*

**The correction itself is unstructured.** No `kind`, no per-fix record, nothing a machine can verify
or roll back — only prose. That is a separate finding, and it is the reason a second round cannot
even be *measured* today.

## 2. The prevention ledger

| Class | Root cause | Gate that prevents it | Strength | Status |
|---|---|---|---|---|
| **replace number** (30) | a measurement in the prose that the cited source does not carry | gate 4 *specifics*: every measurement of a cited paragraph must appear in that source's archived text; gate 5 *coherence* for numbers that contradict across the paper | **strong** — the rule is exact | **already in the studio chain** |
| **replace date** (17) | a date the cited source does not carry | same two gates (dates are part of `extract_specifics`) | **strong** | **already in the studio chain** |
| **reattribute** (155) | the `[N]` points at a source that does not support the sentence | gate 4 *specifics* (the specific must be in the cited source) + gate 7 *claims* (a verbatim quote from the cited source) | **strong for specifics, weak for qualitative claims** | exists, with the gap in the next row |
| **delete claim** (201) | a claim with no source at all | gate 7 *claims*: every claim-check task must be answered and `supported` | **medium** — a claim with no specific and no quote can pass | **open gap** |
| **replace claim** (381) | the claim is true but overstated relative to the source | **no gate** — nothing checks the *degree* of a claim, only whether its specifics appear | **none** | **open gap** |
| **unreadable sources** (155 assertions) | a claim resting on a source whose text cannot be read | the brief says a `missing` or unreachable `tdm_reserved` source cannot carry a claim alone — **advice, not a gate** | **none** | **open gap** |
| **no model stamp** | a paper without provenance | the bundle requires `writer` (`model`, `tool`, `research_model`, `human_review`) | **strong** | **already in the studio chain** |
| **image fit** | an image that does not show what the paragraph claims | the studio `image-check` (VLM verdict `meaningful` / `weak`) | **unknown — the verdict is model-written** | **not addressed by this plan** |

### The honest reading

- **784 fixes across 22 papers, and three of the five fix classes (the 30 numbers, the 17 dates and the\n  155 reattributions of a specific) are structurally prevented for new papers**, because gates 4, 5
  and 7 already exist in the studio chain. The 31 live papers never had them: they were written by
  the retired V1 pipeline, which is exactly why they needed a correction round.
- **Two classes are genuinely open, and they are the two largest**: an overstated claim (no gate checks\n  degree, 381 fixes) and a claim
  resting on an unreadable source (advice in the brief, nothing in code). Both are cheap to close
  and neither is in the plan yet.
- **The image fit class is not addressed at all.** The section round-robin changes *which paragraph
  gets an image first*, not *whether the image belongs there*. A wrong image would still need a
  second correction round, and this plan makes no claim to prevent it.
- **The claim verdicts are model-written.** The studio's claim check is an agent run, and the stored
  evidence quotes are machine-checked against the archived text — that part is real. But a verdict
  *about* whether the quote supports the sentence is not machine-checked, and the owner's own rule
  says a check without an independently written verdict **holds**. The first paper of the new chain
  is therefore the only real test of this class.

## 3. What would close the open gaps

Two small, well-scoped additions, both in the studio chain, neither touching the legacy papers:

1. **A degree check.** The claim check already writes a verdict and a quote per claim. What it does
   not do is compare the claim's *strength* to the quote. A rule that a claim may not be stronger
   than its quote — no added quantifier, no added causal claim, no "proves" where the source says
   "suggests" — turns `replace claim` (20 of the 75 fixes) into a check.
2. **An unreadable-source rule.** A claim whose only cited source has `text_status` in
   `{missing, tdm_reserved}` fails the claims gate instead of being advice in the brief. This turns
   the 155 unverifiable assertions into a publication blocker rather than a footnote.

Neither is written. They are the honest gap between "the correction campaign is running" and "the
next campaign has less to do".

## 4. Correction of the baseline in plan A

The acceptance script disagreed with plan A and **plan A was wrong.** Both of its per-section
figures dropped the first content section of every paper, because the heading walk treated the first
`##` as the title even though the title is the `#` line:

| Figure | Plan A (wrong) | Verified now |
|---|---|---|
| content sections | 189 | **220** (per paper 5 / 7 / 8) |
| sections without an image | 109 (58 %) | **123 of 220 (56 %)** |
| sections with ≥1 image | 80 | **97** |
| sections with ≥4 images | 37 | **45** |
| images missing for 1 per section | 140 | **123** |
| images missing for 4 per section | 649 | **598** |
| fixed tail sections empty | 76 of 93 (82 %) | **76 of 93 (82 %)** — unchanged |
| gallery markers | 52 | **235 in the stored reports**; 52 was the count in the served HTML of one page |
| reference lines without a URL | 83, framed as unverifiable | **83 without an URL, but 0 without a URL *or* a DOI** — they resolve |

The conclusion is unchanged — the majority of sections carry no image and the fixed tail is the
worst place at 82 % — but the absolute numbers were off by one section per paper, and the source
finding was overstated: the 83 lines resolve through their DOI, so G5's only real failure is the
**3** lines carrying raw HTML.

**How it was caught:** `scripts/theo_paper_acceptance.py` measures with the same functions the gates
use and was run against the same export the baseline came from. Two independent counts that
disagree is a signal to recount, not to average. The recount is `C:\tmp\theo_opt\recount_baseline.py`.
