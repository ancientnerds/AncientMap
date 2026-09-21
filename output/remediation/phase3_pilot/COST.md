# COST — one batch of five sites, two stages

Companion to `PILOT.md`. Everything here is measured in this pilot unless marked
*derived* or *from the plan*.

## 1. Instruments — what is measured, what is not

| quantity | value | how |
|---|---|---|
| HTTP fetches, total | **76** | `fetch_log.jsonl` (append-only, one line per request) |
| … finder stage | 62 | `stage` field |
| … reviewer stage | 14 | `stage` field |
| fetches per site | **15.2** | 76 / 5 |
| non-200 responses | 19 (25 %) | 403 ×8, 404 ×3, network error ×5, 504 ×2, 429 ×1 |
| bytes fetched (200 only) | **2,343 KB** (469 KB/site) | sum of `bytes` in `fetch_log.jsonl` |
| evidence files | 76 | `evidence/` (one per fetch, URL-encoded label) |
| research wall clock | 11.2 min | first → last fetch timestamp in the log |
| batch wall clock, end to end | **16.2 min** | first fetch → `PILOT.jsonl` on disk (file mtime); `PILOT.md` at 14.4 min |
| seconds per fetch incl. the model turns around it | ~8.8 | 11.2 min / 76 |
| tokens | **not measured** | no token instrumentation in this role — see §5; do not guess |
| agent turns / tool calls | **not exactly countable from here** | the pre-compaction part of the session is not in my view. Bounded: ≥45 shell invocations in the retained window, many of which carried 2–6 fetches. Treat the fetch count as the reliable instrument and the turn count as approximate. |

## 2. Per-site fetch ledger

| site | fetches | of which reviewer | bytes (200) | non-200 |
|---|---|---|---|---|
| Satsurblia Cave | 13 | 5 | 1,141 KB | 2 |
| Petroglyph Beach SHP | 17 | 2 | 484 KB | 5 |
| Pannonian Limes | 13 | 1 | 133 KB | 2 |
| Karpasia - Town | 12 | 6 | 271 KB | 6 |
| Didnauri | 19 | 0 | 286 KB | 4 |
| two instrument probes (`Misc/`) | 2 | 0 | 29 KB | 0 |

Failure detail, because a failed fetch is a real cost and a hidden risk: Nominatim **403 on
5 of 5** attempts (unusable, not a rate limit — first contact also 403); `html.duckduckgo.com`
connection-reset while `lite.duckduckgo.com` worked; Overpass 504 ×2 (one retried OK, one acted
as a trigger to query narrower), 429 ×1 (retried OK); britannica.com 403; trek.zone 403;
plato.stanford.edu returned a 380-byte JS shell and iep.utm.edu/zeno/ served an unrelated
article (`liar_paradox`); the Alaska State Parks page needed a
search-engine hop because the first guessed URL 404'd. **One in four requests bought nothing**,
and every one of them still cost a turn.

## 3. The size lever (measured, and the cheapest thing in this report)

The six largest pages are **69.9 % of the 2,343 KB that arrived with a 200** — and **65.1 %** of
the 2,516 KB that arrived in total, failures included. One definition per number: the six rows
below, summed, over the denominator named in the sentence. *As first published here the line read
"**70 % of all fetched bytes**", which mixed the two definitions — it sorted by delivered bytes (so
the 105 KB 404 page counted) but divided by the 200-only total. No conclusion changes.*

| page | bytes |
|---|---|
| OSM bbox dump around Satsurblia (raw geometry) | 598 KB |
| OSM bbox dump around Petroglyph Beach (raw geometry) | 400 KB |
| PLOS ONE e111271 (full article HTML) | 231 KB |
| georgia.to Satsurblia page | 183 KB |
| Wikidata Q171303 (Zeno) | 121 KB |
| travelguide.ge (404) | 105 KB |

The two OSM bbox dumps alone are **1.0 MB of 2.34 MB** and were fetched only to find one or two
named features in a 2 km box — a name-filtered Overpass query does that in 4 KB or less (measured
on this pilot: the named-feature queries for **Petroglyph** returned 4.1 KB and 287 bytes. *The
line first published here read "the named-feature queries for Petroglyph and for Satsurblia's box
returned 4.1 KB and 287 bytes respectively" — there is **no Satsurblia Overpass query** in
`fetch_log.jsonl`, and both 287-byte responses are Petroglyph queries (`Petroglyph/overpass` and
`Petroglyph/overpass_bbox`). The Petroglyph pairing is the stronger evidence anyway: 400 KB of raw
bbox dump against 287 bytes for the same box.*) **Derived:** at ~4 characters
per token, *if* every fetched byte entered the agent's context, the batch would be ≈ 585–600 k
tokens (117–120 k/site, the range being decimal vs binary KB) — roughly 3× the plan's own
40 k/site anchor for the fetch text alone. The
pilot stayed below that only because parsing scripts extracted fields from the two dumps instead
of reading them; that is a discipline the batch runner has to impose, not a property of the work.

## 4. Wall clock (measured, one agent)

* Research 11.2 min, batch end to end **16.2 min** for 5 sites → **3.2 min/site**, write-up
  included.
* *Derived:* 363 batches sequentially ≈ **98 h** of agent wall clock (363 = the plan's 5 sites per
  batch; at the ratified 15 sites per run it is 121 batches per stage — `BATCH_PLAN.md`); at 36
  concurrent runs ≈ **2.7 h**.
* The plan's own run-1 anchor (`BATCH_PLAN.md` §Wall clock: 3,653,051 tokens / 37 min at 10–14
  parallel; 180 sites) implies **7.4 min per site per agent** (37 min / 5 sites per agent).
  This batch ran **3.2 min/site**, i.e. 2.3× faster — but its agent did both stages with no
  handoff and no queueing, so treat the two numbers as a bracket, not as a correction: the plan's
  37 min probably includes agent startup and scheduling that one sequential batch does not.
* Caveats, in order of importance: (a) one agent played both stages, so there is **no handoff
  latency** and no second context bootstrap — a real two-agent batch is slower per batch;
  (b) five sites with dense findings were researched by an agent that already knew the five
  record bodies; (c) wall clock is not what the plan budgets in, tokens are.

## 5. Tokens — the plan's two anchors disagree by 2× and I will not average them

The plan (`phase3_worklist/BATCH_PLAN.md`, §"Measured / plan inputs") carries two anchors that
cannot both be right:

* **Anchor A — "~40,000 tokens/site" (both stages)**, from the plan §13 "measured anchor".
* **Anchor B — run-1 = 36 agents / 3,653,051 tokens / 37 min**; read at 36 agents × 5 sites =
  180 sites, that is **20,294.7 tokens/site** (≈ 20,295; *first published here as "20,293" — the
division was written out, so it is corrected to the true quotient rather than rounded away*).

Side by side, neither averaged (the plan itself shows both readings; it flags the same 2×):

| | per site (both stages) | total for 1,813 sites | per batch of 5 (both stages) | per agent run (one stage) |
|---|---|---|---|---|
| **Anchor A** | 40,000 | 1,813 × 40,000 = **72.5 M** | 200,000 | 100,000 |
| **Anchor B** | 20,294.7 (≈ 20,295) | 1,813 × 20,295 = **36.8 M** | 101,474 | 50,737 |

*The Anchor B row first read "20,293 / 36.8 M / 101,500 / 50,700": the total is unchanged at this
precision, the two right-hand cells were rounded from the wrong base (they now follow the true rate
20,294.7: 5 × 20,294.7 = 101,473.5, and half of that per stage).*

So the *total* swings 2× (36.8 M vs 72.5 M) purely on which anchor is believed — and the *run
count* swings 18×, because the two anchors imply different batching: 5 sites per agent gives
**726 runs** (363 finder + 363 reviewer, the plan's own arithmetic), while 40,000 tokens/site
implies run 1 covered only ~91 sites, i.e. **~20 runs per stage / ~40 runs in total**. 726 agent
lifecycles is not the same purchase as 40, because each lifecycle pays the fixed context
overhead. *Derived from the project's own measurement* (`AGENTS.md`: fixed system-prompt +
tool-definition overhead ≈ 31,500 tokens per lifecycle): 726 runs ≈ **22.9 M tokens of overhead
alone**, 40 runs ≈ **1.3 M**. That difference is larger than the whole anchor uncertainty of the
20-run reading.

**This pilot does not settle the anchor question** — it has no token measurement. What it does
contribute: 15.2 fetches and 469 KB of fetched text per site (upper bound 117 k tokens/site if
read raw, §3), a 25 % fetch failure rate, and a 16.2 min/batch wall clock. For the money, the
plan's own derivation stands unchanged: ~$286 for 1,813 sites at the plan's `$0.158/site`
(`BATCH_PLAN.md` §Cost) — plan-derived, not measured here, and still gated on the same anchor
choice.

## 6. The structural cost finding: what Phase 3 can actually write

Measured over the whole phase-3 worklist (`WORKLIST.jsonl`, 1,813 sites, 2,210 findings):

| | n | share |
|---|---|---|
| findings with `proposal=set` | **8** | 0.4 % |
| findings with `proposal=review` | 2,202 | 99.6 % |
| T01 findings (Wikidata-vs-stored) | 1,175 | all `review` |
| T02 findings (Natural Earth polygon) | 117 | all `review` |
| T03 findings (years in text) | 875 | all `review` |
| T05 findings (country hygiene) | 43 | 8 `set`, 35 `review` |
| sites whose findings are *only* T01/coords | **285** | 15.7 % of sites |

The 8 `set` findings are exactly the eight overlap sites' country fixes (§1.1 of `PILOT.md`) —
i.e. the ones the mechanical lane would have done anyway. Consequence: under the applier rule
"only `refuted=false` *and* `proposal=set` is written", **Phase 3's own machine yield before the
reviewer upgrades anything is zero**, and 285 sites (with their 2 × 285 agent runs) can never
produce a write at all, because FIELD_CONTRACT §4.6 makes every coordinate correction a human
review by contract.

**Amended 2026-09-21 (Wave 7) — the second half of that sentence is not what the cited rules say,
and it changed the Phase-3 scope.** Both rules (FIELD_CONTRACT §4 item 6, ENRICHMENT_AUDIT
anti-pattern 4) speak only about **coordinate** findings, while the claim made was about those
sites' **writes in general**. Supported is the narrower statement: **no *census finding* of these
285 sites is writable** — re-verified on `WORKLIST.jsonl` (285 records whose only finding is
`T01/coords`, one finding each; 202 `moderate`, 83 `severe`), and a coordinate correction is human
review by contract. **Not** supported is "those sites can write nothing": the census says nothing
about their other fields, and the pilot found three defects the census never named, **two of them
prose**. The 285 therefore stay in Phase 3: the scope is **1,813 sites, not 1,528** (decision 12's
exclusion is superseded — `BATCH_PLAN.md`), and §7 item 3 below is withdrawn with it.

What the pilot adds to that: the reviewer *can* upgrade a `review` finding into a `set` — in this
batch 4 of 15 census findings (27 %) ended as writable `set`s (two periods, two countries) on 2
of the 5 sites. That is the value Phase 3 buys. It is **not** a rate: this batch is 5 of the only
**39** phase-3 sites that carry ≥3 findings (median site: **1** finding; mean 1.22), and 15 of
2,210 findings (0.7 %). The batch was deliberately the worst-first top of the worklist, so every
per-site figure here (6 `set`s, 15.2 fetches, 3 new defects) is biased **upward** relative to the
1,813-site average, and by an unmeasured factor. Do not multiply it out.

## 7. What I would change in the run, with the arithmetic

1. **Cap fetched bytes.** A 60 KB per-page cap would have kept the five largest pages out
   (1.5 MB → 0.3 MB) and cut the batch's fetched volume by ~55 % (§3), i.e. the whole fetch-text
   cost from ~586 k to ~260 k tokens, with no loss in this batch: every claim above rests on text
   that fits in 60 KB except the PLOS article, which a `?`-less abstract/full-text choice or the
   Europe PMC abstract service (measured, #71) covers.
2. **Fetch named features, not raw geometry.** The two OSM dumps cost 1 MB to answer what a
   filtered Overpass query answered in 4 KB or less (Petroglyph: 400 KB of bbox dump against
   287 bytes for the same box — *as first published "4 KB (Petroglyph) and 287 bytes (Satsurblia
   box)"; there is no Satsurblia Overpass query, see §3*).
3. **Withdrawn 2026-09-21: "Do not spend a finder+reviewer pair on the 285 coords-only sites"**
   (as first published: "… unless the plan intends to write coordinates, which §4.6 forbids.
   Deciding this before the run saves 570 agent runs — more than the entire difference between the
   plan's two token anchors."). The strong claim was unbacked (§6 amendment): the two cited rules
exclude a *coordinate write*, not a write on those sites, and the pilot found three defects the
census never named, two of them prose. **The 285 are in Phase 3**, so this saving does not exist.
   If runs must be saved, the lever is the batch size (decision 12), not a site class.
4. **Reviewer stage is cheap and should stay.** 14 of 76 fetches (18 %) bought 6 refutations and
   1 verdict the pilot left *unresolved* — the Satsurblia coordinate, which the 2026-09-21
   re-adjudication then settled as **WRONG** (`PILOT.md` §2.1), i.e. the reviewer's own evidence
   line was the defect. The highest-value fetches in the batch. Halving it would be false economy.
5. **Batch the de-facto-border T02 classes as one decision, not 117 reviews.** Measured
   composition of all 117 T02 findings: **45** "no country polygon (open water)" (Natural Earth
   coastline generalization — see Petroglyph, 1.1 km), **22** United Kingdom (points in Northern
   Ireland against `Ireland`), **9** Russia (Crimea), **7** Northern Cyprus, **4** "'Northern
   Ireland' matches no Natural Earth admin-0 feature", **2** Akrotiri Sovereign Base Area,
   **2 each** Peru, Turkey, Kosovo, Switzerland, Israel, **1** Baltic Sea, and **17** single cases
   (Jordan, Italy, Greece, Palestine, Armenia, Serbia, Pakistan, Tunisia, Guatemala, Hungary,
   Moldova, Senegal, Germany, Portugal, France, Monaco, Oman). None of the three T02 findings in
   this batch was a data error; 2 were artifacts and one was a *row-internal contradiction* that
   happened to locate a real defect (Pannonian). Treating T02 as one vocabulary decision plus a
   short exception list is a decision for a human, not 117 agent reviews.
6. **Never count a derived source twice.** GeoNames returned the stored Satsurblia coordinate
   *and* the Petroglyph/Wikipedia coordinate verbatim; enwiki's Petroglyph text is a near-copy of
   the Alaska State Parks page. Two agreeing URLs were one source in both cases.
