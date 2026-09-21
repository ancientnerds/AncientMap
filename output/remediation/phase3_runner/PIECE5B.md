# Piece 5b - the three information defects the second recall run exposed

Follow-up to `PIECE5.md`. The second live recall run (`runs/gold2`, 2026-09-21) took the discover
pass from **5 of 19** known-wrong fields to **8 of 19** (`$0.056514`, 75 calls) and raised 17 `WRONG`
verdicts that are **not** in the gold standard. Reading those 17 answers - not counting them -
separated three defects from the model's own errors. All three were mine, and all three were missing
*information* rather than prompt polish: the question did not carry what it needed to be answerable.

## 1. The prompt contradicted itself

The rewrite of `42fb917` said `Only the evidence in this message decides`, and the model then flagged
`England` as `WRONG` because the evidence wrote `United Kingdom` - **citing the clause that allows
exactly that and overriding it in the same sentence**:

> "under the allowed design England is acceptable, yet ... so the stored value differs"

An absolute-sounding rule demoted the per-field clause to a subordinate paragraph. The clause now says
in as many words that it defines what `matches` means for its field and beats the general rules.
False positives of this class in `runs/gold2`: 4 (`Midford Castle`, `Aubrey Holes`, `Overstone`,
`Amyntas` - all `country`).

## 2. `site_type` was judged without the catalogue's vocabulary

All four `site_type` flags were wrong, each by reading the evidence's own phrase as if it were the
target value: "triumphal arch" against `Gate/archway/bridge`, "folly castle" against `Castle/palace`,
"hill fort" against `Fortress/citadel`, "ahu" against `Megalithic statues`. One answer states the doubt
itself:

> "if the catalogue's grouping places 'triumphal arch' under a 'Gate/archway/bridge' class, the
> stored value would instead be CORRECT"

The catalogue uses **70** distinct `site_type` values, and the question never named one of them. It now
carries the list, read from the same snapshot the plan was built from
(`snapshot_plan.site_type_vocabulary`, sorted, deduplicated, refusing an empty result), and refuses to
build the question without it - a question that asks which catalogue value the evidence describes,
while listing none, cannot be answered, and the failure would read as a thinner answer rather than an
error.

## 3. `period_start` gave lower bounds instead of spans

`Bulls of Guisando` was flagged on arithmetic the model got wrong **after** its own verdict:

> "Wait - both -200/-100 and -500 fall in the same bucket... Let me correct."

-500 and -200 are both `500 BC - 1 AD`, so the flag was false. The spans are now read off the site's
own `categorizePeriod` (`ancient-nerds-map/src/data/sites.ts:60-70`), not derived: 4500-3000 BC is
-4500..-3001, and so on, with the two values' spans named before they are compared.

## What changed in the judge path

`judge` reads the catalogue's value list from the snapshot the plan was built from
(`run.py:_judge_discover`). The snapshot is therefore needed at judge time as well as at plan time -
the same artefact the plan is already a function of.

## Guards, and their proof

Five tests, and the mutation sweep grew **20 -> 24**, all 24 caught, every restore byte-identical:

| mutation | caught by |
|---|---|
| the clause no longer beats the general rules | `test_the_field_clause_is_stated_to_beat_the_general_rules` |
| the `site_type` question stops naming the value list | `test_the_site_type_question_carries_the_catalogues_own_value_list` |
| an empty value list is accepted instead of refused | `test_the_site_type_question_refuses_to_be_built_without_the_value_list` |
| the period question goes back to lower bounds without the spans | `test_the_period_question_gives_the_bucket_spans_and_not_only_lower_bounds` |

Restored hashes after the sweep: `discover_stage.py 5fda7bd260a015ab`,
`snapshot_plan.py 983b5ea8e8c42798`,
`model_stage.py 2810315bc048a1ef`,
`fetch_stage.py 880e49d57eb13855`,
`run.py 1f51e01aa3f75d21`.
Sweep log: `output/remediation/logs/phase3_mutations/sweep_after_question_rewrite.txt` (gitignored;
this table is the versioned record).

## A defect this exposed in the suite itself

The tests that read the production snapshot read an artefact that is **not in the repository**
(`.gitignore:216`), so a CI checkout never has it and those tests would fail there. They are now
skipped with a reason when it is absent - the shape `test_t11.py:56` and `test_gallery_audit.py:169`
already use. Proved by hiding the artefact rather than by assuming: **31 passed, 7 skipped, 0 failed**,
with the snapshot restored byte-identically (7 files). The two tests that only need the catalogue's
value list pin it instead of reading it, so they stay hermetic and can still catch a mutation in CI.

## Not established here

Whether the three fixes **move the number**. That is the third recall run (`runs/gold3`), same plan,
same fixture, same question otherwise - the only change is the information the question carries.
