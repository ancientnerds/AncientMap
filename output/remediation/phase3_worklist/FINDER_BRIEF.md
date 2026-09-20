# Phase 3 — Stage 1 FINDER brief

You are the finder in a two-stage factual audit of curated archaeological sites
(`unified_sites`, `source_id = 'ancient_nerds'`, production Postgres, **read-only**).
The deterministic census already ran; it could not settle your sites. You propose; you do
not write.

## Your batch

* 5 sites, given as `(site_id, name, current field values, the census finding(s) that
  flagged them)`.
* The census finding tells you *what* is suspect and *why*; it is a lead, not a verdict.
* Your job: decide, per field, whether the stored value is wrong, and if so what the
  correct value is — **with evidence**.

## Method (plan §Phase 3, Stage 1)

1. For every field under review — `name`, `country`, `lat/lon`, `period_start`,
   `period_name`, `site_type`, `description`, `card_description` — check the stored value
   against **at least two independent sources**. Wikipedia, Wikidata, the site's own
   official page, an ICOMOS/UNESCO listing, a peer-reviewed source. Distinct hosts; two
   pages on one host is one source.
2. Record the evidence as `{source, url, quote, retrieved_at}`. The `quote` is what makes
   the claim reviewable later: paste the exact sentence or claim-value, never a paraphrase.
3. Give each finding a `severity` (`severe` = read aloud wrong / moves pin, scope or title;
   `moderate` = visibly wrong on an indexed page; `cosmetic` = real but invisible), a
   `proposal` (`set` with a `proposed_value`, `clear` to blank it, `review` if a human must
   decide — never `set` without a value), and a `confidence`.
4. **You may not claim a correction with one source.** One authoritative source
   (Wikidata `P625`, an official national register) is enough to mark `authoritative`;
   everything else needs two.

## Briefed false-alarm patterns (plan §4.3) — do NOT report these as errors

1. **Bucket-boundary `period_start`.** 75 % of sites sit on a bucket lower bound
   (−4500/−3000/−1500/−500/1/500/1000/1500). A round value alone is not an error. Report it
   only when the real dating belongs in a **different bucket**.
2. **`England` / `Scotland` / `Wales` instead of `United Kingdom`** is deliberate project
   design. Not an error.
3. **`Archaeological Site of Olympia`** and similar are the official UNESCO title, not
   prefix clutter (34 sites carry this form).
4. **`civilization`** is a copy of `country`, not a cultural attribution. Never an error.
5. **Never downgrade specificity.** If Wikidata `P31` says “archaeological site” and the DB
   says “Temple”, it stays “Temple”.
6. **Same name, different site.** Before any verdict, confirm name **and** coordinate refer
   to the same place.

## What a finding looks like

Same schema as the census (`scripts/remediation/census/model.py::Finding`):

```json
{"site_id": "...", "test_id": "P3/<field>", "field": "period_start",
 "severity": "severe", "dimension": "period",
 "current_value": 1, "proposed_value": -2000, "proposal": "set",
 "confidence": "two_source",
 "evidence": [{"source":"...","url":"...","quote":"...","retrieved_at":"..."}, {...}],
 "note": "why the sources decide it"}
```

## Hard rules

* **No claim without evidence.** No file:line or URL+quote → it is not a finding.
* **Never invent data.** If a value cannot be decided from evidence, the honest output is
  `confidence: "unverifiable"` / `proposal: "review"`, never a plausible guess. A wrong
  value is worse than an empty one.
* **Never swallow an error.** “Could not check” (dead source, 403, ambiguous) is recorded
  as such. It must never become “checked and clean”.
* **An empty field beats a wrong one** — `proposal: "clear"` is allowed and normal.
* **You do not write to the database.** Your findings go to the reviewer.
