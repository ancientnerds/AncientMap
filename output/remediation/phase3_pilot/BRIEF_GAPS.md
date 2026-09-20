# BRIEF_GAPS — what the Phase 3 briefs do not specify

Everything here was hit while running one real batch (`PILOT.md`). Each item names the decision
the pilot made, so the plan owner can ratify or overrule it. Ordered by blast radius, not by
length.

## 1. Which lane owns the eight overlap sites — decided: Phase 3

`MECHANICAL.md` lists **27** sites, defined as carrying *only* `proposal=set` /
`confidence=authoritative` findings. Measured in `WORKLIST.jsonl`: 1,840 records, of which
**1,813** are `phase3=true`, **27** are `phase3=false & mechanically_settable=true`, and **8**
are `phase3=true & mechanically_settable=true` (Satsurblia Cave, Didnauri, Armazi, Tsutskhvati
Cave NM, Tsona Cave, Kutaisi, Dmanisi, Easter Island — seven `T05/disambiguated` on
`Georgia (country)`, one `T05/compound` on `Chile, Easter Island`). So §the 27 is *defined* to
exclude the eight, and `_counts.json`'s `mechanically_settable_sites: 27` already excludes them.

**Decision made in the pilot:** Phase 3 owns the eight, and their `T05` country write is issued
in the same pass as the site's Phase-3 outcome, journaled once per `(site_id, field)`.
**Why:** each of the eight carries a review finding anyway, so the site must be visited by
Phase 3 regardless; letting two lanes write one row means two journal entries per site and a race
between a Phase-3 pass and a mechanical pass. **What the briefs should say:** one sentence.
**Cost of getting it wrong:** the alternative (mechanical lane takes all 8) re-creates a row with
two writers, and `MECHANICAL.md`'s own count of 27 would then be wrong.

## 2. The briefs give no field for "provably wrong, no scalar replacement exists"

Observed three times in five sites: Pannonian `country` (a five-country frontier in a scalar
column), Pannonian `lat/lon` (a 420 km line has no representative point; and `lat`/`lon` are
`NOT NULL`, so `clear` is unavailable), Karpasia `lat/lon` (ancient site vs modern town — three
sources agree it is not the town, none agree on where it is).

The vocabulary is `proposal ∈ {set, clear, review}` and `proposed_value` is a single value, so
"WRONG, no replacement" has to be emitted as `review` — i.e. it lands in the same queue as
"unresolved, need a human to look" and as "not enough evidence". Three different situations, one
word. The applier then cannot distinguish *"this row is known-bad and must not be re-proposed as
clean"* from *"nothing to see"*.

**Decision made in the pilot:** `proposal=review` + `proposed_value=null`, with the note naming
the situation (`no single correct value: …`, `new defect, not named by the census: …`). Note what
that means in practice: the row is *indistinguishable by machine* from "nothing to see" — the
only signal is prose in a free-text field. **What the briefs should say:** either a fourth verb
(`report`/`escalate`) or a required `defect: true|false` flag next to `proposal`, so the human
queue can be sorted by "known defect" rather than by "review".

## 3. The unbounded bucket `< 4500 BC` and the BP/BC unit trap

`categorize_period()` (`pipeline/utils/text.py:255`, mirrors the frontend) buckets everything
below −4500 into one label: `< 4500 BC`. Measured in the snapshot: `< 4500 BC` holds **298**
sites, of which 96 store the bucket's own lower bound `-5000` and 202 store a real year
(Cave of Altamira `-36000`, Cova Foradà `-100000`, Aetokremnos `-11000`). Satsurblia belongs
here: PLOS ONE dates it 25,535–24,408 **cal. BP**, the card says **23,500 BC**.

**Decision made in the pilot:** propose the real year, `period_start = -23500`, because (a) the
majority of sites in the bucket use real years and (b) `-5000` would assert a date 18,000 years
too recent, while `-23500` and `-5000` land in the same bucket anyway. `period_name` follows
from the function: `categorize_period(-23500) = "< 4500 BC"`.
**What the briefs should say:** (i) whether a dating in `cal BP` may be converted to a BC value
and by which convention (the pilot used BP − 1950, the standard offset; the card's `23,500 BC`
is consistent with it), (ii) whether `period_start` should carry the real year or only the
bucket's lower bound. Without (ii) two finders will write two different values for two
sites in the same bucket and both will look defensible.

## 4. T03's finding is filed against `card_description`, but the fix is often `period_start`/`period_name`

**Four** T03 findings in this batch (plus one T05 decision item), four different fix targets:

| site | census files the finding on | the fix actually belongs to |
|---|---|---|
| Satsurblia | `card_description` | `period_start` + `period_name` (the card is right) |
| Didnauri | `card_description` | `period_start` + `period_name` (the card is right) |
| Karpasia | `card_description` | `card_description` (the date belongs to a person born elsewhere) |
| Pannonian | `card_description` | nothing — false alarm |
| (Petroglyph T05) | `country` | nothing — decision item |

`PILOT.jsonl` therefore carries `census_cross_reference` on both ends. **What the briefs should
say:** a T03 finding is a *symptom* on the text field; the proposal must name the field it
writes, and a finder that concludes "the bucket is wrong" must file the proposal on the bucket
fields, not inherit the finding's field.

## 5. `proposal=set` on `card_description` or `description` cannot be applied DB-only

`FIELD_CONTRACT.md` §2.3: on every API boot the card text is overwritten from
`public/data/card_descriptions.json` (`api/main.py:506` calls `import_card_descriptions`; the
upsert is `api/services/card_descriptions.py:42-48`, the file path `:35`). A Phase-3 proposal of
the form `set card_description` would be reverted by the next restart unless the JSON file is
also changed — and the plan puts text regeneration in **Phase 5**. The Phase-3 briefs
list `card_description` as a field to check (and the census files T03 findings on it) without
saying that a `set` there is a different kind of write.

**Decision made in the pilot:** the two card/description defects found (Karpasia card, Pannonian
description) are emitted as `proposal=review` with the note "Phase-5 text route (JSON file, then
DB), not a SQL update". **What the briefs should say:** either forbid `set` on the two prose
fields in Phase 3, or name the JSON+DB route explicitly as part of Phase 3's remit.

Related: the import truncates at `CARD_DESCRIPTION_MAX_LENGTH = 200`
(`api/services/card_descriptions.py:40`, applied at `:103`) because the column is `VARCHAR(200)`.
A proposed card text longer than that is silently cut; the finder gets no signal that half its
sentence is gone. All five cards in this batch are 138–179 characters — the field is currently
near its limit, so a finder that writes a fuller sentence will hit the cut.

## 6. Nothing verifies the prose

The three defects the census never named (PILOT.md §5) were all found by reading the text: the
Pannonian coordinate 82.7 km off the Danube, the Pannonian description that scopes a
multinational frontier to Croatia and contradicts itself, the Karpasia card that gives Zeno of
Citium a birthplace 102 km away. T01 compares *values*, T02 compares *geometry against Natural
Earth*, T03 reads *dates* out of the text, T05 looks at *country strings*. No test asks whether
the **sentences are true**, although the sentences are what the narrator reads
(`pipeline/video/shorts_tts.py` speaks name + card closing line).

**Decision made in the pilot:** report them as `found_not_named` defects with their own
proposal, and count them (3 of 3 in this batch) as a *yield* of the manual pass rather than of
the census. **What the plan should decide:** whether Phase 3's remit includes "read the prose
against sources", because if it does, the batch cost is not driven by the census findings at all
(15 findings here, 3 extra defects) — and if it does not, a distinct pass must be budgeted.

## 7. §4.3's false-alarm patterns are incomplete — five new ones, each measured

ENRICHMENT_AUDIT §4.3 lists the known T03 false-alarm patterns. This batch produced five
families it does not cover:

1. **"The card's only dated claim is the terminus."** Pannonian: the card ends "…to the 5th
   century AD", the bucket `500 BC - 1 AD` covers the *beginning* (Augustus, 31 BC). T03 compares
   the text's latest year with the bucket and calls it `all-outside`/severe. One of the two T03
   false alarms in this batch is of this family (Pannonian); Petroglyph is the same shape but not
   even a finding — its card's only date (about 8,000 years) sits in the right bucket by a
   different route.
2. **"The date belongs to a person, not the site."** Karpasia: 334 BC is Zeno of Citium's birth
   year; the site is 7th-century BC. Fix: T03 must not treat a date attached to a named person
   (or to a "most famous resident") as a dating of the site.
3. **"Wikidata's `P625` is the parent city's or state's coordinate, and it is wrong on
   Wikipedia itself."** Petroglyph: both Wikidata (58.301061/−134.413121) and the Wikipedia
   article's own `{{Coord}}` template carry downtown **Juneau**, 235 km from the beach in
   Wrangell; GeoNames reproduces the same point, so the error propagates and *looks*
   corroborated. T01's 235.60 km lead was correct about the *distance*, wrong about which side
   was broken.
4. **"Wikidata's precision is an alibi."** Satsurblia: `P625` precision `0.01216°` = 1.35 km,
   larger than the 1.28 km difference T01 flagged. Any distance-based T01 threshold below the
   item's own precision is unfalsifiable; the brief says "do not refute on a sub-precision
   difference" but nothing in the census output exposes `P625`'s precision, so a finder cannot
   apply that rule without fetching Wikidata itself.
5. **"Natural Earth draws de-facto borders and drops small islands."** Measured over the 117 T02
   findings: 45 open water (real coastline generalization — Petroglyph's 1.1 km), 22 United
   Kingdom (points in Northern Ireland against the value `Ireland`), 7 Northern Cyprus,
   4 "'Northern Ireland' matches no Natural Earth admin-0 feature", 9 Russia (Crimea),
   2 Akrotiri Sovereign Base Area, 2 Kosovo, 1 Palestine, 1 Baltic Sea, and 17 singles. §4.3
   pattern 2 explains England/Scotland/Wales (a deliberate sub-national vocabulary) but says
   nothing about `Ireland` vs `Northern Ireland`, which is the second-largest T02 class. All
   three T02 findings in this batch were refuted as data errors.

## 8. Country vocabulary has rules nobody wrote down

Measured in the snapshot: `USA` 28 vs `United States` 1; `Georgia` 3 vs `Georgia (country)` 27;
England 1,052, Wales 118, Scotland 83, Ireland 68, Northern Ireland 4, United Kingdom 1;
98 distinct country strings. `Georgia (country)` is wrong because the narrator reads it aloud
(`shorts_tts.py:21-23` splits on the last comma, which the parenthetical does not have) — that is
a *mechanism*, and it is the reason the T05 finding is severe. `USA` vs `United States` breaks no
narration: both are keys of `COUNTRY_CODES`
(`ancient-nerds-map/src/utils/countryFlags.ts:233-234`, both → `US`). It is still a real defect —
the census note measures the consequence, "one country in two hub pages (`/sites/usa` and
`/sites/united-states`) and two entries in the globe's country filter" — but it has no factual
component at all. So one finding is a fact defect and the other is a vocabulary decision, and the
briefs treat them as one class (`spelling-split`).

**Decision made in the pilot:** `Georgia (country)` → `set "Georgia"` (authoritative, house
precedent of 3 sites + Wikidata `P17`); `USA` → `review`, because picking one of two spellings
that both render is a product decision and not a finder's call. **What the briefs should say:**
which spelling is canonical. Otherwise Phase 3 spends a finder+reviewer pair on each of 28 sites
to produce a question.

## 9. `Name - Qualifier` names are house style, not artifacts

97 of 5,004 site names contain `" - "` ("Karpasia - Town", "Akrotiri - Prehistoric City",
"Langweiler - Archaeological Site", "Armeni - Archaeological Site"). A finder that treats them
as malformed names (as one could, looking at `Karpasia - Town`) would propose renames across 97
sites. **Decision made in the pilot:** keep the name; noted as CORRECT with the measurement as
evidence. **What the briefs should say:** one line, so no future batch re-litigates it.

## 10. Reviewer independence is assumed, not ensured

`REVIEWER_BRIEF.md` is built for a *separate* agent: "refute with your OWN research, never by
re-reading the finder's URL". This pilot had one agent run both stages, and the substantive rule
was followed (14 reviewer-stage fetches to sources the finder had not used), but the independence
of *not knowing* the finder's reasoning was not reproduced. The review gate in the plan ("only
`refuted=false` is ever applied") is a process guarantee; a reviewer that shares the finder's
context can satisfy the letter of it and not its purpose. Worth stating in the briefs:
*independence is a property of the agent boundary, not of the URL list.*

## 11. `refuted` has no slot for "the finding is true but the fix is not a correction"

Repeatedly in this batch the census was factually right and the conclusion still wrong:
`T05/spelling-split` on Petroglyph (a real inconsistency, no error), `T02` on Pannonian (a true
statement about the coordinate, whose value is the country), `T03` on Karpasia (a true statement
about the card's date, which belongs to a person). The vocabulary `refuted: true|false` +
`unresolved` forces these either into `false` (apply a non-correction) or into `unresolved`
(pretend the reviewer could not decide). **Decision made in the pilot:** `unresolved` + a note
naming the third reading, and `PILOT.jsonl` uses `found_not_named` / `confirmed_as_inconsistency`
for the reviewer verdicts so a machine reader does not have to parse prose. **What the briefs
should say:** whether "true finding, wrong conclusion" is `refuted: true` or its own value.

## 12. Where the numbers for the run come from (one correction to the plan)

The plan's phrase "363 batches / 726 agent runs" implies **5 sites per batch** (1,813 / 5 = 363,
× 2 stages = 726). The plan's other anchor, "~40,000 tokens/site" with 91 sites per run-1,
implies **~20 runs per stage**. Both are in the plan and they differ by 18× in run count; the
per-site cost anchors differ by 2× (40,000 vs 20,295 = 3,653,051/180). `COST.md` §5 shows both
side by side and refuses to average them. The pilot measured no tokens, so it cannot settle it —
but it can say that with 726 lifecycles the fixed context overhead alone (~31,500 tokens/run per
the project's own measurement) is ~22.9 M tokens, versus ~1.3 M for 40 lifecycles. **Decision
needed before launch, from whoever holds the run-1 token accounting.**
