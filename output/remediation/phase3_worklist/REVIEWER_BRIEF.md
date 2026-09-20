# Phase 3 — Stage 2 REVIEWER brief (adversarial)

You receive the finder's findings for the same sites. Your job is to **try to refute every
single one**. A finding survives only if you cannot break it. You are the reason 61 % of
first-stage claims were refuted in the pilot (plan §4) — if you confirm everything, you have
failed the method.

## DECISIONS (ratified 2026-09-21)

Ratified from the five-site pilot (`../phase3_pilot/BRIEF_GAPS.md`, `PILOT.md`). They override
anything below that disagrees with them. Decisions, not options; every number is the pilot's
measurement (where re-verified here, the snapshot is named).

**1. The eight overlap sites are Phase 3's, and their country is already written.** Satsurblia
Cave, Didnauri, Armazi, Tsutskhvati Cave NM, Tsona Cave, Kutaisi, Dmanisi, Easter Island. **What
changed:** the mechanical lane has ALREADY written their country — all 35 rows including these 8,
run stamp `2026-09-21_mechanical-country`, journal 5,473 rows. So a finding that still flags it
is comparing against the OLD value: check the **current** value in the record, and if it now
reads `Georgia` or `Chile` the item is **already-fixed** — say so, do not treat it as a
correction to apply. Do not issue a second write for the same row: one row, one writer.

**2. Every finding carries a required boolean `defect` next to `proposal`** (both roles), and
checking it is part of your job. `defect: true` means "this row holds a value that is known to be
wrong and must never be re-proposed as clean" — it stays `proposal: review` with
`proposed_value: null` and a prose note naming the situation; do **not** refute it with "there is
no replacement value". `defect: false` with `proposal: review` means "nothing to see". The flag
is what makes the human queue sortable by *known defect* rather than by *review*. Cases that
motivated it: Pannonian `country` (a five-country frontier in a scalar column), Pannonian
`lat/lon` (a 420 km line has no representative point, and `lat`/`lon` are `NOT NULL`, so `clear`
is unavailable), Karpasia `lat/lon` (three sources agree the stored point is not the right place,
none agree on the right one).

**3. The `< 4500 BC` bucket and the BP/BC unit trap.** (a) A dating given in cal BP may be
converted to BC by the standard offset **BP − 1950**, and the finding must say that it did so and
name the source — a conversion that does not declare itself, or uses another offset, is
refutable. (b) `period_start` carries the **real year** when a source gives one; the bucket's own
lower bound (`-5000`) is a display label, not a value. A proposal that invents a year merely to
escape a bucket is refuted. (c) `period_name` must equal `categorize_period(period_start)`
(`pipeline/utils/text.py:255`) — check the label arithmetically instead of accepting it.
Measured: `< 4500 BC` holds **298** sites, 96 storing `-5000` and 202 storing a real year
(re-verified against `../snapshot/unified_sites.jsonl.gz`: 298 / 96 / 202).

**4. T03 is a symptom, not a target.** A T03 finding is filed against `card_description`, but the
fix frequently belongs to `period_start`/`period_name`. The proposal must name **the field it
writes**, not inherit the census finding's field; a finding whose proposal stays on the census
field while the real target is elsewhere is refutable as wrong-target. The JSONL must carry a
`census_cross_reference` showing both ends when they differ. The pilot's four T03 findings had
four different correct targets (period fields, the card, and one false alarm).

**5. No `set` on the prose fields in Phase 3 — report only, and for two different reasons.**
`proposal: set` is unavailable on `card_description` and on `description`; a finding that proposes
one on either field is therefore **refuted as inapplicable**, however true the text is. Both may
only be **reported** — `proposal: review` + `defect: ?`, with the note "Phase-5 text route (JSON
file, then DB), not a SQL update".
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
so a longer card text is silently cut — a proposed card text must name its length and stay at or
under 200 characters. And the pilot's five cards were already **138–179 characters**, so the field
is near its limit.

**6. Reading the prose is in remit.** Nothing in the census verifies whether the SENTENCES are
true, although the narrator speaks them (`pipeline/video/shorts_tts.py`). Items the finder emits
for that are labelled `found_not_named` and are a **counted yield** of the pass, not an
afterthought: review them with your own sources like any other finding. Do not drop them as "not
a census finding" — and do not let them through on the finder's word either.

**7. Five new T03 false-alarm families** (added to the §4.3 list in
`docs/procedures/SITES_DB_REMEDIATION_2026-09.md:191`): (i) *"the card's only dated claim is the
terminus"* — Pannonian's card ends "to the 5th century AD" while the bucket covers the beginning;
(ii) *"the date belongs to a person, not the site"* — 334 BC is Zeno of Citium's birth year, the
site is 7th century BC; (iii) *"Wikidata P625 is the parent city's or state's coordinate, and it
is wrong on Wikipedia itself"* — Petroglyph Beach: Wikidata and the article's own `{{Coord}}`
both carry downtown Juneau 235 km away, and GeoNames reproduces the same point, so the error looks
corroborated; (iv) *"the item's own precision is an alibi"* — Satsurblia P625 precision
0.01216 deg = 1.35 km, larger than the 1.28 km difference flagged, so any threshold below the
item's own precision is unfalsifiable (nothing in the census output exposes that precision, so you
must fetch it); (v) *"Natural Earth draws de-facto borders and drops small islands"* — measured
over the 117 T02 findings: 45 open water, 22 United Kingdom (points in Northern Ireland against
the value Ireland), 9 Russia (Crimea), 7 Northern Cyprus, 4 "Northern Ireland matches no Natural
Earth admin-0 feature", 2 Akrotiri SBA, 2 Kosovo, 1 Palestine, 1 Baltic Sea, 17 singles.

**8. Country vocabulary — canonical spellings, decided.** (a) `Georgia (country)` → `Georgia`
(already written by the mechanical lane). (b) `USA` → **`United States`**: decided this way
because the vocabulary's other long forms are long (United Kingdom, Northern Ireland), because
both spellings resolve to the same flag (`ancient-nerds-map/src/utils/countryFlags.ts:233-234`),
and because the current state is two hubs for one country (`/sites/usa` and
`/sites/united-states`) — the same split-hub defect Georgia had. Recorded consequence: this
changes 28 sites' hub URL, exactly as the Georgia fix changed its hub, and the mechanical lane's
interest measurement already showed that heal. It is **ONE batched vocabulary write for Phase 6,
NOT 28 per-site finder runs** — a finder+reviewer pair per site to answer a spelling question is
money burnt. So an item that asks "USA or United States?" is a vocabulary decision, not 28
corrections: do not confirm individual writes for it. (c) Never invent a country string: if the
value is not one of the canonical spellings, `proposal: review`.

**9. `Name - Qualifier` is house style.** 97 of 5,004 names contain `" - "` (`Karpasia - Town`,
`Akrotiri - Prehistoric City`, …; re-verified against `../snapshot/unified_sites.jsonl.gz`: 97 of
5,004). They are **not** malformed names: refute any rename proposal for them.

**10. Reviewer independence is a property of the agent boundary, not of the URL list.** The finder
and the reviewer are **separate agent runs with separate contexts**, and this is the method, not a
nicety: a reviewer that shares the finder's context can satisfy the letter of "refute with your
own research" and miss its purpose. The pilot ran both stages in one agent and says so; do not
repeat that in the run. **Not knowing the finder's reasoning is part of the job** — your own
sources are your input.

**11. A third verdict value.** `refuted: true|false` plus `unresolved` cannot express "the finding
is factually true but the fix is not a correction" — which happened repeatedly: a real
inconsistency with no error (T05/spelling-split on Petroglyph), a true statement about a
coordinate whose value is the country (T02 on Pannonian), a true statement about a card date that
belongs to a person (T03 on Karpasia). Add the verdict **`true_but_no_correction`** to your
vocabulary, alongside refuted/confirmed/unresolved, and use it in PILOT.jsonl-style output rather
than smuggling it into `unresolved` or into prose.

**12. Run shape — decided from the pilot's own arithmetic.** **15 sites per run** (about 102 runs
per stage over ~1,528 sites); the **285 coords-only sites are excluded entirely**
(`FIELD_CONTRACT.md` §4 item 6 makes every coordinate correction human, so those 570 runs can write
nothing; re-verified against `WORKLIST.jsonl`: 1,813 phase-3 sites minus the 285 whose only
findings are `T01/coords` = 1,528). Your stage stays: 18 % of fetches bought 6 refutations. 60 KB
per-page fetch cap. Fetch **named features** instead of raw geometry dumps (2 OSM dumps cost 1 MB
where a filtered query cost 4 KB). Never count a derived source twice. T02 is **one human
vocabulary decision plus a short exception list**, not 117 reviews. **Superseded:** 5 sites per
batch means 726 agent lifecycles, and the project's own measured fixed overhead is ~31,500 tokens
per lifecycle → ~22.9 M tokens of pure overhead versus ~1.3 M for 40 lifecycles. Token accounting
must be **MEASURED** on the first instrumented run, not assumed: the plan's two anchors differ by
2× and must not be averaged.

## The one rule that defines this stage

**Refute with your OWN research, not by re-reading the finder's evidence.**
Open your own sources — Wikipedia, Wikidata, the official page, satellite/OSM for
coordinates. Do not accept the finder's `quote` as proof; independently confirm the fact it
claims. If your independent source contradicts the finder, the finding is refuted. If you
merely re-read the finder's URL and nod, you have added zero information and the two stages
are one.

## Method

1. For each finding, ask: *is the stored value actually wrong, and is the proposed value
   actually right?* Check both halves.
2. Look first for the specific ways the pilot's finder was wrong (see patterns below).
3. Emit a verdict per finding: `refuted: true|false`, or `true_but_no_correction`
   (decision 11: the finding is factually true but the fix is not a correction), with
   `refutation_evidence` (`{source, url, quote, retrieved_at}`) when refuting — again, your own
   quote.
4. **Only `refuted = false` is ever applied.** A finding you refute, or cannot independently
   reproduce, is dropped — not applied.
5. A finding you cannot settle either way → `refuted: true` is *not* allowed as a lazy
   default. Mark it `unresolved`; it goes to a human, not to the database.

## Briefed false-alarm patterns (plan §4.3) — refute findings that violate these

1. **Bucket-boundary `period_start`.** A round bucket value is not an error unless the real
   dating belongs in a **different bucket**. Refute “it’s round, so wrong”.
2. **`England` / `Scotland` / `Wales` instead of `United Kingdom`** is deliberate project
   design — refute it.
3. **`Archaeological Site of Olympia`** is the official UNESCO title — refute “prefix
   clutter”.
4. **`civilization`** is a copy of `country` — any cultural-attribution error claim on it is
   refuted.
5. **Never downgrade specificity.** A more specific DB value is not wrong just because
   Wikidata is generic.
6. **Same name, different site.** Refute any coordinate/name claim that confuses two
   same-named places.

Five further families are now part of that list — see decision 7 above (the card's only dated
claim is the terminus; the date belongs to a person; P625 is the parent city's coordinate; the
item's own precision is an alibi; Natural Earth draws de-facto borders and drops small islands).

Additional known false-positive sources to check:
* Transposed or comma-decimal coordinates read from the wrong source.
* Museum / visitor-centre founding years misread as `period_start` (designation date, not
  occupation date).
* Round-trip unit or precision errors (Wikidata `P625` precision is often ±1 km or coarser —
  do not refute on a sub-precision difference).

## Application contract (plan §Phase 3) — for the supervisor, not the reviewer

For each surviving (`refuted = false`) finding, a deterministic applier:

* issues a conditional `UPDATE … SET <field> = <new> WHERE id = <site_id> AND <field> IS NOT
  DISTINCT FROM <old>;` — the `WHERE` carries the old value so a concurrent change voids the
  write;
* appends a journal entry (site_id, field, old, new, source of the finding, timestamp);
* **never** `DELETE`; **never** a bare `UPDATE` without the condition;
* if the conditional `WHERE` matches 0 rows, records a conflict, does not force the write.

## Hard rules

* Independent evidence only; not the finder's.
* No invention; `unresolved` and `true_but_no_correction` are valid verdicts.
* A `set` on `card_description` or `description` is refuted as inapplicable, however true the
  text is (decision 5).
* Errors are recorded, never turned into “clean”.
* You do not write to the database; you produce verdicts.
