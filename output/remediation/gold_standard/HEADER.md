# Gold standard — the false-negative rate of the 2026-09 remediation

**Run:** 2026-09-20/21 · **Plan served:** `docs/procedures/SITES_DB_REMEDIATION_2026-09.md`, Phase 0 row
*"Gold standard: 30-40 double-blind sites for the false-negative rate"* and the error-rate method in §4.
**Scope of this document:** an independent, blinded field-by-field verdict on a stratified sample of the
5,004 `ancient_nerds` sites, and the resulting false-negative rate of the machine census.

**Status: partial run.** 2 of 36 sampled sites were completed before the run was cut short; the
headline rate below is computed over the completed sites only and says so. The sample, the draw rule
and the per-site records are complete and reproducible; the remaining 34 sites are named in
§"Not measured" so the next run can pick them up exactly.

---

## 1. What is being measured

The census (Phase 1, ten deterministic checks) is the instrument that steers the expensive part of the
remediation. Nothing so far measures what **all ten checks together still miss**. That is the false
negative: an error that is really in the database but that no machine check flags. The estimate is

    FNR = (errors found by the blinded human-style check that the census did NOT flag)
        / (all errors found by the blinded check)

with the sample size and a Clopper-Pearson interval reported next to it. A false-negative rate of 0 %
on 10 found errors is not evidence that the census is perfect — it bounds the rate at ~26 % with 95 %
confidence. The interval is the honest part of the number and is printed with it.

## 2. Double-blind protocol (and the proof that it was kept)

Rule: **no census output was read until a site's verdicts were already on disk.**

- Forbidden until unblinding: `output/remediation/census.jsonl`, `output/remediation/findings.jsonl`,
  `output/remediation/CENSUS.md`, and every `output/remediation/run_*/` directory.
- The only inputs used while judging were (a) the local DB snapshot
  `output/remediation/snapshot/*.jsonl.gz`, which is the *data under test*, and (b) fresh web fetches.
- Every site's verdict is written to `gold_scratch/records/NN_*.json` and re-rendered into
  `GOLD_STANDARD.md` + `sites.json` **before** the next site is started, so the file mtimes are the
  evidence of the order. The unblinding step (§"The comparison") is a separate, later command whose
  output is appended by hand; the mtimes of `records/` versus the census read are listed there.

The snapshot is the data under test, not the machine's opinion about it: reading it cannot leak a
verdict. That distinction is what makes the blindness real rather than nominal.

## 3. Sample design

Frame, strata, allocation, seed and the exact selection rule: `output/remediation/gold_standard/DRAW.md`
(written before the draw, and before any census file was opened). Script:
`output/remediation/gold_scratch/draw_sample.py`, seed **20260920**, sample file
`output/remediation/gold_standard/sample.json`.

| tier | population | sampled | design weight N_h/n_h |
|---|---|---|---|
| 1 | 525 | 3 | 175.0 |
| 2 | 1,796 | 10 | 179.6 |
| 3 | 2,310 | 14 | 165.0 |
| 4 | 353 | 7 | 50.4 |
| 5 | 20 | 2 | 10.0 |
| total | 5,004 | 36 | — |

Tiers 4/5 are over-weighted to 9/36 = 25 % against a population share of 7.45 %, matching the pilot
(plan §2). The raw count is reported alongside an inverse-probability-weighted estimate
(weight `w_h = N_h/n_h`), because the pilot's unweighted 53 % figure is named in the plan itself as a
known weakness.

## 4. Field definitions — what "every field" means here

Per plan §1.3 (definition of clean), §6.1 (images) and §15.4 (blast radius), each sampled site is
judged on these fields:

| field | what makes it CORRECT | what makes it WRONG |
|---|---|---|
| `name` | the name a source uses for this site, without a Wikipedia disambiguator | a name that belongs to a different site, or a suffix that is not part of the name |
| `country` | the modern state the coordinates fall in | historical polity, compound value, non-country |
| `coordinates` | within the site's own extent as given by two sources | wrong site, wrong continent, off by more than the site's footprint |
| `period_start` | **bucket-correct**: the real dating falls in the bucket `period_start` names | the real dating belongs in a *different* bucket (plan 4.3.1 — a round value alone is not an error) |
| `period_name` | equals `categorize_period(period_start)` | inconsistent with `period_start` |
| `site_type` | a canonical type that is at least as specific as the sources' | a type the sources contradict, or a downgrade to "Ruin"/"Archaeological site" |
| `description` | every checkable claim is supported by a source | a claim contradicted by a source, or unsupported by the description's own citation |
| `card_description` | same rule (it is read aloud) | same rule |
| `civilization` | (by design a copy of `country`, plan 4.3.4) | never — not an audit target |
| `heritage_designation` | empty is allowed (plan 1.3); a wrong value is not | a value no source supports |
| hero + gallery images | metadata says the file depicts this site | a file whose Commons page is about a different site |
| `source_url` | resolves, and is about *this* site | dead, fragment-only where a dedicated article exists, or about another subject |
| `scope` | inside the E3 cutoff (Americas ≤ 1500 AD, rest of world ≤ 500 AD) | outside the cutoff and not flagged/hidden |

Verdicts are exactly three-valued: **CORRECT**, **WRONG** (with the correct value and its source), or
**UNVERIFIABLE** (with the reason). `UNVERIFIABLE` is a measurement, not a failure — it is one of the
things this instrument exists to count.

Two limits are stated up front rather than hidden:

1. **Images are judged from Commons metadata** (file page, categories, description, author, licence).
   This run has no vision tool, so "the bytes show a different site" cannot be decided here; only
   "the file's own documentation says it is a different site" can. That is weaker than the plan's VLM
   pass and is labelled as such in every image verdict.
2. **Two sources per claim is the target, not always the reality.** Where only one independent source
   exists (obscure sites with a single Wikipedia article), the verdict says so in its `sources` list
   rather than inventing a second one.

## 5. Per-site verdicts

Each site below carries: the database values, a verdict row per field with the source URL behind it,
and (after unblinding) the census comparison for that site's errors.
