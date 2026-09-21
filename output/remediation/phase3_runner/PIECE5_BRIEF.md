# Piece 5 — the discover pass: judge a site that no census check flagged

**Status:** brief, not yet built. Supersedes nothing; extends pieces 1–4.
**Written:** 2026-09-21 by the supervisor, from measurements recorded in `AUDIT_LOG.md`.

## 1. Why this piece exists — measured, not argued

Pieces 1–4 built a runner that judges the sites the **census** already suspected. That is not the same
set as the sites that are **wrong**, and the difference is now measured:

| measurement | value | source |
| --- | --- | --- |
| Blinded human-style check found errors the census had not flagged (FNR) | **60.0 %** (24 of 40), CP [43.3 %, 75.1 %] | `gold_standard/fnr_result.json` |
| Distinct sites holding those missed errors | **17** | same, `missed_errors` |
| … of those, present in `WORKLIST.jsonl` | **4** (3 with `phase3: true`) | `phase3_worklist/WORKLIST.jsonl` |
| Blind-examined sites **outside** the planned 1,813 | **25 of 36 (69 %)** | same |
| Error classes the deterministic census covers | **~18 of 54** | plan §12, Phase 1 |

The census ran over all 5,004 sites (`run_t01/census.jsonl` … `run_t11/census.jsonl`, 5,004 rows
each) and its acceptance criterion was met. A site absent from `WORKLIST.jsonl` is therefore not an
unexamined site — it is a site the census examined and **declared clean**, wrongly, in 60 % of the
error cases the blinded check could see.

The consequence for the owner's decision: **the 1,813-site worklist cannot reach these sites.** Widening
the worklist does not help either, because the worklist is built from census *findings* and these sites
have none. A site must be judged on its own text, with no finding to point at it.

## 2. Inputs — all local, all verified

`output/remediation/snapshot/` (`MANIFEST.txt`: exported 2026-09-20T20:20:01+02:00 from the VPS):

| file | rows | what this piece needs from it |
| --- | --- | --- |
| `unified_sites.jsonl.gz` | **5,004** | `id`, `name`, `description`, `site_type`, `country`, `period_start`, `period_end`, `period_name`, `lat`, `lon`, `raw_data` |
| `card_stats.jsonl.gz` | **5,004** | `card_description`, and a `wikidata_qid` column that is **NULL in all 5,004 rows** — see the correction in §3 |
| `site_external_ids.jsonl.gz` | 9,237 | external identifiers where present |
| `wiki_images.jsonl.gz` | 49,691 | **not used here** (images are Phase 2 / G0) |

Plus `run_t*/census.jsonl` (per-test verdicts for all 5,004) and `WORKLIST.jsonl` (the findings, where
they exist). **No database read is required and none is permitted** — this piece runs offline from the
snapshot, exactly like the census.

## 3. Deliverable

1. **`plan --from-snapshot [--site-ids PATH]`** — a deterministic plan over **all 5,004** sites (or an
   explicit site-id list, which is how the recall experiment in §6 is driven). Same `PLAN.jsonl` shape
   as piece 1 (`{"batch_id", "ordinal", "sites"}`), same batches of 15, same byte-identical re-runs.
2. **A site-level question** for sites with no finding: "here are this site's stored values and the
   evidence for them — is each value right?" — the shape the pilot already proved in
   `phase3_pilot/PILOT.jsonl`, which is one record per **(site, field)** with `current_value`,
   `outcome` (`CORRECT` / `WRONG` / `UNVERIFIABLE`), `evidence`, `reviewer`.
3. **Routing for a site-level question**: evidence per field, from the existing `fetch_stage` routers —
   `description` / `period_start` / `site_type` / `country` / `card_description` → enwiki by name, and
   Wikidata by the site's Q-id, read from **`site_external_ids` (`kind='wikidata_qid'`, 4,618 rows)**.
   No raw geometry; the named-feature rule and the 61,440-byte per-page cap are unchanged.

   **Corrected 2026-09-21, from measurement.** This brief first said "Wikidata by `wikidata_qid` where
   `card_stats` carries one". `card_stats.wikidata_qid` is present in all 5,004 exported rows and
   **NULL in every one**: nothing in the repository writes it, the column is created only by
   `api/main.py:126` (`ADD COLUMN IF NOT EXISTS`), and the only writer of a Q-id is
   `pipeline/lyra/prospector/external_ids.py:55`, into `site_external_ids`. Following this brief
   literally would have routed **no site at all** to Wikidata — the failure would have looked like a
   quiet drop in evidence, not like an error. The implementing lane found it, deviated with the
   evidence, and the brief now says what the data says. The lesson is the one this workstream keeps
   relearning: name the artefact, not the field you remember.

## 4. Constraints (these are the contract, not preferences)

* **Never invent data.** A field with no evidence gets `UNVERIFIABLE` and says so. A missing value stays
  missing. `EvidenceUnusable` must still raise for the case it was written for.
* **A single site must never end a batch.** This is the lesson of piece 4 applied to the new failure
  mode: a Wikipedia article large enough to overflow the evidence bound (32,000 chars) must become that
  **site's recorded outcome**, with its reason, while the other 14 sites in the batch are judged
  normally. Decide explicitly whether that outcome is `UNVERIFIABLE` (my ruling: yes — "the evidence was
  too large to judge" is a fact about the evidence, and it is honest) and test it.
* **The finding shape stays the same** (`field`, `test_id`, `current_value`, `proposal`, `severity`,
  `dimension`, `note`, …), with `test_id = "P3/<field>"` for discover findings, so pieces 1–4 and the
  existing consumers keep working.
* **No writes, ever.** This piece produces findings; the writer is a separate, guarded step.
* **Determinism**: two runs from the same snapshot are byte-identical (piece 1's standard), and the
  plan's hash is recorded.

## 5. One open decision, to be made with a reason and a test

**One call per (site, field) or one call per site?** The pilot used per-field. Per-site is about a
fifth of the calls and therefore of the fixed ~437-token per-call overhead, but it concentrates all of
a site's evidence into one prompt and one refusal. Whichever is chosen, the choice and its measured
consequence (calls, tokens, cost, refusal count) go in the report. Do not choose by taste: state the
number that decided it.

## 6. The acceptance test this piece must make possible

`fnr_result.json` records, for each of the 24 missed errors, the **site, the field and the correct
value**. Once the plan can be driven by an explicit site-id list, this experiment runs:

```text
plan --from-snapshot --site-ids <the 17 truth-set ids>   →  prepare → fetch --live → judge --live
```

**recall = how many of the 24 known-wrong fields the finder actually flags.** That number decides
whether this design can do the job at all. If it cannot catch known truths, scope is moot and the
prompt is what needs work — which is the point of spending ~$0.05 before spending $10.

Report it as: caught / 24, by field, with the misses listed by name. A design that "looks audited" is
exactly the failure this number exists to prevent.

## 7. Non-goals

* Images, heroes, galleries (`image_kind`, G0) - separate, already done.
* Rewriting text. This piece proposes; a later, guarded step writes.
* The 285 coords-only sites and the 117 T02 sites - those are human calls by
  `docs/procedures/FIELD_CONTRACT.md` §4 item 6.

## 8. Addendum, 2026-09-21 - the numbers that settle §5, and the fixture §6 needs

**The fixture exists now.** The recall experiment's inputs are committed:

* `output/remediation/gold_standard/truth_sites.txt` - the 17 truth-set site ids, one per line, ready
  for `--site-ids`. All 17 are present in `unified_sites.jsonl.gz` (checked, 0 absent).
* `output/remediation/gold_standard/truth_fields.json` - the 24 entries to score against, each with
  `site_id`, `field`, `stored_value`, **`stored_in`** (the table the value really lives in) and
  `correct_value`.

Read `stored_in` rather than assuming a table. Building this fixture produced exactly the mistake to
avoid: reading `stored_value` from `unified_sites` alone made all five `card_description` entries look
absent, when that column lives in `card_stats` and every one of them has real text. One entry's field
(`scope`) has no column at all - 3 of the 24 are missing values, not wrong ones, and a finder that can
only spot wrong values will miss them.

**What the finder already measures per call**, so §5 is decided on numbers rather than taste: a live
call cost **$0.000486** (provider-reported), mean 2,895 input tokens, and the fixed per-call overhead is
about **437 input tokens ≈ $0.000066**. So all 5,004 sites as one call each is about **$2.43 per
stage**, and five calls per site (one per text field) about **$12.2 per stage**. The evidence fetch is
identical either way, because the evidence store is keyed by (site, feature) and is written once.

Money therefore does not decide it. Two things do: the project's own principle, already written into
`model_stage.py`, that **one question per call is the point** (`FINDER_QUESTION` and `REVIEWER_QUESTION`
are one each), and the pilot's own precedent - `PILOT.jsonl` is one record per **(site, field)**, not
one per site. So: **one call per (site, field)**, with that field's own question. Record the measured
call count, tokens and cost either way.

**One measured constraint to inherit.** `overpass-api.de` is unreachable from this workstation (TLS
reset in 0.077 s; the VPS reaches it in 0.35 s) and piece 4b now records its targets as *not attempted*
instead of retrying them. The discover pass asks about text fields, so this should not bite - but if a
field's routing touches Overpass, the run must record it as not attempted and carry on, never end the
batch. Coordinates are a human call by contract in any case.

**How recall is scored:** for each of the 24 entries, did the finder flag **that field on that site**?
Report caught/24, by field, with the misses named. `batch-0001` and the truth set do not intersect, so
this is the first time the finder's recall is measured at all - and if it is poor, the prompt is what
needs work, not the scope.
