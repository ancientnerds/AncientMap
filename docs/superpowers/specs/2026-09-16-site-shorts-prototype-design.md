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

## Timeline — loop cut (≈19.5 s, 60 fps, third revision 2026-09-16 evening)

The narration (card text, MiniMax voice) starts at t = 0 and runs over 1–2. The
short is built to loop: the return clip's last frame is the opening's first frame.

1. **Opening (6 s, Mapbox clip `short-opening`)** — satellite globe with labels
   (satellite-streets style, stock atmosphere, roads/POIs/site dots hidden): 1 s
   rotate onto the site from space, 2 s continuous zoom down to z14 while the
   camera tilts, 3 s 3D terrain orbit. The take holds the space pose for 0.1 s
   first; the renderer trims that hold so frame 0 is fully drawn and identical
   to the loop's end pose.
2. **Stills (rest of the narration, ≈11 s)** — gallery photos cover-scaled to the
   full 1080×1920 frame; the crop window starts 20 % off-centre and travels 40 %
   of the overflow with ease-in/out, alternating direction (portrait photos pan
   vertically), ≤3.5 s per still, hard cuts.
3. **Return (3 s, Mapbox clip `short-return`)** — lift straight up over the site
   (terrain on), rise to a flat north-up view with terrain off and the centre
   still pinned on the site, then slide to the exact space pose of the opening.
   The site name is spoken (own TTS file, 0.2 s in) and shown in Orbitron,
   fading out 0.15 s before the end so the loop frames match.

No rarity ribbon, URL or credit line in the picture; Commons attribution goes to
`description.txt` (and the site page's gallery), the Mapbox credit stays in frame.

Rejected earlier the same day: dark Three.js globe at 24 fps with the voice after
the approach and blurred-fill Ken-Burns ("boring"); a hero reveal with ribbon and
URL (dropped for the loop). Recorder lessons live in the memory note
`project-site-shorts-prototype`.

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

## Commands (state 2026-09-17)

```
python -m pipeline.video short --name "Machu Picchu"        # export → images → select → tts → record → render
python -m pipeline.video short --name X --steps render       # any subset; only export needs the DB tunnel
python -m pipeline.video audit --name X                      # 13 checks → video-assets/shorts/<slug>/audit.json
python -m pipeline.video report                              # all audits → video-assets/shorts/AUDIT-REPORT.md
python -m pipeline.video batch --limit 10 [--go]             # Epic+Legendary without a passing audit; --go runs,
                                                             # pauses when MiniMax 5h < 30 % or weekly < 20 %
```

Selection (`shorts_select`): panoramas out, MiniMax VLM judges each image against
the card text (kind, subject, people, text, quality, relevance, illustrated
phrase, 9:16 crop), duplicates out by dhash and subject; the renderer takes the
best N by score and shows them in narration order. Orbit zoom follows the site
type (16 for monuments, 15 for complexes, 13.5 for cities/geoglyphs).

Audio: dry voice (high-pass, 1.8:1 compressor), pre-mixed to a WAV, measured
once (EBU R128) and lifted by a fixed gain to −14 LUFS with a true-peak limiter.
No reverb (user decision), no `loudnorm` (3 s look-ahead cut the spoken name).

## Out of scope for the prototype

Music (user picks later, YouTube Audio Library), batch ordering (rarity vs.
Wikipedia pageviews — decision pending), React card reveal, site-page `<video>`
embed with `VideoObject` schema, Commons video clips, Sketchfab 3D.

## Verification

- `ffprobe` on `machu-picchu.mp4`: 1080×1920, ~22 s, H.264 + AAC.
- Frame stills at each timeline boundary reviewed visually.
- Unit tests green; `ruff` clean; `lint-imports` accepts the new package.
