# Phase 3 pilot — one batch of five sites, two stages (finder → reviewer)

Read-only pilot. No database write, no commit, no push. Everything here is derived from
`output/remediation/snapshot/` (exported 2026-09-20), the census output
(`output/remediation/run_t01|run_t02|run_t03|run_t05`), `phase3_worklist/WORKLIST.jsonl` and
76 logged HTTP fetches in `fetch_log.jsonl`.

**What this batch is:** the first five records of `WORKLIST.jsonl` in run order (worst first).
It is one batch out of 363. It measures *cost per batch* and *what a batch produces*; it does
not measure a rate. Anything called a rate below says so and names its n.

## 0. Method honesty — the two stages were run by one agent

The plan's Phase 3 is two agents: a finder proposes, a reviewer tries to refute with its **own**
research. This pilot used one agent playing both roles. Consequences, stated plainly:

* The second stage opened **different sources** than the first (logged with `stage: "reviewer"`
  in `fetch_log.jsonl`, 14 of 76 fetches), not the finder's URLs. That is the substantive part
  of the reviewer rule and it was followed.
* What was *not* reproduced is the independence of **not knowing** the finder's reasoning. A
  separate reviewer agent that never sees the finder's notes may find different refutations.
  Treat this batch's refutation rate as an upper bound on reviewer effectiveness: 6 of 15 census
  leads were refuted here (§4). The plan's own pilot measured 61 % (`REVIEWER_BRIEF.md:4`,
  citing plan §4).
* Both "agents" shared one context, so this batch's token cost is **not** two independent agent
  runs. §4 of `COST.md` says what that does to the extrapolation.

Journal of what failed, kept because a failed fetch is a cost and a risk, not a footnote:
Nominatim returned **403 on 5 of 5** attempts (unusable — not rate limiting, the same 403 on
first contact); `html.duckduckgo.com` connection-reset, while `lite.duckduckgo.com` worked;
Overpass returned 504 twice and 429 once (retry succeeded); britannica.com and trek.zone 403;
plato.stanford.edu/entries/zeno-citium/ returned 380 bytes of JS shell and
iep.utm.edu/zeno/ served an unrelated article (`liar_paradox`, 25 KB, no mention of Zeno's
birthplace); the first guessed
Alaska State Parks URL 404'd (the real one was found via a search engine). 19 of 76 fetches were
non-200 (25 %).

## 1. The batch

| # | site_id | name | census findings |
|---|---|---|---|
| 1 | `31860bc4-476a-49bc-9f97-e25220063d19` | Satsurblia Cave | T01/coords, T03/all-outside, T05/disambiguated |
| 2 | `8c39badd-8113-4a71-a041-21d68f47bf58` | Petroglyph Beach State Historic Park | T01/coords, T02/outside-polygon, T05/spelling-split |
| 3 | `db85cd62-288f-4142-9cad-f15532e4fe26` | Pannonian Limes | T01/country, T02/outside-polygon, T03/all-outside |
| 4 | `e2dbb087-8f25-4726-967a-e1054d4be16c` | Karpasia - Town | T01/coords, T02/outside-polygon, T03/all-outside |
| 5 | `593de422-8bfc-4101-8e13-3db406830e60` | Didnauri | T01/coords, T03/all-outside, T05/disambiguated |

Exactly 3 findings per site, 15 in total — that is how the worklist was built
(`n_findings` 3 for all five), not a property of the census.

### 1.1 The eight overlap sites: Phase 3 owns them

`MECHANICAL.md` lists **27** sites as mechanically settlable (`proposal=set`,
`confidence=authoritative`, no other finding). Measured from `WORKLIST.jsonl`: 27 records have
`phase3=false & mechanically_settable=true`, and the **8** overlap sites — Satsurblia Cave,
Didnauri, Armazi, Tsutskhvati Cave Natural Monument, Tsona Cave, Kutaisi, Dmanisi, Easter
Island — have `phase3=true & mechanically_settable=true`. Seven of the eight carry
`T05/disambiguated` on `Georgia (country)`; Easter Island carries `T05/compound` on
`Chile, Easter Island`. `_counts.json`'s `mechanically_settable_sites: 27` already counts only
the `phase3=false` records, i.e. it already excludes the 8.

**Decision: Phase 3 owns the 8.** Reasons: (a) `MECHANICAL.md`'s 27 is defined as *only*
`set`/`authoritative` findings and the 8 are excluded by construction, so nothing is
re-assigned; (b) the 8 each carry review findings anyway, so the site has to be visited in
Phase 3 regardless — letting the mechanical lane also write their `country` means two writers
on one row and two journal entries for one site; (c) the `T05` `set` is a one-line fix that
costs nothing extra once the site is in a Phase-3 batch. Consequence for the applier: the 8
get their `T05` write in the same pass as the site's Phase-3 outcome, journaled once per
`(site_id, field)`.

## 2. Outcomes — all 40 (site, field) pairs

Vocabulary: **CORRECT** (stored value survives), **WRONG** (it does not), **UNVERIFIABLE**
(no source settles it). `proposal` is the FINDER_BRIEF vocabulary (`set`/`clear`/`review`).
Nothing was written; `proposal=set` means "this would be writable after the reviewer".

| site | field | stored | outcome | proposal | correct value |
|---|---|---|---|---|---|
| Satsurblia | name | `Satsurblia Cave` | CORRECT | — | — |
| Satsurblia | country | `Georgia (country)` | WRONG (severe) | set | `Georgia` |
| Satsurblia | lat/lon | 42.37727, 42.60098 | UNVERIFIABLE (moderate) | review | not decided — 3 candidates |
| Satsurblia | period_start | `-500` | WRONG (severe) | set | `-23500` |
| Satsurblia | period_name | `500 BC - 1 AD` | WRONG (severe) | set | `< 4500 BC` |
| Satsurblia | site_type | `Cave Structures` | CORRECT | — | — |
| Satsurblia | description | (Kumistavi 1.2 km, 287 m asl, 1976) | CORRECT | — | — |
| Satsurblia | card_description | (Paleolithic, 23,500 BC) | CORRECT | — | — |
| Petroglyph | name | `Petroglyph Beach State Historic Park` | CORRECT | — | — |
| Petroglyph | country | `USA` | CORRECT | — | — |
| Petroglyph | lat/lon | 56.48287, -132.39350 | CORRECT | — | — |
| Petroglyph | period_start | `-5000` | CORRECT | — | — |
| Petroglyph | period_name | `< 4500 BC` | CORRECT | — | — |
| Petroglyph | site_type | `Petroglyphs` | CORRECT | — | — |
| Petroglyph | description | (Wrangell, 8,000 years, 40+) | CORRECT | — | — |
| Petroglyph | card_description | (8,000 years, 40+) | CORRECT | — | — |
| Pannonian | name | `Pannonian Limes` | CORRECT | — | — |
| Pannonian | country | `Croatia` | WRONG (moderate) | review | no single value (AT/SK/HU/HR/RS) |
| Pannonian | lat/lon | 44.00010, 20.99992 | WRONG (moderate) | review | no single value (420 km line) |
| Pannonian | period_start | `-500` | CORRECT | — | — |
| Pannonian | period_name | `500 BC - 1 AD` | CORRECT | — | — |
| Pannonian | site_type | `Fortress/citadel` | CORRECT | — | — |
| Pannonian | description | ("in Croatia … from Austria to Serbia") | WRONG (moderate) | review | rewrite (Phase 5 file route) |
| Pannonian | card_description | (420 km, Augustus → 5th c.) | CORRECT | — | — |
| Karpasia | name | `Karpasia - Town` | CORRECT | — | — |
| Karpasia | country | `Cyprus` | CORRECT | — | — |
| Karpasia | lat/lon | 35.59664, 34.37809 | WRONG (moderate) | review | site is at Ayios Philon, 3.4–4.6 km away |
| Karpasia | period_start | `-1500` | CORRECT | — | — |
| Karpasia | period_name | `1500 - 500 BC` | CORRECT | — | — |
| Karpasia | site_type | `City/town/settlement` | CORRECT | — | — |
| Karpasia | description | (3 km from Rizokarpaso, harbour) | CORRECT | — | — |
| Karpasia | card_description | ("Zeno of Citium, resident") | WRONG (severe) | review | rewrite (Phase 5 file route) |
| Didnauri | name | `Didnauri` | CORRECT | — | — |
| Didnauri | country | `Georgia (country)` | WRONG (severe) | set | `Georgia` |
| Didnauri | lat/lon | 41.41470, 46.22281 | CORRECT | — | — |
| Didnauri | period_start | `-3000` | WRONG (severe) | set | `-1500` |
| Didnauri | period_name | `3000 - 1500 BC` | WRONG (severe) | set | `1500 - 500 BC` |
| Didnauri | site_type | `City/town/settlement` | CORRECT | — | — |
| Didnauri | description | (Late Bronze/Early Iron Age) | CORRECT | — | — |
| Didnauri | card_description | (12th–9th c. BC) | CORRECT | — | — |

Totals: **28 CORRECT, 11 WRONG, 1 UNVERIFIABLE**. Of the 11 WRONG, **6 are field-level
`set`s** (2 × country `Georgia`, 2 × period_start, 2 × period_name — i.e. two country fixes
plus two period fixes) and **5 are human decisions** (2 coordinates, 1 multinational `country`,
1 description, 1 card text). Both period fixes and both country fixes are on two of the five
sites.

For comparison with the mechanical lane: of those 6 `set`s, the 2 country fixes are
`confidence=authoritative` and are exactly what the mechanical lane would have applied without
any LLM stage. So this batch's **LLM-only, mechanically applicable output is 2 field-level
corrections** (Satsurblia and Didnauri `period_start`+`period_name`), on 5 sites.

**Confidence audit (the brief's "distinct hosts; two pages on one host is one source" rule).**
Every non-CORRECT verdict in `PILOT.jsonl` was re-checked against that rule: 34 rows are
`two_source`, 5 are `authoritative` and 1 is `unverifiable`, and no non-CORRECT verdict now rests
on a single host unless it is labelled `authoritative`. Three verdicts were **downgraded** during
that audit because their evidence turned out to be one family — the Karpasia card (both items
Wikidata: `P19`/`P27` of Q171303 and the label of Q1743884), the Satsurblia `period_name` (PLOS
ONE plus the local bucket function) and the Petroglyph card (the official Alaska DNR page, from
which the Wikipedia text is derived). Four CORRECT rows carry one external
source plus one **local** check (a `categorize_period`/`normalize_site_type` fixed-point run or a
snapshot measurement, `fetch_log_label: null`) — that is two independent checks, not two sources,
and the label says which is which. Same trap, caught once: GeoNames reproduced both the stored
Satsurblia coordinate *and* Wikipedia's wrong Juneau coordinate, so "GeoNames agrees" was never
counted as corroboration.

## 3. Site by site

Each row: what the census said, what the finder found, what the reviewer checked on its own,
verdict. Quotes are verbatim (curly quotes normalised); every URL is in `fetch_log.jsonl` with
its byte count and HTTP status, and the body is under `evidence/`.

### 3.1 Satsurblia Cave (31860bc4…)

**census 1 — T01/coords (moderate).** "Wikidata P625 is 1.28 km from the stored point (review
threshold 1000 m)".
*Finder:* Wikidata Q28220554 `P625 = 42.388111, 42.606167`, **with its own precision
`0.01216°` = 1.35 km** (fetch #1) — the 1.28 km difference is *smaller than Wikidata's own
stated uncertainty*, and the REVIEWER_BRIEF names exactly this as a false-positive source
("do not refute on a sub-precision difference").
*Reviewer (own sources):* `showcaves.com` "Location: Village Kumistavi, Tskaltubo Municipality.
(42.387795, 42.606163) … 287 m asl., L=130 m, A=1,950 m²" (#55) agrees with Wikidata
(40 m apart). `geonames.org` places "Satsurblia Cave" at **42.3772 / 42.6009** (#65) — the
stored value to four decimals. OpenStreetMap (#57) has a node `საწურბლიას მღვიმე`,
`name:en = Satsurblia Cave`, at **42.39647 / 42.58902**, and puts the stored point 50 m from
the way `პრომეთეს მღვიმე` (`Prometheus Cave Visitors Center & Tickets`) and 75 m from the node
`Prometheus Cave Exit`. So three independent sources put Satsurblia 1.28 km, 1.25 km and 2.35 km (measured)
away from the stored point — and one of them (GeoNames) agrees with it exactly.
*Verdict:* **UNVERIFIABLE → review, no write.** Note the new information the census did not
have: the stored pin sits on the visitor complex of the *neighbouring* Prometheus Cave, so the
row is probably wrong, but no defensible replacement exists (three candidate points, none
authoritative enough to overrule the others). This is a human decision, not an applier write.

**census 2 — T03/all-outside (severe).** "card_description dates the site to 23,500 BC
(< 4500 BC), but the declared period is 500 BC - 1 AD".
*Finder:* the card is right and the bucket is wrong. Peer-reviewed source (own research, #69):
PLOS ONE 10(10):e111271, "The layer is dated to **25,535–24,408 cal. BP** (95.4 % confidence
interval)" → ≈ 23,600–22,400 BC. Independently, `showcaves.com` (#55) and the Georgian
protected-area page (#60) place the site in the Tskaltubo karst and describe the medieval
reuse, and `categorize_period(-23500) = "< 4500 BC"` (run against
`pipeline/utils/text.py:255`).
*Reviewer:* could not refute; the peer-reviewed dating stands.
*Verdict:* **WRONG → `set period_start = -23500`, `set period_name = "< 4500 BC"`**
(two-source: PLOS ONE + enwiki/ka-wiki; the record's own card text agrees). `BRIEF_GAPS.md` §3
records the open sub-question: the bucket is unbounded, and the DB contains both `-5000`
(96 sites) and real years (202 sites, e.g. Cave of Altamira `-36000`) — the pilot chose the real
year, because `-23500` and `-5000` produce the *same* bucket only if `categorize_period`
is applied to a value below −4500, and the DB's Palaeolithic sites overwhelmingly use real
years.

**census 3 — T05/disambiguated (severe).** `country = "Georgia (country)"` → `Georgia`.
*Reviewer:* `pipeline/video/shorts_tts.py:21-23` (`specific_place`) splits the country on the
**last comma**; `Georgia (country)` has no comma, so `spoken_name()` speaks the whole string —
the finding's mechanism is reproduced at source. Wikidata `P17 = Q230` (#1). The snapshot holds
`Georgia (country)` 27× vs `Georgia` 3×, so the parenthetical is the anomaly.
*Verdict:* **WRONG → `set "Georgia"`** (authoritative, mechanically applicable). Confirmed.

### 3.2 Petroglyph Beach State Historic Park (8c39badd…)

**census 1 — T01/coords (severe).** "Wikidata P625 is **235.60 km** from the stored point".
*Finder:* Wikidata Q7178910 `P625 = 58.301061, -134.413121` — and enwiki's own GeoData
coordinates are the same point (#4). The enwiki **text** (#4) says "Located on the shore of
Wrangell, Alaska barely a mile out of town". `geonames.org` "Petroglyph Beach State Historic
Park" also returns 58.3011/−134.4131 (#20) — i.e. GeoNames is downstream of Wikipedia, not an
independent witness.
*Reviewer (own sources, both official/OSM):* the Alaska Department of Natural Resources page
(#28) gives "Address: **Grave Street, Wrangell**" and "Driving Directions: 1 mile from the
ferry terminal"; OSM (#18, #66) shows `Grave Street` in Wrangell with centroids
56.48134–56.48333 / −132.38851…−132.39254 — the stored point is on it; and the Wikidata point
is 0.4 km from the OSM node `Juneau` (58.3019613 / −134.4196751, #23).
*Verdict:* **CORRECT — the census lead is REFUTED.** Wikipedia's coordinate (and therefore
Wikidata's, and GeoNames') is downtown Juneau; the stored value is the real beach. No write.

**census 2 — T02/outside-polygon (cosmetic).** "lies 1.1 km outside the United States of
America polygon … Natural Earth places it in no country polygon (open water)".
*Reviewer:* the point is on Wrangell Island; the official page places the site in Wrangell,
Alaska (#28). Natural Earth's generalized coastline is 1.1 km away from a shore point.
*Verdict:* **CORRECT (country) — refuted.** This is the "Natural Earth resolution" class,
and 45 of the 117 T02 findings are exactly this class (measured; `COST.md` §6).

**census 3 — T05/spelling-split (moderate).** `USA` vs the snapshot's one `United States`.
*Finder/reviewer:* no factual error — both spellings name the same country, and
`ancient-nerds-map/src/utils/countryFlags.ts:233-234` maps both to `US`. But it is not pure
taste: the census note measures the consequence — "one country in two hub pages
(`/sites/usa` and `/sites/united-states`) and two entries in the globe's country filter". So it
is a real defect with a user-visible effect and **no** factual component; the fix is a
vocabulary decision (which spelling is canonical) that no module in the repo declares.
Measured: 28 sites `USA`, 1 `United States`.
*Verdict:* **CORRECT as a fact; `proposal=review`.** This belongs to the decision lane, not to
the finder: it cost a Phase-3 find + review to produce a question for a human, and it will do so
28 more times.

The other six fields: `name` (the enwiki title; the managing agency's designation is
"Petroglyph State Historic Site" — a faithful copy of the source's title, not an error),
`period_start -5000` / `period_name "< 4500 BC"` (ASP page: "The site itself is about 8000
years old" → ≈ 6000 BC, inside the bucket; both the BP and the BC reading land there),
`site_type "Petroglyphs"` (a canonical fixed point, more specific than Wikidata's
`P31`), `description` and `card_description` (both corroborated word-for-word by the official
page: "highest concentration of petroglyphs in the southeast region of Alaska", "became a State
Historic Park in 2000", "At least 40 petroglyphs", "about 8000 years old"). All **CORRECT**.

Note for instrument suspicion: enwiki's text here is a near-verbatim copy of the Alaska State
Parks page, so "two sources" would have been one. The official page is treated as the source of
record and the agreement is reported as derivation, not corroboration.

### 3.3 Pannonian Limes (db85cd62…)

**census 1 — T01/country (moderate).** "stored country normalises to 'HR', Wikidata P17 to
['AT']".
*Finder:* Wikidata Q471153 `P17 = Q40` (Austria) (#5); enwiki (#6, #35) and hrwiki (#34,
"Panonski limes"): "sjeverni dio dunavskog limesa; … 420 km … od Klosterneuburga u današnjoj
Austriji do Beograda (Singidunum)", "car August od 14. pr. Kr. do 31. godine" — a frontier
through Austria, Slovakia, Hungary, Croatia and Serbia. limescroatia.eu (Archaeological
Museum Osijek, the Croatian reference point for limes research, #61/#62) lists the Croatian
section as the sites Batina … Ilok.
*Verdict:* **WRONG → review.** The stored single value is not a description of a five-country
frontier, and it contradicts the record's own coordinate (in Serbia) and its own description
("stretching approximately 420 km from Austria to Serbia"). No scalar replacement exists;
this is a scope decision — keep one multinational record with no single country, or split it
into national segments. The census's lead (`P17 = Austria`) must **not** be used as the fix:
Austria is no more the site's country than Croatia is.

**census 2 — T02/outside-polygon (moderate).** "point (44.00010, 20.99992) lies 182.2 km
outside the Croatia polygon … Natural Earth places it in Republic of Serbia".
*Reviewer:* true and useful, but not as a *country* error — as an internal contradiction of the
row. It is the only signal that led to the coordinate defect below.
*Verdict:* **confirmed as an inconsistency**, no field proposal of its own.

**census 3 — T03/all-outside (severe).** "card_description dates the site to 5th century AD
(1 - 500 AD), but the declared period is 500 BC - 1 AD".
*Finder/reviewer:* the card's only dated claim is the **end** of the frontier ("defended from
the time of Augustus to the 5th century AD"), while the declared bucket covers the
**beginning** (Augustus, 31 BC–AD 14). The inception lies inside `500 BC - 1 AD`
(`categorize_period(-500) = "500 BC - 1 AD"`, `categorize_period(1) = "1 - 500 AD"`; the
Augustan start is 31 BC).
*Verdict:* **CORRECT — the census lead is REFUTED** (false alarm; `BRIEF_GAPS.md` §7.1 records it as a
missing §4.3 pattern). `period_name` unchanged.

**New defect 1 — lat/lon (moderate), the census never named it.** Wikidata has **no `P625`**
for Q471153 (#5), so T01/coords had nothing to compare, and T02 could only say "outside
Croatia".
*Reviewer (own measurement):* Overpass `waterway=river name=Дунав` around the stored point
(#75) returns the nearest Danube geometry **82.7 km** away (44.7437, 20.9918). The Pannonian
Limes *is* the Danube line. The stored point is a village (`Јабучје`, 43.99911/20.99020, ~1 km)
in central Serbia.
*Verdict:* **WRONG → review.** A 420 km linear frontier has no representative point;
`lat`/`lon` are `NOT NULL` (FIELD_CONTRACT §3), so `clear` is not available either. A human
must decide (e.g. the frontier's midpoint, or a re-scope to one fort).

**New defect 2 — description (moderate).** "The Pannonian Limes **in Croatia** is a segment of
the Roman Danubian frontier stretching approximately 420 km **from Austria to Serbia**": the
first clause scopes a multinational frontier to Croatia and the second contradicts it.
*Verdict:* **WRONG → review** (a text rewrite; **not** a database-only edit — see
`FIELD_CONTRACT.md` §2.3: `card_stats.card_description` is overwritten at every API boot by the
import called from `api/main.py:506` (`api/services/card_descriptions.py:42-48`, `ON CONFLICT …
DO UPDATE SET card_description`; authoritative file `public/data/card_descriptions.json` at
`:35`), and the plan's Phase 5 is the route for card texts. The same is true for the generated
`description`).

`name`, `site_type` ("Fortress/citadel" is a canonical fixed point; "Fortification" would be
closer — a taxonomy decision, not a source question), `period_start`/`period_name` and
`card_description` (420 km and the Augustan start are corroborated by hrwiki) are **CORRECT**.

### 3.4 Karpasia - Town (e2dbb087…)

**census 1 — T01/coords (moderate).** "Wikidata P625 is 3.52 km from the stored point".
*Finder:* Wikidata Q1734309 `P625 = 35.61994444, 34.35175`; enwiki's GeoData is
35.59639/34.37806 — **exactly the stored point** (#8) — and enwiki's image caption says
"Ayios Philon Church, situated at the site of Karpasia" while the Princeton Encyclopedia of
Classical Sites entry is titled "**KARPASIA (Haghios Philon) Cyprus**" (#59).
*Reviewer (own sources):* Pleiades 707526 (#30) carries a DARMC representative point
35.626206/34.369934 and types settlement+port; OSM (#76) has a node
`Ayios Philon Roman harbor` at 35.63473/34.39794. Three independent witnesses put the ancient
site at Ayios Philon, **3.4 km / 3.5 km / 4.6 km** (measured) from the stored point, which is the
centre of modern Rizokarpaso — and the record's **own description** says the ancient city was
"located 3 km from modern Rizokarpaso".
*Verdict:* **WRONG → review.** The stored value is the modern town, and the row contradicts
itself; but the three candidates disagree by 1.2 km, so no value is fit to write.
Coordinates also illustrate a structural limit: FIELD_CONTRACT §4.6 and anti-pattern 4 make
coordinate corrections `review` by contract, not by evidence quality.

**census 2 — T02/outside-polygon (moderate).** "lies 68.1 km outside the Cyprus polygon …
Natural Earth places it in Northern Cyprus".
*Reviewer:* the Karpas peninsula is administered by the unrecognised TRNC; the Karpasia
article's Wikidata `P17 = Q229 Cyprus` (#7), Pleiades places the site in Cyprus (#30), and
ENRICHMENT_AUDIT anti-pattern 7 forbids current UN-unrecognised country names.
*Verdict:* **CORRECT — refuted.** A de-facto-borders artifact (`BRIEF_GAPS.md` §7.5).

**census 3 — T03/all-outside (severe).** "card_description dates the site to 334 BC (500 BC -
1 AD), but the declared period is 1500 - 500 BC".
*Finder/reviewer:* 334 BC is **Zeno of Citium's birth year**, not a date of the site. The
site's foundation is the 7th century BC (enwiki) / archaic 750–550 BC (Pleiades), both inside
`1500 - 500 BC`.
*Verdict:* **CORRECT (period) — refuted**; the wrong thing is the card (§ below).

**New defect — card_description (severe), the census never named it.** "An ancient Greek
city-kingdom founded by Phoenicians. Its most famous resident, Zeno of Citium (born c. 334 BC),
founded Stoic philosophy."
*Reviewer (own source):* Wikidata Q171303 (Zeno of Citium) has `P19` (place of birth) **and**
`P27` (citizenship) = `Q1743884`, fetched and resolved separately (#72, #73) as **"Kition —
ancient Phoenician city and kingdom in Cyprus"** — a different Cypriot city, ~102 km away in a
straight line on the south coast. **Weakest evidence in this batch, and it is labelled as such:**
britannica.com was tried for the same claim and blocked (403, recorded in `failed_source_probes`
in `PILOT.jsonl`), so the two facts above are both Wikidata — one source family, not two. If
Wikidata is wrong about Zeno's birthplace, this specific verdict falls; every other WRONG verdict
in this batch rests on two families. It is kept as WRONG because "Zeno of Citium" is the
standard epithet (Citium = Kition = Larnaca) and the claim is the card's alone — but the reader
should see the seam.
*Verdict:* **WRONG (severe) → review.** A false biography claim on a card that is read aloud
(cf. `shorts_tts.py`); the fix is a Phase-5 card rewrite (JSON file, then DB), not a SQL
update. Second clause of suspicion: "ancient Greek city-kingdom … founded by Phoenicians" is
internally odd (the same sentence gives the city a Phoenician founder), and nothing fetched here
settles whether Karpasia counts among the classical Cypriot city-kingdoms: Pleiades types it
"settlement, port" and Wikidata `P31` calls it a human settlement / ancient city / polis.
Left open.

**census: nothing else.** The name `Karpasia - Town` is **CORRECT**: `Name - Qualifier` is a
house pattern measured on 97 of 5,004 sites ("Akrotiri - Prehistoric City", "Armeni -
Archaeological Site", …). `site_type` matches Pleiades' types; the `description` matches
enwiki and the Princeton entry; `period_start -1500` is a bucket lower bound (648 of the 987
sites in that bucket use it) and the real dating is in the same bucket.

### 3.5 Didnauri (593de422…)

**census 1 — T01/coords (moderate).** "Wikidata P625 is 2.86 km from the stored point".
*Finder:* Wikidata Q26001314 `P625 = 41.43, 46.1953` with precision `2.78e-06` (0.3 m — not
credible for a field-surveyed 1.5 km site, #9); enwiki's infobox coordinate
`41°24′53″N 46°13′23″E` = 41.414722/46.223056 is the stored point (#10, #27).
*Reviewer (own source):* OSM (#52, #53) contains **two ways tagged `wikidata=Q26001314`**,
`name = დიდნაურის ნაქალაქარი`, `historic=archaeological_site`,
`archaeological_site=settlement`, `ruins=fort`, `historic:period=iron-age`; the larger one
spans lat 41.41159–41.41729, lon 46.21381–46.23019 (measured 0.63 × 1.37 km) and the **stored
point lies inside it**, 73 m from the polygon's centre, while the Wikidata point lies 2.09 km
north-west of the polygon. mapcarta (#46) repeats 41.41444.
*Verdict:* **CORRECT — the census lead is REFUTED.** The DB's point is the site; Wikidata's is
off it. Third coordinate finding in this batch where the DB side survived.

**census 2 — T03/all-outside (severe).** "card_description dates the site to 12th–9th century
BC (1500 - 500 BC), but the declared period is 3000 - 1500 BC".
*Finder/reviewer:* here the **card, the description and the field disagree, and the card is
right**: the record's own description says "a Late Bronze Age/Early Iron Age settlement", the
card says "12th–9th century BC", enwiki says the Georgian team dates it to the 12th–9th
centuries BC (#10), and OSM tags the site `historic:period=iron-age` (#52).
`categorize_period(-1500) = "1500 - 500 BC"`.
*Verdict:* **WRONG → `set period_start = -1500`, `set period_name = "1500 - 500 BC"`**
(two-source: enwiki + OSM; the record's own text agrees). Confirmed.

**census 3 — T05/disambiguated (severe).** `Georgia (country)` → `Georgia` — same evidence as
Satsurblia. **WRONG → `set "Georgia"`** (authoritative).

`name`, `site_type` (OSM `archaeological_site=settlement`), `description`,
`card_description` and `lat/lon` are **CORRECT**.

## 4. What the 15 census findings turned out to be

(base: the 15 census **findings**, not the 40 (site, field) pairs of §2)

| outcome | n | findings |
|---|---|---|
| real error, mechanically applicable fix | 4 | Satsurblia T03, Satsurblia T05, Didnauri T03, Didnauri T05 |
| real defect → human decision | 4 | Satsurblia T01/coords (unresolved), Pannonian T01/country, Pannonian T02/outside-polygon, Karpasia T01/coords |
| refuted (false alarm) | 6 | Petroglyph T01/coords, Petroglyph T02, Pannonian T03, Karpasia T02, Karpasia T03, Didnauri T01/coords |
| true but not a factual error (decision item) | 1 | Petroglyph T05/spelling-split |

4 + 4 + 6 + 1 = 15. **Refuted as false alarms: 6 of 15 (40 %).** Contrast the plan's own
pilot figure of 61 % (`REVIEWER_BRIEF.md:4`) — but read §0: one agent played both stages, so
40 % is an upper bound on what a separate reviewer would achieve, not a comparable measurement.

T03 was the worst test in this batch: **4** findings, **2 right, 2 false alarms** (Pannonian: the
only dated claim is the terminus; Karpasia: the date belongs to a person born elsewhere;
Satsurblia and Didnauri: right, and the *bucket* was the broken end). T01/coords: **4** findings,
**0 writable**, 2 refuted outright (Petroglyph 235.6 km, Didnauri 2.86 km — in both, Wikidata
was the wrong side), 1 unresolved (Satsurblia, 1.28 km inside Wikidata's own precision) and 1
confirmed-wrong-but-review (Karpasia). T02: 3 findings, all refuted as
data errors (2 Natural Earth artifacts, 1 row-internal contradiction that was useful anyway).

## 5. Defects the census did not name

Three, on 3 of the 5 sites — i.e. the batch produced more *new* real defects than writable
corrections:

1. **Pannonian `lat/lon`** — 82.7 km off the Danube, measured; invisible to T01 because
   Wikidata has no `P625` for this item, and to T02 because T02 only asks about the country.
2. **Pannonian `description`** — a multinational frontier presented as Croatian, in a sentence
   that contradicts itself. No census check reads the description's *scope* claims.
3. **Karpasia `card_description`** — a false "most famous resident" claim (Zeno of Citium,
   born in Kition). No census check reads the card's *facts*; T03 reads only its dates and
   T01/name reads only its identity.

That is the structural gap: the T-series verifies **values against external sources**, but
nothing verifies the **prose** (card and description) against sources, and the prose is what is
read aloud. Two of the three new defects are prose.

## 6. Ledger of what this pilot did and did not establish

**Established (measured).**
* 15.2 fetches per site (76 fetches / 5 sites: 62 finder, 14 reviewer), 19 of 76 non-200
  (25 %) — §3 of `COST.md` has the per-site table.
* 28 of 40 (site, field) pairs CORRECT, 11 WRONG, 1 UNVERIFIABLE.
* 6 of 15 census findings refuted as false alarms (40 %); at the (site, field) level the human
  queue is **6 items**: 5 WRONG→`review` plus 1 UNVERIFIABLE→`review`; 3 of the 6 are
  coordinates, 2 are prose (1 description, 1 card) and 1 is a multinational country.
* 2 mechanically applicable LLM-derived corrections across 5 sites (the two period fixes,
  i.e. 4 field-level `set`s) and 3 new defects the census never named.
* The eight overlap sites belong to Phase 3 (§1.1).
* The instrument limits: Nominatim unusable (403 ×5); GeoNames is *not* independent of
  Wikipedia for at least one site (Satsurblia: 42.3772/42.6009 = the DB value while Wikipedia
  says 42.388/42.606 — so wherever the DB's coordinate "agrees with GeoNames", that is not
  corroboration); the enwiki text of Petroglyph Beach is a near-copy of the Alaska State Parks
  page, so agreeing sources must be checked for derivation, not just counted.

**Not established (do not read a rate out of this batch).**
* Token cost per site. Not measured here — no token instrumentation in this role. `COST.md`
  shows the arithmetic under both of the plan's anchors and refuses to average them.
* A false-negative rate. Five sites with 3 findings each, produced by a worklist that selected
  them *because* they had findings, cannot estimate how many of the 1,813 sites are clean.
* Whether a *separate* reviewer agent refutes more or less than this one did.
* Whether the 3 new defects are typical: n = 3.

## 7. Reproduction

```bash
cd C:/PythonProjects/AncientMap/output/remediation/phase3_pilot
C:/PythonProjects/AncientMap/.venv/Scripts/python.exe http_get.py <stage> <label> <url>   # logs + saves
python - <<'PY'   # or by hand: every claim above is in evidence/ and fetch_log.jsonl
PY
C:/PythonProjects/AncientMap/.venv/Scripts/python.exe build_pilot_jsonl.py                 # PILOT.jsonl
```

`fetch_log.jsonl` is append-only; `evidence/` holds the raw bodies (URL-encoded labels).
Everything in this document is traceable to one of those two places.
