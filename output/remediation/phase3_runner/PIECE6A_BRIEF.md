# Piece 6a — the reviewer stage: what it is, and what would make it worthless

Written 2026-09-21, before the code, because the pilot's numbers say this stage is where the
pipeline's precision is decided.

## Why this piece exists

The discover pass is deliberately **finder-only**: one call per `(site, field)`, asking "is the stored
value wrong, given only the evidence in this message?" That means the finder's precision *is* the
pipeline's precision, and the census measured the finder's blind spot at a false-negative rate of
**60 %** (24 of 40 errors found by a blinded check were not flagged). The answer to a finder that
misses things is not a better finder — it is a second, differently-asked question.

The pilot had it: of the first-stage claims the reviewer looked at, **61 % were refuted**. The
reviewer is not a confirmation step; it is the reason a finding is worth writing.

`REVIEWER_BRIEF.md` (229 lines, ratified 2026-09-21) already fixes the semantics. `model_stage.py`
already carries `Stage.REVIEWER` and

    REVIEWER_QUESTION = "Can the finder's finding for this site be refuted against the evidence in
    this message? Name the single claim that fails, or say that none did. Try to break every finding."

What does not exist is the wiring that asks it. That is this piece.

## What already exists — do not rebuild it

* `discover_stage.parse_answer` (the `VERDICT:` / `PROPOSED:` / `SOURCE:` / `EVIDENCE:` block),
  `normalise_quote`, `quote_occurs`, `pages_from_excerpts`, `source_problems`, `MAX_SOURCES = 3`.
  A reviewer's refutation that cites a URL must be checked by **the same machinery** as the finder's
  citation: an invented source is the same defect in both roles, and round 6 measured exactly that
  (`citation_problems: 0` over 75 calls) because the checker exists.
* `run._judge_discover` **refuses** `--stage reviewer` for a discover batch, and the refusal is right
  about the plan: the plan carries no finder's finding to refute. It stops being right the moment the
  finder has answered — so the refusal becomes a **condition**, not an error: `--stage reviewer`
  requires `answers/` to exist for the batch and refuses when it does not, naming that reason.
* `model_stage.prepare_call(..., stage=...)` already builds the prompt per stage, including which
  question goes in it.

## The contract (from `REVIEWER_BRIEF.md`; its decisions override anything else)

* One verdict per finding: `refuted: true|false`, or `true_but_no_correction`, or `unresolved`.
  `true_but_no_correction` and `unresolved` are **valid answers**, not failures.
* A **required boolean `defect`** sits next to `proposal` in both roles. `defect: true` means: this
  row holds a value that is known to be wrong and must never be re-proposed as clean. Such a finding
  stays `proposal: review` with `proposed_value: null`, and it must **not** be refuted with "there is
  no replacement value" — that is the answer the rule exists to forbid.
* **Only `refuted = false` is ever applied** (plan Phase 3, verbatim), with a conditional `WHERE`
  clause and a journal entry.
* The eight overlap sites' `country` values are **already written** by the mechanical lane (run stamp
  `2026-09-21_mechanical-country`, journal 5 473). A stale flag there is **already fixed**: never a
  second write. One row, one writer.
* The reviewer refutes; it does not write, and it does not invent. Refuting from the evidence in the
  message is what it can prove; a refutation whose quote does not occur on the cited page is recorded
  as a problem and is **not** a candidate for the writer.

## The answer the model must produce, once per finding

    REFUTED: yes | no | unresolved
    WHY: <one sentence naming the single claim that fails, or that none did>
    REFUTATION_SOURCE: <a URL already present in this message>   (only with yes)
    QUOTE: "<a sentence that appears on that page>"              (only with yes)

`no` means "I tried and could not break it" — the only verdict the writer may act on. `unresolved` is
honest when the evidence does not settle it, and it is cheaper than a guess because the writer will
simply not apply it.

## Scope: review what proposes a change, not everything

Only findings that propose a change are reviewed. A finding that says "the stored value is correct"
has nothing the writer can apply, so reviewing it buys nothing at the price of a full call. This is a
scope decision, and it is stated rather than implied: **clean verdicts are not reviewed**, so the
reviewer's job is precisely "may this proposed change be applied?".

## What would make this piece worthless, and how it is measured

A rubber-stamp reviewer — one that refutes nothing — is a second opinion that agrees with the first,
and it would cost the same as the finder while adding nothing. It must be measured before the writer
consumes a single verdict, and the fixture for that exists:

* `runs/gold6/` holds the round-6 finder answers: 13 findings that propose a value, 13 with a source,
  14 with a quote, `citation_problems: 0`.
* `output/remediation/gold_standard/truth_fields.json` holds the true values for the same 17 sites.

So the measurement is cheap (~$0.01) and decisive:

* **Sensitivity**: of the proposals whose value is *wrong* against the truth set, how many does the
  reviewer refute?
* **Specificity**: of the proposals whose value is *right*, how many does it wrongly refute?
* Plus the citation check: how many refutations cite a quote that occurs on the cited page?

Both numbers get reported, neither alone. A reviewer that refutes everything scores perfect
sensitivity and would throw the corrections away; one that refutes nothing scores perfect specificity
and has done no work. The pilot's 61 % is the shape to expect — and if this implementation cannot
reach that band on the fixture, it is broken, not "conservative".

## Deliverable

* `review_stage.py`: `ReviewAnswer` (parsed), `parse_review`, `review_findings(...)` per batch,
  `write_report(...)` → `verdicts.json`, `source_problems` reused for refutation citations.
* `run.py judge --stage reviewer` wired to it, with the condition above.
* Tests for every guard, each with its own mutation (the sweep already has the harness).
* A measurement report, in this directory, with the fixture's numbers and the cost per call.
