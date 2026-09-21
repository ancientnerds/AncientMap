# Piece 6a: the reviewer

The finder asks "is this value wrong". The reviewer asks **"can this finding be refuted"** - a
different question about the same evidence, which is the only kind of second pass that can add
anything. A second pass with the same question would answer itself.

Delivered in the same tree, in three parts.

| part | file | state |
|---|---|---|
| the reviewer stage | `scripts/remediation/phase3/review_stage.py` (new) | written |
| the shared citation check | `scripts/remediation/phase3/discover_stage.py` (`claim_problems`) | split out of `source_problems` |
| the routing | `scripts/remediation/phase3/run.py` (`_judge_discover`, `_has_answers`, `_judge_discover_reviewer`) | refusal became a condition |
| the tests | `tests/remediation/test_phase3_review.py` (20), `tests/remediation/test_phase3_discover.py` (rewritten) | `72 passed` together |
| the mutations | `scripts/remediation/phase3/mutation_sweep.py` | 69, all caught |

## The four decisions that keep the pass from being decorative

1. **Only a complete `WRONG` finding that proposes a change is reviewed.** `CORRECT` and
   `UNVERIFIABLE` propose nothing, so there is no claim to refute. They are written into the report as
   `unreviewable` **with the finder's own reason** - "nothing to review" and "not reviewed yet" must
   not look alike in a receipt.
2. **`UNRESOLVED` is a third state.** `if refuted:` would collapse "I could not settle this" into "not
   refuted", and only `refuted is False` may be applied. The identity comparisons are load-bearing,
   and the suite pins all three states.
3. **The citation check is the finder's own code.** `discover_stage.source_problems` now delegates to
   `claim_problems(sources, pages)`, which the reviewer calls for its own refutations. An invented
   citation is the same defect in both roles; two spellings would have been two chances to drift.
4. **A refutation must cite a page this run fetched**, checked against the same excerpt set the finder
   saw. "The page says otherwise" cannot be a claim about a page nobody opened.

## What the tests caught before anything else could

* **Dead code of mine.** An edit nested `if refuted is not True and sources:` *inside* the
  `if refuted is True and not sources:` block, so the rule "a source on a non-refutation is a problem"
  could never fire. The test failed; the block was dedented.
* **A fixture that invented its own evidence.** It cited `https://en.wikipedia.org/wiki/Cave`, a pretty
  URL the run never fetches. Honest citations are the API URLs the fetch bought, so the fixture now
  derives its URL from `F.targets_for_site(site).url`. A test that invents its evidence would have
  passed against a reviewer that invents its citations.

## The routing, and one unreachable refusal

`run._judge_discover` no longer refuses `--stage reviewer` outright. It refuses **when the batch
carries no finding**: `_has_answers` asks about the answers, not about the directory, because a killed
run leaves an empty `answers/` behind and a reviewer that trusted the directory would buy nothing and
write five empty verdicts - a receipt that says a review happened. The refusal names the empty
directory and the pass to run first.

The second refusal (`args.stage != Stage.FINDER.value`) is **unreachable through `R.main`**:
`--stage` is declared `choices=[s.value for s in Stage]` and `Stage` has exactly two members, so once
the reviewer branch returns, no other value can arrive. Its mutation was therefore **removed** rather
than "tested" with an invented test, and the `--stage` help text - which still claimed a discover
batch was finder-only - was corrected.

## A mutation that would have been caught for the wrong reason

A partial `edit` left `REVIEWER` assigned **twice**; the later, stale assignment named a test that had
just been deleted. pytest would have collected nothing, exited with a collection error, and the sweep
would have counted that as "caught". The pre-sweep check (every anchor unique, every named test
present, no no-op mutation, no duplicated constant) found it. That check first printed `Mutationen: 0 |
Probleme: 0` because it walked `ast.Assign` while the list is annotated (`AnnAssign`) - an empty loop
is not a clean result, so it now asserts a floor on what it read.

## Not yet measured

The reviewer's **sensitivity and specificity on the truth fixture** (`runs/gold6/` +
`truth_fields.json`) is the next measurement, ~$0.01. Until it is run, the reviewer's *quality* is
unproven; what is proven is that it does what its contract says, that its refutations go through the
finder's citation check, and that 69 mutations of its logic are all caught.
