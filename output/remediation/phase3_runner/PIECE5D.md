# Piece 5d - the answer contract: a correction, with a source the run itself can check

Martin's direction of 2026-09-21 changed the deliverable, not the plumbing: every site is to be
checked, the model must **correct** what is wrong rather than only report it, and each correction has
to carry **evidence and a source**. The delivered question said the opposite in so many words -
`Never guess a replacement value.` and `You propose; you do not write.` - so this is a change of the
design, measured like the earlier ones rather than asserted.

## The contract

A `WRONG` verdict now owes three things instead of one:

```
VERDICT: WRONG
PROPOSED: <the value this field should hold>
SOURCE: <a url from the evidence> - "<a sentence copied from that page>"
```

`CORRECT` and `UNVERIFIABLE` are unchanged. Up to three `SOURCE:` lines are allowed, so a value that
needs two pages can cite two. A real answer from round 6 (`The Gop` / `site_type`, stored
`Fortress/citadel`):

```
The evidence states the Aubrey holes are a "Neolithic monument" (Wikidata description) and subclass
of monument (P31 = Q188040), with no mention of a timber circle.

VERDICT: WRONG
PROPOSED: Monument
SOURCE: https://www.wikidata.org/w/api.php?action=wbgetentities&ids=Q4819208&... - "Neolithic monument"
```

## What is machine-checked, and where

The citation is not taken on trust. Five places decide, and each has a test that was proved to have
teeth by mutation:

| check | where | what it refuses |
|---|---|---|
| the question asks for it | `discover_stage.QUESTION_TEMPLATE` | a WRONG answer that carries no `PROPOSED` |
| the answer is parsed | `discover_stage.parse_answer` | an inline verdict (`2. VERDICT: UNVERIFIABLE`) read as missing |
| a source is required | `discover_stage.source_problems` | a `WRONG` verdict without a source |
| the page was fetched | `discover_stage.source_problems` | a url this run never fetched, however plausible |
| the quote is in the page | `discover_stage.quote_occurs` | a paraphrase, an invention, or a sentence from another page |
| the rate over a run | `gold_standard/verify_sources.py` | - reports quotable/citable per run |

`source_problems` is the one the writer will call: a finding that fails it is not writable.

## The trap that would have made this look like the model's fault

The evidence files for `enwiki` and `wikidata_entity` are the APIs' **JSON responses**, and
`model_stage.evidence_block:558` puts that text into the prompt verbatim. The page therefore carries
`\u00c1vila` and `\n` exactly where the model reads `Ávila` and a line break. Comparing a normally
transcribed quote against the raw bytes reports "does not occur" for a perfectly honest quote - the
metric would have measured JSON escaping while reading as a model that fabricates citations. Both
sides are unescaped, whitespace-folded and case-folded first; the words, their order, punctuation and
digits are still required. Mutation `the JSON escapes in the evidence are not undone` keeps that
honest.

## Round 6, measured (run dir `runs/gold6`, 2026-09-21)

Controlled as every round before it: the plan hashes to `ad32d26fccb3913b...`, all six stages exit 0
and are checked against their artefacts, and **33/33 evidence files are byte-identical to round 1**.

| | value |
|---|---|
| recall | **7 of 19 asked = 36.8 %** (of all 24: 7/24 = 29.2 %) |
| verdicts | CORRECT 31, WRONG 13, UNVERIFIABLE 31 |
| WRONG with a proposed value | **13 of 13** |
| WRONG with a source | **13 of 13** |
| quoted sentences | 14 |
| **citation problems** | **0** - every quote occurs in the page it cites |
| cost (frozen `model.json`) | 75 calls, 382,930 in / 7,439 out, **$0.061903** = **$0.000825/call** |

Two readings:

* Recall is unchanged inside the noise band the five earlier rounds established (5, 8, 7, 5, 7). The
  answer contract costs nothing in catches.
* The citation rate is **not** a noise band: 14 of 14 quotes verified against our own bytes. That was
  the risk worth measuring before 25,020 calls - a model that paraphrases would have made the whole
  design unusable at scale, and it does not.
* Cost rose from `$0.000781` to `$0.000825` per call because the answer is longer. The discover stage
  over all 5,004 sites (25,020 calls) therefore projects to **~$20.6**, against $19.5 before. The
  binding constraint stays wall clock.

Out-of-fixture flags fell from 8 (round 5) to 6, five of them `card_description`; `Ksar el Barka`'s
1690 founding and `The Merry Maidens`' 4.6 m were already adjudicated **real** in round 4.

## What this obliges the next piece to do

* The writer (piece 6) must call `source_problems` and refuse a finding that fails it. A finding whose
  source cannot be verified must not reach the journal.
* The mass run (piece 7) should record the citation rate per batch, because it is the one metric that
  says whether the running model is still the measured one. A batch with a citation rate near zero is
  a fleet-level signal, not 15 local mistakes.
* Nothing here lets the model **uphold** a stored value with its own knowledge; the evidence-only
  rubric is untouched.

## Reproducing

```bash
bash output/remediation/logs/gold6_run.sh                 # plan -> prepare -> fetch -> judge, live
./.venv/Scripts/python.exe output/remediation/gold_standard/verify_sources.py \
    output/remediation/phase3_runner/runs/gold6            # the citation check
./.venv/Scripts/python.exe scripts/remediation/phase3/mutation_sweep.py   # 31 mutations
./.venv/Scripts/python.exe -m pytest tests/remediation/test_phase3_discover.py -q   # 51 tests
```

The sweep log lives under the gitignored `output/remediation/logs/`, so the durable record of the
mutation run is this section: **31 of 31 mutations caught, `missed: []`**, with
`discover_stage.py` restored byte-identically (sha256 `cd2a3edb3eb104d28fc74455b56a0804b8074d046bf5db5fe4f97a7712b92033`).
