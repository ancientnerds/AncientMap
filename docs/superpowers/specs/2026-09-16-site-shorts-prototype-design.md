# Site Shorts Prototype (Machu Picchu)

**Date:** 2026-09-16
**Status:** Approved for prototype (user, 2026-09-16)
**Scope:** One vertical teaser video per site, prototype on Machu Picchu. Nothing in
this spec touches live pages, the database, or `public/`.

## Goal

A ~22 s vertical (1080×1920) teaser per site that can later be posted as a YouTube
Short and auto-played on the site detail page. The prototype proves the chain end
to end for one site; batch ordering, site-page embedding, and music are follow-ups.

## Inputs (all exist today)

| Input | Source | Machu Picchu |
|---|---|---|
| Card text (hook, ~165 chars) | `card_stats.card_description` | present |
| Rarity tier / score | `card_stats.rarity_tier`, `rarity_score` | 5 Legendary / 61 |
| Hero + gallery images with author + license | `wiki_images` (`original_url`, `is_hero`) | 13 images, 12 ≥ 1280 px |
| Coordinates | `unified_sites.lat/lon` | present |
| Country, name, slug | `unified_sites` | present |

No new data sources. Images are fetched at original resolution from Commons into
`video-assets/` (gitignored), never into `public/`, so the 800 px web thumbnails
and the pages Google has indexed stay untouched.

## Timeline (target ~25 s, 60 fps, revised 2026-09-16 evening after user review)

The narration (card text, MiniMax voice) starts at t = 0 and runs over 1–2.

1. **Opening (6 s, one Mapbox clip)** — satellite globe with labels and site dots:
   1 s rotate onto the site from space, 2 s continuous zoom down to z14 while the
   camera tilts, 3 s 3D terrain orbit. Recorded with the Puppeteer recorder
   (`ancient-nerds-map/video/`, scene `short-opening`, portrait, 60 fps) on the
   Mapbox globe only, so the zoom never switches canvases. Satellite-streets style
   for labels, stock atmosphere instead of the app's dark fog, road/POI layers hidden.
2. **Stills (rest of the narration, ≈11 s)** — gallery photos cover-scaled to the
   full 1080×1920 frame, each panning left→right or right→left (portrait photos pan
   vertically), ≤3.5 s per still, hard cuts.
3. **Beat (1 s)** — cut to black.
4. **Reveal (7 s)** — hero image with slow zoom; site name, country, rarity ribbon
   fade in (Orbitron heading font, gold for Legendary); `ancientnerds.com` at 4.5 s.

The first cut (dark Three.js globe, 24 fps, terrain orbit under the narration,
blurred-fill Ken-Burns, voice after the approach) was rejected as boring; the
dark globe's satellite mode also rendered black in the recorder.

Attribution for every Commons image used (author, license) is rendered as a small
credit line during the reveal and written to `description.txt`.

## Components

### Python — `pipeline/video/`

- `shorts_export.py` — `export_site(session, site_id) -> dict`: card text, rarity,
  coords, hero + gallery images with attribution. CLI writes `site.json`.
- `shorts_tts.py` — narrates the card text via `pipeline.lyra.tts_generator.call_minimax_tts`
  (extended with a `voice_id` parameter; paper narration keeps its default).
  Writes `narration.mp3` and records its duration.
- `shorts_images.py` — downloads hero + gallery originals through
  `pipeline.lyra.image_fetcher.download_candidate` (Wikimedia throttle, SSRF guard).
- `shorts_render.py` — ffmpeg assembly: portrait scaling/cropping, Ken-Burns via
  `zoompan`, text via `drawtext` with the brand fonts converted to TTF, concat, mux.
- `__main__.py` — `python -m pipeline.video <site-id> --voice <id>` runs export →
  images → tts → render for one site; the globe clips are recorded separately by the
  Node recorder and picked up from `video-assets/shorts/<slug>/clips/`.

Pure functions (timeline math, drawtext escaping, attribution line) get unit tests
in `pipeline/video/tests/`. Network and ffmpeg steps are verified by ffprobe on the
outputs.

### Recorder — `ancient-nerds-map/video/`

- `record.ts`: `--portrait` flag → 1080×1920 window and viewport.
- `scenes/site-short.ts`: reads `video/input/site-short.json` (name, lat, lng, slug)
  and records `short-approach` (globe fly-to + zoom) and `short-terrain` (Mapbox
  satellite with terrain, orbit).
- Demo API additions (only active with `?demo=1`): `setTerrain(exaggeration)` adds
  the Mapbox DEM source and enables terrain; `mapboxOrbit(...)` animates bearing
  with synthetic time, same pattern as `smoothZoom`.

## Out of scope for the prototype

Music (user picks later, YouTube Audio Library), batch ordering (rarity vs.
Wikipedia pageviews — decision pending), React card reveal, site-page `<video>`
embed with `VideoObject` schema, Commons video clips, Sketchfab 3D.

## Verification

- `ffprobe` on `machu-picchu.mp4`: 1080×1920, ~22 s, H.264 + AAC.
- Frame stills at each timeline boundary reviewed visually.
- Unit tests green; `ruff` clean; `lint-imports` accepts the new package.
