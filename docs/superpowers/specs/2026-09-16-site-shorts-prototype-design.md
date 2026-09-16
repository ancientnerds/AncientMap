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

## Timeline (target ~22 s)

1. **Approach (3 s)** — globe from space rotates and flies to the site, zooms in.
   Recorded with the existing Puppeteer recorder (`ancient-nerds-map/video/`),
   portrait viewport.
2. **Narration (≈11 s)** — the card text, spoken by a MiniMax voice. Visual: Mapbox
   satellite terrain orbit around the site (pitch 60°, slow bearing sweep). If the
   terrain clip is unavailable, Ken-Burns over the gallery images.
3. **Beat (1 s)** — cut to black.
4. **Reveal (5 s)** — hero image with slow zoom; site name, country, rarity ribbon
   fade in (Orbitron heading font, gold for Legendary).
5. **Outro (2 s)** — `ancientnerds.com` and the card ribbon hold.

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
