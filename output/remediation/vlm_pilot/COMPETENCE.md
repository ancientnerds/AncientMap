# Is the vision model competent? Measured, not assumed

**Date:** 2026-09-21. **Model:** `deepseek-v4-flash-vision-exp`, 200 calls, one per tile.
**Status of the previous claim:** the G0 gallery audit was signed off with an explicit open caveat —
"reachable, capability proven, semantic competence unverified". This document closes or narrows that
caveat with a measurement. It does not remove it.

## Why it matters

`image_kind` decides whether a gallery image counts as clean, and the plan counts only `'site_photo'`
as clean. If the model over-calls `site_photo`, the audit under-counts soiled images and reports a
healthier gallery than exists. That is exactly the failure mode a number can hide, so the check has to
be behavioural: does the label agree with a human looking at the same picture?

## Method

- 200 real rows drawn from the 49,691 `wiki_images` snapshot, seed `20260921`, **stratified 50 per
  T10 tier** — A `hero`, B `suspect`, C `grey`, D `clear` (the four buckets the T10 lane derived).
- Tiles are **blinded on purpose**: no filename, no title, no site name, no tier label is printed on
  the picture (`SHEETS.json` records that decision). The model sees only pixels, so the verdict cannot
  be read off metadata.
- Ground truth is a **supervisor eye-labelling pass over tiers A and B (100 tiles)** from the contact
  sheets, compared tile by tile against the model's verdict. Tiers C and D were not eye-checked.
- Raw record: `VLM.jsonl` (one row per tile: verdict, raw response, latency, usage), `SAMPLE.jsonl`
  (what each tile is), `MAPPING_PROOF.json` (that a snapshot row resolves to a real image file),
  `REJECTED_KINDS.jsonl`, `SHEETS.json`.

## Run facts (measured)

| quantity | value |
|---|---|
| verdicts parsed | 200 of 200 |
| errors | 0 |
| `finish_reason` | `stop` for all 200 |
| attempts | 195 first try, 4 second, 1 third |
| median latency | 11.2 s per tile |
| wall clock | 735 s |
| cost | $0.35088 total (≈ $0.00175 per tile) |

A side effect worth recording: the earlier belief that this gateway fails the large majority of calls
(measured once as 664 failures in 733) does **not** reproduce here — 0 failures in 200 and 97.5 % first
attempt. Whatever that figure described, it was not this endpoint under this client.

## Result 1 — the model does not reproduce the tier boundaries

`site_photo` share of each tier's 50 tiles:

| tier | meaning | `site_photo` | rest |
|---|---|---|---|
| A | hero | 37 (74 %) | 5 map_or_document, 4 other, 3 painting, 1 artifact |
| B | suspect | 20 (40 %) | 18 artifact, 8 map_or_document, 2 other, 2 painting |
| C | grey | 36 (72 %) | 5 artifact, 4 other, 2 painting, 2 people, 1 map |
| D | clear | 38 (76 %) | 5 other, 4 artifact, 2 map, 1 painting |

Tier B is clearly separated (40 %), which shows the model is reacting to something real. But C and D are
nearly identical (72 % vs 76 %) although they are different tiers — so the model does **not** see the
boundary the metadata drew between "grey" and "clear". That is not automatically a model failure: tier
C's only signal is "the site name is not in the filename", a weak metadata property that need not be
visible in a picture. It is a reason not to treat agreement with the tiers as the competence test.

## Result 2 — eye-checked: competent on rejection, over-inclusive on `site_photo`

**Tier B (suspect), all 50 tiles** — agreement is high, roughly nine in ten. More useful than the rate:
in three disagreements **the model was right and I was wrong**.

- B07 `KSZO_Ostrowiec_stadion_01` — I read a colonnade, the model said `other`. It is a football
  stadium, and `other` is correct. A museum-style false negative avoided.
- B41 `Combat Begram Guimet` — I read in-situ red rock art, the model said `artifact`. It is a museum
  object. Model correct.
- B06 `Durres_amfi.basilica_mosaic_2` — I read a line drawing, the model said `site_photo`. It is a
  basilica mosaic. Model plausibly correct.

**Tier A (hero), all 50 tiles** — this is where it degrades. The model called 37 `site_photo`; my labels
accept about 20. The excess is **generic landscape**: empty fields (A18, A22, A25), hillsides (A19,
A35), a pond (A17), a coastline (A29), a road through fields (A43), a terrain/aerial view (A39). And one
**hard error**: A08 `#66405` is a 19th-century engraving of a building, returned as `site_photo`. An
engraving is not a photograph of a site by any definition in the plan.

So the failure is asymmetric, and that asymmetry is the actionable finding:

- **Rejecting documents, objects and people is reliable.** Obvious engravings, plans, museum objects,
  skulls, portraits and people-in-frame were classified away from `site_photo` with few misses by
  inspection (A01 drawing, A13 frieze, A15 aerial, A26 ornament, A34 plan, A09 skull, A37 person,
  A38 object, B25 portrait, B39 gold vessel, B47 museum case).
- **`site_photo` is over-inclusive: it means "an outdoor photograph", not "a photograph of the site".**

## What this changes

1. **The G0 caveat becomes bounded rather than open.** Competence is no longer "unverified"; it is
   measured with a named error mode. The 105 landed rows and any later use may rely on the model for
   *negative* judgements (this is a map, an object, a person, a drawing) far more safely than for the
   positive one.
2. **`site_photo` must not be read as "this picture shows the archaeology".** For anything that depends
   on the positive claim — the §7 shorts gate's image supply, the gallery's cleanliness count — treat
   `site_photo` as an upper bound on clean images, and re-check the hero-tier rows specifically, since
   that is where the over-call concentrates (74 % claimed, ~40 % accepted).
3. **Strictness needed for the positive claim:** a second pass whose prompt demands visible
   archaeological structure, or a rule that requires corroboration (e.g. the model's verdict plus the
   existing per-row signals) before a hero image counts as clean.

## Limitations, stated plainly

- Ground truth is **one thumbnail pass by the supervisor**, not an independent human panel; tiles are
  judged at contact-sheet resolution. A stricter panel could move the numbers either way.
- Only tiers **A and B** were eye-checked (100 of 200 tiles). C and D rates are the model's own.
- No **repeat-call stability** test was run, so verdict jitter is unmeasured.
- `map_or_document` and `painting_or_artwork` were accepted as "not a site photo" without distinguishing
  them from each other, which is all the decision needed.
- The 200-tile sample is stratified by tier, not random over the 49,691 rows, so these rates describe
  the tiers, not the corpus as a whole.
