# Phase 3 — Stage 1 FINDER brief

You are the finder in a two-stage factual audit of curated archaeological sites
(`unified_sites`, `source_id = 'ancient_nerds'`, production Postgres, **read-only**).
The deterministic census already ran; it could not settle your sites. You propose; you do
not write.

## DECISIONS (ratified 2026-09-21)

Ratified from the five-site pilot (`../phase3_pilot/BRIEF_GAPS.md`, `PILOT.md`). They override
anything below that disagrees with them. Decisions, not options; every number is the pilot's
measurement (where re-verified here, the snapshot is named).

**1. The eight overlap sites are Phase 3's, and their country is already written.**
Satsurblia Cave, Didnauri, Armazi, Tsutskhvati Cave NM, Tsona Cave, Kutaisi, Dmanisi, Easter
Island. **What changed:** the mechanical lane has ALREADY written their country — all 35 rows
including these 8, run stamp `2026-09-21_mechanical-country`, journal 5,473 rows. So their
country is no longer a proposed write; it is done. A census finding that still flags it is
comparing against the OLD value: verify against the **current** value in the record, and if it
now reads `Georgia` or `Chile` the finding is resolved and must be reported as
**already-fixed**, not re-proposed. Do not issue a second write for the same row: one row, one
writer.

**2. Every finding carries a required boolean `defect` next to `proposal`** (both roles).
`defect: true` means "this row holds a value that is known to be wrong and must never be
re-proposed as clean"; `defect: false` with `proposal: review` means "nothing to see". For the
defect case keep `proposal: review` and `proposed_value: null`, and keep the prose note that
names the situation — the flag is what makes the human queue sortable by *known defect*
rather than by *review*. Cases that motivated it: Pannonian `country` (a five-country frontier
in a scalar column), Pannonian `lat/lon` (a 420 km line has no representative point, and
`lat`/`lon` are `NOT NULL`, so `clear` is unavailable), Karpasia `lat/lon` (three sources agree
the stored point is not the right place, none agree on the right one).

**3. The `< 4500 BC` bucket and the BP/BC unit trap.** (a) A dating given in cal BP may be
converted to BC by the standard offset **BP − 1950**, and the finding must say that it did so
and name the source. (b) `period_start` carries the **real year** when a source gives one; the
bucket's own lower bound (`-5000`) is a display label, not a value. Never invent a year merely
to escape a bucket. (c) `period_name` is then whatever `categorize_period()`
(`pipeline/utils/text.py:255`) returns for that year — do not hand-write the label. Measured:
`< 4500 BC` holds **298** sites, 96 storing `-5000` and 202 storing a real year
(re-verified against `../snapshot/unified_sites.jsonl.gz`: 298 / 96 / 202).

**4. T03 is a symptom, not a target.** A T03 finding is filed against `card_description`, but
the fix frequently belongs to `period_start`/`period_name`. Your proposal must name **the field
it writes**, not inherit the census finding's field; a finder that concludes "the bucket is
wrong" files on the bucket fields. The pilot's four T03 findings had four different correct
targets (period fields, the card, and one false alarm). The JSONL must carry a
`census_cross_reference` showing both ends when they differ.

**5. No `set` on the prose fields in Phase 3 — report only, and for two different reasons.**
`proposal: set` is unavailable on `card_description` and on `description`; both may only be
**reported** — `proposal: review` + `defect: ?`, with the note "Phase-5 text route (JSON file, then
DB), not a SQL update".
* `card_description`: a DB-only `set` is **reverted on the next API boot** — the JSON file wins.
  Verified mechanism: `api/main.py:506` calls the import (`api/services/card_descriptions.py:35` is
  the file path constant), and its upsert `:42-48` is `ON CONFLICT (site_id) DO UPDATE SET
  card_description = :desc`, i.e. into `card_stats` (`FIELD_CONTRACT.md` §2.3).
* `unified_sites.description`: **no boot overwriter exists** — verified by grep over the boot path
  and the services. The only writers are user/admin paths, none of them a container start:
  `api/routes/sites.py:1332` and `:1458` (site-edit endpoints, `UPDATE unified_sites … description
  = :description`) and `api/services/snapshots.py:347` (`restore_snapshot`, reachable only from the
  admin endpoint `api/routes/sites.py:955-963`); `api/routes/sites.py:1276` writes
  `user_contributions.description`, a different table. `FIELD_CONTRACT.md` §2 lists exactly three
  boot overwriters and all three are other columns (`site_type`, `name_normalized`,
  `card_stats.card_description`). So the reason to report instead of setting here is the plan's
  **phase split** — text regeneration belongs to Phase 5, not a SQL update — and **not** a restart:
  do not claim a restart reverts `description`.

Two facts to record: the card import truncates at `CARD_DESCRIPTION_MAX_LENGTH = 200`
(`api/services/card_descriptions.py:40`, applied at `:103`) because the column is `VARCHAR(200)`,
so a longer card text is silently cut — **state a length with any card text you draft, and keep it
at or under 200 characters**. And the pilot's five cards were already **138–179 characters**: the
field is near its limit.

**6. Reading the prose is in remit.** Nothing in the census verifies whether the SENTENCES are
true, although the narrator speaks them (`pipeline/video/shorts_tts.py`). All three defects the
census never named came from reading the text against sources. Phase 3 therefore explicitly
includes "read the prose against sources", and such items must be emitted with the label
`found_not_named` plus their own `proposal` and `defect` flag. They are a **counted yield** of
the pass, not an afterthought — and they must not masquerade as census findings.

**7. Five new T03 false-alarm families** (added to the §4.3 list in
`docs/procedures/SITES_DB_REMEDIATION_2026-09.md:191`): (i) *"the card's only dated claim is
the terminus"* — Pannonian's card ends "to the 5th century AD" while the bucket covers the
beginning; (ii) *"the date belongs to a person, not the site"* — 334 BC is Zeno of Citium's
birth year, the site is 7th century BC; (iii) *"Wikidata P625 is the parent city's or state's
coordinate, and it is wrong on Wikipedia itself"* — Petroglyph Beach: Wikidata and the
article's own `{{Coord}}` both carry downtown Juneau 235 km away, and GeoNames reproduces the
same point, so the error looks corroborated; (iv) *"the item's own precision is an alibi"* —
Satsurblia P625 precision 0.01216 deg = 1.35 km, larger than the 1.28 km difference flagged,
so any threshold below the item's own precision is unfalsifiable (and nothing in the census
output exposes that precision, so you must fetch it); (v) *"Natural Earth draws de-facto
borders and drops small islands"* — measured over the 117 T02 findings: 45 open water, 22
United Kingdom (points in Northern Ireland against the value Ireland), 9 Russia (Crimea), 7
Northern Cyprus, 4 "Northern Ireland matches no Natural Earth admin-0 feature", 2 Akrotiri SBA,
2 Kosovo, 1 Palestine, 1 Baltic Sea, 17 singles.

**8. Country vocabulary — canonical spellings, decided.** (a) `Georgia (country)` → `Georgia`
(already written by the mechanical lane). (b) `USA` → **`United States`**: decided this way
because the vocabulary's other long forms are long (United Kingdom, Northern Ireland), because
both spellings resolve to the same flag
(`ancient-nerds-map/src/utils/countryFlags.ts:233-234`), and because the current state is two
hubs for one country (`/sites/usa` and `/sites/united-states`) — the same split-hub defect
Georgia had. Recorded consequence: this changes 28 sites' hub URL, exactly as the Georgia fix
changed its hub, and the mechanical lane's interest measurement already showed that heal. It is
**ONE batched vocabulary write for Phase 6, NOT 28 per-site finder runs** — a finder+reviewer
pair per site to answer a spelling question is money burnt. (c) Never invent a country string:
if the value is not one of the canonical spellings, `proposal: review`.

**9. `Name - Qualifier` is house style.** 97 of 5,004 names contain `" - "` (`Karpasia - Town`,
`Akrotiri - Prehistoric City`, …; re-verified against `../snapshot/unified_sites.jsonl.gz`: 97
of 5,004). They are **not** malformed names. Do not propose renames for them.

**10. Reviewer independence is a property of the agent boundary, not of the URL list.** The
finder and the reviewer are **separate agent runs with separate contexts**. A reviewer that
shares the finder's context can satisfy the letter of "refute with your own research" and miss
its purpose. The pilot ran both stages in one agent and says so; do not repeat that in the run.
For you this means: the reviewer does **not** know your reasoning — the evidence you leave must
stand on its own.

**11. A third verdict value.** `refuted: true|false` plus `unresolved` cannot express "the
finding is factually true but the fix is not a correction" — which happened repeatedly (a real
inconsistency with no error, a true statement about a coordinate whose value is the country, a
true statement about a card date that belongs to a person). The reviewer's vocabulary therefore
gains **`true_but_no_correction`**, alongside refuted/confirmed/unresolved, and PILOT.jsonl-style
output must use it rather than smuggling it into `unresolved` or into prose. You do not emit
verdicts — but do not manufacture a correction to avoid that outcome either: the finder-side
encoding of those cases is `defect: false` + `proposal: review` (decision 2) or a
`found_not_named` report (decision 6).

**12. Run shape — decided from the pilot's own arithmetic.** **15 sites per run** (about 102 runs
per stage over ~1,528 sites), the **285 coords-only sites excluded entirely**
(`FIELD_CONTRACT.md` §4 item 6 makes every coordinate correction human, so those 570 runs can
write nothing; re-verified against `WORKLIST.jsonl`: 1,813 phase-3 sites minus the 285 whose only
findings are `T01/coords` = 1,528). The reviewer stage stays (18 % of fetches bought 6
refutations). 60 KB per-page fetch cap. Fetch **named features** instead of raw geometry dumps (2
OSM dumps cost 1 MB where a filtered query cost 4 KB). Never count a derived source twice. T02 is
**one human vocabulary decision plus a short exception list**, not 117 reviews. **Superseded:** 5
sites per batch means 726 agent lifecycles, and the project's own measured fixed overhead is
~31,500 tokens per lifecycle → ~22.9 M tokens of pure overhead versus ~1.3 M for 40 lifecycles.
Token accounting must be **MEASURED** on the first instrumented run, not assumed: the plan's two
anchors differ by 2× and must not be averaged.

## Your batch

* **15 sites per run** (decision 12 — the pilot's 5 sites per batch is **superseded**: it implies
  726 agent lifecycles at ~31,500 tokens of fixed overhead each), given as
  `(site_id, name, current field values, the census finding(s) that flagged them)`.
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
   decide — never `set` without a value), a **required boolean `defect`** (decision 2), and a
   `confidence`.
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

Five further families are now part of that list — see decision 7 above (the card's only dated
claim is the terminus; the date belongs to a person; P625 is the parent city's coordinate;
the item's own precision is an alibi; Natural Earth draws de-facto borders and drops small
islands).

## What a finding looks like

Same schema as the census (`scripts/remediation/census/model.py::Finding`):

```json
{"site_id": "...", "test_id": "P3/<field>", "field": "period_start",
 "severity": "severe", "dimension": "period",
 "current_value": 1, "proposed_value": -2000, "proposal": "set", "defect": false,
 "confidence": "two_source",
 "evidence": [{"source":"...","url":"...","quote":"...","retrieved_at":"..."}, {...}],
 "note": "why the sources decide it"}
```

`defect` is required on every finding (decision 2). `census_cross_reference` carries the census
finding's own `(test_id, field)` when the proposal writes a different field (decision 4).

## Hard rules

* **No claim without evidence.** No file:line or URL+quote → it is not a finding.
* **Never invent data.** If a value cannot be decided from evidence, the honest output is
  `confidence: "unverifiable"` / `proposal: "review"`, never a plausible guess. A wrong
  value is worse than an empty one.
* **Never swallow an error.** “Could not check” (dead source, 403, ambiguous) is recorded
  as such. It must never become “checked and clean”.
* **An empty field beats a wrong one** — `proposal: "clear"` is allowed and normal.
* **You do not write to the database.** Your findings go to the reviewer.
