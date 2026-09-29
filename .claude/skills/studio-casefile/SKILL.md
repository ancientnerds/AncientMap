---
name: studio-casefile
description: Use when building or fixing a studio episode's casefile.json from a Theo paper or from web sources, when episode check or markers-export reports case-file, unverified-evidence or marker problems, or when choosing the claims, places, quantities, pictures, markers or distribution dots a studio video may show.
---

# Studio case file: the verified evidence an episode may show

## Overview

`<STUDIO_ASSETS>/episodes/<slug>/casefile.json` is the only source of the facts, places,
numbers and pictures that the script and the capture specs may show. Claude writes it. The
workflow `studio-casefile-verify` verifies every evidence item, and the workflow
`studio-marker-check` crop-checks every marker. The code enforces both: a script may use only
`verified` evidence, and a marker without an accepted `hits` blocks the episode.

Commands run from the checkout root as `./.venv/Scripts/python.exe -m pipeline.studio …`,
written `studio …` below. The episode must exist (skill studio-video, step 1).

## Shape (strict: an unknown or missing key is an error)

```json
{"version": 1,
 "paper": {"request_id": "<uuid>", "slug": "<published slug>", "report_sha256": "<hex>"},
 "topic_type": "A",
 "claims": [{"id": "c1", "label": "No one could move 800 t without machines",
             "by": "core claim", "icon": "weight", "status": "pending"}],
 "evidence": [{"id": "e1", "claim_id": "c1", "kind": "quantity",
               "statement": "...",
               "source": {"url": "https://...", "title": "...", "tier": 1, "license": "...",
                          "quote": "<one sentence, verbatim>", "locator": "<section, page>",
                          "source_id": "<dossier source id; optional>"},
               "paper_anchor": "ev-07",
               "verification": {"status": "unverified", "by": "", "at": "", "method": ""}}],
 "places": [{"id": "p1", "name": "Baalbek quarry", "lat": 33.99917, "lng": 36.20028,
             "site_id": null, "coord_source": "..."}],
 "quantities": [{"id": "q1", "label": "2014 block", "value": [1500, 1650], "unit": "t",
                 "basis": "sources differ: DAI 2014 vs Wikipedia", "evidence": ["e1"]}],
 "media": [{"id": "m1", "path": "media/stone_person.jpg", "license": "CC BY-SA 4.0",
            "attribution": "...", "source_url": "https://...", "depicts": "...",
            "markers": [{"id": "mk1", "box": [0.41, 0.52, 0.06, 0.2], "label": "1 PERSON",
                         "verified": "crop-check"}]}],
 "meter": {"hypotheses": ["Roman engineers", "An older, lost civilization"], "start": [50, 50]}}
```

`paper` and `paper_anchor` may be `null`. `kind` is one of fact, quote, quantity, date, image,
place. Ids are unique across the whole file.

## Steps

1. **Paper link.** With a paper, `paper` is episode.json's `{request_id, slug}` plus
   `report_sha256`, the hash of the published report:
   `./.venv/Scripts/python.exe -c "import json,sys; from pipeline.utils.card_provenance import text_sha256; print(text_sha256(json.load(open(sys.argv[1], encoding='utf-8'))['result']['report']))" <STUDIO_ASSETS>/papers/<id>/published_bundle.json`.
   Without one, `paper` is `null` and no item has a `paper_anchor`.
2. **Claims.** `icon` is one of the names in the `icon` enum of the ClaimBoard's `claims` items
   in `video/src/blocks/registry.json`; `label` ≤ 80 characters, `by` ≤ 40. `status` stays
   `pending`: verdicts come only from the script's `status` cues.
3. **Evidence.** `source` always carries url, title, tier, license, quote and locator. Two
   origins, one verbatim sentence of quote each:
   - *From the paper* (`papers/<id>/evidence.json`): `paper_anchor` is the entry's `ev-NN`,
     `source.quote` its `quote`, `source_id` its `quote_source_id`, and url, title and tier
     that source's in the dossier.
   - *From the web* (no paper, or a paper run without archived texts): open the page and copy
     one sentence verbatim into `source.quote`; `locator` says where it stands.
   - Every new item, and every item whose `statement` or `source` you edit, gets
     `"verification": {"status": "unverified", "by": "", "at": "", "method": ""}`. Never set
     `verified` yourself.
4. **Places.** The case-file coordinates are the ones every capture must use: pins and their
   labels (= `name`), platform `measure` and `proximity` points, a Mapbox take's centre.
   `coord_source` says where they come from. A place that is a curated site carries its
   `site_id`; a Mapbox fly-in or orbit with a `country` needs it, and that `country` must be the
   site export's country `c` of the site.
5. **Distribution dots** (#15, Q11) are not case-file places: they are the `site_ids` of the
   script's globe `distribution` take, curated `ancient_nerds` sites only (any other source's id
   is refused), 1-500 points together with at most 12 labelled case-file places. Find ids in the
   site export (current copy: skill studio-video, "Before the first step"):
   `./.venv/Scripts/python.exe -c "import json,sys; q=sys.argv[1].lower(); [print(r['i'], r['n'], r.get('c'), r['la'], r['lo']) for r in json.load(open('public/data/sites/index.json', encoding='utf-8'))['sites'] if r['s'] == 'ancient_nerds' and q in r['n'].lower()]" <name part>`
6. **Quantities.** Where sources differ, `value` is `[low, high]` (low < high) and `basis` says
   so. `evidence` lists existing evidence ids. A chart bar or ScaleZoom end that uses the id
   shows exactly this value and unit.
7. **Media.** Files under the episode's `media/`, each with licence, attribution, source URL and
   `depicts`. A marked picture carries no EXIF rotation (apply it to the pixels and drop the
   tag: the crop and the renderer must see the same pixels). Photorealistic AI
   imagery is refused unless episode.json sets `allow_ai_imagery` (`false` by default).
8. **Markers.** `box` is `[x, y, w, h]` as fractions of the stored pixels, tight on the object
   its `label` names; `"verified": "crop-check"` is required by the format, the proof is step 10.
9. **Verify evidence.** Run the workflow **`studio-casefile-verify`** (Workflow tool by name,
   `args` = the episode workspace path). It checks each item that is not yet `verified` against
   `source.url` and the verbatim quote, or with a `paper_anchor` against
   `papers/<id>/evidence.json`, and writes `verification = {status, by, at, method}`, leaving
   every other key untouched. `refuted`: fix the statement or drop the item. `unverified`: find a
   source that can be checked, or drop the item.
10. **Crop-check markers.** `studio episode markers-export <slug>` (it validates the case file
    first and lists every problem), the workflow **`studio-marker-check`** (`args` = the episode
    workspace path), then `studio episode markers-import <slug>`. `misses`: fix the box or
    remove the marker, then export again (a changed box, label or picture is a new task).
11. `studio episode check <slug>` (needs `script.json`) reports what is left: an unverified item
    the script uses, a marker without `hits`, a paper link or anchor that does not match.

## Picture rules (owner)

- A marker only where the crop check says `hits`; otherwise no marking.
- No measuring lines on oblique photos: a size comparison is a to-scale ScaleDrawing.
- Every comparison states its basis ("a bus: 12 m, about 12 t").
- No agents or characters (no Lyra, Theo or Ben), no title card.
- Maps are our globe or Mapbox takes, never a Google Maps screenshot.

## Never

- Mark an item `verified` or a marker checked by hand, or keep a `refuted` item in use.
- Change a verified item's statement or quote without resetting its verification.
- Put a coordinate, place name or quote into a capture spec that the case file does not hold.
