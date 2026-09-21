# Piece 5c - the question's second and third repair, and where the tuning stops

`PIECE5_BRIEF.md` specified the discover pass; `PIECE5B.md` recorded the first measurement and the
three information defects the second round exposed. This is the record of rounds 3, 4 and 5: the
boundary defect the question itself contained, the century-convention defect the answers exposed, and
the decision to stop.

## The measurement, five rounds on one fixture

19 reachable entries of the 24 known errors (`truth_sites.txt`, `truth_fields.json`); one model
(`opencode-go/deepseek-v4.1-flash`, thinking off); plan sha256
`ad32d26fccb3913b2656d70df5485f9185bbe956a343f4476668e6e00dcbb9c0` for every round; the 33 fetched
evidence files byte-identical across all five rounds (0 differing bytes), so the question is the only
variable.

| round | what changed | caught / 19 | WRONG | CORRECT | UNVERIFIABLE | cost | run dir |
|---|---|---|---|---|---|---|---|
| 1 | first live question | 5 (26.3 %) | 12 | 47 | 16 | $0.054226 | `runs/gold` |
| 2 | silence is not agreement; evidence before verdict | 8 (42.1 %) | 25 | 23 | 27 | $0.056514 | `runs/gold2` |
| 3 | clause precedence; `site_type` vocabulary; bucket spans | 7 (36.8 %) | 17 | 29 | 29 | $0.058108 | `runs/gold3` |
| 4 | spans stated inclusive-first / exclusive-second | 5 (26.3 %) | 13 | 32 | 30 | $0.058388 | `runs/gold4` |
| 5 | century-to-signed-year convention | 7 (36.8 %) | 15 | 33 | 27 | $0.058558 | `runs/gold5` |

Costs are read from each run's frozen `model.json` (75 calls each), never from `LEDGER.jsonl`, which
a live run appends to.

**Recall is noise here.** 5, 8, 7, 5, 7 with one model and 19 entries. Round 4 lost `The Gop/
period_start` and round 5 lost `Beacon Hill/card_description` although the clauses covering those
fields did not change; round 5 regained `Hebbariyeh Roman Temple/site_type` although the `site_type`
clause was untouched between rounds 4 and 5. What moves reliably is the flag count: `WRONG` went
12 -> 25 -> 17 -> 13 -> 15, and the eight `country`/`site_type` false positives of round 2 are gone.

## Defect 2: the question stated bucket boundaries the code does not have

Round 3's `period_start` clause read `-3000 to -1500 is 3000 - 1500 BC; -1500 to -500 is 1500 - 500 BC;
-500 to 1 is 500 BC - 1 AD`. `categorizePeriod` (`ancient-nerds-map/src/data/sites.ts:58-70`) compares
with `<`, so `-1500` belongs to `1500 - 500 BC` and `-500` to `500 BC - 1 AD` - both one bucket later
than the clause said. Four round-3 flags sat on exactly those values, and one answer states the cause:
*"Stored value -1500 falls in the span `3000 - 1500 BC` (upper bound inclusive, i.e. -3000 to -1500)"*.

Repair: every span stated as inclusive of its first year and exclusive of its second, plus the two
named boundaries a reader gets wrong. The guard **derives** the spans from `sites.ts`
(`_categorize_period_steps`) instead of restating them, so the question cannot drift from the code
again. Measured effect: 2 of the 4 flags disappeared.

I predicted the repair "cannot lose a catch" because it only un-flags pairs the code puts in one
bucket. Round 4 refuted that: a clause that insists on numeric spans makes a model refuse to bucket an
era name (*"The evidence states the site is a Neolithic monument but gives no numeric year ... on this
field it is silent"*). The arithmetic was sound; the behaviour was not predictable from it.

## Defect 3: the century convention

Rounds 3 and 4 each carried two flags where the model placed `"2nd century BCE"` / `"4th century BC"`
in `1500 - 500 BC`; both centuries are inside `500 BC - 1 AD`, since -200 and -400 are greater than
-500. This is arithmetic convention rather than subject knowledge, so the clause supplies it as it
supplies the spans, and the test checks the sentence against `categorizePeriod` for every year it
covers rather than checking that the words occur.

Measured effect: one of the two targeted flags disappeared. The other (`Bulls of Guisando/
period_start`) remains despite the fact now being stated in the clause - a model arithmetic failure
with the correct fact in front of it.

## The mutation record

`scripts/remediation/phase3/mutation_sweep.py`, run from outside any lane (a sweep interrupted inside
a lane leaves a mutant in the tree - it happened twice). 26 mutations, 26 caught, every restore
byte-identical; the anchored texts are `PRECEDENCE`, `VOCAB`, `VOCAB_REFUSAL`, `SPANS` plus the
round-5 century sentence.

```
./.venv/Scripts/python.exe scripts/remediation/phase3/mutation_sweep.py
26/26 mutations caught; missed: []
```

The sweep's own log is gitignored; this table and the invariant are what is versioned.

## The freeze

Frozen at round 5's wording, for three measured reasons: the catch count is noise at n=19; the
question no longer asserts anything false; and the residual false flags (century arithmetic, "the
stored claim is unsupported / too general / a legend") are the evidence-only rubric working as
designed - softening it would trade an inspected false-alarm rate for an unknown one.

Delivered numbers for the mass-run decision:

* recall **7/19**, consistent with a band of 5-8 over these five rounds;
* **8 of 15 flags lie outside the fixture**; adjudicated by hand they are 2 real errors the fixture
  does not list (`The Merry Maidens/card_description`: stored 4.6 m against the evidence's 3 m;
  `Ksar el Barka/card_description`: "founded in 1690 by the Kounta"), 1-2 century arithmetic, and the
  rest rubric calls;
* **$0.000781 per call**, so the discover stage over all 5,004 sites is 25,020 calls ≈ **$19.5**;
* the binding constraint stays wall-clock (~211 h as measured earlier), not money.

## Reproducing any round

```bash
bash output/remediation/logs/gold5_run.sh                       # plan, prepare, fetch, judge (live)
./.venv/Scripts/python.exe output/remediation/gold_standard/score_recall.py \
    output/remediation/phase3_runner/runs/gold5                 # -> recall_result_gold5.json
./.venv/Scripts/python.exe output/remediation/gold_standard/list_other_flags.py \
    output/remediation/phase3_runner/runs/gold5                 # the flags outside the fixture
```

`list_other_flags.py` shares `score_recall.py`'s verdict rule on purpose: the first version required
the verdict at the start of a line and under-counted round 2 as 21 `WRONG` against the scorer's 25,
because five answers write it inline (`2. VERDICT: UNVERIFIABLE`). Two instruments disagreeing about
the same artefacts was the finding.
